"""Synthetic unit tests for the God24 PS1 list renderer patch."""
import hashlib
import struct
import unittest
from fmstudio.core import ModError
from fmstudio.ps1_god24_row_patch import (
    AT, ORIGINAL, PATCHED, CHANGED, inspect, apply,
)


def fixture():
    exe=bytearray(0x59000)
    exe[:8]=b'PS-X EXE'
    struct.pack_into('<'+str(len(ORIGINAL))+'I',exe,AT,*ORIGINAL)
    return bytes(exe)


class God24RealListTests(unittest.TestCase):
    def kw(self,exe):
        return {'source_sha256':hashlib.sha256(exe).hexdigest()}

    def test_changes_only_three_instructions_and_leaves_source_untouched(self):
        original=fixture()
        after,report=apply(original,original,range(25),**self.kw(original))
        self.assertEqual(inspect(after)['status'],'aplicado_3_de_3')
        self.assertEqual(report['status'],'aplicado_3_de_3')
        self.assertFalse(report['invocacao_e_combate_modificados'])
        self.assertEqual(original,fixture())
        byte_positions=set()
        for index in CHANGED:
            offset=AT+index*4
            self.assertEqual(struct.unpack_from('<I',after,offset)[0],PATCHED[index])
            byte_positions.update(range(offset,offset+4))
        self.assertTrue(all(a==b for i,(a,b) in enumerate(zip(after,original))
                            if i not in byte_positions))
        for i in range(len(ORIGINAL)):
            if i not in CHANGED:
                self.assertEqual(struct.unpack_from('<I',after,AT+4*i)[0],
                                 ORIGINAL[i])

    def test_mips_load_delay_and_sprite_store_positions_preserved(self):
        self.assertEqual(PATCHED[0],ORIGINAL[0])  # original LHU v0
        self.assertEqual(PATCHED[1],0x92210002)   # independent LBU at
        self.assertEqual(PATCHED[2],ORIGINAL[2])  # ADDIU v0
        self.assertEqual(PATCHED[3],ORIGINAL[3])  # original SH sprite
        self.assertEqual(PATCHED[4],0x30210017)   # mask at
        self.assertEqual(PATCHED[5],ORIGINAL[5])  # no change
        self.assertEqual(PATCHED[6],0x2C220014)   # compare at
        self.assertEqual(PATCHED[7:],ORIGINAL[7:]) # branch+delay
        for kind in range(25):
            self.assertEqual((kind&0x17)<20,kind<20 or kind==24)

    def test_rejects_bad_signatures_hash_and_extra_types(self):
        src=fixture()
        with self.assertRaisesRegex(ModError,'SHA'):
            apply(src,src,[24])
        for invalid in (25,26,27,28,29,30,31):
            with self.assertRaisesRegex(ModError,'25–31'):
                apply(src,src,[24,invalid],**self.kw(src))
        for index in (0,1,2,3,4,5,6,7,8,9,10):
            damaged=bytearray(src)
            struct.pack_into('<I',damaged,AT+4*index,0xFFFFFFFF)
            with self.assertRaisesRegex(ModError,'sequência'):
                apply(src,bytes(damaged),[24],**self.kw(src))

    def test_inspect_partial_and_modified(self):
        orig=bytearray(fixture())
        self.assertEqual(inspect(orig)['status'],'nao_aplicado_0_de_3')
        struct.pack_into('<I',orig,AT+4*CHANGED[0],PATCHED[CHANGED[0]])
        self.assertEqual(inspect(orig)['status'],'parcial_1_de_3')
        struct.pack_into('<I',orig,AT+4*CHANGED[1],PATCHED[CHANGED[1]])
        self.assertEqual(inspect(orig)['status'],'parcial_2_de_3')
        struct.pack_into('<I',orig,AT+4*CHANGED[2],PATCHED[CHANGED[2]])
        self.assertEqual(inspect(orig)['status'],'aplicado_3_de_3')
        orig[AT+4*7]=255
        self.assertEqual(inspect(orig)['status'],'sequencia_divergente')
