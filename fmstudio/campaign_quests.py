"""Generate reproducible, reachable PS1 campaign donation requirements."""
from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from random import Random
import struct
import unicodedata

from .core import ModError
from .rarities import RARITIES
from .tables import (ATTR_NAMES, CARD_COUNT, DECK_SIZE, DUELIST_NAMES_REFERENCE,
                     GUARDIAN_FIELDS, POOL_TOTAL, STAR_NAMES, TYPE_NAMES)

SIMON_MURAN = 1
STORY_DUELISTS = range(2, 39)
DROP_RANKS = ('pow', 'bcd', 'tec')
CRITERIA = ('carta', 'tipo', 'atributo', 'guardian_star', 'raridade')
CATEGORY_NAMES = {
    'tipo': TYPE_NAMES, 'atributo': ATTR_NAMES, 'guardian_star': STAR_NAMES,
    'raridade': tuple(name for name, _ in RARITIES.values()),
}
CATEGORY_LABEL = {'tipo': 'Tipo', 'atributo': 'Atrib.', 'guardian_star': 'Estrela', 'raridade': 'Classe'}
MAX_CRITERIA = 4
FORMAT = 'fm-campaign-quests-v2'
LEGACY_FORMAT = 'fm-campaign-quests-v1'
CHEST_CARD_LIMIT = 250
LABEL_WIDTH = 22
TABLE_PREFIX = b'FMQ2'
TABLE_START = (4 + 39 * 2 + 95 + CARD_COUNT + 1) & ~1
RECORD = struct.Struct(f'<BBHH{LABEL_WIDTH}s')


def guaranteed_predecessors(opponent: int) -> tuple[int, ...]:
    """Simon is available in Free Duel. Other sources require a prior story win."""
    if opponent <= SIMON_MURAN:
        return ()
    previous = [SIMON_MURAN]
    if opponent > 7:
        previous.extend((7, *range(9, min(opponent, 18))))
    # Jono and Teana at Hiding can be encountered before the Palace guard.
    if opponent >= 21:
        previous.append(18)
    if opponent in range(22, 31, 2):
        previous.append(opponent - 1)
    if opponent == 32:
        previous.append(31)
    if opponent >= 33:
        previous.extend(range(21, 31))
        previous.extend(range(33, opponent))
    return tuple(previous)


def _integer(value, label, minimum, maximum):
    try:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ModError(f'{label}: informe um inteiro.') from exc
    if not minimum <= number <= maximum:
        raise ModError(f'{label}: informe um valor de {minimum} a {maximum}.')
    return number


def _add_weight(pool, row):
    card = _integer(row.get('carta_id'), 'Carta do pool', 1, CARD_COUNT)
    weight = _integer(row.get('peso'), 'Peso', 0, POOL_TOTAL)
    if card in pool:
        raise ModError(f'Peso duplicado para a carta #{card}.')
    if weight:
        pool[card] = weight


@dataclass(frozen=True)
class QuestCatalog:
    cards: dict[int, dict]
    drops: dict[tuple[int, str], dict[int, int]]
    starters: dict[int, tuple[int, dict[int, int]]]

    @classmethod
    def from_rows(cls, cards, drops, starters):
        catalog = {}
        for row in cards:
            card = _integer(row.get('id'), 'Carta', 1, 65535)
            if card > CARD_COUNT:
                continue
            rarity = row.get('raridade') or 'comum'
            if card in catalog or rarity not in RARITIES:
                raise ModError(f'Carta #{card}: ID duplicado ou raridade desconhecida.')
            catalog[card] = dict(nome=str(row.get('nome') or f'Carta {card}'), raridade=rarity,
                                 tipo_id=_integer(row.get('tipo_id'), 'Tipo', 0, 31),
                                 atributo_id=_integer(row.get('atributo_id'), 'Atributo', 0, 15),
                                 **{key: _integer(row.get(key), 'Guardian Star', 0, 16)
                                    for key in GUARDIAN_FIELDS})
        if catalog.keys() != set(range(1, CARD_COUNT + 1)):
            raise ModError('As quests PS1 exigem o catálogo completo dos IDs 1–722.')

        pools = {}
        for row in drops:
            rank = str(row.get('grupo', '')).strip().lower()
            if rank == 'deck':
                continue
            if rank not in DROP_RANKS:
                raise ModError(f'Grupo de drop desconhecido: {rank}.')
            opponent = _integer(row.get('duelista_id'), 'Duelista', 0, 39)
            _add_weight(pools.setdefault((opponent, rank), {}), row)
        for (opponent, rank), pool in pools.items():
            if sum(pool.values()) > POOL_TOTAL:
                raise ModError(f'Pool {opponent}/{rank} excede os {POOL_TOTAL} pesos do PS1.')

        initial = {}
        for row in starters:
            group = _integer(row.get('grupo'), 'Pool inicial', 0, 6)
            draws = _integer(row.get('compras'), 'Compras iniciais', 0, DECK_SIZE)
            saved, pool = initial.setdefault(group, (draws, {}))
            if saved != draws:
                raise ModError(f'Quantidade de compras divergente no pool inicial {group}.')
            _add_weight(pool, row)
        if (sum(draws for draws, _ in initial.values()) != DECK_SIZE
                or any(draws and sum(pool.values()) != POOL_TOTAL for draws, pool in initial.values())):
            raise ModError('O deck inicial precisa comprovar as 40 compras ponderadas.')
        return cls(catalog, pools, initial)

    @classmethod
    def read_csv(cls, directory: Path):
        directory = Path(directory)
        if (directory / 'base' / 'cartas.csv').is_file():
            directory /= 'base'

        def rows(name):
            with (directory / name).open(encoding='utf-8-sig', newline='') as stream:
                return list(csv.DictReader(stream, delimiter=';'))

        return cls.from_rows(rows('cartas.csv'), rows('decks_drops.csv'), rows('decks_iniciais.csv'))

    def fingerprint(self):
        source = [[(cid, row['tipo_id'], row['atributo_id'], row['raridade'],
                    *(row[field] for field in GUARDIAN_FIELDS))
                   for cid, row in sorted(self.cards.items())],
                  [(op, rank, sorted(pool.items())) for (op, rank), pool in sorted(self.drops.items()) if pool],
                  [(group, draws, sorted(pool.items()))
                   for group, (draws, pool) in sorted(self.starters.items()) if draws]]
        return hashlib.sha256(json.dumps(source, separators=(',', ':')).encode()).hexdigest()


def normalize_overrides(raw):
    """Read manual requirements or retain the criteria from a previous export."""
    if isinstance(raw, dict) and raw.get('formato') in (FORMAT, LEGACY_FORMAT):
        rows = raw.get('quests')
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ModError('Arquivo de quests incompleto.')
        previous = {str(row.get('oponente_id')): row.get('criterios') for row in rows}
        if len(previous) != len(rows):
            raise ModError('Duelista repetido no arquivo de quests.')
        raw = previous
    if not isinstance(raw, dict):
        raise ModError('Os requisitos devem ser agrupados pelo ID do duelista no JSON.')
    result = {}
    for key, requirements in raw.items():
        duel = str(_integer(key, 'Duelista da campanha', 1, 38))
        if duel == str(SIMON_MURAN):
            continue  # Projects and exports from v1 can still contain Simon's requirement.
        if duel in result or not isinstance(requirements, list) or not 1 <= len(requirements) <= MAX_CRITERIA:
            raise ModError(f'Duelista #{duel}: informe de 1 a {MAX_CRITERIA} requisitos uma vez.')
        result[duel] = []
        targets = set()
        for row in requirements:
            if not isinstance(row, dict) or row.get('tipo') not in CRITERIA:
                raise ModError(f'Duelista #{duel}: tipo de requisito inválido.')
            kind = row['tipo']
            target = (_integer(row.get('alvo'), 'Carta', 1, CARD_COUNT) if kind == 'carta'
                      else _integer(row.get('alvo'), kind, 0, len(CATEGORY_NAMES[kind]) - 1))
            if (kind != 'carta' and not CATEGORY_NAMES[kind][target]) or (kind, target) in targets:
                raise ModError(f'Duelista #{duel}: alvo inexistente ou duplicado.')
            targets.add((kind, target))
            result[duel].append({'tipo': kind, 'alvo': target,
                                 'quantidade': _integer(row.get('quantidade'), 'Quantidade', 1, 255)})
    return result


def _requirements(cards):
    choices = {kind: {} for kind in CRITERIA}
    for cid, card in sorted(cards.items()):
        choices['carta'][cid] = (card['nome'], {cid})
        targets = [('tipo', card['tipo_id']), ('atributo', card['atributo_id']),
                   ('raridade', tuple(RARITIES).index(card['raridade'])),
                   *(('guardian_star', card[field]) for field in GUARDIAN_FIELDS)]
        for kind, value in targets:
            options = CATEGORY_NAMES[kind]
            if value < len(options) and options[value]:
                label = f'{CATEGORY_LABEL[kind]} {options[value]}'
                choices[kind].setdefault(value, (label, set()))[1].add(cid)
    return choices


def _source(catalog, earlier, eligible):
    """Find the best rank among opponents available to farm before the quest."""
    best = None
    for opponent in earlier:
        for rank in DROP_RANKS:
            pool = catalog.drops.get((opponent, rank), {})
            available = sorted(eligible.intersection(pool))
            if available:
                weight = sum(pool[card] for card in available)
                if best is None or weight > best['peso']:
                    best = {'origem': 'drop', 'duelista_id': opponent, 'grupo': rank, 'peso': weight,
                            'carta_fonte': max(available, key=pool.get), 'denominador': POOL_TOTAL}
    return best


def _validate_inventory_capacity(opponent, criteria, choices, obtainable):
    """Each subset of requirements needs distinct spares within the chest capacity."""
    eligible = [choices[row['tipo']][row['alvo']][1] & obtainable for row in criteria]
    for mask in range(1, 1 << len(criteria)):
        subset = [i for i in range(len(criteria)) if mask & (1 << i)]
        ids = set().union(*(eligible[i] for i in subset))
        needed = sum(criteria[i]['quantidade'] for i in subset)
        if needed > len(ids) * CHEST_CARD_LIMIT - DECK_SIZE:
            raise ModError(f'Duelista #{opponent}: as doações exigem mais cópias '
                           'disponíveis por carta do que o baú comporta com o deck protegido.')


def generate_quests(catalog: QuestCatalog, seed: str, overrides=None):
    manual = normalize_overrides({} if overrides is None else overrides)
    choices = _requirements(catalog.cards)
    kinds = CRITERIA if len(choices['raridade']) > 1 else CRITERIA[:-1]
    quests = []
    for opponent in STORY_DUELISTS:
        earlier = guaranteed_predecessors(opponent)

        def candidate(kind, target, quantity=None):
            label, eligible = choices[kind].get(target, ('', set()))
            proof = _source(catalog, earlier, eligible)
            if proof is None:
                return None
            row = {'tipo': kind, 'alvo': target, 'rotulo': label, 'prova': proof}
            if quantity is not None:
                row['quantidade'] = quantity
            return row

        criteria = []
        if str(opponent) in manual:
            for row in manual[str(opponent)]:
                match = candidate(row['tipo'], row['alvo'], row['quantidade'])
                if match is None:
                    raise ModError(f'Duelista #{opponent}: {row["tipo"]} {row["alvo"]} deve estar '
                                   'nos drops de Simon ou de um antecessor garantido.')
                criteria.append(match)
        else:
            rng = Random(f'{seed}:{opponent}')
            options = {kind: [row for target in sorted(choices[kind])
                              if (row := candidate(kind, target)) is not None] for kind in kinds}
            available = [kind for kind in kinds if options[kind]]
            if not available:
                raise ModError(f'Duelista #{opponent}: faltam fontes de cartas para gerar a quest.')
            for kind in rng.sample(available, rng.randint(1, min(2, len(available)))):
                selected = rng.choices(options[kind], [row['prova']['peso'] for row in options[kind]])[0]
                proof = selected['prova']
                draws = rng.randint(12, 36 + opponent // 2)
                selected['quantidade'] = max(1, min(10 if kind == 'carta' else 50,
                                                   round(draws * proof['peso'] / POOL_TOTAL)))
                criteria.append(selected)
        criteria.sort(key=lambda row: row['tipo'] != 'carta')
        obtainable = set().union(*(catalog.drops.get((prior, rank), {})
                                   for prior in earlier for rank in DROP_RANKS))
        _validate_inventory_capacity(opponent, criteria, choices, obtainable)
        quests.append({'oponente_id': opponent, 'oponente': DUELIST_NAMES_REFERENCE[opponent],
                       'antecessores': list(earlier), 'criterios': criteria,
                       'dialogo': [f"{row['rotulo']}: {{baú}}/{row['quantidade']}" for row in criteria]})
    return {'formato': FORMAT, 'seed': str(seed), 'sha256_dados': catalog.fingerprint(),
            'momento': 'antes_do_duelo', 'isentos': [SIMON_MURAN], 'quests': quests}


def verify_quests(config, catalog):
    if not isinstance(config, dict) or config.get('formato') != FORMAT:
        raise ModError('Formato de quests desconhecido.')
    if config.get('sha256_dados') != catalog.fingerprint():
        raise ModError('As origens das quests divergem das cartas, drops ou deck inicial.')
    manual = normalize_overrides(config)
    if set(manual) != {str(duel) for duel in STORY_DUELISTS}:
        raise ModError(f'A tabela precisa incluir os {len(STORY_DUELISTS)} duelistas com quest.')
    return generate_quests(catalog, config['seed'], manual)


def compile_table(config, catalog, glyphs):
    """Little-endian table used by the campaign MIPS overlay."""
    config = verify_quests(config, catalog)
    lookup = {char: code for code, char in glyphs.items() if code < 0xF0}
    if any(char not in lookup for char in '0123456789/'):
        raise ModError('A fonte PS1 não tem os glifos dos contadores das quests.')
    unknown = lookup.get('?', 0)
    table = bytearray(TABLE_PREFIX + bytes(39 * 2))
    table.extend(lookup.get(chr(code), unknown) for code in range(32, 127))
    table.extend(tuple(RARITIES).index(catalog.cards[cid]['raridade']) for cid in range(1, CARD_COUNT + 1))
    table.extend(bytes(TABLE_START - len(table)))
    for quest in config['quests']:
        struct.pack_into('<H', table, 4 + 2 * quest['oponente_id'], len(table))
        criteria = quest['criterios']
        table.extend((len(criteria), 0))
        for row in criteria:
            label = unicodedata.normalize('NFKD', row['rotulo']).encode('ascii', 'ignore').strip()
            if row['tipo'] == 'carta' and (not label or len(label) > LABEL_WIDTH):
                label = f"#{row['alvo']} ".encode('ascii') + label
            table += RECORD.pack(CRITERIA.index(row['tipo']), row['quantidade'], row['alvo'],
                                 row['prova']['carta_fonte'], label[:LABEL_WIDTH])
    return bytes(table)


def table_size(data):
    """Validate the offsets and return the on-disc table length."""
    if (not data.startswith(TABLE_PREFIX) or len(data) < TABLE_START
            or struct.unpack_from('<H', data, 4 + 2 * SIMON_MURAN)[0]):
        raise ModError('Cabeçalho da tabela de quests divergente.')
    end = TABLE_START
    for duel in STORY_DUELISTS:
        if (struct.unpack_from('<H', data, 4 + 2 * duel)[0] != end or end + 2 > len(data)
                or not 1 <= data[end] <= MAX_CRITERIA):
            raise ModError(f'Registro binário de quest inválido para duelista #{duel}.')
        next_end = end + 2 + data[end] * RECORD.size
        if next_end > len(data):
            raise ModError('Tabela binária de quests truncada.')
        for start in range(end + 2, next_end, RECORD.size):
            kind, amount, _, source, _ = RECORD.unpack_from(data, start)
            if kind >= len(CRITERIA) or not amount or not 1 <= source <= CARD_COUNT:
                raise ModError(f'Requisito binário inválido para duelista #{duel}.')
        end = next_end
    return end
