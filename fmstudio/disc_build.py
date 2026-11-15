"""Constrói cópia de teste MODE2/2352 sem reempacotar XA/MDEC e sem alterar originais.

Somente substitui bytes da ISO9660 SLUS_014.11 quando o executável gerado
mantém o mesmo tamanho. Atualiza EDC+ECC para cada setor Mode2/Form1 alterado.
Não implementa efeitos, textos, novas cartas ou fusões no motor de PS1.
"""
from __future__ import annotations

from datetime import datetime, timezone
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
            native_equips=getattr(project,'metadata',{}).get('ps1_equip_additions',{})
            original_wa=b''.join(reader.read_entry(wa_entry)) if (requested_art or native_equips) and wa_entry else None
    except DiscError as exc:
        raise ModError(f'Imagem original inválida: {exc}') from exc

    expected=getattr(project,'metadata',{}).get('base_sha256',{}).get('slus')
    if not expected or hashlib.sha256(original_exe).hexdigest()!=expected:
        raise ModError('SLUS da imagem não corresponde ao executável vinculado ao projeto.')

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
    if native_equips:
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
        from .ps1_equip import patch_equipment_targets
        patched_wa,native_written=patch_equipment_targets(
            patched_wa if patched_wa is not None else original_wa,
            native_equips)

    if patched_exe==original_exe and (patched_wa is None or patched_wa==original_wa):
        if audit_report is not None:
            from .ps1_compat import save_audit, explain_no_writable_changes
            dest = save_audit(project)
            raise ModError(explain_no_writable_changes(project, audit_report)
                           + f'\n\nRelatório salvo em: {dest}')
        raise ModError('Nenhuma diferença binária compatível foi encontrada para gerar o jogo.')

    base=output/'teste_ps1';base.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    bin_file=base/f'FM_STUDIO_TESTE_{stamp}.bin';cue_file=bin_file.with_suffix('.cue')
    meta_file=bin_file.with_suffix('.json');temp=bin_file.with_suffix('.bin.tmp')
    if original_bin in (bin_file.resolve(),temp.resolve()):
        raise ModError('Jamais sobrescrever a imagem original.')
    changed=[]
    try:
        with original_bin.open('rb') as src,temp.open('wb') as dst:
            shutil.copyfileobj(src,dst,8*1024*1024)
        if temp.stat().st_size!=original_bin.stat().st_size:
            raise ModError('Cópia do disco incompleta.')
        with temp.open('r+b') as out:
            changed+=_write_file_patches(out,exe,original_exe,patched_exe)
            if patched_wa is not None and patched_wa!=original_wa:
                changed+=_write_file_patches(out,wa_entry,original_wa,patched_wa)
        temp.replace(bin_file)
        # Reabrir imagem e comparar a extração ISO9660 com os bytes esperados.
        with DiscReader(bin_file) as verify:
            files={e.path.upper():e for e in verify.files() if not e.is_dir}
            if b''.join(verify.read_entry(files['SLUS_014.11']))!=patched_exe:
                raise ModError('SLUS não corresponde após reempacotamento.')
            if patched_wa is not None and b''.join(verify.read_entry(files['DATA/WA_MRG.MRG']))!=patched_wa:
                raise ModError('Artes em WA não correspondem após reempacotamento.')
        cue_file.write_text(f'FILE "{bin_file.name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n',encoding='ascii')
        status='PS1_PARCIAL_ATRIBUTOS_TEXTOS_ARTES'
        result={'formato':'MODE2/2352','status':status,'bin':str(bin_file),'cue':str(cue_file),
                'sha256_slus_original':hashlib.sha256(original_exe).hexdigest(),
                'sha256_slus_modificado':hashlib.sha256(patched_exe).hexdigest(),
                'setores_modificados':len(changed),'lbas':sorted(changed),
                'nomes_aplicados':written_names,'descricoes_aplicadas':written_descriptions,'artes_aplicadas':written_arts,
                'equipamentos_ps1_aplicados':native_written,
                 'tamanho_bin':bin_file.stat().st_size,
                'recursos_pendentes':audit_report['pendente_de_motor'] if audit_report else [],
                'aviso':'Cópia experimental. Atributos, textos curtos, artes e alvos de equipamentos originais. NÃO inclui auras, imunidades, efeitos inéditos, cartas extras ou raridades no PS1.'}
        if hasattr(project, 'edits') and hasattr(project, 'cards') and hasattr(project, 'get'):
            from .disc_verify import verify_image_stats
            verification = verify_image_stats(project, bin_file)
            if verification['divergentes']:
                raise ModError('BIN gerado diverge das alterações numéricas do projeto. '
                               'O arquivo inválido não será mantido.')
            result['verificacao_atributos'] = verification
        meta_file.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        if audit_report:
            (output/'compatibilidade_ps1.json').write_text(json.dumps(audit_report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return result
    except Exception:
        temp.unlink(missing_ok=True);bin_file.unlink(missing_ok=True)
        cue_file.unlink(missing_ok=True);meta_file.unlink(missing_ok=True)
        raise
