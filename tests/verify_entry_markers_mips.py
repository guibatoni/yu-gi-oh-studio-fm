"""Execute the native entry hooks and real ATK/DEF calculation in MIPS."""
import struct
from types import SimpleNamespace

from unicorn import Uc, UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
from unicorn.mips_const import (
    UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_GP, UC_MIPS_REG_PC, UC_MIPS_REG_RA,
    UC_MIPS_REG_SP, UC_MIPS_REG_V0,
)

from fmstudio.core import ENTRY_GROW, ENTRY_SHRINK, ENTRY_TYPE_EVENT
from fmstudio.ps1_runtime import CONFIG_ADDRESS, compile_effects
from fmstudio.ps1_runtime_blob import (
    ENTRY_POINTS, RUNTIME, RUNTIME_BASE, RUNTIME_EXT, RUNTIME_EXT_BASE,
    RUNTIME_MARKERS, RUNTIME_MARKERS_BASE,
)

cards = {1: (19, 1000, 800), 2: (19, 250, 400), 3: (0, 1000, 1000),
         4: (19, 100, 100), 5: (19, 200, 650), 6: (0, 50, 50)}
project = SimpleNamespace(
    effects={
        '1': [{'evento': ENTRY_TYPE_EVENT, 'acao': ENTRY_GROW, 'alvo': 'proprio', 'tipo_id': 19, 'valor': 200}],
        '3': [{'evento': 'invocar', 'acao': ENTRY_SHRINK, 'alvo': 'aliados_tipo', 'tipo_id': 19, 'valor': 500}],
        '4': [{'evento': 'continuo', 'acao': 'monstro_indestrutivel', 'alvo': 'proprio', 'valor': 0}],
    },
    get=lambda cid: {'tipo_id': cards[cid][0]},
)
plan = compile_effects(project, True)
assert not plan.pending and plan.entry_markers
cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
cpu.mem_map(0, 0x200000)


def write(address, fmt, *values):
    cpu.mem_write(address & 0x1FFFFFFF, struct.pack(fmt, *values))


def card_address(slot):
    return 0x801A7AD8 + 28 * slot


def record(slot, cid, *, flags=0x8000, equip=0, terrain=0):
    _, atk, defense = cards[cid]
    write(card_address(slot) + 12, '<hhhhhH', cid, atk, defense, equip, terrain, flags)


def occupied(slot):
    return bool(cpu.mem_read((card_address(slot) + 23) & 0x1FFFFFFF, 1)[0] & 0x80)


SCENE, EFFECT_FLAGS, SOURCE_OBJECT = 0x8009B23A, 0x8009B220, 0x80100400
CREATE, DEACTIVATE, RETAIL_FIELD = 0x80024D34, 0x80024914, 0x8001D670
retail_placements = []
removed = []


def retail_callback(machine, address, size, _):
    if address == CREATE:
        slot, cid = machine.reg_read(UC_MIPS_REG_A0), machine.reg_read(UC_MIPS_REG_A1)
        if slot & 0x80:
            slot = (slot & 0x7F) + 15
        retail_placements.append((slot, cid))
        record(slot, cid, **incoming)
    elif address == DEACTIVATE:
        removed.append((machine.reg_read(UC_MIPS_REG_A0) - card_address(0)) // 28)
    machine.reg_write(UC_MIPS_REG_PC, machine.reg_read(UC_MIPS_REG_RA))


for address in (CREATE, DEACTIVATE, RETAIL_FIELD):
    cpu.hook_add(UC_HOOK_CODE, retail_callback, begin=address, end=address)
for address, code in ((RUNTIME_BASE, RUNTIME), (RUNTIME_EXT_BASE, RUNTIME_EXT),
                      (RUNTIME_MARKERS_BASE, RUNTIME_MARKERS), (CONFIG_ADDRESS, plan.data)):
    cpu.mem_write(address & 0x1FFFFFFF, code)
for cid, (kind, _, _) in cards.items():
    write(0x801D4244 + 4 * (cid - 1), '<I', kind << 26)


def run(key, a0=0, a1=0):
    ret = 0x80010000
    for reg, value in ((UC_MIPS_REG_A0, a0), (UC_MIPS_REG_A1, a1), (UC_MIPS_REG_RA, ret),
                       (UC_MIPS_REG_GP, 0x8009AF08), (UC_MIPS_REG_SP, 0x801FF000)):
        cpu.reg_write(reg, value)
    cpu.emu_start(ENTRY_POINTS[key], ret, timeout=1_000_000, count=80_000)
    assert cpu.reg_read(UC_MIPS_REG_PC) == ret, key
    return cpu.reg_read(UC_MIPS_REG_V0)


def stats(slot):
    packed = run('CalculateStats', card_address(slot))
    return packed & 0xFFFF, packed >> 16


def place(slot, cid, *, ritual=False, source=1, **values):
    global incoming
    incoming = values
    write(SCENE, '<H', 5 if ritual else 8)
    write(0x800E9EF0, '<I', SOURCE_OBJECT)
    write(SOURCE_OBJECT + 0x6A, '<B', source)
    run('CreateMarkedPlacement', slot, cid)


def field():
    write(SCENE, '<H', 5)
    run('FieldActionsWithMarkers')


run('ResetCardsWithMarkers')
place(5, 1, flags=0x9000)
assert stats(5) == (1000, 800), 'no marker before placement is complete'
field()
assert stats(5) == (1200, 1000), 'entry counts itself even face-down'
place(0x85, 2, flags=0x9000, terrain=100)
field()
assert stats(5) == (1400, 1200), 'enemy entry and mirrored index'
place(5, 1, source=5, equip=50)
field()
assert stats(5) == (1450, 1250), 'equipment preserves markers without counting as another entry'

place(21, 4)
field()
place(22, 5, terrain=100)
field()
place(23, 6)
field()
assert stats(5) == (1850, 1650), 'two matching placements and one different type'

write(SCENE, '<H', 7)
run('ConsumeFusionMaterial', card_address(5))
assert removed == [5] and not occupied(5)
place(5, 1, source=5)
field()
assert stats(5) == (1200, 1000), 'fusion returning the same ID starts a new instance'

record(6, 2)
place(7, 3, ritual=True)
write(EFFECT_FLAGS, '<H', 0x8000)
field()
assert occupied(20) and stats(22) == (300, 750), 'wait until ritual animation ends'
write(EFFECT_FLAGS, '<H', 0)
field()
assert removed == [5, 20] and not occupied(20)
assert occupied(21) and stats(21) == (0, 0), 'indestructible monster'
assert stats(22) == (0, 250) and occupied(22), 'survives while one stat is positive'
assert stats(6) == (250, 400) and stats(23) == (50, 50), 'scope and type filters'
field()
assert stats(22) == (0, 250), 'a pending entry is processed once'

run('RemoveCard', card_address(7))
assert stats(22) == (0, 250), 'reductions outlive the source'
run('ResetCardsWithMarkers')
record(22, 5, terrain=100)
assert stats(22) == (300, 750) and len(retail_placements) == 8, 'new duel clears marker state'

cards[7] = (0, 200, 200)
write(0x801D4244 + 4 * (7 - 1), '<I', 0)
for cid in (4, 7):
    write(0x801D5332 + cid, '<B', 1 << 4)
project.effects['1'][0].update(atributo_id=1, combinar_filtros='ou')
project.effects['3'][0].update(tipo_id=-1, atributo_id=1)
filtered_plan = compile_effects(project, True)
cpu.mem_write(CONFIG_ADDRESS & 0x1FFFFFFF, filtered_plan.data)
run('ResetCardsWithMarkers')
for slot, cid in ((5, 1), (20, 7), (21, 4), (22, 2)):
    place(slot, cid)
    field()
assert stats(5) == (1800, 1600), 'type or attribute, including the intersection once'
place(6, 3)
field()
assert not occupied(20) and stats(21) == (0, 0), 'attribute-only reduction'
assert stats(22) == (250, 400), 'attribute mismatch is unaffected, even with the same type'
print('MIPS: marcadores por tipo/atributo, equipamento, fusão, ritual e destruição 0/0 conferidos.')
