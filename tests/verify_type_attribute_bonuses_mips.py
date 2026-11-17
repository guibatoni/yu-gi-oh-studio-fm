"""Execute the Drop x15 bonus filters and cemetery counters in MIPS."""
import struct
from types import SimpleNamespace

from unicorn import Uc, UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_GP, UC_MIPS_REG_PC, UC_MIPS_REG_RA, UC_MIPS_REG_SP, UC_MIPS_REG_V0

from fmstudio.ps1_runtime import CONFIG_ADDRESS, compile_effects
from fmstudio.ps1_runtime_blob import (
    ENTRY_POINTS, RUNTIME, RUNTIME_BASE, RUNTIME_EXT, RUNTIME_EXT_BASE,
    RUNTIME_GRAVE_FILTERS, RUNTIME_GRAVE_FILTERS_BASE,
)
from fmstudio.tables import LEVEL_ADDR, STATS_ADDR


def bonus(action, atk, **criteria):
    return {'evento': 'continuo', 'acao': action, 'alvo': 'proprio', 'valor': atk,
            'valor_def': atk // 10, **criteria}


either = {'tipo_id': 19, 'atributo_id': 1, 'combinar_filtros': 'ou'}
cards = {1: (0, 0), 2: (19, 0), 3: (8, 1), 4: (19, 1), 5: (8, 0)}
project = SimpleNamespace(
    get=lambda cid: {'tipo_id': cards[cid][0]},
    effects={'1': [
        bonus('bonus_por_tipo', 100, escopo='todos', **either),
        bonus('bonus_deck_tipo', 200, **either),
        bonus('bonus_cemiterio_tipo', 300, escopo='todos', **either),
        bonus('bonus_cemiterio_tipo', 400, atributo_id=1),
        bonus('bonus_cemiterio_tipo', 80, tipo_id=19, atributo_id=1, escopo='todos'),
        bonus('bonus_cemiterio_tipo', 60, tipo_id=19, escopo='todos'),
    ]},
)
plan = compile_effects(project, True)
assert not plan.pending and plan.grave_filters and not plan.entry_markers
cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
cpu.mem_map(0, 0x200000)


def write(address, fmt, *values):
    cpu.mem_write(address & 0x1FFFFFFF, struct.pack(fmt, *values))


def seed(slot, cid):
    write(0x801A7AD8 + 28 * slot + 12, '<hhhhhH', cid, 1000, 1200, 0, 0, 0x9000)


def run(entry, a0=0):
    ret = 0x80010000
    for reg, value in ((UC_MIPS_REG_A0, a0), (UC_MIPS_REG_GP, 0x8009AF08),
                       (UC_MIPS_REG_SP, 0x801FF000), (UC_MIPS_REG_RA, ret)):
        cpu.reg_write(reg, value)
    cpu.emu_start(ENTRY_POINTS[entry], ret, count=100000)
    assert cpu.reg_read(UC_MIPS_REG_PC) == ret
    return cpu.reg_read(UC_MIPS_REG_V0)


def check_stats(extra_atk):
    packed = run('CalculateStats', 0x801A7AD8 + 28 * 5)
    assert (packed & 0xFFFF, packed >> 16) == (1000 + extra_atk, 1200 + extra_atk // 10)


def skip_retail(machine, _address, _size, _data):
    machine.reg_write(UC_MIPS_REG_PC, machine.reg_read(UC_MIPS_REG_RA))


for address in (0x80018608, 0x80024914):
    cpu.hook_add(UC_HOOK_CODE, skip_retail, begin=address, end=address)
for address, data in ((RUNTIME_BASE, RUNTIME), (RUNTIME_EXT_BASE, RUNTIME_EXT),
                      (RUNTIME_GRAVE_FILTERS_BASE, RUNTIME_GRAVE_FILTERS), (CONFIG_ADDRESS, plan.data)):
    cpu.mem_write(address & 0x1FFFFFFF, data)
for cid, (kind, attribute) in cards.items():
    write(STATS_ADDR + 4 * (cid - 1), '<I', kind << 26)
    write(LEVEL_ADDR + cid, '<B', attribute << 4)

write(0x8009B23A, '<H', 5)
run('ResetCards')
for index, cid in enumerate((2, 3, 4, 5)):
    write(0x801A7E20 + 6 * index, '<h', cid)
run('Startup')
for slot, cid in ((5, 1), (6, 2), (20, 3), (7, 4), (21, 5)):
    seed(slot, cid)
check_stats(900)
write(0x801A7E20, '<h', 5)
run('Startup')
check_stats(900)  # Holds the composition at the start of the duel.
for slot, expected in ((6, 1160), (20, 1360), (7, 2100), (21, 2100)):
    run('RemoveCard', 0x801A7AD8 + 28 * slot)
    check_stats(expected)
run('ResetCards')
seed(5, 1)
check_stats(0)
print('MIPS: filtro OU no campo/deck/cemitério, interseção única, escopos e reinício do duelo conferidos.')
