"""Verified native extension slots; never change the retail table constant.

The first save seal contains eighteen unused quantity bytes before the
duelist code. These slots are the limit of this save-compatible extension,
not an assertion about the maximum possible size of a redesigned game.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
import unicodedata

from .ps1_card_title import title_bitmap as _title_bitmap
from .tables import CARD_COUNT, EXE_DELTA, STATS_ADDR, LEVEL_ADDR, GUARDIAN_FIELDS, encode_ps1_star

PS1_CARD_CAPACITY = 740
EXTRA_SLOTS = PS1_CARD_CAPACITY - CARD_COUNT
SORT_ADDRESS = 0x801D4D8E
EXPANDED_SORT = SORT_ADDRESS + EXTRA_SLOTS * 4
# D5608 is live password-menu scratch, not padding. Move the complete byte
# table into the verified dialogue-bank tail instead of overwriting it.
EXPANDED_LEVELS = 0x801BFD18
MODEL_TABLE = 0x801D53A0
SAVE_QUANTITIES = 0x50
SAVE_DUELIST = 0x334
LIST_GROWTH = EXTRA_SLOTS * 16
LIST_SIZE = 0x2D4C + LIST_GROWTH
WORKSPACE_SIZE = (0x6344 + EXTRA_SLOTS * 35 + 3) & ~3
MODEL_KEY = 'modelo_ps1_id'


def is_monster(kind):
    return int(kind) < 20 or int(kind) == 24


def same_family(left, right):
    return (is_monster(left) and is_monster(right)) or int(left) == int(right)


def model_candidates(project, kind):
    """Only real original entries can provide an existing native behavior."""
    return [cid for cid in sorted(project.cards) if 1 <= cid <= CARD_COUNT
            and not project.cards[cid].get('virtual')
            and same_family(kind, project.cards[cid]['tipo_id'])]


def native_model(project, cid):
    from .core import ModError
    card = project.get(cid)
    chosen = card.get(MODEL_KEY, card.get('modelo_base_id'))
    if chosen is not None:
        try:
            chosen = int(chosen)
        except (ValueError, TypeError) as exc:
            raise ModError(f'#{cid}: modelo PS1 inválido.') from exc
        if chosen in model_candidates(project, card['tipo_id']):
            return chosen
        if MODEL_KEY in card:
            raise ModError(f'#{cid}: escolha um modelo PS1 do mesmo tipo de carta.')
    candidates = model_candidates(project, card['tipo_id'])
    if not candidates:
        raise ModError(f'#{cid}: importe uma carta original do mesmo tipo para servir de modelo PS1.')
    # Prefer a plain equip and a ritual with an actual three-material recipe.
    preferred = {20: 337, 21: 686, 22: 666, 23: 301}.get(int(card['tipo_id']))
    return preferred if preferred in candidates else candidates[0]


def native_ids(project):
    return {cid for cid in getattr(project, 'cards', {}) if 1 <= cid <= PS1_CARD_CAPACITY}


def pack_stats(cid, card):
    from .core import ModError
    values = {key: int(card.get(key, 0)) for key in (
        'ataque', 'defesa', 'tipo_id', 'guardian_1_id', 'guardian_2_id', 'nivel', 'atributo_id')}
    for key in GUARDIAN_FIELDS:
        values[key] = encode_ps1_star(values[key])
    for key in ('ataque', 'defesa'):
        if not 0 <= values[key] <= 5110 or values[key] % 10:
            raise ModError(f'#{cid}: {key} nativo exige múltiplos de 10 entre 0 e 5110; '
                           'o valor maior continua salvo no Studio.')
    for key, maximum in (('tipo_id', 24), ('guardian_1_id', 15), ('guardian_2_id', 15),
                         ('nivel', 15), ('atributo_id', 5 if is_monster(values['tipo_id']) else 15)):
        if not 0 <= values[key] <= maximum:
            raise ModError(f'#{cid}: {key} não cabe no formato PS1.')
    packed = ((values['tipo_id'] << 26) | (values['guardian_1_id'] << 22)
              | (values['guardian_2_id'] << 18) | (values['defesa'] // 10 << 9)
              | values['ataque'] // 10)
    return packed, (values['atributo_id'] << 4) | values['nivel']


@dataclass(frozen=True)
class ExpansionPlan:
    ids: tuple[int, ...]
    models: tuple[tuple[int, int], ...]
    pending: tuple[str, ...] = ()

    @property
    def enabled(self):
        return bool(self.ids)

    def report(self):
        return {'status': 'experimental' if self.enabled else 'original',
                'capacidade_bau': PS1_CARD_CAPACITY if self.enabled else CARD_COUNT,
                'ids_adicionais': list(self.ids), 'modelos': dict(self.models),
                'quantidades_save_inicio': SAVE_QUANTITIES,
                'quantidades_save_fim': SAVE_QUANTITIES + PS1_CARD_CAPACITY,
                'dados_duelista_inicio': SAVE_DUELIST,
                'save_original_preservado': True, 'validado_epsxe': False,
                'pendencias': list(self.pending)}


def compile_expansion(project, *, profile):
    from .core import ModError
    extras = sorted(cid for cid in getattr(project, 'cards', {}) if cid > CARD_COUNT)
    pending, ids, models = [], [], []
    for cid in extras:
        if not profile or cid > PS1_CARD_CAPACITY:
            pending.append(f'#{cid}: expansão nativa aceita #723–#{PS1_CARD_CAPACITY} '
                           'no perfil Drop x15; carta preservada no Studio.')
            continue
        card = project.get(cid)
        pack_stats(cid, card)
        ids.append(cid)
        models.append((cid, native_model(project, cid)))
    if ids and SAVE_QUANTITIES + PS1_CARD_CAPACITY != SAVE_DUELIST:
        raise ModError('A capacidade calculada invadiria os dados do duelista no save.')
    return ExpansionPlan(tuple(ids), tuple(models), tuple(pending))


def relocate_tables(original, patched, project, plan):
    """Snapshot all source arrays before writing overlapping destinations."""
    if not plan.enabled:
        return patched
    out = bytearray(patched)
    stat_at = STATS_ADDR - EXE_DELTA
    sort_at = SORT_ADDRESS - EXE_DELTA
    level_at = LEVEL_ADDR - EXE_DELTA
    stats = bytes(out[stat_at:stat_at + CARD_COUNT * 4])
    sort = bytes(out[sort_at:sort_at + CARD_COUNT * 2])
    levels = bytes(out[level_at:level_at + CARD_COUNT + 1])
    out[stat_at:stat_at + CARD_COUNT * 4] = stats
    by_id = dict(plan.models)
    for cid in range(CARD_COUNT + 1, PS1_CARD_CAPACITY + 1):
        card = project.get(cid) if cid in by_id else {
            'tipo_id': 0, 'nome': f'Reservado {cid}', 'ataque': 0, 'defesa': 0}
        word, level = pack_stats(cid, card)
        struct.pack_into('<I', out, stat_at + (cid - 1) * 4, word)
        base = by_id.get(cid, 1)
        sort += struct.pack('<h', struct.unpack_from('<h', original, sort_at + (base - 1) * 2)[0])
        levels += bytes((level,))
    at = EXPANDED_SORT - EXE_DELTA
    out[at:at + len(sort)] = sort
    at = EXPANDED_LEVELS - EXE_DELTA
    out[at:at + len(levels)] = levels
    assert at + len(levels) <= 0x801C0000 - EXE_DELTA
    return bytes(out)


def patch_expansion(original, patched, project, plan, *, wa_sectors):
    from .core import ModError
    from .deep_extract import NAME_TABLE, glyph_map
    from .ps1_content import _encode_name
    from .ps1_god24_chest import SOURCE_SHA256
    from .ps1_expansion_profile import PATCHES
    from . import ps1_expanded_runtime_blob as blob
    if not plan.enabled:
        return patched
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA256 or len(original) != len(patched):
        raise ModError('Expansão de cartas exige o SLUS original Drop x15 verificado.')
    out = bytearray(patched)
    for pc, before, after in PATCHES:
        pos = pc - EXE_DELTA
        if struct.unpack_from('<I', original, pos)[0] != before or struct.unpack_from('<I', out, pos)[0] != before:
            raise ModError(f'Expansão: assinatura de memória divergente em 0x{pc:08X}.')
        struct.pack_into('<I', out, pos, after)
    out = bytearray(relocate_tables(original, bytes(out), project, plan))
    models = dict(plan.models)
    for cid in range(CARD_COUNT + 1, PS1_CARD_CAPACITY + 1):
        struct.pack_into('<H', out, MODEL_TABLE - EXE_DELTA + (cid - 723) * 2, models.get(cid, 0))
    struct.pack_into('<I', out, MODEL_TABLE - EXE_DELTA + 36, wa_sectors + EXTRA_SLOTS - 5776)
    for label in ('RUNTIME_EXPANSION', 'RUNTIME_EXPANSION_AUX'):
        code, base = getattr(blob, label), getattr(blob, label + '_BASE')
        at = base - EXE_DELTA
        # The D-bank code occupies the old level array, after the new sort
        # table. The B-bank allocation must still be an empty source tail.
        if label.endswith('AUX') and any(original[at:at + len(code)]):
            raise ModError('A expansão conflita com o banco de diálogos original.')
        out[at:at + len(code)] = code
    hooks = ((0x80013998, (0x27BDFFD8, 0xAFB20018), 'ExpandedTransfer'),
             (0x80056504, (0x27BDFFB8, 0xAFB60038), 'ExpandedModel'),
             (0x80026BA4, (0x2482FED3, 0x2C420032), 'ExpandedEffect'),
             (0x8001F170, (0x94C5000C, 0), 'AttackTrapId'),
             (0x80025084, (0x8462000C, 0), 'SpellTrapId'),
             (0x8001F330, (0x84C3000C, 0), 'FakeTrapId'))
    for pc, words, key in hooks:
        at = pc - EXE_DELTA
        if struct.unpack_from('<II', out, at) != words:
            raise ModError(f'Expansão: rotina {key} foi alterada por outro patch.')
        struct.pack_into('<II', out, at, 0x08000000 | ((blob.ENTRY_POINTS[key] >> 2) & 0x3FFFFFF), 0)
    for pc in (0x80019D00, 0x8002BF68, 0x8002BFA0):
        at = pc - EXE_DELTA
        if struct.unpack_from('<I', out, at)[0] != 0x0C00B339:
            raise ModError('A marcação de cartas vistas não corresponde à base.')
        struct.pack_into('<I', out, at, 0x0C000000 | ((blob.ENTRY_POINTS['ExpandedSeen'] >> 2) & 0x3FFFFFF))
    for pc, before, key in ((0x8001A814, 0x878302FE, 'EquipBonusId'),
                            (0x8001AB98, 0x978402FE, 'EquipAnimationId'),
                            (0x8001ABD8, 0x878302FE, 'EquipSwordId'),
                            (0x8001ABF4, 0x878302FE, 'EquipSecondAnimationId')):
        at = pc - EXE_DELTA
        if struct.unpack_from('<I', out, at)[0] != before:
            raise ModError('Expansão: assinatura de comportamento Equip divergente.')
        # The second native instruction remains the jump's delay slot.
        struct.pack_into('<I', out, at, 0x08000000 | ((blob.ENTRY_POINTS[key] >> 2) & 0x3FFFFFF))
    # Names retain the 16-bit bank-relative format. Reuse the vacated part
    # of the level array and the empty end of the names bank, never D5608.
    regions = [[blob.RUNTIME_EXPANSION_END, 0x801D5608], [0x801D8EB0, 0x801D8F00],
               [0x801D8F04, 0x801D9000]]  # The God type label owns D8F00..D8F04.
    cmap, _ = glyph_map(original)
    font = set(cmap.values())
    names = {}
    for cid in range(CARD_COUNT + 1, PS1_CARD_CAPACITY + 1):
        name = str(project.get(cid).get('nome') or f'Carta {cid}') if cid in models else 'Reservado'
        plain = ''.join(c if c in font else ''.join(x for x in unicodedata.normalize('NFD', c)
                                                   if not unicodedata.combining(x)) for c in name)
        raw = _encode_name(plain, cmap) + b'\xff'
        if raw not in names:
            region = next((r for r in regions if r[0] + len(raw) <= r[1]), None)
            if region is None:
                raise ModError('Os nomes adicionais excedem o espaço nativo disponível. Encurte os nomes das novas cartas.')
            names[raw] = region[0] - 0x801D0000
            at = region[0] - EXE_DELTA
            out[at:at + len(raw)] = raw
            region[0] += len(raw)
        struct.pack_into('<H', out, NAME_TABLE - EXE_DELTA + 2 * cid, names[raw])
    return bytes(out)


def inspect_expansion(exe):
    from .ps1_expansion_profile import PATCHES
    from . import ps1_expanded_runtime_blob as blob
    if len(exe) < MODEL_TABLE - EXE_DELTA + 40:
        return {'status': 'ausente', 'capacidade': CARD_COUNT}
    matches = [struct.unpack_from('<I', exe, pc - EXE_DELTA)[0] == after for pc, _, after in PATCHES]
    if not any(matches):
        return {'status': 'ausente', 'capacidade': CARD_COUNT}
    valid = all(matches)
    for label in ('RUNTIME_EXPANSION', 'RUNTIME_EXPANSION_AUX'):
        code, base = getattr(blob, label), getattr(blob, label + '_BASE')
        valid = valid and exe[base - EXE_DELTA:base - EXE_DELTA + len(code)] == code
    for pc, key in ((0x80013998, 'ExpandedTransfer'), (0x80056504, 'ExpandedModel'),
                    (0x80026BA4, 'ExpandedEffect'), (0x8001F170, 'AttackTrapId'),
                    (0x80025084, 'SpellTrapId'), (0x8001F330, 'FakeTrapId')):
        expected = struct.pack('<II', 0x08000000 | ((blob.ENTRY_POINTS[key] >> 2) & 0x3FFFFFF), 0)
        valid = valid and exe[pc - EXE_DELTA:pc - EXE_DELTA + 8] == expected
    for pc, key, link in ((0x80019D00, 'ExpandedSeen', True), (0x8002BF68, 'ExpandedSeen', True),
                          (0x8002BFA0, 'ExpandedSeen', True), (0x8001A814, 'EquipBonusId', False),
                          (0x8001AB98, 'EquipAnimationId', False), (0x8001ABD8, 'EquipSwordId', False),
                          (0x8001ABF4, 'EquipSecondAnimationId', False)):
        expected = (0x0C000000 if link else 0x08000000) | ((blob.ENTRY_POINTS[key] >> 2) & 0x3FFFFFF)
        valid = valid and struct.unpack_from('<I', exe, pc - EXE_DELTA)[0] == expected
    ids = [cid for cid in range(723, 741) if struct.unpack_from('<H', exe, MODEL_TABLE - EXE_DELTA + 2 * (cid - 723))[0]]
    valid = valid and all(1 <= struct.unpack_from('<H', exe, MODEL_TABLE - EXE_DELTA + 2 * (cid - 723))[0] <= 722 for cid in ids)
    return {'status': 'aplicado' if valid else 'divergente', 'capacidade': PS1_CARD_CAPACITY,
            'ids_adicionais': ids, 'validado_epsxe': False}


def require_original_source(exe):
    """Expanded outputs use different tables and cannot be a retail import base."""
    if inspect_expansion(exe)['status'] == 'aplicado':
        from .core import ModError
        raise ModError('Esta é uma cópia PS1 expandida do Studio. Use Abrir projeto para continuar '
                       'a edição e mantenha o BIN/CUE original como base. A cópia expandida pode '
                       'ser aberta no ePSXe ou em Verificar BIN/CUE.')


def expand_archive(wa, project, plan, *, prefix, art_reports=None):
    """Insert only thumbnail slots; append full art without moving old records.

    The transfer adapter moves subsequent resource requests by 18 sectors.
    Thumbnail streams retain their original card-ID/sector correspondence.
    """
    from .core import ModError
    from .passwords import validate_ps1_prefix
    from .tables import PASSWORD_BASE
    from .ps1_image_optimizer import render_card
    if not plan.enabled:
        return wa
    if len(wa) % 2048 or len(wa) < 5776 * 2048:
        raise ModError('Arquivo WA não é composto por setores completos de cartas.')
    validate_ps1_prefix(wa, prefix)
    original = bytearray(expand_relations(wa, project, plan))
    # Keep an invalid password in holes; the price cannot be -1 until the
    # last record because the stock lookup stops at that sentinel.
    models, thumbs, arts = dict(plan.models), [], []
    for cid in range(723, 741):
        base = models.get(cid, 1)
        thumb = bytearray(wa[(base - 1) * 2048:base * 2048])
        at = ((base - 1) * 7 + 722) * 2048
        art = bytearray(wa[at:at + 7 * 2048])
        rel = getattr(project, 'arts', {}).get(str(cid))
        if rel:
            png = (project.folder / rel).resolve()
            if not png.is_relative_to(project.folder.resolve()) or not png.is_file():
                raise ModError(f'#{cid}: PNG ausente ou fora da pasta do projeto.')
            converted = render_card(
                png, art, thumb,
                options=project.metadata.get('ps1_image_optimizer'),
                verified_layout=True)
            for kind, offset, payload, _ in converted.regions(0, 0):
                target = thumb if kind == 'miniatura' else art
                target[offset:offset + len(payload)] = payload
            if art_reports is not None:
                art_reports[cid] = converted.diagnostics()
        if cid in models:
            art[0x2840:0x2AE0] = _title_bitmap(project.get(cid).get('nome') or f'Carta {cid}')
        thumbs.append(thumb)
        arts.append(art)
        code = int(f'{prefix:05d}{cid:03d}', 16) if cid in models else 0xFFFFFFFE
        struct.pack_into('<II', original, PASSWORD_BASE + cid * 8, 1, code)
    struct.pack_into('<II', original, PASSWORD_BASE + 741 * 8, 0xFFFFFFFF, 0xFFFFFFFE)
    split = 722 * 2048
    return bytes(original[:split] + b''.join(thumbs) + original[split:] + b''.join(arts))


def retail_archive_view(wa):
    """Project an expanded archive back to retail offsets for existing audits."""
    split, tails = CARD_COUNT * 2048, EXTRA_SLOTS * 7 * 2048
    return wa[:split] + wa[split + EXTRA_SLOTS * 2048:-tails]


def expand_relations(wa, project, plan):
    """Expand native variable-length equip/ritual tables in all seven copies."""
    from .core import ModError
    from .mod_data import CONFIG_KEY
    from .tables import (WA_TERRAIN_BASE, TERRAIN_COPIES, TERRAIN_STRIDE,
                         EQUIP_OFF, EQUIP_LEN, RITUAL_OFF, RITUAL_LEN)
    from .ps1_equip import _parse_table
    from .ps1_native import _ritual_records
    custom = project.metadata.get(CONFIG_KEY, {}).get('receitas', {})
    models, out = dict(plan.models), bytearray(wa)
    monsters = {cid: base for cid, base in models.items() if is_monster(project.get(cid)['tipo_id'])}
    for offset, size, label in ((EQUIP_OFF, EQUIP_LEN, 'Equipamentos'), (RITUAL_OFF, RITUAL_LEN, 'Rituais')):
        blocks = [wa[WA_TERRAIN_BASE + t * TERRAIN_STRIDE + offset:
                     WA_TERRAIN_BASE + t * TERRAIN_STRIDE + offset + size] for t in range(TERRAIN_COPIES)]
        if any(len(b) != size or b != blocks[0] for b in blocks):
            raise ModError(f'{label}: as sete tabelas de terreno divergem.')
        if offset == EQUIP_OFF:
            records, end = _parse_table(blocks[0])
            rows = dict(records)
            for equip, targets in list(rows.items()):
                rows[equip] = sorted(set(targets) | {cid for cid, base in monsters.items() if base in targets})
            for cid, base in models.items():
                if int(project.get(cid)['tipo_id']) == 23:
                    if base not in rows:
                        raise ModError(f'#{cid}: o modelo de equipamento não possui tabela de compatibilidade.')
                    rows[cid] = list(rows[base])
            for key, targets in custom.get('equipamentos', {}).items():
                cid = int(key)
                if cid in models or any(t > CARD_COUNT for t in targets):
                    if cid not in rows or any(t not in native_ids(project) for t in targets):
                        raise ModError('Equipamento personalizado contém IDs fora da expansão PS1.')
                    rows[cid] = list(targets)
            packed = b''.join(struct.pack('<HH', cid, len(targets)) + struct.pack(f'<{len(targets)}H', *targets)
                              for cid, targets in rows.items() if targets) + bytes(2)
        else:
            records, end = _ritual_records(blocks[0])
            rows = {cid: values for cid, (_, values) in records.items()}
            for cid, base in models.items():
                if int(project.get(cid)['tipo_id']) == 22:
                    if base not in rows:
                        raise ModError(f'#{cid}: o modelo de Ritual não possui uma receita nativa.')
                    recipe = custom.get('rituais', {}).get(str(cid))
                    if recipe:
                        values = (*recipe['tributos'], recipe['resultado'])
                        if len(values) != 4 or any(int(v) not in native_ids(project) for v in values):
                            raise ModError(f'#{cid}: Ritual PS1 exige três tributos e um resultado entre #001 e #740.')
                        rows[cid] = tuple(map(int, values))
                    else:
                        rows[cid] = rows[base]
            packed = b''.join(struct.pack('<5H', cid, *values) for cid, values in rows.items()) + bytes(2)
        if len(packed) > size:
            raise ModError(f'{label}: as relações adicionais não cabem na tabela nativa de {size} bytes.')
        extension = blocks[0][end:max(end, len(packed))]
        if any(value not in (0, 255) for value in extension):
            raise ModError(f'{label}: a expansão substituiria dados existentes após o terminador.')
        for terrain in range(TERRAIN_COPIES):
            start = WA_TERRAIN_BASE + terrain * TERRAIN_STRIDE + offset
            out[start:start + len(packed)] = packed
    return bytes(out)
