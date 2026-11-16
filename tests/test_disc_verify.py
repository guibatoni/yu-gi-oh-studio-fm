"""Verifica valores de cartas diretamente da imagem selecionada (discos sintéticos)."""
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from fmstudio.disc import SYNC
from fmstudio.disc_verify import verify_image_stats, describe
from fmstudio.core import ModError
from fmstudio.tables import STATS_ADDR, LEVEL_ADDR, EXE_DELTA


def sector(data=b''):
    raw=bytearray(2352)
    raw[:12]=SYNC
    raw[15]=2
    raw[16:20]=b'\x00\x00\x08\x00'
    raw[20:24]=raw[16:20]
    raw[24:24+len(data)]=data
    return bytes(raw)


def directory(name, location, size, flags=0):
    n=len(name)
    length=33+n+(0 if n%2 else 1)
    out=bytearray(length)
    out[0]=length
    struct.pack_into('<I',out,2,location)
    struct.pack_into('<I',out,10,size)
    out[25]=flags
    out[32]=n
    out[33:33+n]=name
    return bytes(out)


def create_disc(path, atk, typ=1):
    exe=bytearray(1902592)
    exe[:8]=b'PS-X EXE'
    off=STATS_ADDR-EXE_DELTA+(16-1)*4
    raw=(typ<<26)|(10<<22)|(8<<18)|(40<<9)|(atk//10)
    struct.pack_into('<I',exe,off,raw)
    exe[LEVEL_ADDR-EXE_DELTA+16]=2
    file_lba=25
    blocks=[sector() for _ in range(file_lba + (len(exe)+2047)//2048)]
    root=directory(b'\x00',20,2048,2)
    pvd=bytearray(2048)
    pvd[0]=1
    pvd[1:6]=b'CD001'
    pvd[6]=1
    pvd[156:156+len(root)]=root
    blocks[16]=sector(pvd)
    contents=bytearray(2048)
    item=directory(b'SLUS_014.11;1',file_lba,len(exe))
    contents[:len(item)]=item
    blocks[20]=sector(contents)
    for i in range((len(exe)+2047)//2048):
        blocks[file_lba+i]=sector(exe[i*2048:(i+1)*2048])
    path.write_bytes(b''.join(blocks))


class CardValueVerificationTests(unittest.TestCase):
    def test_god_type_is_not_silently_skipped_in_bin_verification(self):
        from fmstudio.core import ModError
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'teste.bin'
            create_disc(path,500)
            base={'id':16,'nome':'Time Wizard','ataque':500,'defesa':400,
                  'tipo_id':1,'atributo_id':0,'nivel':2,
                  'guardian_1_id':10,'guardian_2_id':8}
            edited={**base,'ataque':3000,'tipo_id':24}
            project=SimpleNamespace(
                edits={'16':{'ataque':3000,'tipo_id':24}},
                cards={16:base},get=lambda cid:edited)
            with self.assertRaisesRegex(ModError,'incompatível'):
                verify_image_stats(project,path)

    def test_opt_in_god_type_24_rechecked_in_generated_bin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'god24.bin'
            other=Path(tmp)/'wrongtype.bin'
            create_disc(path,3000,typ=24)
            create_disc(other,3000,typ=1)
            base={'id':16,'nome':'Time Wizard','ataque':500,'defesa':400,
                  'tipo_id':1,'atributo_id':0,'nivel':2,
                  'guardian_1_id':10,'guardian_2_id':8}
            edited={**base,'ataque':3000,'tipo_id':24}
            project=SimpleNamespace(
                metadata={'ps1_god_type_test_card_id':16},
                edits={'16':{'ataque':3000,'tipo_id':24}},
                cards={16:base},get=lambda cid:edited)
            good=verify_image_stats(project,path)
            bad=verify_image_stats(project,other)
            self.assertEqual((good['total'],good['corretas'],good['divergentes']),
                             (1,1,0))
            self.assertEqual(bad['divergentes'],1)
            self.assertEqual(good['god24_tipo_gravado_e_verificado'],[16])
            self.assertIn('God 24 gravado',describe(good))
            project.metadata={}
            with self.assertRaisesRegex(ModError,'incompatível'):
                verify_image_stats(project,path)

    def test_time_wizard_differs_on_original_and_matches_on_generated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            original=root/'original.bin'
            patched=root/'FM_STUDIO_TESTE.bin'
            create_disc(original, 500)
            create_disc(patched, 3000)
            base={'id':16,'nome':'Time Wizard','ataque':500,'defesa':400,
                  'tipo_id':1,'atributo_id':0,'nivel':2,
                  'guardian_1_id':10,'guardian_2_id':8}
            edited={**base,'ataque':3000}
            project=SimpleNamespace(
                edits={'16':{'ataque':3000}},
                cards={16:base},
                get=lambda cid:edited)
            wrong=verify_image_stats(project,original)
            good=verify_image_stats(project,patched)
            self.assertEqual((wrong['total'],wrong['divergentes']), (1,1))
            self.assertEqual((good['total'],good['corretas']), (1,1))
            self.assertEqual(wrong['cartas'][0]['campos']['ataque']['bin'],500)
            self.assertEqual(good['cartas'][0]['campos']['ataque']['bin'],3000)
            self.assertIn('BIN 3000', describe(good))
            self.assertIn('BIN 500', describe(wrong))


if __name__=='__main__':
    unittest.main()
