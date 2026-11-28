"""Área do menu de debug como espaço extra para rotinas do mod."""
import hashlib
import struct
import unittest
from unittest.mock import patch

from fmstudio import ps1_debug_space as ds
from fmstudio.ps1_equip_bonus import reserve_block


def synthetic_exe(*, mode0=ds.RUN_DEBUG_MENU, fill=b'\x11'):
    data = bytearray(0x800 + 0xC0000)
    data[:8] = b'PS-X EXE'
    struct.pack_into('<I', data, 0x18, 0x80010000)
    struct.pack_into('<I', data, 0x1C, len(data) - 0x800)
    at = 0x800 + ds.DEBUG_START - 0x80010000
    size = ds.DEBUG_END - ds.DEBUG_START
    data[at:at + size] = (fill * size)[:size]
    struct.pack_into('<I', data, 0x800 + ds.MODE_TABLE - 0x80010000, mode0)
    return bytes(data), hashlib.sha256((fill * size)[:size]).hexdigest()


class DebugSpaceTests(unittest.TestCase):
    def test_claim_zeroes_area_and_redirects_mode(self):
        exe, digest = synthetic_exe()
        with patch.object(ds, 'DEBUG_SHA256', digest):
            self.assertEqual(ds.status(exe), 'original')
            out, regions, report = ds.claim(exe)
            self.assertEqual(ds.status(out), 'liberado')
        self.assertEqual(report['status'], 'liberado')
        self.assertEqual(regions, [(ds.DEBUG_START, ds.DEBUG_END)])
        at = 0x800 + ds.DEBUG_START - 0x80010000
        self.assertFalse(any(out[at:at + ds.DEBUG_END - ds.DEBUG_START]))
        self.assertEqual(struct.unpack_from('<I', out, 0x800 + ds.MODE_TABLE - 0x80010000)[0], ds.RUN_MENU)
        # cabe uma rotina de 200 bytes e vários blocos
        free = regions
        for size in (200, 236, 92, 1200):
            address, free = reserve_block(out, free, size)
            self.assertTrue(ds.DEBUG_START <= address < ds.DEBUG_END)

    def test_unknown_area_is_left_alone(self):
        exe, _ = synthetic_exe()
        out, regions, report = ds.claim(exe)          # SHA não confere
        self.assertEqual((out, regions, report['status']), (exe, [], 'indisponivel'))

    def test_link_screens_are_freed_too(self):
        exe, digest = synthetic_exe()
        data = bytearray(exe)
        size = ds.LINK_END - ds.LINK_START
        at = 0x800 + ds.LINK_START - 0x80010000
        data[at:at + size] = b'\x22' * size
        for mode, runner in zip(ds.LINK_MODES, ds.LINK_RUNNERS):
            struct.pack_into('<I', data, 0x800 + ds.MODE_TABLE + 4 * mode - 0x80010000, runner)
        link_digest = hashlib.sha256(b'\x22' * size).hexdigest()
        zeros = hashlib.sha256(bytes(ds.SOUND_END - ds.SOUND_START)).hexdigest()
        with patch.object(ds, 'DEBUG_SHA256', digest), patch.object(ds, 'LINK_SHA256', link_digest), \
                patch.object(ds, 'SOUND_SHA256', zeros):
            out, regions, report = ds.claim(bytes(data))
            self.assertEqual(ds._link_state(out), 'liberado')
            self.assertEqual(ds.claim(out)[1], regions)
        self.assertEqual(regions, [(ds.DEBUG_START, ds.DEBUG_END), (ds.SOUND_START, ds.SOUND_END),
                                   (ds.LINK_START, ds.LINK_END)])
        self.assertFalse(any(out[at:at + size]))
        for mode in ds.LINK_MODES:
            self.assertEqual(struct.unpack_from('<I', out, 0x800 + ds.MODE_TABLE + 4 * mode - 0x80010000)[0],
                             ds.RUN_MENU)
        self.assertEqual(report['bytes'], 4952 + 1344 + 1448)

    def test_space_size(self):
        self.assertEqual(ds.DEBUG_END - ds.DEBUG_START, 4952)


if __name__ == '__main__':
    unittest.main()
