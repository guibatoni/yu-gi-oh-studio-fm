"""Nova moldura da janela sob xvfb: barra lateral, histórico, busca, biblioteca, lote e status."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('FMSTUDIO_UI_PREFS', str(Path(tempfile.mkdtemp()) / 'interface.json'))

from fmstudio import ui_nav, ui_prefs
from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.gui import Studio

with tempfile.TemporaryDirectory() as temp:
    project = Project.create(Path(temp) / 'mod', 'Projeto da interface')
    for cid in (1, 2, 3):
        project.cards[cid] = {'id': cid, 'nome': f'Carta {cid}', 'descricao': 'x', 'ataque': 1000 * cid,
                              'defesa': 500, 'tipo_id': 1, 'atributo_id': 1, 'nivel': 4,
                              'guardian_1_id': 1, 'guardian_2_id': 2}
    root = Studio()
    root.update()
    assert root._section == 'inicio', root._section
    assert str(root.library) not in root.outer.panes()          # início sem biblioteca
    root.project, root.drafts = project, DraftSession(project)
    root._remember_project()
    root._refresh_all()
    root.update()
    assert root.recent_tree.get_children() == (str(project.folder),)

    # Toda seção abre a tela certa e destaca o item da barra lateral.
    for section in ui_nav.SECTIONS:
        root.show_section(section.key)
        root.update()
        assert root._section == section.key, (section.key, root._section)
        assert root.nav.active == section.key
        assert root.tabs.select() == str(getattr(root, section.tab))
        if section.mod is not None:
            assert root.mod_editor.tabs.index('current') == section.mod
        assert (str(root.library) in root.outer.panes()) == section.library, section.key
        assert bool(root.mod_editor.head.winfo_manager()) == (section.key in ('deck', 'drops', 'iniciais', 'quests')) \
            or section.tab != 'tab_mod', section.key

    # Abas trocadas pelo código antigo (tabs.select) também sincronizam a barra.
    root.tabs.select(root.tab_effects)
    root.update()
    assert root.nav.active == 'efeitos'

    # Histórico.
    root.show_section('drops'); root.update()
    root.show_section('molduras'); root.update()
    root.go_back(); root.update()
    assert root._section == 'drops' and root.mod_editor.tabs.index('current') == 1
    root.go_forward(); root.update()
    assert root._section == 'molduras'

    # Busca rápida.
    root.open_palette(); root.update()
    root.palette.query.set('quest'); root.update()
    root.palette.run(); root.update()
    assert root._section == 'quests'

    # Barra lateral e biblioteca.
    root.toggle_sidebar(); root.update()
    assert root.nav.collapsed and root.prefs['barra_recolhida']
    root.toggle_sidebar(); root.update()
    root.show_section('cartas'); root.update()
    root.toggle_library(); root.update()
    assert str(root.library) not in root.outer.panes()
    root.toggle_library(); root.update()
    assert str(root.library) in root.outer.panes()

    # Edição em lote: vai para os rascunhos, grava só ao salvar.
    from fmstudio.card_batch_gui import CardBatchDialog
    root.tree.selection_set(('1', '2', '3'))
    dialog = CardBatchDialog(root, [1, 2, 3])
    dialog.enabled['ataque'].set(True)
    dialog.values['ataque'].set('2500')
    dialog.enabled['raridade'].set(True)
    dialog.values['raridade'].set('epica — Épica')
    dialog.preview()
    assert len(dialog.tree.get_children()) == 3
    dialog.apply(); root.update()
    assert root.drafts.count == 3 and not project.edits
    assert '●' in root.statusbar.saved.cget('text')
    assert root.save_project()
    assert project.edits['2']['ataque'] == 2500 and project.edits['3']['raridade'] == 'epica'
    assert 'Salvo' in root.statusbar.saved.cget('text')

    # Operação longa: a janela continua viva e a exceção volta para a interface.
    assert root.run_blocking('Teste…', lambda a, b=0: a + b, 2, b=3) == 5
    try:
        root.run_blocking('Teste…', lambda: 1 / 0)
        raise AssertionError('exceção perdida')
    except ZeroDivisionError:
        pass
    assert root._busy is None and not root.statusbar.operation.winfo_manager()

    # Preferências gravadas ao fechar.
    with patch('fmstudio.gui.messagebox.askyesno', return_value=True):
        root._on_close()
    saved = ui_prefs.load()
    assert saved['secao'] == 'cartas', saved['secao']
    assert saved['recentes'][0] == str(project.folder)
print('Interface nova: navegação, histórico, busca, biblioteca, lote, status e preferências: OK')
