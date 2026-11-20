"""Mostrar 20.000 LP no HUD do PS1: cinco algarismos nos dois lados.

O SLUS retail chama func_80016D2C com largura 4 para os LP do rival e do
jogador, e com largura 2 para os contadores do deck ("calculadora"). Cada
algarismo é um sprite 8x8 desenhado com GsSortFastSprite, avançando 8 px.

Com LP acima de 9.999 este patch:

* reescreve func_80016D2C (mesmos 44 words, mesma assinatura) para desenhar
  cada algarismo com GsSortSprite, reduzido para ~6x7 px (escala 0,8 x 0,875),
  avançando 6 px. Os 5 dígitos ocupam 30 px, dentro dos 32 px que os 4
  dígitos originais usavam: cabem no quadro do LP sem invadir o rótulo;
* chama essa função com largura 5 e origem -2 (era -3) nos dois lados;
* desenha o contador do deck com os mesmos dígitos menores, centralizado
  sob/sobre os dígitos de LP (origem +7 em vez de +14).

O bit 27 do atributo (0x08000000, "sem escala/rotação" na libgs) é limpo só
no sprite de rascunho desta função; os demais campos são os do jogo.
Só funciona no SLUS_014.11 do Drop x15 conferido por SHA-256, e cada palavra
original precisa corresponder exatamente. Reaplicável. Visual a conferir no
ePSXe (validado_epsxe=False).
"""
from __future__ import annotations

import hashlib
import struct

from .core import ModError
from .ps1_god24_chest import SOURCE_SHA256
from .mips_asm import Asm, hi_lo
from .tables import EXE_DELTA

# Cada dupla muda a largura 4 -> 5 e a origem -3 -> -2 (dígitos de 6 px:
# 5 x 6 = 30 px dentro dos 32 px originais). JAL e delay slots iguais.
# 0x80016F14/18: oponente; 0x80016F98/9C: jogador.
LP_HUD_PATCHES = (
    (0x80016F14, 0x24070004, 0x24070005, 'LP do oponente: cinco dígitos'),
    (0x80016F18, 0x2442FFFD, 0x2442FFFE, 'LP do oponente: alinhar cinco dígitos'),
    (0x80016F98, 0x24070004, 0x24070005, 'LP do jogador: cinco dígitos'),
    (0x80016F9C, 0x2442FFFD, 0x2442FFFE, 'LP do jogador: alinhar cinco dígitos'),
)
# Versão anterior (1.7.9..1.9.x): dígitos de 8 px com origem -11. Aceita
# como ponto de partida para reaplicar sobre um BIN já gerado.
LEGACY_LP_WORDS = {0x80016F18: 0x2442FFF5, 0x80016F9C: 0x2442FFF5}

# Contador do deck ("calculadora"): continua com dois dígitos; só a origem
# muda de +14 para +7, centralizando os 2 dígitos menores (~11 px) sob o
# centro dos 5 dígitos de LP (x-2 .. x+28).
DECK_COUNT_WORDS = (
    (0x80016F40, 0x24070002),
    (0x80016FC8, 0x24070002),
)
DECK_X_PATCHES = (
    (0x80016F4C, 0x2442000E, 0x24420007, 'Deck do oponente: centralizar'),
    (0x80016FCC, 0x2442000E, 0x24420007, 'Deck do jogador: centralizar'),
)

DIGIT_FUNC = 0x80016D2C
TEXT_ENCODE_DIGITS = 0x800357E8
GS_SORT_SPRITE = 0x800844F0
OT_TABLE = 0x800E9D90               # D_800E9D90[style->ot_index]
DIGIT_ADVANCE = 6
SCALE_X = 0x0CCD                    # 0,8 (ONE = 0x1000)
SCALE_Y = 0x0E00                    # 0,875
SPRITE_ATTRIBUTE = 0x01000000       # 8 bpp, escala ligada (sem o bit 27)
RETAIL_DIGIT_WORDS = (
    0x27BDFFD0, 0xAFB20020, 0x00809021, 0xAFB1001C, 0x00A08821, 0x00C02021,
    0xAFB00018, 0x00E08021, 0x02002821, 0x27A60010, 0xAFBF002C, 0xAFB40028,
    0x0C00D5FA, 0xAFB30024, 0x2610FFFF, 0x06000014, 0x27B30010, 0x3C02800F,
    0x24549D90, 0x02701021, 0x90420000, 0x00000000, 0x000210C0, 0xA222000E,
    0x92420017, 0x96460014, 0x00021080, 0x00541021, 0x8C450000, 0x0C02127C,
    0x02202021, 0x96220004, 0x2610FFFF, 0x24420008, 0x0601FFF0, 0xA6220004,
    0x8FBF002C, 0x8FB40028, 0x8FB30024, 0x8FB20020, 0x8FB1001C, 0x8FB00018,
    0x03E00008, 0x27BD0030,
)


def small_digit_words() -> tuple[int, ...]:
    """func_80016D2C(style, sprite, valor, largura) com dígitos reduzidos."""
    a = Asm(DIGIT_FUNC)
    a.addiu('sp', 'sp', -0x30)
    a.sw('ra', 0x2C, 'sp'); a.sw('s2', 0x20, 'sp')
    a.sw('s1', 0x1C, 'sp'); a.sw('s0', 0x18, 'sp')
    a.move('s2', 'a0'); a.move('s1', 'a1'); a.move('s0', 'a3')
    a.move('a0', 'a2'); a.move('a1', 'a3')
    a.jal(TEXT_ENCODE_DIGITS)
    a.addiu('a2', 'sp', 0x10)
    # GsSPRITE: attribute +0, mx/my +0x18, scalex +0x1C, scaley +0x1E, rotate +0x20
    a.lui('t0', SPRITE_ATTRIBUTE >> 16)
    a.sw('t0', 0x00, 's1')
    a.sw('zero', 0x18, 's1')
    a.lui('t0', SCALE_Y); a.ori('t0', 't0', SCALE_X)
    a.sw('t0', 0x1C, 's1')
    a.addiu('s0', 's0', -1)
    a.bltz('s0', 'done')
    a.sw('zero', 0x20, 's1')        # delay slot: rotate = 0
    a.label('loop')
    a.addu('t0', 'sp', 's0')
    a.lbu('t0', 0x10, 't0')
    a.lbu('t1', 0x17, 's2')         # load delay: instrução independente
    a.sll('t0', 't0', 3)
    a.sb('t0', 0x0E, 's1')
    a.sll('t1', 't1', 2)
    high, low = hi_lo(OT_TABLE)
    a.lui('t2', high)
    a.addu('t1', 't1', 't2')
    a.lw('a1', low, 't1')
    a.lhu('a2', 0x14, 's2')
    a.jal(GS_SORT_SPRITE)
    a.move('a0', 's1')
    a.lhu('t0', 0x04, 's1')
    a.addiu('s0', 's0', -1)
    a.addiu('t0', 't0', DIGIT_ADVANCE)
    a.bgez('s0', 'loop')
    a.sh('t0', 0x04, 's1')
    a.label('done')
    a.lw('ra', 0x2C, 'sp'); a.lw('s2', 0x20, 'sp')
    a.lw('s1', 0x1C, 'sp'); a.lw('s0', 0x18, 'sp')
    a.jr('ra')
    a.addiu('sp', 'sp', 0x30)
    words = a.words()
    if len(words) > len(RETAIL_DIGIT_WORDS):
        raise ModError('Contador LP: rotina de dígitos maior que a original.')
    return tuple(words) + (0,) * (len(RETAIL_DIGIT_WORDS) - len(words))


def _all_patches():
    small = small_digit_words()
    out = [(pc, old, new) for pc, old, new, _ in LP_HUD_PATCHES]
    out += [(pc, old, new) for pc, old, new, _ in DECK_X_PATCHES]
    out += [(DIGIT_FUNC + 4 * i, old, new)
            for i, (old, new) in enumerate(zip(RETAIL_DIGIT_WORDS, small))]
    return out


def _word(data: bytes, pc: int) -> int:
    offset = pc - EXE_DELTA
    if offset < 0 or offset + 4 > len(data):
        raise ModError(f'Contador de LP: endereço fora do SLUS em 0x{pc:08X}.')
    return struct.unpack_from('<I', data, offset)[0]


def retail_words() -> dict[int, int]:
    """Palavras do SLUS retail que este patch confere (útil para fixtures)."""
    words = {pc: old for pc, old, _ in _all_patches()}
    words.update(dict(DECK_COUNT_WORDS))
    return words


def _verified_layout(original: bytes, modified: bytes) -> bool:
    return (len(original) == len(modified) and
            hashlib.sha256(original).hexdigest() == SOURCE_SHA256 and
            all(_word(original, pc) == retail for pc, retail, _ in _all_patches()) and
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
    for pc, retail, wide in _all_patches():
        if _word(modified, pc) not in (retail, wide, LEGACY_LP_WORDS.get(pc, wide)):
            raise ModError(f'Contador LP: conflito MIPS em 0x{pc:08X}.')
    for pc, retail in DECK_COUNT_WORDS:
        if _word(modified, pc) != retail:
            raise ModError(f'Contador LP: contador do deck alterado em 0x{pc:08X}.')

    out = bytearray(modified)
    for pc, _, wide in _all_patches():
        struct.pack_into('<I', out, pc - EXE_DELTA, wide)
    if not verify_lp_hud(original, bytes(out), initial_lp=initial_lp):
        raise ModError('Contador LP: verificação final de cinco dígitos falhou.')
    return bytes(out), {
        'status': 'aplicado', 'digitos': 5, 'lp_inicial': initial_lp,
        'jogador': True, 'adversario': True,
        'enderecos': [f'0x{pc:08X}' for pc, *_ in LP_HUD_PATCHES + DECK_X_PATCHES],
        'rotina_digitos': f'0x{DIGIT_FUNC:08X}',
        'digito_px': DIGIT_ADVANCE, 'escala': [SCALE_X / 0x1000, SCALE_Y / 0x1000],
        'deck_centralizado': True, 'deck_preservado': True, 'validado_epsxe': False,
        'aviso': ('Dígitos de LP reduzidos para caber 5 no quadro original; '
                  'conferir visualmente no ePSXe. LP acima de 32767 ainda exige avaliação do contador assinado.'
                  if initial_lp > 32767 else
                  'Dígitos de LP e do deck reduzidos (6 px); conferir visualmente no ePSXe.'),
    }


def verify_lp_hud(original: bytes, modified: bytes, *, initial_lp: int) -> bool:
    if initial_lp <= 9999:
        return True  # nenhum patch do HUD foi solicitado; outros patches são permitidos
    try:
        return (_verified_layout(original, modified) and
                all(_word(modified, pc) == wide for pc, _, wide in _all_patches()) and
                all(_word(modified, pc) == retail for pc, retail in DECK_COUNT_WORDS))
    except (ModError, struct.error):
        return False
