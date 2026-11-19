"""Cura, dano direto e destruição por tipo das mágicas no PS1."""
from pathlib import Path
import tempfile
import unittest

from fmstudio import ps1_magic_values as mv
from fmstudio.core import ModError, Project
from fmstudio.tables import EXE_DELTA


def executable():
    exe = bytearray(0x1e0800)
    exe[:8] = b'PS-X EXE'
    heal, damage = mv.HEAL_TABLE - EXE_DELTA, mv.DAMAGE_TABLE - EXE_DELTA
    exe[heal:heal + 5] = bytes((2, 5, 10, 20, 50))
    exe[damage:damage + 5] = bytes((5, 10, 20, 50, 100))
    at = mv.REMOVAL_TABLE - EXE_DELTA
    exe[at:at + 14] = bytes((53, 3, 56, 2, 60, 14, 61, 150, 62, 9, 63, 18, 64, 12))
    return bytes(exe)


class MagicValueTests(unittest.TestCase):
    def test_reads_drop15_defaults(self):
        self.assertEqual(mv.read_values(executable()), mv.DROP15_DEFAULTS)

    def test_apply_changes_only_value_bytes(self):
        exe = executable()
        values = {'cura': {342: 3000}, 'dano': {343: 2550},
                  'destruicao': {653: {'tipo': 7}, 661: {'atk_min': 2000}}}
        patched, report = mv.apply(exe, values)
        self.assertEqual(report['cura']['342'], 3000)
        self.assertTrue(mv.matches(patched, values))
        read = mv.read_values(patched)
        self.assertEqual(read['destruicao'][653], {'tipo': 7})
        self.assertEqual(read['destruicao'][661], {'atk_min': 2000})
        self.assertEqual(read['cura'][338], 200)
        changed = [i + EXE_DELTA for i in range(len(exe)) if exe[i] != patched[i]]
        self.assertEqual(changed, [mv.REMOVAL_TABLE + 1, mv.REMOVAL_TABLE + 7,
                                   mv.HEAL_TABLE + 4, mv.DAMAGE_TABLE])

    def test_validation(self):
        for bad in ({'cura': {342: 150}}, {'cura': {342: 25600}}, {'dano': {343: 15}},
                    {'cura': {343: 100}}, {'destruicao': {653: {'tipo': 21}}},
                    {'destruicao': {661: {'atk_min': 200}}}, {'destruicao': {700: {'tipo': 1}}},
                    {'destruicao': {653: {}}}, {'dano': {343: True}}):
            with self.assertRaises(ModError, msg=bad):
                mv.normalize(bad)

    def test_refuses_other_removal_table(self):
        exe = bytearray(executable())
        exe[mv.REMOVAL_TABLE - EXE_DELTA] = 1
        with self.assertRaisesRegex(ModError, 'diverge'):
            mv.apply(bytes(exe), {'cura': {338: 300}})

    def test_settings_persist(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Project.create(Path(folder), 'Teste')
            self.assertTrue(mv.is_empty(mv.magic_values(project)))
            mv.save_magic_values(project, {'dano': {'347': '2000'}, 'destruicao': {'664': {'tipo': '0'}}})
            loaded = mv.magic_values(Project.open(Path(folder)))
            self.assertEqual(loaded['dano'], {347: 2000})
            self.assertEqual(loaded['destruicao'], {664: {'tipo': 0}})


class FieldTrapDefaultsTests(unittest.TestCase):
    def test_terrain_defaults_match_the_stock_table_reader(self):
        import struct
        from fmstudio.ps1_native import TERRAIN_ADDRESS, read_terrain_boosts
        exe = bytearray(0x1e0800)
        at = TERRAIN_ADDRESS - EXE_DELTA
        for (terrain, type_id), points in mv.TERRAIN_DEFAULTS.items():
            struct.pack_into('<b', exe, at + type_id * 6 + terrain - 1, points // 10)
        table = read_terrain_boosts(bytes(exe))
        self.assertEqual({k: v for k, v in table.items() if v}, mv.TERRAIN_DEFAULTS)
        self.assertEqual(len(mv.TERRAIN_NAMES), 6)

    def test_trap_defaults(self):
        self.assertEqual(mv.TRAP_DEFAULTS, {681: 500, 682: 1000, 683: 1500, 684: 2000, 685: 3000, 686: 25500})


if __name__ == '__main__':
    unittest.main()
