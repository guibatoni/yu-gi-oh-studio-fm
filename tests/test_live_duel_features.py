"""Integration coverage for expanded cards, live rank, AI and deck quotas."""
import json
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest

from fmstudio.core import ModError, Project
from fmstudio.deck_generator import (STARTER_MAX_POWER, duelist_preset, generate_deck,
                                     suggest_quantities)
from fmstudio.duel_ai import choose_attack, choose_play, play_ai_turn
from fmstudio.duel_match import Attack, DuelMatch, make_match
from fmstudio.duel_rank import project_rank, rank_grade
from fmstudio.mod_data import CONFIG_KEY, deal_deck, save_rules
from fmstudio.passwords import grant_card, id_code, redeem_id
from fmstudio.tables import CARD_COUNT, DUELIST_COUNT, SUPREME

from test_studio_match import CPU, PLAYER, card, effect, unit


def copy_limit(value):
    return [effect('limite_copias_deck', value, event='regra_deck')]


class LiveDuelFeaturesTests(unittest.TestCase):
    def test_project_card_723_art_export_fusion_equip_and_drop(self):
        with TemporaryDirectory() as temp:
            project = Project.create(Path(temp), 'Fronteira do catálogo')
            last_original = project.add_card(card_id=CARD_COUNT, type_id=0)
            hero = project.add_card(name='Guardião Supremo', type_id=24)
            spell = project.add_card(type_id=20)
            trap = project.add_card(type_id=21)
            ritual = project.add_card(type_id=22)
            equip = project.add_card(type_id=23)
            self.assertEqual((hero, spell, trap, ritual, equip), (723, 724, 725, 726, 727))
            project.set_card(hero, {'ataque': 3400, 'defesa': 3100, 'guardian_1_id': SUPREME,
                                    'guardian_2_id': 9, 'descricao': '{icon:ataque_2x} Milênio'})
            art = Path(__file__).resolve().parents[1] / 'assets' / 'icons' / 'god.png'
            project.attach_art(hero, art)
            project.add_effect(equip, effect('equip_atk', 800, event='equipado', target='monstro_equipado'))
            save_rules(project, {
                'duelistas': {'1': {'deck': {'cartas': [hero]}, 'drops': {'pow': {hero: 9}}}},
                'iniciais': {'Teste': {'cartas': [last_original, last_original, equip, spell, trap]}},
                'receitas': {'fusoes': {f'{last_original},{last_original}': hero},
                             'equipamentos': {equip: [hero]},
                             'rituais': {ritual: {'tributos': [last_original], 'resultado': hero}}},
            })
            project = Project.open(Path(temp))
            saved = project.get(hero)
            self.assertEqual((saved['tipo_id'], saved['ataque'], saved['defesa'],
                              saved['guardian_1_id'], saved['guardian_2_id']), (24, 3400, 3100, SUPREME, 9))
            self.assertEqual(project.art_path(hero).read_bytes(), art.read_bytes())
            self.assertEqual(redeem_id(id_code(hero), project.cards), hero)
            output, _ = project.export(include_ps1=False)
            exported = json.loads((output / 'novas_cartas.json').read_text(encoding='utf-8'))['cartas']
            self.assertEqual(exported[str(hero)], saved)
            game = make_match(project, None, 1, 'Teste', rng=Random(2))
            self.assertEqual(game.hands[CPU], [hero])
            move = next(move for move in game.legal_plays(PLAYER) if move.kind == 'fusao' and move.star == SUPREME)
            game.play(PLAYER, move)
            game.end_turn(PLAYER)
            game.end_turn(CPU)
            game.play(PLAYER, next(move for move in game.legal_plays(PLAYER) if move.kind == 'equip'))
            self.assertEqual(game.resolve()[0][0]['ataque'], 4200)
            game.lp[CPU] = 0
            prize = game.claim_reward(project.metadata[CONFIG_KEY], {}, 1, project_rank(game).grade,
                                      lambda cid: grant_card(project, cid), rng=Random(2))
            self.assertEqual(prize, hero)
            self.assertEqual(Project.open(Path(temp)).metadata['bau_jogador'], {'723': 1})

    def test_rank_follows_play_deck_and_lp_and_uses_retail_boundaries(self):
        cards = {1: card(4000, 3500), 2: card(100, 50), 3: card(kind=20)}
        game = DuelMatch(cards, {}, {PLAYER: [1, 3], CPU: [2]}, rng=Random(2))
        first = project_rank(game)
        self.assertEqual((first.grade, first.score), ('S-POW', 99))
        game.play(PLAYER, next(move for move in game.legal_plays(PLAYER) if move.kind == 'magia'))
        self.assertEqual(project_rank(game).score, 95)
        game.lp[PLAYER] = 700
        rank = project_rank(game)
        self.assertEqual((rank.grade, rank.score), ('A-POW', 84))
        self.assertEqual((rank.counters['cartas_compradas'], rank.counters['cartas_restantes']), (2, 0))
        game.deck_out = CPU
        self.assertEqual((project_rank(game).grade, project_rank(game).score), ('D-TEC', 42))
        self.assertEqual([rank_grade(n) for n in range(0, 100, 10)],
                         ['S-TEC', 'A-TEC', 'B-TEC', 'C-TEC', 'D-TEC',
                          'D-POW', 'C-POW', 'B-POW', 'A-POW', 'S-POW'])

    def test_expert_finds_chains_up_to_five_from_hand_and_field(self):
        cards = {cid: card(1000, 1000) for cid in range(1, 11)}
        cards[9] = card(8800, 5400, stars=(SUPREME, 8))
        recipes = {(1, 2): 6, (3, 6): 7, (4, 7): 8, (5, 8): 9}
        for field in (False, True):
            game = DuelMatch(cards, {}, {PLAYER: [10], CPU: list(range(2 if field else 1, 6))},
                             fusions=recipes, rng=Random(2))
            game.end_turn(PLAYER)
            game.set_field([unit(PLAYER, 1, 10, cards[10], star=8)] +
                           ([unit(CPU, 3, 1, cards[1])] if field else []))
            options = [play for play in game.legal_plays(CPU) if play.kind == 'fusao']
            self.assertEqual({len(move.hand) + int(move.target is not None) for move in options}, {2, 3, 4, 5})
            move = choose_play(game)
            self.assertEqual((move.kind, move.card_id, move.star, len(move.hand)),
                             ('fusao', 9, SUPREME, 4 if field else 5))
            game.play(CPU, move)
            self.assertEqual(set(game.graveyards[CPU]), {1, 2, 3, 4, 5})
            self.assertEqual(project_rank(game, CPU).counters['fusoes'], 4)

    def test_expert_trades_to_win_in_two_attacks(self):
        cards = {1: card(1000, 1000), 2: card(1600, 1200)}
        game = DuelMatch(cards, {}, {PLAYER: [1], CPU: [1, 2]},
                         initial_lp={PLAYER: 1200, CPU: 8000}, rng=Random(3))
        game.end_turn(PLAYER)
        game.set_field([unit(PLAYER, 1, 1, cards[1]), unit(CPU, 1, 1, cards[1]),
                        unit(CPU, 2, 2, cards[2])])
        self.assertEqual(choose_attack(game), Attack(1, 1))
        play_ai_turn(game)
        self.assertEqual(game.winner, CPU)

    def test_bans_fixed_and_pool_decks_and_three_type_starter(self):
        cards = {cid: card(900, 1100, kind=(cid - 1) // 9) for cid in range(1, 28)}
        cards.update({28: card(2200, 1700), 29: card(kind=23), 30: card(kind=23),
                      31: card(kind=20), 40: card(1550, 1500)})
        fusions = {(a, b): 28 for a in range(2, 10) for b in range(10, 28)}
        effects = {1: copy_limit(0), 2: copy_limit(1)}
        for side in (PLAYER, CPU):
            with self.assertRaisesRegex(ModError, 'banida'):
                DuelMatch(cards, effects, {side: [1], (CPU if side == PLAYER else PLAYER): [2]})
        pooled = deal_deck({'pools': [{'compras': 2, 'pesos': {1: 999, 2: 999, 3: 1}}]},
                           cards, effects, Random(2))
        self.assertNotIn(1, pooled)
        self.assertLessEqual(pooled.count(2), 1)
        equips = {29: {2, 10}, 30: {28}}
        counts = suggest_quantities(cards, effects, fusions, equips, starter=True, rng=Random(4))
        deck = generate_deck(cards, effects, fusions, equips, counts, starter=True, rng=Random(4))
        self.assertEqual(len(deck.cards), 40)
        self.assertEqual({cards[cid]['tipo_id'] for cid in deck.cards} - {20, 23}, {0, 1, 2})
        self.assertNotIn(1, deck.cards)
        self.assertNotIn(30, deck.cards)
        self.assertNotIn(40, deck.cards)
        self.assertTrue(all(cards[cid]['ataque'] + cards[cid]['defesa'] <= STARTER_MAX_POWER for cid in deck.cards))
        self.assertGreater(len(deck.fusions), 10)
        self.assertTrue(all(result == 28 for _, _, result in deck.fusions))
        self.assertEqual(duelist_preset(1)[0], (7, 2))
        self.assertTrue(all(duelist_preset(i)[0] for i in range(1, DUELIST_COUNT)))
        self.assertLess(duelist_preset(1)[1], duelist_preset(17)[1])
