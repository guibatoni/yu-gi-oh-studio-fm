"""Test native chest/save routines from a user-supplied expanded BIN/CUE.

Usage: PYTHONPATH=. python tools/verify_expanded_bau_mips.py GAME.bin
Requires Unicorn. Loads only isolated RAM; never writes to the image.
Graphics/audio callbacks are stubbed. This is not a complete emulator test.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import struct


def verify(image):
    from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
    from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3,
                                    UC_MIPS_REG_GP, UC_MIPS_REG_PC, UC_MIPS_REG_RA,
                                    UC_MIPS_REG_S1, UC_MIPS_REG_SP, UC_MIPS_REG_V0)
    from fmstudio.disc import DiscReader
    from fmstudio.ps1_expansion import WORKSPACE_SIZE, LIST_SIZE, LIST_GROWTH, inspect_expansion

    with DiscReader(image) as reader:
        entry = next(e for e in reader.files() if e.path.upper() == 'SLUS_014.11')
        exe = b''.join(reader.read_entry(entry))
    if inspect_expansion(exe)['status'] != 'aplicado':
        raise ValueError('Use uma cópia expandida #723–#740 gerada pelo Studio.')
    cpu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
    cpu.mem_map(0, 0x200000)
    cpu.mem_map(0x1F800000, 0x1000)
    cpu.mem_write(0x10000, exe[0x800:])

    def write(address, value):
        cpu.mem_write(address & 0x1FFFFFFF, value)

    def read(address, size):
        return bytes(cpu.mem_read(address & 0x1FFFFFFF, size))

    def store(address, fmt, *values):
        write(address, struct.pack(fmt, *values))

    def value(address, fmt='<I'):
        return struct.unpack(fmt, read(address, struct.calcsize(fmt)))[0]

    # Retain native array population, comparison, qsort, count, copy and CRC
    # code. Only the screen/audio services are outside this test's scope.
    for pc in (0x80032328, 0x80032370, 0x8003FF08, 0x8004002C, 0x800404CC, 0x800428EC):
        store(pc, '<II', 0x03E00008, 0)
    store(0x800400AC, '<4I', 0x3C028012, 0x34424000, 0x03E00008, 0)
    stop, returned = 0x80123000, 0x80123000

    def monitor(uc, pc, size, _):
        if pc == stop:
            uc.emu_stop()

    cpu.hook_add(UC_HOOK_CODE, monitor)

    def call(pc, *args, finish=returned):
        nonlocal stop
        stop = finish
        for reg, item in zip((UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3), args):
            cpu.reg_write(reg, item & 0xFFFFFFFF)
        cpu.reg_write(UC_MIPS_REG_SP, 0x801FF000)
        cpu.reg_write(UC_MIPS_REG_GP, 0x8009AF08)
        cpu.reg_write(UC_MIPS_REG_RA, returned)
        cpu.emu_start(pc, 0, count=6_000_000)
        assert cpu.reg_read(UC_MIPS_REG_PC) == stop, f'Rotina 0x{pc:08X} não retornou.'
        return cpu.reg_read(UC_MIPS_REG_V0)

    # Probe the last capacity slot even when that slot is not yet a real
    # project card. Its RAM-only quantities do not grant a game collection.
    state, save, other = 0x80100000, 0x801D0200, 0x801D1000
    write(save, bytes(0x680))
    store(save, '<40H', *range(1, 39), 723, 740)
    write(save + 0x50 + 722, b'\x03')
    write(save + 0x50 + 739, b'\x02')
    store(save + 0x334, '<I', 0x12345678)
    write(other, read(save, 0x680))
    write(state, b'\xA5' * (2 * WORKSPACE_SIZE))
    guard = state + 2 * WORKSPACE_SIZE
    write(guard, b'GUARD123')
    call(0x800323F8, state, save, other, 0)
    assert read(guard, 8) == b'GUARD123'
    for base in (state, state + WORKSPACE_SIZE):
        chest, deck = base + 4, base + 4 + LIST_SIZE
        assert value(chest + 0x2D40 + LIST_GROWTH, '<h') == 740
        assert value(chest + 0x2D42 + LIST_GROWTH, '<h') == 740
        assert read(base + 0x606A + 612, 1) == b'\0'
        assert {value(chest + 16 * i + 4, '<H') for i in range(740)} == set(range(1, 741))
        assert set(struct.unpack('<40H', read(save, 80))) == {
            value(deck + 16 * i + 4, '<H') for i in range(40)}
        for mode in range(1, 8):
            write(chest + 0x2D45 + LIST_GROWTH, bytes((mode,)))
            call(0x80032C48, chest)
            assert {value(chest + 16 * i + 4, '<H') for i in range(740)} == set(range(1, 741))
    quantity = state + 0x5D97 + 594
    write(quantity + 740, b'\x07')
    cpu.reg_write(UC_MIPS_REG_S1, state)
    call(0x80033B60, quantity + 1, finish=0x80033BD4)
    assert read(save + 0x50 + 739, 1) == b'\x07'
    assert value(save + 0x334) == 0x12345678
    assert 740 in struct.unpack('<40H', read(save, 80))
    call(0x80021894, 740)
    assert read(save + 0x50 + 739, 1) == b'\x08'
    call(0x8003D03C, 0x801D0000)
    assert read(save, 0x680) == read(0x801D0880, 0x680)
    assert call(0x8003D174, save) == 1
    write(save + 0x50 + 739, b'\x09')
    assert call(0x8003D174, save) == 0
    assert read(guard, 8) == b'GUARD123'
    print('740 linhas, dois painéis, sete ordenações, deck, quantidades e checksums: OK.')
    print('Execução em RAM isolada; o BIN/CUE não foi modificado. Teste completo no ePSXe pendente.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    verify(parser.parse_args().image)
