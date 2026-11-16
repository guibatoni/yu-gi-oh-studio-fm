"""Constrói cópia de teste MODE2/2352 sem reempacotar XA/MDEC e sem alterar originais.

Somente substitui bytes da ISO9660 SLUS_014.11 quando o executável gerado
mantém o mesmo tamanho. Atualiza EDC+ECC para cada setor Mode2/Form1 alterado.
Não implementa efeitos, textos, novas cartas ou fusões no motor de PS1.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
import tempfile
import hashlib
import json
from pathlib import Path
import shutil
import struct

from .core import ModError
from .disc import DiscReader, DiscError, SYNC

RAW_SECTOR = 2352
PAYLOAD = 2048
_EDC_POLY = 0xD8018001


def _tables():
    fwd = []
    bwd = [0] * 256
    edc = []
    for v in range(256):
        f = ((v << 1) ^ (0x1D if v & 0x80 else 0)) & 0xFF
        fwd.append(f)
        bwd[v ^ f] = v
        x = v
        for _ in range(8):
            x = (x >> 1) ^ (_EDC_POLY if x & 1 else 0)
        edc.append(x)
    return fwd, bwd, edc


_ECC_F, _ECC_B, _EDC_TABLE = _tables()


def _edc(buf: bytes) -> int:
    result = 0
    for item in buf:
        result = (result >> 8) ^ _EDC_TABLE[(result ^ item) & 0xFF]
    return result


def _ecc_block(data: bytes, majors: int, minors: int, mult: int, inc: int) -> bytes:
    size = majors * minors
    if len(data) < size:
        raise ValueError('Bloco ECC menor do que o esperado')
    parity = bytearray(majors * 2)
    for major in range(majors):
        offset = ((major >> 1) * mult) + (major & 1)
        a = b = 0
        for _ in range(minors):
            v = data[offset]
            offset += inc
            if offset >= size:
                offset -= size
            a ^= v
            b ^= v
            a = _ECC_F[a]
        a = _ECC_B[_ECC_F[a] ^ b]
        parity[major] = a
        parity[major + majors] = a ^ b
    return bytes(parity)


def regenerate_form1(sector: bytes) -> bytes:
    """Recalcula EDC/ECC Mode2 Form1 sem trocar header, subheader ou dados."""
    if (len(sector) != RAW_SECTOR or sector[:12] != SYNC or sector[15] != 2
            or sector[18] & 0x20 or sector[16:20] != sector[20:24]):
        raise ModError('Setor não é Mode2 Form1 válido; patch abortado')
    out = bytearray(sector)
    struct.pack_into('<I', out, 2072, _edc(out[16:2072]))
    # Em Mode2, os 4 bytes de endereço entram zerados no cálculo ECC.
    psource = bytes(4) + out[16:2076]
    out[2076:2248] = _ecc_block(psource, 86, 24, 2, 86)
    qsource = bytes(4) + out[16:2248]
    out[2248:2352] = _ecc_block(qsource, 52, 43, 86, 88)
    return bytes(out)


def _write_file_patches(out, entry, original: bytes, patched: bytes) -> list[int]:
    """Atualiza arquivo ISO9660 in-place; tamanho e bytes-base devem coincidir."""
    if len(original) != entry.size or len(patched) != entry.size:
        raise ModError(f'{entry.path}: alteração de tamanho não é permitida.')
    changed=[]
    for i in range((entry.size + PAYLOAD-1)//PAYLOAD):
        start=i*PAYLOAD
        before=original[start:start+PAYLOAD]
        after=patched[start:start+PAYLOAD]
        if before == after: continue
        lba=entry.extent+i
        out.seek(lba*RAW_SECTOR)
        raw=out.read(RAW_SECTOR)
        if len(raw)!=RAW_SECTOR or raw[24:24+len(before)]!=before:
            raise ModError(f'{entry.path} não coincide com bytes extraídos no LBA {lba}.')
        fixed=bytearray(raw)
        fixed[24:24+len(after)]=after
        out.seek(lba*RAW_SECTOR)
        out.write(regenerate_form1(bytes(fixed)))
        changed.append(lba)
    return changed


def build_test_disc(project, source_image: Path, *, require_complete: bool=False) -> dict:
    """Cópia segura de BIN com atributos e, quando compatíveis, nomes e imagens.

    Para exigir todos os efeitos e cartas extras, use require_complete=True. Isso
    bloqueará construções parciais ao invés de publicar uma imagem enganosa.
    """
    source_image=Path(source_image).resolve()
    try:
        with DiscReader(source_image) as reader:
            if reader.mode!='MODE2/2352':
                raise ModError('Use BIN/CUE original MODE2/2352 para preservar XA/MDEC.')
            original_bin=reader.path.resolve()
            entries={e.path.upper():e for e in reader.files() if not e.is_dir}
            exe=entries.get('SLUS_014.11')
            if exe is None:
                raise ModError('SLUS_014.11 não encontrado na imagem.')
            original_exe=b''.join(reader.read_entry(exe))
            wa_entry=entries.get('DATA/WA_MRG.MRG')
            # WA só é lido quando houver artes vinculadas.
            requested_art={int(k):v for k,v in getattr(project,'arts',{}).items() if int(k)<=722}
            metadata=getattr(project,'metadata',{})
            equip_mode=metadata.get('ps1_equip_mode','adicionar')
            if equip_mode not in ('adicionar','substituir'):
                raise ModError('Modo de equipamento inválido no projeto.')
            native_equips=(metadata.get('ps1_equip_additions',{})
                           if equip_mode=='adicionar' else {})
            replacements=(metadata.get('ps1_equip_replacements',{})
                          if equip_mode=='substituir' else {})
            # Rituais em pausa a pedido do usuário. Guardamos planos anteriores
            # no projeto, mas não os escrevemos no BIN sem reativação explícita.
            native_rituals=(metadata.get('ps1_ritual_recipes',{})
                            if metadata.get('ps1_rituals_enabled',False) else {})
            native_traps=metadata.get('ps1_trap_thresholds',{})
            native_terrain=metadata.get('ps1_terrain_boosts',{})
            god_test_card=metadata.get('ps1_god_icon_test_card_id')
            original_wa=b''.join(reader.read_entry(wa_entry)) if (requested_art or native_equips or replacements or native_rituals or god_test_card) and wa_entry else None
    except DiscError as exc:
        raise ModError(f'Imagem original inválida: {exc}') from exc

    expected=getattr(project,'metadata',{}).get('base_sha256',{}).get('slus')
    if not expected or hashlib.sha256(original_exe).hexdigest()!=expected:
        raise ModError('SLUS da imagem não corresponde ao executável vinculado ao projeto.')

    from .core import god24_experiment_enabled
    god_type_test=metadata.get('ps1_god_type_test_card_id')
    if god_type_test is not None:
        if type(god_type_test) is not int or not god24_experiment_enabled(project,god_type_test):
            raise ModError('Teste God 24 configurado para carta inválida ou tipo '
                           'diferente de 24. Desative a experiência e configure novamente.')
        if not project.edits.get(str(god_type_test)):
            raise ModError('Teste God 24 sem edição numérica salva para a carta.')

    audit_report=None
    if hasattr(project,'edits') and hasattr(project,'new_cards'):
        from .ps1_compat import audit
        audit_report=audit(project)
        if require_complete and audit_report['pendente_de_motor']:
            raise ModError('Build completo bloqueado: recursos ainda sem suporte PS1. Consulte compatibilidade_ps1.json.')

    output, manifest=project.export()
    source_patched=(output/'build_local'/'SLUS_014.11')
    if manifest.get('slus_modificado_sha256') and source_patched.is_file():
        patched_exe=source_patched.read_bytes()
        if hashlib.sha256(patched_exe).hexdigest()!=manifest['slus_modificado_sha256']:
            raise ModError('Executável exportado não coincide com o manifesto SHA-256.')
    else:
        patched_exe=original_exe
    if len(patched_exe)!=exe.size:
        raise ModError('Executável mudou de tamanho; gravação de disco bloqueada.')
    written_names=[];written_descriptions=[]
    if hasattr(project,'edits'):
        from .ps1_content import patch_names
        edits={int(cid):project.get(int(cid)).get('nome','') for cid,rows in project.edits.items()
               if 'nome' in rows and int(cid)<=722}
        # Nomes que não cabem ficam apenas no projeto; cada tentativa gera
        # relatório separado sem gravar parcialmente uma string inválida.
        for cid,name in sorted(edits.items()):
            try:
                patched_exe,items=patch_names(patched_exe,{cid:name})
                written_names.extend(items)
            except ModError:
                continue

    if hasattr(project,'edits'):
        from .ps1_content import patch_descriptions
        texts={int(cid):project.get(int(cid)).get('descricao','') for cid,rows in project.edits.items()
               if 'descricao' in rows and int(cid)<=722}
        catalog={i:project.get(i) for i in project.cards} if hasattr(project,'cards') else {}
        for cid,desc in sorted(texts.items()):
            try:
                patched_exe,items=patch_descriptions(patched_exe,{cid:desc},catalog)
                written_descriptions.extend(items)
            except ModError:
                continue

    from .ps1_native import patch_trap_thresholds, patch_terrain_boosts, patch_rituals
    patched_exe, traps_written = patch_trap_thresholds(patched_exe, native_traps)
    patched_exe, terrain_written = patch_terrain_boosts(patched_exe, native_terrain)
    from .ps1_effects_lab import patch_deck_global_limit
    patched_exe, deck_copies_written = patch_deck_global_limit(
        patched_exe, metadata.get('ps1_deck_global_limit'))

    from .ps1_effects_lab import patch_initial_duel_lp
    patched_exe, lp_written = patch_initial_duel_lp(patched_exe,metadata.get('ps1_starting_lp'))

    written_arts=[]
    patched_wa=None
    if requested_art:
        if original_wa is None or wa_entry is None:
            raise ModError('DATA/WA_MRG.MRG não encontrado para aplicar artes.')
        provenance=project.folder/'base'/'resumo.json'
        from_original=''
        if provenance.is_file():
            from_original=(json.loads(provenance.read_text(encoding='utf-8')).get('source_sha256') or {}).get('DATA/WA_MRG.MRG','')
        if not from_original or hashlib.sha256(original_wa).hexdigest()!=from_original:
            raise ModError('Artes não podem ser gravadas: hash de WA_MRG.MRG ausente ou divergente. '
                           'Reimporte os dados da mesma imagem para fixar a origem.')
        from .ps1_content import patch_card_art
        patched_wa=original_wa
        for cid,rel in sorted(requested_art.items()):
            # Só aceita o caminho cadastrado no projeto; evita leitura externa.
            path=(project.folder/rel).resolve()
            if not path.is_relative_to(project.folder.resolve()):
                raise ModError('Referência de arte fora da pasta do projeto.')
            if not path.is_file():
                raise ModError(f'PNG não encontrado para carta #{cid}: {path.name}')
            patched_wa,regions=patch_card_art(patched_wa,cid,path)
            written_arts.extend(regions)

    native_written=[]
    if native_equips or replacements:
        if original_wa is None or wa_entry is None:
            raise ModError('DATA/WA_MRG.MRG é necessário para alterar equipamentos.')
        if not requested_art:
            provenance=project.folder/'base'/'resumo.json'
            origin_hash=''
            if provenance.is_file():
                origin_hash=(json.loads(provenance.read_text(encoding='utf-8')).get('source_sha256') or {}).get('DATA/WA_MRG.MRG','')
            if not origin_hash or hashlib.sha256(original_wa).hexdigest()!=origin_hash:
                raise ModError('WA_MRG.MRG não corresponde à origem do projeto; '
                               'não é seguro alterar equipamentos.')
        if equip_mode=='substituir':
            from .ps1_equip import replace_equipment_targets
            patched_wa,native_written=replace_equipment_targets(
                patched_wa if patched_wa is not None else original_wa,
                replacements)
            equip_strategy='troca-u16-original'
        else:
            from .ps1_equip_bitmap import patch_bitmap_equips
            bitmap=patch_bitmap_equips(
                original_exe,
                patched_wa if patched_wa is not None else original_wa,
                native_equips)
            if bitmap is not None:
                patched_wa,native_written=bitmap
                equip_strategy='bitmap-mips-94'
            else:
                from .ps1_equip import patch_equipment_targets
                patched_wa,native_written=patch_equipment_targets(
                    patched_wa if patched_wa is not None else original_wa,
                    native_equips)
                equip_strategy='tabela-stock'

    ritual_written=[]
    if native_rituals:
        if original_wa is None or wa_entry is None:
            raise ModError('DATA/WA_MRG.MRG necessário para alterar rituais.')
        provenance=project.folder/'base'/'resumo.json'
        pinned=''
        if provenance.is_file():
            pinned=(json.loads(provenance.read_text(encoding='utf-8')).get('source_sha256') or {}).get('DATA/WA_MRG.MRG','')
        if not pinned or hashlib.sha256(original_wa).hexdigest()!=pinned:
            raise ModError('Rituais: hash de WA_MRG não corresponde à origem do projeto.')
        patched_wa,ritual_written=patch_rituals(
            patched_wa if patched_wa is not None else original_wa,native_rituals)

    god_icon_report=None
    if god_test_card is not None:
        from .ps1_god_icon import try_patch_god_icon, god_icon_asset
        if isinstance(god_test_card,bool) or not isinstance(god_test_card,int):
            raise ModError('ID inválido do teste God; reconfigure o projeto.')
        if not 1 <= god_test_card <= 722:
            raise ModError('O ícone God experimental exige ID de carta 1–722.')
        card=project.get(god_test_card)
        if not (0 <= int(card['tipo_id']) <= 19 or
                god24_experiment_enabled(project,god_test_card)):
            raise ModError('Teste de ícone: escolha tipo 00–19 ou ative '
                           'explicitamente o teste God 24 desta carta.')
        if original_wa is None:
            raise ModError('O teste de ícone Deus exige DATA/WA_MRG.MRG no BIN de origem.')
        provenance=project.folder/'base'/'resumo.json'
        origin_hash=''
        if provenance.is_file():
            origin_hash=(json.loads(provenance.read_text(encoding='utf-8'))
                         .get('source_sha256') or {}).get('DATA/WA_MRG.MRG','')
        if not origin_hash or hashlib.sha256(original_wa).hexdigest()!=origin_hash:
            raise ModError('Teste God: WA_MRG.MRG não corresponde ao arquivo importado '
                           'ou o hash de origem está ausente.')
        patched_wa,patched_exe,god_icon_report=try_patch_god_icon(
            patched_wa if patched_wa is not None else original_wa,
            patched_exe,god_test_card,god_icon_asset())

    god_chest_report=None
    if metadata.get('ps1_god_chest_preview',False):
        from .ps1_god24_chest import patch_god24_chest_preview
        if type(god_type_test) is not int or not god24_experiment_enabled(project,god_type_test):
            raise ModError('God24 baú: tipo 24 não está autorizado para teste.')
        types=(int(project.get(cid)['tipo_id']) for cid in project.cards
               if type(cid) is int and 1<=cid<=722)
        kinds=list(types)
        patched_exe,god_chest_report=patch_god24_chest_preview(
            original_exe,patched_exe,kinds)
        from .ps1_god24_row_patch import apply as patch_real_list
        patched_exe,row_report=patch_real_list(original_exe,patched_exe,kinds)
        god_chest_report['renderizador_lista_bau']=row_report

    god_duel_report=None
    if metadata.get('ps1_god_hand_preview',False):
        if not metadata.get('ps1_god_chest_preview',False):
            raise ModError('God24 em duelo: primeiro ative o teste de ATK/DEF no baú.')
        from .ps1_god24_play import apply as patch_duel
        patched_exe,god_duel_report=patch_duel(
            original_exe,patched_exe,kinds)

    if patched_exe==original_exe and (patched_wa is None or patched_wa==original_wa):
        if audit_report is not None:
            from .ps1_compat import save_audit, explain_no_writable_changes
            dest = save_audit(project)
            raise ModError(explain_no_writable_changes(project, audit_report)
                           + f'\n\nRelatório salvo em: {dest}')
        raise ModError('Nenhuma diferença binária compatível foi encontrada para gerar o jogo.')

    base=output/'teste_ps1'
    base.mkdir(parents=True,exist_ok=True)

    # Mesmo nome de BIN de origem => mesmo arquivo de teste. O digest impede
    # colisões se dois nomes diferentes só variam em maiúsculas/caracteres
    # removidos pelo Windows (inclusive quando o nome precisa ser encurtado).
    safe_name=re.sub(r'[^A-Za-z0-9À-ÿ()\[\] .,_+-]', '_', original_bin.stem)
    safe_name=safe_name.strip(' .')[:96].rstrip(' .') or 'JOGO'
    name_id=hashlib.sha256(original_bin.name.encode('utf-8')).hexdigest()[:10]
    bin_file=base/f'FM_STUDIO_TESTE_{safe_name}_{name_id}.bin'
    cue_file=bin_file.with_suffix('.cue')
    meta_file=bin_file.with_suffix('.json')
    target_paths=(bin_file,cue_file,meta_file)
    if source_image in target_paths or original_bin in target_paths:
        raise ModError('A imagem original não pode ser usada como arquivo de saída.')
    if any(target.is_symlink() for target in target_paths):
        raise ModError('Destino de teste contém atalho/link simbólico; substituição bloqueada.')
    if any(target.is_dir() for target in target_paths):
        raise ModError('Destino de teste é uma pasta, não um arquivo.')
    replacing=bin_file.exists()
    changed=[]

    # Montagem e validação ocorrem em uma pasta temporária. Um erro de leitura
    # ou patch jamais apaga a última ISO de teste que funcionava.
    with tempfile.TemporaryDirectory(prefix='.fmstudio_build_',dir=base) as work:
        workspace=Path(work)
        stage_bin=workspace/bin_file.name
        stage_cue=workspace/cue_file.name
        stage_meta=workspace/meta_file.name
        with original_bin.open('rb') as origin,stage_bin.open('wb') as dest:
            shutil.copyfileobj(origin,dest,8*1024*1024)
        if stage_bin.stat().st_size!=original_bin.stat().st_size:
            raise ModError('Cópia do disco incompleta. BIN anterior preservado.')

        with stage_bin.open('r+b') as out:
            changed+=_write_file_patches(out,exe,original_exe,patched_exe)
            if patched_wa is not None and patched_wa!=original_wa:
                changed+=_write_file_patches(out,wa_entry,original_wa,patched_wa)

        # A releitura confere o SLUS e, quando necessário, o arquivo WA gravado.
        with DiscReader(stage_bin) as verify:
            files={e.path.upper():e for e in verify.files() if not e.is_dir}
            if b''.join(verify.read_entry(files['SLUS_014.11']))!=patched_exe:
                raise ModError('SLUS não corresponde após reempacotamento.')
            if patched_wa is not None and b''.join(verify.read_entry(files['DATA/WA_MRG.MRG']))!=patched_wa:
                raise ModError('WA_MRG não corresponde após reempacotamento.')

        stage_cue.write_text(
            f'FILE "{bin_file.name}" BINARY\n'
            '  TRACK 01 MODE2/2352\n'
            '    INDEX 01 00:00:00\n',
            encoding='ascii'
        )
        result={'formato':'MODE2/2352','status':'PS1_PARCIAL_ATRIBUTOS_TEXTOS_ARTES',
                'bin':str(bin_file),'cue':str(cue_file),
                'nome_iso_origem':original_bin.name,
                'acao_arquivo':'substituido' if replacing else 'criado',
                'gerado_em':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'sha256_slus_original':hashlib.sha256(original_exe).hexdigest(),
                'sha256_slus_modificado':hashlib.sha256(patched_exe).hexdigest(),
                'setores_modificados':len(changed),'lbas':sorted(changed),
                'nomes_aplicados':written_names,
                'descricoes_aplicadas':written_descriptions,
                'artes_aplicadas':written_arts,
                'equipamentos_ps1_aplicados':native_written,
                'rituais_ps1_aplicados':ritual_written,
                'armadilhas_ps1_aplicadas':traps_written,
                'terrenos_ps1_aplicados':terrain_written,
                'limite_global_copias_ps1_aplicado':deck_copies_written,
                'lp_inicial_mips_aplicado':lp_written,
                'teste_visual_icone_deus':god_icon_report,
                'teste_god24_atk_def_bau':god_chest_report,
                'teste_god24_roteamento_duelo':god_duel_report,
                'teste_tipo_god24':({'carta_id':god_type_test,
                                      'status':'CAMPO_TIPO_24_GRAVADO_SEM_MOTOR_VALIDADO',
                                      'aviso':('Teste de mão e colocação gravado. '
                                               'Valide o duelo no ePSXe.' if god_duel_report else
                                               'O motor original trata o tipo 24 '
                                               'como carta especial.'),
                                      'atk_def_visiveis_no_bau':False,
                                      'tipo_deus_funcional_no_epsxe':False,
                                      'icone_de_tipo_instalado':False}
                                     if god_type_test is not None else None),
                'modo_equip_ps1':equip_mode,
                'estrategia_equip_ps1':equip_strategy if (native_equips or replacements) else 'sem-equip',
                'tamanho_bin':stage_bin.stat().st_size,
                'recursos_pendentes':audit_report['pendente_de_motor'] if audit_report else [],
                'aviso':'Build parcial PS1: stats, textos, artes, Equip, rituais, limiares de Trap e bônus de terreno por tipo. Habilidades inéditas, cartas extras e raridades NÃO implementadas.'}

        if hasattr(project,'edits') and hasattr(project,'cards') and hasattr(project,'get'):
            from .disc_verify import verify_image_stats
            checked=verify_image_stats(project,stage_bin)
            if checked['divergentes']:
                raise ModError('BIN de teste diverge dos atributos do projeto. '
                               'A cópia anterior foi preservada.')
            if metadata.get('ps1_god_chest_preview',False):
                if (checked['god24_mascaras_bau']['status']!='aplicado_2_de_2'
                        or checked['god24_renderizador_lista_bau']
                        ['god24_patch_lista']['status']!='aplicado_3_de_3'):
                    raise ModError('God24: falta confirmação de 2/2 máscaras ou '
                                   '3/3 opcodes do renderizador no BIN final. '
                                   'A cópia anterior foi preservada.')
            if god_duel_report and checked['god24_roteamento_duelo']['status']!='aplicado':
                raise ModError('God24 em duelo: faltam instruções na releitura '
                               'do BIN final. Cópia anterior preservada.')
            checked['imagem']=str(bin_file)
            result['verificacao_atributos']=checked
        stage_meta.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')

        # CUE e manifesto são pequenos: preservamos cópias deles para rollback.
        # O BIN novo só substitui o antigo no ÚLTIMO passo, via replace atômico
        # no mesmo volume. Se o ePSXe mantiver o BIN travado, não perdemos a
        # última versão de teste.
        sidecars=((cue_file,stage_cue),(meta_file,stage_meta))
        old_sidecars={}
        for dest,_ in sidecars:
            backup=workspace/(dest.name+'.anterior')
            if dest.exists():
                shutil.copy2(dest,backup)
                old_sidecars[dest]=backup
            else:
                old_sidecars[dest]=None

        installed=[]
        try:
            for dest,prepared in sidecars:
                prepared.replace(dest)
                installed.append(dest)
            stage_bin.replace(bin_file)
        except OSError as exc:
            rollback_failures=[]
            for dest in reversed(installed):
                try:
                    backup=old_sidecars[dest]
                    if backup is not None:
                        backup.replace(dest)
                    else:
                        dest.unlink(missing_ok=True)
                except OSError as rollback_error:
                    rollback_failures.append(str(rollback_error))
            if rollback_failures:
                raise ModError('Falha ao substituir o BIN e restaurar arquivos auxiliares: '
                               + '; '.join(rollback_failures)) from exc
            raise ModError('Não foi possível substituir a imagem de teste. Feche o '
                           'jogo no ePSXe e tente novamente. A imagem anterior foi preservada.') from exc

    if audit_report:
        (output/'compatibilidade_ps1.json').write_text(
            json.dumps(audit_report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'
        )
    return result
