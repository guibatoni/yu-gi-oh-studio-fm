"""Compile and install Studio effects in the verified Drop x15 PS1 engine."""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

from .continuous import EFFECT_ACTIONS, EQUIPMENT_ACTIONS
from .core import ModError, check_effect
from .mod_data import CONFIG_KEY, drops_from_deck
from .passwords import PS1_ID_PREFIX
from .rarities import RARITIES, TYPE_OVERRIDES, name_style
from .ps1_god24_chest import SOURCE_SHA256
from .ps1_god24_display import SPRITE_ORIGINAL, SPRITE_PATCHED, SPRITE_RAM, extended_sprite_words
from .ps1_runtime_blob import (
    ENTRY_POINTS, RUNTIME, RUNTIME_BASE, RUNTIME_END, RUNTIME_SHA256,
    RUNTIME_EXT, RUNTIME_EXT_BASE, RUNTIME_EXT_END, RUNTIME_EXT_SHA256,
    RUNTIME_PASSWORD, RUNTIME_PASSWORD_BASE, RUNTIME_PASSWORD_END, RUNTIME_PASSWORD_SHA256,
    RUNTIME_MOD, RUNTIME_MOD_BASE, RUNTIME_MOD_END, RUNTIME_MOD_SHA256,
)
from .tables import CARD_COUNT, DECK_SIZE, DUELIST_COUNT, EXE_DELTA

DUEL_STATE = 0x801CD5A0
CONFIG_ADDRESS = 0x801CD7A0
BANK_END = 0x801D0000
COPY_ACTIONS = frozenset(('sem_limite_deck', 'limite_copias_deck'))
PROTECTIONS = {
    'monstro_imune_magia': 1, 'monstro_imune_armadilha': 2, 'monstro_indestrutivel': 4,
    'dano_perfurante': 8,
    'nao_bloqueavel': 16, 'ataque_primeiro_turno': 32,
    'equip_imune_armadilha': 2, 'equip_imune_magia_armadilha': 3, 'equip_indestrutivel': 4,
}
PLAY_ACTIONS = ((EFFECT_ACTIONS - {'bonus_mao_tipo'}) | EQUIPMENT_ACTIONS | set(PROTECTIONS) |
                {'ataques_multiplos', 'perder_lp_por_ataque', 'dano_lp'})
SUPPORTED = PLAY_ACTIONS | COPY_ACTIONS
BONUS_CODES = {'aura_tipo': 1, 'bonus_por_tipo': 2, 'bonus_deck_tipo': 3,
               'bonus_cemiterio_tipo': 6}
SCOPES = {'aliados': 0, 'inimigos': 1, 'todos': 2}
SUMMON_DAMAGE = 7
DROP_ENTRY = 0x80021810
DECK_INIT = (0x800179F4, 0x80017DB4, 0x800245A0)
TEXT_DRAW = (0x80035E20, 0x80036BCC)
CONFIG_EXTRAS = 2 + 2 * (CARD_COUNT + 1)
FIXED_DECK_CONFIG = CONFIG_EXTRAS + 8
NAME_COLOR_CONFIG = FIXED_DECK_CONFIG + 2
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
    def data_end(self):
        return CONFIG_ADDRESS + len(self.data) if self.data else DUEL_STATE

    @property
    def bank_end(self):
        if self.mod_features:
            return RUNTIME_MOD_BASE
        if self.password_prefix is not None:
            return RUNTIME_PASSWORD_BASE
        return RUNTIME_EXT_BASE if self.gameplay else BANK_END


def _name_colors(project, profile):
    if not profile:
        return {}
    return {cid: name_style(project.get(cid))[2] for cid, card in getattr(project, 'cards', {}).items()
            if 1 <= cid <= CARD_COUNT and not card.get('virtual')}


def _pack_name_colors(colors):
    ids = {key: index for index, key in enumerate(NAME_TIERS, 1)}
    lookup = bytearray(CARD_COUNT + 1)
    for cid, key in colors.items():
        lookup[cid] = ids[key]
    palette = [0]
    for rgb in NAME_TIERS.values():
        channels = [int(rgb[index:index + 2], 16) for index in (1, 3, 5)]
        palette.append(sum(((value + 1) // 2) << (8 * i) for i, value in enumerate(channels)))
    return struct.pack(f'<{len(palette)}I', *palette) + bytes(lookup) + b'\0'


def compile_effects(project, profile: bool, *, fixed_decks=None) -> EffectPlan:
    """Keep the same action vocabulary and value checks as the Studio."""
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
    deck_drops = tuple(opponent for opponent in range(DUELIST_COUNT) if drops_from_deck(config, opponent))
    prefix = metadata.get(PS1_ID_PREFIX)
    if prefix is not None and (type(prefix) is not int or not 0 <= prefix <= CARD_COUNT):
        raise ModError('Prefixo dos passwords por ID inválido. Releia os códigos de origem.')
    if not profile:
        pending.extend(f'Drops do deck do duelista #{opponent}: requer o perfil Drop x15.' for opponent in deck_drops)
        if prefix is not None:
            pending.append('Passwords por ID no BIN/CUE exigem o perfil Drop x15.')
        deck_drops, prefix = (), None

    fixed_decks = (fixed_decks or {}) if profile else {}
    colors = _name_colors(project, profile)
    data = bytearray(CONFIG_EXTRAS)
    data[0] = default
    if deck_drops or prefix is not None or fixed_decks or colors:
        flags = sum(1 << opponent for opponent in deck_drops)
        data.extend(struct.pack('<H', int(f'{prefix or 0:05d}', 16)))
        data.extend(flags.to_bytes(DUELIST_COUNT // 8, byteorder='little'))
        data.append(0)
    if deck_drops or fixed_decks or colors:
        data.extend(b'\0' * 4)
        if fixed_decks:
            directory = len(data)
            struct.pack_into('<H', data, FIXED_DECK_CONFIG, directory)
            data.extend(b'\0' * (DUELIST_COUNT * 2))
            for opponent, deck in sorted(fixed_decks.items()):
                struct.pack_into('<H', data, directory + opponent * 2, len(data))
                data.extend(struct.pack(f'<{DECK_SIZE}H', *deck))
        if colors:
            struct.pack_into('<H', data, NAME_COLOR_CONFIG, len(data))
            data.extend(_pack_name_colors(colors))
    offsets = {}
    for key, effects in sorted(getattr(project, 'effects', {}).items(), key=lambda pair: int(pair[0])):
        cid = int(key)
        if not effects:
            continue
        if not profile or not 1 <= cid <= CARD_COUNT:
            pending.append(f'#{cid}: {len(effects)} efeito(s) requerem carta original e perfil Drop x15.')
            continue
        card_type = int(project.get(cid)['tipo_id'])
        protections, attacks, copies, equip_attack, cost = 0, 0, 0, 0, 0
        unlimited, entries, bonuses = False, [], []
        for raw in effects:
            action = raw.get('acao')
            if action not in SUPPORTED:
                pending.append(f'#{cid}: {action} requer outra rotina de duelo no PS1.')
                continue
            effect = check_effect(raw)
            if action == 'dano_lp' and effect['evento'] != 'invocar':
                pending.append(f'#{cid}: dano direto PS1 exige gatilho de entrada em campo.')
                continue
            attribute = effect.get('atributo_id', -1)
            if ((attribute != -1 and action == 'bonus_cemiterio_tipo')
                    or effect.get('origem_contagem') in ('mao', 'cemiterio')):
                pending.append(f'#{cid}: {action} com esse filtro ou zona funciona no Studio.')
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
            if action in EFFECT_ACTIONS:
                if action == 'bonus_por_carta_id':
                    match = effect['carta_referencia_id']
                    if match > CARD_COUNT:
                        pending.append(f'#{cid}: o bônus referencia carta #{match}, fora do catálogo PS1.')
                        continue
                    code = 4 if effect['origem_contagem'] == 'campo' else 5
                else:
                    match = effect['tipo_id'] & 0xFFFF
                    code = BONUS_CODES[action]
                scope = SCOPES[effect['escopo']] | ((attribute + 1) << 2)
                bonuses.append(struct.pack('<BBHHH', code, scope, match,
                                           effect['valor'], effect.get('valor_def', 0)))
            elif action == 'dano_lp':
                receiver = int(effect['alvo'] == 'inimigo')
                bonuses.append(struct.pack('<BBHHH', SUMMON_DAMAGE, receiver, 0, effect['valor'], 0))
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
                copies = min(copies, value) if copies else value
            entries.append((cid, action))
        if not entries:
            continue
        if len(bonuses) > 255:
            raise ModError(f'#{cid}: o PS1 comporta até 255 condições de bônus por carta.')
        payload = struct.pack('<BBBBHH', protections, attacks, 40 if unlimited else copies,
                              len(bonuses), equip_attack, cost) + b''.join(bonuses)
        if payload not in offsets:
            offsets[payload] = len(data)
            data.extend(payload)
        struct.pack_into('<H', data, 2 + 2 * cid, offsets[payload])
        accepted.extend(entries)
    plan = EffectPlan(bytes(data) if accepted or deck_drops or prefix is not None or fixed_decks or colors else b'',
                      tuple(accepted), tuple(pending), default, deck_drops, prefix, tuple(sorted(fixed_decks)), len(colors))
    if plan.data_end > plan.bank_end:
        raise ModError('A tabela de efeitos excede a área reservada do perfil Drop x15.')
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


def _rule_patches(plan: EffectPlan):
    if plan.gameplay:
        for pc, old, key in (*SCENE_HANDLERS, *EFFECT_HANDLERS):
            yield pc, (old,), (ENTRY_POINTS[key],)
        for pc, original_words, key in FUNCTION_ENTRIES:
            yield pc, original_words, (_jump(ENTRY_POINTS[key]), 0)
        for pc, original_target, key in CALLS:
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


def _call_sites(exe, start, end, target):
    words = {_jump(target), _jump(target, link=True)}
    for pc in range(start, min(end, len(exe) + EXE_DELTA - 3), 4):
        word, = struct.unpack_from('<I', exe, pc - EXE_DELTA)
        if word in words:
            yield pc, word


def _valid_original_drop_entry(raw):
    """The trampoline can execute ordinary instructions, without relocating branches."""
    if len(raw) != 8:
        return False
    for word in struct.unpack('<II', raw):
        opcode = word >> 26
        if opcode == 0 and (word & 63) in (0, 2, 3, 4, 6, 7, 0x21, 0x23, 0x24, 0x25, 0x26, 0x2A, 0x2B):
            continue
        if opcode not in (8, 9, 10, 11, 12, 13, 14, 15, 32, 33, 35, 36, 37, 40, 41, 43):
            return False
    return True


def _mod_program(plan, drop_entry):
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
    code_start, cfg_start = RUNTIME_BASE - EXE_DELTA, CONFIG_ADDRESS - EXE_DELTA
    code_ok = exe[code_start:code_start+len(RUNTIME)] == RUNTIME
    if plan.gameplay:
        ext_start = RUNTIME_EXT_BASE - EXE_DELTA
        code_ok = code_ok and exe[ext_start:ext_start+len(RUNTIME_EXT)] == RUNTIME_EXT
    if plan.password_prefix is not None:
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
            'nomes_tier': plan.name_colors if applied else 0}


def install_runtime(original: bytes, exe: bytes, plan: EffectPlan, *,
                    description_icons: bool) -> tuple[bytes, dict | None]:
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
    if plan.password_prefix is not None:
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
        patch(SPRITE_RAM, observed, extended_sprite_words())

    if plan.data:
        config = CONFIG_ADDRESS - EXE_DELTA
        out[config:config + len(plan.data)] = plan.data
    report = {'status': 'aplicado', 'efeitos': [
        {'id': cid, 'acao': action} for cid, action in plan.accepted],
        'pontos_mips': offsets, 'bytes_tabela': len(plan.data),
        'limite_padrao_por_id': plan.global_limit,
        'drops_do_deck': list(plan.deck_drops), 'password_id_prefix': plan.password_prefix,
        'decks_fixos': list(plan.fixed_decks), 'nomes_tier': plan.name_colors,
        'icones_de_descricao': description_icons, 'validado_no_epsxe': False}
    return bytes(out), report
