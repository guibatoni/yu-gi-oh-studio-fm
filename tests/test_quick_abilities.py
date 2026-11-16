"""Regressões das habilidades rápidas e regras novas de combate (somente simulação)."""
import json
import tempfile
import unittest
from pathlib import Path
from fmstudio.abilities import quick_settings, replace_quick_effects
from fmstudio.continuous import resolve_field
from fmstudio.core import check_effect, ModError, Project
from fmstudio.duel_engine import DuelLab
from fmstudio.drafts import DraftSession


def monster(cid=1,side='jogador',slot=1,atk=1800,deff=1000,typ=0,up=True):
    return {'lado':side,'slot':slot,'card_id':cid,'ataque':atk,'defesa':deff,
            'tipo_id':typ,'face_up':up}


def effects(**settings):
    return replace_quick_effects([],settings)


class QuickAbilities(unittest.TestCase):
    def test_all_presets_validate(self):
        arr=effects(ataques=3,custo_lp=250,monstro_indestrutivel=True,
                    monstro_imune_magia=True,monstro_imune_armadilha=True,
                    dano_perfurante=True,nao_bloqueavel=True,sem_limite_deck=True)
        self.assertEqual(len(arr),8)
        self.assertEqual(quick_settings(arr)['ataques'],3)
        for e in arr: self.assertEqual(check_effect(e),e)

    def test_no_extra_presets_means_empty(self):
        self.assertEqual(effects(ataques=1,custo_lp=0),[])

    def test_idempotent_and_preserves_other_effect(self):
        aura=check_effect({'evento':'continuo','acao':'aura_tipo','alvo':'aliados_tipo',
                           'valor':200,'valor_def':0,'tipo_id':-1})
        a=replace_quick_effects([aura],{'ataques':3,'custo_lp':100})
        b=replace_quick_effects(a,{'ataques':3,'custo_lp':100})
        self.assertEqual(a,b)
        self.assertEqual(len(b),3)
        self.assertEqual(replace_quick_effects(a,{'ataques':1,'custo_lp':0}),[aura])

    def test_reject_conflicts_or_wrong_events(self):
        for data in ({'ataques':4},{'ataques':0},{'custo_lp':-1},{'custo_lp':'x'}):
            with self.subTest(data=data),self.assertRaises(ModError):
                replace_quick_effects([],data)
        self.assertEqual(quick_settings(replace_quick_effects([], {'custo_lp':10**90}))['custo_lp'],10**90)
        with self.assertRaises(ModError):
            check_effect({'evento':'invocar','acao':'monstro_indestrutivel','alvo':'proprio','valor':0})
        with self.assertRaises(ModError):
            check_effect({'evento':'continuo','acao':'sem_limite_deck','alvo':'proprio','valor':0})
        with self.assertRaises(ModError):
            check_effect({'evento':'atacar','acao':'perder_lp_por_ataque','alvo':'proprio','valor':0})

    def test_immunities_both_independent_and_face_down_suppressed(self):
        powers=effects(monstro_indestrutivel=True,monstro_imune_magia=True,
                       monstro_imune_armadilha=True)
        face,_=resolve_field([monster()],{'1':powers})
        self.assertTrue(all(face[0][k] for k in ('indestrutivel','imune_magia','imune_armadilha')))
        down,_=resolve_field([monster(up=False)],{'1':powers})
        self.assertFalse(any(down[0][k] for k in ('indestrutivel','imune_magia','imune_armadilha')))

    def test_traps_and_spells_blocked_by_intrinsic(self):
        lab=DuelLab({1:{'tipo_id':0,'defesa':1000}}, {'1':effects(monstro_imune_magia=True)})
        lab.set_field([monster()])
        self.assertTrue(lab.hit_monster('jogador',1,50,kind='magia')['bloqueado'])
        self.assertFalse(lab.hit_monster('jogador',1,50,kind='armadilha')['bloqueado'])

    def test_normal_1_attack_max(self):
        lab=DuelLab({1:{'tipo_id':0}}, {})
        lab.set_field([monster(atk=100)])
        lab.attack('jogador',1)
        with self.assertRaises(ModError): lab.attack('jogador',1)
        lab.new_turn('jogador')
        lab.attack('jogador',1)
        self.assertEqual(lab.lp['adversario'],7800)

    def test_three_attacks_and_lp_cost_per_attack(self):
        lab=DuelLab({1:{'tipo_id':0}}, {'1':effects(ataques=3,custo_lp=500)})
        lab.set_field([monster(atk=100)])
        for n in range(1,4):
            self.assertEqual(lab.attack('jogador',1)['ataques_usados'],n)
        self.assertEqual(lab.lp['jogador'],6500)
        self.assertEqual(lab.lp['adversario'],7700)
        with self.assertRaises(ModError):lab.attack('jogador',1)
        lab.new_turn('jogador')
        self.assertEqual(lab.attack('jogador',1)['ataques_usados'],1)
        self.assertEqual(lab.lp['jogador'],6000)

    def test_two_attacks_and_same_slot_new_monster(self):
        lab=DuelLab({1:{'tipo_id':0},2:{'tipo_id':0}}, {'1':effects(ataques=2)})
        lab.set_field([monster()]);lab.attack('jogador',1)
        lab.set_field([monster(cid=2,atk=500)])
        self.assertEqual(lab.attack('jogador',1)['ataques_usados'],1)

    def test_piercing_vs_defender_damages_lp(self):
        cards={1:{'tipo_id':0},2:{'tipo_id':0}}
        lab=DuelLab(cards,{'1':effects(dano_perfurante=True)})
        lab.set_field([monster(atk=2000),monster(cid=2,side='adversario',deff=1200)])
        res=lab.attack('jogador',1,target_slot=1,against='defesa')
        self.assertEqual(res['dano_lp_oponente'],800)
        self.assertIsNone(lab.get('adversario',1))

    def test_no_piercing_doesnt_damage_lp_vs_defender(self):
        lab=DuelLab({1:{'tipo_id':0},2:{'tipo_id':0}}, {})
        lab.set_field([monster(atk=2000),monster(cid=2,side='adversario',deff=1200)])
        self.assertEqual(lab.attack('jogador',1,target_slot=1)['dano_lp_oponente'],0)

    def test_indestructible_blocks_battle_destruction(self):
        lab=DuelLab({1:{'tipo_id':0},2:{'tipo_id':0}}, {'2':effects(monstro_indestrutivel=True)})
        lab.set_field([monster(atk=2000),monster(cid=2,side='adversario',deff=1200)])
        lab.attack('jogador',1,target_slot=1)
        self.assertIsNotNone(lab.get('adversario',1))

    def test_unblockable_attacks_directly_even_with_enemy(self):
        lab=DuelLab({1:{'tipo_id':0},2:{'tipo_id':0}}, {'1':effects(nao_bloqueavel=True)})
        lab.set_field([monster(atk=1800),monster(cid=2,side='adversario')])
        res=lab.attack('jogador',1,target_slot=1)
        self.assertEqual(res['dano_lp_oponente'],1800)
        self.assertIsNotNone(lab.get('adversario',1))

    def test_direct_without_unblockable_rejects_and_preserves_lp_and_count(self):
        lab=DuelLab({1:{'tipo_id':0},2:{'tipo_id':0}}, {})
        lab.set_field([monster(),monster(cid=2,side='adversario')])
        with self.assertRaises(ModError): lab.attack('jogador',1)
        self.assertEqual(lab.lp['adversario'],8000)
        self.assertEqual(lab.attacks_used,{})

    def test_deck_copy_cap_and_unlimited_flag(self):
        cards={1:{'tipo_id':0}}
        normal=DuelLab(cards,{})
        with self.assertRaises(ModError):normal.set_deck('jogador',[1]*4)
        self.assertEqual(normal.decks['jogador'],[])
        allowed=DuelLab(cards,{'1':effects(sem_limite_deck=True)})
        allowed.set_deck('jogador',[1]*40)
        self.assertEqual(len(allowed.decks['jogador']),40)
        with self.assertRaises(ModError):allowed.set_deck('jogador',[1]*41)

    def test_saved_project_legacy_schema_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Project.create(Path(d)/'p','Teste')
            p.effects={'1':effects(ataques=3,sem_limite_deck=True)}
            p.save()
            again=Project.open(Path(d)/'p')
            self.assertEqual(again.effects,p.effects)
            self.assertEqual(again.metadata['schema'],1)

    def test_draft_quick_replaces_presets_without_saving(self):
        with tempfile.TemporaryDirectory() as d:
            p=Project.create(Path(d)/'p','Teste')
            draft=DraftSession(p)
            draft.set_quick_abilities(1,{'ataques':2,'custo_lp':250})
            self.assertEqual(len(draft.get_effects(1)),2)
            self.assertTrue(draft.is_dirty)
            self.assertEqual(p.effects,{})

if __name__=='__main__':unittest.main()
