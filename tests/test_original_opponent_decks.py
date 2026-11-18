"""Criar/recuperar decks de adversários sem inventar cartas ou reescrever a ISO."""
import tempfile
from pathlib import Path
import unittest
from copy import deepcopy

from fmstudio.core import ModError, Project
from fmstudio.mod_data import CONFIG_KEY, DROP_FROM_DECK, DECK_DROP_WEIGHTS, normalize_rules, save_rules
from fmstudio.original_opponent_decks import (
    original_opponent_profile, original_deck_summary, is_original_deck, restored_rules,
)
from fmstudio.tables import CARD_COUNT, DECK_SIZE


class OriginalOpponentDeckTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project=Project.create(Path(self.directory.name)/'mod', 'Test ISO')
        self.project.cards = {
            cid: {'id':cid,'nome':f'Carta {cid}','tipo_id':0}
            for cid in range(1,CARD_COUNT+1)
        }
        self.base=self.project.folder/'base'
        self.base.mkdir(parents=True,exist_ok=True)

    def write(self, lines):
        path=self.base/'decks_drops.csv'
        path.write_text('duelista_id;grupo;carta_id;peso\n'+'\n'.join(lines)+'\n',
                        encoding='utf-8-sig')
        return path

    def test_reads_exact_source_weights_without_reassigning_cards(self):
        path=self.write([
            '1;deck;16;700', '1;deck;10;548', '1;deck;69;800',
            '1;pow;461;2048', '2;deck;705;2048',
        ])
        original=path.read_bytes()
        result=original_opponent_profile(self.project,1)
        self.assertEqual(result,{'cartas':[], 'pools':[{'compras':40,
            'pesos':{10:548,16:700,69:800}}]})
        self.assertEqual(original_deck_summary(result)['peso_total'],2048)
        self.assertEqual(original_deck_summary(result)['cartas_distintas'],3)
        self.assertEqual(path.read_bytes(), original)
        second=original_opponent_profile(self.project,2)
        self.assertEqual(second['pools'][0]['pesos'],{705:2048})
        self.assertNotIn(461,result['pools'][0]['pesos'])

    def test_cleans_only_selected_duelist_custom_deck_and_difficulty(self):
        self.write(['1;deck;16;2048'])
        old={'lp_inicial':12000,'ia_ps1':'dificil',
             'duelistas':{
                '1':{'deck':{'cartas':[1]*40,'pools':[]},
                     'campanha_dificil':{'nivel':'5.0'},
                     'drops':{'pow':{16:55}},
                     DROP_FROM_DECK:True,
                     DECK_DROP_WEIGHTS:{'pow':{16:2}}},
                '2':{'deck':{'cartas':[2]*40,'pools':[]},'lp':5000}}}
        before=deepcopy(old)
        restored=restored_rules(old,1)
        self.assertEqual(old,before)
        self.assertNotIn('deck',restored['duelistas']['1'])
        self.assertNotIn('campanha_dificil',restored['duelistas']['1'])
        self.assertEqual(restored['duelistas']['1']['drops'],{'pow':{16:55}})
        self.assertEqual(restored['duelistas']['1'][DECK_DROP_WEIGHTS],{'pow':{16:2}})
        self.assertTrue(restored['duelistas']['1'][DROP_FROM_DECK])
        self.assertEqual(restored['duelistas']['2'],old['duelistas']['2'])
        self.assertEqual(restored['lp_inicial'],12000)
        self.assertEqual(restored['ia_ps1'],'dificil')

    def test_original_equivalence_requires_same_weights_and_40_draws(self):
        self.write(['1;deck;16;700','1;deck;10;1348'])
        orig=original_opponent_profile(self.project,1)
        self.assertTrue(is_original_deck(orig,orig))
        same=deepcopy(orig)
        same['pools'][0]['pesos']={'10':1348,'16':700}
        self.assertTrue(is_original_deck(same,orig))
        same['pools'][0]['pesos']['16']=701
        self.assertFalse(is_original_deck(same,orig))
        self.assertFalse(is_original_deck({'cartas':[16]*40,'pools':[]},orig))
        self.assertFalse(is_original_deck({'cartas':[],'pools':[{'compras':39,'pesos':{16:700,10:1348}}]},orig))

    def test_restore_is_persistent_and_never_touches_base_csv(self):
        path=self.write(['1;deck;10;1024','1;deck;16;1024'])
        original=path.read_bytes()
        before={'duelistas':{'1':{'deck':{'cartas':[1]*40,'pools':[]},
                                  'campanha_dificil':{'nivel':'4.2'},
                                  'drops':{'pow':{16:2048}}}}}
        save_rules(self.project,before)
        save_rules(self.project,restored_rules(
            self.project.metadata[CONFIG_KEY],1))
        self.assertNotIn('deck',self.project.metadata[CONFIG_KEY]['duelistas']['1'])
        self.assertEqual(self.project.metadata[CONFIG_KEY]['duelistas']['1']['drops'],
                         {'pow':{16:2048}})
        self.assertEqual(path.read_bytes(),original)
        reopened=Project.open(self.project.folder)
        self.assertNotIn('deck',reopened.metadata[CONFIG_KEY]['duelistas']['1'])
        self.assertTrue(list((self.project.folder/'backups').glob('projeto_*.json')))

    def test_rejects_missing_corrupt_duplicate_and_foreign_source(self):
        with self.assertRaisesRegex(ModError,'não foi encontrada'):
            original_opponent_profile(self.project,1)
        self.write(['2;deck;16;2048'])
        with self.assertRaisesRegex(ModError,'Não foram encontrados'):
            original_opponent_profile(self.project,1)
        self.write(['1;deck;16;100','1;deck;16;1948'])
        with self.assertRaisesRegex(ModError,'repetida'):
            original_opponent_profile(self.project,1)
        self.write(['1;deck;900;2048'])
        with self.assertRaisesRegex(ModError,'fora da tabela original'):
            original_opponent_profile(self.project,1)
        self.write(['1;deck;16;-3'])
        with self.assertRaisesRegex(ModError,'não negativos'):
            original_opponent_profile(self.project,1)
        with self.assertRaises(ModError):
            original_opponent_profile(self.project,40)
        with self.assertRaises(ModError):
            original_opponent_profile(self.project,0)

    def test_preserve_nonstandard_mod_weight_total_instead_of_quantizing(self):
        self.write(['1;deck;16;500','1;deck;10;501'])
        result=original_opponent_profile(self.project,1)
        summary=original_deck_summary(result)
        self.assertEqual(summary['peso_total'],1001)
        self.assertEqual(result['pools'][0]['pesos'],{10:501,16:500})


if __name__=='__main__':
    unittest.main()
