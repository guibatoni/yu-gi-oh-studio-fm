"""Edição em lote dos atributos das cartas (planeja antes, aplica nos rascunhos).

Nada é gravado em disco aqui: ``apply_plan`` só coloca as cartas alteradas na
sessão de rascunhos (``DraftSession``), como se o usuário tivesse editado uma a
uma. Salvar projeto (Ctrl+S) continua sendo o único passo que grava, com a
validação de sempre (``check_card_edit``).
"""
from __future__ import annotations

from .core import ModError
from .rarities import RARITIES
from .tables import SUPREME

STAT_OPERATIONS = {
    'definir': 'Definir',
    'somar': 'Somar',
    'subtrair': 'Subtrair',
    'percentual': 'Percentual (%)',
}
STATS = ('ataque', 'defesa')
CHOICES = ('tipo_id', 'atributo_id', 'nivel', 'raridade', 'guardian_1_id', 'guardian_2_id')
LIMITS = {'tipo_id': (0, 31), 'atributo_id': (0, 15), 'nivel': (0, 15),
          'guardian_1_id': (0, SUPREME), 'guardian_2_id': (0, SUPREME)}
STAT_MAX = 65535


def _int(value, label) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ModError(f'{label}: informe um número inteiro.') from None


def stat_result(current: int, operation: str, amount: int) -> int:
    if operation == 'definir':
        value = amount
    elif operation == 'somar':
        value = current + amount
    elif operation == 'subtrair':
        value = current - amount
    elif operation == 'percentual':
        # Ex.: 110 = +10%. O PS1 guarda ATK/DEF em passos de 10.
        value = int(round(current * amount / 100 / 10)) * 10
    else:
        raise ModError(f'Operação desconhecida: {operation}.')
    return max(0, min(STAT_MAX, value))


def normalize_changes(changes: dict) -> dict:
    """{'ataque': ('somar', '100'), 'tipo_id': 3, 'raridade': 'rara', ...} -> valores validados."""
    clean = {}
    for key, value in (changes or {}).items():
        if key in STATS:
            operation, amount = value
            if operation not in STAT_OPERATIONS:
                raise ModError(f'Operação desconhecida: {operation}.')
            amount = _int(amount, 'ATK' if key == 'ataque' else 'DEF')
            if operation == 'percentual' and not 0 <= amount <= 1000:
                raise ModError('Percentual: use de 0 a 1000 (100 = sem mudança).')
            if operation != 'percentual' and not 0 <= amount <= STAT_MAX:
                raise ModError(f'{"ATK" if key == "ataque" else "DEF"}: use de 0 a {STAT_MAX}.')
            clean[key] = (operation, amount)
        elif key == 'raridade':
            if value not in RARITIES:
                raise ModError('Raridade inválida.')
            clean[key] = value
        elif key in LIMITS:
            number = _int(value, key)
            low, high = LIMITS[key]
            if not low <= number <= high:
                raise ModError(f'{key}: use de {low} a {high}.')
            clean[key] = number
        else:
            raise ModError(f'Campo não suportado na edição em lote: {key}.')
    if not clean:
        raise ModError('Marque pelo menos um campo para alterar.')
    return clean


def plan(get_card, ids, changes: dict) -> list[dict]:
    """Prévia: [{'id', 'antes': {...}, 'depois': {...}}] só das cartas que mudam."""
    changes = normalize_changes(changes)
    rows = []
    for cid in sorted(set(int(i) for i in ids)):
        card = get_card(cid)
        before, after = {}, {}
        for key, value in changes.items():
            old = card.get(key)
            if key in STATS:
                new = stat_result(_int(old, key), *value)
                old = _int(old, key)
            elif key == 'raridade':
                new = value
            else:
                new = value
                old = _int(old, key)
            if new != old:
                before[key], after[key] = old, new
        if after:
            rows.append({'id': cid, 'nome': card.get('nome', ''), 'antes': before, 'depois': after})
    return rows


def apply_plan(drafts, rows: list[dict]) -> int:
    """Coloca cada carta alterada nos rascunhos. Retorna quantas cartas mudaram."""
    for row in rows:
        card = drafts.get_card(row['id'])
        card.update(row['depois'])
        drafts.stage_card(row['id'], card)
    return len(rows)
