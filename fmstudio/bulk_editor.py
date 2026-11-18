"""Operações em massa no baú do Studio e preços Password do PS1.

Não edita saves .mcr: a quantidade no projeto é a do simulador/Studio.
Os preços são efetivamente exportáveis em WA_MRG no perfil compatível.
"""
from __future__ import annotations
from dataclasses import dataclass
from .core import ModError
from .passwords import CHEST_KEY
from .ps1_economy import PASSWORD_PRICES_KEY, PRICE_LIMIT, price_overrides
from .tables import CARD_COUNT

OPERATIONS = ('definir', 'adicionar', 'subtrair', 'zerar')
MAX_COPIES = 9999


@dataclass(frozen=True)
class BulkRow:
    cid: int
    copies_before: int
    copies_after: int
    price_before: int | None
    price_after: int | None


def _int(value, description):
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdecimal():
        raise ModError(f'{description}: informe um número inteiro não negativo.')
    return int(value)


def _apply(current, operation, amount, *, maximum, label):
    if operation not in OPERATIONS:
        raise ModError(f'{label}: operação desconhecida.')
    if operation == 'zerar':
        result = 0
    else:
        number = _int(amount, label)
        result = {'definir': lambda: number,
                  'adicionar': lambda: current + number,
                  'subtrair': lambda: current - number}[operation]()
    if not 0 <= result <= maximum:
        raise ModError(f'{label}: valor final {result} fora do intervalo 0–{maximum}.')
    return result


def plan_bulk(project, ids, *, copies=None, price=None, original_prices=None):
    """Preparar e validar todas as linhas ANTES de modificar qualquer estado."""
    if copies is None and price is None:
        raise ModError('Escolha ao menos uma edição em massa.')
    chosen = sorted(set(_int(i, 'ID da carta') for i in ids))
    if not chosen:
        raise ModError('Selecione uma ou mais cartas.')
    known = getattr(project, 'cards', {})
    chest = project.metadata.get(CHEST_KEY, {})
    if not isinstance(chest, dict):
        raise ModError('Baú do projeto está inválido.')
    override = price_overrides(project)
    originals = original_prices or {}
    result = []
    for cid in chosen:
        if cid not in known:
            raise ModError(f'Carta #{cid} não está no projeto.')
        old_copies = _int(chest.get(str(cid), 0), f'Baú #{cid}')
        if old_copies > MAX_COPIES:
            raise ModError(f'Baú #{cid}: quantidade acima de {MAX_COPIES}.')
        new_copies = _apply(old_copies, *copies, maximum=MAX_COPIES, label=f'Baú #{cid}') if copies else old_copies
        old_price = override.get(cid, originals.get(cid, 1 if cid > CARD_COUNT and cid <= 740 else None))
        new_price = old_price
        if price is not None:
            if cid > 740 or (cid <= CARD_COUNT and known[cid].get('virtual')):
                raise ModError(f'Carta #{cid} não tem registro Password exportável.')
            if old_price is None:
                raise ModError(f'Carta #{cid}: custo original desconhecido. Importe a tabela de Passwords antes.')
            new_price = _apply(old_price, *price, maximum=PRICE_LIMIT, label=f'Password #{cid}')
        result.append(BulkRow(cid, old_copies, new_copies, old_price, new_price))
    return result


def commit_bulk(project, rows, *, copies=False, price=False):
    if not rows or (not copies and not price):
        raise ModError('Edição em massa vazia.')
    # Verificação de duplicatas evita aplicar uma linha duas vezes.
    if len({row.cid for row in rows}) != len(rows):
        raise ModError('Edição em massa possui cartas duplicadas.')
    before = project.metadata
    updated = dict(before)
    if copies:
        chest = dict(updated.get(CHEST_KEY, {}))
        for row in rows:
            if row.cid not in project.cards or not 0 <= row.copies_after <= MAX_COPIES:
                raise ModError('Quantidade inválida ou carta removida durante edição.')
            if row.copies_after:
                chest[str(row.cid)] = row.copies_after
            else:
                chest.pop(str(row.cid), None)
        updated[CHEST_KEY] = chest
    if price:
        prices = {str(cid): amount for cid, amount in price_overrides(project).items()}
        for row in rows:
            if row.cid not in project.cards or not 1 <= row.cid <= 740 or row.price_after is None:
                raise ModError('Preço inválido ou carta sem Password no PS1.')
            if row.cid <= CARD_COUNT and project.cards[row.cid].get('virtual'):
                raise ModError('Carta virtual não possui Password PS1.')
            if not 0 <= row.price_after <= PRICE_LIMIT:
                raise ModError('Custo em Star Chips fora do intervalo.')
            prices[str(row.cid)] = row.price_after
        updated[PASSWORD_PRICES_KEY] = prices
    project.metadata = updated
    try:
        project.save()  # O Project já gera backup rotativo antes de substituir o JSON.
    except Exception:
        project.metadata = before
        raise
    return len(rows)
