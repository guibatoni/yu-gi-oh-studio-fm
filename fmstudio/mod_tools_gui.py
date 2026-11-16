"""Ferramentas de passwords e geração de decks da aba Edição do Mod."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core import ModError
from .deck_generator import DIFFICULTIES, SUPPORT_TYPES, generate_deck
from .expanded import display_name
from .gui import ACCENT, compact_number
from .mod_data import MONSTER_TYPES, deck_copy_limit
from .passwords import id_code, import_original_passwords, original_passwords, redeem_id, redeem_original
from .tables import DECK_SIZE, TYPE_NAMES


def _tree(parent, columns):
    holder = ttk.Frame(parent)
    holder.pack(fill='both', expand=True, pady=(6, 0))
    tree = ttk.Treeview(holder, columns=[row[0] for row in columns], show='headings', selectmode='browse')
    tree.pack(side='left', fill='both', expand=True)
    scroll = ttk.Scrollbar(holder, command=tree.yview)
    scroll.pack(side='right', fill='y')
    tree.configure(yscrollcommand=scroll.set)
    for field, label, width in columns:
        tree.heading(field, text=label)
        tree.column(field, width=width, stretch=field == 'nome')
    return tree


class PasswordPanel(ttk.Frame):
    def __init__(self, parent, cards, *, by_id, open_card, reload_codes=None):
        super().__init__(parent, padding=12)
        self.cards = cards
        self.by_id = by_id
        self.open_card = open_card
        self.reload_codes = reload_codes
        self.records = {}
        self.query = tk.StringVar()
        self.status = tk.StringVar()
        bar = ttk.Frame(self)
        bar.pack(fill='x')
        self.entry = ttk.Entry(bar, textvariable=self.query, width=30)
        self.entry.pack(side='left', fill='x', expand=True)
        self.entry.bind('<Return>', lambda _event: self.redeem())
        ttk.Button(bar, text='Resgatar código', command=self.redeem).pack(side='left', padx=(5, 0))
        columns = [('id', 'ID', 72), ('nome', 'Carta', 240), ('codigo', 'Código', 150)]
        if not by_id:
            columns.append(('custo', 'Star Chips', 110))
        self.tree = _tree(self, columns)
        self.tree.bind('<Double-1>', lambda _event: self._open())
        actions = ttk.Frame(self)
        actions.pack(fill='x', pady=(7, 0))
        if reload_codes is not None:
            ttk.Button(actions, text='Ler códigos do BIN/CUE', command=self._reload).pack(side='left')
        ttk.Button(actions, text='Copiar código', command=self._copy).pack(side='right', padx=(6, 0))
        ttk.Button(actions, text='Abrir carta', command=self._open, style='Accent.TButton').pack(side='right')
        ttk.Label(self, textvariable=self.status, foreground=ACCENT, wraplength=630).pack(anchor='w', pady=(7, 0))
        self.query.trace_add('write', lambda *_: self.render())
        self.render()

    def render(self, results=None):
        self.tree.delete(*self.tree.get_children())
        query = self.query.get().strip().casefold()
        ids = sorted(self.cards if self.by_id else self.records) if results is None else results
        for cid in ids:
            name = display_name(cid, self.cards)
            code = id_code(cid) if self.by_id else self.records[cid].code
            if results is None and query and not any(query in item.casefold() for item in (f'#{cid}', name, code)):
                continue
            values = [compact_number(cid), name, code]
            if not self.by_id:
                values.append(self.records[cid].cost if self.records[cid].cost is not None else '—')
            self.tree.insert('', 'end', iid=str(cid), values=values)
        if self.by_id:
            self.status.set('Busque por nome, ID ou código FM. Use códigos por ID no Studio.')
        elif not self.records:
            self.status.set('Carregue os passwords de oito dígitos da imagem vinculada ao projeto.')
        else:
            self.status.set('Busque por nome, ID ou password original de oito dígitos.')

    def redeem(self):
        try:
            query = self.query.get()
            ids = [redeem_id(query, self.cards)] if self.by_id else redeem_original(query, self.records)
            self.render(ids)
            self.tree.selection_set(str(ids[0]))
            self.tree.see(str(ids[0]))
            self.status.set(f'{len(ids)} carta(s) localizada(s).')
        except (ModError, ValueError) as exc:
            self.status.set(str(exc))

    def _selection(self):
        chosen = self.tree.selection()
        return int(chosen[0]) if chosen else None

    def _copy(self):
        cid = self._selection()
        if cid is not None:
            code = id_code(cid) if self.by_id else self.records[cid].code
            self.clipboard_clear()
            self.clipboard_append(code)
            self.status.set('Código copiado.')

    def _open(self):
        cid = self._selection()
        if cid is not None:
            self.open_card(cid)

    def _reload(self):
        source = filedialog.askopenfilename(title='BIN/CUE vinculado ao projeto',
                                            filetypes=[('PlayStation', '*.bin *.cue')], parent=self)
        if source:
            try:
                self.records = self.reload_codes(Path(source))
                self.render()
            except (ModError, ValueError, OSError) as exc:
                messagebox.showerror('Passwords originais', str(exc), parent=self)


class PasswordsDialog(tk.Toplevel):
    def __init__(self, studio, project, cards, originals):
        super().__init__(studio)
        self.title('Passwords de cartas')
        self.transient(studio)
        self.geometry('680x460')
        self.minsize(550, 330)
        tabs = ttk.Notebook(self)
        tabs.pack(fill='both', expand=True, padx=10, pady=10)

        def reveal(cid):
            studio.select_card(cid)
            self.destroy()

        self.original = PasswordPanel(tabs, cards, by_id=False, open_card=reveal,
                                      reload_codes=lambda path: import_original_passwords(project, path))
        self.original.records = originals
        self.original.render()
        self.ids = PasswordPanel(tabs, cards, by_id=True, open_card=reveal)
        tabs.add(self.original, text='Códigos Originais')
        tabs.add(self.ids, text='Códigos por ID')
        self.bind('<Escape>', lambda _event: self.destroy())
        self.grab_set()
        self.original.entry.focus_set()


def _suggest_quantities(cards, effects, default_copies, fixed):
    types = {cid: int(card['tipo_id']) for cid, card in cards.items()}
    counts = Counter(types.get(cid) for cid in fixed)
    if len(fixed) == DECK_SIZE and all(typ in MONSTER_TYPES.union(SUPPORT_TYPES) for typ in counts):
        return counts
    capacity = Counter()
    for cid, typ in types.items():
        capacity[typ] += deck_copy_limit(effects, cid, default_copies)
    counts = Counter({typ: min(capacity[typ], target) for typ, target in ((20, 4), (21, 3), (23, 2))})
    available = sorted((typ for typ in MONSTER_TYPES if capacity[typ]), key=lambda typ: (-capacity[typ], typ))
    for _ in range(DECK_SIZE - sum(counts.values())):
        candidates = [typ for typ in available if counts[typ] < capacity[typ]]
        if not candidates:
            break
        counts[min(candidates[:3], key=counts.__getitem__)] += 1
    return counts


class DeckGeneratorDialog(tk.Toplevel):
    def __init__(self, editor, cards, effects, fusions, equips, *, default_copies,
                 trap_thresholds, fixed, use_deck, new_starter=False):
        super().__init__(editor.winfo_toplevel())
        self.title('Gerar Deck Aleatório')
        self.transient(editor.winfo_toplevel())
        self.geometry('700x530')
        self.minsize(620, 460)
        self.cards, self.effects, self.fusions, self.equips = cards, effects, fusions, equips
        self.default_copies, self.trap_thresholds = default_copies, trap_thresholds
        self.on_use = use_deck
        self.deck = None
        self.max_atk = tk.StringVar()
        self.max_def = tk.StringVar()
        self.difficulty = tk.StringVar(value='Difícil')
        self.status = tk.StringVar()
        self.summary = tk.StringVar()
        suggestions = _suggest_quantities(cards, effects, default_copies, fixed)
        self.quantities = {typ: tk.StringVar(value=str(suggestions[typ]))
                           for typ in sorted(MONSTER_TYPES.union(SUPPORT_TYPES))}

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True, padx=12, pady=(12, 4))
        setup, monsters, preview = (ttk.Frame(self.tabs, padding=12) for _ in range(3))
        for pane, name in ((setup, 'Composição'), (monsters, 'Tipos de Monstro'), (preview, 'Prévia')):
            self.tabs.add(pane, text=name)
        self.preview = preview
        for row, (label, var) in enumerate((
                ('ATK máximo da carta base', self.max_atk), ('DEF máxima da carta base', self.max_def))):
            ttk.Label(setup, text=label).grid(row=row, column=0, sticky='w', pady=5)
            ttk.Entry(setup, width=16, textvariable=var).grid(row=row, column=1, sticky='w', padx=10)
        ttk.Label(setup, text='Deixe em branco para liberar o teto. Resultados de fusão têm poder livre.',
                  wraplength=570).grid(row=2, column=0, columnspan=2, sticky='w', pady=(0, 10))
        for row, (typ, label) in enumerate(((20, 'Magias'), (21, 'Armadilhas'), (23, 'Equipamentos')), 3):
            self._quantity(setup, typ, label, row, 0)
        ttk.Label(setup, text='Dificuldade').grid(row=6, column=0, sticky='w', pady=5)
        ttk.Combobox(setup, textvariable=self.difficulty, values=list(DIFFICULTIES),
                     state='readonly', width=15).grid(row=6, column=1, sticky='w', padx=10)
        if new_starter:
            ttk.Label(setup, text='O deck escolhido será salvo em um novo perfil inicial.',
                      wraplength=550).grid(row=7, column=0, columnspan=2, sticky='w', pady=5)
        for i, typ in enumerate(sorted(MONSTER_TYPES)):
            row, column = divmod(i, 2)
            self._quantity(monsters, typ, TYPE_NAMES[typ], row, column * 2)
        self.list = _tree(preview, [('qtd', 'Qtd.', 55), ('id', 'ID', 70), ('nome', 'Carta', 265),
                                    ('tipo', 'Tipo', 125)])
        ttk.Label(preview, textvariable=self.summary, wraplength=620, justify='left').pack(anchor='w', pady=(8, 0))

        footer = ttk.Frame(self, padding=(12, 2, 12, 10))
        footer.pack(fill='x')
        ttk.Label(footer, textvariable=self.status, foreground=ACCENT, wraplength=660).pack(anchor='w', pady=4)
        controls = ttk.Frame(footer)
        controls.pack(fill='x')
        ttk.Button(controls, text='Cancelar', command=self.destroy).pack(side='left')
        self.use_button = ttk.Button(controls, text='Usar deck', command=self._use,
                                     state='disabled', style='Accent.TButton')
        self.use_button.pack(side='right')
        ttk.Button(controls, text='Gerar prévia', command=self._generate).pack(side='right', padx=(0, 6))
        for var in (self.max_atk, self.max_def, self.difficulty, *self.quantities.values()):
            var.trace_add('write', self._invalidate)
        self._invalidate()
        self.bind('<Escape>', lambda _event: self.destroy())
        self.grab_set()

    def _quantity(self, parent, typ, name, row, column):
        ttk.Label(parent, text=name).grid(row=row, column=column, sticky='w', padx=(0, 8), pady=3)
        ttk.Spinbox(parent, from_=0, to=DECK_SIZE, width=6, textvariable=self.quantities[typ]).grid(
            row=row, column=column+1, sticky='w', padx=(4, 22), pady=3)

    def _invalidate(self, *_):
        self.deck = None
        self.use_button.state(['disabled'])
        try:
            total = sum(int(var.get() or 0) for var in self.quantities.values())
            self.status.set(f'{total} de {DECK_SIZE} vagas preenchidas.')
        except ValueError:
            self.status.set('Informe quantidades inteiras por tipo.')

    def _generate(self):
        try:
            result = generate_deck(
                self.cards, self.effects, self.fusions, self.equips,
                {typ: var.get() or '0' for typ, var in self.quantities.items()},
                max_atk=self.max_atk.get().strip() or None, max_def=self.max_def.get().strip() or None,
                difficulty=self.difficulty.get(), default_copies=self.default_copies,
                trap_thresholds=self.trap_thresholds,
            )
        except (ModError, ValueError) as exc:
            self.status.set(str(exc))
            return
        self.deck = result
        self.list.delete(*self.list.get_children())
        for cid, amount in sorted(Counter(result.cards).items()):
            self.list.insert('', 'end', values=(amount, compact_number(cid), display_name(cid, self.cards),
                                                 TYPE_NAMES[int(self.cards[cid]['tipo_id'])]))
        routes = [
            f'{display_name(a, self.cards)} + {display_name(b, self.cards)} → {display_name(result, self.cards)}'
            for a, b, result in result.fusions[:3]
        ]
        self.summary.set('\n'.join(routes))
        self.tabs.select(self.preview)
        self.status.set(f'{len(result.cards)} cartas · {len(result.fusions)} fusões disponíveis.')
        self.use_button.state(['!disabled'])

    def _use(self):
        if self.deck is not None:
            try:
                self.on_use(self.deck.cards)
            except (ModError, ValueError, OSError) as exc:
                self.status.set(str(exc))
                return
            self.destroy()
