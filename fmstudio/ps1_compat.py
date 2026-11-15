"""Auditoria explícita do que pode ser transformado em BIN/CUE PS1.

'planejado' jamais é tratado como implementado no executável do console.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .tables import CARD_COUNT
from .ps1_content import name_patch_info, description_patch_info
from .core import ModError


def audit(project) -> dict:
    base=project.folder/'base'/'source_SLUS_014.11'
    exe=base.read_bytes() if base.is_file() else None
    pinned=project.metadata.get('base_sha256',{}).get('slus')
    known=bool(exe and pinned and hashlib.sha256(exe).hexdigest()==pinned)
    wa_summary=project.folder/'base'/'resumo.json'
    wa_pinned=False
    if wa_summary.is_file():
        try:
            meta=json.loads(wa_summary.read_text(encoding='utf-8'))
            wa_pinned=bool((meta.get('source_sha256') or {}).get('DATA/WA_MRG.MRG'))
        except (ValueError,OSError):
            pass
    counts={'estatisticas':0,'nomes':0,'artes':0,'efeitos':0,'cartas_extras':len(project.new_cards),
            'descricoes':0,'classes_cores':0,'icones_especiais':0,'equipamentos_ps1':0,'equip_substituicoes':0}
    blocked=[]; supported=[]
    for key,edits in sorted(project.edits.items(),key=lambda item:int(item[0])):
        cid=int(key); current=project.get(cid)
        changed=set(edits)
        numeric=changed & {'ataque','defesa','tipo_id','atributo_id','nivel','guardian_1_id','guardian_2_id'}
        if numeric:
            if cid>CARD_COUNT or int(current.get('tipo_id',0))==24 or int(current.get('atributo_id',0))>5:
                blocked.append(f'#{cid}: atributos de carta virtual/God/atributo não original requerem patch de motor')
            elif not known:
                blocked.append(f'#{cid}: SLUS original ainda não vinculado/verificado')
            else:
                counts['estatisticas']+=1
                supported.append(f'#{cid}: estatísticas de carta original')
        if 'nome' in changed:
            if known:
                try:
                    name_patch_info(exe,cid,current.get('nome',''))
                    counts['nomes']+=1
                    supported.append(f'#{cid}: nome curto no banco original')
                except ModError as exc:
                    blocked.append(f'#{cid}: nome: {exc}')
            else:
                blocked.append(f'#{cid}: nome requer SLUS de origem confirmado')
        if 'descricao' in changed:
            if known:
                try:
                    names={i:project.get(i) for i in project.cards} if hasattr(project,'cards') else {cid:current}
                    description_patch_info(exe,cid,current.get('descricao',''),names)
                    counts['descricoes']+=1
                    supported.append(f'#{cid}: descrição curta com glifos/cores/ícones originais')
                except ModError as exc:
                    blocked.append(f'#{cid}: descrição: {exc}')
            else:
                blocked.append(f'#{cid}: descrição exige SLUS verificado')
        if changed & {'raridade','cor_nome'}:
            counts['classes_cores']+=1
            blocked.append(f'#{cid}: cor/raridade do nome não implementada no renderizador do PS1')
    for key,rel in project.arts.items():
        cid=int(key)
        if cid>CARD_COUNT:
            blocked.append(f'#{cid}: arte exige expansão de cards do console')
        elif not known or not wa_pinned:
            blocked.append(f'#{cid}: arte precisa de SLUS e WA_MRG.MRG de origem verificados')
        else:
            counts['artes']+=1
            supported.append(f'#{cid}: imagem e miniatura em paletas existentes (se WA validado)')
    equip_mode=project.metadata.get('ps1_equip_mode','adicionar')
    if equip_mode not in ('adicionar','substituir'):
        blocked.append('Modo Equip desconhecido; exportação será recusada')
    if equip_mode=='substituir':
        from .ps1_equip import _validated_replacements
        repl=_validated_replacements(project.metadata.get('ps1_equip_replacements',{}))
        counts['equip_substituicoes']=sum(len(v) for v in repl.values())
        if counts['equip_substituicoes']:
            if known and wa_pinned:
                supported.append(f'{counts["equip_substituicoes"]} troca(s) de alvo Equip sem expandir tabela')
            else:
                blocked.append('Troca Equip exige BIN e WA de origem verificados')
        if project.metadata.get('ps1_equip_additions'):
            blocked.append('Adições Equip salvas permanecem suspensas no modo substituição')
    else:
        native_equips=project.metadata.get('ps1_equip_additions',{})
        if native_equips:
            from .ps1_equip import _validated_plan
            plans=_validated_plan(native_equips)
            counts['equipamentos_ps1']=sum(len(v) for v in plans.values())
            if known and wa_pinned:
                supported.append(f'{counts["equipamentos_ps1"]} alvo(s) de Equip original para gravar em WA_MRG.MRG')
            else:
                blocked.append('Equipamentos PS1: importe BIN/CUE para registrar hashes SLUS e WA_MRG.')
    for key,items in project.effects.items():
        if items:
            counts['efeitos']+=len(items)
            blocked.append(f'#{key}: {len(items)} efeito(s) sem rotina MIPS compilada no PS1')
    if project.new_cards:
        blocked.append(f'{len(project.new_cards)} carta(s) #723+: expansão de estruturas/reserva de IDs pendente')
    return {
      'versao_relatorio':1,'status':'PARCIAL_PS1_NAO_TODOS_OS_EFEITOS',
      'slus_conferido':known,'wa_hash_registrado':wa_pinned,'contagens':counts,'gravavel_hoje':supported,
      'matriz_tecnica':{
        'atributos_originais':'gravavel_em_BIN_EXPERIMENTAL',
        'nomes_curtos_fonte_original':'gravavel_se_couber_no_espaco_original',
        'arte_e_miniatura_722':'gravavel_com_paleta_original_e_WA_verificado',
        'fusoes_original':'preservado_sem_edicao',
        'descricoes_coloridas':'gravavel_se_curta_e_usar_somente_glifos_F8_originais',
        'raridade_e_cor_nomes':'PENDENTE',
        'icones_personalizados':'PENDENTE',
        'cartas_maiores_722':'PENDENTE_MIPS_MEMORIA_TABELAS',
        'tipo_god':'PENDENTE_MIPS_UI',
        'buffs_auras_cemiterio':'PENDENTE_MIPS_EVENTOS',
        'equipamentos_imunidades':'PENDENTE_MIPS_REGRAS; alvos de Equip stock podem ser gravados',
        'ataque_2x_3x_piercing_haste':'PENDENTE_MIPS_COMBATE',
        'decks_e_regras_de_copias':'PENDENTE_MIPS_DECKBUILDER',
        'descarte_e_dano_a_monstros':'PENDENTE_NOVAS_REGRAS',
      },
      'pendente_de_motor':blocked,
      'observacao':'BIN/CUE gerado é build parcial, NUNCA valida efeitos ou novas cartas como jogáveis.',
    }


def explain_no_writable_changes(project, report: dict) -> str:
    """Explica por que edições salvas não geraram bytes modificáveis no PS1."""
    counts = report['contagens']
    edited = len(project.edits)
    pending = report['pendente_de_motor']
    details = '\n'.join('• ' + line for line in pending[:5])
    if len(pending) > 5:
        details += f'\n• ... e mais {len(pending) - 5} pendências'
    if not details:
        details = '• Nenhuma diferença gravável encontrada nos dados originais.'
    return (
        f'O projeto tem {edited} carta(s) com edições salvas, mas nenhuma '
        'alteração compatível gerou bytes novos para o PS1.\n\n'
        f'Classes/cores alteradas: {counts["classes_cores"]}\n'
        f'Efeitos apenas no simulador: {counts["efeitos"]}\n'
        f'Cartas adicionais: {counts["cartas_extras"]}\n\n'
        f'PENDÊNCIAS IDENTIFICADAS:\n{details}\n\n'
        'Para testar uma alteração no ePSXe, escolha uma carta original '
        '(#001–#722), mude seu ATK ou DEF, clique Salvar projeto e depois '
        'Gerar jogo BIN/CUE.\n\n'
        'Raridades, cores de nomes, efeitos, ícones personalizados e cartas '
        'adicionais ainda não são executados pelo motor do PS1.'
    )


def save_audit(project) -> Path:
    dest=project.folder/'exportacao'/'compatibilidade_ps1.json'
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(audit(project),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return dest
