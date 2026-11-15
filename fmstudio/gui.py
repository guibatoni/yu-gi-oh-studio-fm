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
from .core import Project, ModError, EVENTS, ACTIONS, TARGETS, SCOPES, FIELDS, DEFAULT_NAME_COLOR, ONCE_ACTIONS
from .drafts import DraftSession
from .disc import DiscError
from .tables import TYPE_NAMES, ATTR_NAMES, STAR_NAMES
from .continuous import EFFECT_ACTIONS, EQUIPMENT_ACTIONS
from .abilities import QUICK_ACTIONS, BOOLEAN_ACTIONS, quick_settings
from . import __version__
from .rarities import RARITIES, DEFAULT_RARITY, name_style, rarity_options
from .expanded import display_name, bonus_description, resolve_references
from .richtext import NATIVE_ICONS, CUSTOM_ICONS, TEXT_COLORS, tokens
from .updates import read_latest, start_updater, UpdateError

BG = '#0d1220'
SURFACE = '#171f32'
SURFACE2 = '#212c44'
TEXT = '#f2f5fb'
MUTED = '#a8b5cb'
ACCENT = '#32cfb4'
BLUE = '#589bfa'
BORDER = '#344259'


def format_id(cid):
    return f'#{cid:03d}'


def caption_key(mapping, key):
    return mapping.get(key, key)


class EffectDialog(tk.Toplevel):
    """Editor guiado de gatilhos, auras, efeitos por deck e equipamentos."""
    def __init__(self, master, on_save):
        super().__init__(master)
        self.on_save=on_save
        self.title('Criar efeito — Studio FM')
        self.configure(bg=BG)
        self.geometry('610x690')
        self.minsize(565,650)
        self.transient(master)
        self.grab_set()
        form=ttk.Frame(self,padding=20)
        form.pack(fill='both',expand=True)
        self.vars={}
        self.combos={}
        self.sources={'evento':{k:v for k,v in EVENTS.items() if k != 'regra_deck'},
                      'acao':{k:v for k,v in ACTIONS.items() if k not in QUICK_ACTIONS and k != 'bonus_por_carta_id'},
                      'alvo':TARGETS,'escopo':SCOPES}
        row=0
        for key,label in [('evento','Quando ativa'),('acao','O que acontece'),('alvo','Alvo do efeito')]:
            ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',pady=(0,3));row+=1
            source=self.sources[key]
            v=tk.StringVar(value=next(iter(source)))
            self.vars[key]=v
            combo=ttk.Combobox(form,state='readonly',width=60,values=[f'{k} — {t}' for k,t in source.items()])
            combo.current(0)
            combo.grid(row=row,column=0,sticky='ew',pady=(0,9));row+=1
            combo.bind('<<ComboboxSelected>>',lambda e,k=key,c=combo:self._choice(k,list(self.sources[k])[c.current()]))
            self.combos[key]=combo
        ttk.Label(form,text='X pontos (ATK, LP, dano ou cartas descartadas)').grid(row=row,column=0,sticky='w');row+=1
        self.vars['valor']=tk.StringVar(value='500')
        self.value_entry=ttk.Entry(form,textvariable=self.vars['valor'],width=60)
        self.value_entry.grid(row=row,column=0,sticky='ew',pady=(3,9));row+=1
        ttk.Label(form,text='X pontos de DEF (auras e bônus contínuos)').grid(row=row,column=0,sticky='w');row+=1
        self.vars['valor_def']=tk.StringVar(value='0')
        self.def_entry=ttk.Entry(form,textvariable=self.vars['valor_def'],width=60,state='disabled')
        self.def_entry.grid(row=row,column=0,sticky='ew',pady=(3,9));row+=1
        ttk.Label(form,text='Tipo afetado / contado').grid(row=row,column=0,sticky='w');row+=1
        self.vars['tipo_id']=tk.IntVar(value=-1)
        options=[(-1,'Todos os tipos')]+[(i,name) for i,name in enumerate(TYPE_NAMES[:25])]
        self.type_ids=[i for i,_ in options]
        self.type_combo=ttk.Combobox(form,state='disabled',width=60,values=[f'{i:02d} — {label}' for i,label in options])
        self.type_combo.current(0)
        self.type_combo.grid(row=row,column=0,sticky='ew',pady=(3,9));row+=1
        self.type_combo.bind('<<ComboboxSelected>>',lambda e:self.vars['tipo_id'].set(self.type_ids[self.type_combo.current()]))
        ttk.Label(form,text='Quem participa da aura / contagem').grid(row=row,column=0,sticky='w');row+=1
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
        ttk.Button(buttons,text='Adicionar efeito',style='Accent.TButton',command=self._submit).pack(side='left')
        form.columnconfigure(0,weight=1)
        self._refresh_controls()
        self.bind('<Escape>',lambda e:self.destroy())
        self.wait_visibility()
        self.focus_force()

    def _set(self,key,value):
        self.vars[key].set(value)
        self.combos[key].current(list(self.sources[key]).index(value))

    def _choice(self,key,value):
        self.vars[key].set(value)
        action=self.vars['acao'].get()
        if key=='evento':
            if value=='continuo' and action not in EFFECT_ACTIONS:
                self._set('acao','aura_tipo')
            elif value=='equipado' and action not in EQUIPMENT_ACTIONS:
                self._set('acao','equip_atk')
            elif value not in ('continuo','equipado') and action in EFFECT_ACTIONS|EQUIPMENT_ACTIONS:
                self._set('acao','aumentar_atk')
        if key=='acao':
            if value in EFFECT_ACTIONS:
                self._set('evento','continuo')
            elif value in EQUIPMENT_ACTIONS:
                self._set('evento','equipado')
            elif value in ONCE_ACTIONS:
                self._set('evento','invocar')
            elif self.vars['evento'].get() in ('continuo','equipado'):
                self._set('evento','invocar')
        action=self.vars['acao'].get()
        if key=='acao' and action=='descartar_alvo':
            self.vars['valor'].set('1')
        required={
            'aura_tipo':'aliados_tipo', 'bonus_por_tipo':'proprio', 'bonus_deck_tipo':'proprio', 'bonus_cemiterio_tipo':'proprio',
            'cura_lp_deck_tipo':'proprio', 'dano_lp_deck_tipo':'inimigo',
            'descartar_alvo':'inimigo','dano_monstro_alvo':'monstro_alvo',
            'equip_imune_armadilha':'monstro_equipado',
            'equip_imune_magia_armadilha':'monstro_equipado',
            'equip_indestrutivel':'monstro_equipado','equip_atk':'monstro_equipado'}
        if action in required:
            self._set('alvo',required[action])
        elif self.vars['alvo'].get() in ('aliados_tipo','monstro_alvo','monstro_equipado'):
            self._set('alvo','proprio')
        self._refresh_controls()

    def _refresh_controls(self):
        action=self.vars['acao'].get()
        continuous=action in EFFECT_ACTIONS
        typ=continuous or action in ('cura_lp_deck_tipo','dano_lp_deck_tipo')
        protection=action in (EQUIPMENT_ACTIONS-{'equip_atk'})
        self.def_entry.configure(state='normal' if continuous else 'disabled')
        self.type_combo.configure(state='readonly' if typ else 'disabled')
        self.scope_combo.configure(state='readonly' if continuous else 'disabled')
        if protection:
            self.vars['valor'].set('0')
        elif self.vars['valor'].get()=='0' and not continuous:
            self.vars['valor'].set('500' if action!='descartar_alvo' else '1')
        self.value_entry.configure(state='disabled' if protection else 'normal')
        if action=='bonus_cemiterio_tipo':
            help_text='Bônus contínuo: +X ATK e +Y DEF por cada carta do TIPO no cemitério. Atualiza quando cartas morrem ou saem do cemitério.'
        elif action=='bonus_deck_tipo':
            help_text='Bônus contínuo X vezes o número de cartas do tipo no deck configurado (máximo 40). Não acumula a cada turno.'
        elif action in EFFECT_ACTIONS:
            help_text='Auras são recalculadas ao mudar o campo. "Todos os tipos" inclui qualquer criatura; posição e lado dependem do escopo.'
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
        self.help.configure(text=help_text+' Nenhum efeito é gravado no BIN nesta versão.')

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
    def __init__(self, master, cards, on_save):
        super().__init__(master)
        self.title('Efeito por carta específica')
        self.geometry('590x460')
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
        ttk.Label(pane,text='Contar cartas em:').pack(anchor='w')
        self.origin=tk.StringVar(value='campo')
        for label,val in [('Campo (somente viradas para cima)','campo'),('Deck completo configurado','deck')]:
            ttk.Radiobutton(pane,text=label,value=val,variable=self.origin).pack(anchor='w',pady=3)
        ttk.Label(pane,text='Escopo:').pack(anchor='w',pady=(7,3))
        self.scope=tk.StringVar(value='aliados')
        scope=ttk.Combobox(pane,textvariable=self.scope,values=['aliados','inimigos','todos'],state='readonly')
        scope.pack(fill='x',pady=(0,12))
        row=ttk.Frame(pane);row.pack(fill='x')
        self.attack=tk.StringVar(value='200');self.defense=tk.StringVar(value='0')
        for key,v in [('ATK por cópia',self.attack),('DEF por cópia',self.defense)]:
            block=ttk.Frame(row);block.pack(side='left',padx=(0,16))
            ttk.Label(block,text=key).pack(anchor='w');ttk.Entry(block,width=15,textvariable=v).pack()
        ttk.Label(pane,text='A descrição exibirá o NOME da carta, não o ID.\nO efeito será simulado; não será escrito no BIN do PS1.',
                  foreground='#edc47e').pack(anchor='w',pady=14)
        buttons=ttk.Frame(pane);buttons.pack(fill='x')
        ttk.Button(buttons,text='Cancelar',command=self.destroy).pack(side='left')
        ttk.Button(buttons,text='Adicionar efeito + texto',style='Accent.TButton',command=self.submit).pack(side='right')
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
                   'valor_def':int(self.defense.get())}
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
        self._loading = False
        self._update_messages = queue.Queue()
        self._extract_messages = queue.Queue()
        self._extract_running = False
        self.preview_img = None
        self.vars = {}
        self._style()
        self._build()
        self.filter.trace_add('write',lambda *_:self._refresh_cards())
        self.bind('<Control-s>',lambda _ : self.save_project())
        self.bind('<Control-o>',lambda _ : self.open_project())
        self.protocol('WM_DELETE_WINDOW',self._on_close)

    def _style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', font=('Segoe UI',10), background=BG, foreground=TEXT, fieldbackground=SURFACE, bordercolor=BORDER)
        s.configure('TFrame',background=BG)
        s.configure('TLabel',background=BG,foreground=TEXT)
        s.configure('TButton',background=SURFACE2,foreground=TEXT,padding=(12,9),relief='flat')
        s.map('TButton',background=[('active','#354562')])
        s.configure('Accent.TButton',background=ACCENT,foreground='#06171a',font=('Segoe UI',10,'bold'))
        s.map('Accent.TButton',background=[('active','#60e2cb')])
        s.configure('TEntry',fieldbackground=SURFACE,foreground=TEXT,padding=(7,8),insertcolor=TEXT)
        s.configure('TCombobox',fieldbackground=SURFACE,foreground=TEXT,selectbackground=SURFACE2,padding=(7,7))
        s.map('TCombobox',fieldbackground=[('readonly',SURFACE)],foreground=[('readonly',TEXT)])
        s.configure('TNotebook',background=BG,borderwidth=0)
        s.configure('TNotebook.Tab',background=SURFACE2,foreground=MUTED,padding=(16,11))
        s.map('TNotebook.Tab',background=[('selected',SURFACE)],foreground=[('selected',ACCENT)])
        s.configure('Treeview',background=SURFACE,fieldbackground=SURFACE,foreground=TEXT,rowheight=30,borderwidth=0)
        s.map('Treeview',background=[('selected','#265b67')],foreground=[('selected',TEXT)])
        s.configure('Treeview.Heading',background=SURFACE2,foreground=TEXT,font=('Segoe UI',9,'bold'),relief='flat')
        s.configure('TScrollbar',background=SURFACE2,troughcolor=BG)

    def _build(self):
        header = tk.Frame(self,bg=SURFACE,padx=18,pady=13)
        header.pack(fill='x')
        tk.Label(header,text='FM',font=('Segoe UI',25,'bold'),bg=SURFACE,fg=ACCENT).pack(side='left')
        titleframe = tk.Frame(header,bg=SURFACE)
        titleframe.pack(side='left',padx=10)
        tk.Label(titleframe,text='STUDIO CARD FM',font=('Segoe UI',16,'bold'),bg=SURFACE,fg=TEXT).pack(anchor='w')
        tk.Label(titleframe,text='Forbidden Memories  •  PlayStation 1  •  Windows',font=('Segoe UI',9),bg=SURFACE,fg=MUTED).pack(anchor='w')
        self.proj_title = tk.Label(header,text='Nenhum projeto aberto',font=('Segoe UI',10),bg=SURFACE,fg=MUTED)
        self.proj_title.pack(side='right')
        self.update_button = ttk.Button(header, text='⟳ Atualizar', command=self.check_updates)
        self.update_button.pack(side='right',padx=(0,16))

        bar = ttk.Frame(self)
        bar.pack(fill='x',padx=15,pady=12)
        for name,action,style in [('Novo projeto',self.new_project,None),('Abrir projeto',self.open_project,None),
                ('Importar CSVs',self.import_csv,None),('Importar BIN / CUE',self.import_bin,None),
                ('Extrair máximo',self.extract_max,'Accent.TButton'),
                ('Vincular SLUS',self.attach_slus,None),('Salvar projeto',self.save_project,'Accent.TButton'),
                ('Exportar alterações',self.export,None),
                ('Gerar jogo BIN/CUE',self.build_disc,'Accent.TButton')]:
            ttk.Button(bar,text=name,command=action,style=style).pack(side='left',padx=(0,7))
        self.status = tk.StringVar(value='Crie um projeto e importe o CSV ou uma imagem BIN/CUE do jogo.')
        tk.Label(self,textvariable=self.status,bg=SURFACE,fg=MUTED,anchor='w',padx=18,pady=7).pack(side='bottom',fill='x')
        outer = ttk.Frame(self)
        outer.pack(fill='both',expand=True,padx=15,pady=(0,7))

        sidebar = tk.Frame(outer,bg=SURFACE,width=345)
        sidebar.pack(side='left',fill='y',padx=(0,12))
        sidebar.pack_propagate(False)
        tk.Label(sidebar,text='BIBLIOTECA DE CARTAS',bg=SURFACE,fg=TEXT,font=('Segoe UI',11,'bold')).pack(anchor='w',padx=14,pady=(17,8))
        ttk.Button(sidebar,text='+ Criar nova carta (ID acima de 722)',command=self.add_new_card).pack(fill='x',padx=12,pady=(0,9))
        search = ttk.Entry(sidebar,textvariable=self.filter)
        search.pack(fill='x',padx=12,pady=(0,10))
        search.insert(0,'')
        tk.Label(sidebar,text='Pesquisar por ID ou nome da carta',bg=SURFACE,fg=MUTED,font=('Segoe UI',9)).pack(anchor='w',padx=14,pady=(0,8))
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
        self.count_label = tk.Label(sidebar,text='Importe suas tabelas para começar',bg=SURFACE,fg=MUTED,font=('Segoe UI',9))
        self.count_label.pack(anchor='w',padx=14,pady=(0,5))
        self.pending_label = tk.Label(sidebar,text='Nenhuma edição pendente',bg=SURFACE,fg=MUTED,font=('Segoe UI',9,'bold'))
        self.pending_label.pack(anchor='w',padx=14,pady=(0,13))

        main = ttk.Frame(outer)
        main.pack(side='left',fill='both',expand=True)
        self.tabs = ttk.Notebook(main)
        self.tabs.pack(fill='both',expand=True)
        self.tab_cards = ttk.Frame(self.tabs)
        self.tab_effects = ttk.Frame(self.tabs)
        self.tab_fusions = ttk.Frame(self.tabs)
        self.tab_proj = ttk.Frame(self.tabs)
        self.tab_extract = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_cards,text='  Cartas  ')
        self.tabs.add(self.tab_effects,text='  Efeitos  ')
        self.tabs.add(self.tab_fusions,text='  Fusões originais  ')
        self.tabs.add(self.tab_proj,text='  Projeto / Exportação  ')
        self.tabs.add(self.tab_extract,text='  Dados extraídos  ')
        self._cards_tab()
        self._effects_tab()
        self._fusions_tab()
        self._project_tab()
        self._extract_tab()


    def _form_entry(self,parent,label,key,row,width=22,kind='text'):
        ttk.Label(parent,text=label).grid(row=row*2,column=0,sticky='w',padx=(0,12),pady=(9,2))
        if kind=='text':
            var=tk.StringVar()
            entry=ttk.Entry(parent,textvariable=var,width=width)
        else:
            choices={'type':TYPE_NAMES,'attr':ATTR_NAMES,'star':STAR_NAMES}[kind]
            vals=[f'{i:02d} — {v or "Nenhuma"}' for i,v in enumerate(choices)]
            var=tk.StringVar()
            entry=ttk.Combobox(parent,values=vals,state='readonly',width=width,textvariable=var)
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

        tk.Label(body,text='EDITOR DE CARTAS',bg=BG,fg=TEXT,font=('Segoe UI',16,'bold')).pack(anchor='w')
        tk.Label(body,text='Alterações de ATK/DEF, tipo, nível, atributo e estrelas podem gerar um SLUS auxiliar; nomes e descrições ainda são metadados.',
                 bg=BG,fg=MUTED,font=('Segoe UI',9),wraplength=780,justify='left').pack(anchor='w',pady=(4,12))
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
        self.preview_type=self.preview.create_text(128,222,text='TIPO • ATRIBUTO',fill=TEXT,font=('Segoe UI',9))
        self.preview_stats=self.preview.create_text(128,274,text='ATK: —   DEF: —',fill=TEXT,font=('Segoe UI',12,'bold'))
        form=tk.Frame(top,bg=BG)
        form.pack(side='left',fill='both',expand=True)
        self.selected_caption=tk.Label(form,text='Selecione uma carta à esquerda',bg=BG,fg=ACCENT,font=('Segoe UI',12,'bold'))
        self.selected_caption.pack(anchor='w',pady=(0,10))
        grid=ttk.Frame(form)
        grid.pack(fill='x')
        grid.columnconfigure(0,weight=1)
        grid.columnconfigure(1,weight=1)
        left=ttk.Frame(grid)
        right=ttk.Frame(grid)
        left.grid(row=0,column=0,sticky='nsew')
        right.grid(row=0,column=1,sticky='nsew')
        self._form_entry(left,'Nome personalizado','nome',0)
        self._form_entry(left,'Ataque (múltiplos de 10)','ataque',1)
        self._form_entry(left,'Defesa (múltiplos de 10)','defesa',2)
        self._form_entry(left,'Tipo','tipo_id',3,kind='type')
        self._form_entry(right,'Atributo','atributo_id',0,kind='attr')
        self._form_entry(right,'Nível (0 a 15)','nivel',1)
        self._form_entry(right,'Guardian Star 1','guardian_1_id',2,kind='star')
        self._form_entry(right,'Guardian Star 2','guardian_2_id',3,kind='star')
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
        self.color_sample=tk.Label(color_line,text='  ■  ',bg=BG,fg=RARITIES[DEFAULT_RARITY][1],
                                   font=('Segoe UI',13,'bold'))
        self.color_sample.pack(side='left')
        self.class_caption=tk.Label(form,text='Classe: Comum',bg=BG,fg=MUTED,font=('Segoe UI',9))
        self.class_caption.pack(anchor='w',pady=(5,0))
        tk.Label(form,text='Magic: verde • Trap: rosa • Equip: azul • God: azul-marinho. '
                           'A escolha vale para nomes no Studio; o PS1 ainda não foi modificado.',
                 bg=BG,fg=MUTED,font=('Segoe UI',9),wraplength=465,justify='left').pack(anchor='w',pady=(3,0))
        ttk.Button(form,text='Importar arte PNG (prévia)',command=self.import_art).pack(anchor='w',pady=(9,0))
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
        tk.Label(body,text='Gatilhos personalizados continuam simulados. Apenas a compatibilidade de Equip original pode ser gravada no PS1 nesta versão.',
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
                                (proposed.isdigit() and len(proposed) <= 4)))
        ttk.Entry(line,width=9,textvariable=self.quick_vars['custo_lp'],
                  validate='key',validatecommand=(validate,'%P')).pack(side='left')
        self.quick_vars['custo_lp'].trace_add('write',lambda *_:self._on_quick_changed())
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
        tk.Label(quick,text='Até 40 cartas no deck; “Sem limite” remove apenas a restrição de 3 cópias. Salve pelo botão no topo.',
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
        buttons=ttk.Frame(body)
        buttons.pack(fill='x',pady=12)
        ttk.Button(buttons,text='+ Adicionar efeito',style='Accent.TButton',command=self.add_effect).pack(side='left')
        ttk.Button(buttons,text='+ Bônus por carta',command=self.add_specific_effect).pack(side='left',padx=8)
        ttk.Button(buttons,text='Remover efeito selecionado',command=self.remove_effect).pack(side='left',padx=8)
        ttk.Button(buttons,text='PS1: permitir Equip em criatura',command=self.allow_native_equip).pack(side='left',padx=8)
        ttk.Button(buttons,text='PS1: trocar alvo Equip',command=self.replace_native_equip).pack(side='left',padx=8)
        ttk.Button(buttons,text='PS1: usar adições automáticas',command=self.activate_equip_additions).pack(side='left',padx=8)
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
        tk.Label(body,text='IMPORTANTE: SLUS auxiliar ≠ BIN jogável. Efeitos inéditos ainda não são interpretados pelo jogo.\n'
                 'A cópia de teste permite atributos, textos, artes e alvos de Equip stock. Efeitos inéditos NÃO funcionam no PS1.',
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
        if self.project.cards and (self.project.edits or self.project.effects):
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
        # O campo legado fica sincronizado quando a classe/tipo for alterado.
        if self.vars['cor_nome'].get() != color:
            self.vars['cor_nome'].set(color)
        self._on_card_field_input()

    def _on_card_field_input(self):
        if self._loading or not self.drafts or not self.selected_id:
            return
        self._stage_current()
        _label,color,kind=self._apply_name_color_preview()
        # Atualização leve da linha (sem recriar a Treeview durante digitação).
        iid=str(self.selected_id)
        if self.tree.exists(iid):
            row=self.drafts.get_card(self.selected_id)
            tag=f'classe_{kind}'
            self.tree.tag_configure(tag,foreground=color,
                                    background='#EAF0FA' if kind=='deus' else SURFACE)
            self.tree.item(iid,values=(f'{self.selected_id:03d}',
                 (row.get('nome') or '(nome não extraído)') + (' •' if self.selected_id in self.drafts.cards else ''),
                 row.get('ataque',''),row.get('defesa','')),tags=(tag,))
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
        for row in self.tree.get_children():
            self.tree.delete(row)
        if not self.project or not self.project.cards:
            self.count_label.configure(text='Nenhuma carta importada')
            return
        q=self.filter.get().lower().strip()
        count=0
        for cid in sorted(self.project.cards):
            c=self.drafts.get_card(cid) if self.drafts else self.project.get(cid)
            title=c.get('nome') or '(nome não extraído)'
            if q and q not in f'{cid:03d}' and q not in title.lower() and q not in f'#{cid:03d}':
                continue
            flag=' •' if self.drafts and cid in self.drafts.cards else (' ✎' if str(cid) in self.project.edits else '')
            _label,color,kind=name_style(c)
            tag=f'classe_{kind}'
            self.tree.tag_configure(tag,foreground=color,
                                    background='#EAF0FA' if kind=='deus' else SURFACE)
            self.tree.insert('','end',iid=str(cid),values=(f'{cid:03d}',title+flag,c['ataque'],c['defesa']),tags=(tag,))
            count+=1
        self.count_label.configure(text=f'{count} cartas exibidas  •  {len(self.project.cards)} carregadas')
        if keep and self.tree.exists(keep):
            self.tree.selection_set(keep)
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
                n=int(c[key]); self.vars[key].set(f'{n:02d} — {(lookup[n] if n<len(lookup) else '(não mapeado)') or "Nenhuma"}')
            else:
                self.vars[key].set(str(c.get(key,'') or ''))
        self.description.edit_modified(False)
        self._loading=False
        _label,color,_kind=self._apply_name_color_preview()
        ident=format_id(self.selected_id)
        self.selected_caption.configure(text=f'{ident}  {c.get("nome") or "Nome ainda não extraído"}')
        self.preview.itemconfigure(self.preview_name,text=(c.get('nome') or ident)[:42].upper(),fill=color)
        self.preview.itemconfigure(self.preview_type,text=f'{TYPE_NAMES[int(c["tipo_id"])] if int(c["tipo_id"])<len(TYPE_NAMES) else "Tipo não mapeado"} • {ATTR_NAMES[int(c["atributo_id"])] if int(c["atributo_id"])<len(ATTR_NAMES) else "Atributo não mapeado"}')
        self.preview.itemconfigure(self.preview_stats,text=f'ATK {c["ataque"]}   DEF {c["defesa"]}')
        self._load_art()
        self.render_description()
        self._refresh_effects()
        self._refresh_fusions()
        self._update_status(f'Carta {ident} selecionada • alterações pendentes na memória até Salvar projeto')

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
        self._update_pending_label()
        self._update_status(f'Projeto salvo! {count} carta(s) alterada(s), com backup do projeto.json.')
        return True

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
            self.drafts.set_quick_abilities(self.selected_id, settings)
        except ModError as exc:
            self._update_status(f'Habilidade inválida: {exc}')
            return
        self._refresh_effects(skip_quick=True)
        self._update_pending_label()
        self._update_status('Habilidades alteradas. Clique Salvar projeto ou pressione Ctrl+S.')

    def _load_quick_settings(self, effects):
        self._loading_quick=True
        try:
            values=quick_settings(effects)
            for key,variable in self.quick_vars.items():
                variable.set(values[key])
        finally:
            self._loading_quick=False

    def _refresh_effects(self, *, skip_quick=False):
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
                label,caption_key(TARGETS,eff['alvo']),
                ('Todos' if eff.get('tipo_id') == -1 else TYPE_NAMES[eff['tipo_id']] if 'tipo_id' in eff and 0 <= eff['tipo_id'] < len(TYPE_NAMES) else '—'),
                eff['valor'],eff.get('valor_def','—')))
        self.sim_result.configure(text='Escolha um gatilho e clique Simular (não executa o PS1).')

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
        if self._extract_running or not self.project or not self.project.cards:
            messagebox.showinfo('Base ausente','Importe primeiro as 722 cartas de referência.',parent=self)
            return
        if self.selected_id:
            self._stage_current()
        try:
            cid=self.project.add_card(self.selected_id or 1)
        except ModError as exc:
            messagebox.showerror('Nova carta',str(exc),parent=self)
            return
        self.filter.set('')
        self._refresh_cards()
        self.selected_id=None
        self.tree.selection_set(str(cid))
        self.tree.see(str(cid))
        self._on_card_select()
        self._update_status(f'Carta #{cid} criada e registrada no projeto (não adicionada ao BIN PS1).')

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
        tk.Label(body,text='NOVOS ÍCONES (prévia; requerem patch de fontes PS1)',bg=BG,fg=ACCENT).pack(anchor='w',pady=8,padx=12)
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
            txt=(f'Projeto: {pr.metadata["nome"]}\n'
                f'Pasta: {pr.folder}\n'
                f'Base: {pr.metadata.get("base_source") or "Não importada"}\n'
                f'Cartas carregadas: {len(pr.cards)}\n'
                f'Fusões originais: {len(pr.fusions)} (somente leitura)\n'
                f'Cartas alteradas e salvas: {len(pr.edits)}\n'
                f'Cartas com alterações pendentes: {self.drafts.count if self.drafts else 0}\n'
                f'Efeitos planejados: {effects}\n'
                f'Modo Equip PS1: {pr.metadata.get("ps1_equip_mode","adicionar")}\n'
                f'Adições de Equip salvas: {sum(len(v) for v in pr.metadata.get("ps1_equip_additions",{}).values())}\n'
                f'Substituições de Equip salvas: {sum(len(v) for v in pr.metadata.get("ps1_equip_replacements",{}).values())}\n'
                f'Artes PNG vinculadas: {len(pr.arts)} (somente prévia)\n'
                f'Extração profunda: {pr.metadata.get("deep_extraction", {}).get("completed", "ainda não realizada")}\n'
                f'Executável SLUS local: {source}\n\n'
                f'Avisos da extração ({len(pr.imported_notes)}):\n{notes}\n\n'
                'FASES DE EXPORTAÇÃO\n'
                '• Estatísticas: SLUS auxiliar se houver executável vinculado.\n'
                '• Nomes, cores e descrições: apenas registro e prévia no Studio.\n'
                '• Efeitos inéditos: simulação; alvos de Equip original: exportáveis ao PS1.\n'
                '• Fusões: imutáveis, com verificação de integridade.\n'
                '• Imagem BIN/CUE jogável: não gerada nesta versão.\n')
        pane.insert('1.0',txt)
        pane.configure(state='disabled')

    def _refresh_all(self):
        self.proj_title.configure(text=self.project.metadata['nome'] if self.project else 'Nenhum projeto aberto')
        self.selected_id=None
        self._refresh_cards()
        if self.project and self.project.cards:
            self.filter.set('')
            item='1' if self.tree.exists('1') else self.tree.get_children()[0]
            self.tree.selection_set(item)
            self.tree.see(item)
            self.selected_id=int(item)
            self._load_card()
        self._refresh_project()
        self._refresh_extract()
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
            messagebox.showwarning('Sem base','Importe as 722 cartas antes da exportação.')
            return
        self._stage_current()
        if self.drafts and self.drafts.is_dirty:
            messagebox.showinfo('Salve antes de exportar',
                'Existem alterações pendentes. Clique Salvar projeto primeiro.',parent=self)
            return
        try:
            folder,manifest=self.project.export()
        except (OSError,ModError,ValueError) as exc:
            messagebox.showerror('Exportação bloqueada',str(exc))
            return
        self._update_status('Alterações exportadas: '+str(folder))
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
        report = audit(self.project)
        if not report['gravavel_hoje']:
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
        from .ps1_compat import audit
        report=audit(self.project)
        pending=report['pendente_de_motor']
        question = ('Será criada ou atualizada a cópia de teste do disco, sem modificar o original.\n'
                    'Mesmo nome de origem: substitui o teste anterior. Outro nome: cria outro arquivo.\n'
                    'Se o ePSXe estiver usando a imagem anterior, feche o jogo antes de substituí-la.\n\n'
                    'Compatível para teste: estatísticas, textos curtos e artes em paleta original.\n'
                    f'PENDÊNCIAS DE MOTOR: {len(pending)}. Novos efeitos, cartas extras e cores de nomes NÃO serão aplicados.\n\n'
                    + ('\n'.join(pending[:3]) + '\n\n' if pending else '') + 'Gerar somente a cópia parcial de teste?')
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
        messagebox.showinfo(f'Imagem de teste {action}',
            f'Imagem de teste {action} com sucesso.\n\n'
            f'BIN: {manifest["bin"]}\nCUE: {manifest["cue"]}\n'
            f'Setores modificados: {manifest["setores_modificados"]}\n\n'
            'No ePSXe, selecione File > Run ISO e a cópia .BIN gerada.\n'
            f'Nomes: {len(manifest["nomes_aplicados"])}; descrições: {len(manifest["descricoes_aplicadas"])}; artes: {len(manifest["artes_aplicadas"])}.\n'
            f'Recursos pendentes: {len(manifest["recursos_pendentes"])}.\n'
            f'Alterações Equip ({manifest.get("modo_equip_ps1","adicionar")}): {len(manifest.get("equipamentos_ps1_aplicados",[]))}.\n'
            f'Método: {manifest.get("estrategia_equip_ps1","não aplicado")}.\n'
            'Efeitos de jogo continuam somente no Studio.',parent=self)
        self._update_status(f'Imagem de teste {action}: {manifest["bin"]}')

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
            if report['divergentes']:
                messagebox.showwarning('BIN/CUE divergente do Studio', info, parent=self)
            else:
                messagebox.showinfo('BIN/CUE conferido', info, parent=self)
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
