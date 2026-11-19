"""Compile the PS1 quest overlay and relocatable loaders with Zig 0.13."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / 'tools' / 'ps1'
OUTPUT = ROOT / 'fmstudio' / 'ps1_campaign_quest_overlay_blob.py'
BASE = 0x801A9010


def quest_sections(elf):
    if elf[:6] != b'\x7fELF\x01\x01':
        raise ValueError('Esperado ELF32 little endian.')
    header = struct.unpack_from('<HHIIIIIHHHHHH', elf, 16)
    offset, stride, count, names = header[5], header[10], header[11], header[12]
    sections = [struct.unpack_from('<10I', elf, offset + i * stride) for i in range(count)]
    name_offset = sections[names][4]
    values = {}
    for name, _, _, address, start, size, *_ in sections:
        label = elf[name_offset + name:].split(b'\0', 1)[0]
        if label.startswith(b'.quest'):
            values[label.decode('ascii')] = (address, elf[start:start + size])
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zig', default='zig')
    parser.add_argument('--nm', default='nm')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        asm, obj, adapter, executable = (Path(folder) / name for name in
                                          ('quests.s', 'quests.o', 'loader.o', 'quests.elf'))
        cc = [args.zig, 'cc', '-target', 'mipsel-freestanding', '-march=mips1',
              '-msoft-float', '-mno-abicalls', '-fno-pic', '-G0']
        subprocess.run([*cc, '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
                        '-fno-unwind-tables', '-fno-jump-tables', '-Os',
                        '-S', str(SOURCES / 'campaign_quests.c'), '-o', str(asm)], check=True)
        # The retail text VM keeps its global-data base live across all calls.
        if re.search(r'\$(?:gp|28)\b', asm.read_text(encoding='utf-8')):
            raise ValueError('O código das quests deve preservar o registrador global do PS1 ($gp).')
        subprocess.run([*cc, '-c', str(asm), '-o', str(obj)], check=True)
        subprocess.run([*cc, '-c', str(SOURCES / 'campaign_quest_loader.S'),
                        '-o', str(adapter)], check=True)
        subprocess.run([args.zig, 'ld.lld', '-m', 'elf32ltsmip', '-T', str(SOURCES / 'campaign_quests.ld'),
                        str(obj), str(adapter), '-o', str(executable)], check=True)
        names = {name: int(addr, 16) for addr, _, name in (line.split() for line in
                 subprocess.check_output([args.nm, '-n', '--defined-only', str(executable)],
                                         text=True).splitlines())}
        sections = quest_sections(executable.read_bytes())
    address, payload = sections['.quest']
    duel_at, duel = sections['.quest_before']
    answer_at, answer = sections['.quest_answer']
    shop_at, shop = sections['.quest_shop']
    if (address != BASE or names['QuestConfiguration'] != BASE + len(payload)
            or names['QuestDuelLoader'] != duel_at or names['QuestAnswerLoader'] != answer_at
            or names['QuestShopLoader'] != shop_at):
        raise ValueError('Endereços do código MIPS divergentes.')
    header = ['"""Gerado por tools/compile_ps1_campaign_quests.py."""',
              f'BASE = 0x{BASE:08X}', f'SIZE = {len(payload)}',
              f'SHA256 = {hashlib.sha256(payload).hexdigest()!r}', 'ENTRY_POINTS = {']
    header.extend(f'    {name!r}: 0x{names[name]:08X},' for name in
                  ('QuestBeforeDuel', 'QuestAnswer', 'QuestResumeShop', 'QuestCountMissing',
                   'QuestConfiguration'))
    header.append('}')
    for name, data in (('DUEL_LOADER', duel), ('ANSWER_LOADER', answer), ('SHOP_LOADER', shop),
                       ('PAYLOAD', payload.rstrip(b'\0'))):
        header += [f'{name} = bytes.fromhex("""']
        header.extend(data[i:i + 32].hex(' ') for i in range(0, len(data), 32))
        header += ['""")' + (".ljust(SIZE, b'\\0')" if name == 'PAYLOAD' else '')]
    OUTPUT.write_text('\n'.join(header) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
