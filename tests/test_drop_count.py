"""Cartas por vitória (1 a 100) no código residente do Drop x15."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from fmstudio import ps1_drop_count as drops
from fmstudio.core import ModError, Project
from fmstudio.deep_extract import exe_pos
from fmstudio.ps1_campaign_quests import DROP15_CODE, DROP15_END, resident_mod_code


def synthetic_mod():
    """Same size, configurable words and search anchor as the Drop x15 code; filler elsewhere."""
    code = bytearray((i * 29 + 3) & 0xFF for i in range(DROP15_END - DROP15_CODE))
    code[0x08:0x08 + len(drops._ANCHOR)] = drops._ANCHOR
    for offset, word in drops.SITES:
        struct.pack_into('<I', code, offset, word)
    return bytes(code)


MOD = synthetic_mod()
MOD_SHA = hashlib.sha256(MOD).hexdigest()


class DropCountTests(unittest.TestCase):
    def setUp(self):
        patcher = patch('fmstudio.ps1_campaign_quests.DROP15_CODE_SHA256', MOD_SHA)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_original_mod_reads_as_five(self):
        self.assertEqual(drops.count_of(MOD), 5)
        self.assertEqual(drops.canonical(MOD), MOD)

    def test_every_choice_round_trips_and_canonicalizes(self):
        for count in drops.CHOICES:
            patched, positions = drops.patch_copies(MOD, count, required=True)
            self.assertEqual(positions, [0])
            self.assertEqual(len(drops.CHOICES), 100)
            self.assertEqual(drops.count_of(patched), count)
            self.assertEqual(drops.canonical(patched), MOD)
            draw = struct.unpack_from('<I', patched, drops.LIMIT_DRAW[0])[0]
            award = struct.unpack_from('<I', patched, drops.LIMIT_AWARD[0])[0]
            show = struct.unpack_from('<I', patched, drops.LIMIT_SHOW[0])[0]
            self.assertEqual((draw, award, show), (0x24170000 | count + 1, 0x24170000 | count + 1,
                                                    0x24170000 | count))
            changed = {offset for offset in range(0, len(MOD), 4) if patched[offset:offset + 4] != MOD[offset:offset + 4]}
            self.assertLessEqual(changed, {offset for offset, _ in drops.SITES})

    def test_list_fits_before_the_mod_code(self):
        for count in drops.CHOICES:
            patched, _ = drops.patch_copies(MOD, count, required=True)
            low = struct.unpack_from('<I', patched, drops.BASE_DRAW[0])[0] & 0xFFFF
            base = 0x801B0000 + (low - 0x10000 if low & 0x8000 else low)
            last_entry_end = base + 0x20 + 2 * count + 2
            self.assertLessEqual(last_entry_end, DROP15_CODE, count)
            self.assertEqual(base, 0x801AAC00 if count <= 15 else 0x801AAB50)

    def test_all_copies_in_an_archive_are_patched(self):
        archive = b'\x11' * 1000 + MOD + b'\x22' * 333 + MOD + b'\x33' * 7
        patched, positions = drops.patch_copies(archive, 30, required=False)
        self.assertEqual(positions, [1000, 1000 + len(MOD) + 333])
        for start in positions:
            self.assertEqual(drops.count_of(patched[start:start + len(MOD)]), 30)
        self.assertEqual(patched[:1000], archive[:1000])
        broken = archive.replace(MOD[0x60:0x70], b'\0' * 16, 1)
        self.assertEqual(drops.find_copies(broken), [1000 + len(MOD) + 333])
        with self.assertRaisesRegex(ModError, 'não foi encontrado'):
            drops.patch_copies(b'\0' * 4096, 3, required=True)

    def test_apply_and_status_on_executable(self):
        exe = bytearray(0x1e0800)
        at = exe_pos(DROP15_CODE, exe, len(MOD))
        exe[at:at + len(MOD)] = MOD
        wa = b'\x44' * 5000 + MOD
        self.assertEqual(drops.status(bytes(exe)), {'status': 'original_do_mod', 'cartas': 5})
        new_exe, new_wa, report = drops.apply(bytes(exe), wa, 15)
        self.assertEqual((report['copias_slus'], report['copias_wa'], report['cartas']), (1, 1, 15))
        self.assertEqual(drops.status(new_exe), {'status': 'aplicado', 'cartas': 15})
        # The quest overlay keeps accepting the mod code after the change.
        self.assertEqual(drops.canonical(resident_mod_code(new_exe)), MOD)
        self.assertEqual(drops.count_of(resident_mod_code(new_exe)), 15)

    def test_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Project.create(Path(folder), 'Teste')
            self.assertIsNone(drops.cards_per_win(project))
            drops.set_cards_per_win(project, 30)
            self.assertEqual(drops.cards_per_win(Project.open(Path(folder))), 30)
            for bad in (0, 101, True, '5'):
                with self.assertRaisesRegex(ModError, 'escolha'):
                    drops.set_cards_per_win(project, bad)
            drops.set_cards_per_win(project, 77)
            self.assertEqual(drops.cards_per_win(project), 77)
            drops.set_cards_per_win(project, None)
            self.assertIsNone(drops.cards_per_win(project))


if __name__ == '__main__':
    unittest.main()
