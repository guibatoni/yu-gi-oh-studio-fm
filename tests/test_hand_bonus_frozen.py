"""Simulador: bônus por cartas na mão é contado ao entrar em campo e fica fixo (igual ao PS1)."""
import unittest

from fmstudio.core import check_effect
from fmstudio.duel_engine import DuelLab

WARRIOR = 7


def monster(cid, slot=1, side='jogador'):
    return {'lado': side, 'slot': slot, 'card_id': cid, 'tipo_id': WARRIOR,
            'ataque': 1000, 'defesa': 1000, 'face_up': True}


class FrozenHandBonusTests(unittest.TestCase):
    def setUp(self):
        self.cards = {22: {'tipo_id': WARRIOR}, 5: {'tipo_id': WARRIOR}, 6: {'tipo_id': WARRIOR},
                      9: {'tipo_id': 3}}
        effect = check_effect({'evento': 'continuo', 'acao': 'bonus_mao_tipo', 'alvo': 'proprio',
                               'valor': 150, 'valor_def': 150, 'escopo': 'aliados', 'tipo_id': WARRIOR})
        self.lab = DuelLab(self.cards, {'22': [effect]})

    def attack(self):
        return self.lab.resolve()[0][0]['ataque']

    def test_counts_when_entering_and_stays(self):
        self.lab.set_hand('jogador', [5, 9])
        self.lab.set_field([monster(22)])
        self.assertEqual(self.attack(), 1150)              # 1 Guerreiro na mão ao entrar
        self.lab.set_hand('jogador', [5, 6, 5, 9])
        self.assertEqual(self.attack(), 1150)              # comprar não muda
        self.lab.set_hand('jogador', [])
        self.assertEqual(self.attack(), 1150)              # descartar não muda
        # continua fixo quando outro monstro entra ao lado
        self.lab.set_field([monster(22), monster(5, slot=2)])
        self.assertEqual(self.attack(), 1150)

    def test_new_entry_counts_again(self):
        self.lab.set_hand('jogador', [5])
        self.lab.set_field([monster(22)])
        self.lab.set_field([])
        self.lab.set_hand('jogador', [5, 6, 5])
        self.lab.set_field([monster(22, slot=3)])
        self.assertEqual(self.attack(), 1450)


if __name__ == '__main__':
    unittest.main()
