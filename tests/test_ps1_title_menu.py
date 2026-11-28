"""Menu inicial só com NEW GAME e LOAD (overlay do SU.MRG)."""
import struct
import unittest

from fmstudio.core import ModError
from fmstudio import ps1_title_menu as tm


def su_with(words):
    data = bytearray(1239 * 0x800)
    for address, word in zip(tm.PATCHES, words):
        struct.pack_into('<I', data, tm._offset(address), word)
    return bytes(data)


class TitleMenuTests(unittest.TestCase):
    def test_patch_counts_two_entries(self):
        su = su_with([old for old, _ in tm.PATCHES.values()])
        self.assertEqual(tm.status(su), 'original')
        out, report = tm.apply(su)
        self.assertEqual(tm.status(out), 'aplicado')
        self.assertEqual(report['opcoes'], ['NEW GAME', 'LOAD'])
        self.assertEqual(struct.unpack_from('<I', out, 98 * 0x800 + 0x700)[0], 0x2A420002)
        self.assertEqual(tm.apply(out)[0], out)          # aplicar de novo não muda nada

    def test_unknown_overlay_is_refused(self):
        with self.assertRaises(ModError):
            tm.apply(su_with([0, 0]))


if __name__ == '__main__':
    unittest.main()
