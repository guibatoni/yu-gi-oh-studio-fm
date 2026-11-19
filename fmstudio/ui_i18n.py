"""Aplica o idioma escolhido aos widgets do Tkinter.

Só troca textos de exibição (rótulos, botões, caixas de marcar, títulos de
quadros, abas, cabeçalhos de tabela, menus e títulos de janela). Valores de
listas suspensas e variáveis nunca são traduzidos, porque o código os usa como
dados. O texto original em português fica guardado em cada widget, então trocar
de idioma (inclusive de volta para o português) funciona sem reiniciar.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog

from . import i18n

TEXT_CLASSES = {'Label', 'TLabel', 'Button', 'TButton', 'Checkbutton', 'TCheckbutton', 'Radiobutton',
                'TRadiobutton', 'Labelframe', 'TLabelframe', 'Menubutton', 'TMenubutton'}


def _remember(widget, key, value):
    store = widget.__dict__.setdefault('_i18n_original', {})
    if key not in store:
        store[key] = value
    elif value != i18n.translate(store[key]) and value != store[key]:
        store[key] = value          # o programa trocou o texto depois: este é o novo original
    return store[key]


def _translate_widget(widget):
    if widget.__dict__.get('_i18n_skip'):
        return
    try:
        cls = widget.winfo_class()
    except tk.TclError:
        return
    try:
        if cls in TEXT_CLASSES:
            if str(widget.cget('textvariable') or ''):
                return
            current = widget.cget('text')
            if isinstance(current, str) and current:
                original = _remember(widget, 'text', current)
                new = i18n.translate(original)
                if new != current:
                    widget.configure(text=new)
        elif cls == 'TNotebook':
            for index, tab in enumerate(widget.tabs()):
                current = widget.tab(tab, 'text')
                if current:
                    original = _remember(widget, f'tab{index}', current)
                    widget.tab(tab, text=i18n.translate(original))
        elif cls == 'Treeview':
            for column in widget['columns']:
                current = widget.heading(column, 'text')
                if current:
                    original = _remember(widget, f'col:{column}', current)
                    widget.heading(column, text=i18n.translate(original))
        elif cls == 'Menu':
            last = widget.index('end')
            if last is not None:
                for index in range(last + 1):
                    if widget.type(index) in ('command', 'cascade', 'checkbutton', 'radiobutton'):
                        current = widget.entrycget(index, 'label')
                        if current:
                            original = _remember(widget, f'menu{index}', current)
                            widget.entryconfigure(index, label=i18n.translate(original))
        elif cls in ('Toplevel', 'Tk'):
            current = widget.title()
            if current:
                original = _remember(widget, 'title', current)
                new = i18n.translate(original)
                if new != current:
                    widget.title(new)
    except tk.TclError:
        pass


def translate_tree(root):
    """Percorre ``root`` e todos os filhos (inclusive menus e janelas filhas)."""
    stack = [root]
    while stack:
        widget = stack.pop()
        _translate_widget(widget)
        try:
            stack.extend(widget.winfo_children())
        except tk.TclError:
            pass


_patched = False


def patch_dialogs():
    """Caixas de mensagem e perguntas também passam pelo catálogo (textos fixos)."""
    global _patched
    if _patched:
        return
    _patched = True
    for name in ('showinfo', 'showwarning', 'showerror', 'askyesno', 'askyesnocancel', 'askokcancel',
                 'askquestion', 'askretrycancel'):
        original = getattr(messagebox, name)

        def wrapper(title=None, message=None, *args, _original=original, **kwargs):
            return _original(i18n.translate(title) if title else title,
                             i18n.translate(message) if message else message, *args, **kwargs)
        setattr(messagebox, name, wrapper)
    for name in ('askstring', 'askinteger', 'askfloat'):
        original = getattr(simpledialog, name)

        def wrapper(title, prompt, *args, _original=original, **kwargs):
            return _original(i18n.translate(title), i18n.translate(prompt), *args, **kwargs)
        setattr(simpledialog, name, wrapper)
