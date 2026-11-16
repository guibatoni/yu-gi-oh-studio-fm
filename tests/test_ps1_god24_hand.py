"""Regressões da seleção do tipo God24 na mão do duelo."""
import hashlib
import struct
import unittest
from fmstudio.core import ModError
from fmstudio.ps1_god24_hand import SITES, apply, inspect


def fake():
    d = bytearray(0xE000)
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

    def test_real_slus_offsets_match_reported_ram_addresses(self):
        from fmstudio.tables import EXE_DELTA
        pc_list=(0x8001C214,0x8001C400,0x8001C9FC,0x8001CD34)
        offsets=(0xCA14,0xCC00,0xD1FC,0xD534)
        self.assertEqual(EXE_DELTA,0x8000F800)
        self.assertEqual(tuple(at for at,_,_ in SITES),offsets)
        for (offset,_,_),pc in zip(SITES,pc_list):
            self.assertEqual(pc-offset,EXE_DELTA)
        # Antigos offsets da v1.4.20 eram 0x800 bytes anteriores.
        self.assertEqual(tuple(pc-0x80010000 for pc in pc_list),
                         (0xC214,0xC400,0xC9FC,0xCD34))
        src=fake()
        self.assertEqual(inspect(src)['status'],'nao_aplicado_0_de_4')
        modified,report=apply(src,src,[24],**self.kwargs(src))
        self.assertEqual(report['status'],'aplicado_4_de_4')
        for offset,_,_ in SITES:
            self.assertEqual(src[offset-8:offset],modified[offset-8:offset])
            self.assertNotEqual(src[offset:offset+4],modified[offset:offset+4])
            # O patch não toca os offsets incorretos antigos.
            self.assertEqual(src[offset-0x800:offset-0x800+4],
                             modified[offset-0x800:offset-0x800+4])

    def test_real_build_order_chest_rows_and_hand_together(self):
        from fmstudio.ps1_god24_chest import (
            SITES as CHEST_SITES, patch_god24_chest_preview,
        )
        from fmstudio.ps1_god24_row_patch import (
            AT as ROW_AT, ORIGINAL as ROW_ORIGINAL, apply as patch_row, inspect as inspect_row,
        )
        original=bytearray(0x80000)
        original[:8]=b'PS-X EXE'
        for offset,context,_ in CHEST_SITES:
            struct.pack_into('<5I',original,offset-4,*context)
        struct.pack_into('<'+str(len(ROW_ORIGINAL))+'I',
                         original,ROW_AT,*ROW_ORIGINAL)
        for offset,context,_ in SITES:
            struct.pack_into('<5I',original,offset-8,*context)
        initial=bytes(original)
        opts=self.kwargs(initial)
        with_chest,_=patch_god24_chest_preview(initial,initial,[24],**opts)
        with_rows,_=patch_row(initial,with_chest,[24],**opts)
        final,report=apply(initial,with_rows,[24],**opts)
        self.assertEqual(report['status'],'aplicado_4_de_4')
        self.assertEqual(inspect_row(final)['status'],'aplicado_3_de_3')
        self.assertEqual(inspect(final)['status'],'aplicado_4_de_4')
        self.assertEqual(initial,bytes(original))
        # A sequência de alterações no BIN não deve anular o patch do baú.
        for offset,_,_ in CHEST_SITES:
            self.assertEqual(final[offset:offset+4],with_rows[offset:offset+4])

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
            with self.assertRaisesRegex(ModError,"sequência MIPS"):
                apply(src,bytes(b),[24],**self.kwargs(src))
        partial=bytearray(src)
        struct.pack_into("<I",partial,SITES[0][0],
                         (SITES[0][1][2] & 0xFFFF0000) | 0x17)
        self.assertEqual(inspect(partial)["status"],"parcial_1_de_4")
        with self.assertRaisesRegex(ModError,"sequência MIPS"):
            apply(src,bytes(partial),[24],**self.kwargs(src))


if __name__=="__main__":
    unittest.main()
