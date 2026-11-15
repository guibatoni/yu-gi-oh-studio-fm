"""Read-only ISO9660 inspection for PlayStation 1 2048 ISO and MODE1/MODE2 2352 BIN.

This is not a disc image writer. It deliberately refuses unsupported tracks/layouts.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import re
import struct
from typing import Iterator

SYNC = bytes([0]) + bytes([0xff]) * 10 + bytes([0])

class DiscError(Exception):
    pass

@dataclass(frozen=True)
class IsoEntry:
    path: str
    extent: int
    size: int
    is_dir: bool

class DiscReader:
    def __init__(self, path: Path):
        path = Path(path)
        if path.suffix.lower() == '.cue':
            path = self._resolve_cue(path)
        if not path.is_file():
            raise DiscError(f'Arquivo não encontrado: {path}')
        self.path = path
        self.fp = path.open('rb')
        try:
            self.sector_size, self.data_offset, self.mode = self._detect()
        except Exception:
            self.fp.close()
            raise

    @staticmethod
    def _resolve_cue(cue: Path) -> Path:
        content = cue.read_text(encoding='utf-8-sig', errors='replace')
        matches = re.findall(r'^\s*FILE\s+(?:"([^"]+)"|([^\s]+))\s+BINARY\s*$', content, re.I | re.M)
        tracks = re.findall(r'^\s*TRACK\s+\d+\s+([^\s]+)', content, re.I | re.M)
        if len(matches) != 1 or len(tracks) != 1 or tracks[0].upper() not in ('MODE1/2352', 'MODE2/2352'):
            raise DiscError('CUE não é uma única faixa de dados MODE1/2352 ou MODE2/2352; conversão manual necessária.')
        filename = (matches[0][0] or matches[0][1]).replace('\\', '/')
        return cue.parent / filename

    def _detect(self) -> tuple[int, int, str]:
        size = self.path.stat().st_size
        for sector_size in (2352, 2048):
            if size % sector_size:
                continue
            self.fp.seek(sector_size * 16)
            raw = self.fp.read(sector_size)
            if len(raw) != sector_size:
                continue
            if sector_size == 2048:
                if raw[1:6] == b'CD001':
                    return 2048, 0, 'ISO2048'
                continue
            if raw[:12] != SYNC:
                continue
            mode = raw[15]
            if mode == 1 and raw[16+1:16+6] == b'CD001':
                return 2352, 16, 'MODE1/2352'
            if mode == 2 and raw[24+1:24+6] == b'CD001':
                return 2352, 24, 'MODE2/2352'
        raise DiscError('Não foi encontrado ISO9660 PVD no setor 16 (ISO 2048 ou BIN 2352).')

    def close(self):
        self.fp.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def sector(self, lba: int) -> bytes:
        if lba < 0:
            raise DiscError('LBA negativo')
        self.fp.seek(lba * self.sector_size)
        raw = self.fp.read(self.sector_size)
        if len(raw) != self.sector_size:
            raise DiscError(f'Setor incompleto: LBA {lba}')
        if self.sector_size == 2352:
            if raw[:12] != SYNC:
                raise DiscError(f'Cabeçalho de setor inválido: {lba}')
            if self.data_offset == 16 and raw[15] != 1:
                raise DiscError(f'Modo 1 esperado no setor {lba}')
            if self.data_offset == 24 and (raw[15] != 2 or (raw[18] & 0x20)):
                raise DiscError(f'Setor {lba} não é Mode 2 Form 1; extração genérica não suportada')
        return raw[self.data_offset:self.data_offset+2048]

    @staticmethod
    def parse_entry(raw: bytes, prefix: str) -> IsoEntry | None:
        if not raw or raw[0] < 34 or len(raw) < raw[0]:
            return None
        raw = raw[:raw[0]]
        length = raw[32]
        name_bytes = raw[33:33+length]
        if name_bytes in (b'\x00', b'\x01'):
            return None
        name = name_bytes.decode('ascii', errors='replace').split(';')[0]
        extent = struct.unpack_from('<I', raw, 2)[0]
        size = struct.unpack_from('<I', raw, 10)[0]
        is_dir = bool(raw[25] & 2)
        return IsoEntry(f'{prefix}/{name}' if prefix else name, extent, size, is_dir)

    def files(self) -> list[IsoEntry]:
        volume = self.sector(16)
        if volume[0] != 1 or volume[1:6] != b'CD001':
            raise DiscError('Descritor de volume primário ISO9660 inválido')
        root_bytes = volume[156:]
        root_extent = struct.unpack_from('<I', root_bytes, 2)[0]
        root_size = struct.unpack_from('<I', root_bytes, 10)[0]
        queue: list[tuple[str, int, int, int]] = [('', root_extent, root_size, 0)]
        visited: set[tuple[int,int]] = set()
        out: list[IsoEntry] = []
        while queue:
            prefix, extent, size, depth = queue.pop(0)
            if depth > 12 or (extent, size) in visited:
                continue
            visited.add((extent, size))
            # Directory records do not cross 2048-byte sectors.
            for j in range((size + 2047) // 2048):
                raw = self.sector(extent + j)
                pos = 0
                while pos < 2048:
                    length = raw[pos]
                    if not length:
                        break
                    if pos + length > 2048:
                        raise DiscError(f'Registro ISO9660 atravessa setor em {prefix or "/"}')
                    entry = self.parse_entry(raw[pos:pos+length], prefix)
                    pos += length
                    if entry:
                        out.append(entry)
                        if entry.is_dir:
                            queue.append((entry.path, entry.extent, entry.size, depth + 1))
        return out

    def read_entry(self, entry: IsoEntry) -> Iterator[bytes]:
        if entry.is_dir:
            raise DiscError('Não é permitido extrair diretório como arquivo')
        remaining = entry.size
        i = 0
        while remaining:
            part = self.sector(entry.extent + i)[:min(2048, remaining)]
            remaining -= len(part)
            i += 1
            yield part

    def extract(self, entry: IsoEntry, destination: Path) -> dict:
        destination.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        total = 0
        with destination.open('wb') as out:
            for part in self.read_entry(entry):
                out.write(part)
                h.update(part)
                total += len(part)
        return {'path': entry.path, 'size': total, 'sha256': h.hexdigest(), 'extracted_to': str(destination)}

    def hash_image(self) -> str:
        h = hashlib.sha256()
        self.fp.seek(0)
        for part in iter(lambda: self.fp.read(1024*1024), b''):
            h.update(part)
        return h.hexdigest()
