"""Papel de parede do menu principal: textura 4 bpp 256x240 e CLUT no SU.MRG."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from fmstudio import ps1_menu_wallpaper as wp
from fmstudio.core import ModError


def fake_su():
    data = bytearray(1239 * wp.SECTOR)
    for i in range(len(data)):
        data[i] = (i * 7) & 0xFF
    return bytes(data)


class MenuWallpaperTests(unittest.TestCase):
    def setUp(self):
        self.su = fake_su()
        stage1 = hashlib.sha256(self.su[64 * wp.SECTOR:96 * wp.SECTOR]).hexdigest()
        stage2 = hashlib.sha256(self.su[96 * wp.SECTOR:98 * wp.SECTOR]).hexdigest()
        self.patches = (patch.object(wp, 'STAGE1', (64, 96, stage1)),
                        patch.object(wp, 'STAGE2', (96, 98, stage2)))
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])

    def test_texture_layout_and_palette(self):
        wall = Image.new('RGB', (256, 240), (0, 0, 0))
        for x in range(256):
            for y in range(240):
                if x % 2:
                    wall.putpixel((x, y), (248, 0, 0))
        out, report = wp.apply(self.su, wall)
        self.assertEqual(report['status'], 'aplicado')
        self.assertTrue(wp.inspect(out, wall))
        # Só os setores 80-94 (240 linhas) e os 32 bytes da CLUT mudam.
        changed = {i // wp.SECTOR for i, (a, b) in enumerate(zip(self.su, out)) if a != b}
        self.assertTrue(changed <= set(range(80, 95)) | {97})
        self.assertEqual(out[95 * wp.SECTOR:96 * wp.SECTOR], self.su[95 * wp.SECTOR:96 * wp.SECTOR])
        self.assertEqual(out[97 * wp.SECTOR + 32:], self.su[97 * wp.SECTOR + 32:])
        clut = [int.from_bytes(out[97 * wp.SECTOR + 2 * i:97 * wp.SECTOR + 2 * i + 2], 'little')
                for i in range(16)]
        self.assertNotIn(0, clut)                       # nenhuma cor transparente
        self.assertIn(0x8000, clut)                     # preto opaco
        self.assertIn(0x001F, clut)                     # vermelho puro em BGR555
        first = out[80 * wp.SECTOR]
        red, black = clut.index(0x001F), clut.index(0x8000)
        self.assertEqual(first, black | red << 4)       # pixel par = nibble baixo

    def test_tile_mode_repeats(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'tile.png'
            tile = Image.new('RGB', (32, 32), (0, 0, 255))
            tile.putpixel((0, 0), (255, 255, 255))
            tile.save(path)
            wall = wp.compose(path, 'ladrilho', 32)
            self.assertEqual(wall.size, (256, 240))
            self.assertEqual(wall.getpixel((32, 64)), wall.getpixel((0, 0)))
            whole = wp.compose(path, 'imagem')
            self.assertEqual(whole.size, (256, 240))
            shown = wp.preview(wall)
            self.assertEqual(shown.size, (320, 240))
            self.assertEqual(shown.getpixel((256, 5)), shown.getpixel((0, 5)))

    def test_unknown_su_is_refused(self):
        changed = bytearray(self.su)
        changed[85 * wp.SECTOR] ^= 1
        with self.assertRaises(ModError):
            wp.apply(bytes(changed), Image.new('RGB', (256, 240)))

    def test_project_settings_round_trip(self):
        class Project:
            def __init__(self, folder):
                self.folder, self.metadata, self.saved = folder, {}, 0
            def save(self):
                self.saved += 1
        with tempfile.TemporaryDirectory() as folder:
            project = Project(Path(folder))
            self.assertIsNone(wp.requested_wall(project))
            with self.assertRaises(ModError):
                wp.save(project, enabled=True, mode='imagem')
            source = Path(folder) / 'x.png'
            Image.new('RGB', (500, 300), (10, 200, 30)).save(source)
            wp.save(project, enabled=True, mode='imagem', source=str(source))
            self.assertEqual(wp.requested_wall(project).size, (256, 240))
            self.assertEqual(wp.settings(project)['modo'], 'imagem')


if __name__ == '__main__':
    unittest.main()
