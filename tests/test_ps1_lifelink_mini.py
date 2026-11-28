"""Vínculo com Vida no intérprete MIPS próprio (roda sem Unicorn).

Reproduz o estado real do jogo no 1º quadro da batalha: as cartas do atacante
e do alvo já foram tiradas do campo (DuelCard_DeactivateRecord limpa OCCUPIED),
mas id e ATK continuam no registro.
"""
import struct
import unittest

from fmstudio import ps1_lifelink as ll
from tests.mini_mips import MiniCpu

HOOK = 0x80030D2C
RETURN = 0x80000100
LIFE_ID, PLAIN_ID = 627, 11


class LifelinkMiniTests(unittest.TestCase):
    bonus = 0

    def battle(self, attacker, target, *, attack=2100, target_attack=900, lp=(3260, 8750),
               scene=0x0009, occupied=False, life_ids=(LIFE_ID,), target_id=PLAIN_ID):
        cpu = MiniCpu()
        cpu.load(HOOK, ll.code(HOOK, 722))
        cpu.load(ll.SCENE, struct.pack('<H', scene))
        rules_at = 0x400
        for cid in {LIFE_ID, PLAIN_ID, target_id}:
            cpu.load(ll.CONFIG + 2 + 2 * cid, struct.pack('<H', rules_at))
            cpu.load(ll.CONFIG + rules_at, bytes([(ll.LIFELINK | 4) if cid in life_ids else 4]))
            rules_at += 8
        for slot, cid, atk in ((attacker, LIFE_ID, attack), (target, target_id, target_attack)):
            if slot >= 0:
                card = ll.CARDS + slot * 28
                cpu.load(card + 0x0C, struct.pack('<hh', cid, atk))
                cpu.load(card + 0x16, struct.pack('<H', 0x8000 if occupied else 0))
        for side, value in enumerate(lp):
            cpu.load(ll.SIDE_LP + 32 * side, struct.pack('<H', value))

        def runtime_battle(c):          # o runtime grava duel.battle e liga o bit 15
            c.load(ll.DUEL_BATTLE, struct.pack('<bbB', attacker, target, 1))
            c.load(ll.SCENE, struct.pack('<H', scene | 0x8000))
        cpu.r[29], cpu.r[31] = 0x801FFF00, RETURN
        def calculate_stats(c):         # runtime: ATK do registro + bônus de campo
            atk = struct.unpack_from('<h', c.mem, (c.r[4] + 0x0E) & 0x1FFFFF)[0]
            c.r[2] = (1000 << 16) | ((atk + self.bonus) & 0xFFFF)
        end = cpu.run(HOOK, stop={RETURN}, limit=2000,
                      calls={ll.BATTLE: runtime_battle, ll.CALC: calculate_stats})
        self.pending = struct.unpack_from('<2I', cpu.mem,
                                          ll.pending_address(HOOK, 722) & 0x1FFFFF)
        self.assertEqual(end, RETURN)
        self.assertEqual(cpu.r[29], 0x801FFF00)
        return tuple(struct.unpack_from('<H', cpu.mem, (ll.SIDE_LP + 32 * s) & 0x1FFFFF)[0] for s in (0, 1))

    def test_direct_attack_heals_even_with_record_lifted(self):
        self.assertEqual(self.battle(5, -1), (3260 + 2100, 8750))

    def test_attack_monster_heals_attacker_owner(self):
        self.assertEqual(self.battle(6, 21), (3260 + 2100, 8750))

    def test_attacked_lifelink_heals_its_owner(self):
        # COM ataca (slot 22) o monstro com vínculo do jogador (slot 7)
        lp = self.battle(22, 7, attack=1500, target_id=LIFE_ID, life_ids=(LIFE_ID,))
        self.assertEqual(lp, (3260 + 900, 8750 + 1500))   # os dois têm vínculo neste cenário

    def test_only_first_frame(self):
        self.assertEqual(self.battle(5, -1, scene=0x8009), (3260, 8750))

    def test_uses_total_attack_with_bonus_and_queues_animation(self):
        self.bonus = 450
        self.assertEqual(self.battle(5, -1), (3260 + 2550, 8750))
        self.assertEqual(self.pending, (2550, 0))

    def test_plain_card_and_cap(self):
        self.assertEqual(self.battle(5, -1, life_ids=()), (3260, 8750))
        self.assertEqual(self.battle(5, -1, lp=(65000, 1)), (65535, 1))


if __name__ == '__main__':
    unittest.main()
