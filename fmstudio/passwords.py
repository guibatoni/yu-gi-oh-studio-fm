"""Passwords clássicos importados e códigos reversíveis das cartas do Studio."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from .core import ModError, _read_csv, _write_csv, positive_int
from .tables import CARD_COUNT, decode_passwords

ORIGINAL_CODE = re.compile(r'[0-9]{8}')
STUDIO_CODE = re.compile(r'FM-([0-9]+)', re.ASCII | re.IGNORECASE)


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
        if 1 <= cid <= CARD_COUNT and cid in project.cards:
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
        raise ModError('Informe um código por ID, como FM-00000723.')
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
