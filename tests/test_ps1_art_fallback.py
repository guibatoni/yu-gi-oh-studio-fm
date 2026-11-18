import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from fmstudio.core import ModError
from fmstudio.png_pixels import PNG_SIGNATURE, read_png, resize_rgba
from fmstudio.ps1_content import patch_card_art
from fmstudio.ps1_expansion import _title_bitmap


def _chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def _png(width, height, depth, color, rows, *, interlace=0, metadata=b''):
    header = struct.pack('>IIBBBBB', width, height, depth, color, 0, 0, interlace)
    return (PNG_SIGNATURE + _chunk(b'IHDR', header) + metadata
            + _chunk(b'IDAT', zlib.compress(rows)) + _chunk(b'IEND', b''))


class ArtworkWithoutPillowTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.png = Path(directory.name) / 'carta.png'
        pillow = patch.dict('sys.modules', {'PIL': None})
        pillow.start()
        self.addCleanup(pillow.stop)

    def test_original_art_and_thumbnail_use_their_own_palettes(self):
        self.png.write_bytes(_png(2, 1, 8, 6, b'\0\xff\0\0\xff\0\0\xff\0'))
        art_base = 722 * 2048
        original = bytearray(art_base + 7 * 2048)
        struct.pack_into('<H', original, art_base + 0x2640 + 4, 31)
        struct.pack_into('<H', original, 0x500 + 6, 31)
        original[art_base + 0x2840:art_base + 0x2AE0] = b'\x22' * 672

        updated, changes = patch_card_art(bytes(original), 1, self.png)

        self.assertEqual(updated[art_base:art_base + 102], b'\x02' * 51 + b'\0' * 51)
        self.assertEqual(updated[:40], b'\x03' * 20 + b'\0' * 20)
        self.assertEqual({change['regiao'] for change in changes}, {'arte', 'miniatura'})
        self.assertEqual(updated[40 * 32:art_base], original[40 * 32:art_base])
        self.assertEqual(updated[art_base + 102 * 96:], original[art_base + 102 * 96:])

    def test_indexed_interlaced_png_restores_pixel_order_and_transparency(self):
        palette = bytes(i * 17 for i in range(9) for _ in range(3))
        metadata = _chunk(b'PLTE', palette) + _chunk(b'tRNS', b'\0\x80')
        # Each non-empty Adam7 row of the grid 012/345/678, in wire order.
        scanlines = b'\0\x00\0\x20\0\x68\0\x10\0\x70\0\x34\x50'
        self.png.write_bytes(_png(3, 3, 4, 3, scanlines, interlace=1, metadata=metadata))
        width, height, pixels = read_png(self.png)
        self.assertEqual((width, height), (3, 3))
        self.assertEqual(pixels[0::4], bytes(range(0, 9 * 17, 17)))
        self.assertEqual(pixels[3::4], b'\0\x80' + b'\xff' * 7)

    def test_16_bit_color_key_matches_the_original_samples(self):
        metadata = _chunk(b'tRNS', struct.pack('>HHH', 65535, 0, 0))
        rows = b'\0' + struct.pack('>6H', 65535, 0, 0, 65534, 0, 0)
        self.png.write_bytes(_png(2, 1, 16, 2, rows, metadata=metadata))
        self.assertEqual(read_png(self.png)[2], b'\xff\0\0\0\xfe\0\0\xff')

    def test_shrinking_transparent_png_keeps_opaque_color(self):
        pixels = b'\xff\0\0\xff\0\0\xff\0'
        self.assertEqual(resize_rgba(pixels, (2, 1), (1, 1)), b'\xff\0\0\x80')

    def test_invalid_art_error_identifies_the_file(self):
        self.png.write_bytes(b'incomplete')
        original = bytearray(729 * 2048)
        art_base = 722 * 2048
        struct.pack_into('<H', original, art_base + 0x2642, 31)
        struct.pack_into('<H', original, 0x502, 31)
        with self.assertRaisesRegex(ModError, r'PNG carta\.png.*Assinatura'):
            patch_card_art(bytes(original), 1, self.png)

    def test_native_title_is_generated_even_without_card_art(self):
        title = _title_bitmap('Dragão 723')
        self.assertEqual(len(title), 672)
        self.assertTrue(any(title))
        self.assertTrue(all((pixel & 0x88) == 0 for pixel in title))
        self.assertNotEqual(title, _title_bitmap('Dragão 724'))
