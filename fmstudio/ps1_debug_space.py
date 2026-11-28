"""Espaço extra para código do mod: o menu de debug do SLUS (inacessível no jogo).

O SLUS do Drop x15 traz o menu de debug dos desenvolvedores (som, campanha,
filmes, carregar/salvar…). Ele só roda no modo 0 da tabela de modos
(``gMain_apfnModeRunner`` 0x80090B64), que o jogo só escolhe para uma opção
de menu que não existe na tela inicial. As funções de 0x80030090 a 0x800313E8
são chamadas apenas entre si e pela tabela de entradas do próprio menu
(conferido no SLUS: nenhum ``jal``, ponteiro ou ``lui/addiu`` de fora;
``func_800313E8`` logo depois é usada pelo ícone de tipo e fica intacta).

``claim`` troca o modo 0 por ``Main_RunMenu`` (se algo pedir o debug, o jogo
volta ao menu principal em vez de executar a área reaproveitada) e zera a
área, que passa a ser usada só por rotinas do mod (nunca por textos: as
descrições usam ponteiros de 16 bits relativos ao banco 0x801C0000).
"""
from __future__ import annotations

import hashlib
import struct

from .deep_extract import exe_pos

DEBUG_START = 0x80030090
DEBUG_END = 0x800313E8                 # func_800313E8 (ícone de tipo) começa aqui
DEBUG_SHA256 = '20559944ee644450cce8a531b02b74bb37b07361850330464be6020836c20e97'
MODE_TABLE = 0x80090B64                # gMain_apfnModeRunner[0]
RUN_DEBUG_MENU = 0x8002CE08
RUN_MENU = 0x8002D588                  # gMain_apfnModeRunner[8]


# Link Duel e troca por cabo (opções do menu inicial): os modos 14, 15 e 16 da tabela
# de modos rodam só essas telas. A tela volta ao menu (como o modo de debug) e as três
# funções (0x8002D7CC..0x8002DD74, chamadas só pela tabela) viram espaço do mod.
LINK_START = 0x8002D7CC
LINK_END = 0x8002DD74
LINK_SHA256 = '77c092296f4ade44f4387bc3854aff2d35aa211be0894c075b1dcfc9b07c23f1'
LINK_MODES = (14, 15, 16)
LINK_RUNNERS = (0x8002D7CC, 0x8002DA1C, 0x8002DC38)


def _link_state(exe: bytes) -> str:
    try:
        entries = [struct.unpack_from('<I', exe, exe_pos(MODE_TABLE + 4 * m, exe, 4))[0]
                   for m in LINK_MODES]
        at = exe_pos(LINK_START, exe, LINK_END - LINK_START)
        region = exe[at:at + LINK_END - LINK_START]
    except Exception:
        return 'divergente'
    if tuple(entries) == LINK_RUNNERS and hashlib.sha256(region).hexdigest() == LINK_SHA256:
        return 'original'
    if all(e == RUN_MENU for e in entries):
        return 'liberado'
    return 'divergente'


def _region(exe: bytes) -> bytes:
    at = exe_pos(DEBUG_START, exe, DEBUG_END - DEBUG_START)
    return exe[at:at + DEBUG_END - DEBUG_START]


def _mode0(exe: bytes) -> int:
    return struct.unpack_from('<I', exe, exe_pos(MODE_TABLE, exe, 4))[0]


def status(exe: bytes) -> str:
    """'original', 'liberado' ou 'divergente'."""
    try:
        mode0 = _mode0(exe)
        region = _region(exe)
    except Exception:
        return 'divergente'
    if mode0 == RUN_DEBUG_MENU and hashlib.sha256(region).hexdigest() == DEBUG_SHA256:
        return 'original'
    if mode0 == RUN_MENU:
        return 'liberado'
    return 'divergente'


def claim(exe: bytes) -> tuple[bytes, list[tuple[int, int]], dict]:
    """Libera o menu de debug e as telas de link; devolve (SLUS, regiões livres, relatório)."""
    state = status(exe)
    if state == 'divergente':
        return exe, [], {'status': 'indisponivel', 'motivo': 'menu de debug diferente do Drop x15'}
    out = bytearray(exe)
    if state == 'original':
        at = exe_pos(DEBUG_START, exe, DEBUG_END - DEBUG_START)
        out[at:at + DEBUG_END - DEBUG_START] = bytes(DEBUG_END - DEBUG_START)
        struct.pack_into('<I', out, exe_pos(MODE_TABLE, exe, 4), RUN_MENU)
    regions = [(DEBUG_START, DEBUG_END)]
    report = {'status': 'liberado', 'inicio': f'0x{DEBUG_START:08X}', 'fim': f'0x{DEBUG_END:08X}',
              'bytes': DEBUG_END - DEBUG_START, 'modo_debug': 'volta ao menu principal'}
    link = _link_state(exe)
    if link != 'divergente':
        if link == 'original':
            at = exe_pos(LINK_START, exe, LINK_END - LINK_START)
            out[at:at + LINK_END - LINK_START] = bytes(LINK_END - LINK_START)
            for mode in LINK_MODES:
                struct.pack_into('<I', out, exe_pos(MODE_TABLE + 4 * mode, exe, 4), RUN_MENU)
        regions.append((LINK_START, LINK_END))
        report.update(link_duel='desativado (volta ao menu)', bytes_link=LINK_END - LINK_START,
                      bytes=report['bytes'] + LINK_END - LINK_START)
    return bytes(out), regions, report
