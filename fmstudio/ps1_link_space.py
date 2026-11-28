"""Espaço extra para o mod: os buffers de deck do Link Duel (duelo por cabo).

No início de um duelo o jogo aponta os decks em ``gp+0x2D0``/``gp+0x2D4``:
para os duelistas normais usa 0x801D0200; só quando o oponente é -1 (Link
Duel, iniciado em 0x8002DD3C depois de conectar o cabo) usa dois buffers de
4 KiB em 0x801D1200 e 0x801D2200. Fora isso nada escreve em
0x801D1200..0x801D3000 (conferido no SLUS — só o próprio Link Duel e o menu de
debug apontam para lá — e em savestates do ePSXe no menu, no mapa e em duelo:
a área fica sempre zerada; o buffer de save começa em 0x801D3000).

``claim`` desliga o Link Duel: depois de conectar, o jogo volta ao menu em vez
de iniciar o duelo (o ``bne`` que escolhe o duelo vira ``b`` para a saída de
falha). A área passa a guardar as regras de efeitos que não cabem no banco
original (``EffectPlan.far``) e rotinas do mod.
"""
from __future__ import annotations

import struct

from .deep_extract import exe_pos

LINK_START = 0x801D1200
LINK_END = 0x801D3000
LINK_SITE = 0x8002DD2C               # bne s0, v0, falha (conexão ok → Link Duel)
LINK_ORIGINAL = 0x1602000A
LINK_DISABLED = 0x1000000A           # b falha


def _word(exe: bytes) -> int:
    return struct.unpack_from('<I', exe, exe_pos(LINK_SITE, exe, 4))[0]


def status(exe: bytes) -> str:
    """'original', 'liberado' ou 'divergente'."""
    try:
        word = _word(exe)
    except Exception:
        return 'divergente'
    if word == LINK_DISABLED:
        return 'liberado'
    if word != LINK_ORIGINAL:
        return 'divergente'
    at = exe_pos(LINK_START, exe, LINK_END - LINK_START)
    return 'divergente' if any(exe[at:at + LINK_END - LINK_START]) else 'original'


def claim(exe: bytes) -> tuple[bytes, dict]:
    """Desliga o Link Duel e libera a área (não mexe no que já estiver nela)."""
    state = status(exe)
    if state == 'divergente':
        return exe, {'status': 'indisponivel', 'motivo': 'área do Link Duel diferente do Drop x15'}
    out = bytearray(exe)
    struct.pack_into('<I', out, exe_pos(LINK_SITE, exe, 4), LINK_DISABLED)
    return bytes(out), {'status': 'liberado', 'inicio': f'0x{LINK_START:08X}',
                        'fim': f'0x{LINK_END:08X}', 'bytes': LINK_END - LINK_START,
                        'link_duel': 'desativado (volta ao menu)'}
