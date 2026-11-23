"""Dígitos reduzidos do HUD de LP (PS1), executados no Unicorn.

Roda a func_80016D2C retail com os dois patches (jal do bloco novo e avanço
de 6 px) e compara cada POLY_FT4 emitido com o SPRT que o GsSortFastSprite
retail (bytes reais abaixo) gera para o mesmo sprite.
"""
import struct
import unittest

try:
    from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
    from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2,
                                    UC_MIPS_REG_A3, UC_MIPS_REG_RA, UC_MIPS_REG_SP)
except ImportError:  # pragma: no cover
    Uc = None

from fmstudio.ps1_lp_hud import (
    ADVANCE_PC, DIGIT_ADVANCE, DIGIT_FUNC, DIGIT_H, DIGIT_W, DRAW_OFFSET,
    GS_SORT_FAST_SPRITE, PACKET_POINTER, RETAIL_DIGIT_WORDS, SORT_CALL, _func_patches,
    quad_code,
)

TEXT_ENCODE_DIGITS = 0x800357E8
OT_TABLE = 0x800E9D90
HOOK = 0x801D0000
STYLE = 0x80100000
SPRITE = 0x80100100
OT = 0x80110000
OT_ENTRIES = 0x80111000
PACKETS = 0x80120000
RETURN = 0x80000100
M = 0x1FFFFF

GS_SORT_FAST_SPRITE_RETAIL = (
    0x00805821, 0x00A06821, 0x8D6C0000, 0x00000000, 0x05800058, 0x00C07021,
    0x95620008, 0x00000000, 0x10400054, 0x00000000, 0x9562000A, 0x00000000,
    0x10400050, 0x3C04E100, 0x34840200, 0x3C0A00FF, 0x000C1442, 0x30420180,
    0x00441025, 0x000C25C2, 0x30840060, 0x354AFFFF, 0x9563000C, 0x3C078010,
    0x8CE7E240, 0x95650006, 0x3063001F, 0x00621825, 0x00641825, 0x95620004,
    0x00EA5024, 0xACE30004, 0x3C038010, 0x9463E0BC, 0x3C048010, 0x9484E0BE,
    0x91660016, 0x91680015, 0x91690014, 0x00431021, 0x00A42821, 0x3042FFFF,
    0x00052C00, 0x00451025, 0xACE2000C, 0x000C1142, 0x3C030200, 0x00431024,
    0x000C1C80, 0x3C040100, 0x00641824, 0x3C046400, 0x00641825, 0x00431025,
    0x00063400, 0x00461025, 0x00084200, 0x00481025, 0x00491025, 0xACE20008,
    0x9163000F, 0x9162000E, 0x85640012, 0x00031A00, 0x00431025, 0x00042580,
    0x00441025, 0x85630010, 0x3C04003F, 0x00031B00, 0x00641824, 0x00431025,
    0xACE20010, 0x9562000A, 0x95630008, 0x00021400, 0x00621825, 0xACE30014,
    0x31C3FFFF, 0x00031880, 0x8DA40004, 0x8DA20008, 0x00832021, 0x00021080,
    0x00822023, 0x8C820000, 0x3C030500, 0x00431021, 0xACE20000, 0x24E70018,
    0xAC8A0000, 0x3C018010, 0xAC27E240, 0x03E00008, 0x00000000,
)


@unittest.skipIf(Uc is None, 'Unicorn não instalado')
class SmallDigitTests(unittest.TestCase):
    def cpu(self, attr=0x09000000, x=200, y=50):
        cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(0, 0x200000)
        cpu.mem_write(GS_SORT_FAST_SPRITE & M, struct.pack(f'<{len(GS_SORT_FAST_SPRITE_RETAIL)}I',
                                                            *GS_SORT_FAST_SPRITE_RETAIL))
        cpu.mem_write(TEXT_ENCODE_DIGITS & M, struct.pack('<2I', 0x03E00008, 0))
        cpu.mem_write(HOOK & M, quad_code(HOOK))
        cpu.mem_write(PACKET_POINTER & M, struct.pack('<I', PACKETS))
        cpu.mem_write(DRAW_OFFSET & M, struct.pack('<hh', 3, -2))
        cpu.mem_write((STYLE + 0x14) & M, struct.pack('<H', 5))       # prioridade
        cpu.mem_write((STYLE + 0x17) & M, bytes([3]))                  # ot_index
        cpu.mem_write((OT_TABLE + 12) & M, struct.pack('<I', OT))
        cpu.mem_write(OT & M, struct.pack('<3I', 4, OT_ENTRIES, 0))    # length, org, offset
        for i in range(16):
            cpu.mem_write((OT_ENTRIES + 4 * i) & M, struct.pack('<I', 0x00ABCDE0 + i))
        # sprite de rascunho como o jogo o monta
        cpu.mem_write(SPRITE & M, struct.pack('<IhhHHHBBhhBBB', attr, x, y, 8, 8, 0x1E,
                                              0, 0x58, 0x100, 0xF1, 0x80, 0x70, 0x60))
        return cpu

    def call(self, cpu, pc, regs):
        for reg, value in regs.items():
            cpu.reg_write(reg, value)
        cpu.reg_write(UC_MIPS_REG_SP, 0x80180000)
        cpu.reg_write(UC_MIPS_REG_RA, RETURN)
        cpu.emu_start(pc, RETURN, timeout=2_000_000)

    def test_quad_matches_fast_sprite_except_size(self):
        for attr in (0x09000000, 0x49000040, 0x31000000):
            with self.subTest(attr=hex(attr)):
                cpu = self.cpu(attr)
                args = {UC_MIPS_REG_A0: SPRITE, UC_MIPS_REG_A1: OT, UC_MIPS_REG_A2: 5}
                self.call(cpu, GS_SORT_FAST_SPRITE, args)
                sprt = struct.unpack('<6I', cpu.mem_read(PACKETS & M, 24))
                self.call(cpu, HOOK, args)
                quad = struct.unpack('<10I', cpu.mem_read((PACKETS + 24) & M, 40))
                self.assertEqual(struct.unpack('<I', cpu.mem_read(PACKET_POINTER & M, 4))[0],
                                 PACKETS + 24 + 40)
                # OT: o quad entra na mesma entrada e aponta para o SPRT anterior
                entry = OT_ENTRIES + 4 * 5 - 4 * 0
                self.assertEqual(struct.unpack('<I', cpu.mem_read(entry & M, 4))[0],
                                 (PACKETS + 24) & 0xFFFFFF)
                self.assertEqual(quad[0], 0x09000000 | (PACKETS & 0xFFFFFF))
                self.assertEqual(quad[1] & 0x03FFFFFF, sprt[2] & 0x03FFFFFF)   # flags + cor
                self.assertEqual(quad[1] >> 24 & 0xFC, 0x2C)
                x, y = sprt[3] & 0xFFFF, sprt[3] >> 16
                self.assertEqual(quad[2], sprt[3])
                self.assertEqual(quad[4], (x + DIGIT_W) | y << 16)
                self.assertEqual(quad[6], x | (y + DIGIT_H) << 16)
                self.assertEqual(quad[8], (x + DIGIT_W) | (y + DIGIT_H) << 16)
                self.assertEqual(quad[3], sprt[4])                             # uv0 + CLUT
                self.assertEqual(quad[5] >> 16, sprt[1] & 0x1FF)               # tpage = E1
                u, v = sprt[4] & 0xFF, sprt[4] >> 8 & 0xFF
                self.assertEqual(quad[5] & 0xFFFF, (u + 8) | v << 8)
                self.assertEqual(quad[7] & 0xFFFF, u | (v + 8) << 8)
                self.assertEqual(quad[9] & 0xFFFF, (u + 8) | (v + 8) << 8)

    def test_hidden_sprite_emits_nothing(self):
        cpu = self.cpu(attr=0x89000000)
        self.call(cpu, HOOK, {UC_MIPS_REG_A0: SPRITE, UC_MIPS_REG_A1: OT, UC_MIPS_REG_A2: 5})
        self.assertEqual(struct.unpack('<I', cpu.mem_read(PACKET_POINTER & M, 4))[0], PACKETS)

    def test_patched_digit_loop_draws_five_quads_six_pixels_apart(self):
        cpu = self.cpu(x=100)
        func = list(RETAIL_DIGIT_WORDS)
        for pc, old, new in _func_patches(HOOK):
            i = (pc - DIGIT_FUNC) // 4
            self.assertEqual(func[i], old)
            func[i] = new
        cpu.mem_write(DIGIT_FUNC & M, struct.pack('<44I', *func))

        def encode(uc, address, size, _):
            if address == TEXT_ENCODE_DIGITS:
                v, n = uc.reg_read(UC_MIPS_REG_A0), uc.reg_read(UC_MIPS_REG_A1)
                uc.mem_write(uc.reg_read(UC_MIPS_REG_A2) & M,
                             bytes((v // 10 ** i) % 10 for i in range(n)))
        cpu.hook_add(UC_HOOK_CODE, encode)
        self.call(cpu, DIGIT_FUNC, {UC_MIPS_REG_A0: STYLE, UC_MIPS_REG_A1: SPRITE,
                                    UC_MIPS_REG_A2: 20345, UC_MIPS_REG_A3: 5})
        quads = [struct.unpack_from('<10I', cpu.mem_read((PACKETS + 40 * i) & M, 40))
                 for i in range(5)]
        self.assertEqual([(q[2] & 0xFFFF) - 3 for q in quads],
                         [100 + DIGIT_ADVANCE * i for i in range(5)])
        self.assertEqual([(q[3] & 0xFF) // 8 for q in quads], [2, 0, 3, 4, 5])
        self.assertEqual(DIGIT_ADVANCE * 5, 30)
        self.assertEqual(struct.unpack('<I', cpu.mem_read(PACKET_POINTER & M, 4))[0],
                         PACKETS + 5 * 40)


if __name__ == '__main__':
    unittest.main()
