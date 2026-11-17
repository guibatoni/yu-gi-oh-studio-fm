"""Verifica o patch guardado da IA nativa, sem depender de imagem protegida."""
import hashlib
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fmstudio.core import ModError
from fmstudio.mod_data import normalize_rules
from fmstudio.ps1_ai import (
    AI_MODES, HARD_AI_PATCHES, mode_for, patch_hard_ai, verify_hard_ai,
)
from fmstudio.tables import EXE_DELTA


def fake_retail():
    data = bytearray(0x20000)
    for pc, original, _, _ in HARD_AI_PATCHES:
        struct.pack_into('<I', data, pc - EXE_DELTA, original)
    return bytes(data)


class NativeAiTests(unittest.TestCase):
    def setUp(self):
        self.original = fake_retail()
        self.digest = hashlib.sha256(self.original).hexdigest()

    def with_verified_source(self):
        return patch('fmstudio.ps1_ai.SOURCE_SHA256', self.digest)

    def test_hard_ai_changes_only_five_known_conditional_branches(self):
        with self.with_verified_source():
            updated, report = patch_hard_ai(self.original, self.original, mode='dificil')
            self.assertEqual(report['status'], 'aplicado')
            self.assertEqual(report['modo'], 'dificil')
            self.assertFalse(report['validado_epsxe'])
            self.assertEqual(len(report['rotinas']), 5)
            self.assertTrue(verify_hard_ai(self.original, updated, mode='dificil'))
            diffs = [i for i, (old, new) in enumerate(zip(self.original, updated)) if old != new]
            expected = []
            for pc, old, new, _ in HARD_AI_PATCHES:
                offset = pc - EXE_DELTA
                self.assertEqual(struct.unpack_from('<I', updated, offset)[0], new)
                self.assertEqual(struct.unpack_from('<I', self.original, offset)[0], old)
                expected.extend(i for i in range(offset, offset+4)
                                if self.original[i] != updated[i])
                # Não mudar delay slots, fundamentais em MIPS.
                self.assertEqual(updated[offset+4:offset+8],
                                 self.original[offset+4:offset+8])
            self.assertEqual(diffs, expected)

    def test_normal_preserves_retail_behavior_and_repeat_is_idempotent(self):
        with self.with_verified_source():
            normal, report = patch_hard_ai(self.original, self.original, mode='normal')
            self.assertEqual(normal, self.original)
            self.assertEqual(report['status'], 'original')
            self.assertTrue(verify_hard_ai(self.original, normal, mode='normal'))
            advanced, _ = patch_hard_ai(self.original, self.original, mode='dificil')
            twice, _ = patch_hard_ai(self.original, advanced, mode='dificil')
            self.assertEqual(twice, advanced)
            self.assertFalse(verify_hard_ai(self.original, advanced, mode='normal'))

    def test_unknown_game_or_conflicting_patch_is_rejected_atomically(self):
        with self.assertRaisesRegex(ModError, 'Drop x15'):
            patch_hard_ai(self.original, self.original, mode='dificil')
        invalid = bytearray(self.original)
        pc, _, _, _ = HARD_AI_PATCHES[-1]
        struct.pack_into('<I', invalid, pc-EXE_DELTA, 0xFFFFFFFF)
        before = bytes(invalid)
        with self.with_verified_source(), self.assertRaisesRegex(ModError, 'opcode inesperado'):
            patch_hard_ai(self.original, before, mode='dificil')
        self.assertEqual(bytes(invalid), before)

    def test_config_mod_mode_validation_and_default(self):
        project = SimpleNamespace(metadata={})
        self.assertEqual(mode_for(project), 'normal')
        self.assertEqual(AI_MODES, ('normal', 'dificil'))
        project.metadata = {'edicao_mod': {'ia_ps1': 'normal'}}
        self.assertEqual(mode_for(project), 'normal')
        self.assertEqual(normalize_rules({'ia_ps1':'dificil'}, {}), {'ia_ps1':'dificil'})
        with self.assertRaises(ModError):
            normalize_rules({'ia_ps1':'impossivel'}, {})
        project.metadata['edicao_mod']['ia_ps1'] = 'impossivel'
        with self.assertRaises(ModError):
            mode_for(project)


if __name__ == '__main__':
    unittest.main()
