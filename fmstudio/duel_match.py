"""A playable duel built on the Studio's shared combat and effect rules."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from random import SystemRandom

from .continuous import SIDES
from .core import ModError
from .duel_engine import DuelLab, MAX_HAND, POSITIONS
from .guardian import guardian_options
from .mod_data import (
    CONFIG_KEY, MONSTER_TYPES, STOCK_STARTER, base_tables, card_effects, deal_deck,
    drop_weights, duelist_profile, match_recipes, normalize_rules, opposite, starting_life, weighted_choice,
)
from .tables import CARD_COUNT

TRAP_LIMITS = {681: 500, 682: 1000, 683: 1500, 684: 2000, 685: 3000, 686: None}
CURE_SPELLS = dict(zip(range(338, 343), (200, 500, 1000, 2000, 5000)))
DAMAGE_SPELLS = dict(zip(range(343, 348), (50, 100, 200, 500, 1000)))
TARGETED_STATS = {'aumentar_atk', 'reduzir_atk', 'aumentar_def', 'reduzir_def'}
STOCK_EQUIP_BONUS = 500


@dataclass(frozen=True)
class Play:
    kind: str
    hand: tuple[int, ...]
    card_id: int
    slot: int | None = None
    star: int = 0
    position: str = 'ataque'
    target: tuple[str, int] | None = None
    tribute: tuple[int, ...] = ()
    face_up: bool = True


@dataclass(frozen=True)
class Attack:
    slot: int
    target: int | None


class DuelMatch(DuelLab):
    state_fields = DuelLab.state_fields + ('traps', 'active', 'played', 'positions_used',
                                          'swords', 'deck_out', 'terrain')

    def __init__(self, cards, effects, decks, *, initial_lp=8000, fusions=None, equips=None,
                 rituals=None, default_copies=3, rng=None, first='jogador',
                 stock_rules=False, trap_limits=None, terrain_bonuses=None, stock_equips=None):
        super().__init__(cards, effects, initial_lp=initial_lp, default_copies=default_copies)
        if first not in SIDES:
            raise ModError('Escolha o primeiro duelista.')
        self.fusions = fusions or {}
        self.equips = equips or {}
        self.rituals = rituals or {}
        self.stock_rules = stock_rules
        self.stock_equips = stock_equips or set()
        self.trap_limits = {**TRAP_LIMITS, **(trap_limits or {})} if stock_rules else {}
        self.terrain_bonuses = terrain_bonuses or {}
        self.terrain = None
        self.traps = {side: [] for side in SIDES}
        self.swords = {side: 0 for side in SIDES}
        self.active = first
        self.played = False
        self.positions_used = set()
        self.deck_out = None
        self.reward_card = None
        self._pending_reward = None
        rng = rng or SystemRandom()
        for side in SIDES:
            self.set_deck(side, decks[side])
            if not self.decks[side]:
                raise ModError(f'Configure um deck para {side}.')
            rng.shuffle(self.decks[side])
        for side in SIDES:
            self.draw(side, MAX_HAND)
        self._begin(first)

    @property
    def winner(self):
        if self.deck_out is not None:
            return opposite(self.deck_out)
        alive = [side for side in SIDES if self.lp[side] > 0]
        return 'empate' if not alive else alive[0] if len(alive) == 1 else None

    def claim_reward(self, config, pools, opponent, rank, grant, *, rng=None):
        if self.winner != 'jogador':
            raise ModError('Vença o duelo para receber uma recompensa.')
        if self.reward_card is not None:
            return self.reward_card
        if self._pending_reward is None:
            weights = drop_weights(config, pools, opponent, rank, effects=self.effects)
            self._pending_reward = weighted_choice(weights, rng or SystemRandom())
        grant(self._pending_reward)
        self.reward_card = self._pending_reward
        return self.reward_card

    def _require_turn(self, side):
        if self.active != side or self.winner:
            raise ModError('A ação exige um duelo aberto e o turno deste lado.')

    def _field(self, side):
        return [m for m in self.monsters if m['lado'] == side]

    def resolve(self):
        board, events = super().resolve()
        for monster in board:
            bonus = self.terrain_bonuses.get((self.terrain, monster['tipo_id']), 0)
            for stat in ('ataque', 'defesa'):
                monster[stat] = max(0, monster[stat] + bonus)
        return board, events

    def _notify_turn(self, side, event):
        for unit in list(self._field(side)):
            if unit.get('face_up', True) and self.get(side, unit['slot']) is unit:
                self.apply_event(unit['card_id'], side, event, source_slot=unit['slot'], strict=False)

    def _begin(self, side):
        self.active, self.played = side, False
        self.positions_used.clear()
        self.new_turn(side)
        self.draw(side, MAX_HAND)
        if not self.hands[side] and not self.decks[side] and not self._field(side):
            self.deck_out = side
        if not self.winner:
            self._notify_turn(side, 'inicio_turno')

    def end_turn(self, side):
        self._require_turn(side)
        self._notify_turn(side, 'fim_turno')
        self.swords[side] = max(0, self.swords[side] - 1)
        if not self.winner:
            self._begin(opposite(side))

    def _monsters_for(self, kind, hand, cid, slots, tribute=(), field_material=None):
        for slot, star, pose in product(slots, guardian_options(self.card(cid)), POSITIONS):
            yield Play(kind, hand, cid, slot, star, pose, field_material, tribute)
            # The original PS1 supports setting monsters face-down in attack or defense.
            yield Play(kind, hand, cid, slot, star, pose, field_material, tribute, face_up=False)

    def _spell_targets(self, cid, side):
        enemy = opposite(side)
        allies = self._field(side)
        rivals = self._field(enemy)
        effects = card_effects(self.effects, cid)
        scopes = {raw.get('alvo') for raw in effects if raw.get('evento') == 'invocar'
                  and raw.get('acao') in TARGETED_STATS | {'dano_monstro_alvo'}}
        if not scopes:
            return [None]
        candidates = []
        if scopes & {'proprio', 'monstro_alvo'}:
            candidates.extend((side, card['slot']) for card in allies)
        if scopes & {'inimigo', 'monstro_alvo'}:
            candidates.extend((enemy, card['slot']) for card in rivals)
        return candidates

    def _fusion_result(self, a, b):
        result = self.fusions.get(tuple(sorted((a, b))))
        if result in self.cards and int(self.card(result)['tipo_id']) in MONSTER_TYPES:
            return result
        return None

    def _fusion_chains(self, hand, material=None):
        """Explore ordered chains with at most five materials, including a field card."""
        limit = MAX_HAND - int(material is not None)
        pending = [((index,), cid) for index, cid in hand] if material is None else [((), material)]
        seen = {(frozenset(indices), result) for indices, result in pending}
        for indices, current in pending:
            if len(indices) >= limit:
                continue
            for index, cid in hand:
                if index in indices:
                    continue
                result = self._fusion_result(current, cid)
                if result is None:
                    continue
                chain = (*indices, index)
                key = frozenset(chain), result
                if key in seen:
                    continue
                seen.add(key)
                pending.append((chain, result))
                yield chain, result

    def legal_plays(self, side):
        if self.winner or self.active != side or self.played:
            return []
        own = self._field(side)
        occupied = {unit['slot'] for unit in own}
        free = [slot for slot in range(1, 6) if slot not in occupied]
        destinations = free[:1] or sorted(occupied)
        hand = self.hands[side]
        monsters = [(index, cid) for index, cid in enumerate(hand)
                    if int(self.card(cid)['tipo_id']) in MONSTER_TYPES]
        available = []
        for index, cid in enumerate(hand):
            kind = int(self.card(cid)['tipo_id'])
            cost = (index,)
            if kind in MONSTER_TYPES:
                available.extend(self._monsters_for('monstro', cost, cid, destinations))
            elif kind == 20:
                available.extend(Play('magia', cost, cid, target=target) for target in self._spell_targets(cid, side))
            elif kind == 21 and len(self.traps[side]) < 5:
                available.append(Play('armadilha', cost, cid))
            elif kind == 22 and cid in self.rituals:
                materials, result = self.rituals[cid]
                if result not in self.cards or int(self.card(result)['tipo_id']) not in MONSTER_TYPES:
                    continue
                for group in combinations(own, len(materials)):
                    if sorted(unit['card_id'] for unit in group) == sorted(materials):
                        tribute = tuple(unit['slot'] for unit in group)
                        available.extend(self._monsters_for('ritual', cost, result, [tribute[0]], tribute=tribute))
            elif kind == 23:
                targets = self.equips.get(cid)
                if targets is None and any(e['evento'] == 'equipado' for e in card_effects(self.effects, cid)):
                    targets = {unit['card_id'] for unit in own}
                available.extend(Play('equip', cost, cid, slot=unit['slot']) for unit in own
                                 if unit['card_id'] in (targets or ()))
        for indices, result in self._fusion_chains(monsters):
            available.extend(self._monsters_for('fusao', indices, result, destinations))
        for unit in own:
            slot = unit['slot']
            for indices, result in self._fusion_chains(monsters, unit['card_id']):
                available.extend(self._monsters_for('fusao', indices, result, [slot],
                                                    field_material=(side, slot)))
        return available

    def set_position(self, side, slot, position):
        self._require_turn(side)
        unit = self.get(side, slot)
        key = (side, slot, unit['card_id']) if unit else None
        if (position not in POSITIONS or unit is None or slot in self.positions_used
                or key in self.attacks_used):
            raise ModError('Este monstro não pode mudar de posição neste turno.')
        unit['posicao'] = position
        unit['face_up'] = True
        self.positions_used.add(slot)

    def play(self, side, action: Play):
        self._require_turn(side)
        if action not in self.legal_plays(side):
            raise ModError('Jogada indisponível para a mão e o campo atuais.')
        snapshot = self._snapshot()
        try:
            return self._execute_play(side, action)
        except (ModError, ValueError, TypeError, KeyError):
            self._restore(snapshot)
            raise

    def _execute_play(self, side, action):
        hand = self.hands[side]
        spent = [hand[i] for i in action.hand]
        for i in sorted(action.hand, reverse=True):
            del hand[i]
        self.played = True
        cid = action.card_id
        log = {'acao': action.kind, 'lado': side, 'carta': cid, 'slot': action.slot,
               'face_up': action.face_up and action.kind != 'armadilha'}
        if action.kind == 'fusao':
            log['etapas'] = len(spent) - int(action.target is None)
        self.logs.append(log)
        if action.kind == 'armadilha':
            self.traps[side].append(cid)
            self.apply_event(cid, side, 'invocar', kind='armadilha', strict=False)
        elif action.kind == 'equip':
            equip = {'lado': side, 'slot': action.slot, 'card_id': cid}
            self.equipments.append(equip)
            if cid in self.stock_equips:
                unit = self.get(side, action.slot)
                bonus = 1000 if cid == 657 else STOCK_EQUIP_BONUS
                resolved = next(m for m in self.resolve()[0] if (m['lado'], m['slot']) == (side, action.slot))
                if not resolved['imune_armadilha'] and self._counter_trap(opposite(side), 689):
                    bonus = -bonus
                for key in ('modificador_atk', 'modificador_def'):
                    unit[key] = unit.get(key, 0) + bonus
        elif action.kind == 'magia':
            self.graveyards[side].extend(spent)
            if self.stock_rules:
                self._stock_spell(side, cid)
            target_side, target_slot = action.target or (None, None)
            self.apply_event(cid, side, 'invocar', kind='magia', target_side=target_side,
                             target_slot=target_slot, strict=False)
        else:
            for slot in sorted(set((*action.tribute, action.slot))):
                super().remove(side, slot)
            if action.kind != 'monstro':
                self.graveyards[side].extend(spent)
            card = self.card(cid)
            self.monsters.append({'lado': side, 'slot': action.slot, 'card_id': cid,
                                  'tipo_id': int(card['tipo_id']), 'atributo_id': int(card.get('atributo_id', -1)),
                                  'ataque': int(card['ataque']), 'defesa': int(card['defesa']),
                                  'face_up': action.face_up, 'posicao': action.position,
                                  'guardian_id': action.star})
            self.positions_used.add(action.slot)
            self.apply_event(cid, side, 'invocar', source_slot=action.slot, strict=False)
        return log

    def _stock_spell(self, side, cid):
        enemy = opposite(side)
        if 330 <= cid <= 335:
            self.terrain = cid - 329
        elif cid in CURE_SPELLS:
            amount = CURE_SPELLS[cid]
            if self._counter_trap(enemy, 688):
                self.lp[side] = max(0, self.lp[side] - amount)
            else:
                self.lp[side] += amount
        elif cid in DAMAGE_SPELLS:
            receiver = side if self._counter_trap(enemy, 687) else enemy
            self.lp[receiver] = max(0, self.lp[receiver] - DAMAGE_SPELLS[cid])
        elif cid in (336, 337, 349, 350):
            for unit in list(self.resolve()[0]):
                if unit['imune_magia'] or (cid != 336 and unit['lado'] != enemy):
                    continue
                if cid in (336, 337) and not unit['indestrutivel']:
                    self.remove(unit['lado'], unit['slot'])
                elif cid == 349:
                    target = self.get(unit['lado'], unit['slot'])
                    if target is not None:
                        for key in ('modificador_atk', 'modificador_def'):
                            target[key] = target.get(key, 0) - 500
                elif cid == 350:
                    target = self.get(unit['lado'], unit['slot'])
                    if target is not None:
                        target['face_up'] = True
        elif cid == 348:
            self.swords[enemy] = 3

    def _counter_trap(self, side, cid):
        if cid not in self.traps[side]:
            return False
        self.traps[side].remove(cid)
        self.graveyards[side].append(cid)
        self.logs.append({'acao': 'armadilha_ativada', 'lado': side, 'carta': cid})
        return True

    def _attack_timing_error(self, attacker):
        if sum(self.turns.values()) == 1 and not attacker.get('ataque_primeiro_turno', False):
            return 'Só monstros com Ataca no 1º turno podem atacar na abertura do duelo.'
        return super()._attack_timing_error(attacker)

    def can_attack(self, side, slot, board):
        unit = next((m for m in board if (m['lado'], m['slot']) == (side, slot)), None)
        if unit is None:
            return False
        key = (side, slot, unit['card_id'])
        return (unit['posicao'] == 'ataque'
                and not self._attack_timing_error(unit)
                and self.attacks_used.get(key, 0) < unit['ataques_max']
                and (not self.swords[side] or unit['imune_magia']))

    def legal_attacks(self, side, board=None):
        if self.active != side or self.winner:
            return []
        board = self.resolve()[0] if board is None else board
        targets = [unit['slot'] for unit in board if unit['lado'] != side]
        actions = []
        for unit in board:
            slot = unit['slot']
            if unit['lado'] != side or not self.can_attack(side, slot, board):
                continue
            actions.extend(Attack(slot, target) for target in
                           ([None] if unit['nao_bloqueavel'] or not targets else targets))
        return actions

    def _attack_trap(self, side, slot):
        attacker = next(m for m in self.resolve()[0] if (m['lado'], m['slot']) == (side, slot))
        if attacker['imune_armadilha']:
            return
        defender = opposite(side)
        for index, cid in enumerate(self.traps[defender]):
            if cid in self.trap_limits:
                limit = self.trap_limits[cid]
                if attacker['indestrutivel'] or (limit is not None and attacker['ataque'] > limit):
                    continue
                self.remove(side, slot)
            elif any(effect['evento'] in ('atacar', 'defender') for effect in card_effects(self.effects, cid)):
                for event in ('atacar', 'defender'):
                    self.apply_event(cid, defender, event, kind='armadilha', target_side=side,
                                     target_slot=slot, strict=False)
            else:
                continue
            del self.traps[defender][index]
            self.graveyards[defender].append(cid)
            self.logs.append({'acao': 'armadilha_ativada', 'lado': defender, 'carta': cid})
            break

    def attack(self, side, slot, *, target_slot=None, against=None):
        self._require_turn(side)
        if Attack(slot, target_slot) not in self.legal_attacks(side):
            raise ModError('Ataque indisponível neste turno.')
        snapshot = self._snapshot()
        try:
            return self._execute_attack(side, Attack(slot, target_slot))
        except (ModError, ValueError, TypeError, KeyError):
            self._restore(snapshot)
            raise

    def _execute_attack(self, side, action):
        enemy = opposite(side)
        source = self.get(side, action.slot)
        target = self.get(enemy, action.target) if action.target else None
        # An attacking set monster reveals itself before attack triggers/combat.
        # This also enables Ataca no 1º turno while initially face-down in ATK.
        source['face_up'] = True
        starting = self.preview_attack(side, action.slot, target_slot=action.target, against=None)
        old_lp = dict(self.lp)
        self.apply_event(source['card_id'], side, 'atacar', source_slot=action.slot, target_side=enemy,
                         target_slot=action.target, strict=False)
        if self.get(side, action.slot) is not None and not self.winner:
            self._attack_trap(side, action.slot)
        if target is not None and self.get(enemy, action.target) is target and not self.winner:
            target['face_up'] = True
            self.apply_event(target['card_id'], enemy, 'defender', source_slot=action.target,
                             target_side=side, target_slot=action.slot, strict=False)
        if (self.get(side, action.slot) is None or self.winner or
                (action.target is not None and self.get(enemy, action.target) is None)):
            if self.get(side, action.slot) is not None:
                self.attacks_used[side, action.slot, source['card_id']] = starting['ataques_usados']
            self.lp[side] = max(0, self.lp[side] - starting['custo_lp'])
            result = {'acao': 'ataque', 'origem': (side, action.slot), 'alvo': starting['alvo'],
                      'dano_lp_jogador': max(0, old_lp[side] - self.lp[side]),
                      'dano_lp_oponente': max(0, old_lp[enemy] - self.lp[enemy]),
                      'destruidos': [(unit['lado'], unit['slot']) for unit in (source, target)
                                     if unit and self.get(unit['lado'], unit['slot']) is None],
                      'interrompido': True}
            self.logs.append(result)
            return result
        result = super().attack(side, action.slot, target_slot=action.target, against=None)
        if target is not None and (enemy, action.target) in result['destruidos'] and self.get(side, action.slot) is not None:
            self.apply_event(source['card_id'], side, 'destruir', source_slot=action.slot, strict=False)
        return result

    def remove(self, side, slot):
        unit = self.get(side, slot)
        removed = super().remove(side, slot)
        if removed and unit.get('face_up', True):
            self.apply_event(unit['card_id'], side, 'destruido', strict=False)
        return removed


def make_match(project, drafts, opponent, starter=STOCK_STARTER, *, rng=None, first='jogador'):
    cards = {cid: drafts.get_card(cid) if drafts else project.get(cid) for cid in project.cards}
    effects = {cid: drafts.get_effects(cid) if drafts else project.effects.get(str(cid), []) for cid in cards}
    config = normalize_rules(project.metadata.get(CONFIG_KEY, {}), cards)
    pools, stock_starter, equips, rituals = base_tables(project)
    stock_equips = set(equips)
    fusions, equips, rituals = match_recipes(project, equips, rituals)
    rng = rng or SystemRandom()
    profiles = config.get('iniciais', {})
    if starter is None:
        offered = {name: deck['peso'] for name, deck in profiles.items()
                   if deck['peso'] and (deck['cartas'] or deck['pools'])}
        starter = weighted_choice(offered, rng) if offered else STOCK_STARTER
    initial = ({'pools': config.get('pools_iniciais_ps1', stock_starter)} if starter == STOCK_STARTER
               else profiles.get(starter, {}))
    rival = duelist_profile(config, pools, opponent)
    copies = int(project.metadata.get('ps1_deck_global_limit', 3))
    decks = {side: deal_deck(profile, cards, effects, rng, default_copies=copies)
             for side, profile in zip(SIDES, (initial, rival))}
    base = project.folder / 'base' / 'source_SLUS_014.11'
    terrain = {}
    if base.is_file():
        from .ps1_native import read_terrain_boosts
        try:
            terrain.update(read_terrain_boosts(base.read_bytes()))
        except ModError:
            pass
    for key, value in project.metadata.get('ps1_terrain_boosts', {}).items():
        terrain[tuple(map(int, key.split(',')))] = int(value)
    return DuelMatch(cards, effects, decks, initial_lp=starting_life(project, opponent),
                     fusions=fusions, equips=equips, rituals=rituals, default_copies=copies,
                     rng=rng, first=first, stock_rules=any(cid <= CARD_COUNT and not card.get('virtual')
                                                     for cid, card in cards.items()),
                     trap_limits={int(key): int(value) for key, value in
                                  project.metadata.get('ps1_trap_thresholds', {}).items()},
                     terrain_bonuses=terrain, stock_equips=stock_equips)
