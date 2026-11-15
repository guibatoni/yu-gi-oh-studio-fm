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


def build_test_disc(project, source_image: Path) -> dict:
    """Copia o BIN original, altera só o executável e verifica o resultado.

    Não executa se o executável de origem diferir daquele importado no projeto.
    O usuário pode selecionar .cue com uma única trilha MODE2/2352.
    """
    source_image = Path(source_image).resolve()
    try:
        with DiscReader(source_image) as reader:
            if reader.mode != 'MODE2/2352':
                raise ModError('Para preservar XA, use a imagem original MODE2/2352 (.bin/.cue).')
            original_bin = reader.path.resolve()
            entries = [v for v in reader.files() if not v.is_dir and v.path.upper() == 'SLUS_014.11']
            if len(entries) != 1:
                raise ModError('SLUS_014.11 não encontrado ou duplicado na imagem.')
            exe = entries[0]
            original_exe = b''.join(reader.read_entry(exe))
    except DiscError as exc:
        raise ModError(f'Imagem original inválida: {exc}') from exc

    expected = project.metadata.get('base_sha256', {}).get('slus')
    if not expected or hashlib.sha256(original_exe).hexdigest() != expected:
        raise ModError('O SLUS do disco informado não corresponde à base salva no projeto. '
                       'Selecione exatamente o BIN/CUE utilizado para extrair os dados.')
    output, manifest = project.export()
    if not manifest.get('slus_modificado_sha256'):
        raise ModError('Não há alteração de estatísticas compatível com o PS1. '
                       'Para testar a geração do BIN, modifique ATK/DEF de uma carta original e salve.')
    patched_exe = (output / 'build_local' / 'SLUS_014.11').read_bytes()
    if len(patched_exe) != exe.size or len(original_exe) != exe.size:
        raise ModError('O executável mudou de tamanho; não é seguro substituir setores.')
    if hashlib.sha256(patched_exe).hexdigest() != manifest['slus_modificado_sha256']:
        raise ModError('O hash do executável modificado não corresponde ao manifesto.')
    if patched_exe == original_exe:
        raise ModError('Nenhuma diferença foi aplicada ao executável.')

    base = output / 'teste_ps1'
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    bin_file = base / f'FM_STUDIO_TESTE_{stamp}.bin'
    cue_file = bin_file.with_suffix('.cue')
    meta_file = bin_file.with_suffix('.json')
    temp = bin_file.with_suffix('.bin.tmp')
    if original_bin == bin_file.resolve() or original_bin == temp.resolve():
        raise ModError('Não é permitido substituir o arquivo original.')
    changed_sectors = []
    total_sectors = (exe.size + PAYLOAD - 1) // PAYLOAD
    try:
        with original_bin.open('rb') as src, temp.open('wb') as dst:
            shutil.copyfileobj(src, dst, 8 * 1024 * 1024)
        if temp.stat().st_size != original_bin.stat().st_size:
            raise ModError('Cópia do disco incompleta; a imagem de saída foi descartada.')
        with temp.open('r+b') as out:
            for i in range(total_sectors):
                start = i * PAYLOAD
                length = min(PAYLOAD, exe.size - start)
                previous = original_exe[start:start+length]
                current = patched_exe[start:start+length]
                if previous == current:
                    continue
                lba = exe.extent + i
                out.seek(lba * RAW_SECTOR)
                raw = out.read(RAW_SECTOR)
                if len(raw) != RAW_SECTOR or raw[24:24+length] != previous:
                    raise ModError(f'Setor de origem LBA {lba} não coincide com o executável extraído.')
                if raw[18] & 0x20:
                    raise ModError('Encontrado Form2 dentro de SLUS; cópia abortada.')
                updated = bytearray(raw)
                updated[24:24+length] = current
                updated = regenerate_form1(updated)
                out.seek(lba * RAW_SECTOR)
                out.write(updated)
                changed_sectors.append(lba)
        temp.replace(bin_file)
        # Releitura independente usando o mesmo leitor de arquivos ISO9660.
        with DiscReader(bin_file) as verify:
            files = [e for e in verify.files() if not e.is_dir and e.path.upper() == 'SLUS_014.11']
            if len(files) != 1 or b''.join(verify.read_entry(files[0])) != patched_exe:
                raise ModError('Verificação após construção falhou; disco de teste descartado.')
        cue_file.write_text(f'FILE "{bin_file.name}" BINARY\n'
                            '  TRACK 01 MODE2/2352\n'
                            '    INDEX 01 00:00:00\n', encoding='ascii')
        result = {'formato':'MODE2/2352', 'status':'ESTATISTICAS_PS1_SOMENTE',
                  'bin':str(bin_file), 'cue':str(cue_file),
                  'sha256_slus_original':hashlib.sha256(original_exe).hexdigest(),
                  'sha256_slus_modificado':hashlib.sha256(patched_exe).hexdigest(),
                  'setores_modificados':len(changed_sectors), 'lbas':changed_sectors,
                  'tamanho_bin':bin_file.stat().st_size,
                  'aviso':'Habilidades, auras, cemitério, ícones, cores, nomes e cartas extras NÃO executam no PS1.'}
        meta_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        return result
    except Exception:
        temp.unlink(missing_ok=True)
        bin_file.unlink(missing_ok=True)
        cue_file.unlink(missing_ok=True)
        meta_file.unlink(missing_ok=True)
        raise
