"""Regression coverage for the catalog, passwords and generated deck profiles."""
from collections import Counter
import json
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fmstudio.core import ModError, Project, _write_csv
from fmstudio.deck_generator import generate_deck
from fmstudio.duel_match import make_match
from fmstudio.mod_data import DROP_FROM_DECK, MONSTER_TYPES, drop_weights, save_rules
from fmstudio.passwords import chest_cards, grant_card, id_code, original_passwords, redeem_id, redeem_original


def card(kind, atk=0, defense=0):
    return {'tipo_id': kind, 'ataque': atk, 'defesa': defense}


class CatalogTests(unittest.TestCase):
    def test_all_new_card_types_survive_reopen_decks_and_export(self):
        with TemporaryDirectory() as path:
            project = Project.create(Path(path), 'Catálogo expandido')
            kinds = (0, 20, 21, 22, 23, 24)
            ids = [project.add_card(name=f'Carta {kind}', type_id=kind) for kind in kinds]
            self.assertEqual(ids, list(range(723, 729)))
            save_rules(project, {
                'duelistas': {'1': {'deck': {'cartas': ids}}},
                'iniciais': {'Jogador': {'cartas': ids}},
            })
            project = Project.open(project.folder)
            self.assertEqual([project.get(cid)['tipo_id'] for cid in ids], list(kinds))
            output, _ = project.export(include_ps1=False)
            exported = json.loads((output/'novas_cartas.json').read_text(encoding='utf-8'))
            self.assertEqual(set(exported['cartas']), set(map(str, ids)))
            match = make_match(project, None, 1, 'Jogador', rng=Random(4))
            self.assertCountEqual(match.initial_decks['jogador'], ids)
            self.assertCountEqual(match.initial_decks['adversario'], ids)

    def test_existing_original_passwords_keep_leading_zeros_and_cost(self):
        with TemporaryDirectory() as path:
            project = Project.create(Path(path), 'Passwords')
            project.cards[16] = card(24)
            custom = project.add_card(type_id=24, card_id=10**25 + 12)
            base = project.folder/'base'
            base.mkdir()
            _write_csv(base/'senhas.csv', [
                {'carta_id': 16, 'password': '00765432', 'password_valido_bcd': 1, 'custo_starchips': 555},
                {'carta_id': custom, 'password': '00888888', 'password_valido_bcd': 1, 'custo_starchips': 0},
            ])
            records = original_passwords(project)
            self.assertEqual(redeem_original('00765432', records), [16])
            self.assertEqual(records[16].cost, 555)
            with self.assertRaises(ModError):
                redeem_original('765432', records)
            self.assertNotIn(custom, records)
            self.assertEqual(id_code(16), 'FM-00000016')
            self.assertEqual(redeem_id(id_code(16), project.cards), 16)
            self.assertEqual(redeem_id(id_code(custom).lower(), project.cards), custom)
            with self.assertRaises(ModError):
                redeem_id('FM-00000999', project.cards)

    def test_free_id_and_partial_edits_persist_atomically(self):
        with TemporaryDirectory() as path:
            project = Project.create(Path(path), 'Catálogo')
            cid = project.add_card(card_id=343, type_id=20, name='Magia do Studio')
            project.set_card(cid, {'descricao': 'Descrição preservada'})
            project.set_card(cid, {'nome': 'Nova magia'})
            before = (project.folder / 'projeto.json').read_bytes()
            with patch.object(project, 'save', side_effect=OSError('volume cheio')):
                with self.assertRaises(OSError):
                    project.add_card(card_id=724)
                with self.assertRaises(OSError):
                    project.set_card(cid, {'nome': 'Falhou'})
            self.assertNotIn(724, project.cards)
            self.assertEqual(project.get(cid)['nome'], 'Nova magia')
            self.assertEqual((project.folder / 'projeto.json').read_bytes(), before)
            project = Project.open(project.folder)
            self.assertEqual(project.get(cid)['descricao'], 'Descrição preservada')
            self.assertEqual(project.validate(), [])
            with self.assertRaisesRegex(ModError, 'já pertence'):
                project.add_card(card_id=cid)

    def test_redeem_direct_id_and_commit_both_destinations(self):
        with TemporaryDirectory() as path:
            project = Project.create(Path(path), 'Baú')
            cid = project.add_card(type_id=24, card_id=999_887)
            for entry in (str(cid), f'#{cid}', id_code(cid)):
                self.assertEqual(redeem_id(entry, project.cards), cid)
                grant_card(project, cid, starter='Deck do baú')
            with self.assertRaisesRegex(ModError, 'máximo'):
                grant_card(project, cid, starter='Deck do baú')
            with patch.object(project, 'save', side_effect=OSError('volume cheio')):
                with self.assertRaises(OSError):
                    grant_card(project, cid)
            project = Project.open(project.folder)
            self.assertEqual(chest_cards(project), {str(cid): 3})
            self.assertEqual(project.metadata['edicao_mod']['iniciais']['Deck do baú']['cartas'], [cid]*3)

    def test_deck_victory_reward_is_drawn_from_dealt_cards_and_granted_once(self):
        with TemporaryDirectory() as path:
            project = Project.create(Path(path), 'Drops')
            hero, fixed, rare, spare, legacy = [project.add_card() for _ in range(5)]
            config = save_rules(project, {
                'iniciais': {'Principal': {'cartas': [hero]}},
                'duelistas': {'1': {DROP_FROM_DECK: True,
                                   'deck': {'cartas': [fixed, fixed],
                                            'pools': [{'compras': 1, 'pesos': {rare: 3, spare: 1}}]},
                                   'drops': {'pow': {legacy: 10}}}},
            })
            game = make_match(project, None, 1, 'Principal', rng=Random(4))
            initial = game.initial_decks['adversario']
            self.assertCountEqual(initial[:2], [fixed, fixed])
            self.assertFalse(game.decks['adversario'])
            grant = lambda cid: grant_card(project, cid)
            with self.assertRaises(ModError):
                game.claim_reward(config, {}, 1, 'A-TEC', grant)
            game.lp['adversario'] = 0
            rng = Random(0)
            with self.assertRaises(OSError):
                with patch.object(project, 'save', side_effect=OSError('volume cheio')):
                    game.claim_reward(config, {}, 1, 'A-TEC', grant, rng=rng)
            card = game.claim_reward(config, {}, 1, 'A-TEC', grant, rng=rng)
            self.assertIn(card, initial)
            self.assertEqual(game.claim_reward(config, {}, 1, 'S-POW', grant), card)
            self.assertEqual(chest_cards(Project.open(project.folder)), {str(card): 1})
            self.assertEqual(drop_weights(config, {}, 1, 'S-POW', dealt_deck=initial), Counter(initial))
            config['duelistas']['1'][DROP_FROM_DECK] = False
            self.assertEqual(drop_weights(config, {}, 1, 'S-POW', dealt_deck=initial), {legacy: 10})


    def test_saved_cocoon_fusion_is_playable_after_reopening_the_project(self):
        with TemporaryDirectory() as path:
            project = Project.create(Path(path), 'Fusão salva')
            for cid, name, kind in ((16, 'Time Wizard', 1), (56, 'Larvae Moth', 9),
                                    (72, 'Cocoon of Evolution', 9)):
                project.add_card(card_id=cid, name=name, type_id=kind)
            save_rules(project, {'receitas': {'fusoes': {'56,16': 72}},
                                 'duelistas': {'1': {'deck': {'cartas': [72]}}},
                                 'iniciais': {'Teste': {'cartas': [16, 56]}}})
            reopened = Project.open(project.folder)
            game = make_match(reopened, None, 1, 'Teste', rng=Random(1))
            order = game.hands['jogador'].copy()
            for hand in (order, list(reversed(order))):
                game.hands['jogador'] = hand
                self.assertTrue(any(move.kind == 'fusao' and move.card_id == 72
                                    for move in game.legal_plays('jogador')))
            move = next(move for move in game.legal_plays('jogador') if move.kind == 'fusao')
            game.play('jogador', move)
            self.assertEqual(game.get('jogador', move.slot)['card_id'], 72)


class DeckGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.cards = {cid: card(0 if cid <= 10 else 1, 1000 + cid * 10, 1200)
                      for cid in range(1, 21)}
        self.cards.update({
            1000: card(0, atk=2000),
            1001: card(24, atk=10**70, defense=7300),
            1002: card(20),
            1003: card(23),
            1004: card(23),
            681: card(21),
            686: card(21),
        })
        self.effects = {5: [{'evento': 'regra_deck', 'acao': 'limite_copias_deck',
                            'alvo': 'proprio', 'valor': 1}]}
        self.quotas = {0: 17, 1: 16, 20: 3, 21: 2, 23: 2}

    def test_generator_respects_quotas_power_copies_and_equip_compatibility(self):
        result = generate_deck(
            self.cards, self.effects, {(5, 15): 1001}, {1003: {5}, 1004: {1000}},
            self.quotas, max_atk=1500, max_def=1200, difficulty='Máximo', rng=Random(17),
        )
        self.assertEqual(len(result.cards), 40)
        self.assertEqual(Counter(self.cards[cid]['tipo_id'] for cid in result.cards), self.quotas)
        self.assertEqual(result.cards.count(5), 1)
        self.assertEqual(result.cards.count(1003), 2)
        self.assertIn(686, result.cards)
        self.assertNotIn(1004, result.cards)
        self.assertTrue(all(self.cards[cid]['ataque'] <= 1500 and self.cards[cid]['defesa'] <= 1200
                            for cid in result.cards if self.cards[cid]['tipo_id'] in MONSTER_TYPES))
        self.assertIn((5, 15, 1001), result.fusions)
        self.assertNotIn(1001, result.cards)

    def test_impossible_quotas_are_reported_without_partial_deck(self):
        with self.assertRaisesRegex(ModError, '40 cartas'):
            generate_deck(self.cards, self.effects, {}, {}, {0: 39})
        with self.assertRaisesRegex(ModError, 'equipamentos'):
            generate_deck(self.cards, self.effects, {}, {1003: {1001}}, self.quotas)
