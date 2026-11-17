"""Gerador de campanha 3.0–5.0; usa cartas, efeitos e relações reais do projeto.

Não altera a IA, nem inventa efeitos/fusões. O modo PS1 exclui cartas virtuais
ou IDs > 722: só os decks do simulador podem usar novos IDs.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from random import SystemRandom

from .core import ModError
from .deck_generator import DUELIST_THEMES, _support_score
from .mod_data import MONSTER_TYPES, card_effects, deck_copy_limit, validate_deck
from .tables import CARD_COUNT, DECK_SIZE, DUELIST_NAMES_REFERENCE, POOL_TOTAL

# Rótulos de intenção; as ações são escolhidas a partir dos efeitos reais da ISO.
FOCI = (
    '', 'Burn/Fusão', 'Aura/Suporte', 'Combate/Fusão', 'Campo/Plantas',
    'Controle/Pedra', 'Aura/Dragões', 'Poder/Dragões', 'Cemitério/Fiends',
    'Combate/Dinossauros', 'Controle/Insetos', 'Aura/Harpias', 'Máquinas/Controle',
    'Magia/Controle', 'Cemitério/Burn', 'Magia/Ilusão', 'Suporte/Água',
    'Aura/Dragões', 'Combate/Guerreiros', 'Combate/Equips', 'Cura/Aura',
    'Controle/Água', 'Pressão/Aquática', 'Campo/Plantas', 'Aura/Feras',
    'Aura/Dragões', 'Burn/Trovão', 'Controle/Pedra', 'Burn/Demônios',
    'Combate/Feras', 'Fusão/Guerreiros', 'Controle/Labirinto', 'Fusão/Dragões',
    'Controle/Répteis', 'Combate/Demônios', 'Cemitério/Burn',
    'Fusão/Dragões', 'Controle/Burn', 'Fusão/Boss', 'Fusão/Elite',
)
EFFECT_ACTIONS = frozenset((
    'dano_lp', 'cura_lp', 'aura_tipo', 'bonus_por_tipo', 'bonus_deck_tipo',
    'bonus_mao_tipo', 'bonus_cemiterio_tipo', 'bonus_por_carta_id',
    'dano_lp_deck_tipo', 'cura_lp_deck_tipo', 'descartar_alvo',
    'dano_monstro_alvo', 'vinculo_vida', 'ataques_multiplos',
    'monstro_indestrutivel', 'monstro_imune_magia', 'monstro_imune_armadilha',
    'dano_perfurante', 'nao_bloqueavel', 'ataque_primeiro_turno',
    'acumular_atk_def_entrada', 'reduzir_atk_def_entrada',
    'aumentar_atk', 'aumentar_def', 'reduzir_atk', 'reduzir_def',
))
NEGATIVE_ACTIONS = {'perder_lp_por_ataque'}
BURN = {'dano_lp', 'dano_lp_deck_tipo', 'dano_monstro_alvo'}
AURAS = {'aura_tipo', 'bonus_por_tipo', 'bonus_deck_tipo', 'bonus_mao_tipo',
         'bonus_cemiterio_tipo', 'bonus_por_carta_id', 'acumular_atk_def_entrada'}
CONTROL = {'descartar_alvo', 'dano_monstro_alvo', 'reduzir_atk_def_entrada',
           'monstro_imune_magia', 'monstro_imune_armadilha'}
FIELD_SPELLS = {330, 331, 332, 333, 334, 335}


@dataclass(frozen=True)
class CampaignDeck:
    opponent: int
    difficulty: float
    focus: str
    cards: tuple[int, ...]
    weights: dict[int, int]
    fusions: tuple[tuple[int, int, int], ...]
    effect_monsters: int
    max_fusion_atk: int
    notes: tuple[str, ...]

    @property
    def profile(self):
        return {'cartas': [], 'pools': [{'compras': DECK_SIZE,
                                          'pesos': dict(self.weights)}]}


def campaign_level(opponent: int) -> float:
    if not 1 <= opponent <= 39:
        raise ModError('A campanha possui 39 duelistas, de #1 a #39.')
    if opponent <= 10:
        return round(3.0 + (opponent - 1) * .5 / 9, 1)
    if opponent <= 25:
        return round(3.5 + (opponent - 11) * .8 / 14, 1)
    return round(4.3 + (opponent - 26) * .7 / 13, 1)


def campaign_label(opponent: int) -> str:
    return f'{campaign_level(opponent):.1f}/5 · {FOCI[opponent]}'


def _effect_value(effects, cid, focus: str) -> int:
    value = 0
    for entry in card_effects(effects, cid):
        action = entry.get('acao')
        event = entry.get('evento')
        target = entry.get('alvo')
        if action in NEGATIVE_ACTIONS or (action == 'dano_lp' and target == 'proprio'):
            value -= 1600
            continue
        if action not in EFFECT_ACTIONS and not action.startswith(('entrada_',)):
            continue
        amount = max(0, min(3000, int(entry.get('valor', 0) or 0)))
        score = 420 + amount // 8
        if event in ('invocar', 'continuo', 'inicio_turno', 'atacar', 'entrada_tipo'):
            score += 210
        if 'Burn' in focus and action in BURN:
            score += 450
        if 'Aura' in focus and action in AURAS:
            score += 450
        if 'Cemitério' in focus and action == 'bonus_cemiterio_tipo':
            score += 550
        if 'Controle' in focus and action in CONTROL:
            score += 450
        if action == 'dano_lp' and target == 'inimigo':
            score += 350
        value += score
    return value


def _power(card) -> int:
    return int(card.get('ataque', 0) or 0)


def _weights(counts, priority):
    """Arredondamento de maior resto, total exato 2048 e todo ID positivo."""
    raw = {cid: max(1, 100 * amount + priority.get(cid, 0))
           for cid, amount in counts.items() if amount > 0}
    if not raw or len(raw) > POOL_TOTAL:
        raise ModError('Nenhuma carta válida para a pool ponderada.')
    total = sum(raw.values())
    remaining = POOL_TOTAL - len(raw)
    distributed = {cid: 1 + remaining * w // total for cid, w in raw.items()}
    left = POOL_TOTAL - sum(distributed.values())
    order = sorted(raw, key=lambda cid: (-(remaining * raw[cid] % total), cid))
    for cid in order[:left]:
        distributed[cid] += 1
    assert sum(distributed.values()) == POOL_TOTAL
    return dict(sorted(distributed.items()))


def generate_campaign_deck(cards, effects, fusions, equips, opponent, *,
                           default_copies=3, ps1_only=True, max_base_atk=1500,
                           max_base_def=1500, trap_thresholds=None, rng=None):
    """Constrói 40 cartas temáticas, rotas reais de 1–3 fusões e pool ponderada.

    Falha explicitamente quando catálogo ou cópias não permitem uma campanha
    coerente, sem substituir resultados por IDs inventados ou efeitos fictícios.
    """
    level = campaign_level(opponent)
    theme = tuple(t for t in DUELIST_THEMES[opponent][1] if t in MONSTER_TYPES)
    focus = FOCI[opponent]
    rng = rng or SystemRandom()
    allowed = {cid: card for cid, card in cards.items()
               if (not ps1_only or 1 <= cid <= CARD_COUNT and not card.get('virtual'))}
    kinds = {cid: int(card.get('tipo_id', -1)) for cid, card in allowed.items()}
    limits = {cid: deck_copy_limit(effects, cid, default_copies)
              for cid in allowed}
    monsters = {cid for cid, card in allowed.items()
                if kinds[cid] in MONSTER_TYPES and limits[cid] > 0
                and int(card.get('ataque', 0)) <= max_base_atk
                and int(card.get('defesa', 0)) <= max_base_def}
    if len(monsters) < 2:
        raise ModError('Não há materiais suficientes respeitando o teto de ATK/DEF.')
    effect_score = {cid: _effect_value(effects, cid, focus) for cid in monsters}
    useful_edges = defaultdict(set)
    by_material = defaultdict(list)
    pairs = []
    for pair, result in fusions.items():
        if len(pair) != 2 or result not in allowed or kinds[result] not in MONSTER_TYPES:
            continue
        a, b = sorted(map(int, pair))
        if a == b or a not in allowed or b not in allowed:
            continue
        by_material[a].append((b, result))
        by_material[b].append((a, result))
        if a in monsters and b in monsters:
            useful_edges[a].add(b)
            useful_edges[b].add(a)
            theme_count = sum(kinds[x] in theme for x in (a, b))
            power = _power(allowed[result])
            gain = power - max(_power(allowed[a]), _power(allowed[b]))
            rating = (power * 2 + max(-500, gain) + 900 * theme_count
                      + min(900, effect_score[a]) + min(900, effect_score[b]))
            pairs.append((rating, (a, b), ((a, b, result),), result))
    if not pairs:
        raise ModError('Não há fusões reais entre materiais válidos neste projeto.')

    pairs.sort(key=lambda row: (-row[0], row[1]))
    # Priorização de tema: nunca abandona o arquétipo por uma rota genérica.
    themed = [p for p in pairs if any(kinds[x] in theme for x in p[1])]
    seeds = themed[:75] if themed else pairs[:75]
    routes = list(seeds)
    for seed in seeds:
        frontier = [seed]
        for _ in range(2):  # até três fusões em sequência
            extended = []
            for rating, materials, steps, result in frontier:
                choices = []
                for extra, upgraded in by_material[result]:
                    if extra not in monsters or extra in materials:
                        continue
                    if len(materials) >= 4:
                        continue
                    strength = _power(allowed[upgraded])
                    if strength < _power(allowed[result]):
                        continue
                    themed_bonus = 450 if kinds[extra] in theme else 0
                    choices.append((strength * 2 + themed_bonus
                                    + min(900, effect_score[extra]), extra, upgraded))
                for _, extra, upgraded in sorted(choices, reverse=True)[:4]:
                    row = (rating + _power(allowed[upgraded]) +
                           int(500 * (level - 3)), materials + (extra,),
                           steps + ((result, extra, upgraded),), upgraded)
                    extended.append(row)
            if not extended:
                break
            routes.extend(extended)
            frontier = sorted(extended, key=lambda x: (-x[0], x[1]))[:12]
    # Na metade final, valorizar mais 2–3 fusões e 3000+ ATK efetivos.
    def route_value(route):
        _, materials, steps, final = route
        atk = _power(allowed[final])
        effect_materials = sum(effect_score[cid] > 0 for cid in materials)
        themed_materials = sum(kinds[cid] in theme for cid in materials)
        target = 2000 + int((level - 3) * 500)
        return (min(atk, 5000) * 2 + 650 * themed_materials
                + 460 * effect_materials + 430 * max(0, len(steps)-1) * (level-2)
                + (1000 if atk >= target else -1200)
                + (1700 if level >= 4.3 and atk >= 3000 else 0))
    routes.sort(key=lambda r: (-route_value(r), r[1]))
    chosen = []
    for route in routes:
        if not chosen or (len(chosen) < 3 and
                          (set(route[1]) & set(chosen[0][1])
                           or len(chosen) == 1 and set(route[1]) &
                           {c for r in chosen for c in r[1]})):
            if route not in chosen:
                chosen.append(route)
        if len(chosen) == 3:
            break
    if not chosen:
        raise ModError('Nenhuma rota de fusão foi encontrada.')

    counts = Counter()
    preferences = Counter()
    monster_target = 30 if level < 4.3 else 29
    def take(cid, count=1):
        available = min(count, limits[cid]-counts[cid], DECK_SIZE-sum(counts.values()))
        if available > 0:
            counts[cid] += available
        return available

    for idx, (_, materials, steps, result) in enumerate(chosen):
        for cid in materials:
            preferences[cid] += 240 if idx == 0 else 120
            if sum(counts[c] for c in counts if c in monsters) < monster_target:
                take(cid, min(limits[cid], 3 if idx == 0 else 2))
    # Monstros com efeito primeiro; sem efeito só por serem materiais de fusão.
    route_ids = {cid for route in routes[:60] for cid in route[1]}
    def score(cid):
        themed = 1350 if kinds[cid] in theme else 0
        effects_bonus = max(-1500, min(4300, effect_score[cid])) * (1.25 + .2 * (level-3))
        combo = 800 if cid in route_ids else (430 if useful_edges[cid] else -900)
        power = _power(allowed[cid]) // 3
        attr = allowed[cid].get('atributo_id')
        ally = sum(amount for other, amount in counts.items()
                   if other in monsters and allowed[other].get('atributo_id') == attr)
        return themed + effects_bonus + combo + power + ally * 55 - counts[cid]*450

    def monster_slots():
        return sum(amount for cid, amount in counts.items() if cid in monsters)
    while monster_slots() < monster_target:
        candidates = [cid for cid in monsters if counts[cid] < limits[cid] and
                      (effect_score[cid] > 0 or useful_edges[cid] or cid in route_ids)]
        if not candidates:
            break
        best = sorted(candidates, key=lambda cid: (-score(cid), cid))
        # Sorteio controlado entre alternativas próximas permite regenerar o mesmo oponente.
        top = best[:min(3, len(best))]
        take(rng.choice(top))
    if monster_slots() < 22:
        raise ModError('Catálogo insuficiente para criar um deck competitivo de fusões/efeitos.')

    realized = [step for _, materials, steps, _ in routes
                if all(counts[cid] for cid in materials) for step in steps]
    available_reachable = set(counts) | {result for _, _, result in realized}
    support_pool = [cid for cid in allowed if kinds[cid] in (20,21,23)
                    and limits[cid] > 0]
    candidate_support = []
    for cid in support_pool:
        typ = kinds[cid]
        if typ == 23 and not (set(equips.get(cid, ())) & available_reachable):
            continue
        score_support = _support_score(cid, typ, effects, trap_thresholds or {})
        if typ == 23:
            score_support += 420 + 90 * len(set(equips.get(cid, ())) & available_reachable)
        elif cid in FIELD_SPELLS:
            score_support += 120 + int(level * 80)
        elif typ == 21:
            score_support += 150 * (level-3)
        candidate_support.append((score_support, cid))
    candidate_support.sort(key=lambda x: (-x[0], x[1]))
    support_target = DECK_SIZE - monster_slots()
    for _, cid in candidate_support:
        if support_target <= 0:
            break
        quota = 3 if kinds[cid] == 20 else 2
        amount = take(cid, min(quota, support_target))
        support_target -= amount
        preferences[cid] += 60
    # Completar com efeitos/materiais legítimos caso não haja suportes suficientes.
    while sum(counts.values()) < DECK_SIZE:
        candidates = [cid for cid in monsters if counts[cid] < limits[cid] and
                      (effect_score[cid] > 0 or useful_edges[cid])]
        if not candidates:
            raise ModError('Faltam cartas úteis e cópias suficientes para 40 posições.')
        take(max(candidates, key=score))

    deck = tuple(cid for cid, amount in sorted(counts.items()) for _ in range(amount))
    validate_deck(allowed, effects, deck, default_copies)
    # Só reivindicar cadeia quando TODOS os materiais constam do deck.
    unique_steps = list(dict.fromkeys(realized))
    max_fusion_atk = max((_power(allowed[result])
                          for _, _, result in unique_steps), default=0)
    notes = []
    if not any(effect_score[cid] > 0 for cid in counts if cid in monsters):
        notes.append('Catálogo sem efeitos positivos nos materiais disponíveis; prioridade em fusões reais.')
    if level >= 4.3 and max_fusion_atk < 3000:
        notes.append('Sem rota viável de 3000+ ATK com os materiais e fusões disponíveis.')
    if not ps1_only and any(cid > CARD_COUNT or allowed[cid].get('virtual') for cid in counts):
        notes.append('Cartas customizadas #723+: deck exclusivo do Studio, sem exportação PS1.')
    weights = _weights(counts, preferences)
    return CampaignDeck(opponent, level, focus, deck, weights,
                        tuple(unique_steps), sum(counts[cid] for cid in counts
                                                 if cid in monsters and effect_score[cid] > 0),
                        max_fusion_atk, tuple(notes))
