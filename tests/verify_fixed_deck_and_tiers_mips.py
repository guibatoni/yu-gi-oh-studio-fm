"""Exercise the assembled PS1 hooks using synthetic game memory and retail callbacks."""
from collections import Counter
import hashlib
import struct
from types import SimpleNamespace
from unittest.mock import patch

from unicorn import Uc, UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
from unicorn.mips_const import (
    UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_GP, UC_MIPS_REG_RA, UC_MIPS_REG_SP, UC_MIPS_REG_V0,
)
from fmstudio.ps1_mod import compile_mod
from fmstudio.ps1_runtime import (
    CONFIG_ADDRESS, DROP_ENTRY, _jump, _option_calls, _rule_patches, compile_effects, install_runtime, verify_effects,
)
from fmstudio.ps1_runtime_blob import ENTRY_POINTS, RUNTIME_BASE, RUNTIME_END, RUNTIME_MOD_BASE, RUNTIME_MOD_END
from fmstudio.tables import EXE_DELTA

RETURN = 0x80010000
OPPONENT = 0x8009B361
SHUFFLED = 0x80177FE8
SELECTED = 0x8009B338
BOX = 0x800EB0F8
STREAM = 0x800EC000
SPRITE = 0x1F8000C0
RIVAL_SOURCE = 0x801D1300
owns = list(range(1, 38)) + [722, 722, 722]
cards = {i: {'tipo_id': 0} for i in owns}
cards[1] = {'tipo_id': 0, 'raridade': 'epica'}
project = SimpleNamespace(cards=cards, get=cards.__getitem__, effects={}, metadata={
    'edicao_mod': {'duelistas': {'1': {'deck': {'cartas': owns}, 'drops_do_deck': True}}}
})
mod = compile_mod(project, profile=True, wa_verified=False)
plan = compile_effects(project, True, fixed_decks=mod.fixed_decks)
source = bytearray(0x1D0000)
for pc, old, _ in _rule_patches(plan):
    struct.pack_into(f'<{len(old)}I', source, pc-EXE_DELTA, *old)
for pc, _, target, _ in _option_calls(plan):
    struct.pack_into('<I', source, pc-EXE_DELTA, _jump(target, link=True))
# Chosen instructions let us observe that the stock fallback executes the displaced pair.
struct.pack_into('<II', source, DROP_ENTRY-EXE_DELTA, 0x24820060, 0x24420007)
original = bytes(source)
with patch('fmstudio.ps1_runtime.SOURCE_SHA256', hashlib.sha256(original).hexdigest()):
    patched, _ = install_runtime(original, original, plan, description_icons=False)
assert verify_effects(patched, plan, original=original)['status'] == 'aplicado'

cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
cpu.mem_map(0, 0x200000)
cpu.mem_map(0x1F800000, 0x1000)


def address(pc):
    return pc & 0x1FFFFFFF


def write(pc, fmt, *values):
    cpu.mem_write(address(pc), struct.pack('<' + fmt, *values))


def read(pc, fmt):
    return struct.unpack('<' + fmt, cpu.mem_read(address(pc), struct.calcsize(fmt)))


def load_code(start, end):
    cpu.mem_write(address(start), patched[start-EXE_DELTA:end-EXE_DELTA])


def call(pc, a0=0, a1=0):
    cpu.reg_write(UC_MIPS_REG_A0, a0)
    cpu.reg_write(UC_MIPS_REG_A1, a1)
    cpu.reg_write(UC_MIPS_REG_GP, 0x8009AF08)
    cpu.reg_write(UC_MIPS_REG_SP, 0x801FD000)
    cpu.reg_write(UC_MIPS_REG_RA, RETURN)
    cpu.emu_start(pc, RETURN, timeout=1_000_000, count=70_000)
    assert cpu.reg_read(UC_MIPS_REG_SP) == 0x801FD000
    return cpu.reg_read(UC_MIPS_REG_V0)


def stub(pc, callback=None):
    write(pc, 'II', 0x03E00008, 0)
    if callback:
        cpu.hook_add(UC_HOOK_CODE, callback, begin=pc, end=pc)


load_code(RUNTIME_BASE, RUNTIME_END)
load_code(RUNTIME_MOD_BASE, RUNTIME_MOD_END)
load_code(DROP_ENTRY, DROP_ENTRY + 8)
load_code(CONFIG_ADDRESS, CONFIG_ADDRESS + len(plan.data))

original_rivals = []
def shuffle(uc, *_):
    original_rivals.append(uc.reg_read(UC_MIPS_REG_A1))
    rival = original_rivals[-1]
    shuffled = list(reversed(read(rival, '40H'))) if rival else [500] * 40
    write(SHUFFLED, '80H', *([501] * 40 + shuffled))

stub(0x800245A0, shuffle)
stub(DROP_ENTRY + 8)
rng_index = 0
roll_sizes = []
def rng(uc, *_):
    roll_sizes.append(uc.reg_read(UC_MIPS_REG_A0))
    uc.reg_write(UC_MIPS_REG_V0, rng_index)

stub(0x800358FC, rng)
write(OPPONENT, 'B', 1)
assert call(DROP_ENTRY, 0) == 103
call(ENTRY_POINTS['ResetCards'])
call(ENTRY_POINTS['DealConfiguredDecks'])
assert CONFIG_ADDRESS < original_rivals[-1] < CONFIG_ADDRESS + len(plan.data)
assert read(SHUFFLED + 80, '40H') == tuple(reversed(owns))

# Moving cards during the duel and overwriting the shuffle buffer cannot change the reward pool.
write(SHUFFLED + 80, '40H', *([601] * 40))
rewards = []
for rng_index in range(40):
    rewards.append(call(DROP_ENTRY, rng_index % 3))
assert Counter(rewards) == Counter(owns)
assert roll_sizes == [40] * 40

write(RIVAL_SOURCE, '40H', *([500] * 40))
write(OPPONENT, 'B', 2)
call(ENTRY_POINTS['ResetCards'])
call(ENTRY_POINTS['DealConfiguredDecks'], 0, RIVAL_SOURCE)
assert original_rivals[-1] == RIVAL_SOURCE
assert call(DROP_ENTRY, 2) == 105
write(OPPONENT, 'B', 0xFF)
call(ENTRY_POINTS['DealConfiguredDecks'], 0, RIVAL_SOURCE)
assert original_rivals[-1] == RIVAL_SOURCE

def original_insert(uc, *_):
    box = uc.reg_read(UC_MIPS_REG_A0)
    depth, = read(box + 0x58, 'B')
    write(box + 4 * (depth + 1), 'I', STREAM + 12)
    write(box + 0x58, 'B', depth + 1)

def original_end(uc, *_):
    box = uc.reg_read(UC_MIPS_REG_A0)
    depth, = read(box + 0x58, 'B')
    write(box + 0x58, 'B', depth - 1)

seen = []
def sort_sprite(uc, *_):
    sprite = uc.reg_read(UC_MIPS_REG_A0)
    seen.append((read(sprite, 'I')[0], read(sprite + 16, 'HHI')))

stub(0x80037DA4, original_insert)
stub(0x80038E7C, original_end)
stub(0x800849F0, sort_sprite)
write(SELECTED, 'H', 1)
write(STREAM, 'B', 0x20)
write(BOX, 'I', STREAM)
write(BOX + 0x54, 'B', 2)
call(ENTRY_POINTS['InsertTierName'], BOX)
assert read(BOX + 0x54, 'B') == (0x84,)
sprite_fields = (640, 232 + 0x84, 0x808080)
write(SPRITE, 'I', 0x08000040)
write(SPRITE + 16, 'HHI', *sprite_fields)
call(ENTRY_POINTS['SortTierGlyph'], SPRITE)
assert seen[-1] == (0x08000000, (640, 232, 0x803D5B))
assert read(SPRITE + 16, 'HHI') == sprite_fields
assert read(SPRITE, 'I') == (0x08000040,)
call(ENTRY_POINTS['EndTierName'], BOX)
assert read(BOX + 0x54, 'B') == (2,)

write(STREAM, 'B', 0x40)
call(ENTRY_POINTS['InsertTierName'], BOX)
assert read(BOX + 0x54, 'B') == (2,)
write(SPRITE + 16, 'HHI', 640, 234, 0x808080)
call(ENTRY_POINTS['SortTierGlyph'], SPRITE)
assert seen[-1] == (0x08000040, (640, 234, 0x808080))
print('MIPS: deck fixo exato, 40 posições de drop e fallback originais, tier RGB e restauração conferidos.')
