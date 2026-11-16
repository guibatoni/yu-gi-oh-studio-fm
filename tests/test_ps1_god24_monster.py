"""Regressões do scanner de classe God24; somente leitura, sem hook PS1."""
import hashlib
import struct
import unittest

from fmstudio.ps1_effects_lab import (
    GOD24_MONSTER_SITES, _god24_compare_entries,
    diagnose_god24_monster_classification,
)
from fmstudio.tables import EXE_DELTA


def synthetic_exe():
    exe=bytearray(0x75000)
    exe[:8]=b'PS-X EXE'
    struct.pack_into('<II',exe,0x18,EXE_DELTA+0x800,0x68000)
    return exe


class God24MonsterClassificationTests(unittest.TestCase):
    def test_deck_stats_guard_is_found_but_no_bytes_are_changed(self):
        exe=synthetic_exe()
        _,addr,_size,_why=GOD24_MONSTER_SITES['bau_atk_def']
        off=addr-EXE_DELTA+0x60
        struct.pack_into('<III',exe,off,0x2D280014,0x11000003,0x00000000)
        original=bytes(exe)
        report=diagnose_god24_monster_classification(original)
        self.assertEqual(report['status'],'somente_leitura')
        self.assertEqual(report['limite_retail_monstro'],20)
        self.assertEqual(report['comparacoes_imediato_20_total'],1)
        entry=report['rotinas']['bau_atk_def']['comparacoes_imediato_20'][0]
        self.assertEqual(entry['pc'],f'0x{addr+0x60:08X}')
        self.assertEqual(entry['familia'],'sltiu')
        self.assertEqual(entry['reg_origem'],9)
        self.assertEqual(entry['reg_destino'],8)
        self.assertTrue(any('ramo_destino' in x for x in entry['contexto']))
        self.assertFalse(report['tipo_24_funciona_como_monstro_ps1'])
        self.assertFalse(report['escrita_no_slus'])
        self.assertEqual(report['sha256_executavel'],hashlib.sha256(original).hexdigest())
        self.assertEqual(bytes(exe),original)

    def test_invalid_headers_and_outside_segment(self):
        self.assertEqual(diagnose_god24_monster_classification(b'bad')['status'],
                         'executavel_psx_invalido')
        exe=synthetic_exe()
        struct.pack_into('<II',exe,0x18,0x80020000,0x68000)
        self.assertEqual(diagnose_god24_monster_classification(bytes(exe))['status'],
                         'segmento_mips_invalido')
        exe=synthetic_exe()
        struct.pack_into('<II',exe,0x18,EXE_DELTA+0x800,0xFFFFFFFC)
        self.assertEqual(diagnose_god24_monster_classification(bytes(exe))['status'],
                         'segmento_mips_invalido')
        exe=synthetic_exe()
        struct.pack_into('<II',exe,0x18,EXE_DELTA+0x800,0x1000)
        report=diagnose_god24_monster_classification(bytes(exe))
        self.assertTrue(all(x['status']=='fora_segmento_carregado'
                            for x in report['rotinas'].values()))

    def test_only_type20_comparisons_are_reported_not_25_or_ori(self):
        exe=synthetic_exe()
        _,addr,_size,_why=GOD24_MONSTER_SITES['classificacao_linha']
        pos=addr-EXE_DELTA+0x20
        struct.pack_into('<IIII',exe,pos,
                         0x29280014,0x2528FFEC,0x2D280019,0x35280014)
        original=bytes(exe)
        report=diagnose_god24_monster_classification(original)
        pred=report['rotinas']['classificacao_linha']
        self.assertEqual(pred['comparacoes_imediato_20_total'],2)
        self.assertEqual([c['familia'] for c in pred['comparacoes_imediato_20']],
                         ['slti','addiu_-20'])
        self.assertIn('NÃO é seguro',report['alerta'])
        self.assertEqual(bytes(exe),original)

    def test_small_window_and_domain_coverage(self):
        n,found=_god24_compare_entries(struct.pack('<I',0x2D280014),
                                       0x80011200,0x1A00)
        self.assertEqual(n,1)
        self.assertEqual(len(found[0]['contexto']),1)
        report=diagnose_god24_monster_classification(bytes(synthetic_exe()))
        self.assertEqual(len(GOD24_MONSTER_SITES),8)
        self.assertEqual(set(report['rotinas']),set(GOD24_MONSTER_SITES))
        self.assertEqual(report['comparacoes_imediato_20_total'],0)
        self.assertTrue(report['atk_def_armazenados_podem_ficar_ocultos'])


if __name__=='__main__':
    unittest.main()
