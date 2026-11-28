"""Menu inicial só com NEW GAME e LOAD (overlay do menu em DATA/SU.MRG).

O menu inicial é o overlay carregado em 0x80180000 a partir dos setores 98-114
do SU.MRG (layout do decomp ``memories-decomp``, src/overlays/main_menu). Em
``MainMenu_UpdateFrontendMenu``:

* a transição desenha as entradas ``i < 5`` do menu inicial (0x80180700,
  ``slti v0, s2, 5``) — passa a desenhar só ``i < 2`` (NEW GAME e LOAD);
* o cursor anda em ``count = 5`` entradas (0x801808FC, ``addiu s0, zero, 5``)
  — passa a andar só nas 2.

2P DUEL, TRADE e OPTION somem da tela e não podem mais ser escolhidos (o SLUS
já leva 2P DUEL e TRADE de volta ao menu, ver ps1_debug_space). O submenu de
depois do LOAD (entradas 5-10) não muda.
"""
from __future__ import annotations

import struct

from .core import ModError

OVERLAY_BASE = 0x80180000
OVERLAY_OFFSET = 98 * 0x800             # setor 98 do SU.MRG
PATCHES = {
    0x80180700: (0x2A420005, 0x2A420002),   # slti v0, s2, 5 -> 2 (entradas desenhadas)
    0x801808FC: (0x24100005, 0x24100002),   # addiu s0, zero, 5 -> 2 (cursor)
}


def _offset(address: int) -> int:
    return OVERLAY_OFFSET + address - OVERLAY_BASE


def status(su: bytes) -> str:
    words = [struct.unpack_from('<I', su, _offset(a))[0] if len(su) >= _offset(a) + 4 else None
             for a in PATCHES]
    if words == [old for old, _ in PATCHES.values()]:
        return 'original'
    if words == [new for _, new in PATCHES.values()]:
        return 'aplicado'
    return 'divergente'


def apply(su: bytes) -> tuple[bytes, dict]:
    state = status(su)
    if state == 'divergente':
        raise ModError('Menu inicial: o overlay do SU.MRG não é o do Drop x15.')
    out = bytearray(su)
    for address, (_, new) in PATCHES.items():
        struct.pack_into('<I', out, _offset(address), new)
    return bytes(out), {'status': 'aplicado', 'opcoes': ['NEW GAME', 'LOAD'], 'validado_epsxe': False}
