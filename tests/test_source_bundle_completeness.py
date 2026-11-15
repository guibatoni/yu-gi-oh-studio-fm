"""Impedir que Releases de código Python omitam módulos usados pelo Studio."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from fmstudio.updates import SOURCE_FILES, SOURCE_REQUIRED, install_archive
from tools.package_source import ROOT, build


class SourcePackageCompletenessTests(unittest.TestCase):
    def test_all_runtime_modules_are_declared_in_source_bundle(self):
        all_modules = {p.relative_to(ROOT).as_posix()
                       for p in (ROOT / 'fmstudio').glob('*.py')}
        self.assertFalse(all_modules - SOURCE_FILES)
        for required in ('fmstudio/disc_verify.py', 'fmstudio/ps1_equip.py'):
            self.assertIn(required, SOURCE_FILES)
            self.assertIn(required, SOURCE_REQUIRED)

    def test_packager_and_installation_repair_missing_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'FM-Mod-Studio-Source.zip'
            build(archive)
            with zipfile.ZipFile(archive) as data:
                self.assertTrue({'fmstudio/disc_verify.py',
                                 'fmstudio/ps1_equip.py'}.issubset(data.namelist()))
            destination = root / 'instalacao_antiga'
            (destination / 'fmstudio').mkdir(parents=True)
            (destination / 'app.py').write_text('versao antiga', encoding='utf-8')
            (destination / 'fmstudio/gui.py').write_text('gui antiga', encoding='utf-8')
            project = destination / 'projetos' / 'mod' / 'projeto.json'
            project.parent.mkdir(parents=True)
            project.write_text('{"efeitos": "preservados"}', encoding='utf-8')
            install_archive(archive, destination, kind='source')
            self.assertTrue((destination / 'fmstudio/disc_verify.py').is_file())
            self.assertTrue((destination / 'fmstudio/ps1_equip.py').is_file())
            self.assertEqual(project.read_text(encoding='utf-8'),
                             '{"efeitos": "preservados"}')
            env = dict(os.environ, PYTHONPATH=str(destination))
            checked = subprocess.run(
                [sys.executable, '-c',
                 'import fmstudio.disc_verify; import fmstudio.ps1_equip; '
                 'import fmstudio.disc_build; print("imports-ok")'],
                cwd=str(root), env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertIn('imports-ok', checked.stdout)


if __name__ == '__main__':
    unittest.main()
