"""Efeitos de entrada com animações das mágicas do jogo (PS1).

Quando um monstro entra em campo, a regra dele pode pedir:

* ``limpar_armadilhas``   → efeito da 672 (Harpie's Feather Duster);
* ``revelar_cartas``      → efeito da 350 (Dark-piercing Light);
* ``espadas_reveladoras`` → efeito da 348 (Swords of Revealing Light) por 1-3 turnos;
* ``mudar_terreno``       → efeito das mágicas de terreno (330-335) ou terreno 0 (normal);
* ``trocar_posicao``      → giro da Stop Defense nos monstros do oponente (ataque ↔ defesa);
* ``dano_monstro_alvo``   → animação da 349 com o número do dano no monstro mais forte do
  oponente; se o dano for fatal (>= DEF atual), animação do Crush Card só nele.

E o Vínculo com Vida (ps1_lifelink) mostra a animação de cura com o número curado.

Como funciona (sem recompilar o runtime):

* O jogo roda as mágicas pela fila de efeito: ``Duel_StartMagicEffect`` grava id/índice
  e ``EFFECT_FLAGS``; todo quadro ``DuelScene_Update`` chama ``Duel_RunMagicEffect``
  (``jal`` em 0x8002424C), que chama o tratador do "tipo" da mágica e, enquanto o efeito
  estiver ativo, deixa a cena parada.
* A tabela de tratadores tem um tipo 14 sem uso (0x80090ACC/0x80090AD0 → função vazia).
  O índice 0 (id 301) passa a ser do tipo 14 e o tratador 14 passa a ser ``handler``,
  que executa uma fila de operações; nas operações das mágicas ele chama o tratador
  original da mágica (pela tabela, então os filtros de imunidade do runtime continuam
  valendo) e só segue para a próxima quando ele termina.
* ``ConfirmPlacement`` termina com ``j summon_damage`` (0x800FF74C); esse salto passa por
  ``entry``, que põe na fila os códigos 11-14 da regra da carta e segue o salto anterior.
* A chamada de 0x8002424C passa por ``run``: com a cena de campo (FIELD) e nada rodando,
  se houver fila (ou cura do Vínculo com Vida a mostrar) liga o efeito 301 (tipo 14).
"""
from __future__ import annotations

import struct

from .core import ModError
from .deep_extract import exe_pos
from .mips_asm import Asm, hi_lo

# ── códigos nas regras (Bonus.action >= 7: CalculateStats ignora) ──
OP_SPELL = 11       # scope = tipo do tratador, match = id da mágica, attack = turnos (Espadas)
OP_TERRAIN = 12     # match = terreno 0..6 (0 = normal)
OP_DAMAGE = 13      # attack = dano
OP_TOGGLE = 14      # troca ataque/defesa dos monstros do oponente
OP_CRUSH = 15       # interno: dano fatal vira o Crush Card só no alvo
OP_HEAL = 16        # interno: animação de cura do Vínculo com Vida
ENTRY_CODES = (OP_SPELL, OP_TERRAIN, OP_DAMAGE, OP_TOGGLE)

SPELLS = {  # ação do Studio → (id da mágica, tipo do tratador)
    'limpar_armadilhas': (672, 13),
    'revelar_cartas': (350, 8),
    'espadas_reveladoras': (348, 10),
}
CRUSH_CARD, CRUSH_KIND = 661, 5
TERRAIN_KIND = 1
SWORDS_KIND = 10

# ── endereços do jogo (SLUS-01411) ──
RUN_SITE = 0x8002424C          # DuelScene_Update: jal Duel_RunMagicEffect
RUN_EFFECT = 0x80026B34
ENTRY_SITE = 0x800FF74C        # fim de ConfirmPlacement (runtime): j summon_damage
HANDLERS = 0x80090A5C          # [tipo*2 + (flags & 0x4000 ? 1 : 0)]
KINDS = 0x80090AD4             # u8 por índice de mágica
OWN_KIND = 14
OWN_SLOT = HANDLERS + OWN_KIND * 8 + 4
EMPTY_HANDLER = 0x80024E4C
OWN_ID = 301                   # índice 0 → tipo 14
EFFECT_FLAGS = 0x8009B220
EFFECT_ID = 0x8009B1D2
EFFECT_INDEX = 0x8009B1A8
EFFECT_OBJ = 0x8009B17C
REMOVAL_THRESHOLD = 0x8009B1AC
SCENE = 0x8009B23A
TURN = 0x8009B1D5
SLOT_TABLE = 0x800907D8        # u8 [lado*20 + posição]
POS_TABLE = 0x80090800         # (x, z) s16 [lado*80 + posição*4]
CARDS = 0x801A7AD8             # Card: object +0, id +0xC, modifier +0x12, flags +0x16
CONFIG = 0x801CD7A0
SIDES = 0x800E9FF0             # passo 32; +0x19 = turnos das Espadas
CREATE = 0x8002C604            # DuelEffect_Create(tipo)
CREATE_REQUEST = 0x8002C68C    # idem, bloqueando a cena
SE_PLAY = 0x8003FEE0
ROTATE = 0x80019BA0            # (objeto, ângulo de, ângulo para, quadros)
CALC = 0x800170C8              # CalculateStats(card) → def << 16 | atk
HEAL_NUMBERS = 0x8015B4BC + 0x1C   # banco do efeito 5 (cura), s32 da configuração 0
OCCUPIED, DEFENSE = 0x8000, 0x0800
FIELD, STARTUP, DRAW = 5, 1, 2
QUEUE = 8
WAIT_LIMIT = 300               # quadros no máximo esperando uma animação

# ── dados (offsets a partir de 'data') ──
D_COUNT = 0
D_QUEUE = 4                    # QUEUE x 8 bytes: op, lado, tipo, -, valor u16, extra u16
D_CUR = D_QUEUE + QUEUE * 8    # operação em andamento (8 bytes, extra = u32 na cura)
D_STEP = D_CUR + 8
D_K = D_STEP + 4
D_OBJ = D_K + 4
D_TARGET = D_OBJ + 4
D_FRAMES = D_TARGET + 4
D_SAVED = D_FRAMES + 4
D_HIDDEN = D_SAVED + 4
D_TARGET_K = D_HIDDEN + 4
DATA_SIZE = D_TARGET_K + 4


def _j(target: int) -> int:
    return 0x08000000 | ((target & 0x0FFFFFFF) >> 2)


def _jal(target: int) -> int:
    return 0x0C000000 | ((target & 0x0FFFFFFF) >> 2)


def _target(word: int) -> int:
    return 0x80000000 | ((word & 0x03FFFFFF) << 2)


def _assemble(base: int, capacity: int, follow: int | None, heal_pending: int | None) -> Asm:
    a = Asm(base)

    def li32(reg, value):
        h, l = hi_lo(value)
        a.lui(reg, h)
        a.addiu(reg, reg, l)

    # ── run(): no lugar de jal Duel_RunMagicEffect ──
    a.label('run')
    a.addiu('sp', 'sp', -24)
    a.sw('ra', 20, 'sp')
    li32('t0', EFFECT_FLAGS)
    a.lhu('t1', 0, 't0')
    a.la('t5', 'data')
    a.andi('t1', 't1', 0x8000)
    a.bne('t1', 'zero', 'run_call')            # já há efeito: segue o jogo
    a.nop()
    li32('t2', SCENE)
    a.lhu('t3', 0, 't2')
    a.nop()
    a.andi('t3', 't3', 15)
    a.li('t4', STARTUP)
    a.beq('t3', 't4', 'run_clear')
    a.li('t4', DRAW)
    a.beq('t3', 't4', 'run_clear')
    a.li('t4', FIELD)
    a.bne('t3', 't4', 'run_call')
    a.nop()
    a.lw('t6', D_COUNT, 't5')
    a.nop()
    if heal_pending is not None:
        li32('t8', heal_pending)
        a.lw('t7', 0, 't8')
        a.lw('t9', 4, 't8')
        a.or_('t6', 't6', 't7')
        a.or_('t6', 't6', 't9')
    a.beq('t6', 'zero', 'run_call')
    a.nop()
    a.li('t6', OWN_ID)
    li32('t7', EFFECT_ID)
    a.sh('t6', 0, 't7')
    li32('t7', EFFECT_INDEX)
    a.sh('zero', 0, 't7')
    a.sb('zero', D_CUR, 't5')                  # nenhuma operação em andamento
    a.ori('t6', 'zero', 0xC000)
    a.b('run_call')
    a.sh('t6', 0, 't0')
    a.label('run_clear')                       # duelo novo / turno novo: nada pendente
    a.sw('zero', D_COUNT, 't5')
    a.sb('zero', D_CUR, 't5')
    if heal_pending is not None:
        li32('t8', heal_pending)
        a.sw('zero', 0, 't8')
        a.sw('zero', 4, 't8')
    a.label('run_call')
    a.jal(RUN_EFFECT)
    a.nop()
    a.lw('ra', 20, 'sp')
    a.nop()
    a.jr('ra')
    a.addiu('sp', 'sp', 24)

    # ── entry(a0 = slot): enfileira os efeitos de entrada e segue o salto anterior ──
    a.label('entry')
    if follow is not None:
        a.addiu('sp', 'sp', -24)
        a.sw('ra', 20, 'sp'); a.sw('a0', 16, 'sp')
        a.sll('t0', 'a0', 3); a.subu('t0', 't0', 'a0'); a.sll('t0', 't0', 2)
        li32('t1', CARDS)
        a.addu('t1', 't1', 't0')
        a.lhu('t2', 0x0C, 't1')                # id
        a.nop()
        a.addiu('t3', 't2', -1)
        a.sltiu('t3', 't3', capacity)
        a.beq('t3', 'zero', 'entry_out')
        a.sll('t2', 't2', 1)
        li32('t4', CONFIG)
        a.addu('t2', 't2', 't4')
        a.lhu('t2', 2, 't2')                   # offsets[id]
        a.nop()
        a.beq('t2', 'zero', 'entry_out')
        a.addu('t2', 't2', 't4')               # Rules
        a.lbu('t3', 3, 't2')                   # quantidade de bônus
        a.addiu('t2', 't2', 8)
        a.sltiu('t6', 'a0', 15)
        a.xori('t6', 't6', 1)                  # lado do monstro
        a.la('t5', 'data')
        a.label('entry_loop')
        a.beq('t3', 'zero', 'entry_out')
        a.nop()
        a.lbu('t7', 0, 't2')
        a.nop()
        a.addiu('t8', 't7', -OP_SPELL)
        a.sltiu('t8', 't8', len(ENTRY_CODES))
        a.beq('t8', 'zero', 'entry_next')
        a.nop()
        a.lw('t8', D_COUNT, 't5')
        a.nop()
        a.sltiu('t9', 't8', QUEUE)
        a.beq('t9', 'zero', 'entry_out')       # fila cheia
        a.sll('t9', 't8', 3)
        a.addu('t9', 't9', 't5')
        a.sb('t7', D_QUEUE + 0, 't9')
        a.sb('t6', D_QUEUE + 1, 't9')
        a.lbu('t0', 1, 't2')
        a.lhu('t1', 2, 't2')
        a.lhu('t4', 4, 't2')
        a.sb('t0', D_QUEUE + 2, 't9')
        a.sh('t1', D_QUEUE + 4, 't9')
        a.sh('t4', D_QUEUE + 6, 't9')
        a.addiu('t8', 't8', 1)
        a.sw('t8', D_COUNT, 't5')
        a.label('entry_next')
        a.addiu('t3', 't3', -1)
        a.b('entry_loop')
        a.addiu('t2', 't2', 8)
        a.label('entry_out')
        a.lw('a0', 16, 'sp')
        a.lw('ra', 20, 'sp')
        a.addiu('sp', 'sp', 24)
        a.j(follow)
        a.nop()
    else:
        a.jr('ra')
        a.nop()

    # ── handler(): tipo 14 de Duel_RunMagicEffect, uma chamada por quadro ──
    a.label('handler')
    a.addiu('sp', 'sp', -40)
    a.sw('ra', 36, 'sp'); a.sw('s0', 32, 'sp'); a.sw('s1', 28, 'sp')
    a.sw('s2', 24, 'sp'); a.sw('s3', 20, 'sp')
    a.la('s0', 'data')
    a.lbu('t0', D_CUR, 's0')
    a.nop()
    a.bne('t0', 'zero', 'dispatch')
    a.nop()
    # pega a próxima operação: cura do Vínculo com Vida primeiro
    if heal_pending is not None:
        li32('t8', heal_pending)
        for side in (0, 1):
            a.lw('t1', 4 * side, 't8')
            a.nop()
            a.beq('t1', 'zero', f'pop_heal_skip{side}')
            a.nop()
            a.sw('zero', 4 * side, 't8')
            a.li('t2', OP_HEAL)
            a.sb('t2', D_CUR, 's0')
            a.li('t2', side)
            a.sb('t2', D_CUR + 1, 's0')
            a.b('op_begin')
            a.sw('t1', D_CUR + 4, 's0')
            a.label(f'pop_heal_skip{side}')
    a.lw('t3', D_COUNT, 's0')
    a.nop()
    a.beq('t3', 'zero', 'finish_all')
    a.nop()
    a.lw('t4', D_QUEUE, 's0')
    a.lw('t5', D_QUEUE + 4, 's0')
    a.sw('t4', D_CUR, 's0')
    a.sw('t5', D_CUR + 4, 's0')
    for i in range(1, QUEUE):                  # anda a fila
        a.lw('t4', D_QUEUE + 8 * i, 's0')
        a.lw('t5', D_QUEUE + 8 * i + 4, 's0')
        a.sw('t4', D_QUEUE + 8 * (i - 1), 's0')
        a.sw('t5', D_QUEUE + 8 * (i - 1) + 4, 's0')
    a.addiu('t3', 't3', -1)
    a.sw('t3', D_COUNT, 's0')
    a.label('op_begin')
    a.sw('zero', D_STEP, 's0')
    a.sw('zero', D_K, 's0')
    a.sw('zero', D_FRAMES, 's0')
    a.sw('zero', D_HIDDEN, 's0')
    li32('t0', EFFECT_FLAGS)
    a.ori('t1', 'zero', 0xC000)
    a.sh('t1', 0, 't0')
    a.label('dispatch')
    a.lbu('t0', D_CUR, 's0')
    a.nop()
    for op, label in ((OP_SPELL, 'stock'), (OP_TERRAIN, 'stock'), (OP_CRUSH, 'stock'),
                      (OP_DAMAGE, 'damage'), (OP_TOGGLE, 'toggle'), (OP_HEAL, 'heal')):
        a.li('t1', op)
        a.beq('t0', 't1', label)
        a.nop()
    # código desconhecido: descarta
    a.label('op_done')
    a.sb('zero', D_CUR, 's0')
    li32('t0', EFFECT_ID)
    a.li('t1', OWN_ID)
    a.sh('t1', 0, 't0')
    li32('t0', EFFECT_FLAGS)
    a.ori('t1', 'zero', 0xC000)                # segue ocupado: a próxima roda no quadro seguinte
    a.b('handler_out')
    a.sh('t1', 0, 't0')
    a.label('finish_all')
    li32('t0', EFFECT_FLAGS)
    a.sh('zero', 0, 't0')
    li32('t0', EFFECT_ID)
    a.li('t1', OWN_ID)
    a.sh('t1', 0, 't0')
    a.label('handler_out')
    a.lw('ra', 36, 'sp'); a.lw('s0', 32, 'sp'); a.lw('s1', 28, 'sp')
    a.lw('s2', 24, 'sp'); a.lw('s3', 20, 'sp')
    a.jr('ra')
    a.addiu('sp', 'sp', 40)

    # card_at(a0 = posição 0..4 do oponente) → v0 = Card*
    a.label('card_at')
    li32('t0', TURN)
    a.lbu('t1', 0, 't0')
    li32('t2', SLOT_TABLE)
    a.sll('t3', 't1', 2); a.addu('t3', 't3', 't1'); a.sll('t3', 't3', 2)   # TURN*20
    a.addu('t3', 't3', 'a0')
    a.addu('t3', 't3', 't2')
    a.lbu('t3', 5, 't3')
    li32('v0', CARDS)
    a.sll('t4', 't3', 3); a.subu('t4', 't4', 't3'); a.sll('t4', 't4', 2)
    a.jr('ra')
    a.addu('v0', 'v0', 't4')

    # hide(): esconde os monstros do oponente que não são o alvo (Crush só no alvo)
    a.label('hide')
    a.addiu('sp', 'sp', -24)
    a.sw('ra', 20, 'sp'); a.sw('s1', 16, 'sp'); a.sw('s2', 12, 'sp')
    a.move('s1', 'zero')
    a.sw('zero', D_HIDDEN, 's0')
    a.label('hide_loop')
    a.jal('card_at')
    a.move('a0', 's1')
    a.lw('t5', D_TARGET, 's0')
    a.lhu('t6', 0x16, 'v0')
    a.beq('v0', 't5', 'hide_next')
    a.andi('t7', 't6', OCCUPIED)
    a.beq('t7', 'zero', 'hide_next')
    a.xori('t6', 't6', OCCUPIED)
    a.sh('t6', 0x16, 'v0')
    a.lw('t8', D_HIDDEN, 's0')
    a.li('t9', 1)
    a.sllv('t9', 't9', 's1')
    a.or_('t8', 't8', 't9')
    a.sw('t8', D_HIDDEN, 's0')
    a.label('hide_next')
    a.addiu('s1', 's1', 1)
    a.slti('t0', 's1', 5)
    a.bne('t0', 'zero', 'hide_loop')
    a.nop()
    a.lw('ra', 20, 'sp'); a.lw('s1', 16, 'sp'); a.lw('s2', 12, 'sp')
    a.jr('ra')
    a.addiu('sp', 'sp', 24)

    # unhide(): devolve OCCUPIED de quem hide() escondeu
    a.label('unhide')
    a.addiu('sp', 'sp', -24)
    a.sw('ra', 20, 'sp'); a.sw('s1', 16, 'sp')
    a.move('s1', 'zero')
    a.label('unhide_loop')
    a.lw('t8', D_HIDDEN, 's0')
    a.nop()
    a.srlv('t8', 't8', 's1')
    a.andi('t8', 't8', 1)
    a.beq('t8', 'zero', 'unhide_next')
    a.nop()
    a.jal('card_at')
    a.move('a0', 's1')
    a.lhu('t6', 0x16, 'v0')
    a.nop()
    a.ori('t6', 't6', OCCUPIED)
    a.sh('t6', 0x16, 'v0')
    a.label('unhide_next')
    a.addiu('s1', 's1', 1)
    a.slti('t0', 's1', 5)
    a.bne('t0', 'zero', 'unhide_loop')
    a.nop()
    a.sw('zero', D_HIDDEN, 's0')
    a.lw('ra', 20, 'sp'); a.lw('s1', 16, 'sp')
    a.jr('ra')
    a.addiu('sp', 'sp', 24)

    # ── stock: chama o tratador original da mágica até ele terminar ──
    a.label('stock')
    a.lw('t1', D_STEP, 's0')
    a.nop()
    a.bne('t1', 'zero', 'stock_run')
    a.nop()
    a.lhu('t2', D_CUR + 4, 's0')               # id (ou terreno)
    a.li('t3', OP_TERRAIN)
    a.bne('t0', 't3', 'stock_id')
    a.nop()
    a.addiu('t2', 't2', 329)                   # 329 + terreno: o tratador usa id - 0x149
    a.li('t3', TERRAIN_KIND)
    a.sb('t3', D_CUR + 2, 's0')
    a.label('stock_id')
    li32('t4', EFFECT_ID)
    a.sh('t2', 0, 't4')
    a.li('t1', 1)
    a.sw('t1', D_STEP, 's0')
    a.label('stock_run')
    a.lbu('t0', D_CUR, 's0')
    a.li('t1', OP_CRUSH)
    a.bne('t0', 't1', 'stock_call')
    a.nop()
    a.jal('hide')
    a.nop()
    a.label('stock_call')
    a.lbu('t2', D_CUR + 2, 's0')               # tipo do tratador
    li32('t3', HANDLERS + 4)
    a.sll('t2', 't2', 3)
    a.addu('t3', 't3', 't2')
    a.lw('t3', 0, 't3')
    a.nop()
    a.jalr('t3')
    a.nop()
    a.lbu('t0', D_CUR, 's0')
    a.li('t1', OP_CRUSH)
    a.bne('t0', 't1', 'stock_after')
    a.nop()
    a.jal('unhide')
    a.nop()
    a.label('stock_after')
    a.lw('t1', D_FRAMES, 's0')
    a.lbu('t0', D_CUR, 's0')
    a.addiu('t1', 't1', 1)
    a.sw('t1', D_FRAMES, 's0')
    a.li('t2', 1)
    a.bne('t1', 't2', 'stock_check')
    a.nop()
    # 1ª chamada: ajustes
    a.li('t2', OP_CRUSH)
    a.bne('t0', 't2', 'stock_terrain_fix')
    a.nop()
    li32('t3', REMOVAL_THRESHOLD)
    a.sh('zero', 0, 't3')                      # Crush: ATK >= 0 (o alvo, sempre)
    li32('t3', EFFECT_FLAGS)
    a.lhu('t4', 0, 't3')
    a.nop()
    a.ori('t4', 't4', 1)                       # modo ATK (mesmo se a regra do Crush for por tipo)
    a.b('stock_check')
    a.sh('t4', 0, 't3')
    a.label('stock_terrain_fix')
    a.li('t2', OP_TERRAIN)
    a.bne('t0', 't2', 'stock_check')
    a.nop()
    li32('t3', EFFECT_OBJ)
    a.lw('t3', 0, 't3')
    a.nop()
    a.beq('t3', 'zero', 'stock_check')
    a.nop()
    a.lh('t4', 0x1A, 't3')
    a.nop()
    a.bgez('t4', 'stock_check')
    a.nop()
    a.sh('zero', 0x1A, 't3')                   # terreno normal: visual da variante 0
    a.label('stock_check')
    li32('t0', EFFECT_FLAGS)
    a.lhu('t1', 0, 't0')
    a.nop()
    a.andi('t1', 't1', 0x8000)
    a.bne('t1', 'zero', 'handler_out')         # a mágica ainda está rodando
    a.nop()
    # terminou: Espadas com outro número de turnos
    a.lbu('t0', D_CUR, 's0')
    a.lbu('t2', D_CUR + 2, 's0')
    a.li('t1', OP_SPELL)
    a.bne('t0', 't1', 'op_done')
    a.li('t1', SWORDS_KIND)
    a.bne('t2', 't1', 'op_done')
    a.lhu('t3', D_CUR + 6, 's0')               # turnos
    a.nop()
    a.beq('t3', 'zero', 'op_done')
    a.addiu('t3', 't3', 1)                     # o jogo grava 4 para 3 turnos
    li32('t4', TURN)
    a.lbu('t5', 0, 't4')
    li32('t6', SIDES)
    a.xori('t5', 't5', 1)
    a.sll('t5', 't5', 5)
    a.addu('t6', 't6', 't5')
    a.b('op_done')
    a.sb('t3', 0x19, 't6')

    # ── damage: número da 349 no monstro mais forte do oponente; fatal → Crush ──
    a.label('damage')
    a.lw('t1', D_STEP, 's0')
    a.nop()
    a.bne('t1', 'zero', 'wait_obj')
    a.nop()
    a.li('s1', -1)                             # melhor ATK
    a.sw('zero', D_TARGET, 's0')
    a.move('s2', 'zero')                       # posição
    a.label('damage_scan')
    a.jal('card_at')
    a.move('a0', 's2')
    a.lhu('t6', 0x16, 'v0')
    a.move('s3', 'v0')
    a.andi('t6', 't6', OCCUPIED)
    a.beq('t6', 'zero', 'damage_next')
    a.nop()
    a.jal(CALC)
    a.move('a0', 's3')
    a.andi('t1', 'v0', 0xFFFF)
    a.slt('t2', 's1', 't1')
    a.beq('t2', 'zero', 'damage_next')
    a.nop()
    a.move('s1', 't1')
    a.sw('s3', D_TARGET, 's0')
    a.sw('s2', D_TARGET_K, 's0')
    a.srl('t3', 'v0', 16)
    a.sw('t3', D_SAVED, 's0')                  # DEF atual do alvo
    a.label('damage_next')
    a.addiu('s2', 's2', 1)
    a.slti('t0', 's2', 5)
    a.bne('t0', 'zero', 'damage_scan')
    a.nop()
    a.lw('s3', D_TARGET, 's0')
    a.nop()
    a.beq('s3', 'zero', 'op_done')             # oponente sem monstros
    a.nop()
    a.lhu('t1', D_CUR + 6, 's0')               # dano
    a.lw('t2', D_SAVED, 's0')
    a.nop()
    a.sltu('t3', 't1', 't2')
    a.bne('t3', 'zero', 'damage_number')
    a.nop()
    # fatal: vira Crush Card só no alvo (no próximo quadro)
    a.li('t4', OP_CRUSH)
    a.sb('t4', D_CUR, 's0')
    a.li('t4', CRUSH_KIND)
    a.sb('t4', D_CUR + 2, 's0')
    a.li('t4', CRUSH_CARD)
    a.sh('t4', D_CUR + 4, 's0')
    a.b('handler_out')
    a.sw('zero', D_FRAMES, 's0')
    a.label('damage_number')
    a.lhu('t5', 0x12, 's3')                    # modifier -= dano
    a.nop()
    a.subu('t5', 't5', 't1')
    a.sh('t5', 0x12, 's3')
    a.jal(CREATE)
    a.li('a0', 0x0D)
    a.beq('v0', 'zero', 'op_done')             # sem objeto livre: só o efeito
    a.sw('v0', D_OBJ, 's0')
    a.lw('t0', 0, 's3')                        # objeto 3D da carta
    a.nop()
    a.lhu('t1', 0x30, 't0'); a.lhu('t2', 0x32, 't0'); a.lhu('t3', 0x34, 't0')
    a.sh('t1', 0, 'v0'); a.sh('t2', 2, 'v0'); a.sh('t3', 4, 'v0')
    a.lw('t4', D_TARGET_K, 's0')
    a.lw('t5', 0x14, 'v0')
    a.sll('t4', 't4', 14)
    a.addu('t5', 't5', 't4')
    a.sw('t5', 0x14, 'v0')
    a.li('t6', 2)
    a.sh('t6', 0x1A, 'v0')                     # visual da 349
    a.lhu('t1', D_CUR + 6, 's0')
    a.nop()
    a.subu('t1', 'zero', 't1')
    a.sh('t1', 0x12, 'v0')                     # número mostrado: -dano
    a.jal(SE_PLAY)
    a.li('a0', 0x21)
    a.li('t1', 1)
    a.b('handler_out')
    a.sw('t1', D_STEP, 's0')

    # espera o objeto D_OBJ terminar (com limite) e encerra a operação
    a.label('wait_obj')
    a.lw('t1', D_FRAMES, 's0')
    a.lw('t2', D_OBJ, 's0')
    a.addiu('t1', 't1', 1)
    a.sw('t1', D_FRAMES, 's0')
    a.slti('t3', 't1', WAIT_LIMIT)
    a.beq('t3', 'zero', 'wait_done')
    a.nop()
    a.lbu('t4', 0x1C, 't2')
    a.nop()
    a.andi('t4', 't4', 0x80)
    a.bne('t4', 'zero', 'handler_out')
    a.nop()
    a.label('wait_done')
    a.lbu('t0', D_CUR, 's0')
    a.li('t1', OP_HEAL)
    a.bne('t0', 't1', 'op_done')
    a.nop()
    a.lw('t2', D_SAVED, 's0')                  # cura: devolve o número do banco
    li32('t3', HEAL_NUMBERS)
    a.b('op_done')
    a.sw('t2', 0, 't3')

    # ── toggle: giro da Stop Defense em cada monstro do oponente ──
    a.label('toggle')
    a.lw('t1', D_STEP, 's0')
    a.li('t2', 1)
    a.beq('t1', 't2', 'toggle_wait_hit')
    a.li('t2', 2)
    a.beq('t1', 't2', 'toggle_wait_end')
    a.nop()
    a.label('toggle_pick')
    a.lw('s2', D_K, 's0')
    a.nop()
    a.slti('t0', 's2', 5)
    a.beq('t0', 'zero', 'op_done')
    a.nop()
    a.jal('card_at')
    a.move('a0', 's2')
    a.lhu('t6', 0x16, 'v0')
    a.move('s3', 'v0')
    a.andi('t6', 't6', OCCUPIED)
    a.bne('t6', 'zero', 'toggle_start')
    a.nop()
    a.addiu('s2', 's2', 1)
    a.b('toggle_pick')
    a.sw('s2', D_K, 's0')
    a.label('toggle_start')
    a.sw('s3', D_TARGET, 's0')
    a.sw('zero', D_FRAMES, 's0')
    a.jal(CREATE)
    a.li('a0', 0x0C)
    a.beq('v0', 'zero', 'toggle_rotate')       # sem objeto: gira sem o brilho
    a.sw('v0', D_OBJ, 's0')
    li32('t0', TURN)
    a.lbu('t1', 0, 't0')
    li32('t2', POS_TABLE)
    a.sll('t3', 't1', 2); a.addu('t3', 't3', 't1'); a.sll('t3', 't3', 4)   # TURN*80
    a.addiu('t4', 's2', 5)
    a.sll('t4', 't4', 2)
    a.addu('t3', 't3', 't4')
    a.addu('t3', 't3', 't2')
    a.lhu('t5', 0, 't3')
    a.lhu('t6', 2, 't3')
    a.sh('zero', 2, 'v0')
    a.sh('t5', 0, 'v0')
    a.sh('t6', 4, 'v0')
    a.jal(SE_PLAY)
    a.li('a0', 0x20)
    a.li('t1', 1)
    a.b('handler_out')
    a.sw('t1', D_STEP, 's0')
    a.label('toggle_wait_hit')
    a.lw('t1', D_FRAMES, 's0')
    a.lw('t2', D_OBJ, 's0')
    a.addiu('t1', 't1', 1)
    a.sw('t1', D_FRAMES, 's0')
    a.slti('t3', 't1', WAIT_LIMIT)
    a.beq('t3', 'zero', 'toggle_rotate')
    a.nop()
    a.lbu('t4', 0x1D, 't2')
    a.nop()
    a.beq('t4', 'zero', 'handler_out')
    a.nop()
    a.label('toggle_rotate')
    a.lw('s3', D_TARGET, 's0')
    a.nop()
    a.lhu('t6', 0x16, 's3')
    a.nop()
    a.andi('t7', 't6', DEFENSE)
    a.bne('t7', 'zero', 'toggle_to_attack')
    a.xori('t6', 't6', DEFENSE)
    a.li('a1', 0)                              # ataque → defesa
    a.b('toggle_turn')
    a.li('a2', 0xC0)
    a.label('toggle_to_attack')
    a.li('a1', 0xC0)                           # defesa → ataque (como a Stop Defense)
    a.li('a2', 0)
    a.label('toggle_turn')
    a.sh('t6', 0x16, 's3')
    a.lw('a0', 0, 's3')
    a.jal(ROTATE)
    a.li('a3', 6)
    a.sw('zero', D_FRAMES, 's0')
    a.lw('t1', D_OBJ, 's0')
    a.li('t2', 2)
    a.bne('t1', 'zero', 'handler_out')
    a.sw('t2', D_STEP, 's0')
    a.b('toggle_next')                         # sem objeto: próxima posição
    a.nop()
    a.label('toggle_wait_end')
    a.lw('t1', D_FRAMES, 's0')
    a.lw('t2', D_OBJ, 's0')
    a.addiu('t1', 't1', 1)
    a.sw('t1', D_FRAMES, 's0')
    a.slti('t3', 't1', WAIT_LIMIT)
    a.beq('t3', 'zero', 'toggle_next')
    a.nop()
    a.lbu('t4', 0x1C, 't2')
    a.nop()
    a.andi('t4', 't4', 0x80)
    a.bne('t4', 'zero', 'handler_out')
    a.nop()
    a.label('toggle_next')
    a.lw('t1', D_K, 's0')
    a.sw('zero', D_STEP, 's0')
    a.sw('zero', D_OBJ, 's0')
    a.addiu('t1', 't1', 1)
    a.b('handler_out')
    a.sw('t1', D_K, 's0')

    # ── heal: animação de cura (efeito 5, como Dian Keto) com o número curado ──
    a.label('heal')
    a.lw('t1', D_STEP, 's0')
    a.nop()
    a.bne('t1', 'zero', 'wait_obj')
    a.nop()
    li32('t3', HEAL_NUMBERS)
    a.lw('t2', 0, 't3')
    a.nop()
    a.beq('t2', 'zero', 'op_done')             # banco de efeitos não carregado
    a.sw('t2', D_SAVED, 's0')
    a.lw('t4', D_CUR + 4, 's0')
    a.nop()
    a.sw('t4', 0, 't3')
    a.jal(CREATE_REQUEST)
    a.li('a0', 5)
    a.bne('v0', 'zero', 'heal_show')
    a.sw('v0', D_OBJ, 's0')
    a.lw('t2', D_SAVED, 's0')                  # sem pedido livre: devolve o número
    li32('t3', HEAL_NUMBERS)
    a.b('op_done')
    a.sw('t2', 0, 't3')
    a.label('heal_show')
    a.li('t0', 0xA0); a.sh('t0', 0, 'v0')
    a.li('t0', 0x78); a.sh('t0', 2, 'v0')
    a.sh('zero', 0x1A, 'v0')
    a.jal(SE_PLAY)
    a.li('a0', 0x14)
    a.li('t1', 1)
    a.b('handler_out')
    a.sw('t1', D_STEP, 's0')

    a.align(4)
    a.label('data')
    for _ in range(DATA_SIZE // 4):
        a.word(0)
    return a


def code(base: int, capacity: int, follow: int | None, heal_pending: int | None) -> bytes:
    return _assemble(base, capacity, follow, heal_pending).bytes()


def labels(base: int, capacity: int, follow: int | None, heal_pending: int | None) -> dict:
    asm = _assemble(base, capacity, follow, heal_pending)
    asm.bytes()
    return asm.labels


def block_size() -> int:
    return len(code(0x80100000, 722, 0x80100000, 0x80100000))


def wanted(plan) -> bool:
    return any(action in ENTRY_ACTIONS for _, action in getattr(plan, 'accepted', ()))


ENTRY_ACTIONS = set(SPELLS) | {'mudar_terreno', 'trocar_posicao', 'dano_monstro_alvo'}


def encode(effect: dict) -> bytes | None:
    """Bonus (8 bytes) do efeito de entrada; None se a ação não é de entrada."""
    action = effect['acao']
    if effect.get('evento') != 'invocar':
        return None
    if action in SPELLS:
        spell, kind = SPELLS[action]
        turns = effect['valor'] if action == 'espadas_reveladoras' else 0
        return struct.pack('<BBHHH', OP_SPELL, kind, spell, turns, 0)
    if action == 'mudar_terreno':
        return struct.pack('<BBHHH', OP_TERRAIN, TERRAIN_KIND, effect['valor'], 0, 0)
    if action == 'trocar_posicao':
        return struct.pack('<BBHHH', OP_TOGGLE, 0, 0, 0, 0)
    if action == 'dano_monstro_alvo':
        return struct.pack('<BBHHH', OP_DAMAGE, 0, 0, effect['valor'], 0)
    return None


def _word(exe: bytes, address: int) -> int:
    return struct.unpack_from('<I', exe, exe_pos(address, exe, 4))[0]


def apply(exe: bytes, hook: int, capacity: int, *, entries: bool,
          heal_pending: int | None) -> tuple[bytes, dict]:
    if _word(exe, RUN_SITE) != _jal(RUN_EFFECT):
        raise ModError('Efeitos de entrada: a chamada da fila de mágicas não é a esperada.')
    if _word(exe, OWN_SLOT) != EMPTY_HANDLER or exe[exe_pos(KINDS, exe, 1)] != 0:
        raise ModError('Efeitos de entrada: o tipo 14 da tabela de mágicas já está em uso.')
    follow = None
    if entries:
        word = _word(exe, ENTRY_SITE)
        if word >> 26 != 2:
            raise ModError('Efeitos de entrada: a entrada em campo do runtime não está instalada.')
        follow = _target(word)
    block = code(hook, capacity, follow, heal_pending)
    at = exe_pos(hook, exe, len(block))
    if any(exe[at:at + len(block)]):
        raise ModError('Efeitos de entrada: a área reservada no SLUS não está livre.')
    marks = labels(hook, capacity, follow, heal_pending)
    out = bytearray(exe)
    out[at:at + len(block)] = block
    struct.pack_into('<I', out, exe_pos(RUN_SITE, exe, 4), _jal(marks['run']))
    struct.pack_into('<I', out, exe_pos(OWN_SLOT, exe, 4), marks['handler'])
    out[exe_pos(KINDS, exe, 1)] = OWN_KIND
    if entries:
        struct.pack_into('<I', out, exe_pos(ENTRY_SITE, exe, 4), _j(marks['entry']))
    return bytes(out), {'status': 'aplicado', 'rotina': f'0x{hook:08X}',
                        'entrada': bool(entries), 'cura_vinculo': heal_pending is not None,
                        'validado_epsxe': False}


def _hook_of(exe: bytes) -> int | None:
    word = _word(exe, RUN_SITE)
    if word == _jal(RUN_EFFECT) or word >> 26 != 3:
        return None
    return _target(word)


def runtime_view(exe: bytes) -> bytes:
    """SLUS sem estes desvios (para a conferência byte a byte do runtime)."""
    try:
        run = _hook_of(exe)
        if run is None or run & 3:
            return exe
        handler = _word(exe, OWN_SLOT)
        out = bytearray(exe)
        struct.pack_into('<I', out, exe_pos(RUN_SITE, exe, 4), _jal(RUN_EFFECT))
        struct.pack_into('<I', out, exe_pos(OWN_SLOT, exe, 4), EMPTY_HANDLER)
        out[exe_pos(KINDS, exe, 1)] = 0
        entry_word = _word(exe, ENTRY_SITE)
        if entry_word >> 26 == 2 and run <= _target(entry_word) < handler:
            # o bloco termina 'entry' com j <salto anterior>: devolve esse salto
            at = exe_pos(_target(entry_word), exe, 0x200)
            for offset in range(0, handler - _target(entry_word), 4):
                word = struct.unpack_from('<I', exe, at + offset)[0]
                if word >> 26 == 2:
                    struct.pack_into('<I', out, exe_pos(ENTRY_SITE, exe, 4), word)
                    break
        return bytes(out)
    except Exception:
        return exe


def installed(exe: bytes, capacity: int, *, entries: bool, heal_pending: int | None) -> bool:
    try:
        run = _hook_of(exe)
        if run is None:
            return False
        follow = None
        if entries:
            view = runtime_view(exe)
            follow = _target(_word(view, ENTRY_SITE))
        block = code(run, capacity, follow, heal_pending)
        at = exe_pos(run, exe, len(block))
        return exe[at:at + len(block)] == block and exe[exe_pos(KINDS, exe, 1)] == OWN_KIND
    except Exception:
        return False
