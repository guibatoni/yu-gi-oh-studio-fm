"""Motor puro de auras e encantamentos para o simulador do Studio.

Recalcula os efeitos inteiramente do estado-base.
Auras podem conceder bônus a várias cartas ou escalar a própria carta.
Equipamentos permanecem anexos ao slot: status não persistem após remoção.
"""
from __future__ import annotations
from collections import Counter

EFFECT_ACTIONS = {'aura_tipo', 'bonus_por_tipo', 'bonus_deck_tipo', 'bonus_por_carta_id', 'bonus_cemiterio_tipo'}
EQUIPMENT_ACTIONS = {'equip_imune_armadilha', 'equip_imune_magia_armadilha',
                     'equip_indestrutivel', 'equip_atk'}
MAX_MONSTERS_PER_SIDE = 5
SIDES = ('jogador', 'adversario')


def resolve_field(monsters: list[dict], effects_by_card: dict, *,
                  deck_types: dict[str, Counter] | None = None,
                  equipments: list[dict] | None = None,
                  deck_cards: dict[str, list[int]] | None = None,
                  cemetery_types: dict[str, Counter] | None = None) -> tuple[list[dict], list[dict]]:
    """Devolve novas cópias com bônus e proteções; não modifica o tabuleiro fornecido.

    `deck_types` é a contagem de TIPOS no deck completo configurado (incluindo
    cartas compradas), e não a pilha de compra restante. Se omitido, conta 0.
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
        if not 1 <= cid <= 32766 or not 0 <= typ <= 31:
            raise ModError('Campo: ID/tipo fora do intervalo')
        if attack < 0 or defense < 0:
            raise ModError('Campo: ATK/DEF fora do intervalo')
        face = raw.get('face_up', True)
        if not isinstance(face, bool):
            raise ModError('Campo: face_up deve ser verdadeiro ou falso')
        occupied.add((side, slot))
        field.append({'lado':side, 'slot':slot, 'card_id':cid, 'tipo_id':typ,
            'ataque_base':attack, 'defesa_base':defense,
            'ataque':attack, 'defesa':defense, 'face_up':face,
            'imune_armadilha':False, 'imune_magia':False, 'indestrutivel':False,
            'ataques_max':1, 'perfurante':False, 'nao_bloqueavel':False,
            'ataque_primeiro_turno':False})
    index = {(m['lado'],m['slot']): m for m in field}
    counts = Counter((m['lado'],m['tipo_id']) for m in field if m['face_up'])
    by_side = Counter(m['lado'] for m in field if m['face_up'])
    deck_types = deck_types or {}
    deck_cards = deck_cards or {}
    cemetery_types = cemetery_types or {}
    events = []

    def effect_set(cid):
        return effects_by_card.get(str(cid), effects_by_card.get(cid, []))

    def matching(recipient, source, effect):
        scope = effect.get('escopo','aliados')
        return (recipient['face_up'] and
                (effect['tipo_id'] == -1 or recipient['tipo_id'] == effect['tipo_id']) and
                (scope == 'todos' or
                 (recipient['lado'] == source['lado'] if scope == 'aliados'
                  else recipient['lado'] != source['lado'])))

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
        if not source['face_up']:
            continue
        for i, raw in enumerate(effect_set(source['card_id'])):
            action = raw.get('acao')
            if raw.get('evento') == 'continuo' and action in (
                'ataques_multiplos', 'ataque_primeiro_turno', 'monstro_indestrutivel', 'monstro_imune_magia',
                'monstro_imune_armadilha', 'dano_perfurante', 'nao_bloqueavel'):
                eff = check_effect(raw)
                if action == 'ataques_multiplos':
                    source['ataques_max'] = max(source['ataques_max'], eff['valor'])
                elif action == 'ataque_primeiro_turno':
                    source['ataque_primeiro_turno'] = True
                elif action == 'monstro_indestrutivel':
                    source['indestrutivel'] = True
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
            if raw.get('evento') != 'continuo' or raw.get('acao') not in EFFECT_ACTIONS:
                continue
            eff = check_effect(raw)
            if eff['acao'] == 'bonus_por_carta_id':
                scope = eff.get('escopo','aliados')
                sides=([source['lado']] if scope == 'aliados' else
                       [s for s in SIDES if s != source['lado']] if scope == 'inimigos' else list(SIDES))
                ref=eff['carta_referencia_id']
                n = (sum(1 for m in field if m['face_up'] and m['lado'] in sides and m['card_id']==ref)
                     if eff.get('origem_contagem') == 'campo' else
                     sum(1 for sd in sides for cid in deck_cards.get(sd,[]) if cid == ref))
                add_bonus(source,source,eff,n,i)
            elif eff['acao'] == 'bonus_cemiterio_tipo':
                typ = eff['tipo_id']
                scope = eff.get('escopo','aliados')
                sides = ([source['lado']] if scope == 'aliados' else
                         [s for s in SIDES if s != source['lado']] if scope == 'inimigos'
                         else list(SIDES))
                n = sum(sum(cemetery_types.get(s, Counter()).values()) if typ == -1
                        else cemetery_types.get(s, Counter()).get(typ, 0)
                        for s in sides)
                add_bonus(source, source, eff, n, i)
            elif eff['acao'] == 'aura_tipo':
                targets = [m for m in field if matching(m,source,eff)]
                for target in targets:
                    add_bonus(source,target,eff,1,i)
            elif eff['acao'] == 'bonus_por_tipo':
                n = len([m for m in field if matching(m,source,eff)])
                add_bonus(source,source,eff,n,i)
            else: # bônus por cada carta do tipo no deck inicial configurado
                typ = eff['tipo_id']
                scope = eff.get('escopo','aliados')
                select_sides = ([source['lado']] if scope == 'aliados' else
                                [s for s in SIDES if s != source['lado']] if scope == 'inimigos' else list(SIDES))
                n = sum(sum(counter.values()) if typ == -1 else counter.get(typ,0)
                        for s in select_sides for counter in [deck_types.get(s,Counter())])
                add_bonus(source,source,eff,n,i)

    for equipment in equipments or []:
        side = equipment.get('lado')
        try:
            slot, cid = int(equipment.get('slot')), int(equipment.get('card_id'))
        except (ValueError, TypeError) as exc:
            raise ModError('Equipamento: slot e ID devem ser inteiros') from exc
        if side not in SIDES or not 1 <= slot <= MAX_MONSTERS_PER_SIDE or not 1 <= cid <= 32766:
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
            else:
                target['ataque'] = target['ataque'] + eff['valor']
            events.append({'origem':('equip', cid), 'destino':(side,slot),
                           'acao':action, 'tipo_id':None,
                           'quantidade':1,
                           'ataque':eff['valor'] if action == 'equip_atk' else 0,
                           'defesa':0,'indice_efeito':i})
    return field, events
