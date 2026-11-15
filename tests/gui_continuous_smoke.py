"""Smoke UI v0.7.0, necessita monitor (xvfb no Linux)."""
from tempfile import TemporaryDirectory
from pathlib import Path
from fmstudio.gui import Studio, EffectDialog, FieldDialog
from fmstudio.core import Project
from fmstudio.drafts import DraftSession

with TemporaryDirectory() as td:
    root=Studio()
    p=Project.create(Path(td)/'mod','Teste contínuos')
    for cid, typ in ((1,0),(2,8),(3,8)):
        p.cards[cid]={'id':cid,'nome':f'Carta {cid}','descricao':'',
            'ataque':1000,'defesa':1200,'tipo_id':typ,'atributo_id':0,'nivel':4,
            'guardian_1_id':0,'guardian_2_id':0,'valor_hex':'00000000','offset_no_slus':'0x0'}
    root.project=p; root.drafts=DraftSession(p); root._refresh_all(); root.update()
    dialog=EffectDialog(root,lambda e:root.drafts.add_effect(1,e))
    dialog._choice('acao','aura_tipo')
    dialog.vars['valor'].set('500');dialog.vars['valor_def'].set('300')
    dialog._submit();root.update()
    assert root.drafts.get_effects(1)[0]['acao']=='aura_tipo'
    f=FieldDialog(root,p,root.drafts,1)
    f.entries[1][2].set(f.display_by_id[2]);f._evaluate();root.update()
    logs=f.log.get('1.0','end')
    assert 'ATK +500' in logs,logs
    f.entries[0][2].set('— VAZIO —');f._evaluate();root.update()
    assert 'Nenhuma aura' in f.log.get('1.0','end')
    f.destroy();root.destroy()
print('GUI: editor de efeitos e campo 5x5 operacionais')
