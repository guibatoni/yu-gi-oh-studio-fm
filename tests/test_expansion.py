"""Expansion above retail 722, God, text icons and reference-based effects."""
import hashlib
import json
import tempfile
from pathlib import Path
import unittest

import struct
from fmstudio.core import Project, check_card_edit, check_effect, ModError
from fmstudio.expanded import resolve_references, display_name, bonus_description
from fmstudio.richtext import NATIVE_ICONS, CUSTOM_ICONS, TEXT_COLORS, tokens, native_text_only
from fmstudio.tables import TYPE_NAMES
from fmstudio.continuous import resolve_field
from fmstudio.duel_engine import DuelLab,parse_card_ids

class NewFeaturesTests(unittest.TestCase):
    def test_god_type_in_editor_and_auras(self):
        self.assertEqual(TYPE_NAMES[24], 'God')
        self.assertEqual(check_card_edit({'tipo_id':24})['tipo_id'],24)
        e=check_effect({'evento':'continuo','acao':'aura_tipo','alvo':'aliados_tipo','valor':300,'valor_def':0,'tipo_id':24})
        self.assertEqual(e['tipo_id'],24)

    def test_card_name_refs_stay_stable_after_rename(self):
        cards={1:{'nome':'Blue-Eyes White Dragon'},723:{'nome':'Divindade Dourada'}}
        desc='Recebe +250 por cada {card:1}; protege {card:723}.'
        self.assertEqual(resolve_references(desc,cards),'Recebe +250 por cada Blue-Eyes White Dragon; protege Divindade Dourada.')
        cards[1]['nome']='Dragao Branco'
        self.assertIn('Dragao Branco',resolve_references(desc,cards))
        self.assertNotIn('#1',resolve_references(desc,cards))
        self.assertIn('Divindade Dourada',bonus_description(500,100,723,cards))

    def test_custom_text_and_native_codes(self):
        c={1:{'nome':'Carta Um'}}
        val='{color:vermelho}Dano{/color} {icon:perfurar} {f8 0B 08} {card:1}'
        parts=tokens(val,c)
        self.assertTrue(any(x[2]=='perfurar' for x in parts))
        self.assertTrue(any(x[2]=='nativo:Fairy' for x in parts))
        self.assertTrue(any(x[0]=='Carta Um' for x in parts))
        self.assertTrue(any(x[0]=='Dano' and x[1]==TEXT_COLORS['vermelho'][1] for x in parts))
        compiled,warn=native_text_only(val)
        self.assertIn('{f8 0A 06}',compiled)
        self.assertIn('{f8 0A 00}',compiled)
        self.assertTrue(any('ícone personalizado' in x for x in warn))
        self.assertEqual(NATIVE_ICONS['Fairy'],8)
        self.assertEqual(len(CUSTOM_ICONS),10)

    def test_custom_assets_are_16px(self):
        folder=Path(__file__).resolve().parents[1]/'assets'/'icons'
        for icon in CUSTOM_ICONS:
            raw=(folder/(icon+'.png')).read_bytes()
            self.assertTrue(raw.startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertEqual(struct.unpack_from('>II',raw,16),(16,16))
            self.assertLess(len(raw),5000)

    def test_updater_future_safe_files(self):
        from fmstudio.updates import allowed_source_member
        self.assertTrue(allowed_source_member('fmstudio/future_rules.py'))
        self.assertTrue(allowed_source_member('assets/icons/future_icon.png'))
        self.assertFalse(allowed_source_member('assets/icons/../../../rom.bin'))
        self.assertFalse(allowed_source_member('projetos/one/projeto.json'))
        self.assertFalse(allowed_source_member('assets/rom.bin'))
        self.assertFalse(allowed_source_member('fmstudio/evil.exe'))

    def test_effect_validation(self):
        e=check_effect({'evento':'continuo','acao':'bonus_por_carta_id','alvo':'proprio',
                        'valor':200,'valor_def':300,'carta_referencia_id':723,
                        'origem_contagem':'deck','escopo':'todos'})
        self.assertEqual((e['valor'],e['valor_def'],e['carta_referencia_id']),(200,300,723))
        for changes in [dict(valor=0,valor_def=0),dict(carta_referencia_id=0),dict(origem_contagem='mão')]:
            raw=dict(e);raw.update(changes)
            with self.assertRaises(ModError):check_effect(raw)

    def test_field_id_bonus_recalculates(self):
        effect=check_effect({'evento':'continuo','acao':'bonus_por_carta_id','alvo':'proprio',
                             'valor':300,'valor_def':100,'carta_referencia_id':723,
                             'origem_contagem':'campo','escopo':'aliados'})
        a={'lado':'jogador','slot':1,'card_id':1,'tipo_id':0,'ataque':1000,'defesa':1000,'face_up':True}
        b=dict(a,slot=2,card_id=723,tipo_id=24)
        c=dict(a,slot=3,card_id=723,tipo_id=24)
        f,_=resolve_field([a,b,c],{'1':[effect]})
        self.assertEqual((f[0]['ataque'],f[0]['defesa']),(1600,1200))
        f,_=resolve_field([a,b],{'1':[effect]})
        self.assertEqual(f[0]['ataque'],1300)
        f,_=resolve_field([a],{'1':[effect]})
        self.assertEqual(f[0]['ataque'],1000)

    def test_deck_id_bonus(self):
        effect=check_effect({'evento':'continuo','acao':'bonus_por_carta_id','alvo':'proprio',
                             'valor':100,'valor_def':50,'carta_referencia_id':723,
                             'origem_contagem':'deck','escopo':'aliados'})
        cards={1:{'tipo_id':0,'ataque':1000,'defesa':1000},723:{'tipo_id':24,'ataque':3000,'defesa':2500}}
        lab=DuelLab(cards,{'1':[effect]})
        lab.set_deck('jogador',[723,723])
        lab.set_field([{'lado':'jogador','slot':1,'card_id':1,'tipo_id':0,'ataque':1000,'defesa':1000,'face_up':True}])
        f,_=lab.resolve()
        self.assertEqual((f[0]['ataque'],f[0]['defesa']),(1200,1100))
        lab.set_deck('jogador',[723])
        self.assertEqual(lab.resolve()[0][0]['ataque'],1100)
        self.assertEqual(parse_card_ids('723x2'),[723,723])

    def test_project_add_save_reopen_export(self):
        with tempfile.TemporaryDirectory() as d:
            p=Project.create(Path(d)/'mod','Projeto')
            p.cards[1]={'id':1,'nome':'Monstro A','descricao':'', 'ataque':1000,'defesa':1000,
                        'tipo_id':0,'atributo_id':0,'nivel':4,'guardian_1_id':1,'guardian_2_id':2,
                        'valor_hex':'00000000'}
            # Simula a base (sem transportar ROM real)
            from fmstudio.core import _write_csv
            base=p.folder/'base';base.mkdir(exist_ok=True)
            _write_csv(base/'cartas.csv',[p.cards[1]])
            _write_csv(base/'fusoes.csv',[{'material_1':1,'material_2':1,'resultado':1,'possivel_glitch':0}])
            p.metadata['base_sha256']={'cartas':hashlib.sha256((base/'cartas.csv').read_bytes()).hexdigest(),
                                      'fusoes':hashlib.sha256((base/'fusoes.csv').read_bytes()).hexdigest()}
            new=p.add_card(1)
            self.assertEqual(new,723)
            p.set_card(new,{'nome':'Deus Criado','tipo_id':24,
                            'descricao':'{color:azul}DEUS{/color} {icon:god}'})
            p2=Project.open(p.folder)
            self.assertEqual(p2.get(723)['nome'],'Deus Criado')
            self.assertEqual(p2.get(723)['tipo_id'],24)
            self.assertEqual(p2.add_card(723),724)
            out,manifest=p2.export()
            self.assertFalse(manifest['patch_jogavel'])
            self.assertEqual(manifest['cartas_virtuais'],2)
            self.assertEqual(len(json.loads((out/'novas_cartas.json').read_text())['cartas']),2)
            self.assertNotEqual(hashlib.sha256((base/'fusoes.csv').read_bytes()).hexdigest(),'')
            self.assertFalse((out/'build_local'/'SLUS_014.11').is_file())

if __name__=='__main__': unittest.main()
