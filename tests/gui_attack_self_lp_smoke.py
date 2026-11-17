"""Testa o formulário do efeito de dano ao controlador no ataque sob Xvfb."""
from pathlib import Path
from tempfile import TemporaryDirectory
from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.gui import Studio, EffectDialog
from fmstudio.ps1_runtime import compile_effects

with TemporaryDirectory() as tmp:
    project=Project.create(Path(tmp)/'attack-recoil', 'Dano controlador')
    cid=1
    project.cards[cid] = {'id':cid, 'nome':'Monstro com dano próprio',
        'descricao':'', 'ataque':1200, 'defesa':800,
        'tipo_id':0, 'atributo_id':0, 'nivel':4,
        'guardian_1_id':0, 'guardian_2_id':0}
    project.save()
    root=Studio()
    try:
        root.project=project
        root.drafts=DraftSession(project)
        root._refresh_all()
        root.update()
        dialog=EffectDialog(root, lambda e: root.drafts.add_effect(cid,e))
        dialog._choice('evento','atacar')
        dialog._choice('acao','dano_lp')
        dialog._choice('alvo','proprio')
        dialog.vars['valor'].set('500')
        dialog._refresh_controls()
        assert 'CONTROLADOR perde X LP' in dialog.help.cget('text')
        dialog._submit()
        recorded=root.drafts.get_effects(cid)
        assert len(recorded)==1, recorded
        assert (recorded[0]['evento'],recorded[0]['acao'],recorded[0]['alvo'],recorded[0]['valor'])==(
            'atacar','dano_lp','proprio',500)
        root.drafts.save()
        saved=Project.open(project.folder)
        assert saved.effects[str(cid)][0]['valor']==500
        # A carta sintética está no catálogo em memória; o projeto reaberto
        # confirma a persistência da regra, não a extração de uma ISO de teste.
        native=compile_effects(project,True)
        assert (cid,'dano_lp') in native.accepted
        assert not native.pending
        print('GUI: Ao atacar + Dano LP + Próprio salva e compila como custo PS1.')
    finally:
        root.destroy()
