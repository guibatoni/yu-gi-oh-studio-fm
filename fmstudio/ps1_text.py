"""Descriptions and custom text icons for the Drop x15 PS1 profile."""
from __future__ import annotations

import hashlib
import struct
import unicodedata

from .core import ModError
from .deep_extract import BANK_DESC, STRING_TABLE, exe_pos, glyph_map
from .ps1_content import _encode_description, description_slot
from .ps1_god24_display import GOLD_PALETTE, ICON_ROWS
from .ps1_god_icon import PALETTE_OFFSET, ROW_BYTES, decode_icon_png, god_glyph_rows, god_icon_asset
from .ps1_runtime import BANK_END, DUEL_STATE, _runtime_bundle
from .richtext import CUSTOM_ICONS
from .tables import CARD_COUNT

# Matches DescriptionIcon in tools/ps1/hooks.S. God uses the v1.4.24 slot.
ICON_CODES = {name: 0x40 + index for index, name in enumerate(
    name for name in CUSTOM_ICONS if name != 'god')}
ICON_CODES['god'] = 0x31
# 0x49 (célula u=160, CLUT 672,255) é do ícone da Guardian Star Supreme
# (ps1_supreme). O vínculo de vida usa 0x4B; o runtime aceita 0x40..0x4B.
SUPREME_ICON_CODE = 0x49
ICON_CODES['vinculo_vida'] = 0x4B
assert SUPREME_ICON_CODE not in ICON_CODES.values()
MAX_ROWS, COLUMN_WIDTH = 9, 21
MAX_TEXT_BYTES = 2048  # Includes the terminator read by the BIN verifier.
COLOR_CONTROL = b'\xf8\x0a'
ICON_CONTROL = b'\xf8\x0b'
PUNCTUATION = str.maketrans({'–': '-', '—': '-', '−': '-', '’': "'", '‘': "'",
                            '“': '"', '”': '"', '…': '...', '×': 'x', '\xa0': ' ',
                            # alemão/italiano traduzidos: letras sem glifo na fonte americana
                            'ß': 'ss', 'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
                            '«': '"', '»': '"', '„': '"'})
TEXT_ICON_LABELS = {}  # Glifos LP: restaurar_lp 0x4A, vinculo_vida 0x4B (0x49 = Supreme).


def _text_tokens(raw: bytes):
    index = 0
    while index < len(raw):
        size = 3 if raw[index] == 0xF8 else 1
        if index + size > len(raw):
            raise ModError('Comando de descrição PS1 incompleto.')
        yield raw[index:index + size]
        index += size


def _columns(token: bytes) -> int:
    if token[0] != 0xF8:
        return 1
    return 0 if token[1] == 0x0A else 2


def _cursor(rows, column, token):
    if token == b'\xfe':
        return rows + 1, 0
    width = _columns(token)
    if column + width > COLUMN_WIDTH:
        return rows + 1, width
    return rows, column + width


def _layout(raw: bytes) -> tuple[int, set[int]]:
    rows, column = 1, 0
    icons = set()
    for token in _text_tokens(raw):
        if token[:2] == b'\xf8\x0b':
            icons.add(token[2])
        rows, column = _cursor(rows, column, token)
    return rows, icons


def _measure(raw: bytes) -> set[int]:
    """Count the native viewer's 8-pixel columns and return sprite codes."""
    rows, icons = _layout(raw)
    if rows > MAX_ROWS:
        raise ModError(f'Descrição ocupa {rows} linhas. A tela PS1 comporta {MAX_ROWS} de {COLUMN_WIDTH} colunas.')
    if len(raw) + 1 > MAX_TEXT_BYTES:
        raise ModError(f'Os comandos da descrição excedem {MAX_TEXT_BYTES} bytes no PS1.')
    return icons


def _reflow(raw: bytes) -> bytes:
    """Collapse manual line breaks and move whole words to the next line."""
    words = []
    word = []
    for token in _text_tokens(raw):
        if token in (b'\x00', b'\xfe'):
            if word:
                words.append(word)
                word = []
        else:
            word.append(token)
    if word:
        words.append(word)

    out = bytearray()
    column = 0
    for word in words:
        width = sum(map(_columns, word))
        if width and column:
            if column + 1 + min(width, COLUMN_WIDTH) <= COLUMN_WIDTH:
                out.append(0)
                column += 1
            else:
                out.append(0xFE)
                column = 0
        for token in word:
            wrapped, column = _cursor(0, column, token)
            if wrapped and token.startswith(ICON_CONTROL):
                out.append(0xFE)
            out.extend(token)
    return bytes(out)


def _wrap_icons(raw: bytes) -> bytes:
    """The native renderer wraps glyphs but draws a two-column icon in place."""
    column = 0
    out = bytearray()
    for token in _text_tokens(raw):
        wrapped, column = _cursor(0, column, token)
        if wrapped and token.startswith(ICON_CONTROL):
            out.append(0xFE)
        out.extend(token)
    return bytes(out)


def compile_description(value: str, cmap: dict, cards: dict) -> tuple[bytes, str, bool]:
    """Encode the full text, reflowing only when the original layout is too tall."""
    font = set(cmap.values())
    simplified = set()

    def normalize(text):
        result = []
        for char in text:
            fallback = ''.join(base for base in unicodedata.normalize('NFKD', char.translate(PUNCTUATION))
                               if not unicodedata.combining(base))
            if char not in font and fallback and all(base in font for base in fallback):
                simplified.add(char)
                result.append(fallback)
            else:
                result.append(char)
        return ''.join(result)

    raw = _encode_description(value.replace('\r\n', '\n').replace('\r', '\n'),
                              cmap, cards, icon_codes=ICON_CODES, normalize=normalize)
    reflowed = _reflow(raw) if _layout(raw)[0] > MAX_ROWS else _wrap_icons(raw)
    return reflowed, ''.join(sorted(simplified)), reflowed != raw


def compile_compatible_description(value: str, cmap: dict, cards: dict):
    """Spell out Studio icons with no mapped PS1 sprite when necessary."""
    try:
        return (*compile_description(value, cmap, cards), False)
    except ModError as original:
        adapted = value
        for icon, label in TEXT_ICON_LABELS.items():
            adapted = adapted.replace('{icon:' + icon + '}', label)
        if adapted == value:
            raise
        try:
            return (*compile_description(adapted, cmap, cards), True)
        except ModError as exc:
            raise original from exc


def _preview_prefix(raw: bytes, dots: bytes, budget: int) -> bytes | None:
    rows, column, used, color = 1, 0, 0, 0
    prefix = []
    for token in _text_tokens(raw):
        next_row, next_column = _cursor(rows, column, token)
        next_color = token[2] if token.startswith(COLOR_CONTROL) else color
        length = used + len(token) + len(dots) + (3 if next_color else 0)
        if (length > budget or next_row > MAX_ROWS
                or next_row == MAX_ROWS and next_column > COLUMN_WIDTH - len(dots)):
            # Avoid ending in the middle of a later word when a whole word fits.
            if token not in (b'\x00', b'\xfe') and _columns(token):
                for gap in range(len(prefix) - 1, 0, -1):
                    if prefix[gap] in (b'\x00', b'\xfe'):
                        prefix = prefix[:gap]
                        break
            break
        prefix.append(token)
        rows, column = next_row, next_column
        used += len(token)
        color = next_color
    while prefix and (prefix[-1] in (b'\x00', b'\xfe') or _columns(prefix[-1]) == 0):
        prefix.pop()
    if not prefix:
        return None
    last_color = next((token[2] for token in reversed(prefix) if token.startswith(COLOR_CONTROL)), 0)
    return b''.join(prefix) + dots + (COLOR_CONTROL + b'\x00' if last_color else b'')


def preview_description(raw: bytes, cmap: dict, byte_limit: int) -> bytes | None:
    """Fit the most readable prefix, using the original colors/icons when space allows."""
    budget = min(byte_limit, MAX_TEXT_BYTES - 1)
    if budget <= 0 or (len(raw) <= budget and _layout(raw)[0] <= MAX_ROWS):
        return None
    dot = next((code for code, char in cmap.items() if char == '.'), None)
    tokens = list(_text_tokens(raw))
    text_codes = {code for code, char in cmap.items() if char.isalnum()}
    first_line_text = next((i for i, token in enumerate(tokens)
                            if len(token) == 1 and token[0] not in (0, 0xFE)), len(tokens))
    variants = [raw]
    if first_line_text < len(tokens):
        variants.append(_reflow(b''.join(t for t in tokens if not t.startswith(COLOR_CONTROL))))
        variants.append(_reflow(b''.join(t for i, t in enumerate(tokens)
                                         if not t.startswith(COLOR_CONTROL)
                                         and (i >= first_line_text or not t.startswith(ICON_CONTROL)))))
    candidates = []
    for variant in dict.fromkeys(variants):
        if len(variant) <= budget and _layout(variant)[0] <= MAX_ROWS:
            candidates.append(variant)
        elif dot is not None:
            prefix = _preview_prefix(variant, bytes([dot]) * 3, budget)
            if prefix:
                candidates.append(prefix)

    def readable(value):
        return sum(len(t) == 1 and t[0] in text_codes for t in _text_tokens(value))

    best = max(candidates, key=readable, default=None)
    if best and (readable(best) or not readable(raw)):
        return best
    return None


def description_regions(plan, *, has_lp: bool) -> list[tuple[int, int]]:
    """Find free intervals in the text bank without taking space from native code."""
    from .ps1_mod import LP_CODE, LP_BANK_END

    bundle = _runtime_bundle(plan)
    occupied = [(bundle.RUNTIME_RANK_HUD_BASE, bundle.RUNTIME_RANK_HUD_END)]
    for enabled, section in (
        (plan.grave_filters, 'RUNTIME_GRAVE_FILTERS'),
        (plan.entry_markers, 'RUNTIME_MARKERS'),
        (plan.mod_features, 'RUNTIME_MOD'),
        (plan.password_prefix is not None and plan.capacity == CARD_COUNT, 'RUNTIME_PASSWORD'),
        (plan.gameplay, 'RUNTIME_EXT'),
    ):
        if enabled:
            occupied.append((getattr(bundle, section + '_BASE'), getattr(bundle, section + '_END')))
    if has_lp:
        occupied.append((LP_CODE, LP_BANK_END))
    regions = []
    start = plan.data_end
    for lo, hi in sorted(occupied):
        if start < lo:
            regions.append((start, lo))
        start = max(start, hi)
    if start < BANK_END:
        regions.append((start, BANK_END))
    return regions


def _vacant_slot(exe: bytes) -> int | None:
    """Read the original empty description shared by unused IDs."""
    table = exe_pos(STRING_TABLE + 2 * 0x100, exe, 2)
    pointer = struct.unpack_from('<H', exe, table)[0]
    if pointer:
        at = exe_pos(BANK_DESC + pointer, exe, 1)
        if exe[at] == 0xFF:
            return at
    return None


def patch_descriptions(exe: bytes, changes: dict[int, str], cards: dict,
                       *, start: int = DUEL_STATE, end: int = BANK_END,
                       regions=None, preview_new: bool = False) -> tuple[bytes, list[dict], set[str], list[str]]:
    """Place valid edits in existing slots or free intervals and share identical texts."""
    from .ps1_expansion import PS1_CARD_CAPACITY

    available = []
    previous_end = DUEL_STATE
    for lo, hi in sorted(regions if regions is not None else [(start, end)]):
        if not previous_end <= lo <= hi <= BANK_END:
            raise ModError('Área de descrições PS1 fora do banco de texto.')
        previous_end = hi
        at = exe_pos(lo, exe, hi - lo)
        if hi > lo and not any(exe[at:at + hi - lo]):
            available.append([at, at + hi - lo])
    cmap, _ = glyph_map(exe)
    out = bytearray(exe)
    rows, pending, deferred, needed = [], {}, [], set()
    icon_names = {code: name for name, code in ICON_CODES.items()}
    empty = _vacant_slot(exe)
    shared = {b'': empty} if empty is not None else {}

    def allocate(raw):
        if raw in shared:
            return shared[raw]
        size = len(raw) + 1
        slot = min((pair for pair in available if pair[1] - pair[0] >= size),
                   key=lambda pair: pair[1] - pair[0], default=None)
        if slot is None:
            raise ModError('O espaço para descrições maiores deste BIN está cheio.')
        at = slot[0]
        slot[0] += size
        shared[raw] = at
        return at

    def write_text(cid, raw, offset, relocated, icons, simplified, reflowed, reason=''):
        if relocated:
            pointer = exe_pos(STRING_TABLE + 2 * (0x100 + cid), exe, 2)
            struct.pack_into('<H', out, pointer, offset - exe_pos(BANK_DESC, exe))
        out[offset:offset + len(raw) + 1] = raw + b'\xff'
        shared.setdefault(raw, offset)
        names = {icon_names[code] for code in icons if code in icon_names}
        row = {'id': cid, 'offset_exe': offset, 'bytes': len(raw) + 1,
               'realocada': relocated, 'icones': sorted(names),
               'acentos_simplificados': simplified, 'quebras_reorganizadas': reflowed,
               'sha256_texto': hashlib.sha256(raw).hexdigest()}
        if reason:
            row.update(resumida=True, motivo=reason)
        rows.append(row)
        needed.update(names)

    for cid, value in sorted(changes.items()):
        try:
            if not 1 <= cid <= PS1_CARD_CAPACITY:
                raise ModError('Edição PS1 requer ID de 1 a 740.')
            reason = ''
            if preview_new and cid > CARD_COUNT:
                raw, simplified, reflowed, adapted = compile_compatible_description(value, cmap, cards)
                if adapted:
                    reason = 'Ícone sem sprite PS1 foi gravado como texto.'
            else:
                raw, simplified, reflowed = compile_description(value, cmap, cards)
            try:
                offset, capacity = description_slot(exe, cid)
            except ModError:
                offset, capacity = 0, -1
            relocated = len(raw) > capacity
            try:
                icons = _measure(raw)
                if relocated:
                    offset = allocate(raw)
            except ModError as exc:
                if not preview_new or cid <= CARD_COUNT:
                    raise
                deferred.append((cid, raw, simplified, reflowed, ' '.join(filter(None, (reason, str(exc))))))
                continue
            write_text(cid, raw, offset, relocated, icons, simplified, reflowed, reason)
        except ModError as exc:
            pending[cid] = str(exc)

    # Use the remaining space only after all full descriptions were tried.
    previews = {}
    for cid, raw, simplified, reflowed, reason in deferred:
        preview = previews.get(raw)
        if preview is None:
            budget = max((hi - lo - 1 for lo, hi in available), default=0)
            preview = preview_description(raw, cmap, budget)
        if preview is None:
            pending[cid] = reason
            continue
        write_text(cid, preview, allocate(preview), True, _measure(preview),
                   simplified, reflowed, reason)
        previews[raw] = preview
    return (bytes(out), sorted(rows, key=lambda row: row['id']), needed,
            [f'#{cid}: descrição: {reason}' for cid, reason in sorted(pending.items())])


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
    if len(colors) > 16:
        # Cada glifo personalizado possui sua própria célula e CLUT de 16
        # posições, verificadas em patch_icons antes da gravação. Se a arte
        # tiver >15 cores visíveis, quantizar sem tocar CLUTs existentes.
        from .ps1_image_optimizer import render_resource
        from .ps1_image_optimizer import _pillow
        if _pillow() is None:
            raise ModError(f'Ícone {name} tem mais de 15 cores; instale Pillow '
                           'para quantização ou envie PNG indexado.')
        optimized = render_resource(
            god_icon_asset().with_name(name + '.png'), (0,) + (1,) * 15,
            (16, 16), {'mode':'automatico','palette':'personalizada',
                       'dither':'nenhum'}, private_clut=True)
        indices = list(optimized.indices)
        colors = list(optimized.clut)
    if not 1 < len(colors) <= 16:
        raise ModError(f'Ícone {name} exige até 15 cores opacas e transparência.')
    rows = [bytes(indices[i] | indices[i+1] << 4 for i in range(y*16, y*16 + 16, 2))
            for y in range(16)]
    return rows, struct.pack('<16H', *colors, *([0] * (16 - len(colors)))) if len(colors)<16 else struct.pack('<16H', *colors)


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
