"""Não permitir que descrições ignoradas sejam anunciadas como gravadas no PS1."""
import unittest

from fmstudio.core import ModError
from fmstudio.disc_build import _apply_card_descriptions
from fmstudio.ps1_content import description_slot
from test_ps1_content import sample_exe


class DescriptionWriteTests(unittest.TestCase):
    def apply(self, changes, native=False):
        return _apply_card_descriptions(
            sample_exe(), changes, {1: {'nome': 'A'}},
            native_profile=native, start=0x801CD5A0, end=0x801D0000)

    def test_short_description_written_in_existing_ps1_slot(self):
        patched, rows, icons = self.apply({1: 'AA'})
        offset, size = description_slot(patched, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], 1)
        self.assertEqual(patched[offset:offset+3], bytes((1, 1, 255)))
        self.assertEqual(icons, set())

    def test_non_native_long_description_is_an_explicit_error(self):
        with self.assertRaisesRegex(ModError, r'#1: descrição:.*slot original'):
            self.apply({1: 'A' * 50})

    def test_native_profile_relocates_long_description(self):
        patched, rows, _ = self.apply({1: 'A' * 50}, native=True)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['realocada'])
        offset, size = description_slot(patched, 1)
        self.assertEqual(offset, rows[0]['offset_exe'])
        self.assertEqual(patched[offset:offset+51], bytes([1]*50+[255]))

    def test_native_unsupported_icon_is_not_silently_dropped(self):
        with self.assertRaisesRegex(ModError, r'#1: descrição:.*vinculo_vida'):
            self.apply({1: '{icon:vinculo_vida}'}, native=True)

    def test_invalid_description_does_not_modify_source_file(self):
        source = sample_exe()
        with self.assertRaises(ModError):
            _apply_card_descriptions(
                source, {1: 'A' * 50}, {}, native_profile=False,
                start=0x801CD5A0, end=0x801D0000)
        self.assertEqual(source, sample_exe())


if __name__ == '__main__':
    unittest.main()
