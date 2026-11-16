"""Regressões da classificação de God24 no fluxo de duelo."""

import hashlib
import struct
import unittest

from fmstudio.core import ModError
from fmstudio.ps1_god24_hand import apply as apply_legacy_hand
from fmstudio.ps1_god24_play import SITES, apply, inspect
from fmstudio.tables import EXE_DELTA


def origin():
    exe = bytearray(0xE000)
    exe[:8] = b'PS-X EXE'
    struct.pack_into('<II', exe, 0x18, EXE_DELTA + 0x800, len(exe) - 0x800)
    for site in SITES:
        struct.pack_into(f'<{len(site.original)}I', exe, site.offset, *site.original)
    return bytes(exe)


def run_comparison(words, kind, high_bit):
    """Executa os opcodes da janela até a decisão do desvio, com load delay."""
    registers = [0] * 32
    pending = None
    mask32 = 0xFFFFFFFF
    for word in words[:-2]:
        op, rs, rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
        rd, shift, func = (word >> 11) & 31, (word >> 6) & 31, word & 63
        immediate = word & 0xFFFF
        source, target = registers[rs], registers[rt]
        next_load = None
        if pending is not None:
            register, value = pending
            registers[register] = value
        if op == 35:  # lw do registro numérico da carta
            next_load = (rt, high_bit | kind << 26 | 0x034567)
        elif op == 36:  # lbu do tipo já extraído
            next_load = (rt, kind)
        elif op == 13:  # ori
            registers[rt] = source | immediate
        elif op == 12:  # andi
            registers[rt] = source & immediate
        elif op in (10, 11):  # slti ou sltiu
            registers[rt] = int(source < immediate)
        elif not word:  # nop
            pass
        elif op == 0 and func in (2, 3):  # srl ou sra
            if func == 3 and target & 0x80000000:
                target -= 1 << 32
            registers[rd] = (target >> shift) & mask32
        elif op == 0 and func == 4:  # sllv
            registers[rd] = target << (source & 31) & mask32
        else:
            raise AssertionError(f'Opcode inesperado 0x{word:08X}')
        pending = next_load
    branch = words[-2]
    source = registers[(branch >> 21) & 31]
    if branch >> 26 == 1:
        negative = bool(source & 0x80000000)
        taken = not negative if (branch >> 16) & 31 == 1 else negative
    else:
        taken = source == 0 if branch >> 26 == 4 else source != 0
    return taken, registers[16]


class GodPlayTests(unittest.TestCase):
    def test_only_god24_changes_branch_and_keeps_the_real_type(self):
        for site in SITES:
            self.assertEqual(site.replacement[-1], site.original[-1])
            self.assertEqual(site.replacement[-2] & 0xFFFF, site.original[-2] & 0xFFFF)
            for kind in range(32):
                for high_bit in (0, 0x80000000):
                    with self.subTest(site=site.offset, kind=kind, high_bit=high_bit):
                        original, old_s0 = run_comparison(site.original, kind, high_bit)
                        patched, new_s0 = run_comparison(site.replacement, kind, high_bit)
                        self.assertEqual(original != patched, kind == 24)
                        self.assertEqual(old_s0, new_s0)
                        if site.phase == 'mao' and site.offset != 0xCA08:
                            self.assertEqual(new_s0, kind)

    def test_export_confirms_all_three_phases_and_preserves_other_bytes(self):
        source = origin()
        digest = hashlib.sha256(source).hexdigest()
        edited = bytearray(source)
        edited[0x20] = 0x54
        patched, report = apply(source, edited, [1, 21, 23, 24], source_sha256=digest)
        self.assertEqual(report, inspect(patched))
        self.assertEqual(report['status'], 'aplicado')
        self.assertEqual(report['etapas'], {
            'mao': {'aplicados': 4, 'total': 4},
            'colocacao': {'aplicados': 7, 'total': 7},
            'confirmacao': {'aplicados': 2, 'total': 2},
        })
        self.assertFalse(report['validado_no_epsxe'])
        allowed = {site.offset + i for site in SITES for i in range(len(site.original) * 4)}
        for offset, (before, after) in enumerate(zip(edited, patched)):
            if before != after:
                self.assertIn(offset, allowed)

    def test_rejects_other_source_legacy_patches_and_incomplete_signatures(self):
        source = origin()
        digest = hashlib.sha256(source).hexdigest()
        with self.assertRaisesRegex(ModError, 'SHA-256'):
            apply(source, source, [24])
        without_god = [21, 23]
        with self.assertRaisesRegex(ModError, 'exige uma carta God24'):
            apply(source, source, without_god, source_sha256=digest)
        legacy, _ = apply_legacy_hand(source, source, [24], source_sha256=digest)
        with self.assertRaisesRegex(ModError, 'assinatura MIPS inesperada'):
            apply(source, legacy, [24], source_sha256=digest)
        corrupted = bytearray(source)
        placement = next(site for site in SITES if site.phase == 'colocacao')
        corrupted[placement.offset + 16] ^= 1
        self.assertEqual(inspect(corrupted)['status'], 'assinatura_divergente')
        with self.assertRaisesRegex(ModError, f'0x{placement.offset:X}'):
            apply(source, corrupted, [24], source_sha256=digest)
        truncated_code = bytearray(source)
        struct.pack_into('<I', truncated_code, 0x1C, 0x2000)
        self.assertEqual(inspect(truncated_code)['status'], 'assinatura_divergente')


if __name__ == '__main__':
    unittest.main()
