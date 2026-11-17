"""Smoke: compras vazias de pool e preenchimento automático no deck do rival."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fmstudio.core import ModError, Project
from fmstudio.drafts import DraftSession
from fmstudio.gui import Studio
from fmstudio.mod_data import CONFIG_KEY
from fmstudio.tables import DECK_SIZE


with TemporaryDirectory() as temp:
    project = Project.create(Path(temp) / 'mod', 'Correção Compras')
    ids = [project.add_card(name=f'Monstro {i}') for i in range(21)]
    root = Studio()
    try:
        root.project, root.drafts = project, DraftSession(project)
        root._refresh_all()
        root.update()
        editor = root.mod_editor.opponent_deck

        # Cenário da captura: pool com pesos já preenchidos, Compras vazio.
        weighted = {cid: (100 if i == 0 else 20) for i, cid in enumerate(ids)}
        editor.load(project.cards, {
            'cartas': [], 'pools': [{'compras': '', 'pesos': weighted}],
        })
        assert editor.draws.get() == ''
        assert editor._pool_slots() == DECK_SIZE
        assert editor.profile()['pools'][0]['compras'] == DECK_SIZE
        assert editor.draws.get() == '40'
        with patch('tkinter.messagebox.showerror',
                   side_effect=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(args))):
            root.mod_editor.save_opponent()
        saved = project.metadata[CONFIG_KEY]['duelistas']['1']['deck']
        assert saved['pools'][0]['compras'] == 40
        assert saved['pools'][0]['pesos'] == weighted
        assert saved['cartas'] == []
        assert Project.open(project.folder).metadata[CONFIG_KEY]['duelistas']['1']['deck'] == saved

        # Se o Spinbox ficar temporariamente vazio, preservar o valor salvo.
        editor.draws.set('')
        editor._stage()
        assert editor.draws.get() == '40'
        assert editor.rows[0]['compras'] == 40

        # Um valor definido pelo autor, diferente de 40, não é substituído.
        editor.draws.set('17')
        editor._stage()
        editor.draws.set('')
        assert editor.profile()['pools'][0]['compras'] == 17
        assert editor.draws.get() == '17'

        # Erros reais continuam claros e não alteram o último valor válido.
        editor.draws.set('abc')
        before = editor.rows[0]['compras']
        try:
            editor.profile()
        except ModError as exc:
            assert 'Compras do pool' in str(exc), str(exc)
        else:
            raise AssertionError('Compras inválidas deveriam ser rejeitadas')
        assert editor.rows[0]['compras'] == before

        # O botão Completar vagas considera as cartas fixas e outros pools.
        editor.load(project.cards, {'cartas': ids[:5], 'pools': [
            {'compras': 5, 'pesos': weighted},
        ]})
        editor._complete_pool_draws()
        assert editor.draws.get() == '35'
        assert editor._pool_slots() == 35

        # Pool recém-preenchida diretamente, sem pressionar + Pool:
        # o editor cria a primeira pool com todas as vagas restantes.
        editor.load(project.cards, {'cartas': [], 'pools': []})
        editor.table.load(project.cards, weighted)
        assert editor.pool.get() == ''
        assert editor.profile()['pools'][0]['compras'] == 40
        assert editor.pool.get() == 'Pool 1'
    finally:
        root.destroy()

print('GUI pool: compras 40 automáticas, pesos preservados, edição vazia, botão completar, salvamento OK.')
