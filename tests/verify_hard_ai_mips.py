"""Compara fluxo MIPS de decisões aleatórias retail e Difícil via Unicorn.

Os originais executam branch para pular uma busca. O patch executa NOP,
logo deixa seguir para a busca. Isso testa execução, não só comparação textual.
"""
import struct

from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_V0

from fmstudio.ps1_ai import HARD_AI_PATCHES


def path(pc, word, v0):
    cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
    cpu.mem_map(0, 0x200000)
    cpu.mem_write(pc & 0x1FFFFFFF, struct.pack('<4I', word, 0, 0, 0))
    seen = []

    def observe(uc, addr, size, data):
        seen.append(addr)
        if len(seen) == 3:
            uc.emu_stop()

    cpu.hook_add(UC_HOOK_CODE, observe)
    cpu.reg_write(UC_MIPS_REG_V0, v0)
    cpu.emu_start(pc, 0x80100000, count=3, timeout=1_000_000)
    assert len(seen) == 3, (hex(pc), seen)
    return seen


for pc, original, improved, caption in HARD_AI_PATCHES:
    # beq zero -> v0=0, bne zero -> v0=1.
    v0 = 0 if (original >> 26) == 4 else 1
    stock = path(pc, original, v0)
    hard = path(pc, improved, v0)
    displacement = original & 0xFFFF
    if displacement & 0x8000:
        displacement -= 0x10000
    target = pc + 4 + 4 * displacement
    assert stock == [pc, pc+4, target], (caption, stock)
    assert hard == [pc, pc+4, pc+8], (caption, hard)
    print(f'IA Difícil 0x{pc:08X}: branch retail -> 0x{target:08X}; patch -> 0x{pc+8:08X}: OK')

print('MIPS: 5/5 buscas estratégicas deixaram de ser descartadas aleatoriamente.')
