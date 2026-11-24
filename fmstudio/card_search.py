"""Busca e filtros de cartas (sem Tkinter): usados pelo seletor de cartas."""
from __future__ import annotations

from .expanded import card_matches, search_text
from .tables import GUARDIAN_FIELDS, RETAIL_STAR_NAMES, STAR_NAMES, TYPE_NAMES

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


# --- Estrela guardiã e fusões (filtros para montar decks) ---------------------

ALL_STARS = 'Todas as estrelas'
STAR_FILTERS = (ALL_STARS, *[name for name in RETAIL_STAR_NAMES if name], STAR_NAMES[-1])


def _is_monster(card) -> bool:
    try:
        kind = int((card or {}).get('tipo_id', -1))
    except (TypeError, ValueError):
        return False
    return kind < 20 or kind == 24


def card_stars(card) -> tuple[int, ...]:
    """IDs das estrelas guardiãs de um monstro (vazio para magias e afins)."""
    if not _is_monster(card):
        return ()
    stars = []
    for field in GUARDIAN_FIELDS:
        try:
            star = int(card.get(field, 0))
        except (TypeError, ValueError):
            continue
        if 0 < star < len(STAR_NAMES) and STAR_NAMES[star] and star not in stars:
            stars.append(star)
    return tuple(stars)


def star_label(card) -> str:
    return '/'.join(STAR_NAMES[star] for star in card_stars(card)) or '—'


def has_star(card, star_name: str) -> bool:
    if not star_name or star_name == ALL_STARS:
        return True
    return any(STAR_NAMES[star] == star_name for star in card_stars(card))


def _attack(cards, cid) -> int:
    try:
        return int((cards.get(cid) or {}).get('ataque', 0))
    except (TypeError, ValueError):
        return 0


def fusion_results(fusions: dict) -> set[int]:
    """Cartas que saem de alguma fusão (``fusions``: {(a, b): resultado})."""
    return {int(result) for result in fusions.values()}


def fusion_materials(fusions: dict, result: int) -> dict[int, list[int]]:
    """{material: [parceiros]} das receitas que formam ``result``."""
    out: dict[int, list[int]] = {}
    for (a, b), made in fusions.items():
        if int(made) != int(result):
            continue
        for card, partner in ((a, b), (b, a)):
            partners = out.setdefault(int(card), [])
            if int(partner) not in partners:
                partners.append(int(partner))
    return out


def fusions_with(fusions: dict, deck_ids, cards: dict) -> dict[int, tuple[int, int]]:
    """{carta: (resultado, parceiro do deck)}: a melhor fusão (maior ATK) com o deck."""
    deck = {int(cid) for cid in deck_ids}
    best: dict[int, tuple[int, int]] = {}
    for (a, b), made in fusions.items():
        for card, partner in ((int(a), int(b)), (int(b), int(a))):
            if partner not in deck:
                continue
            current = best.get(card)
            if current is None or _attack(cards, made) > _attack(cards, current[0]):
                best[card] = (int(made), partner)
    return best
