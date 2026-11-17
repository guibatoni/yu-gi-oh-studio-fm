"""Sessão de edições pendentes: navegação nunca pede para salvar.

Dados ficam só na memória até salvar(). Em caso de erro de validação ou IO
nenhum rascunho é apagado. A imagem de PS1 permanece intocada.
"""
from __future__ import annotations
from .core import (Project, FIELDS, NUMERIC, check_card_edit, check_effect, DEFAULT_NAME_COLOR,
                   DEFAULT_RARITY, ps1_supports_god24)
from .expanded import GOD_TYPE_ID
from .tables import CARD_COUNT


def same_card(a: dict, b: dict) -> bool:
    """Compara entradas do formulário sem exigir valores numéricos completos.

    Um campo temporariamente inválido (ex.: ATK vazio durante digitação)
    fica pendente e só é validado ao clicar Salvar projeto.
    """
    for k in FIELDS:
        x, y = a.get(k, ''), b.get(k, '')
        if k in NUMERIC:
            try:
                if int(str(x).strip()) != int(str(y).strip()):
                    return False
            except (ValueError, TypeError):
                return False
        elif k == 'cor_nome':
            if str(x).strip().upper() != str(y or DEFAULT_NAME_COLOR).strip().upper():
                return False
        elif str(x) != str(y):
            return False
    return True



class DraftSession:
    def __init__(self, project: Project):
        self.project = project
        self.cards: dict[int, dict] = {}
        self.effects: dict[int, list[dict]] = {}

    @property
    def is_dirty(self) -> bool:
        return bool(self.cards or self.effects)

    @property
    def count(self) -> int:
        return len(set(self.cards) | set(self.effects))

    def get_card(self, cid: int) -> dict:
        return dict(self.cards[cid]) if cid in self.cards else self.project.get(cid)

    def stage_card(self, cid: int, values: dict) -> None:
        baseline = self.project.get(cid)
        merged = dict(baseline)
        merged.update(values)
        if same_card(merged, baseline):
            self.cards.pop(cid, None)
        else:
            self.cards[cid] = merged

    def original_type_target(self, cid: int) -> int:
        """Retorna a classificação da ISO importada (sem forçar carta alguma)."""
        return int(self.project.cards[cid]['tipo_id'])

    def restore_original_type(self, cid: int) -> None:
        """Restaura manualmente o tipo importado, nunca na atualização."""
        card=self.get_card(cid)
        card['tipo_id']=self.original_type_target(cid)
        self.stage_card(cid,card)

    def choose_playable_monster_type(self, cid: int, typ: int,
                                     *, god_visual: bool=False) -> None:
        """Escolhe um tipo de monstro para a cópia PS1."""
        from .core import ModError
        if cid not in self.project.cards:
            raise ModError('Carta não encontrada no projeto.')
        supports_god = cid <= CARD_COUNT and ps1_supports_god24(self.project)
        if type(typ) is not int or not (0 <= typ < 20 or (typ == GOD_TYPE_ID and supports_god)):
            raise ModError('Escolha um tipo de monstro jogável no perfil PS1 do projeto.')
        card=self.get_card(cid)
        card['tipo_id']=typ
        if god_visual:
            card['raridade']='deus'
        self.stage_card(cid,card)

    def reset_card(self, cid: int) -> None:
        baseline = dict(self.project.cards[cid])
        baseline.setdefault('nome', '')
        baseline.setdefault('descricao', '')
        baseline.setdefault('cor_nome', DEFAULT_NAME_COLOR)
        baseline.setdefault('raridade', DEFAULT_RARITY)
        self.stage_card(cid, baseline)

    def get_effects(self, cid: int) -> list[dict]:
        return [dict(e) for e in self.effects.get(cid, self.project.effects.get(str(cid), []))]

    def _stage_effects(self, cid: int, entries: list[dict]):
        baseline = self.project.effects.get(str(cid), [])
        if entries == baseline:
            self.effects.pop(cid, None)
        else:
            self.effects[cid] = entries

    def add_effect(self, cid: int, entry: dict) -> None:
        items = self.get_effects(cid)
        items.append(check_effect(entry))
        self._stage_effects(cid, items)

    def set_quick_abilities(self, cid: int, settings: dict, *, default_copies: int | None = 3) -> None:
        from .abilities import replace_quick_effects
        items = replace_quick_effects(self.get_effects(cid), settings, default_copies=default_copies)
        self._stage_effects(cid, items)

    def replace_effect(self, cid: int, index: int, entry: dict) -> None:
        """Atualiza exatamente uma regra, sem salvar o projeto ou duplicar efeitos."""
        from .core import ModError
        if cid not in self.project.cards:
            raise ModError('Carta não carregada')
        items = self.get_effects(cid)
        if type(index) is not int or not 0 <= index < len(items):
            raise ModError('Selecione um efeito existente para editar.')
        validated = check_effect(entry)  # inválido não altera nenhum rascunho
        items[index] = validated
        self._stage_effects(cid, items)

    def remove_effect(self, cid: int, index: int) -> None:
        items = self.get_effects(cid)
        items.pop(index)
        self._stage_effects(cid, items)

    def simulate(self, cid: int, event: str):
        data = check_card_edit(self.get_card(cid))
        return self.project.simulate(cid, event, card_override=data,
                                     effects_override=self.get_effects(cid))

    def simulate_field(self, monsters: list[dict], *, deck_types=None, equipments=None):
        ids = {m['card_id'] for m in monsters}
        effects = {str(cid): self.get_effects(cid) for cid in ids}
        return self.project.simulate_field(monsters, effects_override=effects,
                                           deck_types=deck_types, equipments=equipments)

    def save(self) -> int:
        if not self.is_dirty:
            return 0
        count = self.count
        # apply_many valida antes de escrever. Se falhar, mantém todos os rascunhos.
        self.project.apply_many(self.cards, self.effects)
        self.cards.clear()
        self.effects.clear()
        return count
