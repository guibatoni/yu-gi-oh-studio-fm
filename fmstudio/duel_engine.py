"""Estado e resolução de combate compartilhados pelo laboratório e pela partida."""
from __future__ import annotations
from collections import Counter
from copy import copy, deepcopy
import re

from .continuous import SIDES, project_stats, resolve_field
from .core import ModError, check_effect, simulation_nonnegative_int
from .guardian import guardian_bonuses
from .mod_data import card_effects, opposite, validate_deck
from .tables import DECK_SIZE

MAX_DECK = DECK_SIZE
MAX_HAND = 5
POSITIONS = ('ataque', 'defesa')


def parse_card_ids(text: str, *, maximum: int = MAX_DECK) -> list[int]:
    """Lê '1, 2x3, #016*2' de forma determinística; lista vazia permitida."""
    text = str(text or '').strip()
    if not text:
        return []
    result = []
    for chunk in re.split(r'[,;\n]+', text):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = re.fullmatch(r'#?0*(\d+)(?:\s*[xX*]\s*(\d+))?',chunk)
        if not match:
            raise ModError(f'Lista de cartas: formato inválido {chunk!r}. Use 1, 2x3, 16*2')
        cid = int(match.group(1))
        qty = int(match.group(2) or '1')
        if cid < 1 or qty < 1 or len(result)+qty > maximum:
            raise ModError(f'Lista de cartas: ID ou quantidade inválida em {chunk!r} (limite {maximum})')
        result.extend([cid]*qty)
    return result


class DuelLab:
    """Estado persistente da simulação; troca de campo não reseta LP/mãos.

    `cards`: registros {id: {tipo_id, defesa...}}, `effects`: por ID da carta.
    Qualquer evento só é aplicado quando trigger() é explicitamente invocado.
    """
    state_fields = ('monsters', 'equipments', 'decks', 'initial_decks', 'graveyards', 'turns',
                    'summoned_turn', 'hands', 'lp', 'damage', 'attacks_used', 'logs')

    def __init__(self, cards: dict, effects: dict, *, summoning_delay: bool = False,
                 initial_lp: int | dict = 8000, default_copies: int = 3):
        self.cards = cards
        self.effects = effects
        self.monsters: list[dict] = []
        self.equipments: list[dict] = []
        self.decks = {side: [] for side in SIDES}
        self.initial_decks = {side: () for side in SIDES}
        self.graveyards = {side: [] for side in SIDES}
        self.summoning_delay = summoning_delay
        self.turns = {side: 0 for side in SIDES}
        self.summoned_turn = {}  # (lado, slot, ID) -> turno em que entrou
        self.hands = {side: [] for side in SIDES}
        values = initial_lp if isinstance(initial_lp, dict) else dict.fromkeys(SIDES, initial_lp)
        self.initial_lp = {side: simulation_nonnegative_int(values[side], 'LP inicial') for side in SIDES}
        self.starting_lp = self.initial_lp['jogador']  # API das versões anteriores
        self.lp = dict(self.initial_lp)
        self.default_copies = default_copies
        self.damage = {}  # (side,slot,card_id) => dano simulado permanente
        self.attacks_used = {}  # (side,slot,card_id) => ataques neste turno
        self.logs = []

    def _snapshot(self, *, include_logs=True):
        return {key: deepcopy(getattr(self, key)) for key in self.state_fields
                if include_logs or key != 'logs'}

    def _restore(self, snapshot):
        for key, value in snapshot.items():
            setattr(self, key, value)

    def fork(self):
        branch = copy(self)
        branch._restore(self._snapshot(include_logs=False))
        branch.logs = []
        return branch

    def card(self, cid):
        c = self.cards.get(int(cid))
        if c is None:
            raise ModError(f'Carta #{cid} não disponível no projeto')
        return c

    def set_deck(self, side: str, ids: list[int]):
        if side not in SIDES:
            raise ModError('Deck: lado inválido.')
        validate_deck(self.cards, self.effects, ids, self.default_copies)
        self.decks[side] = list(ids)
        self.initial_decks[side] = tuple(ids)

    def set_hand(self, side: str, ids: list[int]):
        if side not in SIDES or len(ids) > MAX_HAND:
            raise ModError('Mão: lado inválido ou mais de 5 cartas')
        for cid in ids:
            self.card(cid)
        self.hands[side] = list(ids)

    def set_graveyard(self, side: str, ids: list[int]):
        if side not in SIDES or len(ids) > 300:
            raise ModError('Cemitério: lado inválido ou mais de 300 cartas')
        for cid in ids: self.card(cid)
        self.graveyards[side] = list(ids)

    def draw(self, side: str, quantity: int = 1) -> list[int]:
        if side not in SIDES or quantity < 0:
            raise ModError('Compra: lado ou quantidade inválida.')
        deck, hand = self.decks[side], self.hands[side]
        size = min(quantity, len(deck), MAX_HAND - len(hand))
        drawn = deck[:size]
        del deck[:size]
        hand.extend(drawn)
        return drawn

    def graveyard_type_counts(self):
        return {side: Counter(int(self.card(cid)['tipo_id']) for cid in ids)
                for side, ids in self.graveyards.items()}

    def type_counts(self):
        return {side: Counter(int(self.card(cid)['tipo_id']) for cid in ids)
                for side, ids in self.decks.items()}

    def set_field(self, monsters: list[dict], equipments: list[dict] | None = None):
        # Resolve/valida tudo antes de substituir; se falhar, mantém o estado.
        resolve_field(monsters,self.effects,equipments=equipments or [], catalog=self.cards, zones=self.zones())
        new_keys={(m['lado'],int(m['slot']),int(m['card_id'])) for m in monsters}
        self.damage={key:v for key,v in self.damage.items() if key in new_keys}
        self.summoned_turn={key:v for key,v in self.summoned_turn.items() if key in new_keys}
        for key in new_keys:
            self.summoned_turn.setdefault(key,self.turns[key[0]])
        self.attacks_used={key:v for key,v in self.attacks_used.items() if key in new_keys}
        self.monsters=deepcopy(monsters)
        self.equipments=deepcopy(equipments or [])

    def resolve(self):
        return resolve_field(self.monsters,self.effects,equipments=self.equipments,
                             catalog=self.cards,zones=self.zones())

    def zones(self):
        return {'deck': self.decks, 'deck_inicial': self.initial_decks,
                'mao': self.hands, 'cemiterio': self.graveyards}

    def effective_card(self, side: str, cid: int):
        return project_stats(self.card(cid), cid, side, card_effects(self.effects, cid),
                             self.monsters, catalog=self.cards, zones=self.zones())

    def inspect_zone(self, side: str, zone: str):
        return [self.effective_card(side, cid) for cid in self.zones()[zone][side]]

    def get(self, side: str, slot: int):
        for monster in self.monsters:
            if monster['lado']==side and int(monster['slot'])==int(slot):
                return monster
        return None

    def remove(self, side: str, slot: int):
        monster=self.get(side,slot)
        if monster is None:
            return False
        self.monsters=[m for m in self.monsters if m is not monster]
        keep = []
        for equip in self.equipments:
            if equip['lado'] == side and int(equip['slot']) == int(slot):
                self.graveyards[side].append(int(equip['card_id']))
            else:
                keep.append(equip)
        self.equipments = keep
        self.graveyards[side].append(int(monster['card_id']))
        self.damage.pop((side,int(slot),int(monster['card_id'])),None)
        self.summoned_turn.pop((side,int(slot),int(monster['card_id'])),None)
        self.attacks_used.pop((side,int(slot),int(monster['card_id'])),None)
        return True

    def new_turn(self, side: str) -> None:
        """Reinicia ataques do lado escolhido; não dispara gatilhos de turno."""
        if side not in SIDES:
            raise ModError('Turno: lado inválido')
        self.attacks_used={key:v for key,v in self.attacks_used.items() if key[0] != side}
        self.turns[side] += 1
        self.logs.append({'acao':'novo_turno','lado':side})

    def _attack_timing_error(self, attacker):
        key = (attacker['lado'], attacker['slot'], attacker['card_id'])
        if (self.summoning_delay and self.summoned_turn.get(key) == self.turns[key[0]]
                and not attacker.get('ataque_primeiro_turno', False)):
            return 'Este monstro foi invocado neste turno e não possui Ataca no 1º turno'
        return None

    def preview_attack(self, side: str, slot: int, *, target_slot: int | None = None,
                       against: str | None = 'defesa', board: list[dict] | None = None) -> dict:
        """Resolve the exchange without spending LP, cards or attacks."""
        if side not in SIDES or (against is not None and against not in POSITIONS):
            raise ModError('Combate: lado ou posição alvo inválidos')
        source=self.get(side,slot)
        if source is None or source.get('posicao', 'ataque') != 'ataque':
            raise ModError('Escolha um monstro em posição de ataque.')
        enemy = opposite(side)
        if board is None:
            board = self.resolve()[0]
        indexed={(m['lado'],m['slot']):m for m in board}
        attacker=indexed[(side,int(slot))]
        key=(side,int(slot),int(source['card_id']))
        used=self.attacks_used.get(key,0)
        maximum=attacker['ataques_max']
        blocked = self._attack_timing_error(attacker)
        if blocked:
            raise ModError(blocked)
        if used >= maximum:
            raise ModError(f'Combate: limite de {maximum} ataque(s) por turno atingido; inicie novo turno')
        cost=0
        for raw in card_effects(self.effects, int(source['card_id'])):
            if raw.get('acao') == 'perder_lp_por_ataque' and raw.get('evento') == 'atacar':
                cost += check_effect(raw)['valor']
        if target_slot is not None and not 1 <= int(target_slot) <= 5:
            raise ModError('Combate: slot alvo deve ser de 1 a 5')
        target = indexed.get((enemy,int(target_slot))) if target_slot is not None else None
        if target_slot is not None and target is None and not attacker['nao_bloqueavel']:
            raise ModError('Combate: monstro alvo não encontrado')
        has_blockers=any(m['lado']==enemy for m in board)
        direct = attacker['nao_bloqueavel'] or target_slot is None
        if direct and not attacker['nao_bloqueavel'] and has_blockers:
            raise ModError('Combate: oponente tem monstros; selecione um alvo ou use "Não bloqueável"')
        lost_attacker=0
        lost_defender=0
        destroyed=[]
        if direct:
            target = None
        against = against or (target['posicao'] if target else 'ataque')
        attacker_bonus, target_bonus = guardian_bonuses(attacker['guardian_id'], target['guardian_id']) if target else (0, 0)
        attacker_values = (max(0, attacker['ataque'] + attacker_bonus),
                           max(0, attacker['defesa'] + attacker_bonus))
        target_values = (max(0, target['ataque'] + target_bonus),
                         max(0, target['defesa'] + target_bonus)) if target else None
        atk = attacker_values[0]
        if direct:
            lost_defender=atk
        elif against == 'defesa':
            diff=atk-target_values[1]
            if diff > 0:
                if not target['indestrutivel']:
                    destroyed.append((enemy,target['slot']))
                if attacker['perfurante']:
                    lost_defender=diff
            elif diff < 0:
                lost_attacker=-diff
        else:  # ataque versus ataque
            diff=atk-target_values[0]
            if diff>0:
                lost_defender=diff
                if not target['indestrutivel']:
                    destroyed.append((enemy,target['slot']))
            elif diff<0:
                lost_attacker=-diff
                if not attacker['indestrutivel']:
                    destroyed.append((side,attacker['slot']))
            else:
                if not target['indestrutivel']:
                    destroyed.append((enemy,target['slot']))
                if not attacker['indestrutivel']:
                    destroyed.append((side,attacker['slot']))
        return {'acao':'ataque','origem':(side,slot),
                'alvo':('LP',enemy) if direct else (enemy,target_slot),
                'posicao':against, 'ataques_usados':used+1,'ataques_max':maximum,
                'custo_lp':min(cost,self.lp[side]),
                'dano_lp_jogador':min(self.lp[side], cost+lost_attacker),
                'dano_lp_oponente':min(self.lp[enemy], lost_defender),
                'perfurante':attacker['perfurante'],
                'nao_bloqueavel':attacker['nao_bloqueavel'],
                'atributos_atacante':attacker_values, 'atributos_alvo':target_values,
                'bonus_guardian':(attacker_bonus, target_bonus),
                'destruidos':destroyed}

    def attack(self, side: str, slot: int, *, target_slot: int | None = None,
               against: str | None = 'defesa') -> dict:
        result = self.preview_attack(side, slot, target_slot=target_slot, against=against)
        key = (side, int(slot), int(self.get(side, slot)['card_id']))
        self.attacks_used[key] = result['ataques_usados']
        self.lp[side] -= result['dano_lp_jogador']
        self.lp[opposite(side)] -= result['dano_lp_oponente']
        for target_side, target_slot_to_destroy in result['destruidos']:
            self.remove(target_side, target_slot_to_destroy)
        self.logs.append(result)
        return result

    def hit_monster(self, side: str, slot: int, value: int, *, kind='monstro') -> dict:
        """Dano experimental em HP; proteções de trap/magia evitam o efeito.

        O PS1 original não possui HP por monstro. HP inicial no simulador =
        DEF da carta, mínimo de 1, para tornar possível testar esse efeito.
        """
        if kind not in ('monstro','magia','armadilha'):
            raise ModError('Origem de dano inválida')
        if value < 0:
            raise ModError('Dano inválido')
        unit=self.get(side,slot)
        if unit is None:
            raise ModError('Não existe monstro no slot alvo')
        statuses={ (m['lado'],m['slot']):m for m in self.resolve()[0] }
        resolved=statuses[(side,slot)]
        if kind=='armadilha' and resolved['imune_armadilha'] or kind=='magia' and resolved['imune_magia']:
            return {'aplicado':0,'bloqueado':True,'destruido':False,'hp':None}
        key=(side,slot,int(unit['card_id']))
        hp=max(1,int(unit['defesa']))  # defesa BASE; não a defesa após buffs
        accumulated=self.damage.get(key,0)
        current=max(0,hp-accumulated)
        amount=min(value,current)
        damage=accumulated + amount
        if damage>=hp and resolved['indestrutivel']:
            damage=hp-1
        self.damage[key]=damage
        destroyed=damage>=hp
        if destroyed:
            self.remove(side,slot)
        return {'aplicado':amount,'bloqueado':False,'destruido':destroyed,
                'hp':max(0,hp-damage)}

    def trigger(self, side: str, slot: int, event: str='invocar',
                *, target_side: str | None = None, target_slot: int | None = None,
                kind='monstro') -> list[dict]:
        source=self.get(side,slot)
        if source is None or (event != 'invocar' and not source.get('face_up', True)):
            raise ModError('Escolha um monstro de origem disponível para o gatilho.')
        if kind not in ('monstro','magia','armadilha'):
            raise ModError('Tipo de origem inválido')
        return self.apply_event(int(source['card_id']), side, event, source_slot=slot,
                                target_side=target_side, target_slot=target_slot, kind=kind)

    def apply_event(self, cid, side, event, *, source_slot=None, target_side=None,
                    target_slot=None, kind='monstro', strict=True):
        opposing = opposite(side)
        target_side=target_side or opposing
        if target_side not in SIDES:
            raise ModError('Lado alvo inválido')
        # Transação: um efeito inválido não pode aplicar cura/descarte parcial.
        before=self._snapshot()
        try:
            source = self.get(side, source_slot) if source_slot is not None else None
            visible = source.get('face_up', True) if source is not None else kind != 'armadilha' or event != 'invocar'
            summary = self._apply_trigger(card_effects(self.effects, cid), event, side, opposing,
                                          target_side, target_slot, kind, source_slot, strict)
            for entry in summary:
                record = dict(entry)
                if entry['acao'] in ('dano_lp', 'cura_lp', 'dano_lp_deck_tipo', 'cura_lp_deck_tipo'):
                    record.update(lado=side, carta=cid, evento=event, face_up=visible)
                self.logs.append(record)
            return summary
        except (ModError,ValueError,KeyError,TypeError):
            self._restore(before)
            raise

    def _apply_trigger(self,effects,event,side,opposing,target_side,target_slot,kind,source_slot,strict):
        summary=[]
        for raw in effects:
            if raw.get('evento') != event:
                continue
            eff=check_effect(raw)
            action=eff['acao']; value=eff['valor']
            if action in ('cura_lp_deck_tipo','dano_lp_deck_tipo'):
                typ=eff['tipo_id']
                count=self.type_counts()[side]
                n=sum(count.values()) if typ==-1 else count.get(typ,0)
                applied=value*n
                receiver=side if action=='cura_lp_deck_tipo' else opposing
                old=self.lp[receiver]
                self.lp[receiver]=old+applied if action=='cura_lp_deck_tipo' else max(0,old-applied)
                summary.append({'acao':action,'quantidade':n,'valor':abs(self.lp[receiver]-old),
                                'alvo':receiver})
            elif action=='descartar_alvo':
                removed=[]
                for _ in range(min(value,len(self.hands[opposing]))):
                    removed.append(self.hands[opposing].pop())
                self.graveyards[opposing].extend(removed)
                summary.append({'acao':action,'quantidade':len(removed),'cartas':removed,
                                'alvo':opposing})
            elif action=='dano_monstro_alvo':
                if target_slot is None or self.get(target_side,target_slot) is None:
                    if not strict:
                        continue
                    raise ModError('Selecione um slot para causar dano ao monstro alvo')
                hit=self.hit_monster(target_side,target_slot,value,kind=kind)
                summary.append({'acao':action,'alvo':(target_side,target_slot), **hit})
            elif action in ('dano_lp', 'cura_lp'):
                receiver = opposing if eff['alvo'] == 'inimigo' else side
                delta = value if action == 'cura_lp' else -value
                old = self.lp[receiver]
                self.lp[receiver] = max(0, old + delta)
                summary.append({'acao':action,'alvo':receiver,'valor':abs(self.lp[receiver]-old)})
            elif action in ('aumentar_atk', 'reduzir_atk', 'aumentar_def', 'reduzir_def'):
                receiver = opposing if eff['alvo'] == 'inimigo' else side
                slot = target_slot if target_side == receiver and target_slot else source_slot if receiver == side else None
                unit = self.get(receiver, slot) if slot is not None else None
                if unit is None:
                    if not strict:
                        continue
                    raise ModError('Escolha um monstro para alterar ATK/DEF.')
                resolved = next(m for m in self.resolve()[0] if (m['lado'], m['slot']) == (receiver, slot))
                if resolved.get('imune_' + kind):
                    continue
                key = 'modificador_' + action.rsplit('_', 1)[1]
                delta = value if action.startswith('aumentar_') else -value
                unit[key] = unit.get(key, 0) + delta
                summary.append({'acao':action,'alvo':(receiver, slot),'valor':delta})
        return summary
