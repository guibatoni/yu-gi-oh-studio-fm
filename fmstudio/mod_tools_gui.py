"""Ferramentas de passwords e geração de decks da aba Edição do Mod."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from random import SystemRandom
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .core import ModError, ps1_supports_god24, simulation_nonnegative_int
from .deck_generator import (DIFFICULTIES, STARTER_MAX_POWER, SUPPORT_TYPES, duelist_preset,
                             generate_deck, suggest_quantities)
from .expanded import card_matches, display_name, search_text
from .gui import ACCENT, ROW_ALT, card_row_tags, compact_number, sortable_columns
from .mod_data import CONFIG_KEY, MONSTER_TYPES, STOCK_STARTER
from .passwords import (
    PS1_ID_PREFIX, chest_cards, grant_card, id_code, import_original_passwords, ps1_id_code,
    redeem_id, redeem_original, set_ps1_id_passwords, original_passwords,
)
from .ps1_drop_count import COUNT_MAX, COUNT_MIN, MOD_DEFAULT, cards_per_win, set_cards_per_win
from .ps1_economy import (
    CHEST_VISIBILITY_KEY, PRICE_LIMIT, STAR_LIMIT, chest_show_all,
    fixed_win_reward, price_overrides, set_chest_show_all,
    set_password_price, reset_password_price, set_win_reward,
)
from .tables import CARD_COUNT, DECK_SIZE, TYPE_NAMES


def _tree(parent, columns, *, height=6, raw_values=None, selectmode='browse', horizontal=False):
    holder = ttk.Frame(parent)
    holder.pack(fill='both', expand=True, pady=(6, 0))
    tree = ttk.Treeview(holder, columns=[row[0] for row in columns], show='headings',
                        selectmode=selectmode, height=height)
    tree.tag_configure('stripe', background=ROW_ALT)
    if horizontal:
        hscroll = ttk.Scrollbar(holder, orient='horizontal', command=tree.xview)
        hscroll.pack(side='bottom', fill='x')
        tree.configure(xscrollcommand=hscroll.set)
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
        if prefix is not None and cid <= 740 and (cid > CARD_COUNT or not self.cards[cid].get('virtual')):
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
                            f'No BIN/CUE, digite {prefix:05d} e o ID com três dígitos. Preços configuráveis na aba Estrelas.')
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
        self.geometry('850x640')
        self.minsize(680, 480)
        self.project, self.cards = project, cards
        self.studio, self.changed = studio, changed
        self.into_starter = tk.BooleanVar()
        self.starter = tk.StringVar(value='Deck do baú')
        self.ps1_enabled = tk.BooleanVar(value=PS1_ID_PREFIX in project.metadata)
        self.ps1_chest_visible = tk.BooleanVar(value=chest_show_all(project))
        self.chest_show_zero = tk.BooleanVar(value=True)
        self.price_query = tk.StringVar()
        initial_reward = fixed_win_reward(project)
        self.reward_mode = tk.StringVar(value='fixo' if initial_reward is not None else 'por_rank')
        self.reward_amount = tk.StringVar(value=str(initial_reward if initial_reward is not None else 5))

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
        ttk.Checkbutton(
            chest, text='Mostrar todas as cartas no Studio (inclusive 0/0)',
            variable=self.chest_show_zero, command=self._refresh_chest).pack(anchor='w')
        ttk.Label(chest, text='ID, nome, tipo ou descrição').pack(anchor='w')
        ttk.Entry(chest, textvariable=self.chest_search).pack(fill='x')
        self.chest = _tree(chest, [('id', 'ID', 70), ('nome', 'Carta', 290), ('qtd', 'Cópias no baú', 100)],
                           raw_values=self._chest_sort_value, selectmode='extended')
        self.bulk_chest_count=tk.StringVar(value='0 cartas selecionadas')
        chest_actions=ttk.Frame(chest)
        chest_actions.pack(fill='x',pady=(5,0))
        ttk.Button(chest_actions,text='Selecionar todas',command=lambda:self._select_all_visible(self.chest)).pack(side='left')
        ttk.Button(chest_actions,text='Limpar seleção',command=lambda:self._clear_selection(self.chest)).pack(side='left',padx=(5,0))
        ttk.Button(chest_actions,text='Editar selecionadas',command=lambda:self._open_bulk('chest')).pack(side='left',padx=(5,0))
        ttk.Label(chest_actions,textvariable=self.bulk_chest_count).pack(side='right')
        self.chest_search.trace_add('write', lambda *_: self._refresh_chest())
        self.chest.bind('<Control-a>',lambda _e:self._select_all_visible(self.chest))
        self.chest.bind('<<TreeviewSelect>>',lambda _e:self._update_selection_count())
        self.chest.bind('<Double-1>',lambda _e:reveal(int(self.chest.selection()[0]))
                        if len(self.chest.selection()) == 1 else None)
        tabs.add(self.original, text='Códigos originais')
        tabs.add(self.ids, text='Códigos por ID')
        tabs.add(chest, text='Baú')

        prices = ttk.Frame(tabs, padding=9)
        ttk.Label(prices,text='Custo em Star Chips para comprar cada carta pelo Password do PS1.').pack(anchor='w')
        ttk.Label(prices,text='IDs 1–722 e cartas expandidas 723–740. O preço original permanece no backup.').pack(anchor='w')
        ttk.Entry(prices, textvariable=self.price_query).pack(fill='x',pady=(5,2))
        self.price_tree = _tree(prices,
            [('id','ID',68),('nome','Carta',260),('original','Custo original',125),
             ('novo','Novo custo',125)],
            raw_values=self._price_sort_value, selectmode='extended')
        self.bulk_price_count=tk.StringVar(value='0 cartas selecionadas')
        self.price_query.trace_add('write',lambda *_:self._refresh_prices())
        self.price_tree.bind('<Double-1>',lambda _e:self._edit_price()
                             if len(self.price_tree.selection()) == 1 else None)
        self.price_tree.bind('<Control-a>',lambda _e:self._select_all_visible(self.price_tree))
        self.price_tree.bind('<<TreeviewSelect>>',lambda _e:self._update_selection_count())
        actions=ttk.Frame(prices)
        actions.pack(fill='x',pady=(6,0))
        ttk.Button(actions,text='Editar custo da carta',command=self._edit_price).pack(side='left')
        ttk.Button(actions,text='Restaurar preço original',command=self._reset_price).pack(side='left',padx=(8,0))
        ttk.Button(actions,text='Selecionar todas',command=lambda:self._select_all_visible(self.price_tree)).pack(side='left',padx=(8,0))
        ttk.Button(actions,text='Limpar seleção',command=lambda:self._clear_selection(self.price_tree)).pack(side='left',padx=(5,0))
        ttk.Button(actions,text='Editar selecionadas',command=lambda:self._open_bulk('price')).pack(side='left',padx=(5,0))
        ttk.Label(prices,textvariable=self.bulk_price_count).pack(anchor='e')
        tabs.add(prices,text='Estrelas por carta')

        rewards = ttk.Frame(tabs,padding=16)
        ttk.Label(rewards,text='Estrelas recebidas ao vencer um duelo no PS1',
                  font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(0,12))
        ttk.Radiobutton(rewards,text='Original por rank: S=5 · A=4 · B=3 · C=2 · D=1',
                        variable=self.reward_mode,value='por_rank').pack(anchor='w',pady=5)
        ttk.Radiobutton(rewards,text='Quantidade fixa por vitória (independente do rank)',
                        variable=self.reward_mode,value='fixo').pack(anchor='w',pady=5)
        star_row=ttk.Frame(rewards)
        star_row.pack(fill='x',pady=(6,12))
        ttk.Label(star_row,text='Valor fixo de 1 a 255 Star Chips:').pack(side='left')
        ttk.Entry(star_row,textvariable=self.reward_amount,width=12).pack(side='left',padx=8)
        ttk.Button(rewards,text='Salvar ganho de estrelas',command=self._save_reward).pack(anchor='w')
        ttk.Label(rewards,text=('A pontuação de RANK e os drops não são alterados. '
                               'O valor será gravado no SLUS da próxima cópia BIN/CUE.'),
                  wraplength=600,foreground=ACCENT).pack(anchor='w',pady=(20,0))
        tabs.add(rewards,text='Estrelas por duelo')

        drops = ttk.Frame(tabs,padding=16)
        ttk.Label(drops,text='Cartas recebidas ao vencer um duelo no PS1 (Drop x15)',
                  font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(0,12))
        initial_cards = cards_per_win(project)
        self.cards_default = tk.BooleanVar(value=initial_cards is None)
        self.cards_per_win = tk.IntVar(value=initial_cards or MOD_DEFAULT)
        ttk.Checkbutton(drops,text='Usar o padrão do mod (sem alteração no código de drops)',
                        variable=self.cards_default,command=self._cards_mode_changed).pack(anchor='w')
        row = ttk.Frame(drops)
        row.pack(fill='x',pady=(12,4))
        ttk.Label(row,text='Cartas por vitória:').pack(side='left')
        self.cards_scale = ttk.Scale(row,from_=COUNT_MIN,to=COUNT_MAX,orient='horizontal',
                                     command=lambda v: self.cards_per_win.set(int(float(v))))
        self.cards_scale.pack(side='left',fill='x',expand=True,padx=8)
        self.cards_spin = ttk.Spinbox(row,from_=COUNT_MIN,to=COUNT_MAX,width=5,
                                      textvariable=self.cards_per_win,command=self._cards_spin_changed)
        self.cards_spin.pack(side='left')
        self.cards_spin.bind('<KeyRelease>',lambda _e: self._cards_spin_changed())
        self.cards_scale.set(self.cards_per_win.get())
        ttk.Label(drops,text=f'De {COUNT_MIN} a {COUNT_MAX}. Arraste a barra ou digite o número.',
                  foreground='#5a6b7d').pack(anchor='w')
        ttk.Button(drops,text='Salvar cartas por vitória',command=self._save_cards_per_win).pack(anchor='w',pady=(12,0))
        ttk.Label(drops,text=('Cada carta é sorteada com os pesos de drop do oponente e do RANK, como no jogo. '
                             'Pelo código do Drop x15, o padrão entrega 5 cartas; a tela de resultado repete '
                             'os nomes das cartas sorteadas. O valor é gravado no SLUS e nos dados de duelo '
                             'da próxima cópia BIN/CUE.'),
                  wraplength=600,foreground=ACCENT).pack(anchor='w',pady=(20,0))
        self._cards_mode_changed()
        tabs.add(drops,text='Cartas por vitória')
        if owner is not studio or not originals:
            tabs.select(self.ids)

        footer = ttk.Frame(self, padding=(12, 1, 12, 10))
        footer.pack(fill='x')
        if ps1_supports_god24(project):
            ttk.Checkbutton(footer, text='Ativar passwords por ID no BIN/CUE Drop x15',
                            variable=self.ps1_enabled, command=self._toggle_ps1).pack(anchor='w')
            ttk.Checkbutton(
                footer, text='Mostrar todas as cartas no baú do PS1, inclusive as que não possuo',
                variable=self.ps1_chest_visible, command=self._toggle_chest_ps1).pack(anchor='w')
        destination = ttk.Frame(footer)
        destination.pack(fill='x', pady=(4, 3))
        ttk.Checkbutton(destination, text='Adicionar também ao deck inicial',
                        variable=self.into_starter, command=self._destination).pack(side='left')
        self.profile = ttk.Combobox(destination, textvariable=self.starter, width=21, state='disabled')
        self.profile.pack(side='left', fill='x', expand=True, padx=(5, 0))
        ttk.Button(destination, text='Fechar', command=close).pack(side='right', padx=(6, 0))
        self._refresh_chest()
        self._refresh_prices()
        self.protocol('WM_DELETE_WINDOW', close)
        self.bind('<Escape>', lambda _event: close())
        self.grab_set()
        (self.ids.entry if tabs.select() == str(self.ids) else self.original.entry).focus_set()

    def _check_project(self):
        if self.studio.project is not self.project or self.studio._extract_running:
            raise ModError('Abra os passwords no projeto disponível.')

    def _update_selection_count(self):
        self.bulk_chest_count.set(f'{len(self.chest.selection())} cartas selecionadas')
        self.bulk_price_count.set(f'{len(self.price_tree.selection())} cartas selecionadas')

    def _select_all_visible(self, tree):
        tree.selection_set(*tree.get_children(''))
        self._update_selection_count()
        return 'break'

    def _clear_selection(self, tree):
        tree.selection_remove(tree.selection())
        self._update_selection_count()
        return 'break'

    def _open_bulk(self, source):
        try:
            self._check_project()
            ids=[int(cid) for cid in (self.chest.selection() if source=='chest'
                                      else self.price_tree.selection())]
            if len(ids)<2:
                raise ModError('Selecione pelo menos duas cartas com Ctrl+clique, Shift+clique ou Ctrl+A.')
            from .core import _read_csv
            from .bulk_gui import BulkEditDialog
            csv=self.project.folder/'base'/'senhas.csv'
            originals={}
            if csv.is_file():
                for record in _read_csv(csv):
                    try:
                        originals[int(record['carta_id'])]=int(record['custo_starchips'])
                    except (KeyError,TypeError,ValueError):
                        continue
            def updated():
                self._refresh_chest()
                self._refresh_prices()
                self.original.records=original_passwords(self.project)
                self.original.render()
                if self.changed:
                    self.changed(None)
                self.studio.notify(f'Edição em massa salva para {len(ids)} cartas.')
            BulkEditDialog(self,self.project,self.cards,ids,source=source,
                           original_prices=originals,on_changed=updated)
        except (ModError,ValueError,OSError) as exc:
            messagebox.showerror('Edição em massa',str(exc),parent=self)

    def _destination(self):
        self.profile.configure(state='normal' if self.into_starter.get() else 'disabled')

    def _chest_sort_value(self, item, field):
        if field == 'qtd':
            return int(chest_cards(self.project).get(item, 0))
        return int(item) if field == 'id' else self.chest.set(item, field)

    def _refresh_chest(self):
        selection = self.chest.selection()
        self.chest.delete(*self.chest.get_children())
        query = search_text(self.chest_search.get())
        owned = chest_cards(self.project)
        for index, (cid, card) in enumerate(sorted(self.cards.items())):
            if not card_matches(query, cid, card):
                continue
            count = int(owned.get(str(cid), 0))
            if not self.chest_show_zero.get() and count <= 0:
                continue
            self.chest.insert('', 'end', iid=str(cid),
                              values=(compact_number(cid), display_name(cid, self.cards), count or '0/0'),
                              tags=card_row_tags(self.chest, card, index))
        self.chest.sort_rows()
        remain=[cid for cid in selection if self.chest.exists(cid)]
        if remain:
            self.chest.selection_set(*remain)
        self.profile.configure(values=list(self.project.metadata.get(CONFIG_KEY, {}).get('iniciais', {})))
        self._update_selection_count()

    def _price_sort_value(self, item, field):
        if field == 'id':
            return int(item)
        if field in ('original', 'novo'):
            value = self.price_tree.set(item, field)
            return int(value) if value.lstrip('-').isdigit() else -1
        return self.price_tree.set(item,field)

    def _refresh_prices(self):
        selected=self.price_tree.selection()
        self.price_tree.delete(*self.price_tree.get_children())
        query=search_text(self.price_query.get())
        overrides=price_overrides(self.project)
        original=original_passwords(self.project)
        # No CSV inicial, os valores já são atualizados na visualização.
        # Para mostrar a referência imutável, ler o CSV da extração original.
        from .core import _read_csv
        source=self.project.folder/'base'/'senhas.csv'
        legacy={}
        if source.is_file():
            for row in _read_csv(source):
                try:
                    legacy[int(row['carta_id'])]=int(row['custo_starchips'])
                except (KeyError,ValueError,TypeError):
                    continue
        for index,(cid,card) in enumerate(sorted(self.cards.items())):
            if cid > 740 or card.get('virtual') and cid <= CARD_COUNT:
                continue
            if not card_matches(query,cid,card):
                continue
            base=legacy.get(cid,1 if cid>722 else None)
            after=overrides.get(cid,base)
            self.price_tree.insert('', 'end',iid=str(cid),
                values=(compact_number(cid),display_name(cid,self.cards),
                        base if base is not None else '—',
                        after if after is not None else '—'),
                tags=card_row_tags(self.price_tree,card,index))
        self.price_tree.sort_rows()
        remain=[cid for cid in selected if self.price_tree.exists(cid)]
        if remain:
            self.price_tree.selection_set(*remain)
        self._update_selection_count()

    def _selected_price_id(self):
        selection=self.price_tree.selection()
        if len(selection)!=1:
            messagebox.showinfo('Preço Password','Selecione uma única carta ou use Editar selecionadas.',parent=self)
            return None
        return int(selection[0])

    def _edit_price(self):
        cid=self._selected_price_id()
        if cid is None:
            return
        initial=self.price_tree.set(str(cid),'novo')
        amount=simpledialog.askinteger(
            'Preço do Password',f'Carta #{cid}: novo custo em Star Chips (0 a {PRICE_LIMIT}):',
            parent=self,initialvalue=int(initial) if initial.isdigit() else 1,
            minvalue=0,maxvalue=PRICE_LIMIT)
        if amount is None:
            return
        try:
            self._check_project()
            set_password_price(self.project,cid,amount)
        except (ModError,ValueError,OSError) as exc:
            messagebox.showerror('Preço Password',str(exc),parent=self)
            return
        self._refresh_prices()
        self.original.records=original_passwords(self.project)
        self.original.render()
        self.studio.notify(f'Password #{cid}: {amount} Star Chips. Gere o BIN/CUE.')

    def _reset_price(self):
        cid=self._selected_price_id()
        if cid is None:
            return
        try:
            self._check_project()
            reset_password_price(self.project,cid)
        except (ModError,ValueError,OSError) as exc:
            messagebox.showerror('Preço Password',str(exc),parent=self)
            return
        self._refresh_prices()
        self.original.records=original_passwords(self.project)
        self.original.render()
        self.studio.notify(f'Password #{cid}: preço restaurado no projeto.')

    def _save_reward(self):
        try:
            self._check_project()
            mode=self.reward_mode.get()
            if mode not in ('por_rank','fixo'):
                raise ModError('Escolha modo original por rank ou valor fixo.')
            if mode=='por_rank':
                amount=None
            else:
                raw=self.reward_amount.get().strip()
                if not raw.isdecimal():
                    raise ModError(f'Digite estrelas inteiras entre 1 e {STAR_LIMIT}.')
                amount=int(raw)
            set_win_reward(self.project,amount)
        except (ModError,ValueError,OSError) as exc:
            messagebox.showerror('Estrelas por vitória',str(exc),parent=self)
            return
        self.studio.notify('Ganho original por rank restaurado.' if amount is None else
                           f'Ganho fixo configurado: {amount} Star Chips por vitória.')

    def _cards_mode_changed(self):
        state = 'disabled' if self.cards_default.get() else 'normal'
        self.cards_scale.state(['disabled'] if state == 'disabled' else ['!disabled'])
        self.cards_spin.configure(state=state)

    def _cards_spin_changed(self):
        try:
            value = int(self.cards_spin.get())
        except ValueError:
            return
        if COUNT_MIN <= value <= COUNT_MAX:
            self.cards_scale.set(value)

    def _save_cards_per_win(self):
        try:
            self._check_project()
            if self.cards_default.get():
                count = None
            else:
                count = int(self.cards_spin.get())
            set_cards_per_win(self.project,count)
        except (ModError,ValueError,OSError) as exc:
            messagebox.showerror('Cartas por vitória',str(exc) or f'Digite de {COUNT_MIN} a {COUNT_MAX}.',parent=self)
            return
        self.studio.notify('Padrão do mod restaurado.' if count is None else
                           f'{count} carta(s) por vitória. Gere um BIN/CUE novo para aplicar.')

    def _toggle_chest_ps1(self):
        try:
            self._check_project()
            set_chest_show_all(self.project,self.ps1_chest_visible.get())
        except (ModError,ValueError,OSError) as exc:
            self.ps1_chest_visible.set(chest_show_all(self.project))
            messagebox.showerror('Visualização do baú PS1',str(exc),parent=self)
            return
        self.studio.notify('Baú completo do PS1 ativado.' if self.ps1_chest_visible.get()
                           else 'Baú do PS1 voltará a mostrar apenas cartas obtidas.')

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
