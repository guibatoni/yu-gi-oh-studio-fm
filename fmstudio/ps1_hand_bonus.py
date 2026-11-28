"""Bônus por cartas na mão no PS1 (por tipo e por carta específica).

O runtime conta campo, deck e cemitério, mas não a mão. ``bonus_mao_tipo`` é
compilado como bônus de deck por tipo (código 3) e ``bonus_por_carta_id`` com
origem mão como bônus de deck por ID (código 5), com o ``match`` marcado:
``0x4000 | tipo/ID`` (ou ``0x7FFF`` para qualquer tipo). Sozinho isso conta 0 (nenhum tipo é
0x4000+), então é inofensivo se o desvio abaixo não existir.

A contagem é feita UMA vez, quando o monstro entra em campo, e fica fixa
enquanto ele estiver lá (pedido do usuário: o poder não oscila a cada compra):

* ``entry``: o fim de ``ConfirmPlacement`` (0x800FF74C, ``j summon_damage``,
  só numa entrada nova — invocação ou fusão) passa por aqui. Para cada um dos 4
  primeiros bônus da regra da carta que entrou, se for bônus de mão, conta as
  cartas da MÃO (registros 0-4 de cada lado em CARDS, com o bit OCUPADO, pelo
  próprio ``matches_bonus`` do runtime: atributo, "ou" e sub-tipo funcionam
  igual) e guarda em ``snapshots[slot][bônus]``; depois segue para
  ``summon_damage``.
* a única chamada de ``count_bonus`` (0x800FE984, em CalculateStats) passa
  pelo início do bloco: bônus de mão devolvem o valor guardado do slot (s7 =
  slot, s5 = índice do bônus + 1 no runtime compilado); os demais seguem para o
  ``count_bonus`` original. Sem slot válido, conta na hora (``live``).

Os dois pontos são iguais nos runtimes de 722 e 740 cartas.
"""
from __future__ import annotations

import struct

from .core import ModError
from .deep_extract import exe_pos
from .mips_asm import Asm, hi_lo

CALL_SITE = 0x800FE984
# Fim de ConfirmPlacement numa entrada nova em campo: ``j summon_damage``
# (com o slot em a0). Igual nos runtimes de 722 e 740 cartas.
ENTRY_SITE = 0x800FF74C
SUMMON_ENTRY = 0x801CFDF8
CONFIG = 0x801CD7A0
SNAP_BONUSES = 4             # bônus de mão guardados por slot (os 4 primeiros da regra)
COUNT_BONUS = 0x801CFBBC
MATCHES_BONUS = 0x801CFB14
CARDS = 0x801A7AD8
DECK_TYPE = 3
DECK_ID = 5
HAND_FLAG = 0x4000
ANY_HAND = 0x7FFF
OCCUPIED = 0x8000


def encode_match(type_id: int) -> int:
    return ANY_HAND if type_id == -1 else HAND_FLAG | (type_id & 0x3FFF)


def _jal(target: int) -> int:
    return 0x0C000000 | ((target & 0x0FFFFFFF) >> 2)


def code(base: int, follow: int = SUMMON_ENTRY) -> bytes:
    return _build(base, follow).bytes()


def _labels(base: int, follow: int = SUMMON_ENTRY) -> dict:
    asm = _build(base, follow)
    asm.bytes()
    return asm.labels


def _build(base: int, follow: int = SUMMON_ENTRY) -> Asm:
    a = Asm(base)
    # ------------------------------------------------ count_bonus(bônus, lado)
    # Chamado só por CalculateStats com i == slot: s7 ($23) = slot de quem tem
    # o bônus e s5 ($21) = índice do bônus + 1 (registradores do runtime
    # compilado, iguais nos runtimes de 722 e 740 cartas).
    a.lbu('t0', 0, 'a0')                        # ação
    a.lhu('t2', 2, 'a0')                        # match
    a.ori('t1', 'zero', DECK_TYPE)
    a.beq('t0', 't1', 'is_deck')
    a.nop()
    a.ori('t1', 'zero', DECK_ID)
    a.bne('t0', 't1', 'original')
    a.nop()
    a.label('is_deck')
    a.andi('t3', 't2', 0xC000)
    a.ori('t1', 'zero', HAND_FLAG)
    a.bne('t3', 't1', 'original')
    a.nop()
    # valor guardado na entrada em campo
    a.move('t9', 'ra')
    a.move('t4', 's7')
    a.jal('snapshot_slot')                      # t5 = endereço de snap[slot][0] ou 0
    a.addiu('t6', 's5', -1)                     # delay: índice do bônus
    a.move('ra', 't9')
    a.beqz('t5', 'live')
    a.sltiu('t7', 't6', SNAP_BONUSES)
    a.beqz('t7', 'live')
    a.addu('t5', 't5', 't6')                    # delay
    a.lbu('v0', 0, 't5')
    a.jr('ra')
    a.nop()
    a.label('original')
    a.j(COUNT_BONUS)
    a.nop()

    # ------------------------------------- live(bônus, lado): conta a mão agora
    a.label('live')
    a.lbu('t0', 0, 'a0')
    a.ori('t1', 'zero', DECK_ID)
    a.bne('t0', 't1', 'live_type')
    a.move('t8', 'zero')                        # delay: por tipo
    a.ori('t8', 'zero', 1)                      # por carta específica
    a.label('live_type')
    a.lhu('t2', 2, 'a0')
    a.addiu('sp', 'sp', -0x40)
    a.sw('ra', 0x3C, 'sp'); a.sw('s0', 0x38, 'sp'); a.sw('s1', 0x34, 'sp')
    a.sw('s2', 0x30, 'sp'); a.sw('s3', 0x2C, 'sp'); a.sw('s4', 0x28, 'sp')
    a.sw('t8', 0x24, 'sp')                      # by_id para matches_bonus
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
    a.lw('a2', 0x24, 'sp')                      # delay: 0 tipo / 1 carta específica
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

    # ------------------------- snapshot_slot(t4 = slot) -> t5 = &snap[k][0] ou 0
    a.label('snapshot_slot')
    a.addiu('t5', 't4', -5)
    a.sltiu('t7', 't5', 5)
    a.bnez('t7', 'snap_ok')
    a.addiu('t7', 't4', -15)
    a.addiu('t5', 't4', -20)
    a.sltiu('t5', 't5', 5)
    a.beqz('t5', 'snap_none')
    a.nop()
    a.move('t5', 't7')                          # 20..24 -> 5..9
    a.label('snap_ok')
    a.sll('t5', 't5', 2)                        # SNAP_BONUSES = 4 bytes por slot
    a.la('t7', 'snapshots')
    a.jr('ra')
    a.addu('t5', 't5', 't7')
    a.label('snap_none')
    a.jr('ra')
    a.move('t5', 'zero')

    # ---------------- entry(a0 = slot): fim de ConfirmPlacement numa entrada nova
    a.label('entry')
    a.addiu('sp', 'sp', -0x30)
    a.sw('ra', 0x2C, 'sp'); a.sw('s0', 0x28, 'sp'); a.sw('s1', 0x24, 'sp')
    a.sw('s2', 0x20, 'sp'); a.sw('s3', 0x1C, 'sp')
    a.move('s0', 'a0')
    a.move('t4', 'a0')
    a.jal('snapshot_slot')
    a.nop()
    a.beqz('t5', 'entry_done')
    a.move('s3', 't5')                          # delay: &snap[k][0]
    a.sw('zero', 0, 's3')                       # zera os 4 valores do slot
    # regra da carta que entrou: CONFIG + offsets[id]
    a.sll('t0', 's0', 3)
    a.subu('t0', 't0', 's0')
    a.sll('t0', 't0', 2)                        # slot * 28
    ch, cl = hi_lo(CARDS)
    a.lui('t1', ch); a.addiu('t1', 't1', cl)
    a.addu('t1', 't1', 't0')
    a.lh('t2', 0x0C, 't1')                      # id
    gh, gl = hi_lo(CONFIG)
    a.lui('t3', gh); a.addiu('t3', 't3', gl)
    a.sll('t2', 't2', 1)
    a.addu('t2', 't2', 't3')
    a.lhu('t2', 2, 't2')                        # offsets[id]
    a.nop()
    a.beqz('t2', 'entry_done')
    a.addu('s1', 't3', 't2')                    # delay: regra
    a.lbu('t0', 3, 's1')                        # bonus_count
    a.addiu('s1', 's1', 8)                      # primeiro bônus
    a.sltiu('t1', 't0', SNAP_BONUSES + 1)
    a.bnez('t1', 'entry_count')
    a.nop()
    a.ori('t0', 'zero', SNAP_BONUSES)
    a.label('entry_count')
    a.move('s2', 't0')                          # bônus restantes
    a.label('entry_loop')
    a.beqz('s2', 'entry_done')
    a.nop()
    a.lbu('t0', 0, 's1')
    a.lhu('t2', 2, 's1')
    a.ori('t1', 'zero', DECK_TYPE)
    a.beq('t0', 't1', 'entry_deck')
    a.ori('t1', 'zero', DECK_ID)
    a.bne('t0', 't1', 'entry_next')
    a.nop()
    a.label('entry_deck')
    a.andi('t3', 't2', 0xC000)
    a.ori('t1', 'zero', HAND_FLAG)
    a.bne('t3', 't1', 'entry_next')
    a.nop()
    a.move('a0', 's1')
    a.sltiu('a1', 's0', 15)
    a.jal('live')
    a.xori('a1', 'a1', 1)                       # delay: lado do slot (0 jogador, 1 rival)
    a.sltiu('t0', 'v0', 256)
    a.bnez('t0', 'entry_store')
    a.nop()
    a.ori('v0', 'zero', 255)
    a.label('entry_store')
    a.sb('v0', 0, 's3')
    a.label('entry_next')
    a.addiu('s1', 's1', 8)
    a.addiu('s3', 's3', 1)
    a.b('entry_loop')
    a.addiu('s2', 's2', -1)
    a.label('entry_done')
    a.move('a0', 's0')
    a.lw('ra', 0x2C, 'sp'); a.lw('s0', 0x28, 'sp'); a.lw('s1', 0x24, 'sp')
    a.lw('s2', 0x20, 'sp'); a.lw('s3', 0x1C, 'sp')
    a.j(follow)                                 # segue o salto anterior (summon_damage ou animação de LP)
    a.addiu('sp', 'sp', 0x30)
    a.label('snapshots')
    for _ in range(10 * SNAP_BONUSES // 4):
        a.word(0)
    return a


def block_size() -> int:
    return len(code(0x80100000))


def _j(target: int) -> int:
    return 0x08000000 | ((target & 0x0FFFFFFF) >> 2)


def _target(word: int) -> int:
    return 0x80000000 | ((word & 0x03FFFFFF) << 2)


def apply(exe: bytes, hook: int) -> tuple[bytes, dict]:
    site = exe_pos(CALL_SITE, exe, 4)
    if struct.unpack_from('<I', exe, site)[0] != _jal(COUNT_BONUS):
        raise ModError('Bônus na mão: a chamada de count_bonus do runtime não é a esperada.')
    entry_site = exe_pos(ENTRY_SITE, exe, 4)
    word = struct.unpack_from('<I', exe, entry_site)[0]
    if word >> 26 != 2:
        raise ModError('Bônus na mão: a entrada em campo do runtime não é a esperada.')
    follow = _target(word)          # summon_damage ou a animação de LP ao entrar (ps1_life_splash)
    block = code(hook, follow)
    at = exe_pos(hook, exe, len(block))
    if any(exe[at:at + len(block)]):
        raise ModError('Bônus na mão: a área reservada no SLUS não está livre.')
    out = bytearray(exe)
    out[at:at + len(block)] = block
    struct.pack_into('<I', out, site, _jal(hook))
    struct.pack_into('<I', out, entry_site, _j(_labels(hook, follow)['entry']))
    return bytes(out), {'status': 'aplicado', 'rotina': f'0x{hook:08X}',
                        'contagem': 'ao entrar em campo (fica fixa)', 'validado_epsxe': False}


def _follow_of(exe: bytes, hook: int) -> int | None:
    """Salto que o bloco instalado segue no fim de ``entry``."""
    marks = _labels(hook)
    at = exe_pos(marks['snapshots'] - 8, exe, 4)
    word = struct.unpack_from('<I', exe, at)[0]
    return _target(word) if word >> 26 == 2 else None


def runtime_view(exe: bytes) -> bytes:
    """SLUS com a chamada original de count_bonus e o salto de entrada anterior."""
    try:
        site = exe_pos(CALL_SITE, exe, 4)
        word = struct.unpack_from('<I', exe, site)[0]
        if word == _jal(COUNT_BONUS) or word >> 26 != 3:
            return exe
        hook = 0x80000000 | ((word & 0x03FFFFFF) << 2)
        follow = _follow_of(exe, hook)
        if follow is None:
            return exe
        block = code(hook, follow)
        at = exe_pos(hook, exe, len(block))
        if exe[at:at + len(block)] != block:
            return exe
    except Exception:
        return exe
    out = bytearray(exe)
    struct.pack_into('<I', out, site, _jal(COUNT_BONUS))
    entry_site = exe_pos(ENTRY_SITE, exe, 4)
    if struct.unpack_from('<I', exe, entry_site)[0] == _j(_labels(hook, follow)['entry']):
        struct.pack_into('<I', out, entry_site, _j(follow))
    return bytes(out)
