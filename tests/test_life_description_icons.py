"""Regression for the new 16x16 LP icons and text tokens."""
import unittest
from pathlib import Path

from fmstudio.ps1_god_icon import decode_icon_png
from fmstudio.ps1_text import ICON_CODES, _indexed_sprite
from fmstudio.core import ModError
from fmstudio.ps1_content import _encode_description
from fmstudio.richtext import CUSTOM_ICONS, tokens

ROOT = Path(__file__).resolve().parents[1] / "assets" / "icons"


class LifeIconTests(unittest.TestCase):
    def test_both_icons_are_real_16x16_and_supported_by_ps1_palette(self):
        for name in ("vinculo_vida", "restaurar_lp"):
            with self.subTest(icon=name):
                self.assertIn(name, CUSTOM_ICONS)
                # Dois novos slots endereçáveis no hook MIPS validado.
                self.assertIn(name, ICON_CODES)
                pixels = decode_icon_png(ROOT / (name + ".png"))
                self.assertEqual(len(pixels), 256)
                self.assertTrue(any(alpha == 0 for *_, alpha in pixels))
                rows, palette = _indexed_sprite(name)
                self.assertEqual(len(rows), 16)
                self.assertTrue(all(len(row) == 8 for row in rows))
                self.assertEqual(len(palette), 32)

    def test_ps1_compiles_both_icons_to_real_codes(self):
        for name, code in (('vinculo_vida', 0x49), ('restaurar_lp', 0x4A)):
            with self.subTest(icon=name):
                self.assertEqual(ICON_CODES[name], code)
                self.assertEqual(_encode_description(
                    '{icon:' + name + '}', {}, {}, icon_codes=ICON_CODES),
                    bytes((0xF8,0x0B,code)))

    def test_mips_runtime_validates_11_slots_without_relocating_hooks(self):
        from fmstudio import ps1_runtime_blob, ps1_expanded_runtime_blob
        for bundle in (ps1_runtime_blob, ps1_expanded_runtime_blob):
            with self.subTest(profile=bundle.RUNTIME_BASE):
                at=bundle.ENTRY_POINTS['DescriptionIcon']-bundle.RUNTIME_BASE
                self.assertEqual(bundle.RUNTIME[at+4:at+8],bytes.fromhex('0b 00 44 2c'))
                self.assertGreater(len(bundle.RUNTIME),at+64)

    def test_tokens_show_named_icons(self):
        segments = tokens("A {icon:vinculo_vida} B {icon:restaurar_lp}")
        self.assertIn(("", "#EFEFEF", "vinculo_vida"), segments)
        self.assertIn(("", "#EFEFEF", "restaurar_lp"), segments)


if __name__ == "__main__":
    unittest.main()
