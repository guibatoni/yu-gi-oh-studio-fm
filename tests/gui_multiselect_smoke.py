"""Testes reais Tkinter: multisseleção em drops, pools, decks e biblioteca."""
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.gui import Studio
from fmstudio.mod_data import CONFIG_KEY, DROP_FROM_DECK, DECK_DROP_WEIGHTS, save_rules
from fmstudio.duel_engine import parse_card_ids


with TemporaryDirectory() as tmp:
    project = Project.create(Path(tmp) / 'lote', 'Seleção múltipla')
    a, b, c, d, e = [project.add_card(name=f'Carta lote {i}') for i in range(5)]
    save_rules(project, {'duelistas': {'1': {'deck': {'cartas': [a, b, c]}}}})
    root = Studio()
    try:
        root.project, root.drafts = project, DraftSession(project)
        root._refresh_all()
        ed = root.mod_editor
        with patch('tkinter.messagebox.showerror',
                   side_effect=lambda *args, **kw: (_ for _ in ()).throw(AssertionError(args))):
            # Na tabela normal de drops, adicionar em lote via IDs ou seleção.
            table = ed.drops
            table.selected.set(f'{a}, {b}')
            table.weight.set('3')
            table._apply()
            assert table.weights[a] == table.weights[b] == 3
            assert table.tree.cget('selectmode').__str__() == 'extended'
            table.tree.selection_set([str(a), str(b)])
            table._select(None)
            table.weight.set('7')
            table._apply()
            assert table.weights[a] == table.weights[b] == 7
            table.tree.selection_set([str(a), str(b)])
            table._remove()
            assert a not in table.weights and b not in table.weights
            assert project.metadata[CONFIG_KEY]['duelistas']['1']['drops']['pow'] == {}

            # Drops provenientes do deck: editar vários pesos e excluir com zero.
            ed.use_deck_drops.set(True)
            ed._toggle_deck_drops()
            weighted = ed.deck_drop_table
            weighted.tree.selection_set([str(a), str(b)])
            weighted._select(None)
            weighted.weight.set('9')
            weighted._apply()
            assert weighted.weights[a] == weighted.weights[b] == 9
            weighted.tree.selection_set([str(a), str(c)])
            weighted._remove()
            assert weighted.weights == {b: 9}
            assert weighted.tree.set(str(a), 'peso') == '0'
            assert weighted.tree.set(str(c), 'peso') == '0'
            assert project.metadata[CONFIG_KEY]['duelistas']['1'][DECK_DROP_WEIGHTS]['pow'] == {b: 9}
            # Não é permitido esvaziar inteiramente a tabela ponderada.
            with patch('tkinter.messagebox.showerror', return_value=None):
                weighted.tree.selection_set([str(b)])
                weighted._remove()
            assert weighted.weights == {b: 9}

            # Deck: adicionar dois IDs de uma vez, ajustar cópias e remover em lote.
            deck = ed.opponent_deck
            assert deck.catalog.cget('selectmode').__str__() == 'extended'
            assert deck.deck.cget('selectmode').__str__() == 'extended'
            deck.catalog.selection_set([str(d), str(e)])
            deck.add_quantity.set('1')
            deck.change_card('add')
            assert Counter(parse_card_ids(deck.fixed.get())) == Counter({a:1, b:1, c:1, d:1, e:1})
            deck.deck.selection_set([str(d), str(e)])
            deck.quantity.set('2')
            deck.change_card('set')
            assert Counter(parse_card_ids(deck.fixed.get()))[d] == 2
            assert Counter(parse_card_ids(deck.fixed.get()))[e] == 2
            deck.deck.selection_set([str(d), str(e)])
            deck.change_card('remove')
            assert Counter(parse_card_ids(deck.fixed.get())) == Counter({a:1, b:1, c:1})
            before = deck.fixed.get()
            deck.catalog.selection_set([str(a), str(b)])
            deck.add_quantity.set('40')
            deck.change_card('add')
            assert deck.fixed.get() == before
            assert 'Nada foi alterado' in deck.feedback.get()
            # Botões selecionar visíveis mantêm todas as seleções.
            deck._select_all_catalog()
            assert len(deck.catalog.selection()) == len(deck.catalog.get_children())
            deck._select_all_deck()
            assert set(deck.deck.selection()) == {str(a), str(b), str(c)}

            # Biblioteca principal: seleção múltipla segue para o deck do rival.
            root.tree.selection_set([str(d), str(e)])
            root._add_selected_to_deck()
            assert Counter(parse_card_ids(deck.fixed.get())) == Counter(
                {a:1, b:1, c:1, d:1, e:1})

            # Pools ponderados compartilham a edição de peso em lote.
            deck.add_pool()
            pool = deck.table
            pool.selected.set(f'{a}, {b}')
            pool.weight.set('5')
            pool._apply()
            pool.tree.selection_set([str(a), str(b)])
            pool._select(None)
            pool.weight.set('12')
            pool._apply()
            assert pool.weights == {a:12, b:12}
            pool.tree.selection_set([str(a), str(b)])
            pool._remove()
            assert pool.weights == {}

            # Salvar deck sem o pool vazio e testar persistência.
            deck.remove_pool()
            ed.save_opponent()
            reopened = Project.open(project.folder)
            assert Counter(reopened.metadata[CONFIG_KEY]['duelistas']['1']['deck']['cartas']) == Counter(
                {a:1, b:1, c:1, d:1, e:1})
    finally:
        root.destroy()

print('UI multisseleção: drops, pools, deck, catálogo e limites de cópias OK.')
