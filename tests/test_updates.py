"""Testes offline: atualização compilada e em modo Python, sem ROMs reais."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path

from fmstudio.updates import (
    API, BUNDLE_NAME, SUM_NAME, PROGRAM_NAME, UPDATER_NAME,
    SOURCE_BUNDLE_NAME, SOURCE_SUM_NAME, SOURCE_REQUIRED,
    parse_version, parse_checksum, safe_github_asset_url, read_latest,
    UpdateError, install_archive, validate_archive, installed_kind,
)


class FakeResponse:
    def __init__(self, data: bytes):
        self.buf = io.BytesIO(data)

    def read(self, size=-1):
        return self.buf.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def fake_release(tag: str, names: tuple[str, ...]) -> FakeResponse:
    assets = [{'name': name, 'browser_download_url':
               f'https://github.com/guibatoni/yu-gi-oh-studio-fm/releases/download/{tag}/{name}'}
              for name in names]
    return FakeResponse(json.dumps({'tag_name': tag, 'assets': assets, 'body': 'Notas'}).encode())


class UpdateTests(unittest.TestCase):
    def test_repositorio_oficial(self):
        from fmstudio.updates import REPO
        self.assertEqual(REPO, "guibatoni/yu-gi-oh-studio-fm")
        self.assertIn(REPO, API)

    def test_semver(self):
        self.assertEqual(parse_version('studio-v0.6.2'), (0, 6, 2))
        self.assertIsNone(parse_version('v0.6.2'))
        self.assertIsNone(parse_version('studio-v0.6.2-rc1'))

    def test_checksum_windows_and_source(self):
        sha = 'a' * 64
        self.assertEqual(parse_checksum(f'{sha}  {BUNDLE_NAME}'), sha)
        self.assertEqual(parse_checksum(f'{sha}  {SOURCE_BUNDLE_NAME}',bundle=SOURCE_BUNDLE_NAME),sha)
        with self.assertRaises(UpdateError):
            parse_checksum(f'{sha}  {BUNDLE_NAME}', bundle=SOURCE_BUNDLE_NAME)
        with self.assertRaises(UpdateError):
            parse_checksum('bad')

    def test_urls(self):
        good = f'https://github.com/guibatoni/yu-gi-oh-studio-fm/releases/download/studio-v0.6.2/{SOURCE_BUNDLE_NAME}'
        self.assertTrue(safe_github_asset_url(good))
        self.assertFalse(safe_github_asset_url(good.replace('https:', 'http:')))
        self.assertFalse(safe_github_asset_url('https://other.example.com/test.zip'))
        self.assertFalse(safe_github_asset_url('https://github.com/other/repo/releases/download/tag/test.zip'))

    def test_detect_python(self):
        self.assertEqual(installed_kind(), 'source')

    def test_release_source(self):
        found = read_latest(lambda _: fake_release('studio-v1.0.2',
                                                  (SOURCE_BUNDLE_NAME, SOURCE_SUM_NAME)), kind='source')
        self.assertEqual(found.kind, 'source')
        self.assertEqual(found.version, 'studio-v1.0.2')

    def test_release_windows(self):
        found = read_latest(lambda _: fake_release('studio-v1.0.2',
                                                  (BUNDLE_NAME, SUM_NAME)), kind='windows')
        self.assertEqual(found.kind, 'windows')

    def test_old_is_not_new(self):
        self.assertIsNone(read_latest(lambda _: fake_release('studio-v0.6.0', ()), kind='source'))

    def test_missing_source_bundle_errors(self):
        with self.assertRaisesRegex(UpdateError, 'não possui'):
            read_latest(lambda _: fake_release('studio-v1.0.2', (BUNDLE_NAME, SUM_NAME)), kind='source')

    def test_missing_release_has_explanation(self):
        def err(_):
            raise urllib.error.HTTPError(API, 404, 'not found', {}, None)
        with self.assertRaisesRegex(UpdateError, 'GitHub Releases'):
            read_latest(err, kind='source')

    def test_windows_install_preserves_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / PROGRAM_NAME).write_bytes(b'old')
            (root / UPDATER_NAME).write_bytes(b'old')
            project = root / 'projetos' / 'mod' / 'projeto.json'
            project.parent.mkdir(parents=True)
            project.write_text('meus efeitos', encoding='utf-8')
            archive = root / 'win.zip'
            with zipfile.ZipFile(archive, 'w') as zipped:
                zipped.writestr(PROGRAM_NAME, b'new')
                zipped.writestr(UPDATER_NAME, b'new')
            install_archive(archive, root)
            self.assertEqual((root / PROGRAM_NAME).read_bytes(), b'new')
            self.assertEqual(project.read_text(encoding='utf-8'), 'meus efeitos')

    def test_source_install_preserves_multiple_projects_and_backups(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'fmstudio').mkdir()
            (root / 'app.py').write_text('old', encoding='utf-8')
            (root / 'fmstudio/gui.py').write_text('old gui', encoding='utf-8')
            projects = root / 'projetos' / 'seu-mod' / 'projeto.json'
            projects.parent.mkdir(parents=True)
            projects.write_text('nao modificar', encoding='utf-8')
            backup = root / 'backups' / 'backup.json'
            backup.parent.mkdir()
            backup.write_text('backup seguro', encoding='utf-8')
            archive = root / 'src.zip'
            with zipfile.ZipFile(archive, 'w') as zipped:
                for name in sorted(SOURCE_REQUIRED):
                    zipped.writestr(name, 'new ' + name)
            install_archive(archive, root, kind='source')
            self.assertEqual((root / 'app.py').read_text(), 'new app.py')
            self.assertEqual((root / 'fmstudio/gui.py').read_text(), 'new fmstudio/gui.py')
            self.assertEqual(projects.read_text(), 'nao modificar')
            self.assertEqual(backup.read_text(), 'backup seguro')

    def test_source_zip_rejects_rom(self):
        with tempfile.TemporaryDirectory() as temp:
            zip_path = Path(temp) / 'bad.zip'
            with zipfile.ZipFile(zip_path, 'w') as zipped:
                for name in SOURCE_REQUIRED:
                    zipped.writestr(name, 'good')
                zipped.writestr('base/jogo.bin', b'bad')
            with self.assertRaisesRegex(UpdateError, 'inesperado'):
                validate_archive(zip_path, kind='source')

    def test_source_zip_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            zip_path = Path(temp) / 'bad.zip'
            with zipfile.ZipFile(zip_path, 'w') as zipped:
                for name in SOURCE_REQUIRED:
                    zipped.writestr(name, 'good')
                zipped.writestr('../../projeto.json', b'bad')
            with self.assertRaises(UpdateError):
                validate_archive(zip_path, kind='source')

    def test_windows_requires_updater(self):
        with tempfile.TemporaryDirectory() as temp:
            zip_path = Path(temp) / 'bad.zip'
            with zipfile.ZipFile(zip_path, 'w') as zipped:
                zipped.writestr(PROGRAM_NAME, b'file')
            with self.assertRaises(UpdateError):
                validate_archive(zip_path)


if __name__ == '__main__':
    unittest.main()
