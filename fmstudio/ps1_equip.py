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
