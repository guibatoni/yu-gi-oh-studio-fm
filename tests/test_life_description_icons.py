"""Regression for the new 16x16 LP icons and text tokens."""
import unittest
from pathlib import Path

from fmstudio.ps1_god_icon import decode_icon_png
from fmstudio.ps1_text import ICON_CODES, _indexed_sprite
from fmstudio.richtext import CUSTOM_ICONS, tokens

ROOT = Path(__file__).resolve().parents[1] / "assets" / "icons"


class LifeIconTests(unittest.TestCase):
    def test_both_icons_are_real_16x16_and_supported_by_ps1_palette(self):
        for name in ("vinculo_vida", "restaurar_lp"):
            with self.subTest(icon=name):
                self.assertIn(name, CUSTOM_ICONS)
                # MIPS renderer supports only nine old custom slots; do not emit invalid PS1 codes.
                self.assertNotIn(name, ICON_CODES)
                pixels = decode_icon_png(ROOT / (name + ".png"))
                self.assertEqual(len(pixels), 256)
                self.assertTrue(any(alpha == 0 for *_, alpha in pixels))
                rows, palette = _indexed_sprite(name)
                self.assertEqual(len(rows), 16)
                self.assertTrue(all(len(row) == 8 for row in rows))
                self.assertEqual(len(palette), 32)

    def test_tokens_show_named_icons(self):
        segments = tokens("A {icon:vinculo_vida} B {icon:restaurar_lp}")
        self.assertIn(("", "#EFEFEF", "vinculo_vida"), segments)
        self.assertIn(("", "#EFEFEF", "restaurar_lp"), segments)


if __name__ == "__main__":
    unittest.main()
