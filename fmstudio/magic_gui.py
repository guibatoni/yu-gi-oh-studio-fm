"""Aba Mágicas e armadilhas: valores de cura, dano e destruição por tipo no PS1."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .core import ModError
from .ps1_magic_values import (ATK_SELECTOR_MIN, DAMAGE_CARDS, DAMAGE_SCALE, DROP15_DEFAULTS, HEAL_CARDS,
                               HEAL_SCALE, MONSTER_TYPES, REMOVAL_CARDS, describe_rule, magic_values,
                               save_magic_values)
from .tables import TYPE_NAMES

ATK_OPTION = 'ATK mínimo'


class MagicTrapEditor(ttk.Frame):
    def __init__(self, parent, studio):
        super().__init__(parent)
        self.pack(fill='both', expand=True)
        self.studio, self.project = studio, None
        self.heal, self.damage, self.removal = {}, {}, {}
        ttk.Label(self, text='Valores das mágicas no BIN/CUE Drop x15',
                  font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 6))
        ttk.Label(self, text='Edite só o que quiser mudar; o resto continua como no Drop x15. '
                             'Os valores entram na próxima cópia BIN/CUE.', wraplength=760).pack(anchor='w')
        body = ttk.Frame(self)
        body.pack(fill='both', expand=True, pady=(8, 0))
        heal = ttk.LabelFrame(body, text='Cura (LP, múltiplos de 100)', padding=8)
        damage = ttk.LabelFrame(body, text='Dano ao oponente (LP, múltiplos de 10)', padding=8)
        removal = ttk.LabelFrame(body, text='Destruição por tipo (monstros do oponente)', padding=8)
        heal.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        damage.grid(row=0, column=1, sticky='nsew')
        removal.grid(row=1, column=0, columnspan=2, sticky='nsew', pady=(8, 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        for frame, cards, scale, store, key in ((heal, HEAL_CARDS, HEAL_SCALE, self.heal, 'cura'),
                                                (damage, DAMAGE_CARDS, DAMAGE_SCALE, self.damage, 'dano')):
            for row, cid in enumerate(cards):
                name = tk.StringVar(self)
                value = tk.StringVar(self)
                ttk.Label(frame, textvariable=name, width=28).grid(row=row, column=0, sticky='w')
                ttk.Spinbox(frame, from_=0, to=255 * scale, increment=scale, width=7,
                            textvariable=value).grid(row=row, column=1, padx=4, pady=2)
                ttk.Label(frame, text=f'original {DROP15_DEFAULTS[key][cid]}',
                          foreground='#5a6b7d').grid(row=row, column=2, sticky='w')
                store[cid] = (name, value)
        options = [*TYPE_NAMES[:MONSTER_TYPES], ATK_OPTION]
        for row, cid in enumerate(REMOVAL_CARDS):
            name, kind, atk = tk.StringVar(self), tk.StringVar(self), tk.StringVar(self)
            ttk.Label(removal, textvariable=name, width=28).grid(row=row, column=0, sticky='w')
            box = ttk.Combobox(removal, state='readonly', values=options, textvariable=kind, width=16)
            box.grid(row=row, column=1, padx=4, pady=2)
            spin = ttk.Spinbox(removal, from_=ATK_SELECTOR_MIN * 10, to=2550, increment=50, width=7,
                               textvariable=atk)
            spin.grid(row=row, column=2, padx=4)
            ttk.Label(removal, text=f'original {describe_rule(DROP15_DEFAULTS["destruicao"][cid])}',
                      foreground='#5a6b7d').grid(row=row, column=3, sticky='w')
            box.bind('<<ComboboxSelected>>', lambda _e, k=kind, s=spin: s.configure(
                state='normal' if k.get() == ATK_OPTION else 'disabled'))
            self.removal[cid] = (name, kind, atk, spin)
        actions = ttk.Frame(self)
        actions.pack(fill='x', pady=(10, 0))
        ttk.Button(actions, text='Restaurar originais', command=self._restore).pack(side='left')
        ttk.Button(actions, text='Salvar valores das mágicas', style='Accent.TButton',
                   command=self._save).pack(side='right')
        self.status = tk.StringVar(self)
        ttk.Label(self, textvariable=self.status, foreground='#5a6b7d').pack(anchor='w', pady=(4, 0))
        self.set_project(None)

    def _card_name(self, cid):
        try:
            name = self.project.get(cid).get('nome') if self.project else ''
        except (KeyError, ModError):
            name = ''
        return f'#{cid} {name or ""}'.strip()

    def set_project(self, project):
        self.project = project
        try:
            saved = magic_values(project) if project else {'cura': {}, 'dano': {}, 'destruicao': {}}
        except ModError as exc:
            saved = {'cura': {}, 'dano': {}, 'destruicao': {}}
            self.status.set(str(exc))
        self._fill(saved)

    def _fill(self, saved):
        for key, store in (('cura', self.heal), ('dano', self.damage)):
            for cid, (name, value) in store.items():
                name.set(self._card_name(cid))
                value.set(str(saved[key].get(cid, DROP15_DEFAULTS[key][cid])))
        for cid, (name, kind, atk, spin) in self.removal.items():
            name.set(self._card_name(cid))
            rule = saved['destruicao'].get(cid, DROP15_DEFAULTS['destruicao'][cid])
            if 'tipo' in rule:
                kind.set(TYPE_NAMES[rule['tipo']])
                atk.set('1500')
                spin.configure(state='disabled')
            else:
                kind.set(ATK_OPTION)
                atk.set(str(rule['atk_min']))
                spin.configure(state='normal')

    def _restore(self):
        self._fill({'cura': {}, 'dano': {}, 'destruicao': {}})
        self.status.set('Originais preenchidos. Clique em Salvar para aplicar.')

    def _collect(self):
        values = {'cura': {}, 'dano': {}, 'destruicao': {}}
        for key, store in (('cura', self.heal), ('dano', self.damage)):
            for cid, (_, value) in store.items():
                number = int(value.get().strip())
                if number != DROP15_DEFAULTS[key][cid]:
                    values[key][cid] = number
        for cid, (_, kind, atk, _) in self.removal.items():
            rule = ({'atk_min': int(atk.get().strip())} if kind.get() == ATK_OPTION
                    else {'tipo': TYPE_NAMES.index(kind.get())})
            if rule != DROP15_DEFAULTS['destruicao'][cid]:
                values['destruicao'][cid] = rule
        return values

    def _save(self):
        if not self.project:
            return
        try:
            saved = save_magic_values(self.project, self._collect())
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Valores das mágicas', str(exc) or 'Use números inteiros.', parent=self)
            return
        changed = sum(len(rows) for rows in saved.values())
        self.status.set(f'{changed} valor(es) alterado(s) salvo(s). Gere um BIN/CUE novo para aplicar.'
                        if changed else 'Todos os valores originais. Nada será alterado no BIN.')
