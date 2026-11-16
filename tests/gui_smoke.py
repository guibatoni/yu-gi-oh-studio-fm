"""Verificação manual/CI sob xvfb: navegação sem prompts e cores no nome."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from fmstudio.gui import Studio
from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.rarities import DEFAULT_RARITY, RARITIES

with TemporaryDirectory() as temp:
    root = Studio()
    root.withdraw()
    p = Project.create(Path(temp)/'mod', 'Projeto teste')
    for cid in (1,2,3):
        p.cards[cid] = {
            'id':cid, 'nome':'Blue-Eyes' if cid==1 else f'Carta {cid}', 'descricao':'Uma descrição',
            'ataque':3000 if cid==1 else 1000, 'defesa':2500, 'tipo_id':1, 'atributo_id':1,
            'nivel':8, 'guardian_1_id':1, 'guardian_2_id':2,
            'valor_hex':'00000000', 'offset_no_slus':'0x000',
        }
    root.project=p
    root.drafts=DraftSession(p)
    root._refresh_all()
    root.update()
    root.vars['nome'].set('Dragão Vermelho')
    root.vars['cor_nome'].set('#FF3355')
    root.vars['ataque'].set('3500')
    with patch('fmstudio.gui.messagebox.askyesnocancel', side_effect=AssertionError('Prompt durante seleção')):
        root.tree.selection_set('2')
        root._on_card_select()
        root.tree.selection_set('1')
        root._on_card_select()
    assert root.vars['nome'].get()=='Dragão Vermelho',root.vars['nome'].get()
    assert root.vars['cor_nome'].get()=='#FF3355'
    assert root.vars['ataque'].get()=='3500'
    assert root.preview.itemcget(root.preview_name,'fill')==RARITIES[DEFAULT_RARITY][1]
    assert root.drafts.count==1,root.drafts.count
    assert not p.edits
    root.deiconify()
    root.tabs.select(root.tab_cards)
    root.update()
    assert root.save_project()
    assert p.edits['1']['cor_nome']=='#FF3355'
    assert not root.drafts.is_dirty
    root.destroy()
print('Interface: navegação, cor da classe e persistência da cor legada: OK')
