"""Não permitir que descrições ignoradas sejam anunciadas como gravadas no PS1."""
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fmstudio.core import ModError
from fmstudio.disc_build import _apply_card_descriptions, DescriptionCompatibilityError
from fmstudio.ps1_content import description_slot
from fmstudio.ps1_description_verify import inspect_exe_description
from fmstudio.ps1_text import description_regions
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

    def test_native_life_icon_written_as_real_glyph_code(self):
        patched, rows, icons, failures = self.apply(
            {1: '{icon:vinculo_vida}'}, native=True)
        self.assertFalse(failures)
        self.assertEqual(icons, {'vinculo_vida'})
        self.assertEqual(len(rows), 1)
        offset, _ = description_slot(patched, 1)
        self.assertEqual(patched[offset:offset+4], bytes((0xf8,0x0b,0x4b,0xff)))

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

    def test_life_icon_is_not_replaced_by_words_in_opt_in_mode(self):
        patched, rows, icons, skipped = self.apply(
            {1: '{icon:restaurar_lp}'}, native=True,
            policy='preserve_incompatible')
        self.assertFalse(skipped)
        self.assertEqual(icons, {'restaurar_lp'})
        self.assertFalse(rows[0].get('resumida', False))
        offset, _ = description_slot(patched, 1)
        self.assertEqual(patched[offset:offset+4], bytes((0xf8,0x0b,0x4a,0xff)))

    def test_unknown_policy_is_rejected(self):
        with self.assertRaisesRegex(ModError, 'Política'):
            self.apply({1: 'A'}, policy='ignore_everything')

    def test_strict_error_exposes_all_failed_ids(self):
        with self.assertRaises(DescriptionCompatibilityError) as ctx:
            self.apply({1: 'A' * 50, 2: '{icon:restaurar_lp}'})
        # Perfil não-nativo não possui o hook PS1; ambos são rejeitados.
        self.assertEqual(len(ctx.exception.failures), 2)
        self.assertEqual([row.split(':')[0] for row in ctx.exception.failures],
                         ['#1', '#2'])

    def test_invalid_description_does_not_modify_source_file(self):
        source = sample_exe()
        with self.assertRaises(ModError):
            _apply_card_descriptions(
                source, {1: 'A' * 50}, {}, native_profile=False,
                start=0x801CD5A0, end=0x801D0000)
        self.assertEqual(source, sample_exe())

    def test_ten_manual_lines_can_keep_all_text_icons_and_colors(self):
        text = '{color:azul}{icon:ataque_3x} ' + '\n'.join(['AB AB AB AB AB'] * 10) + '{/color}'
        patched, rows, icons, failures = self.apply({723: text}, native=True)
        self.assertFalse(failures)
        self.assertTrue(rows[0]['quebras_reorganizadas'])
        self.assertEqual(icons, {'ataque_3x'})
        with patch('fmstudio.ps1_expansion.inspect_expansion',
                   return_value={'status': 'aplicado', 'capacidade': 740}):
            result = inspect_exe_description(patched, 723, text, {}, native_profile=True)
        self.assertEqual(result['status'], 'aplicada')
        self.assertEqual(result['texto_no_bin'].split().count('AB'), 49)
        self.assertTrue(result['texto_no_bin'].endswith('AB{f8 0A 00}'))

    def test_expanded_fallback_uses_free_intervals_and_leaves_unregistered_slots_empty(self):
        source = bytearray(sample_exe())
        struct.pack_into('<I', source, where(0x801D9000 + 4 * 4), 0x8144)  # period
        vacant = 0x2FF0
        source[where(0x801C0000 + vacant)] = 0xFF
        for cid in (0, *range(723, 741)):
            struct.pack_into('<H', source, where(0x801C0000 + 2 * (0x100 + cid)), vacant)
        plan = SimpleNamespace(
            data_end=0x801CF9A4, capacity=740, password_prefix=12345,
            grave_filters=False, entry_markers=False, mod_features=False, gameplay=True,
        )
        regions = description_regions(plan, has_lp=True)
        changes = {723: '\n'.join(['A' * 21] * 10), 724: 'B' * 120, 725: '{icon:vinculo_vida}'}
        args = dict(native_profile=True, start=plan.data_end, end=0x801CF9B0, regions=regions)
        with self.assertRaises(DescriptionCompatibilityError) as ctx:
            _apply_card_descriptions(source, changes, {}, **args)
        self.assertEqual([problem.split(':', 1)[0] for problem in ctx.exception.failures], ['#723'])
        patched, rows, _, failures = _apply_card_descriptions(
            source, changes, {}, policy='preserve_incompatible', **args)
        self.assertEqual([(row['id'], row.get('resumida', False)) for row in rows],
                         [(723, True), (724, False), (725, False)])
        self.assertFalse(failures)
        for cid in range(726, 741):
            pointer = where(0x801C0000 + 2 * (0x100 + cid))
            self.assertEqual(struct.unpack_from('<H', patched, pointer)[0], vacant)
        with patch('fmstudio.ps1_expansion.inspect_expansion',
                   return_value={'status': 'aplicado', 'capacidade': 740}):
            results = [inspect_exe_description(patched, cid, text, {}, native_profile=True)
                       for cid, text in changes.items()]
        self.assertEqual([row['status'] for row in results], ['resumida', 'aplicada', 'aplicada'])
        self.assertEqual(results[1]['texto_no_bin'], changes[724])

    def test_complete_description_gets_storage_before_an_optional_preview(self):
        source = bytearray(sample_exe())
        struct.pack_into('<I', source, where(0x801D9000 + 4 * 4), 0x8144)
        _, rows, _, pending = _apply_card_descriptions(
            source, {723: 'A' * 250, 724: 'B' * 45}, {}, native_profile=True,
            start=0x801CD5A0, end=0x801CD5A0 + 52, policy='preserve_incompatible')
        self.assertFalse(pending)
        self.assertEqual([(row['id'], row.get('resumida', False)) for row in rows],
                         [(723, True), (724, False)])
        self.assertEqual(rows[1]['bytes'], 46)

    def test_tiny_description_slot_uses_words_instead_of_only_leading_icons(self):
        source = bytearray(sample_exe())
        struct.pack_into('<I', source, where(0x801D9000 + 4 * 4), 0x8144)
        value = '{color:azul}{icon:indestrutivel}{icon:perfurar}AB AB AB AB AB AB{/color}'
        patched, rows, icons, pending = _apply_card_descriptions(
            source, {723: value}, {}, native_profile=True, start=0x801CD5A0,
            end=0x801CD5A0 + 14, policy='preserve_incompatible')
        self.assertFalse(pending)
        self.assertFalse(icons)
        self.assertTrue(rows[0]['resumida'])
        with patch('fmstudio.ps1_expansion.inspect_expansion',
                   return_value={'status': 'aplicado', 'capacidade': 740}):
            result = inspect_exe_description(patched, 723, value, {}, native_profile=True)
        self.assertEqual(result['status'], 'resumida')
        self.assertEqual(result['texto_no_bin'], 'AB AB AB...')

    def test_life_icons_use_real_codes_in_compatible_new_descriptions(self):
        source = bytearray(sample_exe())
        letters = sorted(set('Vinculo de vida Restaura LP') - {' '})
        codes = (i for i in range(4, 0x5C) if i not in (0x1B, 0x27, 0x28, 0x30, 0x40, 0x47))
        for code, char in zip(codes, letters):
            sjis = chr(ord(char) + 0xFEE0).encode('shift_jis')
            struct.pack_into('<I', source, where(0x801D9000 + 4 * code), int.from_bytes(sjis,'big'))
        text = '{icon:vinculo_vida} {icon:restaurar_lp}'
        patched, rows, _, pending = _apply_card_descriptions(
            source, {723: text}, {}, native_profile=True, start=0x801CD5A0,
            end=0x801CD5A0 + 90, policy='preserve_incompatible')
        self.assertFalse(pending)
        self.assertFalse(rows[0].get('resumida', False))
        self.assertEqual(patched[rows[0]['offset_exe']:rows[0]['offset_exe']+3],
                         bytes((0xf8,0x0b,0x4b)))
        with patch('fmstudio.ps1_expansion.inspect_expansion',
                   return_value={'status': 'aplicado', 'capacidade': 740}):
            result = inspect_exe_description(patched, 723, text, {}, native_profile=True)
        self.assertEqual(result['status'], 'aplicada')

    def test_identical_new_descriptions_share_one_native_string(self):
        _, rows, _, pending = _apply_card_descriptions(
            sample_exe(), {723: 'AB' * 20, 724: 'AB' * 20}, {}, native_profile=True,
            start=0x801CD5A0, end=0x801CD5A0 + 41)
        self.assertFalse(pending)
        self.assertEqual([row['id'] for row in rows], [723, 724])
        self.assertEqual(rows[0]['offset_exe'], rows[1]['offset_exe'])


if __name__ == '__main__':
    unittest.main()
