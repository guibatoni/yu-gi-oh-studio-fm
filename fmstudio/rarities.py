"""Classes visuais do nome das cartas no Studio (ainda sem patch PS1).

O tipo da carta tem precedência para Trap, Magic, Equip e God. A raridade
configurada continua guardada em criaturas, inclusive se o tipo for alterado.
As cores RGB sao usadas apenas na interface e nos metadados do projeto.
"""
from __future__ import annotations

from collections import OrderedDict

RARITIES = OrderedDict([
    ('comum', ('Comum', '#CBD5E1')),          # cinza claro
    ('incomum', ('Incomum', '#FFFFFF')),       # branco
    ('rara', ('Rara', '#FFD84D')),             # amarelo
    ('epica', ('Épica', '#B57AFF')),           # roxo
    ('lendaria', ('Lendária', '#F04F57')),     # vermelho
    ('deus', ('Deus', '#123A79')),             # azul marinho
])
DEFAULT_RARITY = 'comum'

# IDs já utilizados pela tabela do Studio (tables.TYPE_NAMES).
TYPE_OVERRIDES = {
    20: ('Mágica', '#48D995', 'magica'),
    21: ('Trap', '#FF77C8', 'trap'),
    23: ('Equipamento', '#579DFF', 'equip'),
    24: ('Deus', RARITIES['deus'][1], 'deus'),
}


def validate_rarity(value: str) -> str:
    key = str(value).strip().lower()
    if key not in RARITIES:
        raise ValueError('Raridade inválida: escolha Comum, Incomum, Rara, Épica, Lendária ou Deus')
    return key


def name_style(card: dict) -> tuple[str, str, str]:
    """(rótulo, RGB, classe) usada na lista, na amostra e na carta.

    Não altera a cor salva das versões anteriores: o valor legado `cor_nome`
    permanece no projeto e pode ser recuperado em seus backups.
    """
    typ = int(card.get('tipo_id', -1))
    if typ in TYPE_OVERRIDES:
        return TYPE_OVERRIDES[typ]
    rarity = validate_rarity(card.get('raridade') or DEFAULT_RARITY)
    label, rgb = RARITIES[rarity]
    return label, rgb, rarity


def rarity_options() -> list[str]:
    return [f'{k} — {label}' for k, (label, _rgb) in RARITIES.items()]
