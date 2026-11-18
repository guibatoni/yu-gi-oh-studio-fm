"""Append one verified Form1 ISO file without moving XA or movie extents."""
from __future__ import annotations
import struct

from .core import ModError
from .disc import DiscReader, SYNC
from .disc_build import RAW_SECTOR, PAYLOAD, regenerate_form1


def append_iso_file(stream, entry, original, replacement):
    if len(original) != entry.size or len(replacement) <= len(original):
        raise ModError('A anexação exige o arquivo original completo e uma substituição maior.')
    stream.seek(0, 2)
    size = stream.tell()
    if size % RAW_SECTOR:
        raise ModError('BIN não termina em um setor físico completo.')
    extent = size // RAW_SECTOR
    count = (len(replacement) + PAYLOAD - 1) // PAYLOAD
    if extent + count > 360000:
        raise ModError('A cópia expandida ultrapassaria os 80 minutos de um CD de dados.')

    def sector(lba):
        stream.seek(lba * RAW_SECTOR)
        data = stream.read(RAW_SECTOR)
        if (len(data) != RAW_SECTOR or data[:12] != SYNC or data[15] != 2
                or data[18] & 0x20 or data[16:20] != data[20:24]):
            raise ModError(f'Expansão: setor {lba} não é Mode2 Form1.')
        return data

    volume = sector(16)[24:2072]
    root_extent, root_size = struct.unpack_from('<I', volume, 158)[0], struct.unpack_from('<I', volume, 166)[0]
    directory, directory_size = root_extent, root_size
    parts = entry.path.upper().split('/')
    target = None
    for part in parts:
        found = None
        for j in range((directory_size + 2047) // 2048):
            raw = sector(directory + j)[24:2072]
            pos = 0
            while pos < 2048 and raw[pos]:
                length = raw[pos]
                if pos + length > 2048:
                    raise ModError('Registro ISO9660 inválido durante a expansão.')
                record = raw[pos:pos + length]
                parsed = DiscReader.parse_entry(record, '')
                if parsed and parsed.path.upper() == part:
                    if found is not None:
                        raise ModError('Registro ISO9660 duplicado; expansão recusada.')
                    found = (directory + j, pos, parsed)
                pos += length
        if found is None:
            raise ModError(f'Registro ISO9660 não encontrado: {entry.path}.')
        target = found
        directory, directory_size = found[2].extent, found[2].size
    lba, pos, actual = target
    if actual.is_dir or actual.extent != entry.extent or actual.size != entry.size:
        raise ModError('O diretório ISO9660 diverge do arquivo de origem.')
    # Compare before appending; never trust an extent alone.
    for i in range((len(original) + 2047) // 2048):
        expected = original[i * 2048:(i + 1) * 2048]
        if sector(entry.extent + i)[24:24 + len(expected)] != expected:
            raise ModError('Os bytes originais do arquivo ISO divergiram.')
    template = bytearray(sector(entry.extent))
    template[18] = template[22] = 8  # Data, without inherited EOF/EOR bits.
    changed = []
    for i in range(count):
        raw = bytearray(template)
        frames = extent + i + 150
        minute, rest = divmod(frames, 75 * 60)
        second, frame = divmod(rest, 75)
        raw[12:15] = bytes((value // 10 * 16 + value % 10 for value in (minute, second, frame)))
        payload = replacement[i * 2048:(i + 1) * 2048]
        raw[24:2072] = payload.ljust(2048, b'\0')
        stream.seek((extent + i) * RAW_SECTOR)
        stream.write(regenerate_form1(bytes(raw)))
        changed.append(extent + i)
    raw = bytearray(sector(lba))
    for offset, value in ((2, extent), (10, len(replacement))):
        struct.pack_into('<I', raw, 24 + pos + offset, value)
        struct.pack_into('>I', raw, 24 + pos + offset + 4, value)
    stream.seek(lba * RAW_SECTOR)
    stream.write(regenerate_form1(bytes(raw)))
    changed.append(lba)
    for descriptor in range(16, 48):
        raw = bytearray(sector(descriptor))
        payload = raw[24:2072]
        if payload[1:6] != b'CD001':
            raise ModError('Descritores ISO9660 incompletos.')
        if payload[0] == 255:
            break
        if payload[0] in (1, 2):
            struct.pack_into('<I', raw, 24 + 80, extent + count)
            struct.pack_into('>I', raw, 24 + 84, extent + count)
            stream.seek(descriptor * RAW_SECTOR)
            stream.write(regenerate_form1(bytes(raw)))
            changed.append(descriptor)
    else:
        raise ModError('Terminador ISO9660 ausente.')
    return changed
