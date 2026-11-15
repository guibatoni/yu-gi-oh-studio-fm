"""Presets simples de habilidades; definição somente para simulador, não ROM PS1.

`sem_limite_deck` e `limite_copias_deck` controlam cópias por ID; o deck continua até 40.
Múltiplos ataques e imunidades são propriedades recalculadas do monstro em campo.
"""
from __future__ import annotations

QUICK_ACTIONS = frozenset({
    'ataques_multiplos', 'monstro_indestrutivel', 'monstro_imune_magia',
    'monstro_imune_armadilha', 'dano_perfurante', 'nao_bloqueavel',
    'perder_lp_por_ataque', 'sem_limite_deck', 'limite_copias_deck', 'ataque_primeiro_turno',
})
BOOLEAN_ACTIONS = (
    'monstro_indestrutivel', 'monstro_imune_magia', 'monstro_imune_armadilha',
    'dano_perfurante', 'nao_bloqueavel', 'sem_limite_deck', 'ataque_primeiro_turno',
)


def quick_settings(effects: list[dict]) -> dict:
    data = {'ataques': 1, 'custo_lp': 0, 'limite_copias': 3, **{k:False for k in BOOLEAN_ACTIONS}}
    for effect in effects:
        action = effect.get('acao')
        if action == 'ataques_multiplos':
            data['ataques'] = max(data['ataques'], int(effect.get('valor',1)))
        elif action == 'perder_lp_por_ataque':
            data['custo_lp'] = int(effect.get('valor',0))
        elif action == 'limite_copias_deck':
            data['limite_copias'] = int(effect.get('valor',3))
        elif action in BOOLEAN_ACTIONS:
            data[action] = True
    return data


def replace_quick_effects(existing: list[dict], settings: dict) -> list[dict]:
    """Preserva efeitos manuais e substitui só os presets, sem duplicações."""
    from .core import check_effect, ModError
    try:
        attacks = int(settings.get('ataques', 1))
        lp = int(settings.get('custo_lp') or 0)
        copy_limit = int(settings.get('limite_copias',3) or 0)
    except (ValueError, TypeError) as exc:
        raise ModError('Ataques e custo de LP precisam ser números inteiros') from exc
    if attacks not in (1, 2, 3) or not 0 <= lp <= 9999 or not 1 <= copy_limit <= 40:
        raise ModError('Ataques: 1–3; LP: 0–9999; cópias por carta: 1–40')
    result = [dict(e) for e in existing if e.get('acao') not in QUICK_ACTIONS]
    if attacks > 1:
        result.append(check_effect({'evento':'continuo','acao':'ataques_multiplos',
                                    'alvo':'proprio','valor':attacks}))
    for action in BOOLEAN_ACTIONS:
        if settings.get(action, False):
            event = 'regra_deck' if action == 'sem_limite_deck' else 'continuo'
            result.append(check_effect({'evento':event,'acao':action,
                                        'alvo':'proprio','valor':0}))
    if not settings.get('sem_limite_deck', False) and copy_limit != 3:
        result.append(check_effect({'evento':'regra_deck','acao':'limite_copias_deck',
                                    'alvo':'proprio','valor':copy_limit}))
    if lp:
        result.append(check_effect({'evento':'atacar','acao':'perder_lp_por_ataque',
                                    'alvo':'proprio','valor':lp}))
    return result
