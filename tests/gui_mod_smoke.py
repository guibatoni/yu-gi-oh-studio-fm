"""Open the new editor, save settings, and play a turn in a real Tk window."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.duel_gui import MatchDialog
from fmstudio.gui import Studio
from fmstudio.mod_data import CONFIG_KEY, DROP_FROM_DECK, save_rules
from fmstudio.mod_tools_gui import PasswordsDialog
from fmstudio.passwords import chest_cards
from fmstudio.tables import SUPREME


with TemporaryDirectory() as temp:
    project = Project.create(Path(temp)/'teste', 'Teste de partida')
    hero = project.add_card(name='Guardião Supremo')
    enemy = project.add_card(name='Rival')
    secret = project.add_card(type_id=24, name='God de teste')
    huge = 10**90
    project.set_card(hero, {'ataque':huge,'defesa':huge+22,'guardian_1_id':SUPREME})
    project.set_card(enemy, {'ataque':1800,'defesa':1100,'guardian_1_id':7})
    project.add_effect(hero, {'acao':'ataque_primeiro_turno', 'evento':'continuo', 'alvo':'proprio', 'valor':0})
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
        editor.use_deck_drops.set(True)
        editor._toggle_deck_drops()
        assert project.metadata[CONFIG_KEY]['duelistas']['1'][DROP_FROM_DECK]
        assert editor.deck_drop_table.tree.get_children() == (str(enemy),)
        assert editor.deck_drop_table.weights == {enemy: 1}
        editor.mod_lp.set(str(huge))
        editor.save_lp()
        editor.ps1_ai_choice.set('Normal — IA original')
        editor.save_ps1_ai()
        assert project.metadata[CONFIG_KEY]['ia_ps1'] == 'normal'
        editor.ps1_ai_choice.set('Difícil — IA aprimorada')
        editor.save_ps1_ai()
        assert project.metadata[CONFIG_KEY]['ia_ps1'] == 'dificil'
        editor.starter.set('Perfil de teste')
        editor.start_match()
        root.update()
        dialog = next(child for child in root.winfo_children() if isinstance(child, MatchDialog))
        assert dialog.game.lp['jogador'] == huge
        assert dialog.game.lp['adversario'] == huge
        assert '…' in dialog.lp_text['jogador'].get()
        assert dialog.zones['mao'].get_children() == (str(hero),)
        dialog._open_passwords()
        passwords = next(child for child in dialog.winfo_children() if isinstance(child, PasswordsDialog))
        passwords.into_starter.set(True)
        passwords.ids.query.set(f'#{secret}')
        passwords.ids.redeem()
        assert project.metadata[CONFIG_KEY]['iniciais']['Deck do baú']['cartas'] == [secret]
        passwords.destroy()
        selected = next(i for i,a in enumerate(dialog.built_plays) if a.position == 'ataque')
        dialog.play_select.current(selected)
        dialog._play()
        dialog.fields['jogador'].selection_set('1')
        dialog._attack(True)
        assert dialog.game.lp['adversario'] == 0
        assert 'Dano' in dialog.output.get('1.0','end')
        dialog.game.lp['adversario'] = 0
        dialog.render()
        assert dialog.rank.get().startswith('S-POW ')
        dialog._roll_drop()
        assert 'Rival' in dialog.reward.cget('text')
        assert chest_cards(Project.open(project.folder)) == {str(enemy): 1, str(secret): 1}
    root.destroy()
print('GUI: Supreme, filtros, drops, LP altos e ataque de abertura com habilidade.')
