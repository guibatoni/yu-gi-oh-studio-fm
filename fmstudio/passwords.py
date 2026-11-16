"""Passwords clássicos importados e códigos reversíveis das cartas do Studio."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from .core import ModError, _read_csv, _write_csv, positive_int, ps1_supports_god24
from .mod_data import CONFIG_KEY, deal_deck, normalize_rules
from .tables import CARD_COUNT, decode_passwords

ORIGINAL_CODE = re.compile(r'[0-9]{8}')
STUDIO_CODE = re.compile(r'(?:FM-|#)?([0-9]+)', re.ASCII | re.IGNORECASE)
CHEST_KEY = 'bau_jogador'
PS1_ID_PREFIX = 'ps1_password_id_prefix'


@dataclass(frozen=True)
class OriginalPassword:
    code: str
    cost: int | None


def original_passwords(project) -> dict[int, OriginalPassword]:
    path = project.folder / 'base' / 'senhas.csv'
    if not path.is_file():
        return {}
    records = {}
    for row in _read_csv(path):
        code = (row.get('password') or '').strip()
        if row.get('password_valido_bcd') == '0' or not ORIGINAL_CODE.fullmatch(code):
            continue
        cid = positive_int(row.get('carta_id'), 'ID do password')
        if 1 <= cid <= CARD_COUNT and cid in project.cards and not project.cards[cid].get('virtual'):
            cost = (row.get('custo_starchips') or '').strip()
            records[cid] = OriginalPassword(code, int(cost) if cost else None)
    return records


def import_original_passwords(project, source):
    from .ps1_mod import read_linked_wa
    rows = decode_passwords(read_linked_wa(project, source))
    base = project.folder / 'base'
    with TemporaryDirectory(prefix='.senhas_', dir=base) as directory:
        destination = base / 'senhas.csv'
        staged = Path(directory) / destination.name
        _write_csv(staged, rows)
        staged.replace(destination)
    return original_passwords(project)


def id_code(cid: int) -> str:
    return f'FM-{positive_int(cid, "ID da carta"):08d}'


def redeem_id(code: str, cards) -> int:
    match = STUDIO_CODE.fullmatch(code.strip())
    if match is None:
        raise ModError('Informe um ID, como 723, ou o código FM-00000723.')
    cid = int(match[1])
    if cid not in cards:
        raise ModError(f'Carta #{cid} indisponível neste projeto.')
    return cid


def redeem_original(code: str, records) -> list[int]:
    code = code.strip()
    if ORIGINAL_CODE.fullmatch(code) is None:
        raise ModError('Informe os oito dígitos do password original.')
    ids = sorted(cid for cid, record in records.items() if record.code == code)
    if not ids:
        raise ModError('Código original ausente da tabela importada.')
    return ids


def chest_cards(project):
    return project.metadata.get(CHEST_KEY, {})


def grant_card(project, cid, *, starter=None):
    """Salva uma cópia no baú e, quando solicitado, inclui no deck inicial."""
    cid = positive_int(cid, 'ID da carta')
    if cid not in project.cards:
        raise ModError(f'Carta #{cid} indisponível neste projeto.')
    key = str(cid)
    before = project.metadata
    chest = dict(chest_cards(project))
    chest[key] = int(chest.get(key, 0)) + 1
    metadata = {**before, CHEST_KEY: chest}
    if starter is not None:
        if not starter.strip():
            raise ModError('Informe o nome do deck inicial.')
        cards = {cid: project.get(cid) for cid in project.cards}
        rules = normalize_rules(before.get(CONFIG_KEY, {}), cards)
        profile = rules.setdefault('iniciais', {}).setdefault(starter, {'peso': 1, 'cartas': [], 'pools': []})
        profile['cartas'].append(cid)
        deal_deck(profile, cards, project.effects, default_copies=int(before.get('ps1_deck_global_limit', 3)))
        metadata[CONFIG_KEY] = rules
    project.metadata = metadata
    try:
        project.save()
    except Exception:
        project.metadata = before
        raise
    return chest[key]


def choose_ps1_prefix(codes):
    used = {int(code[:5]) for code in codes if ORIGINAL_CODE.fullmatch(code)}
    return next(prefix for prefix in range(CARD_COUNT + 1) if prefix not in used)


def ps1_id_code(prefix, cid):
    return f'{prefix:05d}{cid:03d}'


def set_ps1_id_passwords(project, enabled):
    metadata = dict(project.metadata)
    if enabled:
        if not ps1_supports_god24(project):
            raise ModError('Passwords por ID no BIN/CUE exigem o perfil Drop x15 vinculado.')
        path = project.folder / 'base' / 'senhas.csv'
        if not path.is_file():
            raise ModError('Leia os códigos do BIN/CUE de origem antes de ativar.')
        rows = _read_csv(path)
        if {row.get('carta_id') for row in rows} != {str(cid) for cid in range(1, CARD_COUNT + 1)}:
            raise ModError('Leia a tabela completa de passwords do BIN/CUE de origem.')
        metadata[PS1_ID_PREFIX] = choose_ps1_prefix(row.get('password') or '' for row in rows)
    else:
        metadata.pop(PS1_ID_PREFIX, None)
    previous = project.metadata
    project.metadata = metadata
    try:
        project.save()
    except Exception:
        project.metadata = previous
        raise


def validate_ps1_prefix(wa, prefix):
    rows = decode_passwords(wa)
    if any(row['custo_starchips'] == 0xFFFFFFFF for row in rows):
        raise ModError('A tabela de passwords do BIN termina antes do ID 722.')
    if any(row['password'].startswith(f'{prefix:05d}') for row in rows):
        raise ModError('O prefixo de ID coincide com um password original do BIN. Releia os códigos de origem.')
