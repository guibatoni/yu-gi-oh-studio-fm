"""Sub-tipo: o monstro conta como dos dois tipos (bônus e equipamentos)."""
import unittest

from fmstudio.card_subtypes import equip_additions, subtype, types_of
from fmstudio.continuous import matches_filter
from fmstudio.core import ModError, check_card_edit
from fmstudio.drafts import same_card


def card(typ, sub=-1):
    return {'tipo_id': typ, 'subtipo_id': sub, 'ataque': 1000, 'defesa': 1000}


class SubtypeTests(unittest.TestCase):
    def test_validation(self):
        self.assertEqual(check_card_edit({'subtipo_id': 8})['subtipo_id'], 8)
        self.assertEqual(check_card_edit({'subtipo_id': ''})['subtipo_id'], -1)
        with self.assertRaises(ModError):
            check_card_edit({'subtipo_id': 23})                    # Equip não é tipo de monstro
        self.assertIsNone(subtype(card(8, 8)))                      # igual ao tipo: ignora
        self.assertEqual(types_of(card(0, 8)), {0, 8})

    def test_type_bonus_matches_either_type(self):
        effect = {'tipo_id': 8}
        self.assertTrue(matches_filter(card(0, 8), effect))
        self.assertTrue(matches_filter(card(8), effect))
        self.assertFalse(matches_filter(card(0), effect))

    def test_equips_follow_subtype(self):
        cards = {i: card(8) for i in range(1, 7)}                   # 6 fadas
        cards.update({10: card(0, 8), 11: card(0)})                 # dragão-fada e dragão comum
        equips = {300: {1, 2, 3, 4}, 301: {1}, 302: {10}}
        self.assertEqual(equip_additions(cards, equips), {300: [10]})   # 301 cobre só 1 fada

    def test_draft_detects_subtype_change(self):
        from fmstudio.core import NUMERIC
        base = {key: 0 for key in NUMERIC}
        base.update(nome='x', descricao='', cor_nome='#FFFFFF', raridade='comum')
        self.assertFalse(same_card({**base, 'subtipo_id': 8}, base))
        self.assertTrue(same_card({**base, 'subtipo_id': -1}, base))


if __name__ == '__main__':
    unittest.main()


class Ps1SubtypeTests(unittest.TestCase):
    def test_signature_and_view(self):
        import struct
        from fmstudio import ps1_runtime_blob, ps1_subtypes as st
        at = st.SITE - ps1_runtime_blob.RUNTIME_EXT_BASE
        words = struct.unpack_from('<8I', ps1_runtime_blob.RUNTIME_EXT, at)
        self.assertEqual(words, st.SIGNATURE)
        self.assertEqual(st.block_size(3), len(st.code(0x801C4000, [(5, 8), (9, 0), (12, 3)])))


try:
    from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
    from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_RA,
                                    UC_MIPS_REG_SP, UC_MIPS_REG_V0)
except ImportError:  # pragma: no cover
    Uc = None


@unittest.skipIf(Uc is None, 'Unicorn não instalado')
class MatchesBonusMipsTests(unittest.TestCase):
    """Roda o matches_bonus real do runtime com o trampolim instalado."""

    def run_match(self, match, card_id, by_id=0, scope=0, card_type=0, level_attr=0):
        import struct
        from fmstudio import ps1_runtime_blob as rt, ps1_subtypes as st
        M = 0x1FFFFF
        hook = 0x801C4000
        cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(0, 0x200000)
        cpu.mem_write(rt.RUNTIME_EXT_BASE & M, rt.RUNTIME_EXT)
        cpu.mem_write(hook & M, st.code(hook, [(5, 8), (9, 0)]))
        cpu.mem_write(st.SITE & M, struct.pack('<I', 0x08000000 | ((hook & 0x0FFFFFFF) >> 2)))
        stats = 0x801D4244
        cpu.mem_write((stats + 4 * (card_id - 1)) & M, struct.pack('<I', card_type << 26))
        cpu.mem_write((0x801D5332 + card_id) & M, bytes([level_attr]))
        bonus = 0x80100000
        cpu.mem_write(bonus & M, struct.pack('<BBH', 1, scope, match))
        cpu.reg_write(UC_MIPS_REG_A0, bonus)
        cpu.reg_write(UC_MIPS_REG_A1, card_id)
        cpu.reg_write(UC_MIPS_REG_A2, by_id)
        cpu.reg_write(UC_MIPS_REG_SP, 0x80180000)
        cpu.reg_write(UC_MIPS_REG_RA, 0x80000100)
        cpu.emu_start(0x801CFB14, 0x80000100, timeout=1_000_000)
        return cpu.reg_read(UC_MIPS_REG_V0)

    def test_subtype_counts_as_type(self):
        self.assertEqual(self.run_match(8, 5, card_type=0), 1)      # #5: Dragão com sub-tipo Fada
        self.assertEqual(self.run_match(0, 5, card_type=0), 1)      # o tipo principal continua valendo
        self.assertEqual(self.run_match(8, 6, card_type=0), 0)      # sem sub-tipo
        self.assertEqual(self.run_match(0xFFFF, 6, card_type=3), 1) # qualquer tipo
        self.assertEqual(self.run_match(8, 5, by_id=1), 0)          # comparação por ID não usa sub-tipo
        self.assertEqual(self.run_match(5, 5, by_id=1), 1)
        # filtro de atributo E tipo: sub-tipo bate, atributo também
        self.assertEqual(self.run_match(8, 5, scope=(3 << 2), card_type=0, level_attr=(2 << 4)), 1)
        self.assertEqual(self.run_match(8, 5, scope=(4 << 2), card_type=0, level_attr=(2 << 4)), 0)


@unittest.skipIf(Uc is None, 'Unicorn não instalado')
class HandBonusMipsTests(unittest.TestCase):
    """Wrapper de count_bonus + matches_bonus real: conta a mão."""

    def run_count(self, match, scope, side, hand):
        import struct
        from fmstudio import ps1_runtime_blob as rt, ps1_hand_bonus as hb
        from unicorn import UC_HOOK_CODE
        M = 0x1FFFFF
        hook = 0x801C4400
        cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(0, 0x200000)
        cpu.mem_write(rt.RUNTIME_EXT_BASE & M, rt.RUNTIME_EXT)
        cpu.mem_write(hook & M, hb.code(hook))
        calls = []
        cpu.hook_add(UC_HOOK_CODE, lambda uc, a, s, _: calls.append('original') if a == hb.COUNT_BONUS else None)
        for slot, (cid, typ) in hand.items():
            rec = hb.CARDS + slot * 28
            cpu.mem_write((rec + 0x0C) & M, struct.pack('<h', cid))
            cpu.mem_write((rec + 0x16) & M, struct.pack('<H', 0x8000))
            cpu.mem_write((0x801D4244 + 4 * (cid - 1)) & M, struct.pack('<I', typ << 26))
        bonus = 0x80100000
        cpu.mem_write(bonus & M, struct.pack('<BBHHH', 3, scope, match, 100, 0))
        cpu.reg_write(UC_MIPS_REG_A0, bonus)
        cpu.reg_write(UC_MIPS_REG_A1, side)
        cpu.reg_write(UC_MIPS_REG_SP, 0x80180000)
        cpu.reg_write(UC_MIPS_REG_RA, 0x80000100)
        cpu.mem_write(hb.COUNT_BONUS & M, struct.pack('<2I', 0x03E00008, 0x24020063))  # stub: v0 = 99
        cpu.emu_start(hook, 0x80000100, timeout=2_000_000)
        return cpu.reg_read(UC_MIPS_REG_V0), calls

    def test_counts_hand_by_scope(self):
        from fmstudio.ps1_hand_bonus import encode_match
        hand = {0: (10, 8), 1: (11, 8), 3: (12, 0), 15: (13, 8), 16: (14, 8), 17: (15, 8)}
        self.assertEqual(self.run_count(encode_match(8), 0, 0, hand)[0], 2)     # minhas fadas na mão
        self.assertEqual(self.run_count(encode_match(8), 1, 0, hand)[0], 3)     # fadas do adversário
        self.assertEqual(self.run_count(encode_match(8), 2, 0, hand)[0], 5)     # todos
        self.assertEqual(self.run_count(encode_match(-1), 0, 0, hand)[0], 3)    # qualquer tipo
        value, calls = self.run_count(8, 0, 0, hand)                             # bônus de deck normal
        self.assertEqual((value, calls), (99, ['original']))
