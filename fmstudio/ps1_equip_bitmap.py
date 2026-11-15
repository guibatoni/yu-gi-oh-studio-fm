"""Detecção conservadora de permissões Equip por bitmaps em MODs PS1.

Alguns MODs alteram Duel_CheckEquip para usar registros fixos de 94 bytes:
  u16 equip_id + 92 bytes de bitmap dos 722 IDs de monstro.
A tabela é encontrada por referências MIPS reais, nunca por offset assumido.
Não modifica código MIPS nem realoca dados; só muda um bit validado por cópia.
"""
from __future__ import annotations

import struct

from .core import ModError
from .tables import (CARD_COUNT, EXE_DELTA, EQUIP_OFF, EQUIP_LEN,
                     WA_TERRAIN_BASE, TERRAIN_COPIES, TERRAIN_STRIDE)

CHECK_EQUIP = 0x80019A08
EQUIP_RAM_BASE = 0x8017A1D8
EQUIP_RAM_WINDOW = 0x2100
RECORD_BYTES = 94
BITMAP_BYTES = 92


def _words(exe: bytes, ram: int, count: int) -> list[tuple[int, int]]:
    offset = ram - EXE_DELTA
    if offset < 0 or offset + 4 > len(exe) or offset % 4:
        return []
    total = min(count, (len(exe) - offset) // 4)
    return [(ram + i * 4, struct.unpack_from('<I', exe, offset + i * 4)[0])
            for i in range(total)]


def _signed(value: int) -> int:
    return value - 65536 if value & 0x8000 else value


def _signature_and_addresses(instructions) -> tuple[bool, list[int]]:
    has_step = any((w >> 26) == 9 and ((w >> 21) & 31) == ((w >> 16) & 31)
                   and (w & 0xffff) == RECORD_BYTES for _, w in instructions)
    has_shift = any((w >> 26) == 0 and (w & 63) == 6 for _, w in instructions)
    if not has_step or not has_shift:
        return False, []
    registers = {0: 0}
    addresses = []
    for _, w in instructions:
        op, rs, rt = (w >> 26), ((w >> 21) & 31), ((w >> 16) & 31)
        if op == 15:  # lui
            registers[rt] = (w & 0xffff) << 16
        elif op in (9, 13):  # addiu / ori
            if rs in registers:
                if op == 9:
                    value = (registers[rs] + _signed(w & 0xffff)) & 0xffffffff
                else:
                    value = registers[rs] | (w & 0xffff)
                registers[rt] = value
                if EQUIP_RAM_BASE <= value < EQUIP_RAM_BASE + EQUIP_RAM_WINDOW:
                    if value not in addresses:
                        addresses.append(value)
            else:
                registers.pop(rt, None)
        elif op in (32, 33, 35, 36, 37):  # loads overwrite rt
            registers.pop(rt, None)
        elif op == 0:
            funct, rd = w & 63, (w >> 11) & 31
            if rd and funct not in (8, 9, 12, 13):
                registers.pop(rd, None)
        registers[0] = 0
    return True, addresses


def _candidate_tables(exe: bytes) -> tuple[bool, list[int], str]:
    first = _words(exe, CHECK_EQUIP, 22)
    candidates = [first]
    # Um J pode redirecionar a rotina para outra região do executável.
    for at, w in first:
        if (w >> 26) == 2:
            target = ((at + 4) & 0xf0000000) | ((w & 0x3ffffff) << 2)
            if target != CHECK_EQUIP:
                follow = _words(exe, target, 64)
                if follow:
                    candidates.append(first + follow)
                    candidates.append(follow)
    for code in candidates:
        signature, addresses = _signature_and_addresses(code)
        if signature:
            return True, addresses, (
                'MIPS-Duel_CheckEquip-94-byte-bitmap'
                if len(code) == len(first) else 'MIPS-hook-94-byte-bitmap'
            )
    return False, [], 'sem-assinatura-bitmap-A6'


def _records_at(wa: bytes, ram_address: int, terrain: int) -> dict[int, int]:
    """ID Equip -> posição relativa no registro; nunca modifica a imagem."""
    offset = ram_address - EQUIP_RAM_BASE
    start = WA_TERRAIN_BASE + terrain * TERRAIN_STRIDE + EQUIP_OFF + offset
    max_len = min(EQUIP_RAM_WINDOW - offset, EQUIP_LEN - offset)
    if max_len < RECORD_BYTES or start < 0 or start + max_len > len(wa):
        raise ModError('Tabela bitmap fora da janela de Equip do terreno.')
    seen = {}
    for i in range(max_len // RECORD_BYTES):
        at = start + i * RECORD_BYTES
        equip = struct.unpack_from('<H', wa, at)[0]
        if equip == 0:
            break
        if not 1 <= equip <= CARD_COUNT or equip in seen:
            raise ModError('Registros bitmap Equip não reconhecidos na imagem.')
        seen[equip] = at
    if not seen:
        raise ModError('Não foram encontrados registros Equip bitmap nesta região.')
    return seen


def inspect_bitmap_equips(exe: bytes, wa: bytes, equip_ids) -> dict | None:
    """Retorna layout comprovado para TODOS os equipamentos solicitados.

    Caso exista assinatura A6 mas falte um endereço/tabela comprovado,
    recusa o formato stock em vez de alterar bytes que o MIPS pode ignorar.
    """
    signature, addresses, source = _candidate_tables(exe)
    if not signature:
        return None
    if not addresses:
        raise ModError('MOD usa Duel_CheckEquip em formato bitmap de 94 bytes, '
                       'mas não foi possível confirmar o endereço da tabela MIPS. '
                       'Expansão/alteração bloqueada para preservar a imagem.')
    wanted = {int(equip) for equip in equip_ids}
    if not wanted:
        return None
    matches = []
    for address in addresses:
        try:
            copies = [_records_at(wa, address, i) for i in range(TERRAIN_COPIES)]
        except ModError:
            continue
        if all(wanted.issubset(records) for records in copies):
            matches.append((address, copies))
    if len(matches) != 1:
        raise ModError(
            'Foi detectada uma rotina de equipamentos por bitmap no MOD, '
            'mas não foi possível encontrar uma ÚNICA tabela válida para '
            'todos os equipamentos solicitados. Modificar a tabela antiga '
            'poderia ser ignorado pelo duelo.'
        )
    address, records = matches[0]
    return {'formato': 'bitmap-94', 'origem': source, 'endereco_ram': address,
            'offset_equip': address - EQUIP_RAM_BASE, 'registros': records}


def patch_bitmap_equips(exe: bytes, wa: bytes, additions) -> tuple[bytes, list[dict]] | None:
    """Autoriza Equip em outros monstros ativando um bit por monstro.

    Nenhuma tabela cresce: é possível marcar muitos monstros sem sobrescrever
    dados auxiliares. Recusa binários sem assinatura MIPS comprovada.
    """
    from .ps1_equip import _validated_plan
    plan = _validated_plan(additions)
    layout = inspect_bitmap_equips(exe, wa, plan)
    if layout is None:
        return None
    output = bytearray(wa)
    applied = []
    for equip, monsters in sorted(plan.items()):
        for monster in monsters:
            byte_index = monster >> 3
            if not 0 <= byte_index < BITMAP_BYTES:
                raise ModError('ID fora do bitmap Equip original.')
            mask = 1 << (7 - (monster & 7))
            existed = []
            for terrain, records in enumerate(layout['registros']):
                at = records[equip] + 2 + byte_index
                prior = output[at]
                existed.append(bool(prior & mask))
                output[at] |= mask
            if not all(existed):
                applied.append({
                    'equipamento_id': equip, 'novos_alvos': [monster],
                    'modo': 'bitmap-94', 'endereco_ram': hex(layout['endereco_ram']),
                    'terrenos': TERRAIN_COPIES,
                })
    if not applied:
        return wa, []
    # Verifica que SOMENTE os bits solicitados foram ativados.
    allowed_offsets = set()
    for records in layout['registros']:
        for equip, monsters in plan.items():
            for monster in monsters:
                allowed_offsets.add(records[equip] + 2 + (monster >> 3))
    for offset, (a, b) in enumerate(zip(wa, output)):
        if a != b and offset not in allowed_offsets:
            raise ModError('Edição fora do bitmap identificado; imagem preservada.')
    return bytes(output), applied
