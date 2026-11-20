"""Presets de habilidades compartilhados pelo simulador e pela exportação PS1.

`sem_limite_deck` e `limite_copias_deck` controlam cópias por ID; o deck continua até 40.
Múltiplos ataques e imunidades são propriedades recalculadas do monstro em campo.
"""
from __future__ import annotations

QUICK_ACTIONS = frozenset({
    'ataques_multiplos', 'monstro_indestrutivel', 'monstro_imune_magia',
    'monstro_imune_armadilha', 'dano_perfurante', 'nao_bloqueavel',
    'perder_lp_por_ataque', 'sem_limite_deck', 'limite_copias_deck', 'ataque_primeiro_turno',
    'monstro_indestrutivel_batalha',
})
BOOLEAN_ACTIONS = (
    'monstro_indestrutivel', 'monstro_imune_magia', 'monstro_imune_armadilha',
    'dano_perfurante', 'nao_bloqueavel', 'sem_limite_deck', 'ataque_primeiro_turno',
    'monstro_indestrutivel_batalha',
)


def quick_settings(effects: list[dict], *, default_copies: int | None = 3) -> dict:
    data = {'ataques': 1, 'custo_lp': 0, 'limite_copias': default_copies,
            **{k:False for k in BOOLEAN_ACTIONS}}
    limits = []
    for effect in effects:
        action = effect.get('acao')
        if action == 'ataques_multiplos':
            data['ataques'] = max(data['ataques'], int(effect.get('valor',1)))
        elif action == 'perder_lp_por_ataque':
            data['custo_lp'] = int(effect.get('valor',0))
        elif action == 'limite_copias_deck':
            limits.append(int(effect.get('valor', 3)))
        elif action in BOOLEAN_ACTIONS:
            data[action] = True
    data['limite_copias'] = min(limits, default=default_copies)
    if data['limite_copias'] == 0:
        data['sem_limite_deck'] = False
    return data


def replace_quick_effects(existing: list[dict], settings: dict, *,
                          default_copies: int | None = 3) -> list[dict]:
    """Preserva efeitos manuais e substitui só os presets, sem duplicações."""
    from .core import check_effect, ModError
    try:
        attacks = int(settings.get('ataques', 1))
        lp = int(settings.get('custo_lp') or 0)
        raw_limit = settings.get('limite_copias')
        copy_limit = default_copies if raw_limit in ('', None) else int(raw_limit)
    except (ValueError, TypeError) as exc:
        raise ModError('Ataques e custo de LP precisam ser números inteiros') from exc
    if (attacks not in (1, 2, 3) or lp < 0
            or (copy_limit is not None and not 0 <= copy_limit <= 40)):
        raise ModError('Ataques: 1–3. LP: inteiro não negativo. Cópias por carta: 0–40.')
    result = [dict(e) for e in existing if e.get('acao') not in QUICK_ACTIONS]
    if attacks > 1:
        result.append(check_effect({'evento':'continuo','acao':'ataques_multiplos',
                                    'alvo':'proprio','valor':attacks}))
    unlimited = bool(settings.get('sem_limite_deck')) and copy_limit != 0
    for action in BOOLEAN_ACTIONS:
        enabled = unlimited if action == 'sem_limite_deck' else settings.get(action)
        if enabled:
            event = 'regra_deck' if action == 'sem_limite_deck' else 'continuo'
            result.append(check_effect({'evento':event,'acao':action,
                                        'alvo':'proprio','valor':0}))
    if not unlimited and copy_limit != default_copies:
        result.append(check_effect({'evento':'regra_deck','acao':'limite_copias_deck',
                                    'alvo':'proprio','valor':copy_limit}))
    if lp:
        result.append(check_effect({'evento':'atacar','acao':'perder_lp_por_ataque',
                                    'alvo':'proprio','valor':lp}))
    return result
