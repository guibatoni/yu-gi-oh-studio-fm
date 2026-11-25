"""Save Studio quest settings and install the verified Drop x15 campaign overlay."""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from . import ps1_campaign_quest_overlay_blob as overlay
from .campaign_quests import (STORY_DUELISTS, TABLE_START, QuestCatalog, compile_table,
                              generate_quests, normalize_overrides, normalize_phrases, table_size)
from .core import ModError, ps1_supports_god24
from .deep_extract import EXE_HEADER, EXE_START, exe_pos, extract_texts, glyph_map
from .tables import CARD_COUNT, LEVEL_ADDR, decode_cards, decode_pools, decode_starters

COMMAND_TABLE = 0x80090EAC
SCRIPT_COMMAND_TABLE = 0x80090C50
HOOKS = {
    'duel': (COMMAND_TABLE + 4 * 0x0D, 0x80038530),
    'answer': (COMMAND_TABLE + 4 * 0x12, 0x80038888),
    'shop': (SCRIPT_COMMAND_TABLE + 4 * 8, 0x8002EB48),
}
SETTINGS_KEY = 'ps1_campaign_quests'
SECTOR_BYTES = 2048
OVERLAY_MAGIC = b'QOV7'
OVERLAY_SECTORS = 6
OVERLAY_SIZE = OVERLAY_SECTORS * SECTOR_BYTES
OVERLAY_START = 0x801A9000
OVERLAY_HEADER = struct.Struct('<4sI8x')
INSTALLABLE_PROFILE = 'Quests PS1 exigem o BIN/CUE Original Drop x15 reconhecido pelo Studio.'
CAMPAIGN_SCENE_SECTOR = 0x1E57
CAMPAIGN_SCENE_SECTORS = 0x31
QUEST_SCENE_SECTORS = CAMPAIGN_SCENE_SECTORS + OVERLAY_SECTORS
SCENE_SECTOR_OPERAND = 0x8002FD34
# The resident shop hook recognizes the three Leave Shop operands in this
# script. Validate the exact bytecode in both the input and the exported BIN.
CAMPAIGN_SCRIPT_SECTOR = 0x1E68
CAMPAIGN_SCRIPT_HASH = '3fad8492631848e6074de293b809057644beaadf932af410c9500aa6dc2f73b1'
SCENE_PREFIX_SECTORS = CAMPAIGN_SCRIPT_SECTOR - CAMPAIGN_SCENE_SECTOR + 2
OVERLAY_END = OVERLAY_START + OVERLAY_SIZE
# Drop x15 resident code inside the quest scene arena (measured in ePSXe save
# states of the unmodified Drop x15 image, identical to the SLUS bytes): card
# drop draw (Duel_SelectCardDrop), result rewards and the card-name text
# command jump into 0x801AAC40..0x801AAEE0; 0x801AAC00..0x801AAC3F is its
# register save area. Overwriting it crashed "Doar e duelar" at PC 0x801AAE78.
DROP15_SCRATCH = 0x801AAC00
DROP15_CODE = 0x801AAC40
DROP15_END = 0x801AAEE0
DROP15_CODE_SHA256 = '4049fea05891ce3cd728d8d14e538eb899c053f8dc2eefec3507b5e4c2cd600e'
QUEST_HANDLERS = {'duel': overlay.DUEL_LOADER, 'answer': overlay.ANSWER_LOADER,
                  'shop': overlay.SHOP_LOADER}


def quest_settings(project):
    raw = (getattr(project, 'metadata', None) or {}).get(SETTINGS_KEY, {})
    if not isinstance(raw, dict) or not isinstance(raw.get('ativado', False), bool):
        raise ModError('Configuração de quests do projeto inválida.')
    seed = raw.get('seed', 'campanha')
    if not isinstance(seed, str) or not 1 <= len(seed.strip()) <= 80:
        raise ModError('Informe uma seed de 1 a 80 caracteres.')
    return {'ativado': raw.get('ativado', False), 'seed': seed.strip(),
            'requisitos': normalize_overrides(raw.get('requisitos', {})),
            'frases': normalize_phrases(raw.get('frases', {}))}


def save_quest_settings(project, *, enabled: bool, seed: str, requirements: dict,
                        phrases: dict | None = None):
    previous = project.metadata
    if phrases is None:
        phrases = (previous.get(SETTINGS_KEY) or {}).get('frases', {})
    project.metadata = {**previous, SETTINGS_KEY: {
        'ativado': enabled, 'seed': seed, 'requisitos': requirements, 'frases': phrases,
    }}
    try:
        settings = quest_settings(project)
        project.metadata[SETTINGS_KEY] = settings
        project.save()
    except (OSError, ModError, ValueError):
        project.metadata = previous
        raise
    return settings


def validate_quest_source(project, wa, *, native_profile):
    from .ps1_mod import wa_sha

    if not native_profile:
        raise ModError(INSTALLABLE_PROFILE)
    expected = wa_sha(project)
    if wa is None or not expected or hashlib.sha256(wa).hexdigest() != expected:
        raise ModError('Importe o BIN/CUE Original Drop x15 para vincular o WA_MRG das quests ao projeto.')
    if not _shop_script_matches(wa):
        raise ModError('O mapa e os diálogos da loja da imagem divergem do perfil das quests.')


def _shop_script_matches(wa, *, shift=0):
    start = (CAMPAIGN_SCRIPT_SECTOR + shift) * SECTOR_BYTES
    return hashlib.sha256(wa[start:start + 2 * SECTOR_BYTES]).hexdigest() == CAMPAIGN_SCRIPT_HASH


def append_quest_scene(wa, payload):
    """Reuse the campaign's staged load: graphics, script with quests, portraits."""
    start = CAMPAIGN_SCENE_SECTOR * SECTOR_BYTES
    split = start + SCENE_PREFIX_SECTORS * SECTOR_BYTES
    end = start + CAMPAIGN_SCENE_SECTORS * SECTOR_BYTES
    if end > len(wa) or len(wa) % SECTOR_BYTES or len(payload) != OVERLAY_SIZE:
        raise ModError('Pacote de cena do PS1 incompleto para instalar as quests.')
    return wa + wa[start:split] + payload + wa[split:end]


def project_quest_catalog(project, wa, *, exe=None, level_address=LEVEL_ADDR, supreme=False):
    cards = {cid: project.get(cid) for cid in sorted(project.cards) if cid <= CARD_COUNT}
    # A basic BIN import has statistics but can leave the name column blank.
    if any(not row['nome'] for row in cards.values()):
        original = project.folder / 'base' / 'source_SLUS_014.11'
        if original.is_file():
            stock = original.read_bytes()
            if hashlib.sha256(stock).hexdigest() == project.metadata.get('base_sha256', {}).get('slus'):
                texts, _ = extract_texts(stock)
                for row in texts['nomes_descricoes']:
                    card = cards.get(row['id'])
                    if card is not None and not card['nome']:
                        card['nome'] = row['nome']
    if exe is not None:
        values, _ = decode_cards(exe, level_address=level_address, supreme=supreme)
        cards = {row['id']: {**row, 'nome': cards[row['id']]['nome'],
                             'raridade': cards[row['id']].get('raridade')}
                 for row in values if row['id'] in cards}
    drops, _, _ = decode_pools(wa)
    from .mod_data import CONFIG_KEY
    from .ps1_fixed_drop import fixed_drops
    fixed = fixed_drops(getattr(project, 'metadata', {}).get(CONFIG_KEY) or {}, CARD_COUNT)
    return QuestCatalog.from_rows(cards.values(), drops, decode_starters(wa), fixed)


def preview_project_quests(project, source: Path, seed: str, requirements: dict):
    from .ps1_mod import compile_mod, patch_wa, read_linked_wa

    if not ps1_supports_god24(project):
        raise ModError(INSTALLABLE_PROFILE)
    wa = read_linked_wa(project, source)
    validate_quest_source(project, wa, native_profile=True)
    plan = compile_mod(project, profile=True, wa_verified=True)
    catalog = project_quest_catalog(project, patch_wa(wa, plan) if plan.needs_wa else wa)
    return generate_quests(catalog, seed, requirements)


def resident_mod_code(exe: bytes) -> bytes:
    """Drop x15 code that must survive the quest scene load (verified by SHA-256)."""
    size = DROP15_END - DROP15_CODE
    at = exe_pos(DROP15_CODE, exe, size)
    code = exe[at:at + size]
    from .ps1_drop_count import canonical  # cards-per-win changes 6 words of this code
    if hashlib.sha256(canonical(code)).hexdigest() != DROP15_CODE_SHA256:
        raise ModError('O código residente do Drop x15 em 0x801AAC40 diverge do perfil das quests; '
                       'as quests sobrescreveriam rotinas do mod.')
    return code


def foreign_arena_jumps(exe: bytes) -> list[tuple[int, int]]:
    """J/JAL outside the arena that land in it, other than Drop x15 code and quest entries."""
    allowed = {overlay.ENTRY_POINTS[name] for name in ('QuestBeforeDuel', 'QuestAnswer', 'QuestResumeShop')}
    found = []
    for at in range(EXE_HEADER, len(exe) - 3, 4):
        address = at - EXE_HEADER + EXE_START
        if OVERLAY_START <= address < OVERLAY_END:
            continue
        word = struct.unpack_from('<I', exe, at)[0]
        if word >> 26 not in (2, 3):
            continue
        target = (address & 0xF0000000) | (word & 0x03FFFFFF) << 2
        if (OVERLAY_START <= target < OVERLAY_END and target not in allowed
                and not DROP15_CODE <= target < DROP15_END):
            found.append((address, target))
    return found


def _overlay_layout():
    base = overlay.ENTRY_POINTS['QuestConfiguration']
    if (hashlib.sha256(overlay.PAYLOAD).hexdigest() != overlay.SHA256
            or overlay.BASE != OVERLAY_START + OVERLAY_HEADER.size
            or overlay.BASE + len(overlay.PAYLOAD) != base
            or base + TABLE_START > DROP15_SCRATCH
            or not DROP15_END <= overlay.BSS_START <= overlay.BSS_END <= OVERLAY_END - len(OVERLAY_MAGIC)):
        raise ModError('O código MIPS das quests diverge do compilado.')
    gap = (DROP15_SCRATCH - base, overlay.BSS_END - base)
    return base, gap, OVERLAY_END - len(OVERLAY_MAGIC) - base


def build_quest_overlay(exe: bytes, catalog: QuestCatalog, settings: dict, *, level_address: int,
                        mod_code: bytes | None = None):
    """Return (payload, config, table). ``table`` is the on-disc bytes from QuestConfiguration,
    including the preserved Drop x15 code when the records continue after it."""
    base, gap, limit = _overlay_layout()
    if mod_code is None:
        conflicts = foreign_arena_jumps(exe)
        if conflicts:
            source, target = conflicts[0]
            raise ModError(f'Conflito: 0x{source:08X} salta para 0x{target:08X}, área usada pelas quests.')
        mod_code = resident_mod_code(exe)
    if len(mod_code) != DROP15_END - DROP15_CODE:
        raise ModError('Código residente do Drop x15 incompleto.')
    config = generate_quests(catalog, settings['seed'], settings['requisitos'])
    glyphs, _ = glyph_map(exe)
    table = compile_table(config, catalog, glyphs, gap=gap, limit=limit,
                          phrases=settings.get('frases'))
    payload = bytearray(OVERLAY_HEADER.pack(OVERLAY_MAGIC, level_address) + overlay.PAYLOAD + table)
    if len(payload) > OVERLAY_SIZE - len(OVERLAY_MAGIC):
        raise ModError('A tabela de quests excede o espaço de carregamento do PS1.')
    payload = payload.ljust(OVERLAY_SIZE - len(OVERLAY_MAGIC), b'\0') + OVERLAY_MAGIC
    reserved = slice(DROP15_SCRATCH - OVERLAY_START, overlay.BSS_END - OVERLAY_START)
    if any(payload[reserved]):
        raise ModError('A tabela de quests invadiu o código do Drop x15.')
    at = DROP15_CODE - OVERLAY_START
    payload[at:at + len(mod_code)] = mod_code
    start = base - OVERLAY_START
    return bytes(payload), config, bytes(payload[start:start + len(table)])


def reserve_quest_handlers(exe, regions):
    """Use free intervals shared with the description allocator."""
    free = list(regions)
    addresses = {}
    for name, loader in QUEST_HANDLERS.items():
        size = len(loader)
        for index, (lo, hi) in sorted(enumerate(free), key=lambda item: item[1][1] - item[1][0]):
            address = (hi - size) & ~3
            if address < lo:
                continue
            at = exe_pos(address, exe, size)
            if any(exe[at:at + size]):
                continue
            addresses[name] = address
            free[index:index + 1] = [(start, end) for start, end in
                                     ((lo, address), (address + size, hi)) if start < end]
            break
        else:
            raise ModError('Sem espaço no SLUS para o carregador das quests junto com as regras nativas.')
    return addresses, free


def _scene_patches(sector):
    if not CAMPAIGN_SCENE_SECTOR + CAMPAIGN_SCENE_SECTORS <= sector <= 0xFFFF:
        raise ModError('Setor da cena de quests fora do intervalo do carregador.')
    # Grow the script phase at 0x801A8000 to the end of the arena at 0x801AC000.
    # The native function returns through the game's FlushCache trampoline.
    return (
        (SCENE_SECTOR_OPERAND, 0x24061E57, 0x34060000 | sector),
        (0x8002FD38, 0x24070031, 0x24070000 | QUEST_SCENE_SECTORS),
        (0x8002FCAC, 0x24031000, 0x24030000 | (2 * SECTOR_BYTES + OVERLAY_SIZE)),
        (0x8002FEC8, 0x03E00008, 0x0801D03C),
    )


def install_quest_handlers(exe, addresses, sector):
    result = bytearray(exe)
    for address, expected, replacement in _scene_patches(sector):
        at = exe_pos(address, exe, 4)
        if struct.unpack_from('<I', exe, at)[0] != expected:
            raise ModError(f'Conflito no carregamento da cena de quests em 0x{address:08X}.')
        struct.pack_into('<I', result, at, replacement)
    for name, loader in QUEST_HANDLERS.items():
        hook, expected = HOOKS[name]
        at = exe_pos(hook, exe, 4)
        start = exe_pos(addresses[name], exe, len(loader))
        if struct.unpack_from('<I', exe, at)[0] != expected or any(exe[start:start + len(loader)]):
            raise ModError(f'Conflito no carregador de quests em 0x{hook:08X}.')
        struct.pack_into('<I', result, at, addresses[name])
        result[start:start + len(loader)] = loader
    return bytes(result)


def inspect_quest_overlay(exe, wa=None, *, expanded=False):
    """Recognize the loaders and verify the table in the selected, unmodified disc readback."""
    from .ps1_expansion import EXTRA_SLOTS, EXPANDED_LEVELS
    from .ps1_runtime import BANK_END, DUEL_STATE

    try:
        addresses = {name: struct.unpack_from('<I', exe, exe_pos(hook, exe, 4))[0]
                     for name, (hook, _) in HOOKS.items()}
        if addresses == {name: expected for name, (_, expected) in HOOKS.items()}:
            return {'status': 'ausente'}
        if (addresses['duel'] == HOOKS['duel'][1] and addresses['shop'] == HOOKS['shop'][1]
                and DUEL_STATE <= addresses['answer'] < BANK_END):
            previous = exe_pos(COMMAND_TABLE + 4 * 0x19, exe, 4)
            if DUEL_STATE <= struct.unpack_from('<I', exe, previous)[0] < BANK_END:
                return {'status': 'pos_vitoria'}
        if any(not DUEL_STATE <= addr < BANK_END or addr & 3 for addr in addresses.values()):
            return {'status': 'não reconhecido'}
        def instruction(address):
            return struct.unpack_from('<I', exe, exe_pos(address, exe, 4))[0]

        request = instruction(SCENE_SECTOR_OPERAND)
        if request == 0x24061E57:
            # v1.9.11 synchronously loads QOV2 inside the text interpreter.
            if (instruction(addresses['duel'] + 176), instruction(addresses['duel'] + 180)) == (
                    0x3C0B3256, 0x356B4F51):
                return {'status': 'carregamento_dialogo_antigo'}
            return {'status': 'divergente'}
        sector = request & 0xFFFF
        if any(instruction(address) != value for address, _, value in _scene_patches(sector)):
            return {'status': 'divergente'}
        for name, loader in QUEST_HANDLERS.items():
            at = exe_pos(addresses[name], exe, len(loader))
            if exe[at:at + len(loader)] != loader:
                return {'status': 'divergente'}
        if wa is None:
            return {'status': 'aguardando_wa'}
        shift = EXTRA_SLOTS if expanded else 0
        if not _shop_script_matches(wa, shift=shift):
            return {'status': 'divergente'}
        scene_sector = sector + shift
        scene_start = scene_sector * SECTOR_BYTES
        original_start = (CAMPAIGN_SCENE_SECTOR + shift) * SECTOR_BYTES
        prefix_size = SCENE_PREFIX_SECTORS * SECTOR_BYTES
        original_size = CAMPAIGN_SCENE_SECTORS * SECTOR_BYTES
        sector = scene_sector + SCENE_PREFIX_SECTORS
        at = sector * SECTOR_BYTES
        if (wa[scene_start:at] != wa[original_start:original_start + prefix_size]
                or wa[at + OVERLAY_SIZE:scene_start + original_size + OVERLAY_SIZE]
                != wa[original_start + prefix_size:original_start + original_size]):
            return {'status': 'divergente'}
        payload = wa[at:at + OVERLAY_SIZE]
        level_address = EXPANDED_LEVELS if expanded else LEVEL_ADDR
        if (len(payload) != OVERLAY_SIZE or not payload.endswith(OVERLAY_MAGIC)
                or payload[:OVERLAY_HEADER.size] != OVERLAY_HEADER.pack(OVERLAY_MAGIC, level_address)
                or payload[OVERLAY_HEADER.size:OVERLAY_HEADER.size + overlay.SIZE] != overlay.PAYLOAD):
            return {'status': 'divergente'}
        _, gap, _ = _overlay_layout()
        data = payload[OVERLAY_HEADER.size + overlay.SIZE:-len(OVERLAY_MAGIC)]
        table = data[:table_size(data, gap)]
        if payload[DROP15_CODE - OVERLAY_START:DROP15_END - OVERLAY_START] != resident_mod_code(exe):
            return {'status': 'divergente'}
        return {'status': 'aplicado', 'setor_wa': sector, 'setor_cena_wa': scene_sector,
                'duelistas': len(STORY_DUELISTS),
                'momento': 'antes_do_duelo', 'retorno_card_shop': True,
                'preserva_codigo_drop_x15': True,
                'sha256_tabela': hashlib.sha256(table).hexdigest(), 'validado_epsxe': False}
    except (ModError, ValueError):
        return {'status': 'divergente'}
