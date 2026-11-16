"""Check the native export format and readback with synthetic PS1 files."""
import hashlib
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fmstudio.abilities import quick_settings, replace_quick_effects
from fmstudio.core import ModError
from fmstudio.ps1_god24_display import SPRITE_ORIGINAL, SPRITE_RAM, extended_sprite_words
from fmstudio.ps1_runtime import (
    CONFIG_ADDRESS, DUEL_STATE, _rule_patches, compile_effects, install_runtime, verify_effects,
)
from fmstudio.ps1_text import ICON_CODES, patch_descriptions
from test_ps1_content import sample_exe, where


def effect(action, value=0, *, event='continuo', target='proprio', **fields):
    return {'evento': event, 'acao': action, 'alvo': target, 'valor': value, **fields}


class TestNativeRules(unittest.TestCase):
    def setUp(self):
        self.project = SimpleNamespace(
            metadata={'ps1_deck_global_limit': 6},
            effects={
                '9': [
                    effect('ataques_multiplos', 3),
                    effect('monstro_imune_magia'),
                    effect('limite_copias_deck', 5, event='regra_deck'),
                    effect('sem_limite_deck', event='regra_deck'),
                    effect('bonus_por_carta_id', 100, valor_def=50, escopo='inimigos',
                           carta_referencia_id=16, origem_contagem='deck'),
                    effect('cura_lp', 20, event='invocar'),
                ],
            },
            get=lambda cid: {'tipo_id': 2},
        )

    def test_rule_table_uses_individual_limit_and_bonus_scope(self):
        plan = compile_effects(self.project, True)
        self.assertEqual(len(plan.accepted), 5)
        self.assertEqual(len(plan.pending), 1)
        self.assertIn('cura_lp', plan.pending[0])
        self.assertEqual(plan.data[0], 6)
        offset = struct.unpack_from('<H', plan.data, 2 + 2*9)[0]
        self.assertEqual(struct.unpack_from('<BBBBHH', plan.data, offset), (1, 3, 40, 1, 0, 0))
        self.assertEqual(struct.unpack_from('<BBHHH', plan.data, offset+8), (5, 1, 16, 100, 50))

    def test_three_copies_can_override_the_profile_default(self):
        effects = replace_quick_effects([], {'limite_copias': '3'}, default_copies=None)
        self.assertEqual(quick_settings(effects, default_copies=None)['limite_copias'], 3)
        self.assertIsNone(quick_settings([], default_copies=None)['limite_copias'])
        self.assertEqual(replace_quick_effects(effects, {'limite_copias': ''}, default_copies=None), [])

    def test_unknown_profile_has_no_resident_effects(self):
        plan = compile_effects(self.project, False)
        original = sample_exe()
        self.assertEqual(plan.accepted, ())
        self.assertIn('Drop x15', plan.pending[0])
        self.assertEqual(install_runtime(original, original, plan, description_icons=False),
                         (original, None))

    def test_runtime_readback_detects_table_and_hook_divergence(self):
        plan = compile_effects(self.project, True)
        source = bytearray(sample_exe())
        for pc, old, _ in _rule_patches(plan):
            struct.pack_into(f'<{len(old)}I', source, where(pc), *old)
        struct.pack_into('<28I', source, where(SPRITE_RAM), *SPRITE_ORIGINAL)
        source = bytes(source)
        with patch('fmstudio.ps1_runtime.SOURCE_SHA256', hashlib.sha256(source).hexdigest()):
            result, _ = install_runtime(source, source, plan, description_icons=True)
            self.assertEqual(verify_effects(result, plan)['quantidade'], 5)
            self.assertEqual(struct.unpack_from('<28I', result, where(SPRITE_RAM)), extended_sprite_words())
            for address, key in ((CONFIG_ADDRESS, 'tabela_confere'),
                                 (next(_rule_patches(plan))[0], 'pontos_mips_conferem')):
                divergent = bytearray(result)
                divergent[where(address)] ^= 1
                report = verify_effects(divergent, plan)
                self.assertEqual(report['status'], 'divergente')
                self.assertFalse(report[key])
            occupied = bytearray(source)
            occupied[where(DUEL_STATE)] = 1
            with self.assertRaisesRegex(ModError, 'espaço reservado'):
                install_runtime(source, occupied, plan, description_icons=False)


class TestRichDescriptions(unittest.TestCase):
    def test_relocates_aliased_text_with_color_and_custom_icon(self):
        source = bytearray(sample_exe())
        shared_pointer = where(0x801C0000 + 0x102*2)
        struct.pack_into('<H', source, shared_pointer, 0x3000)
        output, descriptions, icons, pending = patch_descriptions(
            source, {1: '{color:azul}ÁB{/color}{icon:ataque_3x}'}, {})
        self.assertFalse(pending)
        self.assertTrue(descriptions[0]['realocada'])
        self.assertEqual(descriptions[0]['acentos_simplificados'], 'Á')
        self.assertEqual(icons, {'ataque_3x'})
        start = where(DUEL_STATE)
        expected = bytes([0xF8, 0x0A, 2, 1, 2, 0xF8, 0x0A, 0, 0xF8, 0x0B,
                          ICON_CODES['ataque_3x'], 0xFF])
        self.assertEqual(output[start:start+len(expected)], expected)
        self.assertEqual(struct.unpack_from('<H', output, shared_pointer)[0], 0x3000)
        self.assertEqual(output[where(0x801C3000):where(0x801C3000)+13],
                         source[where(0x801C3000):where(0x801C3000)+13])

    def test_description_too_tall_is_reported(self):
        source = sample_exe()
        output, rows, icons, pending = patch_descriptions(source, {1: '\n'.join('A' for _ in range(10))}, {})
        self.assertEqual(source, output)
        self.assertEqual(rows, [])
        self.assertEqual(icons, set())
        self.assertIn('10 linhas', pending[0])
