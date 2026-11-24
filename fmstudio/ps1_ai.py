"""IA avançada real no executável PlayStation 1 Drop x15 verificado.

O retail usa portas aleatórias para decidir se sequer procura equipamentos,
traps, magias, fusões e um caminho adicional de Equip. No modo Difícil,
essas portas são removidas: as rotinas originais continuam decidindo se a
jogada existe e é permitida. O patch não vê a mão do jogador, não altera LP
ou ATK e não muda regras nem RNG global.

Todos os offsets e opcodes são conferidos ANTES de modificar o executável.
Fonte: SLUS_014.11 SHA-256 conhecida; ai_turn_action.c da decompilação
Yu-Gi-Oh-Forbidden-Memories-Recompiled (rotinas 0x80027228, 0x80027508,
0x800279BC). Nenhum outro dump/mod é aceito automaticamente.
"""
from __future__ import annotations

import hashlib
import struct

from .core import ModError
from .ps1_god24_chest import SOURCE_SHA256
from .tables import EXE_DELTA

AI_MODES = ('normal', 'dificil', 'agressiva', 'maxima')
# Modos acima de 'dificil' usam as mesmas cinco instruções e ainda ajustam a
# tabela de parâmetros por oponente (ps1_ai_tuning).
HARD_MODES = ('dificil', 'agressiva', 'maxima')

# (PC, instrução retail, instrução avançada, explicação)
# Substituímos APENAS os branches que pulam uma tentativa por sorteio.
# Nenhuma instrução de delay slot, chamada ou condição de legalidade muda.
HARD_AI_PATCHES = (
    (0x8002727C, 0x10400099, 0x00000000, 'Verificar possibilidade de fusão em todos os turnos'),
    (0x80027524, 0x14400005, 0x00000000, 'Sempre procurar equipamento legal'),
    (0x80027548, 0x14400005, 0x00000000, 'Sempre procurar armadilha aplicável'),
    (0x8002756C, 0x14400005, 0x00000000, 'Sempre procurar magia aplicável'),
    (0x800279F4, 0x14400069, 0x00000000, 'Sempre avaliar alvo de Equip na fase de ação'),
)


def mode_for(project):
    raw = (getattr(project, 'metadata', {}).get('edicao_mod') or {}).get('ia_ps1', 'normal')
    if raw not in AI_MODES:
        raise ModError('IA do PS1: escolha Normal, Difícil, Agressiva ou Máxima em Config. MOD.')
    return raw


def patch_hard_ai(original: bytes, modified: bytes, *, mode: str) -> tuple[bytes, dict]:
    if mode not in AI_MODES:
        raise ModError('Modo de IA do PS1 inválido.')
    if mode == 'normal':
        return modified, {'modo': 'normal', 'status': 'original', 'rotinas': [],
                          'validado_epsxe': False}
    if (len(original) != len(modified) or
            hashlib.sha256(original).hexdigest() != SOURCE_SHA256):
        raise ModError('IA Difícil/Agressiva/Máxima exige a imagem Drop x15 com SLUS_014.11 validado.')
    changes = []
    # Verifique tudo antes de qualquer mutação. O BIN original é imutável.
    for pc, expected, patched, caption in HARD_AI_PATCHES:
        offset = pc - EXE_DELTA
        if offset < 0 or offset + 4 > len(modified):
            raise ModError(f'IA PS1: instrução fora do executável em 0x{pc:08X}.')
        old, current = struct.unpack_from('<I', original, offset)[0], struct.unpack_from('<I', modified, offset)[0]
        if old != expected or current not in (expected, patched):
            raise ModError(f'IA PS1: opcode inesperado em 0x{pc:08X}; patch recusado.')
        changes.append({'endereco': f'0x{pc:08X}', 'descricao': caption})
    out = bytearray(modified)
    for pc, _, value, _ in HARD_AI_PATCHES:
        struct.pack_into('<I', out, pc - EXE_DELTA, value)
    report = {}
    if mode in ('agressiva', 'maxima'):
        from .ps1_ai_tuning import apply as tune
        tuned, report = tune(bytes(out), mode)
        out = bytearray(tuned)
    if not verify_hard_ai(original, out, mode=mode):
        raise ModError('IA PS1: divergência na verificação das cinco instruções.')
    return bytes(out), {'modo': mode, 'status': 'aplicado',
                        'rotinas': changes, 'parametros_oponentes': report, 'validado_epsxe': False}


def verify_hard_ai(original: bytes, modified: bytes, *, mode: str) -> bool:
    if mode not in AI_MODES or len(original) != len(modified):
        return False
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA256:
        return False
    expected_mode = (0x00000000 if mode in HARD_MODES else None)
    for pc, stock, hard, _ in HARD_AI_PATCHES:
        offset = pc - EXE_DELTA
        if struct.unpack_from('<I', original, offset)[0] != stock:
            return False
        observed, = struct.unpack_from('<I', modified, offset)
        if observed != (hard if expected_mode is not None else stock):
            return False
    return True
