"""Interface Windows/Tkinter do FM Mod Studio. Sem dependências externas."""
from __future__ import annotations
import re
import sys
import queue
import threading
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser
from pathlib import Path
from .core import (Project, ModError, EVENTS, ACTIONS, TARGETS, SCOPES, FIELDS, DEFAULT_NAME_COLOR,
                   ONCE_ACTIONS, legacy_god_description_icon_card, ps1_god24_card_ids,
                   ps1_supports_god24)
from .drafts import DraftSession
from .disc import DiscError
from .tables import CARD_COUNT, TYPE_NAMES, ATTR_NAMES, STAR_NAMES, SUPREME
from .continuous import EFFECT_ACTIONS, EQUIPMENT_ACTIONS, SCALING_ACTIONS
from .abilities import QUICK_ACTIONS, BOOLEAN_ACTIONS, quick_settings
from . import __version__
from .rarities import RARITIES, DEFAULT_RARITY, name_style, rarity_options
from .expanded import GOD_TYPE_ID, display_name, bonus_description, resolve_references
from .richtext import NATIVE_ICONS, CUSTOM_ICONS, TEXT_COLORS, tokens
from .updates import read_latest, start_updater, UpdateError
from .guardian import SUPREME_COLOR, guardian_name

BG = '#0d1220'
SURFACE = '#171f32'
SURFACE2 = '#212c44'
TEXT = '#f2f5fb'
MUTED = '#a8b5cb'
ACCENT = '#32cfb4'
BLUE = '#589bfa'
BORDER = '#344259'
ROW_ALT = '#1c263a'


def format_id(cid):
    return f'#{cid:03d}'


def caption_key(mapping, key):
    return mapping.get(key, key)


def effect_target_label(action, target):
    return 'Esta carta' if action in SCALING_ACTIONS else caption_key(TARGETS, target)


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
    }
    def __init__(self, master, on_save, *, initial_effect=None):
        super().__init__(master)
        self.on_save=on_save
        self.initial_effect = dict(initial_effect) if initial_effect is not None else None
        self.title('Editar efeito — Studio FM' if self.initial_effect else 'Criar efeito — Studio FM')
        self.configure(bg=BG)
        self.geometry('610x755')
        self.minsize(565,650)
        self.transient(master)
        self.grab_set()
        form=ttk.Frame(self,padding=20)
        form.pack(fill='both',expand=True)
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
        self.type_combo.bind('<<ComboboxSelected>>',lambda e:self.vars['tipo_id'].set(self.type_ids[self.type_combo.current()]))
        ttk.Label(form,text='Atributo contado').grid(row=row,column=0,sticky='w');row+=1
        self.vars['atributo_id']=tk.IntVar(value=-1)
        self.attribute_combo=ttk.Combobox(form,state='disabled',width=60,values=['Todos',*ATTR_NAMES])
        self.attribute_combo.current(0)
        self.attribute_combo.grid(row=row,column=0,sticky='ew',pady=(3,9));row+=1
        self.attribute_combo.bind('<<ComboboxSelected>>',lambda _e:self.vars['atributo_id'].set(self.attribute_combo.current()-1))
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
        buttons=ttk.Frame(form)
        buttons.grid(row=row,column=0,sticky='e')
        ttk.Button(buttons,text='Cancelar',command=self.destroy).pack(side='left',padx=6)
        ttk.Button(buttons,text='Salvar alterações' if self.initial_effect else 'Adicionar efeito',
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
        self.attribute_combo.current(attr + 1 if 0 <= attr < len(ATTR_NAMES) else 0)
        scope = entry.get('escopo', 'aliados')
        self.vars['escopo'].set(scope)
        self.scope_combo.current(list(SCOPES).index(scope) if scope in SCOPES else 0)
        self._refresh_controls()

    def _choice(self,key,value):
        self.vars[key].set(value)
        action=self.vars['acao'].get()
        if key=='evento':
            if value=='continuo' and action not in EFFECT_ACTIONS and action not in (
                    QUICK_ACTIONS - {'sem_limite_deck', 'limite_copias_deck', 'perder_lp_por_ataque'}):
                self._set('acao','aura_tipo')
            elif value=='equipado' and action not in EQUIPMENT_ACTIONS:
                self._set('acao','equip_atk')
            elif value=='regra_deck' and action not in ('sem_limite_deck','limite_copias_deck'):
                self._set('acao','limite_copias_deck')
            elif value not in ('continuo','equipado','regra_deck') and (
                    action in EFFECT_ACTIONS|EQUIPMENT_ACTIONS or
                    action in QUICK_ACTIONS and not (value=='atacar' and action=='perder_lp_por_ataque')):
                self._set('acao','aumentar_atk')
        if key=='acao':
            if value in EFFECT_ACTIONS or value in QUICK_ACTIONS - {'sem_limite_deck', 'limite_copias_deck', 'perder_lp_por_ataque'}:
                self._set('evento','continuo')
            elif value in EQUIPMENT_ACTIONS:
                self._set('evento','equipado')
            elif value in ('sem_limite_deck','limite_copias_deck'):
                self._set('evento','regra_deck')
            elif value == 'perder_lp_por_ataque':
                self._set('evento','atacar')
            elif value in ONCE_ACTIONS:
                self._set('evento','invocar')
            elif self.vars['evento'].get() in ('continuo','equipado','regra_deck'):
                self._set('evento','invocar')
        action=self.vars['acao'].get()
        if key=='acao' and action=='descartar_alvo':
            self.vars['valor'].set('1')
        if key == 'acao' and action == 'dano_lp':
            self._set('alvo', 'inimigo')
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
        self._refresh_recipient(action)
        counted = action in SCALING_ACTIONS
        self.labels['valor'].configure(
            text='Bônus de ATK por carta contada' if counted else
                 'Bônus de ATK' if continuous else 'X pontos (ATK, LP, dano ou cartas descartadas)')
        self.labels['valor_def'].configure(text='Bônus de DEF por carta contada' if counted else 'Bônus de DEF')
        type_label = {'aura_tipo': 'Tipo de monstro que recebe o bônus',
                      'bonus_por_tipo': 'Tipo contado no campo'}.get(action, 'Tipo contado')
        self.labels['tipo_id'].configure(text=type_label)
        self.labels['escopo'].configure(text='Lados afetados pela aura' if action == 'aura_tipo' else 'Lados que entram na contagem')
        typ=continuous or action in ('cura_lp_deck_tipo','dano_lp_deck_tipo')
        protection=action in (EQUIPMENT_ACTIONS-{'equip_atk'}) or action in BOOLEAN_ACTIONS
        self.def_entry.configure(state='normal' if continuous else 'disabled')
        self.type_combo.configure(state='readonly' if typ else 'disabled')
        self.attribute_combo.configure(state='readonly' if continuous else 'disabled')
        self.scope_combo.configure(state='readonly' if continuous else 'disabled')
        if protection:
            self.vars['valor'].set('0')
        elif self.vars['valor'].get()=='0' and not continuous:
            self.vars['valor'].set('500' if action!='descartar_alvo' else '1')
        self.value_entry.configure(state='disabled' if protection else 'normal')
        if action=='bonus_cemiterio_tipo':
            help_text='Bônus contínuo: +X ATK e +Y DEF por cada carta do TIPO no cemitério. Atualiza quando cartas morrem ou saem do cemitério.'
        elif action=='bonus_deck_tipo':
            help_text='Bônus fixo por carta na composição inicial do deck.'
        elif action=='bonus_mao_tipo':
            help_text='Bônus contínuo por carta na mão. Recalcula após compras, invocações e descartes.'
        elif action=='bonus_por_tipo':
            help_text=('Esta carta recebe o bônus por cada monstro do tipo escolhido no campo. '
                       'Monstros virados para baixo também contam.')
        elif action=='aura_tipo':
            help_text='Cada monstro do tipo escolhido nos lados afetados recebe o bônus, inclusive virado para baixo.'
        elif action in ('cura_lp_deck_tipo','dano_lp_deck_tipo'):
            help_text='X vezes o número de cartas do tipo no deck configurado. Ativado UMA vez ao entrar em campo.'
        elif action=='dano_monstro_alvo':
            help_text='Dano a criatura é experimental: HP simulado começa igual à DEF-base (mínimo 1).'
        elif action=='descartar_alvo':
            help_text='O oponente descarta até X cartas da mão configurada no simulador, uma vez por invocação.'
        elif action in EQUIPMENT_ACTIONS:
            help_text='O efeito se mantém apenas enquanto a carta estiver equipada ao monstro no simulador.'
        else:
            help_text='Efeito ativado; mantenha os testes no simulador antes de planejar implementação no PS1.'
        self.help.configure(text=help_text)

    def _submit(self):
        entry={key:v.get() for key,v in self.vars.items()}
        try:
            self.on_save(entry)
        except (ModError,ValueError) as exc:
            messagebox.showerror('Efeito inválido',str(exc),parent=self)
            return
        self.destroy()


class SpecificCardEffectDialog(tk.Toplevel):
    """Adicionar bônus por carta selecionada sem digitar IDs na descrição."""
    def __init__(self, master, cards, on_save, *, initial_effect=None):
        super().__init__(master)
        self.initial_effect = dict(initial_effect) if initial_effect else None
        self.title('Editar bônus por carta específica' if self.initial_effect
                   else 'Efeito por carta específica')
        self.geometry('590x560')
        self.configure(bg=BG)
        self.transient(master)
        self.grab_set()
        self.cards=cards
        self.on_save=on_save
        pane=ttk.Frame(self,padding=20);pane.pack(fill='both',expand=True)
        ttk.Label(pane,text='Escolha a carta que será contada:').pack(anchor='w',pady=(0,5))
        self.labels={f'{cid:05d} — {display_name(cid,cards)}':cid for cid in sorted(cards)}
        self.selected=tk.StringVar()
        self.combo=ttk.Combobox(pane,textvariable=self.selected,values=list(self.labels),width=62)
        self.combo.pack(fill='x',pady=(0,12))
        if self.labels:self.combo.current(0)
        if self.initial_effect:
            old_ref = int(self.initial_effect.get('carta_referencia_id', 0))
            old_label = next((name for name, cid in self.labels.items() if cid == old_ref), None)
            if old_label is not None:
                self.selected.set(old_label)
        ttk.Label(pane,text='Contar cartas em:').pack(anchor='w')
        self.origin=tk.StringVar(value=self.initial_effect.get('origem_contagem', 'campo')
                                 if self.initial_effect else 'campo')
        for label,val in [('Campo (inclusive cartas viradas para baixo)','campo'),('Monte de compra','deck'),
                          ('Mão','mao'),('Cemitério','cemiterio')]:
            ttk.Radiobutton(pane,text=label,value=val,variable=self.origin).pack(anchor='w',pady=3)
        ttk.Label(pane,text='Escopo:').pack(anchor='w',pady=(7,3))
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
        self.title(f'Yu-Gi-Oh Studio Card FM | v{__version__}')
        self.geometry('1390x825')
        self.minsize(1050,650)
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
        self.bind('<Control-f>', lambda _event: self.focus_catalog())
        self.bind('<Control-s>',lambda _ : self.save_project())
        self.bind('<Control-o>',lambda _ : self.open_project())
        self.protocol('WM_DELETE_WINDOW',self._on_close)

    def _style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', font=('Segoe UI',10), background=BG, foreground=TEXT, fieldbackground=SURFACE, bordercolor=BORDER)
        s.configure('TFrame',background=BG)
        s.configure('TLabel',background=BG,foreground=TEXT)
        for style, resting, hover, pressed, color in (
                ('TButton', SURFACE2, '#354562', '#283852', TEXT),
                ('TMenubutton', SURFACE2, '#354562', '#283852', TEXT),
                ('Accent.TButton', ACCENT, '#60e2cb', '#25a992', '#06171a'),
                ('Danger.TButton', '#3b293b', '#603347', '#4b2939', '#ffd9df')):
            s.configure(style, background=resting, foreground=color, padding=(10, 6), relief='flat')
            s.map(style, background=[('disabled', '#172033'), ('pressed', pressed), ('active', hover)],
                  foreground=[('disabled', '#7f8da5')], bordercolor=[('focus', ACCENT)])
        s.configure('Accent.TButton', font=('Segoe UI',10,'bold'))
        s.configure('TCheckbutton', padding=(5, 5), indicatorbackground=SURFACE2)
        s.map('TCheckbutton', background=[('active', SURFACE2)],
              foreground=[('disabled', '#7f8da5')],
              indicatorbackground=[('selected', ACCENT), ('pressed', '#25a992')])
        s.configure('TSpinbox', fieldbackground=SURFACE, foreground=TEXT, insertcolor=TEXT, padding=(4, 3))
        s.configure('TEntry',fieldbackground=SURFACE,foreground=TEXT,padding=(7,8),insertcolor=TEXT)
        s.configure('TCombobox',fieldbackground=SURFACE,foreground=TEXT,selectbackground=SURFACE2,padding=(7,7))
        s.map('TCombobox',fieldbackground=[('readonly',SURFACE)],foreground=[('readonly',TEXT)])
        s.configure('TNotebook',background=BG,borderwidth=0)
        s.configure('TNotebook.Tab',background=SURFACE2,foreground=MUTED,padding=(10, 8))
        s.map('TNotebook.Tab',background=[('selected',SURFACE),('active','#354562')],
              foreground=[('selected',ACCENT),('active',TEXT)])
        s.configure('Treeview',background=SURFACE,fieldbackground=SURFACE,foreground=TEXT,rowheight=27,borderwidth=0)
        s.map('Treeview',background=[('selected','#265b67')],foreground=[('selected',TEXT)])
        s.configure('Treeview.Heading',background=SURFACE2,foreground=TEXT,font=('Segoe UI',9,'bold'),relief='flat')
        s.configure('TScrollbar',background=SURFACE2,troughcolor=BG)
        s.configure('TLabelframe', background=BG, bordercolor=BORDER)
        s.configure('TLabelframe.Label', background=BG, foreground=ACCENT)

    def _build(self):
        header = tk.Frame(self,bg=SURFACE,padx=14,pady=9)
        header.pack(fill='x')
        tk.Label(header,text='FM',font=('Segoe UI',25,'bold'),bg=SURFACE,fg=ACCENT).pack(side='left')
        titleframe = tk.Frame(header,bg=SURFACE)
        titleframe.pack(side='left',padx=10)
        tk.Label(titleframe,text='STUDIO CARD FM',font=('Segoe UI',16,'bold'),bg=SURFACE,fg=TEXT).pack(anchor='w')
        tk.Label(titleframe,text='Yu-Gi-Oh! Forbidden Memories',font=('Segoe UI',9),bg=SURFACE,fg=MUTED).pack(anchor='w')
        self.proj_title = tk.Label(header,text='Nenhum projeto aberto',font=('Segoe UI',10),bg=SURFACE,fg=MUTED)
        self.proj_title.pack(side='right')
        self.update_button = ttk.Button(header, text='⟳ Atualizar', command=self.check_updates)
        self.update_button.pack(side='right',padx=(0,16))

        bar = ttk.Frame(self)
        bar.pack(fill='x',padx=12,pady=8)
        for title, options in (
                ('Projeto', [('Novo projeto', self.new_project, None),
                             ('Abrir projeto', self.open_project, 'Ctrl+O')]),
                ('Importar', [('Importar CSVs', self.import_csv, None),
                              ('Importar BIN/CUE', self.import_bin, None),
                              ('Extrair máximo', self.extract_max, None),
                              ('Vincular SLUS', self.attach_slus, None)])):
            group = ttk.Menubutton(bar, text=title)
            menu = self._menu(group)
            for label, action, shortcut in options:
                menu.add_command(label=label, command=action, accelerator=shortcut or '')
            group.configure(menu=menu)
            group.pack(side='left', padx=(0, 5))
        self.save_button = ttk.Button(bar, text='Salvar projeto', style='Accent.TButton',
                                      command=self.save_project, state='disabled')
        self.save_button.pack(side='left', padx=5)
        self.build_button = ttk.Button(bar, text='Gerar jogo BIN/CUE', style='Accent.TButton',
                                       command=self.build_disc, state='disabled')
        self.build_button.pack(side='right')
        self.export_button = ttk.Button(bar, text='Exportar alterações', command=self.export, state='disabled')
        self.export_button.pack(side='right', padx=(0, 5))
        self.status = tk.StringVar(value='Abra ou crie um projeto para editar suas cartas.')
        tk.Label(self,textvariable=self.status,bg=SURFACE,fg=MUTED,anchor='w',padx=14,pady=6).pack(side='bottom',fill='x')
        self.toast = tk.Label(self, bg='#22454a', fg=TEXT, font=('Segoe UI', 10, 'bold'),
                              padx=13, pady=9, wraplength=360, justify='left')
        outer = tk.PanedWindow(self, orient='horizontal', bg=BG, sashwidth=8, bd=0)
        outer.pack(fill='both',expand=True,padx=12,pady=(0,6))

        sidebar = tk.Frame(outer,bg=SURFACE)
        outer.add(sidebar, width=327, minsize=260, stretch='never')
        tk.Label(sidebar,text='BIBLIOTECA DE CARTAS',bg=SURFACE,fg=TEXT,font=('Segoe UI',11,'bold')).pack(anchor='w',padx=14,pady=(17,8))
        self.new_card_button = ttk.Button(sidebar, text='＋ Nova carta', style='Accent.TButton',
                                          command=self.add_new_card, state='disabled')
        self.new_card_button.pack(fill='x',padx=12,pady=(0,7))
        tk.Label(sidebar,text='Buscar por ID ou nome   ·   Ctrl+F',bg=SURFACE,fg=MUTED).pack(anchor='w',padx=12)
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
        self.tree = ttk.Treeview(treeholder,columns=('id','nome','atk','def'),show='headings',selectmode='browse')
        for col,text,width,anchor in [('id','ID',48,'w'),('nome','Nome / identificação',146,'w'),('atk','ATK',56,'e'),('def','DEF',56,'e')]:
            self.tree.heading(col,text=text)
            self.tree.column(col,width=width,anchor=anchor,stretch=(col=='nome'))
        scroll = ttk.Scrollbar(treeholder,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left',fill='both',expand=True)
        scroll.pack(side='right',fill='y')
        self.tree.bind('<<TreeviewSelect>>',self._on_card_select)
        self.tree.bind('<Button-3>', self._card_menu)
        self.tree.bind('<Double-1>', lambda _event: self.tabs.select(self.tab_cards) if self.tree.selection() else None)
        self.card_menu = self._menu(self)
        self.card_menu.add_command(label='Abrir carta', command=lambda: self.tabs.select(self.tab_cards))
        self.card_menu.add_command(label='Adicionar ao deck do oponente', command=self._add_selected_to_deck)
        self.count_label = tk.Label(sidebar,text='Importe suas tabelas para começar',bg=SURFACE,fg=MUTED,font=('Segoe UI',9))
        self.count_label.pack(anchor='w',padx=14,pady=(0,5))
        self.pending_label = tk.Label(sidebar,text='Nenhuma edição pendente',bg=SURFACE,fg=MUTED,font=('Segoe UI',9,'bold'))
        self.pending_label.pack(anchor='w',padx=14,pady=(0,13))

        main = ttk.Frame(outer)
        outer.add(main, minsize=655, stretch='always')
        self.tabs = ttk.Notebook(main)
        self.tabs.pack(fill='both',expand=True)
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

    def _menu(self, parent):
        return tk.Menu(parent, tearoff=False, bg=SURFACE, fg=TEXT, activebackground='#354562',
                       activeforeground=TEXT, relief='flat', borderwidth=1)

    def focus_catalog(self):
        if self.grab_current() is None:
            self.card_search.focus_set()
            self.card_search.selection_range(0, 'end')

    def _card_menu(self, event):
        item = self.tree.identify_row(event.y)
        if not item or self._extract_running:
            return
        self.tree.selection_set(item)
        self.tree.focus(item)
        self._on_card_select()
        try:
            self.card_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.card_menu.grab_release()

    def _add_selected_to_deck(self):
        if self.selected_id is not None:
            self.mod_editor.add_catalog_card(self.selected_id)

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
        ttk.Button(form,text='Importar arte PNG (prévia)',command=self.import_art).pack(anchor='w',pady=(9,0))
        links=ttk.LabelFrame(body,text='Efeitos e relações da carta',padding=8)
        links.pack(fill='x',pady=(10,4))
        ttk.Button(links,text='Efeitos e bônus',command=lambda:self.tabs.select(self.tab_effects)).pack(side='left',padx=(0,5))
        ttk.Button(links,text='Fusões, ritual e equipamentos',command=self.edit_card_rules).pack(side='left',padx=5)
        ttk.Button(links,text='Opções PS1',command=self.open_card_ps1_options).pack(side='right')
        tk.Label(body,text='Descrição com ícones, cores e referências a outras cartas (prévia no Studio)',bg=BG,fg=TEXT,font=('Segoe UI',10)).pack(anchor='w',pady=(12,3))
        desc_tools=ttk.Frame(body)
        desc_tools.pack(fill='x',pady=(0,5))
        ttk.Button(desc_tools,text='Inserir ícone',command=self.choose_description_icon).pack(side='left',padx=(0,6))
        ttk.Button(desc_tools,text='Cor no trecho',command=self.choose_description_color).pack(side='left',padx=(0,6))
        ttk.Button(desc_tools,text='Referenciar carta',command=self.choose_description_reference).pack(side='left')
        self.description=tk.Text(body,height=4,wrap='word',bg=SURFACE,fg=TEXT,insertbackground=TEXT,
                                 selectbackground='#365a73',highlightthickness=1,highlightbackground=BORDER,font=('Segoe UI',10))
        self.description.pack(fill='x')
        tk.Label(body,text='PRÉVIA DA DESCRIÇÃO — cores e ícones (não é a renderização exata do PS1)',bg=BG,fg=MUTED,font=('Segoe UI',9)).pack(anchor='w',pady=(7,3))
        self.description_preview=tk.Text(body,height=5,wrap='word',bg='#182339',fg=TEXT,
            highlightthickness=1,highlightbackground=BORDER,font=('Consolas',11),state='disabled',cursor='arrow')
        self.description_preview.pack(fill='both',expand=True)
        buttons=ttk.Frame(body)
        buttons.pack(fill='x',pady=(12,0))
        ttk.Button(buttons,text='Salvar projeto (todas as cartas)',style='Accent.TButton',command=self.save_project).pack(side='left')
        ttk.Button(buttons,text='Restaurar os valores originais',command=self.reset_card).pack(side='left',padx=9)
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
        tk.Label(body,text='Drop x15: bônus, habilidades rápidas e recuperação/dano de LP ao entrar em campo são exportáveis. Outros gatilhos podem funcionar só no simulador.',
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
        tk.Label(copies,text='Cópias da carta no deck (1–40):',bg=SURFACE,fg=TEXT).pack(side='left')
        self.quick_vars['limite_copias']=tk.StringVar()
        check_copies=(self.register(lambda value: value=='' or (value.isdigit() and len(value)<=2)))
        ttk.Entry(copies,width=5,textvariable=self.quick_vars['limite_copias'],
                  validate='key',validatecommand=(check_copies,'%P')).pack(side='left',padx=7)
        self.quick_vars['limite_copias'].trace_add('write',lambda *_:self._on_quick_changed())
        tk.Label(copies,text='Vazio usa o limite padrão. ∞ permite até 40 cópias.',
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
                                ('tipo','Tipo',75),('atk','ATK',70),('def','DEF',70)]:
            self.effect_tree.heading(key,text=label)
            self.effect_tree.column(key,width=w,stretch=True)
        effects_scroll=ttk.Scrollbar(holder,orient='vertical',command=self.effect_tree.yview)
        self.effect_tree.configure(yscrollcommand=effects_scroll.set)
        effects_scroll.pack(side='right',fill='y')
        self.effect_tree.pack(side='left',fill='x',expand=True,padx=1,pady=1)
        self.effect_tree.bind('<Double-1>',lambda _event:self.edit_effect())
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
        diagnostic=ttk.Frame(body)
        diagnostic.pack(fill='x',pady=(0,6))
        ttk.Button(diagnostic,text='Diagnosticar Equip no BIN/CUE',command=self.diagnose_equip).pack(side='left')
        tk.Label(body,text='IMPORTANTE: SLUS auxiliar ≠ BIN jogável. Gere um BIN/CUE novo depois de salvar efeitos.\n'
                 'No perfil Drop x15, apenas os efeitos suportados pelo relatório são aplicados ao PS1. Verifique o BIN/CUE e teste no ePSXe.',
                 bg=BG,fg='#edc47e',font=('Segoe UI',10),justify='left',wraplength=750).pack(anchor='w',pady=(8,0))

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
        self.status.set(text)
        self.update_idletasks()

    def notify(self, text):
        self._update_status(text)
        if self._toast_timeout is not None:
            self.after_cancel(self._toast_timeout)
        self.toast.configure(text=text)
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
        self._refresh_all()
        self._update_status('Projeto criado. Importe analysis\\tabelas ou selecione a imagem .BIN/.CUE.')

    def open_project(self):
        if self._extract_running:
            messagebox.showinfo("Extração em andamento","Conclua a extração antes de editar, importar ou trocar de projeto.",parent=self)
            return False
        if not self._confirm_switch():
            return
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

    def _refresh_cards(self):
        keep = str(self.selected_id) if self.selected_id else None
        top = self.tree.yview()[0]
        self.tree.delete(*self.tree.get_children())
        if not self.project or not self.project.cards:
            self.count_label.configure(text='Nenhuma carta importada')
            return
        q=self.filter.get().casefold().strip()
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
            if q and q not in title.casefold() and q not in f'#{cid:03d}' and q not in f'#{cid}':
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
        self.count_label.configure(text=f'{count} cartas exibidas  •  {len(self.project.cards)} carregadas')
        if keep and self.tree.exists(keep):
            self.tree.selection_set(keep)
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
        rel = self.project.arts.get(str(self.selected_id))
        if not rel:
            candidate = self.project.folder / 'base' / 'extracao_completa' / 'visuais' / 'cartas' / f'{self.selected_id:03d}.png'
            if not candidate.is_file():return
            path=candidate
        else:
            path = self.project.folder / rel
        try:
            img = tk.PhotoImage(file=str(path))
            factor = max(1, (img.width()+207)//208, (img.height()+131)//132)
            self.preview_img = img.subsample(factor,factor) if factor > 1 else img
            self.preview.itemconfigure(self.art_image,image=self.preview_img)
            self.preview.itemconfigure(self.art_placeholder,state='hidden')
        except (OSError,tk.TclError):
            self.preview.itemconfigure(self.art_placeholder,text='ARTE INDISPONÍVEL')

    def import_art(self):
        if not self.project or not self.selected_id:
            messagebox.showinfo('Selecione uma carta','Escolha uma carta primeiro.')
            return
        path = filedialog.askopenfilename(title='Escolha uma arte PNG',filetypes=[('Imagem PNG','*.png')])
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
        buttons.pack(anchor='e',pady=(5,0))
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
                ('Todos' if eff.get('tipo_id') == -1 else TYPE_NAMES[eff['tipo_id']] if 'tipo_id' in eff and 0 <= eff['tipo_id'] < len(TYPE_NAMES) else '—'),
                eff['valor'],eff.get('valor_def','—')))
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
        def submit(entry):
            self.drafts.add_effect(self.selected_id,entry)
            self._refresh_effects()
            self._refresh_project()
            self._update_pending_label()
            self._update_status(f'Efeito pendente para a carta {format_id(self.selected_id)}. Clique Salvar projeto.')
        EffectDialog(self,submit)

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
        self._refresh_cards()
        if not self.tree.exists(str(cid)):
            self._clear_card_filters()
            self._refresh_cards()
        self.tree.focus(str(cid))
        self.tree.see(str(cid))
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
        for label,command in [('Tipo jogável no PS1',self.choose_playable_monster_type),
                              ('Glifo God na descrição',self.toggle_god_icon_ps1)]:
            ttk.Button(content,text=label,command=command).pack(fill='x',pady=4)

    def insert_description_token(self, token: str):
        if not self.project or not self.selected_id:
            return
        self.description.insert('insert', token)
        self.render_description()
        self._stage_current()
        self._update_pending_label()

    def choose_description_icon(self):
        if not self.project: return
        popup=tk.Toplevel(self);popup.title('Ícones de descrição • 16×16');popup.geometry('590x530')
        popup.configure(bg=BG)
        pane=tk.Frame(popup,bg=BG);pane.pack(fill='both',expand=True)
        cv=tk.Canvas(pane,bg=BG,highlightthickness=0)
        scroll=ttk.Scrollbar(pane,command=cv.yview);scroll.pack(side='right',fill='y')
        cv.pack(side='left',fill='both',expand=True);cv.configure(yscrollcommand=scroll.set)
        body=tk.Frame(cv,bg=BG);wid=cv.create_window((0,0),window=body,anchor='nw')
        body.bind('<Configure>',lambda e:cv.configure(scrollregion=cv.bbox('all')))
        cv.bind('<Configure>',lambda e:cv.itemconfigure(wid,width=e.width))
        popup._icon_refs=[]
        tk.Label(body,text='Ícones do Studio (PS1 no perfil Drop x15)',bg=BG,fg=ACCENT).pack(anchor='w',pady=8,padx=12)
        for name,label in CUSTOM_ICONS.items():
            row=tk.Frame(body,bg=BG);row.pack(fill='x',padx=12,pady=2)
            photo=self.get_icon_image(name)
            if photo: popup._icon_refs.append(photo)
            btn=ttk.Button(row,text=label,command=lambda n=name:(self.insert_description_token('{icon:'+n+'}'),popup.destroy()))
            btn.pack(side='left',fill='x',expand=True)
            if photo: tk.Label(row,image=photo,bg=BG).pack(side='left',padx=8)
        tk.Label(body,text='ÍCONES NATIVOS (códigos F8 já documentados no jogo)',bg=BG,fg=ACCENT).pack(anchor='w',pady=(12,5),padx=12)
        for name,code in NATIVE_ICONS.items():
            ttk.Button(body,text=f'{name}   •   {{f8 0B {code:02X}}}',
                command=lambda code=code:(self.insert_description_token(f'{{f8 0B {code:02X}}}'),popup.destroy())).pack(fill='x',padx=12,pady=1)

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
        value=simpledialog.askstring('Referenciar carta','ID da carta (ex.: 1, 723):',parent=self)
        if not value:return
        try:
            cid=int(value.strip().lstrip('#'))
            if cid not in self.project.cards: raise ValueError()
        except ValueError:
            messagebox.showerror('Referência','Carta não encontrada no projeto.',parent=self);return
        self.insert_description_token(f'{{card:{cid}}}')

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
        if event in ('continuo','equipado','regra_deck','atacar') or any(
                e.get('evento') == event and e.get('acao') in ONCE_ACTIONS
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
        for button in (self.save_button, self.build_button, self.export_button, self.new_card_button):
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
            'ATENÇÃO: efeitos novos e cartas extras ainda não funcionam no PS1.',
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
        question = ('Será criada ou atualizada a cópia de teste do disco, sem modificar o original.\n'
                    'Mesmo nome de origem: substitui o teste anterior. Outro nome: cria outro arquivo.\n'
                    'Se o ePSXe estiver usando a imagem anterior, feche o jogo antes de substituí-la.\n\n'
                    'Consulte as alterações compatíveis no relatório do projeto.\n'
                    + ('Ícone Deus na descrição: três caracteres são trocados só na cópia.\n'
                       if description_icon else '')
                    + (f'God (24): {len(god_cards)} carta(s) com nome, ícone e jogabilidade de monstro.\n'
                       if god_cards else '')
                    + (f'PENDÊNCIAS: {len(pending)}.\n' + '\n'.join(pending[:3]) + '\n\n' if pending else '')
                    + 'Gerar a cópia BIN/CUE de teste?')
        if not messagebox.askyesno('Gerar cópia de teste', question, parent=self):
            return
        try:
            from .disc_build import build_test_disc
            manifest = build_test_disc(self.project, Path(source))
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
        simplified=sum(bool(row.get('acentos_simplificados')) for row in manifest['descricoes_aplicadas'])
        messagebox.showinfo(f'Imagem de teste {action}',
            f'Imagem de teste {action} com sucesso.\n\n'
            f'BIN: {manifest["bin"]}\nCUE: {manifest["cue"]}\n'
            f'Cartas com atributos confirmados no BIN: '
            f'{manifest.get("verificacao_atributos",{}).get("corretas","não disponível")}\n'
            f'Setores modificados: {manifest["setores_modificados"]}\n\n'
            'No ePSXe, selecione File > Run ISO e a cópia .BIN gerada.\n'
            f'Nomes: {len(manifest["nomes_aplicados"])}; descrições: {len(manifest["descricoes_aplicadas"])}; artes: {len(manifest["artes_aplicadas"])}.\n'
            f'Efeitos gravados no PS1: {len(runtime.get("efeitos",[]))}. '
            f'Ícones de descrição: {len(manifest.get("icones_de_descricao_ps1",[]))}.\n'
            + ('Ataque na abertura restrito pela habilidade da carta.\n'
               if mod.get('bloqueio_turno_inicial') else '')
            + (f'Configurações do mod aplicadas: {len(mod["aplicado"])}.\n' if mod.get('aplicado') else '')
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
        if self._extract_running:
            messagebox.showwarning("Extração em andamento","A extração está em curso. Aguarde a mensagem de conclusão para não interromper a escrita dos arquivos.",parent=self)
            return
        if self._confirm_switch():
            self.destroy()


def run():
    try:
        Studio().mainloop()
    except tk.TclError as exc:
        print('Erro na interface Tkinter:',exc,file=sys.stderr)
        raise
