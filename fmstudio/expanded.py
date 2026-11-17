"""Cartas adicionais e referências. Metadados de MOD; não escreve no BIN original."""
from __future__ import annotations
import re
import unicodedata

from .tables import TYPE_NAMES
GOD_TYPE_ID = 24

def display_name(cid: int, cards: dict[int, dict]) -> str:
    row=cards.get(int(cid)) or cards.get(str(int(cid))) or {}
    return str(row.get('nome') or row.get('nome_original') or f'Carta #{int(cid):03d}')


def search_text(value: str) -> str:
    return ''.join(char for char in unicodedata.normalize('NFD', str(value).casefold())
                   if not unicodedata.combining(char))


def card_matches(query: str, cid: int, card: dict, *extra: str) -> bool:
    if not query:
        return True
    typ = int(card.get('tipo_id', -1))
    names = TYPE_NAMES[typ] if 0 <= typ < len(TYPE_NAMES) else ''
    names += {20: ' Magia Spell', 21: ' Armadilha', 22: ' Ritual', 23: ' Equipamento'}.get(typ, '')
    text = search_text(' '.join((f'#{cid} #{cid:03d}', str(card.get('nome') or ''),
                                 str(card.get('nome_original') or ''), names,
                                 str(card.get('descricao') or ''), *extra)))
    return all(part in text for part in query.split())

def resolve_references(text: str, cards: dict[int, dict]) -> str:
    """Tokens mantêm o ID original; texto na interface mostra o nome atualizado."""
    return re.sub(r'\{card:([0-9]+)\}', lambda m: display_name(int(m.group(1)), cards), str(text))

def bonus_description(value: int, defense: int, reference: int, cards: dict, source: str='campo') -> str:
    name=display_name(reference,cards)
    stats=' e '.join(filter(None,[f'+{value} ATK' if value else '', f'+{defense} DEF' if defense else '']))
    zone = {'campo':'no campo', 'deck':'no deck', 'mao':'na mão', 'cemiterio':'no cemitério'}[source]
    return f'Esta carta recebe {stats} para cada {name} {zone}.'
