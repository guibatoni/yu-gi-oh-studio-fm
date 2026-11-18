"""Persistence, native limits and ISO growth independent of copyrighted data."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

from fmstudio.core import Project, ModError
from fmstudio.ps1_expansion import (
    PS1_CARD_CAPACITY, SAVE_DUELIST, SAVE_QUANTITIES, MODEL_KEY, EXPANDED_LEVELS,
    EXPANDED_SORT, compile_expansion, model_candidates, pack_stats, relocate_tables, _title_bitmap,
)
from fmstudio.tables import (CARD_COUNT, EXE_DELTA, GUARDIAN_FIELDS, LEVEL_ADDR,
                             PS1_SUPREME, STATS_ADDR, SUPREME, decode_cards)


class ExpandedCardsTests(unittest.TestCase):
    def setUp(self):
        from test_core import StudioCoreTests
        self.fixture = StudioCoreTests('test_save_reload_and_cards')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.project = self.fixture.p

    def test_all_families_persist_with_independent_ids_and_native_models(self):
        ids = []
        for kind, base in ((0, 24), (20, 308), (21, 309), (23, 311), (22, 310)):
            cid = self.project.add_card(base, name=f'Nova {kind}', type_id=kind, native_model_id=base)
            ids.append(cid)
            reopened = Project.open(self.project.folder)
            self.assertIn(cid, reopened.cards)
            self.assertEqual(reopened.get(cid)['tipo_id'], kind)
            self.assertEqual(reopened.get(cid)[MODEL_KEY], base)
        self.assertEqual(ids, list(range(723, 728)))
        output, _ = self.project.export(include_ps1=False)
        cards = json.loads((output / 'novas_cartas.json').read_text())['cartas']
        self.assertEqual(set(cards), set(map(str, ids)))
        self.assertTrue(all(cards[str(cid)]['id'] == cid for cid in ids))

    def test_last_native_slot_keeps_save_geometry_and_above_limit_stays_in_studio(self):
        self.project.add_card(24, card_id=740)
        self.project.add_card(24, card_id=741)
        plan = compile_expansion(self.project, profile=True)
        self.assertEqual(plan.ids, (740,))
        self.assertEqual(len(plan.pending), 1)
        self.assertIn('#741', plan.pending[0])
        self.assertEqual(SAVE_QUANTITIES + PS1_CARD_CAPACITY, SAVE_DUELIST)
        self.assertEqual(Project.open(self.project.folder).get(741)['id'], 741)

    def test_unsupported_profile_cannot_install_any_extra_id(self):
        self.project.add_card(24)
        plan = compile_expansion(self.project, profile=False)
        self.assertFalse(plan.enabled)
        self.assertEqual(len(plan.pending), 1)

    def test_native_model_rejects_a_different_card_family_before_mutation(self):
        before = set(self.project.cards)
        with self.assertRaisesRegex(ModError, 'compatível'):
            self.project.add_card(24, type_id=21, native_model_id=24)
        self.assertEqual(set(self.project.cards), before)
        self.assertFalse(self.project.new_cards)

    def test_changed_original_type_does_not_become_an_invalid_behavior_template(self):
        self.project.set_card(24, {'tipo_id': 21})
        self.assertNotIn(24, model_candidates(self.project, 21))
        self.assertIn(24, model_candidates(self.project, 0))

    def test_native_stat_failure_never_changes_the_saved_studio_value(self):
        cid = self.project.add_card(24)
        self.project.set_card(cid, {'ataque': 123456789})
        with self.assertRaisesRegex(ModError, '5110'):
            compile_expansion(self.project, profile=True)
        self.assertEqual(Project.open(self.project.folder).get(cid)['ataque'], 123456789)
        self.assertEqual(pack_stats(cid, {**self.project.get(cid), 'ataque': 5110})[0] & 511, 511)

    def test_relocation_snapshots_all_original_rows_and_protects_password_scratch(self):
        cid = self.project.add_card(24, card_id=740)
        self.project.set_card(cid, {'ataque': 3210, 'defesa': 2340, 'nivel': 11})
        original = self.fixture.file.read_bytes()
        source = bytearray(original)
        scratch = 0x801D5608 - EXE_DELTA
        source[scratch:scratch + 64] = bytes(range(64))
        patched = relocate_tables(original, bytes(source), self.project,
                                  compile_expansion(self.project, profile=True))
        stats = STATS_ADDR - EXE_DELTA
        self.assertEqual(patched[stats:stats + CARD_COUNT * 4], source[stats:stats + CARD_COUNT * 4])
        self.assertEqual(patched[scratch:scratch + 64], bytes(range(64)))
        levels = EXPANDED_LEVELS - EXE_DELTA
        self.assertEqual(patched[levels:levels + 723], source[LEVEL_ADDR - EXE_DELTA:LEVEL_ADDR - EXE_DELTA + 723])
        self.assertEqual(patched[levels + 740] & 15, 11)
        self.assertEqual(EXPANDED_SORT + 2 * 740, 0x801D539E)
        self.assertEqual(struct.unpack_from('<I', patched, stats + 739 * 4)[0] & 511, 321)

    def test_native_model_edit_survives_a_later_normal_form_save(self):
        cid = self.project.add_card(24)
        self.project.set_card(cid, {MODEL_KEY: 48})
        self.project.set_card(cid, {'nome': 'Monstro editado', 'ataque': 2400})
        self.assertEqual(Project.open(self.project.folder).get(cid)[MODEL_KEY], 48)

    def test_supreme_in_either_slot_keeps_the_project_value_and_fits_the_bin(self):
        choices = {723: (SUPREME, 9), 740: (8, SUPREME)}
        original = self.fixture.file.read_bytes()
        for cid, stars in choices.items():
            self.project.add_card(24, card_id=cid)
            self.project.set_card(cid, dict(zip(GUARDIAN_FIELDS, stars)))
        plan = compile_expansion(self.project, profile=True)
        exe = relocate_tables(original, original, self.project, plan)
        reopened = Project.open(self.project.folder)
        raw_cards, _ = decode_cards(exe, capacity=PS1_CARD_CAPACITY, level_address=EXPANDED_LEVELS)
        cards, _ = decode_cards(exe, capacity=PS1_CARD_CAPACITY, level_address=EXPANDED_LEVELS,
                                supreme=True)
        for cid, stars in choices.items():
            self.assertEqual(tuple(reopened.get(cid)[k] for k in GUARDIAN_FIELDS), stars)
            self.assertEqual(tuple(cards[cid - 1][k] for k in GUARDIAN_FIELDS), stars)
            self.assertEqual(tuple(raw_cards[cid - 1][k] for k in GUARDIAN_FIELDS),
                             tuple(PS1_SUPREME if star == SUPREME else star for star in stars))

    def test_native_titles_have_4bpp_size_and_real_ink(self):
        title = _title_bitmap('Dragão personalizado')
        self.assertEqual(len(title), 96 * 14 // 2)
        self.assertTrue(any(title))
        self.assertTrue(all((v & 15) < 8 and (v >> 4) < 8 for v in title))


class ExpandedDiscTests(unittest.TestCase):
    def test_append_updates_both_endians_and_preserves_existing_extents(self):
        from test_cemetery_disc import fake_disc, sector
        from fmstudio.disc import DiscReader
        from fmstudio.disc_append import append_iso_file
        from fmstudio.disc_build import regenerate_form1
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.bin'
            original = b'PS-X EXE' + bytes(2992)
            fake_disc(path, original)
            # The small legacy fixture omits the descriptor terminator.
            terminal = bytearray(2048)
            terminal[0], terminal[1:6], terminal[6] = 255, b'CD001', 1
            with path.open('r+b') as stream:
                stream.seek(17 * 2352)
                stream.write(sector(terminal))
            before = path.read_bytes()
            with DiscReader(path) as reader:
                entry = next(e for e in reader.files() if e.path == 'SLUS_014.11')
            after = original + b'X' * 2500
            with path.open('r+b') as stream:
                changed = append_iso_file(stream, entry, original, after)
            with DiscReader(path) as reader:
                actual = next(e for e in reader.files() if e.path == entry.path)
                self.assertEqual(b''.join(reader.read_entry(actual)), after)
                self.assertEqual(actual.extent, len(before) // 2352)
                pvd = reader.sector(16)
                self.assertEqual(struct.unpack_from('<I', pvd, 80)[0], path.stat().st_size // 2352)
                self.assertEqual(struct.unpack_from('>I', pvd, 84)[0], path.stat().st_size // 2352)
                record = reader.sector(20)
                self.assertEqual(struct.unpack_from('<I', record, 2)[0], struct.unpack_from('>I', record, 6)[0])
                self.assertEqual(struct.unpack_from('<I', record, 10)[0], len(after))
                self.assertEqual(struct.unpack_from('>I', record, 14)[0], len(after))
            result = path.read_bytes()
            for lba in range(len(before) // 2352):
                if lba not in (16, 20):
                    self.assertEqual(result[lba * 2352:(lba + 1) * 2352], before[lba * 2352:(lba + 1) * 2352])
            for lba in changed:
                raw = result[lba * 2352:(lba + 1) * 2352]
                self.assertEqual(regenerate_form1(raw), raw)


if __name__ == '__main__':
    unittest.main()
