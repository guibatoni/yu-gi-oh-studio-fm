"""Drop fixo por duelista no PS1: rotina MIPS executada num intérprete mínimo (R3000).

O intérprete cobre só as instruções que a rotina usa, com delay slot de desvio,
para rodar sem Unicorn no Windows e no CI.
"""
import struct
import unittest

from fmstudio import ps1_fixed_drop as fd
from fmstudio.mod_data import FIXED_DROP, fixed_drop, normalize_rules
from fmstudio.core import ModError
from tests.mini_mips import M, MiniCpu

HOOK = 0x801CE000
RETURN = 0x80000100
ORIGINAL = (0x27BDFFE8, 0xAFB00010)      # addiu sp,-0x18 ; sw s0,0x10(sp)


class FixedDropMipsTests(unittest.TestCase):
    def call(self, opponent, drops, *, flags=b'', displaced=ORIGINAL):
        cpu = MiniCpu()
        cpu.load(HOOK, fd.code(HOOK, drops, displaced))
        cpu.load(fd.OPPONENT, bytes([opponent]))
        cpu.load(fd.FLAG_BANK + (fd.FLAG_BASE >> 3), flags.ljust(8, b'\0'))
        cpu.r[31] = RETURN
        cpu.r[2] = 0xDEAD
        cpu.r[29] = 0x801FFF00
        end = cpu.run(HOOK, stop={RETURN, fd.RESUME, 0x800FF000})
        bank = bytes(cpu.mem[(fd.FLAG_BANK + (fd.FLAG_BASE >> 3)) & M:][:8])
        return end, cpu.r[2], bank, cpu

    def test_first_win_gives_card_and_sets_flag(self):
        end, card, bank, _ = self.call(5, {5: 123})
        self.assertEqual((end, card), (RETURN, 123))
        flag = fd.FLAG_BASE + 5
        self.assertEqual(bank[(flag >> 3) - (fd.FLAG_BASE >> 3)], 0x80 >> (flag & 7))

    def test_second_win_uses_normal_drop(self):
        flag = fd.FLAG_BASE + 5
        flags = bytearray(8)
        flags[(flag >> 3) - (fd.FLAG_BASE >> 3)] = 0x80 >> (flag & 7)
        end, value, bank, cpu = self.call(5, {5: 123}, flags=bytes(flags))
        self.assertEqual(end, fd.RESUME)          # seguiu para o sorteio original
        self.assertEqual(value, 0xDEAD)
        self.assertEqual(bank, bytes(flags))
        self.assertEqual(cpu.r[29], 0x801FFF00 - 0x18)   # executou as palavras deslocadas

    def test_other_duelist_and_out_of_range(self):
        for opponent in (6, 0, 39, 200):
            end, value, bank, _ = self.call(opponent, {5: 123})
            self.assertEqual((end, value, bank), (fd.RESUME, 0xDEAD, bytes(8)), opponent)

    def test_each_duelist_has_own_flag(self):
        drops = {1: 10, 2: 20, 38: 380, 39: 390}
        for opponent, card in drops.items():
            end, value, bank, _ = self.call(opponent, drops)
            self.assertEqual((end, value), (RETURN, card))
            self.assertEqual(sum(bin(b).count('1') for b in bank), 1)

    def test_deck_drop_jump_is_kept(self):
        jump = 0x08000000 | (0x800FF000 >> 2) & 0x03FFFFFF
        end, value, _, _ = self.call(7, {5: 1}, displaced=(jump, 0))
        self.assertEqual(end, 0x800FF000)         # SelectDeckDrop do runtime


class FixedDropPatchTests(unittest.TestCase):
    def exe(self):
        # SLUS sintético: cabeçalho de 0x800 bytes, texto a partir de 0x80010000
        data = bytearray(0x800 + 0x1D0000)
        struct.pack_into('<I', data, 0x18, 0x80010000)
        struct.pack_into('<I', data, 0x1C, len(data) - 0x800)
        data[:8] = b'PS-X EXE'
        struct.pack_into('<II', data, 0x800 + fd.DROP_ENTRY - 0x80010000, *ORIGINAL)
        return bytes(data)

    def test_apply_view_and_installed(self):
        exe = self.exe()
        out, report = fd.apply(exe, HOOK, {3: 77})
        self.assertEqual(report['status'], 'aplicado')
        self.assertEqual(fd.installed(out), {3: 77})
        view = fd.runtime_view(out)
        at = 0x800 + fd.DROP_ENTRY - 0x80010000
        self.assertEqual(struct.unpack_from('<II', view, at), ORIGINAL)
        self.assertEqual(fd.runtime_view(exe), exe)
        self.assertEqual(len(fd.code(HOOK, {3: 77}, ORIGINAL)), fd.block_size())

    def test_busy_area_is_rejected(self):
        exe = bytearray(self.exe())
        exe[0x800 + HOOK - 0x80010000] = 1
        with self.assertRaises(ModError):
            fd.apply(bytes(exe), HOOK, {3: 77})


class FixedDropConfigTests(unittest.TestCase):
    def test_settings(self):
        cards = {1: {}, 2: {}, 700: {}}
        rules = normalize_rules({'duelistas': {'4': {FIXED_DROP: '700'}, '5': {FIXED_DROP: 0}}}, cards)
        self.assertEqual(fixed_drop(rules, 4), 700)
        self.assertIsNone(fixed_drop(rules, 5))
        self.assertEqual(fd.fixed_drops(rules, 722), {4: 700})
        self.assertEqual(fd.fixed_drops(rules, 600), {})
        with self.assertRaises(ModError):
            normalize_rules({'duelistas': {'4': {FIXED_DROP: 9}}}, cards)


if __name__ == '__main__':
    unittest.main()
