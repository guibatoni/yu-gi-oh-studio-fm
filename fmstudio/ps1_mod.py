"""Drop x15 projection of match rules into the verified SLUS/WA layout."""
from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass, field

from .core import ModError, _write_csv
from .disc import DiscError, DiscReader
from .mod_data import (
    CONFIG_KEY, DROP_GROUPS, base_tables, deck_copy_limit, deck_drop_weights, drops_from_deck,
    normalize_rules, validate_deck,
)
from .tables import (
    CARD_COUNT, DECK_SIZE, DUELIST_BASE, DUELIST_COUNT, DUELIST_STRIDE, EXE_DELTA,
    POOL_OFFSETS, POOL_TOTAL, STARTER_OFFSETS, STARTER_POOLS, STARTER_SIZE,
    STARTER_STRIDE, decode_starters,
)

FIRST_TURN_PC = 0x80017B18
FIRST_TURN_SOURCE = 0x34421000
CHEST_DIM_FLAG_PC = 0x800325F8
CHEST_DIM_FLAG = 0x240B0080  # addiu t3, zero, 0x80
CHEST_ROW_FLAG_PC = 0x80032644
CHEST_ROW_CONTEXT = (0x25040001, 0xA0A00000, 0xA4A4FFF7)
CHEST_ROW_VISIBLE = 0xA0AB0000  # sb t3, 0(a1)
INIT_CALL = 0x80017B08
LP_CODE = 0x801CFF00
LP_TABLE = 0x801CFFA0
LP_BANK_END = 0x801D0000
LP_MAX = 65535  # u16 no motor PS1; o HUD original exibe somente quatro dígitos
LEGACY_SCAN_COUNT = CARD_COUNT - 2
_LP_INIT = 0x0C005D68
_LP_JAL = 0x0C000000 | ((LP_CODE >> 2) & 0x03FFFFFF)
_LP_WORDS = (
    0x27BDFFF0, 0xAFBF000C, _LP_INIT, 0,  # save ra and initialize retail state
    0x83880459, 0, 0x2D090028, 0x11200012, 0x00084040,  # signed opponent ID, skip link mode
    0x3C09801C, 0x3529FFA0, 0x3C0A800E, 0x354A9FF0,  # table and side records
    0x952B0000, 0, 0x11600003, 0, 0xA54B0014, 0xA54B0016,  # player LP and healing cap
    0x01284821, 0x952B0002, 0, 0x11600003, 0, 0xA54B0034, 0xA54B0036,
    0x8FBF000C, 0x27BD0010, 0x03E00008, 0,
)


@dataclass
class ModPlan:
    player_lp: int
    life: list[int]
    groups: dict[tuple[int, str], tuple[int, ...]]
    starters: list[tuple[int, tuple[int, ...]]]
    applied: list[str]
    pending: list[str]
    fixed_decks: dict[int, tuple[int, ...]] = field(default_factory=dict)
    fusions: dict[tuple[int, int], int] = field(default_factory=dict)

    @property
    def needs_wa(self):
        return bool(self.groups or self.starters)

    @property
    def has_lp(self):
        return bool(self.player_lp or any(self.life))


def wa_sha(project):
    path = project.folder / 'base' / 'resumo.json'
    if path.is_file():
        return (json.loads(path.read_text(encoding='utf-8')).get('source_sha256') or {}).get('DATA/WA_MRG.MRG')
    return None


def read_linked_wa(project, source):
    """Read WA_MRG from the image associated with this project."""
    try:
        with DiscReader(source) as disc:
            entries = {entry.path.upper(): entry for entry in disc.files() if not entry.is_dir}
            slus = b''.join(disc.read_entry(entries['SLUS_014.11']))
            wa = b''.join(disc.read_entry(entries['DATA/WA_MRG.MRG']))
    except (DiscError, KeyError) as exc:
        raise ModError('A imagem precisa conter SLUS_014.11 e DATA/WA_MRG.MRG.') from exc
    if hashlib.sha256(slus).hexdigest() != project.metadata.get('base_sha256', {}).get('slus'):
        raise ModError('Selecione a imagem usada para importar este projeto.')
    expected = wa_sha(project)
    if expected and hashlib.sha256(wa).hexdigest() != expected:
        raise ModError('O WA_MRG da imagem diverge do projeto.')
    return wa


def import_starter_tables(project, source):
    rows = decode_starters(read_linked_wa(project, source))
    if not rows:
        raise ModError('A imagem não apresenta as duas cópias compatíveis dos pools iniciais.')
    _write_csv(project.folder/'base'/'decks_iniciais.csv', rows)


def quantize_weights(weights, last_id):
    if not weights or any(not 1 <= cid <= last_id for cid in weights):
        raise ModError(f'O PS1 exige pesos positivos para cartas de 1 a {last_id}.')
    total = sum(weights.values())
    parts = {cid: divmod(weight * POOL_TOTAL, total) for cid, weight in weights.items()}
    allocated = {cid: whole for cid, (whole, _) in parts.items()}
    leftover = POOL_TOTAL - sum(allocated.values())
    for cid in sorted(parts, key=lambda cid: (-parts[cid][1], cid))[:leftover]:
        allocated[cid] += 1
    for cid in sorted(allocated):
        if not allocated[cid]:
            donor = max(allocated, key=allocated.__getitem__)
            allocated[donor] -= 1
            allocated[cid] = 1
    return tuple(allocated.get(cid,0) for cid in range(1,CARD_COUNT+1))


def fusion_uses_original_ids(cards, *ids):
    return all(1 <= cid <= CARD_COUNT and cid in cards and not cards[cid].get('virtual') for cid in ids)


def compile_mod(project, *, profile, wa_verified):
    plan = ModPlan(0, [0] * DUELIST_COUNT, {}, [], [], [])
    raw = getattr(project, 'metadata', {}).get(CONFIG_KEY)
    if not raw:
        return plan
    cards = {cid: project.get(cid) for cid in project.cards}
    config = normalize_rules(raw, cards)
    effects = getattr(project, 'effects', {})
    copies = int(project.metadata.get('ps1_deck_global_limit') or 3)
    tables_ok = profile and wa_verified
    legacy_pools = base_tables(project)[0] if hasattr(project, 'folder') else {}

    def lp(value, label):
        if value is None:
            return 0
        if not profile or value > LP_MAX:
            plan.pending.append(f'{label}: {value} LP não cabe no campo u16 do PS1 (1–65535), ou exige o perfil Drop x15.')
            return 0
        plan.applied.append(label)
        return value

    def group(opponent, kind, weights, name, last_id):
        if not tables_ok:
            plan.pending.append(f'{name}: exige a imagem Drop x15 vinculada ao projeto.')
            return
        try:
            data = quantize_weights(weights, last_id)
        except ModError as exc:
            plan.pending.append(f'{name}: {exc}')
            return
        plan.groups[opponent, kind] = data
        plan.applied.append(name)

    def deck_weights(weights):
        return {cid: weight for cid, weight in weights.items() if deck_copy_limit(effects, cid, copies)}

    # Um valor para ambos, inclusive todos os 39 duelistas, não só o
    # oponente selecionado no editor. 0 no banco significa "use retail 8000".
    global_lp = config.get('lp_inicial', config.get('lp_jogador'))
    plan.player_lp = lp(global_lp, 'LP inicial global do mod')
    if plan.player_lp:
        plan.life = [plan.player_lp] * DUELIST_COUNT
        if plan.player_lp > 9999:
            plan.applied.append(
                'Contador LP de cinco dígitos solicitado; visual ainda exige validação no ePSXe.')
    for key, changes in config.get('duelistas', {}).items():
        opponent = int(key)
        if 'deck' in changes:
            deck = changes['deck']
            fixed, pools = deck['cartas'], deck['pools']
            if not pools:
                name = f'Deck fixo do duelista #{opponent}'
                try:
                    if not profile:
                        raise ModError('requer o executável Drop x15.')
                    if len(fixed) != DECK_SIZE:
                        raise ModError(f'complete as {DECK_SIZE} vagas ({len(fixed)}/{DECK_SIZE}).')
                    if any(cid > CARD_COUNT or cards[cid].get('virtual') for cid in fixed):
                        raise ModError('o BIN/CUE aceita os IDs originais #001–#722.')
                    validate_deck(cards, effects, fixed, copies)
                except ModError as exc:
                    plan.pending.append(f'{name}: {exc}')
                else:
                    plan.fixed_decks[opponent] = tuple(fixed)
                    plan.applied.append(name)
            else:
                name = f'Pool do duelista #{opponent}'
                if fixed or len(pools) != 1 or pools[0]['compras'] != DECK_SIZE:
                    plan.pending.append(f'{name}: use um pool de 40 compras ou 40 cartas fixas para o BIN/CUE.')
                else:
                    weights = deck_weights(pools[0]['pesos'])
                    if len(weights) * 3 < DECK_SIZE:
                        plan.pending.append(f'{name}: o pool precisa de cartas elegíveis para 40 vagas.')
                    elif any(deck_copy_limit(effects, cid, copies) < 3 for cid in weights):
                        plan.pending.append(f'{name}: use um deck fixo para aplicar limites de 1–2 no sorteio PS1.')
                    else:
                        group(opponent, 'deck', weights, name, LEGACY_SCAN_COUNT)
        if drops_from_deck(config, opponent):
            # Em vez do antigo hook que dava uma carta do deck efetivamente
            # sorteado com probabilidade fixa por cópia, escrever as tabelas
            # de drop de cada rank com os pesos escolhidos no editor.
            for kind in DROP_GROUPS:
                weights = deck_drop_weights(config, legacy_pools, opponent, kind, effects=effects)
                group(opponent, kind, weights,
                      f'Drops ponderados do próprio deck #{opponent} ({kind})',
                      CARD_COUNT)
        else:
            for kind, weights in changes.get('drops', {}).items():
                name = f'Drop #{opponent} {kind}'
                if kind not in DROP_GROUPS:
                    plan.pending.append(f'{name}: este rank tem pesos individuais no Studio. O PS1 usa os grupos POW, TEC e B/C/D.')
                else:
                    group(opponent,kind,weights,name,CARD_COUNT)

    if 'pools_iniciais_ps1' in config:
        rows = [{**row, 'pesos': deck_weights(row['pesos'])} for row in config['pools_iniciais_ps1']]
        try:
            if not tables_ok or len(rows) > STARTER_POOLS or sum(row['compras'] for row in rows) != DECK_SIZE:
                raise ModError('O Drop x15 usa até sete pools com 40 compras ao todo.')
            staged = []
            possible_copies = {}
            for row in rows:
                for cid in row['pesos']:
                    possible_copies[cid] = possible_copies.get(cid, 0) + row['compras']
            if any(min(3, available) > deck_copy_limit(effects, cid, copies)
                   for cid, available in possible_copies.items()):
                raise ModError('Os pools originais do PS1 podem ultrapassar os limites individuais de 1–2.')
            for i, row in enumerate(rows):
                ids, draws = row['pesos'].keys(), row['compras']
                used = sum(min(older['compras'], 3 * len(ids & older['pesos'].keys())) for older in rows[:i])
                if 3 * len(ids) - used < draws:
                    raise ModError('O limite original de três cópias pode impedir o sorteio de um dos pools.')
                staged.append((draws, quantize_weights(row['pesos'], LEGACY_SCAN_COUNT)))
            plan.starters = staged
            plan.applied.append('Pools do deck inicial')
        except ModError as exc:
            plan.pending.append(f'Deck inicial: {exc}')
    if config.get('iniciais'):
        plan.pending.append('Perfis adicionais de deck inicial: disponíveis nas partidas do Studio.')
    recipes = config.get('receitas', {})
    for pair, result in recipes.get('fusoes', {}).items():
        a, b = map(int, pair.split(','))
        label = f'Fusão #{a:03d} + #{b:03d} → #{result:03d}'
        if profile and fusion_uses_original_ids(cards, a, b, result):
            plan.fusions[a, b] = result
        else:
            plan.pending.append(f'{label}: o BIN/CUE exige o perfil Drop x15 e IDs originais #001–#722.')
    if plan.fusions:
        plan.applied.append(f'Fusões personalizadas ({len(plan.fusions)})')
    for kind in ('rituais', 'equipamentos'):
        if recipes.get(kind):
            plan.pending.append(f'Relações de cartas ({kind}): compatíveis com as partidas do Studio.')
    return plan


def _replace_word(out, pc, before, after):
    offset = pc - EXE_DELTA
    if struct.unpack_from('<I',out,offset)[0] != before:
        raise ModError(f'Rotina PS1 divergente em 0x{pc:08X}.')
    struct.pack_into('<I',out,offset,after)


def _has_opening_attack_lock(exe):
    offset = FIRST_TURN_PC - EXE_DELTA
    return exe[offset:offset+4] == struct.pack('<I', FIRST_TURN_SOURCE)


def inspect_chest_catalog(exe):
    row_start = CHEST_ROW_FLAG_PC - EXE_DELTA - 4
    dim_start = CHEST_DIM_FLAG_PC - EXE_DELTA
    retail = struct.pack('<3I', *CHEST_ROW_CONTEXT)
    visible = struct.pack('<3I', CHEST_ROW_CONTEXT[0], CHEST_ROW_VISIBLE, CHEST_ROW_CONTEXT[2])
    observed = exe[row_start:row_start + len(retail)]
    if exe[dim_start:dim_start + 4] != struct.pack('<I', CHEST_DIM_FLAG):
        status = 'divergente'
    else:
        status = {retail: 'ausente', visible: 'aplicado'}.get(bytes(observed), 'divergente')
    return {'status': status, 'cartas': CARD_COUNT if status == 'aplicado' else 0}


def patch_chest_catalog(exe):
    """Show empty rows with the stock dim flag on the verified Drop x15."""
    status = inspect_chest_catalog(exe)['status']
    if status == 'aplicado':
        return exe
    if status != 'ausente':
        raise ModError('A rotina do catálogo do baú diverge do Drop x15.')
    out = bytearray(exe)
    _replace_word(out, CHEST_ROW_FLAG_PC, CHEST_ROW_CONTEXT[1], CHEST_ROW_VISIBLE)
    return bytes(out)


def patch_executable(exe, plan, *, profile):
    if not profile:
        return exe
    if not _has_opening_attack_lock(exe):
        raise ModError('A trava original de ataque no primeiro turno diverge do Drop x15.')
    if not plan.has_lp:
        return exe
    out = bytearray(exe)
    start, end = LP_CODE - EXE_DELTA, LP_BANK_END - EXE_DELTA
    if any(out[start:end]):
        raise ModError('O banco reservado para LP do PS1 está ocupado.')
    struct.pack_into(f'<{len(_LP_WORDS)}I',out,start,*_LP_WORDS)
    struct.pack_into(f'<{DUELIST_COUNT+1}H',out,LP_TABLE-EXE_DELTA,plan.player_lp,*plan.life)
    _replace_word(out,INIT_CALL,_LP_INIT,_LP_JAL)
    return bytes(out)


def verify_executable(exe, plan):
    opening_lock = _has_opening_attack_lock(exe)
    life = not plan.has_lp or (
        exe[INIT_CALL-EXE_DELTA:INIT_CALL-EXE_DELTA+4] == struct.pack('<I',_LP_JAL)
        and exe[LP_CODE-EXE_DELTA:LP_CODE-EXE_DELTA+len(_LP_WORDS)*4] == struct.pack(f'<{len(_LP_WORDS)}I',*_LP_WORDS)
        and exe[LP_TABLE-EXE_DELTA:LP_TABLE-EXE_DELTA+2*(DUELIST_COUNT+1)] ==
        struct.pack(f'<{DUELIST_COUNT+1}H',plan.player_lp,*plan.life))
    return opening_lock, life


def patch_wa(wa, plan):
    out = bytearray(wa)
    for (opponent, kind), weights in plan.groups.items():
        start = DUELIST_BASE + DUELIST_STRIDE * opponent + POOL_OFFSETS[kind]
        if start + CARD_COUNT * 2 > len(out):
            raise ModError('Arquivo WA_MRG truncado na tabela de duelistas.')
        struct.pack_into(f'<{CARD_COUNT}H', out, start, *weights)
    if plan.starters:
        if not decode_starters(wa):
            raise ModError('As tabelas iniciais na imagem não têm a estrutura esperada.')
        rows = plan.starters + [(0, (0,) * CARD_COUNT)] * (STARTER_POOLS - len(plan.starters))
        for block in STARTER_OFFSETS:
            if block + STARTER_SIZE > len(out):
                raise ModError('Arquivo WA_MRG truncado nos pools iniciais.')
            for i, (draws, weights) in enumerate(rows):
                struct.pack_into(f'<{CARD_COUNT+1}H',out,block+i*STARTER_STRIDE,draws,*weights)
    return bytes(out)


def verify_wa(wa, plan):
    if not plan.needs_wa:
        return True
    try:
        return patch_wa(wa, plan) == wa
    except ModError:
        return False
