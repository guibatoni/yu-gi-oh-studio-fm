"""Aba Mágicas e armadilhas: valores de cura, dano e destruição por tipo no PS1."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .core import ModError
from .ps1_magic_values import (ATK_SELECTOR_MIN, DAMAGE_CARDS, DAMAGE_SCALE, DROP15_DEFAULTS, HEAL_CARDS,
                               HEAL_SCALE, MONSTER_TYPES, REMOVAL_CARDS, describe_rule, magic_values,
                               save_magic_values)
from .ps1_magic_values import TERRAIN_DEFAULTS, TERRAIN_NAMES, TERRAIN_TYPES, TRAP_DEFAULTS
from .ps1_native import TRAP_IDS
from .tables import TYPE_NAMES
from .ui_shell import ScrollFrame, pin_bottom

ATK_OPTION = 'ATK mínimo'


class MagicTrapEditor(ttk.Frame):
    def __init__(self, parent, studio):
        super().__init__(parent)
        self.pack(fill='both', expand=True)
        self.studio, self.project = studio, None
        self.heal, self.damage, self.removal = {}, {}, {}
        self.terrain, self.traps = {}, {}
        tabs = ttk.Notebook(self)
        tabs.pack(fill='both', expand=True)
        values = ttk.Frame(tabs, padding=8)
        fields = ttk.Frame(tabs, padding=8)
        traps = ttk.Frame(tabs, padding=8)
        tabs.add(values, text='Valores das mágicas')
        tabs.add(fields, text='Campos (terreno)')
        tabs.add(traps, text='Armadilhas')
        self._build_fields(fields)
        self._build_traps(traps)
        ttk.Label(values, text='Valores das mágicas no BIN/CUE Drop x15',
                  font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 6))
        ttk.Label(values, text='Edite só o que quiser mudar; o resto continua como no Drop x15. '
                               'Os valores entram na próxima cópia BIN/CUE.', wraplength=760).pack(anchor='w')
        scroll = ScrollFrame(values)
        scroll.pack(fill='both', expand=True, pady=(8, 0))
        body = scroll.body
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
        actions = ttk.Frame(values)
        pin_bottom(actions, pady=(10, 0))
        ttk.Button(actions, text='Restaurar originais', command=self._restore).pack(side='left')
        ttk.Button(actions, text='Salvar valores das mágicas', style='Accent.TButton',
                   command=self._save).pack(side='right')
        self.status = tk.StringVar(self)
        status = ttk.Label(self, textvariable=self.status, foreground='#5a6b7d')
        pin_bottom(status, pady=(4, 0), fill='none', anchor='w')
        self.set_project(None)

    # --- Campos (terreno) -------------------------------------------------
    def _build_fields(self, frame):
        ttk.Label(frame, text='Bônus de ATK/DEF de cada tipo em cada campo (múltiplos de 10, de -1200 a +1200). '
                              'Células alteradas ficam destacadas.', wraplength=760).pack(anchor='w', pady=(0, 6))
        scroll = ScrollFrame(frame)
        scroll.pack(fill='both', expand=True)
        grid = scroll.body
        ttk.Label(grid, text='Tipo').grid(row=0, column=0, sticky='w')
        for column, name in enumerate(TERRAIN_NAMES, start=1):
            ttk.Label(grid, text=name).grid(row=0, column=column, padx=2)
        for type_id in range(TERRAIN_TYPES):
            ttk.Label(grid, text=TYPE_NAMES[type_id]).grid(row=type_id + 1, column=0, sticky='w')
            for terrain in range(1, len(TERRAIN_NAMES) + 1):
                value = tk.StringVar(self)
                spin = tk.Spinbox(grid, from_=-1200, to=1200, increment=50, width=6, textvariable=value,
                                  justify='right')
                spin.grid(row=type_id + 1, column=terrain, padx=1, pady=1)
                value.trace_add('write', lambda *_a, k=(terrain, type_id), w=spin: self._mark_terrain(k, w))
                self.terrain[(terrain, type_id)] = (value, spin)
        actions = ttk.Frame(frame)
        pin_bottom(actions, pady=(8, 0))
        ttk.Button(actions, text='Restaurar originais', command=lambda: self._fill_terrain({})).pack(side='left')
        ttk.Button(actions, text='Salvar campos', style='Accent.TButton',
                   command=self._save_terrain).pack(side='right')

    def _mark_terrain(self, key, widget):
        try:
            changed = int(self.terrain[key][0].get()) != TERRAIN_DEFAULTS.get(key, 0)
        except ValueError:
            changed = True
        widget.configure(background='#FFF1B8' if changed else 'white')

    def _fill_terrain(self, saved):
        for key, (value, _) in self.terrain.items():
            value.set(str(saved.get(key, TERRAIN_DEFAULTS.get(key, 0))))

    def _saved_terrain(self):
        raw = (self.project.metadata.get('ps1_terrain_boosts') or {}) if self.project else {}
        saved = {}
        for key, value in raw.items():
            terrain, type_id = (int(part) for part in str(key).split(':', 1))
            saved[(terrain, type_id)] = int(value)
        return saved

    def _save_terrain(self):
        if not self.project:
            return
        try:
            plan = {}
            for (terrain, type_id), (value, _) in self.terrain.items():
                bonus = int(value.get().strip())
                if not -1200 <= bonus <= 1200 or bonus % 10:
                    raise ModError(f'{TERRAIN_NAMES[terrain - 1]} / {TYPE_NAMES[type_id]}: '
                                   'use múltiplos de 10 entre -1200 e +1200.')
                if bonus != TERRAIN_DEFAULTS.get((terrain, type_id), 0):
                    plan[f'{terrain}:{type_id}'] = bonus
            previous = self.project.metadata
            self.project.metadata = {**previous, 'ps1_terrain_boosts': plan}
            try:
                self.project.save()
            except OSError:
                self.project.metadata = previous
                raise
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Campos (terreno)', str(exc) or 'Use números inteiros.', parent=self)
            return
        self.status.set(f'Campos: {len(plan)} célula(s) alterada(s) salva(s). Gere um BIN/CUE novo.')

    # --- Armadilhas -------------------------------------------------------
    def _build_traps(self, frame):
        ttk.Label(frame, text='Armadilhas de ataque: destroem o monstro atacante com ATK até o limite. '
                              'O jogo escolhe a armadilha pela faixa de ATK, por isso os limites devem '
                              'ficar em ordem crescente (múltiplos de 100, até 25500).',
                  wraplength=760).pack(anchor='w', pady=(0, 8))
        grid = ttk.Frame(frame)
        grid.pack(fill='x')
        for row, trap in enumerate(TRAP_IDS):
            name, value = tk.StringVar(self), tk.StringVar(self)
            ttk.Label(grid, textvariable=name, width=30).grid(row=row, column=0, sticky='w')
            ttk.Spinbox(grid, from_=100, to=25500, increment=100, width=7,
                        textvariable=value).grid(row=row, column=1, padx=4, pady=2)
            ttk.Label(grid, text=f'original até {TRAP_DEFAULTS[trap]}', foreground='#5a6b7d').grid(
                row=row, column=2, sticky='w')
            self.traps[trap] = (name, value)
        actions = ttk.Frame(frame)
        pin_bottom(actions, pady=(8, 0))
        ttk.Button(actions, text='Restaurar originais', command=lambda: self._fill_traps({})).pack(side='left')
        ttk.Button(actions, text='Salvar armadilhas', style='Accent.TButton',
                   command=self._save_traps).pack(side='right')

    def _fill_traps(self, saved):
        for trap, (name, value) in self.traps.items():
            name.set(self._card_name(trap))
            value.set(str(saved.get(trap, TRAP_DEFAULTS[trap])))

    def _save_traps(self):
        if not self.project:
            return
        try:
            values = {trap: int(value.get().strip()) for trap, (_, value) in self.traps.items()}
            ordered = [values[trap] for trap in TRAP_IDS]
            if any(not 100 <= v <= 25500 or v % 100 for v in ordered):
                raise ModError('Limites das armadilhas: múltiplos de 100, de 100 a 25500.')
            if ordered != sorted(ordered):
                raise ModError('Os limites precisam ficar em ordem crescente (#681 até #686).')
            plan = {str(trap): v for trap, v in values.items() if v != TRAP_DEFAULTS[trap]}
            previous = self.project.metadata
            self.project.metadata = {**previous, 'ps1_trap_thresholds': plan}
            try:
                self.project.save()
            except OSError:
                self.project.metadata = previous
                raise
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Armadilhas', str(exc) or 'Use números inteiros.', parent=self)
            return
        self.status.set(f'Armadilhas: {len(plan)} limite(s) alterado(s) salvo(s). Gere um BIN/CUE novo.')

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
        try:
            self._fill_terrain(self._saved_terrain())
            self._fill_traps({int(k): int(v) for k, v in
                              ((project.metadata.get('ps1_trap_thresholds') or {}) if project else {}).items()})
        except (ValueError, TypeError):
            self.status.set('Campos ou armadilhas salvos em formato inesperado; revise e salve de novo.')

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
