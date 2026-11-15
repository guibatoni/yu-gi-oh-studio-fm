"""Testes do diagnóstico de edições visuais sem patch para PS1."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from fmstudio.gui import Studio
from fmstudio.ps1_compat import audit, explain_no_writable_changes


class EmptyDiscPatchTests(unittest.TestCase):
    def fake_project(self, folder: Path):
        edited = {'1': {'raridade': 'epica'}}
        cards = {1: {'id': 1, 'nome': 'Blue-Eyes White Dragon', 'tipo_id': 0,
                     'atributo_id': 0, 'raridade': 'comum', 'ataque': 3000, 'defesa': 2500}}
        def get(cid):
            card = dict(cards[cid])
            if str(cid) in edited:
                card.update(edited[str(cid)])
            return card
        return SimpleNamespace(folder=folder, metadata={'base_sha256': {}},
                               cards=cards, edits=edited, effects={}, arts={},
                               new_cards={}, get=get)

    def test_explanation_preserves_project_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.fake_project(Path(tmp))
            report = audit(project)
            self.assertFalse(report['gravavel_hoje'])
            msg = explain_no_writable_changes(project, report)
            self.assertIn('Classes/cores alteradas: 1', msg)
            self.assertIn('ATK ou DEF', msg)
            self.assertEqual(project.edits['1']['raridade'], 'epica')

    def test_no_disc_picker_if_only_rarity_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.fake_project(Path(tmp))
            fake = SimpleNamespace(
                _extract_running=False, _ensure_project=lambda: True,
                _stage_current=lambda: None, drafts=None,
                project=project, _update_status=Mock())
            with patch('fmstudio.gui.filedialog.askopenfilename') as picker, \
                 patch('fmstudio.gui.messagebox.showwarning') as warning:
                Studio.build_disc(fake)
            picker.assert_not_called()
            warning.assert_called_once()
            self.assertTrue((Path(tmp) / 'exportacao' / 'compatibilidade_ps1.json').is_file())


if __name__ == '__main__':
    unittest.main()
