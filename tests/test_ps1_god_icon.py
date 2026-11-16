"""Testes locais, sem depender de um disco comercial ou ePSXe."""
import struct
import tempfile
import unittest
import zlib
from unittest.mock import patch
from pathlib import Path

from fmstudio.core import ModError
from fmstudio.ps1_god_icon import (
    ICON_PALETTE_SECTOR, PALETTE_OFFSET, ICON_SHEET_SECTOR,
    GLYPH_U, GLYPH_V, ROW_BYTES, TOKEN_BYTES, glyph_rows,
    patch_god_glyph, patch_god_icon_description, god_icon_asset, decode_god_png,
    FREE_SLOT_CANDIDATES, NoFreeGodIconSlot, icon_cell_start, try_patch_god_icon,
)
from fmstudio.deep_extract import exe_pos, BANK_DESC, STRING_TABLE
from fmstudio.ps1_god24_display import GOLD_PALETTE, ICON_ROWS
from fmstudio.ps1_text import ICON_CODES, patch_descriptions, patch_icons


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

    def test_real_png_without_pillow(self):
        with patch.dict('sys.modules',{'PIL':None,'PIL.Image':None}):
            pixels=decode_god_png(god_icon_asset())
            self.assertEqual(len(pixels),256)
            self.assertTrue(any(pixel[3]>=128 for pixel in pixels))
            output,report=patch_god_glyph(self.fixture_wa(),god_icon_asset())
            self.assertEqual(report['status'],'glifo_inserido_em_celula_vazia')
            self.assertTrue(any(any(r) for r in glyph_rows(output)))

    def test_all_description_icons_export_without_pillow(self):
        exe, _ = self.fixture_exe()
        wa = bytearray(self.fixture_wa())
        wa[GOLD_PALETTE:GOLD_PALETTE+32] = wa[PALETTE_OFFSET:PALETTE_OFFSET+32]
        edited = ''.join(f'{{icon:{name}}}' for name in ICON_CODES)
        with patch.dict('sys.modules', {'PIL': None, 'PIL.Image': None}):
            slus, rows, icons, pending = patch_descriptions(exe, {16: edited}, {})
            self.assertFalse(pending)
            expected = b''.join(bytes((0xF8, 0x0B, code)) for code in ICON_CODES.values()) + b'\xff'
            offset = rows[0]['offset_exe']
            self.assertEqual(slus[offset:offset+len(expected)], expected)
            self.assertEqual(icons, set(ICON_CODES))
            output = patch_icons(wa, icons)
            self.assertEqual(len(output), len(wa))
            self.assertEqual(patch_icons(output, icons), output)
        for name, code in ICON_CODES.items():
            first = ICON_ROWS[0] if name == 'god' else ICON_ROWS[0] + (code - 0x40 + 1) * 8
            self.assertTrue(any(any(output[start:start+8])
                                for start in range(first, first+16*ROW_BYTES, ROW_BYTES)), name)

    def test_reject_corrupted_or_truncated_png(self):
        original=god_icon_asset().read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'god.png'
            source.write_bytes(original[:-5])
            with self.assertRaisesRegex(ModError,'PNG'):
                decode_god_png(source)
            bad=bytearray(original)
            bad[45]^=1
            source.write_bytes(bad)
            with self.assertRaisesRegex(ModError,'CRC|PNG'):
                decode_god_png(source)
            source.write_bytes(b'not a png')
            with self.assertRaisesRegex(ModError,'PNG'):
                decode_god_png(source)

    def test_rgba_png_filters_0_to_4(self):
        line=bytes((n*7%256 for n in range(64)))
        def chunk(name,payload):
            return (struct.pack('>I',len(payload))+name+payload+
                    struct.pack('>I',zlib.crc32(name+payload)&0xffffffff))
        for method in range(5):
            prev=bytes(64)
            rows=[]
            for _ in range(16):
                encoded=bytearray()
                for i,byte in enumerate(line):
                    left=line[i-4] if i>=4 else 0
                    top=prev[i]
                    upper=prev[i-4] if i>=4 else 0
                    if method==0:pred=0
                    elif method==1:pred=left
                    elif method==2:pred=top
                    elif method==3:pred=(left+top)//2
                    else:
                        p=left+top-upper
                        dl,dt,du=abs(p-left),abs(p-top),abs(p-upper)
                        pred=left if dl<=dt and dl<=du else top if dt<=du else upper
                    encoded.append((byte-pred)&255)
                rows.append(bytes([method])+bytes(encoded))
                prev=line
            ihdr=struct.pack('>IIBBBBB',16,16,8,6,0,0,0)
            png=(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',ihdr)
                 +chunk(b'IDAT',zlib.compress(b''.join(rows)))
                 +chunk(b'IEND',b''))
            with tempfile.TemporaryDirectory() as tmp:
                file=Path(tmp)/'filtered.png'
                file.write_bytes(png)
                result=decode_god_png(file)
                self.assertEqual(result[:16],
                                 [tuple(line[i:i+4]) for i in range(0,64,4)])

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

    def test_occupied_29_uses_blank_alternative_and_preserves_mod_pixels(self):
        original=bytearray(self.fixture_wa())
        original[icon_cell_start(0x29)]=0xF0
        baseline=bytes(original)
        modified,info=patch_god_glyph(baseline,god_icon_asset())
        self.assertEqual(info['slot'],0x27)
        self.assertEqual(info['codigo'],'F8 0B 27')
        self.assertEqual(glyph_rows(baseline,0x29),glyph_rows(modified,0x29))
        self.assertNotEqual(glyph_rows(modified,0x27),glyph_rows(baseline,0x27))
        self.assertEqual(len(baseline),len(modified))
        self.assertEqual(modified[icon_cell_start(0x29)],0xF0)

    def test_no_free_slot_reports_and_keeps_icon_and_description_unchanged(self):
        wa=bytearray(self.fixture_wa())
        for slot in FREE_SLOT_CANDIDATES:
            wa[icon_cell_start(slot)]=0xF0
        original=bytes(wa)
        with self.assertRaises(NoFreeGodIconSlot):
            patch_god_glyph(original,god_icon_asset())
        exe,_=self.fixture_exe()
        output_wa,output_exe,report=try_patch_god_icon(
            original,exe,16,god_icon_asset())
        self.assertEqual(report['status'],'icone_nao_inserido_sem_espaco_livre')
        self.assertEqual(output_wa,original)
        self.assertEqual(output_exe,exe)

    def test_dynamic_slot_is_written_to_the_correct_description_token(self):
        wa=bytearray(self.fixture_wa())
        wa[icon_cell_start(0x29)]=0x12
        exe,desc=self.fixture_exe()
        result_wa,result_exe,report=try_patch_god_icon(
            bytes(wa),exe,16,god_icon_asset())
        self.assertEqual(report['glifo']['slot'],0x27)
        self.assertEqual(result_exe[desc:desc+3],bytes((0xF8,0x0B,0x27)))
        self.assertEqual(result_exe[:desc],exe[:desc])
        self.assertEqual(result_exe[desc+3:],exe[desc+3:])
        self.assertEqual(glyph_rows(bytes(wa),0x29),glyph_rows(result_wa,0x29))

    def test_reject_unmapped_slots(self):
        wa=self.fixture_wa()
        for code in (0x26,0x31,0xFF,-1,True):
            with self.assertRaises(ModError):
                glyph_rows(wa,code)
        exe,_=self.fixture_exe()
        with self.assertRaises(ModError):
            patch_god_icon_description(exe,16,0x31)

    def test_refuse_occupied_slot_and_blank_palette(self):
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
