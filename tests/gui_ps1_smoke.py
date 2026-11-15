"""Teste gráfico opcional do painel de compatibilidade, sem ROM real."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from fmstudio.gui import Studio
from fmstudio.core import Project
from fmstudio.drafts import DraftSession

with TemporaryDirectory() as d:
    root=Studio()
    proj=Project.create(Path(d)/'mod','Compatibilidade PS1')
    proj.cards[1]={'id':1,'nome':'Carta 1','descricao':'', 'raridade':'comum',
                   'ataque':1000,'defesa':1000,'tipo_id':0,'atributo_id':0,
                   'nivel':4,'guardian_1_id':0,'guardian_2_id':0}
    root.project=proj;root.drafts=DraftSession(proj)
    root._refresh_all();root.update()
    with patch('fmstudio.gui.messagebox.showinfo') as info:
        root.audit_ps1()
        assert info.called
    assert (proj.folder/'exportacao'/'compatibilidade_ps1.json').exists()
    root.destroy()
print('GUI v1.1.0: auditoria PS1 disponível e relatório gerado')
