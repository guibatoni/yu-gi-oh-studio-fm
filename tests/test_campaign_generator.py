"""Ensaios do gerador progressivo sem ISO, interface gráfica ou downloads."""
import random
import unittest
from collections import Counter

from fmstudio.campaign_generator import (
    campaign_level, campaign_label, generate_campaign_deck,
)
from fmstudio.mod_data import deck_copy_limit, deal_deck


def fixture():
    types = [7, 2, 0, 1, 14, 15, 3, 4, 8, 19]
    cards = {
        cid: {'tipo_id': types[(cid - 1) % len(types)],
              'ataque': 900 + cid % 6 * 100, 'defesa': 700 + cid % 4 * 100,
              'atributo_id': cid % 6}
        for cid in range(1, 61)
    }
    cards.update({
        200: {'tipo_id': 7, 'ataque': 2450, 'defesa': 1700},
        201: {'tipo_id': 7, 'ataque': 2850, 'defesa': 1900},
        202: {'tipo_id': 7, 'ataque': 3300, 'defesa': 2200},
        203: {'tipo_id': 0, 'ataque': 2700, 'defesa': 2200},
        204: {'tipo_id': 0, 'ataque': 3500, 'defesa': 2500},
        723: {'tipo_id': 0, 'ataque': 1500, 'defesa': 1300, 'virtual': True, 'atributo_id': 1},
        724: {'tipo_id': 0, 'ataque': 3900, 'defesa': 3300, 'virtual': True},
    })
    for cid in (330, 332, 335, 336, 337, 348, 349):
        cards[cid] = {'tipo_id': 20, 'ataque': 0, 'defesa': 0}
    for cid in (681, 684, 685, 686):
        cards[cid] = {'tipo_id': 21, 'ataque': 0, 'defesa': 0}
    for cid in (301, 315):
        cards[cid] = {'tipo_id': 23, 'ataque': 0, 'defesa': 0}
    fusions = {
        (1, 2): 200, (200, 3): 201, (201, 4): 202,
        (5, 6): 203, (203, 7): 204, (723, 2): 724,
    }
    # Todas as famílias têm pelo menos algumas fusões válidas de materiais.
    fusions.update({(i, i+1): 200 + i % 5 for i in range(9, 55, 2)})
    effects = {
        str(cid): [{'evento': 'invocar', 'acao': 'dano_lp', 'alvo': 'inimigo', 'valor': 350}]
        for cid in range(1, 26)
    }
    effects['723'] = [{'evento': 'invocar', 'acao': 'dano_lp',
                       'alvo': 'inimigo', 'valor': 1600}]
    equips = {301: {1, 5, 10, 200, 202}, 315: {2, 3, 201, 724}}
    return cards, effects, fusions, equips


class CampaignDeckTests(unittest.TestCase):
    def test_curve_is_monotonic_at_boundaries(self):
        values = [campaign_level(i) for i in range(1, 40)]
        self.assertEqual((values[0], values[-1]), (3.0, 5.0))
        self.assertTrue(all(x <= y for x, y in zip(values, values[1:])))
        self.assertTrue(all(3.0 <= x <= 3.5 for x in values[:10]))
        self.assertTrue(all(3.5 <= x <= 4.3 for x in values[10:25]))
        self.assertTrue(all(4.3 <= x <= 5.0 for x in values[25:]))
        self.assertEqual(len({campaign_label(i) for i in range(1, 40)}), 39)

    def test_valid_ps1_profiles_and_effects(self):
        cards, effects, fusions, equips = fixture()
        for opponent in (1, 10, 11, 25, 26, 39):
            with self.subTest(opponent=opponent):
                generated = generate_campaign_deck(
                    cards, effects, fusions, equips, opponent,
                    rng=random.Random(3))
                self.assertEqual(len(generated.cards), 40)
                self.assertEqual(sum(generated.weights.values()), 2048)
                self.assertTrue(all(1 <= cid <= 722 for cid in generated.cards))
                self.assertGreater(generated.effect_monsters, 0)
                copies = Counter(generated.cards)
                for cid, amount in copies.items():
                    self.assertLessEqual(amount, deck_copy_limit(effects, cid))
                self.assertEqual(len(deal_deck(generated.profile, cards, effects,
                                               rng=random.Random(4))), 40)
                for cid in generated.cards:
                    if cards[cid]['tipo_id'] == 23:
                        self.assertTrue(set(equips[cid]) & (
                            set(generated.cards) |
                            {r for _, _, r in generated.fusions}))

    def test_custom_cards_included_only_in_studio_mode(self):
        cards, effects, fusions, equips = fixture()
        a = generate_campaign_deck(cards, effects, fusions, equips, 39,
                                   rng=random.Random(9), ps1_only=True)
        b = generate_campaign_deck(cards, effects, fusions, equips, 39,
                                   rng=random.Random(9), ps1_only=False)
        self.assertNotIn(723, a.cards)
        self.assertIn(723, b.cards)
        self.assertTrue(any('Studio' in msg for msg in b.notes))

    def test_missing_real_fusions_does_not_fabricate(self):
        cards, effects, _, equips = fixture()
        with self.assertRaisesRegex(ValueError, 'fusões reais'):
            generate_campaign_deck(cards, effects, {}, equips, 1,
                                   rng=random.Random(0))

    def test_weighted_profile_2048_and_no_too_strong_base_monsters(self):
        cards, effects, fusions, equips = fixture()
        deck = generate_campaign_deck(cards, effects, fusions, equips, 39,
                                      rng=random.Random(42))
        for cid in deck.cards:
            if cards[cid]['tipo_id'] not in (20, 21, 22, 23):
                self.assertLessEqual(cards[cid]['ataque'], 1500)
                self.assertLessEqual(cards[cid]['defesa'], 1500)
        self.assertEqual(deck.profile['pools'][0]['compras'], 40)


if __name__ == '__main__':
    unittest.main()
