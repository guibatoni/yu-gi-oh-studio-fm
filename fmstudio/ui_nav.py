"""Modelo da navegação do Studio (sem Tkinter, testável).

Cada seção da barra lateral aponta para uma tela que já existe: uma aba do
notebook principal (``tab``) e, na Edição do Mod, também a sub-aba (``mod``).
As ações da busca rápida (Ctrl+K) chamam métodos que já existem no Studio.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    icon: str
    group: str
    tab: str                      # atributo do Studio com o frame do notebook principal
    mod: int | None = None        # índice da sub-aba da Edição do Mod
    library: bool = True          # mostra a biblioteca de cartas ao lado
    keywords: tuple[str, ...] = ()
    hint: str = ''


SECTIONS: tuple[Section, ...] = (
    Section('inicio', 'Início', '⌂', '', 'tab_home', library=False,
            keywords=('dashboard', 'painel', 'recentes', 'projetos'),
            hint='Projetos recentes, resumo e atalhos'),
    Section('cartas', 'Editor de cartas', '▤', 'Cartas', 'tab_cards',
            keywords=('carta', 'atk', 'def', 'nome', 'descrição', 'arte', 'imagem', 'raridade', 'tipo'),
            hint='Nome, tipo, ATK/DEF, atributo, raridade, arte e descrição'),
    Section('efeitos', 'Efeitos e bônus', '✦', 'Cartas', 'tab_effects',
            keywords=('efeito', 'bônus', 'habilidade', 'ícone', 'simular'),
            hint='Efeitos, bônus e habilidades da carta selecionada'),
    Section('fusoes', 'Fusões originais', '⚭', 'Cartas', 'tab_fusions',
            keywords=('fusão', 'fusões', 'ritual', 'equipamento'),
            hint='Fusões do jogo original para a carta selecionada'),
    Section('deck', 'Deck do oponente', '⚔', 'Oponentes', 'tab_mod', 0,
            keywords=('deck', 'oponente', 'duelista', 'npc', 'gerar deck'),
            hint='Deck de cada duelista, pools ponderados e geração'),
    Section('drops', 'Drops', '◈', 'Oponentes', 'tab_mod', 1,
            keywords=('drop', 'peso', 'rank', 'probabilidade', 'sa pow', 'bcd', 'tec'),
            hint='Pesos de drop por duelista e grupo de rank'),
    Section('iniciais', 'Decks iniciais', '▣', 'Oponentes', 'tab_mod', 2,
            keywords=('inicial', 'starter', 'perfil', 'deck inicial'),
            hint='Perfis de deck inicial do jogador'),
    Section('quests', 'Quests', '⚑', 'Oponentes', 'tab_mod', 4, library=False,
            keywords=('quest', 'missão', 'doação', 'requisito', 'frase'),
            hint='Requisitos e frases das quests de campanha'),
    Section('config', 'Configuração do MOD', '⚙', 'Mod PS1', 'tab_mod', 3, library=False,
            keywords=('lp', 'vida', 'ia', 'dificuldade', 'cartas por vitória', 'hud', 'config'),
            hint='LP, IA, cartas por vitória e opções gerais do MOD'),
    Section('magias', 'Mágicas e armadilhas', '✧', 'Mod PS1', 'tab_mod', 5, library=False,
            keywords=('mágica', 'magia', 'armadilha', 'trap', 'campo', 'terreno', 'cura', 'dano'),
            hint='Valores das mágicas, campos (terreno) e limiares das armadilhas'),
    Section('molduras', 'Molduras', '▢', 'Mod PS1', 'tab_mod', 6, library=False,
            keywords=('moldura', 'cor', 'raridade', 'frame'),
            hint='Cor da moldura das cartas por raridade'),
    Section('exportar', 'Exportar e gerar BIN', '⇪', 'Disco', 'tab_proj', library=False,
            keywords=('exportar', 'bin', 'cue', 'iso', 'gerar', 'validar', 'verificar', 'auditoria'),
            hint='Validação, exportação e geração da imagem BIN/CUE'),
    Section('extracao', 'Dados extraídos', '⛁', 'Disco', 'tab_extract', library=False,
            keywords=('extrair', 'extração', 'dados', 'relatório', 'slus'),
            hint='Extração completa de textos e imagens do disco'),
)
BY_KEY = {section.key: section for section in SECTIONS}


@dataclass(frozen=True)
class Action:
    label: str
    method: str
    shortcut: str = ''
    keywords: tuple[str, ...] = ()


ACTIONS: tuple[Action, ...] = (
    Action('Salvar projeto', 'save_project', 'Ctrl+S', ('salvar', 'gravar')),
    Action('Abrir projeto', 'open_project', 'Ctrl+O', ('abrir',)),
    Action('Novo projeto', 'new_project', 'Ctrl+N', ('criar', 'novo')),
    Action('Importar BIN/CUE', 'import_bin', '', ('importar', 'iso', 'disco')),
    Action('Importar CSVs', 'import_csv', '', ('importar', 'tabela')),
    Action('Extrair máximo do disco', 'extract_max', '', ('extrair',)),
    Action('Vincular SLUS', 'attach_slus', '', ('slus', 'executável')),
    Action('Gerar jogo BIN/CUE', 'build_disc', 'Ctrl+B', ('gerar', 'iso', 'compilar', 'build')),
    Action('Exportar alterações', 'export', '', ('exportar', 'csv')),
    Action('Verificar projeto', 'verify', '', ('validar', 'erros', 'verificar')),
    Action('Conferir BIN/CUE gerado', 'verify_disc', '', ('verificar', 'disco', 'conferir')),
    Action('Nova carta', 'add_new_card', '', ('criar carta', 'adicionar')),
    Action('Edição em lote das cartas selecionadas', 'open_bulk_edit', '', ('lote', 'várias', 'massa', 'batch')),
    Action('Passwords e baú', 'open_passwords', '', ('password', 'senha', 'baú')),
    Action('Verificar atualizações', 'check_updates', '', ('atualizar', 'versão')),
    Action('Mostrar/ocultar biblioteca de cartas', 'toggle_library', 'Ctrl+L', ('biblioteca', 'lista')),
    Action('Recolher/expandir barra lateral', 'toggle_sidebar', 'Ctrl+\\', ('menu', 'lateral')),
)


def fold(text: str) -> str:
    """minúsculas sem acento, para busca tolerante."""
    text = unicodedata.normalize('NFKD', text or '')
    return ''.join(ch for ch in text if not unicodedata.combining(ch)).lower().strip()


def _score(query: str, label: str, keywords: tuple[str, ...]) -> int:
    name = fold(label)
    if name.startswith(query):
        return 0
    if any(word.startswith(query) for word in name.split()):
        return 1
    if query in name:
        return 2
    if any(fold(word).startswith(query) for word in keywords):
        return 3
    if any(query in fold(word) for word in keywords):
        return 4
    return -1


def search(query: str) -> list[tuple[str, object]]:
    """[('secao', Section) | ('acao', Action)] na ordem de relevância."""
    query = fold(query)
    entries = [('secao', s, s.label, s.keywords + (s.hint,)) for s in SECTIONS]
    entries += [('acao', a, a.label, a.keywords) for a in ACTIONS]
    if not query:
        return [(kind, item) for kind, item, _, _ in entries]
    ranked = []
    for order, (kind, item, label, keywords) in enumerate(entries):
        score = _score(query, label, keywords)
        if score >= 0:
            ranked.append((score, order, kind, item))
    return [(kind, item) for _, _, kind, item in sorted(ranked)]


@dataclass
class History:
    """Voltar/avançar entre seções (Alt+← / Alt+→)."""
    limit: int = 50
    back: list[str] = field(default_factory=list)
    forward: list[str] = field(default_factory=list)
    current: str | None = None

    def visit(self, key: str) -> None:
        if key == self.current:
            return
        if self.current is not None:
            self.back.append(self.current)
            del self.back[:-self.limit]
        self.current = key
        self.forward.clear()

    def go_back(self) -> str | None:
        if not self.back:
            return None
        self.forward.append(self.current)
        self.current = self.back.pop()
        return self.current

    def go_forward(self) -> str | None:
        if not self.forward:
            return None
        self.back.append(self.current)
        self.current = self.forward.pop()
        return self.current


def section_for(tab: str, mod_index: int | None) -> str | None:
    """Seção correspondente a uma aba (para sincronizar a barra lateral)."""
    for section in SECTIONS:
        if section.tab == tab and (section.mod is None or section.mod == mod_index):
            return section.key
    return None
