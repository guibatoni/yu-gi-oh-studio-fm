"""Opt-in crash catcher for the "Doar e duelar" ePSXe crash (PC 0x1AAE78)."""
import os
import struct
import unittest
from unittest.mock import patch

from fmstudio.campaign_quests import (DIAG_CATCHER, DIAG_CATCHER_OFFSET, DIAG_GAP,
                                      DIAG_RECORDS_START, STORY_DUELISTS, TABLE_START,
                                      compile_table, generate_quests, table_size)
from fmstudio.core import ModError
from fmstudio.ps1_campaign_quests import (DIAGNOSTIC_ENV, OBSERVED_CRASH_PCS, OVERLAY_HEADER,
                                          OVERLAY_SIZE, build_quest_overlay)
from fmstudio.ps1_expansion import EXPANDED_LEVELS
from fmstudio import ps1_campaign_quest_overlay_blob as blob

from test_campaign_quests import GLYPHS, MANUAL, sample_quests


def build(diagnostic, requirements=None):
    settings = {'seed': 'teste', 'requisitos': requirements or MANUAL}
    with patch('fmstudio.ps1_campaign_quests.glyph_map', return_value=(GLYPHS, [])):
        return build_quest_overlay(b'', sample_quests(), settings,
                                   level_address=EXPANDED_LEVELS, diagnostic=diagnostic)


def word(payload, address):
    at = OVERLAY_HEADER.size + address - blob.BASE
    return struct.unpack_from('<I', payload, at)[0]


class QuestCrashDiagnosticTests(unittest.TestCase):
    def test_default_layout_is_unchanged(self):
        catalog = sample_quests()
        config = generate_quests(catalog, 'mips', MANUAL)
        table = compile_table(config, catalog, GLYPHS)
        self.assertEqual(struct.unpack_from('<H', table, 4 + 2 * STORY_DUELISTS[0])[0], TABLE_START)
        with patch.dict(os.environ, {DIAGNOSTIC_ENV: ''}):
            default, _, _ = build(None)
        self.assertEqual(default, build(False)[0])
        self.assertNotIn(DIAG_CATCHER, default)

    def test_catcher_covers_every_observed_crash_pc(self):
        payload, _, table = build(True)
        base = blob.ENTRY_POINTS['QuestConfiguration']
        self.assertEqual(table_size(table), len(table))
        self.assertEqual(table[TABLE_START:DIAG_RECORDS_START], DIAG_GAP)
        catcher = base + DIAG_CATCHER_OFFSET
        for pc in OBSERVED_CRASH_PCS:
            self.assertLess(base + TABLE_START, pc)
            self.assertLess(pc, catcher)
            # Every word from the crash PC up to the catcher is a NOP (sll $0,$0,0).
            for address in range(pc & ~3, catcher, 4):
                self.assertEqual(word(payload, address), 0, hex(address))
        self.assertEqual(payload[OVERLAY_HEADER.size + catcher - blob.BASE:][:len(DIAG_CATCHER)],
                         DIAG_CATCHER)
        self.assertEqual(len(payload), OVERLAY_SIZE)

    def test_catcher_instructions(self):
        words = struct.unpack('<9I', DIAG_CATCHER)
        self.assertEqual(words[2], 0x03F8C024)          # and t8, ra, t8
        self.assertEqual(words[5] >> 26, 0x0F)          # lui t9 (immediate is the trap)
        self.assertEqual((words[5] & 0xFFFF) << 16 >> 26, 0x1B)
        self.assertEqual(words[7], 0x03000008)          # jr t8
        self.assertEqual(words[8], 0)                   # delay slot

    def test_env_enables_and_worst_case_table_still_fits(self):
        requirements = [*MANUAL['2'], {'tipo': 'carta', 'alvo': 1, 'quantidade': 1}]
        full = {str(npc): requirements for npc in range(2, 39)}
        with patch.dict(os.environ, {DIAGNOSTIC_ENV: '1'}):
            payload, config, table = build(None, full)
        self.assertEqual(len(config['quests']), 37)
        self.assertIn(DIAG_CATCHER, payload)
        self.assertEqual(table_size(table), len(table))

    def test_tampered_gap_is_rejected(self):
        _, _, table = build(True)
        broken = bytearray(table)
        broken[DIAG_CATCHER_OFFSET] ^= 1
        with self.assertRaises(ModError):
            table_size(bytes(broken))


if __name__ == '__main__':
    unittest.main()
