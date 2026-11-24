"""Sub-tipo no PS1: ``matches_bonus`` do runtime também aceita o 2º tipo.

Todos os bônus por tipo do runtime (aura, contagem no campo e no deck, filtros
de cemitério com atributo) passam por ``matches_bonus(bonus, id, by_id)``
(RUNTIME_EXT, igual nos runtimes de 722 e 740 cartas). Na comparação de tipo,
a sequência em 0x801CFB48 calcula ``type_matches``:

    lhu  $2,2($4)   ; match
    nop
    xori $6,$2,0xFFFF
    xor  $2,$2,$3   ; $3 = tipo da carta
    sltiu $2,$2,1
    sltiu $6,$6,1
    or   $6,$6,$2   ; type_matches
    lbu  $2,1($4)   ; (segue: atributo)

O primeiro word vira ``j tramp``; o trampolim refaz essa conta e, quando não
é comparação por ID, também aceita ``subtipo[id] == match`` (lista de pares
id/sub-tipo, só das cartas com sub-tipo), depois volta para 0x801CFB64.

Não cobre: o contador de tipos do cemitério sem filtro de atributo (o jogo
conta pelo tipo principal) e os bônus de terreno nativos do jogo.
"""
from __future__ import annotations

import struct

from .core import ModError
from .deep_extract import exe_pos
from .mips_asm import Asm

SITE = 0x801CFB48
BACK = SITE + 0x1C
SIGNATURE = (0x94820002, 0x00000000, 0x3846FFFF, 0x00431026, 0x2C420001,
             0x2CC60001, 0x00C23025, 0x90820001)


def _assemble(base: int, pairs: list[tuple[int, int]]) -> Asm:
    a = Asm(base)
    a.lhu('v0', 2, 'a0')                        # match
    a.bnez('a2', 'by_id')
    a.xori('a3', 'v0', 0xFFFF)                  # delay
    a.la('t0', 'pairs')
    a.label('loop')
    a.lhu('t1', 0, 't0')
    a.lbu('t2', 2, 't0')
    a.beqz('t1', 'by_id')                       # fim da lista: sem sub-tipo
    a.nop()
    a.bne('t1', 'a1', 'loop')
    a.addiu('t0', 't0', 4)                      # delay: próximo par
    a.subu('t2', 't2', 'v0')
    a.b('join')
    a.sltiu('t0', 't2', 1)                      # delay: sub-tipo == match
    a.label('by_id')
    a.move('t0', 'zero')
    a.label('join')
    a.subu('v0', 'v0', 'v1')                    # match - tipo (== 0 → mesmo tipo)
    a.sltiu('v0', 'v0', 1)
    a.sltiu('a2', 'a3', 1)                      # match == 0xFFFF
    a.or_('a2', 'a2', 'v0')
    a.j(BACK)
    a.or_('a2', 'a2', 't0')                     # delay: ... ou sub-tipo
    a.label('pairs')
    data = b''.join(struct.pack('<HBx', cid, sub) for cid, sub in pairs) + bytes(4)
    for value in struct.unpack(f'<{len(data) // 4}I', data):
        a.word(value)
    return a


def code(base: int, pairs: list[tuple[int, int]]) -> bytes:
    return _assemble(base, pairs).bytes()


def block_size(count: int) -> int:
    return len(code(0x80100000, [(1, 0)] * count))


def pairs_for(cards: dict, capacity: int) -> list[tuple[int, int]]:
    from .card_subtypes import subtype
    return sorted((cid, subtype(card)) for cid, card in cards.items()
                  if 1 <= cid <= capacity and subtype(card) is not None)


def _words(exe: bytes, address: int, count: int) -> tuple[int, ...]:
    return struct.unpack_from(f'<{count}I', exe, exe_pos(address, exe, 4 * count))


def apply(exe: bytes, hook: int, pairs: list[tuple[int, int]]) -> tuple[bytes, dict]:
    if _words(exe, SITE, len(SIGNATURE)) != SIGNATURE:
        raise ModError('Sub-tipo: a rotina de bônus por tipo do runtime não está instalada como esperado.')
    block = code(hook, pairs)
    at = exe_pos(hook, exe, len(block))
    if any(exe[at:at + len(block)]):
        raise ModError('Sub-tipo: a área reservada no SLUS não está livre.')
    out = bytearray(exe)
    out[at:at + len(block)] = block
    struct.pack_into('<I', out, exe_pos(SITE, exe, 4), 0x08000000 | ((hook & 0x0FFFFFFF) >> 2))
    return bytes(out), {'status': 'aplicado', 'cartas': len(pairs), 'rotina': f'0x{hook:08X}',
                        'validado_epsxe': False}


def runtime_view(exe: bytes) -> bytes:
    """SLUS com o word original em SITE, se o trampolim estiver instalado inteiro."""
    try:
        word = _words(exe, SITE, 1)[0]
        if word == SIGNATURE[0] or word >> 26 != 2 or _words(exe, SITE + 4, 7) != SIGNATURE[1:]:
            return exe
        hook = (SITE & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        at = exe_pos(hook, exe, 4)
        # código fixo + pares até o terminador zero
        head = code(hook, [])[:-4]
        if exe[at:at + len(head)] != head:
            return exe
    except Exception:
        return exe
    out = bytearray(exe)
    struct.pack_into('<I', out, exe_pos(SITE, exe, 4), SIGNATURE[0])
    return bytes(out)
