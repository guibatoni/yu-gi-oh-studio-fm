"""Visual smoke v0.9: seleção de carta, habilidades rápidas e laboratório de ataque."""
from pathlib import Path
from tempfile import TemporaryDirectory
from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.gui import Studio
from fmstudio.lab_gui import AdvancedFieldDialog
from fmstudio.abilities import quick_settings

with TemporaryDirectory() as folder:
    root=Studio()
    project=Project.create(Path(folder)/'mod','Teste de habilidades')
    for cid in range(1,5):
        project.cards[cid]={'id':cid,'nome':f'Criatura {cid}', 'descricao':'',
            'ataque':1800 if cid==1 else 500,'defesa':1200, 'tipo_id':0,
            'atributo_id':0, 'nivel':4, 'guardian_1_id':0,'guardian_2_id':0}
    root.project=project
    root.drafts=DraftSession(project)
    root._refresh_all();root.update()
    root.tabs.select(root.tab_effects)
    root.quick_vars['ataques'].set(3)
    root._on_quick_changed()
    root.quick_vars['monstro_indestrutivel'].set(True)
    root._on_quick_changed()
    root.quick_vars['dano_perfurante'].set(True)
    root._on_quick_changed()
    root.quick_vars['custo_lp'].set('100')
    root.update()
    assert quick_settings(root.drafts.get_effects(1))['ataques']==3
    assert len(root.drafts.get_effects(1))==4
    root.drafts.save()
    assert root.project.effects['1'][0]['acao']=='ataques_multiplos'
    assert root.project.folder.joinpath('projeto.json').exists()
    root.tree.selection_set('2');root._on_card_select();root.update()
    assert root.quick_vars['ataques'].get()==1
    root.tree.selection_set('1');root._on_card_select();root.update()
    assert root.quick_vars['ataques'].get()==3
    lab=AdvancedFieldDialog(root,project,root.drafts,1)
    lab.entries[5]['monster'].set(lab.by_id[2])
    lab.entries[5]['face'].set(True)
    lab.evaluate()
    lab.deck_vars['jogador'].set('1,2')
    lab.battle_mode.set('defesa')
    lab.attack_target()
    assert lab.lab.lp['jogador']==7900, lab.lab.lp
    assert lab.lab.lp['adversario']==7400,lab.lab.lp
    lab.new_turn()
    lab.destroy()
    root.destroy()
print('GUI rápida e combate: OK')
