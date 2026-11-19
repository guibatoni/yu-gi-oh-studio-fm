"""Busca e filtros de cartas (sem Tkinter): usados pelo seletor de cartas."""
from __future__ import annotations

from .expanded import card_matches, search_text
from .tables import TYPE_NAMES

CATEGORIES = {
    'Todas as cartas': lambda t: True,
    'Monstros': lambda t: t < 20 or t == 24,
    'Magias': lambda t: t == 20,
    'Armadilhas': lambda t: t == 21,
    'Rituais': lambda t: t == 22,
    'Equipamentos': lambda t: t == 23,
    **{f'Tipo: {name}': (lambda t, i=i: t == i) for i, name in enumerate(TYPE_NAMES[:20])},
}


def filter_cards(cards: dict, query: str = '', category: str = 'Todas as cartas', attribute: int = -1) -> list[int]:
    """IDs que passam na busca e nos filtros, em ordem de ID (sem Tkinter, testável)."""
    query = search_text(query).strip()
    accept = CATEGORIES.get(category, CATEGORIES['Todas as cartas'])
    result = []
    for cid in sorted(cards):
        card = cards[cid] or {}
        try:
            kind = int(card.get('tipo_id', -1))
        except (TypeError, ValueError):
            kind = -1
        if not accept(kind):
            continue
        if attribute != -1:
            try:
                if int(card.get('atributo_id', -1)) != attribute or not (kind < 20 or kind == 24):
                    continue
            except (TypeError, ValueError):
                continue
        if query and not card_matches(query, cid, card):
            continue
        result.append(cid)
    return result
