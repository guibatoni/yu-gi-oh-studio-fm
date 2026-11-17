"""GUI smoke with no ROM: new card, God type, icons, markup and effect by ID."""
from tempfile import TemporaryDirectory
from pathlib import Path
from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.gui import Studio
from fmstudio.mod_gui import NewCardDialog
from fmstudio.expanded import display_name
from fmstudio.richtext import CUSTOM_ICONS

with TemporaryDirectory() as d:
    root=Studio()
    project=Project.create(Path(d)/'project','Test v1.0')
    project.cards[1]={'id':1,'nome':'Blue-Eyes White Dragon','descricao':'',
        'ataque':3000,'defesa':2500,'tipo_id':0,'atributo_id':0,
        'nivel':8,'guardian_1_id':0,'guardian_2_id':0}
    root.project=project;root.drafts=DraftSession(project)
    root._refresh_all();root.update()
    root.add_new_card();root.update()
    dialog=next(child for child in root.winfo_children() if isinstance(child,NewCardDialog))
    dialog.create();root.update()
    assert root.selected_id==723,root.selected_id
    assert len(root.project.cards)==2
    assert root.get_icon_image('perfurar').width()==16
    root.vars['nome'].set('Deus do Milênio')
    root.vars['tipo_id'].set('24 — God')
    root.description.insert('end','{color:vermelho}Divino{/color} {icon:indestrutivel} {card:1}')
    root.render_description();root.update()
    assert 'Blue-Eyes White Dragon' in root.description_preview.get('1.0','end')
    root.tabs.select(root.tab_effects)
    # Add effect directly as if saved through the quick specialized dialog
    root.drafts.add_effect(723,{'evento':'continuo','acao':'bonus_por_carta_id','alvo':'proprio',
        'valor':200,'valor_def':0,'carta_referencia_id':1,'origem_contagem':'campo','escopo':'aliados'})
    root._refresh_effects();root.update()
    assert any('Blue-Eyes' in str(root.effect_tree.item(x,'values')) for x in root.effect_tree.get_children())
    root.save_project();root.update()
    reopened = Project.open(project.folder)
    assert reopened.get(723)['nome'] == 'Deus do Milênio'
    assert reopened.get(723)['tipo_id'] == 24
    root.filter.set('divino god')
    assert root.tree.get_children() == ('723',)
    assert root.mod_editor.opponent_deck.catalog.exists('723')
    root.destroy()
print('GUI expansion: OK')
