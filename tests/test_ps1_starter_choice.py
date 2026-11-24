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
FRAME = ('frame', 0x80150000, 16, 176, 0, (0, 0, 23, 257))


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
        self.assertEqual(text[:2], b'\xfb\x02')                     # FB, 2 opções (sem 0x40)
        confirm = sc.page_text([b'\x01', b'\x02', b'\x03', b'\x04'], 0x20, header=2)
        self.assertEqual(confirm[:2], b'\xfb\x24')                  # 2 linhas de pergunta + 2 opções
        self.assertEqual(confirm[-7:], b'\xfb\x80\x20\x00\x20\x00\xff')
        self.assertEqual(len(confirm), sc.page_layout([b'\x01', b'\x02', b'\x03', b'\x04'], 2))
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
        confirms = [0xD3F3 + i for i in range(8)]
        self.entries = sc._entries(HOOK, rows, self.decks, confirms)
        cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(0, 0x200000)
        cpu.mem_write(HOOK & M, sc.code(HOOK, rows, self.decks, confirms))
        for stub in (sc.FIND_FREE_SLOT, sc.ACQUIRE_SLOT, sc.CONFIGURE_SPRITE, sc.SELECT_OT1, sc.SET_DEPTH,
                     sc.RANGE_LAYOUT, sc.UPDATE_DIALOG, sc.TEXT_BOX_CREATE, sc.TEXT_BOX_DESTROY,
                     sc.TEXT_UPDATE, sc.LIBRARY_SEEN, sc.BUILD_STARTER):
            cpu.mem_write(stub & M, struct.pack('<2I', 0x03E00008, 0))
        self.calls, self.done = [], False
        self.cpu = cpu

        def hook(uc, address, size, _):
            if address == sc.TEXT_BOX_CREATE:
                self.calls.append(('create', uc.reg_read(UC_MIPS_REG_A1)))
                uc.mem_write(BOX & M, bytes(0x64))
                uc.reg_write(UC_MIPS_REG_V0, BOX)
            elif address == sc.ACQUIRE_SLOT:
                uc.mem_write(0x80150000 & M, bytes(0x60))
                uc.reg_write(UC_MIPS_REG_V0, 0x80150000)
            elif address == sc.CONFIGURE_SPRITE:
                sp = uc.reg_read(UC_MIPS_REG_SP)
                extra = struct.unpack('<4I', uc.mem_read((sp + 0x10) & M, 16))
                assert (uc.reg_read(UC_MIPS_REG_A1), uc.reg_read(UC_MIPS_REG_A2), extra) == (16, 176, (0, 0, 23, 257))
            elif address == sc.TEXT_UPDATE:
                uc.mem_write((BOX + 0x30) & M, struct.pack('<I', 0x80123456))
                if self.done:
                    flags = struct.unpack('<H', uc.mem_read((BOX + 0x34) & M, 2))[0]
                    # como o jogo: ao concluir liga DONE e limpa o bit 8
                    uc.mem_write((BOX + 0x34) & M, struct.pack('<H', (flags | 0x2000) & ~8))
            elif address == sc.TEXT_BOX_DESTROY:
                self.calls.append(('destroy',))
            elif address == sc.UPDATE_DIALOG:
                self.calls.append(('update',))
            elif address == sc.LIBRARY_SEEN:
                self.calls.append(('seen', uc.reg_read(UC_MIPS_REG_A0)))
        cpu.hook_add(UC_HOOK_CODE, hook)

    def run_at(self, pc):
        self.cpu.reg_write(UC_MIPS_REG_SP, 0x80180000)
        self.cpu.reg_write(UC_MIPS_REG_RA, RETURN)
        self.cpu.emu_start(pc, RETURN, timeout=5_000_000)
        self.assertEqual(self.cpu.reg_read(UC_MIPS_REG_SP), 0x80180000)

    def frame(self, flags=0x20, dialog=0, choice=None, done=False, held=0):
        self.cpu.mem_write(sc.FLAGS & M, bytes([flags]))
        self.cpu.mem_write(sc.DIALOG_ID & M, struct.pack('<H', dialog))
        self.cpu.mem_write(sc.HELD & M, struct.pack('<H', held))
        if choice is not None:
            self.cpu.mem_write(sc.CHOICE & M, bytes([choice]))
        self.done = done
        self.calls.clear()
        self.run_at(self.entries['poll'])
        return list(self.calls)

    def test_pages_confirmation_and_release_wait(self):
        self.assertEqual(self.frame(flags=0), [('update',)])                 # digitando o nome
        self.assertEqual(self.frame(dialog=0x80F5), [('update',)])           # confirmação do nome aberta
        self.assertEqual(self.frame(held=0x40), [])                          # nome aceito: espera soltar X
        self.assertEqual(self.frame(held=0x40), [])
        self.assertEqual(self.frame(), [('create', 0xD3F0)])                 # página 1
        flags = struct.unpack('<H', self.cpu.mem_read((BOX + 0x34) & M, 2))[0]
        self.assertTrue(flags & 8)
        self.assertEqual(struct.unpack('<I', self.cpu.mem_read((BOX + 0x2C) & M, 4))[0], 0x80150000)
        self.assertEqual(self.frame(), [])                                   # esperando o X
        self.assertEqual(self.frame(choice=3, done=True, held=0x40), [('destroy',)])   # "Mais decks"
        self.assertEqual(self.frame(held=0x40), [])                          # X ainda segurado: não abre
        self.assertEqual(self.frame(), [('create', 0xD3F1)])                 # página 2
        self.assertEqual(self.frame(choice=1, done=True), [('destroy',)])    # 2º deck da página 2 (#5)
        self.assertEqual(self.frame(), [('create', 0xD3F3 + 4)])             # "Iniciar com ...?"
        self.assertEqual(self.frame(choice=1, done=True), [('destroy',)])    # "Não, escolher outro"
        self.assertEqual(self.frame(), [('create', 0xD3F1)])                 # volta à mesma página
        self.assertEqual(self.frame(choice=2, done=True), [('destroy',)])    # 3º da página 2 (#6)
        self.assertEqual(self.frame(), [('create', 0xD3F3 + 5)])
        self.assertEqual(self.frame(choice=0, done=True), [('destroy',)])    # "Sim"
        self.assertEqual(self.frame(), [('update',)])                        # o jogo escurece e conclui
        self.calls.clear()
        self.run_at(self.entries['build'])
        deck = struct.unpack('<40H', self.cpu.mem_read(sc.PLAYER_DECK & M, 80))
        self.assertEqual(deck, tuple(self.decks[5]))
        self.assertEqual(self.calls, [('seen', 6 + 288)] * 40)

    def test_more_wraps_to_first_page(self):
        self.frame(); self.frame()
        self.frame(choice=3, done=True); self.frame()
        self.frame(choice=3, done=True); self.frame()
        self.frame(choice=2, done=True)                                      # página 3: "Mais" é a opção 2
        self.assertEqual(self.frame(), [('create', 0xD3F0)])


class OverlayPlacementTests(unittest.TestCase):
    def test_routine_fits_in_starter_pool_area(self):
        self.assertLessEqual(sc.block_size(sc.MAX_DECKS), sc.OVERLAY_BLOCK_SIZE)
        self.assertEqual(sc.OVERLAY_BLOCK % 4, 0)


class BlockSizeTests(unittest.TestCase):
    def test_reserved_sizes_do_not_depend_on_address(self):
        """block_size() é calculado antes da reserva: o bloco real não pode ser maior."""
        from fmstudio import ps1_life_splash, ps1_lifelink, ps1_lp_hud
        rows = [(0, 0, 0, False)] * 3
        for base in range(0x801C0000, 0x801C0020, 4):
            self.assertEqual(len(sc.code(base, rows, [[1] * 40] * 8)), sc.block_size(8))
            self.assertEqual(len(ps1_life_splash.code(base)), ps1_life_splash.block_size())
            self.assertEqual(len(ps1_lifelink.code(base, 722)), ps1_lifelink.block_size())
            self.assertEqual(len(ps1_lp_hud.quad_code(base)), ps1_lp_hud.block_size())


class DisplayNameTests(unittest.TestCase):
    def test_custom_game_names(self):
        class Project:
            metadata = {sc.SETTINGS_KEY: {'ativado': True, 'decks': ['Deck Fada · Equilibrado', 'B'],
                                          'nomes': {'Deck Fada · Equilibrado': 'Deck das Fadas'}}}
        profiles = {'Deck Fada · Equilibrado': {'cartas': [1] * 40}, 'B': {'cartas': [2] * 40}}
        decks = sc.resolve_decks(Project(), profiles)
        self.assertEqual([name for name, _ in decks], ['Deck das Fadas', 'B'])
