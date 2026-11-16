"""Testes sintéticos MIPS para God24 no baú, não equivalem a ePSXe."""
import hashlib
import struct
import unittest
from fmstudio.core import ModError
from fmstudio.ps1_god24_chest import OLD,NEW,SITES,visible_as_monster,patch_god24_chest_preview


def fixture():
    exe=bytearray(0x80000)
    exe[:8]=b'PS-X EXE'
    for offset,context,_ in SITES:
        struct.pack_into('<5I',exe,offset-4,*context)
    return bytes(exe)


class God24ChestPreviewTests(unittest.TestCase):
    def kwargs(self,data):
        return {'source_sha256':hashlib.sha256(data).hexdigest()}

    def test_patches_exactly_two_words(self):
        source=fixture()
        output,report=patch_god24_chest_preview(
            source,source,[0,1,16,19,20,21,22,23,24],**self.kwargs(source))
        self.assertEqual(report['status'],'mascaras_bau_gravadas_pendente_epsxe')
        self.assertEqual(len(report['pontos']),2)
        self.assertFalse(report['combate_alterado'])
        changed=set()
        for offset,context,_ in SITES:
            self.assertEqual(struct.unpack_from('<I',source,offset)[0],OLD)
            self.assertEqual(struct.unpack_from('<I',output,offset)[0],NEW)
            self.assertEqual(struct.unpack_from('<I',output,offset+4)[0],context[2])
            changed.update(range(offset,offset+4))
        self.assertEqual(sum(a!=b for a,b in zip(source,output)),2)
        self.assertTrue(all(a==b for i,(a,b) in enumerate(zip(source,output))
                            if i not in changed))

    def test_monster_classes_preserved_and_god_accepted(self):
        for kind in range(25):
            new=visible_as_monster(kind,preview=True)
            self.assertEqual(new,kind<20 or kind==24)
            if kind<24:
                self.assertEqual(new,visible_as_monster(kind))
        for kind in (25,26,27,28,29,30,31):
            with self.assertRaises(ModError):
                patch_god24_chest_preview(fixture(),fixture(),[24,kind],
                                           **self.kwargs(fixture()))

    def test_wrong_hash_and_context_refused(self):
        original=fixture()
        with self.assertRaisesRegex(ModError,'SHA'):
            patch_god24_chest_preview(original,original,[24])
        for offset,_,_ in SITES:
            modified=bytearray(original)
            struct.pack_into('<I',modified,offset,0x30420014)
            with self.assertRaisesRegex(ModError,'assinatura'):
                patch_god24_chest_preview(original,bytes(modified),[24],
                                           **self.kwargs(original))
        with self.assertRaisesRegex(ModError,'não há cartas'):
            patch_god24_chest_preview(original,original,[1,19,20],
                                       **self.kwargs(original))

    def test_actual_build_deck_renderer_scan(self):
        from fmstudio.ps1_god24_chest import (
            BUILD_DECK_ROW_RENDER_RAM, BUILD_DECK_ROW_RENDER_SIZE,
            audit_god24_build_deck_rows,
        )
        from fmstudio.tables import EXE_DELTA
        image=bytearray(0x59000)
        image[:8]=b'PS-X EXE'
        struct.pack_into('<II',image,0x18,EXE_DELTA+0x800,0x50000)
        start=BUILD_DECK_ROW_RENDER_RAM-EXE_DELTA
        # lbu v1,2(t0); sltiu v0,v1,20; beq v0,zero,+3.
        sequence=(0x91030002,0x2C620014,0x10400003,0x00000000)
        struct.pack_into('<4I',image,start+0x80,*sequence)
        original=bytes(image)
        report=audit_god24_build_deck_rows(original)
        self.assertEqual(report['status'],'analisado_sem_hook')
        self.assertEqual(report['total_comparacoes_imediato_20'],1)
        self.assertTrue(report['v1415_mascaras_nao_cobrem_esta_funcao'])
        entry=report['potenciais_comparacoes_tipo_20'][0]
        self.assertEqual(entry['offset_slus'],f'0x{start+0x84:X}')
        self.assertTrue(any(c.get('offset_lbu')==2 for c in entry['contexto']))
        self.assertTrue(any(c.get('delay_slot_na_proxima_instrucao')
                            for c in entry['contexto']))
        self.assertEqual(original,bytes(image))
        self.assertEqual(len(report['sha256_regiao']),64)

    def test_actual_renderer_invalid_header_does_not_write(self):
        from fmstudio.ps1_god24_chest import audit_god24_build_deck_rows
        self.assertEqual(audit_god24_build_deck_rows(b'invalid')['status'],
                         'arquivo_invalido')
        self.assertEqual(audit_god24_build_deck_rows(fixture())['status'],
                         'funcao_fora_do_segmento')


    def test_other_stats_retained(self):
        original=fixture()
        data=bytearray(original)
        data[0x12000:0x12004]=b'\x45\x67\x89\xab'
        new,_=patch_god24_chest_preview(original,bytes(data),[24],
                                         **self.kwargs(original))
        self.assertEqual(new[0x12000:0x12004],b'\x45\x67\x89\xab')
        self.assertEqual(original[0x12000:0x12004],b'\0'*4)
