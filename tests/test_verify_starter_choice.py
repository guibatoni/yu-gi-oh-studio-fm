"""A conferência do BIN ignora os pools iniciais quando a escolha de deck está ativa."""
import unittest
from types import SimpleNamespace
from fmstudio.disc_verify import drop_replaced_starters
from fmstudio.ps1_starter_choice import SETTINGS_KEY


def project(enabled):
    return SimpleNamespace(metadata={SETTINGS_KEY: {'ativado': enabled, 'decks': ['A', 'B']}})


class VerifyStarterChoiceTests(unittest.TestCase):
    def plan(self):
        return SimpleNamespace(starters=[(40, (1,) * 722)])

    def test_choice_on_drops_pools_like_build(self):
        self.assertEqual(drop_replaced_starters(project(True), self.plan(), 'god24').starters, [])

    def test_choice_off_keeps_pools(self):
        self.assertTrue(drop_replaced_starters(project(False), self.plan(), 'god24').starters)

    def test_without_native_profile_keeps_pools(self):
        self.assertTrue(drop_replaced_starters(project(True), self.plan(), None).starters)


if __name__ == '__main__':
    unittest.main()
