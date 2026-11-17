"""Testes do contador de LP do BIN PS1: 20000 deve renderizar 5 dígitos."""
import hashlib
import struct
import unittest
from unittest.mock import patch

from fmstudio.core import ModError
from fmstudio.ps1_lp_hud import (
    DECK_COUNT_WORDS, LP_HUD_PATCHES, patch_lp_hud, verify_lp_hud,
)
from fmstudio.tables import EXE_DELTA


def original_status_renderer():
    data = bytearray(0x10000)
    data[:8] = b'PS-X EXE'
    for pc, old, _, _ in LP_HUD_PATCHES:
        struct.pack_into('<I', data, pc-EXE_DELTA, old)
    for pc, old in DECK_COUNT_WORDS:
        struct.pack_into('<I', data, pc-EXE_DELTA, old)
    return bytes(data)


class LpHudTests(unittest.TestCase):
    def setUp(self):
        self.retail = original_status_renderer()
        self.digest = hashlib.sha256(self.retail).hexdigest()

    def verified(self):
        return patch('fmstudio.ps1_lp_hud.SOURCE_SHA256', self.digest)

    def test_20000_appears_in_five_columns_on_both_sides(self):
        with self.verified():
            out, report = patch_lp_hud(self.retail, self.retail, initial_lp=20000)
            self.assertEqual(report['digitos'], 5)
            self.assertEqual(report['status'], 'aplicado')
            self.assertTrue(report['jogador'])
            self.assertTrue(report['adversario'])
            self.assertFalse(report['validado_epsxe'])
            self.assertTrue(verify_lp_hud(self.retail, out, initial_lp=20000))
            changed = [i for i, (a, b) in enumerate(zip(self.retail, out)) if a!=b]
            self.assertEqual(len(changed), 4)
            self.assertEqual(changed, [pc-EXE_DELTA for pc, *_ in LP_HUD_PATCHES])
            for pc, _, patched, _ in LP_HUD_PATCHES:
                self.assertEqual(struct.unpack_from('<I', out, pc-EXE_DELTA)[0], patched)
            for pc, original in DECK_COUNT_WORDS:
                self.assertEqual(struct.unpack_from('<I', out, pc-EXE_DELTA)[0], original)
            out_again, _ = patch_lp_hud(self.retail, out, initial_lp=20000)
            self.assertEqual(out_again, out)

    def test_8000_keeps_original_four_digits(self):
        out, report = patch_lp_hud(self.retail, self.retail, initial_lp=8000)
        self.assertEqual(report['digitos'], 4)
        self.assertEqual(out, self.retail)

    def test_unknown_binary_and_conflicts_fail_closed(self):
        with self.assertRaisesRegex(ModError, 'Drop x15'):
            patch_lp_hud(self.retail, self.retail, initial_lp=20000)
        broken = bytearray(self.retail)
        pc, *_ = LP_HUD_PATCHES[0]
        struct.pack_into('<I', broken, pc-EXE_DELTA, 0xFFFFFFFF)
        with self.verified(), self.assertRaisesRegex(ModError, 'conflito'):
            patch_lp_hud(self.retail, bytes(broken), initial_lp=20000)
        pc, _ = DECK_COUNT_WORDS[0]
        struct.pack_into('<I', broken, pc-EXE_DELTA, 0)
        with self.verified(), self.assertRaises(ModError):
            patch_lp_hud(self.retail, bytes(broken), initial_lp=20000)

    def test_life_points_must_be_positive_int_not_fake_string(self):
        with self.assertRaises(ModError):
            patch_lp_hud(self.retail, self.retail, initial_lp=-1)
        with self.assertRaises(ModError):
            patch_lp_hud(self.retail, self.retail, initial_lp='20000')
        with self.assertRaises(ModError):
            patch_lp_hud(self.retail, self.retail, initial_lp=True)


if __name__ == '__main__':
    unittest.main()
