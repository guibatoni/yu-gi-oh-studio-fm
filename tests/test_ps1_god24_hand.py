"""Regressões da seleção do tipo God24 na mão do duelo."""
import hashlib
import struct
import unittest
from fmstudio.core import ModError
from fmstudio.ps1_god24_hand import SITES, apply, inspect


def fake():
    d = bytearray(0xD200)
    d[:8] = b"PS-X EXE"
    for at, context, _ in SITES:
        struct.pack_into("<5I", d, at - 8, *context)
    return bytes(d)


class GodHandTests(unittest.TestCase):
    def kwargs(self, d):
        return {"source_sha256": hashlib.sha256(d).hexdigest()}

    def test_four_sites_no_unrelated_changes(self):
        before = fake()
        after, report = apply(before, before, range(25), **self.kwargs(before))
        self.assertEqual(report["status"], "aplicado_4_de_4")
        self.assertEqual(inspect(after)["status"], "aplicado_4_de_4")
        allowed = set()
        for at, context, _ in SITES:
            allowed.update(range(at, at+4))
            words = struct.unpack_from("<5I", after, at - 8)
            self.assertEqual(words[0:2], context[0:2])
            self.assertEqual(words[2], (context[2] & 0xFFFF0000) | 0x17)
            self.assertEqual(words[3:], context[3:])
        self.assertTrue(all(a==b for i,(a,b) in enumerate(zip(before,after))
                            if i not in allowed))
        self.assertEqual(before, fake())
        self.assertFalse(report["invocacao_confirmada_no_epsxe"])

    def test_original_types_and_god_only(self):
        for n in range(25):
            normalized=n & 0x17
            if n in (20,21,22,23):
                self.assertEqual(normalized,n)
            elif n==24:
                self.assertEqual(normalized,16)
            elif 8<=n<=15:
                self.assertEqual(normalized,n-8)
            else:
                self.assertEqual(normalized,n)
            self.assertEqual(normalized<20,n<20 or n==24)

    def test_suspicious_and_partial_images_fail_closed(self):
        src = fake()
        with self.assertRaisesRegex(ModError,"SHA"):
            apply(src,src,[24])
        for bad_kind in (25,26,27,28,29,30,31):
            with self.assertRaisesRegex(ModError,"25–31"):
                apply(src,src,[24,bad_kind],**self.kwargs(src))
        for offset,_,_ in SITES:
            b=bytearray(src)
            struct.pack_into("<I",b,offset,0xFFFFFFFF)
            self.assertEqual(inspect(b)["status"],"sequencia_divergente")
            with self.assertRaisesRegex(ModError,"janela MIPS"):
                apply(src,bytes(b),[24],**self.kwargs(src))
        partial=bytearray(src)
        struct.pack_into("<I",partial,SITES[0][0],
                         (SITES[0][1][2] & 0xFFFF0000) | 0x17)
        self.assertEqual(inspect(partial)["status"],"parcial_1_de_4")
        with self.assertRaisesRegex(ModError,"janela MIPS"):
            apply(src,bytes(partial),[24],**self.kwargs(src))


if __name__=="__main__":
    unittest.main()
