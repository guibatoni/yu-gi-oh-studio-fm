"""Cartas adicionais e referências. Metadados de MOD; não escreve no BIN original."""
from __future__ import annotations
import re
GOD_TYPE_ID = 24

def display_name(cid: int, cards: dict[int, dict]) -> str:
    row=cards.get(int(cid)) or cards.get(str(int(cid))) or {}
    return str(row.get('nome') or row.get('nome_original') or f'Carta #{int(cid):03d}')

def resolve_references(text: str, cards: dict[int, dict]) -> str:
    """Tokens mantêm o ID original; texto na interface mostra o nome atualizado."""
    return re.sub(r'\{card:([0-9]+)\}', lambda m: display_name(int(m.group(1)), cards), str(text))

def bonus_description(value: int, defense: int, reference: int, cards: dict, source: str='campo') -> str:
    name=display_name(reference,cards)
    stats=' e '.join(filter(None,[f'+{value} ATK' if value else '', f'+{defense} DEF' if defense else '']))
    zone = {'campo':'no campo', 'deck':'no deck', 'mao':'na mão', 'cemiterio':'no cemitério'}[source]
    return f'Esta carta recebe {stats} para cada {name} {zone}.'
