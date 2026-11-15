"""Regressão: projeto editado é preservado e DiscError aparece como aviso, sem traceback Tkinter."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from fmstudio.gui import Studio
from fmstudio.disc import DiscError


class ImportBinSafetyTests(TestCase):
    def test_edited_project_avoids_reimport_and_preserves_edits(self):
        p = SimpleNamespace(cards={1: {}}, edits={'1': {'ataque': 3500}}, effects={},
                            import_disc=Mock())
        fake = SimpleNamespace(_stage_current=lambda: None, drafts=None,
                               _extract_running=False, _ensure_project=lambda: True,
                               project=p, _update_status=Mock())
        with patch('fmstudio.gui.filedialog.askopenfilename') as dialog, \
             patch('fmstudio.gui.messagebox.showinfo') as info:
            Studio.import_bin(fake)
        dialog.assert_not_called()
        p.import_disc.assert_not_called()
        self.assertEqual(p.edits['1']['ataque'], 3500)
        self.assertIn('Gerar jogo BIN/CUE', info.call_args.args[1])

    def test_disc_error_shows_message_instead_of_tkinter_traceback(self):
        p = SimpleNamespace(cards={}, edits={}, effects={}, import_disc=Mock(side_effect=DiscError('Imagem de disco inválida')))
        fake = SimpleNamespace(_stage_current=lambda: None, drafts=None,
                               _extract_running=False, _ensure_project=lambda: True,
                               project=p, _update_status=Mock())
        with patch('fmstudio.gui.filedialog.askopenfilename', return_value='JOGO.bin'), \
             patch('fmstudio.gui.messagebox.showerror') as error:
            Studio.import_bin(fake)
        self.assertIn('Imagem de disco inválida', error.call_args.args[1])
