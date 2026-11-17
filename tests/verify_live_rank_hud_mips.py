"""Exercise the compiled rank renderer and verify its native glyph calls."""
import struct

from unicorn import Uc, UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
from unicorn.mips_const import (
    UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3,
    UC_MIPS_REG_GP, UC_MIPS_REG_RA, UC_MIPS_REG_SP, UC_MIPS_REG_V0,
)

from fmstudio.duel_rank import RANK_RULES
from fmstudio.ps1_runtime_blob import ENTRY_POINTS, RUNTIME_RANK_HUD, RUNTIME_RANK_HUD_BASE

PLAYER, OPPONENT, RULES = 0x800E9FF0, 0x8009B361, 0x801798A8
NUMBERS, SCORER, SPRITES = 0x80016D2C, 0x80021558, 0x800849F0
PANEL, TABLE, SPRITE, RETURN = 0x80100000, 0x80100100, 0x80100200, 0x80010000
GLYPHS = dict(zip((0xA0,0xA1,0xA2,0xA3,0xA4,0xAE,0xAF,0xB2,0xB3,0xB6,0xBE), 'ABCDEOPSTW-'))
GLYPHS.update({0xE0 + i: str(i) for i in range(10)})
RULE_KEYS = ('turnos','ataques_efetivos','vitorias_defensivas','cartas_setadas','magias',
             'armadilhas','cartas_compradas','lp','fusoes','equipamentos')
BANDS = [RANK_RULES[key] for key in RULE_KEYS]

cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
cpu.mem_map(0, 0x200000)


def write(pc, data):
    cpu.mem_write(pc & 0x1FFFFFFF, data)


write(RUNTIME_RANK_HUD_BASE, RUNTIME_RANK_HUD)
write(RULES, b''.join(struct.pack('<hh', threshold or 32767, points)
                      for row in BANDS for threshold, points in row))
write(0x800E9D94, struct.pack('<I', TABLE))
write(PANEL + 0x14, b'\x02\x00\x00\x01')
write(PANEL + 0x30, struct.pack('<hh', 280, 32))
write(SPRITE + 8, struct.pack('<hh', 8, 8))
for address in (NUMBERS, SCORER, SPRITES):
    write(address, struct.pack('<II', 0x03E00008, 0))  # jr ra, nop

digits, glyphs = [], []


def callback(_cpu, address, _size, _data):
    a0, a1, a2, a3 = (cpu.reg_read(reg) for reg in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
    if address == NUMBERS:
        digits.append((a0, a1, a2, a3))
    elif address == SCORER:
        if a1 >= 0x80000000:
            a1 -= 0x100000000
        points = next(points for maximum, points in BANDS[a0] if maximum is None or a1 < maximum)
        cpu.reg_write(UC_MIPS_REG_V0, points & 0xFFFFFFFF)
    elif address == SPRITES:
        assert (a0, a1, a2) == (SPRITE, TABLE, 2)
        raw = cpu.mem_read(a0 & 0x1FFFFFFF, 24)
        attr, x, y, w, h, page, u, v, cx, cy, rgb = struct.unpack('<IhhhhhBBhhI', raw)
        assert (attr, y, w, h, page, cx, cy, rgb) == (0x08000000, 55, 8, 8, 0xB, 0x290, 0xFA, 0x808080)
        glyphs.append((x, GLYPHS[(v << 1) | ((u - 0x80) >> 3)]))


for address in (NUMBERS, SCORER, SPRITES):
    cpu.hook_add(UC_HOOK_CODE, callback, begin=address, end=address)


def frame(*, lp=20000, stats=b'\0' * 10, drawn=5, opponent=1):
    digits.clear()
    glyphs.clear()
    write(OPPONENT, struct.pack('<b', opponent))
    write(PLAYER, stats)
    write(PLAYER + 0x14, struct.pack('<h', lp))
    write(PLAYER + 0x18, bytes([drawn]))
    for reg, value in ((UC_MIPS_REG_A0, PANEL), (UC_MIPS_REG_A1, SPRITE), (UC_MIPS_REG_A2, 40 - drawn),
                       (UC_MIPS_REG_A3, 2), (UC_MIPS_REG_SP, 0x801FF000), (UC_MIPS_REG_GP, 0x8009AF08),
                       (UC_MIPS_REG_RA, RETURN)):
        cpu.reg_write(reg, value)
    cpu.emu_start(ENTRY_POINTS['DrawLiveRank'], RETURN, count=4000)
    assert digits == [(PANEL, SPRITE, 40 - drawn, 2)]
    return ''.join(dict(glyphs).get(x, ' ') for x in range(245, 309, 8))


assert frame() == 'S-POW 99'
assert frame(lp=700) == 'S-POW 90'
assert frame(lp=700, stats=bytes([0, 1, 0, 0, 0, 1, 0, 0, 0, 0])) == 'A-POW 84'
assert frame(lp=20000, stats=bytes([216, 1, 0, 0, 0, 1, 0, 0, 0, 0])) == 'D-POW 53'
assert frame(lp=0, stats=bytes([216]) + b'\0' * 9, drawn=39) == 'B-TEC 24'
assert frame(lp=0, stats=bytes([216, 33, 20, 15, 31, 10, 7, 0, 15, 15]), drawn=39) == 'S-TEC 00'
assert not frame(opponent=-1).strip()
write(RULES + 16, b'\0\0')
assert not frame().strip()
print('MIPS: rank muda com LP, magia, compra e desfecho; deck original e modo 2P conferidos.')
