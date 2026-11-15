"""Expansão conservadora dos ALVOS de equipamentos existentes no PS1.

Usa as sete cópias documentadas do bloco de equipamentos em WA_MRG.MRG.
Não cria rotinas de efeitos novas; o bônus em combate é o comportamento
original do equipamento e não pode ser configurado livremente aqui.
"""
from __future__ import annotations

import struct

from .core import ModError
from .tables import (CARD_COUNT, EQUIP_LEN, EQUIP_OFF,
                     WA_TERRAIN_BASE, TERRAIN_COPIES, TERRAIN_STRIDE)

META_KEY = 'ps1_equip_additions'


def _unpack(table: bytes) -> list[tuple[int, list[int]]]:
    if len(table) != EQUIP_LEN:
        raise ModError('Tamanho inválido da tabela de equipamentos.')
    cursor = 0
    records = []
    seen = set()
    while cursor + 4 <= len(table):
        equip_id, n = struct.unpack_from('<HH', table, cursor)
        cursor += 4
        if equip_id == 0:
            if n != 0 or any(table[cursor:]):
                raise ModError('Dados desconhecidos após o fim da tabela de equipamentos; patch bloqueado.')
            return records
        if equip_id > CARD_COUNT or equip_id in seen or n > CARD_COUNT:
            raise ModError('Tabela de equipamentos fora do formato original suportado.')
        if cursor + 2 * n > len(table):
            raise ModError('Lista de equipamentos ultrapassa o bloco reservado.')
        targets = list(struct.unpack_from(f'<{n}H', table, cursor)) if n else []
        if any(not 1 <= x <= CARD_COUNT for x in targets):
            raise ModError('Lista original de equipamentos tem ID fora do intervalo.')
        records.append((equip_id, targets))
        seen.add(equip_id)
        cursor += 2 * n
    raise ModError('Tabela de equipamentos sem terminador.')


def list_equipment_targets(wa: bytes) -> dict[int, list[int]]:
    start = WA_TERRAIN_BASE + EQUIP_OFF
    if start + EQUIP_LEN > len(wa):
        raise ModError('WA_MRG.MRG é menor que a tabela de equipamentos.')
    return dict(_unpack(wa[start:start + EQUIP_LEN]))


def _validated_plan(plan: dict) -> dict[int, list[int]]:
    if not isinstance(plan, dict):
        raise ModError('Plano de equipamentos precisa ser um objeto.')
    cleaned = {}
    for k, values in plan.items():
        try:
            equip = int(k)
            targets = [int(x) for x in values]
        except (ValueError, TypeError) as exc:
            raise ModError('IDs dos equipamentos precisam ser inteiros.') from exc
        if not 1 <= equip <= CARD_COUNT or not isinstance(values, (list, tuple)):
            raise ModError('ID/lista de equipamento inválido.')
        if len(targets) > CARD_COUNT or any(not 1 <= t <= CARD_COUNT for t in targets):
            raise ModError('Alvo de equipamento fora de 1–722.')
        if len(set(targets)) != len(targets):
            raise ModError('Alvo duplicado no plano de equipamentos.')
        cleaned[equip] = targets
    return cleaned


def patch_equipment_targets(wa: bytes, additions: dict) -> tuple[bytes, list[dict]]:
    """Altera somente blocos de equipamentos, nunca fusões nem outros bytes."""
    plan = _validated_plan(additions)
    if not plan:
        return wa, []
    original = []
    for index in range(TERRAIN_COPIES):
        pos = WA_TERRAIN_BASE + index * TERRAIN_STRIDE + EQUIP_OFF
        if pos + EQUIP_LEN > len(wa):
            raise ModError('WA_MRG.MRG truncado em uma cópia de terreno.')
        original.append(wa[pos:pos+EQUIP_LEN])
    if any(copy != original[0] for copy in original[1:]):
        raise ModError('As sete cópias de equipamento divergem nesta versão do MOD; '
                       'patch automático bloqueado para preservar seus dados.')
    records = _unpack(original[0])
    known = {equip for equip, _ in records}
    if not set(plan).issubset(known):
        invalid = min(set(plan)-known)
        raise ModError(f'Equipamento #{invalid} não possui uma tabela original conhecida.')

    result = bytearray()
    changed = []
    for equip, targets in records:
        merged = list(targets)
        new = []
        for card in plan.get(equip, []):
            if card not in merged:
                merged.append(card)
                new.append(card)
        result += struct.pack('<HH', equip, len(merged))
        if merged:
            result += struct.pack(f'<{len(merged)}H', *merged)
        if new:
            changed.append({'equipamento_id': equip, 'novos_alvos': new,
                            'alvos_totais': len(merged)})
    result += b'\x00\x00\x00\x00'
    if len(result) > EQUIP_LEN:
        raise ModError(f'Tabela de equipamentos não tem espaço para adicionar alvos '
                       f'({len(result)} > {EQUIP_LEN} bytes).')
    result += bytes(EQUIP_LEN - len(result))
    if not changed:
        return wa, []
    output = bytearray(wa)
    for index in range(TERRAIN_COPIES):
        pos = WA_TERRAIN_BASE + index * TERRAIN_STRIDE + EQUIP_OFF
        output[pos:pos+EQUIP_LEN] = result
    return bytes(output), changed


def add_equipment_target(project, equip: int, target: int) -> bool:
    """Registra uma permissão de equipar; o chamador salva o projeto explicitamente."""
    if not (1 <= equip <= CARD_COUNT and 1 <= target <= CARD_COUNT):
        raise ModError('Selecione equipamento e monstro originais (#001–#722).')
    if int(project.get(equip)['tipo_id']) != 23:
        raise ModError('A carta de origem deve ser do tipo Equip.')
    if int(project.get(target)['tipo_id']) >= 20:
        raise ModError('O alvo deve ser uma criatura original, não Magic/Trap/Equip.')
    plan = _validated_plan(project.metadata.get(META_KEY, {}))
    targets = list(plan.get(equip, []))
    if target in targets:
        return False
    targets.append(target)
    plan[equip] = targets
    project.metadata[META_KEY] = {str(key): value for key, value in plan.items()}
    return True



def inspect_equips_on_disc(path, plan):
    """Lê SLUS e as sete tabelas de Equip do BIN/CUE informado (somente leitura)."""
    from pathlib import Path
    import hashlib
    from .disc import DiscReader, DiscError
    from .tables import EXE_DELTA
    source = Path(path)
    try:
        with DiscReader(source) as reader:
            file_map = {item.path.upper(): item for item in reader.files()
                        if not item.is_dir}
            if 'SLUS_014.11' not in file_map or 'DATA/WA_MRG.MRG' not in file_map:
                raise ModError('O BIN/CUE não possui SLUS_014.11 e WA_MRG.MRG.')
            slus=b''.join(reader.read_entry(file_map['SLUS_014.11']))
            wa=b''.join(reader.read_entry(file_map['DATA/WA_MRG.MRG']))
            resolved=str(reader.path.resolve())
    except DiscError as exc:
        raise ModError('Não foi possível ler BIN/CUE: '+str(exc)) from exc

    copies=[]
    for index in range(TERRAIN_COPIES):
        pos=WA_TERRAIN_BASE+index*TERRAIN_STRIDE+EQUIP_OFF
        if pos+EQUIP_LEN > len(wa):
            raise ModError('WA_MRG.MRG truncado na tabela Equip da cópia '+str(index))
        copy=wa[pos:pos+EQUIP_LEN]
        _unpack(copy)  # garante que cada cópia seja legível
        copies.append(copy)
    tables_same=all(copy==copies[0] for copy in copies[1:])
    targets=dict(_unpack(copies[0]))
    hook_offset=0x80019A08-EXE_DELTA  # Duel_CheckEquip, área conhecida
    hook=slus[hook_offset:hook_offset+0x58] if len(slus)>=hook_offset+0x58 else b''
    return {
        'imagem':resolved,
        'sha256_slus':hashlib.sha256(slus).hexdigest(),
        'sha256_rotina_equip':hashlib.sha256(hook).hexdigest() if hook else None,
        'sete_tabelas_iguais':tables_same,
        'tabelas':[hashlib.sha256(copy).hexdigest() for copy in copies],
        'alvos':{str(equip):{str(monster):monster in targets.get(equip,[])
                          for monster in wanted}
                 for equip,wanted in plan.items()}
    }


def diagnose_equipment_project(project, image):
    """Compara a lista de alvos planejados ao BIN de teste e à origem, se acessível.

    A verificação é dos dados, NÃO de execução no ePSXe. A rotina MIPS de
    Duel_CheckEquip pode ter sido modificada por um MOD.
    """
    from pathlib import Path
    plan=_validated_plan(project.metadata.get(META_KEY,{}))
    if not plan:
        raise ModError('Nenhuma permissão PS1 de Equip cadastrada. '
                       'Na aba Efeitos, selecione Equip e autorize um monstro.')
    result=inspect_equips_on_disc(image,plan)
    base_path=Path(project.metadata.get('base_source') or '')
    original=None
    if base_path.is_file():
        try:
            original=inspect_equips_on_disc(base_path,plan)
        except (ModError, OSError):
            original=None
    result['imagem_origem']=original['imagem'] if original else None
    result['comparacoes']=[]
    for equip,monsters in sorted(plan.items()):
        for monster in monsters:
            after=result['alvos'][str(equip)][str(monster)]
            before=original['alvos'][str(equip)][str(monster)] if original else None
            if not after:
                verdict='NAO_GRAVADO'
            elif before is True:
                verdict='JA_EXISTIA_NA_ORIGEM'
            elif before is False:
                verdict='ADICIONADO_A_TABELA'
            else:
                verdict='PRESENTE_SEM_BASE_COMPARAVEL'
            result['comparacoes'].append({
                'equipamento_id':equip, 'monstro_id':monster,
                'origem_permitia':before, 'bin_permite':after, 'resultado':verdict
            })
    result['codigo_equip_igual_a_origem']=(
        original['sha256_rotina_equip']==result['sha256_rotina_equip']
        if original and original['sha256_rotina_equip'] and result['sha256_rotina_equip']
        else None
    )
    result['aviso']=(
        'A presença do par na tabela não prova execução no PS1. Alguns MODs '
        'alteram Duel_CheckEquip por código MIPS/bitmaps; compare com uma '
        'imagem original não modificada para diagnosticar esse caso.'
    )
    return result


def describe_equip_diagnostic(report):
    lines=['Imagem verificada:', report['imagem'], '',
           'Sete tabelas idênticas: '+('SIM' if report['sete_tabelas_iguais'] else 'NÃO')]
    for row in report['comparacoes']:
        result={
            'NAO_GRAVADO':'NÃO GRAVADO no BIN selecionado',
            'JA_EXISTIA_NA_ORIGEM':'já existia na origem (nenhuma permissão nova)',
            'ADICIONADO_A_TABELA':'adicionado à tabela do BIN',
            'PRESENTE_SEM_BASE_COMPARAVEL':'presente no BIN (origem não localizada)',
        }[row['resultado']]
        lines.append(f"Equip #{row['equipamento_id']:03d} → "
                     f"Monstro #{row['monstro_id']:03d}: {result}")
    lines.append('')
    lines.append('Rotina de equip idêntica à imagem base: '
                 + ('SIM' if report['codigo_equip_igual_a_origem'] is True
                    else 'NÃO' if report['codigo_equip_igual_a_origem'] is False
                    else 'NÃO FOI POSSÍVEL COMPARAR'))
    lines.append('')
    lines.append(report['aviso'])
    return '\n'.join(lines)
