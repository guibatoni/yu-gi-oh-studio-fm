"""Mostrar 20.000 LP no HUD do PS1: cinco algarismos nos dois lados.

O SLUS retail chama func_80016D2C com largura 4 para os LP do rival
e do jogador, e com largura 2 para os contadores do deck. Esta mudança
insere a quinta coluna deslocando os LP oito pixels à esquerda, sem
alterar contadores do deck, valores de LP nem a animação de dano.

A visualização da borda original de 64 pixels ainda requer validação
in-game no ePSXe; o patch não redesenha nem amplia o fundo do painel.

Somente SLUS_014.11 original do Drop x15 verificado por SHA-256,
e cada opcode original precisa corresponder exatamente. Reaplicável.
"""
from __future__ import annotations

import hashlib
import struct

from .core import ModError
from .ps1_god24_chest import SOURCE_SHA256
from .tables import EXE_DELTA

# Cada dupla muda a largura 4 -> 5 e a origem -3 -> -11, mantendo a
# última coluna na posição retail. JAL e delay slots permanecem iguais.
# 0x80016F14/18: oponente; 0x80016F98/9C: jogador.
LP_HUD_PATCHES = (
    (0x80016F14, 0x24070004, 0x24070005, 'LP do oponente: cinco dígitos'),
    (0x80016F18, 0x2442FFFD, 0x2442FFF5, 'LP do oponente: alinhar cinco dígitos'),
    (0x80016F98, 0x24070004, 0x24070005, 'LP do jogador: cinco dígitos'),
    (0x80016F9C, 0x2442FFFD, 0x2442FFF5, 'LP do jogador: alinhar cinco dígitos'),
)

# Verificar que os contadores de cartas, deliberadamente com dois dígitos,
# não foram modificados.
DECK_COUNT_WORDS = (
    (0x80016F40, 0x24070002),
    (0x80016FC8, 0x24070002),
)


def _word(data: bytes, pc: int) -> int:
    offset = pc - EXE_DELTA
    if offset < 0 or offset + 4 > len(data):
        raise ModError(f'Contador de LP: endereço fora do SLUS em 0x{pc:08X}.')
    return struct.unpack_from('<I', data, offset)[0]


def _verified_layout(original: bytes, modified: bytes) -> bool:
    return (len(original) == len(modified) and
            hashlib.sha256(original).hexdigest() == SOURCE_SHA256 and
            all(_word(original, pc) == retail for pc, retail, _, _ in LP_HUD_PATCHES) and
            all(_word(original, pc) == retail for pc, retail in DECK_COUNT_WORDS))


def patch_lp_hud(original: bytes, modified: bytes, *, initial_lp: int) -> tuple[bytes, dict]:
    """Aplicar contador de 5 dígitos se os LP globais ultrapassarem 9.999.

    O patch da inicialização de LP deve continuar sendo aplicado separadamente.
    Não modifica o BIN original nem sobrescreve instruções desconhecidas.
    """
    if type(initial_lp) is not int or initial_lp < 0:
        raise ModError('Contador de LP: valor inicial inválido.')
    if initial_lp <= 9999:
        return modified, {'status': 'original', 'digitos': 4,
                          'lp_inicial': initial_lp, 'validado_epsxe': False}
    if not _verified_layout(original, modified):
        raise ModError('Contador de LP com cinco dígitos exige o SLUS original Drop x15 validado.')
    for pc, retail, wide, _ in LP_HUD_PATCHES:
        if _word(modified, pc) not in (retail, wide):
            raise ModError(f'Contador LP: conflito MIPS em 0x{pc:08X}.')
    for pc, retail in DECK_COUNT_WORDS:
        if _word(modified, pc) != retail:
            raise ModError(f'Contador LP: contador do deck alterado em 0x{pc:08X}.')

    out = bytearray(modified)
    for pc, _, wide, _ in LP_HUD_PATCHES:
        struct.pack_into('<I', out, pc - EXE_DELTA, wide)
    if not verify_lp_hud(original, bytes(out), initial_lp=initial_lp):
        raise ModError('Contador LP: verificação final de cinco dígitos falhou.')
    return bytes(out), {
        'status': 'aplicado', 'digitos': 5, 'lp_inicial': initial_lp,
        'jogador': True, 'adversario': True,
        'enderecos': [f'0x{pc:08X}' for pc, *_ in LP_HUD_PATCHES],
        'deck_preservado': True, 'validado_epsxe': False,
        'aviso': ('A fonte original mostra 5 dígitos mas o fundo original do painel '
                  'tem 64 pixels; alinhar visualmente no ePSXe. '
                  'LP acima de 32767 ainda exige avaliação do contador assinado.'
                  if initial_lp > 32767 else
                  'A exibição dos cinco dígitos deve ser conferida visualmente no ePSXe.'),
    }


def verify_lp_hud(original: bytes, modified: bytes, *, initial_lp: int) -> bool:
    if initial_lp <= 9999:
        return True  # nenhum patch do HUD foi solicitado; outros patches são permitidos
    try:
        return (_verified_layout(original, modified) and
                all(_word(modified, pc) == wide for pc, _, wide, _ in LP_HUD_PATCHES) and
                all(_word(modified, pc) == retail for pc, retail in DECK_COUNT_WORDS))
    except (ModError, struct.error):
        return False
