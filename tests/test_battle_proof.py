"""Efeito "indestrutível por criaturas": simulador do Studio e runtime do PS1."""
import struct
import unittest

from fmstudio import ps1_expanded_runtime_blob, ps1_runtime_blob
from fmstudio.continuous import resolve_field
from fmstudio.core import check_effect
from fmstudio.ps1_runtime import PROTECTIONS


def effect(action, event='continuo', target='proprio'):
    return {'evento': event, 'acao': action, 'alvo': target, 'valor': 0}


class BattleProofTests(unittest.TestCase):
    def test_effect_is_valid_and_mapped_to_ps1_bit(self):
        self.assertEqual(check_effect(effect('monstro_indestrutivel_batalha'))['acao'], 'monstro_indestrutivel_batalha')
        self.assertEqual(check_effect(effect('equip_indestrutivel_batalha', 'equipado', 'monstro_equipado'))['valor'], 0)
        self.assertEqual(PROTECTIONS['monstro_indestrutivel_batalha'], 64)
        self.assertEqual(PROTECTIONS['equip_indestrutivel_batalha'], 64)
        self.assertFalse(set(PROTECTIONS.values()) - {1, 2, 3, 4, 8, 16, 32, 64, 128})

    def test_runtime_battle_checks_accept_new_bit(self):
        for bundle in (ps1_runtime_blob, ps1_expanded_runtime_blob):
            start = bundle.ENTRY_POINTS['Battle'] - bundle.RUNTIME_BASE
            end = bundle.ENTRY_POINTS['Resume'] - bundle.RUNTIME_BASE
            jal = 0x0C000000 | ((bundle.ENTRY_POINTS['protection'] & 0x0FFFFFFF) >> 2)
            checks = [struct.unpack_from('<I', bundle.RUNTIME, o)[0] for o in range(start, end, 4)
                      if struct.unpack_from('<I', bundle.RUNTIME, o - 8)[0] == jal]
            self.assertEqual(checks.count(0x30420044), 3, bundle.__name__)   # batalha: 0x4 | 0x40
            self.assertEqual(checks.count(0x30420008), 1, bundle.__name__)   # perfurante intacto
            # Efeitos (mágicas/armadilhas) continuam testando só INDESTRUCTIBLE.
            collect = bundle.ENTRY_POINTS['CollectTargets'] - bundle.RUNTIME_BASE
            words = [struct.unpack_from('<I', bundle.RUNTIME, o)[0] for o in range(collect, collect + 0x80, 4)]
            self.assertNotIn(0x30420044, words)

    def test_studio_simulator_battle_vs_effects(self):
        from fmstudio.duel_engine import DuelLab
        from tests.test_quick_abilities import effects, monster
        lab = DuelLab({1: {'tipo_id': 0}, 2: {'tipo_id': 0}},
                      {'2': effects(monstro_indestrutivel_batalha=True)})
        lab.set_field([monster(atk=2000), monster(cid=2, side='adversario', atk=1000)])
        result = lab.attack('jogador', 1, target_slot=1, against='ataque')
        self.assertIsNotNone(lab.get('adversario', 1))            # sobreviveu à batalha
        self.assertEqual(result['dano_lp_oponente'], 1000)        # mas o dano aos LP continua
        unit = next(u for u in lab.resolve()[0] if u['card_id'] == 2)
        self.assertTrue(unit['indestrutivel_batalha'])
        self.assertFalse(unit['indestrutivel'])                   # efeitos de destruição ainda o atingem


if __name__ == '__main__':
    unittest.main()
