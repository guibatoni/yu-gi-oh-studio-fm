"""Guardian Stars shared by card previews and the Studio battle engine."""
from __future__ import annotations

from .tables import RETAIL_STAR_NAMES, STAR_NAMES, SUPREME

SUPREME_BADGE = '✦'
SUPREME_COLOR = '#f1cf6e'
# Mars beats Jupiter and the next star wins in each cycle, with wraparound.
STAR_ADVANTAGE = {
    star: star + 1 if star < end else start
    for start, end in ((1, 6), (7, 10)) for star in range(start, end + 1)
}


def guardian_name(star: int) -> str:
    if star == SUPREME:
        return f'{SUPREME_BADGE} Supreme'
    if star == 0:
        return 'Nenhuma'
    if 0 < star < len(STAR_NAMES) and STAR_NAMES[star]:
        return STAR_NAMES[star]
    return f'Estrela reservada {star}'


def guardian_options(card: dict) -> tuple[int, ...]:
    return tuple(dict.fromkeys(int(card.get(key, 0)) for key in ('guardian_1_id', 'guardian_2_id')))


def guardian_bonuses(left: int, right: int) -> tuple[int, int]:
    """Return the modifiers each contestant applies to both combat stats."""
    if left == SUPREME and 1 <= right < len(RETAIL_STAR_NAMES):
        return 700, 0
    if right == SUPREME and 1 <= left < len(RETAIL_STAR_NAMES):
        return 0, 700
    if STAR_ADVANTAGE.get(left) == right:
        return 500, 0
    if STAR_ADVANTAGE.get(right) == left:
        return 0, 500
    return 0, 0
