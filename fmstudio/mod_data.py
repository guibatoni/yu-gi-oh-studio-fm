"""Editable rules layered over the imported, read-only PS1 tables."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from random import SystemRandom

from .core import ModError, _read_csv, check_effect, positive_int, simulation_nonnegative_int
from .tables import CARD_COUNT, DECK_SIZE, DUELIST_NAMES_REFERENCE

CONFIG_KEY = 'edicao_mod'
DROP_FROM_DECK = 'drops_do_deck'
DECK_DROP_WEIGHTS = 'pesos_drops_do_deck'
STOCK_STARTER = 'Original do disco'
RANK_GROUPS = {
    **dict.fromkeys(('Z-POW', 'S-POW', 'A-POW'), 'pow'),
    **dict.fromkeys(('S-TEC', 'A-TEC'), 'tec'),
    **dict.fromkeys(('B-POW', 'C-POW', 'D-POW', 'B-TEC', 'C-TEC', 'D-TEC', 'B/C/D'), 'bcd'),
}
DROP_GROUPS = {'pow': 'S/A/Z-POW', 'tec': 'S/A-TEC', 'bcd': 'B/C/D'}
MONSTER_TYPES = frozenset((*range(20), 24))


def opposite(side: str) -> str:
    return 'adversario' if side == 'jogador' else 'jogador'


def card_effects(effects, cid):
    return effects.get(str(cid), effects.get(cid, ()))


def deck_copy_limit(effects, cid, default=3):
    limits = []
    unlimited = False
    for effect in card_effects(effects, cid):
        action = effect.get('acao')
        if action == 'sem_limite_deck':
            check_effect(effect)
            unlimited = True
        elif action == 'limite_copias_deck':
            limits.append(check_effect(effect)['valor'])
    if 0 in limits:
        return 0
    return DECK_SIZE if unlimited else min(limits, default=default)


def validate_deck(cards, effects, ids, default=3):
    if len(ids) > DECK_SIZE:
        raise ModError(f'Deck comporta até {DECK_SIZE} cartas.')
    for cid, quantity in Counter(ids).items():
        if cid not in cards:
            raise ModError(f'Carta #{cid} não encontrada.')
        limit = deck_copy_limit(effects, cid, default)
        if not limit:
            raise ModError(f'Carta #{cid} banida (limite de 0 cópias por deck).')
        if quantity > limit:
            raise ModError(f'Deck: carta #{cid} tem {quantity} cópias (máximo {limit}).')


def weighted_choice(weights, rng):
    total = sum(weights.values())
    if total <= 0:
        raise ModError('A tabela precisa ter pelo menos um peso positivo.')
    roll = rng.randrange(total)
    for key, weight in weights.items():
        if roll < weight:
            return key
        roll -= weight
    raise ModError('Distribuição de pesos inválida.')


def _can_deal(draws, limits):
    """Check overlapping pools with capacitated matching of cards to draws."""
    assigned = {}

    def place(draw, visited):
        for cid in draw:
            if cid in visited or not limits.get(cid, 0):
                continue
            visited.add(cid)
            owners = assigned.setdefault(cid, [])
            if len(owners) < limits[cid]:
                owners.append(draw)
                return True
            for index, previous in enumerate(owners):
                if place(previous, visited):
                    owners[index] = draw
                    return True
        return False

    return all(place(draw, set()) for draw in sorted(draws, key=len))


def deal_deck(profile, cards, effects, rng=None, *, default_copies=3):
    """Deal the exact list or weighted slots, with no replacement of available copies."""
    rng = rng or SystemRandom()
    fixed = list(profile.get('cartas', []))
    validate_deck(cards, effects, fixed, default_copies)
    held = Counter(fixed)
    draws = [{cid: weight for cid, weight in pool['pesos'].items() if weight > 0}
             for pool in profile.get('pools', []) for _ in range(pool['compras'])]
    if not fixed and not draws:
        raise ModError('Configure as cartas ou os pesos do deck.')
    if len(fixed) + len(draws) > DECK_SIZE:
        raise ModError(f'Deck comporta até {DECK_SIZE} cartas.')
    limits = {cid: deck_copy_limit(effects, cid, default_copies) - held[cid]
              for draw in draws for cid in draw}
    if any(cid not in cards for cid in limits):
        raise ModError('Um dos pools referencia uma carta ausente do catálogo.')
    if not _can_deal(draws, limits):
        raise ModError('Os pools não têm cópias disponíveis para todas as compras configuradas.')
    for offset, draw in enumerate(draws):
        available = {cid: weight for cid, weight in draw.items() if limits[cid] > 0 and weight > 0}
        while available:
            cid = weighted_choice(available, rng)
            limits[cid] -= 1
            if _can_deal(draws[offset+1:], limits):
                fixed.append(cid)
                break
            limits[cid] += 1
            available.pop(cid)
        else:
            raise ModError('Não foi possível preencher o deck com os pesos configurados.')
    return fixed


def _ref(cards, value):
    cid = positive_int(value, 'ID da carta')
    if cid not in cards:
        raise ModError(f'Carta #{cid} não encontrada no catálogo.')
    return cid


def normalize_weights(values, cards):
    weights = {}
    for key, value in values.items():
        cid = _ref(cards, key)
        weight = simulation_nonnegative_int(value, f'Peso de #{cid}')
        if weight:
            weights[cid] = weight
    return weights


def _normalize_deck(value, cards):
    fixed = [_ref(cards, cid) for cid in value.get('cartas', [])]
    pools = []
    for row in value.get('pools', []):
        draws = simulation_nonnegative_int(row.get('compras'), 'Compras do pool')
        weights = normalize_weights(row.get('pesos', {}), cards)
        if draws:
            if not weights:
                raise ModError('Informe pesos para o pool com compras.')
            pools.append({'compras': draws, 'pesos': weights})
    if len(fixed) + sum(pool['compras'] for pool in pools) > DECK_SIZE:
        raise ModError(f'Deck comporta até {DECK_SIZE} cartas.')
    return {'cartas': fixed, 'pools': pools}


def normalize_rules(data, cards):
    """Validate a settings snapshot without changing the project."""
    out = deepcopy(data)
    if 'ia_ps1' in out and out['ia_ps1'] not in ('normal', 'dificil'):
        raise ModError('IA PS1: escolha Normal ou Difícil.')
    if 'lp_inicial' in out:
        out['lp_inicial'] = positive_int(out['lp_inicial'], 'LP inicial para ambos')
    if 'lp_jogador' in out:
        out['lp_jogador'] = positive_int(out['lp_jogador'], 'LP legado do jogador')
    for key, duelist in out.get('duelistas', {}).items():
        if not 0 <= simulation_nonnegative_int(key, 'ID do duelista') < len(DUELIST_NAMES_REFERENCE):
            raise ModError(f'Duelista #{key} fora da grade original.')
        if 'lp' in duelist:
            duelist['lp'] = positive_int(duelist['lp'], 'LP do oponente')
        if 'deck' in duelist:
            duelist['deck'] = _normalize_deck(duelist['deck'], cards)
        if DROP_FROM_DECK in duelist and not isinstance(duelist[DROP_FROM_DECK], bool):
            raise ModError('Escolha se os drops do duelista vêm do próprio deck.')
        for rank, weights in duelist.get(DECK_DROP_WEIGHTS, {}).items():
            if rank not in DROP_GROUPS:
                raise ModError(f'Drops do deck: grupo inválido {rank}.')
            duelist[DECK_DROP_WEIGHTS][rank] = normalize_weights(weights, cards)
        for rank, weights in duelist.get('drops', {}).items():
            if rank not in RANK_GROUPS and rank not in DROP_GROUPS:
                raise ModError(f'Grupo de rank inválido: {rank}.')
            duelist['drops'][rank] = normalize_weights(weights, cards)
    for label, profile in out.get('iniciais', {}).items():
        if not label.strip():
            raise ModError('Informe o nome do deck inicial.')
        out['iniciais'][label] = {
            'peso': simulation_nonnegative_int(profile.get('peso', 1), 'Peso do deck inicial'),
            **_normalize_deck(profile, cards),
        }
    if 'pools_iniciais_ps1' in out:
        out['pools_iniciais_ps1'] = _normalize_deck({'pools': out['pools_iniciais_ps1']}, cards)['pools']
    recipes = out.get('receitas', {})
    if 'fusoes' in recipes:
        fusion_pairs = {}
        for pair, result in recipes['fusoes'].items():
            ids = pair.split(',')
            if len(ids) != 2:
                raise ModError('Uma fusão exige dois materiais.')
            a, b = sorted(_ref(cards, cid) for cid in ids)
            result = _ref(cards, result)
            if any(int(cards[cid]['tipo_id']) not in MONSTER_TYPES for cid in (a, b, result)):
                raise ModError('Materiais e resultado devem ser monstros.')
            fusion_pairs[f'{a},{b}'] = result
        recipes['fusoes'] = fusion_pairs
    if 'rituais' in recipes:
        for key, recipe in recipes['rituais'].items():
            ritual = _ref(cards, key)
            tributes = [_ref(cards, cid) for cid in recipe.get('tributos', [])]
            result = _ref(cards, recipe.get('resultado'))
            if int(cards[ritual]['tipo_id']) != 22 or not 1 <= len(tributes) <= 5:
                raise ModError('Um ritual requer uma carta de Ritual e de 1 a 5 tributos.')
            if any(int(cards[cid]['tipo_id']) not in MONSTER_TYPES for cid in (*tributes, result)):
                raise ModError('Tributos e resultado devem ser monstros.')
            recipes['rituais'][key] = {'tributos': tributes, 'resultado': result}
    if 'equipamentos' in recipes:
        for key, targets in recipes['equipamentos'].items():
            equip = _ref(cards, key)
            if int(cards[equip]['tipo_id']) != 23:
                raise ModError('Selecione uma carta do tipo Equip.')
            targets = sorted({_ref(cards, cid) for cid in targets})
            if any(int(cards[cid]['tipo_id']) not in MONSTER_TYPES for cid in targets):
                raise ModError('Equipamentos devem apontar para monstros.')
            recipes['equipamentos'][key] = targets
    return out


def save_rules(project, rules):
    clean = normalize_rules(rules, {cid: project.get(cid) for cid in project.cards})
    previous = project.metadata.get(CONFIG_KEY)
    project.metadata[CONFIG_KEY] = clean
    try:
        project.save()
    except Exception:
        if previous is None:
            project.metadata.pop(CONFIG_KEY)
        else:
            project.metadata[CONFIG_KEY] = previous
        raise
    return clean


def global_starting_lp(project):
    """Uma única configuração de LP do mod aplicada a ambos os participantes.

    Arquivos antigos usam lp_jogador como fonte de migração; as antigas
    substituições por duelista e do laboratório não definem mais o duelo.
    """
    config = project.metadata.get(CONFIG_KEY, {})
    return positive_int(config.get('lp_inicial', config.get('lp_jogador', 8000)),
                        'LP inicial para ambos')


def starting_life(project, opponent):
    value = global_starting_lp(project)
    return {'jogador': value, 'adversario': value}


def base_tables(project):
    """Read only the extracted CSVs that are present in an existing project."""
    base = project.folder / 'base'

    def rows(name):
        path = base / f'{name}.csv'
        return _read_csv(path) if path.is_file() else []

    pools, starters, equips = {}, {}, {}
    for row in rows('decks_drops'):
        pools.setdefault((int(row['duelista_id']), row['grupo']), {})[int(row['carta_id'])] = int(row['peso'])
    for row in rows('decks_iniciais'):
        group = starters.setdefault(int(row['grupo']), {'compras': int(row['compras']), 'pesos': {}})
        group['pesos'][int(row['carta_id'])] = int(row['peso'])
    for row in rows('equipamentos'):
        equips.setdefault(int(row['equipamento_id']), set()).add(int(row['monstro_id']))
    rituals = {int(row['ritual_id']): ([int(row[f'tributo_{i}']) for i in (1, 2, 3)], int(row['resultado']))
               for row in rows('rituais')}
    return pools, [starters[i] for i in sorted(starters)], equips, rituals


def match_recipes(project, equips, rituals):
    """Build the effective Studio tables while preserving the imported CSVs."""
    custom = project.metadata.get(CONFIG_KEY, {}).get('receitas', {})
    fusions = {tuple(sorted((int(row['material_1']), int(row['material_2'])))): int(row['resultado'])
               for row in project.fusions if str(row.get('possivel_glitch', 0)) != '1'}
    fusions.update({tuple(map(int, pair.split(','))): int(cid)
                    for pair, cid in custom.get('fusoes', {}).items()})
    equips = {cid: set(targets) for cid, targets in equips.items()}
    mode = project.metadata.get('ps1_equip_mode', 'adicionar')
    if mode == 'adicionar':
        for cid, targets in project.metadata.get('ps1_equip_additions', {}).items():
            equips.setdefault(int(cid), set()).update(map(int, targets))
    else:
        for cid, replacements in project.metadata.get('ps1_equip_replacements', {}).items():
            targets = equips.setdefault(int(cid), set())
            for old, new in replacements.items():
                targets.discard(int(old))
                targets.add(int(new))
    equips.update({int(cid): set(targets) for cid, targets in custom.get('equipamentos', {}).items()})
    # Sub-tipo: o monstro recebe os equipamentos que servem no seu 2º tipo.
    from .card_subtypes import equip_additions
    catalog = {cid: project.get(cid) for cid in getattr(project, 'cards', {})}
    for cid, targets in equip_additions(catalog, equips).items():
        equips.setdefault(cid, set()).update(targets)
    if project.metadata.get('ps1_rituals_enabled'):
        for cid, recipe in project.metadata.get('ps1_ritual_recipes', {}).items():
            if isinstance(recipe, dict):
                rituals[int(cid)] = (list(map(int, recipe['tributos'])), int(recipe['resultado']))
            else:
                rituals[int(cid)] = (list(map(int, recipe[:3])), int(recipe[3]))
    rituals.update({int(cid): (recipe['tributos'], recipe['resultado'])
                    for cid, recipe in custom.get('rituais', {}).items()})
    return fusions, equips, rituals


def duelist_profile(config, pools, opponent):
    duelist = config.get('duelistas', {}).get(str(opponent), {})
    if 'deck' in duelist:
        return duelist['deck']
    weights = pools.get((opponent, 'deck'), {})
    return {'pools': [{'compras': DECK_SIZE, 'pesos': weights}]} if weights else {}


def drops_from_deck(config, opponent):
    return config.get('duelistas', {}).get(str(opponent), {}).get(DROP_FROM_DECK, False)


def deck_drop_candidates(config, pools, opponent, *, effects=None):
    """IDs permitidos para drops ponderados, retirados do deck configurado.

    Num deck com pools a seleção é dos candidatos possíveis, não apenas
    das cartas sorteadas no duelo atual. Num deck fixo é exatamente o deck.
    """
    profile = duelist_profile(config, pools, opponent)
    candidates = set(map(int, profile.get('cartas', ()))) | {
        int(cid) for pool in profile.get('pools', ())
        for cid, weight in pool['pesos'].items() if int(weight) > 0
    }
    return {cid for cid in candidates if deck_copy_limit(effects or {}, cid)}


def deck_drop_weights(config, pools, opponent, rank, *, effects=None):
    """Pesos por grupo de rank, restritos ao deck do próprio duelista.

    Projetos antigos com a opção booleana têm migração automática para
    peso 1 por ID, em vez da antiga recompensa fixa do deck sorteado.
    """
    group = RANK_GROUPS.get(rank, rank)
    if group not in DROP_GROUPS:
        raise ModError(f'Grupo de rank de drop inválido: {rank}')
    candidates = deck_drop_candidates(config, pools, opponent, effects=effects)
    custom = config.get('duelistas', {}).get(str(opponent), {}).get(DECK_DROP_WEIGHTS, {})
    if group not in custom:
        return {cid: 1 for cid in sorted(candidates)}
    return {int(cid): int(weight) for cid, weight in custom[group].items()
            if int(cid) in candidates and int(weight) > 0}


def drop_weights(config, pools, opponent, rank, *, dealt_deck=(), effects=None):
    if drops_from_deck(config, opponent):
        return deck_drop_weights(config, pools, opponent, rank, effects=effects)
    rank_group = RANK_GROUPS.get(rank, rank)
    custom = config.get('duelistas', {}).get(str(opponent), {}).get('drops', {})
    weights = custom.get(rank, custom.get(rank_group, pools.get((opponent, rank_group), {})))
    return {int(cid): int(weight) for cid, weight in weights.items() if int(weight) > 0}
