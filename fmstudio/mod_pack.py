"""Pacotes de MOD por nome de carta (formato ``studio-fm-modpack-v1``).

Um pacote descreve o mod com NOMES de cartas e regras de montagem, nunca com
IDs fixos. Na hora de aplicar, os nomes são resolvidos contra o catálogo do
próprio projeto (``base/cartas.csv`` + edições), e todas as regras de
montagem (tipos dos decks, faixas de ATK, limite de efeitos) são conferidas
com os dados reais do disco do usuário.

O resultado é gravado com as mesmas funções da interface do Studio
(``save_rules``, ``save_quest_settings``, ``save_magic_values``), portanto
passa pelas mesmas validações e gera os mesmos backups rotativos.

Somente recursos que o perfil Original Drop x15 executa no PS1 são usados:
efeitos nativos, fusões #001–#722, pools de 40 compras dos oponentes, drops
POW/TEC/B-C-D, pools do deck inicial, quests de doação, IA difícil e a tabela
de destruição por tipo das mágicas.
"""
from __future__ import annotations

import difflib
import json
import re
import shutil
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from .campaign_quests import (CATEGORY_NAMES, QuestCatalog, STORY_DUELISTS, generate_quests,
                              guaranteed_predecessors, normalize_phrases)
from .core import ENTRY_GROW, ENTRY_SHRINK, ENTRY_TYPE_EVENT, ModError, check_effect
from .mod_data import CONFIG_KEY, base_tables, normalize_rules, save_rules
from .ps1_magic_values import REMOVAL_CARDS, magic_values, save_magic_values
from .tables import ATTR_NAMES, CARD_COUNT, DECK_SIZE, POOL_TOTAL, STARTER_POOLS, TYPE_NAMES

FORMAT = 'studio-fm-modpack-v1'
POOL_LAST_ID = CARD_COUNT - 2          # ps1_mod.LEGACY_SCAN_COUNT: pools vão até #720
MONSTER_TYPE_IDS = frozenset((*range(20), 24))
MAX_COPIES = 3
DUELISTS = range(1, 40)

PASSIVES = {'ataques_multiplos', 'ataque_primeiro_turno', 'monstro_indestrutivel', 'monstro_imune_magia',
            'monstro_imune_armadilha', 'dano_perfurante', 'nao_bloqueavel'}
FILTERED = {'aura_tipo': ('continuo', 'aliados_tipo'), 'bonus_por_tipo': ('continuo', 'proprio'),
            'bonus_deck_tipo': ('continuo', 'proprio'), 'bonus_cemiterio_tipo': ('continuo', 'proprio'),
            ENTRY_SHRINK: ('invocar', 'aliados_tipo'), ENTRY_GROW: (ENTRY_TYPE_EVENT, 'proprio')}

# Cartas que nunca entram por preenchimento automático (decks e drops): só
# aparecem onde o pacote pede explicitamente. Mantém as relíquias raras.
RESERVED_DEFAULT = (
    'Time Wizard', 'Dark Elf', 'Dark Magician', 'Magician of Black Chaos', 'Blue-eyes White Dragon',
    'Blue-eyes Ultimate Dragon', 'Black Luster Soldier', 'Gate Guardian', 'Kazejin', 'Sanga of the Thunder',
    'Suijin', 'Tri-horned Dragon', 'Summoned Skull', 'Red-eyes B. Dragon', 'Labyrinth Tank',
    'Perfectly Ultimate Great Moth', 'St. Joan', 'Zoa', 'Meteor B. Dragon', 'B. Skull Dragon',
    'Exodia the Forbidden One', 'Left Arm of the Forbidden One', 'Right Arm of the Forbidden One',
    'Left Leg of the Forbidden One', 'Right Leg of the Forbidden One', 'Cosmo Queen', 'Perfect Machine King',
)


def norm(text: str) -> str:
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', text.lower())


def _type_id(name) -> int:
    if name in (None, '', 'Todos', 'Todas', -1):
        return -1
    lookup = {norm(label): index for index, label in enumerate(TYPE_NAMES)}
    try:
        return lookup[norm(name)]
    except KeyError as exc:
        raise ModError(f'Tipo desconhecido no pacote: {name}') from exc


def _attr_id(name) -> int:
    if name in (None, '', 'Todos', -1):
        return -1
    lookup = {norm(label): index for index, label in enumerate(ATTR_NAMES)}
    try:
        return lookup[norm(name)]
    except KeyError as exc:
        raise ModError(f'Atributo desconhecido no pacote: {name}') from exc


@dataclass
class Report:
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    missing: dict[str, list[str]] = field(default_factory=dict)

    def miss(self, name, where, suggestions):
        hint = f" (parecidas: {', '.join(suggestions)})" if suggestions else ''
        self.missing.setdefault(name, []).append(where)
        self.warnings.append(f'{where}: carta "{name}" não existe no projeto{hint}.')


class Catalog:
    """Visão somente leitura das cartas originais do projeto."""

    def __init__(self, project, report: Report):
        self.project = project
        self.report = report
        self.cards = {}
        for cid in sorted(project.cards):
            row = project.get(cid)
            if cid > CARD_COUNT or row.get('virtual'):
                continue
            self.cards[cid] = {'id': cid, 'nome': str(row.get('nome') or ''), 'tipo': int(row['tipo_id']),
                               'atk': int(row.get('ataque') or 0), 'atributo': int(row.get('atributo_id') or 0)}
        self.by_name = {}
        for cid, card in self.cards.items():
            if card['nome']:
                self.by_name.setdefault(norm(card['nome']), cid)
        self.fusion_results = {int(row['resultado']) for row in getattr(project, 'fusions', [])
                               if str(row.get('possivel_glitch', 0)) != '1'}

    def find(self, name, where):
        key = norm(name)
        if key in self.by_name:
            return self.by_name[key]
        close = difflib.get_close_matches(key, self.by_name, n=3, cutoff=0.72)
        self.report.miss(name, where, [self.cards[self.by_name[c]]['nome'] for c in close])
        return None

    def is_monster(self, cid):
        return self.cards[cid]['tipo'] in MONSTER_TYPE_IDS

    def label(self, cid):
        return f"#{cid:03d} {self.cards[cid]['nome']}"


# ---------------------------------------------------------------- efeitos

def expand_effect(spec: dict, catalog: Catalog, note: str):
    action = spec['acao']
    entry = {'acao': action, 'observacao': note[:500]}
    if action in PASSIVES:
        entry.update(evento='continuo', alvo='proprio', valor=int(spec.get('valor', 0)))
    elif action == 'perder_lp_por_ataque':
        entry.update(evento='atacar', alvo='proprio', valor=int(spec['valor']))
    elif action == 'dano_lp':
        entry.update(evento='invocar', alvo='inimigo', valor=int(spec['valor']))
    elif action == 'cura_lp':
        entry.update(evento='invocar', alvo='proprio', valor=int(spec['valor']))
    elif action == 'bonus_por_carta_id':
        ref = catalog.find(spec['carta'], f'{note} (referência)')
        if ref is None:
            return None
        entry.update(evento='continuo', alvo='proprio', carta_referencia_id=ref,
                     origem_contagem=spec.get('origem', 'campo'), valor=int(spec.get('valor', 0)),
                     valor_def=int(spec.get('def', 0)), escopo=spec.get('escopo', 'aliados'))
    elif action in FILTERED:
        event, target = FILTERED[action]
        entry.update(evento=event, alvo=target, tipo_id=_type_id(spec.get('tipo')),
                     atributo_id=_attr_id(spec.get('atributo')), combinar_filtros='e',
                     valor=int(spec.get('valor', 0)), valor_def=int(spec.get('def', 0)),
                     escopo=spec.get('escopo', 'aliados'))
    else:
        raise ModError(f'Ação de efeito não suportada pelo pacote: {action}')
    return check_effect(entry)


def _merge_cost(effects, amount):
    for effect in effects:
        if effect['acao'] == 'perder_lp_por_ataque':
            effect['valor'] += amount
            return
    effects.append({'acao': 'perder_lp_por_ataque', 'valor': amount})


def build_effects(pack, catalog: Catalog, custom_results: set[int]):
    """Retorna {cid: [efeitos validados]} e a prioridade de corte de cada carta."""
    rules = pack['regras']
    normal_min, fusion_min = rules['atk_minimo_efeito'], rules['atk_minimo_efeito_fusao']
    fusion_results = catalog.fusion_results | custom_results
    report = catalog.report

    def eligible(cid):
        card = catalog.cards[cid]
        limit = fusion_min if cid in fusion_results else normal_min
        return catalog.is_monster(cid) and card['atk'] >= limit

    effects, priority = {}, {}
    for name, spec in pack.get('assinaturas', {}).items():
        cid = catalog.find(name, 'Assinatura')
        if cid is None:
            continue
        if not eligible(cid):
            report.warnings.append(f'Assinatura {catalog.label(cid)}: ATK {catalog.cards[cid]["atk"]} '
                                   'abaixo do mínimo para efeitos; ignorada.')
            continue
        note = f"{pack['nome']}: {spec['nome']}"
        built = [expand_effect(item, catalog, note) for item in spec['efeitos']]
        effects[cid] = [item for item in built if item is not None]
        priority[cid] = (0, -catalog.cards[cid]['atk'])

    templates = {_type_id(name): spec for name, spec in pack.get('arquetipos', {}).items()}
    taxes = sorted(rules.get('taxa_de_poder', []), key=lambda row: -row['atk_min'])
    for cid, card in catalog.cards.items():
        if cid in effects or card['tipo'] not in templates or not eligible(cid):
            continue
        spec = templates[card['tipo']]
        items = [dict(item) for item in spec['efeitos']]
        tax = next((row['perder_lp'] for row in taxes if card['atk'] >= row['atk_min']), 0)
        if tax:
            _merge_cost(items, tax)
        note = f"{pack['nome']}: {spec['nome']}"
        built = [expand_effect(item, catalog, note) for item in items]
        effects[cid] = [item for item in built if item is not None]
        priority[cid] = (1, -card['atk'])
    return effects, priority


# ---------------------------------------------------------------- fusões

def build_fusions(pack, catalog: Catalog):
    recipes, names = {}, []
    for row in pack.get('fusoes', []):
        ids = [catalog.find(row[key], f"Fusão {row['nome']}") for key in ('a', 'b', 'resultado')]
        if None in ids:
            continue
        if not all(catalog.is_monster(cid) for cid in ids):
            catalog.report.warnings.append(f"Fusão {row['nome']}: materiais e resultado precisam ser monstros.")
            continue
        a, b = sorted(ids[:2])
        recipes[f'{a},{b}'] = ids[2]
        names.append(f"{catalog.label(ids[0])} + {catalog.label(ids[1])} → {catalog.label(ids[2])} ({row['nome']})")
    return recipes, names


# ---------------------------------------------------------------- decks

def _reserved(pack, catalog):
    names = pack.get('regras', {}).get('reservadas', RESERVED_DEFAULT)
    return {catalog.by_name[norm(name)] for name in names if norm(name) in catalog.by_name}


def _support_cards(pack, opponent, catalog):
    level = pack['suporte']['niveis'][opponent['nivel']]
    out = Counter()
    where = f"Deck #{opponent['id']} {opponent['nome']}"
    for kind in opponent['tipos']:
        for name in pack['suporte']['equip_por_tipo'].get(kind, []):
            cid = catalog.find(name, where)
            if cid is not None:
                out[cid] = max(out[cid], level['copias_equip'])
    field_name = pack['suporte']['campo_por_tipo'].get(opponent['tipos'][0])
    if field_name:
        cid = catalog.find(field_name, where)
        if cid is not None:
            out[cid] = max(out[cid], level['copias_campo'])
    for name, copies in level['cartas']:
        cid = catalog.find(name, where)
        if cid is not None:
            out[cid] = min(MAX_COPIES, out[cid] + copies)
    return out


def _fill_monsters(deck: Counter, types: set[int], bands, catalog, blocked, where):
    remaining = DECK_SIZE - sum(deck.values())
    pool = sorted((card for cid, card in catalog.cards.items()
                   if card['tipo'] in types and cid <= POOL_LAST_ID and cid not in blocked and cid not in deck),
                  key=lambda card: (-card['atk'], card['id']))
    carry = 0
    for band in bands:
        if remaining <= 0:
            break
        wanted = band['cartas'] + carry
        taken = 0
        for card in pool:
            if remaining <= 0 or taken >= wanted:
                break
            if card['id'] in deck or not band['atk_min'] <= card['atk'] <= band['atk_max']:
                continue
            copies = min(band['copias'], remaining)
            deck[card['id']] += copies
            remaining -= copies
            taken += 1
        carry = max(0, wanted - taken) if band['cartas'] < 99 else 0
    # Tipos com poucas cartas na faixa: completar com 3 cópias das já escolhidas.
    for cid in sorted((cid for cid in deck if catalog.is_monster(cid)), key=lambda cid: catalog.cards[cid]['atk']):
        while remaining > 0 and deck[cid] < MAX_COPIES:
            deck[cid] += 1
            remaining -= 1
    if remaining > 0:
        ceiling = bands[0]['atk_max']
        for card in pool:
            if remaining <= 0:
                break
            if card['id'] not in deck and card['atk'] <= ceiling:
                copies = min(2, remaining)
                deck[card['id']] += copies
                remaining -= copies
    if remaining > 0:
        raise ModError(f'{where}: os tipos escolhidos não têm monstros suficientes para 40 cartas.')


def build_opponent_deck(pack, opponent, catalog: Catalog, blocked):
    where = f"Deck #{opponent['id']} {opponent['nome']}"
    types = {_type_id(name) for name in opponent['tipos']}
    if not 1 <= len(types) <= 2:
        raise ModError(f'{where}: use um ou dois tipos de monstro.')
    deck = Counter()
    for name, copies in opponent.get('assinaturas', []):
        cid = catalog.find(name, where)
        if cid is None:
            continue
        if catalog.is_monster(cid) and catalog.cards[cid]['tipo'] not in types:
            catalog.report.warnings.append(f'{where}: {catalog.label(cid)} é de outro tipo; fora do deck.')
            continue
        if cid > POOL_LAST_ID:
            catalog.report.warnings.append(f'{where}: {catalog.label(cid)} fica fora do pool do PS1 (#001–#720).')
            continue
        deck[cid] = min(MAX_COPIES, deck[cid] + copies)
    for cid, copies in _support_cards(pack, opponent, catalog).items():
        if cid <= POOL_LAST_ID and sum(deck.values()) + copies <= DECK_SIZE - 20:
            deck[cid] = max(deck[cid], copies)
    _fill_monsters(deck, types, pack['faixas'][opponent['nivel']], catalog, blocked, where)
    monsters = [cid for cid in deck if catalog.is_monster(cid)]
    if any(catalog.cards[cid]['tipo'] not in types for cid in monsters):
        raise ModError(f'{where}: monstro fora dos tipos do deck.')
    if len(deck) * MAX_COPIES < DECK_SIZE:
        raise ModError(f'{where}: o pool do PS1 precisa de pelo menos 14 cartas diferentes.')
    return deck


# ---------------------------------------------------------------- drops

def build_drops(pack, opponent, next_opponent, deck: Counter, catalog: Catalog, blocked):
    weights = pack['drops']
    where = f"Drops #{opponent['id']} {opponent['nome']}"
    groups = {'pow': Counter(), 'tec': Counter(), 'bcd': Counter()}
    if next_opponent is not None:
        for kind in next_opponent['tipos']:
            counter = pack['contra'].get(kind, {})
            for name in counter.get('cartas', []):
                cid = catalog.find(name, where)
                if cid is not None:
                    groups['tec'][cid] = max(groups['tec'][cid], weights['peso_contra_carta_tec'])
                    groups['bcd'][cid] = max(groups['bcd'][cid], weights['peso_contra_carta_bcd'])
            if opponent['id'] >= weights['contra_monstros_a_partir_de']:
                for name in counter.get('monstros', []):
                    cid = catalog.find(name, where)
                    if cid is not None:
                        groups['pow'][cid] = max(groups['pow'][cid], weights['peso_contra_monstro_pow'])
    monsters = sorted((cid for cid in deck if catalog.is_monster(cid)), key=lambda cid: -catalog.cards[cid]['atk'])
    for name, _ in opponent.get('assinaturas', []):
        cid = catalog.by_name.get(norm(name))
        if cid is not None and cid in deck and cid not in blocked:
            groups['pow'][cid] = max(groups['pow'][cid], weights['peso_assinatura_pow'])
    for cid in [cid for cid in monsters if cid not in blocked][:3]:
        groups['pow'][cid] = max(groups['pow'][cid], weights['peso_forte_pow'])
    for cid in deck:
        if not catalog.is_monster(cid):
            groups['tec'][cid] = max(groups['tec'][cid], weights['peso_suporte_tec'])
        elif cid not in blocked:
            groups['bcd'][cid] = max(groups['bcd'][cid], weights['peso_monstro_bcd'])
    for group, rows in opponent.get('drops_extra', {}).items():
        for name, weight in rows:
            cid = catalog.find(name, where)
            if cid is not None:
                groups[group][cid] = max(groups[group][cid], int(weight))
    for group, table in groups.items():
        if not table:  # POW vazio no começo: herda o melhor da própria lista.
            table.update({cid: 10 for cid in monsters[:3]})
    return {group: {cid: weight for cid, weight in sorted(table.items()) if cid <= CARD_COUNT}
            for group, table in groups.items()}


# ---------------------------------------------------------------- deck inicial

def build_starter(pack, starter, catalog: Catalog, blocked):
    where = f"Deck inicial {starter['nome']}"
    types = [_type_id(name) for name in starter['tipos']]
    limits = pack['inicial_faixa_monstros']
    by_type = {kind: sorted((card for cid, card in catalog.cards.items()
                             if card['tipo'] == kind and card['atk'] <= limits['atk_max']
                             and cid <= POOL_LAST_ID and cid not in blocked),
                            key=lambda card: (-card['atk'], card['id'])) for kind in types}
    chosen = []
    while len(chosen) < 9 and any(by_type.values()):
        for kind in types:
            if by_type[kind] and len(chosen) < 9:
                chosen.append(by_type[kind].pop(0)['id'])
    if len(chosen) < 9:
        raise ModError(f'{where}: faltam monstros fracos dos tipos escolhidos.')
    deck = Counter({cid: 3 for cid in chosen})
    strong = sorted((card for cid, card in catalog.cards.items()
                     if card['tipo'] in types and limits['atk_max'] < card['atk'] <= limits['atk_max_forte']
                     and cid <= POOL_LAST_ID and cid not in blocked),
                    key=lambda card: (-card['atk'], card['id']))
    singles = [(starter['triplo_equip'], 3), (starter['equip_2'], 2), (starter['campo'], 2),
               (starter['armadilha'], 2), (starter['cura'], 1), (starter['remocao'], 1)]
    for name, copies in singles:
        cid = catalog.find(name, where)
        if cid is not None and cid <= POOL_LAST_ID:
            deck[cid] = copies
    if strong:
        deck[strong[0]['id']] = 2
    spare = [cid for kind in types for cid in (card['id'] for card in by_type[kind])]
    while sum(deck.values()) < DECK_SIZE and spare:
        cid = spare.pop(0)
        deck[cid] = min(3, DECK_SIZE - sum(deck.values()))
    if sum(deck.values()) != DECK_SIZE:
        raise ModError(f'{where}: não foi possível fechar 40 cartas.')
    removal = {catalog.by_name.get(norm('Dark Hole')), catalog.by_name.get(norm('Raigeki'))}
    if not removal.intersection(deck):
        raise ModError(f'{where}: precisa de pelo menos 1 Dark Hole ou 1 Raigeki.')
    return deck


def starter_pools(deck: Counter):
    """Converte 40 cartas exatas em até 7 pools nativos sem sorteio aleatório.

    O PS1 limita 3 cópias por carta; um pool só com cartas de 3 cópias e
    compras = 3 × cartas sai exato, e um pool de uma carta sai exato também.
    """
    triples = {cid: 1 for cid, copies in deck.items() if copies == 3}
    pools = [{'compras': 3 * len(triples), 'pesos': triples}] if triples else []
    pools += [{'compras': copies, 'pesos': {cid: 1}} for cid, copies in sorted(deck.items()) if copies != 3]
    exact = len(pools) <= STARTER_POOLS
    while len(pools) > STARTER_POOLS:
        a, b = pools.pop(), pools.pop()
        pools.append({'compras': a['compras'] + b['compras'], 'pesos': {**a['pesos'], **b['pesos']}})
    return pools, exact


# ---------------------------------------------------------------- quests

def build_quests(pack, catalog: Catalog):
    requirements, phrases = {}, {}
    for opponent in pack['oponentes']:
        key = str(opponent['id'])
        if opponent.get('frase'):
            phrases[key] = opponent['frase']
        rows = []
        for row in opponent.get('quest', []):
            kind = row['tipo']
            if kind == 'carta':
                target = catalog.find(row['alvo'], f"Quest #{key}")
                if target is None:
                    continue
            elif kind == 'tipo':
                target = _type_id(row['alvo'])
            elif kind == 'atributo':
                target = _attr_id(row['alvo'])
            else:
                raise ModError(f'Quest #{key}: requisito {kind} não suportado pelo pacote.')
            rows.append({'tipo': kind, 'alvo': target, 'quantidade': int(row['quantidade'])})
        if rows:
            if len(rows) > 3:
                raise ModError(f'Quest #{key}: o overlay QOV7 aceita até 3 requisitos.')
            requirements[key] = rows
    return requirements, normalize_phrases(phrases)


def _quantized(weights):
    from .ps1_mod import quantize_weights
    data = quantize_weights(weights, CARD_COUNT)
    return {cid: value for cid, value in enumerate(data, 1) if value}


def check_quest_sources(requirements, drops, catalog: Catalog):
    """Mesmo critério do Studio: a fonte precisa estar nos drops de um antecessor garantido."""
    problems = []
    for key, rows in requirements.items():
        earlier = guaranteed_predecessors(int(key))
        available = set().union(*(set(drops.get(op, {}).get(group, {})) for op in earlier
                                  for group in ('pow', 'tec', 'bcd'))) if earlier else set()
        for row in rows:
            if row['tipo'] == 'carta':
                eligible = {row['alvo']}
            else:
                field_name = {'tipo': 'tipo', 'atributo': 'atributo'}[row['tipo']]
                eligible = {cid for cid, card in catalog.cards.items() if card[field_name] == row['alvo']}
            if not eligible & available:
                label = CATEGORY_NAMES.get(row['tipo'], ())
                name = (catalog.label(row['alvo']) if row['tipo'] == 'carta'
                        else label[row['alvo']] if row['alvo'] < len(label) else row['alvo'])
                problems.append(f'Quest #{key}: {row["tipo"]} {name} não cai de nenhum antecessor garantido.')
    return problems


def quest_catalog(project, catalog: Catalog, drops, starter_rows):
    cards = []
    for cid in range(1, CARD_COUNT + 1):
        row = project.get(cid)
        cards.append({'id': cid, 'nome': row.get('nome') or f'Carta {cid}', 'raridade': row.get('raridade') or 'comum',
                      'tipo_id': row['tipo_id'], 'atributo_id': row.get('atributo_id') or 0,
                      'guardian_1_id': row.get('guardian_1_id') or 0, 'guardian_2_id': row.get('guardian_2_id') or 0})
    drop_rows = [{'duelista_id': op, 'grupo': group, 'carta_id': cid, 'peso': weight}
                 for op, groups in drops.items() for group, table in groups.items()
                 for cid, weight in _quantized(table).items()]
    return QuestCatalog.from_rows(cards, drop_rows, starter_rows)


# ---------------------------------------------------------------- plano completo

@dataclass
class ModPlan:
    effects: dict
    priority: dict
    fusions: dict
    fusion_names: list
    decks: dict
    drops: dict
    starters: dict
    starter_ps1: str
    starter_pools: list
    starter_exact: bool
    quests: dict
    phrases: dict
    removal: dict
    report: Report
    trimmed: list = field(default_factory=list)
    blockers: list = field(default_factory=list)
    bytes_used: int = 0
    bytes_limit: int = 0


def load_pack(path: Path) -> dict:
    pack = json.loads(Path(path).read_text(encoding='utf-8'))
    if pack.get('formato') != FORMAT:
        raise ModError(f'Pacote de mod desconhecido: {path}')
    return pack


def plan_mod(project, pack, *, starter: str | int | None = None) -> ModPlan:
    report = Report()
    catalog = Catalog(project, report)
    if len(catalog.cards) < CARD_COUNT:
        raise ModError('O projeto precisa do catálogo completo #001–#722 (importe o BIN/CUE Drop x15).')
    blocked = _reserved(pack, catalog)

    fusions, fusion_names = build_fusions(pack, catalog)
    effects, priority = build_effects(pack, catalog, set(fusions.values()))

    opponents = {row['id']: row for row in pack['oponentes']}
    if set(opponents) != set(DUELISTS):
        raise ModError('O pacote precisa definir os 39 duelistas (#1–#39).')
    order = pack['ordem_historia']
    following = {op: (order[i + 1] if i + 1 < len(order) else None) for i, op in enumerate(order)}
    decks = {op: build_opponent_deck(pack, opponents[op], catalog, blocked) for op in DUELISTS}
    drops = {op: build_drops(pack, opponents[op], opponents.get(following.get(op)), decks[op], catalog, blocked)
             for op in DUELISTS}

    starters, blockers = {}, []
    for row in pack['iniciais']:
        try:
            starters[row['nome']] = build_starter(pack, row, catalog, blocked)
        except ModError as exc:
            blockers.append(str(exc))
            report.warnings.append(f'BLOQUEIO: {exc}')
    if not starters:
        report.warnings.append('BLOQUEIO: nenhum deck inicial ficou válido.')
        starters = {row['nome']: Counter() for row in pack['iniciais'][:1]}
    names = list(starters)
    if starter is None:
        chosen = names[0]
    elif isinstance(starter, int) or str(starter).isdigit():
        index = int(starter) - 1
        if not 0 <= index < len(names):
            raise ModError(f'Deck inicial {starter}: escolha de 1 a {len(names)}.')
        chosen = names[index]
    else:
        matches = [name for name in names if norm(name) == norm(starter)]
        if not matches:
            raise ModError(f'Deck inicial "{starter}" não existe. Opções: {", ".join(names)}')
        chosen = matches[0]
    pools, exact = starter_pools(starters[chosen]) if starters[chosen] else ([], True)

    requirements, phrases = build_quests(pack, catalog)
    for problem in check_quest_sources(requirements, drops, catalog):
        report.warnings.append(problem)

    removal = {}
    for name, rule in pack.get('magias', {}).get('destruicao', {}).items():
        cid = catalog.find(name, 'Mágica de destruição')
        if cid is None:
            continue
        if cid not in REMOVAL_CARDS:
            report.warnings.append(f'{catalog.label(cid)} não usa a tabela de destruição por tipo do PS1.')
            continue
        removal[cid] = ({'atk_min': int(rule['atk_min'])} if 'atk_min' in rule
                        else {'tipo': _type_id(rule['tipo'])})

    plan = ModPlan(effects, priority, fusions, fusion_names, decks, drops, starters, chosen, pools, exact,
                   requirements, phrases, removal, report)
    plan.blockers = blockers + [w for w in report.warnings if 'antecessor' in w]
    return plan


def rules_snapshot(project, plan: ModPlan, pack) -> dict:
    rules = dict(project.metadata.get(CONFIG_KEY) or {})
    rules['ia_ps1'] = pack['regras'].get('ia_ps1', 'dificil')
    duelists = dict(rules.get('duelistas') or {})
    for op in DUELISTS:
        entry = dict(duelists.get(str(op)) or {})
        entry['deck'] = {'cartas': [], 'pools': [{'compras': DECK_SIZE, 'pesos': dict(plan.decks[op])}]}
        entry['drops'] = {group: dict(table) for group, table in plan.drops[op].items()}
        entry['drops_do_deck'] = False
        entry.pop('pesos_drops_do_deck', None)
        duelists[str(op)] = entry
    rules['duelistas'] = duelists
    recipes = dict(rules.get('receitas') or {})
    recipes['fusoes'] = dict(plan.fusions)
    rules['receitas'] = recipes
    rules['iniciais'] = {name: {'peso': 1, 'cartas': sorted(deck.elements())} for name, deck in plan.starters.items()}
    rules['pools_iniciais_ps1'] = plan.starter_pools
    return rules


def _space_probe(project, metadata, effects):
    return SimpleNamespace(metadata=metadata, effects={str(cid): rows for cid, rows in effects.items()},
                           get=project.get, cards=project.cards, folder=getattr(project, 'folder', None),
                           fusions=getattr(project, 'fusions', []))


def fit_native_space(project, plan: ModPlan, pack, rules):
    """Corta arquétipos de menor ATK até as regras nativas caberem na área do Drop x15."""
    from .ps1_mod import compile_mod
    from .ps1_runtime import compile_effects

    margin = int(pack['regras'].get('margem_bytes_ps1', 256))
    metadata = {**project.metadata, CONFIG_KEY: normalize_rules(rules, {cid: project.get(cid) for cid in project.cards})}
    effects = {cid: list(rows) for cid, rows in plan.effects.items()}
    order = sorted(effects, key=lambda cid: plan.priority[cid], reverse=True)
    mod_plan = compile_mod(_space_probe(project, metadata, effects), profile=True, wa_verified=True)
    while True:
        probe = _space_probe(project, metadata, effects)
        try:
            native = compile_effects(probe, True, fixed_decks=mod_plan.fixed_decks, fusions=mod_plan.fusions)
        except ModError as exc:
            if 'excedem a área' not in str(exc):
                raise
            native = None
        if native is not None and native.data_end + margin <= native.bank_end:
            plan.bytes_used = native.data_end - 0x801CD7A0
            plan.bytes_limit = native.bank_end - 0x801CD7A0
            plan.effects = effects
            return mod_plan, native
        if not order or plan.priority[order[0]][0] == 0:
            raise ModError('Os efeitos de assinatura sozinhos não cabem na área nativa do PS1.')
        removed = order.pop(0)
        plan.trimmed.append(removed)
        effects.pop(removed)


def apply_mod(project, pack, *, starter=None, keep_other_effects=False):
    """Aplica o pacote no projeto. Retorna (plano, relatório de exportação)."""
    from .ps1_campaign_quests import save_quest_settings

    plan = plan_mod(project, pack, starter=starter)
    if plan.blockers:
        raise ModError('Corrija antes de aplicar:\n  - ' + '\n  - '.join(plan.blockers))
    rules = rules_snapshot(project, plan, pack)
    mod_plan, native = fit_native_space(project, plan, pack, rules)

    # Validação das quests com as fontes que o mod realmente grava.
    starter_rows = [{'grupo': index, 'compras': row['compras'], 'carta_id': cid, 'peso': weight}
                    for index, row in enumerate(plan.starter_pools)
                    for cid, weight in _quantized(row['pesos']).items()]
    catalog = Catalog(project, plan.report)
    generate_quests(quest_catalog(project, catalog, plan.drops, starter_rows), pack['regras']['seed_quests'],
                    plan.quests)

    folder = Path(project.folder)
    current = folder / 'projeto.json'
    if current.is_file():
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        backup = folder / 'backups' / f'projeto_antes_{norm(pack["nome"])}_{stamp}.json'
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, backup)
        plan.report.notes.append(f'Backup completo antes do mod: {backup}')

    new_effects = {} if not keep_other_effects else {key: rows for key, rows in project.effects.items()}
    new_effects.update({str(cid): rows for cid, rows in plan.effects.items()})
    project.effects = new_effects
    project.metadata['mod_pack'] = {'nome': pack['nome'], 'versao': pack['versao'],
                                    'aplicado_em': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                                    'deck_inicial_ps1': plan.starter_ps1}
    save_rules(project, rules)
    save_quest_settings(project, enabled=True, seed=pack['regras']['seed_quests'],
                        requirements=plan.quests, phrases=plan.phrases)
    values = magic_values(project)
    values['destruicao'].update(plan.removal)
    save_magic_values(project, values)
    return plan, mod_plan, native


def describe(plan: ModPlan, catalog_project, pack, mod_plan=None) -> str:
    catalog = Catalog(catalog_project, Report())
    lines = [f"MOD {pack['nome']} v{pack['versao']}", '']
    lines.append(f'Efeitos nativos: {len(plan.effects)} cartas '
                 f'({sum(1 for c in plan.effects if plan.priority[c][0] == 0)} assinaturas).')
    if plan.bytes_limit:
        lines.append(f'Área nativa do PS1: {plan.bytes_used} de {plan.bytes_limit} bytes.')
    if plan.trimmed:
        lines.append(f'Arquétipos cortados por espaço ({len(plan.trimmed)}): '
                     + ', '.join(catalog.label(cid) for cid in plan.trimmed))
    lines.append(f'Fusões personalizadas: {len(plan.fusions)}')
    lines += [f'  {row}' for row in plan.fusion_names]
    lines.append('')
    names = {row['id']: row for row in pack['oponentes']}
    for op in DUELISTS:
        deck = plan.decks[op]
        monsters = sum(n for cid, n in deck.items() if catalog.is_monster(cid))
        lines.append(f"#{op:02d} {names[op]['nome']} — {names[op]['tema']} ({' + '.join(names[op]['tipos'])}, "
                     f"{names[op]['nivel']}): {monsters} monstros, {40 - monsters} mágicas/armadilhas/equips")
        top = sorted((cid for cid in deck if catalog.is_monster(cid)), key=lambda c: -catalog.cards[c]['atk'])[:4]
        lines.append('    destaques: ' + ', '.join(catalog.label(cid) for cid in top))
        counters = sorted(plan.drops[op]['tec'], key=lambda c: -plan.drops[op]['tec'][c])[:3]
        lines.append('    drops TEC principais: ' + ', '.join(catalog.label(cid) for cid in counters))
        if str(op) in plan.quests:
            parts = []
            for row in plan.quests[str(op)]:
                if row['tipo'] == 'carta':
                    parts.append(f"{row['quantidade']}x {catalog.label(row['alvo'])}")
                else:
                    parts.append(f"{row['quantidade']}x {row['tipo']} {CATEGORY_NAMES[row['tipo']][row['alvo']]}")
            lines.append('    quest: ' + '; '.join(parts))
    lines.append('')
    for name, deck in plan.starters.items():
        mark = ' (gravado no PS1)' if name == plan.starter_ps1 else ''
        lines.append(f'Deck inicial {name}{mark}:')
        lines.append('    ' + ', '.join(f'{n}x {catalog.label(cid)}' for cid, n in sorted(deck.items())))
    if not plan.starter_exact:
        lines.append('Aviso: o deck inicial passou de 7 pools e foi agrupado (sorteio aproximado).')
    if mod_plan is not None and mod_plan.pending:
        lines += ['', 'Pendências do exportador PS1:'] + [f'  - {row}' for row in mod_plan.pending]
    if plan.report.missing:
        lines += ['', f'Nomes não encontrados no projeto ({len(plan.report.missing)}):']
        lines += [f'  - {name}' for name in sorted(plan.report.missing)]
    if plan.report.warnings:
        lines += ['', f'Avisos ({len(plan.report.warnings)}):'] + [f'  - {row}' for row in plan.report.warnings]
    if plan.report.notes:
        lines += [''] + plan.report.notes
    return '\n'.join(lines)
