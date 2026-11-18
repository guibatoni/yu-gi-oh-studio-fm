"""Diagnóstico de texto realmente presente no BIN, inclusive realocação PS1."""
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from fmstudio.ps1_content import patch_descriptions
from fmstudio.ps1_description_verify import (
    inspect_exe_description, scan_disc_descriptions,
)
from fmstudio.ps1_text import patch_descriptions as patch_extended
from test_ps1_content import sample_exe, sample_wa, write_disc


class DescriptionReadbackTests(unittest.TestCase):
    def inspect(self, exe, text, *, native=False):
        return inspect_exe_description(
            exe, 1, text, {1: {'nome': 'A', 'descricao': text}},
            original_exe=sample_exe(), native_profile=native)

    def test_original_text_is_distinguished_from_edited_text(self):
        result = self.inspect(sample_exe(), 'AA')
        self.assertEqual(result['status'], 'original')
        self.assertIn('ponteiro', result)
        self.assertTrue(result['sha256_texto_bin'])

    def test_modified_short_text_is_confirmed(self):
        modified, _ = patch_descriptions(sample_exe(), {1: 'AA'}, {})
        result = self.inspect(modified, 'AA')
        self.assertEqual(result['status'], 'aplicada')
        self.assertEqual(result['texto_no_bin'], 'AA')
        self.assertEqual(result['sha256_texto_esperado'],
                         result['sha256_texto_bin'])

    def test_long_description_relocated_in_drop_x15(self):
        original = sample_exe()
        modified, rows, _, errors = patch_extended(
            original, {1: 'A'*50}, {},
            start=0x801CD5A0, end=0x801D0000)
        self.assertEqual(errors, [])
        self.assertTrue(rows[0]['realocada'])
        result = self.inspect(modified, 'A'*50, native=True)
        self.assertEqual(result['status'], 'aplicada')

    def test_life_icon_is_not_reported_as_exported_until_actual_bytes_are_written(self):
        original = sample_exe()
        result = self.inspect(original, '{icon:vinculo_vida}', native=True)
        self.assertEqual(result['status'], 'original')
        patched, rows, icons, failures = patch_extended(
            original, {1:'{icon:vinculo_vida}'}, {},
            start=0x801CD5A0, end=0x801D0000)
        self.assertFalse(failures)
        self.assertIn('vinculo_vida',icons)
        confirmed = self.inspect(patched, '{icon:vinculo_vida}', native=True)
        self.assertEqual(confirmed['status'], 'aplicada')

    def test_custom_card_above_722_remains_studio_only(self):
        result = inspect_exe_description(sample_exe(), 723, 'Teste', {})
        self.assertEqual(result['status'], 'somente_studio')

    def test_expanded_description_readback_follows_actual_pointer_through_740(self):
        modified, rows, _, errors = patch_extended(
            sample_exe(), {723: 'AA', 740: 'A'}, {},
            start=0x801CD5A0, end=0x801D0000)
        self.assertFalse(errors)
        with patch('fmstudio.ps1_expansion.inspect_expansion',
                   return_value={'status': 'aplicado', 'capacidade': 740}):
            for row in rows:
                text = 'AA' if row['id'] == 723 else 'A'
                result = inspect_exe_description(modified, row['id'], text, {}, native_profile=True)
                self.assertEqual(result['status'], 'aplicada')
                self.assertEqual(result['offset_exe'], row['offset_exe'])
                self.assertEqual(result['texto_no_bin'], text)
            outside = inspect_exe_description(modified, 741, 'A', {}, native_profile=True)
            self.assertEqual(outside['status'], 'somente_studio')

    def test_comparison_reads_selected_bin_without_writing_to_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            base = folder / 'base'
            base.mkdir()
            stock = sample_exe()
            (base / 'source_SLUS_014.11').write_bytes(stock)
            patched, _ = patch_descriptions(stock, {1: 'AA'}, {})
            img = folder / 'teste.bin'
            write_disc(img, patched, sample_wa())
            before = img.stat().st_size
            cards = {1: {'nome': 'A', 'descricao': 'AA'}}
            project = SimpleNamespace(
                folder=folder, cards=cards,
                edits={'1': {'descricao': 'AA'}}, new_cards={},
                get=lambda cid: cards[cid],
            )
            data = scan_disc_descriptions(project, img)
            self.assertEqual(data['contagens']['aplicada'], 1)
            self.assertEqual(data['cartas'][0]['status'], 'aplicada')
            self.assertEqual(img.stat().st_size, before)
            self.assertFalse((folder/'exportacao').exists())


if __name__ == '__main__':
    unittest.main()
