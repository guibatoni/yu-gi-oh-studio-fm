"""Drop fixo por duelista no PS1: a 1ª vitória contra ele entrega uma carta escolhida.

Regra: cada duelista pode ter uma carta de "drop fixo". Na primeira vitória
contra ele, a carta do SPOILS é essa carta; o jogo grava no save que ela já
saiu e, nas vitórias seguintes, o sorteio normal volta (tabelas de drop,
drops do próprio deck, Drop x15 com as cartas extras).

Implementação sem recompilar o runtime:

* ``Duel_SelectCardDrop`` (0x80021810) é chamado uma vez por vitória, no
  resultado (0x80021C60); as cartas extras do Drop x15 são sorteadas pelo
  código do mod, sem passar por ele. A entrada da função recebe
  ``j rotina; nop``; as duas palavras deslocadas (as originais ou o
  ``j SelectDeckDrop; nop`` dos drops do deck) são executadas no fim da
  rotina, seguidas de ``j 0x80021818``.
* a rotina lê o duelista (``gDuel_bOpponentID`` 0x8009B361), procura a carta
  na tabela (40 halfwords) e testa a bandeira de campanha ``0x708 + id``
  (bandeiras de 0x708 a 0x72F: livres; 0x6E0..0x707 são o desbloqueio do
  Free Duel). Sem a bandeira: liga a bandeira e devolve a carta.
* as bandeiras ficam no bloco do save (0x801D0618, MSB primeiro, como
  ``Library_UpdateCardUsedFlag``), então valem por save e o NEW GAME limpa.

``runtime_view`` devolve o SLUS sem o desvio, para a conferência byte a byte
do runtime (mesmo cuidado de ps1_lifelink).
"""
from __future__ import annotations

import struct

from .core import ModError
from .deep_extract import exe_pos
from .mips_asm import Asm, hi_lo
from .tables import DUELIST_COUNT

DROP_ENTRY = 0x80021810             # Duel_SelectCardDrop
RESUME = DROP_ENTRY + 8
OPPONENT = 0x8009B361               # gDuel_bOpponentID (u8)
FLAG_BANK = 0x801D0618              # bandeiras de campanha (bloco do save)
FLAG_BASE = 0x708                   # 0x708 + duelista: drop fixo já entregue
SETTINGS_KEY = 'drop_fixo'          # em mod_data: duelistas[id]['drop_fixo'] = id da carta


def fixed_drops(config, capacity: int) -> dict[int, int]:
    """{duelista: carta} válidos para o PS1 (1..39 e carta dentro do catálogo)."""
    out = {}
    for key, duelist in (config or {}).get('duelistas', {}).items():
        card = duelist.get(SETTINGS_KEY) if isinstance(duelist, dict) else None
        if card is None:
            continue
        opponent = int(key)
        if 1 <= opponent < DUELIST_COUNT and 1 <= int(card) <= capacity:
            out[opponent] = int(card)
    return out


def code(base: int, drops: dict[int, int], displaced: tuple[int, int]) -> bytes:
    a = Asm(base)
    oh, ol = hi_lo(OPPONENT)
    fh, fl = hi_lo(FLAG_BANK)
    a.lui('t0', oh)
    a.lbu('t0', ol, 't0')
    a.nop()
    a.sltiu('t1', 't0', DUELIST_COUNT)
    a.beqz('t1', 'fallback')
    a.sll('t1', 't0', 1)
    a.la('t2', 'table')
    a.addu('t2', 't2', 't1')
    a.lhu('t2', 0, 't2')
    a.nop()
    a.beqz('t2', 'fallback')
    a.addiu('t3', 't0', FLAG_BASE)
    a.srl('t4', 't3', 3)
    a.lui('t5', fh)
    a.addu('t5', 't5', 't4')
    a.lbu('t6', fl, 't5')
    a.andi('t3', 't3', 7)
    a.li('t7', 0x80)
    a.srlv('t7', 't7', 't3')
    a.and_('t8', 't6', 't7')
    a.bnez('t8', 'fallback')
    a.or_('t6', 't6', 't7')
    a.sb('t6', fl, 't5')
    a.jr('ra')
    a.move('v0', 't2')
    a.label('fallback')
    a.word(displaced[0])
    a.word(displaced[1])
    a.j(RESUME)
    a.nop()
    a.label('table')
    for opponent in range(0, DUELIST_COUNT, 2):
        a.word(drops.get(opponent, 0) | drops.get(opponent + 1, 0) << 16)
    return a.bytes()


def block_size() -> int:
    return len(code(0x80100000, {}, (0, 0)))


def _jump(target: int) -> int:
    return 0x08000000 | ((target >> 2) & 0x03FFFFFF)


def _words(exe: bytes, address: int, count: int = 2) -> tuple[int, ...]:
    return struct.unpack_from(f'<{count}I', exe, exe_pos(address, exe, 4 * count))


def apply(exe: bytes, hook: int, drops: dict[int, int]) -> tuple[bytes, dict]:
    displaced = _words(exe, DROP_ENTRY)
    if displaced[0] >> 26 == 2 and (displaced[0] & 0x03FFFFFF) == (hook >> 2) & 0x03FFFFFF:
        raise ModError('Drop fixo: a entrada do sorteio já aponta para esta rotina.')
    block = code(hook, drops, displaced)
    at = exe_pos(hook, exe, len(block))
    if any(exe[at:at + len(block)]):
        raise ModError('Drop fixo: a área reservada no SLUS não está livre.')
    out = bytearray(exe)
    out[at:at + len(block)] = block
    struct.pack_into('<II', out, exe_pos(DROP_ENTRY, exe, 8), _jump(hook), 0)
    return bytes(out), {
        'status': 'aplicado', 'rotina': f'0x{hook:08X}',
        'duelistas': {str(k): v for k, v in sorted(drops.items())},
        'regra': '1ª vitória contra o duelista; bandeira de campanha 0x708 + id no save',
        'validado_epsxe': False,
    }


def _installed(exe: bytes):
    """(hook, deslocadas) se a entrada do sorteio aponta para esta rotina."""
    try:
        first, second = _words(exe, DROP_ENTRY)
        if first >> 26 != 2 or second != 0:
            return None
        hook = 0x80000000 | (first & 0x03FFFFFF) << 2
        if not 0x80010000 <= hook < 0x80200000:
            return None
        size = block_size()
        at = exe_pos(hook, exe, size)
        block = exe[at:at + size]
        displaced = struct.unpack_from('<II', block, size - 4 * (4 + DUELIST_COUNT // 2))
        table = struct.unpack_from(f'<{DUELIST_COUNT}H', block, size - 2 * DUELIST_COUNT)
        drops = {i: card for i, card in enumerate(table) if card}
        if block != code(hook, drops, displaced):
            return None
        return hook, displaced, drops
    except Exception:
        return None


def installed(exe: bytes) -> dict[int, int] | None:
    found = _installed(exe)
    return found[2] if found else None


def runtime_view(exe: bytes) -> bytes:
    """SLUS com a entrada do sorteio devolvida às palavras deslocadas."""
    found = _installed(exe)
    if not found:
        return exe
    out = bytearray(exe)
    struct.pack_into('<II', out, exe_pos(DROP_ENTRY, exe, 8), *found[1])
    return bytes(out)
