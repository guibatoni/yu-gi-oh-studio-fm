"""Vínculo com Vida no PS1: ganha LP quando a carta entra em batalha.

Regra (igual no simulador do Studio): quando um monstro com Vínculo com Vida
ataca (outro monstro ou direto) ou é atacado por um monstro, o dono dele ganha
LP igual ao ATK atual da carta (com bônus de campo/equipamentos já somados).
Ao trocar golpes entre dois monstros com o efeito, os dois donos ganham.

Implementação sem recompilar o runtime:

* a regra da carta recebe o bit 0x80 no byte ``protection`` (livre no runtime:
  ``protection()`` só testa bits específicos);
* a entrada da cena de batalha (tabela 0x800909BC, hoje ``Battle`` do runtime)
  passa por ``wrapper``: chama ``Battle`` e, se ``duel.battle_active`` passou
  de 0 para 1 (início de uma batalha), confere atacante (``duel.battle[0]``) e
  alvo (``duel.battle[1]``; -1 = ataque direto) e cura os donos.

``runtime_view`` devolve o SLUS como o runtime o deixa, para a conferência
byte a byte do runtime (o mesmo cuidado de ps1_life_splash).
"""
from __future__ import annotations

import struct

from .core import ModError
from .deep_extract import exe_pos
from .mips_asm import Asm, hi_lo

LIFELINK = 0x80                     # bit livre em Rules.protection
TABLE_SITE = 0x800909BC             # cena de batalha na tabela de cenas
BATTLE = 0x800FEB8C                 # ENTRY_POINTS['Battle'] (runtime 722 e 740)
DUEL_BATTLE = 0x801CD780            # duel.battle[2], battle_active (+2)
CARDS = 0x801A7AD8                  # Card[30], passo 28: id +0x0C, attack +0x0E, flags +0x16
CONFIG = 0x801CD7A0                 # Config: offsets[id] em +2 + 2*id
SIDE_LP = 0x800E9FF0 + 0x14         # LP do lado 0; lado 1 em +32
OCCUPIED = 0x8000


def code(base: int, capacity: int) -> bytes:
    a = Asm(base)
    # wrapper: chamado pela tabela de cenas no lugar de Battle
    a.label('wrapper')
    a.addiu('sp', 'sp', -0x20)
    a.sw('ra', 0x1C, 'sp'); a.sw('s0', 0x18, 'sp'); a.sw('s1', 0x14, 'sp')
    high, low = hi_lo(DUEL_BATTLE)
    a.lui('s0', high); a.addiu('s0', 's0', low)
    a.jal(BATTLE)
    a.lbu('s1', 2, 's0')                        # battle_active antes
    a.bnez('s1', 'out')
    a.lbu('t0', 2, 's0')                        # delay: battle_active depois
    a.nop()                                     # load delay
    a.beqz('t0', 'out')
    a.nop()
    a.jal('heal')
    a.lb('a0', 0, 's0')                         # atacante
    a.jal('heal')
    a.lb('a0', 1, 's0')                         # alvo (-1 = direto)
    a.label('out')
    a.lw('ra', 0x1C, 'sp'); a.lw('s0', 0x18, 'sp'); a.lw('s1', 0x14, 'sp')
    a.jr('ra')
    a.addiu('sp', 'sp', 0x20)

    # heal(slot): folha, só registradores t
    a.label('heal')
    a.bltz('a0', 'ret')                         # sem monstro (ataque direto)
    a.addiu('t0', 'a0', -5)
    a.sltiu('t1', 't0', 5)                      # 5..9: monstros do lado 0
    a.bnez('t1', 'zone')
    a.addiu('t0', 'a0', -20)
    a.sltiu('t1', 't0', 5)                      # 20..24: monstros do lado 1
    a.beqz('t1', 'ret')
    a.nop()
    a.label('zone')
    a.sll('t0', 'a0', 3); a.subu('t0', 't0', 'a0'); a.sll('t0', 't0', 2)  # slot * 28
    ch, cl = hi_lo(CARDS)
    a.lui('t1', ch); a.addiu('t1', 't1', cl); a.addu('t1', 't1', 't0')
    a.lhu('t2', 0x16, 't1')                     # flags
    a.lh('t3', 0x0C, 't1')                      # id
    a.andi('t2', 't2', OCCUPIED)
    a.beqz('t2', 'ret')
    a.addiu('t4', 't3', -1)
    a.sltiu('t4', 't4', capacity)
    a.beqz('t4', 'ret')
    a.sll('t3', 't3', 1)
    gh, gl = hi_lo(CONFIG)
    a.lui('t5', gh); a.addiu('t5', 't5', gl)
    a.addu('t3', 't3', 't5')
    a.lhu('t3', 2, 't3')                        # CONFIG->offsets[id]
    a.nop()
    a.beqz('t3', 'ret')
    a.addu('t3', 't3', 't5')
    a.lbu('t3', 0, 't3')                        # Rules.protection
    a.lh('t2', 0x0E, 't1')                      # ATK atual
    a.andi('t3', 't3', LIFELINK)
    a.beqz('t3', 'ret')
    a.nop()
    a.blez('t2', 'ret')
    a.sltiu('t0', 'a0', 15)                     # lado 0 se slot < 15
    a.xori('t0', 't0', 1)
    a.sll('t0', 't0', 5)
    lh, ll = hi_lo(SIDE_LP)
    a.lui('t1', lh); a.addiu('t1', 't1', ll); a.addu('t1', 't1', 't0')
    a.lhu('t3', 0, 't1')
    a.nop()
    a.addu('t3', 't3', 't2')
    a.srl('t4', 't3', 16)
    a.beqz('t4', 'store')
    a.nop()
    a.ori('t3', 'zero', 0xFFFF)                 # LP é u16: 65535 no máximo
    a.label('store')
    a.sh('t3', 0, 't1')
    a.label('ret')
    a.jr('ra')
    a.nop()
    return a.bytes()


def block_size() -> int:
    return len(code(0x80100000, 722))


def wants_lifelink(plan) -> bool:
    return any(action == 'vinculo_vida' for _, action in getattr(plan, 'accepted', ()))


def _word(exe: bytes, address: int) -> int:
    return struct.unpack_from('<I', exe, exe_pos(address, exe, 4))[0]


def apply(exe: bytes, hook: int, capacity: int) -> tuple[bytes, dict]:
    if _word(exe, TABLE_SITE) != BATTLE:
        raise ModError('Vínculo com Vida: a cena de batalha do runtime não está instalada.')
    block = code(hook, capacity)
    at = exe_pos(hook, exe, len(block))
    if any(exe[at:at + len(block)]):
        raise ModError('Vínculo com Vida: a área reservada no SLUS não está livre.')
    out = bytearray(exe)
    out[at:at + len(block)] = block
    struct.pack_into('<I', out, exe_pos(TABLE_SITE, exe, 4), hook)
    return bytes(out), {'status': 'aplicado', 'rotina': f'0x{hook:08X}',
                        'regra': 'ATK atual ao atacar ou ser atacado', 'validado_epsxe': False}


def installed(exe: bytes, capacity: int) -> bool:
    try:
        hook = _word(exe, TABLE_SITE)
        if hook == BATTLE or not 0x80010000 <= hook < 0x80200000:
            return False
        block = code(hook, capacity)
        at = exe_pos(hook, exe, len(block))
        return exe[at:at + len(block)] == block
    except Exception:
        return False


def runtime_view(exe: bytes) -> bytes:
    """SLUS com a cena de batalha apontando de volta para ``Battle``."""
    for capacity in (722, 740):
        if installed(exe, capacity):
            out = bytearray(exe)
            struct.pack_into('<I', out, exe_pos(TABLE_SITE, exe, 4), BATTLE)
            return bytes(out)
    return exe
