"""Valores das mágicas no PS1 (Drop x15): cura, dano direto e destruição por tipo.

Tabelas do executável (nomes da decompilação de Forbidden Memories):

* ``gDuel_abLifePointRecoveryUnits`` em ``0x8009AF30``: 5 bytes, cartas #338–#342,
  multiplicados por 100 LP;
* ``gDuel_abDirectDamageUnits`` em ``0x8009AF38``: 5 bytes, cartas #343–#347,
  multiplicados por 10 LP;
* ``gDuel_abMonsterRemovalRules`` em ``0x80090A4C``: 7 pares ``(carta - 600,
  seletor)``. Seletor 0–20 é o tipo destruído; 21 ou mais é um ATK mínimo
  (seletor × 10), como o Crush Card.

Só os bytes de valor mudam; o ID de cada regra é conferido antes da escrita.
"""
from __future__ import annotations

import struct

from .core import ModError
from .tables import EXE_DELTA, TYPE_NAMES

SETTINGS_KEY = 'ps1_magic_values'
HEAL_TABLE, HEAL_FIRST, HEAL_SCALE = 0x8009AF30, 338, 100
DAMAGE_TABLE, DAMAGE_FIRST, DAMAGE_SCALE = 0x8009AF38, 343, 10
FAMILY_SIZE = 5
REMOVAL_TABLE, REMOVAL_BASE = 0x80090A4C, 600
REMOVAL_CARDS = (653, 656, 660, 661, 662, 663, 664)
MONSTER_TYPES = 21          # 0..20; 20 = Magic is not a monster but the engine accepts it
ATK_SELECTOR_MIN = 21       # selectors >= 21 mean "ATK >= selector * 10"
HEAL_CARDS = tuple(range(HEAL_FIRST, HEAL_FIRST + FAMILY_SIZE))
DAMAGE_CARDS = tuple(range(DAMAGE_FIRST, DAMAGE_FIRST + FAMILY_SIZE))


def _at(exe: bytes, address: int, size: int = 1) -> int:
    at = address - EXE_DELTA
    if not exe.startswith(b'PS-X EXE') or at < 0 or at + size > len(exe):
        raise ModError('O executável não contém as tabelas de mágicas do PS1.')
    return at


def _int(value, label):
    if isinstance(value, bool):
        raise ModError(f'{label}: use um número inteiro.')
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ModError(f'{label}: use um número inteiro.') from exc


def normalize(raw) -> dict:
    """{'cura': {cid: LP}, 'dano': {cid: LP}, 'destruicao': {cid: {'tipo': n} | {'atk_min': n}}}"""
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ModError('Valores de mágicas inválidos no projeto.')
    result = {'cura': {}, 'dano': {}, 'destruicao': {}}
    for key, cards, scale, label in (('cura', HEAL_CARDS, HEAL_SCALE, 'Cura'),
                                     ('dano', DAMAGE_CARDS, DAMAGE_SCALE, 'Dano')):
        for cid, value in (raw.get(key) or {}).items():
            cid, value = _int(cid, label), _int(value, label)
            if cid not in cards:
                raise ModError(f'{label}: a carta #{cid} não usa esta tabela do PS1.')
            if not 0 <= value <= 255 * scale or value % scale:
                raise ModError(f'{label} #{cid}: use múltiplos de {scale} entre 0 e {255 * scale}.')
            result[key][cid] = value
    for cid, rule in (raw.get('destruicao') or {}).items():
        cid = _int(cid, 'Destruição')
        if cid not in REMOVAL_CARDS or not isinstance(rule, dict) or len(rule) != 1:
            raise ModError(f'Destruição: regra inválida para a carta #{cid}.')
        if 'tipo' in rule:
            kind = _int(rule['tipo'], 'Tipo')
            if not 0 <= kind < MONSTER_TYPES:
                raise ModError(f'Destruição #{cid}: tipo fora de 0–{MONSTER_TYPES - 1}.')
            result['destruicao'][cid] = {'tipo': kind}
        elif 'atk_min' in rule:
            atk = _int(rule['atk_min'], 'ATK mínimo')
            if not ATK_SELECTOR_MIN * 10 <= atk <= 2550 or atk % 10:
                raise ModError(f'Destruição #{cid}: ATK mínimo em múltiplos de 10, de 210 a 2550.')
            result['destruicao'][cid] = {'atk_min': atk}
        else:
            raise ModError(f'Destruição #{cid}: informe tipo ou ATK mínimo.')
    return result


def magic_values(project) -> dict:
    return normalize((getattr(project, 'metadata', None) or {}).get(SETTINGS_KEY))


def is_empty(values: dict) -> bool:
    return not any(values.values())


def save_magic_values(project, values: dict):
    clean = normalize(values)
    stored = {key: {str(cid): value for cid, value in sorted(rows.items())} for key, rows in clean.items()}
    before = project.metadata
    project.metadata = {**before, SETTINGS_KEY: stored}
    try:
        project.save()
    except OSError:
        project.metadata = before
        raise
    return clean


def read_values(exe: bytes) -> dict:
    """Valores atuais do SLUS, no mesmo formato de ``normalize``."""
    heal = _at(exe, HEAL_TABLE, FAMILY_SIZE)
    damage = _at(exe, DAMAGE_TABLE, FAMILY_SIZE)
    removal = _at(exe, REMOVAL_TABLE, 2 * len(REMOVAL_CARDS))
    rules = {}
    for index, cid in enumerate(REMOVAL_CARDS):
        card, selector = exe[removal + 2 * index], exe[removal + 2 * index + 1]
        if card + REMOVAL_BASE != cid:
            raise ModError('A tabela de destruição por tipo diverge do Drop x15.')
        rules[cid] = {'tipo': selector} if selector < ATK_SELECTOR_MIN else {'atk_min': selector * 10}
    return {'cura': {cid: exe[heal + i] * HEAL_SCALE for i, cid in enumerate(HEAL_CARDS)},
            'dano': {cid: exe[damage + i] * DAMAGE_SCALE for i, cid in enumerate(DAMAGE_CARDS)},
            'destruicao': rules}


def apply(exe: bytes, values: dict) -> tuple[bytes, dict]:
    values = normalize(values)
    read_values(exe)  # validates the removal IDs and table bounds
    result = bytearray(exe)
    heal, damage = _at(exe, HEAL_TABLE, FAMILY_SIZE), _at(exe, DAMAGE_TABLE, FAMILY_SIZE)
    removal = _at(exe, REMOVAL_TABLE, 2 * len(REMOVAL_CARDS))
    for cid, lp in values['cura'].items():
        result[heal + HEAL_CARDS.index(cid)] = lp // HEAL_SCALE
    for cid, lp in values['dano'].items():
        result[damage + DAMAGE_CARDS.index(cid)] = lp // DAMAGE_SCALE
    for cid, rule in values['destruicao'].items():
        selector = rule['tipo'] if 'tipo' in rule else rule['atk_min'] // 10
        result[removal + 2 * REMOVAL_CARDS.index(cid) + 1] = selector
    final = read_values(bytes(result))
    return bytes(result), {'status': 'aplicado',
                           'cura': {str(k): v for k, v in final['cura'].items()},
                           'dano': {str(k): v for k, v in final['dano'].items()},
                           'destruicao': {str(k): v for k, v in final['destruicao'].items()},
                           'validado_epsxe': False}


def matches(exe: bytes, values: dict) -> bool:
    current = read_values(exe)
    values = normalize(values)
    return all(current[key][cid] == value for key in values for cid, value in values[key].items())


def describe_rule(rule: dict) -> str:
    if 'tipo' in rule:
        return TYPE_NAMES[rule['tipo']]
    return f"ATK ≥ {rule['atk_min']}"


# Values of the Drop x15 SLUS (read from ePSXe RAM), shown as "original" in the Studio.
DROP15_DEFAULTS = {
    'cura': dict(zip(HEAL_CARDS, (200, 500, 1000, 2000, 5000))),
    'dano': dict(zip(DAMAGE_CARDS, (50, 100, 200, 500, 1000))),
    'destruicao': {653: {'tipo': 3}, 656: {'tipo': 2}, 660: {'tipo': 14}, 661: {'atk_min': 1500},
                   662: {'tipo': 9}, 663: {'tipo': 18}, 664: {'tipo': 12}},
}
