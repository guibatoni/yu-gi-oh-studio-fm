"""Check the native export format and readback with synthetic PS1 files."""
import hashlib
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fmstudio.abilities import quick_settings, replace_quick_effects
from fmstudio.core import ENTRY_GROW, ENTRY_SHRINK, ENTRY_TYPE_EVENT, ModError, check_effect
from fmstudio.ps1_god24_display import SPRITE_ORIGINAL, SPRITE_RAM, extended_sprite_words
from fmstudio.ps1_runtime import (
    CONFIG_ADDRESS, DROP_ENTRY, DUEL_STATE, FIXED_DECK_CONFIG, FUSION_CONFIG, GRAVE_FILTER_OFFSET, MATCH_EITHER,
    NAME_COLOR_CONFIG, RUNTIME_EXT_BASE, RUNTIME_GRAVE_FILTERS_BASE, RUNTIME_MARKERS_BASE, RUNTIME_MOD_BASE,
    RUNTIME_PASSWORD_BASE, SUMMON_DAMAGE, SUMMON_HEAL,
    _jump, _option_calls, _rule_patches, _valid_original_drop_entry, compile_effects, install_runtime, verify_effects,
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
        self.assertEqual(len(plan.accepted), 6)
        self.assertEqual(len(plan.pending), 0)
        self.assertEqual(plan.data[0], 6)
        offset = struct.unpack_from('<H', plan.data, 2 + 2*9)[0]
        self.assertEqual(struct.unpack_from('<BBBBHH', plan.data, offset), (1, 3, 40, 2, 0, 0))
        self.assertEqual(struct.unpack_from('<BBHHH', plan.data, offset+8), (5, 1, 16, 100, 50))
        self.assertEqual(struct.unpack_from('<BBHHH', plan.data, offset+16), (SUMMON_HEAL, 0, 0, 20, 0))

    def test_summon_damage_and_attribute_aura_compile_for_monsters(self):
        self.project.effects = {'9': [
            effect('dano_lp', 600, event='invocar', target='inimigo'),
            effect('cura_lp', 2000, event='invocar', target='proprio'),
            effect('cura_lp', 750, event='atacar', target='proprio'),
            effect('dano_lp', 500, event='atacar', target='inimigo'),
            effect('aura_tipo', 250, target='aliados_tipo', tipo_id=2, atributo_id=3, valor_def=50),
        ]}
        plan = compile_effects(self.project, True)
        start = struct.unpack_from('<H', plan.data, 2 + 2*9)[0]
        self.assertEqual(plan.accepted, ((9, 'dano_lp'), (9, 'cura_lp'), (9, 'aura_tipo')))
        self.assertEqual(len(plan.pending), 2)
        self.assertEqual(struct.unpack_from('<BBHHH', plan.data, start+8), (SUMMON_DAMAGE, 1, 0, 600, 0))
        self.assertEqual(struct.unpack_from('<BBHHH', plan.data, start+16), (SUMMON_HEAL, 0, 0, 2000, 0))
        self.assertEqual(struct.unpack_from('<BBHHH', plan.data, start+24), (1, 16, 2, 250, 50))

    def test_attack_dano_lp_proprio_uses_real_native_battle_attack_cost(self):
        self.project.effects = {'9': [
            effect('dano_lp', 450, event='atacar', target='proprio'),
            effect('perder_lp_por_ataque', 150, event='atacar', target='proprio'),
            effect('cura_lp', 300, event='invocar', target='proprio'),
        ]}
        plan = compile_effects(self.project, True)
        self.assertEqual(plan.pending, ())
        self.assertEqual(plan.accepted,
                         ((9, 'dano_lp'), (9, 'perder_lp_por_ataque'), (9, 'cura_lp')))
        record = struct.unpack_from('<H', plan.data, 2 + 2 * 9)[0]
        protection, attacks, copies, bonus_count, equip, attack_cost = struct.unpack_from(
            '<BBBBHH', plan.data, record)
        self.assertEqual((bonus_count, attack_cost), (1, 600))
        self.assertEqual(struct.unpack_from('<BBHHH', plan.data, record + 8),
                         (SUMMON_HEAL, 0, 0, 300, 0))
        # Não converter o dano do ataque em efeito de invocação.
        self.assertTrue(plan.gameplay)
        self.assertIn((9, 'dano_lp'), plan.accepted)

    def test_attack_dano_lp_enemy_and_heal_remain_explicitly_unsupported_on_ps1(self):
        self.project.effects = {'9': [
            effect('dano_lp', 500, event='atacar', target='inimigo'),
            effect('cura_lp', 500, event='atacar', target='proprio'),
            effect('dano_lp', 400, event='atacar', target='proprio'),
        ]}
        plan = compile_effects(self.project, True)
        self.assertEqual(plan.accepted, ((9, 'dano_lp'),))
        self.assertEqual(len(plan.pending), 2)
        self.assertEqual(struct.unpack_from(
            '<H', plan.data,
            struct.unpack_from('<H', plan.data, 2 + 2 * 9)[0] + 6)[0], 400)

    def test_attack_self_lp_cost_overflow_is_not_silently_truncated(self):
        self.project.effects = {'9': [
            effect('dano_lp', 9500, event='atacar', target='proprio'),
            effect('perder_lp_por_ataque', 700, event='atacar', target='proprio'),
        ]}
        plan = compile_effects(self.project, True)
        self.assertEqual(plan.accepted, ((9, 'dano_lp'),))
        self.assertTrue(any('limite do PS1' in x for x in plan.pending))

    def test_three_copies_can_override_the_profile_default(self):
        effects = replace_quick_effects([], {'limite_copias': '3'}, default_copies=None)
        self.assertEqual(quick_settings(effects, default_copies=None)['limite_copias'], 3)
        self.assertIsNone(quick_settings([], default_copies=None)['limite_copias'])
        self.assertEqual(replace_quick_effects(effects, {'limite_copias': ''}, default_copies=None), [])

    def test_markers_select_and_verify_their_native_hooks_and_bank(self):
        growth = effect(ENTRY_GROW, 200, event=ENTRY_TYPE_EVENT, tipo_id=19)
        reduction = effect(ENTRY_SHRINK, 400, event='invocar', target='aliados_tipo', tipo_id=0, valor_def=0)
        self.project.effects = {'9': [growth, reduction]}
        self.assertEqual(check_effect(dict(growth, valor_def=''))['valor_def'], 200)
        for changes in ({'tipo_id': 20}, {'valor': -1}, {'evento': 'continuo'}, {'valor': 0}):
            with self.subTest(changes=changes), self.assertRaises(ModError):
                check_effect(dict(growth, **changes))
        plan = compile_effects(self.project, True)
        self.assertEqual(plan.accepted, ((9, ENTRY_GROW), (9, ENTRY_SHRINK)))
        self.assertEqual((plan.data[1], plan.bank_end), (1, RUNTIME_MARKERS_BASE))
        start = struct.unpack_from('<H', plan.data, 2 + 2*9)[0]
        self.assertEqual(struct.unpack_from('<BBHHH', plan.data, start+8), (9, 2, 19, 200, 200))
        self.assertEqual(struct.unpack_from('<BBHHH', plan.data, start+16), (10, 1, 0, 400, 0))
        source = bytearray(sample_exe())
        for pc, words, _ in _rule_patches(plan):
            struct.pack_into(f'<{len(words)}I', source, where(pc), *words)
        source = bytes(source)
        with patch('fmstudio.ps1_runtime.SOURCE_SHA256', hashlib.sha256(source).hexdigest()):
            result, _ = install_runtime(source, source, plan, description_icons=False)
            self.assertEqual(verify_effects(result, plan)['quantidade'], 2)
            occupied = bytearray(source)
            occupied[where(RUNTIME_MARKERS_BASE)] = 1
            with self.assertRaisesRegex(ModError, 'marcadores PS1 conflita'):
                install_runtime(source, occupied, plan, description_icons=False)
        damaged = bytearray(result)
        damaged[where(RUNTIME_MARKERS_BASE)] ^= 1
        self.assertFalse(verify_effects(damaged, plan)['rotina_presente'])

    def test_cemetery_predicates_share_counters_across_scopes(self):
        union = effect('bonus_cemiterio_tipo', 200, tipo_id=19, atributo_id=1, combinar_filtros='ou')
        self.project.effects = {'9': [union, dict(union, escopo='inimigos', valor=100),
                                     dict(union, tipo_id=-1, valor=50)]}
        plan = compile_effects(self.project, True)
        self.assertFalse(plan.pending)
        self.assertTrue(plan.grave_filters)
        self.assertEqual(plan.bank_end, RUNTIME_GRAVE_FILTERS_BASE)
        data = plan.data
        rules, = struct.unpack_from('<H', data, 2 + 2*9)
        table, = struct.unpack_from('<H', data, GRAVE_FILTER_OFFSET)
        self.assertEqual(struct.unpack_from('<BBHHH', data, rules+8), (6, MATCH_EITHER | 8, 0, 200, 0))
        self.assertEqual(struct.unpack_from('<BBHHH', data, rules+16), (6, MATCH_EITHER | 9, 0, 100, 0))
        self.assertEqual(struct.unpack_from('<BBHHH', data, rules+24), (6, 8, 1, 50, 0))
        self.assertEqual(struct.unpack_from('<BBHHH', data, table), (0, MATCH_EITHER | 8, 19, 0, 0))
        self.assertEqual(struct.unpack_from('<BBHHH', data, table+8), (0, 8, 0xFFFF, 0, 0))
        self.assertEqual(data[table+16:], bytes(8))
        source = bytearray(sample_exe())
        for pc, words, _ in _rule_patches(plan):
            struct.pack_into(f'<{len(words)}I', source, where(pc), *words)
        source = bytes(source)
        with patch('fmstudio.ps1_runtime.SOURCE_SHA256', hashlib.sha256(source).hexdigest()):
            result, _ = install_runtime(source, source, plan, description_icons=False)
        self.assertEqual(verify_effects(result, plan)['quantidade'], 3)
        damaged = bytearray(result)
        damaged[where(RUNTIME_GRAVE_FILTERS_BASE)] ^= 1
        self.assertFalse(verify_effects(damaged, plan)['rotina_presente'])

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
            self.assertEqual(verify_effects(result, plan)['quantidade'], 6)
            self.assertEqual(struct.unpack_from('<28I', result, where(SPRITE_RAM)), extended_sprite_words())
            for address, key in ((CONFIG_ADDRESS, 'tabela_confere'),
                                 (RUNTIME_EXT_BASE, 'rotina_presente'),
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


    def test_drop_and_password_installation_check_each_native_call(self):
        self.project.effects = {}
        self.project.metadata.update({
            'edicao_mod': {'duelistas': {'1': {'drops_do_deck': True}, '39': {'drops_do_deck': True}}},
            'ps1_password_id_prefix': 10,
        })
        plan = compile_effects(self.project, True)
        self.assertEqual(plan.bank_end, RUNTIME_PASSWORD_BASE)
        self.assertEqual(plan.deck_drops, ())
        self.assertFalse(plan.gameplay)
        source = bytearray(sample_exe())
        for pc, old, _ in _rule_patches(plan):
            struct.pack_into(f'<{len(old)}I', source, where(pc), *old)
        for pc, _, target, _ in _option_calls(plan):
            struct.pack_into('<I', source, where(pc), _jump(target, link=True))
        original = bytes(source)
        with patch('fmstudio.ps1_runtime.SOURCE_SHA256', hashlib.sha256(original).hexdigest()):
            output, report = install_runtime(original, original, plan, description_icons=False)
        self.assertEqual(report['drops_do_deck'], [])
        check = verify_effects(output, plan)
        self.assertEqual(check['password_id_prefix'], 10)
        self.assertEqual(check['drops_do_deck'], [])
        for pc, _, target, _ in _option_calls(plan):
            divergent = bytearray(output)
            struct.pack_into('<I', divergent, where(pc), _jump(target, link=True))
            self.assertEqual(verify_effects(divergent, plan)['status'], 'divergente')
        unsupported = compile_effects(self.project, False)
        self.assertEqual(unsupported.data, b'')
        self.assertEqual(len(unsupported.pending), 1)


    def test_drop_gateway_accepts_an_absolute_jump_and_rejects_relative_branch(self):
        self.assertTrue(_valid_original_drop_entry(struct.pack('<II', _jump(0x80023F00), 0x24420001)))
        self.assertFalse(_valid_original_drop_entry(struct.pack('<II', 0x10400017, 0)))

    def test_fixed_deck_and_name_colors_verify_exact_bytes(self):
        self.project.effects = {}
        self.project.cards = {
            1: {'tipo_id': 0, 'raridade': 'epica'},
            2: {'tipo_id': 24, 'raridade': 'comum'},
            3: {'tipo_id': 21},
        }
        self.project.get = self.project.cards.__getitem__
        deck = tuple(range(100, 140))
        self.project.metadata['edicao_mod'] = {'duelistas': {'1': {'drops_do_deck': True}}}
        plan = compile_effects(self.project, True, fixed_decks={1: deck})
        directory, colors = struct.unpack_from('<HH', plan.data, FIXED_DECK_CONFIG)
        self.assertEqual(colors, struct.unpack_from('<H', plan.data, NAME_COLOR_CONFIG)[0])
        offset = struct.unpack_from('<H', plan.data, directory + 2)[0]
        self.assertEqual(struct.unpack_from('<40H', plan.data, offset), deck)
        palette = struct.unpack_from('<10I', plan.data, colors)
        tiers = plan.data[colors + 40:colors + 44]
        self.assertEqual(tiers, bytes((0, 4, 6, 8)))
        self.assertEqual([palette[index] for index in tiers[1:]], [0x803D5B, 0x3D1D09, 0x643C80])
        source = bytearray(sample_exe())
        for pc, old, _ in _rule_patches(plan):
            struct.pack_into(f'<{len(old)}I', source, where(pc), *old)
        for index, (pc, _, target, _) in enumerate(_option_calls(plan)):
            location = pc + index * 16
            struct.pack_into('<I', source, where(location), _jump(target, link=True))
            struct.pack_into('<I', source, where(location + 8), _jump(target, link=True))
        struct.pack_into('<II', source, where(DROP_ENTRY), 0x27BDFFF0, 0xAFBF000C)
        original = bytes(source)
        with patch('fmstudio.ps1_runtime.SOURCE_SHA256', hashlib.sha256(original).hexdigest()):
            output, _ = install_runtime(original, original, plan, description_icons=False)
        report = verify_effects(output, plan, original=original)
        self.assertEqual(report['decks_fixos'], [1])
        self.assertEqual(report['drops_do_deck'], [])
        self.assertEqual(report['nomes_tier'], 3)
        self.assertEqual(output[where(DROP_ENTRY):where(DROP_ENTRY)+8],
                         original[where(DROP_ENTRY):where(DROP_ENTRY)+8])
        for changed in (CONFIG_ADDRESS + offset, CONFIG_ADDRESS + colors, RUNTIME_MOD_BASE):
            corrupted = bytearray(output)
            corrupted[where(changed)] ^= 1
            self.assertEqual(verify_effects(corrupted, plan, original=original)['status'], 'divergente')


    def test_edited_fusion_is_verified_in_the_native_bin(self):
        self.project.effects = {}
        plan = compile_effects(self.project, True, fusions={(16, 56): 72, (500, 722): 721})
        start = struct.unpack_from('<H', plan.data, FUSION_CONFIG)[0]
        self.assertEqual(struct.unpack_from('<III', plan.data, start),
                         (16 | 56 << 10 | 72 << 20, 500 | 722 << 10 | 721 << 20, 0))
        source = bytearray(sample_exe())
        for pc, _, target, _ in _option_calls(plan):
            struct.pack_into('<I', source, where(pc), _jump(target, link=True))
        original = bytes(source)
        self.assertEqual(verify_effects(original, plan, original=original)['fusoes'], [])
        with patch('fmstudio.ps1_runtime.SOURCE_SHA256', hashlib.sha256(original).hexdigest()):
            output, report = install_runtime(original, original, plan, description_icons=False)
        expected = [{'material_1': 16, 'material_2': 56, 'resultado': 72},
                    {'material_1': 500, 'material_2': 722, 'resultado': 721}]
        self.assertEqual(report['fusoes'], expected)
        self.assertEqual(verify_effects(output, plan, original=original)['fusoes'], expected)
        corrupted = bytearray(output)
        corrupted[where(CONFIG_ADDRESS + start)] ^= 1
        self.assertEqual(verify_effects(corrupted, plan, original=original)['status'], 'divergente')
        for pc, _, target, _ in _option_calls(plan):
            corrupted = bytearray(output)
            struct.pack_into('<I', corrupted, where(pc), _jump(target, link=True))
            self.assertEqual(verify_effects(corrupted, plan, original=original)['fusoes'], [])


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
