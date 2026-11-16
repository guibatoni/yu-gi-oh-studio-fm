"""Tkinter smoke de criação, passwords e botões de geração nos dois editores."""
from pathlib import Path
from tempfile import TemporaryDirectory

from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.gui import Studio
from fmstudio.mod_data import STOCK_STARTER
from fmstudio.mod_gui import NewCardDialog
from fmstudio.mod_tools_gui import DeckGeneratorDialog, PasswordsDialog
from fmstudio.passwords import chest_cards
from fmstudio.tables import TYPE_NAMES


with TemporaryDirectory() as temp:
    project = Project.create(Path(temp), 'Teste Edição do Mod')
    for index in range(15):
        project.add_card(name=f'Dragão {index}', type_id=0)
    root = Studio()
    root.project, root.drafts = project, DraftSession(project)
    root._refresh_all()
    root.update()
    editor = root.mod_editor
    editor.opponent_deck.fixed.set('723')
    root.filter.set('filtrado')
    root.add_new_card()
    dialog = next(child for child in root.winfo_children() if isinstance(child, NewCardDialog))
    dialog.kind.set(TYPE_NAMES[22])
    dialog.name.set('Ritual de teste')
    dialog.create()
    root.update()
    cid = root.selected_id
    assert project.get(cid)['tipo_id'] == 22
    assert root.tree.exists(str(cid))
    assert editor.opponent_deck.fixed.get() == '723'
    assert cid in editor.opponent_deck.table.labels.values()
    assert Project.open(project.folder).get(cid)['nome'] == 'Ritual de teste'
    root.filter.set('Ritual de teste')
    assert root.tree.get_children() == (str(cid),)
    editor.open_passwords()
    codes = next(child for child in root.winfo_children() if isinstance(child, PasswordsDialog))
    codes.ids.query.set(str(cid))
    codes.ids.redeem()
    assert codes.ids.tree.selection() == (str(cid),)
    assert chest_cards(project) == {str(cid): 1}
    codes.ids._open()

    deck_editor = editor.opponent_deck
    deck_editor.query.set('ritual de teste')
    deck_editor.kind.set(TYPE_NAMES[22])
    assert deck_editor.catalog.get_children() == (str(cid),)
    deck_editor.catalog.selection_set(str(cid))
    deck_editor.quantity.set('2')
    deck_editor.change_card('add')
    assert deck_editor.deck.set(str(cid), 'qtd') == '2'
    deck_editor.quantity.set('1')
    deck_editor.change_card('set')
    assert deck_editor.deck.set(str(cid), 'qtd') == '1'
    first = editor.duelist.get()
    editor.duelist.set(next(name for name, opponent in editor.duelist_ids.items() if opponent == 2))
    editor._load_duelist()
    assert not deck_editor.fixed.get()
    editor.duelist.set(first)
    editor._load_duelist()
    assert deck_editor.deck.set(str(cid), 'qtd') == '1'
    deck_editor.change_card('remove')
    assert deck_editor.fixed.get() == '723'
    assert '1/40' in deck_editor.total.get()

    def setup_deck(target):
        editor.generate_deck(target)
        generator = next(child for child in root.winfo_children() if isinstance(child, DeckGeneratorDialog))
        generator._generate()
        assert generator.deck is not None, generator.status.get()
        assert len(generator.deck.cards) == 40
        generator._use()

    setup_deck(editor.opponent_deck)
    editor.save_opponent()
    assert len(editor.rules['duelistas']['1']['deck']['cartas']) == 40
    setup_deck(editor.starter_deck)
    name = editor.starter.get()
    assert name != STOCK_STARTER
    restored = Project.open(project.folder)
    assert len(restored.metadata['edicao_mod']['iniciais'][name]['cartas']) == 40
    root.destroy()
print('GUI: criação imediata, resgate de password por ID e geração dos dois decks conferidos.')
