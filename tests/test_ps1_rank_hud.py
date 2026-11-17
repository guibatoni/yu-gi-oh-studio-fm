"""Guard and round-trip the rank HUD without a copyrighted disc fixture."""
import hashlib
import struct
from unittest import TestCase
from unittest.mock import patch

from fmstudio.ps1_lp_hud import DECK_COUNT_WORDS, LP_HUD_PATCHES, patch_lp_hud, verify_lp_hud
from fmstudio.ps1_rank_hud import (
    CALL_PC, CODE_END, CODE_START, CONTEXT_PC, RETAIL_WORDS, inspect_rank_hud, patch_rank_hud,
)
from fmstudio.ps1_runtime_blob import RUNTIME_RANK_HUD_BASE
from fmstudio.tables import EXE_DELTA


class RankHudTests(TestCase):
    def fixture(self):
        data = bytearray(CODE_END)
        struct.pack_into('<12I', data, CONTEXT_PC - EXE_DELTA, *RETAIL_WORDS)
        for pc, retail, *_ in (*LP_HUD_PATCHES, *DECK_COUNT_WORDS):
            struct.pack_into('<I', data, pc - EXE_DELTA, retail)
        return bytes(data)

    def test_rank_and_five_digit_life_share_the_same_hud(self):
        source = self.fixture()
        digest = hashlib.sha256(source).hexdigest()
        self.assertEqual(inspect_rank_hud(source)['status'], 'ausente')
        with patch('fmstudio.ps1_rank_hud.SOURCE_SHA256', digest), patch(
                'fmstudio.ps1_lp_hud.SOURCE_SHA256', digest):
            wide, _ = patch_lp_hud(source, source, initial_lp=20000)
            updated, report = patch_rank_hud(source, wide)
            self.assertEqual(report['status'], 'aplicado')
            self.assertTrue(verify_lp_hud(source, updated, initial_lp=20000))
            self.assertEqual(patch_rank_hud(source, updated)[0], updated)
        self.assertEqual(inspect_rank_hud(updated)['status'], 'aplicado')
        self.assertEqual(updated[:CALL_PC - EXE_DELTA], wide[:CALL_PC - EXE_DELTA])
        self.assertEqual(updated[CALL_PC - EXE_DELTA + 4:CODE_START], wide[CALL_PC - EXE_DELTA + 4:CODE_START])
        corrupt = bytearray(updated)
        corrupt[CODE_START] ^= 1
        self.assertEqual(inspect_rank_hud(corrupt)['status'], 'divergente')

    def test_guard_preserves_full_bank_and_unknown_layout(self):
        source = self.fixture()
        self.assertEqual(patch_rank_hud(source, source)[1]['status'], 'perfil_incompativel')
        digest = hashlib.sha256(source).hexdigest()
        with patch('fmstudio.ps1_rank_hud.SOURCE_SHA256', digest):
            original, report = patch_rank_hud(source, source, occupied_until=RUNTIME_RANK_HUD_BASE + 1)
            self.assertIs(original, source)
            self.assertEqual(report['status'], 'sem_espaco')
            conflicting = bytearray(source)
            conflicting[CONTEXT_PC - EXE_DELTA] ^= 0x80
            original, report = patch_rank_hud(source, conflicting)
            self.assertIs(original, conflicting)
            self.assertEqual(report['status'], 'conflito')
