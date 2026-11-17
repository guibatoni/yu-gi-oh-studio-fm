"""Exercise the effect in the question on the installed PS1 stat hook."""
import struct
from types import SimpleNamespace

from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_GP, UC_MIPS_REG_RA, UC_MIPS_REG_SP, UC_MIPS_REG_V0

from fmstudio.ps1_runtime import CONFIG_ADDRESS, compile_effects
from fmstudio.ps1_runtime_blob import ENTRY_POINTS, RUNTIME, RUNTIME_BASE, RUNTIME_EXT, RUNTIME_EXT_BASE

cards = {7: {'tipo_id': 0}, 8: {'tipo_id': 19}, 9: {'tipo_id': 19}}
project = SimpleNamespace(cards=cards, get=cards.__getitem__, metadata={}, effects={
    '7': [{'evento': 'continuo', 'acao': 'bonus_por_tipo', 'alvo': 'proprio',
           'valor': 500, 'valor_def': 0, 'tipo_id': 19, 'escopo': 'aliados'}],
})
plan = compile_effects(project, True)
assert plan.accepted == ((7, 'bonus_por_tipo'),)
cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
cpu.mem_map(0, 0x200000)

def write(pc, data):
    cpu.mem_write(pc & 0x1FFFFFFF, data)

for pc, data in ((RUNTIME_BASE, RUNTIME), (RUNTIME_EXT_BASE, RUNTIME_EXT), (CONFIG_ADDRESS, plan.data)):
    write(pc, data)
for cid, card in cards.items():
    write(0x801D4244 + (cid - 1) * 4, struct.pack('<I', card['tipo_id'] << 26))

def slot_address(slot):
    return 0x801A7AD8 + 28 * slot

def set_card(slot, cid, flags):
    write(slot_address(slot), struct.pack('<IIIhhhhhHI', 0, 0, 0, cid, 1000, 1200, 0, 0, flags, slot))

def stats(slot):
    ret = 0x80010000
    cpu.reg_write(UC_MIPS_REG_A0, slot_address(slot))
    cpu.reg_write(UC_MIPS_REG_RA, ret)
    cpu.reg_write(UC_MIPS_REG_GP, 0x8009AF08)
    cpu.reg_write(UC_MIPS_REG_SP, 0x801FF000)
    cpu.emu_start(ENTRY_POINTS['CalculateStats'], ret, timeout=1_000_000, count=80_000)
    value = cpu.reg_read(UC_MIPS_REG_V0)
    return value & 0xFFFF, value >> 16

write(0x8009B23A, struct.pack('<H', 5))
set_card(5, 7, 0x8000)
set_card(6, 8, 0x9000)
set_card(20, 9, 0x9000)
assert stats(5) == (1500, 1200)
assert stats(6) == (1000, 1200)
assert stats(20) == (1000, 1200)
set_card(6, 8, 0x8000)
assert stats(5) == (1500, 1200)
set_card(6, 8, 0)
assert stats(5) == (1000, 1200)
print('MIPS: +500 ATK próprio por Plant aliado, aberto ou virado para baixo, e recálculo ao retirar.')
