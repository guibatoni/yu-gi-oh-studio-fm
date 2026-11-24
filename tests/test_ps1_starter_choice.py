"""Escolha do deck inicial (New Game) no PS1: formato do texto, overlay e rotina no Unicorn."""
import struct
import unittest

from fmstudio import ps1_starter_choice as sc
from fmstudio.core import ModError

try:
    from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
    from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3,
                                    UC_MIPS_REG_RA, UC_MIPS_REG_SP, UC_MIPS_REG_V0)
except ImportError:  # pragma: no cover
    Uc = None

M = 0x1FFFFF
HOOK = 0x801C8000
BOX = 0x800EB180
RETURN = 0x80000100


class FormatTests(unittest.TestCase):
    def test_pages(self):
        self.assertEqual(sc.pages(2), [(0, 2, False)])
        self.assertEqual(sc.pages(4), [(0, 4, False)])
        self.assertEqual(sc.pages(8), [(0, 3, True), (3, 3, True), (6, 2, True)])

    def test_page_text_matches_game_choice_format(self):
        lines = [b'\x10\x11', b'\x12']
        size = sc.page_layout(lines)
        text = sc.page_text(lines, 0x1234)
        self.assertEqual(len(text), size)
        self.assertEqual(text[:2], b'\xfb\x42')                     # FB, 0x40 | 2 opções
        self.assertEqual(text[2:8], b'\x10\x11\xfe\x12\xfe\xfb')
        self.assertEqual(text[7:], b'\xfb\x80\x34\x12\x34\x12\xff')

    def test_overlay_patch_requires_exact_calls(self):
        wa = bytearray(sc._overlay_offset(sc.OVERLAY_BASE + sc.OVERLAY_SIZE))
        with self.assertRaises(ModError):
            sc.patch_overlay(bytes(wa), HOOK)
        poll_site, main_site = 0x80169C14, 0x8016AAD0
        struct.pack_into('<I', wa, sc._overlay_offset(poll_site), sc._jal(sc.UPDATE_DIALOG))
        struct.pack_into('<I', wa, sc._overlay_offset(main_site), sc._jal(sc.BUILD_STARTER))
        out = sc.patch_overlay(bytes(wa), HOOK)
        entries = sc._entries(HOOK)
        self.assertEqual(struct.unpack_from('<I', out, sc._overlay_offset(poll_site))[0], sc._jal(entries['poll']))
        self.assertEqual(struct.unpack_from('<I', out, sc._overlay_offset(main_site))[0], sc._jal(entries['build']))
        changed = [i for i, (x, y) in enumerate(zip(wa, out)) if x != y]
        self.assertTrue(all(sc._overlay_offset(poll_site) <= i < sc._overlay_offset(poll_site) + 4
                            or sc._overlay_offset(main_site) <= i < sc._overlay_offset(main_site) + 4
                            for i in changed))


@unittest.skipIf(Uc is None, 'Unicorn não instalado')
class RoutineTests(unittest.TestCase):
    def setUp(self):
        rows = [(0xD3F0, 0, 3, True), (0xD3F1, 3, 3, True), (0xD3F2, 6, 2, True)]
        self.decks = [[i + 1] * 40 for i in range(8)]
        self.entries = sc._entries(HOOK, rows, self.decks)
        cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(0, 0x200000)
        cpu.mem_write(HOOK & M, sc.code(HOOK, rows, self.decks))
        for stub in (sc.UPDATE_DIALOG, sc.TEXT_BOX_CREATE, sc.TEXT_BOX_DESTROY, sc.TEXT_UPDATE,
                     sc.LIBRARY_SEEN, sc.BUILD_STARTER):
            cpu.mem_write(stub & M, struct.pack('<2I', 0x03E00008, 0))
        self.calls, self.done = [], False
        self.cpu = cpu

        def hook(uc, address, size, _):
            if address == sc.TEXT_BOX_CREATE:
                sp = uc.reg_read(UC_MIPS_REG_SP)
                w, h = struct.unpack('<II', uc.mem_read((sp + 0x10) & M, 8))
                self.calls.append(('create', uc.reg_read(UC_MIPS_REG_A0), uc.reg_read(UC_MIPS_REG_A1),
                                   uc.reg_read(UC_MIPS_REG_A2), uc.reg_read(UC_MIPS_REG_A3), w, h))
                uc.mem_write(BOX & M, bytes(0x64))
                uc.reg_write(UC_MIPS_REG_V0, BOX)
            elif address == sc.TEXT_UPDATE:
                uc.mem_write((BOX + 0x30) & M, struct.pack('<I', 0x80123456))   # caixa montada
                if self.done:
                    flags = struct.unpack('<H', uc.mem_read((BOX + 0x34) & M, 2))[0]
                    # como o jogo: ao concluir, liga DONE e limpa o bit 8 (o retail espera 0x2008 == 0x2000)
                    uc.mem_write((BOX + 0x34) & M, struct.pack('<H', (flags | 0x2000) & ~8))
            elif address == sc.TEXT_BOX_DESTROY:
                self.calls.append(('destroy', uc.reg_read(UC_MIPS_REG_A0)))
            elif address == sc.UPDATE_DIALOG:
                self.calls.append(('update',))
            elif address == sc.LIBRARY_SEEN:
                self.calls.append(('seen', uc.reg_read(UC_MIPS_REG_A0)))
            elif address == sc.BUILD_STARTER:
                self.calls.append(('random',))
        cpu.hook_add(UC_HOOK_CODE, hook)

    def run_at(self, pc):
        self.cpu.reg_write(UC_MIPS_REG_SP, 0x80180000)
        self.cpu.reg_write(UC_MIPS_REG_RA, RETURN)
        self.cpu.emu_start(pc, RETURN, timeout=5_000_000)
        self.assertEqual(self.cpu.reg_read(UC_MIPS_REG_SP), 0x80180000)

    def frame(self, flags=0x20, dialog=0, choice=None, done=False):
        self.cpu.mem_write(sc.FLAGS & M, bytes([flags]))
        self.cpu.mem_write(sc.DIALOG_ID & M, struct.pack('<H', dialog))
        if choice is not None:
            self.cpu.mem_write(sc.CHOICE & M, bytes([choice]))
        self.done = done
        self.calls.clear()
        self.run_at(self.entries['poll'])
        return list(self.calls)

    def test_full_choice_flow_with_pages(self):
        self.assertEqual(self.frame(flags=0), [('update',)])                 # digitando o nome
        self.assertEqual(self.frame(dialog=0x80F5), [('update',)])           # confirmação ainda aberta
        self.assertEqual(self.frame(), [('create', 2, 0xD3F0, 16, 176, 288, 48)])
        self.assertEqual(self.frame(), [])                                   # esperando o X
        flags = struct.unpack('<H', self.cpu.mem_read((BOX + 0x34) & M, 2))[0]
        self.assertTrue(flags & 8)                                           # modo do retail (0x8000)
        calls = self.frame(choice=3, done=True)                              # "Mais decks..."
        self.assertEqual(calls, [('destroy', BOX), ('create', 2, 0xD3F1, 16, 176, 288, 48)])
        calls = self.frame(choice=1, done=True)                              # 2º deck da página 2
        self.assertEqual(calls, [('destroy', BOX)])
        self.assertEqual(self.frame(), [('update',)])                        # o jogo escurece e conclui
        self.calls.clear()
        self.run_at(self.entries['build'])
        deck = struct.unpack('<40H', self.cpu.mem_read(sc.PLAYER_DECK & M, 80))
        self.assertEqual(deck, tuple(self.decks[4]))
        self.assertEqual(self.calls, [('seen', 5 + 288)] * 40)
        self.calls.clear()
        self.run_at(self.entries['build'])                                  # sem escolha: sorteio original
        self.assertEqual(self.calls, [('random',)])

    def test_more_wraps_to_first_page(self):
        self.frame()
        self.frame(choice=3, done=True)
        self.frame(choice=3, done=True)
        calls = self.frame(choice=2, done=True)                              # página 3: "Mais" é a opção 2
        self.assertEqual(calls, [('destroy', BOX), ('create', 2, 0xD3F0, 16, 176, 288, 48)])


if __name__ == '__main__':
    unittest.main()
