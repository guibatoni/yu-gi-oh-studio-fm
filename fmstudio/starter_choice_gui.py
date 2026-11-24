"""Janela "Escolha no New Game": quais perfis o jogador pode escolher no PS1."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .core import ModError
from .ps1_starter_choice import MAX_DECKS, MAX_NAME, display_name, resolve_decks, save_settings, settings
from .tables import DECK_SIZE
from .ui_shell import pin_bottom


def _usable(profile) -> bool:
    return not profile.get('pools') and len(profile.get('cartas', [])) == DECK_SIZE


class StarterChoiceDialog(tk.Toplevel):
    def __init__(self, owner, project, profiles):
        super().__init__(owner)
        self.title('Escolha do deck inicial no New Game (PS1)')
        self.transient(owner.winfo_toplevel())
        self.project, self.profiles = project, profiles
        current = settings(project)
        self.enabled = tk.BooleanVar(self, value=current['ativado'])
        body = ttk.Frame(self, padding=10)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Depois de digitar o nome, o jogo abre uma caixa com os decks marcados abaixo e o '
                             'jogador precisa escolher um (cursor e X do próprio jogo). Até 4 decks cabem numa '
                             'página; com mais, cada página mostra 3 decks e "Mais decks...". O nome do perfil '
                             f'é o texto mostrado no jogo (até {MAX_NAME} letras). Só perfis com 40 cartas fixas '
                             'podem entrar. Desligado, o jogo sorteia o deck inicial como sempre.',
                  wraplength=560).pack(anchor='w')
        ttk.Checkbutton(body, text='Ativar a escolha do deck inicial no BIN/CUE',
                        variable=self.enabled).pack(anchor='w', pady=(8, 4))
        ttk.Label(body, text=f'Perfis oferecidos (selecione de 2 a {MAX_DECKS}; Ctrl+clique para vários):').pack(anchor='w')
        self.listbox = tk.Listbox(body, selectmode='multiple', height=12, exportselection=False, width=60)
        self.listbox.pack(fill='both', expand=True, pady=4)
        self.names = []
        for name, profile in profiles.items():
            ok = _usable(profile)
            label = name if ok else f'{name}  (indisponível: precisa de 40 cartas fixas)'
            if len(name) > MAX_NAME:
                label += f'  (o jogo mostra só as {MAX_NAME} primeiras letras)'
            self.listbox.insert('end', label)
            self.names.append((name, ok))
            if name in current['decks'] and ok:
                self.listbox.selection_set('end')
        if not self.names:
            self.listbox.insert('end', 'Nenhum perfil criado. Use "+ Perfil" ou "Gerar deck temático".')
        self.display = dict(current.get('nomes', {}))
        rename = ttk.Frame(body)
        rename.pack(fill='x', pady=(4, 0))
        ttk.Label(rename, text=f'Nome no jogo (até {MAX_NAME} letras):').pack(side='left')
        self.display_var = tk.StringVar(self)
        self.display_entry = ttk.Entry(rename, textvariable=self.display_var, width=MAX_NAME + 4,
                                       state='disabled')
        self.display_entry.pack(side='left', padx=6)
        self.display_entry.bind('<Return>', lambda _e: self.apply_name())
        ttk.Button(rename, text='Aplicar nome', command=self.apply_name).pack(side='left')
        self.preview = tk.StringVar(self)
        ttk.Label(body, textvariable=self.preview, foreground='#5a6b7d', wraplength=560).pack(anchor='w')
        self.current_index = None
        self.listbox.bind('<<ListboxSelect>>', self._on_select)
        self._update_preview()
        self.status = tk.StringVar(self)
        ttk.Label(body, textvariable=self.status, foreground='#5a6b7d', wraplength=560).pack(anchor='w')
        footer = ttk.Frame(self, padding=(10, 0, 10, 10))
        ttk.Button(footer, text='Salvar', style='Accent.TButton', command=self.save).pack(side='right')
        ttk.Button(footer, text='Fechar', command=self.destroy).pack(side='right', padx=6)
        pin_bottom(footer)

    def _on_select(self, _event=None):
        index = self.listbox.index('active') if self.names else None      # último perfil clicado
        if index is None or not 0 <= index < len(self.names):
            return
        self.current_index = index
        name = self.names[index][0]
        self.display_entry.configure(state='normal')
        self.display_var.set(self.display.get(name, name)[:MAX_NAME])
        self._update_preview()

    def apply_name(self):
        if self.current_index is None:
            return
        name = self.names[self.current_index][0]
        value = self.display_var.get().strip()[:MAX_NAME]
        if value and value != name:
            self.display[name] = value
        else:
            self.display.pop(name, None)
        self._update_preview()

    def _update_preview(self):
        chosen = self.selected()
        shown = [display_name({'nomes': self.display}, name)[:MAX_NAME] for name in chosen]
        self.preview.set('No jogo: ' + ' · '.join(shown) if shown else 'Nenhum perfil selecionado.')

    def selected(self):
        return [self.names[i][0] for i in self.listbox.curselection()
                if i < len(self.names) and self.names[i][1]]

    def save(self):
        chosen = self.selected()
        if len(chosen) > MAX_DECKS:
            messagebox.showerror('Escolha do deck inicial', f'Selecione no máximo {MAX_DECKS} perfis.', parent=self)
            return
        try:
            self.apply_name()
            saved = save_settings(self.project, enabled=self.enabled.get(), decks=chosen, names=self.display)
            if saved['ativado']:
                resolve_decks(self.project, self.profiles)
        except (ModError, OSError) as exc:
            messagebox.showerror('Escolha do deck inicial', str(exc), parent=self)
            return
        self.status.set('Salvo. Gere um BIN/CUE novo e comece um New Game para escolher o deck.'
                        if saved['ativado'] else 'Salvo: escolha desligada, o deck inicial continua sorteado.')
