"""Smoke test by Xvfb for rarity and category names."""
from tempfile import TemporaryDirectory
from pathlib import Path
from fmstudio.core import Project
from fmstudio.gui import Studio
from fmstudio.drafts import DraftSession

with TemporaryDirectory() as d:
    ui=Studio()
    project=Project.create(Path(d)/'mod','Teste classes')
    common={'descricao':'', 'ataque':2500,'defesa':2000, 'atributo_id':0,'nivel':8,
            'guardian_1_id':1,'guardian_2_id':2}
    for cid,tid,title in [(1,0,'Dragão Raro'),(2,21,'Armadilha Rosa'),(3,20,'Magia Verde'),(4,23,'Equip Azul'),(5,24,'Deus Azul Marinho')]:
        project.cards[cid]=dict(common,id=cid,tipo_id=tid,nome=title)
    ui.project=project
    ui.drafts=DraftSession(project)
    ui._refresh_all(); ui.update()
    ui.vars['raridade'].set('lendaria — Lendária');ui.update()
    assert ui.preview.itemcget(ui.preview_name,'fill')=='#F04F57'
    ui.tree.selection_set('2');ui._on_card_select();ui.update()
    assert ui.preview.itemcget(ui.preview_name,'fill')=='#FF77C8'
    ui.tree.selection_set('3');ui._on_card_select();ui.update()
    assert ui.preview.itemcget(ui.preview_name,'fill')=='#48D995'
    ui.tree.selection_set('4');ui._on_card_select();ui.update()
    assert ui.preview.itemcget(ui.preview_name,'fill')=='#579DFF'
    ui.tree.selection_set('5');ui._on_card_select();ui.update()
    assert ui.preview.itemcget(ui.preview_name,'fill')=='#123A79'
    assert ui.preview.itemcget(ui.preview_name_plate,'state')=='normal'
    ui.tabs.select(ui.tab_cards)
    ui.update()
    ui.deiconify();ui.geometry('1390x825+0+0');ui.update()
    ui.tk.call('update')
    ui.destroy()
print('GUI rarity smoke: OK')
