"""Papel de parede do menu principal (PS1, SU.MRG).

O fundo do menu principal é a "parede": uma textura 4 bpp de 256x240 px com
16 cores, desenhada pelo overlay do menu (MainMenu_DrawFrontendBackground) em
faixas de 64 px com tpage 15 (VRAM x=960..1023, y=0..239) e CLUT em (0,244).
A tela tem 320 px de largura: a textura se repete a cada 256 px, então as 64
primeiras colunas aparecem de novo à direita.

Pacote do menu em DATA/SU.MRG (layout do decomp, conferido por SHA-256):

* setores 64-95: 32 retângulos 64x16 (halfwords) preenchendo VRAM
  (896,0)-(1023,255), descendo 16 linhas por setor e indo 64 px à direita a
  cada 256 linhas. A parede ocupa os setores 80-95 (x=960);
* setores 96-97: bloco de paletas enviado para (0,240) com 256x8 halfwords;
  a CLUT da parede (linha 244) fica no começo do setor 97.

Só dados mudam (nenhum código). Dois modos no Studio:

* ``imagem``: uma imagem ocupa a parede inteira (recortada para 256x240);
* ``ladrilho``: uma imagem pequena repetida pela parede.

O resultado é reduzido a 16 cores. A cor 0x0000 é transparente no PS1, então
o preto vira 0x8000 (preto opaco).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .core import ModError

SU_PATH = 'DATA/SU.MRG'
SECTOR = 0x800
STAGE1 = (64, 96, 'a41dc530ac406b08297a15d7d75bcc43e1a642744315aeaf83cd8935e8783376')
STAGE2 = (96, 98, '26704e08cfa8e4504e20c8d51e7cb860c985fd8b7e4c885b1c626c6207fa1de8')
WALL_SECTOR = 80
PALETTE_OFFSET = 97 * SECTOR            # linha 244 do bloco de paletas (0,240)
WIDTH, HEIGHT = 256, 240
ROW_BYTES = WIDTH // 2                  # 4 bpp
ROWS_PER_SECTOR = SECTOR // ROW_BYTES   # 16
SETTINGS_KEY = 'ps1_papel_parede_menu'
IMAGE_NAME = 'papel_parede_menu.png'
MODES = ('imagem', 'ladrilho')
SCREEN_WIDTH = 320


def settings(project) -> dict:
    raw = (getattr(project, 'metadata', None) or {}).get(SETTINGS_KEY) or {}
    mode = raw.get('modo') if raw.get('modo') in MODES else 'imagem'
    return {'ativado': bool(raw.get('ativado')), 'modo': mode,
            'origem': str(raw.get('origem') or ''),
            'ladrilho': _tile_size(raw.get('ladrilho', 64))}


def _tile_size(value) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = 64
    return min(256, max(8, size))


def image_path(project) -> Path:
    return Path(project.folder) / 'menu' / IMAGE_NAME


def compose(source, mode: str, tile: int = 64):
    """Imagem RGB 256x240 da parede a partir da imagem do usuário."""
    from PIL import Image, ImageOps
    if mode not in MODES:
        raise ModError('Papel de parede: modo inválido.')
    with Image.open(source) as opened:
        picture = opened.convert('RGBA')
    background = Image.new('RGBA', picture.size, (0, 0, 0, 255))
    picture = Image.alpha_composite(background, picture).convert('RGB')
    if mode == 'imagem':
        return ImageOps.fit(picture, (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    tile = _tile_size(tile)
    scale = tile / max(picture.size)
    size = (max(1, round(picture.width * scale)), max(1, round(picture.height * scale)))
    piece = picture.resize(size, Image.Resampling.LANCZOS)
    wall = Image.new('RGB', (WIDTH, HEIGHT))
    for y in range(0, HEIGHT, piece.height):
        for x in range(0, WIDTH, piece.width):
            wall.paste(piece, (x, y))
    return wall


def quantize(wall):
    """(índices 256x240, paleta de 16 cores RGB) reduzidos para o PS1."""
    from PIL import Image
    if wall.size != (WIDTH, HEIGHT):
        raise ModError('Papel de parede: a imagem final precisa ter 256x240 px.')
    # 15 bits por cor antes de escolher a paleta: o PS1 não mostra mais que isso.
    reduced = wall.convert('RGB').point(lambda v: (v >> 3) << 3)
    indexed = reduced.quantize(colors=16, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    palette = indexed.getpalette()[:48]
    palette += [0] * (48 - len(palette))
    colors = [tuple(palette[i * 3:i * 3 + 3]) for i in range(16)]
    return indexed, colors


def preview(wall):
    """Como a tela do menu mostra a parede: 320 px, repetindo a cada 256."""
    from PIL import Image
    indexed, colors = quantize(wall)
    shown = indexed.convert('RGB')
    screen = Image.new('RGB', (SCREEN_WIDTH, HEIGHT))
    screen.paste(shown, (0, 0))
    screen.paste(shown.crop((0, 0, SCREEN_WIDTH - WIDTH, HEIGHT)), (WIDTH, 0))
    return screen


def _bgr555(rgb) -> int:
    r, g, b = (c >> 3 for c in rgb)
    value = r | g << 5 | b << 10
    return value or 0x8000                  # 0x0000 seria transparente


def encode(wall) -> tuple[bytes, bytes]:
    """(16 setores da parede, 32 bytes da CLUT)."""
    indexed, colors = quantize(wall)
    pixels = indexed.tobytes()
    texture = bytearray(WIDTH * HEIGHT // 2)
    for y in range(HEIGHT):
        row = pixels[y * WIDTH:(y + 1) * WIDTH]
        for x in range(0, WIDTH, 2):
            texture[y * ROW_BYTES + x // 2] = (row[x] & 15) | (row[x + 1] & 15) << 4
    clut = b''.join(_bgr555(color).to_bytes(2, 'little') for color in colors)
    return bytes(texture), clut


def verify_source(su: bytes) -> None:
    for start, end, digest in (STAGE1, STAGE2):
        if hashlib.sha256(su[start * SECTOR:end * SECTOR]).hexdigest() != digest:
            raise ModError('Papel de parede: o SU.MRG deste disco não é o original conferido; '
                           'o fundo do menu não foi alterado.')


def apply(su: bytes, wall) -> tuple[bytes, dict]:
    verify_source(su)
    texture, clut = encode(wall)
    out = bytearray(su)
    base = WALL_SECTOR * SECTOR
    for y in range(HEIGHT):
        # A sequência linear de linhas coincide com os setores 80-95 (16 linhas cada).
        out[base + y * ROW_BYTES: base + (y + 1) * ROW_BYTES] = texture[y * ROW_BYTES:(y + 1) * ROW_BYTES]
    out[PALETTE_OFFSET:PALETTE_OFFSET + len(clut)] = clut
    return bytes(out), {'status': 'aplicado', 'arquivo': SU_PATH,
                        'setores': [WALL_SECTOR, WALL_SECTOR + HEIGHT // ROWS_PER_SECTOR - 1, 97],
                        'cores': 16, 'sha256_textura': hashlib.sha256(texture).hexdigest(),
                        'validado_epsxe': False}


def inspect(su: bytes, wall) -> bool:
    texture, clut = encode(wall)
    base = WALL_SECTOR * SECTOR
    return (su[base:base + len(texture)] == texture and
            su[PALETTE_OFFSET:PALETTE_OFFSET + len(clut)] == clut)


def save(project, *, enabled: bool, mode: str, source: str = '', tile: int = 64) -> dict:
    """Guarda a parede já composta (PNG 256x240) na pasta do projeto."""
    if mode not in MODES:
        raise ModError('Papel de parede: modo inválido.')
    target = image_path(project)
    if source and Path(source).is_file():
        wall = compose(source, mode, tile)
        target.parent.mkdir(parents=True, exist_ok=True)
        wall.save(target)
    if enabled and not target.exists():
        raise ModError('Papel de parede: importe uma imagem antes de ativar.')
    clean = {'ativado': bool(enabled), 'modo': mode, 'ladrilho': _tile_size(tile),
             'origem': str(source or settings(project)['origem'])}
    before = project.metadata
    project.metadata = {**before, SETTINGS_KEY: clean}
    try:
        project.save()
    except OSError:
        project.metadata = before
        raise
    return clean


def requested_wall(project):
    """A parede a gravar no BIN, ou None se desativado."""
    from PIL import Image
    if not settings(project)['ativado']:
        return None
    path = image_path(project)
    if not path.exists():
        raise ModError('Papel de parede do menu ativado, mas a imagem do projeto sumiu. '
                       'Importe de novo na aba "Fundo do menu".')
    with Image.open(path) as opened:
        wall = opened.convert('RGB')
    if wall.size != (WIDTH, HEIGHT):
        raise ModError('Papel de parede: a imagem salva não tem 256x240 px; importe de novo.')
    return wall
