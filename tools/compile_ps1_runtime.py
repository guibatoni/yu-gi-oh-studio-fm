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
    'DealConfiguredDecks', 'RetailCardDrop', 'InsertTierName', 'EndTierName',
    'SortTierGlyph', 'SortTierPolygon', 'CheckEditedFusion', 'summon_damage', 'protection',
    'DeckAllowsCopies', 'DrawLiveRank', 'ResetCardsWithMarkers', 'FieldActionsWithMarkers',
    'CreateMarkedPlacement', 'ConsumeFusionMaterial',
)
FLAGS = ('-march=r3000', '-mabi=32', '-msoft-float', '-mno-abicalls', '-fno-pic',
         '-G0', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
         '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-fno-jump-tables',
         '-fno-toplevel-reorder', '-fno-inline', '-Oz')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='mipsel-linux-gnu-gcc')
    parser.add_argument('--prefix', default='mipsel-linux-gnu-')
    parser.add_argument('--expanded', action='store_true', help='Compile the save-compatible 740-card variant')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        objects = []
        flags = (*FLAGS, *(('-DFM_EXPANDED', '-DFM_CARD_CAPACITY=740', '-DFM_LEVEL_ADDRESS=0x801BFD18')
                          if args.expanded else ()))
        inputs = [SOURCES / 'runtime.c', SOURCES / 'hooks.S', SOURCES / 'rank_hud.c']
        if args.expanded:
            inputs.append(SOURCES / 'expansion.S')
        for src in inputs:
            obj = work / (src.stem + '.o')
            subprocess.run([args.cc, *flags, '-c', str(src), '-o', str(obj)], check=True)
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
        password = section_bytes('.runtime_password')
        mod = section_bytes('.runtime_mod')
        rank_hud = section_bytes('.runtime_rank_hud')
        markers = section_bytes('.runtime_markers')
        grave_filters = section_bytes('.runtime_grave_filters')
        expansion = section_bytes('.runtime_expansion') if args.expanded else b''
        expansion_aux = section_bytes('.runtime_expansion_aux') if args.expanded else b''

    pieces = ['"""Gerado por tools/compile_ps1_runtime.py a partir de tools/ps1."""\n',
              f'RUNTIME_SHA256 = {hashlib.sha256(content).hexdigest()!r}',
              f'RUNTIME_BASE = 0x{symbols["__runtime_start"]:08X}',
              f'RUNTIME_END = 0x{symbols["__runtime_end"]:08X}', 'ENTRY_POINTS = {']
    names = (*ENTRIES, *(('ExpandedTransfer', 'ExpandedModel', 'ExpandedEffect', 'ExpandedSeen',
                         'MapNewCard', 'OriginalEffect', 'AttackTrapId', 'SpellTrapId', 'FakeTrapId',
                         'EquipBonusId', 'EquipAnimationId', 'EquipSwordId', 'EquipSecondAnimationId') if args.expanded else ()))
    for name in names:
        pieces.append(f'    {name!r}: 0x{symbols[name]:08X},')
    pieces.extend(('}', 'RUNTIME = bytes.fromhex("""'))
    pieces.extend(content[i:i+32].hex(' ') for i in range(0, len(content), 32))
    sections = [('RUNTIME_EXT', extension, '__runtime_ext'),
                                  ('RUNTIME_PASSWORD', password, '__password'),
                                  ('RUNTIME_MOD', mod, '__runtime_mod'),
                                  ('RUNTIME_RANK_HUD', rank_hud, '__rank_hud'),
                                  ('RUNTIME_MARKERS', markers, '__markers'),
                                  ('RUNTIME_GRAVE_FILTERS', grave_filters, '__grave_filters')]
    if args.expanded:
        sections.extend((('RUNTIME_EXPANSION', expansion, '__expansion'),
                         ('RUNTIME_EXPANSION_AUX', expansion_aux, '__expansion_aux')))
    for label, binary, symbol in sections:
        pieces.extend(('""")', '',
                       f'{label}_SHA256 = {hashlib.sha256(binary).hexdigest()!r}',
                       f'{label}_BASE = 0x{symbols[symbol + "_start"]:08X}',
                       f'{label}_END = 0x{symbols[symbol + "_end"]:08X}',
                       f'{label} = bytes.fromhex("""'))
        pieces.extend(binary[i:i+32].hex(' ') for i in range(0, len(binary), 32))
    pieces.append('""")\n')
    output = OUTPUT.with_name('ps1_expanded_runtime_blob.py') if args.expanded else OUTPUT
    output.write_text('\n'.join(pieces), encoding='utf-8', newline='\n')
    print(f'{len(content)} bytes de código, reserva até 0x{symbols["__runtime_end"]:08X}')


if __name__ == '__main__':
    main()
