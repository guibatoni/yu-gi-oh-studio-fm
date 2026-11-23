"""Testes do contador de LP do BIN PS1: 20000 deve renderizar 5 dígitos."""
import hashlib
import struct
import unittest
from unittest.mock import patch

from fmstudio.core import ModError
from fmstudio.ps1_lp_hud import (
    DECK_COUNT_WORDS, DECK_X_PATCHES, DIGIT_FUNC, LEGACY_LP_WORDS, LP_HUD_PATCHES,
    RETAIL_DIGIT_WORDS, _func_patches, patch_lp_hud, quad_code, verify_lp_hud,
)
from fmstudio.tables import EXE_DELTA

HOOK = 0x80018000


def original_status_renderer():
    data = bytearray(0x10000)
    data[:8] = b'PS-X EXE'
    for pc, old, _, _ in LP_HUD_PATCHES:
        struct.pack_into('<I', data, pc-EXE_DELTA, old)
    for pc, old in DECK_COUNT_WORDS:
        struct.pack_into('<I', data, pc-EXE_DELTA, old)
    for pc, old, _, _ in DECK_X_PATCHES:
        struct.pack_into('<I', data, pc-EXE_DELTA, old)
    struct.pack_into('<44I', data, DIGIT_FUNC-EXE_DELTA, *RETAIL_DIGIT_WORDS)
    return bytes(data)


class LpHudTests(unittest.TestCase):
    def setUp(self):
        self.retail = original_status_renderer()
        self.digest = hashlib.sha256(self.retail).hexdigest()

    def verified(self):
        return patch('fmstudio.ps1_lp_hud.SOURCE_SHA256', self.digest)

    def test_20000_appears_in_five_columns_on_both_sides(self):
        with self.verified():
            out, report = patch_lp_hud(self.retail, self.retail, initial_lp=20000, hook=HOOK)
            self.assertEqual(report['digitos'], 5)
            self.assertEqual(report['status'], 'aplicado')
            self.assertTrue(report['jogador'])
            self.assertTrue(report['adversario'])
            self.assertFalse(report['validado_epsxe'])
            self.assertTrue(verify_lp_hud(self.retail, out, initial_lp=20000))
            changed = {(i - (i % 4)) + EXE_DELTA
                       for i, (a, b) in enumerate(zip(self.retail, out)) if a != b}
            block = quad_code(HOOK)
            allowed = ({pc for pc, *_ in LP_HUD_PATCHES + DECK_X_PATCHES} |
                       {pc for pc, *_ in _func_patches(HOOK)} |
                       set(range(HOOK, HOOK + len(block), 4)))
            self.assertTrue(changed <= allowed)
            for pc, _, patched, _ in LP_HUD_PATCHES + DECK_X_PATCHES:
                self.assertEqual(struct.unpack_from('<I', out, pc-EXE_DELTA)[0], patched)
            self.assertEqual(out[HOOK-EXE_DELTA:HOOK-EXE_DELTA+len(block)], block)
            for pc, _, new in _func_patches(HOOK):
                self.assertEqual(struct.unpack_from('<I', out, pc-EXE_DELTA)[0], new)
            for pc, original in DECK_COUNT_WORDS:
                self.assertEqual(struct.unpack_from('<I', out, pc-EXE_DELTA)[0], original)
            out_again, _ = patch_lp_hud(self.retail, out, initial_lp=20000, hook=HOOK)
            self.assertEqual(out_again, out)

    def test_reapplies_over_previous_eight_pixel_layout(self):
        old = bytearray(self.retail)
        for pc, _, wide, _ in LP_HUD_PATCHES:
            struct.pack_into('<I', old, pc-EXE_DELTA, LEGACY_LP_WORDS.get(pc, wide))
        with self.verified():
            out, report = patch_lp_hud(self.retail, bytes(old), initial_lp=20000, hook=HOOK)
            self.assertEqual(report['status'], 'aplicado')
            self.assertTrue(verify_lp_hud(self.retail, out, initial_lp=20000))

    def test_requires_free_reserved_block(self):
        with self.verified():
            with self.assertRaises(ModError):
                patch_lp_hud(self.retail, self.retail, initial_lp=20000)
            busy = bytearray(self.retail)
            busy[HOOK-EXE_DELTA+8] = 1
            with self.assertRaises(ModError):
                patch_lp_hud(self.retail, bytes(busy), initial_lp=20000, hook=HOOK)

    def test_8000_keeps_original_four_digits(self):
        out, report = patch_lp_hud(self.retail, self.retail, initial_lp=8000)
        self.assertEqual(report['digitos'], 4)
        self.assertEqual(out, self.retail)

    def test_unknown_binary_and_conflicts_fail_closed(self):
        with self.assertRaisesRegex(ModError, 'Drop x15'):
            patch_lp_hud(self.retail, self.retail, initial_lp=20000, hook=HOOK)
        broken = bytearray(self.retail)
        pc, *_ = LP_HUD_PATCHES[0]
        struct.pack_into('<I', broken, pc-EXE_DELTA, 0xFFFFFFFF)
        with self.verified(), self.assertRaisesRegex(ModError, 'conflito'):
            patch_lp_hud(self.retail, bytes(broken), initial_lp=20000, hook=HOOK)
        pc, _ = DECK_COUNT_WORDS[0]
        struct.pack_into('<I', broken, pc-EXE_DELTA, 0)
        with self.verified(), self.assertRaises(ModError):
            patch_lp_hud(self.retail, bytes(broken), initial_lp=20000, hook=HOOK)

    def test_life_points_must_be_positive_int_not_fake_string(self):
        with self.assertRaises(ModError):
            patch_lp_hud(self.retail, self.retail, initial_lp=-1)
        with self.assertRaises(ModError):
            patch_lp_hud(self.retail, self.retail, initial_lp='20000')
        with self.assertRaises(ModError):
            patch_lp_hud(self.retail, self.retail, initial_lp=True)


if __name__ == '__main__':
    unittest.main()
