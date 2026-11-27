"""HUD de duelo novo no PS1: losango do retrato, LP, barra de LP e contador do deck.

Substitui ``Duel_DrawLifePointsAndDeckCounts`` (0x80016E70), que o jogo chama
a cada quadro do duelo pelo objeto do painel. A entrada recebe ``j rotina;
nop`` e a rotina:

1. continua animando o LP mostrado (``Duel_UpdateLifePointDisplay`` nos dois
   lados), como o original;
2. esconde o painel antigo (LP/COM/YOU) tirando o bit 0x40 (desenhável) das
   flags do objeto dele: a lista de objetos só desenha com 0xC0 ligados (o
   renderizador de folhas de sprite do PS1 ignora GsDOFF);
3. desenha o layout de ``duel_hud_layout`` direto na OT do painel, com
   primitivas sem textura e sem GTE: POLY_F4 para faixas e losangos, TILE
   para a barra e para o texto (fonte 5x7 em retângulos). Mesmo deslocamento
   de tela e mesma profundidade que o GsSortFastSprite dos dígitos originais;
4. chama o rank ao vivo do runtime (``DrawLiveRank``), se instalado, com o
   painel movido só durante a chamada para a posição nova.

Na mesma entrada da OT a última primitiva enfileirada é a primeira desenhada,
então o texto e a barra são enfileirados antes das faixas.

Etapa 1: o losango é preenchido com o tom escuro da cor do lado (os retratos
entram numa etapa seguinte). Visual a conferir no ePSXe (validado_epsxe=False).
"""
from __future__ import annotations

import struct

from .core import ModError
from .deep_extract import exe_pos
from .duel_hud_layout import FONT, SIDES, WHITE, glyph_rects
from .mips_asm import Asm, hi_lo

ENTRY = 0x80016E70                       # Duel_DrawLifePointsAndDeckCounts
ENTRY_WORDS = (0x27BDFFD8, 0xAFB00010)   # addiu sp,-0x28 ; sw s0,0x10(sp)
UPDATE_LP = 0x80016DDC                   # Duel_UpdateLifePointDisplay(side)
SIDE_STATES = 0x800E9FF0                 # 2 x 0x20
ORDERING_TABLES = 0x800E9D90             # GsOT *[4]
PACKET_POINTER = 0x800FE240              # GsOUT_PACKET_P
DRAW_OFFSET = 0x800FE0BC                 # deslocamento x/y de tela (halfwords)
SCRATCH_SPRITE = 0x1F800320              # GsSPRITE de rascunho do HUD original
DECK_SIZE = 40
RENDERABLE = 0x40                        # DisplayObject.flags: sem ele a lista não desenha o objeto
X_BIAS = 160                             # vértices guardados como (x - 160, y) em bytes
RANK_X, RANK_Y = 150, 36                 # canto do "C-POW 62" no layout novo
GLYPH_ORDER = '0123456789LP:'


def _bgr(color, code):
    r, g, b = color
    return code << 24 | b << 16 | g << 8 | r


def _quad_table():
    """(cor POLY_F4, 4 vértices) na ordem de enfileiramento."""
    rows = []
    for index in (1, 0):
        side = SIDES[index]
        cx, cy, h = side.diamond
        inner = ((cx, cy - h + 1), (cx + h - 1, cy), (cx, cy + h - 1), (cx - h + 1, cy))
        border = ((cx, cy - h - 1), (cx + h + 1, cy), (cx, cy + h + 1), (cx - h - 1, cy))
        rows.append((_bgr(side.dim, 0x28), inner))        # fica por cima da borda
        rows.append((_bgr(WHITE, 0x28), border))
        for quad in side.bands:
            rows.append((_bgr(side.color, 0x28), quad))
    return rows


def _glyph_data():
    header, offsets, rects = [], [], []
    for char in GLYPH_ORDER:
        parts = glyph_rects(char)
        offsets.append(len(rects) * 2)
        header.append(len(parts) | (len(FONT[char][0]) + 1) << 4)
        rects.extend(parts)
    data = bytearray()
    for x, y, w, h in rects:
        data += bytes((x | y << 3, w | h << 4))
    return bytes(header), bytes(offsets), bytes(data)


def _link(a, length):
    """Encadeia o pacote em s3 na entrada s2 da OT (s5 = 0x00FFFFFF)."""
    a.lw('t8', 0, 's2')
    a.lui('t9', length << 8)
    a.addu('t8', 't8', 't9')
    a.sw('t8', 0, 's3')
    a.and_('t9', 's3', 's5')
    a.sw('t9', 0, 's2')
    a.addiu('s3', 's3', (length + 1) * 4)


def _tile(a, xy, wh, color):
    """TILE: cor, xy (+ deslocamento s4), wh."""
    a.sw(color, 4, 's3')
    a.addu('t8', xy, 's4')
    a.sw('t8', 8, 's3')
    a.sw(wh, 12, 's3')
    _link(a, 3)


def code(base: int, rank_entry: int | None = None) -> bytes:
    a = Asm(base)
    quads = _quad_table()
    header, offsets, rects = _glyph_data()
    sh, sl = hi_lo(SIDE_STATES)

    # ---------------------------------------------------------------- principal
    a.addiu('sp', 'sp', -48)
    a.sw('ra', 44, 'sp')
    for i, reg in enumerate(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7')):
        a.sw(reg, 4 * i + 8, 'sp')
    a.move('s0', 'a0')
    a.lui('a0', sh)
    a.jal(UPDATE_LP)
    a.addiu('a0', 'a0', sl)
    a.lui('a0', sh)
    a.jal(UPDATE_LP)
    a.addiu('a0', 'a0', sl + 0x20)
    a.lw('s1', 0x50, 's0')                       # painel
    a.nop()
    a.lhu('t0', 8, 's1')
    a.nop()
    a.andi('t0', 't0', 0xFFFF & ~RENDERABLE)
    a.sh('t0', 8, 's1')                          # painel antigo deixa de ser desenhado
    oh, ol = hi_lo(ORDERING_TABLES)
    a.lbu('t0', 0x17, 's1')
    a.lui('t1', oh)
    a.sll('t0', 't0', 2)
    a.addu('t1', 't1', 't0')
    a.lw('t1', ol, 't1')                         # GsOT *
    a.lhu('t2', 0x14, 's1')                      # profundidade
    a.lw('t3', 4, 't1')                          # org
    a.lw('t4', 8, 't1')                          # offset
    a.sll('t2', 't2', 2)
    a.addu('t3', 't3', 't2')
    a.sll('t4', 't4', 2)
    a.subu('s2', 't3', 't4')                     # entrada da OT
    ph, pl = hi_lo(PACKET_POINTER)
    a.lui('t0', ph)
    a.lw('s3', pl, 't0')
    dh, dl = hi_lo(DRAW_OFFSET)
    a.lui('t0', dh)
    a.lhu('t1', dl, 't0')
    a.lhu('t2', dl + 2, 't0')
    a.nop()
    a.sll('t2', 't2', 16)
    a.or_('s4', 't1', 't2')
    a.lui('s5', 0x00FF)
    a.ori('s5', 's5', 0xFFFF)
    white = _bgr(WHITE, 0x60)
    a.lui('s6', white >> 16)
    a.ori('s6', 's6', white & 0xFFFF)

    for index in (1, 0):
        side = SIDES[index]
        state = SIDE_STATES + 0x20 * index
        th, tl = hi_lo(state)
        a.lui('s7', th)
        a.addiu('s7', 's7', tl)
        # texto "LP:n" e contador do deck (enfileirados antes de tudo: ficam por cima)
        a.lhu('a0', 0x12, 's7')
        a.li('a1', side.lp_center[0])
        a.li('a2', side.lp_center[1])
        a.jal('text')
        a.li('a3', 1)
        a.lb('t0', 0x18, 's7')
        a.li('a0', DECK_SIZE)
        a.subu('a0', 'a0', 't0')
        a.bgez('a0', f'deck_ok_{index}')
        a.nop()
        a.move('a0', 'zero')
        a.label(f'deck_ok_{index}')
        a.li('a1', side.deck_center[0])
        a.li('a2', side.deck_center[1])
        a.jal('text')
        a.li('a3', 0)
        # barra: branco = LP mostrado / LP inicial (max_life_points em +0x16)
        x0, y0, x1, y1 = side.bar
        width, height = x1 - x0 + 1, y1 - y0 + 1
        a.lhu('t0', 0x12, 's7')
        a.lhu('t1', 0x16, 's7')
        a.li('t2', width)
        a.beqz('t1', f'bar_full_{index}')
        a.sltu('t3', 't0', 't1')
        a.beqz('t3', f'bar_full_{index}')
        a.nop()
        a.multu('t0', 't2')
        a.mflo('t3')
        a.nop()                                  # R3000: mult/div só 2 instruções após mflo
        a.nop()
        a.divu('t3', 't1')
        a.mflo('t2')
        a.label(f'bar_full_{index}')
        a.beqz('t2', f'bar_bg_{index}')
        a.lui('t1', height)
        a.or_('t4', 't1', 't2')                  # wh
        if side.fill_from_right:
            a.li('t5', x1 + 1)
            a.subu('t5', 't5', 't2')
        else:
            a.li('t5', x0)
        a.lui('t6', y0)
        a.or_('t5', 't5', 't6')                  # xy
        _tile(a, 't5', 't4', 's6')
        a.label(f'bar_bg_{index}')
        a.lui('t4', height)
        a.ori('t4', 't4', width)
        a.lui('t5', y0)
        a.ori('t5', 't5', x0)
        dim = _bgr(side.dim, 0x60)
        a.lui('t6', dim >> 16)
        a.ori('t6', 't6', dim & 0xFFFF)
        _tile(a, 't5', 't4', 't6')

    # faixas e losangos (tabela)
    a.la('t6', 'quads')
    a.li('t7', len(quads))
    a.label('quad_loop')
    a.lw('t0', 0, 't6')
    a.nop()
    a.sw('t0', 4, 's3')
    for slot, vertex in enumerate((0, 1, 3, 2)):          # ordem de faixa do POLY_F4
        a.lbu('t0', 4 + 2 * vertex, 't6')
        a.lbu('t1', 5 + 2 * vertex, 't6')
        a.addiu('t0', 't0', X_BIAS)
        a.sll('t1', 't1', 16)
        a.or_('t0', 't0', 't1')
        a.addu('t0', 't0', 's4')
        a.sw('t0', 8 + 4 * slot, 's3')
    _link(a, 5)
    a.addiu('t7', 't7', -1)
    a.bnez('t7', 'quad_loop')
    a.addiu('t6', 't6', 12)

    # devolve o ponteiro de pacotes antes de qualquer GsSort* do jogo
    a.lui('t0', ph)
    a.sw('s3', pl, 't0')
    if rank_entry is not None:
        # DrawLiveRank(painel, sprite, 0, 0): desenha em (x-35, y+23) do painel
        a.lh('s6', 0x30, 's1')
        a.lh('s7', 0x32, 's1')
        a.li('t0', RANK_X + 35)
        a.sh('t0', 0x30, 's1')
        a.li('t0', RANK_Y - 23)
        a.sh('t0', 0x32, 's1')
        sch, scl = hi_lo(SCRATCH_SPRITE)
        a.lui('a1', sch)
        a.ori('a1', 'a1', scl & 0xFFFF)
        a.lui('t0', 0x0008)
        a.ori('t0', 't0', 0x0008)
        a.sw('t0', 8, 'a1')                      # 8x8
        a.move('a0', 's1')
        a.move('a2', 'zero')
        a.jal(rank_entry)
        a.move('a3', 'zero')
        a.sh('s6', 0x30, 's1')
        a.sh('s7', 0x32, 's1')
    for i, reg in enumerate(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7')):
        a.lw(reg, 4 * i + 8, 'sp')
    a.lw('ra', 44, 'sp')
    a.nop()
    a.jr('ra')
    a.addiu('sp', 'sp', 48)

    # ---------------------------------------------------------- text(v, cx, top, prefixo)
    a.label('text')
    a.move('v1', 'ra')
    a.la('t0', 'digits')
    a.move('t1', 'zero')
    a.li('t2', 10)
    a.label('digit_loop')
    a.divu('a0', 't2')
    a.mfhi('t3')
    a.mflo('a0')
    a.addu('t4', 't0', 't1')
    a.sb('t3', 0, 't4')
    a.bnez('a0', 'digit_loop')
    a.addiu('t1', 't1', 1)
    a.sll('t2', 't1', 1)
    a.addu('t2', 't2', 't1')
    a.sll('t2', 't2', 1)                         # 6n
    a.addiu('t2', 't2', -1)
    a.beqz('a3', 'no_prefix')
    a.nop()
    a.addiu('t2', 't2', 14)                      # "LP:" = 6 + 6 + 2
    a.label('no_prefix')
    a.sra('t2', 't2', 1)
    a.subu('a1', 'a1', 't2')
    a.beqz('a3', 'digits_out')
    a.nop()
    for glyph in 'LP:':
        a.jal('glyph')
        a.li('a0', GLYPH_ORDER.index(glyph))
    a.label('digits_out')
    a.addiu('t1', 't1', -1)
    a.addu('t4', 't0', 't1')
    a.jal('glyph')
    a.lbu('a0', 0, 't4')
    a.bnez('t1', 'digits_out')
    a.nop()
    a.jr('v1')
    a.nop()

    # ---------------------------------------------------- glyph(a0 = índice; a1 x, a2 y)
    a.label('glyph')
    a.la('t2', 'glyph_header')
    a.addu('t2', 't2', 'a0')
    a.lbu('t3', 0, 't2')
    a.la('t4', 'glyph_offsets')
    a.addu('t4', 't4', 'a0')
    a.lbu('t4', 0, 't4')
    a.la('t5', 'glyph_rects')
    a.addu('t5', 't5', 't4')
    a.andi('t6', 't3', 15)
    a.label('rect_loop')
    a.lbu('t2', 0, 't5')
    a.lbu('t4', 1, 't5')
    a.andi('t7', 't2', 7)
    a.srl('t2', 't2', 3)
    a.addu('t7', 't7', 'a1')
    a.addu('t2', 't2', 'a2')
    a.sll('t2', 't2', 16)
    a.or_('t7', 't7', 't2')                      # xy
    a.andi('t2', 't4', 15)
    a.srl('t4', 't4', 4)
    a.sll('t4', 't4', 16)
    a.or_('t4', 't4', 't2')                      # wh
    _tile(a, 't7', 't4', 's6')
    a.addiu('t6', 't6', -1)
    a.bnez('t6', 'rect_loop')
    a.addiu('t5', 't5', 2)
    a.srl('t3', 't3', 4)
    a.jr('ra')
    a.addu('a1', 'a1', 't3')

    # ------------------------------------------------------------------ dados
    a.label('quads')
    for color, quad in quads:
        a.word(color)
        packed = b''.join(bytes((x - X_BIAS, y)) for x, y in quad)
        a.word(struct.unpack_from('<I', packed, 0)[0])
        a.word(struct.unpack_from('<I', packed, 4)[0])
    a.label('glyph_header')
    for chunk in _pad4(header):
        a.word(chunk)
    a.label('glyph_offsets')
    for chunk in _pad4(offsets):
        a.word(chunk)
    a.label('glyph_rects')
    for chunk in _pad4(rects):
        a.word(chunk)
    a.label('digits')
    a.word(0)
    a.word(0)
    return a.bytes()


def _pad4(data: bytes):
    data = data + bytes(-len(data) % 4)
    return struct.unpack(f'<{len(data) // 4}I', data)


def block_size(rank: bool = True) -> int:
    return len(code(0x80100000, 0x801CF18C if rank else None))


def _jump(target: int) -> int:
    return 0x08000000 | ((target >> 2) & 0x03FFFFFF)


def apply(exe: bytes, hook: int, rank_entry: int | None) -> tuple[bytes, dict]:
    at = exe_pos(ENTRY, exe, 8)
    words = struct.unpack_from('<II', exe, at)
    if words != ENTRY_WORDS:
        raise ModError('HUD de duelo: a função do painel de LP não confere com o Drop x15.')
    block = code(hook, rank_entry)
    pos = exe_pos(hook, exe, len(block))
    if any(exe[pos:pos + len(block)]):
        raise ModError('HUD de duelo: a área reservada no SLUS não está livre.')
    out = bytearray(exe)
    out[pos:pos + len(block)] = block
    struct.pack_into('<II', out, at, _jump(hook), 0)
    return bytes(out), {
        'status': 'aplicado', 'rotina': f'0x{hook:08X}', 'bytes': len(block),
        'rank_ao_vivo': rank_entry is not None, 'retratos': 'etapa_2',
        'validado_epsxe': False,
    }


def installed(exe: bytes) -> int | None:
    try:
        first, second = struct.unpack_from('<II', exe, exe_pos(ENTRY, exe, 8))
    except Exception:
        return None
    if first >> 26 != 2 or second != 0:
        return None
    return 0x80000000 | (first & 0x03FFFFFF) << 2


def runtime_view(exe: bytes) -> bytes:
    """SLUS com a entrada original do painel (para conferências byte a byte)."""
    if installed(exe) is None:
        return exe
    out = bytearray(exe)
    struct.pack_into('<II', out, exe_pos(ENTRY, exe, 8), *ENTRY_WORDS)
    return bytes(out)
