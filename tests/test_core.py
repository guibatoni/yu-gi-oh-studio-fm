import csv
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from fmstudio.core import (Project, ModError, _write_csv, check_card_edit,
                           check_effect, EVENTS, ACTIONS)
from fmstudio.tables import (CARD_COUNT, EXE_DELTA, LEVEL_ADDR, STATS_ADDR)


class StudioCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.base=root/'analysis'/'tabelas'
        self.base.mkdir(parents=True)
        self.file=root/'analysis'/'extracted'/'SLUS_014.11'
        self.file.parent.mkdir(parents=True)
        maxlen=max(STATS_ADDR - EXE_DELTA + CARD_COUNT*4, LEVEL_ADDR - EXE_DELTA + CARD_COUNT+1)+1024
        data=bytearray(maxlen)
        data[:8]=b'PS-X EXE'
        rows=[]
        for cid in range(1,CARD_COUNT+1):
            raw=(((cid%24)<<26)|((cid%10)<<22)|((cid%10)<<18)|((1200//10)<<9)|(1000//10))
            pos=STATS_ADDR-EXE_DELTA+(cid-1)*4
            struct.pack_into('<I',data,pos,raw)
            data[LEVEL_ADDR-EXE_DELTA+cid]=((cid%6)<<4)|(cid%13)
            rows.append(dict(id=cid, ataque=1000,defesa=1200,tipo_id=cid%24,
                        atributo_id=cid%6,nivel=cid%13,guardian_1_id=cid%10,
                        guardian_2_id=cid%10,valor_hex=f'{raw:08X}',offset_no_slus=f'0x{pos:X}'))
        self.file.write_bytes(data)
        _write_csv(self.base/'cartas.csv', rows)
        self.fusions=[{'material_1':1,'material_2':2,'resultado':3,'possivel_glitch':0},
                      {'material_1':2,'material_2':3,'resultado':10,'possivel_glitch':1}]
        _write_csv(self.base/'fusoes.csv',self.fusions)
        (self.base/'resumo.json').write_text(json.dumps({'warnings':['Versão modificada X15 a confirmar'],
            'source_sha256':{'SLUS_014.11':hashlib.sha256(data).hexdigest()}}))
        self.p=Project.create(root/'MeuMod','Meu MOD')
        self.p.import_tables(self.base)

    def test_time_wizard_god_type_never_silently_discards_attack(self):
        from fmstudio.tables import decode_cards
        source_sha=hashlib.sha256(self.file.read_bytes()).hexdigest()
        # Reproduz captura do usuário: Time Wizard com ATK 3000 e tipo God.
        self.p.set_card(16, {'ataque':3000, 'tipo_id':24})
        with self.assertRaisesRegex(ModError,'Spellcaster'):
            self.p.export()
        self.assertEqual(hashlib.sha256(self.file.read_bytes()).hexdigest(),source_sha)
        self.p.set_card(16, {'ataque':3000,'tipo_id':1})
        output,manifest=self.p.export()
        built=(output/'build_local'/'SLUS_014.11').read_bytes()
        cards,_=decode_cards(built)
        self.assertEqual(cards[15]['ataque'],3000)
        self.assertEqual(cards[15]['tipo_id'],1)
        self.assertEqual(hashlib.sha256(self.file.read_bytes()).hexdigest(),source_sha)

    def test_large_stats_saved_for_simulator_but_ps1_export_blocked(self):
        from fmstudio.core import simulation_nonnegative_int, check_card_edit
        from fmstudio.continuous import resolve_field
        big=123456789012345678901234567890
        self.assertEqual(simulation_nonnegative_int(str(big),'ATK'),big)
        self.assertEqual(check_card_edit({'ataque':str(big),'defesa':'100000'})['ataque'],big)
        self.p.set_card(1,{'ataque':big,'defesa':100000})
        self.assertEqual(self.p.get(1)['ataque'],big)
        state,_=resolve_field([{'lado':'jogador','slot':1,'card_id':1,
                                'tipo_id':0,'ataque':big,'defesa':100000}],{})
        self.assertEqual(state[0]['ataque'],big)
        with self.assertRaisesRegex(ModError,'9 bits'):
            self.p.export()
        with self.assertRaises(ModError):
            check_card_edit({'ataque':'1'*65})
        with self.assertRaises(ModError):
            check_card_edit({'defesa':'-10'})

    def test_import_full_and_fusions_immutable(self):
        self.assertEqual(len(self.p.cards),722)
        self.assertEqual(len(self.p.fusions),2)
        self.assertTrue((self.p.folder/'base'/'source_SLUS_014.11').is_file())
        self.assertEqual(self.p.validate(),[])
        self.assertEqual(self.p.imported_notes,['Versão modificada X15 a confirmar'])

    def test_save_reload_and_cards(self):
        self.p.set_card(1,dict(nome='Dragão da Luz',descricao='Uma carta de teste',ataque=3000,
            defesa=2000,tipo_id=1,atributo_id=2,nivel=8,guardian_1_id=3,guardian_2_id=4))
        reloaded=Project.open(self.p.folder)
        self.assertEqual(reloaded.get(1)['ataque'],3000)
        self.assertEqual(reloaded.get(1)['nome'],'Dragão da Luz')
        self.assertEqual(reloaded.get(1)['nivel'],8)
        self.assertEqual(len(reloaded.fusions),2)

    def test_effect_simulation_only(self):
        self.p.add_effect(1,{'evento':'invocar','acao':'aumentar_atk','alvo':'proprio','valor':'500'})
        self.p.add_effect(1,{'evento':'invocar','acao':'dano_lp','alvo':'inimigo','valor':800})
        stats,applied=self.p.simulate(1,'invocar')
        self.assertEqual(len(applied),2)
        self.assertEqual(stats['ataque'],1500)
        self.assertEqual(stats['lp_adversario'],7200)
        other,_=self.p.simulate(1,'defender')
        self.assertEqual(other['ataque'],1000)
        self.p.remove_effect(1,0)
        self.assertEqual(len(self.p.effects['1']),1)

    def test_export_guarded_slus_and_fusion_hash(self):
        original=self.file.read_bytes()
        self.p.set_card(1,dict(nome='Dragão',descricao='Nova descrição',ataque=4000,
            defesa=2500,tipo_id=1,atributo_id=2,nivel=9,guardian_1_id=3,guardian_2_id=4))
        self.p.add_effect(1,{'evento':'destruido','acao':'dano_lp','alvo':'inimigo','valor':800})
        out,manifest=self.p.export()
        self.assertFalse(manifest['patch_jogavel'])
        self.assertEqual(manifest['fusoes'],'ORIGINAIS_PRESERVADAS')
        self.assertEqual(len(_read(out/'alteracoes_cartas.json')),1)
        self.assertTrue((out/'efeitos_planejados.json').is_file())
        patched=(out/'build_local'/'SLUS_014.11').read_bytes()
        pos=STATS_ADDR-EXE_DELTA
        self.assertNotEqual(patched[pos:pos+4],original[pos:pos+4])
        self.assertEqual(self.file.read_bytes(),original)
        self.assertEqual(patched[:pos],original[:pos])
        self.assertEqual((self.p.folder/'base'/'fusoes.csv').read_bytes(),(self.base/'fusoes.csv').read_bytes())

    def test_only_text_does_not_emit_modded_exe(self):
        self.p.set_card(1,dict(nome='Novo nome',descricao='Descrição nova'))
        out,manifest=self.p.export()
        self.assertFalse((out/'build_local'/'SLUS_014.11').exists())
        self.assertEqual(manifest['cartas_editadas'],1)

    def test_import_rejects_other_executable(self):
        wrong=self.p.folder/'wrong.exe'
        data=bytearray(self.file.read_bytes()); data[STATS_ADDR-EXE_DELTA] ^= 12
        wrong.write_bytes(data)
        with self.assertRaises(ModError):
            self.p.attach_executable(wrong)

    def test_modify_fusion_base_detects(self):
        with (self.p.folder/'base'/'fusoes.csv').open('a') as f: f.write('\n1;4;5;0\n')
        self.assertTrue(any('fusões' in msg for msg in self.p.validate()))
        with self.assertRaises(ModError): self.p.export()

    def test_bad_values(self):
        # Estatísticas altas e valores fora dos múltiplos de 10 são válidos
        # no Studio, mas exportação PS1 deve recusá-los antes da gravação.
        self.assertEqual(check_card_edit({'ataque':5130})['ataque'],5130)
        self.assertEqual(check_card_edit({'defesa':111})['defesa'],111)
        with self.assertRaises(ModError): check_card_edit({'ataque':-1})
        with self.assertRaises(ModError): check_card_edit({'defesa':'a'*65})
        with self.assertRaises(ModError): check_effect({'evento':'invocar','acao':'comer','alvo':'proprio','valor':100})
        with self.assertRaises(ModError): check_effect({'evento':'invocar','acao':'cura_lp','alvo':'inimigo','valor':0})


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


if __name__ == '__main__': unittest.main()

class ImageAttachmentTests(unittest.TestCase):
    def test_png_attachment(self):
        import base64
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda:__import__('shutil').rmtree(root))
        p = Project.create(root/'Mod','Mod')
        p.cards={1:{'id':1, 'valor_hex':'00000000', 'ataque':'0','defesa':'0','nivel':'0','tipo_id':'0','atributo_id':'0','guardian_1_id':'0','guardian_2_id':'0'}}
        imagefile=root/'asset.png'
        imagefile.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL/nwAAAABJRU5ErkJggg=='))
        p.attach_art(1,imagefile)
        self.assertEqual(Project.open(p.folder).arts['1'],'assets/cartas/001.png')
        self.assertTrue((p.folder/'assets'/'cartas'/'001.png').is_file())
