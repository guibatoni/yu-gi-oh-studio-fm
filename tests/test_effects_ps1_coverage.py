"""Inventário: cada efeito do Studio ou funciona no PS1 ou está declarado como só do simulador."""
import unittest

from fmstudio import core
from fmstudio.ps1_runtime import SUPPORTED

# Efeitos que ainda não têm rotina no PS1 (o BIN os lista como pendentes).
STUDIO_ONLY = {
    'aumentar_atk', 'reduzir_atk', 'aumentar_def', 'reduzir_def',   # mudança de ATK/DEF por evento
    'cura_lp_deck_tipo', 'dano_lp_deck_tipo',                       # LP por carta do tipo no deck
    'descartar_alvo', 'dano_monstro_alvo',
}


class EffectCoverageTests(unittest.TestCase):
    def test_every_action_is_classified(self):
        actions = set(core.ACTIONS)
        self.assertEqual(actions - SUPPORTED - STUDIO_ONLY, set())
        self.assertEqual(STUDIO_ONLY & SUPPORTED, set())
        self.assertIn('bonus_mao_tipo', SUPPORTED)
        self.assertIn('vinculo_vida', SUPPORTED)


if __name__ == '__main__':
    unittest.main()
