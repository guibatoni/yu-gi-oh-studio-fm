"""Mostrar 20.000 LP no HUD do PS1: cinco algarismos nos dois lados.

O SLUS retail chama func_80016D2C com largura 4 para os LP do rival e do
jogador, e com largura 2 para os contadores do deck ("calculadora"). Cada
algarismo é um sprite 8x8 desenhado com GsSortFastSprite, avançando 8 px.

Com LP acima de 9.999 este patch:

* troca, dentro de func_80016D2C, a chamada ao GsSortFastSprite por uma
  rotina própria (bloco reservado no SLUS) que emite o mesmo glifo como um
  POLY_FT4 de 6x7 px, sem usar a GTE, e reduz o avanço de 8 para 6 px. Os 5
  dígitos ocupam 30 px, dentro dos 32 px que os 4 dígitos originais usavam;
* chama essa função com largura 5 e origem -2 (era -3) nos dois lados;
* desenha o contador do deck com os mesmos dígitos menores, centralizado
  sob/sobre os dígitos de LP (origem +7 em vez de +14).

A primeira versão usava GsSortSprite com escala; ele depende do estado da
GTE da cena 3D e os dígitos piscavam/sumiam (ex.: escolha de Guardian Star).
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
SORT_CALL = 0x80016DA0              # jal GsSortFastSprite dentro do laço
ADVANCE_PC = 0x80016DB0             # addiu v0,v0,8 (avanço de x)
GS_SORT_FAST_SPRITE = 0x800849F0
PACKET_POINTER = 0x800FE240         # GsOUT_PACKET_P
DRAW_OFFSET = 0x800FE0BC            # deslocamento x/y somado pelo GsSortFastSprite
DIGIT_ADVANCE = 6
DIGIT_W, DIGIT_H = 6, 7             # glifo 8x8 da fonte desenhado em 6x7
QUAD_BYTES = 0x28                   # POLY_FT4: tag + 9 palavras
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


def _jal(target: int) -> int:
    return 0x0C000000 | ((target & 0x0FFFFFFF) >> 2)


def quad_code(base: int) -> bytes:
    """SmallDigit(sprite, ot, pri): igual ao GsSortFastSprite, mas em 6x7.

    Emite um POLY_FT4 texturizado direto no buffer de pacotes, sem GTE (o
    GsSortSprite com escala dependia do estado da GTE da cena 3D e fazia os
    dígitos piscarem). Atributo, cor, tpage, CLUT, deslocamento de tela e
    encadeamento na OT seguem exatamente o GsSortFastSprite retail.
    """
    a = Asm(base)
    a.lw('t4', 0, 'a0')
    a.lui('t7', hi_lo(PACKET_POINTER)[0])
    a.bltz('t4', 'done')                        # bit 31: não exibir
    a.lw('t7', hi_lo(PACKET_POINTER)[1], 't7')
    # palavra 1: 0x2C | semitransparente (bit 30) | sem brilho (bit 6) | cor
    a.srl('t0', 't4', 5); a.lui('t1', 0x0200); a.and_('t0', 't0', 't1')
    a.sll('t1', 't4', 18); a.lui('t2', 0x0100); a.and_('t1', 't1', 't2')
    a.or_('t0', 't0', 't1')
    a.lui('t1', 0x2C00); a.or_('t0', 't0', 't1')
    a.lbu('t1', 0x16, 'a0'); a.lbu('t2', 0x15, 'a0'); a.lbu('t3', 0x14, 'a0')
    a.sll('t1', 't1', 16); a.or_('t0', 't0', 't1')
    a.sll('t2', 't2', 8); a.or_('t0', 't0', 't2')
    a.or_('t0', 't0', 't3')
    a.sw('t0', 4, 't7')
    # vértices (x/y + deslocamento de tela)
    off_hi, off_lo = hi_lo(DRAW_OFFSET)
    a.lui('t1', off_hi)
    a.lhu('t2', off_lo, 't1'); a.lhu('t3', off_lo + 2, 't1')
    a.lhu('t0', 4, 'a0'); a.lhu('t1', 6, 'a0')
    a.addu('t2', 't2', 't0'); a.andi('t2', 't2', 0xFFFF)
    a.addu('t3', 't3', 't1'); a.sll('t3', 't3', 16)
    a.or_('t0', 't2', 't3'); a.sw('t0', 0x08, 't7')
    a.addiu('t5', 't2', DIGIT_W); a.andi('t5', 't5', 0xFFFF)
    a.or_('t0', 't5', 't3'); a.sw('t0', 0x10, 't7')
    a.lui('t1', DIGIT_H); a.addu('t3', 't3', 't1')
    a.or_('t0', 't2', 't3'); a.sw('t0', 0x18, 't7')
    a.or_('t0', 't5', 't3'); a.sw('t0', 0x20, 't7')
    # uv0 + CLUT
    a.lbu('t0', 0x0E, 'a0'); a.lbu('t1', 0x0F, 'a0')
    a.lh('t2', 0x12, 'a0'); a.lh('t3', 0x10, 'a0')
    a.sll('t1', 't1', 8); a.or_('t6', 't0', 't1')         # t6 = u | v<<8
    a.sll('t2', 't2', 22)
    a.sll('t3', 't3', 12); a.lui('t1', 0x3F); a.and_('t3', 't3', 't1')
    a.or_('t2', 't2', 't3'); a.or_('t2', 't2', 't6'); a.sw('t2', 0x0C, 't7')
    # uv1 + tpage (modo de cor bits 24-25, abr bits 28-29, página do sprite)
    a.lhu('t3', 0x0C, 'a0')
    a.srl('t2', 't4', 17); a.andi('t2', 't2', 0x180)     # (preenche o load delay)
    a.andi('t3', 't3', 0x1F); a.or_('t2', 't2', 't3')
    a.srl('t3', 't4', 23); a.andi('t3', 't3', 0x60); a.or_('t2', 't2', 't3')
    a.sll('t2', 't2', 16)
    a.addiu('t3', 't6', 8); a.or_('t2', 't2', 't3'); a.sw('t2', 0x14, 't7')
    a.addiu('t3', 't6', 0x800); a.sw('t3', 0x1C, 't7')
    a.addiu('t3', 't6', 0x808); a.sw('t3', 0x24, 't7')
    # encadear na OT: entrada = org + pri*4 - length*4 (como GsSortFastSprite)
    a.andi('a2', 'a2', 0xFFFF); a.sll('a2', 'a2', 2)
    a.lw('t0', 4, 'a1'); a.lw('t1', 8, 'a1')
    a.addu('t0', 't0', 'a2'); a.sll('t1', 't1', 2); a.subu('t0', 't0', 't1')
    a.lw('t1', 0, 't0')
    a.lui('t2', 0x0900)
    a.addu('t1', 't1', 't2'); a.sw('t1', 0, 't7')
    a.lui('t2', 0x00FF); a.ori('t2', 't2', 0xFFFF)
    a.and_('t2', 't7', 't2'); a.sw('t2', 0, 't0')
    a.addiu('t7', 't7', QUAD_BYTES)
    a.lui('t1', hi_lo(PACKET_POINTER)[0])
    a.sw('t7', hi_lo(PACKET_POINTER)[1], 't1')
    a.label('done')
    a.jr('ra')
    a.nop()
    return a.bytes()


def block_size() -> int:
    return len(quad_code(0x80100000))


def _func_patches(hook: int):
    return ((SORT_CALL, _jal(GS_SORT_FAST_SPRITE), _jal(hook)),
            (ADVANCE_PC, 0x24420008, 0x24420000 | DIGIT_ADVANCE))


def _all_patches(hook: int | None = None):
    out = [(pc, old, new) for pc, old, new, _ in LP_HUD_PATCHES]
    out += [(pc, old, new) for pc, old, new, _ in DECK_X_PATCHES]
    if hook is not None:
        out += list(_func_patches(hook))
    return out


def installed_hook(exe: bytes) -> int | None:
    word = _word(exe, SORT_CALL)
    if word >> 26 != 3 or word == _jal(GS_SORT_FAST_SPRITE):
        return None
    return 0x80000000 | ((word & 0x03FFFFFF) << 2)


def _word(data: bytes, pc: int) -> int:
    offset = pc - EXE_DELTA
    if offset < 0 or offset + 4 > len(data):
        raise ModError(f'Contador de LP: endereço fora do SLUS em 0x{pc:08X}.')
    return struct.unpack_from('<I', data, offset)[0]


def retail_words() -> dict[int, int]:
    """Palavras do SLUS retail que este patch confere (útil para fixtures)."""
    words = {pc: old for pc, old, _ in _all_patches()}
    words.update(dict(DECK_COUNT_WORDS))
    words.update({DIGIT_FUNC + 4 * i: w for i, w in enumerate(RETAIL_DIGIT_WORDS)})
    return words


def _verified_layout(original: bytes, modified: bytes) -> bool:
    return (len(original) == len(modified) and
            hashlib.sha256(original).hexdigest() == SOURCE_SHA256 and
            all(_word(original, pc) == retail for pc, retail, _ in _all_patches()) and
            all(_word(original, DIGIT_FUNC + 4 * i) == w for i, w in enumerate(RETAIL_DIGIT_WORDS)) and
            all(_word(original, pc) == retail for pc, retail in DECK_COUNT_WORDS))


def patch_lp_hud(original: bytes, modified: bytes, *, initial_lp: int,
                 hook: int | None = None) -> tuple[bytes, dict]:
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
    if hook is None:
        raise ModError('Contador LP: sem bloco reservado para os dígitos reduzidos.')
    block = quad_code(hook)
    at = hook - EXE_DELTA
    if (hook & 3 or at < 0 or at + len(block) > len(modified)
            or (any(modified[at:at + len(block)]) and modified[at:at + len(block)] != block)):
        raise ModError('Contador LP: a área reservada para os dígitos não está livre.')
    for i, retail in enumerate(RETAIL_DIGIT_WORDS):
        pc = DIGIT_FUNC + 4 * i
        if pc not in (SORT_CALL, ADVANCE_PC) and _word(modified, pc) != retail:
            raise ModError(f'Contador LP: rotina de dígitos alterada em 0x{pc:08X}.')
    for pc, retail, wide in _all_patches(hook):
        if _word(modified, pc) not in (retail, wide, LEGACY_LP_WORDS.get(pc, wide)):
            raise ModError(f'Contador LP: conflito MIPS em 0x{pc:08X}.')
    for pc, retail in DECK_COUNT_WORDS:
        if _word(modified, pc) != retail:
            raise ModError(f'Contador LP: contador do deck alterado em 0x{pc:08X}.')

    out = bytearray(modified)
    out[at:at + len(block)] = block
    for pc, _, wide in _all_patches(hook):
        struct.pack_into('<I', out, pc - EXE_DELTA, wide)
    if not verify_lp_hud(original, bytes(out), initial_lp=initial_lp):
        raise ModError('Contador LP: verificação final de cinco dígitos falhou.')
    return bytes(out), {
        'status': 'aplicado', 'digitos': 5, 'lp_inicial': initial_lp,
        'jogador': True, 'adversario': True,
        'enderecos': [f'0x{pc:08X}' for pc, *_ in LP_HUD_PATCHES + DECK_X_PATCHES],
        'rotina_digitos': f'0x{hook:08X}',
        'digito_px': [DIGIT_W, DIGIT_H], 'sem_gte': True,
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
        hook = installed_hook(modified)
        if hook is None:
            return False
        block = quad_code(hook)
        at = hook - EXE_DELTA
        return (_verified_layout(original, modified) and
                modified[at:at + len(block)] == block and
                all(_word(modified, pc) == wide for pc, _, wide in _all_patches(hook)) and
                all(_word(modified, pc) == retail for pc, retail in DECK_COUNT_WORDS))
    except (ModError, struct.error):
        return False
