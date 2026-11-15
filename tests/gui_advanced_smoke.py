"""GUI v0.8 - execução em servidor gráfico virtual."""
from pathlib import Path
from tempfile import TemporaryDirectory

from fmstudio.gui import Studio, EffectDialog
from fmstudio.lab_gui import AdvancedFieldDialog
from fmstudio.core import Project
from fmstudio.drafts import DraftSession

with TemporaryDirectory() as td:
    root=Studio()
    p=Project.create(Path(td)/'teste','Teste avançado')
    for cid, typ in [(1,0),(2,8),(3,8),(4,0)]:
        p.cards[cid]={
            'id':cid,'nome':f'Carta {cid}','descricao':'','ataque':1000,'defesa':1200,
            'tipo_id':typ,'atributo_id':0,'nivel':4,
            'guardian_1_id':0,'guardian_2_id':0,'valor_hex':'00000000','offset_no_slus':'0x0'}
    root.project=p
    root.drafts=DraftSession(p)
    root._refresh_all()
    root.update()
    dlg=EffectDialog(root,lambda entry:root.drafts.add_effect(1,entry))
    dlg._choice('acao','cura_lp_deck_tipo')
    dlg.vars['valor'].set('100')
    dlg.vars['tipo_id'].set(8)
    dlg._submit()
    root.update()
    assert root.drafts.get_effects(1)[0]['acao']=='cura_lp_deck_tipo'

    dlg2=EffectDialog(root,lambda entry:root.drafts.add_effect(3,entry))
    dlg2._choice('acao','equip_indestrutivel')
    dlg2._submit()
    root.update()
    assert root.drafts.get_effects(3)[0]['evento']=='equipado'
    lab=AdvancedFieldDialog(root,p,root.drafts,1)
    lab.deck_vars['jogador'].set('2x2,3')
    lab.entries[0]['equip'].set(lab.by_id[3])
    lab.evaluate()
    assert lab.lab.resolve()[0][0]['indestrutivel']
    lab.trigger()
    assert lab.lab.lp['jogador']==8300
    lab.reset_state()
    assert lab.lab.lp['jogador']==8000
    lab.destroy()
    root.destroy()
print('GUI avançada: editor de efeitos, equipamentos, deck e gatilho aprovados')
