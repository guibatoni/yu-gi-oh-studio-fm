"""Resumo da composição de um deck (para a interface; não altera regras de deck)."""
from __future__ import annotations

from collections import Counter

KINDS = {20: 'magias', 21: 'armadilhas', 22: 'rituais', 23: 'equipamentos'}


def composition(cards: dict, ids) -> dict:
    """Conta monstros/magias/armadilhas/rituais/equipamentos e médias de ATK/DEF dos monstros."""
    counts = Counter()
    atk = defense = monsters = 0
    unknown = 0
    for cid in ids:
        card = cards.get(int(cid))
        if not card:
            unknown += 1
            continue
        try:
            kind = int(card.get('tipo_id', -1))
        except (TypeError, ValueError):
            kind = -1
        if kind in KINDS:
            counts[KINDS[kind]] += 1
            continue
        counts['monstros'] += 1
        try:
            atk += int(card.get('ataque', 0))
            defense += int(card.get('defesa', 0))
            monsters += 1
        except (TypeError, ValueError):
            pass
    result = {key: counts.get(key, 0) for key in ('monstros', *KINDS.values())}
    result['desconhecidas'] = unknown
    result['atk_medio'] = round(atk / monsters) if monsters else 0
    result['def_medio'] = round(defense / monsters) if monsters else 0
    return result


def describe(summary: dict) -> str:
    parts = [f'{summary["monstros"]} monstros']
    for key, label in (('magias', 'magias'), ('armadilhas', 'armadilhas'),
                       ('equipamentos', 'equip.'), ('rituais', 'rituais')):
        if summary[key]:
            parts.append(f'{summary[key]} {label}')
    if summary['desconhecidas']:
        parts.append(f'{summary["desconhecidas"]} fora do catálogo')
    if summary['monstros']:
        parts.append(f'ATK médio {summary["atk_medio"]} · DEF médio {summary["def_medio"]}')
    return ' · '.join(parts)
