"""Cor da moldura das cartas por raridade no PS1 (Drop x15).

Dois pontos de desenho recebem a cor:

* mão e campo do duelo (``func_80016784``, descrito abaixo);
* carta ampliada (baú/Build Deck, biblioteca e visualizador do duelo): a placa da
  carta é um objeto de sprite-sheet criado por ``func_800291E0`` e desenhado por
  ``DisplayObject_RenderSpriteSheet``, que copia o RGB do objeto para o sprite em
  ``0x8004177C``. Essa cópia vira ``jal`` para uma segunda rotina que, se o objeto
  for a placa da frente (callback ``CardPreview_UpdateVariant``, variante != verso)
  e estiver com a cor normal, acha o objeto da arte (``func_80028B08``, cujo
  ``+0x54`` aponta para a placa), lê o índice do registro em ``+0x67`` e o ID da
  carta em ``D_800EA0E8[índice] + 0x30``.

``func_80016784`` desenha cada carta do duelo: a moldura é o último sprite (52×60,
``uv 0x8000``), enviado em ``0x80016CCC`` por ``jal DisplayObject_SubmitPacket``.
A arte, os dígitos de ATK/DEF e o marcador de tipo são sprites próprios, por isso
a cor da moldura pode mudar sem tocar neles.

O Studio troca esse ``jal`` por um ``jal`` para uma rotina residente que, para
uma carta virada para cima e com a cor normal (``0x808080``), troca o RGB do
sprite (modulação da GPU: ``0x80`` = textura original) pela cor da classe da
carta e segue para ``DisplayObject_SubmitPacket`` com os mesmos argumentos.
A tabela (8 cores + uma classe por carta) fica num intervalo livre do SLUS.
"""
from __future__ import annotations

import struct

from .core import ModError
from .deep_extract import exe_pos
from .rarities import RARITIES, name_style

SETTINGS_KEY = 'ps1_frame_colors'
SITE = 0x80016CCC
SUBMIT = 0x80042188
CARD_SLOTS = 741                      # IDs 0..740 (expansion included)
SIGNATURE = {
    0x80016C6C: 0x3C02003C,  # lui  v0, 0x3C        extent 52x60
    0x80016C70: 0x34420034,  # ori  v0, v0, 0x34
    0x80016C7C: 0x34028000,  # li   v0, 0x8000      uv da moldura
    0x80016CCC: 0x0C010862,  # jal  DisplayObject_SubmitPacket
    0x80016CD0: 0x02A03821,  # move a3, s5
}
CLASSES = tuple(RARITIES)            # comum, incomum, rara, epica, lendaria, deus
DEFAULT_COLORS = {'comum': '', 'incomum': '', 'rara': '#FFD84D', 'epica': '#B57AFF',
                  'lendaria': '#F04F57', 'deus': '#4A7BD0'}
BIG_SITE = 0x8004177C                 # cópia r,g,b do objeto -> sprite (sprite-sheet)
BIG_SIGNATURE = {
    0x8004177C: 0x9242000C,  # lbu v0, 0xC(s2)
    0x80041780: 0x00000000,
    0x80041784: 0xA2020014,  # sb  v0, 0x14(s0)
    0x80041788: 0x9242000D,  # lbu v0, 0xD(s2)
    0x8004178C: 0x00000000,
    0x80041790: 0xA2020015,  # sb  v0, 0x15(s0)
    0x80041794: 0x9244000E,  # lbu a0, 0xE(s2)   (sb a0, 0x16(s0) em 0x800417C8)
    0x800417C8: 0xA2040016,
}
CARD_PREVIEW_UPDATE = 0x80029108      # CardPreview_UpdateVariant (callback da placa)
BIG_CARD_DRAW = 0x80028B08            # func_80028B08 (arte/nome/ATK da carta ampliada)
OBJECT_POOL = 0x800EFE48              # D_800EFE48: 96 objetos de 0x70 bytes
RECORDS = 0x800EA0E8                  # D_800EA0E8: registros de 0x40, ID em +0x30
CODE1_WORDS = 36
CODE2_WORDS = 59
CODE_WORDS = CODE1_WORDS + CODE2_WORDS
COLORS_SIZE = 8 * 4


def _jump(op: int, address: int) -> int:
    return op << 26 | (address & 0x0FFFFFFF) >> 2


def tint(color: str) -> tuple[int, int, int]:
    """#RRGGBB -> GPU modulation (0x80 = unchanged); 0xC0 maps to neutral."""
    value = int(color.lstrip('#'), 16)
    return tuple(min(255, round(((value >> shift) & 0xFF) * 0x80 / 0xC0)) for shift in (16, 8, 0))


def normalize(raw) -> dict:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ModError('Configuração das molduras inválida.')
    colors = dict(DEFAULT_COLORS)
    for key, value in (raw.get('cores') or {}).items():
        if key not in CLASSES:
            raise ModError(f'Molduras: classe desconhecida {key!r}.')
        value = (value or '').strip()
        if value and (len(value) != 7 or value[0] != '#'
                      or any(ch not in '0123456789abcdefABCDEF' for ch in value[1:])):
            raise ModError(f'Molduras: cor inválida para {RARITIES[key][0]} (use #RRGGBB).')
        colors[key] = value.upper()
    return {'ativado': bool(raw.get('ativado', False)), 'cores': colors}


def frame_settings(project) -> dict:
    return normalize((getattr(project, 'metadata', None) or {}).get(SETTINGS_KEY))


def save_frame_settings(project, settings: dict) -> dict:
    clean = normalize(settings)
    before = project.metadata
    project.metadata = {**before, SETTINGS_KEY: clean}
    try:
        project.save()
    except OSError:
        project.metadata = before
        raise
    return clean


def card_classes(cards: dict) -> dict[int, str]:
    """card id -> rarity class for monsters and God; spells/traps/equips keep their frame."""
    result = {}
    for cid, card in cards.items():
        if 1 <= int(cid) < CARD_SLOTS:
            _, _, kind = name_style(card)
            if kind in RARITIES:
                result[int(cid)] = kind
    return result


def table_bytes(colors: dict, classes: dict[int, str]) -> bytes:
    palette = bytearray(COLORS_SIZE)
    for index, key in enumerate(CLASSES, start=1):
        if colors.get(key):
            palette[4 * index:4 * index + 3] = bytes(tint(colors[key]))
    tiers = bytearray(CARD_SLOTS + 3)  # padded to a word
    for cid, key in classes.items():
        if colors.get(key):
            tiers[cid] = CLASSES.index(key) + 1
    return bytes(palette) + bytes(tiers)


def _hi_lo(address: int) -> tuple[int, int]:
    return (address + 0x8000) >> 16 & 0xFFFF, address & 0xFFFF


def big_hook_code(hook2: int, colors: int) -> bytes:
    """Carta ampliada. In: s2 = objeto sprite-sheet, s0 = sprite (0x1F800320).

    Faz a cópia original de r,g,b e, para a placa da frente de uma carta com
    classe colorida e cor normal, troca pela cor da classe. Usa só t0-t3; ``jr ra``."""
    ch, cl = _hi_lo(colors)
    uh, ul = _hi_lo(CARD_PREVIEW_UPDATE)
    ph, pl = _hi_lo(OBJECT_POOL)
    dh, dl = _hi_lo(BIG_CARD_DRAW)
    rh, rl = _hi_lo(RECORDS + 0x30)
    words = (
        0x9248000C,          # 0  lbu  t0, 0xC(s2)
        0x9249000D,          # 1  lbu  t1, 0xD(s2)
        0x924A000E,          # 2  lbu  t2, 0xE(s2)
        0xA2080014,          # 3  sb   t0, 0x14(s0)      cópia original
        0xA2090015,          # 4  sb   t1, 0x15(s0)
        0xA20A0016,          # 5  sb   t2, 0x16(s0)
        0x8E480010,          # 6  lw   t0, 0x10(s2)      callback de atualização
        0x3C090000 | uh,     # 7  lui  t1, %hi(CardPreview_UpdateVariant)
        0x25290000 | ul,     # 8  addiu t1, t1, %lo
        0x1509002F,          # 9  bne  t0, t1, ret       não é a placa da carta
        0x92480069,          # 10 lbu  t0, 0x69(s2)      variante (2 = verso)   (delay)
        0x24090002,          # 11 li   t1, 2
        0x1109002C,          # 12 beq  t0, t1, ret
        0x3C090080,          # 13 lui  t1, 0x0080        (delay)
        0x35298080,          # 14 ori  t1, t1, 0x8080    cor normal 0x808080
        0x8E48000C,          # 15 lw   t0, 0xC(s2)
        0x00000000,          # 16 nop
        0x00084200,          # 17 sll  t0, t0, 8
        0x00084202,          # 18 srl  t0, t0, 8
        0x15090025,          # 19 bne  t0, t1, ret       escurecida/destacada: mantém
        0x3C0A0000 | ph,     # 20 lui  t2, %hi(pool)     (delay)
        0x254A0000 | pl,     # 21 addiu t2, t2, %lo(pool)
        0x240B0060,          # 22 li   t3, 96
        0x8D480054,          # 23 loop: lw t0, 0x54(t2)  objeto ligado
        0x8D49004C,          # 24 lw   t1, 0x4C(t2)      rotina de desenho
        0x15120004,          # 25 bne  t0, s2, next
        0x3C080000 | dh,     # 26 lui  t0, %hi(func_80028B08)   (delay)
        0x25080000 | dl,     # 27 addiu t0, t0, %lo
        0x11090006,          # 28 beq  t0, t1, found
        0x00000000,          # 29 nop
        0x256BFFFF,          # 30 next: addiu t3, t3, -1
        0x1560FFF7,          # 31 bne  t3, zero, loop
        0x254A0070,          # 32 addiu t2, t2, 0x70     (delay)
        0x10000017,          # 33 b    ret
        0x00000000,          # 34 nop
        0x91480067,          # 35 found: lbu t0, 0x67(t2)  índice do registro
        0x3C0A0000 | rh,     # 36 lui  t2, %hi(D_800EA0E8 + 0x30)
        0x00084180,          # 37 sll  t0, t0, 6
        0x01485021,          # 38 addu t2, t2, t0
        0x85490000 | rl,     # 39 lh   t1, %lo(...)(t2)   ID da carta
        0x3C0B0000 | ch,     # 40 lui  t3, %hi(colors)
        0x256B0000 | cl,     # 41 addiu t3, t3, %lo(colors)
        0x2D2802E5,          # 42 sltiu t0, t1, 741
        0x1100000D,          # 43 beq  t0, zero, ret
        0x01695021,          # 44 addu t2, t3, t1        (delay)
        0x91480020,          # 45 lbu  t0, 0x20(t2)      classe da carta
        0x00000000,          # 46 nop
        0x11000009,          # 47 beq  t0, zero, ret
        0x00084080,          # 48 sll  t0, t0, 2         (delay)
        0x01684021,          # 49 addu t0, t3, t0
        0x8D080000,          # 50 lw   t0, 0(t0)         modulação da classe
        0x00000000,          # 51 nop
        0xA2080014,          # 52 sb   t0, 0x14(s0)
        0x00084202,          # 53 srl  t0, t0, 8
        0xA2080015,          # 54 sb   t0, 0x15(s0)
        0x00084202,          # 55 srl  t0, t0, 8
        0xA2080016,          # 56 sb   t0, 0x16(s0)
        0x03E00008,          # 57 ret: jr ra
        0x00000000,          # 58 nop
    )
    assert len(words) == CODE2_WORDS
    return struct.pack(f'<{len(words)}I', *words)


def hook_code(hook: int) -> bytes:
    """Rotina 1 (mão/campo) seguida da rotina 2 (carta ampliada, em hook + 36 words).

    Rotina 1 — MIPS I (load delays respected). In: a0 = sprite (0x1F800320), s6 = display object.

    a1-a3 and the stacked fifth argument are untouched; ends with ``j SUBMIT``."""
    colors = hook + CODE_WORDS * 4
    high, low = (colors + 0x8000) >> 16 & 0xFFFF, colors & 0xFFFF
    words = (
        0x92C80067,          # 0  lbu  t0, 0x67(s6)      digits variant
        0x92C90069,          # 1  lbu  t1, 0x69(s6)      face down / flipping
        0x92CB006A,          # 2  lbu  t3, 0x6A(s6)      card record index
        0x01094025,          # 3  or   t0, t0, t1
        0x1500001D,          # 4  bne  t0, zero, go
        0x000B50C0,          # 5  sll  t2, t3, 3         (delay)
        0x014B5023,          # 6  subu t2, t2, t3        *7
        0x000A5080,          # 7  sll  t2, t2, 2         *28
        0x3C0B801A,          # 8  lui  t3, 0x801A
        0x256B7AD8,          # 9  addiu t3, t3, 0x7AD8   D_801A7AD8 (duel card records)
        0x014B5021,          # 10 addu t2, t2, t3
        0x8549000C,          # 11 lh   t1, 0x0C(t2)      card id
        0x3C0B0000 | high,   # 12 lui  t3, %hi(colors)
        0x256B0000 | low,    # 13 addiu t3, t3, %lo(colors)
        0x2D2802E5,          # 14 sltiu t0, t1, 741
        0x11000012,          # 15 beq  t0, zero, go
        0x01695021,          # 16 addu t2, t3, t1        (delay)
        0x91480020,          # 17 lbu  t0, 0x20(t2)      class of the card
        0x8C8A0014,          # 18 lw   t2, 0x14(a0)      current sprite RGB
        0x1100000E,          # 19 beq  t0, zero, go
        0x00084080,          # 20 sll  t0, t0, 2         (delay)
        0x3C090080,          # 21 lui  t1, 0x0080
        0x35298080,          # 22 ori  t1, t1, 0x8080    normal color 0x808080
        0x000A5200,          # 23 sll  t2, t2, 8         ignore byte 3
        0x000A5202,          # 24 srl  t2, t2, 8
        0x15490008,          # 25 bne  t2, t1, go        dimmed/highlighted: keep
        0x01684021,          # 26 addu t0, t3, t0        (delay)
        0x8D080000,          # 27 lw   t0, 0(t0)         class modulation (r, g, b)
        0x00000000,          # 28 nop (load delay)
        0xA0880014,          # 29 sb   t0, 0x14(a0)      r
        0x00084202,          # 30 srl  t0, t0, 8
        0xA0880015,          # 31 sb   t0, 0x15(a0)      g
        0x00084202,          # 32 srl  t0, t0, 8
        0xA0880016,          # 33 sb   t0, 0x16(a0)      b
        _jump(2, SUBMIT),    # 34 go: j DisplayObject_SubmitPacket
        0x00000000,          # 35 nop
    )
    assert len(words) == CODE1_WORDS
    return struct.pack(f'<{len(words)}I', *words) + big_hook_code(hook + CODE1_WORDS * 4, colors)


def block_size() -> int:
    return CODE_WORDS * 4 + COLORS_SIZE + CARD_SLOTS + 3


def apply(exe: bytes, colors: dict, classes: dict[int, str], hook: int) -> tuple[bytes, dict]:
    for address, word in {**SIGNATURE, **BIG_SIGNATURE}.items():
        if struct.unpack_from('<I', exe, exe_pos(address, exe, 4))[0] != word:
            raise ModError(f'Molduras: o SLUS diverge do Drop x15 em 0x{address:08X}.')
    block = hook_code(hook) + table_bytes(colors, classes)
    at = exe_pos(hook, exe, len(block))
    if any(exe[at:at + len(block)]):
        raise ModError('Molduras: a área reservada no SLUS não está livre.')
    result = bytearray(exe)
    result[at:at + len(block)] = block
    struct.pack_into('<I', result, exe_pos(SITE, result, 4), _jump(3, hook))
    big = [_jump(3, hook + CODE1_WORDS * 4)] + [0] * 5 + [0x92040016]  # ... lbu a0, 0x16(s0)
    for offset, word in enumerate(big):
        struct.pack_into('<I', result, exe_pos(BIG_SITE + 4 * offset, result, 4), word)
    painted = sum(1 for key in classes.values() if colors.get(key))
    return bytes(result), {'status': 'aplicado', 'rotina': f'0x{hook:08X}', 'cartas_coloridas': painted,
                           'cores': {k: v for k, v in colors.items() if v}, 'locais': ['mao_e_campo', 'carta_ampliada'],
                           'validado_epsxe': False}


def status(exe: bytes) -> dict:
    word = struct.unpack_from('<I', exe, exe_pos(SITE, exe, 4))[0]
    if word == SIGNATURE[SITE]:
        return {'status': 'original'}
    if word >> 26 != 3:
        return {'status': 'divergente'}
    hook = 0x80000000 | (word & 0x03FFFFFF) << 2
    code = hook_code(hook)
    at = exe_pos(hook, exe, len(code))
    return {'status': 'aplicado' if exe[at:at + len(code)] == code else 'divergente', 'rotina': f'0x{hook:08X}'}
