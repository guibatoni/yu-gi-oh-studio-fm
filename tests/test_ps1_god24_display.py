"""Conferência das janelas do tipo God e da gravação conjunta da textura."""

import hashlib
import struct
import unittest

from fmstudio.core import ModError
from fmstudio.deep_extract import NAME_TABLE
from fmstudio.ps1_god24_display import (GOLD_PALETTE, ICON_ROWS, NAME_OFFSET, REGIONS, SPRITE_RAM,
                                       apply, extended_sprite_words, inspect)
from fmstudio.ps1_runtime_blob import RUNTIME, RUNTIME_BASE
from fmstudio.tables import EXE_DELTA, STATS_ADDR


class God24DisplayTests(unittest.TestCase):
    def setUp(self):
        exe = bytearray(0x1D0800)
        exe[:8] = b'PS-X EXE'
        for offset, before, _ in REGIONS:
            exe[offset:offset + len(before)] = before
        self.mars_pointer = NAME_TABLE + 2 * 0x318 - EXE_DELTA
        struct.pack_into('<H', exe, self.mars_pointer, 0x8B80)
        self.source = bytes(exe)
        self.digest = hashlib.sha256(self.source).hexdigest()
        self.wa = bytearray(GOLD_PALETTE + 32)
        struct.pack_into('<16H', self.wa, GOLD_PALETTE, 0, *range(1, 16))

    def test_installs_name_and_icon_and_keeps_stats_and_mars(self):
        edited = bytearray(self.source)
        stats = STATS_ADDR - EXE_DELTA + 15 * 4
        struct.pack_into('<I', edited, stats, 24 << 26 | 1 << 22 | 40 << 9 | 300)
        exe, wa, report = apply(self.source, edited, self.wa, source_sha256=self.digest)

        self.assertEqual(report, inspect(exe, wa))
        self.assertEqual(report['nome'], 'God')
        self.assertTrue(report['icone_instalado'])
        self.assertFalse(report['validado_no_epsxe'])
        self.assertEqual(exe[NAME_OFFSET:NAME_OFFSET + 4], bytes.fromhex('29 04 0C FF'))
        self.assertEqual(exe[self.mars_pointer:self.mars_pointer + 2], b'\x80\x8b')
        self.assertEqual(exe[stats:stats + 4], edited[stats:stats + 4])
        expected_exe = bytearray(edited)
        for offset, _, after in REGIONS:
            expected_exe[offset:offset + len(after)] = after
        self.assertEqual(exe, expected_exe)
        for offset in ICON_ROWS:
            self.wa[offset:offset + 8] = wa[offset:offset + 8]
        self.assertEqual(wa, self.wa)

    def test_verification_requires_both_executable_and_texture(self):
        exe, wa, _ = apply(self.source, self.source, self.wa, source_sha256=self.digest)
        self.assertEqual(inspect(exe)['status'], 'aguardando_textura')
        self.assertEqual(inspect(exe, self.wa)['status'], 'textura_divergente')
        wrong_text = bytearray(exe)
        wrong_text[NAME_OFFSET] = 0
        self.assertFalse(inspect(wrong_text, wa)['icone_instalado'])
        self.assertEqual(inspect(self.source, wa)['status'], 'original')

    def test_rejects_other_profile_or_existing_code_and_texture(self):
        with self.assertRaisesRegex(ModError, 'fora do perfil'):
            apply(self.source, self.source, self.wa)
        edited = bytearray(self.source)
        edited[REGIONS[0][0]] ^= 1
        with self.assertRaisesRegex(ModError, 'assinatura divergente'):
            apply(self.source, edited, self.wa, source_sha256=self.digest)
        self.wa[ICON_ROWS[0]] = 0x12
        with self.assertRaisesRegex(ModError, 'está ocupada'):
            apply(self.source, self.source, self.wa, source_sha256=self.digest)

    def test_description_icons_can_be_present_without_the_god_type_icon(self):
        exe = bytearray(self.source)
        struct.pack_into('<28I', exe, SPRITE_RAM - EXE_DELTA, *extended_sprite_words())
        self.assertEqual(inspect(exe)['status'], 'assinatura_divergente')
        start = RUNTIME_BASE - EXE_DELTA
        exe[start:start + len(RUNTIME)] = RUNTIME
        report = inspect(exe)
        self.assertEqual(report['status'], 'icones_de_descricao')
        self.assertFalse(report['icone_instalado'])
