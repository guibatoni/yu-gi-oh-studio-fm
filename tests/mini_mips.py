"""Intérprete MIPS R3000 mínimo para testar rotinas do mod sem Unicorn (com delay slots)."""
import struct

M = 0x1FFFFF


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

    def run(self, pc, *, stop, limit=500, calls=None):
        """Executa até um endereço de ``stop``; ``calls`` = {endereço: função(cpu)} simula rotinas."""
        calls = calls or {}
        r, delay = self.r, None
        for _ in range(limit):
            if pc in stop:
                return pc
            if pc in calls and delay is None:
                calls[pc](self)
                pc = r[31]
                continue
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
                elif fn == 9: target, val, r[rd] = r[rs], None, pc + 8
                elif fn == 0x21: val = (r[rs] + r[rt]) & 0xFFFFFFFF
                elif fn == 0x23: val = (r[rs] - r[rt]) & 0xFFFFFFFF
                elif fn == 0x26: val = r[rs] ^ r[rt]
                elif fn == 0x2B: val = int(r[rs] < r[rt])
                elif fn == 0x24: val = r[rs] & r[rt]
                elif fn == 0x25: val = r[rs] | r[rt]
                else: raise AssertionError(f'R {fn:#x} em {pc:#x}')
                if val is not None and rd:
                    r[rd] = val
            elif op in (2, 3):
                target = (pc & 0xF0000000) | (ins & 0x03FFFFFF) << 2
                if op == 3:
                    r[31] = pc + 8
            elif op == 1:
                signed = r[rs] - (1 << 32) if r[rs] & 0x80000000 else r[rs]
                if (rt == 0 and signed < 0) or (rt == 1 and signed >= 0):
                    target = (pc + 4 + (s16(imm) << 2)) & 0xFFFFFFFF
            elif op in (6, 7):
                signed = r[rs] - (1 << 32) if r[rs] & 0x80000000 else r[rs]
                if (signed <= 0) if op == 6 else (signed > 0):
                    target = (pc + 4 + (s16(imm) << 2)) & 0xFFFFFFFF
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
            elif op == 13:
                r[rt] = r[rs] | imm
            elif op == 14:
                r[rt] = r[rs] ^ imm
            elif op == 15:
                r[rt] = imm << 16
            elif op in (32, 33, 35, 36, 37, 40, 41, 43):
                addr = (r[rs] + s16(imm)) & 0xFFFFFFFF
                if op == 32: r[rt] = struct.unpack_from('<b', self.mem, addr & M)[0] & 0xFFFFFFFF
                elif op == 33: r[rt] = struct.unpack_from('<h', self.mem, addr & M)[0] & 0xFFFFFFFF
                elif op == 35: r[rt] = struct.unpack_from('<I', self.mem, addr & M)[0]
                elif op == 36: r[rt] = self.mem[addr & M]
                elif op == 37: r[rt] = struct.unpack_from('<H', self.mem, addr & M)[0]
                elif op == 40: self.mem[addr & M] = r[rt] & 0xFF
                elif op == 41: struct.pack_into('<H', self.mem, addr & M, r[rt] & 0xFFFF)
                else: struct.pack_into('<I', self.mem, addr & M, r[rt])
            else:
                raise AssertionError(f'op {op} em {pc:#x}')
            r[0] = 0
            if target is not None:
                delay = target
            pc = nxt
        raise AssertionError('rotina não terminou')


