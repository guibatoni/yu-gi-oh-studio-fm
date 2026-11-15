"""Efeitos nativos PS1 em SLUS e WA: sem alterar os bytes fora das tabelas."""
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fmstudio.core import ModError
from fmstudio.disc import DiscReader
from fmstudio.disc_build import build_test_disc
from fmstudio.ps1_native import (
    patch_rituals, read_rituals, patch_trap_thresholds,
    read_trap_thresholds, patch_terrain_boosts, read_terrain_boosts,
    TRAP_ADDRESS, TRAP_RETAIL, TERRAIN_ADDRESS,
)
from fmstudio.tables import (
    EXE_DELTA, WA_TERRAIN_BASE, TERRAIN_STRIDE,
    TERRAIN_COPIES, FUSION_OFF, FUSION_LEN, RITUAL_OFF, RITUAL_LEN,
)
from test_ps1_equip import sample_wa
from test_ps1_content import write_disc


def native_exe():
    exe = bytearray(b'PS-X EXE' + bytes(0x90000))
    trap = TRAP_ADDRESS - EXE_DELTA
    exe[trap:trap + 6] = TRAP_RETAIL
    terrain = TERRAIN_ADDRESS - EXE_DELTA
    for type_id in range(20):
        exe[terrain + type_id * 6] = 50
        exe[terrain + type_id * 6 + 1] = (-50) & 255
    return bytes(exe)


def native_wa():
    wa = bytearray(sample_wa())
    wa += bytes(RITUAL_LEN)
    for idx in range(TERRAIN_COPIES):
        pos=WA_TERRAIN_BASE + idx*TERRAIN_STRIDE + RITUAL_OFF
        struct.pack_into('<5H',wa,pos,690,1,2,3,4)
        struct.pack_into('<5H',wa,pos+10,691,7,8,9,10)
        # Registro seguinte zero (terminador), sem modificar as fusões.
    return bytes(wa)


class NativePS1TablesTests(unittest.TestCase):
    def test_ritual_replaces_three_tributes_and_result_in_seven_copies(self):
        original=native_wa()
        result,manifest=patch_rituals(original,{'690':[11,12,13,14]})
        self.assertEqual(len(result),len(original))
        self.assertEqual(len(manifest),1)
        self.assertEqual(read_rituals(result)[690],(11,12,13,14))
        self.assertEqual(read_rituals(result)[691],(7,8,9,10))
        differences=[i for i,(old,new) in enumerate(zip(original,result)) if old!=new]
        expected={WA_TERRAIN_BASE+idx*TERRAIN_STRIDE+RITUAL_OFF+2+j
                  for idx in range(TERRAIN_COPIES) for j in (0,2,4,6)}
        self.assertEqual(set(differences),expected)
        for idx in range(TERRAIN_COPIES):
            fusion=WA_TERRAIN_BASE+idx*TERRAIN_STRIDE+FUSION_OFF
            self.assertEqual(original[fusion:fusion+FUSION_LEN],
                             result[fusion:fusion+FUSION_LEN])

    def test_ritual_rejects_unknown_id_and_different_terrain_copy(self):
        original=native_wa()
        with self.assertRaisesRegex(ModError,'não existe'):
            patch_rituals(original,{'699':[1,2,3,4]})
        wa=bytearray(original)
        at=WA_TERRAIN_BASE+TERRAIN_STRIDE+RITUAL_OFF
        wa[at+2]^=1
        with self.assertRaisesRegex(ModError,'diferem'):
            patch_rituals(bytes(wa),{'690':[1,2,3,5]})

    def test_trap_thresholds_are_one_byte_and_require_retail_layout(self):
        original=native_exe()
        out,changes=patch_trap_thresholds(original,{'681':700})
        self.assertEqual(len(changes),1)
        self.assertEqual(read_trap_thresholds(out)[681],700)
        off=TRAP_ADDRESS-EXE_DELTA
        diffs=[i for i,(a,b) in enumerate(zip(original,out)) if a!=b]
        self.assertEqual(diffs,[off])
        with self.assertRaisesRegex(ModError,'ordem crescente'):
            patch_trap_thresholds(original,{'681':3000})
        unsafe=bytearray(original)
        unsafe[off]=99
        with self.assertRaisesRegex(ModError,'diferente do layout'):
            patch_trap_thresholds(bytes(unsafe),{'681':700})

    def test_terrain_boosts_edit_only_requested_byte(self):
        original=native_exe()
        result,changes=patch_terrain_boosts(original,{'1:0':800})
        self.assertEqual(len(changes),1)
        self.assertEqual(read_terrain_boosts(result)[(1,0)],800)
        self.assertEqual(read_terrain_boosts(result)[(2,0)],-500)
        self.assertEqual(len(result),len(original))
        offset=TERRAIN_ADDRESS-EXE_DELTA
        self.assertEqual([i for i,(a,b) in enumerate(zip(original,result)) if a!=b],
                         [offset])
        altered=bytearray(original)
        altered[offset]=0x42
        with self.assertRaisesRegex(ModError,'padrão'):
            patch_terrain_boosts(bytes(altered),{'1:0':800})

    def test_all_three_export_through_same_bin_cue_without_touching_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/'Original-DropX15.bin'
            exe=native_exe()
            wa=native_wa()
            write_disc(source,exe,wa)
            original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            workspace=root/'Studio'
            (workspace/'base').mkdir(parents=True)
            (workspace/'base'/'resumo.json').write_text(
                json.dumps({'source_sha256':{'DATA/WA_MRG.MRG':
                           hashlib.sha256(wa).hexdigest()}}),encoding='utf-8')
            project=SimpleNamespace(
                folder=workspace,arts={},edits={},cards={},new_cards={},
                effects={},
                metadata={'base_sha256':{'slus':hashlib.sha256(exe).hexdigest()},
                          'ps1_ritual_recipes':{'690':[11,12,13,14]},
                          'ps1_trap_thresholds':{'681':700},
                          'ps1_terrain_boosts':{'1:0':800}})
            project.export=lambda: (workspace/'exportacao',{})
            result=build_test_disc(project,source)
            self.assertEqual(len(result['rituais_ps1_aplicados']),1)
            self.assertEqual(len(result['armadilhas_ps1_aplicadas']),1)
            self.assertEqual(len(result['terrenos_ps1_aplicados']),1)
            with DiscReader(result['bin']) as reader:
                files={entry.path:entry for entry in reader.files() if not entry.is_dir}
                new_exe=b''.join(reader.read_entry(files['SLUS_014.11']))
                new_wa=b''.join(reader.read_entry(files['DATA/WA_MRG.MRG']))
            self.assertEqual(read_rituals(new_wa)[690],(11,12,13,14))
            self.assertEqual(read_trap_thresholds(new_exe)[681],700)
            self.assertEqual(read_terrain_boosts(new_exe)[(1,0)],800)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),original_hash)


if __name__=='__main__':
    unittest.main()
