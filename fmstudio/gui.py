"""Interface Windows/Tkinter do FM Mod Studio. Sem dependências externas."""
from __future__ import annotations
import re
import sys
import queue
import threading
import os
import tkinter as tk
from decimal import Decimal
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser
from pathlib import Path
from .core import (Project, ModError, check_effect, EVENTS, ACTIONS, TARGETS, SCOPES, FIELDS, DEFAULT_NAME_COLOR, FILTER_COMBINATIONS,
                   ENTRY_EFFECTS, ENTRY_GROW, ENTRY_SHRINK, ENTRY_TYPE_EVENT,
                   ONCE_ACTIONS, legacy_god_description_icon_card, ps1_god24_card_ids,
                   ps1_supports_god24)
from .drafts import DraftSession
from .disc import DiscError
from .tables import CARD_COUNT, TYPE_NAMES, ATTR_NAMES, STAR_NAMES, SUPREME
from .continuous import COUNT_ZONES, EFFECT_ACTIONS, EQUIPMENT_ACTIONS, SCALING_ACTIONS
from .abilities import QUICK_ACTIONS, BOOLEAN_ACTIONS, quick_settings
from . import __version__
from .rarities import RARITIES, DEFAULT_RARITY, name_style, rarity_options
from .expanded import GOD_TYPE_ID, card_matches, display_name, bonus_description, resolve_references, search_text
from .richtext import NATIVE_ICONS, CUSTOM_ICONS, TEXT_COLORS, tokens
from .updates import read_latest, start_updater, UpdateError
from .guardian import SUPREME_COLOR, guardian_name

from .ui_theme import BG, SURFACE, SURFACE2, TEXT, MUTED, ACCENT, BLUE, BORDER, ROW_ALT, WARNING
from . import ui_theme, ui_prefs, ui_nav
EFFECT_ATTRIBUTE_NAMES = (*ATTR_NAMES, *(f'Atributo {i:02d}' for i in range(len(ATTR_NAMES), 16)))


def format_id(cid):
    return f'#{cid:03d}'


def caption_key(mapping, key):
    return mapping.get(key, key)


def effect_target_label(action, target):
    return 'Esta carta' if action in SCALING_ACTIONS or action == ENTRY_GROW else caption_key(TARGETS, target)


def effect_filter_label(effect):
    kind = effect.get('tipo_id', -1)
    attribute = effect.get('atributo_id', -1)
    type_name = TYPE_NAMES[kind] if 0 <= kind < len(TYPE_NAMES) else ''
    if not 0 <= attribute < len(EFFECT_ATTRIBUTE_NAMES):
        return type_name or ('Todos' if effect.get('tipo_id') == -1 else '—')
    name = EFFECT_ATTRIBUTE_NAMES[attribute]
    return f'{type_name} {effect.get("combinar_filtros", "e")} {name}' if type_name else name


def compact_number(value, width=13):
    text = str(value)
    return text if len(text) <= width else f'{text[:width-4]}…{text[-3:]}'


def card_row_tags(tree, card, index):
    if card is None:
        return ('stripe',) if index % 2 else ()
    _, color, kind = name_style(card)
    tag = f'classe_{kind}_{index % 2}'
    shade = '#EAF0FA' if kind == 'deus' else (ROW_ALT if index % 2 else SURFACE)
    tree.tag_configure(tag, foreground=color, background=shade)
    return (tag,)


def sortable_columns(tree, *, raw_values=None):
    """Bind each heading and return the function that reapplies the active order."""
    columns = tuple(tree['columns'])
    labels = {column: tree.heading(column, 'text') for column in columns}
    ordered_by = None
    reverse = False

    def apply():
        if ordered_by is None:
            return
        rows = []
        for item in tree.get_children():
            value = raw_values(item, ordered_by) if raw_values else tree.set(item, ordered_by)
            raw = str(value)
            number = raw.removeprefix('#').removesuffix('%').strip().replace(',', '.')
            if re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?', number):
                key = (0, Decimal(number))
            else:
                key = (1, search_text(raw))
            rows.append((key, item))
        rows.sort(key=lambda row: row[0], reverse=reverse)
        for index, (_, item) in enumerate(rows):
            tree.move(item, '', index)

    def sort(column):
        nonlocal ordered_by, reverse
        reverse = not reverse if ordered_by == column else False
        ordered_by = column
        for field, caption in labels.items():
            suffix = (' ▼' if reverse else ' ▲') if field == column else ''
            tree.heading(field, text=caption + suffix)
        apply()

    for column in columns:
        tree.heading(column, command=lambda key=column: sort(key))
    return apply


class EffectDialog(tk.Toplevel):
    """Editor guiado de gatilhos, auras, efeitos por deck e equipamentos."""

    fixed_targets = {
        'aura_tipo': 'aliados_tipo',
        **dict.fromkeys(SCALING_ACTIONS, 'proprio'),
        **dict.fromkeys(EQUIPMENT_ACTIONS, 'monstro_equipado'),
        **dict.fromkeys(QUICK_ACTIONS, 'proprio'),
        'cura_lp_deck_tipo': 'proprio',
        'dano_lp_deck_tipo': 'inimigo',
        'descartar_alvo': 'inimigo',
        'dano_monstro_alvo': 'monstro_alvo',
        ENTRY_GROW: 'proprio',
        ENTRY_SHRINK: 'aliados_tipo',
    }
    def __init__(self, master, on_save, *, initial_effect=None, batch=False, existing=()):
        super().__init__(master)
        self.on_save=on_save
        self.cards = getattr(master, 'project', None)
        self.initial_effect = dict(initial_effect) if initial_effect is not None else None
        self.batch = bool(batch and self.initial_effect is None)
        self.pending = []
        self.existing = [check_effect(entry) for entry in existing]
        self.title('Adicionar vários efeitos — Studio FM' if self.batch else
                   'Editar efeito — Studio FM' if self.initial_effect else 'Criar efeito — Studio FM')
        self.configure(bg=BG)
        self.geometry('740x945' if self.batch else '650x790')
        self.minsize(640 if self.batch else 590, 730 if self.batch else 670)
        self.transient(master)
        self.grab_set()
        # Formulário rolável: pesquisa, filtros e efeitos acumulados precisam
        # caber também em monitores 1366×768 sem esconder OK/Cancelar.
        wrapper=ttk.Frame(self)
        wrapper.pack(fill='both',expand=True)
        viewport=tk.Canvas(wrapper,bg=BG,highlightthickness=0)
        scrollbar=ttk.Scrollbar(wrapper,orient='vertical',command=viewport.yview)
        viewport.configure(yscrollcommand=scrollbar.set)
        viewport.pack(side='left',fill='both',expand=True)
        scrollbar.pack(side='right',fill='y')
        form=ttk.Frame(viewport,padding=14)
        form_window=viewport.create_window((0,0),window=form,anchor='nw')
        form.bind('<Configure>',lambda event:viewport.configure(scrollregion=viewport.bbox('all')))
        viewport.bind('<Configure>',lambda event:viewport.itemconfigure(form_window,width=event.width))
        self.bind('<MouseWheel>',lambda event:viewport.yview_scroll(
            -(1 if event.delta>0 else -1),'units'))
        self.bind('<Button-4>',lambda event:viewport.yview_scroll(-1,'units'))
        self.bind('<Button-5>',lambda event:viewport.yview_scroll(1,'units'))
        self.vars={}
        self.combos={}
        self.labels={}
        self.sources={'evento':{k:v for k,v in EVENTS.items() if k != 'regra_deck'},
                      'acao':{k:v for k,v in ACTIONS.items() if k not in QUICK_ACTIONS and k != 'bonus_por_carta_id'},
                      'alvo':{k:TARGETS[k] for k in ('proprio', 'inimigo')},'escopo':SCOPES}
        # Os atalhos já cadastrados também podem ser editados pela tabela,
        # sem habilitar novos atalhos duplicados no formulário de criação.
        if self.initial_effect:
            self.sources['acao'].update((action, ACTIONS[action])
                                       for action in QUICK_ACTIONS)
            self.sources['evento']['regra_deck'] = EVENTS['regra_deck']
        row=0
        if self.batch:
            self.all_actions = dict(self.sources['acao'])
            self.search_action = tk.StringVar()
            self.category_action = tk.StringVar(value='Todas as categorias')
            ttk.Label(form,text='Pesquisar efeito (nome ou código)').grid(
                row=row,column=0,sticky='w',pady=(0,3));row+=1
            ttk.Entry(form,textvariable=self.search_action).grid(
                row=row,column=0,sticky='ew',pady=(0,6));row+=1
            ttk.Label(form,text='Categoria').grid(row=row,column=0,sticky='w');row+=1
            ttk.Combobox(form,textvariable=self.category_action,state='readonly',
                values=['Todas as categorias','Contínuos','Ao entrar em campo',
                        'Equipamentos','Outros'],width=54).grid(
                row=row,column=0,sticky='ew',pady=(0,8));row+=1
            self.search_action.trace_add('write',lambda *_:self._filter_actions())
            self.category_action.trace_add('write',lambda *_:self._filter_actions())
        for key,label in [('evento','Quando ativa'),('acao','O que acontece'),('alvo','Alvo do efeito')]:
            self.labels[key]=ttk.Label(form,text=label)
            self.labels[key].grid(row=row,column=0,sticky='w',pady=(0,3));row+=1
            source=self.sources[key]
            v=tk.StringVar(value=next(iter(source)))
            self.vars[key]=v
            combo=ttk.Combobox(form,state='readonly',width=60,values=[f'{k} — {t}' for k,t in source.items()])
            combo.current(0)
            combo.grid(row=row,column=0,sticky='ew',pady=(0,9));row+=1
            combo.bind('<<ComboboxSelected>>',lambda e,k=key,c=combo:self._choice(k,list(self.sources[k])[c.current()]))
            self.combos[key]=combo
            if key == 'alvo':
                self.recipient = ttk.Label(form, background=SURFACE, padding=(8, 8))
                self.recipient.grid(row=row-1,column=0,sticky='ew',pady=(0,9))
                self.recipient.grid_remove()
        self.labels['valor']=ttk.Label(form)
        self.labels['valor'].grid(row=row,column=0,sticky='w');row+=1
        self.vars['valor']=tk.StringVar(value='500')
        self.value_entry=ttk.Entry(form,textvariable=self.vars['valor'],width=60)
        self.value_entry.grid(row=row,column=0,sticky='ew',pady=(3,9));row+=1
        self.labels['valor_def']=ttk.Label(form)
        self.labels['valor_def'].grid(row=row,column=0,sticky='w');row+=1
        self.vars['valor_def']=tk.StringVar(value='0')
        self.def_entry=ttk.Entry(form,textvariable=self.vars['valor_def'],width=60,state='disabled')
        self.def_entry.grid(row=row,column=0,sticky='ew',pady=(3,9));row+=1
        self.labels['tipo_id']=ttk.Label(form)
        self.labels['tipo_id'].grid(row=row,column=0,sticky='w');row+=1
        self.vars['tipo_id']=tk.IntVar(value=-1)
        options=[(-1,'Todos os tipos')]+[(i,name) for i,name in enumerate(TYPE_NAMES[:25])]
        self.type_ids=[i for i,_ in options]
        self.type_combo=ttk.Combobox(form,state='disabled',width=60,values=[f'{i:02d} — {label}' for i,label in options])
        self.type_combo.current(0)
        self.type_combo.grid(row=row,column=0,sticky='ew',pady=(3,9));row+=1
        self.type_combo.bind('<<ComboboxSelected>>', lambda _: self._filter_selected(
            'tipo_id', self.type_ids[self.type_combo.current()]))
        filters = ttk.Frame(form)
        filters.grid(row=row, column=0, sticky='ew', pady=(0, 9))
        row += 1
        filters.columnconfigure((0, 1), weight=1, uniform='filters')
        ttk.Label(filters, text='Atributo').grid(row=0, column=0, sticky='w')
        self.vars['atributo_id'] = tk.IntVar(value=-1)
        self.attribute_combo = ttk.Combobox(filters, state='disabled', width=22,
                                            values=('Todos os atributos', *EFFECT_ATTRIBUTE_NAMES))
        self.attribute_combo.current(0)
        self.attribute_combo.grid(row=1, column=0, sticky='ew', padx=(0, 8), pady=(3, 0))
        self.attribute_combo.bind('<<ComboboxSelected>>', lambda _: self._filter_selected(
            'atributo_id', self.attribute_combo.current() - 1))
        ttk.Label(filters, text='Combinar filtros').grid(row=0, column=1, sticky='w')
        self.vars['combinar_filtros'] = tk.StringVar(value='e')
        self.sources['combinar_filtros'] = FILTER_COMBINATIONS
        self.filter_combo = ttk.Combobox(filters, state='disabled', width=22,
                                         values=tuple(FILTER_COMBINATIONS.values()))
        self.filter_combo.current(0)
        self.filter_combo.grid(row=1, column=1, sticky='ew', pady=(3, 0))
        self.filter_combo.bind('<<ComboboxSelected>>', lambda _: self.vars['combinar_filtros'].set(
            tuple(FILTER_COMBINATIONS)[self.filter_combo.current()]))
        self.combos['combinar_filtros'] = self.filter_combo
        self.specific_button=ttk.Button(form, text='Escolher carta específica do deck…',
                                        command=self._open_specific)
        self.specific_button.grid(row=row,column=0,sticky='ew',pady=(0,9));row+=1
        self.labels['escopo']=ttk.Label(form)
        self.labels['escopo'].grid(row=row,column=0,sticky='w');row+=1
        self.vars['escopo']=tk.StringVar(value='aliados')
        self.scope_combo=ttk.Combobox(form,state='disabled',width=60,values=[f'{k} — {label}' for k,label in SCOPES.items()])
        self.scope_combo.current(0)
        self.scope_combo.grid(row=row,column=0,sticky='ew',pady=(3,9));row+=1
        self.scope_combo.bind('<<ComboboxSelected>>',lambda e:self.vars['escopo'].set(list(SCOPES)[self.scope_combo.current()]))
        ttk.Label(form,text='Observação (opcional)').grid(row=row,column=0,sticky='w');row+=1
        self.vars['observacao']=tk.StringVar()
        ttk.Entry(form,textvariable=self.vars['observacao']).grid(row=row,column=0,sticky='ew',pady=(3,8));row+=1
        self.help=tk.Label(form,text='',bg=BG,fg='#edc47e',font=('Segoe UI',9),justify='left',wraplength=560)
        self.help.grid(row=row,column=0,sticky='w',pady=(0,8));row+=1
        if self.batch:
            selected=ttk.LabelFrame(form,text='Efeitos preparados (Aplicar não salva)',padding=5)
            selected.grid(row=row,column=0,sticky='nsew',pady=(0,8));row+=1
            self.pending_tree=ttk.Treeview(selected,columns=('num','efeito','valor'),
                                            show='headings',height=4,selectmode='extended')
            for key,title,width in (('num','#',34),('efeito','Efeito adicionado',420),
                                    ('valor','Valor',110)):
                self.pending_tree.heading(key,text=title)
                self.pending_tree.column(key,width=width,stretch=key=='efeito')
            self.pending_tree.pack(fill='both',expand=True)
            self.pending_label=tk.StringVar(value='Nenhum efeito preparado')
            ttk.Label(form,textvariable=self.pending_label).grid(row=row,column=0,sticky='w');row+=1
        # Rodapé fixo fora da área rolável: Aplicar/OK sempre visíveis.
        footer=ttk.Frame(self,padding=(14,8))
        footer.pack(side='bottom',fill='x',before=wrapper)
        buttons=ttk.Frame(footer)
        buttons.pack(side='right')
        ttk.Button(buttons,text='Cancelar',command=self.destroy).pack(side='left',padx=6)
        if self.batch:
            ttk.Button(buttons,text='Remover selecionados',command=self._remove_pending).pack(side='left',padx=6)
            ttk.Button(buttons,text='Aplicar',command=self._apply_pending).pack(side='left',padx=6)
        ttk.Button(buttons,text='OK' if self.batch else
                   'Salvar alterações' if self.initial_effect else 'Adicionar efeito',
                   style='Accent.TButton',command=self._submit).pack(side='left')
        form.columnconfigure(0,weight=1)
        if self.initial_effect:
            self._load_effect(self.initial_effect)
        else:
            self._refresh_controls()
        self.bind('<Escape>',lambda e:self.destroy())
        self.wait_visibility()
        self.focus_force()

    def _set(self,key,value):
        self.vars[key].set(value)
        self.combos[key].current(list(self.sources[key]).index(value))

    def _filter_actions(self):
        if not self.batch or 'acao' not in self.combos:
            return
        term=self.search_action.get().casefold().strip()
        category=self.category_action.get()
        def match(action):
            if action in EFFECT_ACTIONS:
                kind='Contínuos'
            elif action in ENTRY_EFFECTS:
                kind='Ao entrar em campo'
            elif action in EQUIPMENT_ACTIONS:
                kind='Equipamentos'
            else:
                kind='Outros'
            return (category=='Todas as categorias' or category==kind)
        filtered={key:caption for key,caption in self.all_actions.items()
                  if match(key) and (term in key.casefold() or term in caption.casefold())}
        if not filtered:
            return
        self.sources['acao']=filtered
        combo=self.combos['acao']
        combo.configure(values=[f'{key} — {value}' for key,value in filtered.items()])
        current=self.vars['acao'].get()
        if current not in filtered:
            self._choice('acao',next(iter(filtered)))
        else:
            combo.current(list(filtered).index(current))

    def _append_pending(self,entry):
        validated=check_effect(entry)
        if validated in self.pending or validated in self.existing:
            raise ModError('Este efeito já foi adicionado. Revise duplicatas.')
        self.pending.append(validated)
        self._refresh_pending()

    def _apply_pending(self):
        try:
            self._append_pending({key:v.get() for key,v in self.vars.items()})
        except (ModError,ValueError) as exc:
            messagebox.showerror('Efeito inválido',str(exc),parent=self)

    def _refresh_pending(self):
        if not self.batch:
            return
        self.pending_tree.delete(*self.pending_tree.get_children())
        for index,entry in enumerate(self.pending):
            self.pending_tree.insert('', 'end', iid=str(index),
                values=(index+1, ACTIONS.get(entry['acao'],entry['acao']),
                        str(entry.get('valor',0))))
        self.pending_label.set(f'{len(self.pending)} efeito(s) preparado(s); clique OK para confirmar.')

    def _remove_pending(self):
        for index in sorted((int(i) for i in self.pending_tree.selection()),reverse=True):
            self.pending.pop(index)
        self._refresh_pending()

    def _filter_selected(self, key, value):
        self.vars[key].set(value)
        self._refresh_filter_combination()

    def _refresh_filter_combination(self):
        both = (self.attribute_combo.instate(('readonly',))
                and self.vars['tipo_id'].get() != -1 and self.vars['atributo_id'].get() != -1)
        self.filter_combo.configure(state='readonly' if both else 'disabled')

    def _load_effect(self, entry):
        """Preenche os campos existentes sem transformar a regra em outra ação."""
        for key in ('evento', 'acao'):
            self._set(key, entry[key])
        self.vars['alvo'].set(entry['alvo'])
        if entry['alvo'] in self.sources['alvo']:
            self.combos['alvo'].current(list(self.sources['alvo']).index(entry['alvo']))
        for key in ('valor', 'valor_def', 'observacao'):
            self.vars[key].set(str(entry.get(key, '' if key == 'observacao' else 0)))
        typ = int(entry.get('tipo_id', -1))
        self.vars['tipo_id'].set(typ)
        self.type_combo.current(self.type_ids.index(typ) if typ in self.type_ids else 0)
        attr = int(entry.get('atributo_id', -1))
        self.vars['atributo_id'].set(attr)
        self.attribute_combo.current(attr + 1 if 0 <= attr < len(EFFECT_ATTRIBUTE_NAMES) else 0)
        self._set('combinar_filtros', entry.get('combinar_filtros', 'e'))
        scope = entry.get('escopo', 'aliados')
        self.vars['escopo'].set(scope)
        self.scope_combo.current(list(SCOPES).index(scope) if scope in SCOPES else 0)
        self._refresh_controls()

    def _choice(self,key,value):
        self.vars[key].set(value)
        action=self.vars['acao'].get()
        if key=='evento':
            if value == ENTRY_TYPE_EVENT:
                self._set('acao', ENTRY_GROW)
            elif value=='continuo' and action not in EFFECT_ACTIONS and action not in (
                    QUICK_ACTIONS - {'sem_limite_deck', 'limite_copias_deck', 'perder_lp_por_ataque'}):
                self._set('acao','aura_tipo')
            elif value=='equipado' and action not in EQUIPMENT_ACTIONS:
                self._set('acao','equip_atk')
            elif value=='regra_deck' and action not in ('sem_limite_deck','limite_copias_deck'):
                self._set('acao','limite_copias_deck')
            elif value not in ('continuo','equipado','regra_deck') and (
                    action in EFFECT_ACTIONS|EQUIPMENT_ACTIONS or
                    action in ENTRY_EFFECTS and value != ENTRY_EFFECTS[action] or
                    action in QUICK_ACTIONS and not (value=='atacar' and action=='perder_lp_por_ataque')):
                self._set('acao','aumentar_atk')
        if key=='acao':
            if value in ENTRY_EFFECTS:
                self._set('evento', ENTRY_EFFECTS[value])
            elif value in EFFECT_ACTIONS or value in QUICK_ACTIONS - {'sem_limite_deck', 'limite_copias_deck', 'perder_lp_por_ataque'}:
                self._set('evento','continuo')
            elif value in EQUIPMENT_ACTIONS:
                self._set('evento','equipado')
            elif value in ('sem_limite_deck','limite_copias_deck'):
                self._set('evento','regra_deck')
            elif value == 'perder_lp_por_ataque':
                self._set('evento','atacar')
            elif value in ONCE_ACTIONS:
                self._set('evento','invocar')
            elif self.vars['evento'].get() in ('continuo','equipado','regra_deck', ENTRY_TYPE_EVENT):
                self._set('evento','invocar')
        action=self.vars['acao'].get()
        if key=='acao' and action=='descartar_alvo':
            self.vars['valor'].set('1')
        if key == 'acao' and action == 'dano_lp':
            self._set('alvo', 'inimigo')
        if action == 'vinculo_vida':
            self._set('evento', 'atacar')
            self._set('alvo', 'proprio')
            self.vars['valor'].set('0')
        if action in ENTRY_EFFECTS and (key == 'acao' or value == ENTRY_TYPE_EVENT):
            scope = 'todos' if action == ENTRY_GROW else 'inimigos'
            self.vars['escopo'].set(scope)
            self.scope_combo.current(list(SCOPES).index(scope))
            self.vars['valor_def'].set('')
        self._refresh_controls()

    def _refresh_recipient(self, action):
        self.labels['alvo'].configure(text='Quem recebe o bônus' if action in EFFECT_ACTIONS else 'Alvo do efeito')
        target = self.fixed_targets.get(action)
        if target is not None:
            self.vars['alvo'].set(target)
            self.combos['alvo'].grid_remove()
            self.recipient.configure(text=effect_target_label(action, target))
            self.recipient.grid()
        else:
            current = self.vars['alvo'].get()
            self._set('alvo', current if current in self.sources['alvo'] else 'proprio')
            self.recipient.grid_remove()
            self.combos['alvo'].grid()

    def _refresh_controls(self):
        action=self.vars['acao'].get()
        continuous=action in EFFECT_ACTIONS
        marker = action in ENTRY_EFFECTS
        filtered = (continuous and action != 'bonus_por_carta_id') or marker
        self._refresh_recipient(action)
        counted = action in SCALING_ACTIONS
        self.labels['valor'].configure(
            text='ATK a reduzir' if action == ENTRY_SHRINK else 'ATK a acumular' if action == ENTRY_GROW else
                 'Bônus de ATK por carta contada' if counted else
                 'Bônus de ATK' if continuous else 'X pontos (ATK, LP, dano ou cartas descartadas)')
        self.labels['valor_def'].configure(
            text='DEF do marcador (vazio usa o valor de ATK)' if marker else
                 'Bônus de DEF por carta contada' if counted else 'Bônus de DEF')
        type_label = {'aura_tipo': 'Tipo de monstro que recebe o bônus',
                      'bonus_por_tipo': 'Tipo contado no campo',
                      ENTRY_GROW: 'Tipo de monstro que dispara o ganho',
                      ENTRY_SHRINK: 'Tipo de monstro que perde ATK/DEF'}.get(action, 'Tipo contado')
        self.labels['tipo_id'].configure(text=type_label)
        scope_label = {'aura_tipo': 'Lados afetados pela aura',
                       ENTRY_GROW: 'Campos onde a entrada conta',
                       ENTRY_SHRINK: 'Campos atingidos pela redução'}
        self.labels['escopo'].configure(text=scope_label.get(action, 'Lados que entram na contagem'))
        typ = filtered or action in ('cura_lp_deck_tipo','dano_lp_deck_tipo')
        choices = [-1, *(i for i in range(25) if not marker or i < 20 or i == 24)]
        if self.type_ids != choices:
            self.type_ids = choices
            self.type_combo.configure(values=['Todos os tipos', *(f'{i:02d} — {TYPE_NAMES[i]}' for i in choices[1:])])
            selected = self.vars['tipo_id'].get()
            if selected not in choices:
                selected = -1
                self.vars['tipo_id'].set(selected)
            self.type_combo.current(choices.index(selected))
        protection=action in (EQUIPMENT_ACTIONS-{'equip_atk'}) or action in BOOLEAN_ACTIONS or action == 'vinculo_vida'
        self.def_entry.configure(state='normal' if continuous or marker else 'disabled')
        self.type_combo.configure(state='readonly' if typ else 'disabled')
        self.attribute_combo.configure(state='readonly' if filtered else 'disabled')
        self._refresh_filter_combination()
        self.scope_combo.configure(state='readonly' if continuous or marker else 'disabled')
        if protection:
            self.vars['valor'].set('0')
        elif self.vars['valor'].get()=='0' and not (continuous or marker):
            self.vars['valor'].set('500' if action!='descartar_alvo' else '1')
        self.value_entry.configure(state='disabled' if protection else 'normal')
        if action in COUNT_ZONES:
            zone = {'campo': 'no campo', 'deck': 'do deck', 'mao': 'na mão', 'cemiterio': 'no cemitério'}[COUNT_ZONES[action]]
            from . import i18n
            self.specific_button.configure(text=i18n.t(f'Contar uma carta específica {zone} em vez do tipo…'))
            self.specific_button.grid()
        else:
            self.specific_button.grid_remove()
        if action == 'vinculo_vida':
            self.labels['valor'].configure(text='Cura automática: ATK efetivo do atacante')
            help_text='⚔ ♥ Ao declarar um ataque, restaura LP iguais ao ATK efetivo. Funciona mesmo se o alvo defender. Disponível no simulador; PS1 ainda não suporta.'
        elif action=='bonus_cemiterio_tipo':
            help_text='Recebe o bônus por carta correspondente no cemitério. Atualiza conforme as cartas entram ou saem.'
        elif action=='bonus_deck_tipo':
            help_text='Bônus fixo por carta correspondente na composição inicial do deck.'
        elif action=='bonus_mao_tipo':
            help_text='Recebe o bônus por carta correspondente na mão. Recalcula após compras, invocações e descartes.'
        elif action=='bonus_por_tipo':
            help_text=('Esta carta recebe o bônus por cada monstro correspondente no campo. '
                       'Monstros virados para baixo também contam.')
        elif action=='aura_tipo':
            help_text='Cada monstro correspondente nos lados escolhidos recebe o bônus, inclusive virado para baixo.'
        elif action in ('cura_lp_deck_tipo','dano_lp_deck_tipo'):
            help_text='X vezes o número de cartas do tipo no deck configurado. Ativado UMA vez ao entrar em campo.'
        elif action == 'dano_lp':
            if self.vars['evento'].get() == 'atacar':
                if self.vars['alvo'].get() == 'proprio':
                    help_text=('A cada ataque declarado, o CONTROLADOR perde X LP, '
                               'inclusive ao atacar monstro em defesa. '
                               'Suportado no simulador e no PS1 Drop x15 para valores até 9.999.')
                else:
                    help_text=('Ao atacar, causa X LP ao adversário no simulador. '
                               'Este alvo ainda não é suportado no motor PS1.')
            else:
                help_text='Causa X LP ao lado selecionado. Entrada em campo suportada no PS1 Drop x15.'
        elif action=='dano_monstro_alvo':
            help_text='Dano a criatura é experimental: HP simulado começa igual à DEF-base (mínimo 1).'
        elif action=='descartar_alvo':
            help_text='O oponente descarta até X cartas da mão configurada no simulador, uma vez por invocação.'
        elif action == ENTRY_GROW:
            help_text=('Cada monstro que atende ao filtro soma ATK/DEF a esta carta ao entrar, inclusive ela própria. '
                       'Monstros virados para baixo contam. Os pontos duram até a carta sair do campo.')
        elif action == ENTRY_SHRINK:
            help_text=('Ao entrar, reduz o ATK e a DEF de cada monstro escolhido, inclusive virado para baixo. '
                       'A redução dura até o alvo sair do campo. Se o alvo ficar 0/0, ele é destruído.')
        elif action in EQUIPMENT_ACTIONS:
            help_text='O efeito se mantém apenas enquanto a carta estiver equipada ao monstro no simulador.'
        else:
            help_text='Efeito ativado; mantenha os testes no simulador antes de planejar implementação no PS1.'
        self.help.configure(text=help_text)

    def _open_specific(self):
        project = self.cards
        if project is None:
            messagebox.showerror('Sem projeto', 'Abra um projeto antes de selecionar cartas.', parent=self)
            return
        catalog = {cid:project.get(cid) for cid in project.cards}
        def submit(entry):
            if self.batch:
                self._append_pending(entry)
            else:
                self.on_save(entry)
                self.destroy()
        SpecificCardEffectDialog(self, catalog, submit,
                                 default_origin=COUNT_ZONES.get(self.vars['acao'].get(), 'deck'))

    def _submit(self):
        try:
            if self.batch:
                if not self.pending:
                    self._append_pending({key:v.get() for key,v in self.vars.items()})
                self.on_save([dict(entry) for entry in self.pending])
            else:
                entry={key:v.get() for key,v in self.vars.items()}
                self.on_save(entry)
        except (ModError,ValueError) as exc:
            messagebox.showerror('Efeito inválido',str(exc),parent=self)
            return
        self.destroy()


class SpecificCardEffectDialog(tk.Toplevel):
    """Adicionar bônus por carta selecionada sem digitar IDs na descrição."""
    def __init__(self, master, cards, on_save, *, initial_effect=None, default_origin='campo'):
        super().__init__(master)
        self.initial_effect = dict(initial_effect) if initial_effect else None
        self.title('Editar bônus por carta específica' if self.initial_effect
                   else 'Bônus contínuo por carta específica')
        self.geometry('590x560')
        self.configure(bg=BG)
        self.transient(master)
        self.grab_set()
        self.cards=cards
        self.on_save=on_save
        pane=ttk.Frame(self,padding=20);pane.pack(fill='both',expand=True)
        self.labels={f'{cid:05d} — {display_name(cid,cards)}':cid for cid in sorted(cards)}
        self.selected=tk.StringVar()
        if self.labels:
            self.selected.set(next(iter(self.labels)))
        if self.initial_effect:
            old_ref = int(self.initial_effect.get('carta_referencia_id', 0))
            old_label = next((name for name, cid in self.labels.items() if cid == old_ref), None)
            if old_label is not None:
                self.selected.set(old_label)
        chosen=ttk.Frame(pane);chosen.pack(fill='x',pady=(0,12))
        ttk.Label(chosen,text='Carta que será contada:').pack(side='left')
        ttk.Label(chosen,textvariable=self.selected,style='Section.TLabel').pack(side='left',padx=8)
        ttk.Button(chosen,text='Procurar carta…',command=self._browse).pack(side='right')
        ttk.Label(pane,text='Contar cartas em:').pack(anchor='w')
        self.origin=tk.StringVar(value=self.initial_effect.get('origem_contagem', 'campo')
                                 if self.initial_effect else default_origin)
        for label,val in [('Campo (inclusive cartas viradas para baixo)','campo'),('Monte de compra','deck'),
                          ('Mão (só no simulador do Studio)','mao'),('Cemitério (só no simulador do Studio)','cemiterio')]:
            ttk.Radiobutton(pane,text=label,value=val,variable=self.origin).pack(anchor='w',pady=3)
        ttk.Label(pane,text='Quais decks/campos contam?').pack(anchor='w',pady=(7,3))
        self.scope=tk.StringVar(value=self.initial_effect.get('escopo', 'aliados')
                                if self.initial_effect else 'aliados')
        scope=ttk.Combobox(pane,textvariable=self.scope,values=['aliados','inimigos','todos'],state='readonly')
        scope.pack(fill='x',pady=(0,12))
        row=ttk.Frame(pane);row.pack(fill='x')
        self.attack=tk.StringVar(value=str(self.initial_effect.get('valor', 200))
                                 if self.initial_effect else '200')
        self.defense=tk.StringVar(value=str(self.initial_effect.get('valor_def', 0))
                                  if self.initial_effect else '0')
        for key,v in [('ATK por cópia',self.attack),('DEF por cópia',self.defense)]:
            block=ttk.Frame(row);block.pack(side='left',padx=(0,16))
            ttk.Label(block,text=key).pack(anchor='w');ttk.Entry(block,width=15,textvariable=v).pack()
        ttk.Label(pane,text='Exemplo: 3 cópias × +200 ATK = +600 ATK.').pack(anchor='w',pady=(8,2))
        ttk.Label(pane,text='Observação (opcional)').pack(anchor='w',pady=(10,3))
        self.note=tk.StringVar(value=self.initial_effect.get('observacao', '')
                               if self.initial_effect else '')
        ttk.Entry(pane,textvariable=self.note).pack(fill='x')
        ttk.Label(pane,text=('A edição mantém o texto da descrição intacto.'
                             if self.initial_effect else
                             'Ao adicionar, o nome da carta será inserido na descrição.'),
                  foreground='#edc47e').pack(anchor='w',pady=12)
        buttons=ttk.Frame(pane);buttons.pack(fill='x')
        ttk.Button(buttons,text='Cancelar',command=self.destroy).pack(side='left')
        ttk.Button(buttons,text='Salvar alterações' if self.initial_effect
                   else 'Adicionar efeito + texto',style='Accent.TButton',
                   command=self.submit).pack(side='right')
        from .ui_shell import pin_bottom
        pin_bottom(buttons, pady=(8, 0))

    def _browse(self):
        from .card_picker import CardPickerDialog
        current=self.labels.get(self.selected.get())
        def picked(ids):
            label=next((name for name, cid in self.labels.items() if cid == ids[0]), None)
            if label:
                self.selected.set(label)
        CardPickerDialog(self, self.cards, picked, title='Carta que será contada', initial=current)

    def submit(self):
        value=self.selected.get().strip()
        ref=self.labels.get(value)
        if ref is None:
            match=re.match(r'^#?(\d+)',value)
            ref=int(match.group(1)) if match else None
        if not ref or ref not in self.cards:
            messagebox.showerror('Referência inválida','Escolha uma carta existente.',parent=self);return
        try:
            entry={'evento':'continuo','acao':'bonus_por_carta_id','alvo':'proprio',
                   'carta_referencia_id':ref,'origem_contagem':self.origin.get(),
                   'escopo':self.scope.get(),'valor':int(self.attack.get()),
                   'valor_def':int(self.defense.get()), 'observacao':self.note.get()}
            self.on_save(entry)
        except (ValueError,ModError) as exc:
            messagebox.showerror('Efeito inválido',str(exc),parent=self);return
        self.destroy()


class FieldDialog(tk.Toplevel):
    """Campo visual de 5 x 5 slots que recalcula auras instantaneamente."""
    def __init__(self, master, project, drafts, initial_card):
        super().__init__(master)
        self.project = project
        self.drafts = drafts
        self.title('Simular efeitos contínuos — 5 x 5')
        self.geometry('960x735')
        self.minsize(850,680)
        self.configure(bg=BG)
        self.transient(master)
        self.choices = {'— VAZIO —':None}
        self.display_by_id = {}
        for cid in sorted(project.cards):
            card = drafts.get_card(cid)
            display = f'#{cid:03d} — {card.get("nome") or "(sem nome)"}'[:70]
            self.choices[display] = cid
            self.display_by_id[cid] = display
        opts = list(self.choices)
        tk.Label(self,text='SIMULADOR DE CAMPO — EFEITOS CONTÍNUOS',bg=BG,fg=TEXT,
                 font=('Segoe UI',14,'bold')).pack(anchor='w',padx=18,pady=(13,2))
        tk.Label(self,text='Adicione ou remova monstros. O bônus muda imediatamente; não fica acumulado. '
                'Somente monstros aliados virados para cima recebem/contam por tipo.',
                 bg=BG,fg=MUTED,wraplength=890,justify='left').pack(anchor='w',padx=18,pady=(0,8))
        self.entries=[]
        holder=tk.Frame(self,bg=BG)
        holder.pack(fill='both',expand=True,padx=16)
        for col,side in enumerate(('jogador','adversario')):
            panel=tk.Frame(holder,bg=SURFACE,padx=10,pady=10)
            panel.grid(row=0,column=col,sticky='nsew',padx=4)
            tk.Label(panel,text='SEU CAMPO' if col==0 else 'CAMPO ADVERSÁRIO',bg=SURFACE,
                     fg=ACCENT,font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(0,10))
            for slot in range(1,6):
                row=tk.Frame(panel,bg=SURFACE)
                row.pack(fill='x',pady=(0,7))
                tk.Label(row,text=f'{slot}.',bg=SURFACE,fg=TEXT,width=3).pack(side='left')
                v=tk.StringVar(value='— VAZIO —')
                c=ttk.Combobox(row,textvariable=v,width=36,values=opts,state='readonly')
                c.pack(side='left',fill='x',expand=True)
                face=tk.BooleanVar(value=True)
                ttk.Checkbutton(row,text='↑',variable=face,command=self._evaluate).pack(side='left',padx=3)
                state=tk.Label(panel,text='Vazio',bg=SURFACE,fg=MUTED,font=('Segoe UI',9),anchor='w')
                state.pack(fill='x',padx=(20,0),pady=(0,4))
                entry=(side,slot,v,face,state)
                self.entries.append(entry)
                c.bind('<<ComboboxSelected>>',lambda e:self._evaluate())
                if col==0 and slot==1 and initial_card in self.display_by_id:
                    v.set(self.display_by_id[initial_card])
        holder.columnconfigure(0,weight=1)
        holder.columnconfigure(1,weight=1)
        logs=tk.Frame(self,bg=BG)
        logs.pack(fill='both',expand=True,padx=20,pady=(12,0))
        tk.Label(logs,text='BÔNUS APLICADOS',bg=BG,fg=TEXT,font=('Segoe UI',10,'bold')).pack(anchor='w')
        self.log=tk.Text(logs,height=6,wrap='word',bg=SURFACE,fg=TEXT,state='disabled',font=('Consolas',9))
        self.log.pack(fill='both',expand=True,pady=(6,0))
        tk.Label(self,text='Simulação local • não executa efeitos no BIN/PS1',bg=BG,fg='#edc47e').pack(anchor='w',padx=20,pady=(4,10))
        self._evaluate()

    def _evaluate(self):
        if not self.project:
            return
        board=[]
        for side,slot,var,face,label in self.entries:
            cid=self.choices.get(var.get())
            if cid is None:
                label.configure(text='Vazio',fg=MUTED)
                continue
            card=self.drafts.get_card(cid)
            board.append({'lado':side,'slot':slot,'card_id':cid,'tipo_id':card['tipo_id'],
                          'atributo_id':card.get('atributo_id', -1),
                          'ataque':card['ataque'],'defesa':card['defesa'],'face_up':face.get()})
        try:
            resolved,events=self.drafts.simulate_field(board)
        except (ModError,ValueError) as exc:
            self.log.configure(state='normal')
            self.log.delete('1.0','end')
            self.log.insert('end',f'Campo inválido: {exc}')
            self.log.configure(state='disabled')
            return
        mapped={(m['lado'],m['slot']):m for m in resolved}
        for side,slot,var,face,label in self.entries:
            m=mapped.get((side,slot))
            if m:
                da,dd=m['ataque']-m['ataque_base'],m['defesa']-m['defesa_base']
                label.configure(text=f'ATK {m["ataque_base"]} → {m["ataque"]} ({da:+})  •  '
                               f'DEF {m["defesa_base"]} → {m["defesa"]} ({dd:+})',
                                fg=ACCENT if (da or dd) else MUTED)
        self.log.configure(state='normal')
        self.log.delete('1.0','end')
        if not events:
            self.log.insert('end','Nenhuma aura ou bônus por tipo ativo nesse campo.\n')
        for e in events[:80]:
            self.log.insert('end',f'{e["origem"]} → {e["destino"]}: '
                             f'{e["acao"]} ({e["quantidade"]} x)  '
                             f'ATK +{e["ataque"]}, DEF +{e["defesa"]}\n')
        if len(events)>80:
            self.log.insert('end',f'... {len(events)-80} aplicações adicionais.')
        self.log.configure(state='disabled')


class Studio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(self._window_title())
        self.prefs = ui_prefs.load()
        geometry = self.prefs['geometria']
        self.geometry(geometry if ui_prefs.valid_geometry(geometry) else '1390x825')
        self.minsize(min(1050, self.winfo_screenwidth() - 40), min(650, self.winfo_screenheight() - 80))
        if self.prefs.get('maximizada'):
            try:
                self.state('zoomed')
            except tk.TclError:
                pass
        from . import i18n
        from .ui_i18n import patch_dialogs
        i18n.set_language(self.prefs.get('idioma', 'pt'))
        patch_dialogs()
        self.history = ui_nav.History()
        self._section = None
        self._busy = None
        self.configure(bg=BG)
        self.project: Project | None = None
        self.drafts: DraftSession | None = None
        self.selected_id: int | None = None
        self.filter = tk.StringVar()
        self.filter_type = tk.StringVar(value='Todos')
        self.filter_star = tk.StringVar(value='Todas')
        self.filter_from = tk.StringVar()
        self.filter_to = tk.StringVar()
        self._loading = False
        self._suspend_filters = False
        self._toast_timeout = None
        self._update_messages = queue.Queue()
        self._extract_messages = queue.Queue()
        self._extract_running = False
        self.preview_img = None
        self.vars = {}
        self._style()
        self._build()
        for field in (self.filter, self.filter_type, self.filter_star, self.filter_from, self.filter_to):
            field.trace_add('write', lambda *_: self._refresh_cards() if not self._suspend_filters else None)
        self._bind_shortcuts()
        self.bind('<Configure>', self._on_resize, add='+')
        # Toda janela secundária é ajustada à tela ao abrir (notebooks 1366×768, escala 125–150 %).
        self.bind_class('Toplevel', '<Map>', self._fit_toplevel, add='+')
        self.protocol('WM_DELETE_WINDOW',self._on_close)
        start = self.prefs.get('secao', 'inicio')
        self.show_section(start if start in ui_nav.BY_KEY else 'inicio')
        self.apply_language()

    def _style(self):
        ui_theme.apply(self)

    def _build(self):
        from .ui_shell import NavSidebar, StatusBar, CommandPalette, Tooltip
        self.status = tk.StringVar(value='Abra ou crie um projeto para editar suas cartas.')
        self.statusbar = StatusBar(self, self.status)
        self.statusbar.pack(side='bottom', fill='x')
        self.nav = NavSidebar(self, self.show_section, collapsed=self.prefs.get('barra_recolhida', False))
        self.nav.on_collapse = self._sidebar_collapsed
        self.nav.pack(side='left', fill='y')
        workspace = tk.Frame(self, bg=BG)
        workspace.pack(side='left', fill='both', expand=True)

        header = tk.Frame(workspace,bg=SURFACE,padx=12,pady=7)
        header.pack(fill='x')
        history = tk.Frame(header, bg=SURFACE)
        history.pack(side='left', padx=(0, 10))
        self.back_button = ttk.Button(history, text='◀', width=3, style='Small.TButton', command=self.go_back)
        self.back_button.pack(side='left')
        self.forward_button = ttk.Button(history, text='▶', width=3, style='Small.TButton', command=self.go_forward)
        self.forward_button.pack(side='left', padx=(3, 0))
        Tooltip(self.back_button, 'Voltar à tela anterior (Alt+←)')
        Tooltip(self.forward_button, 'Avançar (Alt+→)')
        actions = tk.Frame(header, bg=SURFACE)
        actions.pack(side='right')          # empacotado antes do título: os botões têm prioridade
        from . import i18n
        self.language_button = ttk.Menubutton(actions, text='A文')
        self.language_button._i18n_skip = True
        language_menu = self._menu(self.language_button)
        language_menu._i18n_skip = True
        self.language_choice = tk.StringVar(value=self.prefs.get('idioma', 'pt'))
        for code, name in i18n.LANGUAGES.items():
            language_menu.add_radiobutton(label=name, value=code, variable=self.language_choice,
                                          command=lambda c=code: self.apply_language(c))
        self.language_button.configure(menu=language_menu)
        self.language_button.pack(side='left', padx=(0, 6))
        Tooltip(self.language_button, 'Idioma da interface')
        self.search_button = ttk.Button(actions, text='⌕ Buscar  Ctrl+K', command=self.open_palette)
        self.search_button.pack(side='left', padx=(0, 6))
        Tooltip(self.search_button, 'Ir para qualquer tela ou ação pelo nome')
        for title, options in (
                ('Projeto', [('Novo projeto', self.new_project, 'Ctrl+N'),
                             ('Abrir projeto', self.open_project, 'Ctrl+O'),
                             ('Salvar projeto', self.save_project, 'Ctrl+S'),
                             None,
                             ('Traduzir descrições…', lambda: self.open_translation(), 'Ctrl+T'),
                             ('Exportar alterações (JSON e SLUS auxiliar)', self.export, None),
                             ('Verificar integridade do projeto', self.verify, None)]),
                ('Importar', [('Importar CSVs', self.import_csv, None),
                              ('Importar BIN/CUE', self.import_bin, None),
                              ('Extrair máximo', self.extract_max, None),
                              ('Vincular SLUS', self.attach_slus, None)])):
            group = ttk.Menubutton(actions, text=title)
            menu = self._menu(group)
            for option in options:
                if option is None:
                    menu.add_separator()
                    continue
                label, action, shortcut = option
                menu.add_command(label=label, command=action, accelerator=shortcut or '')
            group.configure(menu=menu)
            group.pack(side='left', padx=(0, 5))
        # Mantido para o código que habilita/desabilita botões; a ação fica no menu Projeto.
        self.export_button = ttk.Button(actions, text='Exportar', command=self.export, state='disabled')
        self.save_button = ttk.Button(actions, text='Salvar', style='Accent.TButton',
                                      command=self.save_project, state='disabled')
        self.save_button.pack(side='left', padx=(0, 5))
        Tooltip(self.save_button, 'Salvar projeto (Ctrl+S)')
        self.translate_button = ttk.Button(actions, text='Traduzir…', command=self.open_translation,
                                           state='disabled')
        self.translate_button.pack(side='left', padx=(0, 5))
        Tooltip(self.translate_button, 'Traduzir as descrições das cartas para outro idioma (Ctrl+T)')
        self.build_button = ttk.Button(actions, text='Gerar BIN/CUE', style='Accent.TButton',
                                       command=self.build_disc, state='disabled')
        self.build_button.pack(side='left', padx=(0, 5))
        Tooltip(self.build_button, 'Gerar o jogo modificado em BIN/CUE (Ctrl+B)')
        self.update_button = ttk.Button(actions, text='⟳', width=3, command=self.check_updates)
        self.update_button.pack(side='left')
        Tooltip(self.update_button, 'Verificar atualizações do Studio')
        titleframe = tk.Frame(header,bg=SURFACE)
        titleframe.pack(side='left', fill='x', expand=True)
        self.section_title = tk.Label(titleframe,text='Início',font=('Segoe UI',14,'bold'),bg=SURFACE,fg=TEXT,anchor='w')
        self.section_title.pack(fill='x')
        self.section_hint = tk.Label(titleframe,text='',font=('Segoe UI',9),bg=SURFACE,fg=MUTED,anchor='w')
        self.section_hint.pack(fill='x')
        self.proj_title = tk.Label(header,text='Nenhum projeto aberto',font=('Segoe UI',10),bg=SURFACE,fg=MUTED)
        self.toast = tk.Label(self, bg='#22454a', fg=TEXT, font=('Segoe UI', 10, 'bold'),
                              padx=13, pady=9, wraplength=360, justify='left')
        self.palette = CommandPalette(self)
        outer = tk.PanedWindow(workspace, orient='horizontal', bg=BG, sashwidth=6, bd=0)
        outer.pack(fill='both',expand=True,padx=(8,8),pady=(8,6))
        self.outer = outer

        sidebar = tk.Frame(outer,bg=SURFACE)
        self.library = sidebar
        outer.add(sidebar, width=self.prefs.get('largura_biblioteca', 327), minsize=240, stretch='never')
        tk.Label(sidebar,text='BIBLIOTECA DE CARTAS',bg=SURFACE,fg=TEXT,font=('Segoe UI',11,'bold')).pack(anchor='w',padx=14,pady=(17,8))
        self.new_card_button = ttk.Button(sidebar, text='＋ Nova carta', style='Accent.TButton',
                                          command=self.add_new_card, state='disabled')
        self.new_card_button.pack(fill='x',padx=12,pady=(0,7))
        tk.Label(sidebar,text='ID, nome, tipo ou descrição · Ctrl+F',bg=SURFACE,fg=MUTED).pack(anchor='w',padx=12)
        self.card_search = ttk.Entry(sidebar,textvariable=self.filter)
        self.card_search.pack(fill='x',padx=12,pady=(3,8))
        filters = tk.Frame(sidebar,bg=SURFACE)
        filters.pack(fill='x',padx=12,pady=(0,8))
        ttk.Label(filters,text='Tipo').grid(row=0,column=0,sticky='w')
        ttk.Label(filters,text='Guardian Star').grid(row=0,column=1,sticky='w')
        ttk.Combobox(filters,textvariable=self.filter_type,state='readonly',width=13,
                     values=['Todos','Monstros',*(f'{i:02d} — {v}' for i,v in enumerate(TYPE_NAMES))]).grid(row=1,column=0,sticky='ew',padx=(0,5))
        ttk.Combobox(filters,textvariable=self.filter_star,state='readonly',width=13,
                     values=['Todas',*(f'{i:02d} — {guardian_name(i)}' for i,v in enumerate(STAR_NAMES) if v)]).grid(row=1,column=1,sticky='ew')
        ttk.Label(filters,text='ID de / até').grid(row=2,column=0,sticky='w',pady=(6,0))
        interval = tk.Frame(filters,bg=SURFACE)
        interval.grid(row=2,column=1,sticky='e',pady=(6,0))
        for field in (self.filter_from,self.filter_to):
            ttk.Entry(interval,textvariable=field,width=6).pack(side='left',padx=(3,0))
        filters.columnconfigure(0,weight=1)
        filters.columnconfigure(1,weight=1)
        treeholder = tk.Frame(sidebar,bg=SURFACE)
        treeholder.pack(fill='both',expand=True,padx=8,pady=(0,8))
        self.tree = ttk.Treeview(treeholder,columns=('id','nome','atk','def'),show='headings',selectmode='extended')
        for col,text,width,anchor in [('id','ID',48,'w'),('nome','Nome / identificação',146,'w'),('atk','ATK',56,'e'),('def','DEF',56,'e')]:
            self.tree.heading(col,text=text)
            self.tree.column(col,width=width,anchor=anchor,stretch=(col=='nome'))
        self.sort_cards = sortable_columns(self.tree, raw_values=self._card_sort_value)
        scroll = ttk.Scrollbar(treeholder,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left',fill='both',expand=True)
        scroll.pack(side='right',fill='y')
        self.tree.bind('<<TreeviewSelect>>',self._on_card_select)
        self.tree.bind('<Button-3>', self._card_menu)
        self.tree.bind('<Control-a>', self._select_visible_cards)
        self.tree.bind('<Double-1>', lambda _event: self.tabs.select(self.tab_cards) if self.tree.selection() else None)
        self.card_menu = self._menu(self)
        self.card_menu.add_command(label='Abrir no editor', accelerator='Enter',
                                   command=lambda: self.show_section('cartas'))
        self.card_menu.add_command(label='Adicionar selecionadas ao deck do oponente',
                                   command=self._add_selected_to_deck)
        self.card_menu.add_command(label='Editar selecionadas em lote…', accelerator='Ctrl+E',
                                   command=self.open_bulk_edit)
        self.card_menu.add_command(label='Copiar linhas', accelerator='Ctrl+C', command=self._copy_card_rows)
        self.card_menu.add_command(label='Traduzir descrições selecionadas…', accelerator='Ctrl+T',
                                   command=self.open_translation)
        self.card_menu.add_separator()
        self.card_menu.add_command(label='Selecionar todas as visíveis', accelerator='Ctrl+A',
                                   command=self._select_visible_cards)
        self.count_label = tk.Label(sidebar,text='Importe suas tabelas para começar',bg=SURFACE,fg=MUTED,font=('Segoe UI',9))
        self.count_label.pack(anchor='w',padx=14,pady=(0,5))
        self.pending_label = tk.Label(sidebar,text='Nenhuma edição pendente',bg=SURFACE,fg=MUTED,font=('Segoe UI',9,'bold'))
        self.pending_label.pack(anchor='w',padx=14,pady=(0,13))

        main = ttk.Frame(outer)
        self.main_pane = main
        outer.add(main, minsize=655, stretch='always')
        self.tabs = ttk.Notebook(main, style='Hidden.TNotebook')
        self.tabs.pack(fill='both',expand=True)
        self.tab_home = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_home, text='Início')
        self.tab_cards = ttk.Frame(self.tabs)
        self.tab_effects = ttk.Frame(self.tabs)
        self.tab_fusions = ttk.Frame(self.tabs)
        self.tab_proj = ttk.Frame(self.tabs)
        self.tab_extract = ttk.Frame(self.tabs)
        self.tab_mod = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_cards,text='Cartas')
        self.tabs.add(self.tab_effects,text='Efeitos')
        self.tabs.add(self.tab_fusions,text='Fusões originais')
        self.tabs.add(self.tab_mod,text='Edição do Mod')
        self.tabs.add(self.tab_proj,text='Exportação')
        self.tabs.add(self.tab_extract,text='Dados extraídos')
        self.tabs.enable_traversal()
        self._cards_tab()
        self._effects_tab()
        self._fusions_tab()
        self._project_tab()
        self._extract_tab()
        from .mod_gui import ModEditor
        self.mod_editor = ModEditor(self.tab_mod,self)
        self.mod_editor.tabs.configure(style='Hidden.TNotebook')
        self._home_tab()
        self.tabs.bind('<<NotebookTabChanged>>', lambda _e: self._sync_section(), add='+')
        self.mod_editor.tabs.bind('<<NotebookTabChanged>>', lambda _e: self._sync_section(), add='+')

    def _menu(self, parent):
        return ui_theme.menu(parent)

    # ── navegação ────────────────────────────────────────────────────────
    def _fit_toplevel(self, event):
        window = event.widget
        if window is self or getattr(window, '_fitted', False) or not isinstance(window, tk.Toplevel):
            return
        try:
            if window.overrideredirect():
                return
        except tk.TclError:
            return
        window._fitted = True
        from .ui_shell import fit_to_screen
        from . import i18n
        if i18n.language() != 'pt':
            from .ui_i18n import translate_tree
            translate_tree(window)
        window.after_idle(lambda: fit_to_screen(window))

    def _window_title(self):
        from .build_info import BUILD
        title = f'Yu-Gi-Oh Studio Card FM | v{__version__}' + (f' ({BUILD})' if BUILD else '')
        project = getattr(self, 'project', None)
        return title + (f' — {project.metadata.get("nome", "")}' if project else '')

    def _bind_shortcuts(self):
        def global_key(sequence, action):
            def handler(event):
                try:
                    if event.widget.winfo_toplevel() is not self:
                        return None
                except (AttributeError, tk.TclError):
                    pass
                if self.grab_current() not in (None, self) or self._busy:
                    return 'break'
                action()
                return 'break'
            self.bind(sequence, handler)
            # Campos de texto têm atalhos de classe (ex.: Ctrl+K apaga a linha no
            # Tk); a combinação do Studio tem prioridade dentro da janela principal.
            for widget_class in ('Text', 'Entry', 'TEntry', 'TCombobox', 'TSpinbox'):
                self.bind_class(widget_class, sequence, handler)
        global_key('<Control-f>', self.focus_catalog)
        global_key('<Control-s>', self.save_project)
        global_key('<Control-o>', self.open_project)
        global_key('<Control-n>', self.new_project)
        global_key('<Control-b>', self.build_disc)
        global_key('<Control-k>', self.open_palette)
        global_key('<Control-t>', self.open_translation)
        global_key('<Control-l>', self.toggle_library)
        global_key('<Control-backslash>', self.toggle_sidebar)
        global_key('<Alt-Left>', self.go_back)
        global_key('<Alt-Right>', self.go_forward)
        global_key('<F1>', lambda: self.show_section('inicio'))
        for number, key in enumerate(('cartas', 'efeitos', 'deck', 'drops', 'iniciais', 'quests'), start=1):
            global_key(f'<Control-Key-{number}>', lambda key=key: self.show_section(key))
        self.tree.bind('<Return>', lambda _e: self.show_section('cartas') if self.tree.selection() else None)
        self.tree.bind('<Control-c>', self._copy_card_rows)
        self.tree.bind('<Control-e>', lambda _e: (self.open_bulk_edit(), 'break')[1])
        self.effect_tree.bind('<Delete>', lambda _e: self.remove_effect())

    def show_section(self, key):
        section = ui_nav.BY_KEY.get(key)
        if section is None:
            return
        self.tabs.select(getattr(self, section.tab))
        if section.mod is not None:
            self.mod_editor.tabs.select(section.mod)
        self._sync_section()

    def _current_section(self):
        try:
            tab = self.tabs.select()
        except tk.TclError:
            return None
        name = next((attr for attr in ('tab_home', 'tab_cards', 'tab_effects', 'tab_fusions', 'tab_mod',
                                       'tab_proj', 'tab_extract') if str(getattr(self, attr, '')) == tab), None)
        mod = self.mod_editor.tabs.index('current') if name == 'tab_mod' else None
        return ui_nav.section_for(name, mod) if name else None

    def _sync_section(self):
        key = self._current_section()
        if key is None or key == self._section:
            return
        self._section = key
        section = ui_nav.BY_KEY[key]
        self.history.visit(key)
        self.nav.set_active(key)
        self._set_section_texts(section)
        self.back_button.configure(state='normal' if self.history.back else 'disabled')
        self.forward_button.configure(state='normal' if self.history.forward else 'disabled')
        if section.tab == 'tab_mod':
            self.mod_editor.show_duelist_header(key in ('deck', 'drops', 'iniciais', 'quests'))
        self._apply_library_visibility()
        self.prefs['secao'] = key
        if key == 'inicio':
            self._refresh_home()

    def _set_section_texts(self, section):
        from . import i18n
        self.section_title.configure(text=i18n.t(section.label))
        self.section_hint.configure(text=i18n.t(section.hint))
        if i18n.language() != 'pt':
            from .ui_i18n import translate_tree
            translate_tree(getattr(self, section.tab))

    def apply_language(self, code=None):
        """Troca o idioma da interface na hora (o português continua sendo o texto-fonte)."""
        from . import i18n
        from .ui_i18n import translate_tree
        if code is not None:
            self.prefs['idioma'] = i18n.set_language(code)
            ui_prefs.save(self.prefs)
        translate_tree(self)
        for child in self.winfo_children():
            if isinstance(child, tk.Toplevel):
                translate_tree(child)
        self.nav.retranslate()
        if self._section:
            self._set_section_texts(ui_nav.BY_KEY[self._section])
        self._update_pending_label()
        self._refresh_frame_status()
        self.language_button.configure(text='A文 ' + i18n.LANGUAGES[i18n.language()].split(' ')[0].split('（')[0])

    def _apply_library_visibility(self):
        section = ui_nav.BY_KEY.get(self._section or 'inicio')
        wanted = bool(section and section.library and self.prefs.get('biblioteca_visivel', True))
        shown = self.library_shown()
        if wanted and not shown:
            self.outer.add(self.library, before=self.main_pane, width=self.prefs.get('largura_biblioteca', 327),
                           minsize=240, stretch='never')
        elif not wanted and shown:
            self._remember_library_width()
            self.outer.forget(self.library)

    def library_shown(self):
        return str(self.library) in [str(pane) for pane in self.outer.panes()]

    def _remember_library_width(self):
        try:
            if self.library_shown() and self.library.winfo_width() > 100:
                self.prefs['largura_biblioteca'] = int(self.library.winfo_width())
        except tk.TclError:
            pass

    def toggle_library(self):
        section = ui_nav.BY_KEY.get(self._section or 'inicio')
        if section and not section.library and not self.prefs.get('biblioteca_visivel', True):
            self.prefs['biblioteca_visivel'] = True
        elif section and not section.library:
            self.show_section('cartas')
            return
        else:
            self.prefs['biblioteca_visivel'] = not self.prefs.get('biblioteca_visivel', True)
        self._apply_library_visibility()

    def toggle_sidebar(self):
        self._auto_collapsed = False
        self.nav.set_collapsed(not self.nav.collapsed)

    def _sidebar_collapsed(self, collapsed):
        if not getattr(self, '_auto_collapsed', False):
            self.prefs['barra_recolhida'] = collapsed

    COMPACT_WIDTH = 1280

    def _on_resize(self, event):
        """Em janelas estreitas (ex.: 1024×768) o menu recolhe sozinho, sem mudar a preferência."""
        if event.widget is not self:
            return
        narrow = event.width < self.COMPACT_WIDTH
        if narrow == getattr(self, '_was_narrow', False):
            return                       # só age quando cruza o limite
        self._was_narrow = narrow
        if narrow and not self.nav.collapsed:
            self._auto_collapsed = True
            self.nav.set_collapsed(True)
        elif not narrow and getattr(self, '_auto_collapsed', False):
            self.nav.set_collapsed(bool(self.prefs.get('barra_recolhida')))
            self._auto_collapsed = False

    def go_back(self):
        key = self.history.go_back()
        if key:
            self._section = key
            self.show_section(key)
            self._after_history_jump(key)

    def go_forward(self):
        key = self.history.go_forward()
        if key:
            self._section = key
            self.show_section(key)
            self._after_history_jump(key)

    def _after_history_jump(self, key):
        # show_section não registra de novo no histórico (já é a seção atual).
        section = ui_nav.BY_KEY[key]
        self.nav.set_active(key)
        self._set_section_texts(section)
        self.back_button.configure(state='normal' if self.history.back else 'disabled')
        self.forward_button.configure(state='normal' if self.history.forward else 'disabled')
        if section.tab == 'tab_mod':
            self.mod_editor.show_duelist_header(key in ('deck', 'drops', 'iniciais', 'quests'))
        self._apply_library_visibility()
        if key == 'inicio':
            self._refresh_home()

    def open_palette(self):
        self.palette.open()

    def run_action(self, method):
        target = getattr(self, method, None) or getattr(self.mod_editor, method, None)
        if callable(target):
            target()

    def open_passwords(self):
        self.show_section('deck')
        self.mod_editor.open_passwords()

    def _copy_card_rows(self, _event=None):
        rows = []
        for item in self.tree.selection():
            values = self.tree.item(item, 'values')
            rows.append('\t'.join(str(v).strip() for v in values))
        if rows:
            self.clipboard_clear()
            self.clipboard_append('\n'.join(rows))
            self._update_status(f'{len(rows)} linha(s) copiada(s) da biblioteca.')
        return 'break'

    # ── painel inicial ──────────────────────────────────────────────────
    def _home_tab(self):
        from .ui_shell import Tooltip
        body = tk.Frame(self.tab_home, bg=BG, padx=22, pady=18)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=3, uniform='home')
        body.columnconfigure(1, weight=2, uniform='home')
        body.rowconfigure(1, weight=1)
        summary = tk.Frame(body, bg=SURFACE, padx=16, pady=14, highlightthickness=1, highlightbackground=BORDER)
        summary.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 12))
        self.home_title = tk.Label(summary, text='Nenhum projeto aberto', bg=SURFACE, fg=TEXT,
                                   font=('Segoe UI', 15, 'bold'))
        self.home_title.pack(anchor='w')
        self.home_details = tk.Label(summary, text='Crie um projeto novo ou abra um existente para começar.',
                                     bg=SURFACE, fg=MUTED, justify='left', anchor='w', wraplength=900)
        self.home_details.pack(anchor='w', pady=(4, 10))
        quick = tk.Frame(summary, bg=SURFACE)
        quick.pack(anchor='w')
        for text, command, style, tip in (
                ('＋ Novo projeto', self.new_project, 'TButton', 'Ctrl+N'),
                ('Abrir projeto…', self.open_project, 'TButton', 'Ctrl+O'),
                ('Importar BIN/CUE', self.import_bin, 'TButton', 'Lê cartas, textos e tabelas de uma cópia do jogo'),
                ('Gerar BIN/CUE', self.build_disc, 'Accent.TButton', 'Ctrl+B')):
            button = ttk.Button(quick, text=text, style=style, command=command)
            button.pack(side='left', padx=(0, 6))
            Tooltip(button, tip)

        recent = tk.Frame(body, bg=SURFACE, padx=14, pady=12, highlightthickness=1, highlightbackground=BORDER)
        recent.grid(row=1, column=0, sticky='nsew', padx=(0, 12))
        tk.Label(recent, text='PROJETOS RECENTES', bg=SURFACE, fg=ACCENT, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        tk.Label(recent, text='Clique duas vezes ou Enter para abrir.', bg=SURFACE, fg=MUTED,
                 font=('Segoe UI', 9)).pack(anchor='w', pady=(0, 6))
        holder = tk.Frame(recent, bg=SURFACE)
        holder.pack(fill='both', expand=True)
        self.recent_tree = ttk.Treeview(holder, columns=('nome', 'pasta'), show='headings', selectmode='browse', height=8)
        self.recent_tree.heading('nome', text='Projeto')
        self.recent_tree.heading('pasta', text='Pasta')
        self.recent_tree.column('nome', width=180, stretch=False)
        self.recent_tree.column('pasta', width=320, stretch=True)
        self.recent_tree.pack(side='left', fill='both', expand=True)
        recent_scroll = ttk.Scrollbar(holder, orient='vertical', command=self.recent_tree.yview)
        recent_scroll.pack(side='right', fill='y')
        self.recent_tree.configure(yscrollcommand=recent_scroll.set)
        self.recent_tree.bind('<Double-1>', lambda _e: self.open_recent())
        self.recent_tree.bind('<Return>', lambda _e: self.open_recent())
        self.recent_tree.bind('<Delete>', lambda _e: self.forget_recent())
        row = tk.Frame(recent, bg=SURFACE)
        row.pack(fill='x', pady=(8, 0))
        ttk.Button(row, text='Abrir selecionado', command=self.open_recent).pack(side='left')
        ttk.Button(row, text='Remover da lista', command=self.forget_recent).pack(side='left', padx=6)

        flow = tk.Frame(body, bg=SURFACE, padx=14, pady=12, highlightthickness=1, highlightbackground=BORDER)
        flow.grid(row=1, column=1, sticky='nsew')
        tk.Label(flow, text='FLUXO DE TRABALHO', bg=SURFACE, fg=ACCENT, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        for number, (label, key) in enumerate((
                ('Editar cartas (atributos, arte, descrição)', 'cartas'),
                ('Efeitos e bônus', 'efeitos'),
                ('Decks dos oponentes', 'deck'),
                ('Drops por duelista', 'drops'),
                ('Quests da campanha', 'quests'),
                ('Configurar o MOD (LP, IA, vitórias)', 'config'),
                ('Validar e gerar o BIN/CUE', 'exportar')), start=1):
            line = tk.Label(flow, text=f'{number}.  {label}  ›', bg=SURFACE, fg=TEXT, anchor='w',
                            cursor='hand2', pady=4)
            line.pack(fill='x')
            line.bind('<Button-1>', lambda _e, key=key: self.show_section(key))
            line.bind('<Enter>', lambda _e, w=line: w.configure(fg=ACCENT))
            line.bind('<Leave>', lambda _e, w=line: w.configure(fg=TEXT))
        tk.Label(flow, text='ATALHOS', bg=SURFACE, fg=ACCENT, font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(12, 2))
        keys = tk.Frame(flow, bg=SURFACE)
        keys.pack(anchor='w', fill='x')
        for row, (combo, text) in enumerate((
                ('Ctrl+K', 'buscar tela ou ação'), ('Ctrl+S', 'salvar projeto'),
                ('Ctrl+B', 'gerar BIN/CUE'), ('Ctrl+F', 'buscar carta'),
                ('Ctrl+1…6', 'cartas, efeitos, deck, drops, iniciais, quests'),
                ('Alt+← →', 'voltar / avançar'), ('Ctrl+L', 'mostrar/ocultar biblioteca'),
                ('Ctrl+\\', 'recolher o menu'),
                ('Ctrl+E', 'edição em lote (biblioteca)'))):
            tk.Label(keys, text=combo, bg=SURFACE, fg=TEXT, font=('Consolas', 9), anchor='w').grid(
                row=row, column=0, sticky='w', padx=(0, 10))
            tk.Label(keys, text=text, bg=SURFACE, fg=MUTED, font=('Segoe UI', 9), anchor='w').grid(
                row=row, column=1, sticky='w')

    def _refresh_home(self):
        if not hasattr(self, 'recent_tree'):
            return
        if self.project:
            pr = self.project
            pending = self.drafts.count if self.drafts else 0
            slus = (pr.folder/'base'/'source_SLUS_014.11').is_file()
            self.home_title.configure(text=pr.metadata.get('nome', 'Projeto'))
            self.home_details.configure(text=(
                f'{pr.folder}\n'
                f'{len(pr.cards)} cartas carregadas  ·  {len(pr.new_cards)} criadas  ·  {len(pr.edits)} alteradas e salvas  ·  '
                f'{pending} com alteração pendente\n'
                f'Base: {pr.metadata.get("base_source") or "não importada"}  ·  SLUS {"vinculado" if slus else "não vinculado"}'))
        else:
            self.home_title.configure(text='Nenhum projeto aberto')
            self.home_details.configure(text='Crie um projeto novo ou abra um existente para começar.')
        self.recent_tree.delete(*self.recent_tree.get_children())
        for folder in self.prefs.get('recentes', []):
            path = Path(folder)
            name = path.name
            try:
                import json
                name = json.loads((path/'projeto.json').read_text(encoding='utf-8')).get('nome') or name
            except (OSError, ValueError, AttributeError):
                name = f'{name} (não encontrado)'
            self.recent_tree.insert('', 'end', iid=folder, values=(name, folder))

    def open_recent(self):
        selection = self.recent_tree.selection()
        if selection:
            self.open_project(Path(selection[0]))

    def forget_recent(self):
        for folder in self.recent_tree.selection():
            ui_prefs.forget_project(self.prefs, folder)
        self._refresh_home()

    def _remember_project(self):
        if self.project:
            ui_prefs.remember_project(self.prefs, self.project.folder)
            ui_prefs.save(self.prefs)

    # ── edição em lote das cartas ───────────────────────────────────────
    def open_bulk_edit(self):
        if self._extract_running or not self._ensure_project() or not self.drafts:
            return
        ids = [int(cid) for cid in self.tree.selection()]
        if len(ids) < 2:
            messagebox.showinfo('Edição em lote', 'Selecione duas ou mais cartas na biblioteca '
                                '(Ctrl+clique, Shift+clique ou Ctrl+A).', parent=self)
            return
        self._stage_current()
        from .card_batch_gui import CardBatchDialog
        CardBatchDialog(self, ids)

    def open_translation(self):
        if self._extract_running or not self._ensure_project() or not self.drafts:
            return
        self._stage_current()
        from .translate_gui import TranslateDialog
        TranslateDialog(self, [int(cid) for cid in self.tree.selection()])

    def _after_translation(self, count, backup):
        self._refresh_cards()
        self._load_card()
        self._refresh_project()
        self._update_pending_label()
        self.notify(f'{count} descrição(ões) traduzida(s). Revise e salve o projeto (Ctrl+S). '
                    f'Originais guardados em {backup.name}.')

    def _after_batch(self, count):
        self._refresh_cards()
        self._load_card()
        self._refresh_project()
        self._update_pending_label()
        self.notify(f'{count} carta(s) alterada(s) em lote. Salve o projeto (Ctrl+S) para gravar.')

    # ── operações longas ────────────────────────────────────────────────
    def run_blocking(self, label, function, *args, **kwargs):
        """Executa ``function`` numa thread mantendo a janela redesenhando.

        A interface fica bloqueada para cliques (grab na barra de status) e
        mostra progresso indeterminado: a operação não informa porcentagem.
        Exceções são relançadas aqui, na thread da interface."""
        import time
        result = {}
        def worker():
            try:
                result['value'] = function(*args, **kwargs)
            except BaseException as exc:  # repassado para a thread da interface
                result['error'] = exc
        self._busy = label
        self.statusbar.begin(label)
        self.configure(cursor='watch')
        try:
            self.statusbar.grab_set()
        except tk.TclError:
            pass
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            while thread.is_alive():
                self.update()
                time.sleep(0.03)
        finally:
            try:
                self.statusbar.grab_release()
            except tk.TclError:
                pass
            self.configure(cursor='')
            self.statusbar.end()
            self._busy = None
        if 'error' in result:
            raise result['error']
        return result.get('value')

    def focus_catalog(self):
        if self.grab_current() is None:
            self.card_search.focus_set()
            self.card_search.selection_range(0, 'end')

    def _card_menu(self, event):
        item = self.tree.identify_row(event.y)
        if not item or self._extract_running:
            return
        if item not in self.tree.selection():
            self.tree.selection_set(item)
        self.tree.focus(item)
        self._on_card_select()
        try:
            self.card_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.card_menu.grab_release()

    def _select_visible_cards(self, _event=None):
        visible = self.tree.get_children()
        self.tree.selection_set(visible)
        return 'break'

    def _add_selected_to_deck(self):
        selected = [int(cid) for cid in self.tree.selection()]
        if selected:
            self.mod_editor.add_catalog_cards(selected)

    def _form_entry(self,parent,label,key,row,width=22,kind='text'):
        ttk.Label(parent,text=label).grid(row=row*2,column=0,sticky='w',padx=(0,12),pady=(9,2))
        if kind=='text':
            var=tk.StringVar()
            entry=ttk.Entry(parent,textvariable=var,width=width)
        else:
            choices={'type':TYPE_NAMES,'attr':ATTR_NAMES,'star':STAR_NAMES}[kind]
            vals=[f'{i:02d} — {guardian_name(i) if kind == "star" else v}'
                  for i,v in enumerate(choices) if kind != 'star' or i == 0 or v]
            var=tk.StringVar()
            entry=ttk.Combobox(parent,values=vals,state='readonly',width=width,textvariable=var)
            # Evita que a roda do mouse altere o tipo enquanto a aba rola.
            entry.bind('<MouseWheel>',lambda _event:'break')
            entry.bind('<Button-4>',lambda _event:'break')
            entry.bind('<Button-5>',lambda _event:'break')
        entry.grid(row=row*2+1,column=0,sticky='ew',padx=(0,12))
        self.vars[key]=var
        return entry

    def _cards_tab(self):
        shell=tk.Frame(self.tab_cards,bg=BG)
        shell.pack(fill='both',expand=True)
        scroll=ttk.Scrollbar(shell,orient='vertical')
        scroll.pack(side='right',fill='y')
        cv=tk.Canvas(shell,bg=BG,highlightthickness=0,yscrollcommand=scroll.set)
        cv.pack(side='left',fill='both',expand=True)
        scroll.configure(command=cv.yview)
        body=tk.Frame(cv,bg=BG,padx=19,pady=12)
        wid=cv.create_window((0,0),window=body,anchor='nw')
        body.bind('<Configure>',lambda evt:cv.configure(scrollregion=cv.bbox('all')))
        cv.bind('<Configure>',lambda evt:cv.itemconfigure(wid,width=evt.width))
        cv.bind('<Enter>',lambda evt:cv.bind_all('<MouseWheel>',lambda e:cv.yview_scroll(-1 if e.delta>0 else 1,'units')))
        cv.bind('<Leave>',lambda evt:cv.unbind_all('<MouseWheel>'))

        top=tk.Frame(body,bg=BG)
        top.pack(fill='x')
        self.preview = tk.Canvas(top,width=258,height=310,bg='#243454',highlightthickness=1,highlightbackground=BORDER)
        self.preview.pack(side='left',anchor='n',padx=(0,22))
        self.preview.create_rectangle(7,7,251,303,outline='#e0b962',width=3)
        self.preview_name=self.preview.create_text(129,35,text='NENHUMA CARTA',fill='#f1cf6e',font=('Segoe UI',12,'bold'),width=222)
        self.preview_name_plate=self.preview.create_rectangle(13,13,244,57,fill='#EAF0FA',outline='',state='hidden')
        self.preview.tag_lower(self.preview_name_plate,self.preview_name)
        self.preview.create_rectangle(22,64,236,202,fill='#111928',outline='#796d59')
        self.art_placeholder = self.preview.create_text(129,134,text='ARTE DA CARTA\n(NÃO IMPORTADA)',fill='#7589a9',font=('Segoe UI',10),justify='center')
        self.art_image = self.preview.create_image(129,134,image=None)
        self.preview_type=self.preview.create_text(140,222,text='TIPO • ATRIBUTO',fill=TEXT,font=('Segoe UI',9))
        self.preview_god_icon=self.preview.create_image(38,221,image=None,state='hidden')
        self.preview_stars=self.preview.create_text(129,244,text='',fill=TEXT,font=('Segoe UI',9),width=226)
        self.preview_stats=self.preview.create_text(129,278,text='ATK: —  DEF: —',fill=TEXT,font=('Segoe UI',11,'bold'),width=224)
        form=tk.Frame(top,bg=BG)
        form.pack(side='left',fill='both',expand=True)
        self.selected_caption=tk.Label(form,text='Selecione uma carta à esquerda',bg=BG,fg=ACCENT,font=('Segoe UI',12,'bold'))
        self.selected_caption.pack(anchor='w',pady=(0,10))
        grid=ttk.Frame(form)
        grid.pack(fill='x')
        grid.columnconfigure(0,weight=1)
        grid.columnconfigure(1,weight=1)
        basic=ttk.LabelFrame(grid,text='Dados básicos e tipo',padding=(9,0,0,10))
        combat=ttk.LabelFrame(grid,text='Status de combate',padding=(9,0,0,10))
        stars=ttk.LabelFrame(grid,text='Atributo e Guardian Stars',padding=(9,0,0,10))
        basic.grid(row=0,column=0,sticky='ew',padx=(0,6))
        combat.grid(row=1,column=0,sticky='ew',padx=(0,6),pady=(6,0))
        stars.grid(row=0,column=1,rowspan=2,sticky='nsew',padx=(6,0))
        for section in (basic,combat,stars):
            section.columnconfigure(0,weight=1)
        self._form_entry(basic,'Nome','nome',0,width=15)
        self._form_entry(basic,'Tipo','tipo_id',1,width=15,kind='type')
        self._form_entry(combat,'ATK','ataque',0,width=15)
        self._form_entry(combat,'DEF','defesa',1,width=15)
        self._form_entry(stars,'Atributo','atributo_id',0,width=15,kind='attr')
        self._form_entry(stars,'Nível (0 a 15)','nivel',1,width=15)
        self._form_entry(stars,'Guardian Star 1','guardian_1_id',2,width=15,kind='star')
        self._form_entry(stars,'Guardian Star 2','guardian_2_id',3,width=15,kind='star')
        self.card_type_warning=ttk.Label(form,text='',wraplength=380)
        self.card_type_warning.pack(anchor='w',pady=(7,0))
        color_line = tk.Frame(form,bg=BG)
        color_line.pack(fill='x',pady=(10,0))
        # cor_nome permanece no esquema para compatibilidade com projetos antigos;
        # o usuário agora seleciona uma classe, nunca digita uma cor RGB.
        self.vars['cor_nome'] = tk.StringVar(value=DEFAULT_NAME_COLOR)
        self.vars['raridade'] = tk.StringVar(value=f'{DEFAULT_RARITY} — {RARITIES[DEFAULT_RARITY][0]}')
        tk.Label(color_line,text='Raridade:',bg=BG,fg=TEXT).pack(side='left',padx=(0,8))
        self.rarity_combo=ttk.Combobox(color_line,values=rarity_options(),
                                      textvariable=self.vars['raridade'],state='readonly',width=22)
        self.rarity_combo.pack(side='left',padx=(0,8))
        self.rarity_combo.bind('<MouseWheel>',lambda _event:'break')
        self.color_sample=tk.Label(color_line,text='  ■  ',bg=BG,fg=RARITIES[DEFAULT_RARITY][1],
                                   font=('Segoe UI',13,'bold'))
        self.color_sample.pack(side='left')
        self.class_caption=tk.Label(form,text='Classe: Comum',bg=BG,fg=MUTED,font=('Segoe UI',9))
        self.class_caption.pack(anchor='w',pady=(5,0))
        ttk.Button(form,text='Importar imagem (PNG/JPG/WEBP/BMP)',command=self.import_art).pack(anchor='w',pady=(9,0))
        ttk.Button(form,text='Comparar original | PS1 (CLUT real)',command=self.preview_ps1_image).pack(anchor='w',pady=(3,0))
        links=ttk.LabelFrame(body,text='Efeitos e relações da carta',padding=8)
        links.pack(fill='x',pady=(10,4))
        ttk.Button(links,text='Efeitos e bônus',command=lambda:self.tabs.select(self.tab_effects)).pack(side='left',padx=(0,5))
        ttk.Button(links,text='Fusões, ritual e equipamentos',command=self.edit_card_rules).pack(side='left',padx=5)
        ttk.Button(links,text='Opções PS1',command=self.open_card_ps1_options).pack(side='right')
        tk.Label(body,text='Descrição da carta — salve o projeto e use Gerar jogo BIN/CUE para gravar no PS1',bg=BG,fg=TEXT,font=('Segoe UI',10)).pack(anchor='w',pady=(12,3))
        desc_tools=ttk.Frame(body)
        desc_tools.pack(fill='x',pady=(0,5))
        ttk.Button(desc_tools,text='Inserir ícone',command=self.choose_description_icon).pack(side='left',padx=(0,6))
        ttk.Button(desc_tools,text='Cor no trecho',command=self.choose_description_color).pack(side='left',padx=(0,6))
        ttk.Button(desc_tools,text='Referenciar carta',command=self.choose_description_reference).pack(side='left')
        ttk.Label(desc_tools,text='Altura (linhas):').pack(side='left',padx=(16,4))
        self.description_height=tk.IntVar(value=8)
        self.description_height_spin=ttk.Spinbox(desc_tools,from_=4,to=28,width=5,
            textvariable=self.description_height,command=self._resize_description)
        self.description_height_spin.pack(side='left')
        self.description_height_spin.bind('<Return>',lambda _event:self._resize_description())
        self.description_height_spin.bind('<FocusOut>',lambda _event:self._resize_description())
        edit_frame=ttk.Frame(body)
        edit_frame.pack(fill='x')
        self.description=tk.Text(edit_frame,height=8,wrap='word',bg=SURFACE,fg=TEXT,insertbackground=TEXT,
                                 selectbackground='#365a73',highlightthickness=1,highlightbackground=BORDER,font=('Segoe UI',11),undo=True)
        description_scroll=ttk.Scrollbar(edit_frame,orient='vertical',command=self.description.yview)
        self.description.configure(yscrollcommand=description_scroll.set)
        description_scroll.pack(side='right',fill='y')
        self.description.pack(side='left',fill='both',expand=True)
        tk.Label(body,text='PRÉVIA DA DESCRIÇÃO — cores e ícones (não é a renderização exata do PS1)',bg=BG,fg=MUTED,font=('Segoe UI',9)).pack(anchor='w',pady=(7,3))
        preview_frame=ttk.Frame(body)
        preview_frame.pack(fill='both',expand=True)
        self.description_preview=tk.Text(preview_frame,height=8,wrap='word',bg='#182339',fg=TEXT,
            highlightthickness=1,highlightbackground=BORDER,font=('Consolas',11),state='disabled',cursor='arrow')
        preview_scroll=ttk.Scrollbar(preview_frame,orient='vertical',command=self.description_preview.yview)
        self.description_preview.configure(yscrollcommand=preview_scroll.set)
        preview_scroll.pack(side='right',fill='y')
        self.description_preview.pack(side='left',fill='both',expand=True)
        buttons=ttk.Frame(body)
        buttons.pack(fill='x',pady=(12,0))
        ttk.Button(buttons,text='Salvar projeto (todas as cartas)',style='Accent.TButton',command=self.save_project).pack(side='left')
        ttk.Button(buttons,text='Restaurar os valores originais',command=self.reset_card).pack(side='left',padx=9)
        ttk.Button(buttons,text='Conferir descrições no BIN/CUE',command=self.verify_ps1_description_bin).pack(side='left',padx=9)
        tk.Label(buttons,text='Troque de carta livremente • Ctrl+S salva tudo',bg=BG,fg=MUTED,font=('Segoe UI',9)).pack(side='right')
        for variable in self.vars.values():
            variable.trace_add('write',lambda *_: self._on_card_field_input())
        for key in ('raridade','tipo_id'):
            self.vars[key].trace_add('write',lambda *_: self._on_class_changed())
        self.description.bind('<<Modified>>',self._on_description_modified)

    def _effects_tab(self):
        # O editor de efeitos precisa caber em janelas menores: layout rolável
        # (não ocultar botões de edição/simulação sob a borda inferior).
        shell=tk.Frame(self.tab_effects,bg=BG)
        shell.pack(fill='both',expand=True)
        scroll=ttk.Scrollbar(shell,orient='vertical')
        scroll.pack(side='right',fill='y')
        canvas=tk.Canvas(shell,bg=BG,highlightthickness=0,bd=0,
                         yscrollcommand=scroll.set)
        canvas.pack(side='left',fill='both',expand=True)
        scroll.configure(command=canvas.yview)
        body=tk.Frame(canvas,bg=BG,padx=22,pady=11)
        window=canvas.create_window((0,0),anchor='nw',window=body)
        body.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(window,width=event.width))
        canvas.bind('<Enter>',lambda event:canvas.bind_all('<MouseWheel>',
            lambda e: canvas.yview_scroll(-1 if e.delta>0 else 1,'units')))
        canvas.bind('<Leave>',lambda event:canvas.unbind_all('<MouseWheel>'))
        tk.Label(body,text='EFEITOS DAS CARTAS',bg=BG,fg=TEXT,font=('Segoe UI',16,'bold')).pack(anchor='w')
        tk.Label(body,text='O Drop x15 aceita bônus, habilidades rápidas, marcadores de ATK/DEF e efeitos de LP ao entrar em campo.',
                 bg=BG,fg='#edc47e',font=('Segoe UI',10),wraplength=780,justify='left').pack(anchor='w',pady=(8,12))
        self.effect_caption=tk.Label(body,text='Escolha uma carta',bg=BG,fg=ACCENT,font=('Segoe UI',12,'bold'))
        self.effect_caption.pack(anchor='w',pady=(0,8))
        quick=tk.LabelFrame(body,text=' HABILIDADES RÁPIDAS — marque e continue editando ',
                            bg=SURFACE,fg=ACCENT,padx=12,pady=10,font=('Segoe UI',10,'bold'),
                            highlightthickness=0)
        quick.pack(fill='x',pady=(0,6))
        self.quick_vars={}
        self._loading_quick=False
        line=tk.Frame(quick,bg=SURFACE);line.pack(fill='x',pady=(0,4))
        tk.Label(line,text='Ataques por turno:',bg=SURFACE,fg=TEXT).pack(side='left')
        self.quick_vars['ataques']=tk.IntVar(value=1)
        for n in (1,2,3):
            ttk.Radiobutton(line,text=f'{n}x',variable=self.quick_vars['ataques'],
                            value=n,command=self._on_quick_changed).pack(side='left',padx=(12,0))
        tk.Label(line,text='   Perde LP a cada ataque:',bg=SURFACE,fg=TEXT).pack(side='left',padx=(22,5))
        self.quick_vars['custo_lp']=tk.StringVar(value='0')
        validate=(self.register(lambda proposed: proposed == '' or
                                (proposed.isascii() and proposed.isdecimal())))
        ttk.Entry(line,width=9,textvariable=self.quick_vars['custo_lp'],
                  validate='key',validatecommand=(validate,'%P')).pack(side='left')
        self.quick_vars['custo_lp'].trace_add('write',lambda *_:self._on_quick_changed())
        copies=tk.Frame(quick,bg=SURFACE)
        copies.pack(fill='x',pady=4)
        tk.Label(copies,text='Limite de cópias no deck',bg=SURFACE,fg=TEXT).pack(side='left')
        self.quick_vars['limite_copias']=tk.StringVar()
        check_copies=(self.register(lambda value: value=='' or (value.isdigit() and len(value)<=2)))
        ttk.Entry(copies,width=5,textvariable=self.quick_vars['limite_copias'],
                  validate='key',validatecommand=(check_copies,'%P')).pack(side='left',padx=7)
        self.quick_vars['limite_copias'].trace_add('write',lambda *_:self._on_quick_changed())
        tk.Label(copies,text='0 bane a carta. Vazio usa o limite padrão. ∞ permite 40.',
                 bg=SURFACE,fg=MUTED).pack(side='left',padx=(10,0))
        rows=[tk.Frame(quick,bg=SURFACE) for _ in range(3)]
        for quick_row in rows: quick_row.pack(fill='x',pady=2)
        names={
            'monstro_indestrutivel':'Indestrutível',
            'monstro_imune_magia':'Imune a mágicas',
            'monstro_imune_armadilha':'Imune a traps',
            'dano_perfurante':'Dano perfurante',
            'nao_bloqueavel':'Não bloqueável',
            'sem_limite_deck':'Sem limite de cópias',
            'ataque_primeiro_turno':'Ataca no 1º turno',
        }
        for index,action in enumerate(BOOLEAN_ACTIONS):
            v=tk.BooleanVar(value=False)
            self.quick_vars[action]=v
            ttk.Checkbutton(rows[index // 3],text=names[action],variable=v,
                            command=self._on_quick_changed).pack(side='left',padx=(0,18))
        tk.Label(quick,text='Drop x15 aceita limites por carta de 1 a 40 cópias. O deck tem 40 espaços.',
                 bg=SURFACE,fg=MUTED,font=('Segoe UI',9)).pack(anchor='w',pady=(3,0))
        holder=tk.Frame(body,bg=SURFACE)
        holder.pack(fill='both',expand=True)
        self.effect_tree=ttk.Treeview(holder,columns=('evento','acao','alvo','tipo','atk','def'),show='headings',height=4)
        for key,label,w in [('evento','Quando',130),('acao','Efeito',205),('alvo','Alvo',135),
                                ('tipo','Filtro',155),('atk','ATK',70),('def','DEF',70)]:
            self.effect_tree.heading(key,text=label)
            self.effect_tree.column(key,width=w,stretch=True)
        self.sort_effects = sortable_columns(self.effect_tree)
        effects_scroll=ttk.Scrollbar(holder,orient='vertical',command=self.effect_tree.yview)
        self.effect_tree.configure(yscrollcommand=effects_scroll.set)
        effects_scroll.pack(side='right',fill='y')
        self.effect_tree.pack(side='left',fill='x',expand=True,padx=1,pady=1)
        self.effect_tree.bind('<Double-1>',lambda _event:self.edit_effect())
        self.effect_tree.bind('<Control-c>',lambda _event:self.copy_selected_effects())
        self.effect_tree.bind('<Control-v>',lambda _event:self.paste_effects())
        self.effect_tree.bind('<Button-3>',self._effects_context_menu)
        buttons=ttk.Frame(body)
        buttons.pack(fill='x',pady=12)
        effect_actions=ttk.Frame(buttons)
        effect_actions.pack(fill='x')
        ttk.Button(effect_actions,text='+ Adicionar efeito',style='Accent.TButton',
                   command=self.add_effect).pack(side='left')
        ttk.Button(effect_actions,text='+ Bônus por carta',
                   command=self.add_specific_effect).pack(side='left',padx=8)
        ttk.Button(effect_actions,text='Editar efeito selecionado',
                   command=self.edit_effect).pack(side='left',padx=8)
        ttk.Button(effect_actions,text='Remover efeito selecionado',
                   command=self.remove_effect).pack(side='left',padx=8)
        copy_row=ttk.Frame(buttons)
        copy_row.pack(fill='x',pady=(5,0))
        ttk.Button(copy_row,text='Copiar efeito(s) Ctrl+C',
                   command=self.copy_selected_effects).pack(side='left')
        ttk.Button(copy_row,text='Copiar todos os efeitos',
                   command=lambda:self.copy_selected_effects(all_effects=True)).pack(side='left',padx=6)
        ttk.Button(copy_row,text='Colar efeitos Ctrl+V',
                   command=self.paste_effects).pack(side='left',padx=6)
        ps1_actions=ttk.Frame(buttons)
        ps1_actions.pack(fill='x',pady=(6,0))
        ttk.Button(ps1_actions,text='PS1: permitir Equip em criatura',
                   command=self.allow_native_equip).pack(side='left')
        ttk.Button(ps1_actions,text='PS1: trocar alvo Equip',
                   command=self.replace_native_equip).pack(side='left',padx=8)
        ttk.Button(ps1_actions,text='PS1: usar adições automáticas',
                   command=self.activate_equip_additions).pack(side='left',padx=8)
        native=tk.Frame(body,bg=SURFACE,padx=12,pady=8)
        native.pack(fill='x',pady=(2,8))
        tk.Label(native,text='LABORATÓRIO DE EFEITOS INÉDITOS — PLAYSTATION 1',
                 bg=SURFACE,fg=ACCENT,font=('Segoe UI',9,'bold')).pack(anchor='w',pady=(0,5))
        row_native=ttk.Frame(native)
        row_native.pack(fill='x')
        ttk.Button(row_native,text='Diagnosticar motor MIPS',command=self.diagnose_effect_engine).pack(side='left')
        ttk.Button(row_native,text='Limite global de cópias no PS1',command=self.configure_ps1_deck_limit).pack(side='left',padx=8)
        tk.Label(native,text='LP dos dois duelistas: Edição do Mod → Config. MOD.',
                 bg=SURFACE,fg=MUTED).pack(anchor='w',pady=(6,0))
        tk.Label(native,text='Rituais retirados desta tela por enquanto. O diagnóstico identifica locais de cálculo de bônus, cemitério, proteção, combate e deck; não injeta habilidades não validadas.',
                 bg=SURFACE,fg=MUTED,wraplength=940,justify='left').pack(anchor='w',pady=(5,0))
        sim=tk.Frame(body,bg=SURFACE,padx=15,pady=12)
        sim.pack(fill='x')
        tk.Label(sim,text='SIMULADOR DE EFEITOS',bg=SURFACE,fg=TEXT,font=('Segoe UI',10,'bold')).pack(anchor='w')
        line=tk.Frame(sim,bg=SURFACE)
        line.pack(fill='x',pady=(8,6))
        self.sim_event=tk.StringVar(value=list(EVENTS)[0])
        self.sim_combo=ttk.Combobox(line,state='readonly',width=27,
                 values=[f'{x} — {EVENTS[x]}' for x in EVENTS])
        self.sim_combo.current(0)
        self.sim_combo.pack(side='left')
        ttk.Button(line,text='Simular gatilho',command=self.simulate).pack(side='left',padx=9)
        ttk.Button(line,text='Laboratório: campo, decks e equips',style='Accent.TButton',command=self.simulate_field).pack(side='left',padx=5)
        self.sim_result=tk.Label(sim,text='Simulação local: ATK/DEF e LP iniciais. Nenhum duelo é executado.',
                        bg=SURFACE,fg=MUTED,justify='left',anchor='w',font=('Segoe UI',9))
        self.sim_result.pack(fill='x')

    def _fusions_tab(self):
        body=tk.Frame(self.tab_fusions,bg=BG,padx=22,pady=20)
        body.pack(fill='both',expand=True)
        tk.Label(body,text='FUSÕES ORIGINAIS — SOMENTE LEITURA',bg=BG,fg=TEXT,font=('Segoe UI',16,'bold')).pack(anchor='w')
        tk.Label(body,text='Não editaremos receitas nesta fase. A base das fusões é preservada e verificada por SHA-256.',
                 bg=BG,fg=MUTED,font=('Segoe UI',10)).pack(anchor='w',pady=(8,12))
        self.fusion_title=tk.Label(body,text='Selecione uma carta para ver suas relações.',bg=BG,fg=ACCENT,font=('Segoe UI',11,'bold'))
        self.fusion_title.pack(anchor='w',pady=(0,10))
        self.fusion_tree=ttk.Treeview(body,columns=('a','b','result','glitch'),show='headings')
        for key,label,width in [('a','Material 1',160),('b','Material 2',160),('result','Resultado',160),('glitch','Leitura excedente?',170)]:
            self.fusion_tree.heading(key,text=label)
            self.fusion_tree.column(key,width=width)
        self.sort_fusions = sortable_columns(self.fusion_tree)
        self.fusion_tree.pack(fill='both',expand=True)
        self.fusion_footer=tk.Label(body,text='Base não importada.',bg=BG,fg=MUTED,font=('Segoe UI',9))
        self.fusion_footer.pack(anchor='w',pady=10)

    def _project_tab(self):
        body=tk.Frame(self.tab_proj,bg=BG,padx=22,pady=20)
        body.pack(fill='both',expand=True)
        tk.Label(body,text='PROJETO E EXPORTAÇÃO',bg=BG,fg=TEXT,font=('Segoe UI',16,'bold')).pack(anchor='w')
        tk.Label(body,text='Suas edições ficam em um projeto separado. Nunca alteramos o BIN original.',bg=BG,fg=MUTED,font=('Segoe UI',10)).pack(anchor='w',pady=(8,12))
        self.project_details=tk.Text(body,height=17,wrap='word',bg=SURFACE,fg=TEXT,insertbackground=TEXT,
                     font=('Consolas',10),highlightthickness=0,padx=12,pady=12,state='disabled')
        self.project_details.pack(fill='both',expand=True)
        buttons=ttk.Frame(body)
        buttons.pack(fill='x',pady=14)
        ttk.Button(buttons,text='Verificar integridade',command=self.verify).pack(side='left')
        ttk.Button(buttons,text='Exportar propostas e SLUS auxiliar',style='Accent.TButton',command=self.export).pack(side='left',padx=8)
        ttk.Button(buttons,text='Compatibilidade PS1',command=self.audit_ps1).pack(side='left',padx=8)
        ttk.Button(buttons,text='Gerar BIN/CUE de teste',command=self.build_disc).pack(side='left',padx=8)
        ttk.Button(buttons,text='Verificar BIN/CUE',command=self.verify_disc).pack(side='left',padx=8)
        graphics=ttk.LabelFrame(body,text='Otimização automática de imagens PS1',padding=8)
        graphics.pack(fill='x',pady=(0,8))
        self.ps1_opt_enabled=tk.BooleanVar(value=True)
        self.ps1_opt_mode=tk.StringVar(value='Automático (recomendado)')
        ttk.Checkbutton(graphics,text='ATIVADA',variable=self.ps1_opt_enabled).pack(side='left',padx=(0,12))
        ttk.Combobox(graphics,textvariable=self.ps1_opt_mode,state='readonly',width=24,
                     values=['Automático (recomendado)','Máxima fidelidade',
                             'Compatibilidade original','Personalizado']).pack(side='left',padx=4)
        ttk.Button(graphics,text='Salvar configuração',command=self.save_image_optimizer_settings).pack(side='left',padx=5)
        ttk.Button(graphics,text='Prévia real PS1 da carta selecionada',command=self.preview_ps1_image).pack(side='left',padx=5)
        diagnostic=ttk.Frame(body)
        diagnostic.pack(fill='x',pady=(0,6))
        ttk.Button(diagnostic,text='Diagnosticar Equip no BIN/CUE',command=self.diagnose_equip).pack(side='left')
        warning=tk.Label(body,text='IMPORTANTE: SLUS auxiliar ≠ BIN jogável. Gere um BIN/CUE novo depois de salvar efeitos.\n'
                 'No perfil Drop x15, apenas os efeitos suportados pelo relatório são aplicados ao PS1. Verifique o BIN/CUE e teste no ePSXe.',
                 bg=BG,fg='#edc47e',font=('Segoe UI',10),justify='left',wraplength=750)
        warning.pack(anchor='w',pady=(8,0))
        # Em janelas baixas o painel de texto encolhe; os botões ficam visíveis.
        from .ui_shell import pin_bottom
        for widget, options in ((buttons, {'pady': 14}), (graphics, {'pady': (0, 8)}),
                                (diagnostic, {'pady': (0, 6)}), (warning, {'pady': (8, 0), 'fill': 'none', 'anchor': 'w'})):
            pin_bottom(widget, **options)

    def _extract_tab(self):
        body=tk.Frame(self.tab_extract,bg=BG,padx=22,pady=18)
        body.pack(fill='both',expand=True)
        tk.Label(body,text='EXTRAÇÃO AVANÇADA DO DISCO',bg=BG,fg=TEXT,font=('Segoe UI',16,'bold')).pack(anchor='w')
        tk.Label(body,text='Extrai nomes, descrições, diálogos, artes, miniaturas, retratos e cruza dados já encontrados. '
                 'Lê apenas sua cópia local do jogo; não grava na imagem BIN/CUE.',bg=BG,fg=MUTED,
                 wraplength=860,justify='left').pack(anchor='w',pady=(6,15))
        commandrow=ttk.Frame(body)
        commandrow.pack(fill='x',pady=(0,12))
        ttk.Button(commandrow,text='Extrair tudo do BIN/CUE ou da pasta',style='Accent.TButton',
                   command=self.extract_max).pack(side='left')
        ttk.Button(commandrow,text='Abrir pasta dos dados extraídos',command=self.open_extract_folder).pack(side='left',padx=9)
        self.extract_progress=tk.StringVar(value='Nenhuma extração completa realizada neste projeto.')
        tk.Label(body,textvariable=self.extract_progress,bg=BG,fg=ACCENT,anchor='w',
                 wraplength=860,justify='left').pack(anchor='w',pady=(0,12))
        self.extract_details=tk.Text(body,wrap='word',bg=SURFACE,fg=TEXT,insertbackground=TEXT,
                     font=('Consolas',10),highlightthickness=0,padx=14,pady=14,state='disabled')
        self.extract_details.pack(fill='both',expand=True)
        tk.Label(body,text='Atenção: os registros de texto com comandos ramificados podem exigir revisão manual. '
                 'A extração não habilita novos efeitos no motor PS1.',bg=BG,fg='#edc47e',
                 wraplength=880,justify='left').pack(anchor='w',pady=(9,0))

    def open_extract_folder(self):
        if not self._ensure_project():return
        folder=self.project.folder/'base'/'extracao_completa'
        if not folder.is_dir():
            messagebox.showinfo('Sem extração','Execute Extrair máximo primeiro.',parent=self)
            return
        try:
            if sys.platform=='win32':os.startfile(str(folder))
            else:messagebox.showinfo('Local dos arquivos',str(folder),parent=self)
        except OSError as exc:
            messagebox.showerror('Não foi possível abrir a pasta',str(exc),parent=self)

    def extract_max(self):
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve primeiro','Clique Salvar projeto antes de iniciar a extração.',parent=self)
            return
        if not self._ensure_project() or self._extract_running:return
        if not self._confirm_switch():return
        answer=messagebox.askyesnocancel('Origem para extração completa',
            'Deseja selecionar a imagem BIN/CUE do jogo?\n\n'
            'SIM: escolher imagem .BIN/.CUE/.ISO\n'
            'NÃO: escolher pasta que contém SLUS_014.11 e DATA/WA_MRG.MRG\n\n'
            'O programa não modificará os arquivos de origem.',parent=self)
        if answer is None:return
        if answer:
            origin=filedialog.askopenfilename(title='Escolha a imagem BIN/CUE usada neste projeto',
                       filetypes=[('Imagem PlayStation','*.bin *.cue *.iso'),('Todos arquivos','*.*')])
        else:
            origin=filedialog.askdirectory(title='Pasta com SLUS_014.11 e DATA/WA_MRG.MRG')
        if not origin:return
        self._extract_running=True
        self.extract_progress.set('Iniciando extração completa...')
        self._update_status('Extração em andamento. A janela continuará disponível.')
        self.tabs.select(self.tab_extract)
        def worker():
            try:
                report=self.project.extract_complete(Path(origin), progress=lambda t:self._extract_messages.put(('progress',t)))
                self._extract_messages.put(('ok',report))
            except Exception as exc:
                self._extract_messages.put(('error',f'{type(exc).__name__}: {exc}'))
        threading.Thread(target=worker,daemon=True).start()
        self.after(150,self._poll_extract)

    def _poll_extract(self):
        done=False
        while True:
            try:kind,obj=self._extract_messages.get_nowait()
            except queue.Empty:break
            if kind=='progress':
                self.extract_progress.set(obj)
                self._update_status(obj)
            elif kind=='ok':
                done=True
                self._extract_running=False
                metric=obj['textos'];art=obj['visuais']
                self.extract_progress.set(f'Concluído: {metric["nomes_cartas"]} nomes, {metric["descricoes_cartas"]} descrições, '
                              f'{art["artes"]} artes e {art["retratos"]} retratos.')
                self._refresh_all()
                self._refresh_extract()
                self.tabs.select(self.tab_extract)
                self._update_status('Extração concluída. Dados e imagens carregados no projeto.')
                messagebox.showinfo('Extração concluída',
                  'Nomes, descrições e recursos visuais extraídos. Consulte Dados extraídos e o relatório completo.\n\n'
                  'Fusões continuam intocadas e efeitos continuam apenas simulados.',parent=self)
            elif kind=='error':
                done=True;self._extract_running=False
                self.extract_progress.set('Extração não concluída: '+str(obj))
                messagebox.showerror('Falha na extração',obj,parent=self)
        if not done:self.after(150,self._poll_extract)

    def _refresh_extract(self):
        pane=self.extract_details
        pane.configure(state='normal');pane.delete('1.0','end')
        txt='Nenhuma extração completa neste projeto. Use o botão Extrair máximo.'
        if self.project:
            file=self.project.folder/'base'/'extracao_completa'/'relatorio_completo.json'
            if file.is_file():
                try:
                    import json
                    r=json.loads(file.read_text(encoding='utf-8'))
                    m=r.get('textos',{});v=r.get('visuais',{})
                    txt=(f'ORIGEM: {r.get("fonte",{}).get("local", "desconhecida")}\n\n'
                         f'NOMES DE CARTAS: {m.get("nomes_cartas",0)}/722\n'
                         f'DESCRIÇÕES: {m.get("descricoes_cartas",0)}/722\n'
                         f'TEXTOS (tabela de nomes): {m.get("strings_nomes",0)}\n'
                         f'TEXTOS (descrições, inclusive reservadas): {m.get("strings_descricoes",0)}\n'
                         f'MENUS / DIÁLOGOS: {m.get("strings_menu_historia",0)}\n\n'
                         f'ARTES: {v.get("artes",0)}/722\n'
                         f'MINIATURAS: {v.get("miniaturas",0)}/722\n'
                         f'FAIXAS VISUAIS: {v.get("faixas",0)}\n'
                         f'RETRATOS: {v.get("retratos",0)}\n'
                         f'CENAS DA HISTÓRIA: {v.get("cenas_historia",0)}\n\n'
                         f'PASTA: {file.parent}\n\nARQUIVOS GERADOS:\n')
                    for f in sorted(file.parent.glob('*.csv')):txt+=f' • {f.name}\n'
                    txt+=' • visuais/ (PNG de cartas, miniaturas, retratos)\n'
                    txt+=' • manifesto_imagens.json\n • relatorio_completo.json\n\n'
                    txt+=f'AVISOS: {len(r.get("avisos",[]))}\n'
                    for note in r.get('avisos',[])[:15]:txt+=f' • {note}\n'
                    txt+='\nIMPORTANTE: textos com {f8 ...} e marcas {jump ...} são registros técnicos e não uma tradução final.\n'
                except (ValueError,OSError) as e:txt=f'Erro ao ler relatório: {e}'
        pane.insert('1.0',txt);pane.configure(state='disabled')

    def _update_status(self,text):
        from . import i18n
        self.status.set(i18n.t(text))
        self.update_idletasks()

    def notify(self, text):
        self._update_status(text)
        if self._toast_timeout is not None:
            self.after_cancel(self._toast_timeout)
        self.toast.configure(text=self.status.get())
        self.toast.place(relx=1, rely=1, x=-16, y=-46, anchor='se')
        self.toast.lift()
        self._toast_timeout = self.after(3300, self._hide_toast)

    def _hide_toast(self):
        self.toast.place_forget()
        self._toast_timeout = None

    def _ensure_project(self):
        if not self.project:
            messagebox.showinfo('Projeto necessário','Crie ou abra um projeto primeiro.')
            return False
        return True

    def new_project(self):
        if self._extract_running:
            messagebox.showinfo("Extração em andamento","Conclua a extração antes de editar, importar ou trocar de projeto.",parent=self)
            return False
        if not self._confirm_switch():
            return
        name=simpledialog.askstring('Novo projeto','Nome do seu MOD:',initialvalue='Meu Forbidden Memories MOD',parent=self)
        if not name:
            return
        parent=filedialog.askdirectory(title='Onde criar o projeto?',initialdir=str(Path.home()))
        if not parent:
            return
        safe=re.sub(r'[^A-Za-z0-9_-]+','_',name.strip())[:65] or 'Novo_MOD'
        folder=Path(parent)/safe
        try:
            self.project=Project.create(folder,name)
        except (OSError,ModError,ValueError) as exc:
            messagebox.showerror('Falha ao criar projeto',str(exc))
            return
        self.drafts=DraftSession(self.project)
        self.selected_id=None
        self._remember_project()
        self._refresh_all()
        self._update_status('Projeto criado. Importe analysis\\tabelas ou selecione a imagem .BIN/.CUE.')

    def open_project(self, folder=None):
        if self._extract_running:
            messagebox.showinfo("Extração em andamento","Conclua a extração antes de editar, importar ou trocar de projeto.",parent=self)
            return False
        if not self._confirm_switch():
            return
        if folder is None:
            folder=filedialog.askdirectory(title='Selecione a pasta com projeto.json')
        if not folder:
            return
        try:
            self.project=Project.open(Path(folder))
        except (OSError,ModError,ValueError,KeyError) as exc:
            messagebox.showerror('Falha ao abrir projeto',str(exc))
            return
        self.drafts=DraftSession(self.project)
        self.selected_id=None
        self._remember_project()
        self._refresh_all()
        self._update_status('Projeto aberto: '+self.project.metadata['nome'])

    def import_csv(self):
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve primeiro','Salve o projeto antes desta operação.',parent=self)
            return

        if self._extract_running:
            messagebox.showinfo("Extração em andamento","Conclua a extração antes de editar, importar ou trocar de projeto.",parent=self)
            return False
        if not self._ensure_project():
            return
        folder=filedialog.askdirectory(title='Selecione a pasta com cartas.csv e fusoes.csv')
        if not folder:
            return
        try:
            self.project.import_tables(Path(folder))
        except (OSError,ModError,ValueError,KeyError) as exc:
            messagebox.showerror('Importação inválida',str(exc))
            return
        self._refresh_all()
        self._update_status('Tabelas importadas: 722 cartas. Fusões originais mantidas e bloqueadas.')

    def import_bin(self):
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve primeiro','Salve o projeto antes desta operação.',parent=self)
            return

        if self._extract_running:
            messagebox.showinfo("Extração em andamento","Conclua a extração antes de editar, importar ou trocar de projeto.",parent=self)
            return False
        if not self._ensure_project():
            return
        has_original = any(cid <= CARD_COUNT and not card.get('virtual') for cid, card in self.project.cards.items())
        if has_original and (self.project.edits or self.project.effects):
            messagebox.showinfo(
                'Projeto editado — não reimporte o jogo',
                'Seu projeto já possui alterações salvas. Reimportar a imagem substituiria '
                'a base das cartas, por isso foi bloqueado para proteger seu trabalho.\n\n'
                'Para TESTAR no ePSXe, clique em Gerar jogo BIN/CUE (na barra superior), '
                'selecione a MESMA imagem de origem e confirme.\n\n'
                'Para iniciar uma base diferente, crie um NOVO projeto.',
                parent=self)
            self._update_status('Base mantida: use Gerar jogo BIN/CUE para criar a cópia de teste.')
            return
        path=filedialog.askopenfilename(title='Imagem original ou mod (.bin/.cue/.iso)',filetypes=[('Disco PS1','*.bin *.cue *.iso'),('Todos arquivos','*.*')])
        if not path:
            return
        try:
            self._update_status('Analisando imagem e extraindo as tabelas. Os arquivos originais não serão alterados...')
            self.project.import_disc(Path(path))
        except (OSError,ModError,DiscError,ValueError,IndexError) as exc:
            messagebox.showerror('Falha ao importar imagem',str(exc))
            self._update_status('Importação não concluída')
            return
        self._refresh_all()
        self._update_status('Importação direta do disco concluída. Conferir avisos na aba Projeto.')

    def attach_slus(self):
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve primeiro','Salve o projeto antes desta operação.',parent=self)
            return

        if self._extract_running:
            messagebox.showinfo("Extração em andamento","Conclua a extração antes de editar, importar ou trocar de projeto.",parent=self)
            return False
        if not self._ensure_project():
            return
        if not self.project.cards:
            messagebox.showinfo('Faltam tabelas','Importe primeiro suas tabelas para validar o executável.')
            return
        path=filedialog.askopenfilename(title='Escolha SLUS_014.11 da MESMA imagem usada na extração')
        if not path:
            return
        try:
            self.project.attach_executable(Path(path))
        except (OSError,ModError,ValueError,KeyError) as exc:
            messagebox.showerror('SLUS incompatível',str(exc))
            return
        self._update_status('SLUS vinculado após verificar os 722 registros da tabela de estatísticas.')
        self._refresh_project()

    def _confirm_switch(self):
        """Só confirma ao sair/trocar DE PROJETO, nunca ao trocar de carta."""
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            return messagebox.askyesno('Descartar alterações pendentes?',
                f'Você tem {self.drafts.count} carta(s) com alterações não salvas.\n\n'
                'Clique NÃO para voltar e usar Salvar projeto.\n'
                'Clique SIM para descartar as alterações pendentes.',parent=self)
        return True

    def _stage_current(self):
        if self._loading or not self.drafts or not self.selected_id:
            return
        self.drafts.stage_card(self.selected_id,self._collect_form())

    def _form_changed(self):
        self._stage_current()
        return bool(self.drafts and self.selected_id in self.drafts.cards)

    def _update_pending_label(self):
        count = self.drafts.count if self.drafts else 0
        if hasattr(self, 'statusbar'):
            self.statusbar.set_saved(count, has_project=bool(self.project))
            self.title(('● ' if count else '') + self._window_title())
        if hasattr(self, 'pending_label'):
            self.pending_label.configure(text=(f'● {count} carta(s) pendente(s) • clique Salvar projeto'
                if count else '✓ Todas as edições salvas'),fg=('#edc47e' if count else ACCENT))

    def _current_name_style(self):
        try:
            typ=int(self.vars['tipo_id'].get().split(' — ',1)[0])
            rarity=self.vars['raridade'].get().split(' — ',1)[0]
            return name_style({'tipo_id':typ,'raridade':rarity})
        except (ValueError,KeyError):
            return name_style({'tipo_id':0,'raridade':DEFAULT_RARITY})

    def _apply_name_color_preview(self):
        label,color,kind=self._current_name_style()
        self.color_sample.configure(fg=color,bg='#ECF1FA' if kind=='deus' else BG)
        self.class_caption.configure(text=f'Classe: {label}  •  {color}',fg=MUTED)
        # O azul-marinho não fica legível no fundo escuro do cartão.
        self.preview.itemconfigure(self.preview_name_plate,state='normal' if kind=='deus' else 'hidden')
        god_image=self.get_icon_image('god') if kind=='deus' else None
        self.preview.itemconfigure(self.preview_god_icon,
            image=god_image if god_image else '',
            state='normal' if god_image else 'hidden')
        self.preview.itemconfigure(self.preview_name,
            text=(self.vars['nome'].get() or format_id(self.selected_id))[:42].upper(),fill=color)
        self.rarity_combo.configure(state='disabled' if kind in ('trap','magica','equip') or
                                    int(self.vars['tipo_id'].get().split(' — ',1)[0])==24
                                    else 'readonly')
        return label,color,kind

    def _on_class_changed(self):
        if self._loading or not self.drafts or not self.selected_id:
            return
        _label,color,_kind=self._current_name_style()
        self._update_card_type_warning()
        # O campo legado fica sincronizado quando a classe/tipo for alterado.
        if self.vars['cor_nome'].get() != color:
            self.vars['cor_nome'].set(color)
        self._on_card_field_input()

    def _update_card_type_warning(self):
        if not getattr(self,'selected_id',None) or not hasattr(self,'card_type_warning'):
            return
        try:
            typ=int(self.vars['tipo_id'].get().split(' — ',1)[0])
            if typ==GOD_TYPE_ID:
                if self.selected_id<=CARD_COUNT and ps1_supports_god24(self.project):
                    msg='God (24) será exportado como monstro com nome e ícone do tipo.'
                else:
                    msg='God (24) no BIN/CUE requer uma carta original e o perfil Drop x15.'
            elif typ>GOD_TYPE_ID:
                msg='Tipo desconhecido: ainda sem suporte de exportação PS1.'
            elif 20<=typ<=23:
                msg=('Este é um tipo de magia, armadilha, ritual ou equipamento. '
                     'Para jogar como monstro, selecione um tipo de monstro ou God (24).')
            elif 0<=typ<20:
                msg=('Tipo de monstro escolhido será exportado no PS1. '
                     'A classe visual Deus é configurada pela raridade.')
            else:
                msg='Tipo não reconhecido.'
            self.card_type_warning.configure(text=msg)
        except (ValueError,KeyError):
            self.card_type_warning.configure(text='Verifique o tipo da carta.')

    def _on_card_field_input(self):
        if self._loading or not self.drafts or not self.selected_id:
            return
        self._stage_current()
        _label,color,kind=self._apply_name_color_preview()
        self._preview_values(self.drafts.get_card(self.selected_id))
        # Atualização leve da linha (sem recriar a Treeview durante digitação).
        iid=str(self.selected_id)
        if self.tree.exists(iid):
            row=self.drafts.get_card(self.selected_id)
            tag=f'classe_{kind}'
            self.tree.tag_configure(tag,foreground=color,
                                    background='#EAF0FA' if kind=='deus' else SURFACE)
            self.tree.item(iid,values=(f'{self.selected_id:03d}',
                 (row.get('nome') or '(nome não extraído)') + (' •' if self.selected_id in self.drafts.cards else ''),
                 compact_number(row.get('ataque',''),8),compact_number(row.get('defesa',''),8)),tags=(tag,))
        self._update_pending_label()

    def _on_description_modified(self, _evt=None):
        if self.description.edit_modified():
            self.description.edit_modified(False)
            self._on_card_field_input()
            self.render_description()

    def _collect_form(self):
        data={}
        for key in FIELDS:
            if key=='descricao':
                data[key]=self.description.get('1.0','end-1c')
            elif key=='raridade':
                data[key]=self.vars[key].get().split(' — ',1)[0]
            elif key in ('tipo_id','atributo_id','guardian_1_id','guardian_2_id'):
                data[key]=self.vars[key].get().split(' — ',1)[0]
            else:
                data[key]=self.vars[key].get()
        return data

    def _card_sort_value(self, item, field):
        cid = int(item)
        if field == 'id':
            return cid
        row = self.drafts.get_card(cid) if self.drafts else self.project.get(cid)
        return row[{'atk': 'ataque', 'def': 'defesa', 'nome': 'nome'}[field]]

    def _refresh_cards(self):
        keep = self.tree.selection()
        active = str(self.selected_id) if self.selected_id else None
        top = self.tree.yview()[0]
        self.tree.delete(*self.tree.get_children())
        if not self.project or not self.project.cards:
            self.count_label.configure(text='Nenhuma carta importada')
            return
        q=search_text(self.filter.get()).strip()
        type_filter=self.filter_type.get()
        star_filter=self.filter_star.get()
        try:
            first=int(self.filter_from.get()) if self.filter_from.get().strip() else 1
            last=int(self.filter_to.get()) if self.filter_to.get().strip() else None
            if first < 1 or last is not None and last < first:
                raise ValueError
        except ValueError:
            self.count_label.configure(text='Informe uma faixa de IDs válida.')
            return
        count=0
        for cid in sorted(self.project.cards):
            if cid < first or last is not None and cid > last:
                continue
            c=self.drafts.get_card(cid) if self.drafts else self.project.get(cid)
            title=c.get('nome') or '(nome não extraído)'
            if not card_matches(q, cid, c):
                continue
            typ=int(c['tipo_id'])
            if type_filter=='Monstros' and not (typ<20 or typ==24):
                continue
            if ' — ' in type_filter and typ!=int(type_filter.split(' — ',1)[0]):
                continue
            if ' — ' in star_filter and int(star_filter.split(' — ',1)[0]) not in (
                    int(c['guardian_1_id']),int(c['guardian_2_id'])):
                continue
            flag=' •' if self.drafts and cid in self.drafts.cards else (' ✎' if str(cid) in self.project.edits else '')
            self.tree.insert('','end',iid=str(cid),values=(compact_number(f'{cid:03d}', 7),title+flag,
                compact_number(c['ataque'],8),compact_number(c['defesa'],8)),tags=card_row_tags(self.tree, c, count))
            count+=1
        self.sort_cards()
        self.count_label.configure(text=f'{count} cartas exibidas  •  {len(self.project.cards)} carregadas')
        valid = [cid for cid in keep if self.tree.exists(cid)]
        if valid:
            self.tree.selection_set(valid)
        elif active and self.tree.exists(active):
            self.tree.selection_set(active)
        self.tree.yview_moveto(top)
        self._update_pending_label()

    def _on_card_select(self,evt=None):
        selection=self.tree.selection()
        if not selection or not self.project:
            return
        cid=int(selection[0])
        if cid==self.selected_id:
            return
        # Armazena o formulário em memória, mesmo com campos incompletos.
        self._stage_current()
        self.selected_id=cid
        self._load_card()
        self._update_pending_label()

    def _load_card(self):
        if not self.project or not self.selected_id:
            return
        c=self.drafts.get_card(self.selected_id) if self.drafts else self.project.get(self.selected_id)
        self._loading=True
        for key in FIELDS:
            if key=='raridade':
                rarity=c.get(key,DEFAULT_RARITY)
                self.vars[key].set(f'{rarity} — {RARITIES[rarity][0]}')
            elif key=='descricao':
                self.description.delete('1.0','end')
                self.description.insert('1.0',c.get(key,'') or '')
            elif key in ('tipo_id','atributo_id','guardian_1_id','guardian_2_id'):
                lookup={'tipo_id':TYPE_NAMES,'atributo_id':ATTR_NAMES,'guardian_1_id':STAR_NAMES,'guardian_2_id':STAR_NAMES}[key]
                n=int(c[key])
                label=guardian_name(n) if key.startswith('guardian_') else lookup[n] if n<len(lookup) else '(não mapeado)'
                self.vars[key].set(f'{n:02d} — {label}')
            else:
                self.vars[key].set(str(c.get(key,'')))
        self.description.edit_modified(False)
        self._loading=False
        self._update_card_type_warning()
        _label,color,_kind=self._apply_name_color_preview()
        ident=format_id(self.selected_id)
        self.selected_caption.configure(text=f'{ident}  {c.get("nome") or "Nome ainda não extraído"}')
        self.preview.itemconfigure(self.preview_name,text=(c.get('nome') or ident)[:42].upper(),fill=color)
        self._preview_values(c)
        self._load_art()
        self.render_description()
        self._refresh_effects()
        self._refresh_fusions()
        self._update_status(f'Carta {ident} selecionada • alterações pendentes na memória até Salvar projeto')

    def _preview_values(self, card):
        typ, attr = int(card['tipo_id']), int(card['atributo_id'])
        type_name = TYPE_NAMES[typ] if typ<len(TYPE_NAMES) else 'Tipo reservado'
        attribute = ATTR_NAMES[attr] if attr<len(ATTR_NAMES) else 'Atributo reservado'
        self.preview.itemconfigure(self.preview_type,text=f'{type_name} • {attribute}')
        stars = tuple(dict.fromkeys(int(card[key]) for key in ('guardian_1_id','guardian_2_id')))
        self.preview.itemconfigure(self.preview_stars,text=' · '.join(guardian_name(star) for star in stars if star),
                                   fill=SUPREME_COLOR if SUPREME in stars else TEXT)
        self.preview.itemconfigure(self.preview_stats,text=(
            f'ATK {compact_number(card["ataque"],11)}  DEF {compact_number(card["defesa"],11)}'))

    def _load_art(self):
        self.preview_img = None
        self.preview.itemconfigure(self.art_image,image='')
        self.preview.itemconfigure(self.art_placeholder,state='normal')
        if not self.project or not self.selected_id:
            return
        path = self.project.art_path(self.selected_id)
        if path is None:
            return
        try:
            img = tk.PhotoImage(file=str(path))
            factor = max(1, (img.width()+207)//208, (img.height()+131)//132)
            self.preview_img = img.subsample(factor,factor) if factor > 1 else img
            self.preview.itemconfigure(self.art_image,image=self.preview_img)
            self.preview.itemconfigure(self.art_placeholder,state='hidden')
        except (OSError,tk.TclError):
            self.preview.itemconfigure(self.art_placeholder,text='ARTE INDISPONÍVEL')

    def preview_ps1_image(self):
        if not self.project or not self.selected_id:
            messagebox.showinfo('Otimização PS1','Selecione uma carta e importe sua imagem.',parent=self)
            return
        try:
            from .ps1_image_preview import ImageOptimizerDialog
            ImageOptimizerDialog(self,self.project,self.selected_id)
        except (OSError,ValueError,ModError,DiscError,tk.TclError) as exc:
            messagebox.showerror('Prévia PS1 indisponível',str(exc),parent=self)

    def save_image_optimizer_settings(self):
        if not self._ensure_project():
            return
        from .ps1_image_optimizer import ImageOptions
        from dataclasses import asdict
        names={'Automático (recomendado)':'automatico',
               'Máxima fidelidade':'maxima_fidelidade',
               'Compatibilidade original':'compatibilidade',
               'Personalizado':'personalizado'}
        data=asdict(ImageOptions.from_mapping(
            self.project.metadata.get('ps1_image_optimizer')))
        data.update(enabled=bool(self.ps1_opt_enabled.get()),
                    mode=names[self.ps1_opt_mode.get()])
        try:
            ImageOptions.from_mapping(data)
            self.project.metadata['ps1_image_optimizer']=data
            self.project.save()
        except (ValueError,KeyError,OSError,ModError) as exc:
            messagebox.showerror('Otimização PS1',str(exc),parent=self)
            return
        self.notify('Configuração de imagens PS1 salva. Próximo BIN usará este perfil.')
        self._refresh_project()

    def import_art(self):
        if not self.project or not self.selected_id:
            messagebox.showinfo('Selecione uma carta','Escolha uma carta primeiro.')
            return
        path = filedialog.askopenfilename(title='Escolha uma imagem',filetypes=[('Imagens','*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff')])
        if not path:
            return
        try:
            self.project.attach_art(self.selected_id,Path(path))
        except (OSError,ModError) as exc:
            messagebox.showerror('Não foi possível importar arte',str(exc))
            return
        self._load_art()
        self._refresh_project()
        self._update_status('Arte PNG vinculada como prévia local; ainda não foi gravada no jogo.')

    def save_card(self):
        """Compatibilidade com atalhos antigos; salva todas as cartas de uma vez."""
        return self.save_project()

    def save_project(self):
        if self._extract_running:
            messagebox.showinfo('Extração em andamento','Conclua a extração antes de salvar.',parent=self)
            return False
        if not self._ensure_project() or not self.drafts:
            return False
        self._stage_current()
        if not self.drafts.is_dirty:
            self._update_status('Nenhuma alteração pendente para salvar.')
            return True
        try:
            count=self.drafts.save()
        except (ModError,ValueError,OSError) as exc:
            messagebox.showerror('Não foi possível salvar o projeto',
                                 f'{exc}\n\nAs alterações continuam pendentes para correção.',parent=self)
            return False
        self._refresh_cards()
        self._load_card()
        self._refresh_project()
        self.mod_editor.refresh_catalog()
        self._update_pending_label()
        self.notify(f'Projeto salvo. {count} carta(s) atualizada(s).')
        return True

    def toggle_god_icon_ps1(self):
        """Configura o glifo Deus na descrição de um monstro original."""
        if not self._ready_native_effect() or not self.selected_id:
            return
        cid=int(self.selected_id)
        current=legacy_god_description_icon_card(self.project)
        if current==cid:
            if not messagebox.askyesno(
                    'Desativar teste de ícone Deus',
                    'Desativar teste visual do símbolo Deus no próximo BIN/CUE? '
                    'Não altera o último disco já gerado.', parent=self):
                return
            self.project.metadata.pop('ps1_god_icon_test_card_id',None)
            self.project.save()
            self._refresh_project()
            self._update_status('Teste de símbolo Deus desativado.')
            return
        if not 1 <= cid <= CARD_COUNT:
            messagebox.showerror('Ícone Deus','Escolha uma carta original #001–#722.',parent=self)
            return
        typ = int(self.project.get(cid)['tipo_id'])
        if typ == GOD_TYPE_ID:
            messagebox.showinfo('Ícone do tipo God',
                'O tipo God tem ícone próprio nos detalhes da carta no Drop x15. '
                'Para incluir um ícone adicional no texto, use o editor de descrição.',parent=self)
            return
        if not 0 <= typ < 20:
            messagebox.showwarning(
                'Tipo não suportado para o teste de ícone',
                'Selecione uma carta salva com tipo de monstro PS1 (00–19).', parent=self)
            return
        if not messagebox.askyesno(
                'Teste real do símbolo Deus no ePSXe',
                f'Adicionar um símbolo Deus 16x16 ao texto da carta #{cid:03d} '
                'no próximo BIN/CUE de teste?\n\n'
                'Apenas a cópia de teste terá os 3 PRIMEIROS CARACTERES da '
                'descrição substituídos pelo símbolo. O projeto, a descrição '
                'original e o BIN fonte continuam intactos.\n\n'
                'O símbolo usará uma célula livre na fonte do jogo. Continuar?', parent=self):
            return
        self.project.metadata['ps1_god_icon_test_card_id']=cid
        if self.project.metadata.get('ps1_god_type_test_card_id') == cid:
            self.project.metadata.pop('ps1_god_type_test_card_id')
        self.project.save()
        self._refresh_project()
        self._update_status(
            f'Ícone Deus nativo configurado para teste visual na carta #{cid:03d}. '
            'Gere BIN/CUE para validar no ePSXe.')

    def choose_playable_monster_type(self):
        """Troca o tipo preservando os atributos e os efeitos da carta."""
        if self._extract_running or not self.project or not self.drafts or not self.selected_id:
            return
        self._stage_current()
        cid=self.selected_id
        card=self.drafts.get_card(cid)
        old_type=int(card['tipo_id'])
        old_rarity=card.get('raridade',DEFAULT_RARITY)
        dialog=tk.Toplevel(self)
        dialog.title('Escolher tipo de monstro para PS1')
        dialog.configure(bg=SURFACE)
        dialog.resizable(False,False)
        dialog.transient(self)
        area=ttk.Frame(dialog,padding=18)
        area.pack(fill='both',expand=True)
        ttk.Label(area,text=f'Carta #{cid:03d} — {card.get("nome") or "Sem nome"}').pack(anchor='w',pady=(0,7))
        ttk.Label(area,text='Selecione o tipo de monstro.',
                  wraplength=440).pack(anchor='w',pady=(0,10))
        types=list(range(20))
        if cid<=CARD_COUNT and ps1_supports_god24(self.project):
            types.append(GOD_TYPE_ID)
        selection=ttk.Combobox(area,state='readonly',
                               values=[f'{i:02d} — {TYPE_NAMES[i]}' for i in types],width=38)
        selection.pack(fill='x')
        original=int(self.project.cards[cid]['tipo_id'])
        initial=old_type if old_type in types else original
        selection.current(types.index(initial) if initial in types else 0)
        keep_god=tk.BooleanVar(value=(old_rarity=='deus'))
        ttk.Checkbutton(area,text='Usar raridade Deus no Studio',
                        variable=keep_god).pack(anchor='w',pady=(12,7))
        buttons=ttk.Frame(area)
        from .ui_shell import pin_bottom
        pin_bottom(buttons, pady=(5,0), fill='none', anchor='e')
        def apply():
            try:
                chosen=types[selection.current()]
                self.drafts.choose_playable_monster_type(
                    cid,chosen,god_visual=keep_god.get())
                self._load_card()
                self._refresh_cards()
                self._update_pending_label()
                self._update_status(
                    f'Carta #{cid:03d}: tipo escolhido {TYPE_NAMES[chosen]} '
                    'mantido em rascunho. Clique Salvar projeto.')
                dialog.destroy()
            except (ModError,ValueError) as exc:
                messagebox.showerror('Tipo inválido',str(exc),parent=dialog)
        ttk.Button(buttons,text='Cancelar',command=dialog.destroy).pack(side='left',padx=5)
        ttk.Button(buttons,text='Aplicar tipo escolhido',
                   command=apply,style='Accent.TButton').pack(side='left')
        dialog.bind('<Escape>',lambda _evt:dialog.destroy())
        dialog.grab_set()
        dialog.wait_window()

    def reset_card(self):
        if self._extract_running or not self.project or not self.selected_id:
            return
        if not messagebox.askyesno('Restaurar carta',
            'Restaurar os valores-base desta carta?\nA restauração só será gravada ao clicar Salvar projeto.',parent=self):
            return
        self.drafts.reset_card(self.selected_id)
        self._load_card()
        self._refresh_cards()
        self._update_pending_label()

    def _on_quick_changed(self):
        if getattr(self,'_loading_quick',False) or not self.drafts or not self.selected_id:
            return
        if self._extract_running:
            return
        settings={k:v.get() for k,v in self.quick_vars.items()}
        if settings['limite_copias'] in ('0', '00') and settings['sem_limite_deck']:
            self.quick_vars['sem_limite_deck'].set(False)
        try:
            self.drafts.set_quick_abilities(self.selected_id, settings, default_copies=None)
        except ModError as exc:
            self._update_status(f'Habilidade inválida: {exc}')
            return
        self._refresh_effects(skip_quick=True)
        self._update_pending_label()
        self._update_status('Habilidades alteradas. Clique Salvar projeto ou pressione Ctrl+S.')

    def _load_quick_settings(self, effects):
        self._loading_quick=True
        try:
            values=quick_settings(effects, default_copies=None)
            for key,variable in self.quick_vars.items():
                variable.set('' if values[key] is None else values[key])
        finally:
            self._loading_quick=False

    def _refresh_effects(self, *, skip_quick=False, select_index=None):
        for iid in self.effect_tree.get_children():
            self.effect_tree.delete(iid)
        if not self.project or not self.selected_id:
            return
        cid=self.selected_id
        effects=self.drafts.get_effects(cid) if self.drafts else self.project.effects.get(str(cid),[])
        if not skip_quick:
            self._load_quick_settings(effects)
        self.effect_caption.configure(text=f'Efeitos de {format_id(cid)} — {len(effects)} cadastrado(s)')
        for i,eff in enumerate(effects):
            label=(f"Bônus por {display_name(eff['carta_referencia_id'],{c:self.drafts.get_card(c) for c in self.project.cards})}"
                   if eff.get('acao')=='bonus_por_carta_id' else caption_key(ACTIONS,eff['acao']))
            self.effect_tree.insert('','end',iid=str(i),values=(caption_key(EVENTS,eff['evento']),
                label,effect_target_label(eff['acao'], eff['alvo']),
                effect_filter_label(eff),
                eff['valor'],eff.get('valor_def','—')))
        self.sort_effects()
        if select_index is not None and 0 <= select_index < len(effects):
            self.effect_tree.selection_set(str(select_index))
            self.effect_tree.focus(str(select_index))
            self.effect_tree.see(str(select_index))
        self.sim_result.configure(text='Escolha um gatilho e clique Simular (não executa o PS1).')

    def diagnose_effect_engine(self):
        """Auditoria MIPS somente leitura, sem modificar ou revelar a ROM."""
        if not self._ready_native_effect():
            return
        try:
            from .ps1_effects_lab import save_project_effect_analysis, analyze_project_effects
            report=analyze_project_effects(self.project)
            dest=save_project_effect_analysis(self.project)
            ready=sum(s.get('status')=='regiao_encontrada_sem_hook_validado'
                      for s in report['funcoes_encontradas'].values())
            groups=', '.join(f'{key}: {len(entries)}' for key,entries
                             in report['grupos_programados_no_studio'].items())
            calls=report.get('referencias_chamadas_mips',{})
            stat_refs=calls.get('por_funcao',{}).get('atributos_dinamicos',{})
            jals=stat_refs.get('total_jal_diretos','não disponível')
            ic=report.get('chamadas_mips_icone_tipo_god',{})
            type_calls=ic.get('rotinas',{}).get('tipo_na_lista',{}).get('total_chamadas_glifo','indisponível')
            identity=ic.get('comparacao_com_relatorio_anterior','sem comparação')
            god_class=report.get('diagnostico_god24_classe_monstro',{})
            god_predicates=god_class.get('comparacoes_imediato_20_total','sem validação')
            duel_flow=report.get('diagnostico_god24_fluxo_duelo',{})
            hand_candidates=duel_flow.get('rotinas',{}).get('mao',{}).get('encontrados','indisponível')
            deck=report['perfil_limite_global_deck']
            msg=(f'Funções MIPS encontradas: {ready}/{len(report["funcoes_encontradas"])}\n'
                 f'Efeitos cadastrados: {groups}\n'
                 f'Limite global de cópias: {deck["status"]}\n'
                 f'Chamadas diretas JAL ao cálculo de atributos: {jals}\n'
                 f'Chamadas de glifo no trecho de tipo: {type_calls}.\n'
                 f'Comparação com diagnóstico anterior: {identity}.\n'
                 'Ícone God24: JALs e delay slots no JSON; SEM hook instalado.\n'
                 f'God24 como monstro: {god_predicates} possível(is) comparação(ões) '
                 'com 20 nas rotinas pesquisadas.\n'
                 'ATK/DEF em branco: tipo 24 não passa a verificação de monstro.\n'
                 f'Fluxo da mão em duelo: {hand_candidates} candidatos MIPS analisados.\n'
                 'Na imagem de origem, God24 segue o fluxo de cartas especiais.\n'
                 'Para conferir o patch na cópia, use Verificar BIN/CUE.\n'
                 'A pesquisa NÃO ativou patch de invocação nem ícone.\n'
                 'Amostras de instruções MIPS adicionadas ao relatório.\n\n'
                 'Os endereços são referências do PS1 original; MODs podem usar hooks.\n'
                 'Nenhum efeito inédito foi instalado no BIN somente por gerar este relatório.\n\n'
                 f'Relatório salvo em:\n{dest}')
            messagebox.showinfo('Diagnóstico do motor MIPS',msg,parent=self)
            self._update_status('Diagnóstico MIPS salvo: '+str(dest))
        except (OSError,ModError,ValueError) as exc:
            messagebox.showerror('Diagnóstico MIPS',str(exc),parent=self)

    def configure_ps1_deck_limit(self):
        """Configuração GLOBAL opcional; não substitui limites por carta na GUI."""
        if not self._ready_native_effect():
            return
        from .ps1_effects_lab import deck_global_patch_probe
        exe=self.project.folder/'base'/'source_SLUS_014.11'
        if not exe.is_file():
            messagebox.showerror('SLUS ausente','Importe a mesma imagem original utilizada neste projeto.',parent=self)
            return
        current=int(self.project.metadata.get('ps1_deck_global_limit',3))
        n=simpledialog.askinteger('Limite global no PS1',
             'Limite padrão de cópias por carta (1–40). O deck tem 40 espaços.\n'
             'A configuração original é 3 cópias, com 1 por peça de Exodia.\n'
             'No Drop x15, o limite definido para uma carta tem prioridade.',
             initialvalue=current,minvalue=1,maxvalue=40,parent=self)
        if n is None:
            return
        try:
            status=deck_global_patch_probe(exe.read_bytes(),n)
            if n!=3 and status['status']!='candidato_unico_experimental':
                raise ModError(status['motivo'])
            if not messagebox.askyesno('Confirmar mudança de regra MIPS',
                f'Limite global: {n} cópias de cada carta (deck físico de 40).\n'
                'Esta é uma alteração experimental do código MIPS e precisa de teste no ePSXe.\n'
                'O BIN original não será modificado.\n'
                'Continuar?',
                parent=self):
                return
            self.project.metadata['ps1_deck_global_limit']=n
            self.project.save()
            self._refresh_project()
            self._update_status(f'Limite global MIPS registrado: {n} cópias por ID.')
        except (OSError,ModError,ValueError) as exc:
            messagebox.showerror('Limite global de deck PS1',str(exc),parent=self)

    def _ready_native_effect(self):
        if self._extract_running or not self._ensure_project():
            return False
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve primeiro','Salve as alterações pendentes do projeto.',parent=self)
            return False
        return True

    def configure_native_ritual(self):
        """Edita receita de Ritual que já existe na tabela do disco PS1."""
        if not self._ready_native_effect():
            return
        ritual=self.selected_id
        if not ritual or int(self.project.get(ritual)['tipo_id'])!=22:
            messagebox.showinfo('Selecione uma carta Ritual',
                                'Escolha na biblioteca a carta Ritual original (#001–#722).',
                                parent=self)
            return
        import csv
        from .ps1_native import patch_rituals
        path=self.project.folder/'base'/'rituais.csv'
        if not path.is_file():
            messagebox.showerror('Ritual sem base','Importe primeiro o BIN/CUE original para obter rituais.csv.',parent=self)
            return
        with path.open('r',encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f,delimiter=';'))
        original=next((row for row in rows if int(row['ritual_id'])==ritual),None)
        if original is None:
            messagebox.showerror('Ritual não registrado',
                                 f'A carta #{ritual:03d} não possui receita na tabela do PS1. '
                                 'Criar novos rituais exigiria outro patch MIPS.',parent=self)
            return
        existing=self.project.metadata.get('ps1_ritual_recipes',{}).get(str(ritual))
        initial=existing or [int(original[k]) for k in
                    ('tributo_1','tributo_2','tributo_3','resultado')]
        result=[]
        for index,name in enumerate(('Tributo 1','Tributo 2','Tributo 3','Monstro invocado')):
            n=simpledialog.askinteger(
                'Ritual do PS1',
                f'#{ritual:03d} — {self.project.get(ritual).get("nome","")}\n'
                f'{name} (ID 1–722):',
                initialvalue=int(initial[index]),minvalue=1,maxvalue=722,parent=self)
            if n is None:
                return
            result.append(n)
        if not messagebox.askyesno(
            'Confirmar Ritual',
            f'Ritual #{ritual:03d}\nTributos: #{result[0]:03d}, #{result[1]:03d}, '
            f'#{result[2]:03d}\nInvoca: #{result[3]:03d}\n\n'
            'Será alterada a receita existente em sete cópias, sem modificar fusões.\n'
            'O comportamento no ePSXe ainda precisará ser validado.',
            parent=self):
            return
        plan=dict(self.project.metadata.get('ps1_ritual_recipes',{}))
        plan[str(ritual)]=result
        try:
            self.project.metadata['ps1_ritual_recipes']=plan
            self.project.save()
            self._refresh_project()
            self._update_status(f'Ritual #{ritual:03d} registrado para BIN/CUE.')
        except (OSError,ModError,ValueError) as exc:
            messagebox.showerror('Ritual no PS1',str(exc),parent=self)

    def configure_native_trap(self):
        if not self._ready_native_effect():
            return
        trap=self.selected_id
        from .ps1_native import TRAP_IDS, read_trap_thresholds, patch_trap_thresholds
        if trap not in TRAP_IDS:
            messagebox.showinfo('Selecione Trap de ataque',
                'Selecione uma armadilha de ataque original (IDs #681–#686). '
                'Outros efeitos de Trap não têm limiar configurável neste motor.',parent=self)
            return
        exe=self.project.folder/'base'/'source_SLUS_014.11'
        if not exe.is_file():
            messagebox.showerror('Base ausente','Vincule o executável SLUS original ao projeto.',parent=self)
            return
        original=exe.read_bytes()
        old=read_trap_thresholds(original)[trap]
        stored=self.project.metadata.get('ps1_trap_thresholds',{}).get(str(trap),old)
        value=simpledialog.askinteger('Limiar de Trap',
            f'#{trap:03d}: maior ATK que esta armadilha pode atingir.\n'
            f'Valor original: {old} ATK.\nUse múltiplos de 100 (100–25500).',
            initialvalue=int(stored),minvalue=100,maxvalue=25500,parent=self)
        if value is None:
            return
        plan=dict(self.project.metadata.get('ps1_trap_thresholds',{}))
        plan[str(trap)]=value
        try:
            patch_trap_thresholds(original,plan)
            self.project.metadata['ps1_trap_thresholds']=plan
            self.project.save()
            self._refresh_project()
            self._update_status(f'Trap #{trap:03d}: ativa com ATK até {value} (PS1).')
        except (OSError,ModError,ValueError) as exc:
            messagebox.showerror('Trap no PS1',str(exc),parent=self)

    def configure_native_terrain(self):
        if not self._ready_native_effect():
            return
        from .ps1_native import patch_terrain_boosts
        terrain_names=('Forest','Wasteland','Mountain','Sogen','Umi','Yami')
        terrain=simpledialog.askinteger('Terreno',
            'Escolha o campo do PS1:\n'
            +'\n'.join(f'{i+1}. {name}' for i,name in enumerate(terrain_names)),
            minvalue=1,maxvalue=6,parent=self)
        if terrain is None:
            return
        type_id=simpledialog.askinteger('Tipo de monstro',
            'Tipo original (0–19):\n' +
            '\n'.join(f'{i:02d} — {name}' for i,name in enumerate(TYPE_NAMES[:20])),
            minvalue=0,maxvalue=19,parent=self)
        if type_id is None:
            return
        key=f'{terrain}:{type_id}'
        from .ps1_native import read_terrain_boosts
        exe=self.project.folder/'base'/'source_SLUS_014.11'
        if not exe.is_file():
            messagebox.showerror('Sem base','Vincule o executável SLUS original ao projeto.',parent=self)
            return
        source=exe.read_bytes()
        original=read_terrain_boosts(source)[(terrain,type_id)]
        default=self.project.metadata.get('ps1_terrain_boosts',{}).get(key,original)
        bonus=simpledialog.askinteger('Bônus de campo',
            f'{terrain_names[terrain-1]}: {TYPE_NAMES[type_id]}\n'
            f'Original: {original:+d} ATK/DEF.\n'
            'Novo valor: múltiplos de 10, de -1200 a +1200.',
            initialvalue=int(default),minvalue=-1200,maxvalue=1200,parent=self)
        if bonus is None:
            return
        plan=dict(self.project.metadata.get('ps1_terrain_boosts',{}))
        plan[key]=bonus
        try:
            patch_terrain_boosts(source,plan)
            self.project.metadata['ps1_terrain_boosts']=plan
            self.project.save()
            self._refresh_project()
            self._update_status(
                f'Campo {terrain_names[terrain-1]}, {TYPE_NAMES[type_id]}: {bonus:+d} ATK/DEF.')
        except (OSError,ModError,ValueError) as exc:
            messagebox.showerror('Bônus de terreno PS1',str(exc),parent=self)

    def activate_equip_additions(self):
        """Volta ao modo de adição sem apagar trocas antigas do usuário."""
        if self._extract_running or not self._ensure_project():
            return
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve primeiro','Salve o projeto antes de trocar o modo Equip.',parent=self)
            return
        plan=self.project.metadata.get('ps1_equip_additions',{})
        if not plan:
            messagebox.showinfo('Sem adições',
                                'Selecione uma carta Equip e use PS1: permitir Equip em criatura '
                                'para adicionar o monstro desejado.',parent=self)
            return
        if not messagebox.askyesno(
            'Usar modo automático',
            'Ativar adições de Equip no próximo BIN/CUE?\n\n'
            'O Studio tentará detectar bitmaps MIPS de 94 bytes. '
            'Se a base usar o formato original, só gravará se houver espaço seguro.\n'
            'As trocas de Equip anteriores permanecerão salvas, mas não serão aplicadas.\n'
            'O BIN original não será alterado.',
            parent=self):
            return
        self.project.metadata['ps1_equip_mode']='adicionar'
        try:
            self.project.save()
        except (OSError,ModError) as exc:
            messagebox.showerror('Equip no PS1',str(exc),parent=self)
            return
        self._refresh_project()
        self._update_status('Modo Equip automático ativado; gerar BIN/CUE para testar.')

    def replace_native_equip(self):
        """Troca uma permissão existente SEM aumentar a tabela: teste opt-in."""
        if self._extract_running or not self._ensure_project():
            return
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve primeiro','Salve as alterações pendentes antes do teste.',parent=self)
            return
        equip=self.selected_id
        if not equip or int(self.project.get(equip)['tipo_id'])!=23:
            messagebox.showinfo('Selecione um Equip',
                                'Selecione uma carta original do tipo Equip na biblioteca.',parent=self)
            return
        from .ps1_equip import list_origin_equip_targets, _validated_replacements
        try:
            available=list_origin_equip_targets(self.project,equip)
            if not available:
                raise ModError(f'Equip #{equip:03d} não possui alvos para trocar.')
            preview=', '.join(f'#{i:03d}' for i in available[:18])
            old=simpledialog.askinteger(
                'Escolher alvo a retirar',
                f'Equip #{equip:03d} — alvo(s) permitidos pela origem:\n{preview}'
                + (' ...' if len(available)>18 else '')
                + '\n\nInforme o ID de UM monstro que perderá a permissão de Equip '
                  '(somente no BIN de teste, não na ROM original).',
                minvalue=1,maxvalue=722,parent=self)
            if old is None:
                return
            if old not in available:
                raise ModError(f'#{old:03d} não aparece entre os alvos originais desse Equip.')
            new=simpledialog.askinteger(
                'Escolher novo monstro',
                f'Equip #{equip:03d}: substituir o monstro #{old:03d} por qual ID?\n'
                'Exemplo: Time Wizard = 016.\n'
                'A tabela não crescerá; é um teste de compatibilidade, não efeito MIPS.',
                minvalue=1,maxvalue=722,parent=self)
            if new is None:
                return
            if int(self.project.get(new)['tipo_id'])>=20:
                raise ModError('O novo alvo precisa ser um monstro original.')
            if new in available:
                raise ModError('O novo monstro já consta dos alvos originais.')
            # As adições previamente cadastradas são preservadas no projeto,
            # mas não entram no build enquanto o modo substituição estiver ativo.
            current=self.project.metadata.get('ps1_equip_replacements',{})
            plan={str(k):dict(v) for k,v in _validated_replacements(current).items()}
            plan.setdefault(str(equip),{})[str(old)]=new
            _validated_replacements(plan)
            if not messagebox.askyesno(
                'Confirmar substituição experimental',
                f'Equip #{equip:03d}\n'
                f'RETIRAR permissão do monstro #{old:03d}\n'
                f'PERMITIR o monstro #{new:03d}\n\n'
                'O BIN original não será alterado. A tabela manterá o mesmo tamanho.\n'
                'O modo substituição SUSPENDERÁ as adições de alvos já salvas '
                '(elas não serão apagadas).\n\n'
                'Essa mudança ainda depende da rotina do MOD para funcionar no ePSXe. Continuar?',
                parent=self):
                return
            self.project.metadata['ps1_equip_replacements']=plan
            self.project.metadata['ps1_equip_mode']='substituir'
            self.project.save()
            self._refresh_project()
            self._update_status(f'Equip #{equip:03d}: alvo #{old:03d} -> #{new:03d} '
                                '(troca sem expandir, modo experimental).')
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Substituição de Equip',str(exc),parent=self)

    def allow_native_equip(self):
        """Autoriza monstro a receber Equip original no motor PS1; salva com backup."""
        if self._extract_running or not self._ensure_project():
            return
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve primeiro',
                                'Salve as cartas pendentes antes de autorizar um Equip PS1.',parent=self)
            return
        if not self.selected_id:
            return
        equip=self.selected_id
        if int(self.project.get(equip)['tipo_id'])!=23:
            messagebox.showinfo('Selecione um Equip',
                                'Escolha primeiro uma carta original do tipo Equip.',
                                parent=self)
            return
        monster=simpledialog.askinteger(
            'Equip original do PS1',
            f'#{equip:03d} — {self.project.get(equip).get("nome","")}\n\n'
            'Informe o ID (#001–#722) do monstro que poderá usar esse Equip.\n'
            'O efeito é o bônus original do equipamento, não uma aura personalizada.',
            minvalue=1,maxvalue=722,parent=self)
        if monster is None:
            return
        from .ps1_equip import add_equipment_target
        try:
            if not add_equipment_target(self.project,equip,monster):
                messagebox.showinfo('Já cadastrado','Esse alvo já está no plano.',parent=self)
                return
            self.project.metadata['ps1_equip_mode']='adicionar'
            self.project.save()
        except (ModError,ValueError,OSError) as exc:
            messagebox.showerror('Equip PS1',str(exc),parent=self)
            return
        self._refresh_project()
        self._update_status(f'Equip #{equip:03d} permite monstro #{monster:03d} '
                            'na próxima cópia BIN/CUE de teste.')

    def add_effect(self):
        if self._extract_running:
            messagebox.showinfo("Extração em andamento","Conclua a extração antes de editar, importar ou trocar de projeto.",parent=self)
            return False
        if not self.project or not self.selected_id:
            messagebox.showinfo('Selecione uma carta','Escolha uma carta antes de adicionar efeitos.')
            return
        self._stage_current()
        def submit(entries):
            self.drafts.add_effects(self.selected_id,entries)
            self._refresh_effects()
            self._refresh_project()
            self._update_pending_label()
            self._update_status(f'{len(entries)} efeito(s) pendentes para {format_id(self.selected_id)}. Clique Salvar projeto.')
        EffectDialog(self,submit,batch=True,existing=self.drafts.get_effects(self.selected_id))

    def edit_effect(self):
        """Abre o formulário correto e substitui a regra selecionada no rascunho."""
        if self._extract_running:
            messagebox.showinfo('Extração em andamento',
                'Conclua a extração antes de editar efeitos.',parent=self)
            return
        if not self.project or not self.drafts or not self.selected_id:
            messagebox.showinfo('Selecione uma carta',
                'Escolha uma carta e um efeito para editar.',parent=self)
            return
        selected=self.effect_tree.selection()
        if not selected:
            messagebox.showinfo('Selecione um efeito',
                'Selecione uma linha da tabela Efeitos das cartas.',parent=self)
            return
        self._stage_current()
        cid=self.selected_id
        idx=int(selected[0])
        effects=self.drafts.get_effects(cid)
        if not 0 <= idx < len(effects):
            self._refresh_effects()
            return
        previous=effects[idx]

        def submit(entry):
            self.drafts.replace_effect(cid,idx,entry)
            self._refresh_project()
            self._refresh_effects(select_index=idx)
            self._update_pending_label()
            self._update_status(
                f'Efeito {idx+1} da carta {format_id(cid)} atualizado no rascunho. '
                'Clique Salvar projeto ou pressione Ctrl+S.')

        if previous['acao']=='bonus_por_carta_id':
            cards={card_id:self.drafts.get_card(card_id) for card_id in self.project.cards}
            return SpecificCardEffectDialog(self,cards,submit,initial_effect=previous)
        return EffectDialog(self,submit,initial_effect=previous)

    def add_specific_effect(self):
        if self._extract_running or not self.project or not self.selected_id:
            return
        self._stage_current()
        cards={cid:self.drafts.get_card(cid) for cid in self.project.cards}
        def submit(entry):
            self.drafts.add_effect(self.selected_id,entry)
            # Texto guarda token referencial; exibição mostra o nome corrente.
            atk, defense=int(entry['valor']),int(entry['valor_def'])
            strength=' e '.join(filter(None,(
                f'+{atk} ATK' if atk else '',f'+{defense} DEF' if defense else '')))
            line=f'Esta carta recebe {strength} para cada {{card:{entry["carta_referencia_id"]}}} no {entry["origem_contagem"]}.'
            existing=self.description.get('1.0','end-1c')
            self.description.insert('end', ('\n' if existing.strip() else '') + line)
            self._stage_current()
            self._refresh_effects()
            self.render_description()
            self._update_pending_label()
        SpecificCardEffectDialog(self,cards,submit)

    def add_new_card(self):
        if self._extract_running or not self._ensure_project():
            return
        if self.selected_id:
            self._stage_current()
        from .mod_gui import NewCardDialog
        NewCardDialog(self)

    def select_card(self, cid):
        self._stage_current()
        self.selected_id = cid
        item = str(cid)
        self._refresh_cards()
        if not self.tree.exists(item):
            self._clear_card_filters()
            self._refresh_cards()
        self.tree.selection_set(item)
        self.tree.focus(item)
        self.tree.see(item)
        self._load_card()
        self.tabs.select(self.tab_cards)

    def select_new_card(self, cid):
        self.mod_editor.refresh_catalog()
        self.select_card(cid)
        self._refresh_project()
        self.notify(f'Carta #{cid} criada e salva.')

    def _clear_card_filters(self):
        self._suspend_filters = True
        try:
            for var,value in ((self.filter,''),(self.filter_type,'Todos'),(self.filter_star,'Todas'),
                              (self.filter_from,''),(self.filter_to,'')):
                if var.get()!=value:
                    var.set(value)
        finally:
            self._suspend_filters = False

    def edit_card_rules(self):
        if self.project and self.selected_id and not self._extract_running:
            from .mod_gui import CardRelationsDialog
            self._stage_current()
            CardRelationsDialog(self,self.selected_id)

    def open_card_ps1_options(self):
        if not self.project or not self.selected_id:
            return
        window=tk.Toplevel(self)
        window.title('Opções PS1 da carta')
        window.transient(self)
        content=ttk.Frame(window,padding=12)
        content.pack(fill='both',expand=True)
        actions = ([('Modelo PS1 e relações', self.edit_card_rules),
                    ('Ícones na descrição', self.choose_description_icon)] if self.selected_id > 722 else
                   [('Tipo jogável no PS1', self.choose_playable_monster_type),
                    ('Glifo God na descrição', self.toggle_god_icon_ps1)])
        for label,command in actions:
            ttk.Button(content,text=label,command=command).pack(fill='x',pady=4)

    def insert_description_token(self, token: str):
        if not self.project or not self.selected_id:
            return
        self.description.insert('insert', token)
        self.render_description()
        self._stage_current()
        self._update_pending_label()

    def _resize_description(self):
        try:
            height=max(4,min(28,int(self.description_height.get())))
        except (ValueError,tk.TclError):
            height=8
        self.description_height.set(height)
        self.description.configure(height=height)

    def choose_description_icon(self):
        if not self.project or not self.selected_id:
            return
        from .icon_composer import IconComposer
        insertion=self.description.index('insert')
        def confirm(items):
            self.description.insert(insertion,''.join(items))
            self.render_description()
            self._stage_current()
            self._update_pending_label()
            self.description.see(insertion)
        IconComposer(self,self.get_icon_image,confirm)

    def verify_ps1_description_bin(self):
        """Confere diretamente o texto da imagem selecionada, não apenas o JSON."""
        if not self.project or not self.selected_id:
            return
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo(
                'Salve antes de conferir',
                'Clique em Salvar projeto antes de comparar as descrições '
                'com o BIN/CUE. A análise utiliza os textos salvos.',
                parent=self)
            return
        folder = self.project.folder / 'exportacao' / 'teste_ps1'
        filepath = filedialog.askopenfilename(
            title='Selecione a cópia BIN/CUE executada no ePSXe',
            initialdir=str(folder if folder.is_dir() else self.project.folder),
            filetypes=[('PlayStation BIN/CUE', '*.cue *.bin'),
                       ('Todos arquivos', '*.*')], parent=self)
        if not filepath:
            return
        try:
            import json
            from .ps1_description_verify import scan_disc_descriptions
            ids = {int(cid) for cid, fields in self.project.edits.items()
                   if 'descricao' in fields}
            ids.update(int(cid) for cid in self.project.new_cards if self.project.get(int(cid)).get('descricao'))
            ids.add(int(self.selected_id))
            result = scan_disc_descriptions(self.project, Path(filepath), ids=ids)
            output = self.project.folder / 'exportacao'
            output.mkdir(parents=True, exist_ok=True)
            target = output / 'diagnostico_descricoes_ps1.json'
            staging = output / '.diagnostico_descricoes_ps1.tmp'
            staging.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            staging.replace(target)
        except (OSError, ValueError, ModError, DiscError) as exc:
            messagebox.showerror('Falha na conferência do BIN/CUE', str(exc), parent=self)
            return
        counts = result['contagens']
        chosen = next((row for row in result['cartas']
                       if row['id'] == self.selected_id), None)
        summary = (
            f'BIN escolhido: {result["imagem_analisada"]}\n'
            f'SHA-256 do SLUS: {result["sha256_slus_bin"][:20]}...\n\n'
            f'Descrições confirmadas: {counts["aplicada"]}\n'
            f'Prévias resumidas: {counts["resumida"]}\n'
            f'Cartas novas sem descrição: {counts["sem_texto"]}\n'
            f'Ainda originais: {counts["original"]}\n'
            f'Diferentes do Studio: {counts["divergente"]}\n'
            f'Incompatíveis: {counts["incompativel"]}\n'
            f'Fora do catálogo nativo desta imagem: {counts["somente_studio"]}\n\n'
        )
        if chosen:
            summary += (f'Carta #{chosen["id"]}: {chosen["status"].upper()}\n'
                        f'{chosen["motivo"]}\n\n')
        problems = [row for row in result['cartas']
                    if row['status'] != 'aplicada']
        if problems:
            summary += 'Primeiras cartas não confirmadas:\n'
            summary += '\n'.join(f'#{row["id"]}: {row["status"]}'
                                 for row in problems[:10]) + '\n\n'
        else:
            summary += ('Os textos esperados estão gravados neste BIN. '
                        'Se não aparecem no ePSXe, confirme que este mesmo '
                        'arquivo foi aberto e que a tela de informações '
                        'está acessível no mod.\n\n')
        summary += f'Relatório completo: {target}'
        messagebox.showinfo('Conferência de descrições no PS1', summary, parent=self)

    def choose_description_color(self):
        if not self.project:return
        popup=tk.Toplevel(self);popup.title('Colorir texto');popup.configure(bg=BG)
        for name,(num,hexcol) in TEXT_COLORS.items():
            tk.Button(popup,text=name.upper(),fg=hexcol,bg=SURFACE,relief='flat',width=24,
                      command=lambda name=name:(self.apply_description_color(name),popup.destroy())).pack(padx=12,pady=3)

    def apply_description_color(self,name):
        if not self.project:return
        try:
            a=self.description.index('sel.first');b=self.description.index('sel.last')
            selection=self.description.get(a,b)
            self.description.delete(a,b)
            self.description.insert(a,'{color:'+name+'}'+selection+'{/color}')
        except tk.TclError:
            self.insert_description_token('{color:'+name+'}')
        self.render_description()
        self._stage_current()

    def choose_description_reference(self):
        if not self.project:return
        from .card_picker import CardPickerDialog
        cards={cid:(self.drafts.get_card(cid) if self.drafts else self.project.get(cid)) for cid in self.project.cards}
        CardPickerDialog(self, cards, lambda ids: self.insert_description_token(f'{{card:{ids[0]}}}'),
                         title='Referenciar carta na descrição', confirm='Inserir referência')

    def get_icon_image(self,name):
        if not hasattr(self,'_icon_cache'):self._icon_cache={}
        if name not in self._icon_cache:
            try:
                root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
                self._icon_cache[name]=tk.PhotoImage(file=str(root/'assets'/'icons'/(name+'.png')))
            except (tk.TclError,OSError):
                self._icon_cache[name]=None
        return self._icon_cache[name]

    def render_description(self):
        if not hasattr(self,'description_preview'):return
        widget=self.description_preview
        widget.configure(state='normal');widget.delete('1.0','end')
        self._desc_images=[]
        c={cid:self.drafts.get_card(cid) for cid in self.project.cards} if self.project and self.drafts else {}
        for chunk,color,icon in tokens(self.description.get('1.0','end-1c'),c):
            if icon:
                img=self.get_icon_image(icon)
                if img:
                    self._desc_images.append(img)
                    widget.image_create('end',image=img)
                else:
                    widget.insert('end',f'[{icon[7:] if icon.startswith("nativo:") else icon}]')
            else:
                tag='col_'+color.lstrip('#')
                widget.tag_configure(tag,foreground=color)
                widget.insert('end',chunk,tag)
        widget.configure(state='disabled')

    def copy_selected_effects(self, *, all_effects=False):
        """Atalhos atuam só na tabela de efeitos, não em campos de texto."""
        if not self.project or not self.selected_id or not self.drafts:
            return 'break'
        from .effects_transfer import encode_effects
        all_entries=self.drafts.get_effects(self.selected_id)
        selected=sorted(int(i) for i in self.effect_tree.selection()
                        if str(i).isdecimal() and 0<=int(i)<len(all_entries))
        entries=all_entries if all_effects else [all_entries[i] for i in selected]
        try:
            text=encode_effects(self.selected_id,entries)
        except (ModError,ValueError) as exc:
            messagebox.showinfo('Copiar efeitos',str(exc),parent=self)
            return 'break'
        self.clipboard_clear()
        self.clipboard_append(text)
        self._update_status(f'{len(entries)} efeito(s) copiado(s). Selecione outra carta e pressione Ctrl+V.')
        return 'break'

    def paste_effects(self):
        if self._extract_running or not self.project or not self.selected_id or not self.drafts:
            return 'break'
        from .effects_transfer import decode_effects, merge_effects, reference_warnings
        try:
            raw=self.clipboard_get()
            source,entries=decode_effects(raw)
        except (ModError,ValueError,tk.TclError) as exc:
            messagebox.showwarning('Colar efeitos',str(exc),parent=self)
            return 'break'
        self._stage_current()
        current=self.drafts.get_effects(self.selected_id)
        answer=messagebox.askyesnocancel(
            'Colar efeitos',
            f'{len(entries)} efeito(s) copiado(s) da carta #{source}.\n'
            f'Destino: carta #{self.selected_id}.\n\n'
            'Sim = acrescentar ao conjunto existente.\n'
            'Não = substituir todos os efeitos atuais.\n'
            'Cancelar = manter os efeitos sem alteração.',parent=self)
        if answer is None:
            return 'break'
        notes=reference_warnings(source,self.selected_id,entries)
        if notes and not messagebox.askokcancel(
                'Conferir referências antes de colar','\n'.join(notes[:12]),
                parent=self):
            return 'break'
        try:
            proposed=merge_effects(current,entries,replace=not answer)
            self.drafts.set_effects(self.selected_id,proposed)
        except (ModError,ValueError) as exc:
            messagebox.showerror('Colar efeitos',str(exc),parent=self)
            return 'break'
        self._refresh_effects()
        self._refresh_project()
        self._update_pending_label()
        self._update_status(f'{len(entries)} efeito(s) colado(s) no rascunho. Salve o projeto para persistir.')
        return 'break'

    def _effects_context_menu(self,event):
        item=self.effect_tree.identify_row(event.y)
        if item and item not in self.effect_tree.selection():
            self.effect_tree.selection_set(item)
        menu=tk.Menu(self,tearoff=0)
        menu.add_command(label='Copiar efeito(s) selecionado(s)',command=self.copy_selected_effects)
        menu.add_command(label='Copiar todos os efeitos',command=lambda:self.copy_selected_effects(all_effects=True))
        menu.add_command(label='Colar efeitos',command=self.paste_effects)
        menu.tk_popup(event.x_root,event.y_root)
        menu.grab_release()
        return 'break'

    def remove_effect(self):
        if self._extract_running:
            messagebox.showinfo("Extração em andamento","Conclua a extração antes de editar, importar ou trocar de projeto.",parent=self)
            return False
        if not self.project or not self.selected_id or not self.effect_tree.selection():
            return
        if not messagebox.askyesno('Excluir efeito','Remover o efeito selecionado do projeto?'):
            return
        idx=int(self.effect_tree.selection()[0])
        self.drafts.remove_effect(self.selected_id,idx)
        self._refresh_effects()
        self._refresh_project()
        self._update_pending_label()

    def simulate_field(self):
        if not self.project or not self.selected_id:
            return
        self._stage_current()
        from .lab_gui import AdvancedFieldDialog
        AdvancedFieldDialog(self,self.project,self.drafts,self.selected_id)

    def simulate(self):
        if not self.project or not self.selected_id:
            return
        event=list(EVENTS)[self.sim_combo.current()]
        if event in ('continuo','equipado','regra_deck','atacar', ENTRY_TYPE_EVENT) or any(
                e.get('evento') == event and (e.get('acao') in ONCE_ACTIONS or e.get('acao') in ENTRY_EFFECTS)
                for e in self.drafts.get_effects(self.selected_id)):
            self.simulate_field()
            return
        self._stage_current()
        try:
            data,effects=self.drafts.simulate(self.selected_id,event)
        except (ValueError, ModError) as exc:
            messagebox.showerror('Não foi possível simular',str(exc),parent=self)
            return
        self.sim_result.configure(text=(f'{len(effects)} efeito(s) ativado(s).  Seu monstro: ATK {data["ataque"]}, DEF {data["defesa"]}.  '
                f'Monstro rival: ATK {data["ataque_adversario"]}, DEF {data["defesa_adversario"]}.\n'
                f'LP: você {data["lp_jogador"]}  •  rival {data["lp_adversario"]}.  Simulação local, sem efeito no jogo.'))

    def _refresh_fusions(self):
        for iid in self.fusion_tree.get_children():
            self.fusion_tree.delete(iid)
        if not self.project or not self.selected_id:
            return
        cid=self.selected_id
        related=[r for r in self.project.fusions if str(r['material_1'])==str(cid) or str(r['material_2'])==str(cid) or str(r['resultado'])==str(cid)]
        self.fusion_title.configure(text=f'{format_id(cid)}  •  {len(related)} combinações envolvendo a carta')
        for i,row in enumerate(related[:1600]):
            self.fusion_tree.insert('','end',iid=str(i),values=(format_id(int(row['material_1'])),
                format_id(int(row['material_2'])),format_id(int(row['resultado'])),
                'Possível glitch' if str(row['possivel_glitch'])=='1' else 'Não'))
        self.sort_fusions()
        self.fusion_footer.configure(text=(f'{len(self.project.fusions):,} receitas importadas. Tabela protegida por SHA-256. '
            f'Exibindo até 1.600 relacionadas.').replace(',','.'))

    def _refresh_project(self):
        pane=self.project_details
        pane.configure(state='normal')
        pane.delete('1.0','end')
        if not self.project:
            txt='Nenhum projeto aberto.\n\n1. Novo projeto\n2. Importar CSVs ou BIN/CUE\n3. Escolher uma carta\n4. Editar / adicionar efeitos\n5. Exportar'
        else:
            pr=self.project
            from .ps1_image_optimizer import ImageOptions
            config=ImageOptions.from_mapping(pr.metadata.get('ps1_image_optimizer'))
            self.ps1_opt_enabled.set(config.enabled)
            labels={'automatico':'Automático (recomendado)',
                    'maxima_fidelidade':'Máxima fidelidade',
                    'compatibilidade':'Compatibilidade original',
                    'personalizado':'Personalizado'}
            self.ps1_opt_mode.set(labels[config.mode])
            effects=sum(map(len,pr.effects.values()))
            source='VINCULADO' if (pr.folder/'base'/'source_SLUS_014.11').is_file() else 'NÃO VINCULADO'
            notes='\n'.join(f' • {x}' for x in pr.imported_notes[:8]) or ' • Nenhum aviso registrado.'
            god_cards=ps1_god24_card_ids(pr)
            god_icon=legacy_god_description_icon_card(pr)
            txt=(f'Projeto: {pr.metadata["nome"]}\n'
                f'Pasta: {pr.folder}\n'
                f'Base: {pr.metadata.get("base_source") or "Não importada"}\n'
                f'Cartas carregadas: {len(pr.cards)}\n'
                f'Cartas criadas no projeto: {len(pr.new_cards)}\n'
                f'Cópias no baú do Studio: {sum(map(int, pr.metadata.get("bau_jogador", {}).values()))}\n'
                f'Fusões originais: {len(pr.fusions)} (somente leitura)\n'
                f'Cartas alteradas e salvas: {len(pr.edits)}\n'
                f'Cartas com alterações pendentes: {self.drafts.count if self.drafts else 0}\n'
                f'Efeitos planejados: {effects}\n'
                f'Modo Equip PS1: {pr.metadata.get("ps1_equip_mode","adicionar")}\n'
                f'Adições de Equip salvas: {sum(len(v) for v in pr.metadata.get("ps1_equip_additions",{}).values())}\n'
                f'Substituições de Equip salvas: {sum(len(v) for v in pr.metadata.get("ps1_equip_replacements",{}).values())}\n'
                f'Receitas Ritual PS1: {len(pr.metadata.get("ps1_ritual_recipes",{}))}\n'
                f'Limiar Trap PS1: {len(pr.metadata.get("ps1_trap_thresholds",{}))}\n'
                f'Bônus terreno PS1: {len(pr.metadata.get("ps1_terrain_boosts",{}))}\n'
                f'Limite global deck MIPS: {pr.metadata.get("ps1_deck_global_limit",3)} cópias\n'
                f'Cartas originais salvas como God (24): {len(god_cards)}\n'
                f'Glifo Deus na descrição (teste PS1): {format_id(god_icon) if god_icon else "desativado"}\n'
                f'Artes PNG vinculadas: {len(pr.arts)} (somente prévia)\n'
                f'Extração profunda: {pr.metadata.get("deep_extraction", {}).get("completed", "ainda não realizada")}\n'
                f'Executável SLUS local: {source}\n\n'
                f'Avisos da extração ({len(pr.imported_notes)}):\n{notes}\n\n'
                'EXPORTAÇÃO\n'
                '• Exportar alterações grava os dados do Studio em JSON.\n'
                '• Gerar jogo BIN/CUE aplica as regras compatíveis à cópia do jogo.\n'
                '• Auditar compatibilidade mostra os recursos graváveis nesta base.\n')
        pane.insert('1.0',txt)
        pane.configure(state='disabled')

    def _refresh_all(self):
        self.proj_title.configure(text=self.project.metadata['nome'] if self.project else 'Nenhum projeto aberto')
        state = 'normal' if self.project else 'disabled'
        for button in (self.save_button, self.build_button, self.export_button, self.new_card_button,
                       self.translate_button):
            button.configure(state=state)
        keep = self.selected_id if self.project and self.selected_id in self.project.cards else None
        if keep is None:
            self._clear_card_filters()
        self.selected_id = keep
        self._refresh_cards()
        if self.project and self.project.cards:
            if keep is None:
                self.selected_id = 1 if 1 in self.project.cards else min(self.project.cards)
            item = str(self.selected_id)
            if self.tree.exists(item):
                self.tree.selection_set(item)
                self.tree.see(item)
            self._load_card()
        self._refresh_project()
        self._refresh_extract()
        self.mod_editor.refresh()
        self._update_pending_label()
        self._refresh_frame_status()
        self._refresh_home()

    def _refresh_frame_status(self):
        pr = self.project
        self.statusbar.set_project(pr.metadata.get('nome') if pr else None)
        if pr:
            slus = (pr.folder/'base'/'source_SLUS_014.11').is_file()
            base = pr.metadata.get('base_source') or ''
            base = Path(str(base)).name if base else 'sem base importada'
            self.statusbar.set_disc(f'Base: {base}  ·  SLUS {"vinculado" if slus else "não vinculado"}')
        else:
            self.statusbar.set_disc('')

    def verify(self):
        if not self._ensure_project():
            return
        errors=self.project.validate()
        if errors:
            messagebox.showwarning('Problemas encontrados','\n'.join(errors[:10]))
        else:
            messagebox.showinfo('Auditoria básica OK','Projeto coerente e tabelas-base preservadas.\n\nIsso NÃO valida os efeitos nem a execução no PS1.')
        self._update_status(f'Integridade do projeto: {len(errors)} erro(s) local(is).')

    def export(self):
        if self._extract_running:
            messagebox.showinfo("Extração em andamento","Conclua a extração antes de editar, importar ou trocar de projeto.",parent=self)
            return False
        if not self._ensure_project():
            return
        if not self.project.cards:
            messagebox.showwarning('Sem cartas','Crie ou importe pelo menos uma carta.')
            return
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve antes de exportar',
                'Existem alterações pendentes. Clique Salvar projeto primeiro.',parent=self)
            return
        try:
            from .core import ps1_stat_export_errors, ps1_unwritable_numeric_edits
            incompatible=ps1_stat_export_errors(self.project) + ps1_unwritable_numeric_edits(self.project)
            folder,manifest=self.project.export(include_ps1=False) if incompatible else self.project.export()
        except (OSError,ModError,ValueError) as exc:
            messagebox.showerror('Exportação bloqueada',str(exc))
            return
        self._update_status('Alterações exportadas: '+str(folder))
        if incompatible:
            messagebox.showinfo('Dados do Studio exportados',f'{folder}\n\n'+'\n'.join(incompatible[:6]),parent=self)
            return
        if messagebox.askyesno(
            'Exportação concluída — gerar jogo de teste?',
            f'Pasta: {folder}\n\nCartas alteradas: {manifest["cartas_editadas"]}\n'
            f'Efeitos planejados: {manifest["efeitos_planejados"]}\n\n'
            'A exportação dos dados foi concluída. Deseja também gerar uma '
            'cópia BIN/CUE de teste para abrir no ePSXe?\n\n'
            'Você escolherá o mesmo BIN/CUE importado no projeto. '
            'O arquivo original NÃO será sobrescrito.\n'
            'A cópia informa os recursos aplicados. No Drop x15, a expansão experimental aceita #723–#740.',
            parent=self):
            self.build_disc()

    def audit_ps1(self):
        if self._extract_running or not self._ensure_project():
            return
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve primeiro','Clique Salvar projeto antes da auditoria PS1.',parent=self)
            return
        try:
            from .ps1_compat import audit, save_audit
            report=audit(self.project)
            dest=save_audit(self.project)
        except (OSError,ValueError,ModError) as exc:
            messagebox.showerror('Auditoria PS1',str(exc),parent=self)
            return
        counts=report['contagens']
        pending=report['pendente_de_motor']
        summary=(f'SLUS verificado: {"SIM" if report["slus_conferido"] else "NÃO"}\n'
                 f'Estatísticas: {counts["estatisticas"]}; nomes curtos: {counts["nomes"]}; '
                 f'descrições curtas: {counts["descricoes"]}; artes: {counts["artes"]}\n'
                 f'Efeitos ainda sem motor PS1: {counts["efeitos"]}\n'
                 f'Cartas adicionais: {counts["cartas_extras"]}\n'
                 f'Pendências: {len(pending)}\n\n'
                 + ('\n'.join(pending[:7]) if pending else 'Nenhuma pendência identificada.')
                 + f'\n\nRelatório: {dest}')
        messagebox.showinfo('Compatibilidade de conteúdo com PS1',summary,parent=self)
        self._update_status(f'Auditoria PS1: {len(pending)} pendências no projeto.')

    def build_disc(self):
        if self._extract_running or not self._ensure_project():
            return
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve primeiro', 'Clique Salvar projeto antes de gerar uma cópia de teste.', parent=self)
            return
        from .ps1_compat import audit, save_audit, explain_no_writable_changes
        from .core import ps1_unwritable_numeric_edits, ps1_stat_export_errors
        unexportable=ps1_unwritable_numeric_edits(self.project)
        oversized=ps1_stat_export_errors(self.project)
        if unexportable or oversized:
            messagebox.showerror(
                'Corrija os atributos antes de gerar o BIN',
                'Há alterações que não seriam aplicadas corretamente no PS1.\n\n'
                +'\n'.join((unexportable+oversized)[:8])
                +'\n\nNenhum BIN/CUE foi modificado.',parent=self)
            return
        report = audit(self.project)
        description_icon=legacy_god_description_icon_card(self.project)
        if not report['gravavel_hoje'] and not description_icon:
            dest = save_audit(self.project)
            messagebox.showwarning(
                'Nenhuma alteração compatível para gerar o jogo',
                explain_no_writable_changes(self.project, report)
                + f'\n\nRelatório salvo em: {dest}', parent=self)
            self._update_status('Sem mudanças graváveis no PS1: confira compatibilidade_ps1.json.')
            return
        source = filedialog.askopenfilename(
            title='Selecione seu jogo original BIN/CUE',
            filetypes=[('PlayStation BIN/CUE', '*.bin *.cue'), ('Todos arquivos', '*.*')], parent=self)
        if not source:
            return
        pending=report['pendente_de_motor']
        god_cards=ps1_god24_card_ids(self.project) if ps1_supports_god24(self.project) else []
        from .ps1_campaign_quests import quest_settings
        quests_enabled = quest_settings(self.project)['ativado']
        question = ('Será criada ou atualizada a cópia de teste do disco, sem modificar o original.\n'
                    'Mesmo nome de origem: substitui o teste anterior. Outro nome: cria outro arquivo.\n'
                    'Se o ePSXe estiver usando a imagem anterior, feche o jogo antes de substituí-la.\n\n'
                    'Consulte as alterações compatíveis no relatório do projeto.\n'
                    + ('Quests de doação ativadas. A cópia de campanha terá o sufixo _QUESTS.\n'
                       if quests_enabled else '')
                    + ('Ícone Deus na descrição: três caracteres são trocados só na cópia.\n'
                       if description_icon else '')
                    + (f'God (24): {len(god_cards)} carta(s) com nome, ícone e jogabilidade de monstro.\n'
                       if god_cards else '')
                    + (f'PENDÊNCIAS: {len(pending)}.\n' + '\n'.join(pending[:3]) + '\n\n' if pending else '')
                    + 'Gerar a cópia BIN/CUE de teste?')
        if not messagebox.askyesno('Gerar cópia de teste', question, parent=self):
            return
        try:
            from .disc_build import build_test_disc, DescriptionCompatibilityError
            manifest = self.run_blocking('Gerando BIN/CUE…', build_test_disc, self.project, Path(source))
        except DescriptionCompatibilityError as exc:
            failed = list(exc.failures)
            summary = '\n'.join('• ' + item for item in failed[:6])
            if len(failed) > 6:
                summary += f'\n• ... e mais {len(failed) - 6}'
            proceed = messagebox.askyesno(
                'Descrições incompatíveis com o PS1',
                f'{len(failed)} descrição(ões) editada(s) não cabem na '
                'imagem selecionada ou usam recursos sem suporte.\n\n'
                + summary
                + '\n\nGerar o BIN/CUE com as descrições compatíveis?\n\n'
                  'Cartas originais com texto incompatível mantêm a descrição de origem. '
                  'Cartas novas recebem uma prévia quando possível ou ficam sem texto na cópia. '
                  'O Studio guarda os textos completos e o relatório lista cada ajuste.',
                parent=self)
            if not proceed:
                self._update_status('BIN/CUE preservado: corrija as descrições incompatíveis.')
                return
            try:
                manifest = self.run_blocking(
                    'Gerando BIN/CUE…', build_test_disc, self.project, Path(source),
                    description_policy='preserve_incompatible')
            except (OSError, ValueError, ModError, DiscError) as retry_exc:
                messagebox.showerror(
                    'Falha na exportação com descrições compatíveis',
                    str(retry_exc), parent=self)
                return
        except ModuleNotFoundError as exc:
            messagebox.showerror(
                'Atualização incompleta',
                f'Falta o módulo {exc.name!r} nesta instalação.\\n\\n'
                'Clique em Atualizar para reinstalar o pacote completo da versão atual. '
                'Se o botão não conseguir corrigir, utilize o migrador ATUALIZAR_SEM_ZIP.ps1. '
                'Suas cartas e arquivos BIN originais serão preservados.', parent=self)
            return
        except (OSError, ValueError, ModError, DiscError) as exc:
            messagebox.showerror('Não foi possível gerar BIN/CUE', str(exc), parent=self)
            return
        action='substituída' if manifest.get('acao_arquivo')=='substituido' else 'criada'
        runtime=manifest.get('efeitos_nativos_ps1') or {}
        mod=manifest.get('edicao_do_mod_ps1',{})
        rank_hud = {
            'aplicado': 'Rank ao vivo gravado no HUD do PS1. Inicie um duelo novo na cópia.\n',
            'sem_espaco': 'Rank no HUD pendente. Efeitos e descrições já ocupam a reserva de código.\n',
            'conflito': 'Rank no HUD pendente. A rotina de desenho do BIN já foi alterada.\n',
            'perfil_incompativel': 'Rank no HUD do PS1 requer a imagem original Drop x15 compatível.\n',
        }.get(manifest.get('rank_hud_ps1', {}).get('status'), '')
        supreme = manifest.get('supreme_ps1', {})
        quests = manifest.get('quests_campanha_ps1', {})
        simplified=sum(bool(row.get('acentos_simplificados')) for row in manifest['descricoes_aplicadas'])
        reflowed=sum(bool(row.get('quebras_reorganizadas')) and not row.get('resumida')
                     for row in manifest['descricoes_aplicadas'])
        previews = manifest.get('descricoes_resumidas_ps1', [])
        no_text = manifest.get('cartas_novas_sem_descricao_ps1', [])
        originals_kept = len(manifest['descricoes_nao_gravadas']) - len(no_text)
        art_ids = {row['id'] for row in manifest['artes_aplicadas']}
        art_ids.update(manifest.get('expansao_cartas_ps1', {}).get('artes_proprias', []))
        name_ids = {row['id'] for row in manifest['nomes_aplicados']}
        name_ids.update(manifest.get('titulos_gravados_ps1', []))
        messagebox.showinfo(f'Imagem de teste {action}',
            f'Imagem de teste {action} com sucesso.\n\n'
            f'BIN: {manifest["bin"]}\nCUE: {manifest["cue"]}\n'
            f'Cartas com atributos confirmados no BIN: '
            f'{manifest.get("verificacao_atributos",{}).get("corretas","não disponível")}\n'
            f'Setores modificados: {manifest["setores_modificados"]}\n\n'
            'No ePSXe, selecione File > Run ISO e a cópia .BIN gerada.\n'
            f'Nomes gravados em {len(name_ids)} carta(s). '
            f'Descrições em {len(manifest["descricoes_aplicadas"])}. Artes em {len(art_ids)}.\n'
            f'Descrições confirmadas por bytes e ponteiros do BIN: {len(manifest.get("descricoes_confirmadas_no_bin", []))}.\n'
            + (f'Quebras de linha reorganizadas em {reflowed} descrição(ões) completas.\n' if reflowed else '')
            + (f'Prévias de descrição em {len(previews)} carta(s) nova(s).\n' if previews else '')
            + (f'Cartas novas sem texto na cópia: {", ".join(f"#{cid}" for cid in no_text)}.\n' if no_text else '')
            + (f'{originals_kept} carta(s) mantiveram o texto original.\n' if originals_kept else '')
            + ('Os textos completos continuam no Studio.\n'
               f'Detalhes: {Path(manifest["bin"]).with_suffix(".json")}\n'
               if previews or no_text or originals_kept else '')
            + f'Efeitos gravados no PS1: {len(runtime.get("efeitos",[]))}. '
            f'Ícones de descrição: {len(manifest.get("icones_de_descricao_ps1",[]))}.\n'
            + ('Ataque na abertura restrito pela habilidade da carta.\n'
               if mod.get('bloqueio_turno_inicial') else '')
            + (f'Configurações do mod aplicadas: {len(mod["aplicado"])}.\n' if mod.get('aplicado') else '')
            + rank_hud
            + (f'Quests antes do duelo gravadas para {quests["duelistas"]} duelistas. Seed {quests["seed"]}.\n'
               'No modo História, desafie um duelista após Simon para testar a doação.\n'
               if quests.get('status') == 'aplicado' else '')
            + (f'Supreme (+700) conferida no BIN em {len(supreme["ids"])} carta(s).\n'
               if supreme.get('status') == 'aplicado' else '')
            + (f'Baú com {manifest["catalogo_bau_ps1"]["cartas"]} cartas, inclusive as sem cópias.\n'
               if manifest.get('catalogo_bau_ps1', {}).get('status') == 'aplicado' else '')
            + ('Baú PS1 no comportamento original (apenas cartas obtidas).\n'
               if manifest.get('catalogo_bau_ps1', {}).get('status') == 'ausente'
               and not manifest.get('catalogo_bau_completo_ativado', True) else '')
            + (f'Preços de Password alterados: {len(manifest.get("precos_password_ps1", []))} carta(s).\n'
               if manifest.get('precos_password_ps1') else '')
            + (f'Estrelas por vitória: {manifest["estrelas_por_vitoria_ps1"]["estrelas"]} (valor fixo).\n'
               if manifest.get('estrelas_por_vitoria_ps1', {}).get('status') == 'fixo' else '')
            + (f'Cartas novas gravadas: {len(manifest["expansao_cartas_ps1"]["ids_adicionais"])}. Expansão experimental até #740.\n'
               if manifest.get('expansao_cartas_ps1', {}).get('status') == 'aplicado' else '')
            + (f'Fusões personalizadas gravadas: {len(runtime["fusoes"])}.\n'
               if runtime.get('fusoes') else '')
            + (f'Decks fixos de 40 cartas: {len(runtime["decks_fixos"])} duelista(s).\n'
               if runtime.get('decks_fixos') else '')
            + (f'Nomes com cor de tier: {runtime["nomes_tier"]} carta(s).\n'
               if runtime.get('nomes_tier') else '')
            + (f'Drops do próprio deck: {len(runtime["drops_do_deck"])} duelista(s).\n'
               if runtime.get('drops_do_deck') else '')
            + (f'Passwords por ID: {runtime["password_id_prefix"]:05d} + os três dígitos do ID.\n'
               if runtime.get('password_id_prefix') is not None else '')
            + (f'Fonte PS1 simplificou acentos em {simplified} descrição(ões).\n' if simplified else '')
            + (f'ATENÇÃO: descrições dos IDs {", ".join(map(str, manifest["descricoes_somente_studio"][:8]))} '
               'ficam apenas no Studio nesta imagem.\n'
               if manifest.get('descricoes_somente_studio') else '')
            + f'Recursos pendentes: {len(manifest["recursos_pendentes"])}.\n'
            + (f'God (24) aplicado a {len(manifest["god24_cartas"])} carta(s). '
               'Abra os detalhes com Triângulo para ver o ícone.\n'
               if manifest.get('god24_cartas') else '')
            + f'Alterações Equip ({manifest.get("modo_equip_ps1","adicionar")}): {len(manifest.get("equipamentos_ps1_aplicados",[]))}.\n'
            f'Método: {manifest.get("estrategia_equip_ps1","não aplicado")}.\n'
            f'Rituais: {len(manifest.get("rituais_ps1_aplicados",[]))}; '
            f'Armadilhas: {len(manifest.get("armadilhas_ps1_aplicadas",[]))}; '
            f'Terrenos: {len(manifest.get("terrenos_ps1_aplicados",[]))}.\n'
            f'Regra de deck MIPS: {len(manifest.get("limite_global_copias_ps1_aplicado",[]))} patch(es).\n'
            f'Ícone Deus (teste visual na descrição): '
            f'{manifest.get("teste_visual_icone_deus",{}).get("status") if manifest.get("teste_visual_icone_deus") else "não habilitado"}.\n'
            + ('AVISO: o glifo da descrição exige uma célula livre na fonte deste mod.\n'
               if (manifest.get('teste_visual_icone_deus') or {}).get('status')
                  == 'icone_nao_inserido_sem_espaco_livre' else '')
            + 'Confira o resultado no ePSXe.',parent=self)
        self.notify(f'Imagem de teste {action}.')

    def diagnose_equip(self):
        if self._extract_running or not self._ensure_project():
            return
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve primeiro', 'Clique Salvar projeto antes do diagnóstico.', parent=self)
            return
        target=self.project.folder/'exportacao'/'teste_ps1'
        path=filedialog.askopenfilename(
            title='Escolha o BIN/CUE gerado para testar o Equip',
            initialdir=str(target if target.is_dir() else self.project.folder),
            filetypes=[('Discos de PlayStation','*.bin *.cue'),('Todos','*.*')],
            parent=self)
        if not path:
            return
        try:
            from .ps1_equip import diagnose_equipment_project, describe_equip_diagnostic
            import json
            report=diagnose_equipment_project(self.project,Path(path))
            folder=self.project.folder/'exportacao'
            folder.mkdir(parents=True,exist_ok=True)
            dest=folder/'diagnostico_equip_ps1.json'
            dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',
                            encoding='utf-8')
            desc=describe_equip_diagnostic(report) + f'\n\nRelatório salvo em: {dest}'
            if (not report['sete_tabelas_iguais'] or
                any(row['resultado']=='NAO_GRAVADO' for row in report['comparacoes'])):
                messagebox.showwarning('Equip não gravado corretamente',desc,parent=self)
            else:
                messagebox.showinfo('Equip presente no BIN — falta validar no jogo',desc,parent=self)
            self._update_status('Diagnóstico Equip salvo: '+str(dest))
        except (OSError,ModError,ValueError,DiscError) as exc:
            messagebox.showerror('Diagnóstico do Equip',str(exc),parent=self)

    def verify_disc(self):
        if self._extract_running or not self._ensure_project():
            return
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve primeiro', 'Salve o projeto antes de verificar o disco.', parent=self)
            return
        selected = filedialog.askopenfilename(
            title='Selecione o BIN/CUE que você realmente abriu no ePSXe',
            filetypes=[('PlayStation BIN/CUE','*.bin *.cue'),('Todos arquivos','*.*')],
            parent=self)
        if not selected:
            return
        try:
            from .disc_verify import verify_image_stats, describe
            report = verify_image_stats(self.project, selected)
            import json
            destination = self.project.folder / 'exportacao' / 'verificacao_bin_ps1.json'
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n',
                                   encoding='utf-8')
            info = describe(report) + f'\n\nRelatório: {destination}'
            god24_unpatched=report['god24_teste_bau_ativado_no_projeto'] and (
                report['god24_mascaras_bau']['status']!='aplicado_2_de_2'
                or report['god24_renderizador_lista_bau']['god24_patch_lista']
                ['status']!='aplicado_3_de_3'
                or report['god24_exibicao_tipo']['status']!='aplicado'
                or report['god24_roteamento_duelo']['status']!='aplicado')
            opening_lock = report['edicao_do_mod_ps1']['bloqueio_turno_inicial']
            if (report['divergentes'] or not report['god24_tipos_conferem'] or god24_unpatched
                    or opening_lock is False or report['efeitos_nativos_ps1']['status']=='divergente'):
                messagebox.showwarning('BIN/CUE diverge do projeto',info,parent=self)
            else:
                messagebox.showinfo('BIN/CUE conferido (teste no ePSXe pendente)',
                                    info,parent=self)
            self._update_status('Verificação salva: ' + str(destination))
        except (OSError, ValueError, ModError, DiscError) as exc:
            messagebox.showerror('Falha na verificação do disco', str(exc), parent=self)

    def check_updates(self):
        """Consulta GitHub Releases fora da thread da interface."""
        if self._extract_running:
            messagebox.showinfo('Extração em andamento','Conclua a extração antes de instalar outra versão.',parent=self)
            return
        self.update_button.state(['disabled'])
        self.update_button.configure(text='Consultando...')
        self._update_status('Verificando novas versões no GitHub Releases...')

        def worker():
            try:
                result = ('ok', read_latest())
            except Exception as exc:
                result = ('erro', f'Não foi possível verificar atualizações: {exc}')
            self._update_messages.put(result)

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, self._receive_update)

    def _receive_update(self):
        try:
            status, value = self._update_messages.get_nowait()
        except queue.Empty:
            self.after(150, self._receive_update)
            return
        self.update_button.state(['!disabled'])
        self.update_button.configure(text='⟳ Atualizar')
        if status != 'ok':
            self._update_status('Falha ao consultar atualizações.')
            messagebox.showwarning('Atualização', value, parent=self)
            return
        if value is None:
            self._update_status(f'Versão v{__version__} está atualizada.')
            messagebox.showinfo('Atualização', f'FM Mod Studio v{__version__}: nenhuma versão estável mais recente.', parent=self)
            return
        release = value
        notes = (release.notes[:1600] + '\n...') if len(release.notes) > 1600 else release.notes
        reply = messagebox.askyesno('Nova versão disponível',
            f'Nova versão: {release.version}\n\n{notes}\n\n'
            'Baixar e instalar automaticamente pelo GitHub?\n'
            'Não será necessário baixar ZIP manualmente.\n'
            'Projetos e backups serão preservados.',parent=self)
        if not reply or not self._confirm_switch():
            self._update_status('Atualização cancelada pelo usuário.')
            return
        try:
            start_updater(release)
        except (OSError, UpdateError) as exc:
            messagebox.showerror('Não foi possível atualizar',str(exc),parent=self)
            return
        self._update_status('Atualizador externo iniciado. O editor será reiniciado após instalar.')
        self.destroy()

    def _on_close(self):
        if self._busy:
            return
        if self._extract_running:
            messagebox.showwarning("Extração em andamento","A extração está em curso. Aguarde a mensagem de conclusão para não interromper a escrita dos arquivos.",parent=self)
            return
        if self._confirm_switch():
            self._save_prefs()
            self.destroy()

    def _save_prefs(self):
        try:
            zoomed = self.state() == 'zoomed'
        except tk.TclError:
            zoomed = False
        self.prefs['maximizada'] = zoomed
        if not zoomed:
            self.prefs['geometria'] = self.geometry()
        self._remember_library_width()
        ui_prefs.save(self.prefs)


def run():
    try:
        Studio().mainloop()
    except tk.TclError as exc:
        print('Erro na interface Tkinter:',exc,file=sys.stderr)
        raise
