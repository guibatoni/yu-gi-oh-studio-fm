"""Install and inspect the live rank in the verified Drop x15 duel HUD."""
from __future__ import annotations

import hashlib
import struct

from .core import ModError
from .ps1_god24_chest import SOURCE_SHA256
from .ps1_runtime_blob import (
    ENTRY_POINTS, RUNTIME_MOD_BASE, RUNTIME_RANK_HUD, RUNTIME_RANK_HUD_BASE,
    RUNTIME_RANK_HUD_END, RUNTIME_RANK_HUD_SHA256,
)
from .tables import EXE_DELTA

CALL_PC = 0x80016FE4
CONTEXT_PC = 0x80016FC0
# End of Duel_DrawLifePointsAndDeckCounts, including the arguments of the
# player's deck count, its delay slot and the first instruction of the epilogue.
RETAIL_WORDS = (
    0x34A50320, 0x94820030, 0x24070002, 0x2442000E, 0xA6220004, 0x82460018,
    0x94820032, 0x02863023, 0x24420005, 0x0C005B4B, 0xA6220006, 0x8FBF0024,
)
CALL_INDEX = (CALL_PC - CONTEXT_PC) // 4
# O HUD de LP com 5 dígitos (ps1_lp_hud) centraliza o contador do deck:
# origem +14 -> +7 nesta mesma janela. O rank continua compatível.
DECK_X_INDEX = 3
DECK_X_SMALL = 0x24420007
RANK_CALL = 0x0C000000 | ((ENTRY_POINTS['DrawLiveRank'] >> 2) & 0x03FFFFFF)
RANK_WORDS = RETAIL_WORDS[:CALL_INDEX] + (RANK_CALL,) + RETAIL_WORDS[CALL_INDEX + 1:]
CODE_START = RUNTIME_RANK_HUD_BASE - EXE_DELTA
CODE_END = RUNTIME_RANK_HUD_END - EXE_DELTA


def _context(exe):
    offset = CONTEXT_PC - EXE_DELTA
    if len(exe) < offset + 48:
        return ()
    words = list(struct.unpack_from('<12I', exe, offset))
    if words[DECK_X_INDEX] == DECK_X_SMALL:
        words[DECK_X_INDEX] = RETAIL_WORDS[DECK_X_INDEX]
    return tuple(words)


def inspect_rank_hud(exe: bytes) -> dict:
    words = _context(exe)
    if words == RANK_WORDS and exe[CODE_START:CODE_END] == RUNTIME_RANK_HUD:
        status = 'aplicado'
    elif words and words[CALL_INDEX] == RANK_CALL:
        status = 'divergente'
    elif words == RETAIL_WORDS:
        status = 'ausente'
    else:
        status = 'perfil_incompativel'
    return {'status': status, 'endereco': f'0x{CALL_PC:08X}'}


def patch_rank_hud(original: bytes, modified: bytes, *, occupied_until: int = 0) -> tuple[bytes, dict]:
    if (hashlib.sha256(original).hexdigest() != SOURCE_SHA256 or _context(original) != RETAIL_WORDS
            or len(original) != len(modified)):
        return modified, {'status': 'perfil_incompativel'}
    if (not RUNTIME_RANK_HUD or CODE_END > len(original)
            or not RUNTIME_RANK_HUD_BASE <= ENTRY_POINTS['DrawLiveRank'] < RUNTIME_RANK_HUD_END
            or RUNTIME_RANK_HUD_END > RUNTIME_MOD_BASE or CODE_END - CODE_START != len(RUNTIME_RANK_HUD)
            or hashlib.sha256(RUNTIME_RANK_HUD).hexdigest() != RUNTIME_RANK_HUD_SHA256):
        raise ModError('Rank no HUD: extensão MIPS inválida.')
    current = inspect_rank_hud(modified)
    if current['status'] == 'aplicado':
        return modified, current
    if any(original[CODE_START:CODE_END]) or _context(modified) != RETAIL_WORDS:
        return modified, {'status': 'conflito'}
    if occupied_until > RUNTIME_RANK_HUD_BASE or any(modified[CODE_START:CODE_END]):
        return modified, {'status': 'sem_espaco'}

    out = bytearray(modified)
    out[CODE_START:CODE_END] = RUNTIME_RANK_HUD  # só CALL_PC muda na janela de contexto
    struct.pack_into('<I', out, CALL_PC - EXE_DELTA, RANK_CALL)
    report = inspect_rank_hud(out)
    if report['status'] != 'aplicado':
        raise ModError('Rank no HUD: verificação final do SLUS falhou.')
    return bytes(out), report
