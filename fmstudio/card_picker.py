"""Seletor de cartas pesquisável, usado sempre que é preciso escolher uma ou várias cartas.

Busca por ID, nome, tipo ou descrição (sem acento), filtros de categoria,
atributo e estrela guardiã, colunas ordenáveis e escolha por duplo clique,
Enter ou botão. Com ``fusions`` (e ``deck_ids``) aparece também o filtro de
fusão: cartas que fundem com o deck atual ou materiais de um resultado.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .card_search import (ALL_STARS, CATEGORIES, STAR_FILTERS, filter_cards, fusion_materials,
                          fusion_results, fusions_with, has_star, star_label)
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

    def __init__(self, master, cards: dict, *, multiple=False, on_pick=None, initial=None, height=12,
                 fusions=None, deck_ids=None):
        super().__init__(master)
        self.cards = cards
        self.on_pick = on_pick
        self.query = tk.StringVar()
        self.category = tk.StringVar(value='Todas as cartas')
        self.attribute = tk.StringVar(value='Todos os atributos')
        self.star = tk.StringVar(value=ALL_STARS)
        self.fusions = fusions
        self.deck_ids = deck_ids
        self.fusion = FusionFilter(self, cards, fusions or {}, lambda: self.deck_ids or (), self.render)
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
        star = ttk.Combobox(top, textvariable=self.star, state='readonly', width=15, values=list(STAR_FILTERS))
        star.pack(side='left', padx=(6, 0))
        for combo in (category, attribute, star):
            combo.bind('<MouseWheel>', lambda _e: 'break')
        if fusions is not None:
            self.fusion.build(self).pack(fill='x', pady=(4, 0))
        self.hint = ttk.Label(self, foreground=MUTED, text='Digite ID, nome, tipo ou parte da descrição. '
                              + ('Ctrl/Shift para várias. ' if multiple else '')
                              + 'Duplo clique ou Enter escolhe.')
        self.hint.pack(anchor='w', pady=(4, 4))
        holder = ttk.Frame(self)
        holder.pack(fill='both', expand=True)
        columns = ('id', 'nome', 'tipo', 'atk', 'def', 'estrelas', 'fusao')
        self.tree = ttk.Treeview(holder, columns=columns, show='headings',
                                 displaycolumns=columns if fusions is not None else columns[:-1],
                                 selectmode='extended' if multiple else 'browse', height=height)
        for key, label, width, anchor in (('id', 'ID', 60, 'w'), ('nome', 'Carta', 210, 'w'),
                                          ('tipo', 'Tipo', 100, 'w'), ('atk', 'ATK', 60, 'e'),
                                          ('def', 'DEF', 60, 'e'), ('estrelas', 'Estrelas', 110, 'w'),
                                          ('fusao', 'Fusão', 200, 'w')):
            self.tree.heading(key, text=label, command=lambda k=key: self._sort(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=key == 'nome')
        scroll = ttk.Scrollbar(holder, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.count = ttk.Label(self, foreground=MUTED)
        self.count.pack(anchor='w', pady=(4, 0))
        self._sort_key, self._reverse = 'id', False
        for var in (self.query, self.category, self.attribute, self.star):
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
        ids = [cid for cid in filter_cards(self.cards, self.query.get(), self.category.get(), attr)
               if has_star(self.cards[cid], self.star.get())]
        notes = self.fusion.notes()
        if notes is not None:
            ids = [cid for cid in ids if cid in notes]
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
                               _stat(card, 'ataque'), _stat(card, 'defesa'), star_label(card),
                               (notes or {}).get(cid, ''))))
        index = {'id': 0, 'nome': 1, 'tipo': 2, 'atk': 3, 'def': 4, 'estrelas': 5, 'fusao': 6}[self._sort_key]

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


FUSION_NONE = 'Fusão: sem filtro'
FUSION_DECK = 'Fusão: combina com o deck'
FUSION_TARGET = 'Fusão: materiais de um resultado…'


class FusionFilter:
    """Filtro de fusão compartilhado (seletor de cartas e catálogo do deck).

    ``notes()`` devolve None sem filtro, ou {carta: texto da coluna Fusão}.
    """

    def __init__(self, master, cards, fusions, deck_ids, changed):
        self.master, self.cards, self.fusions = master, cards, fusions
        self.deck_ids, self.changed = deck_ids, changed
        self.mode = tk.StringVar(value=FUSION_NONE)
        self.target = None
        self.combo = None
        self.hint = None

    def build(self, parent):
        row = ttk.Frame(parent)
        self.combo = ttk.Combobox(row, textvariable=self.mode, state='readonly', width=44,
                                  values=[FUSION_NONE, FUSION_DECK, FUSION_TARGET])
        self.combo.pack(side='left')
        self.combo.bind('<<ComboboxSelected>>', self._selected)
        self.combo.bind('<MouseWheel>', lambda _e: 'break')
        self.hint = ttk.Label(row, foreground=MUTED)
        self.hint.pack(side='left', padx=(8, 0))
        return row

    def set_data(self, cards, fusions):
        self.cards, self.fusions = cards, fusions or {}

    def _label(self, cid):
        return f'#{cid:03d} {display_name(cid, self.cards)}'

    def _selected(self, _event=None):
        mode = self.mode.get()
        if mode == FUSION_TARGET:
            results = {cid: self.cards[cid] for cid in sorted(fusion_results(self.fusions)) if cid in self.cards}
            if not results:
                self.mode.set(FUSION_NONE)
                self.hint.configure(text='Nenhuma fusão carregada no projeto.')
                self.changed()
                return

            def chosen(ids):
                self.target = ids[0]
                label = f'Fusão: materiais de {self._label(self.target)}'
                self.combo.configure(values=[FUSION_NONE, FUSION_DECK, label, FUSION_TARGET])
                self.mode.set(label)
                self.changed()
            self.mode.set(FUSION_NONE)
            CardPickerDialog(self.master, results, chosen, title='Resultado de fusão desejado',
                             initial=self.target)
            return
        self.changed()

    def notes(self):
        mode = self.mode.get()
        if mode == FUSION_DECK:
            deck = set(self.deck_ids())
            best = fusions_with(self.fusions, deck, self.cards)
            if self.hint is not None:
                self.hint.configure(text='Cartas que fundem com alguma carta do deck (melhor resultado).'
                                    if deck else 'O deck está vazio: adicione cartas primeiro.')
            return {cid: f'→ {self._label(result)} ({_stat(self.cards.get(result) or {}, "ataque")})'
                         f' com #{partner:03d}' for cid, (result, partner) in best.items()}
        if mode.startswith('Fusão: materiais de #') and self.target is not None:
            deck = set(self.deck_ids())
            materials = fusion_materials(self.fusions, self.target)
            if self.hint is not None:
                self.hint.configure(text='✓ = o parceiro já está no deck.')
            notes = {}
            for cid, partners in materials.items():
                partners = sorted(partners, key=lambda p: (p not in deck, p))
                mark = '✓ ' if partners[0] in deck else ''
                more = f' (+{len(partners) - 1})' if len(partners) > 1 else ''
                notes[cid] = f'{mark}+ {self._label(partners[0])}{more}'
            return notes
        if self.hint is not None:
            self.hint.configure(text='')
        return None


class CardPickerDialog(tk.Toplevel):
    """Janela modal com o CardPicker. ``on_pick(ids)`` recebe a escolha."""

    def __init__(self, master, cards: dict, on_pick, *, title='Escolher carta', multiple=False,
                 initial=None, confirm='Escolher', fusions=None, deck_ids=None):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        width = min(900 if fusions is not None else 820, self.winfo_screenwidth() - 40)
        height = min(560, self.winfo_screenheight() - 100)
        self.geometry(f'{width}x{height}')
        self.minsize(min(560, width), min(380, height))
        self.callback = on_pick
        footer = ttk.Frame(self, padding=(12, 8))
        footer.pack(side='bottom', fill='x')
        ttk.Button(footer, text='Cancelar', command=self.destroy).pack(side='left')
        ttk.Button(footer, text=confirm, style='Accent.TButton', command=self._confirm).pack(side='right')
        self.picker = CardPicker(self, cards, multiple=multiple, on_pick=self._done, initial=initial,
                                 fusions=fusions, deck_ids=deck_ids)
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
