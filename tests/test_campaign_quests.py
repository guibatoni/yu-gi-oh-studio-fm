import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

try:
    from unicorn import Uc, UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
    from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_GP, UC_MIPS_REG_PC,
                                    UC_MIPS_REG_RA, UC_MIPS_REG_SP)
except ImportError:
    Uc = None

from fmstudio.campaign_quests import (LEGACY_FORMAT, QuestCatalog, compile_table, generate_quests,
                                      normalize_overrides, table_size, verify_quests)
from fmstudio.core import ModError, Project
from fmstudio.deep_extract import exe_pos
from fmstudio.ps1_campaign_quests import (
    DROP15_CODE, DROP15_END, DROP15_SCRATCH, CAMPAIGN_SCENE_SECTOR, CAMPAIGN_SCENE_SECTORS, COMMAND_TABLE, HOOKS, OVERLAY_SIZE,
    OVERLAY_START, OVERLAY_MAGIC, SCENE_PREFIX_SECTORS, SECTOR_BYTES, _scene_patches, append_quest_scene,
    build_quest_overlay, inspect_quest_overlay, install_quest_handlers, quest_settings,
    reserve_quest_handlers, save_quest_settings, foreign_arena_jumps,
)
from fmstudio.campaign_quests import TABLE_START
from fmstudio.ps1_expansion import EXPANDED_LEVELS, EXTRA_SLOTS
from fmstudio.tables import PS1_SUPREME, STATS_ADDR
from fmstudio import ps1_campaign_quest_overlay_blob as quest_blob

GLYPHS = {i: chr(i) for i in range(32, 127)}
QUEST_SECTOR = CAMPAIGN_SCENE_SECTOR + CAMPAIGN_SCENE_SECTORS
MANUAL = {'2': [{'tipo': 'tipo', 'alvo': 8, 'quantidade': 1},
                {'tipo': 'atributo', 'alvo': 1, 'quantidade': 1},
                {'tipo': 'guardian_star', 'alvo': 16, 'quantidade': 1}]}


def sample_quests():
    cards = [dict(id=cid, nome=f'Carta {cid}', tipo_id=8 if cid <= 2 else 0,
                  atributo_id=int(cid == 1), guardian_1_id=1 if cid == 1 else 16 if cid < 4 else 2,
                  guardian_2_id=2, raridade='rara' if cid == 2 else 'comum')
             for cid in range(1, 723)]
    drops = [dict(duelista_id=1, grupo='pow', carta_id=cid, peso=weight)
             for cid, weight in ((1, 1024), (2, 512), (3, 512))]
    drops.extend(dict(duelista_id=op, grupo='pow', carta_id=cid, peso=2048)
                 for op, cid in ((7, 5), (18, 10), (21, 6), (23, 7), (39, 8)))
    starters = [dict(grupo=0, compras=40, carta_id=9, peso=2048)]
    return QuestCatalog.from_rows(cards, drops, starters)


# Stand-in for the Drop x15 resident code (the real bytes come from the user's SLUS).
FAKE_DROP15 = bytes((i * 37 + 11) & 0xFF for i in range(DROP15_END - DROP15_CODE))
FAKE_DROP15_SHA = hashlib.sha256(FAKE_DROP15).hexdigest()


def setUpModule():
    patcher = patch('fmstudio.ps1_campaign_quests.DROP15_CODE_SHA256', FAKE_DROP15_SHA)
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)


def compiled_overlay(requirements=None):
    catalog = sample_quests()
    overrides = requirements or {**MANUAL, '38': MANUAL['2']}
    with patch('fmstudio.ps1_campaign_quests.glyph_map', return_value=(GLYPHS, [])):
        return build_quest_overlay(executable(), catalog, {'seed': 'teste', 'requisitos': overrides},
                                   level_address=EXPANDED_LEVELS)


def executable():
    exe = bytearray(0x1e0800)
    at = exe_pos(DROP15_CODE, exe, len(FAKE_DROP15))
    exe[at:at + len(FAKE_DROP15)] = FAKE_DROP15
    native = [*HOOKS.values(), (COMMAND_TABLE + 4 * 0x19, 0x80038AB0),
              *((address, before) for address, before, _ in _scene_patches(QUEST_SECTOR))]
    for hook, address in native:
        struct.pack_into('<I', exe, exe_pos(hook, exe, 4), address)
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

    def test_seed_and_previous_farmable_drops(self):
        catalog = sample_quests()
        config = generate_quests(catalog, 'seed')
        self.assertEqual(config, generate_quests(catalog, 'seed'))
        self.assertNotEqual(config['quests'], generate_quests(catalog, 'outra')['quests'])
        self.assertEqual([row['oponente_id'] for row in config['quests']], list(range(2, 39)))
        self.assertEqual(config['isentos'], [1])
        for quest in config['quests']:
            for requirement in quest['criterios']:
                proof = requirement['prova']
                self.assertEqual(proof['origem'], 'drop')
                self.assertIn(proof['duelista_id'], quest['antecessores'])
                self.assertLess(proof['duelista_id'], quest['oponente_id'])
        for opponent, card in ((2, 9), (24, 6), (22, 7), (38, 8), (19, 10)):
            with self.assertRaisesRegex(ModError, 'antecessor'):
                generate_quests(catalog, 'seed', {opponent: [
                    {'tipo': 'carta', 'alvo': card, 'quantidade': 1}
                ]})
        actual = generate_quests(catalog, 'seed', {22: [
            {'tipo': 'carta', 'alvo': 6, 'quantidade': 2}
        ]})
        self.assertEqual(actual['quests'][20]['criterios'][0]['prova']['duelista_id'], 21)
        self.assertEqual(generate_quests(catalog, 'seed', MANUAL)['quests'][1:], config['quests'][1:])

    def test_migrating_previous_requirements_leaves_simon_out(self):
        previous = {'formato': LEGACY_FORMAT, 'quests': [
            {'oponente_id': 1, 'criterios': [{'tipo': 'carta', 'alvo': 9, 'quantidade': 20}]},
            {'oponente_id': 2, 'criterios': MANUAL['2']},
        ]}
        self.assertEqual(normalize_overrides(previous), MANUAL)

    def test_requirements_must_fit_the_chest_including_overlapping_targets(self):
        catalog = sample_quests()
        with self.assertRaisesRegex(ModError, 'baú comporta'):
            generate_quests(catalog, 'seed', {2: [
                {'tipo': 'carta', 'alvo': 1, 'quantidade': 150},
                {'tipo': 'atributo', 'alvo': 1, 'quantidade': 61},
            ]})

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

    def test_loader_conflict_old_image_and_archive_readback(self):
        exe = executable()
        regions = [(0x801CE200, 0x801CE800), (0x801CFE00, 0x801CFE80)]
        addresses, free = reserve_quest_handlers(exe, regions)
        for address in addresses.values():
            self.assertFalse(any(lo <= address < hi for lo, hi in free))
        self.assertEqual(inspect_quest_overlay(exe)['status'], 'ausente')
        previous = bytearray(exe)
        for hook in (HOOKS['answer'][0], COMMAND_TABLE + 4 * 0x19):
            struct.pack_into('<I', previous, exe_pos(hook, previous, 4), 0x801CF000)
        self.assertEqual(inspect_quest_overlay(previous)['status'], 'pos_vitoria')
        patched = install_quest_handlers(exe, addresses, QUEST_SECTOR)
        self.assertEqual(inspect_quest_overlay(patched)['status'], 'aguardando_wa')
        with self.assertRaisesRegex(ModError, 'Conflito'):
            install_quest_handlers(patched, addresses, QUEST_SECTOR)
        previous = bytearray(patched)
        for address, before, _ in _scene_patches(QUEST_SECTOR):
            struct.pack_into('<I', previous, exe_pos(address, previous, 4), before)
        struct.pack_into('<2I', previous, exe_pos(addresses['duel'] + 176, previous, 8),
                         0x3C0B3256, 0x356B4F51)
        self.assertEqual(inspect_quest_overlay(previous)['status'], 'carregamento_dialogo_antigo')

        payload, _, _ = compiled_overlay()
        prefix = b'p' * (SCENE_PREFIX_SECTORS * SECTOR_BYTES)
        portraits = b'f' * ((CAMPAIGN_SCENE_SECTORS - SCENE_PREFIX_SECTORS) * SECTOR_BYTES)
        source = bytes(CAMPAIGN_SCENE_SECTOR * SECTOR_BYTES) + prefix + portraits
        wa = bytes(EXTRA_SLOTS * SECTOR_BYTES) + append_quest_scene(source, payload)
        self.assertTrue(wa.endswith(prefix + payload + portraits))
        with patch('fmstudio.ps1_campaign_quests.CAMPAIGN_SCRIPT_HASH',
                   hashlib.sha256(prefix[-2 * SECTOR_BYTES:]).hexdigest()):
            report = inspect_quest_overlay(patched, wa, expanded=True)
            self.assertEqual(report['status'], 'aplicado')
            self.assertEqual(report['setor_cena_wa'], QUEST_SECTOR + EXTRA_SLOTS)
            self.assertEqual(report['setor_wa'], QUEST_SECTOR + EXTRA_SLOTS + SCENE_PREFIX_SECTORS)
            self.assertEqual(inspect_quest_overlay(patched, wa[:-1], expanded=True)['status'], 'divergente')
            end = report['setor_wa'] * SECTOR_BYTES + OVERLAY_SIZE
            wrong = wa[:end - 1] + b'\0' + wa[end:]
            self.assertEqual(inspect_quest_overlay(patched, wrong, expanded=True)['status'], 'divergente')
            self.assertEqual(OVERLAY_MAGIC, b'QOV7')
            old_generation = wa[:end - 4] + b'QOV5' + wa[end:]
            self.assertEqual(inspect_quest_overlay(
                patched, old_generation, expanded=True)['status'], 'divergente')

    def test_scene_fits_three_requirements_for_every_npc_around_drop15(self):
        requirements = MANUAL['2']
        payload, config, table = compiled_overlay({str(npc): requirements for npc in range(2, 39)})
        self.assertEqual(len(payload), OVERLAY_SIZE)
        self.assertEqual(len(config['quests']), 37)
        self.assertTrue(all(len(quest['criterios']) == 3 for quest in config['quests']))
        gap = (DROP15_SCRATCH - quest_blob.ENTRY_POINTS['QuestConfiguration'],
               quest_blob.BSS_END - quest_blob.ENTRY_POINTS['QuestConfiguration'])
        self.assertEqual(table_size(table, gap), len(table))
        self.assertGreater(len(table), gap[1])  # records continue after the mod code

    def test_four_requirements_for_every_npc_is_refused_not_overlapped(self):
        requirements = [*MANUAL['2'], {'tipo': 'carta', 'alvo': 1, 'quantidade': 1}]
        with self.assertRaisesRegex(ModError, 'não cabem'):
            compiled_overlay({str(npc): requirements for npc in range(2, 39)})

    def test_drop15_code_is_preserved_byte_for_byte(self):
        payload, _, _ = compiled_overlay()
        at = DROP15_CODE - OVERLAY_START
        self.assertEqual(payload[at:at + len(FAKE_DROP15)], FAKE_DROP15)
        self.assertFalse(any(payload[DROP15_SCRATCH - OVERLAY_START:at]))       # mod save area
        self.assertFalse(any(payload[quest_blob.BSS_START - OVERLAY_START:
                                     quest_blob.BSS_END - OVERLAY_START]))     # quest state
        self.assertLessEqual(quest_blob.ENTRY_POINTS['QuestConfiguration'] + TABLE_START, DROP15_SCRATCH)
        self.assertGreaterEqual(quest_blob.BSS_START, DROP15_END)

    def test_refuses_wrong_drop15_code_and_foreign_jumps(self):
        exe = bytearray(executable())
        at = exe_pos(DROP15_CODE, exe, 4)
        exe[at] ^= 1
        with patch('fmstudio.ps1_campaign_quests.glyph_map', return_value=(GLYPHS, [])), \
                self.assertRaisesRegex(ModError, 'Drop x15'):
            build_quest_overlay(bytes(exe), sample_quests(), {'seed': 's', 'requisitos': MANUAL},
                                level_address=EXPANDED_LEVELS)
        exe = bytearray(executable())
        site = 0x80021834
        struct.pack_into('<I', exe, exe_pos(site, exe, 4), 0x08000000 | (0x801AA000 >> 2) & 0x03FFFFFF)
        self.assertEqual(foreign_arena_jumps(bytes(exe)), [(site, 0x801AA000)])
        with patch('fmstudio.ps1_campaign_quests.glyph_map', return_value=(GLYPHS, [])), \
                self.assertRaisesRegex(ModError, 'Conflito'):
            build_quest_overlay(bytes(exe), sample_quests(), {'seed': 's', 'requisitos': MANUAL},
                                level_address=EXPANDED_LEVELS)
        # The real Drop x15 hooks (into its own code) are allowed.
        exe = bytearray(executable())
        struct.pack_into('<I', exe, exe_pos(0x80037DFC, exe, 4), 0x0806AB9D)   # j 0x801AAE74
        self.assertEqual(foreign_arena_jumps(bytes(exe)), [])


@unittest.skipIf(Uc is None, 'MIPS verification needs Unicorn')
class CampaignMipsTests(unittest.TestCase):
    def test_donation_return_never_executes_quest_table_as_instructions(self):
        from fmstudio import ps1_campaign_quest_overlay_blob as blob
        # The user's ePSXe PC falls inside quest-criteria data. In the test
        # below we enforce the architectural contract that the answer VM
        # returns *before* the native duel (scene reloader) is called.
        crashing_pc = 0x801AAE80
        self.assertLess(blob.ENTRY_POINTS['QuestConfiguration'], crashing_pc)
        self.assertLess(crashing_pc, OVERLAY_START + OVERLAY_SIZE)
        self.assertLess(blob.ENTRY_POINTS['QuestAnswer'], blob.ENTRY_POINTS['QuestConfiguration'])

    def test_enforced_gate_simon_and_shop_resume(self):
        for opponent, mode, action in ((1, 2, 'native'), (2, 6, 'native'),
                                       (2, 2, 'bad-marker'), (2, 2, 'out-of-window'),
                                       (2, 2, 'pay'), (2, 2, 'early'),
                                       (10, 2, 'tournament'), (38, 2, 'hiding')):
            with self.subTest(opponent=opponent, action=action):
                self.check_route(opponent, mode, action)

    def check_route(self, opponent, mode, action):
        exe = executable()
        addresses, _ = reserve_quest_handlers(exe, [(0x801CF700, 0x801CFF00)])
        patched = install_quest_handlers(exe, addresses, QUEST_SECTOR)
        payload, _, _ = compiled_overlay()
        cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(0, 0x200000)
        channel, shop_channel, stop = 0x80111000, 0x800EB0F8, 0x80010000
        entry = 0x801B1000 if action == 'out-of-window' else 0x801B191F
        trunk, deck, flags = 0x801D0250, 0x801D0200, 0x801D0618

        def write(address, data):
            cpu.mem_write(address & 0x1fffffff, data)

        def read(address, size):
            return bytes(cpu.mem_read(address & 0x1fffffff, size))

        def word(address, value=None):
            if value is not None:
                write(address, struct.pack('<I', value))
            return struct.unpack('<I', read(address, 4))[0]

        def call(name, channel):
            cpu.reg_write(UC_MIPS_REG_GP, 0x8009AF08)
            cpu.reg_write(UC_MIPS_REG_SP, 0x801FF000)
            cpu.reg_write(UC_MIPS_REG_RA, stop)
            cpu.reg_write(UC_MIPS_REG_A0, channel)
            cpu.emu_start(addresses[name], stop, count=1_000_000, timeout=2_000_000)
            self.assertEqual(cpu.reg_read(UC_MIPS_REG_PC), stop)
            self.assertEqual(cpu.reg_read(UC_MIPS_REG_GP), 0x8009AF08)

        def choose(channel, option):
            prompt = word(channel)
            dialogue = read(prompt, 256)
            branch = dialogue.index(b'\xfb\x80') + 2
            target = (prompt & 0xFFFF0000) | struct.unpack_from('<H', dialogue, branch + option * 2)[0]
            self.assertEqual(read(target, 4), b'\xf8\x1a\xf8\x12')
            self.assertEqual(read(target + 5, 1), b'\xff')
            word(channel, target + 4)
            call('answer', channel)

        write(0x80010000, patched[0x800:])
        for address in (HOOKS['duel'][1], HOOKS['shop'][1], 0x8002e5ac, 0x800137E4,
                        0x80014E1C, 0xA0, 0x800393B0, 0x80038B08, 0x800391E4):
            write(address, struct.pack('<II', 0x03E00008, 0))
        write(OVERLAY_START, payload)
        events = []
        entered_overlay = []

        def device(_, address, size, data):
            if address == quest_blob.ENTRY_POINTS['QuestBeforeDuel']:
                entered_overlay.append(address)
            if address in (0x800137E4, 0x80014E1C, 0xA0):
                self.fail('O intérprete de diálogo não deve carregar a cena nem limpar o cache.')
            if address == 0x800393B0:
                word(shop_channel, 0x801B0000)  # First build replaces the text pointer.
                events.append('initialized')
            elif address == 0x80038B08:
                box = cpu.reg_read(UC_MIPS_REG_A0)
                write(box + 0x51, b'\x02')
            elif address == HOOKS['duel'][1]:
                # The real Text_StartCampaignDuel consumes the 6 original
                # operands, sets game mode 3, then Main_RunDuel enters
                # Build Deck / chest (case 0) on the next frame.
                native_ra = cpu.reg_read(UC_MIPS_REG_RA)
                self.assertFalse(0x801A9000 <= native_ra < 0x801AC000,
                                 'O retorno nativo não pode apontar ao overlay descartável.')
                native_channel = cpu.reg_read(UC_MIPS_REG_A0)
                position = word(native_channel)
                op_id, win, loss, terrain, soundlo, soundhi = read(position, 6)
                self.assertEqual(op_id, opponent)
                self.assertEqual((win,loss,terrain,soundlo,soundhi),
                                 (96,97,0,0,0x72))
                events.append(('native', position))
                word(native_channel, position + 6)
                write(0x8009B26C, b'\x03')
                if action not in ('native','bad-marker','out-of-window'):
                    if read(flag,1)[0] & mask:
                        # Simulate the next mode's scene loader replacing the
                        # *entire* quest overlay; any active return into it
                        # would be invalid (user's ePSXe crash).
                        write(OVERLAY_START, bytes(OVERLAY_SIZE))

        cpu.hook_add(UC_HOOK_CODE, device)
        write(entry - 2, bytes((0xF8, 0x0C if action == 'bad-marker' else 0x0D,
                               opponent, 96, 97, 0, 0, 0x72)))
        write(0x8009B26C, bytes([mode]))
        for cid, species, guard in ((1, 8, 1), (2, 8, PS1_SUPREME), (3, 0, PS1_SUPREME)):
            word(STATS_ADDR + 4 * (cid - 1), (species << 26) | (guard << 22))
        write(EXPANDED_LEVELS + 1, b'\x10')
        initial_deck = struct.pack('<40H', 1, 1, 2, 3, 723, 740, *range(100, 134))
        write(deck, initial_deck)
        # Chest counts exclude the deck (card 1 is only in the deck here).
        write(trunk, b'\x00\x01\x01')
        write(trunk + 722, b'\x04')
        flag = flags + ((0x750 + opponent) >> 3)
        mask = 0x80 >> ((0x750 + opponent) & 7)
        if action == 'hiding':
            write(flags + 0x47 // 8, b'\x01')
        word(channel, entry)
        write(channel + 0x34, struct.pack('<H', 0xFC0C))
        write(channel + 0x3e, struct.pack('<H', 240))
        write(channel + 0x42, struct.pack('<H', 32))
        write(channel + 0x5a, b'\x10\x10')
        write(channel + 0x61, b'\x05')
        word(0x8009B340, 0x800393B0)
        call('duel', channel)
        if action in ('native', 'bad-marker', 'out-of-window'):
            self.assertEqual(events, [('native', entry)])
            self.assertEqual(entered_overlay, [],
                             'Entradas inválidas e duelos sem quest devem ir direto ao residente.')
            return
        self.assertEqual(events, [])
        self.assertEqual(word(0x8009B340), 0)
        self.assertEqual(read(channel + 0x34, 2), struct.pack('<H', 0xC008))
        self.assertEqual(read(channel + 0x3e, 2), struct.pack('<H', 288))
        self.assertEqual(read(channel + 0x42, 2), struct.pack('<H', 48))
        self.assertEqual(read(channel + 0x5a, 2), b'\x08\x0c')
        self.assertEqual(read(channel + 0x61, 1), b'\0')
        self.assertEqual(read(flags + 0x20 // 8, 1), b'\0')
        self.assertEqual(read(flags + 0x6e1 // 8, 1), b'\x40')
        if action in ('early', 'hiding', 'tournament'):
            choose(channel, 1)
            self.assertEqual(read(flag, 1), b'\0')
            self.assertEqual(read(trunk, 3), b'\x00\x01\x01')
            if action == 'tournament':
                self.assertEqual(read(0x8009B26C, 1), b'\x02')
                self.assertEqual(read(0x8009B27A, 1), bytes([190]))
                return
            self.assertEqual(read(0x8009B26C, 1), b'\x05')
            self.assertEqual(read(0x8009B363, 1), bytes([13 if action == 'early' else 15]))
            self.assertEqual(read(0x801D0708, 4), struct.pack('<HBB', entry & 0xffff, opponent, 0x4d))
            write(0x8009B26C, b'\x42')
            shop = 0x801A8295 if action == 'early' else 0x801A8B1D
            word(0x8009B290, shop)
            call('shop', 0)
            self.assertEqual(events, ['initialized'])
            self.assertEqual(word(0x8009B290), shop - 1)
            channel = shop_channel
        prompt = word(channel)
        self.assertIn(b'Rever requisitos', read(prompt, 256))
        before_options = read(prompt, 256).index(b'\xf8\x12\xfb\x02')
        word(channel, prompt + before_options + 2)
        write(0x8009B398, struct.pack('<H', 0x00C1))
        call('answer', channel)
        self.assertEqual(read(0x8009B398, 2), b'\x01\0')
        self.assertEqual(word(0x8009B350), 1)
        self.assertEqual(read(trunk, 3), b'\x00\x01\x01')
        word(channel, prompt)
        choose(channel, 0)
        self.assertEqual(word(channel), prompt)
        self.assertEqual(read(flag, 1), b'\0')
        write(trunk, b'\x01\x01\x01')
        choose(channel, 0)
        self.assertEqual(read(word(channel), 256).count(b'1/1'), 3)
        # A SINGLE confirm must donate and hand control to the resident
        # adapter, which uses the original six-byte duel descriptor. No
        # rewriting the VM cursor to F8 0D, no second VM tick needed.
        before_events = list(events)
        choose(channel, 0)
        self.assertEqual(events, before_events + [('native', entry)])
        self.assertEqual(word(channel), entry + 6)
        self.assertEqual(read(entry - 2, 2), b'\xf8\x0d')
        self.assertEqual(read(0x8009B26C,1), b'\x03')
        self.assertEqual(word(0x8009B350), 1)
        self.assertEqual(read(0x8009B398, 2), b'\x01\0')
        self.assertEqual(read(trunk, 3), b'\x00\x00\x00')
        self.assertEqual(read(deck, 80), initial_deck)
        self.assertEqual(read(trunk+722, 1), b'\x04')
        self.assertEqual(read(flag, 1), bytes([mask]))
        self.assertEqual(read(0x801D070B, 1), b'\0') # handoff flag consumed
        self.assertEqual(read(OVERLAY_START + 4, 4), b'\0'*4)
        # Mode 3's next frame must enter Build Deck without donating twice.
        overlay_entries = len(entered_overlay)
        write(0x8009B26C, b'\x02')
        word(channel, entry)
        call('duel', channel)
        self.assertEqual(len(entered_overlay), overlay_entries)
        self.assertEqual(events[-1], ('native', entry))
        self.assertEqual(read(trunk, 3), b'\x00\x00\x00')
