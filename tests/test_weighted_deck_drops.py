"""Drops do próprio deck com pesos editáveis por rank no Studio e no PS1."""
from collections import Counter
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import struct
import unittest

from fmstudio.core import ModError, Project
from fmstudio.mod_data import (
    CONFIG_KEY, DROP_FROM_DECK, DECK_DROP_WEIGHTS, deck_drop_candidates,
    deck_drop_weights, drop_weights, normalize_rules, save_rules, weighted_choice,
)
from fmstudio.ps1_mod import compile_mod, patch_wa, verify_wa
from fmstudio.ps1_runtime import compile_effects
from fmstudio.tables import (
    CARD_COUNT, DUELIST_BASE, DUELIST_STRIDE, POOL_OFFSETS, POOL_TOTAL,
)


def card():
    return {'tipo_id': 0}


class WeightedDeckDropTests(unittest.TestCase):
    def setUp(self):
        self.cards = {cid: card() for cid in range(1, 42)}
        self.profile = {'cartas': list(range(1, 41)), 'pools': []}
        self.config = normalize_rules({
            'duelistas': {'1': {
                'deck': self.profile,
                DROP_FROM_DECK: True,
                DECK_DROP_WEIGHTS: {
                    'pow': {'1': 90, '2': 10, '3': 0, '41': 200},
                    'tec': {'2': 7},
                    'bcd': {'3': 50, '5': 5},
                },
                'drops': {'pow': {'41': 8000}},
            }}
        }, self.cards)

    def test_deck_candidates_and_rank_specific_chances(self):
        self.assertEqual(deck_drop_candidates(self.config, {}, 1), set(range(1, 41)))
        self.assertEqual(drop_weights(self.config, {}, 1, 'S-POW'), {1:90, 2:10})
        self.assertEqual(drop_weights(self.config, {}, 1, 'Z-POW'), {1:90, 2:10})
        self.assertEqual(drop_weights(self.config, {}, 1, 'S-TEC'), {2:7})
        self.assertEqual(drop_weights(self.config, {}, 1, 'B/C/D'), {3:50, 5:5})
        self.assertEqual(drop_weights(self.config, {}, 1, 'S-POW', dealt_deck=[41]*40),
                         {1:90, 2:10})
        class FixedRng:
            def __init__(self, roll): self.roll = roll
            def randrange(self, total):
                assert total == 100
                return self.roll
        self.assertEqual(weighted_choice({1:90, 2:10}, FixedRng(89)), 1)
        self.assertEqual(weighted_choice({1:90, 2:10}, FixedRng(90)), 2)
        self.assertNotIn(41, drop_weights(self.config, {}, 1, 'S-POW'))

    def test_legacy_checkbox_migrates_to_uniform_editable_weights(self):
        legacy = normalize_rules({'duelistas': {'1': {
            'deck': {'cartas': [1, 1, 2, 3], 'pools': []},
            DROP_FROM_DECK: True,
        }}}, self.cards)
        self.assertEqual(deck_drop_weights(legacy, {}, 1, 'S-POW'), {1:1, 2:1, 3:1})
        self.assertEqual(deck_drop_weights(legacy, {}, 1, 'S-TEC'), {1:1, 2:1, 3:1})
        # Só os candidatos do deck, e não todos os IDs do catálogo.
        self.assertNotIn(41, deck_drop_weights(legacy, {}, 1, 'B-TEC'))

    def test_weighted_pool_candidates_and_drop_zero(self):
        self.config['duelistas']['1']['deck'] = {
            'cartas': [1],
            'pools': [{'compras': 39, 'pesos': {2:5, 3:1, 4:0}}],
        }
        self.assertEqual(deck_drop_candidates(self.config, {}, 1), {1,2,3})
        self.assertEqual(drop_weights(self.config, {}, 1, 'S-POW'), {1:90,2:10})
        self.assertEqual(drop_weights(self.config, {}, 1, 'B/C/D'), {3:50})
        with self.assertRaises(ModError):
            normalize_rules({'duelistas': {'1': {DECK_DROP_WEIGHTS: {'bad': {1:3}}}}},
                            self.cards)

    def test_ps1_projection_writes_rank_tables_not_old_fixed_drop_hook(self):
        project = SimpleNamespace(
            cards=self.cards, get=self.cards.__getitem__, effects={},
            metadata={CONFIG_KEY: self.config},
        )
        plan = compile_mod(project, profile=True, wa_verified=True)
        self.assertTrue(plan.needs_wa)
        self.assertEqual(set(plan.groups), {(1,'pow'),(1,'tec'),(1,'bcd')})
        self.assertFalse(any('Drop #1 pow' in x for x in plan.applied))
        self.assertTrue(all(sum(group) == POOL_TOTAL for group in plan.groups.values()))
        wa = bytes(DUELIST_BASE + DUELIST_STRIDE * 2 + CARD_COUNT * 2)
        output = patch_wa(wa, plan)
        self.assertTrue(verify_wa(output, plan))
        for kind, expected in (
            ('pow', {1,2}), ('tec',{2}), ('bcd',{3,5}),
        ):
            start = DUELIST_BASE + DUELIST_STRIDE + POOL_OFFSETS[kind]
            table = struct.unpack_from(f'<{CARD_COUNT}H', output, start)
            self.assertEqual({i+1 for i, weight in enumerate(table) if weight}, expected)
        effects = compile_effects(project, True)
        self.assertEqual(effects.deck_drops, ())
        self.assertFalse(effects.mod_features)
        pending = compile_mod(project, profile=False, wa_verified=False)
        self.assertFalse(pending.groups)
        self.assertTrue(any('exige a imagem Drop x15' in x for x in pending.pending))

    def test_saved_project_reopens_with_weighted_drops_and_zero_exclusion(self):
        with TemporaryDirectory() as folder:
            p = Project.create(Path(folder) / 'projeto', 'Drops com pesos')
            for cid in (1, 2, 3):
                p.cards[cid] = {
                    'id':cid, 'nome':f'Carta {cid}', 'tipo_id':0,
                    'ataque':1000,'defesa':800,'nivel':4,'atributo_id':0,
                    'guardian_1_id':0,'guardian_2_id':0, 'descricao':'',
                }
            save_rules(p, {'duelistas':{'1':{
                'deck':{'cartas':[1,2,3], 'pools':[]},
                DROP_FROM_DECK: True,
                DECK_DROP_WEIGHTS:{'pow':{1:25,2:1},'tec':{3:999},'bcd':{2:3}},
            }}})
            reopened = Project.open(p.folder)
            self.assertEqual(drop_weights(reopened.metadata[CONFIG_KEY], {}, 1, 'S-POW'),
                             {1:25,2:1})
            self.assertEqual(drop_weights(reopened.metadata[CONFIG_KEY], {}, 1, 'S-TEC'),
                             {3:999})
            self.assertEqual(drop_weights(reopened.metadata[CONFIG_KEY], {}, 1, 'B-POW'),
                             {2:3})


if __name__ == '__main__':
    unittest.main()
