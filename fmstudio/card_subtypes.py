"""Sub-tipo das cartas: um segundo tipo/raça para bônus e equipamentos.

Um monstro com sub-tipo conta como dos dois tipos:

* bônus por tipo (aura, contagem no campo/deck, filtros) no simulador e no PS1;
* equipamentos: recebe todo equipamento que "serve no tipo" do sub-tipo. Como
  no FM a lista de cada equipamento é de cartas (não de tipos), o Studio decide
  que um equipamento serve num tipo quando já equipa pelo menos metade (e no
  mínimo 3) dos monstros daquele tipo, e acrescenta a carta à lista.
"""
from __future__ import annotations

from collections import defaultdict

from .mod_data import MONSTER_TYPES

EQUIP_SHARE = 0.5
EQUIP_MINIMUM = 3


def subtype(card) -> int | None:
    try:
        value = int(card.get('subtipo_id', -1))
    except (TypeError, ValueError):
        return None
    if value < 0 or value not in MONSTER_TYPES or value == int(card.get('tipo_id', -1)):
        return None
    return value


def types_of(card) -> set[int]:
    kinds = {int(card['tipo_id'])}
    extra = subtype(card)
    if extra is not None:
        kinds.add(extra)
    return kinds


def equip_additions(cards: dict, equips: dict) -> dict[int, list[int]]:
    """{equipamento: [cartas com sub-tipo a acrescentar]} (sem repetir as já incluídas)."""
    with_subtype = {cid: subtype(card) for cid, card in cards.items() if subtype(card) is not None}
    if not with_subtype:
        return {}
    by_type = defaultdict(set)
    for cid, card in cards.items():
        typ = int(card['tipo_id'])
        if typ in MONSTER_TYPES:
            by_type[typ].add(cid)
    out = {}
    for equip, targets in equips.items():
        targets = {int(t) for t in targets}
        add = []
        for cid, extra in sorted(with_subtype.items()):
            group = by_type.get(extra, set()) - {cid}
            covered = len(group & targets)
            if cid not in targets and covered >= EQUIP_MINIMUM and covered >= EQUIP_SHARE * len(group):
                add.append(cid)
        if add:
            out[int(equip)] = add
    return out
