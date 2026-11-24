"""Aba Fundo do menu: papel de parede do menu principal do PS1."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core import ModError
from . import ps1_menu_wallpaper as wallpaper

IMAGE_TYPES = (('Imagens', '*.png *.jpg *.jpeg *.webp *.bmp *.gif'), ('Todos os arquivos', '*.*'))


class MenuWallpaperEditor(ttk.Frame):
    def __init__(self, parent, studio):
        super().__init__(parent)
        self.pack(fill='both', expand=True)
        self.studio, self.project = studio, None
        self.enabled = tk.BooleanVar(self)
        self.mode = tk.StringVar(self, value='imagem')
        self.tile = tk.IntVar(self, value=64)
        self.source = ''
        self._photo = None
        ttk.Label(self, text='Papel de parede do menu principal (PS1)',
                  font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 6))
        ttk.Label(self, text='Troca a "parede" que aparece atrás do menu principal. A textura do jogo tem '
                             '256x240 px e 16 cores: a imagem é recortada e reduzida para isso. A tela tem '
                             '320 px de largura, então as primeiras 64 colunas se repetem à direita '
                             '(a prévia mostra exatamente isso). Só dados do SU.MRG mudam; nenhum código.',
                  wraplength=760).pack(anchor='w')
        ttk.Checkbutton(self, text='Usar este papel de parede no BIN/CUE',
                        variable=self.enabled).pack(anchor='w', pady=(8, 4))
        modes = ttk.Frame(self)
        modes.pack(anchor='w', pady=(0, 4))
        ttk.Radiobutton(modes, text='Imagem de tela inteira', value='imagem', variable=self.mode,
                        command=self._refresh).pack(side='left')
        ttk.Radiobutton(modes, text='Ladrilho repetido', value='ladrilho', variable=self.mode,
                        command=self._refresh).pack(side='left', padx=(12, 0))
        ttk.Label(modes, text='Tamanho do ladrilho (px):').pack(side='left', padx=(16, 4))
        size = ttk.Spinbox(modes, from_=8, to=256, increment=8, width=5, textvariable=self.tile,
                           command=self._refresh)
        size.pack(side='left')
        size.bind('<Return>', lambda _e: self._refresh())
        ttk.Label(self, text='Dica: no ladrilho, tamanhos que dividem 256 (16, 32, 64, 128) emendam sem '
                             'costura na horizontal.', foreground='#5a6b7d').pack(anchor='w')
        actions = ttk.Frame(self)
        actions.pack(fill='x', pady=(8, 6))
        ttk.Button(actions, text='Importar imagem…', command=self._import).pack(side='left')
        ttk.Button(actions, text='Salvar fundo do menu', style='Accent.TButton',
                   command=self._save).pack(side='right')
        self.canvas = tk.Label(self, relief='groove', text='Sem imagem: o menu usa a parede original.',
                               width=80, height=12)
        self.canvas.pack(anchor='w', pady=(4, 4))
        self.status = tk.StringVar(self)
        ttk.Label(self, textvariable=self.status, foreground='#5a6b7d', wraplength=760).pack(anchor='w')
        self.set_project(None)

    def set_project(self, project):
        self.project = project
        current = wallpaper.settings(project) if project else wallpaper.settings(None)
        self.enabled.set(current['ativado'])
        self.mode.set(current['modo'])
        self.tile.set(current['ladrilho'])
        self.source = current['origem']
        self._show_saved()

    def _show_saved(self):
        if not self.project:
            self._show(None)
            return
        path = wallpaper.image_path(self.project)
        if path.exists():
            from PIL import Image
            with Image.open(path) as opened:
                self._show(opened.convert('RGB'))
        else:
            self._show(None)

    def _show(self, wall):
        if wall is None:
            self._photo = None
            self.canvas.configure(image='', text='Sem imagem: o menu usa a parede original.',
                                  width=80, height=12)
            return
        from PIL import Image, ImageTk
        screen = wallpaper.preview(wall).resize((480, 360), Image.Resampling.NEAREST)
        self._photo = ImageTk.PhotoImage(screen)
        self.canvas.configure(image=self._photo, text='', width=480, height=360)

    def _refresh(self):
        if not self.source:
            return
        try:
            self._show(wallpaper.compose(self.source, self.mode.get(), self.tile.get()))
            self.status.set('Prévia com 16 cores, como o PS1 mostra. Salve para gravar no projeto.')
        except (OSError, ValueError, tk.TclError, ModError) as exc:
            self.status.set(f'Não foi possível ler a imagem: {exc}')

    def _import(self):
        path = filedialog.askopenfilename(parent=self, title='Imagem do fundo do menu', filetypes=IMAGE_TYPES)
        if path:
            self.source = path
            self.enabled.set(True)
            self._refresh()

    def _save(self):
        if not self.project:
            messagebox.showinfo('Fundo do menu', 'Abra um projeto primeiro.', parent=self)
            return
        try:
            tile = int(self.tile.get())
        except (tk.TclError, ValueError):
            tile = 64
        try:
            saved = wallpaper.save(self.project, enabled=self.enabled.get(), mode=self.mode.get(),
                                   source=self.source, tile=tile)
        except (ModError, OSError, ValueError) as exc:
            messagebox.showerror('Fundo do menu', str(exc), parent=self)
            return
        self._show_saved()
        self.status.set('Fundo do menu salvo. Gere um BIN/CUE novo.' if saved['ativado']
                        else 'Fundo do menu desativado: o BIN mantém a parede original.')
