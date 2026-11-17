"""Não permitir que descrições ignoradas sejam anunciadas como gravadas no PS1."""
import struct
import unittest

from fmstudio.core import ModError
from fmstudio.disc_build import _apply_card_descriptions, DescriptionCompatibilityError
from fmstudio.ps1_content import description_slot
from test_ps1_content import sample_exe, where


class DescriptionWriteTests(unittest.TestCase):
    def apply(self, changes, native=False, policy='strict'):
        return _apply_card_descriptions(
            sample_exe(), changes, {1: {'nome': 'A'}},
            native_profile=native, start=0x801CD5A0, end=0x801D0000,
            policy=policy)

    def test_short_description_written_in_existing_ps1_slot(self):
        patched, rows, icons, skipped = self.apply({1: 'AA'})
        self.assertEqual(skipped, [])
        offset, size = description_slot(patched, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], 1)
        self.assertEqual(patched[offset:offset+3], bytes((1, 1, 255)))
        self.assertEqual(icons, set())

    def test_non_native_long_description_is_an_explicit_error(self):
        with self.assertRaisesRegex(ModError, r'#1: descrição:.*slot original'):
            self.apply({1: 'A' * 50})

    def test_native_profile_relocates_long_description(self):
        patched, rows, _, skipped = self.apply({1: 'A' * 50}, native=True)
        self.assertEqual(skipped, [])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['realocada'])
        offset, size = description_slot(patched, 1)
        self.assertEqual(offset, rows[0]['offset_exe'])
        self.assertEqual(patched[offset:offset+51], bytes([1]*50+[255]))

    def test_native_unsupported_icon_is_not_silently_dropped(self):
        with self.assertRaisesRegex(ModError, r'#1: descrição:.*vinculo_vida'):
            self.apply({1: '{icon:vinculo_vida}'}, native=True)

    def test_explicit_fallback_keeps_old_slot_and_records_reason(self):
        original = sample_exe()
        fallback, rows, icons, skipped = self.apply(
            {1: 'A' * 50}, policy='preserve_incompatible')
        self.assertEqual(fallback, original)
        self.assertEqual(rows, [])
        self.assertEqual(icons, set())
        self.assertEqual(len(skipped), 1)
        self.assertIn('#1: descrição:', skipped[0])

    def test_fallback_writes_compatible_and_skips_only_invalid(self):
        original = bytearray(sample_exe())
        struct.pack_into('<H', original, where(0x801C0000 + 0x102 * 2), 0x3010)
        original[where(0x801C3010):where(0x801C3010)+3] = b'\x01\x01\xff'
        patched, rows, icons, skipped = _apply_card_descriptions(
            bytes(original), {1: 'AA', 2: 'A' * 50}, {},
            native_profile=False, start=0x801CD5A0, end=0x801D0000,
            policy='preserve_incompatible')
        self.assertEqual([row['id'] for row in rows], [1])
        self.assertEqual(patched[where(0x801C3000):where(0x801C3000)+3],
                         b'\x01\x01\xff')
        self.assertEqual(patched[where(0x801C3010):where(0x801C3010)+3],
                         b'\x01\x01\xff')
        self.assertEqual(len(skipped), 1)
        self.assertIn('#2:', skipped[0])

    def test_unsupported_new_icon_keeps_original_in_opt_in_mode(self):
        original = sample_exe()
        result, rows, _, skipped = self.apply(
            {1: '{icon:restaurar_lp}'}, native=True,
            policy='preserve_incompatible')
        self.assertEqual(result, original)
        self.assertEqual(rows, [])
        self.assertIn('restaurar_lp', skipped[0])

    def test_unknown_policy_is_rejected(self):
        with self.assertRaisesRegex(ModError, 'Política'):
            self.apply({1: 'A'}, policy='ignore_everything')

    def test_strict_error_exposes_all_failed_ids(self):
        with self.assertRaises(DescriptionCompatibilityError) as ctx:
            self.apply({1: 'A' * 50, 2: '{icon:restaurar_lp}'})
        self.assertEqual(len(ctx.exception.failures), 2)

    def test_invalid_description_does_not_modify_source_file(self):
        source = sample_exe()
        with self.assertRaises(ModError):
            _apply_card_descriptions(
                source, {1: 'A' * 50}, {}, native_profile=False,
                start=0x801CD5A0, end=0x801D0000)
        self.assertEqual(source, sample_exe())


if __name__ == '__main__':
    unittest.main()
