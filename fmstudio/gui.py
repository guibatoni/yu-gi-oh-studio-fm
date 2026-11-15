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
from .core import Project, ModError, EVENTS, ACTIONS, TARGETS, FIELDS, DEFAULT_NAME_COLOR
from .drafts import DraftSession
from .tables import TYPE_NAMES, ATTR_NAMES, STAR_NAMES
from . import __version__
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
    def __init__(self, master, on_save):
        super().__init__(master)
        self.on_save = on_save
        self.title('Adicionar efeito à carta')
        self.configure(bg=BG)
        self.resizable(False,False)
        self.transient(master)
        self.grab_set()
        self.vars = {}
        options = [('evento','Quando acontece', EVENTS),('acao','O que acontece',ACTIONS),('alvo','Quem recebe o efeito',TARGETS)]
        for i,(key,title,source) in enumerate(options):
            ttk.Label(self,text=title).grid(row=i*2,column=0,padx=18,pady=(12,2),sticky='w')
            v = tk.StringVar(value=list(source.keys())[0])
            self.vars[key] = v
            labels = [f'{keyname} — {label}' for keyname,label in source.items()]
            combo = ttk.Combobox(self,width=42,state='readonly',values=labels)
            combo.current(0)
            combo.grid(row=i*2+1,column=0,padx=18,sticky='ew')
            combo.bind('<<ComboboxSelected>>',lambda e,k=key,s=source,c=combo: self.vars[k].set(list(s.keys())[c.current()]))
        ttk.Label(self,text='Valor (pontos)').grid(row=6,column=0,padx=18,pady=(12,2),sticky='w')
        self.vars['valor'] = tk.StringVar(value='500')
        ttk.Entry(self,textvariable=self.vars['valor'],width=44).grid(row=7,column=0,padx=18,sticky='ew')
        ttk.Label(self,text='Observação (opcional)').grid(row=8,column=0,padx=18,pady=(12,2),sticky='w')
        self.vars['observacao'] = tk.StringVar()
        ttk.Entry(self,textvariable=self.vars['observacao'],width=44).grid(row=9,column=0,padx=18,sticky='ew')
        controls = ttk.Frame(self)
        controls.grid(row=10,column=0,padx=18,pady=18,sticky='e')
        ttk.Button(controls,text='Cancelar',command=self.destroy).pack(side='left',padx=(0,8))
        ttk.Button(controls,text='Adicionar efeito',style='Accent.TButton',command=self._submit).pack(side='left')
        self.bind('<Escape>',lambda e:self.destroy())
        self.wait_visibility()
        self.focus_force()

    def _submit(self):
        value = {key:var.get() for key,var in self.vars.items()}
        try:
            self.on_save(value)
        except (ModError,ValueError) as exc:
            messagebox.showerror('Efeito inválido',str(exc),parent=self)
            return
        self.destroy()


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
                ('Exportar alterações',self.export,None)]:
            ttk.Button(bar,text=name,command=action,style=style).pack(side='left',padx=(0,7))
        self.status = tk.StringVar(value='Crie um projeto e importe o CSV ou uma imagem BIN/CUE do jogo.')
        tk.Label(self,textvariable=self.status,bg=SURFACE,fg=MUTED,anchor='w',padx=18,pady=7).pack(side='bottom',fill='x')
        outer = ttk.Frame(self)
        outer.pack(fill='both',expand=True,padx=15,pady=(0,7))

        sidebar = tk.Frame(outer,bg=SURFACE,width=345)
        sidebar.pack(side='left',fill='y',padx=(0,12))
        sidebar.pack_propagate(False)
        tk.Label(sidebar,text='BIBLIOTECA DE CARTAS',bg=SURFACE,fg=TEXT,font=('Segoe UI',11,'bold')).pack(anchor='w',padx=14,pady=(17,8))
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
        body = tk.Frame(self.tab_cards,bg=BG,padx=19,pady=12)
        body.pack(fill='both',expand=True)
        tk.Label(body,text='EDITOR DE CARTAS',bg=BG,fg=TEXT,font=('Segoe UI',16,'bold')).pack(anchor='w')
        tk.Label(body,text='Alterações de ATK/DEF, tipo, nível, atributo e estrelas podem gerar um SLUS auxiliar; nomes e descrições ainda são metadados.',
                 bg=BG,fg=MUTED,font=('Segoe UI',9),wraplength=780,justify='left').pack(anchor='w',pady=(4,12))
        top=tk.Frame(body,bg=BG)
        top.pack(fill='x')
        self.preview = tk.Canvas(top,width=258,height=310,bg='#243454',highlightthickness=1,highlightbackground=BORDER)
        self.preview.pack(side='left',anchor='n',padx=(0,22))
        self.preview.create_rectangle(7,7,251,303,outline='#e0b962',width=3)
        self.preview_name=self.preview.create_text(129,35,text='NENHUMA CARTA',fill='#f1cf6e',font=('Segoe UI',12,'bold'),width=222)
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
        self.vars['cor_nome'] = tk.StringVar(value=DEFAULT_NAME_COLOR)
        tk.Label(color_line,text='Cor do nome:',bg=BG,fg=TEXT).pack(side='left',padx=(0,8))
        self.color_sample = tk.Label(color_line,text='   ■   ',bg=BG,fg=DEFAULT_NAME_COLOR,font=('Segoe UI',13,'bold'))
        self.color_sample.pack(side='left')
        ttk.Button(color_line,text='Escolher cor',command=self.choose_name_color).pack(side='left',padx=(6,5))
        ttk.Button(color_line,text='Cor padrão',command=lambda:self.vars['cor_nome'].set(DEFAULT_NAME_COLOR)).pack(side='left')
        tk.Label(form,text='A cor aparece na prévia e na biblioteca; ainda não é aplicada no PS1.',
                 bg=BG,fg=MUTED,font=('Segoe UI',9),wraplength=465,justify='left').pack(anchor='w',pady=(4,0))
        ttk.Button(form,text='Importar arte PNG (prévia)',command=self.import_art).pack(anchor='w',pady=(9,0))
        tk.Label(body,text='Descrição personalizada (ainda não codificada para o PS1)',bg=BG,fg=TEXT,font=('Segoe UI',10)).pack(anchor='w',pady=(17,4))
        self.description=tk.Text(body,height=3,wrap='word',bg=SURFACE,fg=TEXT,insertbackground=TEXT,
                                 selectbackground='#365a73',highlightthickness=1,highlightbackground=BORDER,font=('Segoe UI',10))
        self.description.pack(fill='both',expand=True)
        buttons=ttk.Frame(body)
        buttons.pack(fill='x',pady=(12,0))
        ttk.Button(buttons,text='Salvar projeto (todas as cartas)',style='Accent.TButton',command=self.save_project).pack(side='left')
        ttk.Button(buttons,text='Restaurar os valores originais',command=self.reset_card).pack(side='left',padx=9)
        tk.Label(buttons,text='Troque de carta livremente • Ctrl+S salva tudo',bg=BG,fg=MUTED,font=('Segoe UI',9)).pack(side='right')
        for variable in self.vars.values():
            variable.trace_add('write',lambda *_: self._on_card_field_input())
        self.description.bind('<<Modified>>',self._on_description_modified)

    def _effects_tab(self):
        body=tk.Frame(self.tab_effects,bg=BG,padx=22,pady=13)
        body.pack(fill='both',expand=True)
        tk.Label(body,text='EFEITOS DAS CARTAS',bg=BG,fg=TEXT,font=('Segoe UI',16,'bold')).pack(anchor='w')
        tk.Label(body,text='Gatilhos e ações para planejar e simular efeitos. NÃO são aplicados no motor do PS1 nesta versão.',
                 bg=BG,fg='#edc47e',font=('Segoe UI',10),wraplength=780,justify='left').pack(anchor='w',pady=(8,12))
        self.effect_caption=tk.Label(body,text='Escolha uma carta',bg=BG,fg=ACCENT,font=('Segoe UI',12,'bold'))
        self.effect_caption.pack(anchor='w',pady=(0,12))
        holder=tk.Frame(body,bg=SURFACE)
        holder.pack(fill='both',expand=True)
        self.effect_tree=ttk.Treeview(holder,columns=('evento','acao','alvo','valor'),show='headings',height=7)
        for key,label,w in [('evento','Quando',165),('acao','Efeito',185),('alvo','Alvo',170),('valor','Valor',90)]:
            self.effect_tree.heading(key,text=label)
            self.effect_tree.column(key,width=w,stretch=True)
        self.effect_tree.pack(fill='both',expand=True,padx=1,pady=1)
        buttons=ttk.Frame(body)
        buttons.pack(fill='x',pady=12)
        ttk.Button(buttons,text='+ Adicionar efeito',style='Accent.TButton',command=self.add_effect).pack(side='left')
        ttk.Button(buttons,text='Remover efeito selecionado',command=self.remove_effect).pack(side='left',padx=8)
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
        ttk.Button(line,text='Simular este gatilho',command=self.simulate).pack(side='left',padx=9)
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
        tk.Label(body,text='IMPORTANTE: SLUS auxiliar ≠ BIN jogável. Os efeitos ainda não são interpretados pelo jogo.\n'
                 'Esta versão exporta os dados; a montagem segura do disco e o patch de efeitos serão desenvolvidos depois.',
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

    def _on_card_field_input(self):
        if self._loading or not self.drafts or not self.selected_id:
            return
        self._stage_current()
        color=self.vars['cor_nome'].get()
        self.color_sample.configure(fg=color if re.fullmatch(r'#[0-9a-fA-F]{6}',color) else DEFAULT_NAME_COLOR)
        self.preview.itemconfigure(self.preview_name,text=(self.vars['nome'].get() or format_id(self.selected_id))[:42].upper(),
                                   fill=color if re.fullmatch(r'#[0-9a-fA-F]{6}',color) else DEFAULT_NAME_COLOR)
        # Atualização leve da linha (sem recriar a Treeview durante digitação).
        iid=str(self.selected_id)
        if self.tree.exists(iid):
            row=self.drafts.get_card(self.selected_id)
            tag=f'nome_cor_{color.upper().lstrip("#")}' if re.fullmatch(r'#[0-9a-fA-F]{6}',color) else 'sem_cor'
            if tag!='sem_cor':self.tree.tag_configure(tag,foreground=color)
            self.tree.item(iid,values=(f'{self.selected_id:03d}',
                 (row.get('nome') or '(nome não extraído)') + (' •' if self.selected_id in self.drafts.cards else ''),
                 row.get('ataque',''),row.get('defesa','')),tags=(tag,))
        self._update_pending_label()

    def _on_description_modified(self, _evt=None):
        if self.description.edit_modified():
            self.description.edit_modified(False)
            self._on_card_field_input()

    def choose_name_color(self):
        if not self.project or not self.selected_id:
            return
        current=self.vars['cor_nome'].get()
        chosen=colorchooser.askcolor(color=current,title='Escolher cor do nome',parent=self)[1]
        if chosen:
            self.vars['cor_nome'].set(chosen.upper())

    def _collect_form(self):
        data={}
        for key in FIELDS:
            if key=='descricao':
                data[key]=self.description.get('1.0','end-1c')
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
            color=c.get('cor_nome',DEFAULT_NAME_COLOR)
            tag=f'nome_cor_{str(color).upper().lstrip("#")}'
            if re.fullmatch(r'#[0-9A-Fa-f]{6}',str(color)):
                self.tree.tag_configure(tag, foreground=color)
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
            if key=='descricao':
                self.description.delete('1.0','end')
                self.description.insert('1.0',c.get(key,'') or '')
            elif key in ('tipo_id','atributo_id','guardian_1_id','guardian_2_id'):
                lookup={'tipo_id':TYPE_NAMES,'atributo_id':ATTR_NAMES,'guardian_1_id':STAR_NAMES,'guardian_2_id':STAR_NAMES}[key]
                n=int(c[key]); self.vars[key].set(f'{n:02d} — {(lookup[n] if n<len(lookup) else '(não mapeado)') or "Nenhuma"}')
            else:
                self.vars[key].set(str(c.get(key,'') or ''))
        self.description.edit_modified(False)
        self._loading=False
        color=c.get('cor_nome',DEFAULT_NAME_COLOR)
        self.color_sample.configure(fg=color)
        ident=format_id(self.selected_id)
        self.selected_caption.configure(text=f'{ident}  {c.get("nome") or "Nome ainda não extraído"}')
        self.preview.itemconfigure(self.preview_name,text=(c.get('nome') or ident)[:42].upper(),fill=color)
        self.preview.itemconfigure(self.preview_type,text=f'{TYPE_NAMES[int(c["tipo_id"])] if int(c["tipo_id"])<len(TYPE_NAMES) else "Tipo não mapeado"} • {ATTR_NAMES[int(c["atributo_id"])] if int(c["atributo_id"])<len(ATTR_NAMES) else "Atributo não mapeado"}')
        self.preview.itemconfigure(self.preview_stats,text=f'ATK {c["ataque"]}   DEF {c["defesa"]}')
        self._load_art()
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

    def _refresh_effects(self):
        for iid in self.effect_tree.get_children():
            self.effect_tree.delete(iid)
        if not self.project or not self.selected_id:
            return
        cid=self.selected_id
        effects=self.drafts.get_effects(cid) if self.drafts else self.project.effects.get(str(cid),[])
        self.effect_caption.configure(text=f'Efeitos de {format_id(cid)} — {len(effects)} cadastrado(s)')
        for i,eff in enumerate(effects):
            self.effect_tree.insert('','end',iid=str(i),values=(caption_key(EVENTS,eff['evento']),
                caption_key(ACTIONS,eff['acao']),caption_key(TARGETS,eff['alvo']),eff['valor']))
        self.sim_result.configure(text='Escolha um gatilho e clique Simular (não executa o PS1).')

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

    def simulate(self):
        if not self.project or not self.selected_id:
            return
        event=list(EVENTS)[self.sim_combo.current()]
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
                f'Artes PNG vinculadas: {len(pr.arts)} (somente prévia)\n'
                f'Extração profunda: {pr.metadata.get("deep_extraction", {}).get("completed", "ainda não realizada")}\n'
                f'Executável SLUS local: {source}\n\n'
                f'Avisos da extração ({len(pr.imported_notes)}):\n{notes}\n\n'
                'FASES DE EXPORTAÇÃO\n'
                '• Estatísticas: SLUS auxiliar se houver executável vinculado.\n'
                '• Nomes, cores e descrições: apenas registro e prévia no Studio.\n'
                '• Efeitos: apenas planejamento e simulação.\n'
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
        messagebox.showinfo('Exportação concluída',
            f'Pasta: {folder}\n\nCartas alteradas: {manifest["cartas_editadas"]}\n'
            f'Efeitos planejados: {manifest["efeitos_planejados"]}\n\n'
            'Fusões preservadas. O arquivo BIN/CUE jogável ainda não foi gerado; novos efeitos são somente simulações.')
        self._update_status('Exportação concluída (ainda NÃO jogável no ePSXe): '+str(folder))

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
            'Instalar agora? Seus projetos e backups serão preservados.',parent=self)
        if not reply or not self._confirm_switch():
            self._update_status('Atualização cancelada.')
            return
        try:
            start_updater(release)
        except (OSError, UpdateError) as exc:
            messagebox.showerror('Não foi possível atualizar',str(exc),parent=self)
            return
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
