"""Execute the 740-card adapters and rules in isolated PS1 MIPS RAM."""
import struct
from types import SimpleNamespace
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import *

from fmstudio import ps1_expanded_runtime_blob as blob
from fmstudio.ps1_expansion import EXPANDED_LEVELS, MODEL_TABLE
from fmstudio.ps1_runtime import CONFIG_ADDRESS, compile_effects

cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
cpu.mem_map(0, 0x200000)
RETURN = 0x80123000


def write(address, value):
    cpu.mem_write(address & 0x1FFFFFFF, value)


def read(address, size):
    return bytes(cpu.mem_read(address & 0x1FFFFFFF, size))


def word(address, value):
    write(address, struct.pack('<I', value))


for label in ('RUNTIME', 'RUNTIME_EXT', 'RUNTIME_MOD', 'RUNTIME_EXPANSION', 'RUNTIME_EXPANSION_AUX'):
    write(getattr(blob, label + '_BASE'), getattr(blob, label))
models = {723: 1, 724: 337, 725: 686, 726: 657, 727: 666, 740: 4}
for cid, base in models.items():
    write(MODEL_TABLE + 2 * (cid - 723), struct.pack('<H', base))
word(MODEL_TABLE + 36, 18000 + 18 - 5776)


def call(key, *args, stop=RETURN):
    for reg, value in zip((UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3), args):
        cpu.reg_write(reg, value & 0xFFFFFFFF)
    cpu.reg_write(UC_MIPS_REG_SP, 0x801FF000)
    cpu.reg_write(UC_MIPS_REG_GP, 0x8009AF08)
    cpu.reg_write(UC_MIPS_REG_RA, RETURN)
    hook = cpu.hook_add(UC_HOOK_CODE, lambda uc, pc, size, _: uc.emu_stop() if pc == stop else None)
    cpu.emu_start(blob.ENTRY_POINTS[key] if isinstance(key, str) else key, 0, count=1_000_000)
    cpu.hook_del(hook)
    assert cpu.reg_read(UC_MIPS_REG_PC) == stop, (key, hex(cpu.reg_read(UC_MIPS_REG_PC)))
    return cpu.reg_read(UC_MIPS_REG_V0)


for cid in (1, 16, 722, 723, 724, 725, 726, 727, 728, 740, 741):
    cpu.reg_write(UC_MIPS_REG_V0, cid)
    assert call('MapNewCard') == models.get(cid, cid)

# Card art, thumbnail streaming, every subsequent WA package, other files
# and absolute-sector requests retain distinct transfer rules.
for file_id, sector, callback, expected in (
    (0, 0, 0x800245EC, 0), (0, 739, 0x800245EC, 739),
    (0, 722, 0x800289BC, 740), (0, 5769, 0x800289BC, 5787),
    (0, 5776, 0x800289BC, 18018), (0, 5895, 0x800289BC, 18137),
    (0, 6000, 0x80020000, 6018), (1, 6000, 0x80020000, 6000),
    (0, -500, 0x80020000, -500),
):
    word(0x801FF014, callback)
    call('ExpandedTransfer', 0x80120000, file_id, 0, sector, stop=0x800139A0)
    assert cpu.reg_read(UC_MIPS_REG_A3) == expected & 0xFFFFFFFF
    assert cpu.reg_read(UC_MIPS_REG_SP) == 0x801FEFD8

for slot, model, expected in ((0, 722, 0), (1, 739, 3), (2, 739, 739), (128, 722, 0), (0, -1, -1)):
    call('ExpandedModel', slot, model, stop=0x8005650C)
    assert cpu.reg_read(UC_MIPS_REG_A1) == expected & 0xFFFFFFFF
    assert cpu.reg_read(UC_MIPS_REG_RA) == RETURN
    assert cpu.reg_read(UC_MIPS_REG_SP) == 0x801FEFB8

cards = {cid: {'tipo_id': 0, 'ataque': 1000, 'defesa': 1200} for cid in (1, 2, 4, 723, 740)}
cards.update({724: {'tipo_id': 20}, 725: {'tipo_id': 21}, 726: {'tipo_id': 23}, 727: {'tipo_id': 22}})
project = SimpleNamespace(cards=cards, get=cards.__getitem__, metadata={'ps1_password_id_prefix': 0},
    effects={'723': [
        {'evento': 'invocar', 'acao': 'dano_lp', 'alvo': 'inimigo', 'valor': 800},
        {'evento': 'regra_deck', 'acao': 'limite_copias_deck', 'alvo': 'proprio', 'valor': 1},
    ], '740': [{'evento': 'regra_deck', 'acao': 'limite_copias_deck', 'alvo': 'proprio', 'valor': 0}]})
plan = compile_effects(project, True, fusions={(1, 2): 723, (723, 740): 4})
assert plan.capacity == 740 and not plan.pending
write(CONFIG_ADDRESS, plan.data)
write(0x80019A60, struct.pack('<III', 0x240203E7, 0x03E00008, 0))
for a, b, expected in ((1, 2, 723), (2, 1, 723), (723, 740, 4), (740, 723, 4),
                        (723, 4, 0), (740, 740, 0), (1, 4, 999)):
    assert call('CheckEditedFusion', a, b) == expected
assert call('DeckAllowsCopies', 723, 0) == 1
assert call('DeckAllowsCopies', 723, 1) == 0
assert call('DeckAllowsCopies', 740, 0) == 0

# Dispatch delegates to a synthetic continuation with the native store ABI.
write(0x80026BAC, struct.pack('<III', 0xA78402CA, 0x03E00008, 0))
for cid, expected in ((724, 337), (727, 727), (337, 337)):
    kind = cards.get(cid, {}).get('tipo_id', 20)
    word(0x801D4244 + 4 * (cid - 1), kind << 26)
    call('ExpandedEffect', cid, 1)
    assert struct.unpack('<H', read(0x8009B1D2, 2))[0] == expected

record = 0x80122000
write(record + 12, struct.pack('<h', 725))
cpu.reg_write(UC_MIPS_REG_V1, record)
call('SpellTrapId', stop=0x8002508C)
assert cpu.reg_read(UC_MIPS_REG_V0) == 686
assert cpu.reg_read(UC_MIPS_REG_V1) == record
assert cpu.reg_read(UC_MIPS_REG_RA) == RETURN
call('AttackTrapId', 0x80122100, 0, record, stop=0x8001F178)
assert cpu.reg_read(UC_MIPS_REG_A1) == 686
assert cpu.reg_read(UC_MIPS_REG_A0) == 0x80122100

write(0x8009B206, struct.pack('<H', 726))
for key, stop, register in (('EquipBonusId', 0x8001A81C, UC_MIPS_REG_V1),
                            ('EquipAnimationId', 0x8001ABA0, UC_MIPS_REG_A0),
                            ('EquipSecondAnimationId', 0x8001ABFC, UC_MIPS_REG_V1)):
    call(key, stop=stop)
    assert cpu.reg_read(register) == 657
cpu.reg_write(UC_MIPS_REG_V0, 120)
call('EquipSwordId', stop=0x8001ABE0)
assert cpu.reg_read(UC_MIPS_REG_V0) == 120 and cpu.reg_read(UC_MIPS_REG_V1) == 657

slot = 0x801A7AD8 + 28 * 5
write(slot + 12, struct.pack('<h', 723))
write(slot + 22, struct.pack('<H', 0x9000))
write(0x800E9FF0 + 20, struct.pack('<H', 8000))
write(0x800EA010 + 20, struct.pack('<H', 8000))
call('summon_damage', 5)
assert struct.unpack('<H', read(0x800EA010 + 20, 2))[0] == 7200

# Alias transactions may not consume campaign bits for extra IDs. A hole
# must keep the invalid native password instead of being turned into a card.
shop_calls = []
def shop(uc, pc, size, _):
    if pc != 0x8016A37C:
        return
    cid = 100 * read(0x8016D415, 1)[0] + 10 * read(0x8016D416, 1)[0] + read(0x8016D417, 1)[0]
    entry = read(0x801A8000 + cid * 8, 8)
    flag = 0x801D0618 + ((cid + 0x400) >> 3)
    shop_calls.append((cid, entry, read(flag, 1)))
    write(flag, b'\xff')
    uc.reg_write(UC_MIPS_REG_PC, uc.reg_read(UC_MIPS_REG_RA))

hook = cpu.hook_add(UC_HOOK_CODE, shop)
for cid in (723, 740):
    entry = 0x801A8000 + cid * 8
    write(entry, struct.pack('<II', 99, 0xFFFFFFFE))
    write(0x8016D410, bytes(int(c) for c in f'{cid:08d}'))
    write(0x8016D424, bytes(2))
    flag = 0x801D0618 + ((cid + 0x400) >> 3)
    write(flag, b'\xa5')
    call('UpdatePasswordShop')
    assert shop_calls[-1][1] == struct.pack('<II', 1, int(f'{cid:08d}', 16))
    assert shop_calls[-1][2][0] & (0x80 >> ((cid + 0x400) & 7)) == 0
    assert read(flag, 1) == b'\xa5'
    assert read(entry, 8) == struct.pack('<II', 99, 0xFFFFFFFE)
write(0x8016D410, bytes(int(c) for c in f'{728:08d}'))
write(0x801A8000 + 728 * 8, struct.pack('<II', 1, 0xFFFFFFFE))
call('UpdatePasswordShop')
assert shop_calls[-1][1] == struct.pack('<II', 1, 0xFFFFFFFE)
cpu.hook_del(hook)
print('740-card MIPS: transfers, models, all five types, fusions, limits, summon damage and password/save guards passed.')
