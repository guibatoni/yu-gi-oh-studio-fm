"""Modelo da nova interface: preferências, navegação/busca e edição em lote (sem Tk)."""
import os
import tempfile
import unittest
from pathlib import Path

from fmstudio import card_batch, ui_nav, ui_prefs
from fmstudio.core import ModError, Project
from fmstudio.drafts import DraftSession


class PrefsTests(unittest.TestCase):
    def test_defaults_roundtrip_and_bad_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sub' / 'interface.json'
            self.assertEqual(ui_prefs.load(path)['secao'], 'inicio')
            prefs = ui_prefs.load(path)
            prefs.update(barra_recolhida=True, largura_biblioteca=5000, secao='drops', geometria='1200x700+10+20')
            for index in range(12):
                ui_prefs.remember_project(prefs, Path(folder) / f'p{index}')
            ui_prefs.remember_project(prefs, Path(folder) / 'p3')
            self.assertTrue(ui_prefs.save(prefs, path))
            loaded = ui_prefs.load(path)
            self.assertTrue(loaded['barra_recolhida'])
            self.assertEqual(loaded['largura_biblioteca'], 900)
            self.assertEqual(loaded['secao'], 'drops')
            self.assertEqual(len(loaded['recentes']), ui_prefs.RECENT_LIMIT)
            self.assertEqual(loaded['recentes'][0], str(Path(folder) / 'p3'))
            ui_prefs.forget_project(loaded, Path(folder) / 'p3')
            self.assertNotIn(str(Path(folder) / 'p3'), loaded['recentes'])
            path.write_text('{quebrado', encoding='utf-8')
            self.assertEqual(ui_prefs.load(path), ui_prefs.load(Path(folder) / 'nada.json'))
            path.write_text('{"recentes": "x", "barra_recolhida": 1, "largura_biblioteca": "a"}', encoding='utf-8')
            loaded = ui_prefs.load(path)
            self.assertEqual(loaded['recentes'], [])
            self.assertTrue(loaded['barra_recolhida'])
            self.assertEqual(loaded['largura_biblioteca'], 327)

    def test_geometry_and_env_override(self):
        self.assertTrue(ui_prefs.valid_geometry('1390x825'))
        self.assertTrue(ui_prefs.valid_geometry('1200x700+-8+0'))
        self.assertFalse(ui_prefs.valid_geometry('10x10'))
        self.assertFalse(ui_prefs.valid_geometry('abc'))
        old = os.environ.get('FMSTUDIO_UI_PREFS')
        os.environ['FMSTUDIO_UI_PREFS'] = '/tmp/x.json'
        try:
            self.assertEqual(ui_prefs.prefs_path(), Path('/tmp/x.json'))
        finally:
            if old is None:
                del os.environ['FMSTUDIO_UI_PREFS']
            else:
                os.environ['FMSTUDIO_UI_PREFS'] = old


class NavTests(unittest.TestCase):
    def test_sections_cover_existing_screens(self):
        keys = [s.key for s in ui_nav.SECTIONS]
        self.assertEqual(len(keys), len(set(keys)))
        mods = sorted(s.mod for s in ui_nav.SECTIONS if s.tab == 'tab_mod')
        self.assertEqual(mods, list(range(8)))      # as 8 sub-abas da Edição do Mod
        tabs = {s.tab for s in ui_nav.SECTIONS}
        self.assertEqual(tabs, {'tab_home', 'tab_cards', 'tab_effects', 'tab_fusions', 'tab_mod',
                                'tab_proj', 'tab_extract'})
        self.assertEqual(ui_nav.section_for('tab_mod', 6), 'molduras')
        self.assertEqual(ui_nav.section_for('tab_cards', None), 'cartas')

    def test_search_is_accent_insensitive_and_ranked(self):
        first = ui_nav.search('magia')[0]
        self.assertEqual(first[1].key, 'magias')
        self.assertEqual(ui_nav.search('MÁGICAS')[0][1].key, 'magias')
        self.assertEqual(ui_nav.search('gerar')[0][1].method, 'build_disc')
        self.assertEqual(ui_nav.search('salvar')[0][1].method, 'save_project')
        self.assertEqual(ui_nav.search('zzzz'), [])
        self.assertEqual(len(ui_nav.search('')), len(ui_nav.SECTIONS) + len(ui_nav.ACTIONS))

    def test_history(self):
        history = ui_nav.History(limit=3)
        for key in ('inicio', 'cartas', 'drops', 'quests', 'deck'):
            history.visit(key)
        history.visit('deck')
        self.assertEqual(history.back, ['cartas', 'drops', 'quests'])
        self.assertEqual(history.go_back(), 'quests')
        self.assertEqual(history.go_back(), 'drops')
        self.assertEqual(history.go_forward(), 'quests')
        history.visit('molduras')
        self.assertIsNone(history.go_forward())
        self.assertEqual(history.current, 'molduras')


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temp.name) / 'mod', 'Lote')
        for cid, atk in ((1, 1000), (2, 2000), (3, 1500)):
            self.project.cards[cid] = {'id': cid, 'nome': f'C{cid}', 'descricao': '', 'ataque': atk,
                                       'defesa': 500, 'tipo_id': 1, 'atributo_id': 1, 'nivel': 4,
                                       'guardian_1_id': 1, 'guardian_2_id': 2}
        self.drafts = DraftSession(self.project)

    def tearDown(self):
        self.temp.cleanup()

    def test_stat_operations(self):
        self.assertEqual(card_batch.stat_result(1000, 'somar', 250), 1250)
        self.assertEqual(card_batch.stat_result(100, 'subtrair', 250), 0)
        self.assertEqual(card_batch.stat_result(1234, 'percentual', 110), 1360)
        self.assertEqual(card_batch.stat_result(1, 'definir', 99999), card_batch.STAT_MAX)

    def test_plan_and_apply_go_to_drafts_only(self):
        rows = card_batch.plan(self.drafts.get_card, [1, 2, 3, 3],
                               {'ataque': ('definir', '2000'), 'raridade': 'rara', 'tipo_id': '01'})
        self.assertEqual([r['id'] for r in rows], [1, 2, 3])
        self.assertEqual(rows[1]['depois'], {'raridade': 'rara'})           # ATK e tipo já iguais
        self.assertEqual(rows[0]['antes'], {'ataque': 1000, 'raridade': self.project.get(1).get('raridade', 'comum')})
        self.assertEqual(card_batch.apply_plan(self.drafts, rows), 3)
        self.assertEqual(self.drafts.count, 3)
        self.assertEqual(self.drafts.get_card(1)['ataque'], 2000)
        self.assertFalse(self.project.edits)                                 # nada gravado ainda
        self.drafts.save()
        self.assertEqual(self.project.edits['3']['raridade'], 'rara')
        self.assertEqual(self.project.edits['1']['ataque'], 2000)

    def test_validation(self):
        for changes in ({}, {'ataque': ('multiplicar', 2)}, {'ataque': ('somar', 'x')},
                        {'nivel': 16}, {'raridade': 'mitica'}, {'nome': 'x'},
                        {'ataque': ('percentual', 5000)}):
            with self.assertRaises(ModError, msg=changes):
                card_batch.normalize_changes(changes)


class DeckSummaryTests(unittest.TestCase):
    def test_composition(self):
        from fmstudio.deck_summary import composition, describe
        cards = {1: {'tipo_id': 0, 'ataque': 3000, 'defesa': 2500}, 2: {'tipo_id': 20},
                 3: {'tipo_id': 21}, 4: {'tipo_id': 23}, 5: {'tipo_id': 24, 'ataque': 1000, 'defesa': 500}}
        summary = composition(cards, [1, 1, 2, 3, 4, 5, 99])
        self.assertEqual((summary['monstros'], summary['magias'], summary['armadilhas'],
                          summary['equipamentos'], summary['desconhecidas']), (3, 1, 1, 1, 1))
        self.assertEqual(summary['atk_medio'], 2333)
        text = describe(summary)
        self.assertIn('3 monstros', text)
        self.assertIn('1 fora do catálogo', text)
        self.assertEqual(describe(composition(cards, [])), '0 monstros')


class CardPickerFilterTests(unittest.TestCase):
    def test_filter_cards(self):
        from fmstudio.card_search import filter_cards
        cards = {1: {'nome': 'Blue-Eyes White Dragon', 'tipo_id': 0, 'atributo_id': 0},
                 2: {'nome': 'Mystical Elf', 'tipo_id': 1, 'atributo_id': 0},
                 3: {'nome': 'Dian Keto', 'tipo_id': 20},
                 4: {'nome': 'Armadilha', 'tipo_id': 21},
                 5: {'nome': 'Dragão Negro', 'tipo_id': 0, 'atributo_id': 1}}
        self.assertEqual(filter_cards(cards), [1, 2, 3, 4, 5])
        self.assertEqual(filter_cards(cards, 'elf'), [2])
        self.assertEqual(filter_cards(cards, 'dragao'), [5])          # sem acento
        self.assertEqual(filter_cards(cards, category='Magias'), [3])
        self.assertEqual(filter_cards(cards, category='Monstros'), [1, 2, 5])
        self.assertEqual(filter_cards(cards, category='Tipo: Dragon'), [1, 5])
        self.assertEqual(filter_cards(cards, attribute=1), [5])
        self.assertEqual(filter_cards(cards, '3'), [3])


if __name__ == '__main__':
    unittest.main()
