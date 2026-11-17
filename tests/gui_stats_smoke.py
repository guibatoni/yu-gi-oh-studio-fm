"""Smoke Tkinter: ATK/DEF nas abas Drops, Deck do oponente e Decks iniciais."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.gui import Studio
from fmstudio.mod_data import save_rules
from fmstudio.mod_gui import _monster_stat, _monster_stat_sort, WEIGHT_COLUMNS


with TemporaryDirectory() as tmp:
    project = Project.create(Path(tmp) / 'stats', 'Mostrar ATK DEF')
    dragon = project.add_card(name='Dragão Supremo', type_id=0)
    god = project.add_card(name='Divindade', type_id=24)
    spell = project.add_card(name='Magia de Teste', type_id=20)
    trap = project.add_card(name='Armadilha de Teste', type_id=21)
    ritual = project.add_card(name='Ritual de Teste', type_id=22)
    equip = project.add_card(name='Equipamento de Teste', type_id=23)
    project.cards[dragon].update(ataque=12345678, defesa=7654321)
    project.cards[god].update(ataque=20000, defesa=0)
    for cid in (spell, trap, ritual, equip):
        # Mesmo que um registro antigo carregue poder indevidamente,
        # cartas que não são monstros nunca devem exibir ATK/DEF.
        project.cards[cid].update(ataque=9999, defesa=8888)
    project.save()
    ids = [dragon, god, spell, trap, ritual, equip]
    save_rules(project, {
        'duelistas': {'1': {
            'deck': {'cartas': ids, 'pools': []},
            'drops': {'pow': {cid: index+1 for index, cid in enumerate(ids)}},
        }},
        'iniciais': {'Inicial de teste': {'cartas': ids, 'pools': []}},
    })
    root = Studio()
    try:
        root.project, root.drafts = project, DraftSession(project)
        root._refresh_all()
        root.update()
        ed = root.mod_editor

        def check_stats(tree, *, weight_table=False):
            assert 'atk' in tree['columns'] and 'def' in tree['columns']
            assert tree.set(str(dragon), 'atk') == '12345678'
            assert tree.set(str(dragon), 'def') == '7654321'
            if tree.exists(str(god)):
                assert tree.set(str(god), 'atk') == '20000'
                assert tree.set(str(god), 'def') == '0'
            for cid in (spell, trap, ritual, equip):
                if tree.exists(str(cid)):
                    assert tree.set(str(cid), 'atk') == '—', cid
                    assert tree.set(str(cid), 'def') == '—', cid
            if weight_table:
                assert tree.set(str(dragon), 'peso') == '1'
                assert tree.set(str(spell), 'peso') == '3'
            else:
                assert tree.cget('selectmode').__str__() == 'extended'

        check_stats(ed.drops.tree, weight_table=True)
        assert ed.drops._sort_value(str(dragon), 'atk') == 12345678
        assert ed.drops._sort_value(str(spell), 'atk') == -1
        assert WEIGHT_COLUMNS == ('carta','nome','atk','def','peso','chance','chance_ps1')
        ed.drops.tree.selection_set([str(dragon), str(spell)])
        ed.drops.weight.set('12')
        ed.drops._apply()
        assert ed.drops.weights[dragon] == ed.drops.weights[spell] == 12
        check_stats(ed.drops.tree)
        assert ed.drops.tree.set(str(spell), 'peso') == '12'

        # A edição por duplo clique continua funcionando apesar do deslocamento
        # das colunas Peso/Chance pela inserção de ATK/DEF.
        root.tabs.select(root.tab_mod)
        ed.tabs.select(1)
        root.update()
        box = ed.drops.tree.bbox(str(dragon), 'peso')
        if box:
            # Clique no centro da célula para não acertar a borda da coluna anterior.
            ed.drops._edit_weight(SimpleNamespace(
                x=box[0] + box[2] // 2, y=box[1] + box[3] // 2))
            assert ed.drops.inline is not None
            ed.drops._close_inline()
        ed.drops.tree.selection_set([str(dragon), str(spell)])
        ed.drops._remove()
        assert dragon not in ed.drops.weights and spell not in ed.drops.weights

        # Tabelas normais do deck do rival (catálogo e cartas já presentes).
        for tree in (ed.opponent_deck.catalog, ed.opponent_deck.deck):
            check_stats(tree)
            assert ed.opponent_deck._deck_sort_value(str(dragon), 'atk') == 12345678
        assert ed.opponent_deck.deck.set(str(dragon), 'qtd') == '1'
        ed.opponent_deck.deck.selection_set([str(dragon), str(god)])
        ed.opponent_deck.quantity.set('2')
        ed.opponent_deck.change_card('set')
        assert ed.opponent_deck.deck.set(str(dragon), 'qtd') == '2'
        check_stats(ed.opponent_deck.deck)

        # Abas de decks iniciais usam exatamente o mesmo editor.
        ed.starter.set('Inicial de teste')
        ed._load_starter()
        root.update()
        for tree in (ed.starter_deck.catalog, ed.starter_deck.deck):
            check_stats(tree)
        assert ed.starter_deck.deck.set(str(dragon), 'qtd') == '1'

        # O modo drops do próprio deck mostra as mesmas estatísticas.
        with patch('tkinter.messagebox.showerror',
                   side_effect=lambda *args, **kw: (_ for _ in ()).throw(AssertionError(args))):
            ed.use_deck_drops.set(True)
            ed._toggle_deck_drops()
        check_stats(ed.deck_drop_table.tree)
        assert ed.deck_drop_table.tree.set(str(dragon), 'peso') == '1'

        # Pools do deck também exibem ATK/DEF e mantêm seleção múltipla.
        ed.opponent_deck.add_pool()
        ed.opponent_deck.table.load(ed.cards, {dragon: 7, spell: 3})
        check_stats(ed.opponent_deck.table.tree)
        ed.opponent_deck.remove_pool()

        # Atualização de atributo após salvar carta: as células mostram o valor atual.
        project.cards[dragon]['ataque'] = 54321
        ed.refresh_catalog()
        assert ed.opponent_deck.catalog.set(str(dragon), 'atk') == '54321'
        assert ed.opponent_deck.deck.set(str(dragon), 'atk') == '54321'
        assert ed.drops.tree.get_children() or ed.deck_drop_table.tree.get_children()
    finally:
        root.destroy()

print('GUI: ATK/DEF nos drops, deck inicial, deck oponente e pools; seleção e edição OK.')
