"""Tkinter editors for mod distributions and Studio card relations."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .core import ModError, positive_int, simulation_nonnegative_int
from .duel_engine import MAX_DECK, parse_card_ids
from .expanded import display_name
from .gui import ACCENT, MUTED, ROW_ALT, compact_number
from .mod_data import (
    CONFIG_KEY, DROP_FROM_DECK, DROP_GROUPS, MONSTER_TYPES, RANK_GROUPS, STOCK_STARTER,
    base_tables, deal_deck, drop_weights, drops_from_deck, duelist_profile, match_recipes,
    normalize_rules, save_rules, starting_life, validate_deck,
)
from .tables import DUELIST_NAMES_REFERENCE, TYPE_NAMES

WEIGHT_COLUMNS = ('carta', 'nome', 'peso', 'chance')


def _probability(weight, total):
    value = weight * 1_000_000 // total if total else 0
    return f'{value//10000},{value%10000:04d}%'


class WeightTable(ttk.Frame):
    """Pick cards by name or ID and inspect normalized odds for a weight table."""
    def __init__(self, parent):
        super().__init__(parent)
        self.cards = {}
        self.labels = {}
        self.weights = {}
        self.changed = None
        edit = ttk.Frame(self)
        edit.pack(fill='x', pady=(0, 5))
        self.selected = tk.StringVar()
        self.card = ttk.Combobox(edit, textvariable=self.selected, width=28)
        self.card.pack(side='left', fill='x', expand=True)
        self.card.bind('<KeyRelease>', self._search)
        self.weight = tk.StringVar(value='1')
        ttk.Label(edit, text='Peso').pack(side='left', padx=(7, 3))
        ttk.Entry(edit, textvariable=self.weight, width=8).pack(side='left', padx=(0, 4))
        ttk.Button(edit, text='Aplicar', command=self._apply).pack(side='left')
        ttk.Button(edit, text='Remover', style='Danger.TButton',
                   command=self._remove).pack(side='left', padx=(4, 0))
        holder = ttk.Frame(self)
        holder.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(holder, columns=WEIGHT_COLUMNS, show='headings', height=6)
        widths = (65, 250, 90, 105)
        for key, label, width in zip(WEIGHT_COLUMNS, ('ID', 'Carta', 'Peso', 'Probabilidade'), widths):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=55, stretch=key == 'nome')
        self.tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(holder, command=self.tree.yview)
        scroll.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>', self._select)
        self.summary = ttk.Label(self, foreground=MUTED)
        self.summary.pack(anchor='w', pady=(3, 0))

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
        keep = self.tree.selection()
        top = self.tree.yview()[0]
        self.tree.delete(*self.tree.get_children())
        total = sum(self.weights.values())
        self.tree.tag_configure('stripe', background=ROW_ALT)
        for index, (cid, weight) in enumerate(sorted(self.weights.items())):
            self.tree.insert('', 'end', iid=str(cid), values=(
                compact_number(cid), display_name(cid, self.cards), compact_number(weight),
                _probability(weight, total)), tags=('stripe',) if index % 2 else ())
        if keep and self.tree.exists(keep[0]):
            self.tree.selection_set(keep[0])
        self.tree.yview_moveto(top)
        self.summary.configure(text=f'{len(self.weights)} cartas · peso total {compact_number(total)}')

    def _search(self, _event=None):
        query = self.selected.get().strip().casefold()
        self.card.configure(values=[label for label in self.labels if query in label.casefold()])

    def _select(self, _event):
        selection = self.tree.selection()
        if selection and int(selection[0]) in self.weights:
            cid = int(selection[0])
            self.selected.set(f'#{cid} — {display_name(cid, self.cards)}')
            self.weight.set(str(self.weights[cid]))

    def _apply(self):
        try:
            raw = self.selected.get().strip()
            cid = self.labels.get(raw) or positive_int(raw.lstrip('#').split(' — ', 1)[0], 'Carta')
            if cid not in self.cards:
                raise ModError('Escolha um ID ou um nome existente no catálogo.')
            amount = simulation_nonnegative_int(self.weight.get(), 'Peso')
            self._set(cid, amount)
        except (ModError, OSError, ValueError) as exc:
            messagebox.showerror('Tabela de pesos', str(exc), parent=self)

    def _remove(self):
        if self.tree.selection():
            try:
                self._set(int(self.tree.selection()[0]), 0)
            except (ModError, OSError, ValueError) as exc:
                messagebox.showerror('Tabela de pesos', str(exc), parent=self)

    def _set(self, cid, amount):
        edited = dict(self.weights)
        if amount:
            edited[cid] = amount
        else:
            edited.pop(cid, None)
        if self.changed is not None:
            self.changed(edited)
        self.weights = edited
        self.render()


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
        self.quantity = tk.StringVar(value='1')
        self.total = tk.StringVar()
        self.feedback = tk.StringVar()
        self.loading = False

        header = ttk.Frame(self)
        header.pack(fill='x', pady=(0, 5))
        ttk.Label(header, textvariable=self.total, foreground=ACCENT).pack(side='left')
        ttk.Label(self, textvariable=self.feedback, foreground=ACCENT, wraplength=500).pack(
            side='bottom', anchor='w', pady=(3, 0))
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True)
        self.fixed_pane, self.pool_pane = (ttk.Frame(self.tabs, padding=7) for _ in range(2))
        self.tabs.add(self.fixed_pane, text='Cartas fixas')
        self.tabs.add(self.pool_pane, text='Pools ponderados')

        filters = ttk.Frame(self.fixed_pane)
        filters.pack(fill='x')
        ttk.Label(filters, text='Busca').pack(side='left', padx=(0, 5))
        search = ttk.Entry(filters, textvariable=self.query, width=17)
        search.pack(side='left', fill='x', expand=True)
        kind = ttk.Combobox(filters, textvariable=self.kind, width=14, state='readonly',
                            values=['Todos os tipos', 'Monstros', *TYPE_NAMES])
        kind.pack(side='left', padx=(5, 0))

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
        self.catalog = _tree(catalog, [('id', 'ID', 50), ('nome', 'Carta', 120),
                                       ('tipo', 'Tipo', 80)], height=5)
        self.deck = _tree(fixed, [('id', 'ID', 50), ('nome', 'Carta', 126),
                                  ('qtd', 'Cópias', 58)], height=5)
        self.catalog.bind('<Double-1>', lambda _event: self.change_card('add'))
        self.catalog.bind('<Return>', lambda _event: self.change_card('add'))
        self.catalog.bind('<<TreeviewSelect>>', self._update_buttons)
        self.deck.bind('<<TreeviewSelect>>', self._select_copy)
        self.deck.bind('<Delete>', lambda _event: self.change_card('remove'))
        search.bind('<Return>', lambda _event: self._focus_result())

        controls = ttk.Frame(self.fixed_pane)
        controls.pack(fill='x', pady=2)
        ttk.Label(controls, text='Cópias').pack(side='left', padx=(0, 4))
        ttk.Spinbox(controls, from_=1, to=MAX_DECK, width=4,
                    textvariable=self.quantity).pack(side='left', padx=(0, 5))
        self.add_btn = ttk.Button(controls, text='＋ Adicionar', style='Accent.TButton',
                                  command=lambda: self.change_card('add'))
        self.set_btn = ttk.Button(controls, text='Ajustar cópias', command=lambda: self.change_card('set'))
        self.remove_btn = ttk.Button(controls, text='− Remover', style='Danger.TButton',
                                     command=lambda: self.change_card('remove'))
        for button in (self.add_btn, self.set_btn, self.remove_btn):
            button.pack(side='left', padx=(0, 4))
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
        self.table = WeightTable(self.pool_pane)
        self.table.pack(fill='both', expand=True)

        for variable in (self.kind, self.query):
            variable.trace_add('write', lambda *_: self._render_catalog())
        self.fixed.trace_add('write', lambda *_: self._render_deck())
        self.draws.trace_add('write', lambda *_: self._render_deck())
        self._render_deck()

    def refresh_catalog(self, cards, project):
        self.cards, self.project = cards, project
        self.table.refresh_catalog(cards)
        self._render_catalog()
        self._render_deck()

    def _render_catalog(self):
        query = self.query.get().strip().casefold()
        kind = self.kind.get()
        rows = []
        for cid in sorted(self.cards):
            typ = int(self.cards[cid]['tipo_id'])
            label = TYPE_NAMES[typ] if 0 <= typ < len(TYPE_NAMES) else str(typ)
            if kind == 'Monstros' and typ not in MONSTER_TYPES:
                continue
            if kind not in ('Todos os tipos', 'Monstros') and label != kind:
                continue
            name = display_name(cid, self.cards)
            if query in name.casefold() or query in f'#{cid:03d}' or query in f'#{cid}':
                rows.append((cid, (compact_number(cid), name, label)))
        self._render_rows(self.catalog, rows)
        self._update_buttons()

    def _render_rows(self, tree, rows):
        selected = tree.selection()
        top = tree.yview()[0]
        tree.delete(*tree.get_children())
        for index, (cid, values) in enumerate(rows):
            tree.insert('', 'end', iid=str(cid), values=values,
                        tags=('stripe',) if index % 2 else ())
        if selected and tree.exists(selected[0]):
            tree.selection_set(selected[0])
        tree.yview_moveto(top)

    def _render_deck(self):
        if self.loading:
            return
        try:
            fixed = parse_card_ids(self.fixed.get(), maximum=MAX_DECK)
            pools = self._pool_slots()
            self.total.set(f'{len(fixed) + pools}/{MAX_DECK} cartas · {len(fixed)} fixas + {pools} de pools')
        except (ModError, ValueError):
            fixed = []
            self.total.set('Revise os IDs ou as compras dos pools')
        self._render_rows(self.deck, [(cid, (compact_number(cid), display_name(cid, self.cards), amount))
                                     for cid, amount in sorted(Counter(fixed).items())])
        self._update_buttons()

    def _pool_slots(self):
        amounts = [self.draws.get() if i == self.current else row['compras']
                   for i, row in enumerate(self.rows)]
        return sum(simulation_nonnegative_int(amount, 'Compras do pool') for amount in amounts)

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
        if selection:
            self.quantity.set(self.deck.set(selection[0], 'qtd'))
        self._update_buttons()

    def start_fixed_deck(self):
        self.load(self.cards, {})
        self.tabs.select(self.fixed_pane)
        self.feedback.set('Deck em branco. Adicione cartas e salve.')

    def change_card(self, action, cid=None):
        selection = self.catalog.selection() if action == 'add' else self.deck.selection()
        if cid is None and not selection:
            return
        cid = cid if cid is not None else int(selection[0])
        try:
            ids = parse_card_ids(self.fixed.get(), maximum=MAX_DECK)
            amount = positive_int(self.quantity.get(), 'Cópias') if action != 'remove' else 0
            occupied = self._pool_slots()
            if amount > MAX_DECK:
                raise ModError(f'Informe até {MAX_DECK} cópias.')
            if action != 'add':
                ids = [other for other in ids if other != cid]
            ids.extend([cid] * amount)
            if len(ids) + occupied > MAX_DECK:
                raise ModError(f'{occupied} vaga(s) de pools neste deck. Ajuste a composição para caber em {MAX_DECK} cartas.')
            meta = getattr(self.project, 'metadata', {})
            effects = getattr(self.project, 'effects', {})
            validate_deck(self.cards, effects, ids, int(meta.get('ps1_deck_global_limit', 3)))
        except (ModError, ValueError) as exc:
            self.feedback.set(str(exc))
            return
        self.fixed.set(', '.join(map(str, ids)))
        if self.deck.exists(str(cid)):
            self.deck.selection_set(str(cid))
            self.deck.see(str(cid))
        self.feedback.set(f'#{cid} atualizado. Salve o deck.')

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
            self.rows[self.current] = {'compras': self.draws.get(), 'pesos': dict(self.table.weights)}

    def _select_pool(self, _event):
        current = self.pool_combo.current()
        self._stage()
        self._show(current)

    def add_pool(self):
        self._stage()
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
            self.rows.append({'compras': self.draws.get() or '40', 'pesos': dict(self.table.weights)})
            self.current = len(self.rows) - 1
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
        self.player_lp = tk.StringVar()
        self.opponent_lp = tk.StringVar()
        self.opponent_first = tk.BooleanVar()
        self.status = tk.StringVar(value='Abra um projeto para editar as tabelas.')
        self.duelist_ids = {f'{i:02d} · {name}': i for i, name in enumerate(DUELIST_NAMES_REFERENCE) if i}
        self.rank_ids = {f'{label} (grupo PS1)': key for key, label in DROP_GROUPS.items()}
        self.rank_ids.update({rank: rank for rank in RANK_GROUPS if rank != 'B/C/D'})
        head = ttk.Frame(self)
        head.pack(fill='x', pady=(0, 8))
        ttk.Label(head, text='Duelista').pack(side='left', padx=(0, 5))
        chooser = ttk.Combobox(head, textvariable=self.duelist, state='readonly', values=list(self.duelist_ids), width=24)
        chooser.pack(side='left')
        chooser.bind('<<ComboboxSelected>>', lambda _e: self._load_duelist())
        self.password_button = ttk.Button(head, text='Passwords e baú', command=self.open_passwords)
        self.password_button.pack(side='left', padx=6)
        self.duel_button = ttk.Button(head, text='Jogar duelo', style='Accent.TButton', command=self.start_match)
        self.duel_button.pack(side='right')
        ttk.Checkbutton(head, text='Oponente começa', variable=self.opponent_first).pack(side='right', padx=8)
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True)
        self.tabs.enable_traversal()
        drop_pane, deck_pane, start_pane, lp_pane = [ttk.Frame(self.tabs, padding=9) for _ in range(4)]
        self.deck_pane = deck_pane
        for pane, name in zip((deck_pane, drop_pane, start_pane, lp_pane),
                              ('Deck do oponente', 'Drops do oponente', 'Decks iniciais', 'Life Points')):
            self.tabs.add(pane, text=name)
        self.drop_toggle = ttk.Checkbutton(drop_pane, text='Dropar Cartas do Próprio Deck',
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
        self.deck_drop_detail = ttk.Label(self.deck_drop_panel, wraplength=480, foreground=MUTED)
        self.deck_drop_detail.pack(anchor='w')
        from .mod_tools_gui import _tree
        self.deck_drop_candidates = _tree(self.deck_drop_panel, [('id', 'ID', 63), ('nome', 'Carta', 220),
                                                                ('origem', 'Origem no deck', 140)])
        self.deck_drop_candidates.bind('<Double-1>', self._open_drop_candidate)

        self.opponent_deck = DeckProfileEditor(deck_pane)
        opponent_actions = ttk.Frame(deck_pane)
        opponent_actions.pack(side='bottom', fill='x', pady=(5, 0))
        self.blank_deck_button = ttk.Button(opponent_actions, text='Novo deck fixo',
                                            command=self.opponent_deck.start_fixed_deck)
        self.blank_deck_button.pack(side='left')
        self.generate_button = ttk.Button(opponent_actions, text='Gerar Deck Aleatório',
                                          command=lambda: self.generate_deck(self.opponent_deck))
        self.generate_button.pack(side='left', padx=5)
        self.save_opponent_button = ttk.Button(opponent_actions, text='Salvar deck', style='Accent.TButton',
                                               command=self.save_opponent)
        self.save_opponent_button.pack(side='right')
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
        ttk.Button(starter_actions, text='Salvar deck inicial', style='Accent.TButton',
                   command=self.save_starter).pack(side='right')

        for caption, variable in (('LP inicial do jogador', self.player_lp),
                                  ('LP do duelista selecionado', self.opponent_lp)):
            ttk.Label(lp_pane, text=caption).pack(anchor='w', pady=(6, 3))
            ttk.Entry(lp_pane, textvariable=variable, width=34).pack(anchor='w')
        ttk.Button(lp_pane, text='Salvar LP', style='Accent.TButton', command=self.save_lp).pack(anchor='w', pady=9)
        ttk.Label(self, textvariable=self.status, foreground=ACCENT, wraplength=610).pack(anchor='w', pady=(5, 0))
        self._update_available()

    def _update_available(self):
        state = 'normal' if self.project else 'disabled'
        for button in (self.password_button, self.duel_button, self.drop_toggle, self.save_opponent_button,
                       self.generate_button, self.blank_deck_button):
            button.configure(state=state)

    def refresh(self):
        if self.project is not self.studio.project:
            self._opponent_drafts.clear()
            self._loaded_opponent = None
        else:
            self._remember_opponent()
        self.project = self.studio.project
        self._update_available()
        if self.project:
            self.cards = {cid: self.project.get(cid) for cid in self.project.cards}
            self.pools, self.stock, _, _ = base_tables(self.project)
            self.rules = normalize_rules(self.project.metadata.get(CONFIG_KEY, {}), self.cards)
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
        self._load_drop()
        if self.project:
            lp = starting_life(self.project, opponent)
            self.player_lp.set(str(lp['jogador']))
            self.opponent_lp.set(str(lp['adversario']))

    def _load_drop(self):
        active = drops_from_deck(self.rules, self._duel_id())
        self.use_deck_drops.set(active)
        if active:
            self.rank_editor.pack_forget()
            self.deck_drop_panel.pack(fill='both', expand=True)
            self._render_deck_drops()
        else:
            self.deck_drop_panel.pack_forget()
            self.rank_editor.pack(fill='both', expand=True)
            weights = drop_weights(self.rules, self.pools, self._duel_id(), self.rank_ids[self.rank.get()])
            self.drops.load(self.cards, weights)

    def _render_deck_drops(self):
        profile = duelist_profile(self.rules, self.pools, self._duel_id())
        fixed = set(profile.get('cartas', ()))
        pool = {cid for row in profile.get('pools', ()) for cid in row['pesos']}
        ids = sorted(fixed | pool)
        self.deck_drop_candidates.delete(*self.deck_drop_candidates.get_children())
        for index, cid in enumerate(ids):
            source = 'Fixa e pool' if cid in fixed and cid in pool else 'Fixa' if cid in fixed else 'Pool'
            self.deck_drop_candidates.insert('', 'end', iid=str(cid), values=(
                compact_number(cid), display_name(cid, self.cards), source),
                tags=('stripe',) if index % 2 else ())
        self.deck_drop_detail.configure(text=f'{len(ids)} candidatas na configuração salva. A vitória premia uma carta do deck efetivamente sorteado, em qualquer rank.')

    def _open_drop_candidate(self, _event):
        selection = self.deck_drop_candidates.selection()
        if selection:
            self.studio.select_card(int(selection[0]))

    def _toggle_deck_drops(self):
        try:
            rules = self._edit()
            self._selected_duelist(rules)[DROP_FROM_DECK] = self.use_deck_drops.get()
            caption = 'Drops do próprio deck ativados.' if self.use_deck_drops.get() else 'Pesos por rank restaurados.'
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
        self.refresh_catalog()
        self.studio.tabs.select(self.studio.tab_mod)
        self.tabs.select(self.deck_pane)
        self.opponent_deck.tabs.select(self.opponent_deck.fixed_pane)
        self.opponent_deck.quantity.set('1')
        self.opponent_deck.change_card('add', cid)

    def generate_deck(self, editor):
        if self.project is None or self.studio._extract_running:
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
            stock = editor is self.starter_deck and self.starter.get() == STOCK_STARTER
            DeckGeneratorDialog(
                self, self.cards, self.project.effects, fusions, equips, default_copies=copies,
                trap_thresholds=thresholds, fixed=fixed, new_starter=stock,
                use_deck=lambda ids: self._use_generated_deck(editor, ids, stock),
            )
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Gerar Deck Aleatório', str(exc), parent=self)

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

    def save_opponent(self):
        try:
            rules = self._edit()
            self._selected_duelist(rules)['deck'] = self.opponent_deck.profile()
            rules = normalize_rules(rules, self.cards)
            profile = self._selected_duelist(rules)['deck']
            if profile['cartas'] or profile['pools']:
                copies = int(self.project.metadata.get('ps1_deck_global_limit', 3))
                deal_deck(profile, self.cards, self.project.effects, default_copies=copies)
            self._commit(rules, 'Deck do oponente salvo.')
            self.opponent_deck.feedback.set('')
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
            rules = self._edit()
            rules['lp_jogador'] = self.player_lp.get()
            self._selected_duelist(rules)['lp'] = self.opponent_lp.get()
            self._commit(rules, 'LP iniciais salvos.')
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Life Points', str(exc), parent=self)

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
            MatchDialog(self.studio, match, opponent, self.rules, self.pools, project=self.project,
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
        if self.template is not None:
            card = self.project.get(self.template)
            typ = int(card['tipo_id'])
            self.kind.set(TYPE_NAMES[typ] if 0 <= typ < len(TYPE_NAMES) else TYPE_NAMES[0])
            ttk.Checkbutton(pane, text=f'Usar #{self.template} como modelo de atributos',
                            variable=self.clone).pack(anchor='w', pady=7)
        self.feedback = tk.StringVar()
        ttk.Label(pane, textvariable=self.feedback, foreground=ACCENT, wraplength=320).pack(anchor='w', pady=(5, 0))
        actions = ttk.Frame(pane)
        actions.pack(fill='x', pady=(6, 0))
        ttk.Button(actions, text='Cancelar', command=self.destroy).pack(side='left')
        ttk.Button(actions, text='Criar e salvar', style='Accent.TButton', command=self.create).pack(side='right')
        self.bind('<Return>', lambda _e: self.create())
        self.bind('<Escape>', lambda _e: self.destroy())
        self.grab_set()
        name.focus_set()

    def create(self):
        try:
            if self.project is not self.studio.project or self.studio._extract_running:
                raise ModError('Reabra a criação de cartas no projeto atual.')
            cid = self.project.add_card(self.template if self.clone.get() else None,
                                        name=self.name.get().strip() or None,
                                        type_id=TYPE_NAMES.index(self.kind.get()),
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
        self.fusion_tree = ttk.Treeview(fusions, columns=('a','b','result'), show='headings', height=6)
        for key, caption in zip(('a','b','result'), ('Material 1','Material 2','Resultado')):
            self.fusion_tree.heading(key, text=caption)
            self.fusion_tree.column(key, width=180)
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
        ttk.Label(equip, text='IDs dos monstros equipáveis, separados por vírgula').pack(anchor='w')
        ttk.Entry(equip, textvariable=self.equip_targets).pack(fill='x', pady=(3, 8))
        ttk.Button(equip, text='Salvar alvos', style='Accent.TButton', command=self._save_equip).pack(anchor='e')
        typ = int(studio.project.get(cid)['tipo_id'])
        if typ == 22:
            tabs.select(ritual)
        if typ == 23:
            tabs.select(equip)
        self._refresh()

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
        if self.cid in rituals:
            tribute, result = rituals[self.cid]
            self.tributes.set(', '.join(map(str, tribute)))
            self.ritual_result.set(str(result))
        if self.cid in equips:
            self.equip_targets.set(', '.join(map(str, sorted(equips[self.cid]))))

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
            apply(entries)
            save_rules(project, rules)
            self.studio.mod_editor.refresh()
            self.studio._update_status('Relações salvas.')
            self._refresh()
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Relações da carta', str(exc), parent=self)

    def _save_fusion(self, remove=False):
        def edit(entries):
            a, b = sorted(positive_int(v.get(), 'Material') for v in self.fusion_values[:2])
            key = f'{a},{b}'
            if remove:
                entries.pop(key, None)
            else:
                entries[key] = positive_int(self.fusion_values[2].get(), 'Resultado')
        self._change('fusoes', edit)

    def _save_ritual(self):
        self._change('rituais', lambda entries: entries.update({str(self.cid): {
            'tributos': parse_card_ids(self.tributes.get(), maximum=5),
            'resultado': positive_int(self.ritual_result.get(), 'Resultado')}}))

    def _save_equip(self):
        self._change('equipamentos', lambda entries: entries.update({str(self.cid):
            parse_card_ids(self.equip_targets.get(), maximum=len(self.studio.project.cards))}))
