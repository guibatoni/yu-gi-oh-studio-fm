"""Guardian Star Supreme for the verified PS1 disc profile."""
from __future__ import annotations

import hashlib
import struct

from .ps1_supreme_blob import BASE, CODE, END, ENTRY_POINTS
from .tables import CARD_COUNT, EXE_DELTA, GUARDIAN_FIELDS, PS1_SUPREME, SUPREME

# 0x8322 is the first unused alias after the ten stock star names. The new
# string and code fit between the empty text-record list and DA000 scratch.
NAME_POINTER = 0x801D5800 + 2 * 0x322 - EXE_DELTA
NAME_ADDRESS = 0x801D9B00
NAME = bytes.fromhex('1d 0d 14 08 01 0e 01 ff')  # Supreme, in the PS1 font
CODE_OFFSET = BASE - EXE_DELTA

# 4bpp boot texture A. U=160 is after the God and description icons.
# The palette at (672,255) is separate from their CLUTs.
ICON_START = 0x1690 * 2048 + 192 * 128 + 160 // 2
ICON_ROWS = tuple(ICON_START + 128 * y for y in range(16))
CLUT_OFFSET = 0x16C0 * 2048 + 7 * 512 + (672 - 512) * 2
CLUT = struct.pack('<16H', 0, 0x898A, 0xB73E, 0xDFFF, *([0] * 12))
PIXELS = (
    '0000000110000000',
    '0000000110000000',
    '0000001221000000',
    '0000001221000000',
    '0000012322100000',
    '0000122332210000',
    '0011223333221100',
    '1122233333322211',
    '1122233333322211',
    '0011223333221100',
    '0000122332210000',
    '0000012232100000',
    '0000001221000000',
    '0000001221000000',
    '0000000110000000',
    '0000000110000000',
)
ICON = tuple(bytes(int(row[x]) | int(row[x + 1]) << 4 for x in range(0, 16, 2))
             for row in PIXELS)


def _redirect(entry: str, *, link: bool = False) -> bytes:
    op = 0x0C000000 if link else 0x08000000
    return struct.pack('<I', op | ((ENTRY_POINTS[entry] >> 2) & 0x3FFFFFF))


def _words(*values):
    return struct.pack(f'<{len(values)}I', *values)


HOOKS = (
    (0x8002CB80, _words(0x2484FFF9, 0x04800006), _redirect('SupremeMatchup') + bytes(4)),
    (0x80037FE8, _words(0x30C200FF, 0x14400003), _redirect('SupremeTextIcon') + bytes(4)),
    (0x80038070, _words(0x9385043C, 0x27BDFFE8), _redirect('SupremeFieldIcon') + bytes(4)),
    (0x8002C77C, _words(0x0C0518AC), _redirect('SupremeGather', link=True)),
    (0x8001FF58, _words(0x978202C8, 0), _redirect('SupremeDisplayBonus') + bytes(4)),
)
SPRITE_HOOK = _redirect('SupremeSprite') + bytes(4)


def _cards_with_star(project, capacity: int, star: int) -> list[int]:
    ids = []
    for cid in sorted(getattr(project, 'cards', {})):
        if not 1 <= cid <= capacity:
            continue
        card = project.get(cid)
        if cid <= CARD_COUNT and card.get('virtual'):
            continue
        if any(int(card.get(field, 0)) == star for field in GUARDIAN_FIELDS):
            ids.append(cid)
    return ids


def supreme_cards(project, capacity: int) -> list[int]:
    return _cards_with_star(project, capacity, SUPREME)


def validate_slot(project, capacity: int) -> None:
    from .core import ModError

    collisions = _cards_with_star(project, capacity, PS1_SUPREME)
    if collisions:
        labels = ', '.join(f'#{cid:03d}' for cid in collisions[:8])
        raise ModError(f'Supreme usa o código reservado 11 no PS1. Troque a estrela '
                       f'reservada de {labels} por uma Guardian Star válida antes de gerar.')


def _sprite_variants():
    from . import ps1_expanded_runtime_blob, ps1_runtime_blob
    from .ps1_god24_display import SPRITE_ORIGINAL, SPRITE_PATCHED, extended_sprite_words

    return tuple(_words(*variant) for variant in (
        SPRITE_ORIGINAL, SPRITE_PATCHED, extended_sprite_words(ps1_runtime_blob.ENTRY_POINTS),
        extended_sprite_words(ps1_expanded_runtime_blob.ENTRY_POINTS)))


def sprite_without_supreme(exe: bytes, region: bytes) -> bytes:
    """Expose the underlying renderer to the existing God icon inspector."""
    if region.startswith(SPRITE_HOOK) and exe[CODE_OFFSET:CODE_OFFSET + len(CODE)] == CODE:
        for variant in _sprite_variants():
            if region[8:] == variant[8:]:
                return variant
    return region


def inspect_supreme(exe: bytes, wa: bytes | None = None) -> dict:
    from .ps1_god24_display import SPRITE_RAM, SPRITE_ORIGINAL

    code_matches = exe[CODE_OFFSET:CODE_OFFSET + len(CODE)] == CODE
    applied = [exe[pc - EXE_DELTA:pc - EXE_DELTA + len(after)] == after
               for pc, _, after in HOOKS]
    at = SPRITE_RAM - EXE_DELTA
    sprite = exe[at:at + len(SPRITE_ORIGINAL) * 4]
    if not code_matches and not any(applied) and not sprite.startswith(SPRITE_HOOK):
        status = 'ausente'
    elif (not code_matches or not all(applied) or sprite_without_supreme(exe, sprite) == sprite
          or exe[NAME_POINTER:NAME_POINTER + 2] != struct.pack('<H', NAME_ADDRESS & 0xFFFF)
          or exe[NAME_ADDRESS - EXE_DELTA:NAME_ADDRESS - EXE_DELTA + len(NAME)] != NAME):
        status = 'divergente'
    elif wa is None:
        status = 'aguardando_textura'
    elif (wa[CLUT_OFFSET:CLUT_OFFSET + len(CLUT)] == CLUT
          and all(wa[pos:pos + 8] == row for pos, row in zip(ICON_ROWS, ICON))):
        status = 'aplicado'
    else:
        status = 'textura_divergente'
    return {'status': status, 'id_ps1': PS1_SUPREME, 'bonus': 700, 'validado_epsxe': False}


def patch_supreme(original: bytes, exe: bytes, wa: bytes) -> tuple[bytes, bytes]:
    from .core import ModError
    from .ps1_god24_chest import SOURCE_SHA256
    from .ps1_god24_display import SPRITE_RAM, SPRITE_ORIGINAL

    if len(original) != len(exe) or hashlib.sha256(original).hexdigest() != SOURCE_SHA256:
        raise ModError('Supreme no PS1 exige o SLUS verificado do Original Drop x15.')
    code_end = END - EXE_DELTA
    name_at = NAME_ADDRESS - EXE_DELTA
    if (not CODE or not BASE < END <= NAME_ADDRESS < 0x801DA000
            or len(CODE) != END - BASE or name_at + len(NAME) > len(exe)
            or any(exe[CODE_OFFSET:code_end]) or any(exe[name_at:name_at + len(NAME)])
            or exe[NAME_POINTER:NAME_POINTER + 2] != struct.pack('<H', 0x8ACE)):
        raise ModError('Supreme: banco de código ou nome nativo incompatível com a imagem.')
    out = bytearray(exe)
    for pc, before, after in HOOKS:
        pos = pc - EXE_DELTA
        if exe[pos:pos + len(before)] != before:
            raise ModError(f'Supreme: rotina PS1 incompatível em 0x{pc:08X}.')
        out[pos:pos + len(after)] = after
    sprite_at = SPRITE_RAM - EXE_DELTA
    if exe[sprite_at:sprite_at + len(SPRITE_ORIGINAL) * 4] not in _sprite_variants():
        raise ModError('Supreme: renderizador de Guardian Stars incompatível com a imagem.')
    out[sprite_at:sprite_at + len(SPRITE_HOOK)] = SPRITE_HOOK
    out[CODE_OFFSET:code_end] = CODE
    out[name_at:name_at + len(NAME)] = NAME
    struct.pack_into('<H', out, NAME_POINTER, NAME_ADDRESS & 0xFFFF)

    if (len(wa) < CLUT_OFFSET + len(CLUT) or any(wa[CLUT_OFFSET:CLUT_OFFSET + len(CLUT)])
            or any(any(wa[pos:pos + 8]) for pos in ICON_ROWS)):
        raise ModError('Supreme: a célula ou a paleta do ícone PS1 está ocupada no WA_MRG.')
    archive = bytearray(wa)
    archive[CLUT_OFFSET:CLUT_OFFSET + len(CLUT)] = CLUT
    for pos, row in zip(ICON_ROWS, ICON):
        archive[pos:pos + 8] = row
    return bytes(out), bytes(archive)
