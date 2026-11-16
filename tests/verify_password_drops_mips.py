"""Execute the native drop and password handlers in MIPS with synthetic retail stubs."""
import struct
from types import SimpleNamespace

from unicorn import Uc, UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_GP, UC_MIPS_REG_RA, UC_MIPS_REG_SP, UC_MIPS_REG_V0
from fmstudio.ps1_runtime import CONFIG_ADDRESS, compile_effects
from fmstudio.ps1_runtime_blob import (
    ENTRY_POINTS, RUNTIME, RUNTIME_BASE, RUNTIME_EXT, RUNTIME_EXT_BASE, RUNTIME_PASSWORD, RUNTIME_PASSWORD_BASE,
)

RETURN = 0x80010000
OPPONENT = 0x8009B361
DECK = 0x801A7E20
SHOP = 0x8016A37C
STAGE = 0x8016D424
PREVIEW = 0x8016D4DC
DIGITS = 0x8016D410
RECORDS = 0x801A8000
machine = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
machine.mem_map(0, 0x200000)


def address(pc):
    return pc & 0x1FFFFFFF


def write(pc, fmt, *values):
    machine.mem_write(address(pc), struct.pack('<' + fmt, *values))


def read(pc, fmt):
    return struct.unpack('<' + fmt, machine.mem_read(address(pc), struct.calcsize(fmt)))


def call(name, argument=0):
    machine.reg_write(UC_MIPS_REG_A0, argument)
    machine.reg_write(UC_MIPS_REG_GP, 0x8009AF08)
    machine.reg_write(UC_MIPS_REG_SP, 0x801FD000)
    machine.reg_write(UC_MIPS_REG_RA, RETURN)
    machine.emu_start(ENTRY_POINTS[name], RETURN, timeout=1_000_000, count=50_000)
    assert machine.reg_read(UC_MIPS_REG_SP) == 0x801FD000
    return machine.reg_read(UC_MIPS_REG_V0)


def stub(pc, callback=None):
    write(pc, 'II', 0x03E00008, 0)
    if callback:
        machine.hook_add(UC_HOOK_CODE, callback, begin=pc, end=pc)


plan = compile_effects(SimpleNamespace(metadata={
    'edicao_mod': {'duelistas': {'3': {'drops_do_deck': True}}},
    'ps1_password_id_prefix': 10,
}), True)
for pc, data in ((RUNTIME_BASE, RUNTIME), (RUNTIME_EXT_BASE, RUNTIME_EXT),
                 (RUNTIME_PASSWORD_BASE, RUNTIME_PASSWORD), (CONFIG_ADDRESS, plan.data)):
    machine.mem_write(address(pc), data)

stub(0x80018608)
random_index = 0
ranges = []
fallback_ranks = []


def rng(uc, *_):
    ranges.append(uc.reg_read(UC_MIPS_REG_A0))
    uc.reg_write(UC_MIPS_REG_V0, random_index)


def old_drop(uc, *_):
    fallback_ranks.append(uc.reg_read(UC_MIPS_REG_A0))
    uc.reg_write(UC_MIPS_REG_V0, 100)


stub(0x800358FC, rng)
stub(0x80021810, old_drop)
write(OPPONENT, 'B', 3)
assert call('SelectDeckDrop', 1) == 100
for index, cid in enumerate([6] * 40 + [9, 722, 16, 16] + [0] * 36):
    write(DECK + index * 6, 'h', cid)
write(0x8009B23A, 'H', 2)
call('ResetCards')
call('Startup')
write(DECK + 40 * 6, 'h', 700)
for random_index, cid in enumerate((9, 722, 16, 16)):
    assert call('SelectDeckDrop', random_index % 3) == cid
assert ranges == [4] * 4
write(OPPONENT, 'B', 4)
assert call('SelectDeckDrop', 2) == 100
assert fallback_ranks == [1, 2]
call('ResetCards')
write(OPPONENT, 'B', 3)
assert call('SelectDeckDrop', 1) == 100


def digits(code):
    write(DIGITS, '8B', *map(int, code))


observed = []
god = RECORDS + 8 * 16
last = RECORDS + 8 * 722
write(god, 'II', 1234, 0x01237654)
write(last, 'II', 141, 0xFFFFFFFE)


def shop(uc, *_):
    observed.append((read(god, 'II'), read(last, 'II')))


stub(SHOP, shop)
for stage in (0, 2, 3, 4):
    write(STAGE, 'H', stage | 0x8000)
    write(PREVIEW, 'H', 16)
    digits('00010016')
    call('UpdatePasswordShop')
    assert observed[-1] == ((1, 0x00010016), (141, 0xFFFFFFFE)), observed[-1]
    assert read(god, 'II') == (1234, 0x01237654)
for code in ('01237654', '00010000', '00010723'):
    digits(code)
    write(STAGE, 'H', 0)
    call('UpdatePasswordShop')
    assert observed[-1][0] == (1234, 0x01237654)
digits('00010722')
call('UpdatePasswordShop')
assert observed[-1][1] == (1, 0x00010722)
assert read(last, 'II') == (141, 0xFFFFFFFE)
print('MIPS verificado: snapshots, seleção por duelista, fallback por rank, IDs #016/#722, preço e restauração dos passwords originais.')
