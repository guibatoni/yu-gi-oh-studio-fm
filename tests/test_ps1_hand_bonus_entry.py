"""Bônus de mão no PS1: contado ao entrar em campo e fixo depois (intérprete MIPS próprio)."""
import struct
import unittest

from fmstudio import ps1_hand_bonus as hb
from tests.mini_mips import M, MiniCpu

HOOK = 0x80030000
RETURN = 0x80000100
TYPES = {10: 7, 11: 7, 12: 3, 13: 7, 20: 7, 21: 7, 30: 7}   # id -> tipo
HAND_CARD = 30           # carta com o bônus (+150 por Guerreiro na mão)
RULE_AT = 0x40


def cpu_with(hand0, hand1, *, field=((6, HAND_CARD),), extra_bonus=True):
    cpu = MiniCpu()
    asm = hb._build(HOOK)
    cpu.load(HOOK, asm.bytes())
    # CONFIG: offsets[id] em +2; regra: protection, ..., bonus_count em +3, bônus a partir de +8
    cpu.load(hb.CONFIG + 2 + 2 * HAND_CARD, struct.pack('<H', RULE_AT))
    bonuses = [struct.pack('<BBHHH', hb.DECK_TYPE, 0, hb.encode_match(7), 150, 150)]
    if extra_bonus:
        bonuses.insert(0, struct.pack('<BBHHH', 2, 0, 7, 100, 0))          # bônus de campo comum
    cpu.load(hb.CONFIG + RULE_AT, bytes([0, 0, 0, len(bonuses)]) + bytes(4) + b''.join(bonuses))
    for side, hand in ((0, hand0), (1, hand1)):
        for i in range(5):
            card = hb.CARDS + (side * 15 + i) * 28
            cid = hand[i] if i < len(hand) else 0
            cpu.load(card + 0x0C, struct.pack('<h', cid))
            cpu.load(card + 0x16, struct.pack('<H', hb.OCCUPIED if cid else 0))
    for slot, cid in field:
        cpu.load(hb.CARDS + slot * 28 + 0x0C, struct.pack('<h', cid))
    return cpu, asm


def matches(c):
    match = struct.unpack_from('<H', c.mem, (c.r[4] + 2) & M)[0]
    cid, by_id = c.r[5] & 0xFFFF, c.r[6]
    if by_id:
        c.r[2] = int(cid == match)
    else:
        c.r[2] = int(match == 0xFFFF or TYPES.get(cid) == match)


def run(cpu, pc, *, a0=0, a1=0, s5=0, s7=0):
    summons, originals = [], []
    cpu.r[29], cpu.r[31] = 0x801FFF00, RETURN
    cpu.r[4], cpu.r[5] = a0, a1
    cpu.r[21], cpu.r[23] = s5, s7
    saved = [cpu.r[i] for i in range(16, 24)]

    def summon(c):
        summons.append(c.r[4])

    def original(c):
        originals.append(c.r[4])
        c.r[2] = 99
    end = cpu.run(pc, stop={RETURN}, limit=50000,
                  calls={hb.MATCHES_BONUS: matches, hb.SUMMON_ENTRY: summon, hb.COUNT_BONUS: original})
    assert end == RETURN and cpu.r[29] == 0x801FFF00
    assert [cpu.r[i] for i in range(16, 24)] == saved
    return cpu.r[2], summons, originals


def bonus_address(index, extra=True):
    return hb.CONFIG + RULE_AT + 8 + 8 * index


class HandBonusEntryTests(unittest.TestCase):
    def test_counts_on_entry_and_stays_fixed(self):
        cpu, asm = cpu_with([10, 11, 12], [20, 21])            # 2 Guerreiros na mão do jogador
        _, summons, _ = run(cpu, asm.labels['entry'], a0=6)
        self.assertEqual(summons, [6])                          # segue para summon_damage(slot)
        snap = asm.labels['snapshots'] + (6 - 5) * hb.SNAP_BONUSES
        self.assertEqual(bytes(cpu.mem[snap & M:][:2]), b'\x00\x02')
        # a mão muda (compra 2 Guerreiros): o bônus continua 2
        for i, cid in enumerate((10, 11, 12, 13, 20)):
            cpu.load(hb.CARDS + i * 28 + 0x0C, struct.pack('<h', cid))
            cpu.load(hb.CARDS + i * 28 + 0x16, struct.pack('<H', hb.OCCUPIED))
        value, _, originals = run(cpu, HOOK, a0=bonus_address(1), a1=0, s5=2, s7=6)
        self.assertEqual((value, originals), (2, []))
        # contagem ao vivo (fora de um slot de monstro) já veria 4
        value, _, _ = run(cpu, HOOK, a0=bonus_address(1), a1=0, s5=2, s7=0)
        self.assertEqual(value, 4)

    def test_other_bonuses_go_to_the_runtime(self):
        cpu, asm = cpu_with([10], [])
        run(cpu, asm.labels['entry'], a0=6)
        value, _, originals = run(cpu, HOOK, a0=bonus_address(0), a1=0, s5=1, s7=6)
        self.assertEqual((value, originals), (99, [bonus_address(0)]))

    def test_rival_side_and_reentry(self):
        cpu, asm = cpu_with([10, 11], [20, 21, 12], field=((22, HAND_CARD),), extra_bonus=False)
        run(cpu, asm.labels['entry'], a0=22)
        snap = asm.labels['snapshots'] + (22 - 15) * hb.SNAP_BONUSES
        self.assertEqual(cpu.mem[snap & M], 2)                  # conta a mão do rival
        value, _, _ = run(cpu, HOOK, a0=bonus_address(0), a1=1, s5=1, s7=22)
        self.assertEqual(value, 2)
        # sai e entra de novo com a mão diferente: nova contagem
        cpu.load(hb.CARDS + (15 + 3) * 28 + 0x0C, struct.pack('<h', 13))
        cpu.load(hb.CARDS + (15 + 3) * 28 + 0x16, struct.pack('<H', hb.OCCUPIED))
        run(cpu, asm.labels['entry'], a0=22)
        self.assertEqual(cpu.mem[snap & M], 3)

    def test_card_without_rule_only_clears(self):
        cpu, asm = cpu_with([10, 11], [], field=((7, 11),))
        snap = asm.labels['snapshots'] + (7 - 5) * hb.SNAP_BONUSES
        cpu.load(snap, b'\x05\x05\x05\x05')
        _, summons, _ = run(cpu, asm.labels['entry'], a0=7)
        self.assertEqual((bytes(cpu.mem[snap & M:][:4]), summons), (bytes(4), [7]))

    def test_patch_sites(self):
        data = bytearray(0x800 + 0x200000)
        data[:8] = b'PS-X EXE'
        struct.pack_into('<I', data, 0x18, 0x80010000)
        struct.pack_into('<I', data, 0x1C, len(data) - 0x800)
        at = lambda address: 0x800 + address - 0x80010000
        struct.pack_into('<I', data, at(hb.CALL_SITE), hb._jal(hb.COUNT_BONUS))
        struct.pack_into('<I', data, at(hb.ENTRY_SITE), hb._j(hb.SUMMON_ENTRY))
        out, report = hb.apply(bytes(data), HOOK)
        self.assertEqual(struct.unpack_from('<I', out, at(hb.ENTRY_SITE))[0],
                         hb._j(hb._labels(HOOK)['entry']))
        view = hb.runtime_view(out)
        self.assertEqual(struct.unpack_from('<I', view, at(hb.ENTRY_SITE))[0], hb._j(hb.SUMMON_ENTRY))
        self.assertEqual(struct.unpack_from('<I', view, at(hb.CALL_SITE))[0], hb._jal(hb.COUNT_BONUS))


if __name__ == '__main__':
    unittest.main()
