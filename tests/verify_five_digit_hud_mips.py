"""Execute instruções reais do contador LP com Unicorn (R3000A, little endian).

Duas chamadas recebem a largura 5 e origem 8px mais à esquerda;
os dois contadores do deck continuam com largura 2.
"""
import struct

from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
from unicorn.mips_const import UC_MIPS_REG_A3, UC_MIPS_REG_V0

from fmstudio.ps1_lp_hud import LP_HUD_PATCHES, DECK_COUNT_WORDS

for side, offset in (('oponente', 0), ('jogador', 2)):
    group = LP_HUD_PATCHES[offset:offset+2]
    assert len(group) == 2
    orig = (group[0][1], group[1][1])
    wide = (group[0][2], group[1][2])
    for name, words, expected_width, expected_x in (
            ('original', orig, 4, 277),
            ('cinco digitos', wide, 5, 269)):
        cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(0, 0x200000)
        cpu.mem_write(0x10000, struct.pack('<2I', *words))
        cpu.reg_write(UC_MIPS_REG_V0, 280)
        cpu.emu_start(0x10000, 0x10008, count=2, timeout=1000000)
        count = cpu.reg_read(UC_MIPS_REG_A3)
        x = cpu.reg_read(UC_MIPS_REG_V0)
        assert (count, x) == (expected_width, expected_x), (
            side, name, count, x)
    print(f'{side}: largura 4 -> 5 e origem 277 -> 269 pixels (MIPS OK)')
for _, word in DECK_COUNT_WORDS:
    assert word == 0x24070002
print('Contadores do deck preservados em dois algarismos.')
