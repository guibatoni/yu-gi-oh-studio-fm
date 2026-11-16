"""Compile the PS1 runtime blob with GNU mipsel-linux-gnu GCC and binutils.

The emitted Python module keeps updates and export self-contained on Windows.
The runtime is freestanding MIPS I (R3000A) and links at its reserved RAM base.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / 'tools' / 'ps1'
OUTPUT = ROOT / 'fmstudio' / 'ps1_runtime_blob.py'
ENTRIES = (
    'CalculateStats', 'ResetCards', 'Startup', 'DrawPhase', 'RemoveCard',
    'AttackTrap', 'Battle', 'Resume', 'BoardDestruction', 'MonsterRemoval',
    'StopDefense', 'Raigeki', 'Reveal', 'StatPenalty', 'Swords',
    'FieldActions', 'Placement', 'ConfirmPlacement', 'DeckCopyGate',
    'DescriptionIcon', 'SpellUsed', 'CollectTargets', 'SelectDeckDrop', 'UpdatePasswordShop',
)
FLAGS = ('-march=r3000', '-mabi=32', '-msoft-float', '-mno-abicalls', '-fno-pic',
         '-G0', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
         '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-fno-jump-tables',
         '-fno-toplevel-reorder', '-fno-inline', '-Oz')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='mipsel-linux-gnu-gcc')
    parser.add_argument('--prefix', default='mipsel-linux-gnu-')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        objects = []
        for src in (SOURCES / 'runtime.c', SOURCES / 'hooks.S'):
            obj = work / (src.stem + '.o')
            subprocess.run([args.cc, *FLAGS, '-c', str(src), '-o', str(obj)], check=True)
            objects.append(obj)
        elf = work / 'runtime.elf'
        subprocess.run([args.prefix + 'ld', '-T', str(SOURCES / 'runtime.ld'),
                        '-o', str(elf), *map(str, objects)], check=True)
        info = subprocess.check_output([args.prefix + 'nm', '-n', str(elf)], text=True)
        symbols = {name: int(address, 16) for address, _, name in
                   (line.split() for line in info.splitlines())}
        def section_bytes(section):
            raw = work / f'{section}.bin'
            subprocess.run([args.prefix + 'objcopy', '-O', 'binary', '-j', section,
                            str(elf), str(raw)], check=True)
            return raw.read_bytes()

        content = section_bytes('.runtime')
        extension = section_bytes('.runtime_ext')

    pieces = ['"""Gerado por tools/compile_ps1_runtime.py a partir de tools/ps1."""\n',
              f'RUNTIME_SHA256 = {hashlib.sha256(content).hexdigest()!r}',
              f'RUNTIME_BASE = 0x{symbols["__runtime_start"]:08X}',
              f'RUNTIME_END = 0x{symbols["__runtime_end"]:08X}', 'ENTRY_POINTS = {']
    for name in ENTRIES:
        pieces.append(f'    {name!r}: 0x{symbols[name]:08X},')
    pieces.extend(('}', 'RUNTIME = bytes.fromhex("""'))
    pieces.extend(content[i:i+32].hex(' ') for i in range(0, len(content), 32))
    pieces.extend(('""")', '',
                   f'RUNTIME_EXT_SHA256 = {hashlib.sha256(extension).hexdigest()!r}',
                   f'RUNTIME_EXT_BASE = 0x{symbols["__runtime_ext_start"]:08X}',
                   f'RUNTIME_EXT_END = 0x{symbols["__runtime_ext_end"]:08X}',
                   'RUNTIME_EXT = bytes.fromhex("""'))
    pieces.extend(extension[i:i+32].hex(' ') for i in range(0, len(extension), 32))
    pieces.append('""")\n')
    OUTPUT.write_text('\n'.join(pieces), encoding='utf-8', newline='\n')
    print(f'{len(content)} bytes de código, reserva até 0x{symbols["__runtime_end"]:08X}')


if __name__ == '__main__':
    main()
