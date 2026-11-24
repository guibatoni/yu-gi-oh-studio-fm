"""Bônus de ATK/DEF por equipamento no PS1 (Drop x15).

No executável, ``DuelScene_UpdateCardPlacement`` grava o bônus da animação de
equipamento em ``0x8001A7F8..0x8001A830``: +500 para todos e +1000 quando o
efeito é o Megamorph (``0x291``), somando a diferença em ``D_8009B154``
(``0x24C($gp)``), o valor que Reverse Trap desfaz.

O Studio troca duas instruções em ``0x8001A81C`` (depois da leitura do ID, que
a expansão de 740 cartas já traduz para a carta-base) por um ``j`` para uma
rotina residente que consulta uma tabela ``(ID do equipamento, bônus)`` e volta
para ``0x8001A834``. Equipamentos fora da tabela mantêm exatamente o
comportamento original. ``$ra`` não é alterado. A rotina e a tabela ficam num
intervalo livre do SLUS, reservado pelo mesmo alocador das descrições.
"""
from __future__ import annotations

import struct

from .core import ModError
from .deep_extract import exe_pos
from .tables import CARD_COUNT

SETTINGS_KEY = 'ps1_equip_bonus'
BONUS_MIN, BONUS_MAX = 0, 5000
MEGAMORPH = 0x291
SITE = 0x8001A81C
ID_LOAD = 0x8001A814  # lh v1, 0x2FE(gp) ou o salto da expansão de 740 cartas
RESUME = 0x8001A834
# Assinatura original do trecho (Drop x15 / retail).
SIGNATURE = {
    0x8001A7F8: 0x240201F4,  # li   v0, 500
    0x8001A800: 0xA622002A,  # sh   v0, 0x2A(s1)
    0x8001A814: 0x878302FE,  # lh   v1, 0x2FE(gp)   equipamento
    0x8001A818: 0x24020291,  # li   v0, 0x291       Megamorph
    0x8001A81C: 0x14620005,  # bne  v1, v0, 0x8001A834
    0x8001A820: 0x240303E8,  # li   v1, 1000
    0x8001A824: 0x9782024C,  # lhu  v0, 0x24C(gp)
    0x8001A828: 0xA623002A,  # sh   v1, 0x2A(s1)
    0x8001A82C: 0x244201F4,  # addiu v0, v0, 500
    0x8001A830: 0xA782024C,  # sh   v0, 0x24C(gp)
}


def _jump(op: int, address: int) -> int:
    return op << 26 | (address & 0x0FFFFFFF) >> 2


def site_words(hook: int) -> dict[int, int]:
    return {0x8001A81C: _jump(2, hook),        # j    hook   (v1 = ID do equipamento)
            0x8001A820: 0x00000000}            # nop


def hook_code(hook: int) -> bytes:
    """MIPS I (load delays respected). In: v1 = equipment ID, s1 = placement, gp.
    Ends with ``j 0x8001A834`` (the native code after the Megamorph branch)."""
    table = hook + 21 * 4
    high, low = (table + 0x8000) >> 16 & 0xFFFF, table & 0xFFFF
    words = (
        0x3C080000 | high,   # 0  lui   t0, %hi(table)
        0x25080000 | low,    # 1  addiu t0, t0, %lo(table)
        0x95090000,          # 2  loop: lhu t1, 0(t0)      ID (0 = fim)
        0x00000000,          # 3  nop (load delay)
        0x11200005,          # 4  beq   t1, zero, default
        0x850A0002,          # 5  lh    t2, 2(t0)          bônus (delay slot)
        0x1523FFFB,          # 6  bne   t1, v1, loop
        0x25080004,          # 7  addiu t0, t0, 4          (delay slot)
        0x10000006,          # 8  b     apply
        0x00000000,          # 9  nop
        0x240A01F4,          # 10 default: li t2, 500
        0x24090291,          # 11 li    t1, 0x291
        0x14690002,          # 12 bne   v1, t1, apply
        0x00000000,          # 13 nop
        0x240A03E8,          # 14 li    t2, 1000
        0xA62A002A,          # 15 apply: sh t2, 0x2A(s1)
        0x9789024C,          # 16 lhu   t1, 0x24C(gp)
        0x254AFE0C,          # 17 addiu t2, t2, -500
        0x012A4821,          # 18 addu  t1, t1, t2
        _jump(2, RESUME),    # 19 j     0x8001A834
        0xA789024C,          # 20 sh    t1, 0x24C(gp)      (delay slot)
    )
    return struct.pack(f'<{len(words)}I', *words)


def table_bytes(bonuses: dict[int, int]) -> bytes:
    rows = b''.join(struct.pack('<Hh', cid, bonus) for cid, bonus in sorted(bonuses.items()))
    return rows + b'\0\0\0\0'


def block_size(bonuses: dict[int, int]) -> int:
    return 21 * 4 + 4 * (len(bonuses) + 1)


def normalize(raw) -> dict[int, int]:
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ModError('Bônus de equipamentos inválidos no projeto.')
    result = {}
    for key, value in raw.items():
        try:
            cid, bonus = int(key), int(value)
        except (TypeError, ValueError) as exc:
            raise ModError('Bônus de equipamento: use números inteiros.') from exc
        if isinstance(value, bool) or not 1 <= cid <= CARD_COUNT:
            raise ModError(f'Bônus de equipamento: carta #{key} fora de 1–{CARD_COUNT}.')
        if not BONUS_MIN <= bonus <= BONUS_MAX:
            raise ModError(f'Bônus de equipamento #{cid}: use de {BONUS_MIN} a {BONUS_MAX}.')
        result[cid] = bonus
    return result


def equip_bonuses(project) -> dict[int, int]:
    return normalize((getattr(project, 'metadata', None) or {}).get(SETTINGS_KEY))


def set_equip_bonus(project, cid: int, bonus: int | None):
    current = equip_bonuses(project)
    if bonus is None:
        current.pop(int(cid), None)
    else:
        current.update(normalize({cid: bonus}))
    before = project.metadata
    project.metadata = {**before, SETTINGS_KEY: {str(k): v for k, v in sorted(current.items())}}
    try:
        project.save()
    except OSError:
        project.metadata = before
        raise


def default_bonus(cid: int) -> int:
    return 1000 if cid == MEGAMORPH else 500


def reserve_block(exe: bytes, regions, size: int):
    """Take an aligned, zero-filled interval from the shared SLUS free list."""
    free = list(regions or [])
    for index, (lo, hi) in sorted(enumerate(free), key=lambda item: item[1][1] - item[1][0]):
        address = (hi - size) & ~3
        if address < lo:
            continue
        at = exe_pos(address, exe, size)
        if any(exe[at:at + size]):
            continue
        free[index:index + 1] = [(start, end) for start, end in
                                 ((lo, address), (address + size, hi)) if start < end]
        return address, free
    raise ModError(f'Sem espaço livre no SLUS ({size} bytes) para os recursos novos do mod '
                   '(bônus de equipamento, molduras, animação de LP, HUD de LP, Vínculo com Vida, '
                   'escolha de deck ou descrições maiores). Desative um deles ou encurte descrições.')


def apply(exe: bytes, bonuses: dict[int, int], hook: int) -> tuple[bytes, dict]:
    result = bytearray(exe)
    for address, word in SIGNATURE.items():
        found = struct.unpack_from('<I', exe, exe_pos(address, exe, 4))[0]
        if found != word and not (address == ID_LOAD and found >> 26 == 2):
            raise ModError(f'Bônus de equipamento: o SLUS diverge do Drop x15 em 0x{address:08X}.')
    block = hook_code(hook) + table_bytes(bonuses)
    at = exe_pos(hook, exe, len(block))
    if any(exe[at:at + len(block)]):
        raise ModError('Bônus de equipamento: a área reservada no SLUS não está livre.')
    result[at:at + len(block)] = block
    for address, word in site_words(hook).items():
        struct.pack_into('<I', result, exe_pos(address, result, 4), word)
    return bytes(result), {'status': 'aplicado', 'rotina': f'0x{hook:08X}',
                           'bonus': {str(k): v for k, v in sorted(bonuses.items())},
                           'validado_epsxe': False}


def status(exe: bytes) -> dict:
    jump = struct.unpack_from('<I', exe, exe_pos(SITE, exe, 4))[0]
    if jump == SIGNATURE[SITE]:
        return {'status': 'original'}
    if jump >> 26 != 2:
        return {'status': 'divergente'}
    hook = 0x80000000 | (jump & 0x03FFFFFF) << 2
    code = hook_code(hook)
    at = exe_pos(hook, exe, len(code))
    if exe[at:at + len(code)] != code:
        return {'status': 'divergente'}
    bonuses, at = {}, at + len(code)
    while True:
        cid, bonus = struct.unpack_from('<Hh', exe, at)
        if not cid:
            break
        bonuses[str(cid)] = bonus
        at += 4
    return {'status': 'aplicado', 'rotina': f'0x{hook:08X}', 'bonus': bonuses}
