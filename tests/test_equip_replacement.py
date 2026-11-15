"""Experimento seguro para Equip sem bytes de expansão na ISO do PS1."""
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
from fmstudio.ps1_equip import (
    list_equipment_targets, patch_equipment_targets, replace_equipment_targets,
)
from fmstudio.tables import (
    EQUIP_OFF, TERRAIN_COPIES, TERRAIN_STRIDE, WA_TERRAIN_BASE,
    FUSION_OFF, FUSION_LEN,
)
from test_ps1_content import write_disc
from test_ps1_equip import sample_wa


def no_free_space_wa():
    wa = bytearray(sample_wa())
    for idx in range(TERRAIN_COPIES):
        start = WA_TERRAIN_BASE + idx * TERRAIN_STRIDE + EQUIP_OFF
        # Na fixture, terminador u16 é 0x0e/0x0f e o byte não nulo
        # começa IMEDIATAMENTE após 0x10 (sem espaço de expansão).
        wa[start + 16:start + 20] = b'\xA7\xBE\x35\x23'
    return bytes(wa)


class InPlaceEquipmentTests(unittest.TestCase):
    def test_no_space_add_rejected_but_replacement_keeps_all_other_bytes(self):
        source = no_free_space_wa()
        with self.assertRaisesRegex(ModError, 'insuficiente'):
            patch_equipment_targets(source, {'650': [7]})
        actual, applied = replace_equipment_targets(source, {'650': {'16': 7}})
        self.assertEqual(applied[0]['novo_alvo'], 7)
        self.assertEqual(list_equipment_targets(actual)[650], [7])
        self.assertEqual(list_equipment_targets(source)[650], [16])
        self.assertEqual(len(actual), len(source))
        diffs = [index for index, (x, y) in enumerate(zip(source, actual)) if x != y]
        self.assertEqual(diffs, [WA_TERRAIN_BASE + k * TERRAIN_STRIDE + EQUIP_OFF + 4
                                  for k in range(TERRAIN_COPIES)])
        for idx in range(TERRAIN_COPIES):
            start = WA_TERRAIN_BASE + idx * TERRAIN_STRIDE
            self.assertEqual(actual[start + FUSION_OFF:start + FUSION_OFF + FUSION_LEN],
                             source[start + FUSION_OFF:start + FUSION_OFF + FUSION_LEN])
            self.assertEqual(actual[start + EQUIP_OFF + 16:start + EQUIP_OFF + 20],
                             source[start + EQUIP_OFF + 16:start + EQUIP_OFF + 20])

    def test_requires_existing_target_and_different_replacement(self):
        wa = no_free_space_wa()
        with self.assertRaisesRegex(ModError,'não permite'):
            replace_equipment_targets(wa, {'650': {'10':7}})
        with self.assertRaisesRegex(ModError,'já permite'):
            replace_equipment_targets(wa, {'651': {'1':4}})
        with self.assertRaisesRegex(ModError,'diferente'):
            replace_equipment_targets(wa, {'650': {'16':16}})

    def test_generation_on_no_space_image_preserves_old_additions_in_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            source=folder/'mod-x15.bin'
            original_exe=b'PS-X EXE'+bytes(2048)
            original_wa=no_free_space_wa()
            write_disc(source,original_exe,original_wa)
            source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            project_root=folder/'projeto'
            (project_root/'base').mkdir(parents=True)
            (project_root/'base'/'resumo.json').write_text(
                json.dumps({'source_sha256':{
                    'DATA/WA_MRG.MRG':hashlib.sha256(original_wa).hexdigest()}}),
                encoding='utf-8')
            metadata={
                'base_sha256':{'slus':hashlib.sha256(original_exe).hexdigest()},
                'ps1_equip_mode':'substituir',
                'ps1_equip_replacements':{'650':{'16':7}},
                'ps1_equip_additions':{'651':[40]},
            }
            project=SimpleNamespace(folder=project_root,metadata=metadata,arts={})
            project.export=lambda:(project_root/'exportacao',{})
            result=build_test_disc(project,source)
            self.assertEqual(result['modo_equip_ps1'],'substituir')
            self.assertEqual(len(result['equipamentos_ps1_aplicados']),1)
            self.assertEqual(metadata['ps1_equip_additions'], {'651':[40]})
            with DiscReader(result['bin']) as disc:
                entry=next(x for x in disc.files() if x.path=='DATA/WA_MRG.MRG')
                modified=b''.join(disc.read_entry(entry))
            self.assertEqual(list_equipment_targets(modified)[650],[7])
            self.assertEqual(list_equipment_targets(modified)[651],[1,4])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),source_hash)


if __name__=='__main__':
    unittest.main()
