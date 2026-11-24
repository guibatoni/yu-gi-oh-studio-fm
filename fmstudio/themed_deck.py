"""Deck inicial temático: um tipo principal, sinergia de fusões e uma fusão-chave.

Gera 40 cartas com as tabelas reais do projeto (cartas, fusões, equipamentos e
limites de cópias), sem internet:

1. **Fusão-chave**: entre as fusões cujos dois materiais cabem no teto de
   força do deck, escolhe o resultado com ATK na faixa "forte para avançar"
   (ligado ao tema: resultado e/ou materiais do tipo escolhido). Prefere o
   resultado que tem vários pares de materiais, para sair com frequência.
2. **Núcleo**: os materiais da fusão-chave entram com o máximo de cópias.
3. **Corpo**: monstros fracos, a maioria do tipo escolhido, escolhidos pela
   quantidade de fusões úteis que fazem com o que já está no deck. Fusões
   mais fortes que a faixa da chave não contam pontos (o deck não fica forte
   demais por acidente).
4. **Apoio**: equipamentos que servem nos monstros do deck e magias leves de
   dano/cura.

``design`` devolve o deck e um relatório legível (fusões, médias, tema).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from random import Random, SystemRandom

from .core import ModError
from .duel_match import CURE_SPELLS, DAMAGE_SPELLS
from .mod_data import MONSTER_TYPES, deck_copy_limit, validate_deck
from .tables import CARD_COUNT, DECK_SIZE, TYPE_NAMES

EQUIP = 23
# nível -> (teto de ATK dos monstros do deck, faixa de ATK da fusão-chave)
LEVELS = {
    'Fraco': (1200, (1800, 2300)),
    'Equilibrado': (1400, (2000, 2500)),
    'Moderado': (1600, (2200, 2800)),
}
LIGHT_SPELLS = tuple(sorted(set(range(343, 346)) | set(range(338, 341))))  # dano 50-200, cura 200-1000


@dataclass
class ThemedDeck:
    cards: tuple[int, ...]
    theme: int
    level: str
    key_fusion: tuple[int, tuple[tuple[int, int], ...]]      # resultado, pares no deck
    fusions: list[tuple[int, int, int]] = field(default_factory=list)  # (a, b, resultado)
    theme_share: float = 0.0
    average_atk: int = 0
    max_atk: int = 0

    def report(self, cards) -> str:
        name = lambda cid: f"#{cid:03d} {cards[cid].get('nome', '?')}"
        atk = lambda cid: int(cards[cid]['ataque'])
        result, pairs = self.key_fusion
        lines = [f'Tema: {TYPE_NAMES[self.theme]} · nível {self.level}',
                 f'Monstros do tema: {self.theme_share:.0%} · ATK médio {self.average_atk} · '
                 f'maior ATK no deck {self.max_atk}',
                 '', f'Fusão-chave: {name(result)} (ATK {atk(result)})']
        for a, b in pairs:
            lines.append(f'  {name(a)} + {name(b)}')
        others = [row for row in self.fusions if row[2] != result]
        if others:
            lines += ['', 'Outras fusões do deck (mais fortes primeiro):']
            for a, b, r in sorted(others, key=lambda row: -atk(row[2]))[:12]:
                lines.append(f'  {name(a)} + {name(b)} → {name(r)} (ATK {atk(r)})')
        return '\n'.join(lines)


def _atk(cards, cid):
    return int(cards[cid]['ataque'])


def design(cards, effects, fusions, equips, theme: int, *, level='Equilibrado',
           default_copies=3, rng=None) -> ThemedDeck:
    if theme not in MONSTER_TYPES or theme == 24:
        raise ModError('Escolha um tipo de monstro para o tema.')
    if level not in LEVELS:
        raise ModError('Escolha o nível do deck.')
    rng = rng or SystemRandom()
    cap, (band_low, band_high) = LEVELS[level]
    band_mid = (band_low + band_high) // 2
    cards = {cid: card for cid, card in cards.items() if 1 <= cid <= CARD_COUNT and not card.get('virtual')}
    types = {cid: int(card['tipo_id']) for cid, card in cards.items()}
    limits = {cid: deck_copy_limit(effects, cid, default_copies) for cid in cards}
    material = {cid for cid, typ in types.items()
                if typ in MONSTER_TYPES and typ != 24 and limits[cid]
                and _atk(cards, cid) <= cap and int(cards[cid]['defesa']) <= cap + 400}
    if sum(1 for cid in material if types[cid] == theme) < 6:
        raise ModError(f'Poucos monstros {TYPE_NAMES[theme]} fracos o bastante para um deck inicial.')

    links = defaultdict(dict)       # material -> {parceiro: resultado}
    by_result = defaultdict(list)
    for (a, b), result in fusions.items():
        if a in material and b in material and result in cards and types[result] in MONSTER_TYPES:
            if a == b and limits[a] < 2:
                continue
            links[a][b] = links[b][a] = result
            by_result[result].append((a, b))

    # 1. fusão-chave
    def relevance(result, pairs):
        return 3 * (types[result] == theme) + max(
            (types[a] == theme) + (types[b] == theme) for a, b in pairs)

    candidates = []
    for result, pairs in by_result.items():
        value = _atk(cards, result)
        if not band_low <= value <= band_high:
            continue
        rel = relevance(result, pairs)
        if rel < 1:
            continue
        variety = len({cid for pair in pairs for cid in pair})
        score = rel * 1000 + min(variety, 8) * 120 - abs(value - band_mid) // 2 + rng.randrange(250)
        candidates.append((score, result))
    if not candidates:
        raise ModError(f'Nenhuma fusão com materiais fracos chega a ATK {band_low}-{band_high} '
                       f'com o tema {TYPE_NAMES[theme]}. Tente outro nível ou tipo.')
    candidates.sort(reverse=True)
    key = rng.choice(candidates[:3])[1]
    # pares da chave priorizando materiais do tema e reaproveitáveis
    key_pairs = sorted(by_result[key], key=lambda pair: (
        -((types[pair[0]] == theme) + (types[pair[1]] == theme)),
        -(len(links[pair[0]]) + len(links[pair[1]])), rng.random()))[:3]

    held = Counter()
    deck = []

    def take(cid, copies=1):
        for _ in range(copies):
            if held[cid] < limits[cid] and len(deck) < DECK_SIZE:
                deck.append(cid)
                held[cid] += 1

    support_slots = 8
    monster_slots = DECK_SIZE - support_slots
    # 2. núcleo da fusão-chave
    for a, b in key_pairs:
        for cid in (a, b):
            take(cid, max(0, min(limits[cid], 3) - held[cid]))
            if len(deck) >= 12:
                break

    # 3. corpo: sinergia com o que já está no deck
    def synergy(cid):
        total = 0
        for other, result in links[cid].items():
            if not held[other] or (other == cid and held[cid] < 1):
                continue
            gain = min(_atk(cards, result), band_high) - max(_atk(cards, cid), _atk(cards, other))
            if _atk(cards, result) > band_high:
                gain = 0                          # forte demais: não premia
            total += max(0, gain)
        return total

    while len(deck) < monster_slots:
        theme_count = sum(1 for cid in deck if types[cid] == theme)
        need_theme = theme_count < monster_slots * 0.6
        pool = [cid for cid in material if held[cid] < limits[cid]]
        themed = [cid for cid in pool if types[cid] == theme]
        if need_theme and themed:
            pool = themed
        if not pool:
            break

        def score(cid):
            return (3 * synergy(cid) + (700 if types[cid] == theme else 0)
                    + _atk(cards, cid) // 4 + 40 * min(len(links[cid]), 15)
                    - 450 * held[cid] + rng.randrange(300))
        take(max(pool, key=score))

    # 4. apoio: equipamentos que servem nos monstros do deck + magias leves
    monsters = set(deck)
    equip_pool = [cid for cid, typ in types.items() if typ == EQUIP and limits[cid]
                  and len(set(equips.get(cid, ())) & monsters) >= 3]
    equip_pool.sort(key=lambda cid: (-len(set(equips.get(cid, ())) & monsters), rng.random()))
    for cid in equip_pool[:3]:
        if len(deck) < DECK_SIZE - 2:
            take(cid)
    for cid in LIGHT_SPELLS:
        if cid in cards and len(deck) < DECK_SIZE:
            take(cid)
    while len(deck) < DECK_SIZE:                  # completa com monstros do tema
        pool = [cid for cid in material if held[cid] < limits[cid]]
        if not pool:
            raise ModError('Não há cartas suficientes para completar 40.')
        take(max(pool, key=lambda cid: (types[cid] == theme, synergy(cid), -held[cid], rng.random())))

    validate_deck(cards, effects, deck, default_copies)
    in_deck = [cid for cid in deck if types[cid] in MONSTER_TYPES]
    reachable = sorted({(min(a, b), max(a, b), r) for a in set(in_deck) for b, r in links[a].items()
                        if held[b] >= (2 if a == b else 1)})
    present_pairs = tuple((a, b) for a, b in by_result[key] if held[a] and held[b] >= (2 if a == b else 1))
    rng.shuffle(deck)
    return ThemedDeck(
        cards=tuple(deck), theme=theme, level=level, key_fusion=(key, present_pairs[:6]),
        fusions=reachable,
        theme_share=sum(types[c] == theme for c in in_deck) / max(1, len(in_deck)),
        average_atk=sum(_atk(cards, c) for c in in_deck) // max(1, len(in_deck)),
        max_atk=max((_atk(cards, c) for c in in_deck), default=0))
