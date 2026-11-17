"""Execute the PS1 copy gate against the same rules compiled for BIN/CUE."""
from types import SimpleNamespace

from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_RA, UC_MIPS_REG_SP, UC_MIPS_REG_V0

from fmstudio.ps1_runtime import CONFIG_ADDRESS, compile_effects
from fmstudio.ps1_runtime_blob import ENTRY_POINTS, RUNTIME, RUNTIME_BASE

cards = {cid: {'tipo_id': 0} for cid in (1, 2, 3, 17)}
project = SimpleNamespace(cards=cards, get=cards.__getitem__, metadata={}, effects={
    str(cid): [{'evento': 'regra_deck', 'acao': 'limite_copias_deck', 'alvo': 'proprio', 'valor': limit}]
    for cid, limit in ((1, 0), (2, 1))
})
plan = compile_effects(project, True)
cpu = Uc(UC_ARCH_MIPS, UC_MODE_LITTLE_ENDIAN | UC_MODE_MIPS32)
cpu.mem_map(0, 0x200000)
cpu.mem_write(RUNTIME_BASE & 0x1FFFFFFF, RUNTIME)
cpu.mem_write(CONFIG_ADDRESS & 0x1FFFFFFF, plan.data)


def allows(cid, copies):
    end = 0x80010000
    for register, value in ((UC_MIPS_REG_A0, cid), (UC_MIPS_REG_A1, copies),
                            (UC_MIPS_REG_RA, end), (UC_MIPS_REG_SP, 0x801FF000)):
        cpu.reg_write(register, value)
    cpu.emu_start(ENTRY_POINTS['DeckAllowsCopies'], end, count=300)
    return bool(cpu.reg_read(UC_MIPS_REG_V0))


assert not allows(1, 0)
assert allows(2, 0) and not allows(2, 1)
assert allows(3, 2) and not allows(3, 3)
assert allows(17, 0) and not allows(17, 1)
print('MIPS: carta banida, limite individual 1, padrão 3 e peça de Exodia.')
