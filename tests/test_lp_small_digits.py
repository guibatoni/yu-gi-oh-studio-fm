"""Executa a nova func_80016D2C (dígitos reduzidos do HUD de LP) no Unicorn."""
import struct
import unittest

try:
    from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
    from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2,
                                    UC_MIPS_REG_A3, UC_MIPS_REG_PC, UC_MIPS_REG_RA,
                                    UC_MIPS_REG_SP)
except ImportError:  # pragma: no cover
    Uc = None

from fmstudio.ps1_lp_hud import (
    DIGIT_ADVANCE, DIGIT_FUNC, GS_SORT_SPRITE, OT_TABLE, SCALE_X, SCALE_Y,
    TEXT_ENCODE_DIGITS, small_digit_words,
)

BASE = 0x80000000
STYLE = 0x80100000
SPRITE = 0x80100100
RETURN = 0x80000100


@unittest.skipIf(Uc is None, 'Unicorn não instalado')
class SmallDigitTests(unittest.TestCase):
    def run_digits(self, value, count, x=200):
        cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(BASE, 0x200000)
        cpu.mem_write(DIGIT_FUNC, struct.pack('<44I', *small_digit_words()))
        for stub in (TEXT_ENCODE_DIGITS, GS_SORT_SPRITE):
            cpu.mem_write(stub, struct.pack('<2I', 0x03E00008, 0))   # jr ra; nop
        # style: ot_index (+0x17) = 3, prioridade (+0x14) = 0x55
        cpu.mem_write(STYLE + 0x14, struct.pack('<H', 0x55))
        cpu.mem_write(STYLE + 0x17, bytes([3]))
        cpu.mem_write(OT_TABLE + 12, struct.pack('<I', 0x80123450))
        # sprite de rascunho como o jogo o monta
        cpu.mem_write(SPRITE, struct.pack('<IhhHHH', 0x09000000, x, 50, 8, 8, 0x1E))
        cpu.mem_write(SPRITE + 0x18, b'\xAA' * 12)
        calls = []

        def hook(uc, address, size, _):
            if address == TEXT_ENCODE_DIGITS:
                out = uc.reg_read(UC_MIPS_REG_A2)
                n = uc.reg_read(UC_MIPS_REG_A1)
                v = uc.reg_read(UC_MIPS_REG_A0)
                digits = bytes((v // 10 ** i) % 10 for i in range(n))  # [0] = unidade
                uc.mem_write(out, digits)
            elif address == GS_SORT_SPRITE:
                sp = uc.reg_read(UC_MIPS_REG_A0)
                raw = uc.mem_read(sp, 0x24)
                calls.append({
                    'sprite': sp, 'ot': uc.reg_read(UC_MIPS_REG_A1),
                    'pri': uc.reg_read(UC_MIPS_REG_A2),
                    'attr': struct.unpack_from('<I', raw, 0)[0],
                    'x': struct.unpack_from('<h', raw, 4)[0],
                    'u': raw[0x0E],
                    'mxmy': struct.unpack_from('<I', raw, 0x18)[0],
                    'scale': struct.unpack_from('<HH', raw, 0x1C),
                    'rotate': struct.unpack_from('<I', raw, 0x20)[0],
                })

        cpu.hook_add(UC_HOOK_CODE, hook)
        cpu.reg_write(UC_MIPS_REG_A0, STYLE)
        cpu.reg_write(UC_MIPS_REG_A1, SPRITE)
        cpu.reg_write(UC_MIPS_REG_A2, value)
        cpu.reg_write(UC_MIPS_REG_A3, count)
        cpu.reg_write(UC_MIPS_REG_SP, 0x80180000)
        cpu.reg_write(UC_MIPS_REG_RA, RETURN)
        cpu.emu_start(DIGIT_FUNC, RETURN, timeout=2_000_000)
        self.assertEqual(cpu.reg_read(UC_MIPS_REG_SP), 0x80180000)
        return calls

    def test_five_lp_digits_fit_thirty_pixels(self):
        calls = self.run_digits(20000 + 345, 5, x=100)
        self.assertEqual([c['u'] // 8 for c in calls], [2, 0, 3, 4, 5])
        self.assertEqual([c['x'] for c in calls],
                         [100 + DIGIT_ADVANCE * i for i in range(5)])
        self.assertEqual(DIGIT_ADVANCE * 5, 30)
        for c in calls:
            self.assertEqual(c['sprite'], SPRITE)
            self.assertEqual(c['ot'], 0x80123450)
            self.assertEqual(c['pri'], 0x55)
            self.assertEqual(c['attr'], 0x01000000)      # bit 27 limpo: escala vale
            self.assertEqual(c['scale'], (SCALE_X, SCALE_Y))
            self.assertEqual((c['mxmy'], c['rotate']), (0, 0))

    def test_deck_counter_two_digits(self):
        calls = self.run_digits(37, 2, x=120)
        self.assertEqual([c['u'] // 8 for c in calls], [3, 7])
        self.assertEqual([c['x'] for c in calls], [120, 126])

    def test_zero_count_draws_nothing(self):
        self.assertEqual(self.run_digits(5, 0), [])


if __name__ == '__main__':
    unittest.main()
