"""Drop fixo por duelista no PS1: rotina MIPS executada num intérprete mínimo (R3000).

O intérprete cobre só as instruções que a rotina usa, com delay slot de desvio,
para rodar sem Unicorn no Windows e no CI.
"""
import struct
import unittest

from fmstudio import ps1_fixed_drop as fd
from fmstudio.mod_data import FIXED_DROP, fixed_drop, normalize_rules
from fmstudio.core import ModError

M = 0x1FFFFF
HOOK = 0x801CE000
RETURN = 0x80000100
ORIGINAL = (0x27BDFFE8, 0xAFB00010)      # addiu sp,-0x18 ; sw s0,0x10(sp)


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


class MiniCpu:
    def __init__(self):
        self.mem = bytearray(0x200000)
        self.r = [0] * 32

    def load(self, address, data):
        self.mem[address & M:(address & M) + len(data)] = data

    def word(self, address):
        return struct.unpack_from('<I', self.mem, address & M)[0]

    def run(self, pc, *, stop, limit=500):
        r, delay = self.r, None
        for _ in range(limit):
            if pc in stop:
                return pc
            ins = self.word(pc)
            nxt = delay if delay is not None else pc + 4
            delay = None
            op, rs, rt = ins >> 26, ins >> 21 & 31, ins >> 16 & 31
            rd, sa, fn, imm = ins >> 11 & 31, ins >> 6 & 31, ins & 63, ins & 0xFFFF
            target = None
            if op == 0:
                if fn == 0: val = r[rt] << sa & 0xFFFFFFFF
                elif fn == 2: val = r[rt] >> sa
                elif fn == 6: val = r[rt] >> (r[rs] & 31)
                elif fn == 8: target, val = r[rs], None
                elif fn == 0x21: val = (r[rs] + r[rt]) & 0xFFFFFFFF
                elif fn == 0x24: val = r[rs] & r[rt]
                elif fn == 0x25: val = r[rs] | r[rt]
                else: raise AssertionError(f'R {fn:#x} em {pc:#x}')
                if val is not None and rd:
                    r[rd] = val
            elif op == 2:
                target = (pc & 0xF0000000) | (ins & 0x03FFFFFF) << 2
            elif op in (4, 5):
                taken = (r[rs] == r[rt]) if op == 4 else (r[rs] != r[rt])
                if taken:
                    target = (pc + 4 + (s16(imm) << 2)) & 0xFFFFFFFF
            elif op == 9:
                r[rt] = (r[rs] + s16(imm)) & 0xFFFFFFFF
            elif op == 11:
                r[rt] = int(r[rs] < (s16(imm) & 0xFFFFFFFF))
            elif op == 12:
                r[rt] = r[rs] & imm
            elif op == 15:
                r[rt] = imm << 16
            elif op in (36, 37, 40, 43):
                addr = (r[rs] + s16(imm)) & 0xFFFFFFFF
                if op == 36: r[rt] = self.mem[addr & M]
                elif op == 37: r[rt] = struct.unpack_from('<H', self.mem, addr & M)[0]
                elif op == 40: self.mem[addr & M] = r[rt] & 0xFF
                else: struct.pack_into('<I', self.mem, addr & M, r[rt])
            else:
                raise AssertionError(f'op {op} em {pc:#x}')
            r[0] = 0
            if target is not None:
                delay = target
            pc = nxt
        raise AssertionError('rotina não terminou')


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
