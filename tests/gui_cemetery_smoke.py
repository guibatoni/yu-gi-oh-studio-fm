"""Teste de interface com Xvfb. Executar PYTHONPATH=. python tests/gui_cemetery_smoke.py."""
from pathlib import Path
from tempfile import TemporaryDirectory
from fmstudio.gui import Studio, EffectDialog
from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.lab_gui import AdvancedFieldDialog

with TemporaryDirectory() as tmp:
    studio=Studio()
    project=Project.create(Path(tmp)/'Mod','Teste')
    for cid,t in ((1,0),(2,0),(3,8)):
        project.cards[cid]={'id':cid,'nome':f'Carta {cid}','descricao':'','cor_nome':'#CBD5E1',
            'raridade':'comum','ataque':1000,'defesa':1000,'tipo_id':t,'atributo_id':0,
            'nivel':4,'guardian_1_id':0,'guardian_2_id':0,'valor_hex':'00000000','offset_no_slus':'0x0'}
    studio.project=project;studio.drafts=DraftSession(project);studio._refresh_all();studio.update()
    form=EffectDialog(studio,lambda e:studio.drafts.add_effect(1,e))
    form._choice('acao','bonus_cemiterio_tipo')
    form.vars['valor'].set('200');form.vars['valor_def'].set('100');form.vars['tipo_id'].set(0)
    form._submit();studio.update()
    assert studio.drafts.get_effects(1)[0]['acao']=='bonus_cemiterio_tipo'
    studio.quick_vars['ataque_primeiro_turno'].set(True)
    studio._on_quick_changed();studio.update()
    assert any(e['acao']=='ataque_primeiro_turno' for e in studio.drafts.get_effects(1))
    lab=AdvancedFieldDialog(studio,project,studio.drafts,1)
    lab.entries[1]['monster'].set(lab.by_id[2]);lab.evaluate()
    lab.target.set('Você slot 2')
    lab.remove_target()
    assert lab.lab.graveyards['jogador']==[2],lab.lab.graveyards
    assert lab.lab.resolve()[0][0]['ataque']==1200
    lab.destroy();studio.destroy()
print('GUI v1.0.3: cemitério, bônus dinâmico e habilidade rápida OK')
