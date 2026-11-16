"""Open the new editor, save settings, and play a turn in a real Tk window."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.duel_gui import MatchDialog
from fmstudio.gui import Studio
from fmstudio.mod_data import CONFIG_KEY, save_rules
from fmstudio.tables import SUPREME


with TemporaryDirectory() as temp:
    project = Project.create(Path(temp)/'teste', 'Teste de partida')
    hero = project.add_card(name='Guardião Supremo')
    enemy = project.add_card(name='Rival')
    project.add_card(type_id=20, name='Magia')
    huge = 10**90
    project.set_card(hero, {'ataque':huge,'defesa':huge+22,'guardian_1_id':SUPREME})
    project.set_card(enemy, {'ataque':1800,'defesa':1100,'guardian_1_id':7})
    save_rules(project, {'duelistas':{'1':{'deck':{'cartas':[enemy]*3}}},
                         'iniciais':{'Perfil de teste':{'cartas':[hero]*3}}})
    root = Studio()
    root.project, root.drafts = project, DraftSession(project)
    root._refresh_all()
    root.filter_star.set('16 — ✦ Supreme')
    root.update()
    assert root.tree.get_children() == (str(hero),)
    assert 'Supreme' in root.preview.itemcget(root.preview_stars,'text')
    root.tabs.select(root.tab_mod)
    editor = root.mod_editor
    with patch('tkinter.messagebox.showerror', side_effect=lambda *a,**kw: (_ for _ in ()).throw(AssertionError(a))):
        editor.drops.selected.set(str(hero))
        editor.drops.weight.set('37')
        editor.drops._apply()
        assert project.metadata[CONFIG_KEY]['duelistas']['1']['drops']['pow'][hero] == 37
        editor.player_lp.set(str(huge))
        editor.opponent_lp.set(str(huge+100))
        editor.save_lp()
        editor.starter.set('Perfil de teste')
        editor.start_match()
        root.update()
        dialog = next(child for child in root.winfo_children() if isinstance(child, MatchDialog))
        assert dialog.game.lp['jogador'] == huge
        assert '…' in dialog.lp_text['jogador'].get()
        assert dialog.zones['mao'].get_children() == (str(hero),)
        selected = next(i for i,a in enumerate(dialog.built_plays) if a.position == 'ataque')
        dialog.play_select.current(selected)
        dialog._play()
        dialog.fields['jogador'].selection_set('1')
        dialog._attack(True)
        assert dialog.game.lp['adversario'] == 100
        assert 'Dano' in dialog.output.get('1.0','end')
    root.destroy()
print('GUI: Supreme, filtros, drops, LP altos e duelo com ataque no primeiro turno.')
