"""Deck inicial temático: tema, fusão-chave e teto de força."""
import unittest
from collections import Counter
from random import Random

from fmstudio.core import ModError
from fmstudio.themed_deck import LEVELS, design

FAIRY, ROCK, DRAGON, MAGIC, EQUIP = 8, 18, 0, 20, 23


def catalog():
    cards, fusions, equips = {}, {}, {}
    cid = 1

    def add(typ, atk, name):
        nonlocal cid
        cards[cid] = {'nome': name, 'tipo_id': typ, 'ataque': atk, 'defesa': atk // 2}
        cid += 1
        return cid - 1

    fairies = [add(FAIRY, 500 + 70 * i, f'Fada {i}') for i in range(14)]
    rocks = [add(ROCK, 600 + 50 * i, f'Rocha {i}') for i in range(6)]
    dragons = [add(DRAGON, 900, f'Dragão {i}') for i in range(4)]
    strong = add(FAIRY, 2200, 'Fada Forte')          # resultado da chave (faixa 2000-2500)
    medium = add(FAIRY, 1600, 'Fada Média')
    too_strong = add(DRAGON, 3500, 'Dragão Supremo')  # não deve ser premiada
    big = add(FAIRY, 2600, 'Fada Grande Demais')      # não pode entrar como material
    for f in fairies[:4]:
        for r in rocks[:3]:
            fusions[tuple(sorted((f, r)))] = strong
    for a in fairies:
        for b in fairies:
            if a < b:
                fusions[(a, b)] = medium
    for d in dragons:
        for f in fairies[4:8]:
            fusions[tuple(sorted((d, f)))] = too_strong
    for spell in range(338, 348):
        cards[spell] = {'nome': f'Magia {spell}', 'tipo_id': MAGIC, 'ataque': 0, 'defesa': 0}
    megamorph = 657
    cards[megamorph] = {'nome': 'Megamorph', 'tipo_id': EQUIP, 'ataque': 0, 'defesa': 0}
    equips[megamorph] = list(range(1, cid))
    bugs = [add(9, 700, f'Inseto {i}') for i in range(10)]          # sem nenhuma fusão
    sword = 301
    cards[sword] = {'nome': 'Espada', 'tipo_id': EQUIP, 'ataque': 0, 'defesa': 0}
    equips[sword] = fairies[:]
    return cards, fusions, equips, fairies, rocks, strong, too_strong, big


class ThemedDeckTests(unittest.TestCase):
    def test_fairy_deck_has_key_fusion_and_respects_cap(self):
        cards, fusions, equips, fairies, rocks, strong, too_strong, big = catalog()
        for seed in range(5):
            deck = design(cards, {}, fusions, equips, FAIRY, level='Equilibrado', rng=Random(seed))
            self.assertEqual(len(deck.cards), 40)
            self.assertEqual(deck.key_fusion[0], strong)
            self.assertTrue(deck.key_fusion[1])                    # pares presentes no deck
            held = Counter(deck.cards)
            self.assertTrue(all(count <= 3 for count in held.values()))
            cap = LEVELS['Equilibrado'][0]
            monsters = [c for c in deck.cards if cards[c]['tipo_id'] not in (MAGIC, EQUIP)]
            self.assertTrue(all(cards[c]['ataque'] <= cap for c in monsters))
            self.assertNotIn(big, held)
            self.assertGreaterEqual(deck.theme_share, 0.6)
            self.assertIn(301, held)                               # equipamento que serve
            self.assertNotIn(657, held)                            # Megamorph: fim de jogo
            self.assertIn('Fusão-chave', deck.report(cards))

    def test_theme_without_fusions_still_builds(self):
        cards, fusions, equips, *_ = catalog()
        deck = design(cards, {}, fusions, equips, 9, rng=Random(1))  # Inseto: sem fusões
        self.assertEqual(len(deck.cards), 40)
        self.assertIsNone(deck.key_fusion[0])
        self.assertIn('nenhuma', deck.report(cards))
        self.assertGreaterEqual(deck.theme_share, 0.6)

    def test_impossible_theme_is_explained(self):
        cards, fusions, equips, *_ = catalog()
        with self.assertRaises(ModError):
            design(cards, {}, fusions, equips, 10)                 # Dinossauro: sem monstros
        with self.assertRaises(ModError):
            design(cards, {}, fusions, equips, 24)                 # Deus não é tema


if __name__ == '__main__':
    unittest.main()
