"""Componentes da moldura da janela: barra lateral, barra de status e busca rápida."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import ui_nav
from .ui_theme import (ACCENT, BORDER, FAINT, MUTED, NAV_BG, SELECT, SURFACE, SURFACE2, SURFACE3,
                       TEXT, WARNING, DANGER, font)


class Tooltip:
    """Dica ao parar o mouse sobre um widget (sem dependências)."""

    def __init__(self, widget, text, delay=550):
        self.widget, self.text, self.delay = widget, text, delay
        self._job = None
        self._tip = None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')

    def _schedule(self, _event=None):
        self._hide()
        if self.text:
            self._job = self.widget.after(self.delay, self._show)

    def _show(self):
        self._job = None
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() + 6
            y = self.widget.winfo_rooty() + 2
        except tk.TclError:
            return
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f'+{x}+{y}')
        tk.Label(self._tip, text=self.text, bg=SURFACE2, fg=TEXT, font=font(9), padx=8, pady=5,
                 justify='left', wraplength=320, highlightthickness=1,
                 highlightbackground=BORDER).pack()

    def _hide(self, _event=None):
        if self._job is not None:
            self.widget.after_cancel(self._job)
            self._job = None
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class NavSidebar(tk.Frame):
    """Barra lateral recolhível. ``on_select(key)`` é chamado ao clicar numa seção."""

    WIDE, NARROW = 214, 52

    def __init__(self, master, on_select, *, collapsed=False):
        super().__init__(master, bg=NAV_BG, width=self.NARROW if collapsed else self.WIDE)
        self.pack_propagate(False)
        self.on_select = on_select
        self.collapsed = collapsed
        self.active = None
        self.rows: dict[str, tuple[tk.Frame, tk.Label, tk.Label]] = {}
        self.group_labels: list[tk.Label] = []
        top = tk.Frame(self, bg=NAV_BG)
        top.pack(fill='x', pady=(8, 6))
        self.toggle = tk.Label(top, text='☰', bg=NAV_BG, fg=MUTED, font=font(14), cursor='hand2',
                               padx=14, pady=2)
        self.toggle.pack(side='left')
        self.toggle.bind('<Button-1>', lambda _e: self.set_collapsed(not self.collapsed))
        Tooltip(self.toggle, 'Recolher/expandir menu (Ctrl+\\)')
        self.brand = tk.Label(top, text='FM STUDIO', bg=NAV_BG, fg=TEXT, font=font(11, 'bold'))
        self.brand.pack(side='left')
        group = None
        for section in ui_nav.SECTIONS:
            if section.group != group:
                group = section.group
                if group:
                    label = tk.Label(self, text=group.upper(), bg=NAV_BG, fg=FAINT, font=font(8, 'bold'),
                                     anchor='w', padx=16)
                    label.pack(fill='x', pady=(10, 2))
                    self.group_labels.append(label)
            self._row(section)
        self._apply_collapsed()

    def _row(self, section):
        row = tk.Frame(self, bg=NAV_BG, cursor='hand2')
        row.pack(fill='x', padx=6, pady=1)
        marker = tk.Frame(row, bg=NAV_BG, width=3)
        marker.pack(side='left', fill='y')
        icon = tk.Label(row, text=section.icon, bg=NAV_BG, fg=MUTED, font=font(12), width=2, pady=5)
        icon.pack(side='left', padx=(8, 6))
        label = tk.Label(row, text=section.label, bg=NAV_BG, fg=MUTED, font=font(10), anchor='w')
        label.pack(side='left', fill='x', expand=True)
        for widget in (row, icon, label):
            widget.bind('<Button-1>', lambda _e, key=section.key: self.on_select(key))
            widget.bind('<Enter>', lambda _e, key=section.key: self._hover(key, True))
            widget.bind('<Leave>', lambda _e, key=section.key: self._hover(key, False))
        Tooltip(icon, f'{section.label}\n{section.hint}' if section.hint else section.label)
        self.rows[section.key] = (row, icon, label, marker)

    def _paint(self, key, *, hover=False):
        row, icon, label, marker = self.rows[key]
        active = key == self.active
        bg = SELECT if active else (SURFACE3 if hover else NAV_BG)
        fg = TEXT if active or hover else MUTED
        for widget in (row, icon, label):
            widget.configure(bg=bg)
        icon.configure(fg=ACCENT if active else fg)
        label.configure(fg=fg, font=font(10, 'bold') if active else font(10))
        marker.configure(bg=ACCENT if active else bg)

    def _hover(self, key, inside):
        self._paint(key, hover=inside)

    def set_active(self, key):
        previous, self.active = self.active, key
        for item in (previous, key):
            if item in self.rows:
                self._paint(item)

    def set_collapsed(self, collapsed):
        self.collapsed = bool(collapsed)
        self._apply_collapsed()
        if callable(getattr(self, 'on_collapse', None)):
            self.on_collapse(self.collapsed)

    def _apply_collapsed(self):
        self.configure(width=self.NARROW if self.collapsed else self.WIDE)
        for _row, _icon, label, _marker in self.rows.values():
            if self.collapsed:
                label.pack_forget()
            elif not label.winfo_manager():
                label.pack(side='left', fill='x', expand=True)
        if self.collapsed:
            self.brand.pack_forget()
            for label in self.group_labels:
                label.configure(text='─' * 2, anchor='center', padx=0)
        else:
            if not self.brand.winfo_manager():
                self.brand.pack(side='left')
            groups = [s.group for s in ui_nav.SECTIONS]
            names = [g for i, g in enumerate(groups) if g and g not in groups[:i]]
            for label, name in zip(self.group_labels, names):
                label.configure(text=name.upper(), anchor='w', padx=16)


class StatusBar(tk.Frame):
    """Barra inferior: mensagem, operação em andamento com progresso, projeto e estado."""

    def __init__(self, master, message_var: tk.StringVar):
        super().__init__(master, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        self.saved = tk.Label(self, text='', bg=SURFACE, fg=MUTED, padx=10, font=font(9, 'bold'))
        self.saved.pack(side='right')
        self._sep(); self.disc = tk.Label(self, text='', bg=SURFACE, fg=MUTED, padx=10, font=font(9))
        self.disc.pack(side='right')
        self._sep(); self.project = tk.Label(self, text='Nenhum projeto', bg=SURFACE, fg=MUTED, padx=10,
                                             font=font(9))
        self.project.pack(side='right')
        # Empacotada por último: em janelas estreitas é a mensagem que encolhe,
        # não o projeto, a base e o estado salvo.
        self.message = tk.Label(self, textvariable=message_var, bg=SURFACE, fg=MUTED, anchor='w',
                                padx=12, pady=5, font=font(9))
        self.message.pack(side='left', fill='x', expand=True)
        self.operation = tk.Frame(self, bg=SURFACE)
        self.operation_label = tk.Label(self.operation, text='', bg=SURFACE, fg=ACCENT, font=font(9, 'bold'),
                                        padx=8)
        self.operation_label.pack(side='left')
        self.progress = ttk.Progressbar(self.operation, length=160, mode='indeterminate')
        self.progress.pack(side='left', padx=(0, 10), pady=4)

    def _sep(self):
        tk.Frame(self, bg=BORDER, width=1).pack(side='right', fill='y', pady=4)

    def set_project(self, name: str | None, folder: str | None = None):
        self.project.configure(text=f'Projeto: {name}' if name else 'Nenhum projeto',
                               fg=TEXT if name else MUTED)
        self._project_folder = folder

    def set_disc(self, text: str):
        self.disc.configure(text=text)

    def set_saved(self, pending: int, *, has_project: bool):
        if not has_project:
            self.saved.configure(text='', fg=MUTED)
        elif pending:
            self.saved.configure(text=f'● {pending} alteração(ões) não salva(s)', fg=WARNING)
        else:
            self.saved.configure(text='✓ Salvo', fg=ACCENT)

    def begin(self, text: str, *, total: int | None = None):
        """Mostra uma operação. Sem ``total`` a barra fica indeterminada (sem % inventado)."""
        self.operation_label.configure(text=text)
        if total:
            self.progress.stop()
            self.progress.configure(mode='determinate', maximum=total, value=0)
        else:
            self.progress.configure(mode='indeterminate')
            self.progress.start(12)
        if not self.operation.winfo_manager():
            self.operation.pack(side='left', before=self.message)

    def step(self, value: int, text: str | None = None):
        self.progress.configure(value=value)
        if text:
            self.operation_label.configure(text=text)

    def end(self):
        self.progress.stop()
        self.operation.pack_forget()

    def flash_error(self, text: str):
        self.message.configure(fg=DANGER)
        self.after(4000, lambda: self.message.configure(fg=MUTED))


class CommandPalette(tk.Toplevel):
    """Busca rápida de telas e ações (Ctrl+K)."""

    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.withdraw()
        self.overrideredirect(True)
        self.configure(bg=BORDER)
        frame = tk.Frame(self, bg=SURFACE, padx=10, pady=10)
        frame.pack(fill='both', expand=True, padx=1, pady=1)
        tk.Label(frame, text='Ir para tela ou ação  ·  Enter abre  ·  Esc fecha', bg=SURFACE, fg=MUTED,
                 font=font(9)).pack(anchor='w', pady=(0, 6))
        self.query = tk.StringVar()
        self.entry = ttk.Entry(frame, textvariable=self.query, style='Search.TEntry', font=font(11))
        self.entry.pack(fill='x')
        self.listbox = tk.Listbox(frame, bg=SURFACE, fg=TEXT, selectbackground=SELECT, selectforeground=TEXT,
                                  activestyle='none', highlightthickness=0, borderwidth=0, font=font(10),
                                  height=12)
        self.listbox.pack(fill='both', expand=True, pady=(8, 0))
        self.items = []
        self.query.trace_add('write', lambda *_: self.refresh())
        self.entry.bind('<Down>', lambda _e: self._move(1))
        self.entry.bind('<Up>', lambda _e: self._move(-1))
        self.entry.bind('<Return>', lambda _e: self.run())
        self.listbox.bind('<Double-1>', lambda _e: self.run())
        self.listbox.bind('<Return>', lambda _e: self.run())
        for widget in (self, self.entry, self.listbox):
            widget.bind('<Escape>', lambda _e: self.close())
        self.bind('<FocusOut>', self._focus_out)

    def open(self):
        self.query.set('')
        self.refresh()
        self.update_idletasks()
        width = 520
        x = self.studio.winfo_rootx() + max(0, (self.studio.winfo_width() - width) // 2)
        y = self.studio.winfo_rooty() + 70
        self.geometry(f'{width}x360+{x}+{y}')
        self.deiconify()
        self.lift()
        self.entry.focus_force()

    def close(self):
        self.withdraw()
        try:
            self.studio.focus_set()
        except tk.TclError:
            pass

    def _focus_out(self, _event):
        self.after(120, self._close_if_outside)

    def _close_if_outside(self):
        if not self.winfo_viewable():
            return
        try:
            focus = self.focus_get()
            inside = focus is not None and focus.winfo_toplevel() is self
        except (KeyError, tk.TclError):
            inside = False
        if not inside:
            self.close()

    def refresh(self):
        self.items = ui_nav.search(self.query.get())
        self.listbox.delete(0, 'end')
        for kind, item in self.items:
            if kind == 'secao':
                group = f'{item.group} › ' if item.group else ''
                self.listbox.insert('end', f'  {item.icon}   {group}{item.label}')
            else:
                shortcut = f'    [{item.shortcut}]' if item.shortcut else ''
                self.listbox.insert('end', f'  ▸   {item.label}{shortcut}')
        if self.items:
            self.listbox.selection_set(0)

    def _move(self, delta):
        if not self.items:
            return 'break'
        current = (self.listbox.curselection() or (0,))[0]
        index = max(0, min(len(self.items) - 1, current + delta))
        self.listbox.selection_clear(0, 'end')
        self.listbox.selection_set(index)
        self.listbox.see(index)
        return 'break'

    def run(self):
        selection = self.listbox.curselection()
        if not selection or not self.items:
            return 'break'
        kind, item = self.items[selection[0]]
        self.close()
        if kind == 'secao':
            self.studio.show_section(item.key)
        else:
            self.studio.run_action(item.method)
        return 'break'
