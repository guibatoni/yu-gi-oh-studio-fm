"""Sessão de edições pendentes: navegação nunca pede para salvar.

Dados ficam só na memória até salvar(). Em caso de erro de validação ou IO
nenhum rascunho é apagado. A imagem de PS1 permanece intocada.
"""
from __future__ import annotations
from .core import Project, FIELDS, NUMERIC, check_card_edit, check_effect, DEFAULT_NAME_COLOR, DEFAULT_RARITY


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



# Referência explícita para cartas cujo tipo pode ter sido alterado na ISO:
# Time Wizard #016 é Spellcaster no Forbidden Memories original.
# Nenhuma carta é alterada automaticamente na importação ou atualização.
RETAIL_TYPE_REFERENCES = {16: 1}


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
        """Para #016, a referência retail é independente da ISO modificada."""
        return RETAIL_TYPE_REFERENCES.get(cid,int(self.project.cards[cid]['tipo_id']))

    def restore_original_type(self, cid: int) -> None:
        """Restaura apenas o tipo alvo; mantém ATK/DEF e efeitos inalterados."""
        card=self.get_card(cid)
        card['tipo_id']=self.original_type_target(cid)
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

    def set_quick_abilities(self, cid: int, settings: dict) -> None:
        from .abilities import replace_quick_effects
        items = replace_quick_effects(self.get_effects(cid), settings)
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
