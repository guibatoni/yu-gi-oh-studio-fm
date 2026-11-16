"""Tests for read-only God24 duel-routing analysis."""
import hashlib
import struct
import unittest

from fmstudio.ps1_god24_duel import REGIONS, analyze_god24_duel
from fmstudio.tables import EXE_DELTA


def fixture():
    exe = bytearray(0x78000)
    exe[:8] = b"PS-X EXE"
    struct.pack_into("<II", exe, 0x18, EXE_DELTA + 0x800, 0x70000)
    return exe


class DuelRoutingTests(unittest.TestCase):
    def test_reads_hand_threshold_and_branch_without_modifying_bytes(self):
        exe = fixture()
        _,ram,_ = REGIONS["mao"]
        at = ram - EXE_DELTA + 0x88
        struct.pack_into("<5I",exe,at,
                         0x00021782,0x3042001F,0x2C420014,
                         0x10400002,0x02002021)
        initial = bytes(exe)
        report = analyze_god24_duel(initial)
        self.assertEqual(report["status"],"somente_leitura")
        hand = report["rotinas"]["mao"]
        self.assertTrue(any(x["categoria"]=="limite_monstro"
                            for x in hand["amostras"]))
        self.assertTrue(any(x["categoria"]=="mascara_tipo_5_bits"
                            for x in hand["amostras"]))
        threshold = next(x for x in hand["amostras"]
                         if x["categoria"]=="limite_monstro")
        self.assertTrue(any(i.get("delay_slot") for i in threshold["contexto_mips"]))
        self.assertEqual(report["sha256_slus"],hashlib.sha256(initial).hexdigest())
        self.assertFalse(report["patch_mips_duelo_aplicado"])
        self.assertEqual(bytes(exe),initial)

    def test_keeps_spell_types_outside_monster_classification(self):
        report=analyze_god24_duel(bytes(fixture()))
        self.assertFalse(report["tipo_24_tratado_como_monstro_no_motor_retail"])
        self.assertIn("20 para 25",report["alerta"])
        self.assertEqual(len(report["rotinas"]),len(REGIONS))

    def test_invalid_headers_and_code_bounds(self):
        self.assertEqual(analyze_god24_duel(b"broken")["status"],"slus_invalido")
        data=fixture()
        struct.pack_into("<II",data,0x18,EXE_DELTA+0x800,0xFFFFFFFC)
        self.assertEqual(analyze_god24_duel(bytes(data))["status"],"segmento_invalido")
        data=fixture()
        struct.pack_into("<II",data,0x18,EXE_DELTA+0x800,0x1000)
        report=analyze_god24_duel(bytes(data))
        self.assertTrue(all(x["status"]=="fora_segmento"
                            for x in report["rotinas"].values()))

    def test_caps_sample_count_without_hiding_totals(self):
        data=fixture()
        _,ram,_=REGIONS["uso_carta_especial"]
        at=ram-EXE_DELTA
        for i in range(8):
            struct.pack_into("<I",data,at+4*i,0x2C420014)
        out=analyze_god24_duel(bytes(data),maximum_per_region=2)
        section=out["rotinas"]["uso_carta_especial"]
        self.assertEqual(section["encontrados"],8)
        self.assertEqual(len(section["amostras"]),2)
        self.assertTrue(section["truncado"])


if __name__=="__main__":
    unittest.main()
