"""Regressão da conversão PS1 real: index, RGB555, CLUT, miniatura e fallback."""
from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fmstudio.core import ModError
from fmstudio.png_pixels import read_png
from fmstudio.ps1_content import patch_card_art, render_card_art
from fmstudio.ps1_image_optimizer import (
    ART_SIZE, THUMB_SIZE, ImageOptions, clut_words, pack_rgb555, png_rgba,
    render_card, render_resource, rgba_from_indices, rgb555,
)
from fmstudio.deep_extract import _indexed_png_bytes, _colors


def png(path, size, pixels):
    path.write_bytes(png_rgba(bytes(pixels), size))
    return path


def records():
    art = bytearray(7 * 2048)
    thumb = bytearray(2048)
    for a in (art, thumb):
        if len(a) > 0x2840:
            a[0x2840:0x2AE0] = b'\x03' * (0x2AE0 - 0x2840)
    words = [0, 31, 31 << 5, 31 << 10, pack_rgb555(255, 193, 20),
             1, 0x7FFF, 0x8000]
    for i, value in enumerate(words):
        struct.pack_into('<H', art, 0x2640 + 2*i, value)
        struct.pack_into('<H', thumb, 0x500 + 2*i, value)
    return bytes(art), bytes(thumb)


def sample_colors(size=(102,96)):
    w,h=size
    p=bytearray()
    colors=((255,0,0,255), (0,255,0,255), (0,0,255,255), (255,193,20,255))
    for y in range(h):
        for x in range(w):
            p.extend(colors[(y>=h//2)*2+(x>=w//2)])
    return bytes(p)


class PS1ImagePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.png = png(self.folder/'card.png',ART_SIZE,sample_colors())
        self.art,self.thumb=records()

    def test_bgr555_primary_colors_and_stp_bit(self):
        self.assertEqual(rgb555(31), (255,0,0,255))
        self.assertEqual(rgb555(31 << 5), (0,255,0,255))
        self.assertEqual(rgb555(31 << 10), (0,0,255,255))
        self.assertEqual(rgb555(0), (0,0,0,0))
        self.assertEqual(rgb555(0x8000), (0,0,0,255))
        self.assertEqual(pack_rgb555(255,0,0), 31)

    def test_real_preview_decodes_exactly_as_exported_ps1(self):
        result=render_card(self.png,self.art,self.thumb,
                           {'mode':'automatico','dither':'nenhum'})
        self.assertEqual(result.art.size,ART_SIZE)
        self.assertEqual(result.thumbnail.size,THUMB_SIZE)
        for part in (result.art,result.thumbnail):
            self.assertEqual(len(part.indices), part.size[0]*part.size[1])
            self.assertEqual(part.preview_rgba,
                             rgba_from_indices(part.indices,part.clut))
            image=_indexed_png_bytes(part.indices,0,part.size[0]//2,
                                     part.size[1],[bytes(rgb555(v)) for v in part.clut])
            out=self.folder/'extracted.png'
            out.write_bytes(image)
            w,h,rgba=read_png(out)
            self.assertEqual((w,h),part.size)
            self.assertEqual(rgba,part.preview_rgba)

    def test_palette_remains_bitwise_unchanged_on_original_card(self):
        wa=bytearray((722+7)*2048)
        art_off=722*2048
        wa[art_off:art_off+len(self.art)]=self.art
        wa[:len(self.thumb)]=self.thumb
        before=bytes(wa)
        changed,regions=patch_card_art(before,1,self.png,
              options={'mode':'automatico','dither':'bayer4','palette':'personalizada'})
        self.assertEqual([r['regiao'] for r in regions],['arte','miniatura'])
        self.assertEqual(changed[art_off+0x2640:art_off+0x2840],
                         before[art_off+0x2640:art_off+0x2840])
        self.assertEqual(changed[0x500:0x580],before[0x500:0x580])
        self.assertEqual(changed[art_off+0x2840:],before[art_off+0x2840:])
        self.assertEqual(changed[1280:art_off],before[1280:art_off])
        self.assertTrue(any('bloqueada' in w for w in regions[0]['otimizacao']['avisos']))

    def test_red_green_blue_gold_are_mapped_to_local_palette(self):
        result=render_card(self.png,self.art,self.thumb,
                           {'mode':'automatico','dither':'nenhum'})
        art=result.art.indices
        self.assertEqual(art[0],1)
        self.assertEqual(art[101],2)
        self.assertEqual(art[95*102],3)
        self.assertEqual(art[-1],4)
        self.assertEqual(len(set(art)),4)

    def test_proportion_preserved_and_no_cropping_in_auto(self):
        wide=png(self.folder/'wide.png',(80,20),bytes((255,0,0,255))*1600)
        result=render_card(wide,self.art,self.thumb,
                           {'mode':'automatico','dither':'nenhum'})
        w,h=ART_SIZE
        self.assertEqual(result.art.indices[0],0)
        self.assertEqual(result.art.indices[(h//2)*w+(w//2)],1)
        self.assertTrue(any(result.art.indices[y*w] == 0 for y in range(h//4)))

    def test_original_compatibility_does_not_add_letterboxing(self):
        wide=png(self.folder/'wide.png',(80,20),bytes((255,0,0,255))*1600)
        rendered=render_card(wide,self.art,self.thumb)
        self.assertEqual(set(rendered.art.indices),{1})

    def test_alpha_is_preserved_when_index_zero_is_transparent(self):
        rgba=bytes((255,0,0,0))*100 + bytes((0,255,0,255))*(102*96-100)
        path=png(self.folder/'transparent.png',ART_SIZE,rgba)
        result=render_card(path,self.art,self.thumb,{'dither':'nenhum'})
        self.assertEqual(result.art.indices[0],0)
        self.assertEqual(result.art.preview_rgba[:4],b'\0'*4)
        self.assertEqual(result.art.indices[-1],2)

    def test_opaque_zero_clut_rejects_fake_transparency(self):
        altered=bytearray(self.art)
        struct.pack_into('<H', altered, 0x2640, 0x8000)
        p=png(self.folder/'transparent.png',ART_SIZE,
              bytes((255,0,0,0))*(102*96))
        with self.assertRaisesRegex(ModError,'índice zero'):
            render_card(p, bytes(altered), self.thumb, {'mode':'automatico'})

    def test_dithering_algorithms_have_correct_dimensions(self):
        gray=png(self.folder/'gray.png',ART_SIZE,
                 bytes((135,135,135,255))*(102*96))
        for algo in ('nenhum','floyd','bayer2','bayer4','bayer8','automatico'):
            with self.subTest(method=algo):
                output=render_card(gray,self.art,self.thumb,
                                  {'dither':algo,'intensity':.85})
                self.assertEqual(len(output.art.indices),9792)
                self.assertLessEqual(max(output.art.indices),255)

    def test_no_pillow_uses_safe_png_decoder_and_area_scaling(self):
        with patch.dict(sys.modules, {'PIL':None}):
            result=render_card(self.png,self.art,self.thumb,
                                {'mode':'automatico','dither':'bayer2'})
            self.assertFalse(result.art.report['pillow'])
            self.assertEqual(len(result.art.indices),102*96)
            self.assertEqual(len(result.thumbnail.indices),40*32)
            self.assertTrue(any('Pillow ausente' in w for w in result.art.report['avisos']))

    def test_private_clut_only_allowed_for_explicitly_isolated_resource(self):
        try:
            import PIL
        except ImportError:
            self.skipTest("Pillow não disponível")
        original=clut_words(self.art,0x2640,256)
        allowed=render_resource(self.png,original,ART_SIZE,
                                {'mode':'automatico','palette':'personalizada'},
                                private_clut=True)
        self.assertEqual(allowed.report['paleta'],'privada_adaptativa')
        self.assertNotEqual(allowed.clut,original)
        blocked=render_resource(self.png,original,ART_SIZE,
                                {'mode':'automatico','palette':'personalizada'},
                                private_clut=False)
        self.assertEqual(blocked.clut,original)
        self.assertEqual(blocked.report['paleta'],'original_preservada')

    def test_invalid_configuration_fails_without_mutating_image(self):
        for config in ({'intensity':5}, {'resample':'unknown'},
                       {'brightness':2}, {'mode':'arbitrario'}):
            with self.assertRaises(ModError):
                render_card(self.png,self.art,self.thumb,config)
        self.assertEqual(read_png(self.png)[2],sample_colors())


if __name__ == '__main__':
    unittest.main()
