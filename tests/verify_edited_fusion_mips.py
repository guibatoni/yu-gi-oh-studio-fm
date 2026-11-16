"""Run the patched player and AI call sites with synthetic PS1 memory."""
import hashlib
import struct
from types import SimpleNamespace
from unittest.mock import patch

from unicorn import Uc, UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_V0

from fmstudio.ps1_mod import compile_mod
from fmstudio.ps1_runtime import (
    CONFIG_ADDRESS, FUSION_CALLERS, RETAIL_FUSION, _jump, compile_effects, install_runtime, verify_effects,
)
from fmstudio.ps1_runtime_blob import RUNTIME_BASE, RUNTIME_END
from fmstudio.tables import EXE_DELTA

cards = {cid: {'tipo_id': 1 if cid in (16, 500) else 9}
         for cid in (10, 16, 56, 69, 72, 500, 721, 722)}
project = SimpleNamespace(cards=cards, get=cards.__getitem__, effects={}, metadata={
    'edicao_mod': {'receitas': {'fusoes': {'56,16': 72, '722,500': 721}}},
})
mod = compile_mod(project, profile=True, wa_verified=False)
# Exercise a fusion-only payload, with no native deck or tier hooks.
runtime_project = SimpleNamespace(metadata=project.metadata, effects={})
plan = compile_effects(runtime_project, True, fusions=mod.fusions)
source = bytearray(0x1D0000)
for start, _ in FUSION_CALLERS:
    struct.pack_into('<II', source, start - EXE_DELTA, _jump(RETAIL_FUSION, link=True), 0)
original = bytes(source)
with patch('fmstudio.ps1_runtime.SOURCE_SHA256', hashlib.sha256(original).hexdigest()):
    exe, _ = install_runtime(original, original, plan, description_icons=False)
assert verify_effects(exe, plan, original=original)['status'] == 'aplicado'

cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
cpu.mem_map(0, 0x200000)
for start, end in ((RUNTIME_BASE, RUNTIME_END), (CONFIG_ADDRESS, CONFIG_ADDRESS + len(plan.data))):
    cpu.mem_write(start & 0x1FFFFFFF, exe[start-EXE_DELTA:end-EXE_DELTA])
for start, _ in FUSION_CALLERS:
    cpu.mem_write(start & 0x1FFFFFFF, exe[start-EXE_DELTA:start-EXE_DELTA+8])

fallback = []
def stock(uc, *_):
    materials = (uc.reg_read(UC_MIPS_REG_A0), uc.reg_read(UC_MIPS_REG_A1))
    fallback.append(materials)
    uc.reg_write(UC_MIPS_REG_V0, 69 if set(materials) == {10, 16} else 0)

cpu.mem_write(RETAIL_FUSION & 0x1FFFFFFF, struct.pack('<II', 0x03E00008, 0))
cpu.hook_add(UC_HOOK_CODE, stock, begin=RETAIL_FUSION, end=RETAIL_FUSION)
for start, _ in FUSION_CALLERS:
    for a, b, expected in ((16, 56, 72), (56, 16, 72), (722, 500, 721),
                           (16, 10, 69), (10, 16, 69), (16, 57, 0)):
        cpu.reg_write(UC_MIPS_REG_A0, a)
        cpu.reg_write(UC_MIPS_REG_A1, b)
        cpu.emu_start(start, start + 8, timeout=1_000_000, count=10_000)
        assert cpu.reg_read(UC_MIPS_REG_V0) == expected, (hex(start), a, b, expected)
assert fallback == [(16, 10), (10, 16), (16, 57)] * len(FUSION_CALLERS)
print('MIPS: #016 + #056 → #072 nas duas ordens, jogador, IA e receitas originais verificadas.')
