"""Testes locais, sem depender de um disco comercial ou ePSXe."""
import struct
import tempfile
import unittest
from pathlib import Path

from fmstudio.core import ModError
from fmstudio.ps1_god_icon import (
    ICON_PALETTE_SECTOR, PALETTE_OFFSET, ICON_SHEET_SECTOR,
    GLYPH_U, GLYPH_V, TOKEN_BYTES, glyph_rows,
    patch_god_glyph, patch_god_icon_description, god_icon_asset,
)
from fmstudio.deep_extract import exe_pos, BANK_DESC, STRING_TABLE


class GodIconNativeTests(unittest.TestCase):
    def fixture_wa(self):
        wa = bytearray((ICON_PALETTE_SECTOR + 2) * 2048)
        # Uma linha CLUT retail sintética: transparente + 15 cores.
        for i in range(1,16):
            struct.pack_into('<H',wa,PALETTE_OFFSET+2*i,0x8000|i*0x421)
        return bytes(wa)

    def fixture_exe(self):
        exe = bytearray(1902592)
        exe[:8] = b'PS-X EXE'
        ptr = exe_pos(STRING_TABLE,exe,0x400*2)
        struct.pack_into('<H',exe,ptr+(0x100+16)*2,0x120)
        desc=exe_pos(BANK_DESC+0x120,exe,13)
        exe[desc:desc+13]=b'TIME WIZARD!\xff'
        return bytes(exe),desc

    def test_god_glyph_only_uses_empty_eight_byte_rows(self):
        source=self.fixture_wa()
        path=god_icon_asset()
        self.assertTrue(path.is_file())
        changed,info=patch_god_glyph(source,path)
        self.assertEqual(info['status'],'glifo_inserido_em_celula_vazia')
        self.assertEqual(len(changed),len(source))
        self.assertNotEqual(glyph_rows(source),glyph_rows(changed))
        self.assertTrue(any(any(row) for row in glyph_rows(changed)))
        again,skipped=patch_god_glyph(changed,path)
        self.assertEqual(again,changed)
        self.assertEqual(skipped['status'],'ja_presente')
        self.assertEqual(source[PALETTE_OFFSET:PALETTE_OFFSET+32],
                         changed[PALETTE_OFFSET:PALETTE_OFFSET+32])
        offsets=set()
        for y in range(16):
            base=ICON_SHEET_SECTOR*2048+(GLYPH_V+y)*128+GLYPH_U//2
            offsets.update(range(base,base+8))
        self.assertTrue(all(a==b for pos,(a,b) in enumerate(zip(source,changed))
                            if pos not in offsets))

    def test_refuse_occupied_slot_and_blank_palette(self):
        wa=bytearray(self.fixture_wa())
        pos=ICON_SHEET_SECTOR*2048+GLYPH_V*128+GLYPH_U//2
        wa[pos]=0xF0
        with self.assertRaisesRegex(ModError,'não está vazia'):
            patch_god_glyph(bytes(wa),god_icon_asset())
        blank=bytearray(self.fixture_wa())
        blank[PALETTE_OFFSET:PALETTE_OFFSET+32]=b'\0'*32
        with self.assertRaisesRegex(ModError,'Paleta'):
            patch_god_glyph(bytes(blank),god_icon_asset())

    def test_description_patch_keeps_all_but_three_bytes(self):
        source,at=self.fixture_exe()
        result,info=patch_god_icon_description(source,16)
        self.assertEqual(info['status'],'icone_inserido_no_texto_do_card')
        self.assertEqual(result[at:at+3],TOKEN_BYTES)
        self.assertEqual(result[:at],source[:at])
        self.assertEqual(result[at+3:],source[at+3:])
        self.assertEqual(source[at:at+3],b'TIM')
        same,info2=patch_god_icon_description(result,16)
        self.assertEqual(same,result)
        self.assertEqual(info2['status'],'ja_presente')

    def test_reject_shared_description_and_special_header(self):
        exe,at=self.fixture_exe()
        shared=bytearray(exe)
        ptr=exe_pos(STRING_TABLE,shared,0x400*2)
        struct.pack_into('<H',shared,ptr+(0x100+17)*2,0x120)
        with self.assertRaisesRegex(ModError,'exclusivo'):
            patch_god_icon_description(bytes(shared),16)
        special=bytearray(exe)
        special[at]=0xF8
        with self.assertRaisesRegex(ModError,'controles'):
            patch_god_icon_description(bytes(special),16)
        for n in (0,723,-1,True,'16'):
            with self.assertRaises(ModError):
                patch_god_icon_description(exe,n)


if __name__=='__main__':
    unittest.main()
