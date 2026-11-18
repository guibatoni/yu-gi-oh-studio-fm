"""Campaign donation quests in the PS1 mod editor."""
from __future__ import annotations

import json
from pathlib import Path
import secrets
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .campaign_quests import normalize_overrides
from .core import ModError, ps1_supports_god24
from .ps1_campaign_quests import preview_project_quests, quest_settings, save_quest_settings
from .tables import DUELIST_NAMES_REFERENCE


class CampaignQuestEditor(ttk.Frame):
    def __init__(self, parent, studio):
        super().__init__(parent)
        self.pack(fill='both', expand=True)
        self.studio = studio
        self.project = None
        self.requirements = {}
        self.enabled = tk.BooleanVar(self)
        self.seed = tk.StringVar(self)
        self.status = tk.StringVar(self)
        self.manual_status = tk.StringVar(self)

        ttk.Label(self, text='Doações para avançar na campanha',
                  font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 5))
        ttk.Label(self, text='Ao vencer um duelista, confira o progresso no baú e confirme a entrega '
                  'para continuar a história. As cartas do deck ativo ficam protegidas.',
                  wraplength=675, justify='left').pack(anchor='w', pady=(0, 8))
        self.toggle = ttk.Checkbutton(self, text='Ativar quests no BIN/CUE de teste', variable=self.enabled)
        self.toggle.pack(anchor='w')

        settings = ttk.Frame(self)
        settings.pack(fill='x', pady=8)
        ttk.Label(settings, text='Seed').pack(side='left', padx=(0, 5))
        self.seed_entry = ttk.Entry(settings, width=20, textvariable=self.seed)
        self.seed_entry.pack(side='left')
        self.random_button = ttk.Button(settings, text='Sortear seed', command=self._random_seed)
        self.random_button.pack(side='left', padx=5)
        self.preview_button = ttk.Button(settings, text='Gerar prévia', command=self._preview)
        self.preview_button.pack(side='left')
        self.save_button = ttk.Button(settings, text='Salvar configuração', style='Accent.TButton',
                                      command=self._save)
        self.save_button.pack(side='right')

        manual = ttk.Frame(self)
        manual.pack(fill='x', pady=(0, 7))
        self.import_button = ttk.Button(manual, text='Importar requisitos JSON', command=self._import)
        self.import_button.pack(side='left')
        self.clear_button = ttk.Button(manual, text='Remover importados', command=self._clear_manual)
        self.clear_button.pack(side='left', padx=5)
        ttk.Label(manual, textvariable=self.manual_status).pack(side='left', padx=4)

        preview = ttk.Frame(self)
        preview.pack(fill='both', expand=True)
        columns = (('duelist', 'Duelista', 155), ('requirement', 'Doação', 195),
                   ('source', 'Fonte disponível', 190), ('odds', 'Peso / 2048', 100))
        self.table = ttk.Treeview(preview, columns=[col[0] for col in columns], show='headings', height=8)
        for key, label, width in columns:
            self.table.heading(key, text=label)
            self.table.column(key, width=width, minwidth=75, anchor='e' if key == 'odds' else 'w')
        scroll = ttk.Scrollbar(preview, command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        ttk.Label(self, textvariable=self.status, wraplength=675).pack(anchor='w', pady=(7, 0))
        self.seed.trace_add('write', self._invalidate_preview)
        self._load(None)

    def set_project(self, project):
        if project is not self.project:
            self._load(project)

    def _load(self, project):
        self.project = project
        state = 'normal' if project else 'disabled'
        for control in (self.toggle, self.seed_entry, self.random_button, self.preview_button,
                        self.save_button, self.import_button):
            control.configure(state=state)
        error = ''
        try:
            settings = quest_settings(project)
        except ModError as exc:
            settings = quest_settings(None)
            error = str(exc)
        self.enabled.set(settings['ativado'])
        self.seed.set(settings['seed'])
        self.requirements = settings['requisitos']
        self._manual_changed()
        if error:
            self.status.set(error)
        elif not project:
            self.status.set('Abra um projeto para configurar a campanha.')
        elif not ps1_supports_god24(project):
            self.status.set('A exportação de quests usa o BIN/CUE Original Drop x15 importado no projeto.')
        else:
            self.status.set('Gere a prévia com os drops e o deck inicial salvos no projeto.')

    def _invalidate_preview(self, *_):
        items = self.table.get_children()
        if items:
            self.table.delete(*items)
            self.status.set('Gere uma nova prévia para conferir os requisitos.')

    def _manual_changed(self):
        self.clear_button.configure(state='normal' if self.requirements else 'disabled')
        self.manual_status.set(f'{len(self.requirements)} duelista(s) com requisitos importados'
                               if self.requirements else 'Requisitos gerados pela seed')
        self._invalidate_preview()

    def _random_seed(self):
        self.seed.set(secrets.token_hex(6))

    def _import(self):
        path = filedialog.askopenfilename(parent=self, title='Importar requisitos das quests',
                                         filetypes=[('Quests JSON', '*.json')])
        if not path:
            return
        try:
            self.requirements = normalize_overrides(json.loads(Path(path).read_text(encoding='utf-8-sig')))
        except (OSError, ModError, ValueError) as exc:
            messagebox.showerror('Requisitos das quests', str(exc), parent=self)
            return
        self._manual_changed()
        self.status.set('Requisitos carregados. Gere a prévia para validar as fontes de cada doação.')

    def _clear_manual(self):
        self.requirements = {}
        self._manual_changed()

    def _preview(self):
        if not self.project or self.studio._extract_running:
            return
        self.studio._stage_current()
        if self.studio.drafts and self.studio.drafts.is_dirty:
            self.status.set('Salve as alterações das cartas para atualizar a prévia das quests.')
            return
        seed = self.seed.get().strip()
        if not 1 <= len(seed) <= 80:
            messagebox.showerror('Seed da campanha', 'Informe uma seed de 1 a 80 caracteres.', parent=self)
            return
        source = self.project.metadata.get('base_source')
        if not source or not Path(source).is_file():
            source = filedialog.askopenfilename(parent=self, title='BIN/CUE Original Drop x15 do projeto',
                                               filetypes=[('PlayStation BIN/CUE', '*.bin *.cue')])
        if not source:
            return
        self._invalidate_preview()
        self.status.set('Conferindo os drops e as fontes de cada doação…')
        self.update_idletasks()
        try:
            config = preview_project_quests(self.project, Path(source), seed, self.requirements)
        except (OSError, ModError, ValueError) as exc:
            self.status.set('Confira a imagem de origem e os requisitos importados.')
            messagebox.showerror('Prévia das quests', str(exc), parent=self)
            return
        ranks = {'pow': 'S/A-POW', 'bcd': 'B/C/D', 'tec': 'S/A-TEC'}
        for quest in config['quests']:
            for requirement in quest['criterios']:
                proof = requirement['prova']
                origin = ('Deck inicial' if proof['origem'] == 'inicial' else
                          f"{DUELIST_NAMES_REFERENCE[proof['duelista_id']]} · {ranks[proof['grupo']]}")
                label = f"{requirement['rotulo']} ×{requirement['quantidade']}"
                self.table.insert('', 'end', values=(quest['oponente'], label, origin,
                                                     f"{proof['peso']} / {proof['denominador']}"))
        self.status.set(f"{len(config['quests'])} duelistas conferidos para a seed {seed}. "
                        'Salve a configuração e use Gerar jogo BIN/CUE.')

    def _save(self):
        if not self.project or self.studio._extract_running:
            return
        try:
            settings = save_quest_settings(self.project, enabled=self.enabled.get(), seed=self.seed.get(),
                                          requirements=self.requirements)
        except (OSError, ModError, ValueError) as exc:
            messagebox.showerror('Salvar quests', str(exc), parent=self)
            return
        self.status.set('Quests ativadas e salvas. Use Gerar jogo BIN/CUE para criar a cópia _QUESTS.'
                        if settings['ativado'] else 'Configuração salva com as quests desativadas.')
