"""Cartas recebidas por vitória no Drop x15: 1, 3, 5 (padrão do mod), 15 ou 30.

O Drop x15 sorteia as cartas no próprio código residente (0x801AAC40..0x801AAEE0):

* ``0x801AAC78`` laço do sorteio, ``li s7, N+1``;
* ``0x801AAD74`` laço da entrega (``Duel_AwardCard``), ``li s7, N+1``;
* ``0x801AADEC`` rodízio do nome exibido no resultado, ``li s7, N``;
* a lista sorteada fica em ``base + 0x20 + 2*k`` (k = 1..N), com
  ``base = 0x801AAC00``. Cabem 15 cartas antes do código do mod; para 30 a
  base passa a ``0x801AABE0`` (``addiu`` em ``0x801AAC44``, ``0x801AAD50`` e
  ``0x801AADD0``). Essa área faz parte do buffer de script de IA do campo,
  que é recarregado a cada duelo; o sorteio acontece depois do combate.

O código do mod existe no SLUS e nos registros do WA_MRG que o recarregam;
todas as cópias reconhecidas (SHA-256 canônico) são alteradas da mesma forma.
"""
from __future__ import annotations

import struct

from .core import ModError

CHOICES = (1, 3, 5, 15, 30)
MOD_DEFAULT = 5
SETTINGS_KEY = 'ps1_cartas_por_vitoria'
SCRATCH_LIMIT = 15  # entradas que cabem em 0x801AAC20..0x801AAC3F

# (deslocamento a partir de 0x801AAC40, palavra original)
LIMIT_DRAW = (0x038, 0x24170006)
LIMIT_AWARD = (0x134, 0x24170006)
LIMIT_SHOW = (0x1AC, 0x24170005)
BASE_DRAW = (0x004, 0x27BDAC00)
BASE_AWARD = (0x110, 0x2484AC00)
BASE_SHOW = (0x190, 0x2442AC00)
SITES = (LIMIT_DRAW, LIMIT_AWARD, LIMIT_SHOW, BASE_DRAW, BASE_AWARD, BASE_SHOW)
WIDE_BASE = 0xABE0  # 0x801AABE0 (0x801B0000 - 0x5420)


def words_for(count: int) -> dict[int, int]:
    if count not in CHOICES:
        raise ModError(f'Cartas por vitória: escolha {", ".join(map(str, CHOICES))}.')
    words = {LIMIT_DRAW[0]: 0x24170000 | (count + 1), LIMIT_AWARD[0]: 0x24170000 | (count + 1),
             LIMIT_SHOW[0]: 0x24170000 | count}
    for offset, original in (BASE_DRAW, BASE_AWARD, BASE_SHOW):
        words[offset] = (original & 0xFFFF0000) | (WIDE_BASE if count > SCRATCH_LIMIT else original & 0xFFFF)
    return words


def _read(code: bytes, offset: int) -> int:
    return struct.unpack_from('<I', code, offset)[0]


def count_of(code: bytes) -> int | None:
    """Quantidade gravada numa cópia do código do mod (None se não reconhecida)."""
    for count in CHOICES:
        if all(_read(code, offset) == word for offset, word in words_for(count).items()):
            return count
    return None


def canonical(code: bytes) -> bytes:
    """Restaura as 6 instruções configuráveis para comparar o código com o perfil."""
    if count_of(code) is None:
        return code
    result = bytearray(code)
    for offset, original in SITES:
        struct.pack_into('<I', result, offset, original)
    return bytes(result)


def _matches(code: bytes) -> bool:
    import hashlib
    from .ps1_campaign_quests import DROP15_CODE_SHA256
    return hashlib.sha256(canonical(code)).hexdigest() == DROP15_CODE_SHA256


def find_copies(blob: bytes) -> list[int]:
    """Posições de todas as cópias do código do Drop x15 num arquivo."""
    from .ps1_campaign_quests import DROP15_CODE, DROP15_END
    size = DROP15_END - DROP15_CODE
    anchor_start = BASE_DRAW[0] + 4
    found, at = [], 0
    while True:
        at = blob.find(_ANCHOR, at)
        if at < 0:
            return found
        start = at - anchor_start
        if start >= 0 and start + size <= len(blob) and _matches(blob[start:start + size]):
            found.append(start)
        at += 1


def patch_copies(blob: bytes, count: int, *, required: bool) -> tuple[bytes, list[int]]:
    positions = find_copies(blob)
    if required and not positions:
        raise ModError('O código de drops do Drop x15 não foi encontrado; '
                       'cartas por vitória exigem o SLUS Drop x15 original.')
    words = words_for(count)
    result = bytearray(blob)
    for start in positions:
        for offset, word in words.items():
            struct.pack_into('<I', result, start + offset, word)
    return bytes(result), positions


def cards_per_win(project) -> int | None:
    value = (getattr(project, 'metadata', None) or {}).get(SETTINGS_KEY)
    if value is None:
        return None
    if isinstance(value, bool) or value not in CHOICES:
        raise ModError('Configuração de cartas por vitória inválida no projeto.')
    return value


def set_cards_per_win(project, count: int | None):
    if count is not None:
        words_for(count)
    before = project.metadata
    project.metadata = {**before, SETTINGS_KEY: count}
    try:
        project.save()
    except OSError:
        project.metadata = before
        raise


def apply(exe: bytes, wa: bytes | None, count: int) -> tuple[bytes, bytes | None, dict]:
    """Aplica a quantidade no SLUS (cópia obrigatória) e em toda cópia no WA_MRG."""
    exe, exe_hits = patch_copies(exe, count, required=True)
    wa_hits = []
    if wa is not None:
        wa, wa_hits = patch_copies(wa, count, required=False)
    return exe, wa, {'status': 'aplicado', 'cartas': count, 'copias_slus': len(exe_hits),
                     'copias_wa': len(wa_hits), 'base_lista': '0x801AABE0' if count > SCRATCH_LIMIT
                     else '0x801AAC00', 'validado_epsxe': False}


def status(exe: bytes) -> dict:
    positions = find_copies(exe)
    if not positions:
        return {'status': 'ausente'}
    from .ps1_campaign_quests import DROP15_CODE, DROP15_END
    counts = {count_of(exe[p:p + DROP15_END - DROP15_CODE]) for p in positions}
    return {'status': 'aplicado' if counts != {MOD_DEFAULT} else 'original_do_mod',
            'cartas': counts.pop() if len(counts) == 1 else None}


# Bytes estáveis logo após a primeira instrução configurável (0x801AAC48..0x801AAC78).
_ANCHOR = bytes.fromhex('0000a2af0400a3af0800b0af0c00a4af1000a5af1400bfaf1800b6af1c00b7af2000a0a32000b693000000000100d626')
