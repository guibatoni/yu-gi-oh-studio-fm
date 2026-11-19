"""Sistema visual do Studio: paleta, tipografia, espaçamentos e estilos ttk.

Todas as telas usam estas constantes (``gui.py`` as reexporta com os nomes
antigos BG, SURFACE, ...). Sem dependências externas: só ttk/clam.
"""
from __future__ import annotations

# Paleta (tema escuro). Contraste do texto principal sobre BG/SURFACE > 12:1,
# do texto secundário (MUTED) > 7:1.
BG = '#0d1220'          # fundo da área de trabalho
SURFACE = '#171f32'     # painéis, campos
SURFACE2 = '#212c44'    # botões, cabeçalhos
SURFACE3 = '#2b3854'    # hover
NAV_BG = '#0a0f1b'      # barra lateral
TEXT = '#f2f5fb'
MUTED = '#a8b5cb'
FAINT = '#7f8da5'       # desabilitado
ACCENT = '#32cfb4'      # ação principal, item ativo
ACCENT_DARK = '#1b6f63'
BLUE = '#589bfa'
BORDER = '#344259'
ROW_ALT = '#1c263a'
SELECT = '#265b67'
WARNING = '#edc47e'
DANGER = '#ff8f9c'
SUCCESS = ACCENT

FONT = 'Segoe UI'
MONO = 'Consolas'
SIZE = 10
PAD = 8                 # espaçamento padrão
PAD_L = 14


def font(size: int = SIZE, weight: str = 'normal'):
    return (FONT, size, weight) if weight != 'normal' else (FONT, size)


def apply(root) -> None:
    """Configura todos os estilos ttk usados pelo Studio."""
    from tkinter import ttk
    s = ttk.Style(root)
    s.theme_use('clam')
    s.configure('.', font=font(), background=BG, foreground=TEXT, fieldbackground=SURFACE,
                bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, focuscolor=ACCENT,
                troughcolor=BG, selectbackground=SELECT, selectforeground=TEXT,
                insertcolor=TEXT)
    s.configure('TFrame', background=BG)
    s.configure('Card.TFrame', background=SURFACE)
    s.configure('TLabel', background=BG, foreground=TEXT)
    s.configure('Muted.TLabel', foreground=MUTED)
    s.configure('Title.TLabel', font=font(15, 'bold'))
    s.configure('Section.TLabel', font=font(11, 'bold'), foreground=ACCENT)
    s.configure('Card.TLabel', background=SURFACE)
    s.configure('CardMuted.TLabel', background=SURFACE, foreground=MUTED)
    for style, resting, hover, pressed, color in (
            ('TButton', SURFACE2, '#354562', '#283852', TEXT),
            ('TMenubutton', SURFACE2, '#354562', '#283852', TEXT),
            ('Accent.TButton', ACCENT, '#60e2cb', '#25a992', '#06171a'),
            ('Danger.TButton', '#3b293b', '#603347', '#4b2939', '#ffd9df'),
            ('Ghost.TButton', BG, SURFACE2, SURFACE, MUTED)):
        s.configure(style, background=resting, foreground=color, padding=(10, 6), relief='flat',
                    borderwidth=1)
        s.map(style, background=[('disabled', '#172033'), ('pressed', pressed), ('active', hover)],
              foreground=[('disabled', FAINT)] + ([('active', TEXT)] if style == 'Ghost.TButton' else []),
              bordercolor=[('focus', ACCENT)])
    s.configure('Accent.TButton', font=font(SIZE, 'bold'))
    s.configure('Small.TButton', padding=(6, 3))
    s.configure('TCheckbutton', padding=(5, 5), indicatorbackground=SURFACE2)
    s.map('TCheckbutton', background=[('active', SURFACE2)],
          foreground=[('disabled', FAINT)],
          indicatorbackground=[('selected', ACCENT), ('pressed', '#25a992')])
    s.configure('TRadiobutton', padding=(5, 4), indicatorbackground=SURFACE2)
    s.map('TRadiobutton', background=[('active', SURFACE2)], foreground=[('disabled', FAINT)],
          indicatorbackground=[('selected', ACCENT)])
    s.configure('TSpinbox', fieldbackground=SURFACE, foreground=TEXT, insertcolor=TEXT, padding=(4, 3),
                arrowcolor=MUTED, background=SURFACE2)
    s.configure('TEntry', fieldbackground=SURFACE, foreground=TEXT, padding=(7, 8), insertcolor=TEXT)
    s.map('TEntry', bordercolor=[('focus', ACCENT)], lightcolor=[('focus', ACCENT)])
    s.configure('Search.TEntry', padding=(9, 7))
    s.configure('TCombobox', fieldbackground=SURFACE, foreground=TEXT, selectbackground=SURFACE2,
                padding=(7, 7), arrowcolor=MUTED, background=SURFACE2)
    s.map('TCombobox', fieldbackground=[('readonly', SURFACE)], foreground=[('readonly', TEXT)],
          bordercolor=[('focus', ACCENT)])
    root.option_add('*TCombobox*Listbox.background', SURFACE)
    root.option_add('*TCombobox*Listbox.foreground', TEXT)
    root.option_add('*TCombobox*Listbox.selectBackground', SELECT)
    root.option_add('*TCombobox*Listbox.font', font())
    s.configure('TNotebook', background=BG, borderwidth=0)
    s.configure('TNotebook.Tab', background=SURFACE2, foreground=MUTED, padding=(10, 8))
    s.map('TNotebook.Tab', background=[('selected', SURFACE), ('active', '#354562')],
          foreground=[('selected', ACCENT), ('active', TEXT)])
    # Notebook cujas abas são escolhidas pela barra lateral: sem cabeçalho.
    s.configure('Hidden.TNotebook', background=BG, borderwidth=0, tabmargins=0)
    s.layout('Hidden.TNotebook.Tab', [])
    s.configure('Treeview', background=SURFACE, fieldbackground=SURFACE, foreground=TEXT, rowheight=27,
                borderwidth=0)
    s.map('Treeview', background=[('selected', SELECT)], foreground=[('selected', TEXT)])
    s.configure('Treeview.Heading', background=SURFACE2, foreground=TEXT, font=font(9, 'bold'),
                relief='flat', padding=(6, 5))
    s.map('Treeview.Heading', background=[('active', '#354562')])
    s.configure('TScrollbar', background=SURFACE2, troughcolor=BG, arrowcolor=MUTED, borderwidth=0)
    s.map('TScrollbar', background=[('active', SURFACE3)])
    s.configure('TLabelframe', background=BG, bordercolor=BORDER)
    s.configure('TLabelframe.Label', background=BG, foreground=ACCENT, font=font(SIZE, 'bold'))
    s.configure('TSeparator', background=BORDER)
    s.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor=SURFACE2, borderwidth=0,
                thickness=8, lightcolor=ACCENT, darkcolor=ACCENT)
    s.configure('TScale', background=SURFACE2, troughcolor=SURFACE)


def menu(parent):
    import tkinter as tk
    return tk.Menu(parent, tearoff=False, bg=SURFACE, fg=TEXT, activebackground='#354562',
                   activeforeground=TEXT, relief='flat', borderwidth=1, font=font())
