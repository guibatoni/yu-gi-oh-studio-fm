"""Verify the Supreme matchups and icon adapters in isolated MIPS RAM."""
import struct

from unicorn import Uc, UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
from unicorn.mips_const import (
    UC_MIPS_REG_A0 as A0, UC_MIPS_REG_A1 as A1, UC_MIPS_REG_A2 as A2,
    UC_MIPS_REG_GP as GP, UC_MIPS_REG_PC as PC, UC_MIPS_REG_RA as RA,
    UC_MIPS_REG_S1 as S1, UC_MIPS_REG_S2 as S2, UC_MIPS_REG_S6 as S6,
    UC_MIPS_REG_SP as SP, UC_MIPS_REG_V0 as V0, UC_MIPS_REG_V1 as V1,
)

from fmstudio.guardian import guardian_bonuses
from fmstudio.ps1_supreme_blob import BASE, CODE, ENTRY_POINTS
from fmstudio.tables import PS1_SUPREME, STATS_ADDR, SUPREME


cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
cpu.mem_map(0, 0x200000)
STACK, GLOBALS, RETURN = 0x801FF000, 0x8009AF08, 0x80122000


def write(address, data):
    cpu.mem_write(address & 0x1FFFFFFF, data)


def pack(address, fmt, *values):
    write(address, struct.pack(fmt, *values))


def read(address, fmt):
    return struct.unpack(fmt, cpu.mem_read(address & 0x1FFFFFFF, struct.calcsize(fmt)))


def call(entry, a0=0, a1=0, a2=0, *, stop=RETURN):
    for register, value in ((GP, GLOBALS), (SP, STACK), (RA, RETURN),
                            (A0, a0), (A1, a1), (A2, a2)):
        cpu.reg_write(register, value)
    cpu.emu_start(ENTRY_POINTS[entry], stop, count=200)
    assert cpu.reg_read(PC) == stop, (entry, hex(cpu.reg_read(PC)))
    word = cpu.reg_read(V0)
    return struct.unpack('<i', struct.pack('<I', word))[0]


write(BASE, CODE)
for star in range(16):
    if star == PS1_SUPREME:
        continue
    left, right = guardian_bonuses(SUPREME, star)
    assert call('SupremeMatchup', PS1_SUPREME, star) == left - right
    left, right = guardian_bonuses(star, SUPREME)
    assert call('SupremeMatchup', star, PS1_SUPREME) == left - right
assert call('SupremeMatchup', PS1_SUPREME, PS1_SUPREME) == 0
for left, branch in ((1, 0x8002CBA0), (8, 0x8002CB8C)):
    call('SupremeMatchup', left, 3, stop=branch)
    assert cpu.reg_read(A0) == (left - 7) & 0xFFFFFFFF
    assert cpu.reg_read(A1) == 3 and cpu.reg_read(V1) == 6

for input_icon, output_icon in ((0x20, 0x20), (0x22, 0x49), (0x31, 0x31)):
    call('SupremeTextIcon', 0, input_icon, stop=0x80037FF4)
    assert cpu.reg_read(A1) == output_icon
    write(GLOBALS + 0x43C, bytes([input_icon]))
    call('SupremeFieldIcon', stop=0x80038078)
    assert cpu.reg_read(A1) == output_icon and cpu.reg_read(SP) == STACK - 24
call('SupremeTextIcon', 0, 0x22, 1, stop=0x80037FFC)
assert cpu.reg_read(A1) == 0x22  # The missing-second-star route stays suppressed.

SPRITE, SOURCE, STREAM, TEMP = (0x80122200, 0x80122400, 0x80122600, 0x80122800)
pack(STACK + 0x34, '<I', SPRITE)
pack(STACK + 0x100, '<I', SOURCE)
pack(SOURCE + 4, '<I', 0x00100000)
cpu.reg_write(S2, STREAM)
cpu.reg_write(S6, TEMP)
write(STREAM - 6, b'\x49')
call('SupremeSprite', stop=0x800362A8)
assert read(SPRITE, '<I4xHHHBBHH') == (0x08100000, 16, 16, 10, 160, 192, 672, 255)
write(STREAM - 6, b'\x22')
call('SupremeSprite', stop=0x8003608C)
assert cpu.reg_read(S1) == cpu.reg_read(V1) == SPRITE and cpu.reg_read(V0) == 0xB

GATHER, WORK = 0x801462B0, 0x80123000
pack(GATHER, '<II', 0x03E00008, 0)
phases = []
cpu.hook_add(UC_HOOK_CODE, lambda uc, pc, size, _: phases.append(uc.reg_read(A1)),
             begin=GATHER, end=GATHER)
call('SupremeGather', 14, PS1_SUPREME - 1, WORK)
assert phases == [0]
assert read(WORK + 0x8C4, '<4H') == (160, 192, 0x2A, (255 << 6) | (672 >> 4))
call('SupremeGather', 14, 6, WORK)
call('SupremeGather', 2, PS1_SUPREME - 1, WORK)
assert phases == [0, 6, PS1_SUPREME - 1]

OBJECT = 0x80124000
for cid, flags, stars, side, limit in (
    (723, 0, (PS1_SUPREME, 8), 0, 700),
    (740, 0x200, (8, PS1_SUPREME), 1, 700),
    (1, 0, (8, 9), 0, 500),
):
    pack(0x800E9EF0, '<II', OBJECT, OBJECT)
    pack(OBJECT + 0x6A, '<B', 0)
    pack(0x801A7AD8 + 12, '<h', cid)
    pack(0x801A7AD8 + 22, '<H', flags)
    pack(STATS_ADDR + 4 * (cid - 1), '<I', (stars[0] << 22) | (stars[1] << 18))
    pack(GLOBALS + 0x2B1, '<b', side)
    pack(GLOBALS + 0x2C8, '<H', limit - 8)
    pack(GLOBALS + 0x26C, '<B', 0x60)
    cpu.reg_write(V1, 0x60)
    call('SupremeDisplayBonus', stop=0x8001FF90)
    assert read(GLOBALS + 0x2C8, '<H') == (limit,)
    assert read(GLOBALS + 0x26C, '<B') == (0x20,)

print('MIPS: Supreme em ambos os lados, ícone, animação +700 e rotas originais conferidos.')
