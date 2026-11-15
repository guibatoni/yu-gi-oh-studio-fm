"""Fluxo de exportação com geração de BIN/CUE sob solicitação."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from fmstudio.gui import Studio


class ExportFlowTests(TestCase):
    def fake_studio(self):
        disc = Mock()
        fake = SimpleNamespace(
            _extract_running=False,
            _ensure_project=lambda: True,
            _stage_current=lambda: None,
            drafts=None,
            project=SimpleNamespace(
                cards={1: {"nome": "Teste"}},
                export=lambda: (Path("exportacao"), {"cartas_editadas": 29, "efeitos_planejados": 0}),
            ),
            _update_status=lambda message: None,
            build_disc=disc,
        )
        return fake, disc

    def test_offer_to_generate_bin_after_export(self):
        fake, disc = self.fake_studio()
        with patch("fmstudio.gui.messagebox.askyesno", return_value=True) as ask:
            Studio.export(fake)
        self.assertTrue(ask.called)
        disc.assert_called_once_with()

    def test_export_without_generating_disc(self):
        fake, disc = self.fake_studio()
        with patch("fmstudio.gui.messagebox.askyesno", return_value=False):
            Studio.export(fake)
        disc.assert_not_called()
