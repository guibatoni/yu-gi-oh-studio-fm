"""Não é um teste em ePSXe: apenas integridade de bytes e construção MIPS."""
import hashlib
import struct
import unittest
from fmstudio.core import ModError
from fmstudio.tables import EXE_DELTA
from fmstudio.ps1_god24_hook import (
    god24_hook_words,probe_god24_hook,patch_god24_hook,
    SITE_OFFSET,ORIGINAL_JAL,ORIGINAL_DELAY,WINDOW_START,WINDOW_SIZE,
)


def fixture():
    exe=bytearray(0x59000)
    exe[:8]=b'PS-X EXE'
    struct.pack_into('<II',exe,0x18,EXE_DELTA+0x800,0x50000)
    struct.pack_into('<II',exe,SITE_OFFSET,ORIGINAL_JAL,ORIGINAL_DELAY)
    cave=0x48000
    return bytes(exe),cave


class God24HookTests(unittest.TestCase):
    def kwargs(self,exe):
        return {'source_sha256':hashlib.sha256(exe).hexdigest(),
                'window_sha256':hashlib.sha256(
                    exe[WINDOW_START:WINDOW_START+WINDOW_SIZE]).hexdigest()}

    def test_wrapper_only_changes_kind_zero_id_24(self):
        words=god24_hook_words(0x27)
        self.assertEqual(len(words),19)
        self.assertEqual(words[17],0x0800DB05)
        self.assertEqual(words[18],0)
        # Todos os branches convergem para o jump de retorno em i=17.
        for i in (1,9,14):
            displacement=words[i]&0xffff
            self.assertEqual(i+1+displacement,17)
        self.assertEqual(words[16]&0xffff,0x27)
        self.assertEqual(words[11]&0xffff,0xffff) # stream byte anterior
        with self.assertRaises(ModError):
            god24_hook_words(0x26)

    def test_no_write_without_external_cave_confirmation(self):
        original,cave=fixture()
        before=original
        state=probe_god24_hook(original,0x29,cave,**self.kwargs(original))
        self.assertEqual(state['status'],'candidato_zero_nao_comprovado_livre')
        with self.assertRaisesRegex(ModError,'auditoria independente'):
            patch_god24_hook(original,0x29,cave,**self.kwargs(original))
        self.assertEqual(before,original)

    def test_patch_only_changes_exact_callsite_and_explicit_cave(self):
        original,cave=fixture()
        kwargs=self.kwargs(original)
        changed,report=patch_god24_hook(
            original,0x2A,cave,auditoria_externa_confirmada=True,**kwargs)
        self.assertTrue(report['aplicado'])
        self.assertTrue(report['delay_slot_preservado'])
        self.assertNotEqual(changed,original)
        self.assertEqual(changed[SITE_OFFSET+4:SITE_OFFSET+8],
                         original[SITE_OFFSET+4:SITE_OFFSET+8])
        allowed=set(range(SITE_OFFSET,SITE_OFFSET+4))|set(range(cave,cave+76))
        self.assertTrue(all(a==b for i,(a,b) in enumerate(zip(original,changed))
                            if i not in allowed))
        with self.assertRaises(ModError):
            patch_god24_hook(original,0x29,cave,source_sha256='0'*64,window_sha256=kwargs['window_sha256'],
                             auditoria_externa_confirmada=True)

    def test_occupied_cave_and_modified_jal_rejected(self):
        original,cave=fixture()
        data=bytearray(original)
        data[cave]=0xff
        modified=bytes(data)
        result=probe_god24_hook(modified,0x2A,cave,**self.kwargs(modified))
        self.assertEqual(result['status'],'incompativel')
        data=bytearray(original)
        struct.pack_into('<I',data,SITE_OFFSET,0)
        modified=bytes(data)
        result=probe_god24_hook(modified,0x2A,cave,**self.kwargs(modified))
        self.assertIn('JAL',result['motivo'])

    def test_invalid_header_and_no_cave(self):
        orig,cave=fixture()
        self.assertEqual(probe_god24_hook(b'invalid',0x27)['status'],'incompativel')
        report=probe_god24_hook(orig,0x27,**self.kwargs(orig))
        self.assertEqual(report['status'],'assinatura_confirmada_sem_cave_aprovado')
        self.assertFalse(report['aplicado'])


if __name__=='__main__':
    unittest.main()
