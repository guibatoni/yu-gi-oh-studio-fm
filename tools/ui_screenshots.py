"""Capturas reais da interface sob xvfb (CI). Uso: xvfb-run -a -s '-screen 0 1600x950x24' python tools/ui_screenshots.py pasta"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('FMSTUDIO_UI_PREFS', str(Path(tempfile.mkdtemp()) / 'interface.json'))

from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.gui import Studio

out = Path(sys.argv[1] if len(sys.argv) > 1 else 'capturas')
out.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    project = Project.create(Path(temp) / 'Meu_MOD', 'Meu Forbidden Memories MOD')
    names = ['Blue-Eyes White Dragon', 'Mystical Elf', 'Hitotsu-Me Giant', 'Flame Swordsman', 'Skull Servant',
             'Dark Magician', 'Gaia The Fierce Knight', 'Celtic Guardian', 'Basic Insect', 'Mammoth Graveyard']
    for cid, name in enumerate(names, start=1):
        project.cards[cid] = {'id': cid, 'nome': name, 'descricao': 'Descrição de exemplo da carta.',
                              'ataque': 300 * cid, 'defesa': 200 * cid, 'tipo_id': cid % 20, 'atributo_id': cid % 6,
                              'nivel': cid % 12, 'guardian_1_id': 1 + cid % 10, 'guardian_2_id': 1 + (cid + 3) % 10}
    root = Studio()
    root.geometry('1500x900+0+0')
    root.project, root.drafts = project, DraftSession(project)
    root._remember_project()
    root._refresh_all()

    if sys.platform == 'win32':
        root.state('zoomed')

    def shot(name):
        root.update()
        root.after(400)
        root.update()
        if sys.platform == 'win32':
            from PIL import ImageGrab
            ImageGrab.grab().save(out / f'{name}.png')
        else:
            subprocess.run(['import', '-window', 'root', '-crop', '1500x900+0+0', str(out / f'{name}.png')],
                           check=True)

    for key in ('inicio', 'cartas', 'efeitos', 'deck', 'drops', 'quests', 'config', 'magias', 'molduras',
                'exportar', 'extracao'):
        root.show_section(key)
        shot(key)
    root.show_section('cartas')
    root.toggle_sidebar()
    shot('menu_recolhido')
    root.toggle_sidebar()
    root.open_palette()
    root.palette.query.set('dro')
    shot('busca_rapida')
    root.palette.close()
    root.tree.selection_set(('1', '2', '3'))
    from fmstudio.card_batch_gui import CardBatchDialog
    dialog = CardBatchDialog(root, [1, 2, 3])
    dialog.geometry('860x640+300+120')
    dialog.enabled['ataque'].set(True)
    dialog.operations['ataque'].set('Percentual (%)')
    dialog.values['ataque'].set('110')
    dialog.preview()
    shot('edicao_em_lote')
    dialog.destroy()
    root.statusbar.begin('Gerando BIN/CUE…')
    shot('status_operacao')
    root.statusbar.end()
    root.destroy()
print('capturas em', out)
