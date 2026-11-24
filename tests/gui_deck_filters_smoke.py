"""Smoke: filtros de estrela guardiã e fusão no catálogo do deck do rival e no seletor de cartas."""
from fmstudio.card_picker import FUSION_DECK, FUSION_NONE, CardPickerDialog
from fmstudio.card_search import ALL_STARS
from fmstudio.gui import Studio
import tkinter as tk

CARDS = {
    1: {'nome': 'Marte A', 'tipo_id': 0, 'ataque': 1200, 'defesa': 800, 'guardian_1_id': 1, 'guardian_2_id': 8},
    2: {'nome': 'Lua B', 'tipo_id': 9, 'ataque': 900, 'defesa': 700, 'guardian_1_id': 9, 'guardian_2_id': 10},
    3: {'nome': 'Magia', 'tipo_id': 20, 'ataque': 0, 'defesa': 0},
    10: {'nome': 'Fusão X', 'tipo_id': 0, 'ataque': 2000, 'defesa': 1500, 'guardian_1_id': 1, 'guardian_2_id': 1},
}
FUSIONS = {(1, 2): 10, (2, 1): 10}

root = Studio()
try:
    root.update()
    editor = root.mod_editor.opponent_deck
    editor.load(CARDS, {'cartas': [], 'pools': []})
    editor._fusion_cache = FUSIONS
    editor.fusion_filter.set_data(CARDS, FUSIONS)

    editor.star.set('Mars')
    root.update()
    assert set(editor.catalog.get_children()) == {'1', '10'}, editor.catalog.get_children()
    assert editor.catalog.set('1', 'estrelas') == 'Mars/Sun'
    editor.star.set(ALL_STARS)

    editor.fixed.set('2')
    editor.fusion_filter.mode.set(FUSION_DECK)
    editor._render_catalog()
    root.update()
    assert list(editor.catalog.get_children()) == ['1'], editor.catalog.get_children()
    assert 'Fusão X' in editor.catalog.set('1', 'fusao')

    editor.fusion_filter.target = 10
    editor.fusion_filter.mode.set('Fusão: materiais de #010 Fusão X')
    editor._render_catalog()
    root.update()
    assert set(editor.catalog.get_children()) == {'1', '2'}
    assert editor.catalog.set('1', 'fusao').startswith('✓')      # parceiro 2 já está no deck
    editor.fusion_filter.mode.set(FUSION_NONE)
    editor._render_catalog()
    assert len(editor.catalog.get_children()) == 4

    picked = []
    dialog = CardPickerDialog(root, CARDS, picked.extend, multiple=True, fusions=FUSIONS, deck_ids={1})
    root.update()
    dialog.picker.fusion.mode.set(FUSION_DECK)
    dialog.picker.render()
    assert list(dialog.picker.tree.get_children()) == ['2']
    dialog.picker.star.set('Moon')
    root.update()
    assert list(dialog.picker.tree.get_children()) == ['2']
    dialog.picker.star.set('Mars')
    root.update()
    assert list(dialog.picker.tree.get_children()) == []
    dialog.destroy()
    print('ok: filtros de estrela e fusão')
finally:
    root.destroy()
