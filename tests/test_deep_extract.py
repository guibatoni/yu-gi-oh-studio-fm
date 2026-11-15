"""Testes sintéticos, sem qualquer imagem de jogo real."""
from __future__ import annotations
import tempfile
import unittest
import csv
import struct
from pathlib import Path
from unittest.mock import patch

from fmstudio.deep_extract import (exe_pos,extract_texts,_art_image,export_visuals,
                                   ExtractionError, prepare_full_catalog)
from fmstudio.core import Project, _write_csv
from fmstudio.tables import CARD_COUNT

SZ = 1902592
BASE = 0x80010000

def addr(a):return a-BASE+0x800

def synthetic_exe():
    exe=bytearray(SZ)
    exe[:8]=b'PS-X EXE'
    # Glifo 01: A e 02: B, Shift-JIS de largura total, depois NFKC.
    struct.pack_into('<I',exe,addr(0x801D9000+4),0x8260)
    struct.pack_into('<I',exe,addr(0x801D9000+8),0x8261)
    # Carta 1 -> offset de nome no banco 0x801D0000.
    struct.pack_into('<H',exe,addr(0x801D5800+2),0x6000)
    exe[addr(0x801D6000):addr(0x801D6000)+3]=bytes([1,2,0xff])
    # Carta 1 -> descrição D101, pointer 0x2000 no banco 0x801C0000.
    struct.pack_into('<H',exe,addr(0x801C0000+(0x100+1)*2),0x2000)
    exe[addr(0x801C2000):addr(0x801C2000)+4]=bytes([1,0xfe,2,0xff])
    # Menu 0x0000 -> pointer de diálogo 0x2200 no banco 0x801B0000.
    struct.pack_into('<H',exe,addr(0x801C0000),0x2200)
    exe[addr(0x801B2200):addr(0x801B2200)+2]=bytes([1,0xff])
    return bytes(exe)

class TestDeepExtract(unittest.TestCase):
    def test_memory_bounds(self):
        self.assertEqual(exe_pos(BASE, bytes(0x900),1),0x800)
        with self.assertRaises(ExtractionError):exe_pos(BASE+0x2000,bytes(0x900),1)

    def test_text_from_original_banks(self):
        results, warnings=extract_texts(synthetic_exe())
        self.assertEqual(results['nomes_descricoes'][0]['nome'],'AB')
        self.assertEqual(results['nomes_descricoes'][0]['descricao'],'A\nB')
        self.assertEqual(results['textos_menu_historia'][0]['texto'],'A')
        self.assertEqual(results['metricas_texto'][0]['nomes_cartas'],1)
        self.assertEqual(len(results['textos_nomes']),0x360)
        self.assertEqual(len(results['textos_descricoes']),0x300)

    def test_palette_png(self):
        wa=bytearray(4096)
        # Indices 0 e 1, cor 1=vermelho, paleta a 256.
        wa[0:4]=bytes([1,0,1,0])
        struct.pack_into('<H',wa,258,31)
        png=_art_image(bytes(wa),0,1,2,256,256)
        self.assertEqual(png[:8],b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II',png[16:24]),(2,2))

    def test_art_and_portrait_outputs_on_synthetic_data(self):
        # Reduz amostra para três cartas; ainda valida que cenas e retratos são processados.
        wa=bytes(37_748_736)
        with tempfile.TemporaryDirectory() as t, patch('fmstudio.deep_extract.CARD_COUNT',3):
            numbers,manifest,errors=export_visuals(wa,Path(t),include_strips=True)
            self.assertEqual(numbers['artes'],3)
            self.assertEqual(numbers['miniaturas'],3)
            self.assertEqual(numbers['faixas'],6)
            self.assertEqual(numbers['retratos'],65)
            self.assertEqual(numbers['cenas_historia'],105)
            self.assertFalse(errors)
            self.assertTrue((Path(t)/'cartas'/'001.png').is_file())
            self.assertTrue((Path(t)/'cenas_historia'/'cena_m2_12.png').is_file())
            self.assertEqual(len(manifest),3*4+65+105)

    def test_enrichment_never_rewrites_stats(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t)
            rows=[{'id':cid,'valor_hex':f'{cid:08X}','ataque':cid,'defesa':0} for cid in range(1,CARD_COUNT+1)]
            _write_csv(base/'cartas.csv',rows)
            before=[(i['id'],i['valor_hex'],i['ataque']) for i in rows]
            txt=[{'id':cid,'nome':f'Carta {cid}','descricao':'Desc'} for cid in range(1,CARD_COUNT+1)]
            metric=prepare_full_catalog(base,txt)
            self.assertEqual(metric['campos_adicionados'],1444)
            with (base/'cartas.csv').open('r',encoding='utf-8-sig',newline='') as f:
                after=list(csv.DictReader(f,delimiter=';'))
            self.assertEqual(before,[(int(r['id']),r['valor_hex'],int(r['ataque'])) for r in after])
            self.assertEqual(after[0]['nome'],'Carta 1')
            self.assertTrue((base/'cartas_antes_textos.csv').exists())

if __name__=='__main__':unittest.main()
