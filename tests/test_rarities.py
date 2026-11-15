"""Regras de raridade e preservação de projetos antigos (sem ROM)."""
import tempfile
import unittest
from pathlib import Path

from fmstudio.rarities import RARITIES, DEFAULT_RARITY, name_style, validate_rarity
from fmstudio.core import Project, ModError, check_card_edit, DEFAULT_NAME_COLOR, _write_csv
from fmstudio.drafts import DraftSession


class RarityTests(unittest.TestCase):
    def test_six_creature_rarities(self):
        assert len(RARITIES) == 6
        expected=['#CBD5E1','#FFFFFF','#FFD84D','#B57AFF','#F04F57','#123A79']
        for i,(code,(label,color)) in enumerate(RARITIES.items()):
            with self.subTest(code=code):
                self.assertEqual(name_style({'tipo_id':0,'raridade':code}),(label,expected[i],code))

    def test_special_type_precedence(self):
        for typ,colour in [(20,'#48D995'),(21,'#FF77C8'),(23,'#579DFF'),(24,'#123A79')]:
            for rarity in RARITIES:
                with self.subTest(typ=typ,rarity=rarity):
                    self.assertEqual(name_style({'tipo_id':typ,'raridade':rarity})[1],colour)

    def test_ritual_not_reclassified(self):
        self.assertEqual(name_style({'tipo_id':22,'raridade':'epica'})[1],'#B57AFF')

    def test_validation_and_legacy(self):
        self.assertEqual(validate_rarity(DEFAULT_RARITY),'comum')
        with self.assertRaises(ValueError):validate_rarity('inventada')
        with self.assertRaises(ModError):check_card_edit({'raridade':'inventada'})
        with tempfile.TemporaryDirectory() as tmp:
            p=Project.create(Path(tmp)/'p','Legacy')
            p.cards[1]={'id':1,'nome':'Legado','descricao':'','cor_nome':DEFAULT_NAME_COLOR,
                'ataque':1000,'defesa':1000,'tipo_id':0,'atributo_id':0,'nivel':4,
                'guardian_1_id':0,'guardian_2_id':0}
            _write_csv(p.folder/'base'/'cartas.csv',[p.cards[1]])
            self.assertEqual(p.get(1)['raridade'],DEFAULT_RARITY)
            p.set_card(1,{'raridade':'lendaria'})
            self.assertEqual(Project.open(p.folder).get(1)['raridade'],'lendaria')

    def test_draft_navigation_and_single_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Project.create(Path(tmp)/'p','Raridades')
            p.cards[1]={'id':1,'nome':'Monstro','descricao':'','ataque':1000,'defesa':1000,
                        'tipo_id':0,'atributo_id':0,'nivel':4,'guardian_1_id':0,'guardian_2_id':0}
            d=DraftSession(p)
            d.stage_card(1,dict(d.get_card(1),raridade='epica',cor_nome='#B57AFF'))
            self.assertTrue(d.is_dirty)
            self.assertNotIn('1',p.edits)
            d.save()
            self.assertEqual(p.get(1)['raridade'],'epica')
            self.assertEqual(p.get(1)['cor_nome'],'#B57AFF')

if __name__=='__main__':unittest.main()
