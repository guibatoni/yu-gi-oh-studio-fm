"""Janela "Gerar deck temático": deck inicial por tipo, com fusão-chave."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .core import ModError
from .mod_data import MONSTER_TYPES
from .tables import TYPE_NAMES
from .themed_deck import LEVELS, design
from .ui_shell import pin_bottom

TYPE_LABELS_PT = {
    0: 'Dragão', 1: 'Mago', 2: 'Zumbi', 3: 'Guerreiro', 4: 'Besta-Guerreira', 5: 'Besta',
    6: 'Besta Alada', 7: 'Demônio', 8: 'Fada', 9: 'Inseto', 10: 'Dinossauro', 11: 'Réptil',
    12: 'Peixe', 13: 'Serpente Marinha', 14: 'Máquina', 15: 'Trovão', 16: 'Aqua', 17: 'Piro',
    18: 'Rocha', 19: 'Planta',
}


def type_label(typ: int) -> str:
    return f'{TYPE_LABELS_PT.get(typ, TYPE_NAMES[typ])} ({TYPE_NAMES[typ]})'


class ThemedDeckDialog(tk.Toplevel):
    def __init__(self, owner, cards, effects, fusions, equips, *, default_copies, use_deck):
        super().__init__(owner)
        self.title('Gerar deck temático')
        self.transient(owner.winfo_toplevel())
        self.cards, self.effects, self.fusions, self.equips = cards, effects, fusions, equips
        self.copies, self.use_deck, self.result = default_copies, use_deck, None
        self.choices = {type_label(t): t for t in sorted(MONSTER_TYPES) if t != 24}
        self.theme = tk.StringVar(self, value=type_label(8))
        self.level = tk.StringVar(self, value='Equilibrado')
        body = ttk.Frame(self, padding=10)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Monta 40 cartas a partir das cartas e fusões deste projeto: monstros fracos '
                             'do tipo escolhido que fundem entre si, pelo menos uma fusão-chave forte para '
                             'avançar no mod, equipamentos que servem nesses monstros e magias leves.',
                  wraplength=620).pack(anchor='w')
        form = ttk.Frame(body)
        form.pack(fill='x', pady=8)
        ttk.Label(form, text='Tipo principal').grid(row=0, column=0, sticky='w')
        ttk.Combobox(form, textvariable=self.theme, values=list(self.choices), state='readonly',
                     width=28).grid(row=0, column=1, sticky='w', padx=6)
        ttk.Label(form, text='Força').grid(row=1, column=0, sticky='w', pady=(6, 0))
        levels = ttk.Frame(form)
        levels.grid(row=1, column=1, sticky='w', padx=6, pady=(6, 0))
        for name, (cap, (low, high)) in LEVELS.items():
            ttk.Radiobutton(levels, text=f'{name} (monstros até {cap} · chave {low}-{high})',
                            value=name, variable=self.level).pack(anchor='w')
        self.text = tk.Text(body, width=86, height=20, wrap='word')
        self.text.pack(fill='both', expand=True)
        footer = ttk.Frame(self, padding=(10, 0, 10, 10))
        ttk.Button(footer, text='Gerar', command=self.generate).pack(side='left')
        self.use_button = ttk.Button(footer, text='Usar este deck', style='Accent.TButton',
                                     command=self.accept, state='disabled')
        self.use_button.pack(side='right')
        ttk.Button(footer, text='Fechar', command=self.destroy).pack(side='right', padx=6)
        pin_bottom(footer)
        self.generate()

    def generate(self):
        try:
            self.result = design(self.cards, self.effects, self.fusions, self.equips,
                                 self.choices[self.theme.get()], level=self.level.get(),
                                 default_copies=self.copies)
        except ModError as exc:
            self.result = None
            self._show(str(exc))
            self.use_button.configure(state='disabled')
            return
        self._show(self.result.report(self.cards) +
                   '\n\nNão gostou? Clique em Gerar de novo: cada geração varia a fusão-chave e o corpo.')
        self.use_button.configure(state='normal')

    def _show(self, text):
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', text)
        self.text.configure(state='disabled')

    def accept(self):
        if self.result is None:
            return
        name = f"{TYPE_LABELS_PT.get(self.result.theme, TYPE_NAMES[self.result.theme])} · {self.result.level}"
        try:
            self.use_deck(list(self.result.cards), name)
        except (ModError, OSError) as exc:
            messagebox.showerror('Gerar deck temático', str(exc), parent=self)
            return
        self.destroy()
