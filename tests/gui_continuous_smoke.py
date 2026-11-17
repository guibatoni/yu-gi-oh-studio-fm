"""Smoke UI v0.7.0, necessita monitor (xvfb no Linux)."""
from tempfile import TemporaryDirectory
from pathlib import Path
from fmstudio.gui import Studio, EffectDialog, FieldDialog
from fmstudio.core import Project
from fmstudio.drafts import DraftSession

with TemporaryDirectory() as td:
    root=Studio()
    p=Project.create(Path(td)/'mod','Teste contínuos')
    for cid, typ in ((1,0),(2,8),(3,19),(4,19)):
        p.cards[cid]={'id':cid,'nome':f'Carta {cid}','descricao':'',
            'ataque':1000,'defesa':1200,'tipo_id':typ,'atributo_id':0,'nivel':4,
            'guardian_1_id':0,'guardian_2_id':0,'valor_hex':'00000000','offset_no_slus':'0x0'}
    root.project=p; root.drafts=DraftSession(p); root._refresh_all(); root.update()
    dialog=EffectDialog(root,lambda e:root.drafts.add_effect(1,e))
    dialog._choice('acao','aura_tipo')
    # Fixe Fairy na primeira aura; o cenário Plant posterior deve medir só o bônus por contagem.
    dialog.type_combo.current(dialog.type_ids.index(8))
    dialog.type_combo.event_generate('<<ComboboxSelected>>')
    root.update()
    assert dialog.recipient.cget('text') == 'Monstros do tipo escolhido'
    assert not dialog.combos['alvo'].grid_info()
    dialog.vars['valor'].set('500');dialog.vars['valor_def'].set('300')
    dialog._submit();root.update()
    assert root.drafts.get_effects(1)[0]['acao']=='aura_tipo'
    f=FieldDialog(root,p,root.drafts,1)
    f.entries[1][2].set(f.display_by_id[2]);f._evaluate();root.update()
    logs=f.log.get('1.0','end')
    assert 'ATK +500' in logs,logs
    f.entries[0][2].set('— VAZIO —');f._evaluate();root.update()
    assert 'Nenhuma aura' in f.log.get('1.0','end')
    f.destroy()

    dialog = EffectDialog(root, lambda e: root.drafts.add_effect(1, e))
    dialog.combos['acao'].current(list(dialog.sources['acao']).index('bonus_por_tipo'))
    dialog.combos['acao'].event_generate('<<ComboboxSelected>>')
    root.update()
    assert dialog.recipient.cget('text') == 'Esta carta'
    assert not dialog.combos['alvo'].grid_info()
    assert dialog.labels['tipo_id'].cget('text') == 'Tipo contado no campo'
    assert dialog.type_combo.instate(('readonly', '!disabled'))
    dialog.type_combo.current(dialog.type_ids.index(19))
    dialog.type_combo.event_generate('<<ComboboxSelected>>')
    root.update()
    dialog._submit()
    bonus = root.drafts.get_effects(1)[-1]
    assert (bonus['alvo'], bonus['tipo_id'], bonus['escopo'], bonus['valor']) == ('proprio', 19, 'aliados', 500)
    root.drafts.save()
    reopened = Project.open(p.folder)
    board = [
        {**p.cards[1], 'lado': 'jogador', 'slot': 1, 'card_id': 1},
        {**p.cards[3], 'lado': 'jogador', 'slot': 2, 'card_id': 3, 'face_up': False},
        {**p.cards[4], 'lado': 'adversario', 'slot': 1, 'card_id': 4, 'face_up': False},
    ]
    result, _ = reopened.simulate_field(board)
    assert [row['ataque'] for row in result] == [1500, 1000, 1000]
    result, _ = reopened.simulate_field([board[0], board[2]])
    assert [row['ataque'] for row in result] == [1000, 1000]
    root.destroy()
print('GUI: aura e bônus próprio de +500 por Plant aliado virado para baixo conferidos.')
