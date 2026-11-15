"""Laboratório gráfico de campo, decks, gatilhos e equipamentos (somente simulação)."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox

from .core import EVENTS, ModError
from .duel_engine import DuelLab, parse_card_ids
from .gui import BG, SURFACE, TEXT, MUTED, ACCENT, BORDER


class AdvancedFieldDialog(tk.Toplevel):
    def __init__(self, master, project, drafts, initial_card):
        super().__init__(master)
        self.title('Laboratório de efeitos — Campo / Deck / Encantamentos')
        self.geometry('1290x870')
        self.minsize(1040,720)
        self.configure(bg=BG)
        self.project=project
        self.drafts=drafts
        self._updating=False
        cards={cid:drafts.get_card(cid) for cid in project.cards}
        effects={str(cid):drafts.get_effects(cid) for cid in project.cards
                 if drafts.get_effects(cid)}
        self.lab=DuelLab(cards,effects)
        self.choices={'— VAZIO —':None}
        self.by_id={}
        for cid,c in sorted(cards.items()):
            name=c.get('nome') or '(sem nome)'
            title=f'#{cid:03d} — {name}'[:55]
            self.choices[title]=cid
            self.by_id[cid]=title
        self.entries=[]
        self.deck_vars={}
        self.hand_vars={}
        self._last_hand={side:'' for side in ('jogador','adversario')}
        self.lp_label={}
        self.logs=[]
        title=tk.Frame(self,bg=BG)
        title.pack(fill='x',padx=16,pady=(13,7))
        tk.Label(title,text='LABORATÓRIO DE EFEITOS',font=('Segoe UI',15,'bold'),bg=BG,fg=TEXT).pack(anchor='w')
        tk.Label(title,text='Deck completo (até 40 cartas) • efeitos ativados só por clique • equipamentos anexados ao monstro • tudo é SIMULAÇÃO, não um patch de PS1.',
                 bg=BG,fg=MUTED,wraplength=1180,justify='left').pack(anchor='w',pady=(2,0))
        tabs=ttk.Notebook(self)
        tabs.pack(fill='both',expand=True,padx=16,pady=6)
        self.tab_board=ttk.Frame(tabs)
        self.tab_decks=ttk.Frame(tabs)
        tabs.add(self.tab_board,text='Campo e equipamentos')
        tabs.add(self.tab_decks,text='Deck, mão e gatilhos')
        self._board_ui()
        self._deck_ui()
        self._output_ui()
        if initial_card in self.by_id:
            self.entries[0]['monster'].set(self.by_id[initial_card])
        self.evaluate()

    def _board_ui(self):
        container=tk.Frame(self.tab_board,bg=BG)
        container.pack(fill='both',expand=True,padx=8,pady=8)
        for col,side in enumerate(('jogador','adversario')):
            panel=tk.Frame(container,bg=SURFACE,padx=10,pady=9)
            panel.grid(row=0,column=col,sticky='nsew',padx=5)
            tk.Label(panel,text='MEUS 5 SLOTS' if side=='jogador' else 'SLOTS DO OPONENTE',
                     bg=SURFACE,fg=ACCENT,font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(0,4))
            tk.Label(panel,text='Monstro / Encantamento equipado / ↑ virado para cima',
                     bg=SURFACE,fg=MUTED,font=('Segoe UI',9)).pack(anchor='w',pady=(0,7))
            for slot in range(1,6):
                row=tk.Frame(panel,bg=SURFACE)
                row.pack(fill='x',pady=4)
                tk.Label(row,text=f'{slot}.',bg=SURFACE,fg=TEXT,width=3).pack(side='left')
                monster=tk.StringVar(value='— VAZIO —')
                cm=ttk.Combobox(row,textvariable=monster,values=list(self.choices),width=27,state='readonly')
                cm.pack(side='left',fill='x',expand=True)
                equip=tk.StringVar(value='— VAZIO —')
                ce=ttk.Combobox(row,textvariable=equip,values=list(self.choices),width=26,state='readonly')
                ce.pack(side='left',padx=4)
                face=tk.BooleanVar(value=True)
                ttk.Checkbutton(row,variable=face,text='↑',command=self.evaluate).pack(side='left')
                info=tk.Label(panel,text='Vazio',bg=SURFACE,fg=MUTED,anchor='w',font=('Segoe UI',9))
                info.pack(fill='x',padx=(23,0),pady=(0,3))
                self.entries.append({'side':side,'slot':slot,'monster':monster,
                                     'equip':equip,'face':face,'label':info})
                cm.bind('<<ComboboxSelected>>',lambda event:self.evaluate())
                ce.bind('<<ComboboxSelected>>',lambda event:self.evaluate())
        container.columnconfigure(0,weight=1)
        container.columnconfigure(1,weight=1)
        tk.Label(self.tab_board,text='Auras e bônus são recalculados sem acumular. Equipamentos deixam de funcionar quando o monstro sai do campo.',
                 bg=BG,fg=MUTED,font=('Segoe UI',9)).pack(anchor='w',padx=15,pady=7)

    def _deck_ui(self):
        host=tk.Frame(self.tab_decks,bg=BG)
        host.pack(fill='both',expand=True,padx=14,pady=10)
        tk.Label(host,text='CARREGAR DECKS E MÃOS PARA SIMULAÇÃO',bg=BG,fg=TEXT,font=('Segoe UI',12,'bold')).pack(anchor='w')
        tk.Label(host,text='IDs separados por vírgula. Ex.: 1x3, 16x2, 300 (repetições 1x3 = 3 cópias). '
                 'Contagem usa o DECK configurado, não somente o monte restante.',
                 bg=BG,fg=MUTED,wraplength=1150,justify='left').pack(anchor='w',pady=(4,10))
        for side,caption in [('jogador','MEU DECK'),('adversario','DECK ADVERSÁRIO')]:
            panel=tk.Frame(host,bg=SURFACE,padx=12,pady=8)
            panel.pack(fill='x',pady=5)
            tk.Label(panel,text=caption,bg=SURFACE,fg=ACCENT,font=('Segoe UI',10,'bold')).pack(anchor='w')
            tk.Label(panel,text='Deck até 40:',bg=SURFACE,fg=TEXT).pack(side='left',padx=(0,6))
            d=tk.StringVar()
            self.deck_vars[side]=d
            ttk.Entry(panel,textvariable=d,width=60).pack(side='left',fill='x',expand=True)
            tk.Label(panel,text='Mão até 5:',bg=SURFACE,fg=TEXT).pack(side='left',padx=8)
            h=tk.StringVar()
            self.hand_vars[side]=h
            ttk.Entry(panel,textvariable=h,width=28).pack(side='left')
            self.lp_label[side]=tk.Label(panel,text='LP 8000',bg=SURFACE,fg=TEXT)
            self.lp_label[side].pack(side='left',padx=10)
            d.trace_add('write',lambda *_:self.evaluate())
            h.trace_add('write',lambda *_:self.evaluate())
        controls=tk.Frame(host,bg=BG)
        controls.pack(fill='x',pady=15)
        tk.Label(controls,text='Origem',bg=BG,fg=TEXT).pack(side='left')
        self.slot_options={}
        for side,label in [('jogador','Você'),('adversario','Oponente')]:
            for slot in range(1,6):
                self.slot_options[f'{label} slot {slot}']=(side,slot)
        self.origin=tk.StringVar(value='Você slot 1')
        ttk.Combobox(controls,textvariable=self.origin,width=19,state='readonly',
                     values=list(self.slot_options)).pack(side='left',padx=5)
        tk.Label(controls,text='Alvo',bg=BG,fg=TEXT).pack(side='left',padx=(8,0))
        self.target=tk.StringVar(value='Oponente slot 1')
        ttk.Combobox(controls,textvariable=self.target,width=19,state='readonly',
                     values=list(self.slot_options)).pack(side='left',padx=5)
        tk.Label(controls,text='Gatilho',bg=BG,fg=TEXT).pack(side='left',padx=(8,0))
        self.event=tk.StringVar(value='invocar')
        opts=[k for k in EVENTS if k not in ('continuo','equipado','regra_deck')]
        ttk.Combobox(controls,textvariable=self.event,width=16,state='readonly',values=opts).pack(side='left',padx=5)
        self.origin_kind=tk.StringVar(value='monstro')
        ttk.Combobox(controls,textvariable=self.origin_kind,width=12,state='readonly',values=['monstro','magia','armadilha']).pack(side='left',padx=5)
        actions=tk.Frame(host,bg=BG)
        actions.pack(fill='x')
        ttk.Button(actions,text='Aplicar gatilho uma vez',style='Accent.TButton',command=self.trigger).pack(side='left',padx=(0,10))
        ttk.Button(actions,text='Remover monstro alvo',command=self.remove_target).pack(side='left',padx=5)
        ttk.Button(actions,text='Reiniciar LP e mãos',command=self.reset_state).pack(side='left',padx=5)
        battle=tk.Frame(host,bg=BG)
        battle.pack(fill='x',pady=(9,0))
        tk.Label(battle,text='COMBATE:',bg=BG,fg=ACCENT,font=('Segoe UI',10,'bold')).pack(side='left')
        self.battle_mode=tk.StringVar(value='defesa')
        ttk.Combobox(battle,textvariable=self.battle_mode,state='readonly',width=12,
                     values=['defesa','ataque']).pack(side='left',padx=7)
        ttk.Button(battle,text='Atacar alvo',style='Accent.TButton',command=self.attack_target).pack(side='left',padx=4)
        ttk.Button(battle,text='Ataque direto',command=self.attack_direct).pack(side='left',padx=4)
        ttk.Button(battle,text='Novo turno (origem)',command=self.new_turn).pack(side='left',padx=4)
        tk.Label(battle,text='Dano perfurante em DEF; custos de LP por ataque.',
                 bg=BG,fg=MUTED).pack(side='left',padx=10)
        tk.Label(host,text='Dano a monstro usa resistência experimental (HP = DEF-base, mínimo 1).'
                 ' Proteções bloqueiam efeitos de mágicas/armadilhas e indestrutibilidade evita destruição.',
                 bg=BG,fg='#edc47e',wraplength=1100,justify='left').pack(anchor='w',pady=12)

    def _output_ui(self):
        footer=tk.Frame(self,bg=BG)
        footer.pack(fill='both',expand=False,padx=16,pady=(3,14))
        top=tk.Frame(footer,bg=BG)
        top.pack(fill='x')
        tk.Label(top,text='EVENTOS E BÔNUS',bg=BG,fg=TEXT,font=('Segoe UI',10,'bold')).pack(side='left')
        ttk.Button(top,text='Recalcular campo',command=self.evaluate).pack(side='right')
        self.output=tk.Text(footer,bg=SURFACE,fg=TEXT,font=('Consolas',9),height=9,
                            wrap='word',state='disabled',highlightthickness=1,highlightbackground=BORDER)
        self.output.pack(fill='both',expand=True,pady=(5,0))

    def _board(self):
        monsters=[]
        equipments=[]
        for item in self.entries:
            side,slot=item['side'],item['slot']
            cid=self.choices.get(item['monster'].get())
            equip=self.choices.get(item['equip'].get())
            if cid is not None:
                c=self.lab.card(cid)
                monsters.append({'lado':side,'slot':slot,'card_id':cid,'tipo_id':int(c['tipo_id']),
                                 'ataque':int(c['ataque']),'defesa':int(c['defesa']),
                                 'face_up':bool(item['face'].get())})
                if equip is not None:
                    equipments.append({'lado':side,'slot':slot,'card_id':equip})
        return monsters,equipments

    def _sync(self):
        for side in ('jogador','adversario'):
            self.lab.set_deck(side,parse_card_ids(self.deck_vars[side].get(),maximum=40))
            hand_string=self.hand_vars[side].get()
            if self._last_hand[side] != hand_string:
                self.lab.set_hand(side,parse_card_ids(hand_string,maximum=5))
                self._last_hand[side]=hand_string
        m,e=self._board()
        self.lab.set_field(m,e)

    def evaluate(self):
        if self._updating:
            return
        try:
            self._sync()
            board,events=self.lab.resolve()
        except (ValueError,ModError) as exc:
            self._write(f'Erro na configuração: {exc}')
            return
        by_key={(m['lado'],m['slot']):m for m in board}
        for entry in self.entries:
            key=(entry['side'],entry['slot'])
            m=by_key.get(key)
            if not m:
                entry['label'].configure(text='Vazio',fg=MUTED)
                continue
            da,dd=m['ataque']-m['ataque_base'],m['defesa']-m['defesa_base']
            protection=[p for p in ('imune_armadilha','imune_magia','indestrutivel') if m[p]]
            if m['perfurante']: protection.append('perfurante')
            if m['nao_bloqueavel']: protection.append('não bloqueável')
            if m['ataques_max']>1: protection.append(f'{m["ataques_max"]} ataques')
            self_hp=max(1,int(m['defesa_base']))-self.lab.damage.get((entry['side'],entry['slot'],m['card_id']),0)
            text=f'ATK {m["ataque"]} ({da:+}) · DEF {m["defesa"]} ({dd:+}) · HP* {self_hp} '
            if protection:
                text+=' · '+','.join(protection).replace('imune_','Imune ')
            entry['label'].configure(text=text,fg=ACCENT if da or dd or protection else MUTED)
        for side in self.lp_label:
            self.lp_label[side].configure(text=f'LP {self.lab.lp[side]} / mão {len(self.lab.hands[side])}')
        lines=[f'Bônus / proteções aplicados: {len(events)}.']
        for event in events[:12]:
            lines.append(f'{event["origem"]} → {event["destino"]}: {event["acao"]}, '
                         f'ATK {event["ataque"]:+}, DEF {event["defesa"]:+}, x{event["quantidade"]}')
        lines.extend(self.logs[-8:])
        self._write('\n'.join(lines))

    def _write(self,text):
        if not hasattr(self,'output'):
            return
        self.output.configure(state='normal')
        self.output.delete('1.0','end')
        self.output.insert('1.0',text)
        self.output.configure(state='disabled')

    def trigger(self):
        try:
            self._sync()
            side,slot=self.slot_options[self.origin.get()]
            target_side,target_slot=self.slot_options[self.target.get()]
            applied=self.lab.trigger(side,slot,self.event.get(),target_side=target_side,
                                     target_slot=target_slot,kind=self.origin_kind.get())
            self.logs.extend([f'Gatilho {self.event.get()}: {entry}' for entry in applied] or ['Nenhum efeito ativado.'])
            self._clear_removed()
            self.evaluate()
        except (ValueError,ModError) as exc:
            messagebox.showerror('Simulação',str(exc),parent=self)

    def _clear_removed(self):
        keys={(m['lado'],m['slot']) for m in self.lab.monsters}
        self._updating=True
        try:
            for entry in self.entries:
                if (entry['side'],entry['slot']) not in keys:
                    entry['monster'].set('— VAZIO —')
                    entry['equip'].set('— VAZIO —')
        finally:
            self._updating=False

    def _do_attack(self, direct=False):
        try:
            self._sync()
            side,slot=self.slot_options[self.origin.get()]
            enemy,enemy_slot=self.slot_options[self.target.get()]
            if enemy==side and not direct:
                raise ModError('Selecione um monstro do adversário como alvo')
            result=self.lab.attack(side,slot,target_slot=None if direct else enemy_slot,
                                   against=self.battle_mode.get())
            self.logs.append(f'ATAQUE {result["ataques_usados"]}/{result["ataques_max"]}: '
                             f'custo {result["custo_lp"]} LP, dano ao jogador {result["dano_lp_jogador"]}, '
                             f'dano ao oponente {result["dano_lp_oponente"]}, '
                             f'destruídos {result["destruidos"]}')
            self._clear_removed()
            self.evaluate()
        except (ValueError,ModError) as exc:
            messagebox.showerror('Combate no laboratório',str(exc),parent=self)

    def attack_target(self):
        self._do_attack(False)

    def attack_direct(self):
        self._do_attack(True)

    def new_turn(self):
        side,_=self.slot_options[self.origin.get()]
        self.lab.new_turn(side)
        self.logs.append(f'Novo turno: ataques de {side} reiniciados')
        self.evaluate()

    def remove_target(self):
        side,slot=self.slot_options[self.target.get()]
        self.lab.remove(side,slot)
        self.logs.append(f'Monstro removido: {side} slot {slot}')
        self._clear_removed()
        self.evaluate()

    def reset_state(self):
        for side in ('jogador','adversario'):
            self.lab.lp[side]=8000
            self._last_hand[side]='__RESET__'
        self.lab.damage.clear()
        self.lab.attacks_used.clear()
        self.logs.clear()
        self.evaluate()
