"""Testes sintéticos do motor Equip bitmap de 94 bytes usado por MODs PS1."""
from __future__ import annotations

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
from fmstudio.ps1_equip import patch_equipment_targets, list_equipment_targets
from fmstudio.ps1_equip_bitmap import (
    CHECK_EQUIP, RECORD_BYTES, _candidate_tables, inspect_bitmap_equips,
    patch_bitmap_equips,
)
from fmstudio.tables import (EXE_DELTA, WA_TERRAIN_BASE, TERRAIN_STRIDE,
                             TERRAIN_COPIES, EQUIP_OFF, FUSION_OFF, FUSION_LEN)
from test_ps1_equip import sample_wa
from test_ps1_content import write_disc

BITMAP_OFFSET = 0x600
EQUIP_ID = 315
MONSTER = 16


def fake_exe(hook=False, recognized=True):
    exe = bytearray(b'PS-X EXE' + bytes(0xB200))
    at = CHECK_EQUIP - EXE_DELTA
    if hook:
        addr = 0x8001A008
        j = (2 << 26) | ((addr & 0x0fffffff) >> 2)
        struct.pack_into('<I', exe, at, j)
        at = addr - EXE_DELTA
    # lui t0, 0x8018; addiu t0,t0,-0x5828 == 0x8017A7D8.
    # addiu t2,t2,94; srlv t3,t4,t5.
    code = [0x3C088018, 0x2508A7D8,
            0x254A005E if recognized else 0x254A005D,
            (13 << 21) | (12 << 16) | (11 << 11) | 6]
    for i, word in enumerate(code):
        struct.pack_into('<I', exe, at + 4 * i, word)
    return bytes(exe)


def fake_wa():
    wa = bytearray(sample_wa())
    for terrain in range(TERRAIN_COPIES):
        base = WA_TERRAIN_BASE + terrain * TERRAIN_STRIDE + EQUIP_OFF
        # Tabela antiga sem byte livre imediatamente após o terminador.
        wa[base+16:base+20] = b'\xDE\xAD\xBE\xEF'
        record = base + BITMAP_OFFSET
        struct.pack_into('<H', wa, record, EQUIP_ID)
        # Monstro #004 já permitido no bitmap.
        wa[record+2] = 0x08
        # Próximo registro contém ID=0 e termina a lista.
        struct.pack_into('<H', wa, record + RECORD_BYTES, 0)
    return bytes(wa)


class EquipBitmapTests(unittest.TestCase):
    def test_legacy_extension_fails_but_bitmap_addition_preserves_other_bytes(self):
        exe, wa = fake_exe(), fake_wa()
        with self.assertRaisesRegex(ModError, 'insuficiente'):
            patch_equipment_targets(wa, {'650': [7]})
        layout = inspect_bitmap_equips(exe, wa, {str(EQUIP_ID):[MONSTER]})
        self.assertEqual(layout['offset_equip'], BITMAP_OFFSET)
        patched, entries = patch_bitmap_equips(exe, wa, {str(EQUIP_ID):[MONSTER]})
        self.assertEqual(entries[0]['modo'], 'bitmap-94')
        offset = BITMAP_OFFSET + 2 + (MONSTER >> 3)
        differences = [i for i, (a, b) in enumerate(zip(wa, patched)) if a != b]
        self.assertEqual(differences, [
            WA_TERRAIN_BASE + k*TERRAIN_STRIDE + EQUIP_OFF + offset
            for k in range(TERRAIN_COPIES)
        ])
        self.assertEqual(len(patched), len(wa))
        for terrain in range(TERRAIN_COPIES):
            start = WA_TERRAIN_BASE + terrain*TERRAIN_STRIDE
            self.assertEqual(
                wa[start+FUSION_OFF:start+FUSION_OFF+FUSION_LEN],
                patched[start+FUSION_OFF:start+FUSION_OFF+FUSION_LEN]
            )
            self.assertEqual(wa[start+EQUIP_OFF+16:start+EQUIP_OFF+20],
                             patched[start+EQUIP_OFF+16:start+EQUIP_OFF+20])
        # A tabela stock continua intocada.
        self.assertEqual(list_equipment_targets(wa), list_equipment_targets(patched))

    def test_hooked_code_is_detected(self):
        exe, wa = fake_exe(hook=True), fake_wa()
        report = inspect_bitmap_equips(exe, wa, {str(EQUIP_ID):[MONSTER]})
        self.assertEqual(report['offset_equip'], BITMAP_OFFSET)
        self.assertIn('hook', report['origem'])

    def test_unknown_mips_returns_no_bitmap_patch(self):
        exe, wa = fake_exe(recognized=False), fake_wa()
        self.assertIsNone(inspect_bitmap_equips(exe, wa, {str(EQUIP_ID):[MONSTER]}))
        self.assertIsNone(patch_bitmap_equips(exe, wa, {str(EQUIP_ID):[MONSTER]}))

    def test_signature_without_table_address_refuses_stock_fallback(self):
        exe = bytearray(fake_exe())
        at = CHECK_EQUIP - EXE_DELTA
        struct.pack_into('<II', exe, at, 0, 0)
        with self.assertRaisesRegex(ModError, 'não foi possível confirmar'):
            patch_bitmap_equips(bytes(exe), fake_wa(), {str(EQUIP_ID):[MONSTER]})

    def test_addition_is_idempotent(self):
        exe, wa = fake_exe(), fake_wa()
        first, applied = patch_bitmap_equips(exe,wa,{str(EQUIP_ID):[MONSTER]})
        self.assertEqual(len(applied),1)
        after, redundant = patch_bitmap_equips(exe,first,{str(EQUIP_ID):[MONSTER]})
        self.assertEqual(after,first)
        self.assertEqual(redundant, [])

    def test_bin_cue_generation_uses_mips_bitmap_without_shifting_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            image=root/'Drop-x15.bin'
            exe,wa=fake_exe(),fake_wa()
            write_disc(image,exe,wa)
            old_sha=hashlib.sha256(image.read_bytes()).hexdigest()
            project_root=root/'Studio'
            (project_root/'base').mkdir(parents=True)
            (project_root/'base'/'resumo.json').write_text(
                json.dumps({'source_sha256':{
                    'DATA/WA_MRG.MRG': hashlib.sha256(wa).hexdigest()
                }}),encoding='utf-8')
            project=SimpleNamespace(
                folder=project_root,arts={},
                metadata={'base_sha256':{'slus':hashlib.sha256(exe).hexdigest()},
                          'ps1_equip_additions':{str(EQUIP_ID):[MONSTER]},
                          'ps1_equip_mode':'adicionar'})
            project.export=lambda:(project_root/'exportacao',{})
            built=build_test_disc(project,image)
            self.assertEqual(built['estrategia_equip_ps1'],'bitmap-mips-94')
            self.assertEqual(len(built['equipamentos_ps1_aplicados']),1)
            with DiscReader(built['bin']) as disc:
                entry=next(x for x in disc.files()
                           if x.path=='DATA/WA_MRG.MRG')
                wa2=b''.join(disc.read_entry(entry))
            self.assertNotEqual(wa,wa2)
            self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(),old_sha)


if __name__=='__main__':
    unittest.main()
