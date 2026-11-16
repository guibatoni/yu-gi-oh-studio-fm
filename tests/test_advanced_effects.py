"""Novos cenários de v0.8: deck, dano, descarte, encantamentos e auras."""
import unittest
from fmstudio.core import check_effect, ModError
from fmstudio.duel_engine import DuelLab,parse_card_ids
from fmstudio.continuous import resolve_field

FAIRY=8
DRAGON=0


def m(side='jogador',slot=1,cid=1,typ=FAIRY,atk=1000,defense=1200,face=True):
    return {'lado':side,'slot':slot,'card_id':cid,'tipo_id':typ,
            'ataque':atk,'defesa':defense,'face_up':face}


def effect(action,*,event='invocar',target=None,value=100,typ=FAIRY,defense=0,scope='aliados'):
    target = target or ('monstro_equipado' if action.startswith('equip_') else
                        'aliados_tipo' if action=='aura_tipo' else
                        'monstro_alvo' if action=='dano_monstro_alvo' else
                        'inimigo' if action in ('dano_lp_deck_tipo','descartar_alvo') else 'proprio')
    e={'evento':event,'acao':action,'alvo':target,'valor':value,'tipo_id':typ,
       'valor_def':defense,'escopo':scope}
    return check_effect(e)


class AdvancedTests(unittest.TestCase):
    def test_simulator_lp_above_previous_cap(self):
        from fmstudio.duel_engine import DuelLab
        big=1234567890123456789012345
        lab=DuelLab({1:{'tipo_id':0}},{},initial_lp=big)
        self.assertEqual(lab.lp['jogador'],big)
        self.assertEqual(lab.starting_lp,big)
        lab.lp['jogador']+=big
        self.assertEqual(lab.lp['jogador'],2*big)


    def setUp(self):
        self.cards={1:{'tipo_id':DRAGON,'ataque':2000,'defesa':1500},
                    2:{'tipo_id':FAIRY,'ataque':1000,'defesa':1200},
                    3:{'tipo_id':FAIRY,'ataque':600,'defesa':500},
                    4:{'tipo_id':DRAGON,'ataque':900,'defesa':300},
                    5:{'tipo_id':DRAGON,'ataque':0,'defesa':0}}

    def lab(self, effects=None):
        return DuelLab(self.cards,effects or {})

    def test_deck_text_repetition_and_max(self):
        self.assertEqual(parse_card_ids('1x3, #016*2; 4'), [1,1,1,16,16,4])
        self.assertEqual(parse_card_ids(''), [])
        with self.assertRaises(ModError):parse_card_ids('1x41')
        self.assertEqual(parse_card_ids('32767'),[32767])
        with self.assertRaises(ModError):parse_card_ids('1 and 2')
        with self.assertRaises(ModError):parse_card_ids('1,-2')

    def test_any_type_auras_and_scopes(self):
        aura=effect('aura_tipo',event='continuo',value=150,defense=80,typ=-1)
        board=[m(cid=1,typ=DRAGON),m(slot=2,cid=2),m(side='adversario',slot=1,cid=3)]
        resolved,ev=resolve_field(board,{'1':[aura]})
        self.assertEqual([z['ataque'] for z in resolved],[1150,1150,1000])
        self.assertEqual(len(ev),2)
        aura['escopo']='todos'
        self.assertEqual([z['ataque'] for z in resolve_field(board,{'1':[aura]})[0]], [1150,1150,1150])

    def test_receives_per_any_card_while_field_changes(self):
        effects={'1':[effect('bonus_por_tipo',event='continuo',value=200,typ=-1,scope='todos')]}
        b=[m(cid=1,typ=DRAGON),m(slot=2,cid=2),m(side='adversario',cid=3)]
        self.assertEqual(resolve_field(b,effects)[0][0]['ataque'],1600)
        self.assertEqual(resolve_field(b[:1],effects)[0][0]['ataque'],1200)

    def test_deck_count_adds_attack_and_defense_to_source(self):
        eff=effect('bonus_deck_tipo',event='continuo',value=200,defense=75)
        lab=self.lab({'1':[eff]})
        lab.set_deck('jogador',[2,2,2,4,1])
        lab.set_field([m(cid=1,typ=DRAGON)])
        res,_=lab.resolve()
        self.assertEqual((res[0]['ataque'],res[0]['defesa']), (1600,1425))
        self.assertEqual(lab.resolve()[0],res)
        lab.set_deck('jogador',[4,1])
        self.assertEqual(lab.resolve()[0][0]['ataque'],1000)

    def test_deck_type_all_and_opponent_scope(self):
        eff=effect('bonus_deck_tipo',event='continuo',value=50,typ=-1,scope='inimigos')
        lab=self.lab({'1':[eff]})
        lab.set_deck('adversario',[1,2,3,4])
        lab.set_field([m(cid=1,typ=DRAGON,atk=2000)])
        self.assertEqual(lab.resolve()[0][0]['ataque'],2200)

    def test_gain_lp_from_deck_type_once(self):
        eff=effect('cura_lp_deck_tipo',value=200)
        lab=self.lab({'1':[eff]})
        lab.lp['jogador']=7000
        lab.set_deck('jogador',[2,3,2,4])
        lab.set_field([m(cid=1,typ=DRAGON)])
        self.assertEqual(lab.trigger('jogador',1)[0]['valor'],600)
        self.assertEqual(lab.lp['jogador'],7600)
        lab.resolve()  # recalcular não reativa cura
        self.assertEqual(lab.lp['jogador'],7600)

    def test_damage_lp_by_deck_type(self):
        eff=effect('dano_lp_deck_tipo',value=300)
        lab=self.lab({'1':[eff]})
        lab.set_deck('jogador',[2,3,4])
        lab.set_field([m(cid=1,typ=DRAGON)])
        lab.trigger('jogador',1)
        self.assertEqual(lab.lp['adversario'],7400)
        lab.resolve()
        self.assertEqual(lab.lp['adversario'],7400)

    def test_discard_enemy_hand_and_never_negative(self):
        lab=self.lab({'1':[effect('descartar_alvo',value=3)]})
        lab.set_hand('adversario',[2,3])
        lab.set_field([m(cid=1,typ=DRAGON)])
        self.assertEqual(lab.trigger('jogador',1)[0]['quantidade'],2)
        self.assertEqual(lab.hands['adversario'],[])
        self.assertEqual(lab.trigger('jogador',1)[0]['quantidade'],0)

    def test_damage_to_monster_kills_and_equip_removed(self):
        lab=self.lab({'1':[effect('dano_monstro_alvo',value=500)]})
        lab.set_field([m(cid=1,typ=DRAGON),m('adversario',1,4,DRAGON,900,300)])
        result=lab.trigger('jogador',1,target_side='adversario',target_slot=1)
        self.assertTrue(result[0]['destruido'])
        self.assertIsNone(lab.get('adversario',1))

    def test_damage_accumulates_across_two_attacks(self):
        lab=self.lab()
        lab.set_field([m('adversario',1,4,DRAGON,900,300)])
        self.assertEqual(lab.hit_monster('adversario',1,100)['hp'],200)
        self.assertEqual(lab.hit_monster('adversario',1,100)['hp'],100)
        self.assertTrue(lab.hit_monster('adversario',1,100)['destruido'])

    def test_trap_immunity_stops_trap_but_not_spell(self):
        equip=effect('equip_imune_armadilha',event='equipado',target='monstro_equipado',value=0)
        lab=self.lab({'3':[equip]})
        lab.set_field([m('adversario',1,4,DRAGON,900,300)],
                      [{'lado':'adversario','slot':1,'card_id':3}])
        self.assertTrue(lab.hit_monster('adversario',1,500,kind='armadilha')['bloqueado'])
        self.assertTrue(lab.hit_monster('adversario',1,500,kind='magia')['destruido'])

    def test_magic_trap_immunity_stops_both(self):
        equip=effect('equip_imune_magia_armadilha',event='equipado',target='monstro_equipado',value=0)
        lab=self.lab({'3':[equip]})
        lab.set_field([m('adversario',1,4,DRAGON,900,300)],
                      [{'lado':'adversario','slot':1,'card_id':3}])
        self.assertTrue(lab.hit_monster('adversario',1,500,kind='magia')['bloqueado'])
        self.assertTrue(lab.hit_monster('adversario',1,500,kind='armadilha')['bloqueado'])
        self.assertTrue(lab.hit_monster('adversario',1,500,kind='monstro')['destruido'])

    def test_indestructible_survives_lethal_until_unequipped(self):
        equip=effect('equip_indestrutivel',event='equipado',target='monstro_equipado',value=0)
        lab=self.lab({'3':[equip]})
        field=[m('adversario',1,4,DRAGON,900,300)]
        lab.set_field(field,[{'lado':'adversario','slot':1,'card_id':3}])
        hit=lab.hit_monster('adversario',1,10000)
        self.assertFalse(hit['destruido'])
        self.assertEqual(hit['hp'],1)
        lab.set_field(field)
        self.assertTrue(lab.hit_monster('adversario',1,1)['destruido'])

    def test_equipment_adds_attack_and_removed_with_source(self):
        lab=self.lab({'3':[effect('equip_atk',event='equipado',target='monstro_equipado',value=600)]})
        field=[m(cid=1,typ=DRAGON,atk=2000)]
        lab.set_field(field,[{'lado':'jogador','slot':1,'card_id':3}])
        self.assertEqual(lab.resolve()[0][0]['ataque'],2600)
        self.assertEqual(lab.resolve()[0][0]['ataque'],2600)
        lab.set_field(field)
        self.assertEqual(lab.resolve()[0][0]['ataque'],2000)

    def test_both_aura_and_equip_stack(self):
        lab=self.lab({'1':[effect('aura_tipo',event='continuo',value=400,typ=-1)],
                      '3':[effect('equip_atk',event='equipado',target='monstro_equipado',value=300)]})
        lab.set_field([m(cid=1,typ=DRAGON,atk=2000)],
                      [{'lado':'jogador','slot':1,'card_id':3}])
        self.assertEqual(lab.resolve()[0][0]['ataque'],2700)

    def test_type_any_valid_and_bad_settings_rejected(self):
        e=effect('aura_tipo',event='continuo',value=100,typ=-1,scope='inimigos')
        self.assertEqual(e['tipo_id'],-1)
        with self.assertRaises(ModError): effect('aura_tipo',event='continuo',value=100,typ=25)
        with self.assertRaises(ModError): effect('equip_imune_armadilha',event='equipado',value=2)
        with self.assertRaises(ModError): effect('descartar_alvo',value=6)

    def test_invalid_equipment_does_not_modify_field(self):
        lab=self.lab()
        lab.set_field([m(cid=1,typ=DRAGON)])
        before=lab.monsters.copy()
        with self.assertRaises(ModError):
            lab.set_field([m(cid=1,typ=DRAGON)],[{'lado':'jogador','slot':99,'card_id':2}])
        self.assertEqual(lab.monsters,before)

    def test_summon_never_fires_by_recalculation(self):
        lab=self.lab({'1':[effect('dano_lp_deck_tipo',value=100)]})
        lab.set_deck('jogador',[2,2])
        lab.set_field([m(cid=1,typ=DRAGON)])
        lab.resolve(); lab.resolve()
        self.assertEqual(lab.lp['adversario'],8000)
        lab.trigger('jogador',1)
        self.assertEqual(lab.lp['adversario'],7800)

    def test_zero_def_hp_is_minimum_one(self):
        lab=self.lab()
        lab.set_field([m('adversario',1,5,DRAGON,0,0)])
        self.assertTrue(lab.hit_monster('adversario',1,1)['destruido'])

if __name__=='__main__':unittest.main()

class TransactionTests(unittest.TestCase):
    def test_failed_second_effect_rolls_back_lp_and_hand(self):
        cards={1:{'tipo_id':0,'defesa':2000},2:{'tipo_id':8,'defesa':1200}}
        events={'1':[
            check_effect({'evento':'invocar','acao':'cura_lp_deck_tipo','alvo':'proprio','valor':100,'tipo_id':8}),
            check_effect({'evento':'invocar','acao':'dano_monstro_alvo','alvo':'monstro_alvo','valor':400}),
        ]}
        lab=DuelLab(cards,events)
        lab.set_deck('jogador',[2,2])
        lab.set_field([m(cid=1,typ=0)])
        with self.assertRaises(ModError):
            lab.trigger('jogador',1)  # alvo monstro ausente
        self.assertEqual(lab.lp['jogador'],8000)
        self.assertEqual(lab.logs,[])
