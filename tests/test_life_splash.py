"""Animação de cura/dano ao entrar em campo (PS1): MIPS executado no Unicorn."""
import struct
import unittest

from fmstudio import ps1_life_splash as ls

try:
    from unicorn import UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32, Uc
    from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_PC, UC_MIPS_REG_RA, UC_MIPS_REG_SP,
                                    UC_MIPS_REG_V0)
except ImportError:  # pragma: no cover - CI instala o Unicorn
    Uc = None

HOOK = 0x801D0000
REQUEST = 0x80150000
END = 0x80010000


class LayoutTests(unittest.TestCase):
    def test_block_and_signature(self):
        block = ls.code(HOOK)
        self.assertEqual(len(block), ls.block_size())
        names = ls.labels(HOOK)
        self.assertEqual(names['summon'], HOOK)
        self.assertTrue(HOOK < names['tick'] < names['data'])
        self.assertEqual(block[names['data'] - HOOK:], bytes(ls.DATA_SIZE))
        self.assertEqual(ls.SIGNATURE[ls.SUMMON_SITE], 0x08073F7E)   # j 0x801CFDF8

    def test_apply_patches_sites(self):
        exe = bytearray(0x800 + 0x1F0000)
        struct.pack_into('<4I', exe, 0x10, 0x80010000, 0, 0, len(exe) - 0x800)  # cabeçalho PS-X EXE
        struct.pack_into('<I', exe, 0x18, 0x80010000)
        struct.pack_into('<I', exe, 0x1C, len(exe) - 0x800)
        for address, word in ls.SIGNATURE.items():
            struct.pack_into('<I', exe, 0x800 + address - 0x80010000, word)
        patched, report = ls.apply(bytes(exe), HOOK)
        self.assertEqual(report['status'], 'aplicado')
        tick = struct.unpack_from('<I', patched, 0x800 + ls.TICK_SITE - 0x80010000)[0]
        self.assertEqual(0x80000000 | (tick & 0x03FFFFFF) << 2, ls.labels(HOOK)['tick'])
        self.assertEqual(ls.status(patched)['status'], 'aplicado')
        with self.assertRaises(Exception):
            ls.apply(patched, HOOK)                         # sítios já trocados: não reaplica


@unittest.skipIf(Uc is None, 'Unicorn não instalado')
class SplashMipsTests(unittest.TestCase):
    def setUp(self):
        self.cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        self.cpu.mem_map(0, 0x200000)
        self.cpu.mem_write(HOOK & 0x1FFFFF, ls.code(HOOK))
        self.created, self.sounds = [], []
        self.lp_change = {0: 0, 1: 0}
        for address in (ls.SUMMON_DAMAGE, ls.CREATE_REQUEST, ls.SE_PLAY, ls.UPDATE_REQUESTS):
            self.cpu.hook_add(UC_HOOK_CODE, self._fake, begin=address, end=address)
        self.set_lp(8000, 8000)

    # memória
    def w(self, address, fmt, *values):
        self.cpu.mem_write(address & 0x1FFFFF, struct.pack(fmt, *values))

    def r(self, address, fmt):
        return struct.unpack(fmt, bytes(self.cpu.mem_read(address & 0x1FFFFF, struct.calcsize(fmt))))[0]

    def set_lp(self, a, b):
        self.w(ls.LP[0], '<H', a)
        self.w(ls.LP[1], '<H', b)

    def lp(self):
        return self.r(ls.LP[0], '<H'), self.r(ls.LP[1], '<H')

    def bank(self):
        for i, value in enumerate((200, 500, 1000, 2000, 5000)):
            self.w(ls.HEAL_NUMBERS + i * 0x24, '<i', value)
        for i, value in enumerate((-50, -100, -200, -500, -1000)):
            self.w(ls.DAMAGE_NUMBERS + i * 0x1E, '<h', value)

    def _fake(self, cpu, address, size, _):
        a0 = cpu.reg_read(UC_MIPS_REG_A0)
        if address == ls.SUMMON_DAMAGE:
            for side in (0, 1):
                value = self.r(ls.LP[side], '<H') + self.lp_change[side]
                self.w(ls.LP[side], '<H', max(0, min(0xFFFF, value)))
        elif address == ls.CREATE_REQUEST:
            self.created.append(a0)
            self.w(REQUEST, '<hhh', 0, 0, 0)
            self.w(REQUEST + 0x18, '<hhB', a0, 0, 0x80)
            cpu.reg_write(UC_MIPS_REG_V0, REQUEST)
        elif address == ls.SE_PLAY:
            self.sounds.append(a0)
        elif address == ls.UPDATE_REQUESTS:
            cpu.reg_write(UC_MIPS_REG_V0, 7)
        cpu.reg_write(UC_MIPS_REG_PC, cpu.reg_read(UC_MIPS_REG_RA))

    def call(self, name, a0=0):
        labels = ls.labels(HOOK)
        self.cpu.reg_write(UC_MIPS_REG_A0, a0)
        self.cpu.reg_write(UC_MIPS_REG_RA, END)
        self.cpu.reg_write(UC_MIPS_REG_SP, 0x801FF000)
        self.cpu.emu_start(labels[name], END, count=20000)
        self.assertEqual(self.cpu.reg_read(UC_MIPS_REG_PC), END, name)
        return self.cpu.reg_read(UC_MIPS_REG_V0)

    def finish_request(self):
        self.w(REQUEST + 0x1C, '<B', 0)

    def test_heal_then_damage_with_animation(self):
        self.bank()
        self.lp_change = {0: 700, 1: -300}
        self.call('summon', 6)
        self.assertEqual(self.lp(), (8000, 8000))                     # nada muda antes da animação
        self.assertEqual(self.created, [ls.HEAL])
        self.assertEqual(self.sounds, [ls.SOUND[ls.HEAL]])
        self.assertEqual(self.r(REQUEST, '<h'), 0xA0)
        self.assertEqual(self.r(REQUEST + 2, '<h'), 0x78)
        self.assertEqual(self.r(REQUEST + 0x1A, '<h'), 1)               # 500 ≤ 700 < 1000 → 2ª carta
        self.assertEqual(self.r(ls.HEAL_NUMBERS + 0x24, '<i'), 700)    # mostra o valor da carta
        self.assertEqual(self.call('tick'), 7)                          # devolve o v0 original
        self.assertEqual(self.lp(), (8000, 8000))                     # ainda animando
        self.finish_request()
        self.call('tick')
        self.assertEqual(self.lp(), (8700, 8000))
        self.assertEqual(self.r(ls.HEAL_NUMBERS + 0x24, '<i'), 500)    # número devolvido
        self.assertEqual(self.created, [ls.HEAL, ls.DAMAGE])           # agora o dano
        self.assertEqual(self.r(REQUEST + 0x1A, '<h'), 2)               # 200 ≤ 300 < 500
        self.assertEqual(self.r(ls.DAMAGE_NUMBERS + 2 * 0x1E, '<h'), -300)
        self.finish_request()
        self.call('tick')
        self.assertEqual(self.lp(), (8700, 7700))
        self.assertEqual(self.r(ls.DAMAGE_NUMBERS + 2 * 0x1E, '<h'), -200)
        self.assertEqual(self.sounds, [ls.SOUND[ls.HEAL], ls.SOUND[ls.DAMAGE]])
        self.call('tick')
        self.assertEqual(self.lp(), (8700, 7700))                     # fila vazia: nada mais

    def test_large_heal_uses_biggest_splash_and_no_bank_applies_directly(self):
        self.bank()
        self.lp_change = {0: 9999, 1: 0}
        self.call('summon', 6)
        self.assertEqual(self.r(REQUEST + 0x1A, '<h'), 4)
        self.finish_request()
        self.call('tick')
        self.assertEqual(self.lp(), (17999, 8000))
        self.assertEqual(self.r(ls.HEAL_NUMBERS + 4 * 0x24, '<i'), 5000)
        # banco de efeitos não carregado: sem animação, LP aplicados no próximo quadro
        for i in range(5):
            self.w(ls.HEAL_NUMBERS + i * 0x24, '<i', 0)
        self.created.clear()
        self.lp_change = {0: 100, 1: 0}
        self.call('summon', 6)
        self.assertEqual(self.created, [])
        self.call('tick')
        self.assertEqual(self.lp(), (18099, 8000))

    def test_damage_floors_at_zero_and_new_summon_flushes_pending(self):
        self.bank()
        self.set_lp(8000, 200)
        self.lp_change = {0: 0, 1: -1000}
        self.call('summon', 6)
        self.lp_change = {0: 0, 1: 0}
        self.call('summon', 7)                   # outra entrada antes do fim da animação
        self.assertEqual(self.lp(), (8000, 0))  # a pendente foi aplicada (com piso em 0)
        self.assertEqual(self.r(ls.DAMAGE_NUMBERS + 2 * 0x1E, '<h'), -200)    # número devolvido
        self.finish_request()
        self.call('tick')
        self.assertEqual(self.lp(), (8000, 0))


if __name__ == '__main__':
    unittest.main()
