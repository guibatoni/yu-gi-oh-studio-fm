"""Filtros do catálogo de deck: estrela guardiã e fusões (sem Tkinter)."""
import unittest

from fmstudio.card_search import (ALL_STARS, STAR_FILTERS, card_stars, fusion_materials,
                                  fusion_results, fusions_with, has_star, star_label)

CARDS = {
    1: {'tipo_id': 0, 'ataque': 1200, 'guardian_1_id': 1, 'guardian_2_id': 8},    # Mars/Sun
    2: {'tipo_id': 9, 'ataque': 900, 'guardian_1_id': 9, 'guardian_2_id': 10},    # Moon/Venus
    3: {'tipo_id': 20, 'guardian_1_id': 1, 'guardian_2_id': 1},                   # magia
    10: {'tipo_id': 0, 'ataque': 2000, 'guardian_1_id': 1, 'guardian_2_id': 1},
    11: {'tipo_id': 0, 'ataque': 2600, 'guardian_1_id': 2, 'guardian_2_id': 3},
}
FUSIONS = {(1, 2): 10, (2, 1): 10, (2, 4): 11, (4, 2): 11, (5, 6): 10}


class StarFilterTests(unittest.TestCase):
    def test_labels_and_match(self):
        self.assertEqual(STAR_FILTERS[0], ALL_STARS)
        self.assertEqual(star_label(CARDS[1]), 'Mars/Sun')
        self.assertEqual(star_label(CARDS[10]), 'Mars')
        self.assertEqual(card_stars(CARDS[3]), ())          # magia não tem estrela
        self.assertTrue(has_star(CARDS[1], 'Sun'))
        self.assertTrue(has_star(CARDS[1], 'Mars'))
        self.assertFalse(has_star(CARDS[2], 'Mars'))
        self.assertFalse(has_star(CARDS[3], 'Mars'))
        self.assertTrue(has_star(CARDS[3], ALL_STARS))


class FusionFilterTests(unittest.TestCase):
    def test_results_and_materials(self):
        self.assertEqual(fusion_results(FUSIONS), {10, 11})
        self.assertEqual(fusion_materials(FUSIONS, 10), {1: [2], 2: [1], 5: [6], 6: [5]})

    def test_best_fusion_with_deck(self):
        best = fusions_with(FUSIONS, {2}, CARDS)
        self.assertEqual(best, {1: (10, 2), 4: (11, 2)})
        both = fusions_with(FUSIONS, {1, 4}, CARDS)
        self.assertEqual(both[2], (11, 4))                  # 2600 > 2000
        self.assertEqual(fusions_with(FUSIONS, set(), CARDS), {})


if __name__ == '__main__':
    unittest.main()
