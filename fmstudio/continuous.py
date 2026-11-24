"""Motor puro de auras e encantamentos para o simulador do Studio.

Recalcula os efeitos inteiramente do estado-base.
Auras podem conceder bônus a várias cartas ou escalar a própria carta.
Equipamentos permanecem anexos ao slot: status não persistem após remoção.
"""
from __future__ import annotations
from collections import Counter

EFFECT_ACTIONS = {'aura_tipo', 'bonus_por_tipo', 'bonus_deck_tipo', 'bonus_por_carta_id',
                  'bonus_cemiterio_tipo', 'bonus_mao_tipo'}
COUNT_ZONES = {'bonus_por_tipo': 'campo', 'bonus_deck_tipo': 'deck',
               'bonus_cemiterio_tipo': 'cemiterio', 'bonus_mao_tipo': 'mao'}
SCALING_ACTIONS = frozenset(COUNT_ZONES) | {'bonus_por_carta_id'}
EQUIPMENT_ACTIONS = {'equip_imune_armadilha', 'equip_imune_magia_armadilha',
                     'equip_indestrutivel', 'equip_indestrutivel_batalha', 'equip_atk'}
MAX_MONSTERS_PER_SIDE = 5
SIDES = ('jogador', 'adversario')


def _in_scope(source, target, scope):
    return scope == 'todos' or (source == target) == (scope == 'aliados')


def matches_filter(card, effect, cid=None):
    if 'carta_referencia_id' in effect:
        return cid == effect['carta_referencia_id']
    type_id = effect.get('tipo_id', -1)
    attribute = effect.get('atributo_id', -1)
    subtype = card.get('subtipo_id', -1)
    type_matches = (type_id == -1 or int(card['tipo_id']) == type_id
                    or (subtype not in (None, '', -1) and int(subtype) == type_id))
    attribute_matches = attribute == -1 or int(card.get('atributo_id', -1)) == attribute
    if type_id != -1 and attribute != -1 and effect.get('combinar_filtros') == 'ou':
        return type_matches or attribute_matches
    return type_matches and attribute_matches


def _count_bonus(effect, side, field, catalog, zones, legacy):
    origin = effect.get('origem_contagem') or COUNT_ZONES[effect['acao']]
    sides = [candidate for candidate in SIDES if _in_scope(side, candidate, effect['escopo'])]
    if origin == 'campo':
        return sum(monster['lado'] in sides and matches_filter(monster, effect, int(monster['card_id']))
                   for monster in field)
    if origin == 'deck' and 'deck_inicial' in zones:
        origin = 'deck_inicial'
    if origin in zones:
        return sum(matches_filter(catalog[cid], effect, cid)
                   for candidate in sides for cid in zones[origin].get(candidate, ()))
    if effect.get('atributo_id', -1) != -1:
        return 0
    if 'carta_referencia_id' in effect:
        return sum(legacy['deck_cards'].get(candidate, ()).count(effect['carta_referencia_id'])
                   for candidate in sides) if origin == 'deck' else 0
    typ = effect['tipo_id']
    return sum(sum(counter.values()) if typ == -1 else counter.get(typ, 0)
               for candidate in sides for counter in [legacy.get(origin, {}).get(candidate, {})])


def project_stats(card, cid, side, effects, field, *, catalog, zones):
    """Project a card's own counting bonuses in the hand or draw pile."""
    from .core import check_effect
    attack, defense = int(card['ataque']), int(card['defesa'])
    for raw in effects:
        if raw.get('evento') != 'continuo' or raw.get('acao') not in SCALING_ACTIONS:
            continue
        effect = check_effect(raw)
        count = _count_bonus(effect, side, field, catalog, zones, {})
        attack += effect['valor'] * count
        defense += effect['valor_def'] * count
    return {**card, 'id': cid, 'ataque_base': int(card['ataque']), 'defesa_base': int(card['defesa']),
            'ataque': attack, 'defesa': defense}


def resolve_field(monsters: list[dict], effects_by_card: dict, *,
                  deck_types: dict[str, Counter] | None = None,
                  equipments: list[dict] | None = None,
                  deck_cards: dict[str, list[int]] | None = None,
                  cemetery_types: dict[str, Counter] | None = None,
                  catalog: dict | None = None, zones: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Devolve novas cópias com bônus e proteções; não modifica o tabuleiro fornecido.

    `zones` contém os IDs das zonas e o deck inicial usado pelos bônus. Os contadores antigos
    ainda são aceitos em chamadas que fornecem somente as quantidades por tipo.
    `equipments`: lista {lado, slot, card_id}; associa uma carta equip ao monstro.
    """
    from .core import ModError, check_effect

    occupied: set[tuple[str, int]] = set()
    field = []
    for raw in monsters:
        side = raw.get('lado')
        if side not in SIDES:
            raise ModError('Campo: lado precisa ser jogador ou adversario')
        try:
            slot, cid, typ = (int(raw.get(key)) for key in ('slot','card_id','tipo_id'))
            attack, defense = (int(raw.get(key)) for key in ('ataque','defesa'))
        except (ValueError, TypeError) as exc:
            raise ModError('Campo: carta, tipo, slot, ATK e DEF devem ser inteiros') from exc
        if not 1 <= slot <= MAX_MONSTERS_PER_SIDE or (side, slot) in occupied:
            raise ModError('Campo: slot inválido ou ocupado')
        if cid < 1 or not 0 <= typ <= 31:
            raise ModError('Campo: ID/tipo fora do intervalo')
        if attack < 0 or defense < 0:
            raise ModError('Campo: ATK/DEF fora do intervalo')
        face = raw.get('face_up', True)
        if not isinstance(face, bool):
            raise ModError('Campo: face_up deve ser verdadeiro ou falso')
        occupied.add((side, slot))
        field.append({'lado':side, 'slot':slot, 'card_id':cid, 'tipo_id':typ,
            'subtipo_id':int(raw.get('subtipo_id', (catalog or {}).get(cid, {}).get('subtipo_id', -1))),
            'atributo_id':int(raw.get('atributo_id', -1)),
            'ataque_base':attack, 'defesa_base':defense,
            'ataque':attack + int(raw.get('modificador_atk', 0)),
            'defesa':defense + int(raw.get('modificador_def', 0)), 'face_up':face,
            'guardian_id':int(raw.get('guardian_id', raw.get('guardian_1_id', 0))),
            'posicao':raw.get('posicao', 'ataque'),
            'imune_armadilha':False, 'imune_magia':False, 'indestrutivel':False,
            'indestrutivel_batalha':False,
            'ataques_max':1, 'perfurante':False, 'nao_bloqueavel':False,
            'ataque_primeiro_turno':False})
    index = {(m['lado'],m['slot']): m for m in field}
    legacy = {'deck': deck_types or {}, 'deck_cards': deck_cards or {},
              'cemiterio': cemetery_types or {}}
    catalog, zones = catalog or {}, zones or {}
    events = []

    def effect_set(cid):
        return effects_by_card.get(str(cid), effects_by_card.get(cid, []))

    def add_bonus(src, target, effect, n, idx):
        atk = effect['valor'] * n
        defense = effect.get('valor_def',0) * n
        target['ataque'] = target['ataque'] + atk
        target['defesa'] = target['defesa'] + defense
        if atk or defense:
            events.append({'origem':(src['lado'],src['slot']),
                           'destino':(target['lado'],target['slot']),
                           'acao':effect['acao'], 'tipo_id':effect.get('tipo_id'),
                           'quantidade':n, 'ataque':atk, 'defesa':defense,
                           'indice_efeito':idx})

    for source in field:
        for i, raw in enumerate(effect_set(source['card_id'])):
            if raw.get('evento') != 'continuo':
                continue
            action = raw.get('acao')
            if (source['face_up'] or action == 'ataque_primeiro_turno') and action in (
                'ataques_multiplos', 'ataque_primeiro_turno', 'monstro_indestrutivel', 'monstro_imune_magia',
                'monstro_imune_armadilha', 'dano_perfurante', 'nao_bloqueavel',
                'monstro_indestrutivel_batalha'):
                eff = check_effect(raw)
                if action == 'ataques_multiplos':
                    source['ataques_max'] = max(source['ataques_max'], eff['valor'])
                elif action == 'ataque_primeiro_turno':
                    source['ataque_primeiro_turno'] = True
                elif action == 'monstro_indestrutivel':
                    source['indestrutivel'] = True
                elif action == 'monstro_indestrutivel_batalha':
                    source['indestrutivel_batalha'] = True
                elif action == 'monstro_imune_magia':
                    source['imune_magia'] = True
                elif action == 'monstro_imune_armadilha':
                    source['imune_armadilha'] = True
                elif action == 'dano_perfurante':
                    source['perfurante'] = True
                elif action == 'nao_bloqueavel':
                    source['nao_bloqueavel'] = True
                events.append({'origem':(source['lado'],source['slot']),
                               'destino':(source['lado'],source['slot']),
                               'acao':action,'tipo_id':None,'quantidade':1,
                               'ataque':0,'defesa':0,'indice_efeito':i})
                continue
            if action not in EFFECT_ACTIONS:
                continue
            eff = check_effect(raw)
            if action == 'aura_tipo':
                for target in field:
                    if _in_scope(source['lado'], target['lado'], eff['escopo']) and matches_filter(target, eff):
                        add_bonus(source, target, eff, 1, i)
            else:
                n = _count_bonus(eff, source['lado'], field, catalog, zones, legacy)
                add_bonus(source, source, eff, n, i)

    for equipment in equipments or []:
        side = equipment.get('lado')
        try:
            slot, cid = int(equipment.get('slot')), int(equipment.get('card_id'))
        except (ValueError, TypeError) as exc:
            raise ModError('Equipamento: slot e ID devem ser inteiros') from exc
        if side not in SIDES or not 1 <= slot <= MAX_MONSTERS_PER_SIDE or cid < 1:
            raise ModError('Equipamento: alvo ou carta inválidos')
        target = index.get((side,slot))
        if target is None:  # removido => anexos não produzem efeito
            continue
        for i,raw in enumerate(effect_set(cid)):
            if raw.get('evento') != 'equipado' or raw.get('acao') not in EQUIPMENT_ACTIONS:
                continue
            eff = check_effect(raw)
            action = eff['acao']
            if action == 'equip_imune_armadilha':
                target['imune_armadilha'] = True
            elif action == 'equip_imune_magia_armadilha':
                target['imune_armadilha'] = target['imune_magia'] = True
            elif action == 'equip_indestrutivel':
                target['indestrutivel'] = True
            elif action == 'equip_indestrutivel_batalha':
                target['indestrutivel_batalha'] = True
            else:
                target['ataque'] = target['ataque'] + eff['valor']
            events.append({'origem':('equip', cid), 'destino':(side,slot),
                           'acao':action, 'tipo_id':None,
                           'quantidade':1,
                           'ataque':eff['valor'] if action == 'equip_atk' else 0,
                           'defesa':0,'indice_efeito':i})
    for monster in field:
        for key in ('ataque', 'defesa'):
            monster[key] = max(0, monster[key])
    return field, events
