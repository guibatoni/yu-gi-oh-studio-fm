"""Tkinter editors for mod distributions and Studio card relations."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from fractions import Fraction
from math import gcd
from pathlib import Path
import re
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .core import ModError, positive_int, ps1_supports_god24, simulation_nonnegative_int
from .duel_engine import MAX_DECK, parse_card_ids
from .expanded import card_matches, display_name, search_text
from .gui import ACCENT, MUTED, ROW_ALT, WARNING, card_row_tags, compact_number, sortable_columns
from .mod_data import (
    CONFIG_KEY, DROP_FROM_DECK, DECK_DROP_WEIGHTS, DROP_GROUPS, MONSTER_TYPES,
    RANK_GROUPS, STOCK_STARTER, base_tables, deal_deck, deck_drop_candidates,
    deck_drop_weights, drop_weights, drops_from_deck, duelist_profile, match_recipes,
    FIXED_DROP, fixed_drop,
    normalize_rules, save_rules, starting_life, validate_deck,
)
from .tables import CARD_COUNT, DUELIST_NAMES_REFERENCE, POOL_TOTAL, TYPE_NAMES
from .card_search import ALL_STARS, STAR_FILTERS, has_star, star_label
from .card_picker import FUSION_NONE, FusionFilter
from .original_opponent_decks import (
    original_opponent_profile, original_deck_summary, is_original_deck, restored_rules,
)

FIXED_DROP_NONE = '— nenhum —'
WEIGHT_COLUMNS = ('carta', 'nome', 'atk', 'def', 'peso', 'chance', 'chance_ps1')


def _monster_stat(card, stat):
    """Mostrar valores base apenas para monstros (incluindo Deus, tipo 24)."""
    if not card or int(card.get('tipo_id', -1)) not in MONSTER_TYPES:
        return '—'
    value = card.get(stat)
    return str(value) if value is not None and str(value).strip() else '—'


def _monster_stat_sort(card, stat):
    value = _monster_stat(card, stat)
    return int(value) if value != '—' else -1


def _probability(weight, total):
    value = weight * 1_000_000 // total if total else 0
    return f'{value//10000},{value%10000:04d}%'


class WeightTable(ttk.Frame):
    """Pick cards by name or ID and inspect normalized odds for a weight table."""
    def __init__(self, parent, *, show_zero=False):
        super().__init__(parent)
        self.show_zero = show_zero
        self.ps1_projection = False
        self.ps1_weights = ()
        self.cards = {}
        self.labels = {}
        self.weights = {}
        self.changed = None
        self.inline = None
        self.query = tk.StringVar()
        search = ttk.Frame(self)
        search.pack(fill='x', pady=(0, 5))
        ttk.Label(search, text='Filtrar lista').pack(side='left', padx=(0, 5))
        ttk.Entry(search, textvariable=self.query).pack(side='left', fill='x', expand=True)
        ttk.Button(search, text='Selecionar visíveis',
                   command=self._select_visible).pack(side='right', padx=(7, 0))
        ttk.Label(self, text='Selecione várias cartas com Ctrl/Shift ou informe IDs separados por vírgula.',
                  foreground=MUTED).pack(anchor='w')
        edit = ttk.Frame(self)
        edit.pack(fill='x', pady=(0, 5))
        self.selected = tk.StringVar()
        self.card = ttk.Combobox(edit, textvariable=self.selected, width=28)
        self.card.pack(side='left', fill='x', expand=True)
        ttk.Button(edit, text='Procurar…', command=self._browse).pack(side='left', padx=(4, 0))
        self.card.bind('<KeyRelease>', self._search)
        self.card.bind('<Return>', lambda _event: self._apply())
        self.weight = tk.StringVar(value='1')
        ttk.Label(edit, text='Peso').pack(side='left', padx=(7, 3))
        weight = ttk.Entry(edit, textvariable=self.weight, width=8)
        weight.pack(side='left', padx=(0, 4))
        weight.bind('<Return>', lambda _event: self._apply())
        ttk.Button(edit, text='Aplicar peso', command=self._apply).pack(side='left')
        ttk.Button(edit, text='Remover selecionadas', style='Danger.TButton',
                   command=self._remove).pack(side='left', padx=(4, 0))
        holder = ttk.Frame(self)
        holder.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(holder, columns=WEIGHT_COLUMNS, displaycolumns=WEIGHT_COLUMNS[:-1],
                                 show='headings', selectmode='extended', height=6)
        widths = (58, 170, 78, 78, 70, 105, 100)
        for key, label, width in zip(
            WEIGHT_COLUMNS, ('ID', 'Carta', 'ATK', 'DEF', 'Peso', 'Chance', 'Chance PS1'), widths
        ):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=55, stretch=key == 'nome',
                             anchor='e' if key in ('atk', 'def', 'peso', 'chance', 'chance_ps1') else 'w')
        self.sort_rows = sortable_columns(self.tree, raw_values=self._sort_value)
        hscroll = ttk.Scrollbar(holder, orient='horizontal', command=self.tree.xview)
        hscroll.pack(side='bottom', fill='x')
        self.tree.configure(xscrollcommand=hscroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(holder, command=self.tree.yview)
        scroll.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>', self._select)
        self.tree.bind('<Double-1>', self._edit_weight)
        self.tree.bind('<Delete>', lambda _event: self._remove())
        self.tree.bind('<Control-a>', self._select_visible)
        self.tree.bind('<Button-3>', self._context_menu)
        from .ui_theme import menu as themed_menu
        self.menu = themed_menu(self)
        self.menu.add_command(label='Aplicar o peso digitado às selecionadas', command=self._apply)
        self.menu.add_command(label='Multiplicar pesos das selecionadas…', command=self._multiply)
        self.menu.add_command(label='Remover selecionadas', accelerator='Delete', command=self._remove)
        self.menu.add_separator()
        self.menu.add_command(label='Selecionar visíveis', accelerator='Ctrl+A', command=self._select_visible)
        self.summary = ttk.Label(self, foreground=MUTED)
        self.summary.pack(anchor='w', pady=(3, 0))
        self.query.trace_add('write', lambda *_: self.render())

    def _sort_value(self, item, field):
        cid = int(item)
        if field in ('peso', 'chance'):
            return self.weights.get(cid, 0)
        if field == 'chance_ps1':
            return self._ps1_weight(cid)
        if field in ('atk', 'def'):
            return _monster_stat_sort(self.cards.get(cid), 'ataque' if field == 'atk' else 'defesa')
        return cid if field == 'carta' else display_name(cid, self.cards)

    def _ps1_weight(self, cid):
        return self.ps1_weights[cid - 1] if 1 <= cid <= len(self.ps1_weights) else 0

    def refresh_catalog(self, cards):
        self.cards = cards
        self.labels = {f'#{cid} — {display_name(cid, cards)}': cid for cid in sorted(cards)}
        self._search()
        self.render()

    def load(self, cards, weights):
        self.selected.set('')
        self.weights = {int(cid): int(value) for cid, value in weights.items() if int(value)}
        self.refresh_catalog(cards)

    def render(self):
        self._close_inline()
        keep = self.tree.selection()
        top = self.tree.yview()[0]
        self.tree.delete(*self.tree.get_children())
        total = sum(self.weights.values())
        self.ps1_weights = ()
        if self.ps1_projection and total:
            from .ps1_mod import quantize_weights
            try:
                self.ps1_weights = quantize_weights(self.weights, CARD_COUNT)
            except ModError:
                pass
        self.tree.configure(displaycolumns=WEIGHT_COLUMNS if self.ps1_projection else WEIGHT_COLUMNS[:-1])
        self.tree.tag_configure('stripe', background=ROW_ALT)
        rows = ((cid, self.weights.get(cid, 0)) for cid in sorted(self.cards)) if self.show_zero else sorted(self.weights.items())
        query = search_text(self.query.get())
        rows = ((cid, weight) for cid, weight in rows if cid in self.cards and card_matches(query, cid, self.cards[cid]))
        for index, (cid, weight) in enumerate(rows):
            self.tree.insert('', 'end', iid=str(cid), values=(
                compact_number(cid), display_name(cid, self.cards),
                _monster_stat(self.cards[cid], 'ataque'),
                _monster_stat(self.cards[cid], 'defesa'), compact_number(weight),
                _probability(weight, total),
                _probability(self._ps1_weight(cid), POOL_TOTAL) if self.ps1_weights else '—'),
                tags=card_row_tags(self.tree, self.cards.get(cid), index))
        self.sort_rows()
        valid = [item for item in keep if self.tree.exists(item)]
        if valid:
            self.tree.selection_set(valid)
        self.tree.yview_moveto(top)
        count = len(self.tree.selection())
        suffix = f' · {count} selecionadas' if count > 1 else ''
        self.summary.configure(text=(
            f'{len(self.weights)} cartas com peso · peso total {compact_number(total)}{suffix}'))

    def _search(self, _event=None):
        query = search_text(self.selected.get()).strip()
        self.card.configure(values=[label for label, cid in self.labels.items()
                                    if card_matches(query, cid, self.cards[cid])])

    def _select(self, _event):
        selection = self.tree.selection()
        if len(selection) == 1 and int(selection[0]) in self.cards:
            cid = int(selection[0])
            self.selected.set(f'#{cid} — {display_name(cid, self.cards)}')
            self.weight.set(str(self.weights.get(cid, 0)))
        elif len(selection) > 1:
            self.selected.set('')
        total = sum(self.weights.values())
        chosen = sum(self.weights.get(int(cid), 0) for cid in selection if cid.isdigit())
        self.summary.configure(text=(
            f'{len(self.weights)} cartas com peso · peso total {compact_number(total)}'
            + (f' · {len(selection)} selecionadas = {_probability(chosen, total)} de chance somada'
               if len(selection) > 1 else '')))

    def _select_visible(self, _event=None):
        visible = self.tree.get_children()
        self.tree.selection_set(visible)
        self._select(None)
        if visible:
            self.tree.focus(visible[0])
            self.tree.focus_set()
        return 'break'

    def _apply(self):
        try:
            raw = self.selected.get().strip()
            amount = simulation_nonnegative_int(self.weight.get(), 'Peso')
            if len(self.tree.selection()) > 1:
                ids = [int(cid) for cid in self.tree.selection()]
            elif raw in self.labels:
                ids = [self.labels[raw]]
            elif re.fullmatch(r'#?[0-9]+(?:[\s,]+#?[0-9]+)*', raw):
                ids = [positive_int(part.removeprefix('#'), 'Carta') for part in re.split(r'[\s,]+', raw)]
            else:
                query = search_text(raw)
                ids = [cid for cid, card in self.cards.items() if query and card_matches(query, cid, card)]
                if len(ids) != 1:
                    raise ModError('Selecione uma carta na busca ou informe IDs separados por vírgula.')
            if any(cid not in self.cards for cid in ids):
                raise ModError('O lote contém uma carta fora do catálogo desta tabela.')
            self._update_weights(dict.fromkeys(ids, amount))
        except (ModError, OSError, ValueError) as exc:
            messagebox.showerror('Tabela de pesos', str(exc), parent=self)

    def _browse(self):
        """Escolher uma ou várias cartas na lista com filtros e aplicar o peso digitado."""
        from .card_picker import CardPickerDialog

        def picked(ids):
            try:
                amount = simulation_nonnegative_int(self.weight.get(), 'Peso') or 1
                self._update_weights(dict.fromkeys(ids, amount))
                for cid in ids:
                    if self.tree.exists(str(cid)):
                        self.tree.see(str(cid))
                self.tree.selection_set([str(cid) for cid in ids if self.tree.exists(str(cid))])
            except (ModError, OSError, ValueError) as exc:
                messagebox.showerror('Tabela de pesos', str(exc), parent=self)
        context = getattr(self, 'picker_context', None)
        fusions, deck = context() if context else (None, None)
        if deck is not None:
            deck = set(deck) | {cid for cid, weight in self.weights.items() if weight}
        CardPickerDialog(self, self.cards, picked, multiple=True, fusions=fusions, deck_ids=deck,
                         title='Adicionar cartas à tabela', confirm=f'Adicionar com o peso digitado')

    def _context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item and item not in self.tree.selection():
            self.tree.selection_set(item)
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _multiply(self):
        from tkinter import simpledialog
        selection = [int(cid) for cid in self.tree.selection()]
        if not selection:
            return
        factor = simpledialog.askfloat('Multiplicar pesos', f'Multiplicar o peso de {len(selection)} carta(s) por:',
                                       parent=self, minvalue=0, maxvalue=1000, initialvalue=2)
        if factor is None:
            return
        try:
            self._update_weights({cid: int(round(self.weights.get(cid, 0) * factor)) for cid in selection})
        except (ModError, OSError, ValueError) as exc:
            messagebox.showerror('Tabela de pesos', str(exc), parent=self)

    def _remove(self):
        selection = tuple(int(cid) for cid in self.tree.selection())
        if selection:
            try:
                self._update_weights(dict.fromkeys(selection, 0))
            except (ModError, OSError, ValueError) as exc:
                messagebox.showerror('Tabela de pesos', str(exc), parent=self)

    def _set(self, cid, amount):
        self._update_weights({cid: amount})

    def _update_weights(self, changes):
        edited = dict(self.weights)
        for cid, amount in changes.items():
            if amount:
                edited[cid] = amount
            else:
                edited.pop(cid, None)
        if self.changed is not None:
            self.changed(edited)
        self.weights = edited
        self.render()

    def _close_inline(self):
        entry, self.inline = self.inline, None
        if entry is not None:
            entry.destroy()

    def _edit_weight(self, event):
        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item or not column.startswith('#') or column == '#0':
            return
        visible_columns = tuple(self.tree['displaycolumns'])
        column_index = int(column[1:]) - 1
        if column_index < 0 or column_index >= len(visible_columns):
            return
        field = visible_columns[column_index]
        if field not in ('peso', 'chance'):
            return
        self._close_inline()
        cid = int(item)
        x, y, width, height = self.tree.bbox(item, field)
        entry = self.inline = ttk.Entry(self.tree)
        value = str(self.weights.get(cid, 0)) if field == 'peso' else self.tree.set(item, field).removesuffix('%')
        entry.insert(0, value)
        entry.select_range(0, 'end')
        entry.place(x=x, y=y, width=width, height=height)
        entry.focus_set()

        def save(_event):
            try:
                if entry.get() == value:
                    self._close_inline()
                elif field == 'peso':
                    self._set(cid, simulation_nonnegative_int(entry.get(), 'Peso'))
                else:
                    self._set_chance(cid, entry.get())
            except (ModError, OSError, ValueError) as exc:
                messagebox.showerror('Tabela de pesos', str(exc), parent=self)
            return 'break'

        entry.bind('<Return>', save)
        entry.bind('<Escape>', lambda _event: self._close_inline())
        entry.bind('<FocusOut>', lambda _event: self._close_inline())
        return 'break'

    def _set_chance(self, cid, raw):
        raw = raw.strip().removesuffix('%').strip().replace(',', '.')
        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', raw):
            raise ModError('Informe uma porcentagem entre 0 e 100.')
        chance = Fraction(raw) / 100
        if not 0 <= chance <= 1:
            raise ModError('Informe uma porcentagem entre 0 e 100.')
        if chance == 0:
            self._set(cid, 0)
            return
        others = {other: weight for other, weight in self.weights.items() if other != cid}
        if not others:
            if chance != 1:
                raise ModError('Adicione outra carta para configurar uma chance menor que 100%.')
            self._set(cid, max(1, self.weights.get(cid, 0)))
            return
        if chance == 1:
            raise ModError('Para usar 100%, zere primeiro os outros pesos.')
        weight = sum(others.values()) * chance / (1 - chance)
        changes = {other: value * weight.denominator for other, value in others.items()}
        changes[cid] = weight.numerator
        common = gcd(*changes.values())
        self._update_weights({other: value // common for other, value in changes.items()})


class DeckProfileEditor(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.cards = {}
        self.project = None
        self.rows = []
        self.current = None
        self.fixed = tk.StringVar()
        self.draws = tk.StringVar()
        self.pool = tk.StringVar()

        self.query = tk.StringVar()
        self.kind = tk.StringVar(value='Todos os tipos')
        self.star = tk.StringVar(value=ALL_STARS)
        self._fusion_cache = None
        self.add_quantity = tk.StringVar(value='1')
        self.quantity = tk.StringVar(value='1')
        self.total = tk.StringVar()
        self.feedback = tk.StringVar()
        self.loading = False

        self.composition = tk.StringVar()
        header = ttk.Frame(self)
        header.pack(fill='x', pady=(0, 5))
        self.total_label = ttk.Label(header, textvariable=self.total, foreground=ACCENT)
        self.total_label.pack(side='left')
        ttk.Label(header, textvariable=self.composition, foreground=MUTED).pack(side='left', padx=(12, 0))
        ttk.Label(self, textvariable=self.feedback, foreground=ACCENT, wraplength=500).pack(
            side='bottom', anchor='w', pady=(3, 0))
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True)
        self.fixed_pane, self.pool_pane = (ttk.Frame(self.tabs, padding=7) for _ in range(2))
        self.tabs.add(self.fixed_pane, text='Cartas fixas')
        self.tabs.add(self.pool_pane, text='Pools ponderados')

        filters = ttk.Frame(self.fixed_pane)
        filters.pack(fill='x')
        ttk.Label(filters, text='ID, nome, tipo ou descrição').pack(side='left', padx=(0, 5))
        search = ttk.Entry(filters, textvariable=self.query, width=17)
        search.pack(side='left', fill='x', expand=True)
        kind = ttk.Combobox(filters, textvariable=self.kind, width=14, state='readonly',
                            values=['Todos os tipos', 'Monstros', *TYPE_NAMES])
        kind.pack(side='left', padx=(5, 0))
        star = ttk.Combobox(filters, textvariable=self.star, width=15, state='readonly',
                            values=list(STAR_FILTERS))
        star.pack(side='left', padx=(5, 0))
        for combo in (kind, star):
            combo.bind('<MouseWheel>', lambda _e: 'break')
        self.fusion_filter = FusionFilter(self, self.cards, {}, self._deck_ids, self._render_catalog)
        fusion_row = self.fusion_filter.build(self.fixed_pane)
        fusion_row.pack(fill='x', pady=(4, 0))

        lists = ttk.Frame(self.fixed_pane)
        lists.pack(fill='both', expand=True, pady=(5, 2))
        for col in range(2):
            lists.columnconfigure(col, weight=1, uniform='decks')
        lists.rowconfigure(0, weight=1)
        catalog = ttk.LabelFrame(lists, text='Catálogo', padding=3)
        catalog.grid(row=0, column=0, sticky='nsew', padx=(0, 3))
        fixed = ttk.LabelFrame(lists, text='Deck atual', padding=3)
        fixed.grid(row=0, column=1, sticky='nsew', padx=(3, 0))
        from .mod_tools_gui import _tree
        self.catalog = _tree(catalog, [('id', 'ID', 50), ('nome', 'Carta', 135),
                                       ('tipo', 'Tipo', 76), ('atk', 'ATK', 78),
                                       ('def', 'DEF', 78), ('estrelas', 'Estrelas', 96),
                                       ('fusao', 'Fusão', 210)], height=5, raw_values=self._catalog_sort_value,
                             selectmode='extended', horizontal=True)
        self.deck = _tree(fixed, [('id', 'ID', 50), ('nome', 'Carta', 135),
                                  ('atk', 'ATK', 78), ('def', 'DEF', 78),
                                  ('qtd', 'Cópias', 58)], height=5, raw_values=self._deck_sort_value,
                          selectmode='extended', horizontal=True)
        self.catalog.bind('<Double-1>', lambda _event: self.change_card('add'))
        self.catalog.bind('<Return>', lambda _event: self.change_card('add'))
        self.catalog.bind('<<TreeviewSelect>>', self._update_buttons)
        self.catalog.bind('<Control-a>', self._select_all_catalog)
        self.deck.bind('<<TreeviewSelect>>', self._select_copy)
        self.deck.bind('<Control-a>', self._select_all_deck)
        self.deck.bind('<Delete>', lambda _event: self.change_card('remove'))
        search.bind('<Return>', lambda _event: self._focus_result())
        ttk.Label(self.fixed_pane, text='Ctrl/Shift: selecione várias cartas; as ações valem para todas.',
                  foreground=MUTED).pack(anchor='w', pady=(3, 0))

        controls = ttk.Frame(self.fixed_pane)
        controls.pack(fill='x', pady=2)
        ttk.Label(controls, text='Cópias a inserir').pack(side='left', padx=(0, 4))
        self.add_count = ttk.Spinbox(controls, from_=1, to=MAX_DECK, width=3, textvariable=self.add_quantity)
        self.add_count.pack(side='left', padx=(0, 4))
        self.add_btn = ttk.Button(controls, text='＋ Adicionar', style='Accent.TButton',
                                  command=lambda: self.change_card('add'))
        self.add_btn.pack(side='left', padx=(0, 6))
        ttk.Label(controls, text='Total por carta').pack(side='left', padx=(0, 4))
        ttk.Spinbox(controls, from_=1, to=MAX_DECK, width=3,
                    textvariable=self.quantity).pack(side='left', padx=(0, 4))
        self.set_btn = ttk.Button(controls, text='Ajustar', command=lambda: self.change_card('set'))
        self.remove_btn = ttk.Button(controls, text='− Remover', style='Danger.TButton',
                                     command=lambda: self.change_card('remove'))
        for button in (self.set_btn, self.remove_btn):
            button.pack(side='left', padx=(0, 4))
        selection_tools = ttk.Frame(self.fixed_pane)
        selection_tools.pack(fill='x', pady=(3, 0))
        ttk.Button(selection_tools, text='Selecionar catálogo visível',
                   command=self._select_all_catalog).pack(side='left', padx=(0, 6))
        ttk.Button(selection_tools, text='Selecionar deck visível',
                   command=self._select_all_deck).pack(side='left')
        ttk.Label(self.fixed_pane, text='IDs (ex. 16x2, 723)').pack(anchor='w', pady=(3, 0))
        ttk.Entry(self.fixed_pane, textvariable=self.fixed).pack(fill='x')

        actions = ttk.Frame(self.pool_pane)
        actions.pack(fill='x', pady=(0, 7))
        self.pool_combo = ttk.Combobox(actions, textvariable=self.pool, state='readonly', width=13)
        self.pool_combo.pack(side='left')
        self.pool_combo.bind('<<ComboboxSelected>>', self._select_pool)
        ttk.Button(actions, text='＋ Pool', command=self.add_pool).pack(side='left', padx=3)
        ttk.Button(actions, text='Excluir pool', style='Danger.TButton',
                   command=self.remove_pool).pack(side='left', padx=3)
        ttk.Label(actions, text='Compras').pack(side='left', padx=(9, 5))
        ttk.Spinbox(actions, from_=0, to=MAX_DECK, width=4, textvariable=self.draws).pack(side='left')
        pool_guide = ttk.Frame(self.pool_pane)
        pool_guide.pack(fill='x', pady=(0, 7))
        ttk.Label(
            pool_guide,
            text='Compras = cartas sorteadas desta pool. Para PS1: 1 pool com 40 compras e 0 fixas.',
            foreground=MUTED, wraplength=420, justify='left',
        ).pack(side='left', fill='x', expand=True)
        ttk.Button(pool_guide, text='Completar vagas',
                   command=self._complete_pool_draws).pack(side='right', padx=(8, 0))
        self.table = WeightTable(self.pool_pane)
        self.table.pack(fill='both', expand=True)

        for variable in (self.kind, self.query, self.star):
            variable.trace_add('write', lambda *_: self._render_catalog())
        self.fixed.trace_add('write', lambda *_: self._render_deck())
        self.fixed.trace_add('write', lambda *_: self._refresh_fusion_view())
        self.table.picker_context = lambda: (self._fusion_map(), self._deck_ids())
        self.tabs.bind('<<NotebookTabChanged>>', lambda _e: self._refresh_fusion_view())
        self.draws.trace_add('write', lambda *_: self._render_deck())
        self._render_deck()

    def refresh_catalog(self, cards, project):
        self.cards, self.project = cards, project
        self._fusion_cache = None
        self.fusion_filter.set_data(cards, self._fusion_map())
        self.table.refresh_catalog(cards)
        self._render_catalog()
        self._render_deck()

    def _fusion_map(self):
        """{(a, b): resultado} do projeto (receitas originais + alterações), em cache."""
        if self._fusion_cache is None:
            self._fusion_cache = {}
            if self.project is not None:
                try:
                    _, _, equips, rituals = base_tables(self.project)
                    self._fusion_cache, _, _ = match_recipes(self.project, equips, rituals)
                except (ModError, OSError, ValueError, KeyError):
                    self._fusion_cache = {}
        return self._fusion_cache

    def _deck_ids(self):
        """Cartas do deck em edição: fixas + todas as cartas com peso nos pools."""
        try:
            ids = set(parse_card_ids(self.fixed.get(), maximum=MAX_DECK))
        except (ModError, ValueError):
            ids = set()
        for index, row in enumerate(self.rows):
            weights = self.table.weights if index == self.current else row.get('pesos', {})
            ids.update(int(cid) for cid, weight in weights.items() if int(weight))
        return ids

    def _refresh_fusion_view(self):
        if self.fusion_filter.mode.get() != FUSION_NONE and not self.loading:
            self._render_catalog()

    def _render_catalog(self):
        query = search_text(self.query.get())
        kind = self.kind.get()
        star = self.star.get()
        self.fusion_filter.cards = self.cards
        notes = self.fusion_filter.notes()
        rows = []
        for cid in sorted(self.cards):
            if not has_star(self.cards[cid], star):
                continue
            if notes is not None and cid not in notes:
                continue
            typ = int(self.cards[cid]['tipo_id'])
            label = ('Deus' if typ == 24 else TYPE_NAMES[typ]
                     if 0 <= typ < len(TYPE_NAMES) else str(typ))
            if kind == 'Monstros' and typ not in MONSTER_TYPES:
                continue
            if kind not in ('Todos os tipos', 'Monstros') and label != kind:
                continue
            name = display_name(cid, self.cards)
            if card_matches(query, cid, self.cards[cid]):
                rows.append((cid, (
                    compact_number(cid), name, label,
                    _monster_stat(self.cards[cid], 'ataque'),
                    _monster_stat(self.cards[cid], 'defesa'),
                    star_label(self.cards[cid]), (notes or {}).get(cid, ''))))
        self._render_rows(self.catalog, rows)
        self._render_deck()
        self._update_buttons()

    def _catalog_sort_value(self, item, field):
        if field in ('atk', 'def'):
            return _monster_stat_sort(self.cards.get(int(item)),
                                      'ataque' if field == 'atk' else 'defesa')
        return int(item) if field == 'id' else self.catalog.set(item, field)

    def _deck_sort_value(self, item, field):
        if field in ('atk', 'def'):
            return _monster_stat_sort(self.cards.get(int(item)),
                                      'ataque' if field == 'atk' else 'defesa')
        return int(item) if field == 'id' else self.deck.set(item, field)

    def _render_rows(self, tree, rows):
        selected = tree.selection()
        top = tree.yview()[0]
        tree.delete(*tree.get_children())
        for index, (cid, values) in enumerate(rows):
            tree.insert('', 'end', iid=str(cid), values=values,
                        tags=card_row_tags(tree, self.cards.get(cid), index))
        tree.sort_rows()
        valid = [item for item in selected if tree.exists(item)]
        if valid:
            tree.selection_set(valid)
        tree.yview_moveto(top)

    def _render_deck(self):
        if self.loading:
            return
        try:
            fixed = parse_card_ids(self.fixed.get(), maximum=MAX_DECK)
            pools = self._pool_slots()
            space = MAX_DECK - len(fixed) - pools
            self.total.set(f'{len(fixed) + pools}/{MAX_DECK} cartas · {len(fixed)} fixas + {pools} de pools')
            self.total_label.configure(foreground=ACCENT if len(fixed) + pools == MAX_DECK else WARNING)
            from .deck_summary import composition, describe
            self.composition.set(describe(composition(self.cards, fixed)) if fixed else '')
            self.add_count.configure(to=max(space, 1))
            if space == 1 and self.add_quantity.get() != '1':
                self.add_quantity.set('1')
        except (ModError, ValueError):
            fixed = []
            self.total.set('Revise os IDs ou as compras dos pools')
            self.total_label.configure(foreground=WARNING)
            self.composition.set('')
        query = search_text(self.query.get())
        self._render_rows(self.deck, [
            (cid, (compact_number(cid), display_name(cid, self.cards),
                   _monster_stat(self.cards.get(cid), 'ataque'),
                   _monster_stat(self.cards.get(cid), 'defesa'), amount))
            for cid, amount in sorted(Counter(fixed).items())
            if card_matches(query, cid, self.cards.get(cid, {}))
        ])
        self._update_buttons()

    def _remaining_pool_slots(self):
        fixed = len(parse_card_ids(self.fixed.get(), maximum=MAX_DECK))
        other = sum(
            simulation_nonnegative_int(row['compras'], 'Compras do pool')
            for index, row in enumerate(self.rows) if index != self.current
        )
        available = MAX_DECK - fixed - other
        if available <= 0:
            raise ModError('Não há vagas livres: reduza as cartas fixas ou as compras de outros pools.')
        return available

    def _current_pool_draws(self):
        """Evita perder as compras quando o Spinbox fica vazio na edição.

        Um pool já salvo conserva sua última quantidade válida. Se a linha
        ainda não tinha quantidade, preenche exatamente as vagas restantes.
        Valores não vazios inválidos continuam gerando erro explícito.
        """
        typed = self.draws.get().strip()
        if typed:
            return simulation_nonnegative_int(typed, 'Compras do pool')
        if self.current is not None:
            previous = self.rows[self.current].get('compras', '')
            if str(previous).strip():
                return simulation_nonnegative_int(previous, 'Compras do pool')
        return self._remaining_pool_slots()

    def _complete_pool_draws(self):
        try:
            value = self._remaining_pool_slots()
            self.draws.set(str(value))
            self.feedback.set(
                f'Compras do pool: {value}. Para exportar ao PS1, use 40 compras '
                'em uma única pool, sem cartas fixas.'
            )
        except (ModError, ValueError) as exc:
            self.feedback.set(str(exc))

    def _pool_slots(self):
        amounts = [
            self._current_pool_draws() if i == self.current else
            simulation_nonnegative_int(row['compras'], 'Compras do pool')
            for i, row in enumerate(self.rows)
        ]
        return sum(amounts)

    def _focus_result(self):
        results = self.catalog.get_children()
        if results:
            self.catalog.selection_set(results[0])
            self.catalog.focus(results[0])
            self.catalog.focus_set()

    def _update_buttons(self, _event=None):
        self.add_btn.configure(state='normal' if self.catalog.selection() else 'disabled')
        state = 'normal' if self.deck.selection() else 'disabled'
        self.set_btn.configure(state=state)
        self.remove_btn.configure(state=state)

    def _select_copy(self, _event=None):
        selection = self.deck.selection()
        if len(selection) == 1:
            self.quantity.set(self.deck.set(selection[0], 'qtd'))
        self._update_buttons()

    def _select_all_catalog(self, _event=None):
        visible = self.catalog.get_children()
        self.catalog.selection_set(visible)
        if visible:
            self.catalog.focus(visible[0])
            self.catalog.focus_set()
        self._update_buttons()
        return 'break'

    def _select_all_deck(self, _event=None):
        visible = self.deck.get_children()
        self.deck.selection_set(visible)
        if visible:
            self.deck.focus(visible[0])
            self.deck.focus_set()
        self._update_buttons()
        return 'break'

    def start_fixed_deck(self):
        self.load(self.cards, {})
        self.tabs.select(self.fixed_pane)
        self.feedback.set('Deck em branco. Adicione cartas e salve.')

    def change_card(self, action, cid=None, *, copies=None):
        """Edite várias cartas atomicamente, sem ultrapassar 40 slots ou cópias.

        Adicionar soma N cópias a cada ID selecionado; Ajustar define o total
        de cópias de cada ID; Remover elimina todas as cópias selecionadas.
        """
        if action not in ('add', 'set', 'remove'):
            raise ValueError(f'Ação de deck desconhecida: {action}')
        widget = self.catalog if action == 'add' else self.deck
        selected = (int(cid),) if cid is not None else tuple(int(item) for item in widget.selection())
        if not selected:
            return
        selected = tuple(dict.fromkeys(selected))
        try:
            ids = parse_card_ids(self.fixed.get(), maximum=MAX_DECK)
            old_counts = Counter(ids)
            counts = old_counts.copy()
            if action == 'add':
                amount = positive_int(self.add_quantity.get() if copies is None else copies,
                                      'Cópias por carta')
                for card_id in selected:
                    counts[card_id] += amount
            elif action == 'set':
                amount = simulation_nonnegative_int(self.quantity.get(), 'Total por carta')
                for card_id in selected:
                    counts[card_id] = amount
            else:
                for card_id in selected:
                    counts.pop(card_id, None)
            fixed_total = sum(counts.values())
            pools = self._pool_slots()
            if fixed_total + pools > MAX_DECK:
                raise ModError(f'Deck excederia {MAX_DECK} cartas: {fixed_total} fixas '
                               f'+ {pools} de pools. Nada foi alterado.')
            # Não reordenar cópias intercaladas do deck original. Adições
            # entram no final; ajuste diminui a quantidade das últimas cópias.
            if action == 'add':
                updated = list(ids)
                for card_id in selected:
                    updated.extend([card_id] * amount)
            elif action == 'remove':
                updated = [card_id for card_id in ids if card_id not in selected]
            else:
                remaining = {card_id: counts[card_id] for card_id in selected}
                updated = []
                for card_id in ids:
                    if card_id not in remaining:
                        updated.append(card_id)
                    elif remaining[card_id]:
                        updated.append(card_id)
                        remaining[card_id] -= 1
                for card_id in selected:
                    updated.extend([card_id] * remaining[card_id])
            meta = getattr(self.project, 'metadata', {})
            effects = getattr(self.project, 'effects', {})
            validate_deck(self.cards, effects, updated,
                          int(meta.get('ps1_deck_global_limit', 3)))
        except (ModError, ValueError) as exc:
            self.feedback.set(str(exc))
            return
        self.fixed.set(', '.join(map(str, updated)))
        if action == 'add':
            self.add_quantity.set('1')
        # Depois de adicionar, selecionar as novas cartas também no "Deck atual"
        # preserva o fluxo legado de ajustar cópias logo na operação seguinte.
        keep = [str(card_id) for card_id in selected if self.deck.exists(str(card_id))]
        if keep:
            self.deck.selection_set(keep)
            self.deck.see(keep[0])
        self.feedback.set(f'{len(selected)} carta(s) atualizada(s) no deck. Salve o deck.')

    def load(self, cards, profile, *, show_fixed=True):
        self.cards = cards
        self.loading = True
        self.feedback.set('')
        self.fixed.set(', '.join(map(str, profile.get('cartas', []))))
        if show_fixed:
            self.tabs.add(self.fixed_pane)
        else:
            self.tabs.hide(self.fixed_pane)
        self.rows = deepcopy(profile.get('pools', []))
        self._show(0 if self.rows else None)
        self.loading = False
        self._render_catalog()
        self._render_deck()

    def snapshot(self):
        self._stage()
        return {
            'ids': self.fixed.get(), 'rows': deepcopy(self.rows), 'index': self.current,
            'draws': self.draws.get(), 'weights': dict(self.table.weights),
            'selected': self.table.selected.get(), 'weight': self.table.weight.get(),
            'deck_selection': self.deck.selection(), 'deck_top': self.deck.yview()[0],
            'feedback': self.feedback.get(),
        }

    def restore(self, draft):
        self.loading = True
        self.fixed.set(draft['ids'])
        self.rows = deepcopy(draft['rows'])
        self._show(draft['index'])
        self.draws.set(draft['draws'])
        self.table.load(self.cards, draft['weights'])
        self.table.selected.set(draft['selected'])
        self.table.weight.set(draft['weight'])
        self.table._search()
        self.loading = False
        self._render_deck()
        self.deck.selection_set([item for item in draft['deck_selection'] if self.deck.exists(item)])
        self.deck.yview_moveto(draft['deck_top'])
        self.feedback.set(draft['feedback'])
        self._update_buttons()

    def _show(self, index):
        self.current = index
        titles = [f'Pool {i+1}' for i in range(len(self.rows))]
        self.pool_combo.configure(values=titles)
        if index is None:
            self.pool.set('')
            self.draws.set('')
            self.table.load(self.cards, {})
        else:
            self.pool_combo.current(index)
            self.draws.set(str(self.rows[index]['compras']))
            self.table.load(self.cards, self.rows[index]['pesos'])
        self._render_deck()

    def _stage(self):
        if self.current is not None:
            count = self._current_pool_draws()
            self.rows[self.current] = {'compras': count, 'pesos': dict(self.table.weights)}
            if not self.draws.get().strip():
                self.draws.set(str(count))

    def _select_pool(self, _event):
        current = self.pool_combo.current()
        try:
            self._stage()
        except (ModError, ValueError) as exc:
            self.feedback.set(f'{exc} Corrija as compras antes de trocar de pool.')
            if self.current is not None:
                self.pool_combo.current(self.current)
            return
        self._show(current)

    def add_pool(self):
        try:
            self._stage()
        except (ModError, ValueError) as exc:
            self.feedback.set(f'{exc} Corrija as compras antes de criar outro pool.')
            return
        if self.current is None and not self.rows and not self.table.weights:
            weights = {}
        else:
            weights = dict(self.table.weights) if self.current is None else {}
        self.rows.append({'compras': '40' if not self.rows and not self.fixed.get().strip() else '1', 'pesos': weights})
        self._show(len(self.rows) - 1)

    def remove_pool(self):
        if self.current is not None:
            del self.rows[self.current]
            self._show(0 if self.rows else None)

    def profile(self):
        if self.current is None and (self.table.weights or self.draws.get().strip()):
            count = self._current_pool_draws()
            self.rows.append({'compras': count, 'pesos': dict(self.table.weights)})
            self._show(len(self.rows) - 1)
        self._stage()
        return {'cartas': parse_card_ids(self.fixed.get(), maximum=MAX_DECK),
                'pools': deepcopy(self.rows)}


class ModEditor(ttk.Frame):
    def __init__(self, parent, studio):
        super().__init__(parent, padding=12)
        self.pack(fill='both', expand=True)
        self.studio = studio
        self.project = None
        self.cards, self.pools = {}, {}
        self.stock = []
        self.rules = {}
        self._loaded_opponent = None
        self._opponent_drafts = {}
        self._starter_baseline = None
        self.use_deck_drops = tk.BooleanVar()
        self.duelist = tk.StringVar(value='01 · Simon Muran')
        self.rank = tk.StringVar()
        self.starter = tk.StringVar(value=STOCK_STARTER)
        self.starter_weight = tk.StringVar(value='1')
        self.random_starter = tk.BooleanVar()
        self.mod_lp = tk.StringVar(value='8000')
        self.ps1_ai_modes = {'Normal — IA original': 'normal',
                             'Difícil — IA aprimorada': 'dificil',
                             'Agressiva — mais fusões e ataques': 'agressiva',
                             'Máxima — vê 20 cartas e funde sempre': 'maxima'}
        self.ps1_ai_choice = tk.StringVar(value='Normal — IA original')
        self.opponent_first = tk.BooleanVar()
        self.status = tk.StringVar(value='Abra um projeto para editar as tabelas.')
        from .campaign_generator import campaign_label
        self.duelist_ids = {
            f'{i:02d} · {name}  [{campaign_label(i)}]': i
            for i, name in enumerate(DUELIST_NAMES_REFERENCE) if i
        }
        self.duelist.set(next(iter(self.duelist_ids)))
        self.campaign_badge_text = tk.StringVar()
        self.rank_ids = {f'{label} (grupo PS1)': key for key, label in DROP_GROUPS.items()}
        self.rank_ids.update({rank: rank for rank in RANK_GROUPS if rank != 'B/C/D'})
        head = self.head = ttk.Frame(self)
        head.pack(fill='x', pady=(0, 8))
        ttk.Label(head, text='Duelista').pack(side='left', padx=(0, 5))
        chooser = ttk.Combobox(head, textvariable=self.duelist, state='readonly', values=list(self.duelist_ids), width=34)
        chooser.pack(side='left')
        chooser.bind('<<ComboboxSelected>>', lambda _e: self._load_duelist())
        self.campaign_badge = tk.Label(
            head, textvariable=self.campaign_badge_text, bg='#1D3945',
            fg=ACCENT, padx=9, pady=5, font=('Segoe UI', 9, 'bold'))
        self.campaign_badge.pack(side='left', padx=5)
        self.password_button = ttk.Button(head, text='Passwords e baú', command=self.open_passwords)
        self.password_button.pack(side='left', padx=6)
        self.duel_button = ttk.Button(head, text='Jogar duelo', style='Accent.TButton', command=self.start_match)
        self.duel_button.pack(side='right')
        ttk.Checkbutton(head, text='Oponente começa', variable=self.opponent_first).pack(side='right', padx=8)
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True)
        self.tabs.enable_traversal()
        drop_pane, deck_pane, start_pane, lp_pane, quest_pane, magic_pane, frame_pane, wall_pane = [
            ttk.Frame(self.tabs, padding=9) for _ in range(8)]
        self.deck_pane = deck_pane
        for pane, name in zip((deck_pane, drop_pane, start_pane, lp_pane, quest_pane, magic_pane, frame_pane,
                               wall_pane),
                              ('Deck oponente', 'Drops', 'Decks iniciais', 'Config. MOD',
                               'Quests', 'Mágicas/Traps', 'Molduras', 'Fundo do menu')):
            self.tabs.add(pane, text=name)
        from .quest_gui import CampaignQuestEditor
        self.quest_editor = CampaignQuestEditor(quest_pane, studio)
        from .magic_gui import MagicTrapEditor
        self.magic_editor = MagicTrapEditor(magic_pane, studio)
        from .frame_gui import FrameColorEditor
        self.frame_editor = FrameColorEditor(frame_pane, studio)
        from .wallpaper_gui import MenuWallpaperEditor
        self.wallpaper_editor = MenuWallpaperEditor(wall_pane, studio)
        fixed_row = ttk.Frame(drop_pane)
        fixed_row.pack(fill='x', pady=(0, 4))
        ttk.Label(fixed_row, text='Drop fixo (só na 1ª vitória):').pack(side='left', padx=(0, 6))
        self.fixed_drop_var = tk.StringVar(value=FIXED_DROP_NONE)
        self.fixed_drop_box = ttk.Combobox(fixed_row, textvariable=self.fixed_drop_var, width=38)
        self.fixed_drop_box.pack(side='left')
        self.fixed_drop_box.bind('<KeyRelease>', self._filter_fixed_drop)
        self.fixed_drop_box.bind('<<ComboboxSelected>>', lambda _e: self._save_fixed_drop())
        self.fixed_drop_box.bind('<Return>', lambda _e: self._save_fixed_drop())
        ttk.Button(fixed_row, text='Remover', command=self._clear_fixed_drop).pack(side='left', padx=(6, 0))
        ttk.Label(drop_pane, foreground=MUTED, wraplength=630, text=(
            'A primeira vitória contra este duelista entrega esta carta no SPOILS; '
            'o save guarda que ela já saiu e as vitórias seguintes usam o sorteio normal. '
            'Digite parte do nome ou o número para filtrar.')).pack(anchor='w', pady=(0, 6))
        self.drop_toggle = ttk.Checkbutton(drop_pane, text='Drops ponderados do próprio deck',
                                           variable=self.use_deck_drops, command=self._toggle_deck_drops)
        self.drop_toggle.pack(anchor='w', pady=(0, 6))
        self.rank_editor = ttk.Frame(drop_pane)
        select_rank = ttk.Frame(self.rank_editor)
        select_rank.pack(fill='x', pady=(0, 5))
        rank = ttk.Combobox(select_rank, textvariable=self.rank, values=list(self.rank_ids), width=23, state='readonly')
        rank.current(0)
        rank.pack(side='left')
        rank.bind('<<ComboboxSelected>>', lambda _e: self._load_drop())
        ttk.Button(select_rank, text='Restaurar pesos herdados', command=self._inherit_drop).pack(side='right')
        self.drops = WeightTable(self.rank_editor)
        self.drops.changed = self._save_drop
        self.drops.pack(fill='both', expand=True)
        self.deck_drop_panel = ttk.Frame(drop_pane)
        deck_rank = ttk.Frame(self.deck_drop_panel)
        deck_rank.pack(fill='x', pady=(0, 6))
        ttk.Label(deck_rank, text='Grupo de rank:').pack(side='left', padx=(0, 6))
        self.deck_rank_selector = ttk.Combobox(
            deck_rank, textvariable=self.rank, state='readonly', width=28,
            values=[key for key, code in self.rank_ids.items() if code in DROP_GROUPS])
        self.deck_rank_selector.pack(side='left')
        self.deck_rank_selector.bind('<<ComboboxSelected>>', lambda _event: self._load_drop())
        ttk.Button(deck_rank, text='Restaurar pesos iguais',
                   command=self._reset_deck_drop).pack(side='right')
        self.deck_drop_detail = ttk.Label(self.deck_drop_panel, wraplength=630, foreground=MUTED)
        self.deck_drop_detail.pack(anchor='w', pady=(0, 6))
        self.deck_drop_table = WeightTable(self.deck_drop_panel, show_zero=True)
        self.deck_drop_table.changed = self._save_deck_drop
        self.deck_drop_table.pack(fill='both', expand=True)

        self.opponent_deck = DeckProfileEditor(deck_pane)
        opponent_actions = ttk.Frame(deck_pane)
        opponent_actions.pack(side='bottom', fill='x', pady=(5, 0))
        self.blank_deck_button = ttk.Button(opponent_actions, text='Novo deck fixo',
                                            command=self.opponent_deck.start_fixed_deck)
        self.blank_deck_button.pack(side='left')
        self.generate_button = ttk.Button(opponent_actions, text='Gerar Deck Aleatório',
                                          command=lambda: self.generate_deck(self.opponent_deck))
        self.generate_button.pack(side='left', padx=5)
        self.original_deck_button = ttk.Button(opponent_actions, text='Criar deck da ISO original',
                                                command=self.create_deck_from_original_iso)
        self.original_deck_button.pack(side='left', padx=(2, 5))
        self.save_opponent_button = ttk.Button(opponent_actions, text='Salvar deck', style='Accent.TButton',
                                               command=self.save_opponent)
        self.save_opponent_button.pack(side='right')
        self.preset_39_button = ttk.Button(
            opponent_actions, text='Gerar Decks Difíceis (3/5 → 5/5)',
            style='Accent.TButton', command=self.generate_hard_campaign)
        self.preset_39_button.pack(side='right', padx=(0, 8))
        self.opponent_deck.pack(fill='both', expand=True)

        profiles = ttk.Frame(start_pane)
        profiles.pack(fill='x', pady=(0, 6))
        self.profiles = ttk.Combobox(profiles, textvariable=self.starter, state='readonly', width=22)
        self.profiles.pack(side='left')
        self.profiles.bind('<<ComboboxSelected>>', lambda _e: self._load_starter())
        ttk.Button(profiles, text='+ Perfil', command=self._add_starter).pack(side='left', padx=4)
        ttk.Button(profiles, text='Excluir', style='Danger.TButton',
                   command=self._delete_starter).pack(side='left')
        ttk.Label(profiles, text='Peso do perfil').pack(side='left', padx=(8, 4))
        ttk.Entry(profiles, width=7, textvariable=self.starter_weight).pack(side='left')
        self.starter_deck = DeckProfileEditor(start_pane)
        self.starter_deck.pack(fill='both', expand=True)
        starter_actions = ttk.Frame(start_pane)
        starter_actions.pack(fill='x')
        ttk.Button(starter_actions, text='Ler pools do BIN/CUE', command=self._load_starter_disc).pack(side='left')
        ttk.Checkbutton(starter_actions, text='Sortear perfil no duelo',
                        variable=self.random_starter).pack(side='left', padx=5)
        ttk.Button(profiles, text='Gerar Deck Aleatório',
                   command=lambda: self.generate_deck(self.starter_deck)).pack(side='right')
        ttk.Button(profiles, text='✦ Gerar deck temático…', style='Accent.TButton',
                   command=self.generate_themed_starter).pack(side='right', padx=(0, 6))
        ttk.Button(starter_actions, text='Salvar deck inicial', style='Accent.TButton',
                   command=self.save_starter).pack(side='right')
        ttk.Button(starter_actions, text='Escolha no New Game (PS1)…',
                   command=self.open_starter_choice).pack(side='right', padx=(0, 6))

        ttk.Label(lp_pane, text='Life Points iniciais — jogador e TODOS os oponentes',
                  font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(6, 7))
        ttk.Label(lp_pane, text='Valor global único para cada duelo do mod, inclusive no simulador. '
                  'No Drop x15 o Studio prepara cinco dígitos para LP acima de 9.999; '
                  'a apresentação do painel deve ser conferida no ePSXe.',
                  wraplength=630, justify='left').pack(anchor='w', pady=(0, 8))
        ttk.Entry(lp_pane, textvariable=self.mod_lp, width=25).pack(anchor='w')
        ttk.Button(lp_pane, text='Salvar LP para ambos', style='Accent.TButton',
                   command=self.save_lp).pack(anchor='w', pady=9)
        ttk.Separator(lp_pane, orient='horizontal').pack(fill='x', pady=13)
        ttk.Label(lp_pane, text='Inteligência artificial dos oponentes — PlayStation 1',
                  font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(4, 7))
        ttk.Label(lp_pane, text='Difícil: o oponente procura fusões, equipamentos, armadilhas e magias '
                  'em todo turno (sem sorteio para tentar). Agressiva: além disso, monta fusões completas '
                  '(até 3 níveis, inclusive só com cartas da mão), enxerga pelo menos 10 cartas '
                  '(mão + próximas do deck), continua fundindo até o fim do deck e ataca cartas '
                  'viradas com mais frequência. Máxima: enxerga 20 cartas e ataca cartas viradas na '
                  'maioria das vezes. Nenhum modo aumenta atributos.',
                  wraplength=630, justify='left').pack(anchor='w', pady=(0, 9))
        ttk.Combobox(lp_pane, textvariable=self.ps1_ai_choice, state='readonly',
                     values=list(self.ps1_ai_modes), width=38).pack(anchor='w')
        ttk.Button(lp_pane, text='Salvar dificuldade da IA', style='Accent.TButton',
                   command=self.save_ps1_ai).pack(anchor='w', pady=9)
        ttk.Label(lp_pane, text='Disponível para a imagem Drop x15 validada. '
                  'Após salvar, gere outro BIN/CUE. A IA do simulador não é alterada.',
                  foreground=MUTED, wraplength=630).pack(anchor='w', pady=(0, 8))
        ttk.Label(self, textvariable=self.status, foreground=ACCENT, wraplength=610).pack(anchor='w', pady=(5, 0))
        self._update_available()

    def _update_available(self):
        state = 'normal' if self.project else 'disabled'
        for button in (self.password_button, self.duel_button, self.drop_toggle, self.save_opponent_button,
                       self.generate_button, self.original_deck_button,
                       self.blank_deck_button, self.preset_39_button):
            button.configure(state=state)

    def refresh(self):
        if self.project is not self.studio.project:
            self._opponent_drafts.clear()
            self._loaded_opponent = None
        else:
            self._remember_opponent()
        self.project = self.studio.project
        self.quest_editor.set_project(self.project)
        self.magic_editor.set_project(self.project)
        self.frame_editor.set_project(self.project)
        self.wallpaper_editor.set_project(self.project)
        self._update_available()
        if self.project:
            self.cards = {cid: self.project.get(cid) for cid in self.project.cards}
            self.pools, self.stock, _, _ = base_tables(self.project)
            self.rules = normalize_rules(self.project.metadata.get(CONFIG_KEY, {}), self.cards)
            self.mod_lp.set(str(starting_life(self.project, self._duel_id())['jogador']))
            current_ai = self.rules.get('ia_ps1', 'normal')
            self.ps1_ai_choice.set(next((label for label, code in self.ps1_ai_modes.items()
                                         if code == current_ai), 'Normal — IA original'))
            self.status.set('')
        else:
            self.cards, self.pools, self.rules, self.stock = {}, {}, {}, []
        self._load_duelist()
        self._refresh_profiles()

    def _remember_opponent(self):
        if self._loaded_opponent is not None:
            self._opponent_drafts[self._loaded_opponent] = self.opponent_deck.snapshot()

    def refresh_catalog(self):
        if self.project is not self.studio.project:
            self.refresh()
            return
        if self.project is None:
            return
        self.cards = {cid: self.project.get(cid) for cid in self.project.cards}
        self.drops.refresh_catalog(self.cards)
        for editor in (self.opponent_deck, self.starter_deck):
            editor.refresh_catalog(self.cards, self.project)
        if self.use_deck_drops.get():
            self._render_deck_drops()

    def _refresh_profiles(self, *, reload_editor=True):
        names = [STOCK_STARTER, *self.rules.get('iniciais', {})]
        self.profiles.configure(values=names)
        if self.starter.get() not in names:
            self.starter.set(STOCK_STARTER)
            reload_editor = True
        if reload_editor:
            self._load_starter()

    def _duel_id(self):
        return self.duelist_ids[self.duelist.get()]

    def _load_duelist(self):
        opponent = self._duel_id()
        if self._loaded_opponent != opponent:
            self._remember_opponent()
        draft = self._opponent_drafts.get(opponent)
        self.opponent_deck.refresh_catalog(self.cards, self.project)
        if draft is None:
            self.opponent_deck.load(self.cards, duelist_profile(self.rules, self.pools, opponent))
        else:
            self.opponent_deck.restore(draft)
        self._loaded_opponent = opponent if self.project else None
        self._refresh_campaign_badge()
        self._load_drop()
 
    def _fixed_drop_values(self):
        return [FIXED_DROP_NONE] + [f'#{cid:03d} {self.cards[cid].get("nome") or "?"}'
                                    for cid in sorted(self.cards)]

    def _filter_fixed_drop(self, event=None):
        if event is not None and event.keysym in ('Return', 'Up', 'Down', 'Escape'):
            return
        text = self.fixed_drop_var.get().strip().lower()
        values = self._fixed_drop_values()
        if text and text != FIXED_DROP_NONE.lower():
            values = [v for v in values if text in v.lower()][:200] or values
        self.fixed_drop_box.configure(values=values)

    def _load_fixed_drop(self):
        card = fixed_drop(self.rules, self._duel_id()) if self.project else None
        self.fixed_drop_box.configure(values=self._fixed_drop_values())
        if card and card in self.cards:
            self.fixed_drop_var.set(f'#{card:03d} {self.cards[card].get("nome") or "?"}')
        else:
            self.fixed_drop_var.set(FIXED_DROP_NONE)

    def _save_fixed_drop(self):
        text = self.fixed_drop_var.get().strip()
        try:
            if not text or text == FIXED_DROP_NONE:
                card = None
            else:
                digits = text.lstrip('#').split()[0]
                if not digits.isdigit():
                    raise ModError('Escolha a carta do drop fixo na lista (ex.: #001 Blue-Eyes...).')
                card = int(digits)
                if card not in self.cards:
                    raise ModError(f'Drop fixo: carta #{card} não existe no projeto.')
            rules = self._edit()
            duel = self._selected_duelist(rules)
            if card is None:
                duel.pop(FIXED_DROP, None)
                caption = 'Drop fixo removido.'
            else:
                duel[FIXED_DROP] = card
                caption = f'Drop fixo salvo: #{card:03d} na 1ª vitória.'
            self._commit(rules, caption)
        except (ModError, ValueError, OSError) as exc:
            self.status.set(str(exc))
        self._load_fixed_drop()

    def _clear_fixed_drop(self):
        self.fixed_drop_var.set(FIXED_DROP_NONE)
        self._save_fixed_drop()

    def _load_drop(self):
        self._load_fixed_drop()
        active = drops_from_deck(self.rules, self._duel_id())
        self.use_deck_drops.set(active)
        if active:
            self.rank_editor.pack_forget()
            self.deck_drop_panel.pack(fill='both', expand=True)
            self._render_deck_drops()
        else:
            self.deck_drop_panel.pack_forget()
            self.rank_editor.pack(fill='both', expand=True)
            rank = self.rank_ids[self.rank.get()]
            self.drops.ps1_projection = bool(self.project and ps1_supports_god24(self.project)
                                             and rank in DROP_GROUPS)
            weights = drop_weights(self.rules, self.pools, self._duel_id(), rank)
            self.drops.load(self.cards, weights)

    def _render_deck_drops(self):
        opponent = self._duel_id()
        effects = self.project.effects if self.project else None
        candidates = deck_drop_candidates(self.rules, self.pools, opponent, effects=effects)
        # Exibir também os candidatos com peso zero para poder reativá-los.
        cards = {cid: self.cards[cid] for cid in sorted(candidates) if cid in self.cards}
        rank = self.rank_ids[self.rank.get()]
        weights = deck_drop_weights(self.rules, self.pools, opponent, rank, effects=effects)
        self.deck_drop_table.ps1_projection = bool(self.project and ps1_supports_god24(self.project))
        self.deck_drop_table.load(cards, weights)
        label = DROP_GROUPS.get(RANK_GROUPS.get(rank, rank), rank)
        self.deck_drop_detail.configure(text=(
            f'{len(cards)} cartas candidatas do deck salvo · {label}. '
            'Selecione uma carta e edite o peso; peso 0 impede o drop. '
            'A probabilidade muda automaticamente. '
            'Decks com pools usam seus candidatos configurados, mesmo se '
            'a carta não saiu no sorteio deste duelo.'
        ))

    def _save_deck_drop(self, weights):
        opponent = self._duel_id()
        group = RANK_GROUPS.get(self.rank_ids[self.rank.get()],
                               self.rank_ids[self.rank.get()])
        candidates = deck_drop_candidates(self.rules, self.pools, opponent, effects=self.project.effects)
        if not candidates:
            raise ModError('Salve primeiro o deck do oponente para editar seus drops.')
        if not weights:
            raise ModError('Mantenha pelo menos uma carta com peso positivo em cada grupo.')
        if not set(weights).issubset(candidates):
            raise ModError('Drops do próprio deck só aceitam cartas do deck do oponente.')
        rules = self._edit()
        duel = self._selected_duelist(rules)
        if not duel.get(DROP_FROM_DECK):
            raise ModError('Ative drops ponderados do próprio deck antes de editar.')
        duel.setdefault(DECK_DROP_WEIGHTS, {})[group] = weights
        self._commit(rules, f'Pesos de drop do deck salvos em {DROP_GROUPS[group]}.')

    def _reset_deck_drop(self):
        try:
            opponent = self._duel_id()
            candidates = deck_drop_candidates(self.rules, self.pools, opponent, effects=self.project.effects)
            weights = {cid: 1 for cid in sorted(candidates)}
            self._save_deck_drop(weights)
            self._render_deck_drops()
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Drops ponderados', str(exc), parent=self)

    def _toggle_deck_drops(self):
        try:
            rules = self._edit()
            opponent = self._duel_id()
            active = self.use_deck_drops.get()
            duel = self._selected_duelist(rules)
            if active:
                ids = deck_drop_candidates(rules, self.pools, opponent, effects=self.project.effects)
                if not ids:
                    raise ModError('Salve primeiro um deck de oponente com cartas para ativar os drops.')
                custom = duel.setdefault(DECK_DROP_WEIGHTS, {})
                for group in DROP_GROUPS:
                    custom.setdefault(group, {cid: 1 for cid in sorted(ids)})
            duel[DROP_FROM_DECK] = active
            caption = ('Drops ponderados do próprio deck ativados.'
                       if active else 'Pesos por rank do modo original restaurados.')
            self._commit(rules, caption)
        except (ModError, ValueError, OSError) as exc:
            self.status.set(str(exc))
        self._load_drop()

    def _load_starter(self):
        name = self.starter.get()
        profile = (self.rules.get('iniciais', {}).get(name, {}) if name != STOCK_STARTER
                   else {'pools': self.rules.get('pools_iniciais_ps1', self.stock)})
        self.starter_weight.set(str(profile.get('peso', 1)))
        self.starter_deck.refresh_catalog(self.cards, self.project)
        self.starter_deck.load(self.cards, profile, show_fixed=name != STOCK_STARTER)
        self._starter_baseline = self.starter_deck.snapshot()

    def _edit(self):
        if not self.project or self.studio._extract_running:
            raise ModError('Abra um projeto disponível para salvar a edição.')
        return normalize_rules(self.project.metadata.get(CONFIG_KEY, {}), self.cards)

    def _selected_duelist(self, rules):
        return rules.setdefault('duelistas', {}).setdefault(str(self._duel_id()), {})

    def _commit(self, rules, message):
        self.rules = save_rules(self.project, rules)
        self.status.set('✓ ' + message)
        self.studio._refresh_project()
        self.studio.notify(message)

    def _save_drop(self, weights):
        rules = self._edit()
        drops = self._selected_duelist(rules).setdefault('drops', {})
        drops[self.rank_ids[self.rank.get()]] = weights
        self._commit(rules, 'Pesos de drop salvos.')

    def _inherit_drop(self):
        try:
            rules = self._edit()
            self._selected_duelist(rules).get('drops', {}).pop(self.rank_ids[self.rank.get()], None)
            self._commit(rules, 'Pesos herdados restaurados.')
            self._load_drop()
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Drops', str(exc), parent=self)

    def show_duelist_header(self, visible: bool):
        """Seletor de duelista só nas telas que dependem dele (deck, drops, iniciais, quests)."""
        shown = bool(self.head.winfo_manager())
        if visible and not shown:
            self.head.pack(fill='x', pady=(0, 8), before=self.tabs)
        elif not visible and shown:
            self.head.pack_forget()

    def open_passwords(self):
        if self.project is None or self.studio._extract_running:
            return
        from .mod_tools_gui import PasswordsDialog
        from .passwords import original_passwords
        try:
            self.refresh_catalog()
            PasswordsDialog(self.studio, self.project, self.cards, original_passwords(self.project),
                            changed=self.collection_changed)
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Passwords de cartas', str(exc), parent=self)

    def collection_changed(self, starter=None):
        if self.project is not self.studio.project:
            return
        self.rules = normalize_rules(self.project.metadata.get(CONFIG_KEY, {}), self.cards)
        draft = self.starter_deck.snapshot()
        keys = ('ids', 'rows', 'draws', 'weights')
        no_draft = self._starter_baseline and all(draft[key] == self._starter_baseline[key] for key in keys)
        self._refresh_profiles(reload_editor=starter is not None and self.starter.get() == starter and no_draft)
        self.studio._refresh_project()
        self.studio.notify('Carta salva no baú.' if starter is None else f'Carta salva no baú e em {starter}.')

    def add_catalog_card(self, cid):
        self.add_catalog_cards([cid])

    def add_catalog_cards(self, ids):
        """Adicionar ao deck do rival um lote da biblioteca principal."""
        if not ids:
            return
        self.refresh_catalog()
        self.studio.tabs.select(self.studio.tab_mod)
        self.tabs.select(self.deck_pane)
        editor = self.opponent_deck
        editor.tabs.select(editor.fixed_pane)
        editor.kind.set('Todos os tipos')
        editor.query.set('')
        available = [str(cid) for cid in dict.fromkeys(ids) if editor.catalog.exists(str(cid))]
        if len(available) != len(set(ids)):
            editor.feedback.set('Há cartas da seleção que não existem no catálogo deste projeto.')
            return
        editor.catalog.selection_set(available)
        editor.change_card('add', copies=1)

    def _ready_for_generator(self, title):
        if self.project is None:
            messagebox.showinfo(title, 'Abra ou crie um projeto primeiro (menu Projeto). '
                                'O gerador usa as cartas e fusões do projeto.', parent=self)
            return False
        if self.studio._extract_running:
            messagebox.showinfo(title, 'Aguarde a extração terminar.', parent=self)
            return False
        return True

    def generate_deck(self, editor):
        if not self._ready_for_generator('Gerar Deck Aleatório'):
            return
        from .mod_tools_gui import DeckGeneratorDialog
        try:
            self.refresh_catalog()
            _, _, equips, rituals = base_tables(self.project)
            fusions, equips, _ = match_recipes(self.project, equips, rituals)
            metadata = self.project.metadata
            copies = int(metadata.get('ps1_deck_global_limit', 3))
            thresholds = {int(cid): int(value) for cid, value in metadata.get('ps1_trap_thresholds', {}).items()}
            try:
                fixed = parse_card_ids(editor.fixed.get(), maximum=MAX_DECK)
            except ModError:
                fixed = []
            starter = editor is self.starter_deck
            stock = starter and self.starter.get() == STOCK_STARTER
            DeckGeneratorDialog(
                self, self.cards, self.project.effects, fusions, equips, default_copies=copies,
                trap_thresholds=thresholds, fixed=fixed, new_starter=stock,
                starter=starter, opponent=None if starter else self._duel_id(),
                use_deck=lambda ids: self._use_generated_deck(editor, ids, stock),
            )
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Gerar Deck Aleatório', str(exc), parent=self)

    def open_starter_choice(self):
        if not self._ready_for_generator('Escolha do deck inicial'):
            return
        from .starter_choice_gui import StarterChoiceDialog
        StarterChoiceDialog(self, self.project, self.rules.get('iniciais', {}))

    def generate_themed_starter(self):
        if not self._ready_for_generator('Gerar deck temático'):
            return
        from .themed_deck_gui import ThemedDeckDialog
        try:
            self.refresh_catalog()
            _, _, equips, rituals = base_tables(self.project)
            fusions, equips, _ = match_recipes(self.project, equips, rituals)
            copies = int(self.project.metadata.get('ps1_deck_global_limit', 3))
            ThemedDeckDialog(self, self.cards, self.project.effects, fusions, equips,
                             default_copies=copies, use_deck=self._save_themed_starter)
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Gerar deck temático', str(exc), parent=self)

    def _save_themed_starter(self, ids, label):
        rules = self._edit()
        profiles = rules.setdefault('iniciais', {})
        name, suffix = f'Deck {label}', 2
        while name in profiles:
            name = f'Deck {label} {suffix}'
            suffix += 1
        profiles[name] = {'peso': 1, 'cartas': list(ids), 'pools': []}
        self._commit(rules, f'Perfil {name} salvo.')
        self.starter.set(name)
        self._refresh_profiles()

    def _use_generated_deck(self, editor, ids, stock):
        profile = {'cartas': list(ids), 'pools': []}
        if stock:
            rules = self._edit()
            profiles = rules.setdefault('iniciais', {})
            name = 'Deck inicial gerado'
            suffix = 2
            while name in profiles:
                name = f'Deck inicial gerado {suffix}'
                suffix += 1
            profiles[name] = {'peso': 1, **profile}
            self._commit(rules, f'Perfil {name} salvo.')
            self.starter.set(name)
            self._refresh_profiles()
            return
        editor.load(self.cards, profile)
        self.status.set('Deck gerado no editor. Salve quando terminar os ajustes.')
        self.studio.notify(f'Deck gerado com {len(ids)} cartas.')

    def _refresh_campaign_badge(self):
        from .campaign_generator import campaign_label
        opponent = self._duel_id()
        saved = (self.rules.get('duelistas', {}).get(str(opponent), {})
                 .get('campanha_dificil', {}))
        caption = campaign_label(opponent)
        if saved:
            caption = f"{saved.get('nivel', caption.split('/5')[0])}/5 · {saved.get('foco', 'Fusão')}"
        self.campaign_badge_text.set(caption)

    def _campaign_options(self):
        """Escolha explícita entre os 39 rivais ou apenas o rival selecionado."""
        dialog = tk.Toplevel(self)
        dialog.title('Campanha difícil — Gerador de decks')
        dialog.transient(self.winfo_toplevel())
        dialog.resizable(False, False)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Gerar Decks Difíceis (3/5 → 5/5)',
                  font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(0, 8))
        mode = tk.StringVar(value='all')
        custom = tk.BooleanVar(value=False)
        ttk.Radiobutton(body, text='Gerar todos os 39 oponentes', variable=mode,
                        value='all').pack(anchor='w', pady=4)
        ttk.Radiobutton(body, text=f'Regenerar apenas {self.duelist.get().split("[")[0].strip()}',
                        variable=mode, value='one').pack(anchor='w', pady=4)
        ttk.Checkbutton(body, text='Usar também cartas customizadas #723+ (somente Studio)',
                        variable=custom).pack(anchor='w', pady=(10, 5))
        ttk.Label(body, text='Padrão: cartas PS1 originais e compatibilidade BIN/CUE.\n'
                  'ATK/DEF dos materiais: até 1500; fusões podem superar 3000.\n'
                  'Os efeitos, fusões e equipamentos vêm do projeto carregado.',
                  foreground=MUTED, justify='left').pack(anchor='w', pady=8)
        choice = []
        commands = ttk.Frame(body)
        commands.pack(fill='x', pady=(12, 0))
        def complete():
            choice.append((mode.get(), custom.get()))
            dialog.destroy()
        ttk.Button(commands, text='Cancelar', command=dialog.destroy).pack(side='right')
        ttk.Button(commands, text='Gerar', style='Accent.TButton',
                   command=complete).pack(side='right', padx=6)
        dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
        dialog.wait_window()
        return choice[0] if choice else None

    def generate_hard_campaign(self):
        """Geração atômica: valida todos os decks antes de salvar o projeto."""
        if self.project is None or self.studio._extract_running:
            return
        options = self._campaign_options()
        if options is None:
            return
        mode, allow_custom = options
        try:
            from .campaign_generator import generate_campaign_deck
            self.refresh_catalog()
            _, _, equips, rituals = base_tables(self.project)
            fusions, equips, _ = match_recipes(self.project, equips, rituals)
            copies = int(self.project.metadata.get('ps1_deck_global_limit', 3))
            trap_thresholds = {int(cid): int(value) for cid, value
                               in self.project.metadata.get('ps1_trap_thresholds', {}).items()}
            opponents = list(range(1, 40)) if mode == 'all' else [self._duel_id()]
            results = {}
            self.configure(cursor='watch')
            for opponent in opponents:
                self.status.set(f'Planejando e validando {opponent:02d}/39...')
                self.update_idletasks()
                generated = generate_campaign_deck(
                    self.cards, self.project.effects, fusions, equips, opponent,
                    default_copies=copies, ps1_only=not allow_custom,
                    trap_thresholds=trap_thresholds)
                profile = normalize_rules(
                    {'duelistas': {str(opponent): {'deck': generated.profile}}},
                    self.cards)['duelistas'][str(opponent)]['deck']
                deal_deck(profile, self.cards, self.project.effects,
                          default_copies=copies)
                results[opponent] = (generated, profile)
            self.configure(cursor='')
            warnings = list(dict.fromkeys(
                note for generated, _ in results.values() for note in generated.notes
            ))
            effects_count = sum(generated.effect_monsters for generated, _ in results.values())
            lines = [
                f'{len(results)} deck(s), todos com 40 posições ponderadas e peso total 2048.',
                f'{effects_count} posições de monstros com efeito (na composição projetada).',
                'IDs #723+ só entram no modo Studio, sem exportação nativa ao PS1.',
                'A ação substitui os decks escolhidos, NÃO altera cartas, efeitos ou fusões.',
                'Um backup do projeto será feito ao salvar.',
            ]
            if warnings:
                lines.append('\nAvisos: ' + ' | '.join(warnings[:4]))
            lines.append('\nConfirmar gravação dos novos decks no projeto aberto?')
            if not messagebox.askyesno('Validar campanha difícil',
                                       '\n'.join(lines), parent=self):
                self.status.set('Geração cancelada; nenhum deck foi substituído.')
                return
            rules = self._edit()
            duelists = rules.setdefault('duelistas', {})
            for opponent, (generated, profile) in results.items():
                duelist = duelists.setdefault(str(opponent), {})
                duelist['deck'] = profile
                duelist['campanha_dificil'] = {
                    'nivel': f'{generated.difficulty:.1f}',
                    'foco': generated.focus,
                    'efeitos': generated.effect_monsters,
                    'fusao_max_atk': generated.max_fusion_atk,
                    'customizadas': allow_custom,
                    'deck_fixo_ps1': generated.fixed_for_ps1,
                    'pesos_planejados': (generated.weights
                                        if generated.fixed_for_ps1 else {}),
                }
                if duelist.get(DROP_FROM_DECK):
                    candidates = (set(profile['cartas']) if profile['cartas']
                                  else set(profile['pools'][0]['pesos']))
                    current = duelist.setdefault(DECK_DROP_WEIGHTS, {})
                    for group in DROP_GROUPS:
                        original = current.get(group, {})
                        current[group] = {
                            cid: original.get(cid, 1) for cid in sorted(candidates)
                            if original.get(cid, 1) > 0
                        } or {cid: 1 for cid in sorted(candidates)}
            # Descarte de prévias antigas ANTES da atualização dos controles.
            self._opponent_drafts.clear()
            self._loaded_opponent = None
            self._commit(rules, f'{len(results)} deck(s) difícil(is) gerado(s) com sucesso.')
            self._load_duelist()
        except (ModError, ValueError, OSError, KeyError) as exc:
            messagebox.showerror('Campanha difícil', str(exc), parent=self)
            self.status.set('Falha ao gerar campanha: ' + str(exc))
        finally:
            self.configure(cursor='')

    def create_deck_from_original_iso(self):
        """Restaura o deck de 40 sorteios da ISO, sem converter pesos em cópias.

        Um perfil original sem override usa o próprio WA_MRG no PS1. Isso
        preserva exatamente os pools, inclusive os que têm poucas cartas.
        """
        if not self.project or self.studio._extract_running:
            return
        opponent = self._duel_id()
        try:
            original = original_opponent_profile(self.project, opponent)
            summary = original_deck_summary(original)
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Deck da ISO original', str(exc), parent=self)
            return

        popup = tk.Toplevel(self)
        popup.title(f'Deck original da ISO — {self.duelist.get()}')
        popup.geometry('780x620')
        popup.minsize(650, 460)
        popup.transient(self.winfo_toplevel())
        popup.grab_set()
        body = ttk.Frame(popup, padding=15)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Recriar deck com os pesos originais da ISO',
                  font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Label(body, text=(
            f"Oponente #{opponent:02d} · {summary['cartas_distintas']} cartas distintas "
            f"· {summary['compras']} compras · peso total {summary['peso_total']}"
        )).pack(anchor='w', pady=(7, 3))
        warning = ('Atenção: a soma desta ISO não é 2048. Os pesos serão '
                   'preservados exatamente como foram extraídos.'
                   if summary['peso_total'] != POOL_TOTAL else
                   'A soma dos pesos corresponde à tabela PS1 (2048).')
        ttk.Label(body, text=warning, foreground=MUTED,
                  wraplength=720).pack(anchor='w', pady=(0, 6))
        table = ttk.Frame(body)
        table.pack(fill='both', expand=True, pady=6)
        tree = ttk.Treeview(table, columns=('id', 'nome', 'peso', 'chance'),
                            show='headings', height=14)
        for key, title, width in (
                ('id','ID',65), ('nome','Nome da carta',380),
                ('peso','Peso na ISO',110), ('chance','Chance por sorteio',140)):
            tree.heading(key, text=title)
            tree.column(key, width=width, stretch=key=='nome')
        scroll=ttk.Scrollbar(table, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        total=summary['peso_total']
        for cid, weight in summary['pesos_originais'].items():
            tree.insert('', 'end', iid=str(cid), values=(
                f'{cid:03d}', display_name(cid, self.cards),
                weight, f'{100*weight/total:.3f}%',
            ))
        ttk.Label(body, text=(
            'Criar substitui o deck deste oponente no projeto, após confirmação. '
            'O BIN/CUE original e os pesos da ISO não serão modificados. '
            'Ao gerar o jogo, sem override, o PS1 usa sua tabela de deck original. '
            'As edições de drops de rank, cartas, efeitos e fusões são preservadas.'
        ), wraplength=720, foreground=MUTED).pack(anchor='w', pady=(5, 7))
        actions=ttk.Frame(body)
        from .ui_shell import pin_bottom
        pin_bottom(actions, pady=(6, 0))
        def confirm():
            try:
                # Releitura antes de salvar evita aplicar tabelas alteradas
                # entre a abertura da janela e a confirmação.
                if self.project is not self.studio.project or self._duel_id() != opponent:
                    raise ModError('O projeto/oponente mudou. Abra a prévia novamente.')
                latest=original_opponent_profile(self.project, opponent)
                if latest != original:
                    raise ModError('A extração original mudou. Confira a nova prévia antes de salvar.')
                rules=restored_rules(self._edit(), opponent)
                # Não carregar o rascunho anterior depois de salvar; em caso
                # de falha no disco, devolver o editor ao estado anterior.
                old_draft = self._opponent_drafts.pop(opponent, None)
                old_loaded = self._loaded_opponent
                self._loaded_opponent = None
                try:
                    self._commit(rules, f'Deck original do oponente #{opponent:02d} recriado: '
                                        f"{summary['cartas_distintas']} IDs e 40 compras.")
                except Exception:
                    if old_draft is not None:
                        self._opponent_drafts[opponent] = old_draft
                    self._loaded_opponent = old_loaded
                    raise
                self._load_duelist()
                self.opponent_deck.tabs.select(self.opponent_deck.pool_pane)
                self.opponent_deck.feedback.set(
                    'Deck da ISO original carregado com pesos exatos. '
                    'Para personalizá-lo, altere os pesos e clique Salvar deck.')
            except (ModError, ValueError, OSError) as exc:
                messagebox.showerror('Deck da ISO original', str(exc), parent=popup)
                return
            popup.destroy()
        ttk.Button(actions, text='Cancelar', command=popup.destroy).pack(side='right')
        ttk.Button(actions, text='Criar deck da ISO original', style='Accent.TButton',
                   command=confirm).pack(side='right', padx=(0, 8))
        popup.protocol('WM_DELETE_WINDOW', popup.destroy)
        popup.bind('<Escape>', lambda _event:popup.destroy())
        popup.wait_window()

    def save_opponent(self):
        try:
            rules = self._edit()
            opponent = self._duel_id()
            old_candidates = deck_drop_candidates(rules, self.pools, opponent, effects=self.project.effects)
            duel = self._selected_duelist(rules)
            duel['deck'] = self.opponent_deck.profile()
            if duel.get(DROP_FROM_DECK):
                new_candidates = deck_drop_candidates(rules, self.pools, opponent, effects=self.project.effects)
                if not new_candidates:
                    raise ModError('O deck deve conter cartas para manter drops ponderados.')
                store = duel.setdefault(DECK_DROP_WEIGHTS, {})
                for group in DROP_GROUPS:
                    previous = store.get(group, {cid: 1 for cid in old_candidates})
                    # Preservar pesos dos IDs mantidos e exclusões anteriores.
                    # Cartas recém-incluídas recebem peso inicial 1.
                    updated = {cid: weight for cid, weight in previous.items()
                               if cid in new_candidates}
                    updated.update({cid: 1 for cid in new_candidates - old_candidates})
                    if not updated:
                        updated = {cid: 1 for cid in new_candidates}
                    store[group] = updated
            rules = normalize_rules(rules, self.cards)
            profile = self._selected_duelist(rules)['deck']
            # Salvar uma cópia idêntica aos pesos de origem deve conservar
            # a leitura retail, sem injetar um patch redundante no WA do PS1.
            try:
                original = original_opponent_profile(self.project, opponent)
            except ModError:
                original = None
            inherited = original is not None and is_original_deck(profile, original)
            if inherited:
                rules = restored_rules(rules, opponent)
            elif profile['cartas'] or profile['pools']:
                copies = int(self.project.metadata.get('ps1_deck_global_limit', 3))
                deal_deck(profile, self.cards, self.project.effects, default_copies=copies)
            count = len(profile['cartas']) + sum(pool['compras'] for pool in profile['pools'])
            caption = (f'Deck original da ISO preservado com {count}/{MAX_DECK} cartas.'
                       if inherited else f'Deck do oponente salvo com {count}/{MAX_DECK} cartas.')
            self._commit(rules, caption)
            pending_slot = ps1_supports_god24(self.project) and not profile['pools'] and count < MAX_DECK
            self.opponent_deck.feedback.set('Complete as 40 cartas fixas para gerar o BIN/CUE.' if pending_slot else '')
            if self.use_deck_drops.get():
                self._render_deck_drops()
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Deck do oponente', str(exc), parent=self)

    def _add_starter(self):
        if not self.project:
            return
        name = simpledialog.askstring('Deck inicial', 'Nome do perfil', parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        try:
            rules = self._edit()
            profiles = rules.setdefault('iniciais', {})
            if name == STOCK_STARTER or name in profiles:
                raise ModError('Já existe um perfil com esse nome.')
            profiles[name] = {'peso': 1, 'cartas': [], 'pools': []}
            self._commit(rules, f'Perfil {name} criado.')
            self.starter.set(name)
            self._refresh_profiles()
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Deck inicial', str(exc), parent=self)

    def _delete_starter(self):
        if self.starter.get() == STOCK_STARTER:
            return
        try:
            rules = self._edit()
            rules.setdefault('iniciais', {}).pop(self.starter.get(), None)
            self._commit(rules, 'Perfil de deck inicial excluído.')
            self._refresh_profiles()
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Deck inicial', str(exc), parent=self)

    def save_starter(self):
        try:
            rules = self._edit()
            profile = self.starter_deck.profile()
            name = self.starter.get()
            if profile['cartas'] or profile['pools']:
                profile = normalize_rules({'iniciais': {name: profile}}, self.cards)['iniciais'][name]
                copies = int(self.project.metadata.get('ps1_deck_global_limit', 3))
                deal_deck(profile, self.cards, self.project.effects, default_copies=copies)
            if name == STOCK_STARTER:
                rules['pools_iniciais_ps1'] = profile['pools']
            else:
                profile['peso'] = self.starter_weight.get()
                rules.setdefault('iniciais', {})[name] = profile
            self._commit(rules, 'Deck inicial salvo.')
            self.starter_deck.feedback.set('')
            self._starter_baseline = self.starter_deck.snapshot()
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Deck inicial', str(exc), parent=self)

    def _load_starter_disc(self):
        if not self.project or self.studio._extract_running:
            return
        source = filedialog.askopenfilename(title='Imagem BIN/CUE do projeto',
                                            filetypes=[('PlayStation', '*.bin *.cue')], parent=self)
        if not source:
            return
        from .ps1_mod import import_starter_tables
        try:
            import_starter_tables(self.project, Path(source))
            self.refresh()
            self.status.set('✓ Pools iniciais da imagem carregados.')
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Pools iniciais', str(exc), parent=self)

    def save_lp(self):
        try:
            from .core import positive_int
            value = positive_int(self.mod_lp.get(), 'LP inicial do mod')
            rules = self._edit()
            rules['lp_inicial'] = value
            # Elimina fontes antigas que antes criavam LP diferente para cada oponente.
            rules.pop('lp_jogador', None)
            for duelist in rules.get('duelistas', {}).values():
                duelist.pop('lp', None)
            self._commit(rules, f'{value} LP iniciais configurados para jogador e todos os oponentes.')
            # O patch experimental antigo não pode sobrescrever a regra global.
            self.project.metadata.pop('ps1_starting_lp', None)
            self.project.metadata.pop('studio_initial_lp', None)
            self.project.save()
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Config. MOD — Life Points', str(exc), parent=self)

    def save_ps1_ai(self):
        try:
            value = self.ps1_ai_modes.get(self.ps1_ai_choice.get())
            if value is None:
                raise ModError('Escolha um modo para a IA do PlayStation 1.')
            rules = self._edit()
            rules['ia_ps1'] = value
            self._commit(rules, 'IA PS1: ' +
                         (f'{self.ps1_ai_choice.get()}. Recrie o BIN/CUE para ativar.' if value != 'normal'
                          else 'Normal. Recrie o BIN/CUE para restaurar.'))
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Config. MOD — IA PlayStation 1', str(exc), parent=self)

    def start_match(self):
        if not self.project or self.studio._extract_running:
            return
        from .duel_gui import MatchDialog
        from .duel_match import make_match
        try:
            self.studio._stage_current()
            opponent = self._duel_id()
            starter = None if self.random_starter.get() else self.starter.get()
            match = make_match(self.project, self.studio.drafts, opponent, starter,
                               first='adversario' if self.opponent_first.get() else 'jogador')
            rules = normalize_rules(self.project.metadata.get(CONFIG_KEY, {}), self.cards)
            MatchDialog(self.studio, match, opponent, rules, self.pools, project=self.project,
                        collection_changed=self.collection_changed)
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Simular duelo', str(exc), parent=self)


class NewCardDialog(tk.Toplevel):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.project = studio.project
        self.template = studio.selected_id
        self.title('Nova carta')
        self.transient(studio)
        pane = ttk.Frame(self, padding=14)
        pane.pack(fill='both', expand=True)
        self.card_id = tk.StringVar(value=str(self.project.next_card_id()))
        ttk.Label(pane, text='ID livre da carta').pack(anchor='w')
        ttk.Entry(pane, textvariable=self.card_id, width=17).pack(anchor='w', fill='x')
        self.name = tk.StringVar()
        self.kind = tk.StringVar(value=TYPE_NAMES[0])
        self.clone = tk.BooleanVar()
        ttk.Label(pane, text='Nome').pack(anchor='w', pady=(5, 0))
        name = ttk.Entry(pane, width=34, textvariable=self.name)
        name.pack(fill='x')
        ttk.Label(pane, text='Tipo').pack(anchor='w', pady=(5, 0))
        ttk.Combobox(pane, state='readonly', textvariable=self.kind, values=TYPE_NAMES).pack(fill='x')
        ttk.Label(pane, text='Modelo de comportamento / animação no PS1').pack(anchor='w', pady=(7, 0))
        self.native_model = tk.StringVar()
        self.native_choices = ttk.Combobox(pane, state='readonly', textvariable=self.native_model, width=44)
        self.native_choices.pack(fill='x')
        ttk.Label(pane, text='IDs #723–#740: expansão PS1 experimental. O modelo fornece o comportamento; '
                  'a carta conserva nome, atributos e arte próprios.', foreground=MUTED,
                  wraplength=340).pack(anchor='w', pady=(3, 5))
        if self.template is not None:
            card = self.project.get(self.template)
            typ = int(card['tipo_id'])
            self.kind.set(TYPE_NAMES[typ] if 0 <= typ < len(TYPE_NAMES) else TYPE_NAMES[0])
            ttk.Checkbutton(pane, text=f'Usar #{self.template} como modelo de atributos',
                            variable=self.clone).pack(anchor='w', pady=7)
        self.kind.trace_add('write', lambda *_: self._native_models())
        self._native_models()
        self.feedback = tk.StringVar()
        ttk.Label(pane, textvariable=self.feedback, foreground=ACCENT, wraplength=320).pack(anchor='w', pady=(5, 0))
        actions = ttk.Frame(pane)
        from .ui_shell import pin_bottom
        pin_bottom(actions, pady=(6, 0))
        ttk.Button(actions, text='Cancelar', command=self.destroy).pack(side='left')
        ttk.Button(actions, text='Criar e salvar', style='Accent.TButton', command=self.create).pack(side='right')
        self.bind('<Return>', lambda _e: self.create())
        self.bind('<Escape>', lambda _e: self.destroy())
        self.grab_set()
        name.focus_set()

    def _native_models(self):
        from .ps1_expansion import model_candidates, native_model
        kind = TYPE_NAMES.index(self.kind.get())
        candidates = model_candidates(self.project, kind)
        self.native_choices['values'] = [f'#{cid:03d} {display_name(cid, self.project.cards)}' for cid in candidates]
        current = self.native_model.get().split()[0].lstrip('#') if self.native_model.get() else ''
        chosen = int(current) if current.isdecimal() and int(current) in candidates else None
        if chosen is None:
            preferred = {20: 337, 21: 686, 22: 666, 23: 301}.get(kind)
            chosen = preferred if preferred in candidates else next(iter(candidates), None)
        self.native_model.set(f'#{chosen:03d} {display_name(chosen, self.project.cards)}' if chosen else '')

    def create(self):
        try:
            if self.project is not self.studio.project or self.studio._extract_running:
                raise ModError('Reabra a criação de cartas no projeto atual.')
            cid = self.project.add_card(self.template if self.clone.get() else None,
                                        name=self.name.get().strip() or None,
                                        type_id=TYPE_NAMES.index(self.kind.get()),
                                        native_model_id=int(self.native_model.get().split()[0].lstrip('#')) if self.native_model.get() else None,
                                        card_id=positive_int(self.card_id.get().strip().lstrip('#'), 'ID da carta'))
        except (ModError, ValueError, OSError) as exc:
            self.feedback.set(str(exc))
            return
        self.destroy()
        self.studio.select_new_card(cid)


class CardRelationsDialog(tk.Toplevel):
    def __init__(self, studio, cid):
        super().__init__(studio)
        self.studio, self.cid = studio, cid
        self.title(f'Relações • #{cid}')
        self.transient(studio)
        self.geometry('710x510')
        self.minsize(610, 450)
        pane = ttk.Frame(self, padding=14)
        pane.pack(fill='both', expand=True)
        tabs = ttk.Notebook(pane)
        tabs.pack(fill='both', expand=True)
        fusions, ritual, equip = [ttk.Frame(tabs, padding=9) for _ in range(3)]
        tabs.add(fusions, text='Fusões')
        tabs.add(ritual, text='Ritual')
        tabs.add(equip, text='Equipamentos')
        if cid > CARD_COUNT:
            from .ps1_expansion import model_candidates, native_model
            native = ttk.Frame(tabs, padding=9)
            tabs.add(native, text='Modelo PS1')
            ttk.Label(native, text='Comportamento original e animação usados pela nova carta. '
                      'As edições da carta e seu ID permanecem independentes.', wraplength=580).pack(anchor='w')
            self.native_template = tk.StringVar()
            candidates = model_candidates(studio.project, studio.project.get(cid)['tipo_id'])
            options = [f'#{i:03d} {display_name(i, studio.project.cards)}' for i in candidates]
            selector = ttk.Combobox(native, state='readonly', values=options, textvariable=self.native_template, width=50)
            selector.pack(fill='x', pady=9)
            try:
                selected = native_model(studio.project, cid)
                self.native_template.set(options[candidates.index(selected)])
            except ModError:
                pass
            self.native_feedback = tk.StringVar()
            ttk.Label(native, textvariable=self.native_feedback, foreground=ACCENT).pack(anchor='w')
            ttk.Button(native, text='Salvar modelo PS1', style='Accent.TButton', command=self._save_native_model).pack(anchor='e')
        self.fusion_tree = ttk.Treeview(fusions, columns=('a','b','result'), show='headings', height=6)
        for key, caption in zip(('a','b','result'), ('Material 1','Material 2','Resultado')):
            self.fusion_tree.heading(key, text=caption)
            self.fusion_tree.column(key, width=180)
        self.sort_fusions = sortable_columns(
            self.fusion_tree, raw_values=lambda item, key: int(self.fusion_tree.set(item, key).split()[0][1:]))
        self.fusion_tree.pack(fill='both', expand=True)
        self.fusion_tree.bind('<<TreeviewSelect>>', self._select_fusion)
        fusion_edit = ttk.Frame(fusions)
        fusion_edit.pack(fill='x', pady=6)
        self.fusion_values = []
        for caption, initial in (('Material 1', ''), ('Material 2', ''), ('Resultado', str(cid))):
            cell = ttk.Frame(fusion_edit)
            cell.pack(side='left', padx=(0, 5), fill='x', expand=True)
            ttk.Label(cell, text=caption).pack(anchor='w')
            variable = tk.StringVar(value=initial)
            ttk.Entry(cell, textvariable=variable, width=15).pack(fill='x')
            self.fusion_values.append(variable)
        self.fusion_status = tk.StringVar()
        if ps1_supports_god24(studio.project):
            self.fusion_status.set('Receitas #001–#740 entram na cópia Drop x15; IDs adicionais usam a expansão experimental.')
        else:
            self.fusion_status.set('Receitas salvas ficam disponíveis no simulador do Studio.')
        ttk.Label(fusions, textvariable=self.fusion_status, foreground=MUTED,
                  wraplength=540).pack(anchor='w', pady=(0, 5))
        ttk.Button(fusions, text='Salvar fusão', style='Accent.TButton', command=self._save_fusion).pack(side='right')
        ttk.Button(fusions, text='Remover alteração', command=lambda: self._save_fusion(remove=True)).pack(side='right', padx=5)
        self.tributes = tk.StringVar()
        self.ritual_result = tk.StringVar()
        ttk.Label(ritual, text='Tributos em campo (IDs separados por vírgula)').pack(anchor='w')
        ttk.Entry(ritual, textvariable=self.tributes).pack(fill='x', pady=(3, 8))
        ttk.Label(ritual, text='ID do monstro invocado').pack(anchor='w')
        ttk.Entry(ritual, textvariable=self.ritual_result).pack(fill='x', pady=(3, 8))
        ttk.Button(ritual, text='Salvar ritual', style='Accent.TButton', command=self._save_ritual).pack(anchor='e')
        self.equip_targets = tk.StringVar()
        bonus_row = ttk.Frame(equip)
        bonus_row.pack(fill='x', pady=(0, 8))
        from .ps1_equip_bonus import BONUS_MAX, default_bonus, equip_bonuses
        current_bonus = equip_bonuses(studio.project).get(cid)
        self.equip_bonus = tk.StringVar(value=str(current_bonus if current_bonus is not None
                                                  else default_bonus(cid)))
        ttk.Label(bonus_row, text='Bônus de ATK/DEF no PS1:').pack(side='left')
        ttk.Spinbox(bonus_row, from_=0, to=BONUS_MAX, increment=50, width=7,
                    textvariable=self.equip_bonus).pack(side='left', padx=6)
        ttk.Button(bonus_row, text='Salvar bônus', command=self._save_equip_bonus).pack(side='left')
        ttk.Button(bonus_row, text='Original', command=lambda: self._save_equip_bonus(reset=True)).pack(side='left', padx=4)
        self.equip_bonus_status = tk.StringVar(value=('Bônus personalizado.' if current_bonus is not None else
                                                      f'Original: +{default_bonus(cid)}.'))
        ttk.Label(bonus_row, textvariable=self.equip_bonus_status, foreground='#5a6b7d').pack(side='left', padx=6)

        ttk.Label(equip, text='Monstros equipáveis: busque e selecione vários (Ctrl/Shift + clique)').pack(anchor='w')
        search_row = ttk.Frame(equip)
        search_row.pack(fill='x', pady=(3, 3))
        self.equip_query = tk.StringVar()
        query = ttk.Entry(search_row, textvariable=self.equip_query)
        query.pack(side='left', fill='x', expand=True)
        query.bind('<KeyRelease>', lambda _e: self._render_equip_list())
        ttk.Button(search_row, text='Selecionar visíveis', command=lambda: self._select_equip_visible(True)).pack(side='left', padx=(5, 0))
        ttk.Button(search_row, text='Limpar visíveis', command=lambda: self._select_equip_visible(False)).pack(side='left', padx=(5, 0))
        self.equip_list = tk.Listbox(equip, selectmode='extended', height=9, exportselection=False)
        self.equip_list.pack(fill='both', expand=True)
        self.equip_list.bind('<<ListboxSelect>>', self._equip_list_changed)
        self._equip_rows, self._equip_selected = [], set()
        self.equip_count = tk.StringVar()
        ttk.Label(equip, textvariable=self.equip_count).pack(anchor='w')
        ttk.Label(equip, text='IDs (também editável à mão, separados por vírgula)').pack(anchor='w', pady=(4, 0))
        ttk.Entry(equip, textvariable=self.equip_targets).pack(fill='x', pady=(3, 8))
        ttk.Button(equip, text='Salvar alvos', style='Accent.TButton', command=self._save_equip).pack(anchor='e')
        typ = int(studio.project.get(cid)['tipo_id'])
        if typ == 22:
            tabs.select(ritual)
        if typ == 23:
            tabs.select(equip)
        self._refresh()

    def _save_native_model(self):
        try:
            value = int(self.native_template.get().split()[0].lstrip('#'))
            self.studio.project.set_card(self.cid, {'modelo_ps1_id': value})
        except (ModError, ValueError, IndexError, OSError) as exc:
            self.native_feedback.set(str(exc) or 'Selecione um modelo compatível.')
            return
        self.native_feedback.set('Modelo PS1 salvo.')

    def _refresh(self):
        pr = self.studio.project
        _, _, equips, rituals = base_tables(pr)
        fusions, equips, rituals = match_recipes(pr, equips, rituals)
        cards = pr.cards
        self.fusion_tree.delete(*self.fusion_tree.get_children())
        for (a, b), result in fusions.items():
            if self.cid in (a,b,result):
                self.fusion_tree.insert('', 'end', iid=f'{a},{b},{result}',
                    values=[f'#{n} {display_name(n, cards)}' for n in (a,b,result)])
        self.sort_fusions()
        if self.cid in rituals:
            tribute, result = rituals[self.cid]
            self.tributes.set(', '.join(map(str, tribute)))
            self.ritual_result.set(str(result))
        if self.cid in equips:
            self.equip_targets.set(', '.join(map(str, sorted(equips[self.cid]))))
        self._equip_selected = set(equips.get(self.cid, ()))
        self._render_equip_list()

    def _select_fusion(self, _event):
        selected = self.fusion_tree.selection()
        if selected:
            for variable, value in zip(self.fusion_values, selected[0].split(',')):
                variable.set(value)

    def _change(self, scope, apply):
        try:
            project = self.studio.project
            rules = deepcopy(project.metadata.get(CONFIG_KEY, {}))
            entries = rules.setdefault('receitas', {}).setdefault(scope, {})
            status = apply(entries)
            save_rules(project, rules)
            self.studio.mod_editor.refresh()
            self.studio._update_status(status or 'Relações salvas.')
            if scope == 'fusoes' and status:
                self.fusion_status.set(status)
            self._refresh()
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Relações da carta', str(exc), parent=self)

    def _save_fusion(self, remove=False):
        from .ps1_mod import fusion_uses_original_ids

        def edit(entries):
            a, b = sorted(positive_int(v.get(), 'Material') for v in self.fusion_values[:2])
            key = f'{a},{b}'
            if remove:
                entries.pop(key, None)
                return 'Alteração da fusão removida.'
            result = positive_int(self.fusion_values[2].get(), 'Resultado')
            entries[key] = result
            project = self.studio.project
            label = f'#{a:03d} + #{b:03d} → #{result:03d}'
            if ps1_supports_god24(project) and fusion_uses_original_ids(project.cards, a, b, result):
                return f'{label} salva. Gere outra cópia BIN/CUE para aplicar.'
            return f'{label} salva no simulador.'

        self._change('fusoes', edit)

    def _save_ritual(self):
        self._change('rituais', lambda entries: entries.update({str(self.cid): {
            'tributos': parse_card_ids(self.tributes.get(), maximum=5),
            'resultado': positive_int(self.ritual_result.get(), 'Resultado')}}))

    def _monster_rows(self):
        cards = self.studio.project.cards
        rows = []
        for cid in sorted(cards):
            card = self.studio.project.get(cid)
            if int(card.get('tipo_id', 0)) < 20:
                type_name = TYPE_NAMES[int(card['tipo_id'])] if int(card['tipo_id']) < len(TYPE_NAMES) else ''
                rows.append((cid, f"#{cid:03d}  {display_name(cid, cards)}  · {type_name}"))
        return rows

    def _render_equip_list(self):
        query = self.equip_query.get().casefold().lstrip('#').strip()
        self._equip_rows = [row for row in self._monster_rows() if not query or query in row[1].casefold()]
        self.equip_list.delete(0, 'end')
        for index, (cid, label) in enumerate(self._equip_rows):
            self.equip_list.insert('end', label)
            if cid in self._equip_selected:
                self.equip_list.selection_set(index)
        self.equip_count.set(f'{len(self._equip_selected)} monstro(s) selecionado(s)')

    def _equip_list_changed(self, _event=None):
        visible = {cid for cid, _ in self._equip_rows}
        chosen = {self._equip_rows[i][0] for i in self.equip_list.curselection()}
        self._equip_selected = (self._equip_selected - visible) | chosen
        self.equip_targets.set(', '.join(map(str, sorted(self._equip_selected))))
        self.equip_count.set(f'{len(self._equip_selected)} monstro(s) selecionado(s)')

    def _select_equip_visible(self, selected):
        if selected:
            self.equip_list.selection_set(0, 'end')
        else:
            self.equip_list.selection_clear(0, 'end')
        self._equip_list_changed()

    def _save_equip_bonus(self, reset=False):
        from .ps1_equip_bonus import default_bonus, set_equip_bonus
        try:
            value = None if reset else int(self.equip_bonus.get().strip())
            set_equip_bonus(self.studio.project, self.cid, value)
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Bônus do equipamento', str(exc) or 'Digite um número inteiro.', parent=self)
            return
        if value is None:
            self.equip_bonus.set(str(default_bonus(self.cid)))
            self.equip_bonus_status.set(f'Original: +{default_bonus(self.cid)}.')
        else:
            self.equip_bonus_status.set(f'+{value} salvo. Gere um BIN/CUE novo para aplicar.')

    def _save_equip(self):
        self._change('equipamentos', lambda entries: entries.update({str(self.cid):
            parse_card_ids(self.equip_targets.get(), maximum=len(self.studio.project.cards))}))
