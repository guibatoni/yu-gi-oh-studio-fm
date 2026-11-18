"""Render the separate 96×14 4bpp title texture for additional PS1 cards."""
from __future__ import annotations

import unicodedata

from .png_pixels import resize_rgba


# Seven rows per glyph, with the leftmost pixel in bit 4.
GLYPHS = {
    'A': (14, 17, 17, 31, 17, 17, 17),
    'B': (30, 17, 17, 30, 17, 17, 30),
    'C': (14, 17, 16, 16, 16, 17, 14),
    'D': (30, 17, 17, 17, 17, 17, 30),
    'E': (31, 16, 16, 30, 16, 16, 31),
    'F': (31, 16, 16, 30, 16, 16, 16),
    'G': (14, 17, 16, 23, 17, 17, 15),
    'H': (17, 17, 17, 31, 17, 17, 17),
    'I': (14, 4, 4, 4, 4, 4, 14),
    'J': (7, 2, 2, 2, 18, 18, 12),
    'K': (17, 18, 20, 24, 20, 18, 17),
    'L': (16, 16, 16, 16, 16, 16, 31),
    'M': (17, 27, 21, 21, 17, 17, 17),
    'N': (17, 25, 21, 19, 17, 17, 17),
    'O': (14, 17, 17, 17, 17, 17, 14),
    'P': (30, 17, 17, 30, 16, 16, 16),
    'Q': (14, 17, 17, 17, 21, 18, 13),
    'R': (30, 17, 17, 30, 20, 18, 17),
    'S': (15, 16, 16, 14, 1, 1, 30),
    'T': (31, 4, 4, 4, 4, 4, 4),
    'U': (17, 17, 17, 17, 17, 17, 14),
    'V': (17, 17, 17, 17, 17, 10, 4),
    'W': (17, 17, 17, 21, 21, 27, 17),
    'X': (17, 17, 10, 4, 10, 17, 17),
    'Y': (17, 17, 10, 4, 4, 4, 4),
    'Z': (31, 1, 2, 4, 8, 16, 31),
    '0': (14, 17, 19, 21, 25, 17, 14),
    '1': (4, 12, 4, 4, 4, 4, 14),
    '2': (14, 17, 1, 2, 4, 8, 31),
    '3': (30, 1, 1, 14, 1, 1, 30),
    '4': (2, 6, 10, 18, 31, 2, 2),
    '5': (31, 16, 16, 30, 1, 1, 30),
    '6': (14, 16, 16, 30, 17, 17, 14),
    '7': (31, 1, 2, 4, 8, 8, 8),
    '8': (14, 17, 17, 14, 17, 17, 14),
    '9': (14, 17, 17, 15, 1, 1, 14),
    ' ': (0, 0, 0, 0, 0, 0, 0),
    '!': (4, 4, 4, 4, 4, 0, 4),
    '?': (14, 17, 1, 2, 4, 0, 4),
    '-': (0, 0, 0, 14, 0, 0, 0),
    '.': (0, 0, 0, 0, 0, 4, 4),
    ',': (0, 0, 0, 0, 0, 4, 8),
    ':': (0, 4, 4, 0, 4, 4, 0),
    '+': (0, 4, 4, 31, 4, 4, 0),
    '/': (1, 1, 2, 4, 8, 16, 16),
    '#': (10, 10, 31, 10, 31, 10, 10),
    '&': (12, 18, 20, 8, 21, 18, 13),
    '(': (2, 4, 8, 8, 8, 4, 2),
    ')': (8, 4, 2, 2, 2, 4, 8),
    "'": (4, 4, 8, 0, 0, 0, 0),
    '"': (10, 10, 0, 0, 0, 0, 0),
    '«': (0, 0, 9, 18, 9, 0, 0),
    '»': (0, 0, 18, 9, 18, 0, 0),
    '·': (0, 0, 0, 4, 0, 0, 0),
    'Α': (0, 0, 13, 18, 18, 18, 13),
    'Β': (12, 18, 18, 28, 18, 18, 28),
    'Γ': (0, 0, 17, 10, 4, 4, 8),
}


def _title_size(width: int, height: int) -> tuple[int, int]:
    scale = min(94 / width, 12 / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def _pillow_title(text: str) -> tuple[tuple[int, int], bytes]:
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.load_default(size=22)
    except TypeError:  # Pillow versions predating the scalable default font.
        font = ImageFont.load_default()
    left, top, right, bottom = font.getbbox(text)
    canvas = Image.new('L', (max(1, right - left), max(1, bottom - top)))
    ImageDraw.Draw(canvas).text((-left, -top), text, font=font, fill=255)
    target = _title_size(*canvas.size)
    return target, canvas.resize(target, getattr(Image, 'Resampling', Image).LANCZOS).tobytes()


def _bitmap_title(text: str) -> tuple[tuple[int, int], bytes]:
    width, height = max(1, 6 * len(text) - 1), 7
    rgba = bytearray(width * height * 4)
    for i, letter in enumerate(text):
        glyph = GLYPHS.get(letter.upper(), GLYPHS['?'])
        for y, row in enumerate(glyph):
            for x in range(5):
                if row & (16 >> x):
                    at = (y * width + i * 6 + x) * 4
                    rgba[at:at + 4] = b'\xff\xff\xff\xff'
    target = _title_size(width, height)
    return target, resize_rgba(rgba, (width, height), target)[3::4]


def title_bitmap(name: str) -> bytes:
    text = ''.join(c for c in unicodedata.normalize('NFD', str(name)) if not unicodedata.combining(c))
    try:
        (width, height), ink = _pillow_title(text)
    except (ImportError, OSError, ValueError, AttributeError):
        (width, height), ink = _bitmap_title(text)
    indices = bytearray(96 * 14)
    top = (14 - height) // 2
    for row in range(height):
        start = 96 * (row + top) + 1
        indices[start:start + width] = bytes((p * 7 + 127) // 255 for p in ink[row * width:(row + 1) * width])
    return bytes(low | (high << 4) for low, high in zip(indices[::2], indices[1::2]))
