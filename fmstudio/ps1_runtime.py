"""Compile and install Studio effects in the verified Drop x15 PS1 engine."""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

from .continuous import EFFECT_ACTIONS, EQUIPMENT_ACTIONS
from .core import ENTRY_EFFECTS, ENTRY_GROW, ENTRY_SHRINK, ModError, check_effect
from .mod_data import CONFIG_KEY
from .passwords import PS1_ID_PREFIX
from .rarities import RARITIES, TYPE_OVERRIDES, name_style
from .ps1_god24_chest import SOURCE_SHA256
from .ps1_god24_display import SPRITE_ORIGINAL, SPRITE_PATCHED, SPRITE_RAM, extended_sprite_words
from .ps1_runtime_blob import (
    ENTRY_POINTS, RUNTIME, RUNTIME_BASE, RUNTIME_END, RUNTIME_SHA256,
    RUNTIME_EXT, RUNTIME_EXT_BASE, RUNTIME_EXT_END, RUNTIME_EXT_SHA256,
    RUNTIME_PASSWORD, RUNTIME_PASSWORD_BASE, RUNTIME_PASSWORD_END, RUNTIME_PASSWORD_SHA256,
    RUNTIME_MOD, RUNTIME_MOD_BASE, RUNTIME_MOD_END, RUNTIME_MOD_SHA256,
    RUNTIME_MARKERS, RUNTIME_MARKERS_BASE, RUNTIME_MARKERS_END, RUNTIME_MARKERS_SHA256,
    RUNTIME_GRAVE_FILTERS, RUNTIME_GRAVE_FILTERS_BASE, RUNTIME_GRAVE_FILTERS_END, RUNTIME_GRAVE_FILTERS_SHA256,
    RUNTIME_RANK_HUD_BASE,
)
from .tables import CARD_COUNT, DECK_SIZE, DUELIST_COUNT, EXE_DELTA

DUEL_STATE = 0x801CD5A0
CONFIG_ADDRESS = 0x801CD7A0
BANK_END = 0x801D0000
COPY_ACTIONS = frozenset(('sem_limite_deck', 'limite_copias_deck'))
PROTECTIONS = {
    'monstro_imune_magia': 1, 'monstro_imune_armadilha': 2, 'monstro_indestrutivel': 4,
    'dano_perfurante': 8, 'monstro_indestrutivel_batalha': 64,
    'nao_bloqueavel': 16, 'ataque_primeiro_turno': 32,
    'equip_imune_armadilha': 2, 'equip_imune_magia_armadilha': 3, 'equip_indestrutivel': 4,
    'equip_indestrutivel_batalha': 64,
    # Bit livre no runtime; lido pela rotina de ps1_lifelink na cena de batalha.
    'vinculo_vida': 128,
}
PLAY_ACTIONS = (EFFECT_ACTIONS | EQUIPMENT_ACTIONS | set(PROTECTIONS) |
                set(ENTRY_EFFECTS) | {'ataques_multiplos', 'perder_lp_por_ataque', 'dano_lp', 'cura_lp'})
SUPPORTED = PLAY_ACTIONS | COPY_ACTIONS
BONUS_CODES = {'aura_tipo': 1, 'bonus_por_tipo': 2, 'bonus_deck_tipo': 3,
               # mão: bônus de deck com o match marcado (ps1_hand_bonus conta a mão)
               'bonus_mao_tipo': 3,
               'bonus_cemiterio_tipo': 6, ENTRY_GROW: 9, ENTRY_SHRINK: 10}
SCOPES = {'aliados': 0, 'inimigos': 1, 'todos': 2}
MATCH_EITHER = 0x80
SUMMON_DAMAGE = 7
SUMMON_HEAL = 8
DROP_ENTRY = 0x80021810
DECK_INIT = (0x800179F4, 0x80017DB4, 0x800245A0)
TEXT_DRAW = (0x80035E20, 0x80036BCC)
RETAIL_FUSION = 0x80019A60
FUSION_CALLERS = (
    (0x80019D18, 0x8001B0CC),  # Placement and fusion for the player and opponent.
    (0x80027228, 0x80027508),  # AI turn selection.
    (0x800727C0, 0x80072A48),  # AI searches for fusions.
)
CONFIG_EXTRAS = 2 + 2 * (CARD_COUNT + 1)
GRAVE_FILTER_OFFSET = 2  # Reserved directory entry for card ID 0.
FIXED_DECK_CONFIG = CONFIG_EXTRAS + 8
NAME_COLOR_CONFIG = FIXED_DECK_CONFIG + 2
FUSION_CONFIG = NAME_COLOR_CONFIG + 2
NAME_TIERS = {key: color for key, (_, color) in RARITIES.items()}
NAME_TIERS.update({key: color for _, color, key in TYPE_OVERRIDES.values()})


@dataclass(frozen=True)
class EffectPlan:
    data: bytes
    accepted: tuple[tuple[int, str], ...]
    pending: tuple[str, ...]
    global_limit: int
    deck_drops: tuple[int, ...] = ()
    password_prefix: int | None = None
    fixed_decks: tuple[int, ...] = ()
    name_colors: int = 0
    fusions: tuple[tuple[int, int, int], ...] = ()
    capacity: int = CARD_COUNT

    @property
    def fusion_report(self):
        return [{'material_1': a, 'material_2': b, 'resultado': result}
                for a, b, result in self.fusions]

    @property
    def deck_features(self):
        return bool(self.deck_drops or self.fixed_decks)

    @property
    def mod_features(self):
        return self.deck_features or bool(self.name_colors)

    @property
    def copy_rules(self):
        return any(action in COPY_ACTIONS for _, action in self.accepted)

    @property
    def gameplay(self):
        return any(action in PLAY_ACTIONS for _, action in self.accepted)

    @property
    def entry_markers(self):
        return any(action in ENTRY_EFFECTS for _, action in self.accepted)

    @property
    def grave_filters(self):
        return bool(self.data and struct.unpack_from('<H', self.data, GRAVE_FILTER_OFFSET)[0])

    @property
    def data_end(self):
        return CONFIG_ADDRESS + len(self.data) if self.data else DUEL_STATE

    @property
    def bank_end(self):
        if self.grave_filters:
            return RUNTIME_GRAVE_FILTERS_BASE
        if self.entry_markers:
            return RUNTIME_MARKERS_BASE
        if self.mod_features:
            return RUNTIME_MOD_BASE
        if self.password_prefix is not None:
            return RUNTIME_PASSWORD_BASE
        return RUNTIME_EXT_BASE if self.gameplay else BANK_END


def _runtime_bundle(plan):
    if plan.capacity > CARD_COUNT:
        from . import ps1_expanded_runtime_blob as bundle
    else:
        from . import ps1_runtime_blob as bundle
    return bundle


def _name_colors(project, profile, capacity=CARD_COUNT):
    if not profile:
        return {}
    return {cid: name_style(project.get(cid))[2] for cid, card in getattr(project, 'cards', {}).items()
            if 1 <= cid <= capacity and (capacity > CARD_COUNT or not card.get('virtual'))}


def _pack_name_colors(colors, capacity=CARD_COUNT):
    ids = {key: index for index, key in enumerate(NAME_TIERS, 1)}
    lookup = bytearray(capacity + 1)
    for cid, key in colors.items():
        lookup[cid] = ids[key]
    palette = [0]
    for rgb in NAME_TIERS.values():
        channels = [int(rgb[index:index + 2], 16) for index in (1, 3, 5)]
        palette.append(sum(((value + 1) // 2) << (8 * i) for i, value in enumerate(channels)))
    packed = struct.pack(f'<{len(palette)}I', *palette) + bytes(lookup)
    return packed + bytes((-len(packed)) % 4)


def compile_effects(project, profile: bool, *, fixed_decks=None, fusions=None) -> EffectPlan:
    """Keep the same action vocabulary and value checks as the Studio."""
    capacity = 740 if profile and any(722 < cid <= 740 for cid in getattr(project, 'cards', {})) else CARD_COUNT
    extras = 2 + 2 * (capacity + 1)
    fixed_config, color_config, fusion_config = extras + 8, extras + 10, extras + 12
    metadata = getattr(project, 'metadata', {})
    default = metadata.get('ps1_deck_global_limit')
    try:
        default = 3 if default is None else int(str(default))
    except ValueError as exc:
        raise ModError('Limite de cópias PS1 inválido.') from exc
    if not 1 <= default <= 40:
        raise ModError('Limite de cópias PS1 deve ficar entre 1 e 40.')

    accepted, pending = [], []
    config = metadata.get(CONFIG_KEY, {})
    # Desde a v1.7.10 os drops do próprio deck usam tabelas ponderadas
    # POW/TEC/BCD de WA_MRG, compiladas em ps1_mod.compile_mod.
    # Não instalar o antigo hook SelectDeckDrop que sorteava sem pesos.
    deck_drops = ()
    prefix = metadata.get(PS1_ID_PREFIX)
    if prefix is not None and (type(prefix) is not int or not 0 <= prefix <= CARD_COUNT):
        raise ModError('Prefixo dos passwords por ID inválido. Releia os códigos de origem.')
    if not profile:
        pending.extend(f'Drops do deck do duelista #{opponent}: requer o perfil Drop x15.' for opponent in deck_drops)
        if prefix is not None:
            pending.append('Passwords por ID no BIN/CUE exigem o perfil Drop x15.')
        deck_drops, prefix = (), None

    fixed_decks = (fixed_decks or {}) if profile else {}
    colors = _name_colors(project, profile, capacity)
    edited_fusions = tuple((a, b, result) for (a, b), result in sorted((fusions or {}).items())) if profile else ()
    data = bytearray(extras)
    data[0] = default
    if deck_drops or prefix is not None or fixed_decks or colors or edited_fusions or capacity > CARD_COUNT:
        flags = sum(1 << opponent for opponent in deck_drops)
        data.extend(struct.pack('<H', int(f'{prefix or 0:05d}', 16)))
        data.extend(flags.to_bytes(DUELIST_COUNT // 8, byteorder='little'))
        data.append(0)
    if deck_drops or fixed_decks or colors or edited_fusions or capacity > CARD_COUNT:
        data.extend(b'\0' * 4)
        if edited_fusions or capacity > CARD_COUNT:
            data.extend(b'\0' * 4)
            struct.pack_into('<H', data, fusion_config, len(data))
            for a, b, result in edited_fusions:
                data.extend(struct.pack('<I', a | (b << 10) | (result << 20)))
            data.extend(b'\0' * 4)
        if fixed_decks:
            directory = len(data)
            struct.pack_into('<H', data, fixed_config, directory)
            data.extend(b'\0' * (DUELIST_COUNT * 2))
            for opponent, deck in sorted(fixed_decks.items()):
                struct.pack_into('<H', data, directory + opponent * 2, len(data))
                data.extend(struct.pack(f'<{DECK_SIZE}H', *deck))
        if colors:
            struct.pack_into('<H', data, color_config, len(data))
            data.extend(_pack_name_colors(colors, capacity))
    offsets, grave_filters = {}, {}
    for key, effects in sorted(getattr(project, 'effects', {}).items(), key=lambda pair: int(pair[0])):
        cid = int(key)
        if not effects:
            continue
        if not profile or not 1 <= cid <= capacity:
            pending.append(f'#{cid}: {len(effects)} efeito(s) requerem carta original e perfil Drop x15.')
            continue
        card_type = int(project.get(cid)['tipo_id'])
        protections, attacks, equip_attack, cost = 0, 0, 0, 0
        copies = None
        unlimited, entries, bonuses = False, [], []
        for raw in effects:
            action = raw.get('acao')
            if action not in SUPPORTED:
                pending.append(f'#{cid}: {action} requer outra rotina de duelo no PS1.')
                continue
            effect = check_effect(raw)
            if action in ('dano_lp', 'cura_lp') and effect['evento'] != 'invocar':
                if not (action == 'dano_lp' and effect['evento'] == 'atacar'
                        and effect['alvo'] == 'proprio'):
                    pending.append(f'#{cid}: {action} no PS1 exige entrada em campo; '
                                   'somente dano_lp ao próprio controlador é aceito ao atacar.')
                    continue
            attribute = effect.get('atributo_id', -1)
            if effect.get('origem_contagem') == 'cemiterio':
                pending.append(f'#{cid}: {action} com essa zona funciona no Studio.')
                continue
            if max(effect['valor'], effect.get('valor_def', 0)) > 9999:
                pending.append(f'#{cid}: {action} excede 9999 pontos da rotina de efeitos PS1.')
                continue
            needs_monster = action not in COPY_ACTIONS and action not in EQUIPMENT_ACTIONS
            if needs_monster and not (card_type < 20 or card_type == 24):
                pending.append(f'#{cid}: {action} exige carta monstro no PS1.')
                continue
            if action in EQUIPMENT_ACTIONS and card_type != 23:
                pending.append(f'#{cid}: {action} exige carta de Equipamento no PS1.')
                continue
            if action in EFFECT_ACTIONS or action in ENTRY_EFFECTS:
                if action == 'bonus_por_carta_id':
                    match = effect['carta_referencia_id']
                    if match > capacity:
                        pending.append(f'#{cid}: o bônus referencia carta #{match}, fora do catálogo PS1.')
                        continue
                    code = 4 if effect['origem_contagem'] == 'campo' else 5
                    if effect['origem_contagem'] == 'mao':
                        from .ps1_hand_bonus import encode_match
                        match = encode_match(match)     # ID marcado: ps1_hand_bonus conta a mão
                elif action == 'bonus_mao_tipo':
                    from .ps1_hand_bonus import encode_match
                    match = encode_match(effect['tipo_id'])
                    code = BONUS_CODES[action]
                else:
                    match = effect['tipo_id'] & 0xFFFF
                    code = BONUS_CODES[action]
                predicate = (attribute + 1) << 2
                if effect.get('combinar_filtros') == 'ou':
                    predicate |= MATCH_EITHER
                if action == 'bonus_cemiterio_tipo' and attribute != -1:
                    match = grave_filters.setdefault((match, predicate), len(grave_filters))
                scope = SCOPES[effect['escopo']] | predicate
                bonuses.append(struct.pack('<BBHHH', code, scope, match,
                                           effect['valor'], effect.get('valor_def', 0)))
            elif action == 'dano_lp' and effect['evento'] == 'atacar':
                # O campo attack_cost das regras já é cobrado no hook
                # Battle() uma vez por ataque, para ambos os duelistas.
                # Não incluir esse efeito na lista de danos por invocação.
                if cost + effect['valor'] > 9999:
                    pending.append(f'#{cid}: dano LP acumulado ao atacar excede 9999 no PS1.')
                    continue
                cost += effect['valor']
            elif action in ('dano_lp', 'cura_lp'):
                receiver = int(effect['alvo'] == 'inimigo')
                code = SUMMON_HEAL if action == 'cura_lp' else SUMMON_DAMAGE
                bonuses.append(struct.pack('<BBHHH', code, receiver, 0, effect['valor'], 0))
            elif action in PROTECTIONS:
                protections |= PROTECTIONS[action]
            elif action == 'ataques_multiplos':
                attacks = max(attacks, effect['valor'])
            elif action == 'perder_lp_por_ataque':
                if cost + effect['valor'] > 9999:
                    pending.append(f'#{cid}: custo acumulado de ataque excede o limite do PS1.')
                    continue
                cost += effect['valor']
            elif action == 'equip_atk':
                if equip_attack + effect['valor'] > 9999:
                    pending.append(f'#{cid}: bônus acumulado de Equip excede o limite do PS1.')
                    continue
                equip_attack += effect['valor']
            elif action == 'sem_limite_deck':
                unlimited = True
            else:
                value = effect['valor']
                copies = min(copies, value) if copies is not None else value
            entries.append((cid, action))
        if not entries:
            continue
        if len(bonuses) > 255:
            raise ModError(f'#{cid}: o PS1 comporta até 255 condições de bônus por carta.')
        limit_byte = 0xFF if copies == 0 else (40 if unlimited else copies or 0)
        payload = struct.pack('<BBBBHH', protections, attacks, limit_byte,
                              len(bonuses), equip_attack, cost) + b''.join(bonuses)
        if payload not in offsets:
            offsets[payload] = len(data)
            data.extend(payload)
        struct.pack_into('<H', data, 2 + 2 * cid, offsets[payload])
        accepted.extend(entries)
    if grave_filters:
        struct.pack_into('<H', data, GRAVE_FILTER_OFFSET, len(data))
        for kind, predicate in grave_filters:
            data.extend(struct.pack('<BBHHH', 0, predicate, kind, 0, 0))
        data.extend(bytes(8))
    data[1] = any(action in ENTRY_EFFECTS for _, action in accepted)
    configured = accepted or deck_drops or prefix is not None or fixed_decks or colors or edited_fusions or capacity > CARD_COUNT
    plan = EffectPlan(bytes(data) if configured else b'', tuple(accepted), tuple(pending), default,
                      deck_drops, prefix, tuple(sorted(fixed_decks)), len(colors), edited_fusions, capacity)
    if plan.data_end > plan.bank_end:
        raise ModError('As regras nativas excedem a área reservada do perfil Drop x15.')
    return plan


def _jump(target: int, *, link=False) -> int:
    return (0x0C000000 if link else 0x08000000) | ((target >> 2) & 0x03FFFFFF)


def _change_words(out: bytearray, pc: int, before: tuple[int, ...], after: tuple[int, ...]):
    offset = pc - EXE_DELTA
    expected = struct.pack(f'<{len(before)}I', *before)
    if out[offset:offset+len(expected)] != expected:
        raise ModError(f'Extensão PS1: instruções incompatíveis em 0x{pc:08X}.')
    out[offset:offset+len(expected)] = struct.pack(f'<{len(after)}I', *after)


SCENE_HANDLERS = (
    (0x8009099C, 0x80018608, 'Startup'),
    (0x800909A0, 0x8001898C, 'DrawPhase'),
    (0x800909AC, 0x8001D670, 'FieldActions'),
    (0x800909B4, 0x80019D18, 'Placement'),
    (0x800909B8, 0x8001B170, 'ConfirmPlacement'),
    (0x800909BC, 0x8001F55C, 'Battle'),
    (0x800909C4, 0x8001825C, 'Resume'),
)
EFFECT_HANDLERS = (
    (0x80090A80, 0x800257A0, 'BoardDestruction'),
    (0x80090A88, 0x8002538C, 'MonsterRemoval'),
    (0x80090A90, 0x800255FC, 'StopDefense'),
    (0x80090A98, 0x8002596C, 'Raigeki'),
    (0x80090AA0, 0x80025BEC, 'Reveal'),
    (0x80090AA8, 0x80025D30, 'StatPenalty'),
    (0x80090AB0, 0x80025F3C, 'Swords'),
)
FUNCTION_ENTRIES = (
    (0x800170C8, (0x8482000E, 0x84830012), 'CalculateStats'),
    (0x8001778C, (0x3C02801A, 0x24447AD8), 'ResetCards'),
    (0x80024954, (0x27BDFFE8, 0xAFB00010), 'RemoveCard'),
    (0x8002C9B4, (0x27BDFFD8, 0xAFB20018), 'CollectTargets'),
)
CALLS = (
    (0x8001F67C, 0x8001F0D0, 'AttackTrap'),
    (0x80019870, 0x80026BA4, 'SpellUsed'),
)
MARKER_CALLS = (
    (0x8001A618, 0x80024954, 'ConsumeFusionMaterial'),
    (0x8001B590, 0x80024D34, 'CreateMarkedPlacement'),
    (0x8002673C, 0x80024D34, 'CreateMarkedPlacement'),
)


def _rule_patches(plan: EffectPlan):
    ENTRY_POINTS = _runtime_bundle(plan).ENTRY_POINTS
    if plan.gameplay:
        marker_wrappers = {'FieldActions': 'FieldActionsWithMarkers',
                           'ResetCards': 'ResetCardsWithMarkers'} if plan.entry_markers else {}
        for pc, old, key in (*SCENE_HANDLERS, *EFFECT_HANDLERS):
            yield pc, (old,), (ENTRY_POINTS[marker_wrappers.get(key, key)],)
        for pc, original_words, key in FUNCTION_ENTRIES:
            yield pc, original_words, (_jump(ENTRY_POINTS[marker_wrappers.get(key, key)]), 0)
        for pc, original_target, key in (*CALLS, *(MARKER_CALLS if plan.entry_markers else ())):
            yield pc, (_jump(original_target, link=True),), (_jump(ENTRY_POINTS[key], link=True),)
    if plan.copy_rules:
        # The native inventory check and the forty-slot check stay in place.
        # Exodia defaults to one copy unless the project supplies an override.
        yield 0x8003383C, (0x10600022,), (0,)
        yield 0x80033870, (0x2C420003, 0x10400014), (_jump(ENTRY_POINTS['DeckCopyGate']), 0)
    if plan.deck_features and not plan.gameplay:
        pc, original_words, key = FUNCTION_ENTRIES[1]
        yield pc, original_words, (_jump(ENTRY_POINTS[key]), 0)
    if plan.name_colors:
        yield 0x80090EAC, (0x80037DA4,), (ENTRY_POINTS['InsertTierName'],)
        yield 0x80090F54, (0x80038E7C,), (ENTRY_POINTS['EndTierName'],)


def _option_calls(plan):
    if plan.deck_features:
        yield (*DECK_INIT, 'DealConfiguredDecks')
    if plan.password_prefix is not None:
        yield 0x8002D684, 0x8002D6C8, 0x8016A37C, 'UpdatePasswordShop'
    if plan.name_colors:
        yield (*TEXT_DRAW, 0x800849F0, 'SortTierGlyph')
        yield (*TEXT_DRAW, 0x80084320, 'SortTierPolygon')
    if plan.fusions or plan.capacity > CARD_COUNT:
        for start, end in FUSION_CALLERS:
            yield start, end, RETAIL_FUSION, 'CheckEditedFusion'


def _call_sites(exe, start, end, target):
    words = {_jump(target), _jump(target, link=True)}
    for pc in range(start, min(end, len(exe) + EXE_DELTA - 3), 4):
        word, = struct.unpack_from('<I', exe, pc - EXE_DELTA)
        if word in words:
            yield pc, word


def _valid_original_drop_entry(raw):
    """Allow ordinary displaced instructions or a same-region jump with its delay slot."""
    if len(raw) != 8:
        return False
    for index, word in enumerate(struct.unpack('<II', raw)):
        opcode = word >> 26
        if index == 0 and opcode == 2:
            continue
        if opcode == 0 and (word & 63) in (0, 2, 3, 4, 6, 7, 0x21, 0x23, 0x24, 0x25, 0x26, 0x2A, 0x2B):
            continue
        if opcode not in (8, 9, 10, 11, 12, 13, 14, 15, 32, 33, 35, 36, 37, 40, 41, 43):
            return False
    return True


def _mod_program(plan, drop_entry):
    bundle = _runtime_bundle(plan)
    RUNTIME_MOD, ENTRY_POINTS = bundle.RUNTIME_MOD, bundle.ENTRY_POINTS
    if not plan.deck_drops:
        return RUNTIME_MOD
    if not _valid_original_drop_entry(drop_entry):
        raise ModError('A entrada da rotina de drops do SLUS não pode ser executada na extensão.')
    position = ENTRY_POINTS['RetailCardDrop'] - RUNTIME_MOD_BASE
    return RUNTIME_MOD[:position] + drop_entry + RUNTIME_MOD[position + 8:]


def _valid_call_count(key, count):
    if key == 'UpdatePasswordShop':
        return count == 1
    return 1 <= count <= 4


def verify_effects(exe: bytes, plan: EffectPlan, *, original: bytes | None = None) -> dict:
    """Read the resident code, rules and hooks from the selected BIN/CUE."""
    # A animação de LP ao entrar em campo troca um salto dentro do runtime.
    from .ps1_life_splash import runtime_view
    from .ps1_lifelink import runtime_view as lifelink_view
    from .ps1_subtypes import runtime_view as subtype_view
    from .ps1_hand_bonus import runtime_view as hand_view
    from .ps1_fixed_drop import runtime_view as fixed_drop_view
    exe = fixed_drop_view(hand_view(subtype_view(lifelink_view(runtime_view(exe)))))
    bundle = _runtime_bundle(plan)
    ENTRY_POINTS = bundle.ENTRY_POINTS
    RUNTIME = bundle.RUNTIME
    RUNTIME_END = bundle.RUNTIME_END
    RUNTIME_SHA256 = bundle.RUNTIME_SHA256
    RUNTIME_EXT = bundle.RUNTIME_EXT
    RUNTIME_EXT_END = bundle.RUNTIME_EXT_END
    RUNTIME_EXT_SHA256 = bundle.RUNTIME_EXT_SHA256
    RUNTIME_PASSWORD = bundle.RUNTIME_PASSWORD
    RUNTIME_PASSWORD_END = bundle.RUNTIME_PASSWORD_END
    RUNTIME_PASSWORD_SHA256 = bundle.RUNTIME_PASSWORD_SHA256
    RUNTIME_MOD = bundle.RUNTIME_MOD
    RUNTIME_MOD_END = bundle.RUNTIME_MOD_END
    RUNTIME_MOD_SHA256 = bundle.RUNTIME_MOD_SHA256
    RUNTIME_MARKERS = bundle.RUNTIME_MARKERS
    RUNTIME_MARKERS_END = bundle.RUNTIME_MARKERS_END
    RUNTIME_MARKERS_SHA256 = bundle.RUNTIME_MARKERS_SHA256
    RUNTIME_GRAVE_FILTERS = bundle.RUNTIME_GRAVE_FILTERS
    RUNTIME_GRAVE_FILTERS_END = bundle.RUNTIME_GRAVE_FILTERS_END
    RUNTIME_GRAVE_FILTERS_SHA256 = bundle.RUNTIME_GRAVE_FILTERS_SHA256
    code_start, cfg_start = RUNTIME_BASE - EXE_DELTA, CONFIG_ADDRESS - EXE_DELTA
    code_ok = exe[code_start:code_start+len(RUNTIME)] == RUNTIME
    if plan.capacity > CARD_COUNT:
        from .ps1_expansion import inspect_expansion
        code_ok = code_ok and inspect_expansion(exe)['status'] == 'aplicado'
    if plan.gameplay:
        ext_start = RUNTIME_EXT_BASE - EXE_DELTA
        code_ok = code_ok and exe[ext_start:ext_start+len(RUNTIME_EXT)] == RUNTIME_EXT
    if plan.entry_markers:
        start = RUNTIME_MARKERS_BASE - EXE_DELTA
        code_ok = code_ok and exe[start:start + len(RUNTIME_MARKERS)] == RUNTIME_MARKERS
    if plan.grave_filters:
        start = RUNTIME_GRAVE_FILTERS_BASE - EXE_DELTA
        code_ok = code_ok and exe[start:start + len(RUNTIME_GRAVE_FILTERS)] == RUNTIME_GRAVE_FILTERS
    if plan.password_prefix is not None and plan.capacity == CARD_COUNT:
        password_start = RUNTIME_PASSWORD_BASE - EXE_DELTA
        code_ok = code_ok and exe[password_start:password_start+len(RUNTIME_PASSWORD)] == RUNTIME_PASSWORD
    if plan.mod_features:
        start = RUNTIME_MOD_BASE - EXE_DELTA
        original_start = DROP_ENTRY - EXE_DELTA
        trampoline = ENTRY_POINTS['RetailCardDrop'] - EXE_DELTA
        drop_entry = (original[original_start:original_start + 8] if original is not None
                      else exe[trampoline:trampoline + 8])
        try:
            code_ok = code_ok and exe[start:start + len(RUNTIME_MOD)] == _mod_program(plan, drop_entry)
        except ModError:
            code_ok = False
    if not plan.data:
        return {'status': 'sem_regras_configuradas', 'rotina_presente': code_ok, 'quantidade': 0}
    table_ok = exe[cfg_start:cfg_start+len(plan.data)] == plan.data
    hooks_ok = all(exe[pc-EXE_DELTA:pc-EXE_DELTA+4*len(words)] ==
                   struct.pack(f'<{len(words)}I', *words)
                   for pc, _, words in _rule_patches(plan))
    for start, end, target, key in _option_calls(plan):
        installed = list(_call_sites(exe, start, end, ENTRY_POINTS[key]))
        hooks_ok = hooks_ok and _valid_call_count(key, len(installed)) and not any(_call_sites(exe, start, end, target))
        if hooks_ok and original is not None:
            expected = [(pc, _jump(ENTRY_POINTS[key], link=word >> 26 == 3))
                        for pc, word in _call_sites(original, start, end, target)]
            hooks_ok = installed == expected
    if plan.deck_drops:
        offset = DROP_ENTRY - EXE_DELTA
        hooks_ok = hooks_ok and exe[offset:offset + 8] == struct.pack('<II', _jump(ENTRY_POINTS['SelectDeckDrop']), 0)
    applied = code_ok and table_ok and hooks_ok
    return {'status': 'aplicado' if applied else 'divergente',
            'rotina_presente': code_ok, 'tabela_confere': table_ok,
            'pontos_mips_conferem': hooks_ok, 'quantidade': len(plan.accepted) if applied else 0,
            'drops_do_deck': list(plan.deck_drops) if applied else [],
            'password_id_prefix': plan.password_prefix if applied else None,
            'decks_fixos': list(plan.fixed_decks) if applied else [],
            'nomes_tier': plan.name_colors if applied else 0,
            'fusoes': plan.fusion_report if applied else []}


def install_runtime(original: bytes, exe: bytes, plan: EffectPlan, *,
                    description_icons: bool) -> tuple[bytes, dict | None]:
    bundle = _runtime_bundle(plan)
    ENTRY_POINTS = bundle.ENTRY_POINTS
    RUNTIME = bundle.RUNTIME
    RUNTIME_END = bundle.RUNTIME_END
    RUNTIME_SHA256 = bundle.RUNTIME_SHA256
    RUNTIME_EXT = bundle.RUNTIME_EXT
    RUNTIME_EXT_END = bundle.RUNTIME_EXT_END
    RUNTIME_EXT_SHA256 = bundle.RUNTIME_EXT_SHA256
    RUNTIME_PASSWORD = bundle.RUNTIME_PASSWORD
    RUNTIME_PASSWORD_END = bundle.RUNTIME_PASSWORD_END
    RUNTIME_PASSWORD_SHA256 = bundle.RUNTIME_PASSWORD_SHA256
    RUNTIME_MOD = bundle.RUNTIME_MOD
    RUNTIME_MOD_END = bundle.RUNTIME_MOD_END
    RUNTIME_MOD_SHA256 = bundle.RUNTIME_MOD_SHA256
    RUNTIME_MARKERS = bundle.RUNTIME_MARKERS
    RUNTIME_MARKERS_END = bundle.RUNTIME_MARKERS_END
    RUNTIME_MARKERS_SHA256 = bundle.RUNTIME_MARKERS_SHA256
    RUNTIME_GRAVE_FILTERS = bundle.RUNTIME_GRAVE_FILTERS
    RUNTIME_GRAVE_FILTERS_END = bundle.RUNTIME_GRAVE_FILTERS_END
    RUNTIME_GRAVE_FILTERS_SHA256 = bundle.RUNTIME_GRAVE_FILTERS_SHA256
    if not plan.data and not description_icons:
        return exe, None
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA256 or len(exe) != len(original):
        raise ModError('Extensão PS1 exige o executável conhecido do Drop x15.')
    start, end = RUNTIME_BASE - EXE_DELTA, RUNTIME_END - EXE_DELTA
    data_start, data_end = DUEL_STATE - EXE_DELTA, plan.data_end - EXE_DELTA
    if (end - start != len(RUNTIME) or hashlib.sha256(RUNTIME).hexdigest() != RUNTIME_SHA256
            or end > 0x80100000 - EXE_DELTA or data_end > plan.bank_end - EXE_DELTA):
        raise ModError('Extensão PS1 incompleta ou fora dos limites da RAM.')
    if any(exe[start:end]) or any(exe[data_start:data_end]):
        raise ModError('Extensão PS1 conflita com código ou texto no espaço reservado.')
    out = bytearray(exe)
    out[start:end] = RUNTIME
    if plan.gameplay:
        ext_start, ext_end = RUNTIME_EXT_BASE - EXE_DELTA, RUNTIME_EXT_END - EXE_DELTA
        if (not RUNTIME_EXT or ext_end - ext_start != len(RUNTIME_EXT)
                or hashlib.sha256(RUNTIME_EXT).hexdigest() != RUNTIME_EXT_SHA256
                or RUNTIME_EXT_END > 0x801CFF00 or ext_end > len(exe)):
            raise ModError('Extensão de efeitos PS1 incompleta ou fora da área reservada.')
        if any(exe[ext_start:ext_end]):
            raise ModError('Extensão PS1 conflita com código ou texto no espaço reservado.')
        out[ext_start:ext_end] = RUNTIME_EXT
    if plan.entry_markers:
        begin, end = RUNTIME_MARKERS_BASE - EXE_DELTA, RUNTIME_MARKERS_END - EXE_DELTA
        if (not RUNTIME_MARKERS or end - begin != len(RUNTIME_MARKERS) or end > len(exe)
                or RUNTIME_MARKERS_END > RUNTIME_RANK_HUD_BASE
                or hashlib.sha256(RUNTIME_MARKERS).hexdigest() != RUNTIME_MARKERS_SHA256):
            raise ModError('Extensão de marcadores PS1 incompleta ou fora da área reservada.')
        if any(exe[begin:end]):
            raise ModError('Extensão de marcadores PS1 conflita com código ou texto na área reservada.')
        out[begin:end] = RUNTIME_MARKERS
    if plan.grave_filters:
        begin, end = RUNTIME_GRAVE_FILTERS_BASE - EXE_DELTA, RUNTIME_GRAVE_FILTERS_END - EXE_DELTA
        if (not RUNTIME_GRAVE_FILTERS or end - begin != len(RUNTIME_GRAVE_FILTERS) or end > len(exe)
                or RUNTIME_GRAVE_FILTERS_END > RUNTIME_MARKERS_BASE
                or hashlib.sha256(RUNTIME_GRAVE_FILTERS).hexdigest() != RUNTIME_GRAVE_FILTERS_SHA256):
            raise ModError('Extensão dos filtros de cemitério PS1 incompleta ou fora da área reservada.')
        if any(exe[begin:end]):
            raise ModError('Extensão dos filtros de cemitério PS1 conflita com a área reservada.')
        out[begin:end] = RUNTIME_GRAVE_FILTERS
    if plan.password_prefix is not None and plan.capacity == CARD_COUNT:
        password_start = RUNTIME_PASSWORD_BASE - EXE_DELTA
        password_end = RUNTIME_PASSWORD_END - EXE_DELTA
        if (not RUNTIME_PASSWORD or password_end - password_start != len(RUNTIME_PASSWORD)
                or hashlib.sha256(RUNTIME_PASSWORD).hexdigest() != RUNTIME_PASSWORD_SHA256
                or RUNTIME_PASSWORD_END > RUNTIME_EXT_BASE or password_end > len(exe)):
            raise ModError('Extensão de passwords PS1 fora da área reservada.')
        if any(exe[password_start:password_end]):
            raise ModError('Extensão de passwords PS1 conflita com a área reservada.')
        out[password_start:password_end] = RUNTIME_PASSWORD
    drop_offset = DROP_ENTRY - EXE_DELTA
    if plan.mod_features:
        mod_start, mod_end = RUNTIME_MOD_BASE - EXE_DELTA, RUNTIME_MOD_END - EXE_DELTA
        if (mod_end - mod_start != len(RUNTIME_MOD) or mod_end > len(exe)
                or hashlib.sha256(RUNTIME_MOD).hexdigest() != RUNTIME_MOD_SHA256
                or RUNTIME_MOD_END > RUNTIME_PASSWORD_BASE):
            raise ModError('Extensão de decks e nomes PS1 fora da área reservada.')
        if any(exe[mod_start:mod_end]):
            raise ModError('Extensão de decks e nomes PS1 conflita com código ou texto no espaço reservado.')
        out[mod_start:mod_end] = _mod_program(plan, original[drop_offset:drop_offset + 8])
    offsets = []

    def patch(pc, before, after):
        _change_words(out, pc, before, after)
        offsets.append(f'0x{pc:08X}')

    for pc, before, after in _rule_patches(plan):
        patch(pc, before, after)
    for start, end, target, key in _option_calls(plan):
        matches = list(_call_sites(original, start, end, target))
        if not _valid_call_count(key, len(matches)):
            raise ModError(f'Extensão PS1: chamadas divergentes em 0x{start:08X}.')
        for pc, old_word in matches:
            patch(pc, (old_word,), (_jump(ENTRY_POINTS[key], link=old_word >> 26 == 3),))
    if plan.deck_drops:
        previous = struct.unpack_from('<II', original, drop_offset)
        patch(DROP_ENTRY, previous, (_jump(ENTRY_POINTS['SelectDeckDrop']), 0))
    if description_icons:
        original_renderer = SPRITE_RAM - EXE_DELTA
        observed = struct.unpack_from('<28I', out, original_renderer)
        if observed not in (SPRITE_ORIGINAL, SPRITE_PATCHED):
            raise ModError('Extensão PS1 encontrou um renderizador de ícones incompatível.')
        patch(SPRITE_RAM, observed, extended_sprite_words(ENTRY_POINTS))

    if plan.data:
        config = CONFIG_ADDRESS - EXE_DELTA
        out[config:config + len(plan.data)] = plan.data
    report = {'status': 'aplicado', 'efeitos': [
        {'id': cid, 'acao': action} for cid, action in plan.accepted],
        'pontos_mips': offsets, 'bytes_tabela': len(plan.data),
        'limite_padrao_por_id': plan.global_limit,
        'drops_do_deck': list(plan.deck_drops), 'password_id_prefix': plan.password_prefix,
        'decks_fixos': list(plan.fixed_decks), 'nomes_tier': plan.name_colors,
        'fusoes': plan.fusion_report,
        'icones_de_descricao': description_icons, 'validado_no_epsxe': False}
    return bytes(out), report
