"""Cor da moldura por raridade (mão/campo do duelo e carta ampliada)."""
from pathlib import Path
import struct
import tempfile
import unittest

try:
    from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
    from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_PC, UC_MIPS_REG_RA, UC_MIPS_REG_S0,
                                    UC_MIPS_REG_S2, UC_MIPS_REG_S6)
except ImportError:
    Uc = None

from fmstudio import ps1_frame_colors as fc
from fmstudio.core import ModError, Project
from fmstudio.deep_extract import exe_pos

HOOK = 0x801CE400
CARDS = {1: {'tipo_id': 0, 'raridade': 'rara'}, 2: {'tipo_id': 5, 'raridade': 'comum'},
         3: {'tipo_id': 20, 'raridade': 'lendaria'}, 4: {'tipo_id': 24}, 5: {'tipo_id': 3, 'raridade': 'epica'}}


def executable():
    exe = bytearray(0x1e0800)
    exe[:8] = b'PS-X EXE'
    for address, word in {**fc.SIGNATURE, **fc.BIG_SIGNATURE}.items():
        struct.pack_into('<I', exe, exe_pos(address, exe, 4), word)
    return bytes(exe)


class FrameColorTests(unittest.TestCase):
    def test_tint_and_settings(self):
        self.assertEqual(fc.tint('#C0C0C0'), (0x80, 0x80, 0x80))
        self.assertEqual(fc.tint('#FFFFFF'), (0xAA, 0xAA, 0xAA))
        self.assertEqual(fc.normalize({})['ativado'], False)
        with self.assertRaises(ModError):
            fc.normalize({'cores': {'rara': 'amarelo'}})
        with self.assertRaises(ModError):
            fc.normalize({'cores': {'magica': '#FFFFFF'}})
        with tempfile.TemporaryDirectory() as folder:
            project = Project.create(Path(folder), 'Teste')
            fc.save_frame_settings(project, {'ativado': True, 'cores': {'comum': '#112233'}})
            loaded = fc.frame_settings(Project.open(Path(folder)))
            self.assertTrue(loaded['ativado'])
            self.assertEqual(loaded['cores']['comum'], '#112233')
            self.assertEqual(loaded['cores']['rara'], fc.DEFAULT_COLORS['rara'])

    def test_classes_skip_spells_and_use_god(self):
        self.assertEqual(fc.card_classes(CARDS), {1: 'rara', 2: 'comum', 4: 'deus', 5: 'epica'})

    def test_table_layout(self):
        colors = dict(fc.DEFAULT_COLORS)
        table = fc.table_bytes(colors, fc.card_classes(CARDS))
        self.assertEqual(len(table), fc.COLORS_SIZE + fc.CARD_SLOTS + 3)
        tiers = table[fc.COLORS_SIZE:]
        self.assertEqual(tiers[1], fc.CLASSES.index('rara') + 1)
        self.assertEqual(tiers[2], 0)   # comum has no color by default
        self.assertEqual(tiers[3], 0)   # spell keeps its frame
        rara = fc.CLASSES.index('rara') + 1
        self.assertEqual(table[4 * rara:4 * rara + 3], bytes(fc.tint(colors['rara'])))

    def test_apply_and_status(self):
        exe = executable()
        self.assertEqual(fc.status(exe), {'status': 'original'})
        patched, report = fc.apply(exe, dict(fc.DEFAULT_COLORS), fc.card_classes(CARDS), HOOK)
        self.assertEqual(fc.status(patched)['status'], 'aplicado')
        self.assertEqual(report['cartas_coloridas'], 3)
        changed = [i for i in range(len(exe)) if exe[i] != patched[i]]
        site = exe_pos(fc.SITE, exe, 4)
        block = exe_pos(HOOK, exe, fc.block_size())
        big = exe_pos(fc.BIG_SITE, exe, 28)
        self.assertTrue(all(site <= i < site + 4 or big <= i < big + 28
                            or block <= i < block + fc.block_size() for i in changed))
        jal = struct.unpack_from('<I', patched, big)[0]
        self.assertEqual(0x80000000 | (jal & 0x03FFFFFF) << 2, HOOK + fc.CODE1_WORDS * 4)
        self.assertEqual(struct.unpack_from('<I', patched, big + 24)[0], 0x92040016)
        self.assertEqual(report['locais'], ['mao_e_campo', 'carta_ampliada'])
        bad = bytearray(exe)
        struct.pack_into('<I', bad, exe_pos(0x80016C7C, bad, 4), 0)
        with self.assertRaisesRegex(ModError, 'diverge'):
            fc.apply(bytes(bad), dict(fc.DEFAULT_COLORS), {}, HOOK)


@unittest.skipIf(Uc is None, 'MIPS verification needs Unicorn')
class FrameColorMipsTests(unittest.TestCase):
    def run_hook(self, card_id, *, face_down=0, digits=0, rgb=0x00808080):
        cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(0, 0x200000)
        block = fc.hook_code(HOOK) + fc.table_bytes(dict(fc.DEFAULT_COLORS), fc.card_classes(CARDS))
        cpu.mem_write(HOOK & 0x1FFFFF, block)
        sprite, obj, index = 0x80150000, 0x80160000, 3
        cpu.mem_write((sprite + 0x14) & 0x1FFFFF, struct.pack('<I', rgb | 0x7F000000))
        cpu.mem_write((obj + 0x67) & 0x1FFFFF, bytes((digits, 0, face_down, index)))
        cpu.mem_write((0x801A7AD8 + index * 28 + 0x0C) & 0x1FFFFF, struct.pack('<h', card_id))
        cpu.reg_write(UC_MIPS_REG_A0, sprite)
        cpu.reg_write(UC_MIPS_REG_S6, obj)
        cpu.emu_start(HOOK, fc.SUBMIT, count=200)
        self.assertEqual(cpu.reg_read(UC_MIPS_REG_PC), fc.SUBMIT)
        return struct.unpack('<I', bytes(cpu.mem_read((sprite + 0x14) & 0x1FFFFF, 4)))[0]

    def test_colors_only_normal_face_up_rarity_cards(self):
        r, g, b = fc.tint(fc.DEFAULT_COLORS['rara'])
        self.assertEqual(self.run_hook(1), 0x7F000000 | b << 16 | g << 8 | r)
        r, g, b = fc.tint(fc.DEFAULT_COLORS['deus'])
        self.assertEqual(self.run_hook(4), 0x7F000000 | b << 16 | g << 8 | r)
        for kwargs in ({'card_id': 2}, {'card_id': 3}, {'card_id': 1, 'face_down': 1},
                       {'card_id': 1, 'digits': 5}, {'card_id': 1, 'rgb': 0x00404040},
                       {'card_id': -1}, {'card_id': 900}):
            self.assertEqual(self.run_hook(**kwargs) & 0xFFFFFF,
                             kwargs.get('rgb', 0x00808080) & 0xFFFFFF, kwargs)

    def run_big(self, card_id, *, rgb=0x00808080, variant=0, callback=fc.CARD_PREVIEW_UPDATE,
                linked=True, slot=7):
        cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(0, 0x200000)
        block = fc.hook_code(HOOK) + fc.table_bytes(dict(fc.DEFAULT_COLORS), fc.card_classes(CARDS))
        cpu.mem_write(HOOK & 0x1FFFFF, block)
        sprite, plate, index, back = 0x80150000, 0x800F0B68, 3, 0x80041784
        cpu.mem_write((sprite + 0x14) & 0x1FFFFF, struct.pack('<I', 0x7F000000))
        cpu.mem_write((plate + 0x0C) & 0x1FFFFF, struct.pack('<II', rgb, callback))
        cpu.mem_write((plate + 0x69) & 0x1FFFFF, bytes((variant,)))
        art = fc.OBJECT_POOL + slot * 0x70
        cpu.mem_write((art + 0x4C) & 0x1FFFFF, struct.pack('<I', fc.BIG_CARD_DRAW))
        cpu.mem_write((art + 0x54) & 0x1FFFFF, struct.pack('<I', plate if linked else 0))
        cpu.mem_write((art + 0x67) & 0x1FFFFF, bytes((index,)))
        cpu.mem_write((fc.RECORDS + index * 0x40 + 0x30) & 0x1FFFFF, struct.pack('<h', card_id))
        cpu.reg_write(UC_MIPS_REG_S0, sprite)
        cpu.reg_write(UC_MIPS_REG_S2, plate)
        cpu.reg_write(UC_MIPS_REG_RA, back)
        cpu.emu_start(HOOK + fc.CODE1_WORDS * 4, back, count=2000)
        self.assertEqual(cpu.reg_read(UC_MIPS_REG_PC), back)
        return struct.unpack('<I', bytes(cpu.mem_read((sprite + 0x14) & 0x1FFFFF, 4)))[0]

    def test_big_card_plate(self):
        r, g, b = fc.tint(fc.DEFAULT_COLORS['rara'])
        self.assertEqual(self.run_big(1), 0x7F000000 | b << 16 | g << 8 | r)
        self.assertEqual(self.run_big(1, slot=95), 0x7F000000 | b << 16 | g << 8 | r)
        r, g, b = fc.tint(fc.DEFAULT_COLORS['epica'])
        self.assertEqual(self.run_big(5, slot=0), 0x7F000000 | b << 16 | g << 8 | r)
        for kwargs, expected in (({'card_id': 2}, 0x808080), ({'card_id': 3}, 0x808080),
                                 ({'card_id': 1, 'variant': 2}, 0x808080),
                                 ({'card_id': 1, 'rgb': 0x404040}, 0x404040),
                                 ({'card_id': 1, 'callback': 0x80012345}, 0x808080),
                                 ({'card_id': 1, 'linked': False}, 0x808080),
                                 ({'card_id': 900}, 0x808080)):
            self.assertEqual(self.run_big(**kwargs), 0x7F000000 | expected, kwargs)


if __name__ == '__main__':
    unittest.main()
