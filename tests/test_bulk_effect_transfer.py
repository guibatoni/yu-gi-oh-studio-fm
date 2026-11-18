"""Regressão da edição em massa e transferência de efeitos entre cartas."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fmstudio.bulk_editor import plan_bulk, commit_bulk, MAX_COPIES
from fmstudio.core import Project, ModError
from fmstudio.passwords import CHEST_KEY
from fmstudio.ps1_economy import PASSWORD_PRICES_KEY
from fmstudio.effects_transfer import (
    encode_effects,decode_effects,merge_effects,reference_warnings,
)
from fmstudio.drafts import DraftSession


def effect(action='cura_lp',amount=500):
    return {'evento':'invocar','acao':action,'alvo':'proprio','valor':amount}


class BulkEditorTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project=Project.create(Path(self.temp.name)/'project','Bulk')
        self.project.cards={
            1:{'id':1,'nome':'Um','tipo_id':0},
            2:{'id':2,'nome':'Dois','tipo_id':0},
            723:{'id':723,'nome':'Extra','tipo_id':0},
            741:{'id':741,'nome':'Apenas Studio','tipo_id':0},
        }
        self.project.metadata[CHEST_KEY]={'1':3,'2':0}
        self.project.save()

    def test_define_add_subtract_zero_and_preserve_non_selected(self):
        previous=self.project.metadata
        rows=plan_bulk(self.project,[1,2],copies=('adicionar','3'))
        self.assertEqual([(r.cid,r.copies_before,r.copies_after) for r in rows],
                         [(1,3,6),(2,0,3)])
        commit_bulk(self.project,rows,copies=True)
        self.assertEqual(self.project.metadata[CHEST_KEY],{'1':6,'2':3})
        self.assertEqual(previous[CHEST_KEY],{'1':3,'2':0})
        rows=plan_bulk(self.project,[1,2],copies=('subtrair','2'))
        commit_bulk(self.project,rows,copies=True)
        self.assertEqual(self.project.metadata[CHEST_KEY],{'1':4,'2':1})
        rows=plan_bulk(self.project,[2],copies=('zerar','999'))
        commit_bulk(self.project,rows,copies=True)
        self.assertEqual(self.project.metadata[CHEST_KEY],{'1':4})
        self.assertEqual(json.loads((self.project.folder/'projeto.json').read_text())[
            CHEST_KEY],{'1':4})

    def test_price_and_chest_atomic_and_roundtrip(self):
        old_prices={1:100,2:200}
        rows=plan_bulk(self.project,[1,2],copies=('definir','15'),
                       price=('subtrair','10'),original_prices=old_prices)
        commit_bulk(self.project,rows,copies=True,price=True)
        self.assertEqual(self.project.metadata[CHEST_KEY]['1'],15)
        self.assertEqual(self.project.metadata[PASSWORD_PRICES_KEY],{'1':90,'2':190})
        opened=Project.open(self.project.folder)
        self.assertEqual(opened.metadata[PASSWORD_PRICES_KEY],{'1':90,'2':190})
        self.assertEqual(opened.metadata[CHEST_KEY]['2'],15)
        self.assertTrue(list((self.project.folder/'backups').glob('projeto_*.json')))

    def test_reject_invalid_range_without_mutating(self):
        snapshot=json.dumps(self.project.metadata,sort_keys=True)
        for kw in (
            {'copies':('subtrair','10')},
            {'copies':('adicionar',str(MAX_COPIES))},
            {'copies':('definir','-4')},
            {'price':('definir','20.5'),'original_prices':{1:3}},
            {'price':('subtrair','9'),'original_prices':{1:3}},
        ):
            with self.subTest(kw=kw),self.assertRaises(ModError):
                plan_bulk(self.project,[1],**kw)
        with self.assertRaises(ModError):
            plan_bulk(self.project,[741],price=('definir','30'),
                      original_prices={741:100})
        self.assertEqual(json.dumps(self.project.metadata,sort_keys=True),snapshot)

    def test_transaction_rolls_back_when_save_fails(self):
        rows=plan_bulk(self.project,[1,2],copies=('definir','5'))
        before=self.project.metadata
        with patch.object(self.project,'save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                commit_bulk(self.project,rows,copies=True)
        self.assertEqual(self.project.metadata,before)

    def test_copy_rejects_missing_original_price_and_virtual_ids(self):
        with self.assertRaisesRegex(ModError,'custo original desconhecido'):
            plan_bulk(self.project,[1],price=('definir','500'))
        self.project.cards[2]['virtual']=True
        with self.assertRaisesRegex(ModError,'Password exportável'):
            plan_bulk(self.project,[2],price=('definir','50'),original_prices={2:10})


class EffectTransferTests(unittest.TestCase):
    def test_copy_multiple_preserves_parameters(self):
        aura={'evento':'continuo','acao':'bonus_por_carta_id','alvo':'proprio',
              'carta_referencia_id':16,'origem_contagem':'deck',
              'valor':300,'valor_def':200,'escopo':'aliados'}
        payload=encode_effects(1,[effect(),aura])
        source,restored=decode_effects(payload)
        self.assertEqual(source,1)
        self.assertEqual(len(restored),2)
        self.assertEqual(restored[1]['carta_referencia_id'],16)
        self.assertEqual(restored[1]['origem_contagem'],'deck')
        self.assertEqual(restored[1]['valor_def'],200)
        self.assertEqual(len(merge_effects([],restored)),2)
        self.assertIn('Referência fixa: carta #16.',reference_warnings(1,2,restored))

    def test_paste_append_replace_cancel_is_pure(self):
        before=[effect()]
        transferred=[effect('dano_lp',200)]
        appended=merge_effects(before,transferred)
        replaced=merge_effects(before,transferred,replace=True)
        self.assertEqual(len(appended),2)
        self.assertEqual(len(replaced),1)
        self.assertEqual(len(before),1)
        with self.assertRaisesRegex(ModError,'duplicaria'):
            merge_effects(before,before)
        with self.assertRaises(ModError):
            decode_effects('not a studio clipboard')

    def test_drafts_batch_is_atomic_and_duplicate_safe(self):
        with TemporaryDirectory() as path:
            project=Project.create(Path(path)/'project','Draft')
            project.cards={1:{'id':1,'nome':'A'},2:{'id':2,'nome':'B'}}
            draft=DraftSession(project)
            draft.add_effects(1,[effect(),effect('dano_lp',250)])
            self.assertEqual(len(draft.get_effects(1)),2)
            with self.assertRaisesRegex(ModError,'já está'):
                draft.add_effects(1,[effect('dano_lp',300),effect()])
            self.assertEqual(len(draft.get_effects(1)),2)
            copied=decode_effects(encode_effects(1,draft.get_effects(1)))[1]
            draft.set_effects(2,merge_effects([],copied))
            self.assertEqual(len(draft.get_effects(2)),2)
            self.assertEqual(project.effects,{})
            # Salvar rascunho usa a mesma validação atômica do projeto.
            draft.save()
            self.assertEqual(len(project.effects['2']),2)


if __name__=='__main__':
    unittest.main()
