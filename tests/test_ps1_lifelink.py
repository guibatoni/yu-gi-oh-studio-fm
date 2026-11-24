"""Vínculo com Vida no PS1: a rotina da cena de batalha executada no Unicorn."""
import struct
import unittest

try:
    from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
    from unicorn.mips_const import UC_MIPS_REG_RA, UC_MIPS_REG_SP
except ImportError:  # pragma: no cover
    Uc = None

from fmstudio import ps1_lifelink as ll

M = 0x1FFFFF
HOOK = 0x801D9000
RETURN = 0x80000100
LIFE_ID, PLAIN_ID = 10, 11


@unittest.skipIf(Uc is None, 'Unicorn não instalado')
class LifelinkMipsTests(unittest.TestCase):
    def run_battle(self, attacker, target, *, attack=1200, target_attack=900,
                   lp=(3000, 4000), already_active=False, life_ids=(LIFE_ID,)):
        cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(0, 0x200000)
        cpu.mem_write(HOOK & M, ll.code(HOOK, 722))
        # Battle falso: liga battle_active e grava os slots (como o runtime)
        cpu.mem_write(ll.BATTLE & M, struct.pack('<2I', 0x03E00008, 0))
        cpu.mem_write((ll.DUEL_BATTLE + 2) & M, bytes([1]))         # battle_active pode ficar em 1
        cpu.mem_write(ll.SCENE & M, struct.pack('<H', 0x8003 if already_active else 0x0003))

        def battle(uc, address, size, _):
            if address == ll.BATTLE:
                uc.mem_write(ll.DUEL_BATTLE & M, struct.pack('<bbB', attacker, target, 1))
        cpu.hook_add(UC_HOOK_CODE, battle)
        # regras: offsets[id] -> Rules; protection 0x80 só para LIFE_ID
        rules_at = 0x400
        for cid in (LIFE_ID, PLAIN_ID):
            cpu.mem_write((ll.CONFIG + 2 + 2 * cid) & M, struct.pack('<H', rules_at))
            prot = ll.LIFELINK | 4 if cid in life_ids else 4
            cpu.mem_write((ll.CONFIG + rules_at) & M, bytes([prot]))
            rules_at += 8
        for slot, cid, atk in ((attacker, LIFE_ID, attack), (target, LIFE_ID if target == 22 else PLAIN_ID, target_attack)):
            if slot >= 0:
                card = ll.CARDS + slot * 28
                cpu.mem_write((card + 0x0C) & M, struct.pack('<hh', cid, atk))
                cpu.mem_write((card + 0x16) & M, struct.pack('<H', 0x8000))
        for side, value in enumerate(lp):
            cpu.mem_write((ll.SIDE_LP + 32 * side) & M, struct.pack('<H', value))
        cpu.reg_write(UC_MIPS_REG_SP, 0x80180000)
        cpu.reg_write(UC_MIPS_REG_RA, RETURN)
        cpu.emu_start(HOOK, RETURN, timeout=2_000_000)
        return tuple(struct.unpack('<H', cpu.mem_read((ll.SIDE_LP + 32 * s) & M, 2))[0]
                     for s in range(2))

    def test_attacking_monster_heals_owner(self):
        self.assertEqual(self.run_battle(6, 21), (4200, 4000))

    def test_direct_attack_heals_owner(self):
        self.assertEqual(self.run_battle(7, -1), (4200, 4000))

    def test_attacked_monster_heals_its_owner(self):
        # atacante do lado 1 sem efeito; alvo do lado 0 com efeito
        self.assertEqual(self.run_battle(21, 6, attack=800, target_attack=1500,
                                         life_ids=(PLAIN_ID,)), (3000 + 1500, 4000))

    def test_both_sides_heal(self):
        self.assertEqual(self.run_battle(6, 22, attack=1000, target_attack=700), (4000, 4700))

    def test_only_on_battle_start(self):
        self.assertEqual(self.run_battle(6, 21, already_active=True), (3000, 4000))

    def test_lp_caps_at_u16(self):
        self.assertEqual(self.run_battle(6, -1, attack=9000, lp=(60000, 1)), (65535, 1))


if __name__ == '__main__':
    unittest.main()
