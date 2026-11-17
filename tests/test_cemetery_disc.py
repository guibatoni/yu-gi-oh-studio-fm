"""Testes offline de cemitério, ataque no primeiro turno e escrita de BIN/CUE.

Disco construído exclusivamente com setores sintéticos; nenhum ROM é incluído.
"""
from collections import Counter
import hashlib
import tempfile
import unittest
from pathlib import Path

from fmstudio.abilities import replace_quick_effects
from fmstudio.continuous import resolve_field
from fmstudio.core import ModError, check_effect
from fmstudio.disc import DiscReader, SYNC
from fmstudio.disc_build import _edc, regenerate_form1, build_test_disc
from fmstudio.duel_engine import DuelLab
from fmstudio.richtext import CUSTOM_ICONS, native_text_only

DRAGON=0
FAIRY=8

def monster(cid=1,typ=DRAGON,side='jogador',slot=1,atk=1000):
    return {'lado':side,'slot':slot,'card_id':cid,'tipo_id':typ,
            'ataque':atk,'defesa':1000,'face_up':True}

def grave_effect(typ=DRAGON,atk=200,defense=100,scope='aliados'):
    return check_effect({'evento':'continuo','acao':'bonus_cemiterio_tipo','alvo':'proprio',
                         'valor':atk,'valor_def':defense,'tipo_id':typ,'escopo':scope})

class CemeteryTests(unittest.TestCase):
    def test_graveyard_bonus_dynamically_after_summoning(self):
        cards={1:{'tipo_id':0},2:{'tipo_id':0},3:{'tipo_id':8}}
        lab=DuelLab(cards,{'1':[grave_effect()]})
        lab.set_field([monster(1),monster(2,slot=2),monster(3,side='adversario',slot=1)])
        self.assertEqual(lab.resolve()[0][0]['ataque'],1000)
        self.assertTrue(lab.remove('jogador',2))
        self.assertEqual(lab.graveyards['jogador'],[2])
        self.assertEqual(lab.resolve()[0][0]['ataque'],1200)
        lab.set_graveyard('jogador',[])
        self.assertEqual(lab.resolve()[0][0]['ataque'],1000)

    def test_enemy_and_all_cemetery_scopes_and_type_filter(self):
        field=[monster(1)]
        grave={'jogador':Counter({DRAGON:2,FAIRY:1}),
               'adversario':Counter({DRAGON:3,FAIRY:4})}
        for scope,n in [('aliados',2),('inimigos',3),('todos',5)]:
            out,ev=resolve_field(field,{'1':[grave_effect(scope=scope)]},cemetery_types=grave)
            self.assertEqual(out[0]['ataque'],1000+200*n)
            self.assertEqual(ev[0]['quantidade'],n)
        all_types,ev=resolve_field(field,{'1':[grave_effect(typ=-1,atk=50,defense=0,scope='todos')]},cemetery_types=grave)
        self.assertEqual(all_types[0]['ataque'],1500)

    def test_invalid_cemetery_effects(self):
        with self.assertRaises(ModError): check_effect({**grave_effect(), 'evento':'invocar'})
        with self.assertRaises(ModError): check_effect({**grave_effect(), 'tipo_id':32})
        with self.assertRaises(ModError): check_effect({**grave_effect(), 'valor':0,'valor_def':0})
        with self.assertRaises(ModError): DuelLab({1:{'tipo_id':0}},{}).set_graveyard('jogador',[2])

    def test_first_turn_attack_without_haste_is_blocked(self):
        lab=DuelLab({1:{'tipo_id':DRAGON}}, {}, summoning_delay=True)
        lab.set_field([monster(1,atk=100)])
        with self.assertRaisesRegex(ModError,'invocado neste turno'):
            lab.attack('jogador',1)
        lab.new_turn('jogador')
        lab.attack('jogador',1)
        self.assertEqual(lab.lp['adversario'],7900)

    def test_first_turn_attack_with_haste_and_multiple_attacks(self):
        eff=replace_quick_effects([],{ 'ataques':2,'ataque_primeiro_turno':True})
        lab=DuelLab({1:{'tipo_id':0}}, {'1':eff},summoning_delay=True)
        lab.set_field([monster(1,atk=100)])
        self.assertEqual(lab.attack('jogador',1)['ataques_usados'],1)
        self.assertEqual(lab.attack('jogador',1)['ataques_usados'],2)
        with self.assertRaises(ModError): lab.attack('jogador',1)
        self.assertEqual(lab.lp['adversario'],7800)

    def test_icon_custom_visible_and_export_warning(self):
        self.assertIn('ataque_primeiro_turno',CUSTOM_ICONS)
        _,warnings=native_text_only('{icon:ataque_primeiro_turno}')
        self.assertTrue(any('patch' in v for v in warnings))


def sector(data=b''):
    raw=bytearray(2352);raw[:12]=SYNC;raw[15]=2
    raw[16:20]=bytes([0,0,8,0]);raw[20:24]=raw[16:20]
    raw[24:24+len(data)] = data
    return regenerate_form1(raw)

def dir_entry(name,extent,size,flags=0):
    n=len(name);length=33+n+(0 if n&1 else 1)
    out=bytearray(length);out[0]=length;out[2:6]=extent.to_bytes(4,'little')
    out[10:14]=size.to_bytes(4,'little');out[25]=flags
    out[32]=n;out[33:33+n]=name
    return bytes(out)

def fake_disc(path,exe):
    # ISO9660 começa no LBA16, o diretório raiz no LBA20 e o SLUS no LBA25.
    blocks=[sector() for _ in range(max(30, 25 + (len(exe)+2047)//2048))]
    pvd=bytearray(2048);pvd[0]=1;pvd[1:6]=b'CD001';pvd[6]=1
    pvd[156:190]=dir_entry(b'\x00',20,2048,2)
    blocks[16]=sector(pvd)
    directory=bytearray(2048);record=dir_entry(b'SLUS_014.11;1',25,len(exe))
    directory[0:len(record)]=record
    blocks[20]=sector(directory)
    for i in range((len(exe)+2047)//2048):
        blocks[25+i]=sector(exe[i*2048:(i+1)*2048])
    path.write_bytes(b''.join(blocks))

class DiscBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)
        self.original=b'PS-X EXE'+bytes([1])*2992
        self.patched=self.original[:2100]+b'A'+self.original[2101:]
        self.src=self.path/'original.bin'
        fake_disc(self.src,self.original)
        self.project=type('ProjectStub',(),{})()
        self.project.folder=self.path/'proj';self.project.folder.mkdir()
        self.project.metadata={'base_sha256':{'slus':hashlib.sha256(self.original).hexdigest()}}
        def export():
            output=self.project.folder/'exportacao'/'build_local';output.mkdir(parents=True,exist_ok=True)
            (output/'SLUS_014.11').write_bytes(self.patched)
            return output.parent, {'slus_modificado_sha256':hashlib.sha256(self.patched).hexdigest()}
        self.project.export=export

    def test_edc_ecc_rebuild_is_deterministic(self):
        raw=sector(bytes([6])*2048)
        self.assertEqual(regenerate_form1(raw),raw)
        self.assertEqual(int.from_bytes(raw[2072:2076],'little'),_edc(raw[16:2072]))
        self.assertTrue(any(raw[2076:2352]))

    def test_patches_only_executable_sectors_and_preserves_original(self):
        original_bytes=self.src.read_bytes()
        result=build_test_disc(self.project,self.src)
        self.assertEqual(result['setores_modificados'],1)
        self.assertEqual(result['lbas'],[26])
        with DiscReader(result['bin']) as r:
            entry=next(e for e in r.files() if e.path=='SLUS_014.11')
            self.assertEqual(b''.join(r.read_entry(entry)),self.patched)
        modified=Path(result['bin']).read_bytes()
        self.assertEqual(self.src.read_bytes(),original_bytes)
        self.assertEqual(modified[:26*2352],original_bytes[:26*2352])
        self.assertEqual(len(modified),len(original_bytes))
        self.assertIn('MODE2/2352',Path(result['cue']).read_text())

    def test_reject_wrong_image_without_output(self):
        self.project.metadata['base_sha256']['slus']='0'*64
        with self.assertRaisesRegex(ModError,'não corresponde'):
            build_test_disc(self.project,self.src)

    def test_reject_unchanged_executable(self):
        self.patched=self.original
        with self.assertRaises(ModError):build_test_disc(self.project,self.src)

class StableDiscOutputTests(DiscBuildTests):
    """Mesmo nome substitui; nome diferente cria outra imagem, sem tocar na origem."""

    def test_rebuild_same_source_replaces_instead_of_duplicating(self):
        original_hash=hashlib.sha256(self.src.read_bytes()).hexdigest()
        first=build_test_disc(self.project,self.src)
        first_path=Path(first['bin'])
        first_bytes=first_path.read_bytes()
        self.assertEqual(first['acao_arquivo'],'criado')
        self.assertIn('original',first_path.name)
        self.assertEqual(len(list(first_path.parent.glob('*.bin'))),1)

        self.patched=self.original[:2100]+b'B'+self.original[2101:]
        second=build_test_disc(self.project,self.src)
        self.assertEqual(first['bin'],second['bin'])
        self.assertEqual(first['cue'],second['cue'])
        self.assertEqual(second['acao_arquivo'],'substituido')
        self.assertNotEqual(first_bytes,first_path.read_bytes())
        self.assertEqual(hashlib.sha256(self.src.read_bytes()).hexdigest(),original_hash)
        self.assertEqual(len(list(first_path.parent.glob('*.bin'))),1)
        self.assertFalse(any(first_path.parent.glob('.fmstudio_build_*')))
        with DiscReader(second['bin']) as reader:
            slus=next(e for e in reader.files() if e.path=='SLUS_014.11')
            self.assertEqual(b''.join(reader.read_entry(slus)),self.patched)

    def test_rebuild_restores_original_lock_even_without_other_edits(self):
        import struct
        from unittest.mock import patch
        from fmstudio.ps1_mod import FIRST_TURN_PC, FIRST_TURN_SOURCE
        from fmstudio.tables import EXE_DELTA

        offset = FIRST_TURN_PC - EXE_DELTA
        original = bytearray(offset + 4)
        original[:8] = b'PS-X EXE'
        struct.pack_into('<I', original, offset, FIRST_TURN_SOURCE)
        self.original = bytes(original)
        fake_disc(self.src, self.original)
        digest = hashlib.sha256(self.original).hexdigest()
        self.project.metadata['base_sha256']['slus'] = digest
        self.patched = self.original[:offset] + struct.pack('<I', 0x34420000)
        legacy = build_test_disc(self.project, self.src)
        self.assertNotEqual(Path(legacy['bin']).read_bytes(), self.src.read_bytes())

        self.patched = self.original
        with patch('fmstudio.ps1_runtime.SOURCE_SHA256', digest):
            fresh = build_test_disc(self.project, self.src)
        self.assertEqual(fresh['bin'], legacy['bin'])
        self.assertEqual(fresh['acao_arquivo'], 'substituido')
        self.assertEqual(fresh['setores_modificados'], 0)
        self.assertTrue(fresh['edicao_do_mod_ps1']['bloqueio_turno_inicial'])
        self.assertEqual(Path(fresh['bin']).read_bytes(), self.src.read_bytes())

    def test_dificil_ai_reaches_bin_and_keeps_original_disc_unmodified(self):
        import struct
        from unittest.mock import patch
        from fmstudio.ps1_ai import HARD_AI_PATCHES
        from fmstudio.ps1_mod import FIRST_TURN_PC, FIRST_TURN_SOURCE
        from fmstudio.tables import EXE_DELTA

        end = max(pc - EXE_DELTA + 8 for pc, *_ in HARD_AI_PATCHES)
        source = bytearray(end + 4)
        source[:8] = b'PS-X EXE'
        struct.pack_into('<I', source, FIRST_TURN_PC - EXE_DELTA, FIRST_TURN_SOURCE)
        for pc, old, _, _ in HARD_AI_PATCHES:
            struct.pack_into('<I', source, pc - EXE_DELTA, old)
        self.original = bytes(source)
        self.patched = self.original
        self.project.cards = {}
        self.project.get = self.project.cards.__getitem__
        self.project.metadata['edicao_mod'] = {'ia_ps1': 'dificil'}
        digest = hashlib.sha256(self.original).hexdigest()
        self.project.metadata['base_sha256']['slus'] = digest
        fake_disc(self.src, self.original)
        original_disc_hash = hashlib.sha256(self.src.read_bytes()).hexdigest()
        with patch('fmstudio.ps1_runtime.SOURCE_SHA256', digest), patch(
                'fmstudio.ps1_ai.SOURCE_SHA256', digest):
            result = build_test_disc(self.project, self.src)
        self.assertEqual(result['ia_nativa_ps1']['status'], 'aplicado')
        self.assertEqual(len(result['ia_nativa_ps1']['rotinas']), 5)
        with DiscReader(result['bin']) as reader:
            exe = next(e for e in reader.files() if e.path == 'SLUS_014.11')
            modified = b''.join(reader.read_entry(exe))
        for pc, _, expected, _ in HARD_AI_PATCHES:
            self.assertEqual(struct.unpack_from('<I', modified, pc - EXE_DELTA)[0],
                             expected)
        self.assertEqual(hashlib.sha256(self.src.read_bytes()).hexdigest(),
                         original_disc_hash)
        self.assertEqual(len(modified), len(self.original))

    def test_20000_lp_five_digit_hud_in_rebuilt_bin_cue(self):
        import struct
        from unittest.mock import patch
        from fmstudio.ps1_lp_hud import LP_HUD_PATCHES, DECK_COUNT_WORDS
        from fmstudio.ps1_mod import FIRST_TURN_PC, FIRST_TURN_SOURCE, LP_BANK_END
        from fmstudio.tables import EXE_DELTA

        # A imagem fake reserva todo o banco nativo de LP, não contém ROM real.
        source = bytearray(LP_BANK_END-EXE_DELTA+0x800)
        source[:8] = b'PS-X EXE'
        struct.pack_into('<I', source, FIRST_TURN_PC-EXE_DELTA, FIRST_TURN_SOURCE)
        for pc, original, _, _ in LP_HUD_PATCHES:
            struct.pack_into('<I', source, pc-EXE_DELTA, original)
        for pc, original in DECK_COUNT_WORDS:
            struct.pack_into('<I', source, pc-EXE_DELTA, original)
        self.original = bytes(source)
        self.patched = self.original
        fake_disc(self.src, self.original)
        digest = hashlib.sha256(self.original).hexdigest()
        self.project.metadata['base_sha256']['slus'] = digest
        self.project.metadata['edicao_mod'] = {'lp_inicial': 20000}
        self.project.cards = {}
        self.project.get = self.project.cards.__getitem__
        from fmstudio.ps1_runtime import SOURCE_SHA256 as normal_hash
        with patch('fmstudio.ps1_runtime.SOURCE_SHA256', digest), patch(
                'fmstudio.ps1_lp_hud.SOURCE_SHA256', digest):
            result = build_test_disc(self.project, self.src)
        self.assertEqual(result['contador_lp_ps1']['status'], 'aplicado')
        self.assertEqual(result['contador_lp_ps1']['lp_inicial'], 20000)
        self.assertEqual(result['contador_lp_ps1']['digitos'], 5)
        with DiscReader(result['bin']) as reader:
            entry = next(entry for entry in reader.files() if entry.path == 'SLUS_014.11')
            rebuilt = b''.join(reader.read_entry(entry))
        self.assertEqual(len(rebuilt), len(self.original))
        for pc, old, wide, _ in LP_HUD_PATCHES:
            self.assertEqual(struct.unpack_from('<I', rebuilt, pc-EXE_DELTA)[0], wide)
        for pc, deck_count in DECK_COUNT_WORDS:
            self.assertEqual(struct.unpack_from('<I', rebuilt, pc-EXE_DELTA)[0], deck_count)
        # O código inicializa LP de ambos os lados com o mesmo 20000.
        from fmstudio.ps1_mod import LP_TABLE
        self.assertEqual(struct.unpack_from('<4H', rebuilt, LP_TABLE-EXE_DELTA),
                         (20000, 20000, 20000, 20000))
        self.assertEqual(self.src.read_bytes(), self.src.read_bytes())
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), digest)

    def test_different_source_filename_creates_distinct_image(self):
        first=build_test_disc(self.project,self.src)
        another=self.path/'outro_mod.bin'
        another.write_bytes(self.src.read_bytes())
        second=build_test_disc(self.project,another)
        self.assertNotEqual(first['bin'],second['bin'])
        self.assertTrue(Path(first['bin']).is_file())
        self.assertTrue(Path(second['bin']).is_file())
        self.assertEqual(len(list(Path(first['bin']).parent.glob('*.bin'))),2)
        self.assertEqual(second['acao_arquivo'],'criado')

    def test_failed_patch_preserves_prior_bin_and_sidecars(self):
        from unittest.mock import patch
        result=build_test_disc(self.project,self.src)
        files=[Path(result[k]) for k in ('bin','cue')]
        files.append(files[0].with_suffix('.json'))
        before={f:f.read_bytes() for f in files}
        self.patched=self.original[:2100]+b'B'+self.original[2101:]
        with patch('fmstudio.disc_build._write_file_patches',side_effect=ModError('falha simulada')):
            with self.assertRaisesRegex(ModError,'falha simulada'):
                build_test_disc(self.project,self.src)
        self.assertEqual({f:f.read_bytes() for f in files},before)
        self.assertFalse(any(files[0].parent.glob('.fmstudio_build_*')))

    def test_locked_bin_rolls_back_sidecars_and_preserves_last_good(self):
        from unittest.mock import patch
        result=build_test_disc(self.project,self.src)
        files=[Path(result[k]) for k in ('bin','cue')]
        files.append(files[0].with_suffix('.json'))
        before={f:f.read_bytes() for f in files}
        self.patched=self.original[:2100]+b'Z'+self.original[2101:]
        native_replace=Path.replace

        def fail_on_bin(inst,target):
            if inst.suffix=='.bin' and inst.parent.name.startswith('.fmstudio_build_'):
                raise PermissionError('ePSXe bloqueou o arquivo')
            return native_replace(inst,target)

        with patch.object(Path,'replace',fail_on_bin):
            with self.assertRaisesRegex(ModError,'Feche o jogo no ePSXe'):
                build_test_disc(self.project,self.src)
        self.assertEqual({f:f.read_bytes() for f in files},before)
        self.assertFalse(any(files[0].parent.glob('.fmstudio_build_*')))

if __name__=='__main__':unittest.main()
