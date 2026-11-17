"""Tactical search over public board information and the adversary's own hand."""
from __future__ import annotations

from .core import ModError
from .guardian import guardian_bonuses
from .mod_data import MONSTER_TYPES, opposite


def posture(match, side):
    rival = opposite(side)
    own, enemies = match._field(side), match._field(rival)
    if (match.lp[side] < match.lp[rival] and len(own) <= len(enemies)) or len(own) + 1 < len(enemies):
        return 'defensiva'
    if len(own) > len(enemies) or match.lp[side] > match.lp[rival]:
        return 'agressiva'
    return 'estratégica'


def _public_view(match, side):
    enemy = opposite(side)
    view = match.fork()
    # Keep only the counts of the rival's hidden zones. Estimation uses the
    # public catalog, never the identity or order of the cards in those zones.
    placeholder = max(view.cards, default=0) + 1
    view.cards = {**view.cards, placeholder: {'tipo_id': -1, 'atributo_id': -1, 'ataque': 0, 'defesa': 0}}
    view.hands[enemy] = [placeholder] * len(view.hands[enemy])
    view.decks[enemy] = [placeholder] * len(view.decks[enemy])
    view.initial_decks[enemy] = (placeholder,) * len(view.initial_decks[enemy])
    view.traps[enemy] = []
    hidden = [unit for unit in view._field(enemy) if not unit.get('face_up', True)]
    if hidden:
        defenses = sorted(int(card['defesa']) for card in view.cards.values()
                          if int(card['tipo_id']) in MONSTER_TYPES)
        uncertainty = defenses[3 * len(defenses)//4] if defenses else 0
        hidden_slots = {unit['slot'] for unit in hidden}
        view.equipments = [e for e in view.equipments
                           if e['lado'] != enemy or e['slot'] not in hidden_slots]
        for unit in hidden:
            unit.update(card_id=placeholder, tipo_id=31, atributo_id=-1,
                        ataque=0, defesa=uncertainty, guardian_id=0,
                        modificador_atk=0, modificador_def=0)
    # A unit's displayed ATK/DEF is public even when one of its effects
    # depends on a hidden zone. Preserve those displayed values in forecasts.
    real_board = {(m['lado'], m['slot']): m for m in match.resolve()[0] if m['face_up']}
    for unit in view.resolve()[0]:
        key = unit['lado'], unit['slot']
        if key in real_board:
            raw = view.get(*key)
            for stat, label in (('ataque', 'atk'), ('defesa', 'def')):
                modifier = 'modificador_' + label
                raw[modifier] = raw.get(modifier, 0) + real_board[key][stat] - unit[stat]
    return view


def _field_value(game, board, side, stance):
    own = [unit for unit in board if unit['lado'] == side]
    rivals = [unit for unit in board if unit['lado'] != side and unit['face_up']]
    total = 1300 * len(own)
    for unit in own:
        stat = 'defesa' if unit['posicao'] == 'defesa' else 'ataque'
        strength = unit[stat]
        total += strength * (4 if stat == 'defesa' and stance == 'defensiva' else
                             4 if stat == 'ataque' else 2)
        total += 500 * (unit['imune_magia'] + unit['imune_armadilha'] + unit['indestrutivel'])
        if not rivals and stat == 'ataque':
            total += strength
        for rival in rivals:
            own_star, enemy_star = guardian_bonuses(unit['guardian_id'], rival['guardian_id'])
            own_power = max(0, strength + own_star)
            threat = max(0, rival['ataque'] + enemy_star)
            if not unit['indestrutivel'] and threat > own_power:
                total -= (threat - own_power) * (3 if stance == 'defensiva' else 2)
            if stat == 'ataque':
                defense = max(0, rival[rival['posicao']] + enemy_star)
                if not rival['indestrutivel'] and own_power > defense:
                    total += 900 + min(own_power - defense, game.lp[opposite(side)])
            total += own_star - enemy_star
    return total


def _fusion_potential(game, side):
    hand = game.hands[side]
    field = [unit['card_id'] for unit in game._field(side)]
    remaining = set(game.decks[side])
    scores = {}

    def power(cid):
        if cid not in scores:
            scores[cid] = game.effective_card(side, cid)['ataque']
        return scores[cid]

    highest = 0
    for index, cid in enumerate(hand):
        present = set(hand[index+1:]) | set(field)
        for material in present | remaining:
            result = game._fusion_result(cid, material)
            if result:
                gain = power(result) - max(power(cid), power(material))
                highest = max(highest, gain if material in present else gain // 3)
    return highest


def _direct_followup(game, side):
    if game._field(opposite(side)) or game.winner:
        return 0
    points = 0
    board = game.resolve()[0]
    for action in game.legal_attacks(side, board):
        if action.target is not None:
            continue
        preview = game.preview_attack(side, action.slot, against=None, board=board)
        remaining = preview['ataques_max'] - preview['ataques_usados'] + 1
        if preview['custo_lp'] and preview['custo_lp'] * remaining >= game.lp[side]:
            remaining = (game.lp[side] - 1) // preview['custo_lp']
        points += preview['atributos_atacante'][0] * remaining
    return points


def _rank_attack(view, side, action, stance):
    enemy = opposite(side)
    ours, theirs = view._field(side), view._field(enemy)
    branch = view.fork()
    try:
        result = branch._execute_attack(side, action)
    except (ModError, ValueError, TypeError, KeyError):
        return None
    if branch.winner == side:
        return (3, 0, view.lp[enemy]), action
    if branch.winner:
        return None
    own_loss = len(ours) - len(branch._field(side))
    enemy_loss = len(theirs) - len(branch._field(enemy))
    paid = view.lp[side] - branch.lp[side]
    dealt = view.lp[enemy] - branch.lp[enemy]
    follow = _direct_followup(branch, side)
    trade = (own_loss == enemy_loss == 1 and result.get('posicao') == 'ataque'
             and result.get('atributos_alvo') and result['atributos_atacante'][0] == result['atributos_alvo'][0])
    if trade and len(ours) == 2 and len(theirs) == 1 and follow > 0:
        return (2, follow, -paid), action
    if trade and len(ours) == len(theirs) == 1:
        parity = len(branch.hands[side]) >= len(branch.hands[enemy])
        reserve = len(branch.decks[side]) >= len(branch.decks[enemy])
        if ((branch.lp[side] >= branch.lp[enemy] and (parity or reserve))
                or (parity and not reserve and stance == 'defensiva')):
            return (1, 1, -paid), action
        return None
    if own_loss or (paid > dealt and enemy_loss == 0):
        return None
    if not enemy_loss and dealt <= 0:
        return None
    if follow >= branch.lp[enemy] > 0:
        return (2, 0, follow), action
    score = enemy_loss * 1800 + dealt * 3 - paid * (4 if stance == 'defensiva' else 2)
    return ((1, 0, score), action) if score > 0 else None


def _preferred_attack(view, side, stance):
    options = [ranked for action in view.legal_attacks(side)
               if (ranked := _rank_attack(view, side, action, stance)) is not None]
    return max(options, key=lambda option: option[0], default=None)


def choose_attack(match, side='adversario'):
    candidate = _preferred_attack(_public_view(match, side), side, posture(match, side))
    return candidate[1] if candidate else None



def _prefer_safe_guardian_stars(actions, visible_rivals):
    """Compare only alternatives for the *same* move, using public Guardian Stars.

    No star can be completely safe against every visible monster in some
    multi-monster boards. In those cases, minimize the number of matchups
    where the rival receives the Guardian bonus, then favor more advantages.
    Never inspect face-down enemies: their identities and stars are private.
    """
    stars = tuple(int(unit['guardian_id']) for unit in visible_rivals
                  if unit.get('face_up', True))
    if not stars:
        return actions

    def identity(action):
        return (action.kind, action.hand, action.card_id, action.slot,
                action.position, action.target, action.tribute, action.face_up)

    def risk(action):
        matchups = [guardian_bonuses(action.star, rival_star) for rival_star in stars]
        return (sum(enemy_bonus > 0 for _, enemy_bonus in matchups),
                sum(enemy_bonus for _, enemy_bonus in matchups),
                -sum(own_bonus for own_bonus, _ in matchups))

    best_risk = {}
    for action in actions:
        if action.kind not in ('monstro', 'fusao', 'ritual'):
            continue
        key, value = identity(action), risk(action)
        if key not in best_risk or value < best_risk[key]:
            best_risk[key] = value
    return [action for action in actions
            if action.kind not in ('monstro', 'fusao', 'ritual')
            or risk(action) == best_risk[identity(action)]]


def choose_play(match, side='adversario'):
    options = match.legal_plays(side)
    if not options:
        return None
    stance = posture(match, side)
    enemy = opposite(side)
    view = _public_view(match, side)
    # Refuse a losing Guardian Star when this move offers a safer star.
    # The public view masks face-down monsters before evaluating the choice.
    options = _prefer_safe_guardian_stars(options, view._field(enemy))
    base = view.resolve()[0]
    field_score = _field_value(view, base, side, stance) - _field_value(view, base, enemy, 'estratégica')
    held_fusion = _fusion_potential(view, side)
    baseline = _preferred_attack(view, side, stance)
    baseline_win = baseline and baseline[0][0] == 3
    best = None
    defensive_fallback = None
    no_monsters = not view._field(side)
    for action in options:
        branch = view.fork()
        try:
            branch._execute_play(side, action)
            board = branch.resolve()[0]
        except (ModError, ValueError, KeyError, TypeError):
            continue
        if branch.winner == side:
            return action
        if branch.winner:
            continue
        pressure = _preferred_attack(branch, side, stance)
        if baseline_win and not (pressure and pressure[0][0] == 3):
            continue
        score = (_field_value(branch, board, side, stance)
                 - _field_value(branch, board, enemy, 'estratégica') - field_score)
        score += (branch.lp[side] - view.lp[side]) * (4 if stance == 'defensiva' else 2)
        score += (view.lp[enemy] - branch.lp[enemy]) * (4 if stance == 'agressiva' else 3)
        score += (len(view.hands[enemy]) - len(branch.hands[enemy])) * 500
        score += (_fusion_potential(branch, side) - held_fusion) // 2
        score -= len(action.hand) * (350 if stance == 'defensiva' else 200)
        if action.kind == 'armadilha':
            card = action.card_id
            known = (card in branch.trap_limits or
                     any(e['evento'] in ('atacar', 'defender') for e in branch.effects.get(card, branch.effects.get(str(card), ())))
                     or branch.stock_rules and card in (687, 688, 689, 690))
            if known:
                score += 1300 if stance == 'defensiva' else 550
        win = bool(pressure and pressure[0][0] == 3)
        attack_value = pressure[0][2] if pressure else 0
        if pressure and not baseline and not win:
            score += max(0, attack_value)
        key = (win, score, attack_value)
        if (win or score > 0) and (best is None or key > best[0]):
            best = key, action
        # Uma IA sem monstros não deve simplesmente passar a vez porque
        # as unidades inimigas têm poder muito maior: estabelecer defesa
        # preserva a chance de sobreviver e comprar/fundir no turno seguinte.
        # Só monstros normais em defesa (sem consumir material de fusão).
        if no_monsters and action.kind == 'monstro' and action.position == 'defesa':
            unit = next((unit for unit in board
                         if unit['lado'] == side and unit['slot'] == action.slot), None)
            if unit is not None:
                choice = (unit['defesa'], int(not action.face_up), score)
                if defensive_fallback is None or choice > defensive_fallback[0]:
                    defensive_fallback = choice, action
    return best[1] if best else defensive_fallback[1] if defensive_fallback else None


def _reposition(match, side):
    stance = posture(match, side)
    view = _public_view(match, side)
    before = view.resolve()[0]
    baseline = _field_value(view, before, side, stance)
    old_attack = _preferred_attack(view, side, stance)
    for unit in before:
        if unit['lado'] != side:
            continue
        slot, current = unit['slot'], unit['posicao']
        new = 'ataque' if current == 'defesa' else 'defesa'
        branch = view.fork()
        try:
            branch.set_position(side, slot, new)
        except ModError:
            continue
        candidate = _preferred_attack(branch, side, stance)
        improvement = _field_value(branch, branch.resolve()[0], side, stance) > baseline
        if new == 'ataque' and candidate and (not old_attack or candidate[0] > old_attack[0]):
            match.set_position(side, slot, new)
            return True
        if new == 'defesa' and not old_attack and improvement and stance == 'defensiva':
            match.set_position(side, slot, new)
            return True
    return False


def play_ai_turn(match, side='adversario'):
    """Use the same public actions available to a human and hand off the turn."""
    match._require_turn(side)
    start = len(match.logs)
    opening = _preferred_attack(_public_view(match, side), side, posture(match, side))
    if opening and opening[0][0] >= 2:
        _, action = opening
        match.attack(side, action.slot, target_slot=action.target)
    if not match.winner:
        action = choose_play(match, side)
        if action is not None:
            match.play(side, action)
    while not match.winner:
        action = choose_attack(match, side)
        if action is not None:
            match.attack(side, action.slot, target_slot=action.target)
        elif not _reposition(match, side):
            break
    if not match.winner:
        match.end_turn(side)
    return match.logs[start:]
