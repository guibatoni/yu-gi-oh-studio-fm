import json
import tempfile
import unittest
from pathlib import Path
from fmstudio.core import Project, ModError, DEFAULT_NAME_COLOR
from fmstudio.drafts import DraftSession

CARD = dict(id=1,nome='Original',descricao='Exemplo',ataque=3000,defesa=2500,
            tipo_id=1,atributo_id=1,nivel=8,guardian_1_id=1,guardian_2_id=2,
            valor_hex='00000000',offset_no_slus='0x000')
CARD2 = dict(CARD, id=2, nome='Segunda',ataque=1000)

class DraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Project.create(Path(self.temp.name)/'mod','Mod antigo')
        self.project.cards = {1: dict(CARD), 2: dict(CARD2)}
        self.drafts=DraftSession(self.project)

    def test_time_wizard_restores_spellcaster_even_when_iso_says_equip(self):
        self.project.cards[16]=dict(CARD,id=16,nome='Time Wizard',
                                    tipo_id=23,ataque=500,defesa=400)
        card=self.drafts.get_card(16)
        card.update({'tipo_id':24,'ataque':3000,'defesa':400})
        self.drafts.stage_card(16,card)
        self.drafts.add_effect(16,{'evento':'invocar','acao':'aumentar_atk',
                                   'alvo':'proprio','valor':500})
        self.assertEqual(self.drafts.original_type_target(16),1)
        self.drafts.restore_original_type(16)
        now=self.drafts.get_card(16)
        self.assertEqual((now['tipo_id'],now['ataque'],now['defesa']),
                         (1,3000,400))
        self.assertEqual(len(self.drafts.get_effects(16)),1)
        self.drafts.save()
        self.assertEqual(self.project.get(16)['tipo_id'],1)
        self.assertEqual(self.project.get(16)['ataque'],3000)

    def test_restore_type_preserves_stats_and_effects(self):
        original_type=self.project.cards[1]['tipo_id']
        changed=self.drafts.get_card(1)
        changed.update({'tipo_id':23,'ataque':3000,'nome':'Teste de tipo'})
        self.drafts.stage_card(1,changed)
        self.drafts.add_effect(1,{'evento':'invocar','acao':'aumentar_atk',
                                  'alvo':'proprio','valor':500})
        self.assertEqual(self.drafts.get_card(1)['tipo_id'],23)
        self.drafts.restore_original_type(1)
        recovered=self.drafts.get_card(1)
        self.assertEqual(recovered['tipo_id'],original_type)
        self.assertEqual(recovered['ataque'],3000)
        self.assertEqual(recovered['nome'],'Teste de tipo')
        self.assertEqual(len(self.drafts.get_effects(1)),1)
        self.drafts.save()
        self.assertEqual(self.project.get(1)['tipo_id'],original_type)

    def test_navigation_keeps_edits_until_manual_save(self):
        first=self.drafts.get_card(1)
        first.update(nome='Dragão RUBI',cor_nome='#ff2244',ataque='4000')
        self.drafts.stage_card(1,first)
        second=self.drafts.get_card(2)
        second.update(nome='Carta azul',cor_nome='#33aaff')
        self.drafts.stage_card(2,second)
        self.assertTrue(self.drafts.is_dirty)
        self.assertEqual(self.drafts.count,2)
        self.assertFalse(self.project.edits)
        self.assertEqual(self.drafts.get_card(1)['ataque'],'4000')
        self.assertEqual(Project.open(self.project.folder).edits,{})
        self.assertEqual(self.drafts.save(),2)
        self.assertFalse(self.drafts.is_dirty)
        new=Project.open(self.project.folder)
        self.assertEqual(new.edits['1']['cor_nome'],'#FF2244')
        self.assertEqual(new.edits['2']['cor_nome'],'#33AAFF')
        self.assertEqual(new.edits['1']['ataque'],4000)
        self.assertEqual(new.edits['2']['nome'],'Carta azul')

    def test_staged_effects_saved_only_with_button(self):
        effect={'evento':'invocar','acao':'aumentar_atk','alvo':'proprio','valor':'500'}
        self.drafts.add_effect(1,effect)
        self.assertEqual(self.project.effects,{})
        self.assertEqual(self.drafts.simulate(1,'invocar')[0]['ataque'],3500)
        self.assertEqual(self.drafts.save(),1)
        self.assertEqual(Project.open(self.project.folder).effects['1'][0]['valor'],500)
        self.drafts.remove_effect(1,0)
        self.assertEqual(len(self.project.effects['1']),1)
        self.drafts.save()
        self.assertEqual(Project.open(self.project.folder).effects,{})

    def test_incomplete_value_not_lost_on_navigation_failed_save(self):
        value=self.drafts.get_card(1)
        value['ataque']=''
        self.drafts.stage_card(1,value)
        self.drafts.stage_card(2,dict(self.drafts.get_card(2),nome='Alteração válida'))
        with self.assertRaises(ModError):
            self.drafts.save()
        self.assertEqual(Project.open(self.project.folder).edits,{})
        self.assertEqual(self.drafts.count,2)
        value['ataque']='3500'
        self.drafts.stage_card(1,value)
        self.assertEqual(self.drafts.save(),2)
        self.assertEqual(Project.open(self.project.folder).edits['1']['ataque'],3500)

    def test_restore_saved_card_at_next_commit(self):
        self.project.set_card(1,{'nome':'Nome novo','cor_nome':'#FF0000'})
        self.drafts.reset_card(1)
        self.assertEqual(self.project.get(1)['nome'],'Nome novo')
        self.assertEqual(self.drafts.get_card(1)['nome'],'Original')
        self.drafts.save()
        self.assertEqual(self.project.get(1)['nome'],'Original')
        self.assertEqual(self.project.get(1)['cor_nome'],DEFAULT_NAME_COLOR)

    def test_default_color_old_project_and_hex_validation(self):
        self.assertEqual(self.project.get(1)['cor_nome'],DEFAULT_NAME_COLOR)
        for bad in ('red','fff','#GGGGGG','#FFF',''):
            with self.subTest(bad=bad):
                self.drafts.stage_card(1,dict(self.drafts.get_card(1),cor_nome=bad))
                with self.assertRaises(ModError):
                    self.drafts.save()
        self.drafts.stage_card(1,dict(self.drafts.get_card(1),cor_nome=DEFAULT_NAME_COLOR))
        self.assertFalse(self.drafts.is_dirty)

    def test_fusions_untouched_and_single_backup(self):
        file=self.project.folder/'base'/'fusoes.csv'
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text('material_1;material_2;resultado\n1;2;3\n')
        old=file.read_bytes()
        self.drafts.stage_card(1,dict(self.drafts.get_card(1),nome='Mudei'))
        self.drafts.stage_card(2,dict(self.drafts.get_card(2),nome='Também'))
        self.drafts.save()
        backups=list((self.project.folder/'backups').glob('projeto_*.json'))
        self.assertEqual(len(backups),1)
        self.assertEqual(file.read_bytes(),old)

if __name__=='__main__': unittest.main()
