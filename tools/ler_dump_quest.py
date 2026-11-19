"""Read the mode-2 quest crash dump from an ePSXe save state (or a raw RAM dump).

Usage: python tools/ler_dump_quest.py <save state or RAM file> [--words N]

The catcher stores r2..r31 at 0x801AAD00 + 4*r and EPC/Cause/SR/BadVAddr/HI/LO
at +0x80..+0x94, then writes the magic 0x51444247 at 0x801AAD00. ePSXe save
states are gzip-compressed and contain the 2 MiB main RAM; the RAM base is found
from the magic, so no knowledge of the save-state header is needed.
"""
from __future__ import annotations

import argparse
import gzip
import struct
import sys
from pathlib import Path

DUMP = 0x801AAD00
MAGIC = 0x51444247
RAM_SIZE = 0x200000
NAMES = ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3', 't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
         's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra']
EXTRA = ['EPC', 'Cause', 'SR', 'BadVAddr', 'HI', 'LO']


def load(path: Path) -> bytes:
    data = path.read_bytes()
    try:
        return gzip.decompress(data)
    except OSError:
        return data


def find_ram(blob: bytes) -> int:
    needle = struct.pack('<I', MAGIC)
    at = blob.find(needle)
    while at >= 0:
        base = at - (DUMP & 0x1FFFFF)
        if base >= 0 and base + RAM_SIZE <= len(blob):
            sp = struct.unpack_from('<I', blob, at + 4 * 29)[0]
            if 0x80000000 <= sp < 0x80200000:
                return base
        at = blob.find(needle, at + 1)
    raise SystemExit('Magic do diagnóstico não encontrado: o pegador não foi executado neste arquivo.')


def word(ram: bytes, address: int) -> int:
    return struct.unpack_from('<I', ram, address & 0x1FFFFF)[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--words', type=int, default=48, help='palavras da pilha a exibir')
    args = parser.parse_args(argv)
    blob = load(args.file)
    base = find_ram(blob)
    ram = blob[base:base + RAM_SIZE]
    print(f'RAM encontrada no deslocamento 0x{base:X} do arquivo.')
    regs = {name: word(ram, DUMP + 4 * index) for index, name in enumerate(NAMES) if index >= 2}
    regs.update({name: word(ram, DUMP + 0x80 + 4 * index) for index, name in enumerate(EXTRA)})
    for name, value in regs.items():
        print(f'{name:>8} = 0x{value:08X}')
    cause = regs['Cause']
    print(f'Cause.ExcCode = {(cause >> 2) & 31}  Cause.BD = {cause >> 31}  IP = 0x{(cause >> 8) & 0xFF:02X}')
    sp = regs['sp']
    print(f'\nPilha a partir de sp = 0x{sp:08X}:')
    for index in range(args.words):
        address = sp + 4 * index
        value = word(ram, address)
        hint = ' <- código?' if 0x80010000 <= value < 0x801FFFFF and value & 3 == 0 else ''
        print(f'  0x{address:08X}: 0x{value:08X}{hint}')
    out = args.file.with_suffix(args.file.suffix + '.ram.bin')
    out.write_bytes(ram)
    print(f'\nRAM completa salva em {out}')


if __name__ == '__main__':
    sys.exit(main())
