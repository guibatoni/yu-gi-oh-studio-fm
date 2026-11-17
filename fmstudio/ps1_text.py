"""Descriptions and custom text icons for the Drop x15 PS1 profile."""
from __future__ import annotations

import struct
import unicodedata

from .core import ModError
from .deep_extract import BANK_DESC, STRING_TABLE, exe_pos, glyph_map
from .ps1_content import _encode_description, description_slot
from .ps1_god24_display import GOLD_PALETTE, ICON_ROWS
from .ps1_god_icon import PALETTE_OFFSET, ROW_BYTES, decode_icon_png, god_glyph_rows, god_icon_asset
from .ps1_runtime import BANK_END, DUEL_STATE
from .richtext import CUSTOM_ICONS
from .tables import CARD_COUNT

# Matches DescriptionIcon in tools/ps1/hooks.S. God uses the v1.4.24 slot.
ICON_CODES = {name: 0x40 + index for index, name in enumerate(
    name for name in CUSTOM_ICONS if name not in ('god', 'vinculo_vida', 'restaurar_lp'))}
ICON_CODES['god'] = 0x31
MAX_ROWS, COLUMN_WIDTH = 9, 21


def _measure(raw: bytes) -> set[int]:
    """Count the native viewer's 8-pixel columns and return sprite codes."""
    index, rows, width = 0, 1, 0
    icons = set()
    while index < len(raw):
        op = raw[index]
        if op == 0xF8:
            command, operand = raw[index + 1:index + 3]
            index += 3
            if command == 0x0A:
                continue
            icons.add(operand)
            size = 2
        elif op == 0xFE:
            index += 1
            rows += 1
            width = 0
            continue
        else:
            index += 1
            size = 1
        if width + size > COLUMN_WIDTH:
            rows += 1
            width = 0
        width += size
    if rows > MAX_ROWS:
        raise ModError(f'Descrição ocupa {rows} linhas. A tela PS1 comporta {MAX_ROWS} de {COLUMN_WIDTH} colunas.')
    return icons


def patch_descriptions(exe: bytes, changes: dict[int, str], cards: dict,
                       *, start: int = DUEL_STATE, end: int = BANK_END) -> tuple[bytes, list[dict], set[str], list[str]]:
    """Reuse original string slots and allocate larger strings from the verified bank tail."""
    if not DUEL_STATE <= start <= end <= BANK_END:
        raise ModError('Área de descrições PS1 fora do banco de texto.')
    cmap, _ = glyph_map(exe)
    font = set(cmap.values())
    out = bytearray(exe)
    rows, pending, needed = [], [], set()
    icon_names = {code: name for name, code in ICON_CODES.items()}
    for cid, value in sorted(changes.items()):
        simplified = set()

        def normalize(text):
            result = []
            for char in text:
                fallback = ''.join(base for base in unicodedata.normalize('NFD', char)
                                   if not unicodedata.combining(base))
                if char not in font and fallback and all(base in font for base in fallback):
                    simplified.add(char)
                    result.append(fallback)
                else:
                    result.append(char)
            return ''.join(result)

        try:
            if not 1 <= cid <= CARD_COUNT:
                raise ModError('Edição PS1 requer carta original.')
            raw = _encode_description(value.replace('\r\n', '\n'), cmap, cards,
                                      icon_codes=ICON_CODES, normalize=normalize)
            icons = _measure(raw)
            try:
                offset, capacity = description_slot(exe, cid)
            except ModError:
                offset, capacity = 0, -1
            moved = len(raw) > capacity
            if moved:
                size = len(raw) + 1
                if start + size > end:
                    raise ModError('O espaço para descrições maiores deste BIN está cheio.')
                offset = exe_pos(start, exe, size)
                if any(exe[offset:offset+size]):
                    raise ModError('Área reservada de descrição já contém texto ou código.')
                pointer = exe_pos(STRING_TABLE + 2 * (0x100 + cid), exe, 2)
                struct.pack_into('<H', out, pointer, start - BANK_DESC)
                start += size
            raw += b'\xff'
            out[offset:offset+len(raw)] = raw
            names = {icon_names[code] for code in icons if code in icon_names}
            rows.append({'id': cid, 'offset_exe': offset, 'bytes': len(raw),
                         'realocada': moved, 'icones': sorted(names),
                         'acentos_simplificados': ''.join(sorted(simplified))})
            needed.update(names)
        except ModError as exc:
            pending.append(f'#{cid}: descrição: {exc}')
    return bytes(out), rows, needed, pending


def _indexed_sprite(name: str) -> tuple[list[bytes], bytes]:
    """Give each icon a dedicated 4bpp CLUT, with index zero transparent."""
    pixels = decode_icon_png(god_icon_asset().with_name(name + '.png'))
    colors = [0]
    indices = []
    for red, green, blue, alpha in pixels:
        if alpha < 128:
            indices.append(0)
            continue
        rgb = ((red >> 3) | ((green >> 3) << 5) | ((blue >> 3) << 10)) or 1
        if rgb not in colors:
            colors.append(rgb)
        indices.append(colors.index(rgb))
    if not 1 < len(colors) <= 16:
        raise ModError(f'Ícone {name} exige até 15 cores opacas e transparência.')
    rows = [bytes(indices[i] | indices[i+1] << 4 for i in range(y*16, y*16 + 16, 2))
            for y in range(16)]
    return rows, struct.pack('<16H', *colors, *([0] * (16 - len(colors))))


def patch_icons(wa: bytes, icons: set[str]) -> bytes:
    out = bytearray(wa)
    for name in sorted(icons):
        if name == 'god':
            positions = ICON_ROWS
            rows = god_glyph_rows(out, god_icon_asset(), palette_offset=GOLD_PALETTE)
        else:
            index = ICON_CODES[name] - 0x40
            first = ICON_ROWS[0] + (index + 1) * 8
            positions = tuple(first + y * ROW_BYTES for y in range(16))
            rows, colors = _indexed_sprite(name)
            x, y = (656 + index*16, 251) if index < 7 else (640 + (index-7)*16, 255)
            palette = PALETTE_OFFSET + (y - 252)*512 + (x - 512)*2
            if out[palette:palette+len(colors)] not in (bytes(len(colors)), colors):
                raise ModError(f'A paleta reservada para o ícone {name} está ocupada.')
            out[palette:palette+len(colors)] = colors
        for pos, row in zip(positions, rows):
            if out[pos:pos+8] not in (b'\0'*8, row):
                raise ModError(f'A célula de textura para o ícone {name} está ocupada.')
            out[pos:pos+8] = row
    return bytes(out)
