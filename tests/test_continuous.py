"""Cenários de campo: efeitos contínuos recalculados (somente simulador)."""
import tempfile
import unittest
from pathlib import Path

from fmstudio.core import Project, ModError, check_effect
from fmstudio.drafts import DraftSession
from fmstudio.continuous import COUNT_ZONES, project_stats, resolve_field

FAIRY = 8
DRAGON = 0


def m(slot, card_id, type_id, atk=1000, defense=1200, side='jogador', face_up=True):
    return {'slot':slot, 'card_id':card_id, 'tipo_id':type_id, 'ataque':atk,
            'defesa':defense, 'lado':side, 'face_up':face_up}


def aura(atk=500, defense=300, typ=FAIRY):
    return {'evento':'continuo','acao':'aura_tipo','alvo':'aliados_tipo',
            'valor':atk,'valor_def':defense,'tipo_id':typ}


def scaling(atk=200, defense=100, typ=FAIRY):
    return {'evento':'continuo','acao':'bonus_por_tipo','alvo':'proprio',
            'valor':atk,'valor_def':defense,'tipo_id':typ}


class ContinuousTests(unittest.TestCase):
    def test_fairy_aura_includes_fairy_source_and_excludes_enemies(self):
        board=[m(1,1,FAIRY),m(2,2,FAIRY),m(3,3,DRAGON),m(1,4,FAIRY,side='adversario')]
        result, events=resolve_field(board, {'1':[aura()]})
        stats={(x['lado'],x['slot']):(x['ataque'],x['defesa']) for x in result}
        self.assertEqual(stats[('jogador',1)],(1500,1500))
        self.assertEqual(stats[('jogador',2)],(1500,1500))
        self.assertEqual(stats[('jogador',3)],(1000,1200))
        self.assertEqual(stats[('adversario',1)],(1000,1200))
        self.assertEqual(len(events),2)

    def test_aura_removed_when_source_dies(self):
        effects={'1':[aura()]}
        field=[m(1,1,DRAGON),m(2,2,FAIRY)]
        self.assertEqual(resolve_field(field,effects)[0][1]['ataque'],1500)
        self.assertEqual(resolve_field(field[1:],effects)[0][0]['ataque'],1000)

    def test_per_type_updates_immediately_when_one_dies(self):
        effects={'1':[scaling()]}
        field=[m(1,1,DRAGON),m(2,2,FAIRY),m(3,3,FAIRY)]
        result,_=resolve_field(field,effects)
        self.assertEqual((result[0]['ataque'],result[0]['defesa']),(1400,1400))
        result,_=resolve_field(field[:-1],effects)
        self.assertEqual((result[0]['ataque'],result[0]['defesa']),(1200,1300))
        result,_=resolve_field(field[:1],effects)
        self.assertEqual((result[0]['ataque'],result[0]['defesa']),(1000,1200))

    def test_type_source_counts_itself_and_does_not_compound(self):
        effects={'1':[scaling(atk=100, defense=50)]}
        field=[m(1,1,FAIRY)]
        one,_=resolve_field(field,effects)
        two,_=resolve_field(field,effects)
        self.assertEqual(one[0]['ataque'],1100)
        self.assertEqual(one,two)
        self.assertEqual(field[0]['ataque'],1000)

    def test_multiple_aura_sources_stack_dynamically(self):
        field=[m(1,1,DRAGON),m(2,1,DRAGON),m(3,2,FAIRY)]
        result,events=resolve_field(field,{'1':[aura()]})
        self.assertEqual(result[2]['ataque'],2000)
        self.assertEqual(len(events),2)
        result,_=resolve_field(field[1:],{'1':[aura()]})
        self.assertEqual(result[1]['ataque'],1500)

    def test_face_down_cards_grant_receive_and_count_for_field_bonuses(self):
        field = [m(1,1,DRAGON,face_up=False), dict(m(2,2,FAIRY,face_up=False), atributo_id=3),
                 dict(m(3,3,FAIRY), atributo_id=4)]
        effects = {'1': [dict(aura(), atributo_id=3), dict(scaling(), atributo_id=3)]}
        resolved, _ = resolve_field(field, effects)
        self.assertEqual([(row['ataque'], row['defesa']) for row in resolved],
                         [(1200, 1300), (1500, 1500), (1000, 1200)])

    def test_type_or_attribute_counts_the_union_once_in_each_zone(self):
        field = [dict(m(slot, slot, kind), atributo_id=attr) for slot, (kind, attr) in
                 enumerate(((DRAGON, 0), (FAIRY, 0), (DRAGON, 1), (FAIRY, 1), (DRAGON, 4)), 1)]
        catalog = {row['card_id']: row for row in field}
        zones = {zone: {'jogador': [2, 3, 4, 5]} for zone in ('deck_inicial', 'cemiterio', 'mao')}
        zones['deck'] = {'jogador': [5]}
        for action in COUNT_ZONES:
            with self.subTest(action=action):
                rule = dict(scaling(), acao=action, atributo_id=1, combinar_filtros='ou')
                for effect, count in ((rule, 3), (dict(rule, combinar_filtros='e'), 1), (dict(rule, tipo_id=-1), 2)):
                    stats = project_stats(field[0], 1, 'jogador', [effect], field, catalog=catalog, zones=zones)
                    self.assertEqual((stats['ataque'], stats['defesa']), (1000 + 200 * count, 1200 + 100 * count))
        board, events = resolve_field(field, {1: [dict(aura(), atributo_id=1, combinar_filtros='ou')]})
        self.assertEqual([r['ataque'] for r in board], [1000, 1500, 1500, 1500, 1000])
        self.assertEqual(len(events), 3)

    def test_reject_invalid_configs(self):
        with self.assertRaises(ModError): check_effect({**aura(), 'evento':'invocar'})
        with self.assertRaises(ModError): check_effect({**aura(), 'tipo_id':99})
        with self.assertRaises(ModError): check_effect({**aura(), 'atributo_id':16})
        with self.assertRaises(ModError): check_effect({**aura(), 'combinar_filtros':'xor'})
        with self.assertRaises(ModError): check_effect({**scaling(), 'alvo':'inimigo'})
        with self.assertRaises(ModError): check_effect({**aura(), 'valor':0, 'valor_def':0})
        with self.assertRaises(ModError): resolve_field([m(1,1,FAIRY),m(1,2,FAIRY)],{})

    def test_draft_save_reload_field_sim(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Project.create(Path(tmp)/'mod','Mod')
            base={'nome':'Carta teste','descricao':'','cor_nome':'#F1CF6E',
                  'ataque':1000,'defesa':1200,'tipo_id':FAIRY,'atributo_id':0,
                  'nivel':4,'guardian_1_id':0,'guardian_2_id':0,'valor_hex':'00000000',
                  'offset_no_slus':'0x000'}
            p.cards={1:dict(base),2:dict(base)}
            d=DraftSession(p)
            d.add_effect(1,aura())
            self.assertFalse(p.effects)
            result,_=d.simulate_field([m(1,1,FAIRY),m(2,2,FAIRY)])
            self.assertEqual(result[1]['ataque'],1500)
            d.save()
            self.assertEqual(Project.open(p.folder).effects['1'][0]['valor_def'],300)


if __name__=='__main__':
    unittest.main()
