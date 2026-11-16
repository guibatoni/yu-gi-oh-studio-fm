"""Constrói decks completos a partir das cartas e das relações do projeto."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from random import SystemRandom

from .core import ModError, simulation_nonnegative_int
from .duel_match import CURE_SPELLS, DAMAGE_SPELLS, TRAP_LIMITS
from .mod_data import MONSTER_TYPES, card_effects, deck_copy_limit, validate_deck
from .tables import CARD_COUNT, DECK_SIZE, TYPE_NAMES

SUPPORT_TYPES = (20, 21, 23)
DIFFICULTIES = {
    'Equilibrado': (2, 4, 620),
    'Difícil': (4, 7, 260),
    'Máximo': (6, 10, 95),
}


@dataclass(frozen=True)
class GeneratedDeck:
    cards: tuple[int, ...]
    fusions: tuple[tuple[int, int, int], ...]


def _support_score(cid, kind, effects, trap_limits):
    if kind == 21:
        limit = trap_limits.get(cid, 0)
        score = 2100 if limit is None else min(1500, limit // 2)
        if cid in (687, 688, 689, 690):
            score += 600
        events = ('atacar', 'defender')
    elif kind == 20:
        score = 1700 if cid in (337, 348) else 950 if cid in (336, 349, 350) else 0
        score += DAMAGE_SPELLS.get(cid, 0) + CURE_SPELLS.get(cid, 0) // 4
        events = ('invocar',)
    else:
        score = 500 if cid <= CARD_COUNT else 0
        events = ('equipado',)
    for effect in card_effects(effects, cid):
        if effect.get('evento') in events:
            value = int(effect.get('valor', 0))
            score += 300 + min(value, 2000)
    return score


def generate_deck(cards, effects, fusions, equips, quantities, *,
                  max_atk=None, max_def=None, difficulty='Difícil', default_copies=3,
                  trap_thresholds=None, rng=None) -> GeneratedDeck:
    """Use quotas exatas e preserve o limite de cópias registrado para cada carta."""
    if difficulty not in DIFFICULTIES:
        raise ModError('Escolha a dificuldade do deck.')
    allowed = MONSTER_TYPES.union(SUPPORT_TYPES)
    if any(type(typ) is not int or typ not in allowed for typ in quantities):
        raise ModError('Há um tipo de carta indisponível no gerador.')
    counts = {typ: simulation_nonnegative_int(value, f'Quantidade de {TYPE_NAMES[typ]}')
              for typ, value in quantities.items()}
    if sum(counts.values()) != DECK_SIZE:
        raise ModError(f'Distribua exatamente {DECK_SIZE} cartas entre as categorias.')
    if not any(counts.get(typ, 0) for typ in MONSTER_TYPES):
        raise ModError('Reserve pelo menos uma vaga de monstro.')
    atk_limit = None if max_atk is None else simulation_nonnegative_int(max_atk, 'Teto de ATK')
    def_limit = None if max_def is None else simulation_nonnegative_int(max_def, 'Teto de DEF')
    rng = rng or SystemRandom()
    direct_weight, fusion_weight, noise = DIFFICULTIES[difficulty]
    types = {cid: int(card['tipo_id']) for cid, card in cards.items()}
    powers = {}
    groups = defaultdict(list)
    limits = {}
    for cid in sorted(cards):
        typ = types[cid]
        if typ in MONSTER_TYPES:
            atk, defense = int(cards[cid]['ataque']), int(cards[cid]['defesa'])
            powers[cid] = (max(atk, defense), atk + defense, atk)
            if (atk_limit is not None and atk > atk_limit) or (def_limit is not None and defense > def_limit):
                continue
        if counts.get(typ, 0):
            groups[typ].append(cid)
            limits[cid] = deck_copy_limit(effects, cid, default_copies)
    for typ, count in counts.items():
        capacity = sum(limits[cid] for cid in groups[typ])
        if count > capacity:
            raise ModError(f'{TYPE_NAMES[typ]} tem {capacity} vaga(s) disponíveis para {count} solicitadas.')

    # A ordenação usa inteiros. Os atributos do Studio podem ter muitos dígitos.
    distinct_powers = sorted(set(powers.values()))
    ranks = {power: 1000 * index // len(distinct_powers)
             for index, power in enumerate(distinct_powers, start=1)}
    power_score = {cid: ranks[power] for cid, power in powers.items()}
    monsters = [cid for typ in sorted(MONSTER_TYPES) for cid in groups[typ]]
    eligible_monsters = set(monsters)
    links = defaultdict(dict)
    recipes = []
    for (a, b), result in fusions.items():
        if a not in eligible_monsters or b not in eligible_monsters or result not in powers:
            continue
        if a == b and limits[a] < 2:
            continue
        if types[a] == types[b] and counts[types[a]] < 2:
            continue
        gain = power_score[result] - max(power_score[a], power_score[b])
        weight = max(1, power_score[result] + 2 * gain)
        recipes.append((weight, a, b, result))
        links[a][b] = links[b][a] = weight, result
    recipes.sort(reverse=True)
    potential = {cid: max((weight for weight, _ in links[cid].values()), default=0)
                 for cid in monsters}

    targets_by_equip = {}
    for cid in groups[23]:
        targets = equips.get(cid)
        if targets is None and any(e.get('evento') == 'equipado' for e in card_effects(effects, cid)):
            targets = powers.keys()
        targets_by_equip[cid] = set(targets or ()) & powers.keys()
    equipped_by = defaultdict(set)
    for cid, targets in targets_by_equip.items():
        for target in targets:
            equipped_by[target].add(cid)
    equips_needed = counts.get(23, 0)
    trap_limits = {**TRAP_LIMITS, **(trap_thresholds or {})}
    support = {cid: _support_score(cid, typ, effects, trap_limits)
               for typ in SUPPORT_TYPES for cid in groups[typ]}

    def build(anchor):
        deck = []
        held = Counter()
        open_slots = dict(counts)
        ready = {}
        compatible = set()

        def take(cid):
            deck.append(cid)
            held[cid] += 1
            open_slots[types[cid]] -= 1

        def place_monster(cid):
            take(cid)
            compatible.update(equipped_by[cid])
            for other, (weight, result) in links[cid].items():
                ready[other] = max(weight, ready.get(other, 0))
                if held[other] >= (2 if cid == other else 1):
                    compatible.update(equipped_by[result])

        if anchor is not None:
            _, left, right, _ = anchor
            place_monster(left)
            place_monster(right)

        def monster_score(cid):
            need = max(0, equips_needed - sum(limits[equip] for equip in compatible))
            coverage = sum(limits[equip] for equip in equipped_by[cid] - compatible) if need else 0
            return (power_score[cid] * direct_weight + ready.get(cid, 0) * fusion_weight
                    + potential[cid] // 2 + 16000 * min(need, coverage)
                    - 220 * held[cid] + rng.randrange(noise))

        while any(open_slots.get(typ, 0) for typ in MONSTER_TYPES):
            available = [cid for cid in monsters if open_slots[types[cid]] and held[cid] < limits[cid]]
            place_monster(max(available, key=monster_score))

        achieved = [(weight, a, b, result) for weight, a, b, result in recipes
                    if held[a] and held[b] >= (2 if a == b else 1)]
        if sum(limits[cid] for cid in compatible) < equips_needed:
            return None
        for typ in SUPPORT_TYPES:
            candidates = groups[typ] if typ != 23 else sorted(compatible)
            for _ in range(open_slots.get(typ, 0)):
                def score(cid):
                    coverage = sum(held[target] for target in targets_by_equip[cid]) if typ == 23 else 0
                    return support[cid] + 130 * coverage - 380 * held[cid] + rng.randrange(noise)

                take(max((cid for cid in candidates if held[cid] < limits[cid]), key=score))
        value = (direct_weight * sum(power_score[cid] for cid in deck if cid in powers)
                 + fusion_weight * sum(row[0] for row in achieved[:12])
                 + sum(support.get(cid, 0) for cid in deck))
        return (bool(achieved), value, deck, tuple((a, b, result) for _, a, b, result in achieved))

    # Varie as cartas de partida, mantendo o melhor conjunto que cabe nas quotas.
    seeds = [None] if not recipes else [recipes[0], None, *rng.sample(recipes[:32], min(8, len(recipes)))]
    best = max((candidate for seed in seeds if (candidate := build(seed)) is not None),
               key=lambda candidate: candidate[:2], default=None)
    if best is None:
        raise ModError('A seleção precisa de mais monstros compatíveis para preencher os equipamentos.')
    _, _, deck, combinations = best
    validate_deck(cards, effects, deck, default_copies)
    rng.shuffle(deck)
    return GeneratedDeck(tuple(deck), combinations)
