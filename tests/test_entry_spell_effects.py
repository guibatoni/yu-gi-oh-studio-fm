"""Efeitos de entrada com mágicas do jogo: validação, simulador do Studio e regras PS1."""
import struct
import unittest

from fmstudio.core import ModError, check_effect
from fmstudio.duel_match import DuelMatch
from fmstudio import ps1_entry_effects as ee
from fmstudio.ps1_runtime import compile_effects

PLAYER, CPU = 'jogador', 'adversario'


def card(attack=0, defense=0, *, kind=0):
    return {'ataque': attack, 'defesa': defense, 'tipo_id': kind, 'atributo_id': 0,
            'guardian_1_id': 0, 'guardian_2_id': 0}


def unit(side, slot, cid, row, *, position='ataque', face_up=True):
    return dict(row, lado=side, slot=slot, card_id=cid, face_up=face_up, guardian_id=0, posicao=position)


def entry(action, value=0, target='inimigo'):
    return check_effect({'evento': 'invocar', 'acao': action, 'alvo': target, 'valor': value})


class ValidationTests(unittest.TestCase):
    def test_values_and_event(self):
        self.assertEqual(entry('espadas_reveladoras', 2)['valor'], 2)
        self.assertEqual(entry('mudar_terreno', 0, 'proprio')['valor'], 0)
        for bad in (lambda: entry('espadas_reveladoras', 4),
                    lambda: entry('mudar_terreno', 7, 'proprio'),
                    lambda: entry('revelar_cartas', 5),
                    lambda: entry('mudar_terreno', 1),
                    lambda: check_effect({'evento': 'atacar', 'acao': 'revelar_cartas',
                                          'alvo': 'inimigo', 'valor': 0})):
            with self.assertRaises(ModError):
                bad()


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.cards = {1: card(1000, 900), 2: card(1800, 1500), 3: card(1200, 700), 4: card(500, 500),
                      90002: card(kind=21)}

    def game(self, effects):
        game = DuelMatch(self.cards, effects, {PLAYER: [1, 2, 3, 4], CPU: [1, 2, 3, 4]})
        game.set_field([unit(PLAYER, 1, 1, self.cards[1]),
                        unit(CPU, 1, 2, self.cards[2], position='defesa', face_up=False),
                        unit(CPU, 2, 3, self.cards[3])])
        return game

    def test_spells_on_entry(self):
        game = self.game({1: [entry('limpar_armadilhas'), entry('revelar_cartas'),
                              entry('espadas_reveladoras', 2), entry('mudar_terreno', 4, 'proprio'),
                              entry('trocar_posicao')]})
        game.traps[CPU] = [90002]
        game.terrain = 1
        game.apply_event(1, PLAYER, 'invocar', source_slot=1)
        self.assertEqual(game.traps[CPU], [])
        self.assertIn(90002, game.graveyards[CPU])
        self.assertTrue(game.get(CPU, 1)['face_up'])
        self.assertEqual(game.swords[CPU], 2)
        self.assertEqual(game.terrain, 4)
        self.assertEqual(game.get(CPU, 1)['posicao'], 'ataque')
        self.assertEqual(game.get(CPU, 2)['posicao'], 'defesa')

    def test_normal_terrain(self):
        game = self.game({1: [entry('mudar_terreno', 0, 'proprio')]})
        game.terrain = 3
        game.apply_event(1, PLAYER, 'invocar', source_slot=1)
        self.assertIsNone(game.terrain)

    def test_damage_hits_strongest_like_ps1(self):
        damage = check_effect({'evento': 'invocar', 'acao': 'dano_monstro_alvo',
                               'alvo': 'monstro_alvo', 'valor': 600})
        game = self.game({1: [damage]})
        summary = game.apply_event(1, PLAYER, 'invocar', source_slot=1, strict=False)
        self.assertEqual(summary[0]['alvo'], (CPU, 1))
        self.assertFalse(summary[0]['destruido'])
        strongest = next(m for m in game.resolve()[0] if (m['lado'], m['slot']) == (CPU, 1))
        self.assertEqual((strongest['ataque'], strongest['defesa']), (1200, 900))

    def test_damage_only_hits_chosen_type(self):
        self.cards[3]['tipo_id'] = 7
        damage = check_effect({'evento': 'invocar', 'acao': 'dano_monstro_alvo',
                               'alvo': 'monstro_alvo', 'valor': 300, 'tipo_id': 7})
        self.assertEqual(damage['tipo_id'], 7)
        game = self.game({1: [damage]})
        summary = game.apply_event(1, PLAYER, 'invocar', source_slot=1, target_side=CPU,
                                   target_slot=1, strict=False)
        self.assertEqual(summary[0]['alvo'], (CPU, 2))          # o slot 1 não é do tipo
        game = self.game({1: [check_effect(dict(damage, tipo_id=12))]})
        self.assertEqual(game.apply_event(1, PLAYER, 'invocar', source_slot=1, strict=False), [])

    def test_fatal_damage_destroys(self):
        damage = check_effect({'evento': 'invocar', 'acao': 'dano_monstro_alvo',
                               'alvo': 'monstro_alvo', 'valor': 1500})
        game = self.game({1: [damage]})
        summary = game.apply_event(1, PLAYER, 'invocar', source_slot=1, strict=False)
        self.assertTrue(summary[0]['destruido'])
        self.assertIsNone(game.get(CPU, 1))


class CompileTests(unittest.TestCase):
    def test_rules_carry_entry_codes(self):
        class Project:
            metadata = {}
            effects = {'5': [entry('revelar_cartas'), entry('espadas_reveladoras', 1),
                             entry('limpar_armadilhas'), entry('trocar_posicao'),
                             entry('mudar_terreno', 6, 'proprio'),
                             check_effect({'evento': 'invocar', 'acao': 'dano_monstro_alvo',
                                           'alvo': 'monstro_alvo', 'valor': 700}),
                             check_effect({'evento': 'atacar', 'acao': 'dano_monstro_alvo',
                                           'alvo': 'monstro_alvo', 'valor': 700})]}
            cards = {}

            def get(self, cid):
                return {'tipo_id': 0, 'ataque': 1000, 'defesa': 1000}
        plan = compile_effects(Project(), True)
        self.assertEqual(len(plan.pending), 1)
        offset = struct.unpack_from('<H', plan.data, 2 + 2 * 5)[0]
        count = plan.data[offset + 3]
        bonuses = [struct.unpack_from('<BBHHH', plan.data, offset + 8 + 8 * i) for i in range(count)]
        self.assertEqual(bonuses, [
            (ee.OP_SPELL, 8, 350, 0, 0), (ee.OP_SPELL, 10, 348, 1, 0), (ee.OP_SPELL, 13, 672, 0, 0),
            (ee.OP_TOGGLE, 0, 0, 0, 0), (ee.OP_TERRAIN, 1, 6, 0, 0), (ee.OP_DAMAGE, 0, 0xFFFF, 700, 0)])
        self.assertTrue(ee.wanted(plan))


if __name__ == '__main__':
    unittest.main()
