"""Idiomas da interface: catálogo completo, sem Tkinter."""
import json
import unittest

from fmstudio import i18n, ui_nav


class I18nTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('pt')

    def test_catalog_shape(self):
        catalog = i18n.catalog()
        self.assertGreater(len(catalog), 700)
        for key, values in catalog.items():
            self.assertEqual(key, key.strip(), key)
            self.assertEqual(len(values), len(i18n.ORDER), key)
            self.assertTrue(all(isinstance(v, str) and v.strip() for v in values), key)

    def test_navigation_is_fully_translated(self):
        texts = [s.label for s in ui_nav.SECTIONS] + [s.hint for s in ui_nav.SECTIONS] \
            + [s.group for s in ui_nav.SECTIONS if s.group] + [a.label for a in ui_nav.ACTIONS]
        missing = sorted({t for t in texts if t not in i18n.catalog()})
        self.assertEqual(missing, [])
        for code in i18n.ORDER:
            self.assertEqual(i18n.coverage(code, texts), 1.0, code)

    def test_translate_keeps_spaces_and_falls_back(self):
        i18n.set_language('en')
        self.assertEqual(i18n.t('Salvar'), 'Save')
        self.assertEqual(i18n.t('   Perde LP a cada ataque:'), '   Loses LP on each attack:')
        self.assertEqual(i18n.t('texto sem tradução'), 'texto sem tradução')
        self.assertEqual(i18n.t('Salvar', 'ja'), '保存')
        i18n.set_language('xx')
        self.assertEqual(i18n.language(), 'pt')
        self.assertEqual(i18n.t('Salvar'), 'Salvar')

    def test_search_finds_translated_names(self):
        i18n.set_language('en')
        result = ui_nav.search('frames', translate=i18n.t)
        self.assertEqual(result[0][1].key, 'molduras')
        self.assertEqual(ui_nav.search('molduras', translate=i18n.t)[0][1].key, 'molduras')


class TranslateTests(unittest.TestCase):
    def test_protect_restore_and_google_parsing(self):
        from fmstudio import translate as tr
        text = 'Ganha {color:amarelo}500 ATK{/color} por {card:12} no campo.'
        protected, tokens = tr.protect(text)
        self.assertNotIn('{', protected)
        self.assertEqual(tr.restore(protected, tokens), text)
        with self.assertRaises(tr.TranslationError):
            tr.restore(protected.replace('⟦1⟧', ''), tokens)
        self.assertEqual(tr.restore('X ⟦ 0 ⟧ Y ⟦1⟧ ⟦2⟧', tokens), 'X {color:amarelo} Y {/color} {card:12}')
        payload = json.dumps([[['Gains ', 'Ganha ', None], ['500 ATK.', '500 ATK.', None]], None, 'pt'])
        self.assertEqual(tr.parse_google(payload), 'Gains 500 ATK.')

    def test_translate_many_with_fake_service(self):
        from fmstudio import translate as tr
        calls = []

        def fetch(url, data, headers):
            calls.append(url)
            import urllib.parse
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['q'][0]
            if 'quebra' in q:
                return json.dumps([[['sem marcador', q, None]]])
            return json.dumps([[[q.replace('Ganha', 'Gewinnt').replace('Dragão', 'Drache'), q, None]]])
        items = {1: 'Ganha ⟦x⟧ {card:5}\nDragão grande', 2: '', 3: 'quebra {icon:god}', 4: 'Ganha ß'}
        results = {r.id: r for r in tr.translate_many(items, 'de', fetch=fetch)}
        self.assertEqual(results[1].translated, 'Gewinnt ⟦x⟧ {card:5} Drache grande')
        self.assertIsNone(results[2].translated)
        self.assertIsNone(results[3].translated)           # marcador sumiu: não traduz
        self.assertEqual(results[4].translated, 'Gewinnt ss')  # adaptado para a fonte do PS1
        self.assertEqual(len(calls), 3)
        backup = tr.backup_payload(list(results.values()), 'de', 'google')
        self.assertEqual(set(backup['originais']), {'1', '4'})

    def test_deepl_and_errors(self):
        from fmstudio import translate as tr
        seen = {}

        def fetch(url, data, headers):
            seen.update(url=url, data=data, headers=headers)
            return json.dumps({'translations': [{'text': 'Hallo'}]})
        self.assertEqual(tr.translate_text('Olá', 'de', provider='deepl', api_key='abc:fx', fetch=fetch), 'Hallo')
        self.assertIn('api-free.deepl.com', seen['url'])
        self.assertIn(b'target_lang=DE', seen['data'])
        with self.assertRaises(tr.TranslationError):
            tr.translate_text('Olá', 'de', provider='deepl', api_key='', fetch=fetch)
        with self.assertRaises(tr.TranslationError):
            tr.translate_text('Olá', 'de', provider='google', fetch=lambda *a: 'não é json')


if __name__ == '__main__':
    unittest.main()
