"""Testes do caminho real BIN/CUE com arquivos *sintéticos* de PS1.

Não incluem ROMs, imagens comerciais ou dados extraídos do jogo.
"""
from __future__ import annotations
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from fmstudio.core import ModError
from fmstudio.deep_extract import EXE_START, EXE_HEADER
from fmstudio.disc import DiscReader, SYNC
from fmstudio.disc_build import build_test_disc, regenerate_form1, DescriptionCompatibilityError
from fmstudio.ps1_content import patch_card_art, patch_names, name_patch_info, patch_descriptions, description_patch_info
from fmstudio.ps1_compat import audit


def where(addr):return addr-EXE_START+EXE_HEADER


def sample_exe():
    b=bytearray(1902592)
    b[:8]=b'PS-X EXE'
    # 0x01=A, 0x02=B, 0x03=C no mapa Shift-JIS de glifos.
    for n,sjis in ((1,0x8260),(2,0x8261),(3,0x8262)):
        struct.pack_into('<I',b,where(0x801D9000+4*n),sjis)
    struct.pack_into('<H',b,where(0x801D5800+2),0x6000)
    b[where(0x801D6000):where(0x801D6000)+3]=b'\x01\x02\xff'
    struct.pack_into('<H',b,where(0x801C0000 + 0x101*2),0x3000)
    b[where(0x801C3000):where(0x801C3000)+13]=bytes([1])*12+b'\xff'
    return bytes(b)


def sample_wa():
    b=bytearray(1_570_000)
    base=722*2048
    struct.pack_into('<H',b,base+0x2640+2,31) # índice 1 -> vermelho
    struct.pack_into('<H',b,base+0x2640+4,31<<10) # índice 2 -> azul
    struct.pack_into('<H',b,0x500+2,31<<10) # thumbnail índice 1 -> azul
    b[base:base+102*96]=bytes([2])*(102*96)
    b[0:40*32]=bytes([0])*(40*32)
    return bytes(b)


def raw_sector(data=b''):
    s=bytearray(2352);s[:12]=SYNC;s[15]=2
    s[16:20]=b'\x00\x00\x08\x00';s[20:24]=s[16:20]
    s[24:24+len(data)]=data
    return bytes(s)


def directory_record(name,sector,size,flags=0):
    length=33+len(name)+(1 if len(name)%2==0 else 0)
    b=bytearray(length);b[0]=length
    struct.pack_into('<I',b,2,sector);struct.pack_into('<I',b,10,size)
    b[25]=flags;b[32]=len(name);b[33:33+len(name)]=name
    return bytes(b)


def write_disc(path,exe,wa):
    sectors=[raw_sector() for _ in range(1000+(len(wa)+2047)//2048)]
    pvd=bytearray(2048);pvd[0]=1;pvd[1:6]=b'CD001';pvd[6]=1
    pvd[156:156+34]=directory_record(b'\0',20,2048,2)
    sectors[16]=raw_sector(pvd)
    root=bytearray(2048)
    root_entries=[directory_record(b'SLUS_014.11;1',25,len(exe)),directory_record(b'DATA',22,2048,2)]
    root[:len(root_entries[0])]=root_entries[0]
    root[len(root_entries[0]):len(root_entries[0])+len(root_entries[1])]=root_entries[1]
    sectors[20]=raw_sector(root)
    sub=directory_record(b'WA_MRG.MRG;1',1000,len(wa))
    sectors[22]=raw_sector(sub)
    for data,at in ((exe,25),(wa,1000)):
        for i in range((len(data)+2047)//2048):
            sectors[at+i]=raw_sector(data[i*2048:(i+1)*2048])
    path.write_bytes(b''.join(sectors))


class TestContentPatch(unittest.TestCase):
    def test_name_shortens_without_touching_neighbor(self):
        exe=sample_exe()
        patched,changes=patch_names(exe,{1:'A'})
        self.assertEqual(len(changes),1)
        self.assertEqual(patched[where(0x801D6000):where(0x801D6000)+3],b'\x01\xff\xff')
        self.assertEqual(len(patched),len(exe))
        self.assertEqual(patched[:where(0x801D6000)],exe[:where(0x801D6000)])

    def test_reject_long_unknown_shared_name(self):
        exe=sample_exe()
        for name in ('AAA','🔥'):
            with self.assertRaises(ModError):name_patch_info(exe,1,name)
        shared=bytearray(exe)
        struct.pack_into('<H',shared,where(0x801D5800+4),0x6000)
        with self.assertRaises(ModError):name_patch_info(bytes(shared),1,'A')

    def test_colored_description_native_and_custom_icon_blocked(self):
        original=sample_exe()
        description='{color:vermelho}A{/color} {f8 0B 08}'
        patched,changes=patch_descriptions(original,{1:description},{})
        self.assertEqual(len(changes),1)
        at=where(0x801C3000)
        self.assertEqual(patched[at:at+3],bytes([0xF8,0x0A,6]))
        self.assertIn(bytes([0xF8,0x0B,8]),patched[at:at+14])
        self.assertEqual(original[:at],patched[:at])
        with self.assertRaises(ModError):
            description_patch_info(original,1,'{icon:perfurar}',{})
        with self.assertRaises(ModError):
            description_patch_info(original,1,'A'*99,{})

    def test_art_patch_preserves_palette_and_other_regions(self):
        with tempfile.TemporaryDirectory() as temp:
            png=Path(temp)/'art.png'
            Image.new('RGBA',(102,96),(255,0,0,255)).save(png)
            wa=sample_wa()
            patched,records=patch_card_art(wa,1,png)
            base=722*2048
            self.assertEqual([r['regiao'] for r in records],['arte','miniatura'])
            self.assertEqual(patched[base:base+102*96],bytes([1])*9792)
            self.assertEqual(patched[base+0x2640:base+0x2840],wa[base+0x2640:base+0x2840])
            self.assertEqual(patched[0x500:0x580],wa[0x500:0x580])
            self.assertEqual(patched[base+0x2840:base+0x2ae0],wa[base+0x2840:base+0x2ae0])
            self.assertEqual(patched[0:1280],bytes([1])*1280) # thumb mantém azul, paleta local
            with self.assertRaises(ModError):patch_card_art(wa,723,png)

    def test_integrated_bin_with_name_and_art(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);exe=sample_exe();wa=sample_wa();src=root/'game.bin'
            write_disc(src,exe,wa)
            project_dir=root/'projeto';(project_dir/'base').mkdir(parents=True)
            (project_dir/'assets'/'cartas').mkdir(parents=True)
            Image.new('RGBA',(102,96),(255,0,0,255)).save(project_dir/'assets'/'cartas'/'001.png')
            (project_dir/'base'/'source_SLUS_014.11').write_bytes(exe)
            (project_dir/'base'/'resumo.json').write_text(json.dumps({'source_sha256':{'DATA/WA_MRG.MRG':hashlib.sha256(wa).hexdigest()}}))
            p=type('ProjectStub',(),{})()
            p.folder=project_dir;p.edits={'1':{'nome':'A','descricao':'{color:vermelho}A{/color}'}};p.effects={};p.new_cards={}
            p.arts={'1':'assets/cartas/001.png'}
            p.metadata={'base_sha256':{'slus':hashlib.sha256(exe).hexdigest()},
                        'ps1_god_type_test_card_id':1,
                        'ps1_god_chest_preview':True,'ps1_god_hand_preview':True,
                        'ps1_god_icon_test_card_id':1}
            p.get=lambda cid:{'nome':'A','descricao':'{color:vermelho}A{/color}','tipo_id':0,'atributo_id':0}
            def do_export():
                path=project_dir/'exportacao';path.mkdir(exist_ok=True)
                return path,{}
            p.export=do_export
            original=src.read_bytes()
            result=build_test_disc(p,src)
            self.assertEqual(result['god24_cartas'],[])
            self.assertIsNone(result['teste_visual_icone_deus'])
            self.assertEqual(len(result['nomes_aplicados']),1)
            self.assertEqual(len(result['descricoes_aplicadas']),1)
            self.assertEqual(len(result['artes_aplicadas']),2)
            self.assertIn('PENDENTE',json.dumps(audit(p),ensure_ascii=False))
            self.assertTrue((project_dir/'exportacao'/'compatibilidade_ps1.json').exists())
            with DiscReader(Path(result['bin'])) as v:
                paths={x.path:x for x in v.files() if not x.is_dir}
                patched_exe=b''.join(v.read_entry(paths['SLUS_014.11']))
                patched_wa=b''.join(v.read_entry(paths['DATA/WA_MRG.MRG']))
            self.assertEqual(patched_exe[where(0x801D6000):where(0x801D6000)+2],b'\x01\xff')
            self.assertEqual(patched_exe[where(0x801C3000):where(0x801C3000)+3],bytes([0xF8,0x0A,6]))
            self.assertEqual(patched_wa[722*2048],1)
            self.assertEqual(src.read_bytes(),original)
            for lba in result['lbas']:
                raw=Path(result['bin']).read_bytes()[lba*2352:(lba+1)*2352]
                self.assertEqual(raw,regenerate_form1(raw))
            # Regressão: uma descrição incompatível deve bloquear no modo
            # rigoroso, mas permitir uma segunda tentativa consciente, com
            # a descrição original intacta e o motivo registrado no JSON.
            previous_bin=Path(result['bin']).read_bytes()
            p.edits={'1':{'nome':'A','descricao':'A'*50}}
            p.get=lambda cid:{'nome':'A','descricao':'A'*50,
                              'tipo_id':0,'atributo_id':0}
            with self.assertRaises(DescriptionCompatibilityError):
                build_test_disc(p,src)
            self.assertEqual(Path(result['bin']).read_bytes(),previous_bin)
            retry=build_test_disc(p,src,description_policy='preserve_incompatible')
            self.assertEqual(retry['politica_descricoes_ps1'],'preserve_incompatible')
            self.assertEqual(len(retry['descricoes_nao_gravadas']),1)
            self.assertEqual(retry['descricoes_aplicadas'],[])
            self.assertTrue(Path(retry['bin']).with_suffix('.json').is_file())
            with DiscReader(Path(retry['bin'])) as check:
                check_files={x.path:x for x in check.files() if not x.is_dir}
                after_exe=b''.join(check.read_entry(check_files['SLUS_014.11']))
            self.assertEqual(after_exe[where(0x801C3000):where(0x801C3000)+13],
                             bytes([1])*12+b'\xff')
            self.assertEqual(src.read_bytes(),original)
            p.effects={'1':[{'acao':'falso'}]}
            with self.assertRaisesRegex(ModError,'Build completo bloqueado'):
                build_test_disc(p,src,require_complete=True)

if __name__=='__main__':unittest.main()
