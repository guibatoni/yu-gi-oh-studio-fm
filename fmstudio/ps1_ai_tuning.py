"""IA dos oponentes no PS1: mais fusões e mais agressividade (só dados).

A IA do FM é um script fixo (bytecode no WA_MRG) que lê, para cada oponente,
uma linha de 9 bytes em ``gDuel_aOpponentData`` (SLUS, 0x800917F0; linhas
0-39, a 0 não é usada). Pesquisa do decomp (notes/ai-hard-mode-research.md):

=====  ==========================================================
byte   uso no jogo original
=====  ==========================================================
0      janela de cartas que a IA enxerga (mão + próximas do deck), 5-20;
       ela troca as cartas escolhidas do deck para a mão
1      limiar de LP x100 (abaixo dele usa a estratégia B)
2      cartas restantes no deck abaixo das quais reduz a busca de fusão
3      profundidade da estratégia A (melhor monstro/fusão), 1-3
4      profundidade da estratégia B (melhorar o monstro mais fraco), 1-3
5, 6   não lidos pelo jogo
7      % de uso do Harpie's Feather Duster / segurar dano-cura
8      % de ataque contra cartas viradas para baixo
=====  ==========================================================

Profundidade 1 não monta fusão só com cartas da mão (precisa de 3 para isso);
3 é o máximo usado pelos chefes do jogo, então é seguro para o executor de
fusões (buffers de 6 bytes). Nada aqui muda código nem o bytecode.
"""
from __future__ import annotations

import struct

from .core import ModError
from .tables import EXE_DELTA

TABLE = 0x800917F0
ROW = 9
OPPONENTS = range(1, 40)
SETTINGS_KEY = 'ps1_ia_oponentes'
MODES = {
    'original': 'Original do jogo',
    'agressiva': 'Agressiva: mais fusões e ataques',
    'maxima': 'Máxima: vê 20 cartas, funde sempre e ataca muito',
}


def settings(project) -> dict:
    raw = (getattr(project, 'metadata', None) or {}).get(SETTINGS_KEY) or {}
    mode = raw.get('modo') if raw.get('modo') in MODES else 'original'
    return {'modo': mode}


def save_settings(project, mode: str) -> dict:
    if mode not in MODES:
        raise ModError('IA dos oponentes: modo inválido.')
    before = project.metadata
    project.metadata = {**before, SETTINGS_KEY: {'modo': mode}}
    try:
        project.save()
    except OSError:
        project.metadata = before
        raise
    return {'modo': mode}


def _rows(exe: bytes) -> dict[int, bytearray]:
    start = TABLE - EXE_DELTA
    if start < 0 or start + ROW * 40 > len(exe):
        raise ModError('IA dos oponentes: tabela fora do SLUS.')
    return {opp: bytearray(exe[start + ROW * opp:start + ROW * (opp + 1)]) for opp in OPPONENTS}


def looks_like_table(exe: bytes) -> bool:
    """Confere faixas de todos os 39 oponentes (sem exigir os valores exatos do retail)."""
    try:
        rows = _rows(exe)
    except ModError:
        return False
    return all(5 <= r[0] <= 20 and 1 <= r[1] <= 99 and 1 <= r[3] <= 3 and 1 <= r[4] <= 3
               and r[7] <= 100 and r[8] <= 100 for r in rows.values())


def tuned_row(row: bytes, mode: str) -> bytes:
    r = bytearray(row)
    if mode == 'original':
        return bytes(r)
    r[3] = r[4] = 3                              # busca de fusão completa (inclusive só da mão)
    r[2] = min(r[2], 5)                          # continua fundindo até o fim do deck
    r[1] = min(r[1], 10)                         # só muda para a estratégia B abaixo de 1000 LP
    if mode == 'agressiva':
        r[0] = min(20, max(r[0], 10))            # pelo menos 10 cartas para montar fusões
        r[8] = max(r[8], 50)                     # ataca carta virada com mais frequência
        r[7] = max(r[7], 50)
    else:
        r[0] = 20
        r[8] = max(r[8], 75)
        r[7] = max(r[7], 75)
    return bytes(r)


def apply(exe: bytes, mode: str) -> tuple[bytes, dict]:
    if mode not in MODES:
        raise ModError('IA dos oponentes: modo inválido.')
    if mode == 'original':
        return exe, {'status': 'original'}
    if not looks_like_table(exe):
        raise ModError('IA dos oponentes: a tabela de parâmetros deste SLUS não é a esperada; '
                       'a IA foi mantida como está.')
    out = bytearray(exe)
    start = TABLE - EXE_DELTA
    changed = 0
    for opp, row in _rows(exe).items():
        new = tuned_row(row, mode)
        changed += new != bytes(row)
        out[start + ROW * opp:start + ROW * (opp + 1)] = new
    return bytes(out), {'status': 'aplicado', 'modo': mode, 'oponentes_alterados': changed,
                        'endereco': f'0x{TABLE:08X}', 'validado_epsxe': False}
