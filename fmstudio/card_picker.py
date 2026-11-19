"""Seletor de cartas pesquisável, usado sempre que é preciso escolher uma ou várias cartas.

Busca por ID, nome, tipo ou descrição (sem acento), filtros de categoria e
atributo, colunas ordenáveis e escolha por duplo clique, Enter ou botão.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .card_search import CATEGORIES, filter_cards
from .expanded import display_name, search_text
from .tables import ATTR_NAMES, TYPE_NAMES
from .ui_theme import MUTED

def _stat(card, key):
    try:
        kind = int(card.get('tipo_id', -1))
        return str(int(card.get(key, 0))) if kind < 20 or kind == 24 else '—'
    except (TypeError, ValueError):
        return '—'


class CardPicker(ttk.Frame):
    """Lista pesquisável. ``on_pick(ids)`` no duplo clique/Enter; ``selected()`` para ler a escolha."""

    def __init__(self, master, cards: dict, *, multiple=False, on_pick=None, initial=None, height=12):
        super().__init__(master)
        self.cards = cards
        self.on_pick = on_pick
        self.query = tk.StringVar()
        self.category = tk.StringVar(value='Todas as cartas')
        self.attribute = tk.StringVar(value='Todos os atributos')
        top = ttk.Frame(self)
        top.pack(fill='x')
        self.entry = ttk.Entry(top, textvariable=self.query, style='Search.TEntry')
        self.entry.pack(side='left', fill='x', expand=True)
        category = ttk.Combobox(top, textvariable=self.category, state='readonly', width=20,
                                values=list(CATEGORIES))
        category.pack(side='left', padx=(6, 0))
        attribute = ttk.Combobox(top, textvariable=self.attribute, state='readonly', width=16,
                                 values=['Todos os atributos', *ATTR_NAMES])
        attribute.pack(side='left', padx=(6, 0))
        for combo in (category, attribute):
            combo.bind('<MouseWheel>', lambda _e: 'break')
        self.hint = ttk.Label(self, foreground=MUTED, text='Digite ID, nome, tipo ou parte da descrição. '
                              + ('Ctrl/Shift para várias. ' if multiple else '')
                              + 'Duplo clique ou Enter escolhe.')
        self.hint.pack(anchor='w', pady=(4, 4))
        holder = ttk.Frame(self)
        holder.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(holder, columns=('id', 'nome', 'tipo', 'atk', 'def'), show='headings',
                                 selectmode='extended' if multiple else 'browse', height=height)
        for key, label, width, anchor in (('id', 'ID', 60, 'w'), ('nome', 'Carta', 230, 'w'),
                                          ('tipo', 'Tipo', 110, 'w'), ('atk', 'ATK', 64, 'e'),
                                          ('def', 'DEF', 64, 'e')):
            self.tree.heading(key, text=label, command=lambda k=key: self._sort(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=key == 'nome')
        scroll = ttk.Scrollbar(holder, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.count = ttk.Label(self, foreground=MUTED)
        self.count.pack(anchor='w', pady=(4, 0))
        self._sort_key, self._reverse = 'id', False
        for var in (self.query, self.category, self.attribute):
            var.trace_add('write', lambda *_: self.render())
        self.tree.bind('<Double-1>', lambda _e: self._pick())
        self.tree.bind('<Return>', lambda _e: self._pick())
        self.entry.bind('<Down>', self._into_list)
        self.entry.bind('<Return>', self._enter_from_search)
        self.render()
        if initial is not None and self.tree.exists(str(initial)):
            self.tree.selection_set(str(initial))
            self.tree.see(str(initial))
        self.entry.focus_set()

    def render(self):
        attribute = self.attribute.get()
        attr = ATTR_NAMES.index(attribute) if attribute in ATTR_NAMES else -1
        ids = filter_cards(self.cards, self.query.get(), self.category.get(), attr)
        keep = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        rows = []
        for cid in ids:
            card = self.cards[cid] or {}
            try:
                kind = int(card.get('tipo_id', -1))
                kind_name = TYPE_NAMES[kind] if 0 <= kind < len(TYPE_NAMES) else '?'
            except (TypeError, ValueError):
                kind_name = '?'
            rows.append((cid, (f'{cid:03d}', display_name(cid, self.cards), kind_name,
                               _stat(card, 'ataque'), _stat(card, 'defesa'))))
        index = {'id': 0, 'nome': 1, 'tipo': 2, 'atk': 3, 'def': 4}[self._sort_key]

        def key(row):
            value = row[1][index]
            if self._sort_key in ('id', 'atk', 'def'):
                return int(value) if value.isdigit() else -1
            return search_text(value)
        rows.sort(key=key, reverse=self._reverse)
        for number, (cid, values) in enumerate(rows):
            self.tree.insert('', 'end', iid=str(cid), values=values, tags=('stripe',) if number % 2 else ())
        self.tree.tag_configure('stripe', background='#1c263a')
        valid = [item for item in keep if self.tree.exists(item)]
        if valid:
            self.tree.selection_set(valid)
        elif rows and len(rows) <= 50:
            first = str(rows[0][0])
            self.tree.selection_set(first)
            self.tree.focus(first)
        self.count.configure(text=f'{len(rows)} de {len(self.cards)} cartas')

    def _sort(self, key):
        self._reverse = not self._reverse if key == self._sort_key else False
        self._sort_key = key
        self.render()

    def selected(self) -> list[int]:
        return [int(item) for item in self.tree.selection()]

    def _into_list(self, _event=None):
        children = self.tree.get_children()
        if children:
            target = (self.tree.selection() or children)[0]
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.focus_set()
        return 'break'

    def _enter_from_search(self, _event=None):
        if len(self.tree.get_children()) == 1:
            self.tree.selection_set(self.tree.get_children()[0])
        self._pick()
        return 'break'

    def _pick(self):
        ids = self.selected()
        if ids and self.on_pick:
            self.on_pick(ids)
        return 'break'


class CardPickerDialog(tk.Toplevel):
    """Janela modal com o CardPicker. ``on_pick(ids)`` recebe a escolha."""

    def __init__(self, master, cards: dict, on_pick, *, title='Escolher carta', multiple=False,
                 initial=None, confirm='Escolher'):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        width = min(720, self.winfo_screenwidth() - 40)
        height = min(560, self.winfo_screenheight() - 100)
        self.geometry(f'{width}x{height}')
        self.minsize(min(560, width), min(380, height))
        self.callback = on_pick
        footer = ttk.Frame(self, padding=(12, 8))
        footer.pack(side='bottom', fill='x')
        ttk.Button(footer, text='Cancelar', command=self.destroy).pack(side='left')
        ttk.Button(footer, text=confirm, style='Accent.TButton', command=self._confirm).pack(side='right')
        self.picker = CardPicker(self, cards, multiple=multiple, on_pick=self._done, initial=initial)
        self.picker.pack(fill='both', expand=True, padx=12, pady=(12, 0))
        self.bind('<Escape>', lambda _e: self.destroy())
        self.grab_set()
        self.picker.entry.focus_set()

    def _confirm(self):
        ids = self.picker.selected()
        if ids:
            self._done(ids)

    def _done(self, ids):
        self.destroy()
        self.callback(ids)
