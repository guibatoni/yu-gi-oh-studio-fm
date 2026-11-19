"""Bônus de ATK/DEF por equipamento no PS1."""
from pathlib import Path
import struct
import tempfile
import unittest

try:
    from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
    from unicorn.mips_const import UC_MIPS_REG_GP, UC_MIPS_REG_PC, UC_MIPS_REG_S1, UC_MIPS_REG_V1
except ImportError:
    Uc = None

from fmstudio import ps1_equip_bonus as eb
from fmstudio.core import ModError, Project
from fmstudio.deep_extract import exe_pos

HOOK = 0x801CE300
GP = 0x8009AF08


def executable(*, expansion_jump=False):
    exe = bytearray(0x1e0800)
    exe[:8] = b'PS-X EXE'
    for address, word in eb.SIGNATURE.items():
        struct.pack_into('<I', exe, exe_pos(address, exe, 4), word)
    if expansion_jump:  # The 740-card expansion replaces the ID load with a jump.
        struct.pack_into('<I', exe, exe_pos(eb.ID_LOAD, exe, 4), 0x08000000 | (0x801D5400 >> 2) & 0x3FFFFFF)
    return bytes(exe)


class EquipBonusTests(unittest.TestCase):
    def test_apply_and_status_round_trip(self):
        exe = executable()
        self.assertEqual(eb.status(exe), {'status': 'original'})
        bonuses = {657: 1500, 301: 800, 302: 0}
        patched, report = eb.apply(exe, bonuses, HOOK)
        self.assertEqual(report['bonus'], {'301': 800, '302': 0, '657': 1500})
        self.assertEqual(eb.status(patched)['bonus'], report['bonus'])
        # Only the jump, its delay slot and the reserved block change.
        changed = [i for i in range(len(exe)) if exe[i] != patched[i]]
        site = exe_pos(eb.SITE, exe, 8)
        block = exe_pos(HOOK, exe, eb.block_size(bonuses))
        self.assertTrue(all(site <= i < site + 8 or block <= i < block + eb.block_size(bonuses) for i in changed))
        self.assertEqual(struct.unpack_from('<I', patched, exe_pos(eb.ID_LOAD, patched, 4))[0], 0x878302FE)

    def test_works_together_with_the_740_card_expansion(self):
        patched, _ = eb.apply(executable(expansion_jump=True), {301: 700}, HOOK)
        self.assertEqual(eb.status(patched)['bonus'], {'301': 700})

    def test_refuses_foreign_code_and_used_space(self):
        exe = bytearray(executable())
        struct.pack_into('<I', exe, exe_pos(0x8001A824, exe, 4), 0)
        with self.assertRaisesRegex(ModError, 'diverge'):
            eb.apply(bytes(exe), {301: 700}, HOOK)
        exe = bytearray(executable())
        exe[exe_pos(HOOK + 8, exe, 1)] = 1
        with self.assertRaisesRegex(ModError, 'não está livre'):
            eb.apply(bytes(exe), {301: 700}, HOOK)

    def test_reserve_block_uses_free_zero_space(self):
        exe = bytearray(executable())
        address, free = eb.reserve_block(bytes(exe), [(0x801CE000, 0x801CE400)], 0x60)
        self.assertEqual(address, 0x801CE3A0)
        self.assertEqual(free, [(0x801CE000, 0x801CE3A0)])
        exe[exe_pos(0x801CE3F0, exe, 1)] = 7
        with self.assertRaisesRegex(ModError, 'Sem espaço'):
            eb.reserve_block(bytes(exe), [(0x801CE380, 0x801CE400)], 0x60)

    def test_normalize_and_settings(self):
        self.assertEqual(eb.normalize({'657': '1500'}), {657: 1500})
        for bad in ({'0': 500}, {'301': 6000}, {'301': -1}, {'301': 'x'}):
            with self.assertRaises(ModError):
                eb.normalize(bad)
        with tempfile.TemporaryDirectory() as folder:
            project = Project.create(Path(folder), 'Teste')
            eb.set_equip_bonus(project, 301, 900)
            eb.set_equip_bonus(project, 657, 2000)
            self.assertEqual(eb.equip_bonuses(Project.open(Path(folder))), {301: 900, 657: 2000})
            eb.set_equip_bonus(project, 301, None)
            self.assertEqual(eb.equip_bonuses(project), {657: 2000})
        self.assertEqual((eb.default_bonus(657), eb.default_bonus(301)), (1000, 500))


@unittest.skipIf(Uc is None, 'MIPS verification needs Unicorn')
class EquipBonusMipsTests(unittest.TestCase):
    def run_hook(self, equip_id, bonuses, reverse_trap=500):
        cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(0, 0x200000)
        block = eb.hook_code(HOOK) + eb.table_bytes(bonuses)
        cpu.mem_write(HOOK & 0x1FFFFF, block)
        placement = 0x80150000
        cpu.mem_write((placement + 0x2A) & 0x1FFFFF, struct.pack('<h', 500))
        cpu.mem_write((GP + 0x24C) & 0x1FFFFF, struct.pack('<H', reverse_trap))
        cpu.reg_write(UC_MIPS_REG_V1, equip_id)
        cpu.reg_write(UC_MIPS_REG_S1, placement)
        cpu.reg_write(UC_MIPS_REG_GP, GP)
        cpu.emu_start(HOOK, eb.RESUME, count=500)
        self.assertEqual(cpu.reg_read(UC_MIPS_REG_PC), eb.RESUME)
        bonus = struct.unpack('<h', bytes(cpu.mem_read((placement + 0x2A) & 0x1FFFFF, 2)))[0]
        undo = struct.unpack('<H', bytes(cpu.mem_read((GP + 0x24C) & 0x1FFFFF, 2)))[0]
        return bonus, undo

    def test_table_and_original_defaults(self):
        table = {301: 800, 657: 1500, 400: 0}
        self.assertEqual(self.run_hook(301, table), (800, 800))
        self.assertEqual(self.run_hook(657, table), (1500, 1500))
        self.assertEqual(self.run_hook(400, table), (0, 0))
        self.assertEqual(self.run_hook(302, table), (500, 500))      # not in table: original +500
        self.assertEqual(self.run_hook(657, {}), (1000, 1000))       # original Megamorph
        self.assertEqual(self.run_hook(302, {}), (500, 500))


if __name__ == '__main__':
    unittest.main()
