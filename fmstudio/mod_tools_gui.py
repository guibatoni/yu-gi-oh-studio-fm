"""Ferramentas de passwords e geração de decks da aba Edição do Mod."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from random import SystemRandom
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core import ModError, ps1_supports_god24, simulation_nonnegative_int
from .deck_generator import (DIFFICULTIES, STARTER_MAX_POWER, SUPPORT_TYPES, duelist_preset,
                             generate_deck, suggest_quantities)
from .expanded import card_matches, display_name, search_text
from .gui import ACCENT, ROW_ALT, card_row_tags, compact_number, sortable_columns
from .mod_data import CONFIG_KEY, MONSTER_TYPES, STOCK_STARTER
from .passwords import (
    PS1_ID_PREFIX, chest_cards, grant_card, id_code, import_original_passwords, ps1_id_code,
    redeem_id, redeem_original, set_ps1_id_passwords,
)
from .tables import CARD_COUNT, DECK_SIZE, TYPE_NAMES


def _tree(parent, columns, *, height=6, raw_values=None):
    holder = ttk.Frame(parent)
    holder.pack(fill='both', expand=True, pady=(6, 0))
    tree = ttk.Treeview(holder, columns=[row[0] for row in columns], show='headings',
                        selectmode='browse', height=height)
    tree.tag_configure('stripe', background=ROW_ALT)
    tree.pack(side='left', fill='both', expand=True)
    scroll = ttk.Scrollbar(holder, command=tree.yview)
    scroll.pack(side='right', fill='y')
    tree.configure(yscrollcommand=scroll.set)
    for field, label, width in columns:
        tree.heading(field, text=label)
        tree.column(field, width=width, stretch=field == 'nome')
    tree.sort_rows = sortable_columns(tree, raw_values=raw_values)
    return tree



class PasswordPanel(ttk.Frame):
    def __init__(self, parent, cards, *, by_id, open_card, grant, reload_codes=None, project=None):
        super().__init__(parent, padding=9)
        self.cards = cards
        self.by_id = by_id
        self.open_card = open_card
        self.grant = grant
        self.project = project
        self.reload_codes = reload_codes
        self.records = {}
        self.query = tk.StringVar()
        self.status = tk.StringVar()
        ttk.Label(self, text='ID, nome, tipo, descrição ou código').pack(anchor='w')
        bar = ttk.Frame(self)
        bar.pack(fill='x', pady=(3, 0))
        self.entry = ttk.Entry(bar, textvariable=self.query, width=24)
        self.entry.pack(side='left', fill='x', expand=True)
        self.entry.bind('<Return>', lambda _event: self.redeem())
        ttk.Button(bar, text='Resgatar carta', style='Accent.TButton',
                   command=self.redeem).pack(side='left', padx=(5, 0))
        columns = [('id', 'ID', 65), ('nome', 'Carta', 230), ('codigo', 'Código', 136)]
        columns.append(('ps1', 'Código PS1', 96) if by_id else ('custo', 'Star Chips no PS1', 130))
        self.tree = _tree(self, columns, raw_values=self._sort_value)
        self.tree.bind('<Double-1>', lambda _event: self._open())
        actions = ttk.Frame(self)
        actions.pack(fill='x', pady=(7, 0))
        if reload_codes is not None:
            ttk.Button(actions, text='Ler códigos do BIN/CUE', command=self._reload).pack(side='left')
        if by_id:
            self.copy_ps1 = ttk.Button(actions, text='Copiar código PS1', command=lambda: self._copy(ps1=True))
            self.copy_ps1.pack(side='left')
        ttk.Button(actions, text='Copiar código', command=self._copy).pack(side='right', padx=(6, 0))
        ttk.Button(actions, text='Abrir carta', command=self._open).pack(side='right')
        ttk.Label(self, textvariable=self.status, foreground=ACCENT, wraplength=520).pack(anchor='w', pady=(7, 0))
        self.query.trace_add('write', lambda *_: self.render())
        self.render()

    def _ps1_code(self, cid):
        prefix = self.project.metadata.get(PS1_ID_PREFIX)
        if prefix is not None and cid <= CARD_COUNT and not self.cards[cid].get('virtual'):
            return ps1_id_code(prefix, cid)
        return '—'

    def _sort_value(self, item, field):
        return int(item) if field == 'id' else self.tree.set(item, field)

    def render(self, results=None):
        self.tree.delete(*self.tree.get_children())
        query = search_text(self.query.get())
        ids = sorted(self.cards if self.by_id else self.records) if results is None else results
        index = 0
        for cid in ids:
            name = display_name(cid, self.cards)
            code = id_code(cid) if self.by_id else self.records[cid].code
            extra = self._ps1_code(cid) if self.by_id else self.records[cid].cost
            if results is None and not card_matches(query, cid, self.cards[cid], code, str(extra or '')):
                continue
            self.tree.insert('', 'end', iid=str(cid),
                             values=(compact_number(cid), name, code, '—' if extra is None else extra),
                             tags=card_row_tags(self.tree, self.cards.get(cid), index))
            index += 1
        self.tree.sort_rows()
        if self.by_id:
            prefix = self.project.metadata.get(PS1_ID_PREFIX)
            self.copy_ps1.configure(state='disabled' if prefix is None else 'normal')
            self.status.set('Digite o ID da carta ou selecione uma linha.' if prefix is None else
                            f'No BIN/CUE, digite {prefix:05d} e o ID com três dígitos. Custo de 1 Star Chip.')
        elif not self.records:
            self.status.set('Carregue a tabela original do BIN/CUE vinculado ao projeto.')
        else:
            self.status.set('O resgate no simulador adiciona uma cópia ao baú.')

    def redeem(self):
        try:
            cid = self._selection()
            if cid is None:
                query = self.query.get()
                if self.by_id:
                    cid = redeem_id(query, self.cards)
                else:
                    ids = redeem_original(query, self.records)
                    if len(ids) > 1:
                        self.render(ids)
                        self.status.set('Selecione a carta desejada para concluir o resgate.')
                        return
                    cid = ids[0]
            count = self.grant(cid)
            self.render([cid])
            self.tree.selection_set(str(cid))
            self.tree.see(str(cid))
            self.status.set(f'{display_name(cid, self.cards)} resgatada · {count} no baú.')
        except (ModError, ValueError, OSError) as exc:
            self.status.set(str(exc))

    def _selection(self):
        chosen = self.tree.selection()
        return int(chosen[0]) if chosen else None

    def _copy(self, *, ps1=False):
        cid = self._selection()
        if cid is None:
            self.status.set('Selecione uma carta para copiar seu código.')
            return
        if ps1:
            code = self._ps1_code(cid)
            if code == '—':
                self.status.set('Esta carta usa código de resgate do Studio.')
                return
        else:
            code = id_code(cid) if self.by_id else self.records[cid].code
        self.clipboard_clear()
        self.clipboard_append(code)
        self.status.set('Código copiado.')

    def _open(self):
        cid = self._selection()
        if cid is not None:
            self.open_card(cid)

    def _reload(self):
        source = filedialog.askopenfilename(title='BIN/CUE vinculado ao projeto',
                                            filetypes=[('PlayStation', '*.bin *.cue')], parent=self)
        if source:
            try:
                self.records = self.reload_codes(Path(source))
                self.render()
            except (ModError, ValueError, OSError) as exc:
                self.status.set(str(exc))


class PasswordsDialog(tk.Toplevel):
    def __init__(self, studio, project, cards, originals, *, owner=None, changed=None):
        owner = owner or studio
        super().__init__(owner)
        self.title('Passwords e baú')
        self.transient(owner)
        self.geometry('710x500')
        self.minsize(580, 395)
        self.project, self.cards = project, cards
        self.studio, self.changed = studio, changed
        self.into_starter = tk.BooleanVar()
        self.starter = tk.StringVar(value='Deck do baú')
        self.ps1_enabled = tk.BooleanVar(value=PS1_ID_PREFIX in project.metadata)

        tabs = ttk.Notebook(self)
        tabs.pack(fill='both', expand=True, padx=10, pady=(10, 5))
        previous_grab = self.grab_current()

        def close():
            self.destroy()
            if previous_grab is not None and previous_grab.winfo_exists():
                previous_grab.grab_set()

        def reveal(cid):
            if studio.project is project:
                studio.select_card(cid)
            close()

        self.original = PasswordPanel(tabs, cards, by_id=False, open_card=reveal,
                                      grant=self._grant,
                                      reload_codes=lambda path: import_original_passwords(project, path))
        self.original.records = originals
        self.original.render()
        self.ids = PasswordPanel(tabs, cards, by_id=True, open_card=reveal,
                                 grant=self._grant, project=project)
        chest = ttk.Frame(tabs, padding=9)
        self.chest_search = tk.StringVar()
        ttk.Label(chest, text='ID, nome, tipo ou descrição').pack(anchor='w')
        ttk.Entry(chest, textvariable=self.chest_search).pack(fill='x')
        self.chest = _tree(chest, [('id', 'ID', 70), ('nome', 'Carta', 290), ('qtd', 'Cópias', 90)],
                           raw_values=lambda item, field: int(item) if field == 'id' else self.chest.set(item, field))
        self.chest_search.trace_add('write', lambda *_: self._refresh_chest())
        self.chest.bind('<Double-1>', lambda _e: reveal(int(self.chest.selection()[0]))
                        if self.chest.selection() else None)
        tabs.add(self.original, text='Códigos originais')
        tabs.add(self.ids, text='Códigos por ID')
        tabs.add(chest, text='Baú')
        if owner is not studio or not originals:
            tabs.select(self.ids)

        footer = ttk.Frame(self, padding=(12, 1, 12, 10))
        footer.pack(fill='x')
        if ps1_supports_god24(project):
            ttk.Checkbutton(footer, text='Ativar passwords por ID no BIN/CUE Drop x15',
                            variable=self.ps1_enabled, command=self._toggle_ps1).pack(anchor='w')
        destination = ttk.Frame(footer)
        destination.pack(fill='x', pady=(4, 3))
        ttk.Checkbutton(destination, text='Adicionar também ao deck inicial',
                        variable=self.into_starter, command=self._destination).pack(side='left')
        self.profile = ttk.Combobox(destination, textvariable=self.starter, width=21, state='disabled')
        self.profile.pack(side='left', fill='x', expand=True, padx=(5, 0))
        ttk.Button(destination, text='Fechar', command=close).pack(side='right', padx=(6, 0))
        self._refresh_chest()
        self.protocol('WM_DELETE_WINDOW', close)
        self.bind('<Escape>', lambda _event: close())
        self.grab_set()
        (self.ids.entry if tabs.select() == str(self.ids) else self.original.entry).focus_set()

    def _check_project(self):
        if self.studio.project is not self.project or self.studio._extract_running:
            raise ModError('Abra os passwords no projeto disponível.')

    def _destination(self):
        self.profile.configure(state='normal' if self.into_starter.get() else 'disabled')

    def _refresh_chest(self):
        self.chest.delete(*self.chest.get_children())
        query = search_text(self.chest_search.get())
        for index, (key, count) in enumerate(sorted(chest_cards(self.project).items(), key=lambda item: int(item[0]))):
            cid = int(key)
            if not card_matches(query, cid, self.cards.get(cid, {})):
                continue
            self.chest.insert('', 'end', iid=key, values=(compact_number(cid), display_name(cid, self.cards), count),
                              tags=card_row_tags(self.chest, self.cards.get(cid), index))
        self.chest.sort_rows()
        self.profile.configure(values=list(self.project.metadata.get(CONFIG_KEY, {}).get('iniciais', {})))

    def _grant(self, cid):
        self._check_project()
        starter = self.starter.get().strip() if self.into_starter.get() else None
        if starter == STOCK_STARTER:
            raise ModError('Escolha outro nome para o deck inicial.')
        count = grant_card(self.project, cid, starter=starter)
        self._refresh_chest()
        if self.changed:
            self.changed(starter)
        return count

    def _toggle_ps1(self):
        try:
            self._check_project()
            set_ps1_id_passwords(self.project, self.ps1_enabled.get())
        except (ModError, ValueError, OSError) as exc:
            self.ps1_enabled.set(PS1_ID_PREFIX in self.project.metadata)
            self.ids.status.set(str(exc))
            self.original.status.set(str(exc))
            return
        self.ids.render()
        caption = 'Passwords por ID ativados para a próxima geração BIN/CUE.' if self.ps1_enabled.get() else 'Passwords por ID desativados no BIN/CUE.'
        self.original.status.set(caption)
        self.studio.notify(caption)


class DeckGeneratorDialog(tk.Toplevel):
    def __init__(self, editor, cards, effects, fusions, equips, *, default_copies,
                 trap_thresholds, fixed, use_deck, new_starter=False, starter=False, opponent=None):
        super().__init__(editor.winfo_toplevel())
        self.title('Gerar Deck Aleatório')
        self.transient(editor.winfo_toplevel())
        self.geometry('700x530')
        self.minsize(620, 460)
        self.cards, self.effects, self.fusions, self.equips = cards, effects, fusions, equips
        self.default_copies, self.trap_thresholds = default_copies, trap_thresholds
        self.on_use = use_deck
        self.starter = starter or new_starter
        self.opponent = opponent
        self.deck = None
        self.difficulty = tk.StringVar(value='Difícil')
        self.max_atk = tk.StringVar()
        self.max_def = tk.StringVar()
        self.ps1_only = tk.BooleanVar(value=bool(getattr(editor.winfo_toplevel(), 'project', None)
                                                  and ps1_supports_god24(editor.winfo_toplevel().project)))
        self.status = tk.StringVar()
        self.summary = tk.StringVar()
        current = Counter(int(cards[cid]['tipo_id']) for cid in fixed if cid in cards)
        self.quantities = {typ: tk.StringVar(value=str(current[typ]))
                           for typ in sorted(MONSTER_TYPES.union(SUPPORT_TYPES))}

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True, padx=12, pady=(12, 4))
        setup, monsters, preview = (ttk.Frame(self.tabs, padding=12) for _ in range(3))
        for pane, name in ((setup, 'Composição'), (monsters, 'Tipos de Monstro'), (preview, 'Prévia')):
            self.tabs.add(pane, text=name)
        self.preview = preview
        description = (
            f'Deck inicial com três tipos. ATK + DEF de cada monstro até {STARTER_MAX_POWER}.'
            if self.starter else 'Os tetos são opcionais e se aplicam às cartas incluídas no deck.'
        )
        ttk.Label(setup, text=description,
                  wraplength=570).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 10))
        for row, (typ, label) in enumerate(((20, 'Magias'), (21, 'Armadilhas'), (23, 'Equipamentos')), 1):
            self._quantity(setup, typ, label, row, 0)
        ttk.Checkbutton(setup, text='Gerar somente cartas compatíveis com PS1 (#001–#722)',
                        variable=self.ps1_only).grid(row=4,column=0,columnspan=2,sticky='w',pady=7)
        ttk.Label(setup, text='Dificuldade').grid(row=5, column=0, sticky='w', pady=5)
        ttk.Combobox(setup, textvariable=self.difficulty, values=list(DIFFICULTIES),
                     state='readonly', width=15).grid(row=5, column=1, sticky='w', padx=10)
        for row, (caption, variable) in enumerate((('ATK máximo', self.max_atk), ('DEF máxima', self.max_def)), 6):
            ttk.Label(setup, text=caption).grid(row=row, column=0, sticky='w', pady=3)
            ttk.Entry(setup, textvariable=variable, width=17).grid(row=row, column=1, sticky='w', padx=10)
        ttk.Button(setup, text='Sortear trio inicial' if self.starter else 'Aplicar tema do duelista',
                   command=lambda: self._suggest(randomize=self.starter, apply_theme=True)).grid(
                       row=8, column=0, columnspan=2, sticky='w', pady=8)
        if new_starter:
            ttk.Label(setup, text='O deck escolhido será salvo em um novo perfil inicial.',
                      wraplength=550).grid(row=9, column=0, columnspan=2, sticky='w', pady=5)
        for i, typ in enumerate(sorted(MONSTER_TYPES)):
            row, column = divmod(i, 2)
            self._quantity(monsters, typ, TYPE_NAMES[typ], row, column * 2)
        self.list = _tree(preview, [('qtd', 'Qtd.', 55), ('id', 'ID', 70), ('nome', 'Carta', 265),
                                    ('tipo', 'Tipo', 125)],
                          raw_values=lambda item, key: int(item) if key == 'id' else self.list.set(item, key))
        ttk.Label(preview, textvariable=self.summary, wraplength=620, justify='left').pack(anchor='w', pady=(8, 0))

        footer = ttk.Frame(self, padding=(12, 2, 12, 10))
        footer.pack(fill='x')
        ttk.Label(footer, textvariable=self.status, foreground=ACCENT, wraplength=660).pack(anchor='w', pady=4)
        controls = ttk.Frame(footer)
        controls.pack(fill='x')
        ttk.Button(controls, text='Cancelar', command=self.destroy).pack(side='left')
        self.use_button = ttk.Button(controls, text='Usar deck', command=self._use,
                                     state='disabled', style='Accent.TButton')
        self.use_button.pack(side='right')
        ttk.Button(controls, text='Gerar prévia', command=self._generate).pack(side='right', padx=(0, 6))
        for var in (self.difficulty, self.ps1_only, self.max_atk, self.max_def, *self.quantities.values()):
            var.trace_add('write', self._invalidate)
        self._invalidate()
        if self.starter or sum(int(var.get()) for var in self.quantities.values()) != DECK_SIZE:
            self._suggest(apply_theme=True)
        self.bind('<Escape>', lambda _event: self.destroy())
        self.grab_set()

    def _quantity(self, parent, typ, name, row, column):
        ttk.Label(parent, text=name).grid(row=row, column=column, sticky='w', padx=(0, 8), pady=3)
        ttk.Spinbox(parent, from_=0, to=DECK_SIZE, width=6, textvariable=self.quantities[typ]).grid(
            row=row, column=column+1, sticky='w', padx=(4, 22), pady=3)

    def _invalidate(self, *_):
        self.deck = None
        self.use_button.state(['disabled'])
        try:
            total = sum(int(var.get() or 0) for var in self.quantities.values())
            self.status.set(f'{total} de {DECK_SIZE} vagas preenchidas.')
        except ValueError:
            self.status.set('Informe quantidades inteiras por tipo.')

    def _power_limits(self):
        return {key: simulation_nonnegative_int(var.get(), label) if var.get().strip() else None
                for key, var, label in (('max_atk', self.max_atk, 'ATK máximo'),
                                        ('max_def', self.max_def, 'DEF máxima'))}

    def _suggest(self, *, randomize=False, apply_theme=False):
        theme = ()
        if not self.starter and self.opponent is not None:
            theme, power, difficulty = duelist_preset(self.opponent)
            if apply_theme:
                self.max_atk.set(str(power))
                self.max_def.set(str(power))
                self.difficulty.set(difficulty)
        try:
            counts = suggest_quantities(
                self.cards, self.effects, self.fusions, self.equips, default_copies=self.default_copies,
                theme=theme, starter=self.starter, ps1_only=self.ps1_only.get(),
                rng=SystemRandom() if randomize else None, **self._power_limits(),
            )
        except ModError as exc:
            self.status.set(str(exc))
            return
        for typ, variable in self.quantities.items():
            variable.set(str(counts[typ]))
        selected = ', '.join(TYPE_NAMES[typ] for typ in sorted(MONSTER_TYPES) if counts[typ])
        self.status.set(f'{DECK_SIZE} vagas preenchidas · {selected}.')

    def _generate(self):
        try:
            result = generate_deck(
                self.cards, self.effects, self.fusions, self.equips,
                {typ: var.get() or '0' for typ, var in self.quantities.items()},
                difficulty=self.difficulty.get(), default_copies=self.default_copies,
                trap_thresholds=self.trap_thresholds, ps1_only=self.ps1_only.get(),
                starter=self.starter, **self._power_limits(),
            )
        except (ModError, ValueError) as exc:
            self.status.set(str(exc))
            return
        self.deck = result
        self.list.delete(*self.list.get_children())
        for index, (cid, amount) in enumerate(sorted(Counter(result.cards).items())):
            self.list.insert('', 'end', iid=str(cid), values=(amount, compact_number(cid), display_name(cid, self.cards),
                                                TYPE_NAMES[int(self.cards[cid]['tipo_id'])]),
                             tags=card_row_tags(self.list, self.cards[cid], index))
        self.list.sort_rows()
        routes = [
            f'{display_name(a, self.cards)} + {display_name(b, self.cards)} → {display_name(result, self.cards)}'
            for a, b, result in result.fusions[:3]
        ]
        self.summary.set('\n'.join(routes))
        self.tabs.select(self.preview)
        source = 'pronto para deck PS1' if self.ps1_only.get() else 'modo Studio'
        self.status.set(f'{len(result.cards)}/40 cartas · {len(result.fusions)} fusões · {source}.')
        self.use_button.state(['!disabled'])

    def _use(self):
        if self.deck is not None:
            try:
                self.on_use(self.deck.cards)
            except (ModError, ValueError, OSError) as exc:
                self.status.set(str(exc))
                return
            self.destroy()
