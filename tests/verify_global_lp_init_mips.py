"""Executa rotina real de LP do Drop x15 no Unicorn MIPS para dois duelistas.

O teste usa RAM sintética, sem ler ou modificar discos do usuário.
"""
import struct
from types import SimpleNamespace

from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
from unicorn.mips_const import UC_MIPS_REG_GP, UC_MIPS_REG_RA, UC_MIPS_REG_SP

from fmstudio.ps1_mod import LP_CODE, LP_TABLE, _LP_WORDS, _LP_INIT, compile_mod


def physical(address):
    return address & 0x1FFFFFFF


cards = {1: {'tipo_id': 0}}
project = SimpleNamespace(cards=cards, get=cards.__getitem__, metadata={
    'edicao_mod': {'lp_inicial': 20000, 'duelistas': {'1': {'lp': 8000}}}})
plan = compile_mod(project, profile=True, wa_verified=False)
assert plan.player_lp == 20000
assert all(value == 20000 for value in plan.life)
retail = 0x80000000 | ((_LP_INIT & 0x03FFFFFF) << 2)


def run_init(opponent):
    cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
    cpu.mem_map(0, 0x200000)
    cpu.mem_write(physical(LP_CODE), struct.pack(f'<{len(_LP_WORDS)}I', *_LP_WORDS))
    cpu.mem_write(physical(LP_TABLE),
                  struct.pack(f'<{len(plan.life)+1}H', plan.player_lp, *plan.life))
    # Função original substituída por retorno direto: verificamos apenas o hook LP.
    cpu.mem_write(physical(retail), struct.pack('<II', 0x03E00008, 0))
    cpu.mem_write(physical(0x8009B361), bytes([opponent]))
    cpu.reg_write(UC_MIPS_REG_GP, 0x8009AF08)
    cpu.reg_write(UC_MIPS_REG_SP, 0x801FF000)
    cpu.reg_write(UC_MIPS_REG_RA, 0x80010000)
    cpu.emu_start(LP_CODE, 0x80010000, count=20000, timeout=1_000_000)
    return tuple(struct.unpack('<H', cpu.mem_read(physical(0x800E9FF0+offset), 2))[0]
                 for offset in (0x14, 0x16, 0x34, 0x36))


for opponent in (1, 2, 39):
    actual = run_init(opponent)
    assert actual == (20000, 20000, 20000, 20000), (opponent, actual)
print('MIPS: ambos os duelistas iniciam com 20000 LP e teto 20000 em 1, 2 e 39.')
