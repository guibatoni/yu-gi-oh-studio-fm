"""Teste de ícone Deus no BIN PS1: um glifo 16x16 na fonte do boot.

A célula 0x29 não consta dos 41 ícones documentados e é usada SOMENTE
quando estiver integralmente zerada na imagem de origem. Se estiver ocupada,
não gravamos. Esta prova é no TEXTO da carta, não implementa tipo God 24.
"""
from __future__ import annotations

import struct
from pathlib import Path

from .core import ModError
from .deep_extract import exe_pos, BANK_DESC, STRING_TABLE

WA_SECTOR = 2048
ICON_SHEET_SECTOR = 0x16A0
ICON_PALETTE_SECTOR = 0x16C0
GLYPH_INDEX = 0x29
# func_80035E20: para 0x29, u=128, v=128; palette x=0x200,y=0xFC.
GLYPH_U = 128
GLYPH_V = 128
WIDTH = HEIGHT = 16
ROW_BYTES = 128
PALETTE_OFFSET = ICON_PALETTE_SECTOR * WA_SECTOR + 4 * 512
TOKEN_BYTES = bytes((0xF8, 0x0B, GLYPH_INDEX))


def glyph_rows(wa: bytes) -> list[bytes]:
    sheet = ICON_SHEET_SECTOR * WA_SECTOR
    offsets = [sheet + (GLYPH_V + y) * ROW_BYTES + GLYPH_U // 2
               for y in range(HEIGHT)]
    if len(wa) < max(offsets) + 8:
        raise ModError('WA_MRG.MRG não contém a segunda página de ícones do boot.')
    return [wa[offset:offset + 8] for offset in offsets]


def patch_god_glyph(wa: bytes, image_path: Path) -> tuple[bytes, dict]:
    """Pinta apenas um slot comprovadamente vazio, com a paleta do próprio jogo."""
    if PALETTE_OFFSET + 32 > len(wa):
        raise ModError('Paleta original de ícones ausente no WA_MRG.MRG.')
    try:
        from PIL import Image
    except ImportError as exc:
        raise ModError('A exportação do ícone God necessita de Pillow.') from exc
    image_path = Path(image_path)
    try:
        with Image.open(image_path) as source:
            source.load()
            rgba = source.convert('RGBA')
            if rgba.size != (WIDTH, HEIGHT):
                raise ModError('O ícone Deus deve ser PNG 16x16.')
            pixels = list(rgba.getdata())
    except OSError as exc:
        raise ModError('Não foi possível ler o PNG Deus usado no teste.') from exc
    palette = [struct.unpack_from('<H', wa, PALETTE_OFFSET + 2*i)[0]
               for i in range(16)]
    available = [i for i in range(1, 16) if palette[i] != 0]
    if not available:
        raise ModError('Paleta de ícones está vazia; não há cores para o teste.')
    def rgb(value):
        return ((value & 31) * 255 // 31,
                ((value >> 5) & 31) * 255 // 31,
                ((value >> 10) & 31) * 255 // 31)
    rgb_palette = {index: rgb(palette[index]) for index in available}
    def closest(pixel):
        if pixel[3] < 128:
            return 0
        return min(available, key=lambda i: sum(
            (pixel[ch] - rgb_palette[i][ch]) ** 2 for ch in range(3)))
    idx = [closest(pixel) for pixel in pixels]
    if not any(idx):
        raise ModError('Ícone Deus sem pixels visíveis após aplicar a paleta.')
    desired = []
    for y in range(HEIGHT):
        row = bytes(idx[y*16 + x] | (idx[y*16 + x+1] << 4)
                    for x in range(0, 16, 2))
        desired.append(row)
    before = glyph_rows(wa)
    if before == desired:
        return wa, {'codigo':'F8 0B 29','slot':GLYPH_INDEX,
                     'status':'ja_presente','offsets_wa':[]}
    if any(any(row) for row in before):
        raise ModError('Célula 0x29 não está vazia nesta imagem: não é seguro '
                       'substituir um ícone/gráfico do mod.')
    out = bytearray(wa)
    changes = []
    for y, row in enumerate(desired):
        off = ICON_SHEET_SECTOR * WA_SECTOR + (GLYPH_V+y)*ROW_BYTES + GLYPH_U//2
        out[off:off+8] = row
        changes.append(off)
    if glyph_rows(out) != desired:
        raise ModError('Falha ao reler o ícone Deus gravado no WA.')
    return bytes(out), {'codigo':'F8 0B 29','slot':GLYPH_INDEX,
                        'status':'glifo_inserido_em_celula_vazia',
                        'offsets_wa':changes,
                        'aviso':'Teste apenas em texto da carta; não troca o ícone '
                                'do tipo na interface nem implementa God 24.'}


def patch_god_icon_description(exe: bytes, card_id: int) -> tuple[bytes, dict]:
    """Troca 3 GLIFOS iniciais por ícone no BIN de TESTE, sem mudar comprimento.

    Os textos e descrições no projeto continuam intocados. A exigência de
    slot exclusivo protege textos compartilhados. A versão original do jogo
    não é sobrescrita: esta função só recebe cópias em memória.
    """
    if isinstance(card_id, bool) or not isinstance(card_id, int) or not 1 <= card_id <= 722:
        raise ModError('Teste de Deus exige carta original com ID 1–722.')
    if exe[:8] != b'PS-X EXE':
        raise ModError('SLUS inválido para testar ícone Deus.')
    ptr = exe_pos(STRING_TABLE, exe, 0x400 * 2)
    offsets = [struct.unpack_from('<H',exe,ptr+2*i)[0]
               for i in range(0x100,0x400)]
    offset = offsets[card_id]
    if not offset or offsets.count(offset) != 1:
        raise ModError('Descrição da carta sem espaço exclusivo para teste de ícone God.')
    ceiling = min((x for x in offsets if x > offset), default=0x10000)
    start = exe_pos(BANK_DESC+offset, exe, 3)
    if start + 3 > exe_pos(BANK_DESC+ceiling,exe,0):
        raise ModError('Descrição curta demais para inserir ícone Deus.')
    first = exe[start:start+3]
    if first == TOKEN_BYTES:
        return exe, {'carta_id':card_id,'status':'ja_presente',
                     'codigo':'F8 0B 29','offset_slus':f'0x{start:X}'}
    if len(first) != 3 or any(b >= 0xF0 for b in first) or 0xFF in first:
        raise ModError('A descrição começa com controles especiais ou menos '
                       'de três caracteres; o teste God foi bloqueado.')
    # O restante do texto é preservado byte a byte. Os 3 caracteres iniciais
    # são substituídos SOMENTE na cópia de teste, com permissão explícita.
    patched = bytearray(exe)
    patched[start:start+3] = TOKEN_BYTES
    if patched[start:start+3] != TOKEN_BYTES:
        raise ModError('Falha na verificação do código do ícone Deus.')
    return bytes(patched), {
        'carta_id':card_id,'status':'icone_inserido_no_texto_do_card',
        'codigo':'F8 0B 29','offset_slus':f'0x{start:X}',
        'bytes_substituidos':first.hex(),
        'aviso':'Primeiros 3 caracteres da descrição foram substituídos apenas '
                'na cópia do BIN. Tipo original permanece inalterado.'
    }


def god_icon_asset() -> Path:
    import sys
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return root / 'assets' / 'icons' / 'god.png'
