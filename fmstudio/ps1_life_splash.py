"""Animação de cura/dano quando um monstro com "ganha/causa LP ao entrar" entra em campo (PS1).

Sem isto, ``summon_damage`` (runtime do MOD) muda os LP direto, sem nenhum efeito
visual. Aqui a mudança passa a ser mostrada como as mágicas de LP do jogo:

* ``ConfirmPlacement`` termina com ``j summon_damage``; esse salto vai para
  ``summon``: guarda os LP dos dois lados, chama ``summon_damage``, mede quanto
  cada lado mudou, desfaz a mudança e põe até 2 mudanças numa fila.
* Para a primeira da fila cria o mesmo pedido de efeito das mágicas (id 5 =
  cura, como Dian Keto; id 6 = dano direto, como Hinotama) no centro da tela,
  com o som delas. O número mostrado é o da própria carta: o valor do banco de
  efeitos é trocado durante a animação e devolvido no fim.
* ``DuelScene_Update`` chama ``DuelEffect_UpdateRequests`` todo quadro; essa
  chamada passa por ``tick``, que espera o pedido terminar (a cena fica parada
  enquanto o efeito bloqueia, como nas mágicas), devolve o número original,
  aplica os LP e começa a próxima animação da fila.

Desenho igual ao do port de PC do decomp (``pc/cards/monster_effects_duel.c``,
``start_splash``); endereços conferidos em savestates do Drop x15.
"""
from __future__ import annotations

import struct

from .core import ModError
from .deep_extract import exe_pos
from .mips_asm import Asm, hi_lo

SUMMON_DAMAGE = 0x801CFDF8          # runtime do MOD (ConfirmPlacement faz j para cá)
SUMMON_SITE = 0x800FF74C            # j summon_damage no fim de ConfirmPlacement
TICK_SITE = 0x8002421C              # DuelScene_Update: jal DuelEffect_UpdateRequests
UPDATE_REQUESTS = 0x8002C6C8
CREATE_REQUEST = 0x8002C68C         # DuelEffect_CreateRequest(id) -> pedido ou 0
SE_PLAY = 0x8003FEE0                # SD_SEPlayFull(som)
LP = (0x800EA004, 0x800EA024)       # D_800E9FF0[lado].life_points (+0x14, passo 32)
HEAL_NUMBERS = 0x8015B4BC + 0x1C    # banco WA do efeito 5: s32 a cada 0x24
DAMAGE_NUMBERS = 0x8015B3D8 + 0x1C  # banco WA do efeito 6: s16 a cada 0x1E
HEAL, DAMAGE = 5, 6
SOUND = {HEAL: 0x14, DAMAGE: 0x1C}
REQUEST_ACTIVE = 0x80

SIGNATURE = {
    SUMMON_SITE: 0x08000000 | ((SUMMON_DAMAGE & 0x0FFFFFFF) >> 2),
    TICK_SITE: 0x0C000000 | ((UPDATE_REQUESTS & 0x0FFFFFFF) >> 2),
}
DATA_SIZE = 40   # count, (lado, delta) x2, pedido, endereço do número, número salvo, tipo


def _jump(op: int, address: int) -> int:
    return (op << 26) | ((address & 0x0FFFFFFF) >> 2)


def _assemble(base: int) -> Asm:
    a = Asm(base)

    def load_data(reg):
        a.la(reg, 'data')

    # ── summon(a0 = slot): mede a mudança de LP feita por summon_damage ──
    a.label('summon')
    a.addiu('sp', 'sp', -40)
    a.sw('ra', 36, 'sp'); a.sw('s0', 32, 'sp'); a.sw('s1', 28, 'sp')
    a.sw('s2', 24, 'sp'); a.sw('s3', 20, 'sp')
    a.move('s2', 'a0')
    load_data('s3')
    a.lw('t0', 0, 's3')
    a.nop()
    a.beq('t0', 'zero', 'summon_measure')
    a.nop()
    a.jal('flush')                    # sobrou fila de antes: aplica já
    a.nop()
    a.label('summon_measure')
    h0, l0 = hi_lo(LP[0]); h1, l1 = hi_lo(LP[1])
    a.lui('t0', h0); a.lhu('s0', l0, 't0')
    a.lui('t1', h1); a.lhu('s1', l1, 't1')
    a.jal(SUMMON_DAMAGE)
    a.move('a0', 's2')
    a.lui('t0', h0); a.lhu('t2', l0, 't0')
    a.lui('t1', h1); a.lhu('t3', l1, 't1')
    a.sh('s0', l0, 't0')              # desfaz: os LP mudam só depois da animação
    a.sh('s1', l1, 't1')
    a.subu('t2', 't2', 's0')
    a.subu('t3', 't3', 's1')
    a.move('t4', 'zero')
    a.beq('t2', 'zero', 'summon_side1')
    a.nop()
    a.sw('zero', 4, 's3')
    a.sw('t2', 8, 's3')
    a.addiu('t4', 't4', 1)
    a.label('summon_side1')
    a.beq('t3', 'zero', 'summon_queued')
    a.sll('t6', 't4', 3)
    a.addu('t6', 't6', 's3')
    a.li('t7', 1)
    a.sw('t7', 4, 't6')
    a.sw('t3', 8, 't6')
    a.addiu('t4', 't4', 1)
    a.label('summon_queued')
    a.sw('t4', 0, 's3')
    a.beq('t4', 'zero', 'summon_out')
    a.nop()
    a.jal('start')
    a.lw('a0', 8, 's3')
    a.label('summon_out')
    a.lw('ra', 36, 'sp'); a.lw('s0', 32, 'sp'); a.lw('s1', 28, 'sp')
    a.lw('s2', 24, 'sp'); a.lw('s3', 20, 'sp')
    a.jr('ra')
    a.addiu('sp', 'sp', 40)

    # ── start(a0 = delta): pedido de efeito 5/6 com o número da carta ──
    a.label('start')
    a.addiu('sp', 'sp', -32)
    a.sw('ra', 28, 'sp'); a.sw('s0', 24, 'sp'); a.sw('s1', 20, 'sp'); a.sw('s2', 16, 'sp')
    load_data('s1')
    a.sw('zero', 20, 's1')            # sem pedido até criar um
    a.sw('zero', 24, 's1')            # sem número trocado
    a.bltz('a0', 'start_damage')
    a.move('s0', 'a0')                # tamanho = |delta|
    a.li('t0', HEAL)
    a.la('t1', HEAL_NUMBERS)
    a.b('start_kind')
    a.li('t2', 0x24)
    a.label('start_damage')
    a.subu('s0', 'zero', 'a0')
    a.li('t0', DAMAGE)
    a.la('t1', DAMAGE_NUMBERS)
    a.li('t2', 0x1E)
    a.label('start_kind')
    a.sw('t0', 32, 's1')
    a.li('t7', 0x7FFF)                # o número da animação de dano é s16
    a.slt('t6', 't7', 's0')
    a.beq('t6', 'zero', 'start_sized')
    a.nop()
    a.move('s0', 't7')
    a.label('start_sized')
    # escolhe o maior "tamanho" do banco que não passa do valor (Dian Keto, Hinotama...)
    a.move('t3', 't1')                # melhor = configuração 0
    a.move('s2', 'zero')              # índice da melhor
    a.move('t4', 't1')
    a.li('t5', 1)                     # índice do cursor
    a.label('start_loop')
    a.addu('t4', 't4', 't2')
    a.li('t7', HEAL)
    a.bne('t0', 't7', 'start_loop_half')
    a.nop()
    a.lw('t6', 0, 't4')
    a.b('start_loop_abs')
    a.nop()
    a.label('start_loop_half')
    a.lh('t6', 0, 't4')
    a.nop()
    a.label('start_loop_abs')
    a.bgez('t6', 'start_loop_cmp')
    a.nop()
    a.subu('t6', 'zero', 't6')
    a.label('start_loop_cmp')
    a.beq('t6', 'zero', 'start_chosen')   # banco incompleto: para
    a.slt('t7', 's0', 't6')
    a.bne('t7', 'zero', 'start_chosen')
    a.nop()
    a.move('t3', 't4')
    a.move('s2', 't5')
    a.addiu('t5', 't5', 1)
    a.slti('t7', 't5', 5)
    a.bne('t7', 'zero', 'start_loop')
    a.nop()
    a.label('start_chosen')
    a.li('t7', HEAL)                  # número salvo da configuração escolhida
    a.bne('t0', 't7', 'start_saved_half')
    a.nop()
    a.lw('t6', 0, 't3')
    a.b('start_saved')
    a.nop()
    a.label('start_saved_half')
    a.lh('t6', 0, 't3')
    a.nop()
    a.label('start_saved')
    a.beq('t6', 'zero', 'start_out')  # banco de efeitos não carregado: tick aplica direto
    a.nop()
    a.sw('t3', 24, 's1')
    a.sw('t6', 28, 's1')
    a.move('t7', 's0')
    a.bgez('t6', 'start_write')
    a.nop()
    a.subu('t7', 'zero', 's0')        # o banco de dano guarda o número negativo
    a.label('start_write')
    a.li('t5', HEAL)
    a.bne('t0', 't5', 'start_write_half')
    a.nop()
    a.b('start_request')
    a.sw('t7', 0, 't3')
    a.label('start_write_half')
    a.sh('t7', 0, 't3')
    a.label('start_request')
    a.jal(CREATE_REQUEST)
    a.lw('a0', 32, 's1')
    a.beq('v0', 'zero', 'start_failed')
    a.sw('v0', 20, 's1')
    a.li('t0', 0xA0); a.sh('t0', 0, 'v0')
    a.li('t0', 0x78); a.sh('t0', 2, 'v0')
    a.sh('s2', 0x1A, 'v0')            # tamanho da explosão = carta da família
    a.lw('t0', 32, 's1')
    a.li('t1', HEAL)
    a.beq('t0', 't1', 'start_sound')
    a.li('a0', SOUND[HEAL])
    a.li('a0', SOUND[DAMAGE])
    a.label('start_sound')
    a.jal(SE_PLAY)
    a.nop()
    a.b('start_out')
    a.nop()
    a.label('start_failed')
    a.jal('restore')                  # nenhum pedido livre: devolve o número
    a.nop()
    a.label('start_out')
    a.lw('ra', 28, 'sp'); a.lw('s0', 24, 'sp'); a.lw('s1', 20, 'sp'); a.lw('s2', 16, 'sp')
    a.jr('ra')
    a.addiu('sp', 'sp', 32)

    # ── tick(): no lugar de DuelEffect_UpdateRequests ──
    a.label('tick')
    a.addiu('sp', 'sp', -24)
    a.sw('ra', 20, 'sp'); a.sw('s0', 16, 'sp')
    a.jal(UPDATE_REQUESTS)
    a.nop()
    a.sw('v0', 12, 'sp')
    load_data('s0')
    a.lw('t0', 0, 's0')
    a.lw('t1', 20, 's0')
    a.beq('t0', 'zero', 'tick_out')
    a.nop()
    a.beq('t1', 'zero', 'tick_finish')    # sem animação: aplica já
    a.nop()
    a.lbu('t2', 0x1C, 't1')
    a.lh('t3', 0x18, 't1')
    a.andi('t2', 't2', REQUEST_ACTIVE)
    a.beq('t2', 'zero', 'tick_finish')
    a.lw('t4', 32, 's0')
    a.nop()                               # load delay de t4
    a.beq('t3', 't4', 'tick_out')         # ainda é a nossa animação: espera
    a.nop()
    a.label('tick_finish')
    a.jal('restore')
    a.nop()
    a.jal('apply_front')
    a.nop()
    a.lw('t0', 0, 's0')
    a.nop()
    a.beq('t0', 'zero', 'tick_out')
    a.nop()
    a.jal('start')
    a.lw('a0', 8, 's0')
    a.label('tick_out')
    a.lw('v0', 12, 'sp')
    a.lw('ra', 20, 'sp'); a.lw('s0', 16, 'sp')
    a.jr('ra')
    a.addiu('sp', 'sp', 24)

    # ── restore(): devolve o número original do banco de efeitos ──
    a.label('restore')
    load_data('t0')
    a.lw('t1', 24, 't0')
    a.lw('t2', 28, 't0')
    a.beq('t1', 'zero', 'restore_out')
    a.lw('t3', 32, 't0')
    a.li('t4', HEAL)
    a.bne('t3', 't4', 'restore_half')
    a.sw('zero', 24, 't0')
    a.b('restore_out')
    a.sw('t2', 0, 't1')
    a.label('restore_half')
    a.sh('t2', 0, 't1')
    a.label('restore_out')
    a.jr('ra')
    a.nop()

    # ── apply_front(): aplica o primeiro da fila nos LP e anda a fila ──
    a.label('apply_front')
    load_data('t0')
    a.lw('t1', 4, 't0')               # lado
    a.lw('t2', 8, 't0')               # delta
    a.sll('t1', 't1', 5)
    a.la('t3', LP[0])
    a.addu('t3', 't3', 't1')
    a.lhu('t4', 0, 't3')
    a.nop()
    a.addu('t4', 't4', 't2')
    a.bgez('t4', 'apply_high')
    a.nop()
    a.move('t4', 'zero')
    a.label('apply_high')
    a.lui('t5', 1)
    a.slt('t6', 't4', 't5')
    a.bne('t6', 'zero', 'apply_store')
    a.nop()
    a.ori('t4', 'zero', 0xFFFF)
    a.label('apply_store')
    a.sh('t4', 0, 't3')
    a.lw('t1', 0, 't0')
    a.lw('t2', 12, 't0')
    a.addiu('t1', 't1', -1)
    a.sw('t1', 0, 't0')
    a.lw('t3', 16, 't0')
    a.sw('t2', 4, 't0')
    a.sw('t3', 8, 't0')
    a.sw('zero', 20, 't0')
    a.jr('ra')
    a.nop()

    # ── flush(): termina tudo o que estava na fila (nova entrada antes do fim) ──
    a.label('flush')
    a.addiu('sp', 'sp', -24)
    a.sw('ra', 20, 'sp'); a.sw('s0', 16, 'sp')
    a.jal('restore')
    a.nop()
    load_data('s0')
    a.label('flush_loop')
    a.lw('t0', 0, 's0')
    a.nop()
    a.blez('t0', 'flush_out')
    a.nop()
    a.jal('apply_front')
    a.nop()
    a.b('flush_loop')
    a.nop()
    a.label('flush_out')
    a.sw('zero', 0, 's0')
    a.lw('ra', 20, 'sp'); a.lw('s0', 16, 'sp')
    a.jr('ra')
    a.addiu('sp', 'sp', 24)

    # Alinhamento a 4 (o código já termina assim): o tamanho não pode depender
    # do endereço, pois block_size() é calculado antes da reserva.
    a.label('data')
    return a


def code(base: int) -> bytes:
    """Rotinas + área de dados (zerada) a partir de ``base``."""
    return _assemble(base).bytes() + bytes(DATA_SIZE)


def labels(base: int) -> dict[str, int]:
    assembled = _assemble(base)
    assembled.bytes()
    return dict(assembled.labels)


def wants_splash(project) -> bool:
    """Algum monstro ganha ou causa LP ao entrar em campo?"""
    for rows in (getattr(project, 'effects', None) or {}).values():
        for effect in rows or []:
            if effect.get('acao') in ('dano_lp', 'cura_lp') and effect.get('evento') == 'invocar':
                return True
    return False


def block_size() -> int:
    return len(code(0x80100000))


def has_summon_life(exe: bytes) -> bool:
    return struct.unpack_from('<I', exe, exe_pos(SUMMON_SITE, exe, 4))[0] == SIGNATURE[SUMMON_SITE]


def apply(exe: bytes, hook: int) -> tuple[bytes, dict]:
    for address, word in SIGNATURE.items():
        if struct.unpack_from('<I', exe, exe_pos(address, exe, 4))[0] != word:
            raise ModError(f'Animação de LP: o SLUS diverge do esperado em 0x{address:08X}.')
    block = code(hook)
    at = exe_pos(hook, exe, len(block))
    if any(exe[at:at + len(block)]):
        raise ModError('Animação de LP: a área reservada no SLUS não está livre.')
    entry = labels(hook)
    result = bytearray(exe)
    result[at:at + len(block)] = block
    struct.pack_into('<I', result, exe_pos(SUMMON_SITE, result, 4), _jump(2, entry['summon']))
    struct.pack_into('<I', result, exe_pos(TICK_SITE, result, 4), _jump(3, entry['tick']))
    return bytes(result), {'status': 'aplicado', 'rotina': f'0x{hook:08X}', 'validado_epsxe': False}


def status(exe: bytes) -> dict:
    word = struct.unpack_from('<I', exe, exe_pos(TICK_SITE, exe, 4))[0]
    if word == SIGNATURE[TICK_SITE]:
        return {'status': 'original'}
    return {'status': 'aplicado', 'tick': f'0x{0x80000000 | (word & 0x03FFFFFF) << 2:08X}'}


def runtime_view(exe: bytes) -> bytes:
    """O SLUS como o runtime original o deixou, sem o desvio da animação.

    ``apply`` troca uma palavra dentro do runtime (o ``j summon_damage`` em
    SUMMON_SITE). Quem confere o runtime byte a byte usa esta visão; ela só
    desfaz o desvio se a rotina inteira e o gancho do quadro estiverem
    instalados exatamente como ``apply`` os deixa.
    """
    try:
        site = exe_pos(SUMMON_SITE, exe, 4)
        word = struct.unpack_from('<I', exe, site)[0]
        if word == SIGNATURE[SUMMON_SITE] or word >> 26 != 2:
            return exe
        hook = (SUMMON_SITE & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        block = code(hook)
        at = exe_pos(hook, exe, len(block))
        tick = struct.unpack_from('<I', exe, exe_pos(TICK_SITE, exe, 4))[0]
        if (exe[at:at + len(block)] != block
                or tick != _jump(3, labels(hook)['tick'])):
            return exe
    except Exception:  # fora dos limites / SLUS de outro perfil: não mexe
        return exe
    out = bytearray(exe)
    struct.pack_into('<I', out, site, SIGNATURE[SUMMON_SITE])
    return bytes(out)
