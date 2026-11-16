"""Auditoria explícita do que pode ser transformado em BIN/CUE PS1.

'planejado' jamais é tratado como implementado no executável do console.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .tables import CARD_COUNT, SUPREME
from .ps1_content import name_patch_info, description_patch_info
from .core import ACTIONS, ModError, ps1_supports_god24
from .expanded import GOD_TYPE_ID
from .ps1_runtime import compile_effects
from .ps1_mod import LP_CODE, LP_BANK_END, compile_mod


def audit(project) -> dict:
    base=project.folder/'base'/'source_SLUS_014.11'
    exe=base.read_bytes() if base.is_file() else None
    pinned=project.metadata.get('base_sha256',{}).get('slus')
    known=bool(exe and pinned and hashlib.sha256(exe).hexdigest()==pinned)
    native_profile=known and ps1_supports_god24(project)
    wa_summary=project.folder/'base'/'resumo.json'
    wa_pinned=False
    if wa_summary.is_file():
        try:
            meta=json.loads(wa_summary.read_text(encoding='utf-8'))
            wa_pinned=bool((meta.get('source_sha256') or {}).get('DATA/WA_MRG.MRG'))
        except (ValueError,OSError):
            pass
    counts={'estatisticas':0,'nomes':0,'artes':0,'efeitos':0,'cartas_extras':len(project.new_cards),
            'descricoes':0,'classes_cores':0,'icones_especiais':0,'equipamentos_ps1':0,'equip_substituicoes':0,
            'rituais_ps1':0,'armadilhas_ps1':0,'terrenos_ps1':0,'limite_global_deck_ps1':0}
    mod_plan=compile_mod(project,profile=native_profile,wa_verified=wa_pinned)
    native_plan=compile_effects(project,native_profile,fixed_decks=mod_plan.fixed_decks)
    counts['nomes_tier_ps1'] = native_plan.name_colors
    counts['decks_fixos_ps1'] = len(native_plan.fixed_decks)
    blocked=[*native_plan.pending,*mod_plan.pending]; supported=list(mod_plan.applied)
    if native_profile:
        supported.append('Bloqueio de ataque na abertura com exceção por carta')
    supported.extend(f'Drops do deck do duelista #{opponent}' for opponent in native_plan.deck_drops)
    if native_plan.name_colors:
        supported.append(f'Cores de tier em {native_plan.name_colors} nomes de cartas no PS1')
    if native_plan.password_prefix is not None:
        supported.append(f'Passwords por ID no BIN/CUE com prefixo {native_plan.password_prefix:05d}')
    descriptions={}
    for key,edits in sorted(project.edits.items(),key=lambda item:int(item[0])):
        cid=int(key); current=project.get(cid)
        if current.get('virtual'):
            continue
        changed=set(edits)
        numeric=changed & {'ataque','defesa','tipo_id','atributo_id','nivel','guardian_1_id','guardian_2_id'}
        if numeric:
            typ=int(current.get('tipo_id',0))
            if cid>CARD_COUNT or typ>GOD_TYPE_ID or int(current.get('atributo_id',0))>5:
                blocked.append(f'#{cid}: carta adicional ou tipo/atributo incompatível com o PS1')
            elif typ == GOD_TYPE_ID and not native_profile:
                blocked.append(f'#{cid}: God 24 no PS1 exige o perfil Drop x15 vinculado ao projeto.')
            elif any(int(current.get(key,0)) == SUPREME for key in ('guardian_1_id','guardian_2_id')):
                blocked.append(f'#{cid}: Supreme usa uma Guardian Star do Studio.')
            elif any(
                    int(current[stat])>5110 or int(current[stat])%10
                    for stat in ('ataque','defesa')):
                blocked.append(f'#{cid}: ATK/DEF acima de 5110 ou não múltiplos de 10; apenas simulador')
            elif not known:
                blocked.append(f'#{cid}: SLUS original ainda não vinculado/verificado')
            else:
                counts['estatisticas']+=1
                supported.append(f'#{cid}: estatísticas de carta original')
                if typ == GOD_TYPE_ID:
                    supported.append(f'#{cid}: God 24 com nome, ícone e jogabilidade de monstro')
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
            if native_profile:
                descriptions[cid]=current.get('descricao','')
            elif known:
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
            if not native_profile or cid > CARD_COUNT:
                blocked.append(f'#{cid}: cores de tier no BIN/CUE exigem carta original e perfil Drop x15.')
    if descriptions:
        from .ps1_text import patch_descriptions
        catalog={cid:project.get(cid) for cid in project.cards}
        _,rows,icons,pending=patch_descriptions(exe,descriptions,catalog,start=native_plan.data_end,
                                               end=min(native_plan.bank_end, LP_CODE if mod_plan.has_lp else LP_BANK_END))
        counts['descricoes']=len(rows)
        counts['icones_especiais']=len(icons)
        for row in rows:
            supported.append(f'#{row["id"]}: descrição com cores e ícones')
        blocked.extend(pending)
    for key,rel in project.arts.items():
        cid=int(key)
        if cid>CARD_COUNT or str(cid) in project.new_cards:
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
                supported.append(f'{counts["equipamentos_ps1"]} alvo(s) de Equip a testar (bitmap MIPS automático se identificado; senão tabela stock)')
            else:
                blocked.append('Equipamentos PS1: importe BIN/CUE para registrar hashes SLUS e WA_MRG.')
    rituals=project.metadata.get('ps1_ritual_recipes',{})
    traps=project.metadata.get('ps1_trap_thresholds',{})
    terrain=project.metadata.get('ps1_terrain_boosts',{})
    from .ps1_native import patch_trap_thresholds, patch_terrain_boosts
    if rituals and not project.metadata.get('ps1_rituals_enabled',False):
        blocked.append(f'{len(rituals)} receita(s) de Ritual suspensa(s) no projeto; nenhuma será gravada no BIN')
    if rituals and project.metadata.get('ps1_rituals_enabled',False):
        counts['rituais_ps1']=len(rituals)
        if known and wa_pinned:
            supported.append(f'{len(rituals)} receita(s) de Ritual na tabela PS1 original')
        else:
            blocked.append('Rituais: SLUS e WA_MRG de origem precisam estar verificados')
    if traps:
        counts['armadilhas_ps1']=len(traps)
        if known:
            try:
                patch_trap_thresholds(exe,traps)
                supported.append(f'{len(traps)} limiar(es) de Trap original de ataque')
            except ModError as exc:
                blocked.append(f'Armadilhas PS1: {exc}')
        else:
            blocked.append('Armadilhas: SLUS original precisa ser verificado')
    if terrain:
        counts['terrenos_ps1']=len(terrain)
        if known:
            try:
                patch_terrain_boosts(exe,terrain)
                supported.append(f'{len(terrain)} bônus de campo por tipo na tabela PS1')
            except ModError as exc:
                blocked.append(f'Campo PS1: {exc}')
        else:
            blocked.append('Campos: SLUS original precisa ser verificado')
    global_copy_limit=project.metadata.get('ps1_deck_global_limit')
    if global_copy_limit is not None and int(global_copy_limit)!=3:
        from .ps1_effects_lab import deck_global_patch_probe
        if native_plan.copy_rules:
            counts['limite_global_deck_ps1']=1
            supported.append(f'Limite padrão de {native_plan.global_limit} cópias por ID e limites por carta')
        elif known:
            probe=deck_global_patch_probe(exe,global_copy_limit)
            if probe['status']=='candidato_unico_experimental':
                counts['limite_global_deck_ps1']=1
                supported.append(f'Limite global MIPS de {global_copy_limit} cópias por ID (EXPERIMENTAL; teste no ePSXe pendente)')
            else:
                blocked.append('Limite global PS1: '+probe['motivo'])
        else:
            blocked.append('Limite global MIPS de cópias exige SLUS original confirmado')
    counts['efeitos']=sum(map(len,project.effects.values()))
    counts['efeitos_nativos_ps1']=len(native_plan.accepted)
    supported.extend(f'#{cid}: {ACTIONS[action]} no PS1' for cid,action in native_plan.accepted)
    if project.new_cards:
        blocked.append(f'{len(project.new_cards)} carta(s) adicionais usam o catálogo do Studio.')
    return {
      'versao_relatorio':1,'status':'PARCIAL_PS1_NAO_TODOS_OS_EFEITOS',
      'slus_conferido':known,'wa_hash_registrado':wa_pinned,'contagens':counts,'gravavel_hoje':supported,
      'matriz_tecnica':{
        'atributos_originais':'gravavel_em_BIN_EXPERIMENTAL',
        'nomes_curtos_fonte_original':'gravavel_se_couber_no_espaco_original',
        'arte_e_miniatura_722':'gravavel_com_paleta_original_e_WA_verificado',
        'fusoes_original':'preservado_sem_edicao',
        'descricoes_coloridas':'Cores e ícones do jogo. Drop x15 também aceita ícones do Studio e realocação de texto.',
        'raridade_e_cor_nomes':'Cores de tier salvo por carta no Drop x15',
        'icones_personalizados':'Graváveis nas descrições no perfil Drop x15',
        'cartas_maiores_722':'PENDENTE_MIPS_MEMORIA_TABELAS',
        'tipo_god':'O tipo 24 ativa automaticamente o nome, o ícone e o roteamento de monstro no Drop x15.',
        'buffs_auras_cemiterio':'Bônus de campo com cartas viradas para baixo, deck inicial e cemitério no Drop x15',
        'equipamentos_imunidades':'Equipamentos com ATK e proteção, imunidades e indestrutibilidade no Drop x15',
        'rituais_tres_tributos_originais':'gravavel_na_tabela_WA_SEM_NOVOS_IDS',
        'armadilhas_ataque_681_686':'gravavel_no_SLUS_SE_TABELA_RETAIL',
        'bonus_terreno_tipo':'gravavel_no_SLUS_SE_TABELA_RETAIL',
        'ataque_2x_3x_piercing_haste':'Ataques 2x/3x e perfuração no Drop x15',
        'decks_e_regras_de_copias':'Deck fixo de 40 cartas ou pool de 40 compras no Drop x15',
        'descarte_e_dano_a_monstros':'PENDENTE_NOVAS_REGRAS',
      },
      'pendente_de_motor':blocked,
      'observacao':'Confira a lista de efeitos que o projeto pode gravar e as pendências desta base.',
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
        f'Efeitos com suporte no PS1: {counts.get("efeitos_nativos_ps1",0)} de {counts["efeitos"]}\n'
        f'Cartas adicionais: {counts["cartas_extras"]}\n\n'
        f'PENDÊNCIAS IDENTIFICADAS:\n{details}\n\n'
        'Para testar uma alteração no ePSXe, escolha uma carta original '
        '(#001–#722), mude seu ATK ou DEF, clique Salvar projeto e depois '
        'Gerar jogo BIN/CUE. O perfil Drop x15 também aceita as descrições '
        'com ícones e os efeitos compatíveis identificados no relatório.'
    )


def save_audit(project) -> Path:
    dest=project.folder/'exportacao'/'compatibilidade_ps1.json'
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(audit(project),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return dest
