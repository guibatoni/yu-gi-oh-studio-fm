"""Laboratório de duelo: efeitos ativados por evento, deck, mãos e equipamentos.

Este é um simulador de regras NOVAS, não as regras reais do PS1. Para dano
em monstros é usada uma 'resistência' experimental com base em DEF (mínimo 1),
independente dos cálculos originais de combate. A lista do deck é integral
(40 cartas no máximo) e estática para a partida; não é o monte de compra.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
import re

from .continuous import SIDES, resolve_field
from .core import ModError, check_effect

MAX_DECK = 40
MAX_HAND = 5
MAX_LP = 99999


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
        if cid < 1 or cid > 32766 or qty < 1 or qty > maximum or len(result)+qty > maximum:
            raise ModError(f'Lista de cartas: ID ou quantidade inválida em {chunk!r} (limite {maximum})')
        result.extend([cid]*qty)
    return result


class DuelLab:
    """Estado persistente da simulação; troca de campo não reseta LP/mãos.

    `cards`: registros {id: {tipo_id, defesa...}}, `effects`: por ID da carta.
    Qualquer evento só é aplicado quando trigger() é explicitamente invocado.
    """
    def __init__(self, cards: dict, effects: dict, *, summoning_delay: bool = False):
        self.cards = cards
        self.effects = effects
        self.monsters: list[dict] = []
        self.equipments: list[dict] = []
        self.decks = {side: [] for side in SIDES}
        self.graveyards = {side: [] for side in SIDES}
        self.summoning_delay = summoning_delay
        self.turns = {side: 0 for side in SIDES}
        self.summoned_turn = {}  # (lado, slot, ID) -> turno em que entrou
        self.hands = {side: [] for side in SIDES}
        self.lp = {side: 8000 for side in SIDES}
        self.damage = {}  # (side,slot,card_id) => dano simulado permanente
        self.attacks_used = {}  # (side,slot,card_id) => ataques neste turno
        self.logs = []

    def card(self, cid):
        c = self.cards.get(int(cid))
        if c is None:
            raise ModError(f'Carta #{cid} não disponível no projeto')
        return c

    def set_deck(self, side: str, ids: list[int]):
        if side not in SIDES or len(ids) > MAX_DECK:
            raise ModError('Deck: lado inválido ou mais de 40 cartas')
        counts = Counter(ids)
        for cid, quantity in counts.items():
            self.card(cid)
            unlimited = any(e.get('acao') == 'sem_limite_deck' and
                            e.get('evento') == 'regra_deck' and
                            check_effect(e)['acao'] == 'sem_limite_deck'
                            for e in self.effects.get(str(cid), self.effects.get(cid, [])))
            if quantity > 3 and not unlimited:
                raise ModError(f'Deck: carta #{cid} tem {quantity} cópias (máximo padrão 3). '
                               'Marque "Sem limite de cópias" na carta para permitir mais.')
        self.decks[side] = list(ids)

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

    def graveyard_type_counts(self):
        return {side: Counter(int(self.card(cid)['tipo_id']) for cid in ids)
                for side, ids in self.graveyards.items()}

    def type_counts(self):
        return {side: Counter(int(self.card(cid)['tipo_id']) for cid in ids)
                for side, ids in self.decks.items()}

    def set_field(self, monsters: list[dict], equipments: list[dict] | None = None):
        # Resolve/valida tudo antes de substituir; se falhar, mantém o estado.
        resolve_field(monsters,self.effects,deck_types=self.type_counts(),equipments=equipments or [],
                      deck_cards=self.decks,cemetery_types=self.graveyard_type_counts())
        new_keys={(m['lado'],int(m['slot']),int(m['card_id'])) for m in monsters}
        self.damage={key:v for key,v in self.damage.items() if key in new_keys}
        self.summoned_turn={key:v for key,v in self.summoned_turn.items() if key in new_keys}
        for key in new_keys:
            self.summoned_turn.setdefault(key,self.turns[key[0]])
        self.attacks_used={key:v for key,v in self.attacks_used.items() if key in new_keys}
        self.monsters=deepcopy(monsters)
        self.equipments=deepcopy(equipments or [])

    def resolve(self):
        return resolve_field(self.monsters,self.effects,deck_types=self.type_counts(),
                             equipments=self.equipments,deck_cards=self.decks,
                             cemetery_types=self.graveyard_type_counts())

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
        self.equipments=[e for e in self.equipments if not (e['lado']==side and int(e['slot'])==int(slot))]
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

    def attack(self, side: str, slot: int, *, target_slot: int | None = None,
               against: str = 'defesa') -> dict:
        """Simula combate: ataque versus DEF/ATK, perfurante e ataque direto.

        Não reproduz todo o motor original do PS1 e não implementa fase de
        bloqueadores de MTGA: 'não bloqueável' significa ataque direto mesmo
        quando o adversário controla monstros.
        """
        if side not in SIDES or against not in ('ataque','defesa'):
            raise ModError('Combate: lado ou posição alvo inválidos')
        source=self.get(side,slot)
        if source is None or not source.get('face_up',True):
            raise ModError('Combate: escolha uma criatura sua virada para cima')
        enemy = 'adversario' if side == 'jogador' else 'jogador'
        board,_ = self.resolve()
        indexed={(m['lado'],m['slot']):m for m in board}
        attacker=indexed[(side,int(slot))]
        key=(side,int(slot),int(source['card_id']))
        used=self.attacks_used.get(key,0)
        maximum=attacker['ataques_max']
        if (self.summoning_delay and self.summoned_turn.get(key)==self.turns[side]
                and not attacker['ataque_primeiro_turno']):
            raise ModError('Este monstro foi invocado neste turno e não possui Ataca no 1º turno')
        if used >= maximum:
            raise ModError(f'Combate: limite de {maximum} ataque(s) por turno atingido; inicie novo turno')
        cost=0
        for raw in self.effects.get(str(source['card_id']), self.effects.get(int(source['card_id']), [])):
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
        atk=attacker['ataque']
        if direct:
            lost_defender=atk
        elif against == 'defesa':
            diff=atk-target['defesa']
            if diff > 0:
                if not target['indestrutivel']:
                    destroyed.append((enemy,target['slot']))
                if attacker['perfurante']:
                    lost_defender=diff
            elif diff < 0:
                lost_attacker=-diff
        else:  # ataque versus ataque
            diff=atk-target['ataque']
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
        self.attacks_used[key]=used+1
        old_self=self.lp[side]
        old_enemy=self.lp[enemy]
        self.lp[side]=max(0,old_self-cost-lost_attacker)
        self.lp[enemy]=max(0,old_enemy-lost_defender)
        for target_side,target_slot_to_destroy in destroyed:
            self.remove(target_side,target_slot_to_destroy)
        result={'acao':'ataque','origem':(side,slot),
                'alvo':('LP',enemy) if direct else (enemy,target_slot),
                'posicao':against, 'ataques_usados':used+1,'ataques_max':maximum,
                'custo_lp':min(cost,old_self),
                'dano_lp_jogador':old_self-self.lp[side],
                'dano_lp_oponente':old_enemy-self.lp[enemy],
                'perfurante':attacker['perfurante'],
                'nao_bloqueavel':attacker['nao_bloqueavel'],
                'destruidos':destroyed}
        self.logs.append(result)
        return result

    def hit_monster(self, side: str, slot: int, value: int, *, kind='monstro') -> dict:
        """Dano experimental em HP; proteções de trap/magia evitam o efeito.

        O PS1 original não possui HP por monstro. HP inicial no simulador =
        DEF da carta, mínimo de 1, para tornar possível testar esse efeito.
        """
        if kind not in ('monstro','magia','armadilha'):
            raise ModError('Origem de dano inválida')
        if not 0 <= value <= MAX_LP:
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
        if source is None or not source.get('face_up',True):
            raise ModError('Escolha um monstro de origem virado para cima')
        if kind not in ('monstro','magia','armadilha'):
            raise ModError('Tipo de origem inválido')
        opposing='adversario' if side=='jogador' else 'jogador'
        target_side=target_side or opposing
        if target_side not in SIDES:
            raise ModError('Lado alvo inválido')
        cid=int(source['card_id'])
        summary=[]
        # Transação: um efeito inválido não pode aplicar cura/descarte parcial.
        before=(deepcopy(self.monsters),deepcopy(self.equipments),
                deepcopy(self.hands),dict(self.lp),dict(self.damage),list(self.logs))
        effects=self.effects.get(str(cid),self.effects.get(cid,[]))
        try:
            return self._apply_trigger(effects, event, side, opposing,
                                       target_side, target_slot, kind, summary)
        except (ModError,ValueError,KeyError,TypeError):
            (self.monsters,self.equipments,self.hands,self.lp,self.damage,self.logs)=before
            raise

    def _apply_trigger(self,effects,event,side,opposing,target_side,target_slot,kind,summary):
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
                self.lp[receiver]=min(MAX_LP,old+applied) if action=='cura_lp_deck_tipo' else max(0,old-applied)
                summary.append({'acao':action,'quantidade':n,'valor':abs(self.lp[receiver]-old),
                                'alvo':receiver})
            elif action=='descartar_alvo':
                removed=[]
                for _ in range(min(value,len(self.hands[opposing]))):
                    removed.append(self.hands[opposing].pop())
                summary.append({'acao':action,'quantidade':len(removed),'cartas':removed,
                                'alvo':opposing})
            elif action=='dano_monstro_alvo':
                if target_slot is None:
                    raise ModError('Selecione um slot para causar dano ao monstro alvo')
                hit=self.hit_monster(target_side,target_slot,value,kind=kind)
                summary.append({'acao':action,'alvo':(target_side,target_slot), **hit})
            # Os efeitos convencionais antigos continuam no simulador original.
        self.logs.extend(summary)
        return summary
