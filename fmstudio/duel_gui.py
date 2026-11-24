"""Interactive player-versus-CPU match and live zone inspection."""
from __future__ import annotations

from collections import Counter
import tkinter as tk
from tkinter import messagebox, ttk

from .continuous import SIDES
from .core import ENTRY_EFFECTS, ModError
from .duel_ai import play_ai_turn, posture
from .duel_rank import project_rank
from .expanded import display_name
from .guardian import guardian_name
from .gui import ACCENT, BORDER, ROW_ALT, SURFACE, TEXT, card_row_tags, compact_number, sortable_columns
from .mod_data import drops_from_deck

FIXED_GIVEN_KEY = 'simulador_drops_fixos_entregues'  # duelistas cujo drop fixo já saiu no simulador
from .passwords import grant_card, original_passwords
from .tables import DUELIST_NAMES_REFERENCE


def zone_tree(parent):
    cols = ('id', 'nome', 'atk', 'def', 'copias')
    tree = ttk.Treeview(parent, columns=cols, show='headings', height=6)
    tree.tag_configure('stripe', background=ROW_ALT)
    for key, label, width in zip(cols, ('ID', 'Carta', 'ATK efetivo', 'DEF efetiva', 'Cópias'),
                                 (70, 215, 115, 115, 65)):
        tree.heading(key, text=label)
        tree.column(key, width=width, minwidth=45, stretch=key == 'nome')
    tree.sort_values = {}
    tree.sort_rows = sortable_columns(tree, raw_values=lambda item, key: tree.sort_values[item][key])
    tree.pack(side='left', fill='both', expand=True)
    scroll = ttk.Scrollbar(parent, command=tree.yview)
    scroll.pack(side='right', fill='y')
    tree.configure(yscrollcommand=scroll.set)
    return tree


def fill_zone(tree, game, side, zone):
    old = tree.selection()
    tree.delete(*tree.get_children())
    cards = game.inspect_zone(side, zone)
    tree.sort_values.clear()
    copies = Counter(card['id'] for card in cards)
    by_id = {card['id']: card for card in cards}
    ids = sorted(by_id) if zone == 'deck' else by_id
    for index, cid in enumerate(ids):
        row = by_id[cid]
        tree.sort_values[str(cid)] = {'id': cid, 'nome': display_name(cid, game.cards), 'atk': row['ataque'],
                                      'def': row['defesa'], 'copias': copies[cid]}
        tree.insert('', 'end', iid=str(cid), values=(compact_number(cid),
            display_name(cid, game.cards), compact_number(row['ataque']),
            compact_number(row['defesa']), copies[cid]),
            tags=card_row_tags(tree, game.cards.get(cid), index))
    tree.sort_rows()
    if old and tree.exists(old[0]):
        tree.selection_set(old[0])


def show_exact(parent, title, text, *, art=None):
    window = tk.Toplevel(parent)
    window.title(title)
    window.transient(parent)
    window.geometry('610x350')
    if art is not None:
        try:
            image = tk.PhotoImage(master=window, file=str(art))
            scale = max(1, (image.width() + 159) // 160, (image.height() + 111) // 112)
            window.card_image = image.subsample(scale, scale) if scale > 1 else image
            ttk.Label(window, image=window.card_image).pack(anchor='w', padx=10, pady=7)
        except tk.TclError:
            pass
    widget = tk.Text(window, wrap='char', bg=SURFACE, fg=TEXT,
                     highlightthickness=1, highlightbackground=BORDER, padx=10, pady=9)
    scroll = ttk.Scrollbar(window, command=widget.yview)
    scroll.pack(side='right', fill='y')
    widget.configure(yscrollcommand=scroll.set)
    widget.pack(fill='both', expand=True)
    widget.insert('1.0', text)
    widget.configure(state='disabled')


class MatchDialog(tk.Toplevel):
    def __init__(self, parent, game, opponent, rules, pools, *, project=None, collection_changed=None):
        super().__init__(parent)
        self.title(f'Duelo contra {DUELIST_NAMES_REFERENCE[opponent]}')
        self.geometry('1120x780')
        self.minsize(960, 700)
        self.studio = parent
        self.project = project or getattr(parent, 'project', None)
        self.collection_changed = collection_changed
        self.game = game
        self.opponent = opponent
        self.rules = rules
        self.pools = pools
        self.result = tk.StringVar()
        self.rank = tk.StringVar()
        self.lp_text = {}
        self.fields = {}
        self.log_lines = []
        self.built_plays = []
        self.ai_running = False
        self.deck_drops = drops_from_deck(rules, opponent)
        self._auto_reward_attempted = False
        pane = ttk.Frame(self, padding=12)
        pane.pack(fill='both', expand=True)
        header = ttk.Frame(pane)
        header.pack(fill='x')
        ttk.Label(header, textvariable=self.result, foreground=ACCENT).pack(side='left')
        ttk.Button(header, text='Ver LP completos', command=self._exact_life).pack(side='right')
        ttk.Button(header, text='Passwords e baú', command=self._open_passwords,
                   state='normal' if self.project else 'disabled').pack(side='right', padx=6)

        battlefield = ttk.Frame(pane)
        battlefield.pack(fill='x', pady=(9, 5))
        for i, side in enumerate(SIDES):
            battlefield.columnconfigure(i, weight=1, uniform='field')
            panel = ttk.LabelFrame(battlefield, text='Seu campo' if side == 'jogador'
                                   else DUELIST_NAMES_REFERENCE[opponent], padding=6)
            panel.grid(row=0, column=i, sticky='nsew', padx=(0, 4) if i == 0 else (4, 0))
            lp = self.lp_text[side] = tk.StringVar()
            ttk.Label(panel, textvariable=lp).pack(anchor='w', pady=(0, 4))
            if i == 0:
                ttk.Label(panel, textvariable=self.rank, foreground=ACCENT,
                          font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 4))
            else:
                ttk.Label(panel, text='', font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 4))
            cols = ('posição', 'carta', 'atk', 'def', 'estrela')
            tree = ttk.Treeview(panel, columns=cols, show='headings', height=5, selectmode='browse')
            tree.tag_configure('stripe', background=ROW_ALT)
            for key, title, width in zip(cols, ('Slot', 'Carta', 'ATK', 'DEF', 'Guardian'), (62, 165, 75, 75, 95)):
                tree.heading(key, text=title)
                tree.column(key, width=width, minwidth=38, stretch=key == 'carta')
            tree.sort_rows = sortable_columns(tree)
            tree.pack(fill='x')
            tree.bind('<Double-1>', lambda _e, sd=side: self._inspect_field(sd))
            self.fields[side] = tree

        battle = ttk.Frame(pane)
        battle.pack(fill='x', pady=(3, 6))
        self.attack_button = ttk.Button(battle, text='Atacar alvo', command=lambda: self._attack(False))
        self.direct_button = ttk.Button(battle, text='Atacar LP', command=lambda: self._attack(True))
        self.pose_button = ttk.Button(battle, text='Trocar posição', command=self._change_position)
        self.end_button = ttk.Button(battle, text='Encerrar turno', command=self._end_turn)
        for widget in (self.attack_button, self.direct_button, self.pose_button, self.end_button):
            widget.pack(side='left', padx=(0, 5))
        ttk.Label(battle, text='Selecione seu monstro e o alvo nos campos.').pack(side='right')

        action = ttk.Frame(pane)
        action.pack(fill='x', pady=(2, 7))
        self.play_select = ttk.Combobox(action, state='readonly')
        self.play_select.pack(side='left', fill='x', expand=True)
        self.play_button = ttk.Button(action, text='Jogar carta', style='Accent.TButton', command=self._play)
        self.play_button.pack(side='right', padx=(6, 0))

        tabs = ttk.Notebook(pane)
        tabs.pack(fill='both', expand=True)
        self.zones = {}
        for zone, label in (('mao', 'Mão'), ('deck', 'Monte de compra'), ('cemiterio', 'Cemitério')):
            host = ttk.Frame(tabs, padding=5)
            tabs.add(host, text=label)
            view = zone_tree(host)
            view.bind('<Double-1>', lambda _e, z=zone: self._inspect_zone(z))
            self.zones[zone] = view

        reward = ttk.Frame(pane)
        reward.pack(fill='x', pady=(5, 0))
        self.drop_button = ttk.Button(reward, text='Receber recompensa',
                                      style='Accent.TButton', command=self._roll_drop)
        self.drop_button.pack(side='left', padx=5)
        self.reward = ttk.Label(reward, foreground=ACCENT,
                                text='Recompensa ponderada pelo deck do oponente.' if self.deck_drops else '')
        self.reward.pack(side='left')
        self.output = tk.Text(pane, height=4, wrap='word', state='disabled', bg=SURFACE, fg=TEXT)
        self.output.pack(fill='x', pady=(5, 0))
        self.render()
        if game.active == 'adversario':
            self.after_idle(self._ai)

    def _play_label(self, action):
        name = display_name(action.card_id, self.game.cards)
        used = '/'.join(map(str, (i + 1 for i in action.hand)))
        details = []
        if action.slot:
            details.append(f'slot {action.slot}')
        if action.kind in ('monstro', 'fusao', 'ritual'):
            details += [action.position, guardian_name(action.star)]
            if not action.face_up:
                details.append('virada para baixo')
        if action.target:
            target = 'seu campo' if action.target[0] == 'jogador' else 'rival'
            relation = 'material' if action.kind == 'fusao' else 'alvo'
            details.append(f'{relation} no {target} slot {action.target[1]}')
        text = ' · '.join(details)
        label = {'fusao':'Fusão', 'magia':'Magia', 'monstro':'Invocar', 'ritual':'Ritual',
                 'armadilha':'Preparar armadilha', 'equip':'Equipar'}[action.kind]
        return f'Mão {used} · {label} {name}' + (f' · {text}' if text else '')

    def _exact_life(self):
        text = '\n\n'.join(f'{side.capitalize()}\nLP {self.game.lp[side]}' for side in SIDES)
        show_exact(self, 'Life Points', text)

    def _inspect_field(self, side):
        selection = self.fields[side].selection()
        if not selection:
            return
        slot = int(selection[0])
        unit = next(m for m in self.game.resolve()[0] if (m['lado'], m['slot']) == (side,slot))
        if side != 'jogador' and not unit['face_up']:
            return
        name = display_name(unit['card_id'], self.game.cards)
        details = f'ATK {unit["ataque"]}\nDEF {unit["defesa"]}\n{guardian_name(unit["guardian_id"])}'
        atk, defense = self.game.stat_markers.get((side, slot, unit['card_id']), (0, 0))
        if atk or defense:
            details += f'\nMarcadores de entrada {atk:+} ATK / {defense:+} DEF'
        show_exact(self, name, details,
                   art=self.project.art_path(unit['card_id']) if self.project else None)

    def _inspect_zone(self, zone):
        selection = self.zones[zone].selection()
        if selection:
            cid = int(selection[0])
            card = self.game.effective_card('jogador', cid)
            show_exact(self, display_name(cid, self.game.cards),
                       f'ATK {card["ataque"]}\nDEF {card["defesa"]}\n\n{card.get("descricao", "")}',
                       art=self.project.art_path(cid) if self.project else None)

    def _write_logs(self, entries):
        for event in entries:
            action = event['acao']
            if action == 'ataque':
                side, slot = event['origem']
                dealt = compact_number(event['dano_lp_oponente'],22)
                paid = compact_number(event['dano_lp_jogador'],22)
                target = 'LP rivais' if event['alvo'][0]=='LP' else f'slot {event["alvo"][1]} rival'
                text = f'{side.capitalize()} atacou do slot {slot} aos {target}. Dano {dealt}, perda própria {paid} LP.'
                if event.get('destruidos'):
                    text += ' Destruição em ' + ', '.join(f'{s} {n}' for s,n in event['destruidos']) + '.'
                if any(event.get('bonus_guardian',())):
                    bonuses=event['bonus_guardian']
                    text += f' Guardian {bonuses[0]:+}/{bonuses[1]:+}.'
            elif action=='novo_turno':
                text=f'Início do turno de {event["lado"]}.'
            elif action in ENTRY_EFFECTS or action == 'destruido_por_marcador':
                side, slot = event['alvo']
                side_name = 'Seu campo' if side == 'jogador' else 'Campo oponente'
                text = f'{side_name} · slot {slot} · '
                if action == 'destruido_por_marcador':
                    text += 'Destruído por ficar com ATK e DEF em 0.'
                else:
                    text += f'Marcador {event["valor"]:+} ATK / {event["valor_def"]:+} DEF.'
            elif 'carta' in event:
                side = event['lado']
                visible = side == 'jogador' or event.get('face_up', True)
                name = display_name(event['carta'], self.game.cards) if visible else 'Carta virada para baixo'
                if action in ('dano_lp', 'cura_lp', 'dano_lp_deck_tipo', 'cura_lp_deck_tipo'):
                    amount = compact_number(event['valor'], 22)
                    target = 'oponente' if event['alvo'] == 'adversario' else 'jogador'
                    timing = ' ao entrar em campo' if event['evento'] == 'invocar' else ''
                    if action.startswith('dano'):
                        text = f'{name} causou {amount} de dano aos LP do {target}{timing}.'
                    else:
                        text = f'{name} recuperou {amount} LP do {target}{timing}.'
                else:
                    text = f'{side.capitalize()} · {action.replace("_", " ")} · {name}'
            else:
                text=f'{action.replace("_"," ").capitalize()} · {compact_number(event.get("valor",0),22)}'
            self.log_lines.append(text)
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', '\n'.join(self.log_lines[-50:]))
        self.output.see('end')
        self.output.configure(state='disabled')

    def render(self):
        if self.game.winner:
            caption = {'jogador':'Você venceu','adversario':'O duelista venceu','empate':'Empate'}[self.game.winner]
        elif self.game.active == 'jogador':
            caption = f'Seu turno {self.game.turns["jogador"]}'
        else:
            caption = f'Turno {self.game.turns["adversario"]} do oponente · postura {posture(self.game, "adversario")}'
        self.result.set(caption)
        rank = project_rank(self.game)
        self.rank.set(f'{rank.grade} {rank.score:02d}')
        board = self.game.resolve()[0]
        for side in SIDES:
            self.lp_text[side].set(f'LP {compact_number(self.game.lp[side],20)}   '
                f'Mão {len(self.game.hands[side])}   Deck {len(self.game.decks[side])}   '
                f'Arm. {len(self.game.traps[side])}')
            tree = self.fields[side]
            old = tree.selection()
            tree.delete(*tree.get_children())
            for unit in sorted(board, key=lambda m: m['slot']):
                if unit['lado'] != side:
                    continue
                slot = unit['slot']
                shown = side == 'jogador' or unit['face_up']
                card = self.game.cards.get(unit['card_id']) if shown else None
                name = display_name(unit['card_id'], self.game.cards) if shown else 'Virada para baixo'
                tree.insert('', 'end', iid=str(slot), values=(
                    f'{slot} · {"ATQ" if unit["posicao"] == "ataque" else "DEF"}', name,
                    compact_number(unit['ataque'],9) if shown else '—',
                    compact_number(unit['defesa'],9) if shown else '—',
                    guardian_name(unit['guardian_id']) if shown else '—'),
                    tags=card_row_tags(tree, card, slot - 1))
            tree.sort_rows()
            if old and tree.exists(old[0]):
                tree.selection_set(old[0])
        for zone, tree in self.zones.items():
            fill_zone(tree, self.game, 'jogador', zone)
        enabled = self.game.active == 'jogador' and not self.game.winner and not self.ai_running
        self.built_plays = self.game.legal_plays('jogador') if enabled else []
        self.play_select.configure(values=[self._play_label(a) for a in self.built_plays],
                                   state='readonly' if self.built_plays else 'disabled')
        if self.built_plays:
            self.play_select.current(0)
        else:
            self.play_select.set('')
        for button in (self.attack_button, self.direct_button, self.pose_button, self.end_button):
            button.configure(state='normal' if enabled else 'disabled')
        self.play_button.configure(state='normal' if self.built_plays else 'disabled')
        can_claim = self.game.winner == 'jogador' and self.game.reward_card is None
        self.drop_button.configure(state='normal' if can_claim else 'disabled')

    def _action(self, callback):
        before = len(self.game.logs)
        try:
            callback()
        except ModError as exc:
            messagebox.showinfo('Duelo', str(exc), parent=self)
        self._write_logs(self.game.logs[before:])
        self.render()

    def _play(self):
        index = self.play_select.current()
        if index >= 0:
            self._action(lambda: self.game.play('jogador', self.built_plays[index]))

    def _slot(self, side):
        selection = self.fields[side].selection()
        if not selection:
            raise ModError('Selecione um monstro no campo.')
        return int(selection[0])

    def _attack(self, direct):
        self._action(lambda: self.game.attack('jogador', self._slot('jogador'),
                     target_slot=None if direct else self._slot('adversario')))

    def _change_position(self):
        def change():
            slot = self._slot('jogador')
            position = self.game.get('jogador', slot)['posicao']
            self.game.set_position('jogador', slot, 'defesa' if position == 'ataque' else 'ataque')
        self._action(change)

    def _end_turn(self):
        self._action(lambda: self.game.end_turn('jogador'))
        if not self.game.winner and self.game.active == 'adversario':
            self.after_idle(self._ai)

    def _ai(self):
        if self.game.winner or self.game.active != 'adversario':
            return
        self.ai_running = True
        self._action(lambda: play_ai_turn(self.game))
        self.ai_running = False
        self.render()

    def _check_project(self):
        if not self.project or self.project is not self.studio.project or self.studio._extract_running:
            raise ModError('O baú está vinculado ao projeto que abriu este duelo.')

    def _open_passwords(self):
        from .mod_tools_gui import PasswordsDialog
        try:
            self._check_project()
            cards = {cid: self.project.get(cid) for cid in self.project.cards}
            PasswordsDialog(self.studio, self.project, cards, original_passwords(self.project),
                            owner=self, changed=self.collection_changed)
        except (ModError, ValueError, OSError) as exc:
            messagebox.showerror('Passwords e baú', str(exc), parent=self)

    def _roll_drop(self):
        try:
            self._check_project()
            given = set(map(int, self.project.metadata.get(FIXED_GIVEN_KEY, [])))
            cid = self.game.claim_reward(self.rules, self.pools, self.opponent, project_rank(self.game).grade,
                                         lambda card: grant_card(self.project, card), fixed_given=given)
            if getattr(self.game, 'fixed_reward', False) and int(self.opponent) not in given:
                self.project.metadata = {**self.project.metadata,
                                         FIXED_GIVEN_KEY: sorted(given | {int(self.opponent)})}
                self.project.save()
        except (ModError, ValueError, OSError) as exc:
            self.reward.configure(text=str(exc))
            return
        self.reward.configure(text=f'{display_name(cid, self.game.cards)} enviada ao baú.')
        self.drop_button.configure(state='disabled')
        if self.collection_changed:
            self.collection_changed()
