"""Aba Molduras: cor da moldura das cartas por raridade no PS1."""
from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from .core import ModError
from .ps1_frame_colors import CLASSES, DEFAULT_COLORS, frame_settings, save_frame_settings, tint
from .rarities import RARITIES


class FrameColorEditor(ttk.Frame):
    def __init__(self, parent, studio):
        super().__init__(parent)
        self.pack(fill='both', expand=True)
        self.studio, self.project = studio, None
        self.enabled = tk.BooleanVar(self)
        self.colors = {key: tk.StringVar(self) for key in CLASSES}
        self.swatches = {}
        ttk.Label(self, text='Cor da moldura das cartas por raridade (PS1)',
                  font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 6))
        ttk.Label(self, text='A cor vale para as cartas na mão e no campo do duelo e para a carta ampliada '
                             '(baú/Build Deck, biblioteca e visualizador do duelo). '
                             'A arte, o ATK/DEF e o ícone de tipo não mudam. Mágicas, armadilhas e '
                             'equipamentos mantêm a moldura própria. Deixe a cor vazia para a moldura original.',
                  wraplength=760).pack(anchor='w')
        ttk.Checkbutton(self, text='Colorir molduras por raridade no BIN/CUE Drop x15',
                        variable=self.enabled).pack(anchor='w', pady=(8, 6))
        grid = ttk.Frame(self)
        grid.pack(fill='x')
        for row, key in enumerate(CLASSES):
            ttk.Label(grid, text=RARITIES[key][0], width=12).grid(row=row, column=0, sticky='w', pady=3)
            ttk.Entry(grid, textvariable=self.colors[key], width=10).grid(row=row, column=1, padx=4)
            ttk.Button(grid, text='Escolher…', command=lambda k=key: self._choose(k)).grid(row=row, column=2)
            ttk.Button(grid, text='Sem cor', command=lambda k=key: self.colors[k].set('')).grid(
                row=row, column=3, padx=4)
            swatch = tk.Label(grid, width=14, relief='groove')
            swatch.grid(row=row, column=4, padx=6)
            self.swatches[key] = swatch
            self.colors[key].trace_add('write', lambda *_a, k=key: self._paint(k))
        actions = ttk.Frame(self)
        actions.pack(fill='x', pady=(10, 0))
        ttk.Button(actions, text='Cores sugeridas', command=self._defaults).pack(side='left')
        ttk.Button(actions, text='Salvar molduras', style='Accent.TButton', command=self._save).pack(side='right')
        self.status = tk.StringVar(self)
        ttk.Label(self, textvariable=self.status, foreground='#5a6b7d').pack(anchor='w', pady=(4, 0))
        ttk.Label(self, text='A amostra mostra a moldura de monstro original tingida pela cor escolhida '
                             '(o PS1 multiplica a cor da textura).', foreground='#5a6b7d',
                  wraplength=760).pack(anchor='w')
        self.set_project(None)

    def _paint(self, key):
        value = self.colors[key].get().strip()
        try:
            if not value:
                raise ValueError
            r, g, b = tint(value)
            base = (0xC8, 0x8C, 0x48)  # monster frame tone
            mixed = '#%02X%02X%02X' % tuple(min(255, c * m // 0x80) for c, m in zip(base, (r, g, b)))
            self.swatches[key].configure(bg=mixed, text='')
        except ValueError:
            self.swatches[key].configure(bg='#C88C48', text='original')

    def _choose(self, key):
        picked = colorchooser.askcolor(color=self.colors[key].get() or None, parent=self)[1]
        if picked:
            self.colors[key].set(picked.upper())

    def _defaults(self):
        for key, value in DEFAULT_COLORS.items():
            self.colors[key].set(value)

    def set_project(self, project):
        self.project = project
        try:
            settings = frame_settings(project) if project else frame_settings(None)
        except ModError as exc:
            settings = frame_settings(None)
            self.status.set(str(exc))
        self.enabled.set(settings['ativado'])
        for key, value in settings['cores'].items():
            self.colors[key].set(value)

    def _save(self):
        if not self.project:
            return
        try:
            saved = save_frame_settings(self.project, {
                'ativado': self.enabled.get(),
                'cores': {key: var.get().strip() for key, var in self.colors.items()}})
        except (ModError, OSError) as exc:
            messagebox.showerror('Molduras', str(exc), parent=self)
            return
        self.status.set('Molduras ativadas. Gere um BIN/CUE novo.' if saved['ativado']
                        else 'Molduras desativadas: o BIN mantém as molduras originais.')
