"""Round-trip native mod tables and opening-turn/LP code with synthetic bytes."""
from types import SimpleNamespace
import struct
import unittest

from fmstudio.core import ModError
from fmstudio.ps1_mod import (
    CHEST_DIM_FLAG, CHEST_DIM_FLAG_PC, CHEST_ROW_CONTEXT, CHEST_ROW_FLAG_PC, CHEST_ROW_VISIBLE,
    FIRST_TURN_PC, FIRST_TURN_SOURCE, INIT_CALL, LP_TABLE, ModPlan, _LP_INIT,
    compile_mod, inspect_chest_catalog, patch_chest_catalog, patch_executable, patch_wa, verify_executable, verify_wa,
)
from fmstudio.tables import CARD_COUNT, DECK_SIZE, DUELIST_BASE, DUELIST_STRIDE, EXE_DELTA, POOL_OFFSETS, POOL_TOTAL


def seed_chest_catalog(exe):
    struct.pack_into('<I', exe, CHEST_DIM_FLAG_PC - EXE_DELTA, CHEST_DIM_FLAG)
    struct.pack_into('<3I', exe, CHEST_ROW_FLAG_PC - EXE_DELTA - 4, *CHEST_ROW_CONTEXT)


class ModProjectionTests(unittest.TestCase):
    def test_full_chest_changes_only_the_initial_visibility_flag(self):
        original = bytearray(CHEST_ROW_FLAG_PC - EXE_DELTA + 8)
        seed_chest_catalog(original)
        self.assertEqual(inspect_chest_catalog(original)['status'], 'ausente')
        patched = patch_chest_catalog(bytes(original))
        self.assertEqual(inspect_chest_catalog(patched), {'status':'aplicado', 'cartas':CARD_COUNT})
        self.assertEqual(patch_chest_catalog(patched), patched)
        location = CHEST_ROW_FLAG_PC - EXE_DELTA
        self.assertEqual(patched, bytes(original[:location]) + struct.pack('<I', CHEST_ROW_VISIBLE)
                         + bytes(original[location + 4:]))
        original[CHEST_DIM_FLAG_PC - EXE_DELTA] ^= 1
        self.assertEqual(inspect_chest_catalog(original)['status'], 'divergente')
        with self.assertRaisesRegex(ModError, 'baú diverge'):
            patch_chest_catalog(original)

    def test_opening_attack_lock_preserved_and_legacy_unlock_rejected(self):
        plan = ModPlan(0, [], {}, [], [], [])
        offset = FIRST_TURN_PC - EXE_DELTA
        source = bytearray(offset + 4)
        struct.pack_into('<I', source, offset, FIRST_TURN_SOURCE)
        self.assertEqual(patch_executable(bytes(source), plan, profile=True), bytes(source))
        self.assertEqual(verify_executable(source, plan), (True, True))

        struct.pack_into('<I', source, offset, 0x34420000)
        self.assertEqual(verify_executable(source, plan), (False, True))
        with self.assertRaisesRegex(ModError, 'trava original'):
            patch_executable(source, plan, profile=True)

    def test_full_fixed_deck_keeps_exact_ids_and_counts(self):
        cards = {cid: {'tipo_id': 0} for cid in (*range(1, 41), 722)}
        cards[723] = {'tipo_id': 24, 'virtual': True}
        cards[741] = {'tipo_id': 0, 'virtual': True}
        deck = [*range(1, 38), 722, 722, 722]
        project = SimpleNamespace(cards=cards, get=cards.__getitem__, metadata={'edicao_mod': {
            'duelistas': {
                '1': {'deck': {'cartas': deck}},
                '2': {'deck': {'cartas': deck[:-1]}},
                '3': {'deck': {'cartas': [*deck[:-1], 723]}},
                '4': {'deck': {'cartas': [*deck[:-1], 741]}},
            }
        }})
        plan = compile_mod(project, profile=True, wa_verified=False)
        self.assertEqual(plan.fixed_decks, {1: tuple(deck), 3: (*deck[:-1], 723)})
        self.assertFalse(plan.needs_wa)
        self.assertTrue(any('39/40' in note for note in plan.pending))
        self.assertTrue(any('#001–#740' in note for note in plan.pending))
        self.assertEqual(compile_mod(project, profile=False, wa_verified=True).fixed_decks, {})

    def test_saved_fusions_export_for_supported_expanded_ids(self):
        cards = {cid: {'tipo_id': 9} for cid in (16, 56, 72, 723, 741)}
        cards[16]['tipo_id'] = 24
        cards[723]['virtual'] = True
        project = SimpleNamespace(cards=cards, get=cards.__getitem__, metadata={'edicao_mod': {
            'receitas': {'fusoes': {'56,16': 72, '56,72': 723, '16,72': 741}}
        }})
        plan = compile_mod(project, profile=True, wa_verified=False)
        self.assertEqual(plan.fusions, {(16, 56): 72, (56, 72): 723})
        self.assertIn('Fusões personalizadas (2)', plan.applied)
        self.assertFalse(plan.needs_wa)
        self.assertTrue(any('#741' in item for item in plan.pending))
        self.assertFalse(compile_mod(project, profile=False, wa_verified=True).fusions)

    def test_edited_native_pools_skip_banned_ids_and_report_unsupported_limits(self):
        cards = {cid: {'tipo_id': 0} for cid in range(1, 25)}
        effects = {cid: [{'evento': 'regra_deck', 'acao': 'limite_copias_deck',
                          'alvo': 'proprio', 'valor': limit}] for cid, limit in ((1, 0), (24, 1))}
        pool = {'compras': DECK_SIZE, 'pesos': dict.fromkeys(range(1, 24), 1)}
        project = SimpleNamespace(cards=cards, get=cards.__getitem__, effects=effects,
                                  metadata={'edicao_mod': {'duelistas': {
                                      '1': {'deck': {'pools': [pool]}, 'drops_do_deck': True},
                                      '2': {'deck': {'pools': [{**pool, 'pesos': {**pool['pesos'], 24: 1}}]}},
                                  }}})
        plan = compile_mod(project, profile=True, wa_verified=True)
        for group in ('deck', 'pow', 'tec', 'bcd'):
            self.assertEqual(plan.groups[(1, group)][0], 0)
            self.assertEqual(sum(plan.groups[(1, group)]), POOL_TOTAL)
        self.assertNotIn((2, 'deck'), plan.groups)
        self.assertTrue(any('limites de 1–2' in line for line in plan.pending))

    def test_global_20000_lp_applies_to_every_opponent_in_native_table(self):
        cards = {1: {'tipo_id': 0}}
        project = SimpleNamespace(cards=cards, get=cards.__getitem__, metadata={
            'edicao_mod': {
                'lp_inicial': 20000,
                'lp_jogador': 8000,
                'duelistas': {'1': {'lp': 8000}, '39': {'lp': 1500}},
            }
        })
        plan = compile_mod(project, profile=True, wa_verified=False)
        self.assertEqual(plan.player_lp, 20000)
        self.assertEqual(len(plan.life), len(ModPlan(0, [0] * len(plan.life), {}, [], [], []).life))
        self.assertTrue(all(value == 20000 for value in plan.life))
        exe = bytearray(0x1D0000)
        struct.pack_into('<I', exe, FIRST_TURN_PC-EXE_DELTA, FIRST_TURN_SOURCE)
        struct.pack_into('<I', exe, INIT_CALL-EXE_DELTA, _LP_INIT)
        out = patch_executable(bytes(exe), plan, profile=True)
        self.assertEqual(struct.unpack_from('<4H', out, LP_TABLE-EXE_DELTA),
                         (20000, 20000, 20000, 20000))
        self.assertEqual(verify_executable(out, plan), (True, True))

    def test_pools_lp_and_opening_turn_verify_without_truncating_studio_settings(self):
        cards = {i:{'tipo_id':0} for i in range(1, 30)}
        project = SimpleNamespace(cards=cards, get=cards.__getitem__, metadata={'edicao_mod':{
            'lp_jogador':8800,
            'duelistas':{
                '1':{'lp':6101,'drops':{'pow':{'1':901,'2':17}, 'S-TEC':{'3':19}},
                     'deck':{'pools':[{'compras':DECK_SIZE,'pesos':{i:i for i in cards}}]}},
                '2':{'lp':10**90,'deck':{'cartas':[3,3]}},
            }}})
        plan = compile_mod(project, profile=True, wa_verified=True)
        self.assertEqual(plan.player_lp,8800)
        self.assertEqual(plan.life[:3],[8800,8800,8800])
        self.assertEqual(set(plan.groups),{(1,'pow'),(1,'deck')})
        self.assertEqual(len(plan.pending),2)
        self.assertTrue(all(sum(row)==POOL_TOTAL for row in plan.groups.values()))
        exe = bytearray(0x1D0000)
        struct.pack_into('<I',exe,FIRST_TURN_PC-EXE_DELTA,FIRST_TURN_SOURCE)
        struct.pack_into('<I',exe,INIT_CALL-EXE_DELTA,_LP_INIT)
        patched = patch_executable(exe,plan,profile=True)
        self.assertEqual(struct.unpack_from('<I',patched,FIRST_TURN_PC-EXE_DELTA)[0], FIRST_TURN_SOURCE)
        self.assertEqual(verify_executable(patched,plan),(True,True))
        corrupted = bytearray(patched)
        corrupted[LP_TABLE-EXE_DELTA] ^= 1
        self.assertEqual(verify_executable(corrupted,plan),(True,False))
        wa = bytes(DUELIST_BASE + 2 * DUELIST_STRIDE)
        patched_wa = patch_wa(wa,plan)
        self.assertTrue(verify_wa(patched_wa,plan))
        self.assertFalse(verify_wa(wa,plan))
        offset = DUELIST_BASE + DUELIST_STRIDE + POOL_OFFSETS['pow']
        self.assertEqual(sum(struct.unpack_from(f'<{CARD_COUNT}H',patched_wa,offset)), POOL_TOTAL)
        self.assertEqual(patched_wa[:DUELIST_BASE + DUELIST_STRIDE],wa[:DUELIST_BASE + DUELIST_STRIDE])
