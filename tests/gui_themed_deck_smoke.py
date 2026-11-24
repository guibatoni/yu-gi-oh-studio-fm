"""Janela Gerar deck temático e aba Fundo do menu sob servidor gráfico virtual."""
import tkinter as tk
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from tests.test_themed_deck import catalog
from fmstudio.themed_deck_gui import ThemedDeckDialog
from fmstudio.wallpaper_gui import MenuWallpaperEditor

root = tk.Tk()
cards, fusions, equips, *_ = catalog()
saved = []
dialog = ThemedDeckDialog(root, cards, {}, fusions, equips, default_copies=3,
                          use_deck=lambda ids, label: saved.append((ids, label)))
root.update()
assert dialog.result is not None and len(dialog.result.cards) == 40
assert 'Fusão-chave' in dialog.text.get('1.0', 'end')
dialog.generate()
dialog.accept()
root.update()
assert saved and len(saved[0][0]) == 40 and saved[0][1].startswith('Fada')


class Project:
    def __init__(self, folder):
        self.folder, self.metadata = folder, {}

    def save(self):
        pass


with TemporaryDirectory() as folder:
    frame = tk.Frame(root)
    editor = MenuWallpaperEditor(frame, None)
    project = Project(Path(folder))
    editor.set_project(project)
    source = Path(folder) / 'fundo.png'
    Image.new('RGB', (64, 64), (30, 60, 200)).save(source)
    editor.source = str(source)
    editor.mode.set('ladrilho')
    editor.tile.set(32)
    editor._refresh()
    editor.enabled.set(True)
    editor._save()
    root.update()
    assert project.metadata['ps1_papel_parede_menu']['ativado']
    assert (Path(folder) / 'menu' / 'papel_parede_menu.png').exists()
root.destroy()
print('gui_themed_deck_smoke ok')
