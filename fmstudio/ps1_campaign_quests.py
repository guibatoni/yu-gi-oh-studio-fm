"""Save Studio quest settings and install the verified Drop x15 campaign overlay."""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from . import ps1_campaign_quest_overlay_blob as overlay
from .campaign_quests import (STORY_DUELISTS, QuestCatalog, compile_table, generate_quests,
                              normalize_overrides, table_size)
from .core import ModError, ps1_supports_god24
from .deep_extract import exe_pos, extract_texts, glyph_map
from .tables import CARD_COUNT, LEVEL_ADDR, decode_cards, decode_pools, decode_starters

COMMAND_TABLE = 0x80090EAC
HOOKS = {0x19: 0x80038AB0, 0x12: 0x80038888}
SETTINGS_KEY = 'ps1_campaign_quests'
SECTOR_BYTES = 2048
OVERLAY_MAGIC = b'QOV1'
OVERLAY_SECTORS = 8
OVERLAY_SIZE = OVERLAY_SECTORS * SECTOR_BYTES
OVERLAY_START = 0x801DC000
OVERLAY_HEADER = struct.Struct('<4sI8x')
INSTALLABLE_PROFILE = 'Quests PS1 exigem o BIN/CUE Original Drop x15 reconhecido pelo Studio.'


def quest_settings(project):
    raw = (getattr(project, 'metadata', None) or {}).get(SETTINGS_KEY, {})
    if not isinstance(raw, dict) or not isinstance(raw.get('ativado', False), bool):
        raise ModError('Configuração de quests do projeto inválida.')
    seed = raw.get('seed', 'campanha')
    if not isinstance(seed, str) or not 1 <= len(seed.strip()) <= 80:
        raise ModError('Informe uma seed de 1 a 80 caracteres.')
    return {'ativado': raw.get('ativado', False), 'seed': seed.strip(),
            'requisitos': normalize_overrides(raw.get('requisitos', {}))}


def save_quest_settings(project, *, enabled: bool, seed: str, requirements: dict):
    previous = project.metadata
    project.metadata = {**previous, SETTINGS_KEY: {
        'ativado': enabled, 'seed': seed, 'requisitos': requirements,
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
    return QuestCatalog.from_rows(cards.values(), drops, decode_starters(wa))


def preview_project_quests(project, source: Path, seed: str, requirements: dict):
    from .ps1_mod import compile_mod, patch_wa, read_linked_wa

    if not ps1_supports_god24(project):
        raise ModError(INSTALLABLE_PROFILE)
    wa = read_linked_wa(project, source)
    validate_quest_source(project, wa, native_profile=True)
    plan = compile_mod(project, profile=True, wa_verified=True)
    catalog = project_quest_catalog(project, patch_wa(wa, plan) if plan.needs_wa else wa)
    return generate_quests(catalog, seed, requirements)


def build_quest_overlay(exe: bytes, catalog: QuestCatalog, settings: dict, *, level_address: int):
    if (hashlib.sha256(overlay.PAYLOAD).hexdigest() != overlay.SHA256
            or overlay.BASE != OVERLAY_START + OVERLAY_HEADER.size
            or overlay.BASE + len(overlay.PAYLOAD) != overlay.ENTRY_POINTS['QuestConfiguration']):
        raise ModError('O código MIPS das quests diverge do compilado.')
    config = generate_quests(catalog, settings['seed'], settings['requisitos'])
    glyphs, _ = glyph_map(exe)
    table = compile_table(config, catalog, glyphs)
    payload = OVERLAY_HEADER.pack(OVERLAY_MAGIC, level_address) + overlay.PAYLOAD + table
    if len(payload) > OVERLAY_SIZE - len(OVERLAY_MAGIC):
        raise ModError('A tabela de quests excede o espaço de carregamento do PS1.')
    return payload.ljust(OVERLAY_SIZE - len(OVERLAY_MAGIC), b'\0') + OVERLAY_MAGIC, config, table


def reserve_quest_handlers(exe, regions):
    """Use a pair of small free intervals shared with the description allocator."""
    free = list(regions)
    addresses = {}
    for opcode, loader in ((0x19, overlay.WIN_LOADER), (0x12, overlay.ANSWER_LOADER)):
        size = len(loader)
        for index, (lo, hi) in sorted(enumerate(free), key=lambda item: item[1][1] - item[1][0]):
            address = (hi - size) & ~3
            if address < lo:
                continue
            at = exe_pos(address, exe, size)
            if any(exe[at:at + size]):
                continue
            addresses[opcode] = address
            free[index:index + 1] = [(start, end) for start, end in
                                     ((lo, address), (address + size, hi)) if start < end]
            break
        else:
            raise ModError('Sem espaço no SLUS para o carregador das quests junto com as regras nativas.')
    return addresses, free


def _loader_payloads(sector):
    if not 0 < sector <= 65535:
        raise ModError('Setor das quests fora do intervalo do carregador.')
    win = bytearray(overlay.WIN_LOADER)
    pos = overlay.SECTOR_OFFSET
    if struct.unpack_from('<I', win, pos)[0] != 0x34060000:
        raise ModError('Operando de setor do carregador de quests divergente.')
    struct.pack_into('<I', win, pos, 0x34060000 | sector)
    return {0x19: bytes(win), 0x12: overlay.ANSWER_LOADER}


def install_quest_handlers(exe, addresses, sector):
    result = bytearray(exe)
    for opcode, loader in _loader_payloads(sector).items():
        at = exe_pos(COMMAND_TABLE + 4 * opcode, exe, 4)
        start = exe_pos(addresses[opcode], exe, len(loader))
        if struct.unpack_from('<I', exe, at)[0] != HOOKS[opcode] or any(exe[start:start + len(loader)]):
            raise ModError(f'Conflito no carregador do comando de diálogo F8 {opcode:02X}.')
        struct.pack_into('<I', result, at, addresses[opcode])
        result[start:start + len(loader)] = loader
    return bytes(result)


def inspect_quest_overlay(exe, wa=None, *, expanded=False):
    """Recognize the loaders and verify the table in the selected, unmodified disc readback."""
    from .ps1_expansion import EXTRA_SLOTS, EXPANDED_LEVELS
    from .ps1_runtime import BANK_END, DUEL_STATE

    try:
        addresses = {op: struct.unpack_from('<I', exe, exe_pos(COMMAND_TABLE + 4 * op, exe, 4))[0]
                     for op in HOOKS}
        if addresses == HOOKS:
            return {'status': 'ausente'}
        if any(not DUEL_STATE <= addr < BANK_END or addr & 3 for addr in addresses.values()):
            return {'status': 'não reconhecido'}
        pos = exe_pos(addresses[0x19] + overlay.SECTOR_OFFSET, exe, 4)
        sector = struct.unpack_from('<H', exe, pos)[0]
        for op, loader in _loader_payloads(sector).items():
            at = exe_pos(addresses[op], exe, len(loader))
            if exe[at:at + len(loader)] != loader:
                return {'status': 'divergente'}
        if wa is None:
            return {'status': 'aguardando_wa'}
        sector += EXTRA_SLOTS if expanded else 0
        at = sector * SECTOR_BYTES
        payload = wa[at:at + OVERLAY_SIZE]
        level_address = EXPANDED_LEVELS if expanded else LEVEL_ADDR
        if (len(payload) != OVERLAY_SIZE or not payload.endswith(OVERLAY_MAGIC)
                or payload[:OVERLAY_HEADER.size] != OVERLAY_HEADER.pack(OVERLAY_MAGIC, level_address)
                or payload[OVERLAY_HEADER.size:OVERLAY_HEADER.size + overlay.SIZE] != overlay.PAYLOAD):
            return {'status': 'divergente'}
        data = payload[OVERLAY_HEADER.size + overlay.SIZE:-len(OVERLAY_MAGIC)]
        table = data[:table_size(data)]
        return {'status': 'aplicado', 'setor_wa': sector, 'duelistas': len(STORY_DUELISTS),
                'sha256_tabela': hashlib.sha256(table).hexdigest(), 'validado_epsxe': False}
    except (ModError, ValueError):
        return {'status': 'divergente'}
