"""Tkinter editors for mod distributions and Studio card relations."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .core import ModError, positive_int, simulation_nonnegative_int
from .duel_engine import MAX_DECK, parse_card_ids
from .expanded import display_name
from .gui import ACCENT, MUTED, compact_number
from .mod_data import (
    CONFIG_KEY, DROP_GROUPS, RANK_GROUPS, STOCK_STARTER, base_tables, drop_weights,
    duelist_profile, match_recipes, normalize_rules, save_rules, starting_life,
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
        ttk.Button(edit, text='Remover', command=self._remove).pack(side='left', padx=(4, 0))
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
        self.tree.delete(*self.tree.get_children())
        total = sum(self.weights.values())
        for cid, weight in sorted(self.weights.items()):
            self.tree.insert('', 'end', iid=str(cid), values=(
                compact_number(cid), display_name(cid, self.cards), compact_number(weight),
                _probability(weight, total)))
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
        self.rows = []
        self.current = None
        self.fixed = tk.StringVar()
        self.draws = tk.StringVar()
        self.pool = tk.StringVar()
        self.fixed_row = ttk.Frame(self)
        self.fixed_row.pack(fill='x', pady=(0, 7))
        ttk.Label(self.fixed_row, text='Cartas fixas').pack(side='left', padx=(0, 5))
        ttk.Entry(self.fixed_row, textvariable=self.fixed).pack(side='left', fill='x', expand=True)
        ttk.Label(self.fixed_row, text='IDs, ex. 1x3, 16, 723').pack(side='right', padx=(7, 0))
        actions = ttk.Frame(self)
        actions.pack(fill='x', pady=(0, 7))
        self.pool_combo = ttk.Combobox(actions, textvariable=self.pool, state='readonly', width=13)
        self.pool_combo.pack(side='left')
        self.pool_combo.bind('<<ComboboxSelected>>', self._select_pool)
        ttk.Button(actions, text='+ Pool', command=self.add_pool).pack(side='left', padx=3)
        ttk.Button(actions, text='Excluir pool', command=self.remove_pool).pack(side='left', padx=3)
        ttk.Label(actions, text='Compras do pool').pack(side='left', padx=(9, 5))
        ttk.Entry(actions, width=6, textvariable=self.draws).pack(side='left')
        self.table = WeightTable(self)
        self.table.pack(fill='both', expand=True)

    def load(self, cards, profile, *, show_fixed=True):
        self.cards = cards
        self.fixed.set(', '.join(map(str, profile.get('cartas', []))))
        if show_fixed:
            self.fixed_row.pack(fill='x', pady=(0, 7), before=self.pool_combo.master)
        else:
            self.fixed_row.pack_forget()
        self.rows = deepcopy(profile.get('pools', []))
        self._show(0 if self.rows else None)

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
        ttk.Button(head, text='Passwords de Cartas', command=self.open_passwords).pack(side='left', padx=8)
        ttk.Button(head, text='Simular duelo', style='Accent.TButton', command=self.start_match).pack(side='right')
        ttk.Checkbutton(head, text='Oponente começa', variable=self.opponent_first).pack(side='right', padx=8)
        tabs = ttk.Notebook(self)
        tabs.pack(fill='both', expand=True)
        drop_pane, deck_pane, start_pane, lp_pane = [ttk.Frame(tabs, padding=9) for _ in range(4)]
        for pane, name in zip((drop_pane, deck_pane, start_pane, lp_pane),
                              ('Drops por rank', 'Decks de oponentes', 'Decks iniciais', 'Life Points')):
            tabs.add(pane, text=name)
        select_rank = ttk.Frame(drop_pane)
        select_rank.pack(fill='x', pady=(0, 5))
        rank = ttk.Combobox(select_rank, textvariable=self.rank, values=list(self.rank_ids), width=23, state='readonly')
        rank.current(0)
        rank.pack(side='left')
        rank.bind('<<ComboboxSelected>>', lambda _e: self._load_drop())
        ttk.Button(select_rank, text='Restaurar pesos herdados', command=self._inherit_drop).pack(side='right')
        self.drops = WeightTable(drop_pane)
        self.drops.changed = self._save_drop
        self.drops.pack(fill='both', expand=True)

        self.opponent_deck = DeckProfileEditor(deck_pane)
        self.opponent_deck.pack(fill='both', expand=True)
        opponent_actions = ttk.Frame(deck_pane)
        opponent_actions.pack(fill='x', pady=(4, 0))
        ttk.Button(opponent_actions, text='Gerar Deck Aleatório',
                   command=lambda: self.generate_deck(self.opponent_deck)).pack(side='left')
        ttk.Button(opponent_actions, text='Salvar deck do duelista', style='Accent.TButton',
                   command=self.save_opponent).pack(side='right')

        profiles = ttk.Frame(start_pane)
        profiles.pack(fill='x', pady=(0, 6))
        self.profiles = ttk.Combobox(profiles, textvariable=self.starter, state='readonly', width=22)
        self.profiles.pack(side='left')
        self.profiles.bind('<<ComboboxSelected>>', lambda _e: self._load_starter())
        ttk.Button(profiles, text='+ Perfil', command=self._add_starter).pack(side='left', padx=4)
        ttk.Button(profiles, text='Excluir', command=self._delete_starter).pack(side='left')
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
        ttk.Label(self, textvariable=self.status, foreground=ACCENT, wraplength=750).pack(anchor='w', pady=(6, 0))

    def refresh(self):
        self.project = self.studio.project
        if self.project:
            self.cards = {cid: self.project.get(cid) for cid in self.project.cards}
            self.pools, self.stock, _, _ = base_tables(self.project)
            self.rules = normalize_rules(self.project.metadata.get(CONFIG_KEY, {}), self.cards)
            self.status.set('')
        else:
            self.cards, self.pools, self.rules, self.stock = {}, {}, {}, []
        self._load_duelist()
        self._refresh_profiles()

    def refresh_catalog(self):
        if self.project is not self.studio.project:
            self.refresh()
            return
        if self.project is None:
            return
        self.cards = {cid: self.project.get(cid) for cid in self.project.cards}
        self.drops.refresh_catalog(self.cards)
        for editor in (self.opponent_deck, self.starter_deck):
            editor.cards = self.cards
            editor.table.refresh_catalog(self.cards)

    def _refresh_profiles(self):
        names = [STOCK_STARTER, *self.rules.get('iniciais', {})]
        self.profiles.configure(values=names)
        if self.starter.get() not in names:
            self.starter.set(STOCK_STARTER)
        self._load_starter()

    def _duel_id(self):
        return self.duelist_ids[self.duelist.get()]

    def _load_duelist(self):
        self._load_drop()
        self.opponent_deck.load(self.cards, duelist_profile(self.rules, self.pools, self._duel_id()))
        if self.project:
            lp = starting_life(self.project, self._duel_id())
            self.player_lp.set(str(lp['jogador']))
            self.opponent_lp.set(str(lp['adversario']))

    def _load_drop(self):
        self.drops.load(self.cards, drop_weights(self.rules, self.pools, self._duel_id(), self.rank_ids[self.rank.get()]))

    def _load_starter(self):
        name = self.starter.get()
        profile = (self.rules.get('iniciais', {}).get(name, {}) if name != STOCK_STARTER
                   else {'pools': self.rules.get('pools_iniciais_ps1', self.stock)})
        self.starter_weight.set(str(profile.get('peso', 1)))
        self.starter_deck.load(self.cards, profile, show_fixed=name != STOCK_STARTER)

    def _edit(self):
        if not self.project or self.studio._extract_running:
            raise ModError('Abra um projeto disponível para salvar a edição.')
        return deepcopy(self.rules)

    def _selected_duelist(self, rules):
        return rules.setdefault('duelistas', {}).setdefault(str(self._duel_id()), {})

    def _commit(self, rules, message):
        self.rules = save_rules(self.project, rules)
        self.status.set('✓ ' + message)
        self.studio._refresh_project()
        self.studio._update_status(message)

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
            PasswordsDialog(self.studio, self.project, self.cards, original_passwords(self.project))
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Passwords de cartas', str(exc), parent=self)

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
        self.status.set('Deck gerado no editor. Ajuste as cartas e salve o deck.')

    def save_opponent(self):
        try:
            rules = self._edit()
            profile = self.opponent_deck.profile()
            self._selected_duelist(rules)['deck'] = profile
            self._commit(rules, 'Deck do oponente salvo.')
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
            MatchDialog(self.studio, match, opponent, self.rules, self.pools)
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
        ttk.Label(pane, text=f'Nova carta #{self.project.next_card_id()}').pack(anchor='w')
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
        ttk.Button(pane, text='Criar carta', style='Accent.TButton', command=self.create).pack(anchor='e', pady=(7, 0))
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
                                        type_id=TYPE_NAMES.index(self.kind.get()))
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Nova carta', str(exc), parent=self)
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
