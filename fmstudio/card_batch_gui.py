"""Janela de edição em lote das cartas selecionadas na biblioteca (prévia antes de aplicar)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from . import card_batch
from .core import ModError
from .guardian import guardian_name
from .rarities import RARITIES
from .tables import ATTR_NAMES, STAR_NAMES, TYPE_NAMES
from .ui_theme import MUTED, WARNING, font

FIELD_LABELS = {'ataque': 'ATK', 'defesa': 'DEF', 'tipo_id': 'Tipo', 'atributo_id': 'Atributo',
                'nivel': 'Nível', 'raridade': 'Raridade', 'guardian_1_id': 'Guardian Star 1',
                'guardian_2_id': 'Guardian Star 2'}


def _choices(key):
    if key == 'tipo_id':
        return [f'{i:02d} — {name}' for i, name in enumerate(TYPE_NAMES)]
    if key == 'atributo_id':
        return [f'{i:02d} — {name}' for i, name in enumerate(ATTR_NAMES)]
    if key == 'nivel':
        return [str(i) for i in range(16)]
    if key == 'raridade':
        return [f'{k} — {v[0]}' for k, v in RARITIES.items()]
    return [f'{i:02d} — {guardian_name(i)}' for i, name in enumerate(STAR_NAMES) if i == 0 or name]


def _show(key, value):
    if key == 'tipo_id':
        return TYPE_NAMES[value] if value < len(TYPE_NAMES) else str(value)
    if key == 'atributo_id':
        return ATTR_NAMES[value] if value < len(ATTR_NAMES) else str(value)
    if key == 'raridade':
        return RARITIES.get(value, (value,))[0]
    if key.startswith('guardian_'):
        return guardian_name(value)
    return str(value)


class CardBatchDialog(tk.Toplevel):
    def __init__(self, studio, ids):
        super().__init__(studio)
        self.studio = studio
        self.ids = sorted(set(ids))
        self.rows = None
        self.title(f'Edição em lote — {len(self.ids)} cartas')
        width = min(860, studio.winfo_screenwidth() - 40)
        height = min(640, studio.winfo_screenheight() - 80)
        self.geometry(f'{width}x{height}')
        self.minsize(min(720, width), min(520, height))
        self.transient(studio)
        self.bind('<Escape>', lambda _e: self.destroy())
        body = ttk.Frame(self, padding=14)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text=f'{len(self.ids)} cartas selecionadas', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, style='Muted.TLabel', wraplength=800, text=(
            'Marque os campos que quer mudar. Campos desmarcados ficam como estão. '
            'Calcule a prévia, confira e aplique: as cartas entram como alterações pendentes '
            '(● na lista) e só são gravadas ao Salvar projeto (Ctrl+S).')).pack(anchor='w', pady=(3, 10))
        grid = ttk.Frame(body)
        grid.pack(fill='x')
        self.enabled = {}
        self.values = {}
        self.operations = {}
        row = 0
        for key in card_batch.STATS:
            self.enabled[key] = tk.BooleanVar()
            self.operations[key] = tk.StringVar(value=card_batch.STAT_OPERATIONS['definir'])
            self.values[key] = tk.StringVar(value='100' if key == 'ataque' else '100')
            ttk.Checkbutton(grid, text=FIELD_LABELS[key], variable=self.enabled[key]).grid(row=row, column=0, sticky='w')
            op = ttk.Combobox(grid, state='readonly', width=16, textvariable=self.operations[key],
                              values=list(card_batch.STAT_OPERATIONS.values()))
            op.grid(row=row, column=1, sticky='w', padx=6, pady=3)
            entry = ttk.Entry(grid, width=10, textvariable=self.values[key])
            entry.grid(row=row, column=2, sticky='w')
            for widget in (op, entry):
                widget.bind('<FocusIn>', lambda _e, k=key: self.enabled[k].set(True), add='+')
            row += 1
        ttk.Label(grid, style='Muted.TLabel', text='Percentual: 110 = +10%, 90 = −10% (arredondado a múltiplos de 10, como no PS1).'
                  ).grid(row=row, column=0, columnspan=4, sticky='w', pady=(0, 6))
        row += 1
        for key in card_batch.CHOICES:
            self.enabled[key] = tk.BooleanVar()
            self.values[key] = tk.StringVar()
            ttk.Checkbutton(grid, text=FIELD_LABELS[key], variable=self.enabled[key]).grid(row=row, column=0, sticky='w')
            combo = ttk.Combobox(grid, state='readonly', width=30, textvariable=self.values[key], values=_choices(key))
            combo.grid(row=row, column=1, columnspan=2, sticky='w', padx=6, pady=3)
            combo.bind('<<ComboboxSelected>>', lambda _e, k=key: self.enabled[k].set(True))
            combo.bind('<MouseWheel>', lambda _e: 'break')
            row += 1
        actions = ttk.Frame(body)
        actions.pack(fill='x', pady=(10, 6))
        ttk.Button(actions, text='Calcular prévia', command=self.preview).pack(side='left')
        self.apply_button = ttk.Button(actions, text='Aplicar às cartas', style='Accent.TButton',
                                       command=self.apply, state='disabled')
        self.apply_button.pack(side='left', padx=6)
        ttk.Button(actions, text='Fechar', command=self.destroy).pack(side='right')
        self.summary = ttk.Label(body, text='', foreground=WARNING)
        self.summary.pack(anchor='w', pady=(0, 4))
        holder = ttk.Frame(body)
        holder.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(holder, columns=('id', 'nome', 'mudancas'), show='headings')
        for column, text, width, stretch in (('id', 'ID', 60, False), ('nome', 'Carta', 220, False),
                                             ('mudancas', 'Antes → depois', 480, True)):
            self.tree.heading(column, text=text)
            self.tree.column(column, width=width, stretch=stretch)
        scroll = ttk.Scrollbar(holder, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        for var in (*self.enabled.values(), *self.values.values(), *self.operations.values()):
            var.trace_add('write', lambda *_: self._invalidate())

    def _invalidate(self):
        self.rows = None
        self.apply_button.configure(state='disabled')

    def _changes(self):
        changes = {}
        reverse = {label: key for key, label in card_batch.STAT_OPERATIONS.items()}
        for key, enabled in self.enabled.items():
            if not enabled.get():
                continue
            value = self.values[key].get()
            if key in card_batch.STATS:
                changes[key] = (reverse[self.operations[key].get()], value)
            else:
                if not value:
                    raise ModError(f'{FIELD_LABELS[key]}: escolha um valor.')
                changes[key] = value.split(' — ', 1)[0]
        return changes

    def preview(self):
        try:
            rows = card_batch.plan(self.studio.drafts.get_card, self.ids, self._changes())
        except ModError as exc:
            messagebox.showerror('Edição em lote', str(exc), parent=self)
            return
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            parts = [f'{FIELD_LABELS[k]}: {_show(k, row["antes"][k])} → {_show(k, row["depois"][k])}'
                     for k in row['depois']]
            self.tree.insert('', 'end', values=(f'{row["id"]:03d}', row['nome'] or '(sem nome)', '  ·  '.join(parts)))
        unchanged = len(self.ids) - len(rows)
        self.summary.configure(text=f'{len(rows)} carta(s) mudam' + (f' · {unchanged} já têm esses valores' if unchanged else ''))
        self.rows = rows
        self.apply_button.configure(state='normal' if rows else 'disabled')

    def apply(self):
        if not self.rows:
            return
        count = card_batch.apply_plan(self.studio.drafts, self.rows)
        self.studio._after_batch(count)
        self.destroy()
