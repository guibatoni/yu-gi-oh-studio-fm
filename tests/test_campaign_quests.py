from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

try:
    from unicorn import Uc, UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
    from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_A2, UC_MIPS_REG_A3,
                                    UC_MIPS_REG_PC, UC_MIPS_REG_RA, UC_MIPS_REG_SP,
                                    UC_MIPS_REG_T1)
except ImportError:
    Uc = None

from fmstudio.campaign_quests import QuestCatalog, compile_table, generate_quests, table_size, verify_quests
from fmstudio.core import ModError, Project
from fmstudio.deep_extract import exe_pos
from fmstudio.ps1_campaign_quests import (
    COMMAND_TABLE, HOOKS, OVERLAY_SECTORS, OVERLAY_START, build_quest_overlay, inspect_quest_overlay,
    install_quest_handlers, quest_settings, reserve_quest_handlers, save_quest_settings,
)
from fmstudio.ps1_expansion import EXPANDED_LEVELS, EXTRA_SLOTS
from fmstudio.tables import PS1_SUPREME, STATS_ADDR

GLYPHS = {i: chr(i) for i in range(32, 127)}
MANUAL = {'1': [{'tipo': 'tipo', 'alvo': 8, 'quantidade': 1},
                {'tipo': 'atributo', 'alvo': 1, 'quantidade': 1},
                {'tipo': 'guardian_star', 'alvo': 16, 'quantidade': 1}]}


def sample_quests():
    cards = [dict(id=cid, nome=f'Carta {cid}', tipo_id=8 if cid <= 2 else 0,
                  atributo_id=int(cid == 1), guardian_1_id=1 if cid == 1 else 16 if cid < 4 else 2,
                  guardian_2_id=2, raridade='rara' if cid == 2 else 'comum')
             for cid in range(1, 723)]
    drops = [dict(duelista_id=op, grupo='pow', carta_id=cid, peso=2048)
             for op, cid in ((1, 4), (7, 5), (21, 6), (23, 7), (39, 8))]
    starters = [dict(grupo=0, compras=40, carta_id=cid, peso=weight)
                for cid, weight in ((1, 1024), (2, 512), (3, 512))]
    return QuestCatalog.from_rows(cards, drops, starters)


def compiled_overlay():
    catalog = sample_quests()
    with patch('fmstudio.ps1_campaign_quests.glyph_map', return_value=(GLYPHS, [])):
        return build_quest_overlay(b'', catalog, {'seed': 'teste', 'requisitos': MANUAL},
                                   level_address=EXPANDED_LEVELS)


def executable():
    exe = bytearray(0x1e0800)
    for op, address in HOOKS.items():
        struct.pack_into('<I', exe, exe_pos(COMMAND_TABLE + 4 * op, exe, 4), address)
    return bytes(exe)


class CampaignQuestsTests(unittest.TestCase):
    def test_config_is_opt_in_and_persists_through_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Project.create(Path(folder), 'Teste')
            self.assertFalse(quest_settings(project)['ativado'])
            settings = save_quest_settings(project, enabled=True, seed=' campanha 2 ', requirements=MANUAL)
            self.assertEqual(settings['seed'], 'campanha 2')
            self.assertEqual(quest_settings(Project.open(Path(folder))), settings)
            with self.assertRaises(ModError):
                save_quest_settings(project, enabled=True, seed='', requirements=MANUAL)
            self.assertEqual(quest_settings(project), settings)

    def test_seed_and_previous_guaranteed_drops(self):
        catalog = sample_quests()
        config = generate_quests(catalog, 'seed')
        self.assertEqual(config, generate_quests(catalog, 'seed'))
        self.assertNotEqual(config['quests'], generate_quests(catalog, 'outra')['quests'])
        self.assertEqual(len(config['quests']), 38)
        for quest in config['quests']:
            for requirement in quest['criterios']:
                proof = requirement['prova']
                if proof['origem'] == 'drop':
                    self.assertIn(proof['duelista_id'], quest['antecessores'])
                    self.assertLess(proof['duelista_id'], quest['oponente_id'])
        for opponent, card in ((2, 4), (24, 6), (22, 7), (38, 8)):
            with self.assertRaisesRegex(ModError, 'antecessor'):
                generate_quests(catalog, 'seed', {opponent: [
                    {'tipo': 'carta', 'alvo': card, 'quantidade': 1}
                ]})
        actual = generate_quests(catalog, 'seed', {22: [
            {'tipo': 'carta', 'alvo': 6, 'quantidade': 2}
        ]})
        self.assertEqual(actual['quests'][21]['criterios'][0]['prova']['duelista_id'], 21)

    def test_binary_offsets_and_changes_in_real_drop_proof(self):
        catalog = sample_quests()
        config = generate_quests(catalog, 'mips', MANUAL)
        table = compile_table(config, catalog, GLYPHS)
        self.assertEqual(table_size(table), len(table))
        self.assertEqual(verify_quests(config, catalog), config)
        with self.assertRaises(ModError):
            table_size(table[:-1])
        catalog.drops[7, 'pow'][5] -= 1
        with self.assertRaisesRegex(ModError, 'divergem'):
            verify_quests(config, catalog)

    def test_loader_and_table_readback_detect_conflict_or_corruption(self):
        exe = executable()
        regions = [(0x801CE200, 0x801CE800), (0x801CFE00, 0x801CFE80)]
        addresses, free = reserve_quest_handlers(exe, regions)
        for address in addresses.values():
            self.assertFalse(any(lo <= address < hi for lo, hi in free))
        self.assertEqual(inspect_quest_overlay(exe)['status'], 'ausente')
        patched = install_quest_handlers(exe, addresses, 2)
        self.assertEqual(inspect_quest_overlay(patched)['status'], 'aguardando_wa')
        with self.assertRaisesRegex(ModError, 'Conflito'):
            install_quest_handlers(patched, addresses, 2)
        payload, _, _ = compiled_overlay()
        wa = bytes((2 + EXTRA_SLOTS) * 2048) + payload
        self.assertEqual(inspect_quest_overlay(patched, wa, expanded=True)['status'], 'aplicado')
        self.assertEqual(inspect_quest_overlay(patched, wa[:-1], expanded=True)['status'], 'divergente')


@unittest.skipIf(Uc is None, 'MIPS verification needs Unicorn')
class CampaignMipsTests(unittest.TestCase):
    def test_loader_overlapping_goals_and_no_deck_debit(self):
        for full_transfer, mode, spares in ((True, 2, True), (True, 2, False),
                                            (False, 2, True), (True, 6, True)):
            with self.subTest(full_transfer=full_transfer, mode=mode, spares=spares):
                self.check_route(full_transfer, mode, spares)

    def check_route(self, full_transfer, mode, spares):
        exe = executable()
        addresses, _ = reserve_quest_handlers(exe, [(0x801CF800, 0x801CFF00)])
        patched = install_quest_handlers(exe, addresses, 18432)
        payload, _, _ = compiled_overlay()
        cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(0, 0x200000)
        channel, victory, stop = 0x80111000, 0x801B191F, 0x80010000
        trunk, deck, flags = 0x801D0250, 0x801D0200, 0x801D0618

        def write(address, data):
            cpu.mem_write(address & 0x1fffffff, data)

        def read(address, size):
            return bytes(cpu.mem_read(address & 0x1fffffff, size))

        def word(address, value=None):
            if value is not None:
                write(address, struct.pack('<I', value))
            return struct.unpack('<I', read(address, 4))[0]

        def call(address):
            cpu.reg_write(UC_MIPS_REG_SP, 0x801FF000)
            cpu.reg_write(UC_MIPS_REG_RA, stop)
            cpu.reg_write(UC_MIPS_REG_A0, channel)
            cpu.emu_start(address, stop, count=1_000_000, timeout=2_000_000)
            self.assertEqual(cpu.reg_read(UC_MIPS_REG_PC), stop)

        write(0x80010000, patched[0x800:])
        for address in (HOOKS[0x19], 0x800137E4, 0xA0):
            write(address, struct.pack('<II', 0x03E00008, 0))
        # Request returns nonzero after checking the native argument positions.
        write(0x80014E1C, struct.pack('<III', 0x24020001, 0x03E00008, 0))
        events = []

        def device(_, address, size, data):
            if address == 0x80014E1C:
                self.assertEqual(cpu.reg_read(UC_MIPS_REG_A2), 18432)
                self.assertEqual(cpu.reg_read(UC_MIPS_REG_A3), OVERLAY_SECTORS)
                self.assertEqual(word(cpu.reg_read(UC_MIPS_REG_SP) + 24), OVERLAY_START)
                write(OVERLAY_START, payload if full_transfer else payload[:-2048])
                events.append('read')
            elif address == 0xA0:
                self.assertEqual(cpu.reg_read(UC_MIPS_REG_T1), 0x44)
                events.append('flush')

        cpu.hook_add(UC_HOOK_CODE, device)
        write(victory, b'\x01\xff')
        write(0x8009B26C, bytes([mode]))
        write(0x8009B361, b'\x01\x00')
        for cid, species, guard in ((1, 8, 1), (2, 8, PS1_SUPREME), (3, 0, PS1_SUPREME)):
            word(STATS_ADDR + 4 * (cid - 1), (species << 26) | (guard << 22))
        write(EXPANDED_LEVELS + 1, b'\x10')  # The only eligible Dark card.
        initial_deck = struct.pack('<40H', 1, 1, 2, 3, 723, 740, *range(100, 134))
        write(deck, initial_deck)
        inventory = b'\x03\x02\x02' if spares else b'\x03\x01\x01'
        write(trunk, inventory)
        write(trunk + 722, b'\x04')
        word(channel, victory)
        call(addresses[0x19])
        self.assertEqual(events, ([] if mode != 2 else ['read', 'flush'] if full_transfer else ['read']))
        if mode != 2 or not full_transfer:
            self.assertEqual(word(channel), victory)
            self.assertEqual(read(trunk, 3), inventory)
            return
        prompt = word(channel)
        dialogue = read(prompt, 256)
        self.assertEqual(dialogue.count(b'1/1'), 3 if spares else 1)
        self.assertIn(b'Confirmar doacao' if spares else b'Entregar com reserva', dialogue)
        flag = flags + (0x751 >> 3)
        self.assertEqual(read(flag, 1), b'\0')
        branch = dialogue.index(b'\xfb\x80') + 2
        for option in (1, 0):
            target = (prompt & 0xFFFF0000) | struct.unpack_from('<H', dialogue, branch + 2 * option)[0]
            word(channel, target + 4)
            call(addresses[0x12])
            if option:
                self.assertEqual(read(trunk, 3), inventory)
                self.assertEqual(word(channel), prompt)
        self.assertEqual(read(trunk, 3), b'\x02\x01\x01')
        self.assertEqual(read(trunk + 722, 1), b'\x04')
        self.assertEqual(read(deck, 80), initial_deck)
        self.assertEqual(read(flag, 1), b'\x40')
        self.assertEqual(word(channel), victory)
        call(addresses[0x19])
        self.assertEqual(word(channel), victory)
