"""Forbidden Memories rank projected from completed actions in a Studio duel."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

# Exclusive upper thresholds from the retail rank table. The last entry
# saturates the rule, including Studio LP and counts beyond retail values.
RANK_RULES = {
    'turnos': ((5, 12), (9, 8), (29, 0), (33, -8), (None, -12)),
    'ataques_efetivos': ((2, 4), (4, 2), (10, 0), (20, -2), (None, -4)),
    'vitorias_defensivas': ((2, 0), (6, -10), (10, -20), (15, -30), (None, -40)),
    'cartas_setadas': ((1, 0), (11, -2), (21, -4), (31, -6), (None, -8)),
    'fusoes': ((1, 4), (5, 0), (10, -4), (15, -8), (None, -12)),
    'equipamentos': ((1, 4), (5, 0), (10, -4), (15, -8), (None, -12)),
    'magias': ((1, 2), (4, -4), (7, -8), (10, -12), (None, -16)),
    'armadilhas': ((1, 2), (3, -8), (5, -16), (7, -24), (None, -32)),
    'cartas_compradas': ((9, 15), (13, 12), (33, 0), (37, -5), (None, -7)),
    'lp': ((100, -7), (1000, -5), (7000, 0), (8000, 4), (None, 6)),
}
PLAY_COUNTERS = {'equip': 'equipamentos', 'magia': 'magias', 'ritual': 'magias',
                 'armadilha_ativada': 'armadilhas'}


@dataclass(frozen=True)
class DuelRank:
    grade: str
    score: int
    counters: dict[str, int]


def rank_grade(score: int) -> str:
    score = min(99, max(0, score))
    return f'{"SABCDDCBAS"[score // 10]}-{"TEC" if score < 50 else "POW"}'


def project_rank(match, side='jogador') -> DuelRank:
    remaining = len(match.decks[side])
    counts = Counter(turnos=match.turns[side], lp=match.lp[side],
                     cartas_compradas=len(match.initial_decks[side]) - remaining,
                     cartas_restantes=remaining)
    for event in match.logs:
        action = event['acao']
        if action == 'ataque':
            origin = event['origem'][0]
            target = event['alvo']
            destroyed = event['destruidos']
            if origin == side:
                counts['ataques_diretos'] += target[0] == 'LP'
                counts['monstros_destruidos'] += sum(owner != side for owner, _ in destroyed)
                counts['ataques_efetivos'] += (
                    event.get('posicao') == 'ataque' and target in destroyed
                    and event['dano_lp_oponente'] > 0)
                counts['dano_batalha_sofrido'] += event['dano_lp_jogador']
            elif target[0] == side and event.get('posicao') == 'defesa':
                counts['vitorias_defensivas'] += (
                    target not in destroyed and event['atributos_alvo'][1] > event['atributos_atacante'][0])
                counts['dano_batalha_sofrido'] += event['dano_lp_oponente']
            elif target == ('LP', side) or target[0] == side:
                counts['dano_batalha_sofrido'] += event['dano_lp_oponente']
        elif event.get('lado') == side:
            if action in PLAY_COUNTERS:
                counts[PLAY_COUNTERS[action]] += 1
            if action == 'fusao':
                counts['fusoes'] += event.get('etapas', 1)
            counts['cartas_setadas'] += action in ('monstro', 'fusao', 'armadilha', 'ritual') and not event.get('face_up', True)
    # Direct attacks and damage matter through the winning condition and
    # remaining LP. Retail awards effective attacks for wins over ATK targets.
    adjustment = -40 if match.deck_out is not None and match.winner == side else 2
    score = 50 + adjustment + sum(
        next(points for threshold, points in bands if threshold is None or counts[key] < threshold)
        for key, bands in RANK_RULES.items()
    )
    score = min(99, max(0, score))
    return DuelRank(rank_grade(score), score, dict(counts))
