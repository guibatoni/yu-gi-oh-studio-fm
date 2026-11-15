"""Testes sem ROM: efeitos nativos de equipamento em sete cópias WA."""
import struct
import unittest
from types import SimpleNamespace

from fmstudio.core import ModError
from fmstudio.tables import (WA_TERRAIN_BASE, TERRAIN_STRIDE, TERRAIN_COPIES,
                             EQUIP_OFF, EQUIP_LEN, FUSION_OFF, FUSION_LEN)
from fmstudio.ps1_equip import (patch_equipment_targets, list_equipment_targets,
                               add_equipment_target, META_KEY)


def sample_wa():
    size = WA_TERRAIN_BASE + (TERRAIN_COPIES-1)*TERRAIN_STRIDE + FUSION_OFF + FUSION_LEN
    wa = bytearray(size)
    equip = struct.pack('<HHH', 650, 1, 16) + struct.pack('<HHHH',651,2,1,4)
    equip += b'\x00'*4
    for i in range(TERRAIN_COPIES):
        pos=WA_TERRAIN_BASE+i*TERRAIN_STRIDE
        wa[pos+EQUIP_OFF:pos+EQUIP_OFF+len(equip)] = equip
        wa[pos+FUSION_OFF:pos+FUSION_OFF+10] = b'FUSIONDATA'
    return bytes(wa)


class NativeEquipTests(unittest.TestCase):
    def test_add_one_monster_to_equipment_without_touching_fusions(self):
        source=sample_wa()
        modified,actions=patch_equipment_targets(source,{'650':[1,4]})
        self.assertEqual(len(actions),1)
        self.assertEqual(actions[0]['novos_alvos'],[1,4])
        self.assertEqual(len(modified),len(source))
        targets=list_equipment_targets(modified)
        self.assertEqual(targets[650],[16,1,4])
        self.assertEqual(targets[651],[1,4])
        for i in range(TERRAIN_COPIES):
            p=WA_TERRAIN_BASE+i*TERRAIN_STRIDE
            self.assertEqual(modified[p+FUSION_OFF:p+FUSION_OFF+FUSION_LEN],
                             source[p+FUSION_OFF:p+FUSION_OFF+FUSION_LEN])
            self.assertEqual(modified[p+EQUIP_OFF:p+EQUIP_OFF+EQUIP_LEN],
                             modified[WA_TERRAIN_BASE+EQUIP_OFF:
                                      WA_TERRAIN_BASE+EQUIP_OFF+EQUIP_LEN])

    def test_noop_does_not_modify_bytes(self):
        original=sample_wa()
        result,actions=patch_equipment_targets(original,{'650':[16]})
        self.assertIs(result,original)
        self.assertEqual(actions,[])

    def test_unknown_equip_is_rejected(self):
        with self.assertRaises(ModError):
            patch_equipment_targets(sample_wa(),{'652':[1]})

    def test_different_terrain_is_rejected(self):
        broken=bytearray(sample_wa())
        p=WA_TERRAIN_BASE+TERRAIN_STRIDE+EQUIP_OFF
        broken[p] ^= 0x01
        with self.assertRaisesRegex(ModError,'divergem'):
            patch_equipment_targets(bytes(broken),{'650':[1]})

    def test_register_target_requires_original_equip_and_monster(self):
        cards={650:23,16:1,1:0}
        def card(cid):return {'tipo_id':cards[cid]}
        project=SimpleNamespace(get=card,metadata={})
        self.assertTrue(add_equipment_target(project,650,16))
        self.assertEqual(project.metadata[META_KEY],{'650':[16]})
        self.assertFalse(add_equipment_target(project,650,16))
        with self.assertRaises(ModError):
            add_equipment_target(project,16,1)

class NativeEquipDiscIntegration(unittest.TestCase):
    def test_build_bin_rewrites_all_equip_tables_and_preserves_source(self):
        import hashlib
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from fmstudio.disc import DiscReader
        from fmstudio.disc_build import build_test_disc
        from test_ps1_content import write_disc

        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/'original.bin'
            exe=b'PS-X EXE'+bytes(2048)
            wa=sample_wa()
            write_disc(source,exe,wa)
            image_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            project_folder=root/'studio-project'
            (project_folder/'base').mkdir(parents=True)
            (project_folder/'base'/'resumo.json').write_text(
                __import__('json').dumps({
                    'source_sha256':{'DATA/WA_MRG.MRG':hashlib.sha256(wa).hexdigest()}
                }),encoding='utf-8')
            project=SimpleNamespace(
                folder=project_folder,
                arts={},
                metadata={'base_sha256':{'slus':hashlib.sha256(exe).hexdigest()},
                          META_KEY:{'650':[1]}})
            project.export=lambda : (project_folder/'exportacao', {})
            result=build_test_disc(project,source)
            self.assertEqual(result['equipamentos_ps1_aplicados'][0]['novos_alvos'],[1])
            self.assertTrue(result['setores_modificados']>0)
            with DiscReader(Path(result['bin'])) as reader:
                wa_entry=next(x for x in reader.files() if x.path=='DATA/WA_MRG.MRG')
                modified=b''.join(reader.read_entry(wa_entry))
            self.assertIn(1,list_equipment_targets(modified)[650])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),image_hash)


if __name__=='__main__':
    unittest.main()
