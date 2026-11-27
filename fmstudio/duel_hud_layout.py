"""Layout do HUD de duelo novo (retrato em losango, LP, barra e deck), em pixels do PS1.

Fonte única para a rotina MIPS e para a prévia do Studio: tudo é desenhado com
primitivas simples da GPU — quadriláteros chapados (POLY_F4), retângulos
(TILE) para a barra e para o texto, e um quadrilátero texturizado (POLY_FT4)
para o retrato. Tela do duelo: 320x240.

Lado 1 = rival (vermelho, em cima à esquerda); lado 0 = jogador (azul, embaixo
à direita), como no desenho do usuário. A barra de LP enche a partir do lado do
retrato e vai de 0 ao LP inicial do duelo (cura acima do inicial: barra cheia).
"""
from __future__ import annotations

from dataclasses import dataclass

SCREEN_W, SCREEN_H = 320, 240

RED, RED_DIM = (255, 16, 16), (156, 60, 60)
BLUE, BLUE_DIM = (0, 66, 229), (40, 80, 181)
WHITE = (255, 255, 255)

# Fonte 3x5 (só o que o HUD usa), para o texto caber com folga nas faixas de 8 px.
# Cada glifo vira poucos retângulos (TILE).
FONT = {
    '0': ("111", "101", "101", "101", "111"),
    '1': ("010", "110", "010", "010", "111"),
    '2': ("111", "001", "111", "100", "111"),
    '3': ("111", "001", "111", "001", "111"),
    '4': ("101", "101", "111", "001", "001"),
    '5': ("111", "100", "111", "001", "111"),
    '6': ("111", "100", "111", "101", "111"),
    '7': ("111", "001", "001", "001", "001"),
    '8': ("111", "101", "111", "101", "111"),
    '9': ("111", "101", "111", "001", "111"),
    'L': ("100", "100", "100", "100", "111"),
    'P': ("111", "101", "111", "100", "100"),
    ':': ("0", "1", "0", "1", "0"),
}
GLYPH_H = 5
DIGIT_ADVANCE = len(FONT['0'][0]) + 1
PREFIX = 'LP:'
PREFIX_WIDTH = sum(len(FONT[c][0]) + 1 for c in PREFIX)


def glyph_rects(char: str) -> tuple[tuple[int, int, int, int], ...]:
    """Cobre o glifo com retângulos (x, y, w, h): junta trechos iguais de linhas seguidas."""
    rows = FONT[char]
    runs = []
    for y, row in enumerate(rows):
        x = 0
        while x < len(row):
            if row[x] == '1':
                start = x
                while x < len(row) and row[x] == '1':
                    x += 1
                runs.append([start, y, x - start, 1])
            else:
                x += 1
    merged = []
    for run in runs:
        for rect in merged:
            if rect[0] == run[0] and rect[2] == run[2] and rect[1] + rect[3] == run[1]:
                rect[3] += 1
                break
        else:
            merged.append(run)
    return tuple(tuple(r) for r in merged)


def text_width(text: str) -> int:
    return sum(len(FONT[c][0]) + 1 for c in text) - 1


@dataclass(frozen=True)
class Side:
    """Um bloco do HUD. ``bands``: quadriláteros (4 pontos, sentido horário)."""
    color: tuple
    dim: tuple
    diamond: tuple            # (cx, cy, meia-diagonal)
    bands: tuple              # ((x, y) * 4, ...)
    bar: tuple                # (x0, y0, x1, y1) inclusivo
    fill_from_right: bool     # barra enche a partir do retrato
    lp_center: tuple          # (cx, topo) do texto "LP: n"
    deck_center: tuple        # (cx, topo) do contador do deck


def _band(left_top, left_mid, left_bottom, right_top, right_bottom, round_right=True):
    """Faixa com a ponta do retrato em ``left_*`` e ponta arredondada (chanfro) do outro lado."""
    quads = []
    (lx0, y0), (lxm, ym), (lx1, y1) = left_top, left_mid, left_bottom
    rx, ry0, ry1 = right_top[0], right_top[1], right_bottom[1]
    quads.append(((lx0, y0), (rx, y0), (rx, ym), (lxm, ym)))
    quads.append(((lxm, ym), (rx, ym), (rx, y1), (lx1, y1)))
    # ponta arredondada: meia-elipse em leque de quadriláteros convexos
    import math
    r = (y1 - y0 + 1) / 2
    cy = y0 + r - 0.5
    arc = [(rx + round(0.8 * r * math.sin(a)), round(cy - r * math.cos(a) + (0.5 if a > math.pi / 2 else 0)))
           for a in (i * math.pi / 6 for i in range(7))]
    arc[0], arc[-1] = (rx, y0), (rx, y1)
    quads.append((arc[0], arc[1], arc[2], arc[3]))
    quads.append((arc[0], arc[3], arc[4], arc[5]))
    quads.append((arc[0], arc[5], arc[6], arc[6]))
    return quads


def _mirror(quads):
    """Espelha horizontalmente (x -> -x) mantendo o sentido horário."""
    return [tuple((-x, y) for x, y in reversed(q)) for q in quads]


def _shift(quads, dx):
    return [tuple((x + dx, y) for x, y in q) for q in quads]


# Caixa do HUD na tela do duelo (pedida pelo usuário): x 223..315, y 5..61.
BOX = (223, 5, 315, 61)
GAP = 2                   # espaço entre o losango e as faixas


def _side_rival():
    cx, cy, h = 236, 19, 13          # losango em y 6..32 (borda 5..33)

    def edge_up(y):      # aresta superior direita do losango
        return cx + (y - (cy - h))

    def edge_down(y):    # aresta inferior direita
        return cx + ((cy + h) - y)
    top = _band((edge_up(6) + GAP, 6), (edge_up(10) + GAP, 10), (edge_up(13) + GAP, 13), (300, 6), (300, 13))
    bar = _band((edge_up(15) + GAP, 15), (cx + h + GAP, cy), (edge_down(22) + GAP, 22), (302, 15), (302, 22))
    deck = _band((edge_down(24) + GAP, 24), (edge_down(28) + GAP, 28), (edge_down(31) + GAP, 31),
                 (262, 24), (262, 31))
    return Side(RED, RED_DIM, (cx, cy, h), tuple(top + bar + deck), (256, 17, 297, 20), False,
                (271, 8), (252, 26))


def _side_player():
    cx, cy, h = 302, 47, 13          # losango em y 34..60 (borda 33..61)

    def edge_up(y):      # aresta superior esquerda
        return cx - (y - (cy - h))

    def edge_down(y):    # aresta inferior esquerda
        return cx - ((cy + h) - y)
    # desenha como o rival (ponta do retrato à esquerda) em coordenadas espelhadas
    top = _band((-(edge_up(34) - GAP), 34), (-(edge_up(38) - GAP), 38), (-(edge_up(41) - GAP), 41),
                (-240, 34), (-240, 41))
    bar = _band((-(edge_up(43) - GAP), 43), (-(cx - h - GAP), cy), (-(edge_down(50) - GAP), 50),
                (-237, 43), (-237, 50))
    deck = _band((-(edge_down(52) - GAP), 52), (-(edge_down(56) - GAP), 56), (-(edge_down(59) - GAP), 59),
                 (-276, 52), (-276, 59))
    quads = _mirror(top + bar + deck)
    return Side(BLUE, BLUE_DIM, (cx, cy, h), tuple(quads), (242, 45, 282, 48), True, (266, 36), (285, 54))


SIDES = {1: _side_rival(), 0: _side_player()}


def lp_text(value: int) -> str:
    return f'LP:{max(0, int(value))}'


def bar_fill(side: Side, lp: int, start: int) -> int:
    """Pixels brancos da barra (0..largura)."""
    x0, _, x1, _ = side.bar
    width = x1 - x0 + 1
    if start <= 0:
        return width
    return max(0, min(width, (max(0, lp) * width) // start))


# --------------------------------------------------------------------------- prévia
def render_preview(base=None, *, lp=(1000, 7000), start=(8000, 8000), deck=(35, 40), portraits=None):
    """Desenha o HUD numa imagem 320x240 (Pillow). ``portraits``: {lado: Image} opcional."""
    from PIL import Image, ImageDraw

    img = (base.copy() if base is not None else Image.new('RGB', (SCREEN_W, SCREEN_H), (40, 40, 40))).convert('RGB')
    draw = ImageDraw.Draw(img)

    def text(value, center, color=WHITE):
        cx, top = center
        x = cx - text_width(value) // 2
        for char in value:
            for gx, gy, gw, gh in glyph_rects(char):
                draw.rectangle([x + gx, top + gy, x + gx + gw - 1, top + gy + gh - 1], fill=color)
            x += len(FONT[char][0]) + 1

    for index in (1, 0):
        side = SIDES[index]
        for quad in side.bands:
            draw.polygon(quad, fill=side.color)
        x0, y0, x1, y1 = side.bar
        draw.rectangle([x0, y0, x1, y1], fill=side.dim)
        fill = bar_fill(side, lp[index], start[index])
        if fill:
            if side.fill_from_right:
                draw.rectangle([x1 - fill + 1, y0, x1, y1], fill=WHITE)
            else:
                draw.rectangle([x0, y0, x0 + fill - 1, y1], fill=WHITE)
        text(lp_text(lp[index]), side.lp_center)
        text(str(deck[index]), side.deck_center)
        cx, cy, h = side.diamond
        draw.polygon([(cx, cy - h - 1), (cx + h + 1, cy), (cx, cy + h + 1), (cx - h - 1, cy)], fill=WHITE)
        picture = (portraits or {}).get(index)
        if picture is None:
            draw.polygon([(cx, cy - h + 1), (cx + h - 1, cy), (cx, cy + h - 1), (cx - h + 1, cy)], fill=side.dim)
        else:
            size = 2 * h
            face = picture.convert('RGB').resize((size, size))
            mask = Image.new('L', (size, size), 0)
            ImageDraw.Draw(mask).polygon([(h, 1), (size - 2, h), (h, size - 2), (1, h)], fill=255)
            img.paste(face, (cx - h, cy - h), mask)
    return img
