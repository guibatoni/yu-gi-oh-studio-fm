"""Smoke da edição in-place dos efeitos do Cortex (executar sob Xvfb no Linux)."""
from pathlib import Path
from tempfile import TemporaryDirectory

from fmstudio.core import Project
from fmstudio.drafts import DraftSession
from fmstudio.gui import Studio, EffectDialog, SpecificCardEffectDialog


with TemporaryDirectory() as td:
    root = Studio()
    try:
        project = Project.create(Path(td) / 'mod', 'Testar edição de efeito')
        template = {'descricao': '', 'ataque': 1000, 'defesa': 1200,
                    'tipo_id': 19, 'atributo_id': 0, 'nivel': 4,
                    'guardian_1_id': 0, 'guardian_2_id': 0,
                    'valor_hex': '00000000', 'offset_no_slus': '0x0'}
        for cid in (1, 2, 35):
            project.cards[cid] = {'id': cid, 'nome': f'Carta {cid}', **template}
        root.project = project
        root.drafts = DraftSession(project)
        root._refresh_all()
        root.update()

        root.drafts.add_effect(1, {'evento': 'invocar', 'acao': 'cura_lp',
                                   'alvo': 'proprio', 'valor': 2000,
                                   'observacao': 'original'})
        root.drafts.add_effect(1, {'evento': 'continuo', 'acao': 'bonus_por_tipo',
                                   'alvo': 'proprio', 'tipo_id': 19, 'valor': 500,
                                   'valor_def': 100, 'escopo': 'aliados',
                                   'atributo_id': 0})
        root.drafts.add_effect(1, {'evento': 'continuo', 'acao': 'bonus_por_carta_id',
                                   'alvo': 'proprio', 'carta_referencia_id': 2,
                                   'origem_contagem': 'campo', 'valor': 200,
                                   'valor_def': 0, 'escopo': 'aliados'})
        root.drafts.add_effect(1, {'evento': 'continuo', 'acao': 'ataque_primeiro_turno',
                                   'alvo': 'proprio', 'valor': 0})
        root._refresh_effects()

        # O botão deve carregar a regra atual em vez de criar outra.
        root.effect_tree.selection_set('0')
        dialog = root.edit_effect()
        assert isinstance(dialog, EffectDialog)
        assert dialog.title() == 'Editar efeito — Studio FM'
        assert dialog.vars['acao'].get() == 'cura_lp'
        assert dialog.vars['valor'].get() == '2000'
        assert dialog.vars['observacao'].get() == 'original'
        dialog.vars['valor'].set('3000')
        dialog._submit()
        root.update()
        assert len(root.drafts.get_effects(1)) == 4
        assert root.drafts.get_effects(1)[0]['valor'] == 3000
        assert root.effect_tree.selection() == ('0',)

        # Preserve combo de tipo/atributo/escopo e ATK/DEF.
        root.effect_tree.selection_set('1')
        dialog = root.edit_effect()
        assert dialog.vars['tipo_id'].get() == 19
        assert dialog.vars['atributo_id'].get() == 0
        assert dialog.vars['escopo'].get() == 'aliados'
        assert (dialog.vars['valor'].get(), dialog.vars['valor_def'].get()) == ('500', '100')
        dialog.vars['valor'].set('750')
        dialog._submit()
        root.update()
        assert root.drafts.get_effects(1)[1]['valor'] == 750

        # Modal especial continua editável e não altera descrição ao salvar.
        root.effect_tree.selection_set('2')
        dialog = root.edit_effect()
        assert isinstance(dialog, SpecificCardEffectDialog)
        assert dialog.labels[dialog.selected.get()] == 2
        assert dialog.origin.get() == 'campo'
        dialog.origin.set('deck')
        dialog.attack.set('450')
        dialog.submit()
        root.update()
        assert root.drafts.get_effects(1)[2]['origem_contagem'] == 'deck'
        assert root.drafts.get_effects(1)[2]['valor'] == 450

        # Atalho de combate pode ser editado sem mudar a regra de outra linha.
        root.effect_tree.selection_set('3')
        dialog = root.edit_effect()
        assert isinstance(dialog, EffectDialog)
        assert dialog.vars['acao'].get() == 'ataque_primeiro_turno'
        assert dialog.vars['valor'].get() == '0'
        dialog._choice('acao', 'ataques_multiplos')
        dialog.vars['valor'].set('2')
        dialog._submit()
        root.update()
        assert root.drafts.get_effects(1)[3]['acao'] == 'ataques_multiplos'
        assert root.drafts.get_effects(1)[3]['valor'] == 2

        # Cancelar não escreve no rascunho.
        previous = root.drafts.get_effects(1)
        root.effect_tree.selection_set('0')
        dialog = root.edit_effect()
        dialog.vars['valor'].set('9000')
        dialog.destroy()
        assert root.drafts.get_effects(1) == previous
        assert project.effects == {}
        assert root.save_project() is True
        stored = Project.open(project.folder).effects['1']
        assert len(stored) == 4
        assert [effect['valor'] for effect in stored] == [3000, 750, 450, 2]
        print('GUI: botão Editar efeito, preenchimento, bônus específico, habilidade, cancelar e salvar OK.')
    finally:
        root.destroy()
