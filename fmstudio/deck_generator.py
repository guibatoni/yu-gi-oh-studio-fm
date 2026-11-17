"""Constrói decks completos a partir das cartas e das relações do projeto."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from random import SystemRandom

from .core import ModError, simulation_nonnegative_int
from .duel_match import CURE_SPELLS, DAMAGE_SPELLS, TRAP_LIMITS
from .mod_data import MONSTER_TYPES, card_effects, deck_copy_limit, validate_deck
from .tables import CARD_COUNT, DECK_SIZE, TYPE_NAMES

SUPPORT_TYPES = (20, 21, 23)
STARTER_MAX_POWER = 2450  # Maior ATK + DEF dos quatro pools originais de monstros.
DIFFICULTIES = {
    'Equilibrado': (2, 4, 620),
    'Difícil': (4, 7, 260),
    'Máximo': (6, 10, 95),
}
# Indexado pelo ID original. A etapa ajusta o teto e a agressividade do gerador.
DUELIST_THEMES = (
    (0, ()), (0, (7, 2)), (0, (8,)), (0, (3, 4)),
    (0, (12, 16)), (0, (0,)), (0, (17, 5)), (1, (0,)), (1, (7, 1, 0)),
    (1, (10,)), (1, (9,)), (1, (8, 6, 19)), (1, (14,)), (1, (1, 7)),
    (1, (18, 7, 1)), (1, (1, 8, 6)), (1, (16, 1)), (2, (0, 15)),
    (1, (3, 1)), (1, (3, 4, 5)), (1, (8, 19)), (1, (16, 12, 13)),
    (2, (13, 16, 12)), (1, (19, 9, 5)), (2, (19, 9, 8)), (1, (18, 6)),
    (2, (15, 6, 0)), (1, (18, 2, 11)), (2, (2, 7, 18)), (1, (5, 4, 19)),
    (2, (5, 3, 4)), (2, (18, 1, 7)), (2, (0, 15)), (2, (11, 0)),
    (2, (3, 7)), (2, (0, 1, 7)), (2, (0, 15, 1)), (2, (7, 2, 1)),
    (2, (24, 0, 7)), (2, (0, 1, 14, 15)),
)


def duelist_preset(opponent):
    stage, types = DUELIST_THEMES[opponent]
    return types, (1750, 2400, 3000)[stage], tuple(DIFFICULTIES)[stage]


@dataclass(frozen=True)
class GeneratedDeck:
    cards: tuple[int, ...]
    fusions: tuple[tuple[int, int, int], ...]


def _eligible(card, cid, max_atk, max_def, starter, ps1_only):
    if ps1_only and (not 1 <= cid <= CARD_COUNT or card.get('virtual')):
        return False
    if int(card['tipo_id']) not in MONSTER_TYPES:
        return True
    atk, defense = int(card['ataque']), int(card['defesa'])
    return ((max_atk is None or atk <= max_atk) and (max_def is None or defense <= max_def)
            and (not starter or atk + defense <= STARTER_MAX_POWER))


def suggest_quantities(cards, effects, fusions, equips, *, default_copies=3, theme=(),
                       max_atk=None, max_def=None, starter=False, ps1_only=False, rng=None):
    """Choose a feasible type mix from actual copy capacity and cross-type recipes."""
    types = {cid: int(card['tipo_id']) for cid, card in cards.items()
             if _eligible(card, cid, max_atk, max_def, starter, ps1_only)
             and deck_copy_limit(effects, cid, default_copies)}
    limits = {cid: deck_copy_limit(effects, cid, default_copies) for cid in types}
    capacity = Counter()
    for cid, typ in types.items():
        capacity[typ] += limits[cid]
    available = sorted(typ for typ in MONSTER_TYPES if capacity[typ])
    if not available:
        raise ModError('Nenhum monstro atende ao teto de poder e ao limite de cópias.')
    affinity = Counter()
    for (a, b), result in fusions.items():
        left, right = types.get(a), types.get(b)
        if (left not in MONSTER_TYPES or right not in MONSTER_TYPES or result not in cards
                or int(cards[result]['tipo_id']) not in MONSTER_TYPES
                or a == b and limits[a] < 2
                or ps1_only and (result > CARD_COUNT or cards[result].get('virtual'))):
            continue
        gain = int(cards[result]['ataque']) - max(int(cards[a]['ataque']), int(cards[b]['ataque']))
        affinity[min(left, right), max(left, right)] += 1 + max(0, min(3000, gain)) // 500

    def support(group):
        equip_capacity = sum(limits[cid] for cid in equips.keys() & types.keys()
                             if types[cid] == 23
                             and any(types.get(target) in group for target in equips[cid]))
        return Counter({20: min(capacity[20], 2 if starter else 4),
                        21: 0 if starter else min(capacity[21], 3),
                        23: min(equip_capacity, 1 if starter else 2)})

    if starter:
        ranked = []
        for group in combinations(available, 3):
            counts = support(group)
            if sum(capacity[typ] for typ in group) + counts.total() < DECK_SIZE:
                continue
            pairs = list(combinations(group, 2))
            score = sum(1000 * affinity[pair] // max(1, capacity[pair[0]] * capacity[pair[1]])
                        for pair in pairs)
            connected = sum(affinity[pair] > 0 for pair in pairs)
            ranked.append(((connected, score), group, counts))
        if not ranked:
            raise ModError('São necessários três tipos que preencham as vagas dentro do teto inicial.')
        ranked.sort(reverse=True, key=lambda item: item[0])
        finalists = [row for row in ranked if row[0][0] == ranked[0][0][0]][:8]
        _, group, counts = (rng.choice(finalists) if rng else finalists[0])
        priority = list(group)
    else:
        priority = [typ for typ in theme if typ in available]
        if not priority:
            priority = sorted(available, key=lambda typ: -capacity[typ])[:3]
        rest = sorted(set(available) - set(priority),
                      key=lambda typ: (-sum(affinity[tuple(sorted((typ, other)))] for other in priority),
                                       -capacity[typ], typ))
        counts = support(priority)
        group = (*priority, *rest)
    slots = DECK_SIZE - counts.total()
    for offset in range(slots):
        choices = [typ for typ in group if counts[typ] < capacity[typ]]
        if not choices:
            raise ModError('O catálogo não tem cópias disponíveis para preencher as 40 vagas.')
        themed = [typ for typ in choices if typ in priority]
        if themed and offset * 4 < slots * 3:
            choices = themed
        elif not starter:
            choices = choices[:len(priority) + 3]
        chosen = min(choices, key=lambda typ: (counts[typ], group.index(typ)))
        counts[chosen] += 1
    return counts


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
                  trap_thresholds=None, rng=None, ps1_only=False, starter=False) -> GeneratedDeck:
    """Monte 40 cartas. O teto se aplica aos materiais, inclusive no deck inicial."""
    if ps1_only:
        cards = {cid: card for cid, card in cards.items()
                 if 1 <= cid <= CARD_COUNT and not card.get('virtual')}
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
    if starter and sum(counts.get(typ, 0) > 0 for typ in MONSTER_TYPES) != 3:
        raise ModError('Distribua as vagas de monstros entre três tipos para o deck inicial.')
    atk_limit = None if max_atk is None else simulation_nonnegative_int(max_atk, 'Teto de ATK')
    def_limit = None if max_def is None else simulation_nonnegative_int(max_def, 'Teto de DEF')
    rng = rng or SystemRandom()
    direct_weight, fusion_weight, noise = DIFFICULTIES[difficulty]
    fusion_first = starter or atk_limit is not None and atk_limit < 2000
    synergy = fusion_first or atk_limit is not None and atk_limit <= 3000
    if fusion_first:
        direct_weight = max(1, direct_weight // 2)
        fusion_weight *= 3
    types = {cid: int(card['tipo_id']) for cid, card in cards.items()}
    powers = {}
    groups = defaultdict(list)
    limits = {}
    for cid in sorted(cards):
        typ = types[cid]
        if typ in MONSTER_TYPES:
            atk, defense = int(cards[cid]['ataque']), int(cards[cid]['defesa'])
            powers[cid] = (max(atk, defense), atk + defense, atk)
        if counts.get(typ, 0) and _eligible(cards[cid], cid, atk_limit, def_limit, starter, ps1_only):
            limit = deck_copy_limit(effects, cid, default_copies)
            if not limit:
                continue
            groups[typ].append(cid)
            limits[cid] = limit
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
        if ps1_only and result not in cards:
            continue
        if a not in eligible_monsters or b not in eligible_monsters or result not in powers:
            continue
        if a == b and limits[a] < 2:
            continue
        if types[a] == types[b] and counts[types[a]] < 2:
            continue
        gain = power_score[result] - max(power_score[a], power_score[b])
        weight = max(1, power_score[result] + (4 if fusion_first else 2) * gain)
        recipes.append((weight, a, b, result))
        links[a][b] = links[b][a] = weight, result
    recipes.sort(reverse=True)
    potential = {cid: sum(sorted((weight for weight, _ in links[cid].values()), reverse=True)[:6])
                 for cid in monsters}

    targets_by_equip = {}
    for cid in groups[23]:
        targets_by_equip[cid] = set(equips.get(cid, ())) & eligible_monsters
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
        ready = Counter()
        attributes = Counter()
        compatible = set()

        def take(cid):
            deck.append(cid)
            held[cid] += 1
            open_slots[types[cid]] -= 1

        def place_monster(cid):
            take(cid)
            attributes[cards[cid].get('atributo_id', -1)] += 1
            compatible.update(equipped_by[cid])
            if held[cid] == 1:
                for other, (weight, _) in links[cid].items():
                    ready[other] += weight

        if anchor is not None:
            _, left, right, _ = anchor
            place_monster(left)
            place_monster(right)

        def monster_score(cid):
            need = max(0, equips_needed - sum(limits[equip] for equip in compatible))
            coverage = sum(limits[equip] for equip in equipped_by[cid] - compatible) if need else 0
            attr = cards[cid].get('atributo_id', -1)
            affinity = 90 * min(8, attributes[attr]) if synergy and attr != -1 else 0
            return (power_score[cid] * direct_weight + ready[cid] * fusion_weight // (1 + held[cid])
                    + potential[cid] // 3 + 200000 * min(need, coverage) + affinity
                    - 550 * held[cid] + rng.randrange(noise))

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
                 + fusion_weight * sum(row[0] for row in achieved[:32 if synergy else 12])
                 + (700 * len(achieved) if synergy else 0)
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
