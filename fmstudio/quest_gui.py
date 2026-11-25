"""Campaign donation quests in the PS1 mod editor."""
from __future__ import annotations

import json
from pathlib import Path
import secrets
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .campaign_quests import (CATEGORY_NAMES, MAX_CRITERIA, PHRASE_LINE, PHRASE_LINES, STORY_DUELISTS,
                              normalize_overrides, normalize_phrases)
from .core import ModError, ps1_supports_god24
from .ps1_campaign_quests import preview_project_quests, quest_settings, save_quest_settings
from .tables import CARD_COUNT, DUELIST_NAMES_REFERENCE


CRITERION_LABELS = {'': 'Vazio', 'carta': 'Carta', 'tipo': 'Tipo', 'atributo': 'Atributo',
                    'guardian_star': 'Guardian Star', 'raridade': 'Raridade'}


class QuestRequirementsDialog(tk.Toplevel):
    def __init__(self, parent, opponent, cards, requirements, phrase=''):
        super().__init__(parent)
        self.title(f'Quest de {DUELIST_NAMES_REFERENCE[opponent]}')
        self.transient(parent.winfo_toplevel())
        self.opponent = str(opponent)
        self.result = None
        self.phrase_result = None
        self.inputs = []
        self.labels = {label: kind for kind, label in CRITERION_LABELS.items()}
        self.targets = {kind: [f'{idx} · {label}' for idx, label in enumerate(names) if label]
                        for kind, names in CATEGORY_NAMES.items()}
        self.targets['carta'] = [f'{cid} · {card.get("nome") or f"Carta {cid}"}'
                                 for cid, card in cards.items()]

        pane = ttk.Frame(self, padding=13)
        pane.pack(fill='both', expand=True)
        ttk.Label(pane, text='Escolha o critério, o alvo e a quantidade. Digite o nome ou o ID para buscar cartas, '
                             'ou use Procurar… para ver a lista com filtros.',
                  wraplength=600).grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 9))
        for column, label in enumerate(('Critério', 'Carta ou categoria', 'Quantidade')):
            ttk.Label(pane, text=label).grid(row=1, column=column, sticky='w', padx=4)
        pane.columnconfigure(1, weight=1)
        for index in range(MAX_CRITERIA):
            row = index + 2
            initial = requirements[index] if index < len(requirements) else {}
            kind = tk.StringVar(self, value=CRITERION_LABELS[initial.get('tipo', '')])
            quantity = tk.StringVar(self, value=str(initial.get('quantidade', 1)))
            selector = ttk.Combobox(pane, width=13, state='readonly', textvariable=kind,
                                    values=list(self.labels))
            selector.grid(row=row, column=0, padx=4, pady=4, sticky='ew')
            target = ttk.Combobox(pane, width=32)
            target.grid(row=row, column=1, padx=4, pady=4, sticky='ew')
            amount = ttk.Spinbox(pane, from_=1, to=255, width=5, textvariable=quantity)
            amount.grid(row=row, column=2, padx=4, pady=4, sticky='ew')
            browse = ttk.Button(pane, text='Procurar…', width=10)
            browse.grid(row=row, column=3, padx=4, pady=4)
            self.inputs.append((kind, target, quantity))

            def pick(*, target=target):
                from .card_picker import CardPickerDialog

                def chosen(ids):
                    prefix = f'{ids[0]} · '
                    target.set(next((label for label in self.targets['carta'] if label.startswith(prefix)),
                                    str(ids[0])))
                CardPickerDialog(self, cards, chosen, title='Carta pedida na quest')

            browse.configure(command=pick)

            def set_kind(_event=None, *, kind=kind, target=target, amount=amount, browse=browse):
                key = self.labels[kind.get()]
                target.set('')
                target.configure(values=self.targets.get(key, ()),
                                 state='normal' if key == 'carta' else 'readonly' if key else 'disabled')
                amount.configure(state='normal' if key else 'disabled')
                browse.configure(state='normal' if key == 'carta' else 'disabled')

            def search(_event, *, kind=kind, target=target):
                if self.labels[kind.get()] == 'carta':
                    query = target.get().casefold().lstrip('#').strip()
                    target.configure(values=[value for value in self.targets['carta']
                                             if query in value.casefold()])

            selector.bind('<<ComboboxSelected>>', set_kind)
            target.bind('<KeyRelease>', search)
            set_kind()
            if initial:
                prefix = f"{initial['alvo']} · "
                target.set(next((label for label in self.targets[initial['tipo']] if label.startswith(prefix)),
                                str(initial['alvo'])))

        speech = ttk.LabelFrame(pane, text='Frase do duelista antes do pedido', padding=8)
        speech.grid(row=MAX_CRITERIA + 2, column=0, columnspan=4, sticky='ew', pady=(10, 0))
        ttk.Label(speech, text=f'Aparece numa página própria, antes dos requisitos. Até {PHRASE_LINES} linhas '
                               f'de {PHRASE_LINE} caracteres; acentos são removidos (a fonte do PS1 não os tem). '
                               'Deixe vazio para não mostrar frase.', wraplength=540).pack(anchor='w')
        self.phrase = tk.Text(speech, height=2, width=PHRASE_LINE + 6, wrap='word', font=('Consolas', 11))
        self.phrase.pack(anchor='w', pady=(5, 3))
        self.phrase.insert('1.0', phrase.replace('\n', ' '))
        self.phrase_preview = tk.StringVar(self)
        ttk.Label(speech, textvariable=self.phrase_preview, font=('Consolas', 10), justify='left').pack(anchor='w')
        self.phrase.bind('<KeyRelease>', self._preview_phrase)
        self._preview_phrase()

        actions = ttk.Frame(self, padding=(13, 0, 13, 12))
        actions.pack(side='bottom', fill='x', before=pane)       # sempre visível
        ttk.Button(actions, text='Usar a seed deste NPC', command=self._restore).pack(side='left')
        ttk.Button(actions, text='Cancelar', command=self.destroy).pack(side='right', padx=(6, 0))
        ttk.Button(actions, text='Aplicar requisitos', style='Accent.TButton', command=self._apply).pack(side='right')
        self.grab_set()

    def _phrase_text(self):
        return self.phrase.get('1.0', 'end').strip()

    def _preview_phrase(self, _event=None):
        try:
            text = normalize_phrases({self.opponent: self._phrase_text()}).get(self.opponent, '')
        except ModError as exc:
            self.phrase_preview.set(f'⚠ {exc}')
            return
        self.phrase_preview.set('No PS1:\n' + text if text else 'Sem frase: o pedido começa em "Antes do duelo".')

    def _restore(self):
        self.result = []
        self.phrase_result = self._phrase_text()
        self.destroy()

    def _apply(self):
        rows = [{'tipo': self.labels[kind.get()],
                 'alvo': target.get().split(' · ', 1)[0].strip().lstrip('#'),
                 'quantidade': quantity.get()} for kind, target, quantity in self.inputs
                if self.labels[kind.get()]]
        try:
            self.result = normalize_overrides({self.opponent: rows})[self.opponent]
            self.phrase_result = normalize_phrases({self.opponent: self._phrase_text()}).get(self.opponent, '')
        except ModError as exc:
            messagebox.showerror('Editar quest', str(exc), parent=self)
            return
        self.destroy()


class CampaignQuestEditor(ttk.Frame):
    def __init__(self, parent, studio):
        super().__init__(parent)
        self.pack(fill='both', expand=True)
        self.studio = studio
        self.project = None
        self.requirements = {}
        self.phrases = {}
        self.preview_requirements = {}
        self.enabled = tk.BooleanVar(self)
        self.seed = tk.StringVar(self)
        self.status = tk.StringVar(self)
        self.manual_status = tk.StringVar(self)

        ttk.Label(self, text='Doações para avançar na campanha',
                  font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 5))
        ttk.Label(self, text='Simon Muran está liberado. Antes dos outros duelos, entregue as cópias '
                  'do baú. Volte ao Card Shop para preparar o deck ou buscar cartas no Duelo Livre.',
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

        editor = ttk.Frame(self)
        editor.pack(fill='x', pady=(0, 7))
        ttk.Label(editor, text='Duelista').pack(side='left', padx=(0, 5))
        self.duelists = {f'#{op:02d} · {DUELIST_NAMES_REFERENCE[op]}': op for op in STORY_DUELISTS}
        self.opponent = ttk.Combobox(editor, state='readonly', values=list(self.duelists), width=27)
        self.opponent.pack(side='left')
        self.opponent.current(0)
        self.edit_button = ttk.Button(editor, text='Editar quest', command=self._edit_quest)
        self.edit_button.pack(side='left', padx=5)

        manual = ttk.Frame(self)
        manual.pack(fill='x', pady=(0, 7))
        self.import_button = ttk.Button(manual, text='Importar requisitos JSON', command=self._import)
        self.import_button.pack(side='left')
        self.clear_button = ttk.Button(manual, text='Limpar requisitos manuais', command=self._clear_manual)
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
        self.table.bind('<Double-1>', self._select_preview)
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
                        self.save_button, self.import_button, self.edit_button):
            control.configure(state=state)
        self.opponent.configure(state='readonly' if project else 'disabled')
        error = ''
        try:
            settings = quest_settings(project)
        except ModError as exc:
            settings = quest_settings(None)
            error = str(exc)
        self.enabled.set(settings['ativado'])
        self.seed.set(settings['seed'])
        self.requirements = settings['requisitos']
        self.phrases = dict(settings.get('frases', {}))
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
        self.preview_requirements = {}
        items = self.table.get_children()
        if items:
            self.table.delete(*items)
            self.status.set('Gere uma nova prévia para conferir os requisitos.')

    def _manual_changed(self):
        self.clear_button.configure(state='normal' if self.requirements else 'disabled')
        self.manual_status.set(f'{len(self.requirements)} duelista(s) com requisitos manuais'
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

    def _select_preview(self, event):
        item = self.table.identify_row(event.y)
        if item:
            opponent = self.table.item(item, 'values')[0]
            self.opponent.set(next(label for label, op in self.duelists.items()
                                   if DUELIST_NAMES_REFERENCE[op] == opponent))
            self._edit_quest()

    def _edit_quest(self):
        if not self.project or self.studio._extract_running:
            return
        opponent = self.duelists.get(self.opponent.get())
        if opponent is None:
            return
        key = str(opponent)
        requirements = self.requirements.get(key, self.preview_requirements.get(key, []))
        cards = {cid: self.project.get(cid) for cid in sorted(self.project.cards) if cid <= CARD_COUNT}
        dialog = QuestRequirementsDialog(self, opponent, cards, requirements, self.phrases.get(key, ''))
        self.wait_window(dialog)
        if dialog.result is None:
            return
        try:
            phrase = normalize_phrases({key: dialog.phrase_result or ''}).get(key, '')
        except ModError as exc:
            messagebox.showerror('Frase da quest', str(exc), parent=self)
            phrase = self.phrases.get(key, '')
        if phrase:
            self.phrases[key] = phrase
        else:
            self.phrases.pop(key, None)
        if dialog.result:
            self.requirements[key] = dialog.result
        else:
            self.requirements.pop(key, None)
        self._manual_changed()
        self.status.set('Quest editada. Gere a prévia para validar a origem das cartas e salve a configuração.')

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
        ranks = {'pow': 'S/A-POW', 'bcd': 'B/C/D', 'tec': 'S/A-TEC', 'fixo': 'drop fixo (1ª vitória)'}
        for quest in config['quests']:
            self.preview_requirements[str(quest['oponente_id'])] = quest['criterios']
            for requirement in quest['criterios']:
                proof = requirement['prova']
                origin = f"{DUELIST_NAMES_REFERENCE[proof['duelista_id']]} · {ranks[proof['grupo']]}"
                label = f"{requirement['rotulo']} ×{requirement['quantidade']}"
                self.table.insert('', 'end', values=(quest['oponente'], label, origin,
                                                     'garantido' if proof['grupo'] == 'fixo'
                                                     else f"{proof['peso']} / {proof['denominador']}"))
        self.status.set(f"{len(config['quests'])} duelistas conferidos para a seed {seed}. "
                        'Salve a configuração e use Gerar jogo BIN/CUE.')

    def _save(self):
        if not self.project or self.studio._extract_running:
            return
        try:
            settings = save_quest_settings(self.project, enabled=self.enabled.get(), seed=self.seed.get(),
                                          requirements=self.requirements, phrases=self.phrases)
        except (OSError, ModError, ValueError) as exc:
            messagebox.showerror('Salvar quests', str(exc), parent=self)
            return
        self.status.set('Quests ativadas e salvas. Use Gerar jogo BIN/CUE para criar a cópia _QUESTS.'
                        if settings['ativado'] else 'Configuração salva com as quests desativadas.')
