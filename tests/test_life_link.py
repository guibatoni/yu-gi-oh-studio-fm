"""Regression tests for life-link, its event validation, and exact-ID deck bonuses."""
import unittest

from fmstudio.core import ModError, check_effect
from fmstudio.duel_engine import DuelLab
from fmstudio.continuous import resolve_field


def creature(cid, atk=1500, defense=1000, typ=0):
    return {'nome': f'Carta {cid}', 'tipo_id': typ, 'atributo_id': 1,
            'ataque': atk, 'defesa': defense, 'guardian_1_id': 0,
            'guardian_2_id': 0}


def unit(cid, side, slot, atk=1500, defense=1000):
    return {'card_id': cid, 'lado': side, 'slot': slot, 'tipo_id': 0,
            'atributo_id': 1, 'ataque': atk, 'defesa': defense, 'face_up': True,
            'posicao': 'ataque'}


LIFE = {'evento': 'atacar', 'acao': 'vinculo_vida',
        'alvo': 'proprio', 'valor': 0}


class LifeLinkTests(unittest.TestCase):
    def test_validation_and_bad_event(self):
        self.assertEqual(check_effect(LIFE)['valor'], 0)
        for invalid in ({**LIFE, 'evento': 'invocar'},
                        {**LIFE, 'alvo': 'inimigo'}, {**LIFE, 'valor': 100}):
            with self.assertRaises(ModError):
                check_effect(invalid)

    def test_direct_attack_heals_exact_effective_attack(self):
        lab = DuelLab({1: creature(1)}, {1: [LIFE]})
        lab.set_field([unit(1, 'jogador', 1)])
        lab.lp['jogador'] = 4000
        result = lab.attack('jogador', 1)
        self.assertEqual(result['cura_lp_vinculo'], 1500)
        self.assertEqual(lab.lp['jogador'], 5500)
        self.assertEqual(lab.lp['adversario'], 6500)

    def test_defense_attack_heals_without_battle_damage(self):
        lab = DuelLab({1: creature(1), 2: creature(2, defense=1900)}, {1: [LIFE]})
        enemy = unit(2, 'adversario', 1, defense=1900)
        enemy['posicao'] = 'defesa'
        lab.set_field([unit(1, 'jogador', 1), enemy])
        lab.lp['jogador'] = 4000
        result = lab.attack('jogador', 1, target_slot=1, against='defesa')
        self.assertEqual(result['cura_lp_vinculo'], 1500)
        self.assertEqual(lab.lp['jogador'], 5100)  # 1500 healed, 400 recoil

    def test_attacked_lifelink_monster_heals_its_owner(self):
        lab = DuelLab({1: creature(1, atk=1000), 2: creature(2, atk=1800)}, {2: [LIFE]})
        lab.set_field([unit(1, 'jogador', 1, atk=1000), unit(2, 'adversario', 1, atk=1800)])
        lab.lp['adversario'] = 4000
        result = lab.attack('jogador', 1, target_slot=1, against='ataque')
        self.assertEqual(result['cura_lp_vinculo'], 0)
        self.assertEqual(result['cura_lp_vinculo_alvo'], 1800)
        self.assertEqual(lab.lp['adversario'], 5800)
        self.assertEqual(lab.lp['jogador'], 8000 - 800)

    def test_both_lifelink_monsters_heal_both_owners(self):
        lab = DuelLab({1: creature(1, atk=1500), 2: creature(2, atk=1500)}, {1: [LIFE], 2: [LIFE]})
        lab.set_field([unit(1, 'jogador', 1), unit(2, 'adversario', 1)])
        lab.lp = {'jogador': 1000, 'adversario': 1000}
        lab.attack('jogador', 1, target_slot=1, against='ataque')
        self.assertEqual(lab.lp, {'jogador': 2500, 'adversario': 2500})

    def test_ps1_rule_bit_for_lifelink(self):
        from fmstudio.ps1_runtime import PROTECTIONS, SUPPORTED
        from fmstudio.ps1_lifelink import LIFELINK
        self.assertIn('vinculo_vida', SUPPORTED)
        self.assertEqual(PROTECTIONS['vinculo_vida'], LIFELINK)
        others = 0
        for key, value in PROTECTIONS.items():
            if key != 'vinculo_vida':
                others |= value
        self.assertFalse(LIFELINK & others)

    def test_multiple_duplicates_do_not_multiply_heal(self):
        lab = DuelLab({1: creature(1)}, {1: [LIFE, LIFE]})
        lab.set_field([unit(1, 'jogador', 1)])
        lab.lp['jogador'] = 2000
        self.assertEqual(lab.attack('jogador', 1)['cura_lp_vinculo'], 1500)
        self.assertEqual(lab.lp['jogador'], 3500)

    def test_exact_card_id_counts_in_initial_deck(self):
        bonus = check_effect({'evento':'continuo','acao':'bonus_por_carta_id',
            'alvo':'proprio','carta_referencia_id':723,'origem_contagem':'deck',
            'escopo':'aliados','valor':200,'valor_def':100})
        cards = {1:creature(1), 723:creature(723), 724:creature(724)}
        field = [unit(1, 'jogador', 1)]
        resolved, _ = resolve_field(field, {1:[bonus]}, catalog=cards,
            zones={'deck_inicial':{'jogador':(723,724,723), 'adversario':()}})
        self.assertEqual(resolved[0]['ataque'], 1900)
        self.assertEqual(resolved[0]['defesa'], 1200)


if __name__ == '__main__':
    unittest.main()
