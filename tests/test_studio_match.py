"""Regression tests for Studio matches and the expanded project format."""
from collections import Counter
from pathlib import Path
from random import Random
import tempfile
import unittest

from fmstudio.core import Project, ModError
from fmstudio.duel_ai import choose_attack, choose_play, play_ai_turn
from fmstudio.duel_engine import DuelLab, parse_card_ids
from fmstudio.duel_match import Attack, DuelMatch, make_match
from fmstudio.expanded import resolve_references
from fmstudio.guardian import guardian_bonuses
from fmstudio.mod_data import (
    CONFIG_KEY, deal_deck, drop_weights, normalize_rules, save_rules, starting_life,
)
from fmstudio.tables import SUPREME

PLAYER, CPU = 'jogador', 'adversario'


def card(attack=0, defense=0, *, kind=0, attribute=0, stars=(0,0)):
    return {'ataque':attack,'defesa':defense,'tipo_id':kind,'atributo_id':attribute,
            'guardian_1_id':stars[0],'guardian_2_id':stars[1]}


def unit(side, slot, cid, row, *, star=0, position='ataque'):
    return dict(row,lado=side,slot=slot,card_id=cid,face_up=True,
                guardian_id=star,posicao=position)


def effect(action, value, *, event='continuo', target='proprio', **extra):
    return {'evento':event,'acao':action,'alvo':target,'valor':value,**extra}


class StudioMatchTests(unittest.TestCase):
    def setUp(self):
        self.cards = {1:card(1000, 900), 2:card(2200, 1500), 3:card(1000, 1200),
                      4:card(50, 50), 90000:card(3000, 2400, stars=(8,SUPREME)),
                      90001:card(kind=20), 90002:card(kind=21), 90003:card(kind=22),
                      90004:card(kind=23)}
        self.decks = {PLAYER:[1,2,3,4], CPU:[1,2,3,4]}

    def test_fair_draws_follow_each_shuffled_deck(self):
        decks = {PLAYER:[1,2,3,4,90000,90001,90002], CPU:[1,2,3,4,90004,90003,90000]}
        class Capture(Random):
            def __init__(self):
                super().__init__(81)
                self.orders = []
            def shuffle(self, values):
                super().shuffle(values)
                self.orders.append(list(values))
        rng = Capture()
        game = DuelMatch(self.cards, {}, decks, rng=rng)
        for index, side in enumerate((PLAYER,CPU)):
            order = rng.orders[index]
            self.assertEqual(game.hands[side], order[:5])
            self.assertEqual(game.decks[side], order[5:])
            self.assertEqual(Counter(order), Counter(decks[side]))
            game.hands[side].pop()
            self.assertEqual(game.draw(side), order[5:6])
            self.assertEqual(game.decks[side], order[6:])

    def test_regular_summon_in_the_opening_requires_the_ability(self):
        for side in (PLAYER, CPU):
            for allowed in (False, True):
                with self.subTest(side=side, allowed=allowed):
                    effects = {1: [effect('ataque_primeiro_turno', 0)]} if allowed else {}
                    game = DuelMatch(self.cards, effects, self.decks, rng=Random(42), first=side)
                    action = next(a for a in game.legal_plays(side)
                                  if a.position == 'ataque' and a.card_id == 1)
                    game.play(side, action)
                    if allowed:
                        self.assertEqual(game.attack(side, action.slot)['dano_lp_oponente'], 1000)
                    else:
                        self.assertEqual(game.legal_attacks(side), [])
                        self.assertIsNone(choose_attack(game, side))
                        with self.assertRaisesRegex(ModError, 'abertura do duelo'):
                            game.preview_attack(side, action.slot)
                        with self.assertRaises(ModError):
                            game.attack(side, action.slot)

    def test_life_gain_on_summon_works_once_and_keeps_2000_lp(self):
        cards = {2: card(1100, 800), 35: card(1500, 1100)}
        effects = {2: [effect('cura_lp', 2000, event='invocar', target='proprio')]}
        game = DuelMatch(cards, effects, {PLAYER: [2, 35], CPU: [35]},
                         first=PLAYER, rng=Random(4))
        game.lp[PLAYER] = 8000
        play = next(a for a in game.legal_plays(PLAYER)
                    if a.card_id == 2 and not a.face_up and a.position == 'defesa')
        game.play(PLAYER, play)
        self.assertEqual(game.lp[PLAYER], 10000)
        gained = [entry for entry in game.logs if entry['acao'] == 'cura_lp']
        self.assertEqual(len(gained), 1)
        self.assertEqual((gained[0]['valor'], gained[0]['alvo']), (2000, PLAYER))
        game.end_turn(PLAYER)
        game.end_turn(CPU)
        game.set_position(PLAYER, play.slot, 'ataque')
        self.assertEqual(game.lp[PLAYER], 10000)
        self.assertEqual(sum(entry['acao'] == 'cura_lp' for entry in game.logs), 1)

    def test_face_down_attack_position_with_first_turn_ability_reveals_on_attack(self):
        cards = {35: card(1200, 900), 2: card(900, 700)}
        effects = {35: [effect('ataque_primeiro_turno', 0)]}
        game = DuelMatch(cards, effects, {PLAYER: [35], CPU: [2]},
                         first=PLAYER, rng=Random(8))
        play = next(a for a in game.legal_plays(PLAYER)
                    if a.card_id == 35 and not a.face_up and a.position == 'ataque')
        game.play(PLAYER, play)
        self.assertFalse(game.get(PLAYER, play.slot)['face_up'])
        self.assertIn(Attack(play.slot, None), game.legal_attacks(PLAYER))
        result = game.attack(PLAYER, play.slot)
        self.assertTrue(game.get(PLAYER, play.slot)['face_up'])
        self.assertEqual(result['dano_lp_oponente'], 1200)

    def test_face_down_without_first_turn_cannot_attack_opening(self):
        cards = {35: card(1200, 900), 2: card(900, 700)}
        game = DuelMatch(cards, {}, {PLAYER: [35], CPU: [2]},
                         first=PLAYER, rng=Random(8))
        play = next(a for a in game.legal_plays(PLAYER)
                    if a.card_id == 35 and not a.face_up and a.position == 'ataque')
        game.play(PLAYER, play)
        self.assertEqual(game.legal_attacks(PLAYER), [])
        with self.assertRaises(ModError):
            game.attack(PLAYER, play.slot)
        self.assertFalse(game.get(PLAYER, play.slot)['face_up'])

    def test_face_down_defense_remains_unable_to_attack_opening(self):
        cards = {35: card(1200, 900), 2: card(900, 700)}
        effects = {35: [effect('ataque_primeiro_turno', 0)]}
        game = DuelMatch(cards, effects, {PLAYER: [35], CPU: [2]},
                         first=PLAYER, rng=Random(8))
        play = next(a for a in game.legal_plays(PLAYER)
                    if a.card_id == 35 and not a.face_up and a.position == 'defesa')
        game.play(PLAYER, play)
        self.assertEqual(game.legal_attacks(PLAYER), [])
        with self.assertRaises(ModError):
            game.attack(PLAYER, play.slot)

    def test_regular_summon_can_attack_after_the_opening_on_either_side(self):
        for opener, side in ((PLAYER, CPU), (CPU, PLAYER)):
            game = DuelMatch(self.cards, {}, self.decks, rng=Random(42), first=opener)
            game.end_turn(opener)
            action = next(a for a in game.legal_plays(side) if a.position == 'ataque' and a.card_id == 1)
            game.play(side, action)
            self.assertEqual(game.turns[side], 1)
            self.assertEqual(game.attack(side, action.slot)['dano_lp_oponente'], 1000)

    def test_opening_fusions_check_the_result_ability_for_both_fusion_paths(self):
        haste = effect('ataque_primeiro_turno', 0)
        for side in (PLAYER, CPU):
            for from_field in (False, True):
                for result_has_ability in (False, True):
                    with self.subTest(side=side, from_field=from_field, allowed=result_has_ability):
                        effects = {1: [haste]}
                        if result_has_ability:
                            effects[90000] = [haste]
                        game = DuelMatch(self.cards, effects, self.decks, first=side,
                                         fusions={(1,4):90000}, rng=Random(42))
                        if from_field:
                            game.set_field([unit(side,1,1,self.cards[1])])
                        fusion = next(a for a in game.legal_plays(side)
                                      if a.kind == 'fusao' and a.position == 'ataque'
                                      and bool(a.target) == from_field)
                        game.play(side, fusion)
                        self.assertEqual(game.get(side, fusion.slot)['card_id'], 90000)
                        if result_has_ability:
                            self.assertEqual(game.legal_attacks(side), [Attack(fusion.slot, None)])
                            self.assertEqual(game.attack(side, fusion.slot)['dano_lp_oponente'], 3000)
                        else:
                            self.assertEqual(game.legal_attacks(side), [])
                            with self.assertRaises(ModError):
                                game.attack(side, fusion.slot)

    def test_team_trades_equal_monster_then_second_attacks_directly(self):
        game = DuelMatch(self.cards, {}, self.decks, rng=Random(21))
        game.end_turn(PLAYER)
        game.set_field([unit(PLAYER,1,3,self.cards[3]), unit(CPU,1,1,self.cards[1]),
                        unit(CPU,2,2,self.cards[2])])
        self.assertEqual(choose_attack(game), Attack(1,1))
        attacks = [row for row in play_ai_turn(game) if row['acao'] == 'ataque']
        self.assertEqual(set(attacks[0]['destruidos']), {(PLAYER,1),(CPU,1)})
        self.assertTrue(any(row['origem'] == (CPU,2) and row['alvo'] == ('LP',PLAYER)
                            for row in attacks[1:]))

    def test_advantageous_one_on_one_trade_with_the_opening_ability(self):
        effects = {1: [effect('ataque_primeiro_turno', 0)]}
        game = DuelMatch(self.cards, effects, self.decks, rng=Random(21), first=CPU,
                         initial_lp={PLAYER:7000, CPU:9500})
        game.set_field([unit(PLAYER,1,3,self.cards[3]), unit(CPU,1,1,self.cards[1])])
        self.assertEqual(choose_attack(game), Attack(1,1))

    def test_ai_uses_effective_guardian_power_when_attacking(self):
        game = DuelMatch(self.cards, {}, self.decks, rng=Random(21))
        game.end_turn(PLAYER)
        game.set_field([unit(PLAYER,1,3,self.cards[3],star=SUPREME),
                        unit(CPU,1,1,self.cards[1],star=8)])
        self.assertIsNone(choose_attack(game))
        game.set_field([unit(PLAYER,1,3,self.cards[3],star=8),
                        unit(CPU,1,1,self.cards[1],star=SUPREME)])
        self.assertEqual(choose_attack(game), Attack(1,1))
        result = game.attack(CPU,1,target_slot=1)
        self.assertEqual(result['bonus_guardian'], (700,0))
        self.assertEqual(result['dano_lp_oponente'],700)

    def test_supreme_wins_all_retail_stars_and_defends_with_700(self):
        for star in range(1,11):
            self.assertEqual(guardian_bonuses(SUPREME,star),(700,0))
            self.assertEqual(guardian_bonuses(star,SUPREME),(0,700))
        self.assertEqual(guardian_bonuses(SUPREME,SUPREME),(0,0))
        game = DuelMatch(self.cards, {}, self.decks, first=CPU)
        game.end_turn(CPU)
        game.set_field([unit(PLAYER,1,1,self.cards[1],star=8),
                        unit(CPU,1,3,self.cards[3],star=SUPREME,position='defesa')])
        result = game.attack(PLAYER,1,target_slot=1)
        self.assertEqual(result['atributos_alvo'],(1700,1900))
        self.assertEqual(result['dano_lp_jogador'],900)

    def test_ai_fuses_and_chooses_supreme_against_visible_rival(self):
        self.cards[90000].update(ataque=3200, defesa=2800)
        game = DuelMatch(self.cards, {}, {PLAYER:[3], CPU:[1,4]},
                         fusions={(1,4):90000})
        game.end_turn(PLAYER)
        game.set_field([unit(PLAYER,1,3,self.cards[3],star=9)])
        action = choose_play(game)
        self.assertEqual((action.kind,action.card_id,action.star),('fusao',90000,SUPREME))
        game.play(CPU,action)
        self.assertEqual(sorted(game.graveyards[CPU]),[1,4])

    def test_ai_avoids_losing_star_against_revealed_monster(self):
        cards = {1: card(2500, 2300, stars=(2, 3)),
                 2: card(1100, 900, stars=(1, 1))}
        game = DuelMatch(cards, {}, {PLAYER: [2], CPU: [1]}, first=CPU, rng=Random(3))
        game.set_field([unit(PLAYER, 1, 2, cards[2], star=1)])
        # Jupiter (2) loses to Mars (1). Saturn (3) is neutral.
        self.assertEqual(guardian_bonuses(2, 1), (0, 500))
        self.assertEqual(guardian_bonuses(3, 1), (0, 0))
        action = choose_play(game)
        self.assertIsNotNone(action)
        self.assertEqual((action.kind, action.card_id, action.star), ('monstro', 1, 3))
        game.play(CPU, action)
        self.assertEqual(game.get(CPU, action.slot)['guardian_id'], 3)

    def test_ai_chooses_winning_star_instead_of_losing_star(self):
        cards = {1: card(2500, 2300, stars=(4, 2)),
                 2: card(1100, 900, stars=(3, 3))}
        game = DuelMatch(cards, {}, {PLAYER: [2], CPU: [1]}, first=CPU, rng=Random(3))
        game.set_field([unit(PLAYER, 1, 2, cards[2], star=3)])
        # Saturn (3) beats Uranus (4), while Jupiter (2) beats Saturn (3).
        self.assertEqual(guardian_bonuses(4, 3), (0, 500))
        self.assertEqual(guardian_bonuses(2, 3), (500, 0))
        action = choose_play(game)
        self.assertIsNotNone(action)
        self.assertEqual(action.star, 2)

    def test_ai_minimizes_unavoidable_guardian_disadvantages(self):
        cards = {1: card(2700, 2300, stars=(2, 4)),
                 2: card(1000, 900, stars=(1, 1)),
                 3: card(1100, 950, stars=(3, 3))}
        game = DuelMatch(cards, {}, {PLAYER: [2, 3], CPU: [1]}, first=CPU, rng=Random(4))
        game.set_field([unit(PLAYER, 1, 2, cards[2], star=1),
                        unit(PLAYER, 2, 3, cards[3], star=3)])
        # Both choices lose to one rival. Jupiter (2) also beats Saturn (3).
        action = choose_play(game)
        self.assertIsNotNone(action)
        self.assertEqual(action.star, 2)

    def test_ai_does_not_inspect_hidden_opponent_guardian(self):
        cards = {1: card(2500, 2300, stars=(2, 3)),
                 2: card(1000, 900, stars=(1, 3))}
        choices = []
        for secret_star in (1, 3):
            game = DuelMatch(cards, {}, {PLAYER: [2], CPU: [1]}, first=CPU,
                             rng=Random(3))
            hidden = unit(PLAYER, 1, 2, cards[2], star=secret_star)
            hidden['face_up'] = False
            game.set_field([hidden])
            choices.append(choose_play(game))
        self.assertIsNotNone(choices[0])
        self.assertEqual(choices[0], choices[1])

    def test_two_fusion_paths_ritual_and_equip_above_722(self):
        self.cards[91000] = card(4550,2900,stars=(SUPREME,0))
        effects = {90004:[effect('equip_atk',5000,event='equipado',target='monstro_equipado')]}
        game = DuelMatch(self.cards,effects,{PLAYER:[1,4,90003,90004],CPU:[2,3]},
                         fusions={(1,4):90000},rituals={90003:([90000],91000)},
                         equips={90004:{91000}}, rng=Random(7))
        self.assertTrue(any(a.kind == 'fusao' and len(a.hand) == 2 for a in game.legal_plays(PLAYER)))
        game.set_field([unit(PLAYER,1,1,self.cards[1])])
        fusion = next(a for a in game.legal_plays(PLAYER) if a.kind == 'fusao' and a.target)
        game.play(PLAYER,fusion)
        game.end_turn(PLAYER)
        game.end_turn(CPU)
        ritual = next(a for a in game.legal_plays(PLAYER) if a.kind == 'ritual')
        game.play(PLAYER,ritual)
        game.end_turn(PLAYER)
        game.end_turn(CPU)
        equip = next(a for a in game.legal_plays(PLAYER) if a.kind == 'equip')
        game.play(PLAYER,equip)
        self.assertEqual(game.get(PLAYER,1)['card_id'],91000)
        self.assertEqual(game.resolve()[0][0]['ataque'],9550)

    def test_ai_casts_a_spell_for_lethal_instead_of_taking_damage(self):
        effects = {90001:[effect('dano_lp',9000,event='invocar',target='inimigo')]}
        game = DuelMatch(self.cards,effects,{PLAYER:[2],CPU:[4,90001]},
                         first=CPU,initial_lp={PLAYER:8000,CPU:350})
        game.set_field([unit(PLAYER,1,2,self.cards[2]), unit(CPU,1,4,self.cards[4])])
        self.assertIsNone(choose_attack(game))
        self.assertEqual(choose_play(game).card_id,90001)
        play_ai_turn(game)
        self.assertEqual(game.winner,CPU)

    def test_custom_trap_removes_attacker_and_moves_cards_to_graveyard(self):
        effects = {90002:[effect('dano_monstro_alvo',3000,event='atacar',target='monstro_alvo')]}
        game = DuelMatch(self.cards,effects,{PLAYER:[90002],CPU:[1]})
        game.play(PLAYER,game.legal_plays(PLAYER)[0])
        game.end_turn(PLAYER)
        game.play(CPU,next(a for a in game.legal_plays(CPU) if a.position == 'ataque'))
        result = game.attack(CPU,1)
        self.assertTrue(result['interrompido'])
        self.assertEqual(game.graveyards[PLAYER],[90002])
        self.assertEqual(game.graveyards[CPU],[1])

    def test_face_down_summon_burn_fires_once_with_both_sides(self):
        for side, enemy in ((PLAYER, CPU), (CPU, PLAYER)):
            with self.subTest(side=side):
                effects = {1: [effect('dano_lp', 500, event='invocar', target='inimigo')]}
                game = DuelMatch(self.cards, effects, self.decks, first=side, initial_lp=400)
                play = next(a for a in game.legal_plays(side) if a.card_id == 1 and not a.face_up)
                game.play(side, play)
                self.assertEqual(game.lp, {side: 400, enemy: 0})
                self.assertEqual(game.winner, side)
                self.assertFalse(game.get(side, play.slot)['face_up'])
                game.resolve()
                burns = [row for row in game.logs if row['acao'] == 'dano_lp']
                self.assertEqual(len(burns), 1)
                self.assertEqual((burns[0]['carta'], burns[0]['evento'], burns[0]['valor']), (1, 'invocar', 400))

    def test_stats_keep_initial_deck_bonus_and_react_to_graveyard(self):
        large = 10**120
        self.cards[90000].update(ataque=large, defesa=large, atributo_id=3)
        self.cards[2]['atributo_id'] = 3
        self.cards[3]['atributo_id'] = 3
        effects = {90000:[
            effect('bonus_deck_tipo',300,tipo_id=-1,atributo_id=3,valor_def=30),
            effect('bonus_cemiterio_tipo',50,tipo_id=0,atributo_id=3,valor_def=5),
        ]}
        lab = DuelLab(self.cards,effects,initial_lp=large)
        lab.set_deck(PLAYER,[2,90000])
        lab.set_hand(PLAYER,[90000])
        lab.set_field([unit(PLAYER,1,90000,self.cards[90000])])
        self.assertEqual(lab.inspect_zone(PLAYER,'mao')[0]['ataque'],large+600)
        self.assertEqual(lab.inspect_zone(PLAYER,'deck')[1]['defesa'],large+60)
        lab.draw(PLAYER)
        self.assertEqual(lab.decks[PLAYER], [90000])
        self.assertEqual(lab.resolve()[0][0]['ataque'],large+600)
        self.assertEqual(lab.effective_card(PLAYER,90000)['defesa'],large+60)
        lab.set_graveyard(PLAYER,[2,3,1])
        self.assertEqual(lab.effective_card(PLAYER,90000)['ataque'],large+700)
        lab.set_graveyard(PLAYER,[])
        self.assertEqual(lab.effective_card(PLAYER,90000)['ataque'],large+600)

    def test_weighted_pools_reserve_cards_required_for_later_draws(self):
        cards = {1:card(),2:card()}
        profile = {'pools':[{'compras':3,'pesos':{1:10**10,2:1}},
                            {'compras':3,'pesos':{1:1}}]}
        self.assertEqual(deal_deck(profile,cards,{},Random(8)),[2,2,2,1,1,1])
        profile['pools'][1]['compras'] = 4
        with self.assertRaises(ModError):
            deal_deck(profile,cards,{},Random(8))

    def test_project_roundtrip_expanded_card_relations_and_mod_rules(self):
        with tempfile.TemporaryDirectory() as path:
            project = Project.create(Path(path),'Novo')
            mod_monster = project.add_card(type_id=0,name='Conta Suprema',card_id=5_555_555)
            spell, trap, ritual, equip = [project.add_card(type_id=i) for i in (20,21,22,23)]
            rival = project.add_card(type_id=0)
            self.assertEqual(spell,723)
            huge = 10**5000
            project.set_card(mod_monster,{'ataque':huge,'defesa':90000,'guardian_1_id':SUPREME})
            project.add_effect(mod_monster,effect('bonus_por_carta_id',100,valor_def=9,
                                                  carta_referencia_id=rival,origem_contagem='cemiterio'))
            save_rules(project, {
                'lp_jogador':huge,
                'duelistas':{'1':{'lp':huge+1,'deck':{'cartas':[rival]},
                                  'drops':{'S-TEC':{spell:10,'0'+str(trap):2}}}},
                'iniciais':{'Principal':{'peso':3,'cartas':[mod_monster,spell,trap,ritual,equip]}},
                'receitas':{'rituais':{str(ritual):{'tributos':[rival],'resultado':mod_monster}},
                            'equipamentos':{str(equip):[mod_monster]}},
            })
            reopened = Project.open(Path(path))
            self.assertEqual(reopened.get(mod_monster)['ataque'],huge)
            self.assertEqual(resolve_references('{card:5555555}',reopened.cards),'Conta Suprema')
            self.assertEqual(parse_card_ids('5555555'),[mod_monster])
            self.assertEqual(starting_life(reopened,1),{PLAYER:huge,CPU:huge+1})
            game = make_match(reopened,None,1,'Principal',rng=Random(12))
            self.assertEqual(set(game.hands[PLAYER]),{mod_monster,spell,trap,ritual,equip})
            config = normalize_rules(reopened.metadata[CONFIG_KEY],reopened.cards)
            self.assertEqual(drop_weights(config,{},1,'S-TEC'),{spell:10,trap:2})
            output, _ = reopened.export(include_ps1=False)
            self.assertTrue((output/'edicao_mod.json').is_file())
