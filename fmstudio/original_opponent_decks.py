"""Recriar o pool de um duelista usando exclusivamente a extração da ISO de origem.

O CSV `base/decks_drops.csv` é criado pelo decoder read-only de WA_MRG.MRG
quando a ISO é importada. Nunca usamos pesos que o usuário já editou no Studio.
Uma restauração *remove o override* do duelista, de modo que o PS1 continue
lendo a tabela original do disco, inclusive se o pool tiver <14 cartas distintas.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .core import ModError, _read_csv
from .tables import CARD_COUNT, DECK_SIZE, DUELIST_COUNT, POOL_TOTAL


def original_opponent_profile(project, opponent: int) -> dict:
    """Retorna 40 compras e pesos sem quantização, de CSV criado pela ISO."""
    if type(opponent) is not int or not 1 <= opponent < DUELIST_COUNT:
        raise ModError('Escolha um dos 39 adversários originais.')
    path = Path(project.folder) / 'base' / 'decks_drops.csv'
    if not path.is_file():
        raise ModError('A tabela de decks da ISO original não foi encontrada. '
                       'Importe/extraia a ISO no projeto antes de usar este botão.')
    try:
        rows = _read_csv(path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ModError(f'Não foi possível ler a tabela original: {exc}') from exc
    weights = {}
    for row in rows:
        try:
            if str(row['grupo']).strip().lower() != 'deck':
                continue
            raw_opponent = str(row['duelista_id']).strip()
            if not raw_opponent.isascii() or not raw_opponent.isdecimal():
                raise ValueError('ID do duelista inválido')
            if int(raw_opponent) != opponent:
                continue
            raw_cid, raw_weight = (str(row[field]).strip()
                                   for field in ('carta_id', 'peso'))
            if not all(x.isascii() and x.isdecimal() for x in (raw_cid, raw_weight)):
                raise ValueError('IDs/pesos devem ser inteiros não negativos')
            cid, weight = int(raw_cid), int(raw_weight)
            if not 1 <= cid <= CARD_COUNT or not 1 <= weight <= 65535:
                raise ValueError(f'Carta #{cid}: ID ou peso fora da tabela original.')
            if cid in weights:
                raise ValueError(f'Carta #{cid} repetida no pool original.')
            weights[cid] = weight
        except (KeyError, TypeError, ValueError) as exc:
            raise ModError(f'Tabela original do duelista #{opponent} inválida: {exc}') from exc
    if not weights:
        raise ModError(f'Não foram encontrados pesos de deck para o duelista #{opponent} '
                       'na ISO extraída. Nenhum deck foi alterado.')
    missing = sorted(cid for cid in weights if cid not in project.cards)
    if missing:
        raise ModError(f'Cartas originais ausentes no projeto: {missing[:8]}. '
                       'Não é seguro criar este deck.')
    return {'cartas': [], 'pools': [{
        'compras': DECK_SIZE, 'pesos': dict(sorted(weights.items()))
    }]}


def is_original_deck(profile: dict, original: dict) -> bool:
    """Igualdade exata dos IDs, compras e pesos; não basta o mesmo conjunto."""
    if not isinstance(profile, dict):
        return False
    try:
        return (not profile.get('cartas') and len(profile.get('pools', [])) == 1
                and int(profile['pools'][0]['compras']) == DECK_SIZE
                and {int(cid): int(weight) for cid, weight in profile['pools'][0]['pesos'].items()}
                == original['pools'][0]['pesos'])
    except (TypeError, ValueError, KeyError, AttributeError):
        return False


def restored_rules(rules: dict, opponent: int) -> dict:
    """Preserva todas as outras regras. Sem override, PS1 usa o WA original."""
    result = deepcopy(rules)
    duel = result.get('duelistas', {}).get(str(opponent))
    if duel is not None:
        duel.pop('deck', None)
        # O selo de dificuldade era uma propriedade do deck substituído.
        duel.pop('campanha_dificil', None)
    return result


def original_deck_summary(profile: dict) -> dict:
    weights = profile['pools'][0]['pesos']
    return {'cartas_distintas': len(weights),
            'compras': DECK_SIZE,
            'peso_total': sum(weights.values()),
            'peso_esperado': POOL_TOTAL,
            'pesos_originais': dict(weights)}
