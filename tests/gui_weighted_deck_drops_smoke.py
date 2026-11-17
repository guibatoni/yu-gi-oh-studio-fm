"""Testa interface real de pesos do deck por rank sob Xvfb."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.gui import Studio
from fmstudio.mod_data import (
    CONFIG_KEY, DECK_DROP_WEIGHTS, deck_drop_weights, drop_weights, save_rules,
)

with TemporaryDirectory() as tmp:
    project = Project.create(Path(tmp) / 'pesos', 'Drops ponderados')
    a = project.add_card(name='Dragão A')
    b = project.add_card(name='Dragão B')
    c = project.add_card(name='Dragão C')
    d = project.add_card(name='Dragão D')
    save_rules(project, {'duelistas': {
        '1': {'deck': {'cartas': [a,b,c], 'pools': []}}
    }})
    root = Studio()
    try:
        root.project, root.drafts = project, DraftSession(project)
        root._refresh_all()
        editor = root.mod_editor
        assert editor._duel_id() == 1
        with patch('tkinter.messagebox.showerror', side_effect=lambda *a, **kw: (_ for _ in ()).throw(AssertionError(a))):
            editor.use_deck_drops.set(True)
            editor._toggle_deck_drops()
            assert set(editor.deck_drop_table.tree.get_children()) == {str(a), str(b), str(c)}
            assert editor.deck_drop_table.weights == {a:1, b:1, c:1}
            editor.deck_drop_table.tree.selection_set(str(a))
            editor.deck_drop_table._select(None)
            editor.deck_drop_table.weight.set('9')
            editor.deck_drop_table._apply()
            editor.deck_drop_table.tree.selection_set(str(c))
            editor.deck_drop_table._select(None)
            editor.deck_drop_table.weight.set('0')
            editor.deck_drop_table._apply()
            assert editor.deck_drop_table.tree.set(str(c), 'peso') == '0'
            assert editor.deck_drop_table.weights == {a:9, b:1}
            assert project.metadata[CONFIG_KEY]['duelistas']['1'][DECK_DROP_WEIGHTS]['pow'] == {a:9, b:1}
            editor.rank.set('S/A-TEC (grupo PS1)')
            editor._load_drop()
            assert editor.deck_drop_table.weights == {a:1, b:1, c:1}
            editor.deck_drop_table.tree.selection_set(str(b))
            editor.deck_drop_table._select(None)
            editor.deck_drop_table.weight.set('20')
            editor.deck_drop_table._apply()
            assert project.metadata[CONFIG_KEY]['duelistas']['1'][DECK_DROP_WEIGHTS]['tec'][b] == 20
            editor.rank.set('S/A/Z-POW (grupo PS1)')
            editor._load_drop()
            assert editor.deck_drop_table.weights == {a:9, b:1}
            assert editor.deck_drop_table.tree.set(str(c), 'peso') == '0'
            editor.opponent_deck.load(editor.cards, {'cartas':[a,b,d], 'pools':[]})
            editor.save_opponent()
            settings = project.metadata[CONFIG_KEY]
            assert deck_drop_weights(settings, {}, 1, 'S-POW') == {a:9,b:1,d:1}
            assert deck_drop_weights(settings, {}, 1, 'S-TEC') == {a:1,b:20,d:1}
            assert set(editor.deck_drop_table.tree.get_children()) == {str(a),str(b),str(d)}
            assert drop_weights(settings, {}, 1, 'S-POW') == {a:9,b:1,d:1}
            editor._reset_deck_drop()
            assert editor.deck_drop_table.weights == {a:1,b:1,d:1}
            table = editor.deck_drop_table
            table.selected.set(f'{a}, #{d}')
            table.weight.set('8')
            table._apply()
            assert table.weights == {a: 8, b: 1, d: 8}
            assert table.tree.set(str(a), 'chance') == '47,0588%'
            table.tree.tk.call(table.tree.heading('peso', 'command'))
            assert table.tree.get_children()[0] == str(b)
            table.tree.tk.call(table.tree.heading('peso', 'command'))
            assert table.tree.get_children()[-1] == str(b)
            table.query.set('dragao b')
            assert table.tree.get_children() == (str(b),)
            assert table.tree.set(str(b), 'chance') == '5,8823%'
            table._set_chance(b, '25%')
            assert table.tree.set(str(b), 'chance') == '25,0000%'
            assert table.weights == {a: 3, b: 2, d: 3}
            reopened = Project.open(project.folder)
            assert deck_drop_weights(reopened.metadata[CONFIG_KEY], {}, 1, 'S-TEC') == {a:1,b:20,d:1}
            editor.use_deck_drops.set(False)
            editor._toggle_deck_drops()
            assert not project.metadata[CONFIG_KEY]['duelistas']['1']['drops_do_deck']
    finally:
        root.destroy()
print('GUI: pesos do deck por POW/TEC, zero, revisão do deck, reset, persistência e alternância OK.')
