"""Round-trip native mod tables and opening-turn/LP code with synthetic bytes."""
from types import SimpleNamespace
import struct
import unittest

from fmstudio.core import ModError
from fmstudio.ps1_mod import (
    FIRST_TURN_PC, FIRST_TURN_SOURCE, INIT_CALL, LP_TABLE, ModPlan, _LP_INIT,
    compile_mod, patch_executable, patch_wa, verify_executable, verify_wa,
)
from fmstudio.tables import CARD_COUNT, DECK_SIZE, DUELIST_BASE, DUELIST_STRIDE, EXE_DELTA, POOL_OFFSETS, POOL_TOTAL


class ModProjectionTests(unittest.TestCase):
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
        self.assertEqual(plan.life[:3],[0,6101,0])
        self.assertEqual(set(plan.groups),{(1,'pow'),(1,'deck')})
        self.assertEqual(len(plan.pending),3)
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
