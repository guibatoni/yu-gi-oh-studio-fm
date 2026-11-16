"""Execute the native callback with synthetic PS1 records and a retail stub."""
import struct
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_GP, UC_MIPS_REG_RA, UC_MIPS_REG_SP
from fmstudio.ps1_runtime_blob import ENTRY_POINTS, RUNTIME, RUNTIME_BASE, RUNTIME_EXT, RUNTIME_EXT_BASE

LOCK = 0x8009B16C
STEP = 0x8009B174
RETAIL = 0x8001D670
RETURN = 0x80010000
CONFIG = 0x801CD7A0

machine = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
machine.mem_map(0, 0x200000)

def address(pc):
    return pc & 0x1FFFFFFF

def write(pc, fmt, *values):
    machine.mem_write(address(pc), struct.pack('<'+fmt, *values))

def read(pc, fmt):
    return struct.unpack('<'+fmt, machine.mem_read(address(pc), struct.calcsize(fmt)))[0]

machine.mem_write(address(RUNTIME_BASE), RUNTIME)
machine.mem_write(address(RUNTIME_EXT_BASE), RUNTIME_EXT)
write(RETAIL, 'II', 0x03E00008, 0)
write(CONFIG + 2 + 2 * 16, 'H', 0x780)
write(CONFIG + 0x780, 'BBBBHH', 32, 0, 0, 0, 0, 0)
seen = []

def retail_call(uc, pc, size, unused):
    seen.append(read(LOCK, 'H'))
    if read(STEP, 'B') & 15 == 11:
        write(LOCK, 'H', read(LOCK, 'H') & ~0x1000)

machine.hook_add(UC_HOOK_CODE, retail_call, begin=RETAIL, end=RETAIL)
for side in (0, 1):
    write(0x8009B1D5, 'B', side)
    write(0x8009B23A, 'H', 5)
    cursor = 0x800E9F48 + side * 0x70
    write(cursor+0xF, 'BB', 0, 2)
    card = 0x801A7AD8 + (5+15*side)*28
    write(card + 0x16, 'H', 0x8000)
    for cid, step, observed, final in ((9, 3, 0x1000, 0x1000),
                                       (16, 0x83, 0, 0x1000),
                                       (16, 5, 0x1000, 0x1000),
                                       (16, 11, 0x1000, 0)):
        write(card+0xC, 'H', cid)
        write(LOCK, 'H', 0x1000)
        write(STEP, 'B', step)
        machine.reg_write(UC_MIPS_REG_GP, 0x8009AF08)
        machine.reg_write(UC_MIPS_REG_SP, 0x801FD000)
        machine.reg_write(UC_MIPS_REG_RA, RETURN)
        seen.clear()
        machine.emu_start(ENTRY_POINTS['FieldActions'], RETURN, timeout=1000000, count=15000)
        assert seen == [observed], (side, cid, step, seen, observed)
        assert read(LOCK, 'H') == final, (side, cid, step, read(LOCK, 'H'), final)
print('MIPS: bloqueio por carta selecionada e fim de turno verificados.')
