"""Janela "Traduzir descrições": escolhe idioma/cartas, traduz com progresso real e mostra a prévia."""
from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import translate
from .expanded import display_name
from .ui_theme import MUTED, WARNING, font


class TranslateDialog(tk.Toplevel):
    def __init__(self, studio, selected_ids=()):
        super().__init__(studio)
        self.studio = studio
        self.selected_ids = [int(c) for c in selected_ids]
        self.results = []
        self.messages = queue.Queue()
        self.cancel_flag = threading.Event()
        self.running = False
        self.title('Traduzir descrições das cartas')
        self.transient(studio)
        width = min(980, self.winfo_screenwidth() - 40)
        height = min(700, self.winfo_screenheight() - 100)
        self.geometry(f'{width}x{height}')
        self.minsize(min(760, width), min(520, height))
        prefs = studio.prefs.setdefault('traducao', {}) if isinstance(studio.prefs.get('traducao'), dict) else {}
        studio.prefs['traducao'] = prefs
        self.prefs = prefs
        self.language = tk.StringVar(value=translate.LANGUAGES.get(prefs.get('idioma', 'en'), translate.LANGUAGES['en']))
        self.provider = tk.StringVar(value=translate.PROVIDERS.get(prefs.get('tradutor', 'google'),
                                                                   translate.PROVIDERS['google']))
        self.api_key = tk.StringVar(value=prefs.get('chave_deepl', ''))
        self.scope = tk.StringVar(value='selecionadas' if len(self.selected_ids) > 0 else 'todas')
        self.for_ps1 = tk.BooleanVar(value=True)
        self.keep_breaks = tk.BooleanVar(value=False)

        footer = ttk.Frame(self, padding=(14, 8))
        footer.pack(side='bottom', fill='x')
        self.close_button = ttk.Button(footer, text='Fechar', command=self._close)
        self.close_button.pack(side='left')
        self.apply_button = ttk.Button(footer, text='Aplicar às cartas (pendente até salvar)',
                                       style='Accent.TButton', command=self.apply, state='disabled')
        self.apply_button.pack(side='right')
        self.run_button = ttk.Button(footer, text='Traduzir', command=self.start)
        self.run_button.pack(side='right', padx=6)

        body = ttk.Frame(self, padding=14)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Traduzir descrições', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, style='Muted.TLabel', wraplength=900, text=(
            'O texto de cada carta é enviado a um tradutor online (precisa de internet). Cores, ícones e '
            'referências a cartas são preservados. A tradução entra como alteração pendente: revise e use '
            'Salvar projeto. Os textos originais ficam guardados em traducoes/ dentro do projeto.')).pack(
            anchor='w', pady=(3, 10))
        grid = ttk.Frame(body)
        grid.pack(fill='x')
        ttk.Label(grid, text='Idioma de destino').grid(row=0, column=0, sticky='w')
        ttk.Combobox(grid, textvariable=self.language, state='readonly', width=30,
                     values=[v for k, v in translate.LANGUAGES.items()]).grid(row=1, column=0, sticky='w', padx=(0, 12))
        ttk.Label(grid, text='Tradutor').grid(row=0, column=1, sticky='w')
        provider = ttk.Combobox(grid, textvariable=self.provider, state='readonly', width=34,
                                values=list(translate.PROVIDERS.values()))
        provider.grid(row=1, column=1, sticky='w', padx=(0, 12))
        ttk.Label(grid, text='Chave DeepL (opcional)').grid(row=0, column=2, sticky='w')
        ttk.Entry(grid, textvariable=self.api_key, width=28, show='•').grid(row=1, column=2, sticky='w')
        scope = ttk.Frame(body)
        scope.pack(fill='x', pady=(10, 0))
        ttk.Label(scope, text='Cartas:').pack(side='left', padx=(0, 6))
        ttk.Radiobutton(scope, text=f'Selecionadas na biblioteca ({len(self.selected_ids)})', value='selecionadas',
                        variable=self.scope, state='normal' if self.selected_ids else 'disabled').pack(side='left')
        ttk.Radiobutton(scope, text='Com descrição editada no projeto', value='editadas',
                        variable=self.scope).pack(side='left', padx=8)
        ttk.Radiobutton(scope, text='Todas com descrição', value='todas', variable=self.scope).pack(side='left')
        options = ttk.Frame(body)
        options.pack(fill='x', pady=(6, 0))
        ttk.Checkbutton(options, text='Adaptar para a fonte do PS1 (ß→ss, ä→ae…)', variable=self.for_ps1).pack(side='left')
        ttk.Checkbutton(options, text='Manter as quebras de linha', variable=self.keep_breaks).pack(side='left', padx=12)
        ttk.Label(body, style='Muted.TLabel', wraplength=900, text=(
            'Japonês, chinês e coreano: o BIN/CUE americano ainda não tem esses caracteres na fonte; essas '
            'descrições aparecem no Studio, mas na geração do BIN a carta mantém o texto anterior até a fonte '
            'nova existir. Textos mais longos que o original podem não caber no PS1 (o gerador avisa).')).pack(
            anchor='w', pady=(6, 6))
        progress = ttk.Frame(body)
        progress.pack(fill='x', pady=(2, 6))
        self.progress = ttk.Progressbar(progress, mode='determinate')
        self.progress.pack(side='left', fill='x', expand=True)
        self.progress_label = ttk.Label(progress, text='', width=26)
        self.progress_label.pack(side='left', padx=8)
        holder = ttk.Frame(body)
        holder.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(holder, columns=('id', 'nome', 'traducao', 'estado'), show='headings')
        for key, label, width, stretch in (('id', 'ID', 56, False), ('nome', 'Carta', 170, False),
                                           ('traducao', 'Tradução', 520, True), ('estado', 'Situação', 150, False)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, stretch=stretch)
        scroll = ttk.Scrollbar(holder, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.tree.bind('<<TreeviewSelect>>', self._show_detail)
        self.detail = tk.Text(body, height=5, wrap='word', bg='#182339', fg='#f2f5fb', relief='flat',
                              font=font(10), state='disabled')
        self.detail.pack(fill='x', pady=(6, 0))
        self.protocol('WM_DELETE_WINDOW', self._close)
        self.bind('<Escape>', lambda _e: self._close())

    # ── dados ───────────────────────────────────────────────────────────
    def _code(self, var, mapping):
        return next(k for k, v in mapping.items() if v == var.get())

    def _items(self):
        studio = self.studio
        cards = {cid: studio.drafts.get_card(cid) for cid in studio.project.cards}
        scope = self.scope.get()
        if scope == 'selecionadas':
            ids = self.selected_ids
        elif scope == 'editadas':
            ids = [cid for cid in cards if 'descricao' in studio.project.edits.get(str(cid), {})
                   or (cid in studio.drafts.cards and studio.drafts.cards[cid].get('descricao')
                       != studio.project.get(cid).get('descricao'))]
        else:
            ids = list(cards)
        return {cid: cards[cid].get('descricao', '') for cid in ids
                if cid in cards and (cards[cid].get('descricao') or '').strip()}

    # ── execução ────────────────────────────────────────────────────────
    def start(self):
        if self.running:
            self.cancel_flag.set()
            return
        items = self._items()
        if not items:
            messagebox.showinfo('Traduzir descrições', 'Nenhuma carta com descrição neste grupo.', parent=self)
            return
        target = self._code(self.language, translate.LANGUAGES)
        provider = self._code(self.provider, translate.PROVIDERS)
        self.prefs.update({'idioma': target, 'tradutor': provider, 'chave_deepl': self.api_key.get().strip()})
        self.target, self.provider_code = target, provider
        self.results = []
        self.tree.delete(*self.tree.get_children())
        self.apply_button.configure(state='disabled')
        self.cancel_flag.clear()
        self.running = True
        self.run_button.configure(text='Cancelar tradução')
        self.progress.configure(maximum=len(items), value=0)
        self.progress_label.configure(text=f'0 de {len(items)}')
        args = dict(provider=provider, api_key=self.api_key.get(), keep_breaks=self.keep_breaks.get(),
                    for_ps1=self.for_ps1.get())

        def worker():
            try:
                results = translate.translate_many(
                    items, target, progress=lambda done, total: self.messages.put(('progresso', (done, total))),
                    cancelled=self.cancel_flag.is_set, **args)
                self.messages.put(('fim', results))
            except Exception as exc:  # erro inesperado: mostrado na interface
                self.messages.put(('erro', f'{type(exc).__name__}: {exc}'))
        threading.Thread(target=worker, daemon=True).start()
        self.after(120, self._poll)

    def _poll(self):
        finished = False
        while True:
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == 'progresso':
                done, total = value
                self.progress.configure(value=done)
                self.progress_label.configure(text=f'{done} de {total}')
            elif kind == 'fim':
                finished = True
                self._show(value)
            else:
                finished = True
                messagebox.showerror('Traduzir descrições', value, parent=self)
        if finished or not self.winfo_exists():
            self.running = False
            if self.winfo_exists():
                self.run_button.configure(text='Traduzir')
            return
        self.after(120, self._poll)

    def _show(self, results):
        self.results = results
        cards = {cid: self.studio.drafts.get_card(cid) for cid in self.studio.project.cards}
        ok = 0
        for row in results:
            if row.translated is not None:
                ok += 1
                state = 'pronta'
                if len(row.translated) > len(row.original) * 1.25:
                    state = 'pronta · texto maior'
            else:
                state = f'falhou: {row.error}'
            self.tree.insert('', 'end', iid=str(row.id), values=(
                f'{row.id:03d}', display_name(row.id, cards), (row.translated or row.original).replace('\n', ' '), state))
        failed = len(results) - ok
        cancelled = self.cancel_flag.is_set()
        self.progress_label.configure(text=f'{ok} traduzida(s)' + (f' · {failed} com falha' if failed else '')
                                      + (' · cancelado' if cancelled else ''))
        self.apply_button.configure(state='normal' if ok else 'disabled')

    def _show_detail(self, _event=None):
        selection = self.tree.selection()
        row = next((r for r in self.results if selection and str(r.id) == selection[0]), None)
        self.detail.configure(state='normal')
        self.detail.delete('1.0', 'end')
        if row:
            self.detail.insert('1.0', f'ORIGINAL:\n{row.original}\n\nTRADUÇÃO:\n{row.translated or "—  " + row.error}')
        self.detail.configure(state='disabled')

    def apply(self):
        ready = [r for r in self.results if r.translated is not None]
        if not ready:
            return
        folder = self.studio.project.folder / 'traducoes'
        try:
            folder.mkdir(parents=True, exist_ok=True)
            name = f'originais_{self.target}_{time.strftime("%Y%m%d_%H%M%S")}.json'
            (folder / name).write_text(json.dumps(translate.backup_payload(ready, self.target, self.provider_code),
                                                  ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError as exc:
            messagebox.showerror('Traduzir descrições', f'Não foi possível guardar o backup dos originais: {exc}',
                                 parent=self)
            return
        self.studio._stage_current()
        for row in ready:
            card = self.studio.drafts.get_card(row.id)
            card['descricao'] = row.translated
            self.studio.drafts.stage_card(row.id, card)
        self.studio._after_translation(len(ready), folder / name)
        self.destroy()

    def _close(self):
        if self.running:
            self.cancel_flag.set()
        self.destroy()
