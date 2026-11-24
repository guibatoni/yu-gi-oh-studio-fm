"""Bônus por cartas na mão (``bonus_mao_tipo``) no PS1.

O runtime conta campo, deck e cemitério, mas não a mão. A regra é compilada
como um bônus de deck (código 3) com o ``match`` marcado: ``0x4000 | tipo``
(ou ``0x7FFF`` para qualquer tipo). Sozinho isso conta 0 (nenhum tipo é
0x4000+), então é inofensivo se o desvio abaixo não existir.

A única chamada de ``count_bonus`` (0x800FE984, dentro de CalculateStats,
igual nos runtimes de 722 e 740 cartas) passa por ``wrapper``: bônus de deck
marcados contam as cartas da MÃO (registros 0-4 de cada lado em CARDS, com o
bit OCUPADO) usando o próprio ``matches_bonus`` do runtime (atributo, "ou" e
sub-tipo funcionam igual); os demais seguem para o ``count_bonus`` original.
"""
from __future__ import annotations

import struct

from .core import ModError
from .deep_extract import exe_pos
from .mips_asm import Asm, hi_lo

CALL_SITE = 0x800FE984
COUNT_BONUS = 0x801CFBBC
MATCHES_BONUS = 0x801CFB14
CARDS = 0x801A7AD8
DECK_TYPE = 3
HAND_FLAG = 0x4000
ANY_HAND = 0x7FFF
OCCUPIED = 0x8000


def encode_match(type_id: int) -> int:
    return ANY_HAND if type_id == -1 else HAND_FLAG | (type_id & 0x3FFF)


def _jal(target: int) -> int:
    return 0x0C000000 | ((target & 0x0FFFFFFF) >> 2)


def code(base: int) -> bytes:
    a = Asm(base)
    a.lbu('t0', 0, 'a0')                        # ação
    a.lhu('t2', 2, 'a0')                        # match
    a.ori('t1', 'zero', DECK_TYPE)
    a.bne('t0', 't1', 'original')
    a.andi('t3', 't2', 0xC000)                  # delay
    a.ori('t1', 'zero', HAND_FLAG)
    a.bne('t3', 't1', 'original')
    a.nop()
    a.addiu('sp', 'sp', -0x40)
    a.sw('ra', 0x3C, 'sp'); a.sw('s0', 0x38, 'sp'); a.sw('s1', 0x34, 'sp')
    a.sw('s2', 0x30, 'sp'); a.sw('s3', 0x2C, 'sp'); a.sw('s4', 0x28, 'sp')
    # cópia do bônus com o tipo real (sem a marca) em sp+0x18
    a.lw('t4', 0, 'a0')
    a.lw('t5', 4, 'a0')
    a.sw('t4', 0x18, 'sp')
    a.sw('t5', 0x1C, 'sp')
    a.andi('t2', 't2', 0x3FFF)
    a.ori('t1', 'zero', 0x3FFF)
    a.bne('t2', 't1', 'store_match')
    a.nop()
    a.ori('t2', 'zero', 0xFFFF)                 # qualquer tipo
    a.label('store_match')
    a.sh('t2', 0x1A, 'sp')
    a.lbu('s2', 1, 'a0')
    a.move('s3', 'a1')                          # lado de quem recebe o bônus
    a.andi('s2', 's2', 3)                       # escopo: 0 aliados, 1 inimigos, 2 todos
    a.move('s0', 'zero')                        # contagem
    a.move('s4', 'zero')                        # lado 0, depois 1
    a.label('side')
    a.sltiu('t0', 's2', 2)
    a.beqz('t0', 'count_side')
    a.xor('t1', 's3', 's2')                     # delay: lado aceito pelo escopo
    a.bne('s4', 't1', 'next_side')
    a.nop()
    a.label('count_side')
    a.sll('t0', 's4', 4)                        # lado * 15 registros * 28 bytes
    a.subu('t0', 't0', 's4')                    # lado * 15
    a.sll('t1', 't0', 3)
    a.subu('t1', 't1', 't0')
    a.sll('t1', 't1', 2)                        # (lado*15) * 28
    ch, cl = hi_lo(CARDS)
    a.lui('s1', ch); a.addiu('s1', 's1', cl)
    a.addu('s1', 's1', 't1')                    # primeiro registro da mão
    a.ori('t9', 'zero', 5)
    a.sw('t9', 0x20, 'sp')                      # cartas restantes na mão
    a.label('card')
    a.lhu('t0', 0x16, 's1')
    a.lh('a1', 0x0C, 's1')
    a.andi('t0', 't0', OCCUPIED)
    a.beqz('t0', 'next_card')
    a.addiu('a0', 'sp', 0x18)                   # delay: bônus sem a marca
    a.jal(MATCHES_BONUS)
    a.move('a2', 'zero')
    a.addu('s0', 's0', 'v0')
    a.label('next_card')
    a.lw('t9', 0x20, 'sp')
    a.addiu('s1', 's1', 28)
    a.addiu('t9', 't9', -1)
    a.bnez('t9', 'card')
    a.sw('t9', 0x20, 'sp')
    a.label('next_side')
    a.addiu('s4', 's4', 1)
    a.sltiu('t0', 's4', 2)
    a.bnez('t0', 'side')
    a.nop()
    a.move('v0', 's0')
    a.lw('ra', 0x3C, 'sp'); a.lw('s0', 0x38, 'sp'); a.lw('s1', 0x34, 'sp')
    a.lw('s2', 0x30, 'sp'); a.lw('s3', 0x2C, 'sp'); a.lw('s4', 0x28, 'sp')
    a.jr('ra')
    a.addiu('sp', 'sp', 0x40)
    a.label('original')
    a.j(COUNT_BONUS)
    a.nop()
    return a.bytes()


def block_size() -> int:
    return len(code(0x80100000))


def apply(exe: bytes, hook: int) -> tuple[bytes, dict]:
    site = exe_pos(CALL_SITE, exe, 4)
    if struct.unpack_from('<I', exe, site)[0] != _jal(COUNT_BONUS):
        raise ModError('Bônus na mão: a chamada de count_bonus do runtime não é a esperada.')
    block = code(hook)
    at = exe_pos(hook, exe, len(block))
    if any(exe[at:at + len(block)]):
        raise ModError('Bônus na mão: a área reservada no SLUS não está livre.')
    out = bytearray(exe)
    out[at:at + len(block)] = block
    struct.pack_into('<I', out, site, _jal(hook))
    return bytes(out), {'status': 'aplicado', 'rotina': f'0x{hook:08X}', 'validado_epsxe': False}


def runtime_view(exe: bytes) -> bytes:
    """SLUS com a chamada original de count_bonus, se o desvio estiver inteiro."""
    try:
        site = exe_pos(CALL_SITE, exe, 4)
        word = struct.unpack_from('<I', exe, site)[0]
        if word == _jal(COUNT_BONUS) or word >> 26 != 3:
            return exe
        hook = 0x80000000 | ((word & 0x03FFFFFF) << 2)
        block = code(hook)
        at = exe_pos(hook, exe, len(block))
        if exe[at:at + len(block)] != block:
            return exe
    except Exception:
        return exe
    out = bytearray(exe)
    struct.pack_into('<I', out, site, _jal(COUNT_BONUS))
    return bytes(out)
