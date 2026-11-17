"""Execute the real native summon LP instructions on a PS1 MIPS emulator.

Uses an isolated 2MB RAM image: no user's ROM or mod is modified.
"""
import struct
from types import SimpleNamespace

from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
from unicorn.mips_const import (
    UC_MIPS_REG_A0, UC_MIPS_REG_GP, UC_MIPS_REG_RA, UC_MIPS_REG_SP,
)

from fmstudio.ps1_runtime import CONFIG_ADDRESS, SUMMON_DAMAGE, SUMMON_HEAL, compile_effects
from fmstudio.ps1_runtime_blob import (
    ENTRY_POINTS, RUNTIME, RUNTIME_BASE, RUNTIME_EXT, RUNTIME_EXT_BASE,
)

project = SimpleNamespace(
    cards={2: {'tipo_id': 0}},
    effects={'2': [
        {'evento': 'invocar', 'acao': 'cura_lp', 'alvo': 'proprio', 'valor': 2000},
        {'evento': 'invocar', 'acao': 'dano_lp', 'alvo': 'inimigo', 'valor': 600},
    ]},
    metadata={},
    get=lambda cid: {'tipo_id': 0},
)
plan = compile_effects(project, True)
assert plan.accepted == ((2, 'cura_lp'), (2, 'dano_lp')), plan
off = struct.unpack_from('<H', plan.data, 2 + 2 * 2)[0]
assert struct.unpack_from('<BBHHH', plan.data, off + 8)[0] == SUMMON_HEAL
assert struct.unpack_from('<BBHHH', plan.data, off + 16)[0] == SUMMON_DAMAGE

cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
cpu.mem_map(0, 0x200000)

def write(pc, data):
    cpu.mem_write(pc & 0x1FFFFFFF, data)

def lp(side):
    return struct.unpack('<H', cpu.mem_read((0x800E9FF0 + 32 * side + 0x14) & 0x1FFFFFFF, 2))[0]

def set_lp(side, value):
    write(0x800E9FF0 + 32 * side + 0x14, struct.pack('<H', value))

for pc, data in ((RUNTIME_BASE, RUNTIME),
                 (RUNTIME_EXT_BASE, RUNTIME_EXT),
                 (CONFIG_ADDRESS, plan.data)):
    write(pc, data)
for slot in (5, 20):
    write(0x801A7AD8 + 28 * slot + 12, struct.pack('<h', 2))

def summon(slot):
    ret = 0x80010000
    cpu.reg_write(UC_MIPS_REG_A0, slot)
    cpu.reg_write(UC_MIPS_REG_RA, ret)
    cpu.reg_write(UC_MIPS_REG_GP, 0x8009AF08)
    cpu.reg_write(UC_MIPS_REG_SP, 0x801FF000)
    cpu.emu_start(ENTRY_POINTS['summon_damage'], ret, timeout=1_000_000, count=80_000)

set_lp(0, 8000)
set_lp(1, 8000)
summon(5)
assert (lp(0), lp(1)) == (10000, 7400), (lp(0), lp(1))
summon(20)
assert (lp(0), lp(1)) == (9400, 9400), (lp(0), lp(1))
set_lp(0, 65000)
summon(5)
assert lp(0) == 65535, lp(0)
print('MIPS: cura 2000 LP na invocação, dano 600 ao rival, ambos os donos e saturação u16 conferidos.')
