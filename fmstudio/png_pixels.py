"""Read static PNG pixels and resize RGBA without optional image libraries."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
PNG_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8),
              4: (8, 16), 6: (8, 16)}
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
         (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 16_777_216
MAX_DIMENSION = 16_384


def _chunks(data: bytes):
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError('Assinatura PNG inválida.')
    data = memoryview(data)
    offset = len(PNG_SIGNATURE)
    while offset < len(data):
        if len(data) - offset < 12:
            raise ValueError('Bloco PNG incompleto.')
        length, kind = struct.unpack_from('>I4s', data, offset)
        start = offset + 8
        end = start + length
        if end + 4 > len(data):
            raise ValueError('Tamanho de bloco PNG inválido.')
        payload = data[start:end]
        if zlib.crc32(payload, zlib.crc32(kind)) != struct.unpack_from('>I', data, end)[0]:
            raise ValueError('CRC PNG incorreto.')
        offset = end + 4
        if kind == b'IEND' and (length or offset != len(data)):
            raise ValueError('Encerramento PNG inválido.')
        yield kind, payload


def _passes(width, height, interlace, bits):
    passes = []
    for x, y, step_x, step_y in ADAM7 if interlace else ((0, 0, 1, 1),):
        columns = (width - x + step_x - 1) // step_x
        rows = (height - y + step_y - 1) // step_y
        if columns > 0 and rows > 0:
            row_bytes = (columns * bits + 7) // 8
            passes.append((x, y, step_x, step_y, columns, rows, row_bytes))
    return passes


def _unfilter(row: bytearray, previous: bytearray, stride: int, method: int):
    if method == 0:
        return
    if method == 1:
        for i in range(stride, len(row)):
            row[i] = (row[i] + row[i - stride]) & 255
    elif method == 2:
        row[:] = bytes((value + above) & 255 for value, above in zip(row, previous))
    elif method in (3, 4):
        for i in range(len(row)):
            left = row[i - stride] if i >= stride else 0
            above = previous[i]
            if method == 3:
                prediction = (left + above) // 2
            else:
                corner = previous[i - stride] if i >= stride else 0
                a = abs(above - corner)
                b = abs(left - corner)
                c = abs(left + above - 2 * corner)
                prediction = left if a <= b and a <= c else above if b <= c else corner
            row[i] = (row[i] + prediction) & 255
    else:
        raise ValueError('Filtro PNG desconhecido.')


def _samples(row, depth, channels, count):
    if depth == 16:
        yield from struct.iter_unpack('>' + 'H' * channels, row)
    elif depth == 8:
        yield from (tuple(row[i:i + channels]) for i in range(0, len(row), channels))
    else:
        mask = (1 << depth) - 1
        for bit in range(0, count * depth, depth):
            yield ((row[bit // 8] >> (8 - depth - bit % 8)) & mask,)


def _rgba(row, depth, color, count, entries, transparent):
    if (depth, color) == (8, 6):
        return row
    pixels = bytearray(4 * count)
    if depth == 8 and transparent is None and color in (0, 2):
        if color == 0:
            pixels[0::4] = pixels[1::4] = pixels[2::4] = row
        else:
            for channel in range(3):
                pixels[channel::4] = row[channel::3]
        pixels[3::4] = b'\xff' * count
        return pixels
    maximum = (1 << depth) - 1
    for i, sample in enumerate(_samples(row, depth, PNG_CHANNELS[color], count)):
        if color == 3:
            index = sample[0]
            if index >= len(entries):
                raise ValueError('Índice de cor fora da paleta PNG.')
            pixel = entries[index]
        else:
            values = tuple(value * 255 // maximum for value in sample)
            if color == 0:
                pixel = (values[0],) * 3 + (0 if sample == transparent else 255,)
            elif color == 2:
                pixel = values + (0 if sample == transparent else 255,)
            elif color == 4:
                pixel = (values[0],) * 3 + (values[1],)
            else:
                pixel = values
        pixels[i * 4:i * 4 + 4] = bytes(pixel)
    return pixels


def read_png(path: Path, *, max_bytes: int = MAX_FILE_BYTES,
             expected_size: tuple[int, int] | None = None) -> tuple[int, int, bytes]:
    """Return width, height and tightly packed RGBA for a bounded PNG."""
    with path.open('rb') as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f'Arquivo PNG excede {max_bytes // 1024} KiB.')
    chunks = iter(_chunks(data))
    kind, header = next(chunks, (None, b''))
    if kind != b'IHDR' or len(header) != 13:
        raise ValueError('Cabeçalho PNG inválido.')
    width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', header)
    if (not 1 <= width <= MAX_DIMENSION or not 1 <= height <= MAX_DIMENSION
            or width * height > MAX_PIXELS):
        raise ValueError('Dimensões PNG inválidas. Limites de 16.777.216 pixels e 16.384 por lado.')
    if expected_size is not None and (width, height) != expected_size:
        raise ValueError(f'Use um PNG de {expected_size[0]}×{expected_size[1]} pixels.')
    if depth not in PNG_DEPTHS.get(color, ()) or compression or filtering or interlace not in (0, 1):
        raise ValueError('Formato PNG não suportado.')
    palette, transparency, parts = None, None, []
    for kind, payload in chunks:
        if kind == b'PLTE':
            if palette is not None or parts or not 0 < len(payload) <= 768 or len(payload) % 3:
                raise ValueError('Paleta PNG inválida.')
            palette = bytes(payload)
        elif kind == b'tRNS':
            if transparency is not None or parts:
                raise ValueError('Transparência PNG inválida.')
            transparency = bytes(payload)
        elif kind == b'IDAT':
            parts.append(payload)
        elif kind == b'IEND':
            break
        elif not (kind[0] & 0x20):
            raise ValueError('Bloco PNG obrigatório não suportado.')
    if kind != b'IEND' or not parts:
        raise ValueError('Arquivo PNG incompleto.')

    entries, transparent = (), None
    if color == 3:
        if palette is None or len(palette) // 3 > 1 << depth:
            raise ValueError('Paleta PNG ausente ou incompatível.')
        count = len(palette) // 3
        if transparency is not None and not 1 <= len(transparency) <= count:
            raise ValueError('Transparência da paleta PNG inválida.')
        alpha = (transparency or b'').ljust(count, b'\xff')
        entries = [palette[3 * i:3 * i + 3] + bytes([alpha[i]]) for i in range(count)]
    elif transparency is not None:
        if color not in (0, 2) or len(transparency) != PNG_CHANNELS[color] * 2:
            raise ValueError('Transparência PNG incompatível.')
        transparent = struct.unpack('>' + 'H' * PNG_CHANNELS[color], transparency)

    bits = depth * PNG_CHANNELS[color]
    stride = (bits + 7) // 8
    passes = _passes(width, height, interlace, bits)
    expected = sum(rows * (row_bytes + 1) for *_, rows, row_bytes in passes)
    inflater = zlib.decompressobj()
    try:
        raw = inflater.decompress(b''.join(parts), expected + 1)
    except zlib.error as exc:
        raise ValueError('Dados compactados PNG inválidos.') from exc
    if len(raw) != expected or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
        raise ValueError('Tamanho dos dados PNG incompatível com a imagem.')

    result = bytearray(width * height * 4)
    offset = 0
    for x, y, step_x, step_y, columns, rows, row_bytes in passes:
        previous = bytearray(row_bytes)
        for row_index in range(rows):
            method = raw[offset]
            row = bytearray(raw[offset + 1:offset + row_bytes + 1])
            offset += row_bytes + 1
            _unfilter(row, previous, stride, method)
            pixels = _rgba(row, depth, color, columns, entries, transparent)
            start = ((y + row_index * step_y) * width + x) * 4
            if step_x == 1:
                result[start:start + columns * 4] = pixels
            else:
                step = step_x * 4
                for channel in range(4):
                    first = start + channel
                    result[first:first + (columns - 1) * step + 1:step] = pixels[channel::4]
            previous = row
    return width, height, bytes(result)


def _axis_weights(source: int, target: int):
    if target <= source:
        weights = []
        for i in range(target):
            start, end = i * source, (i + 1) * source
            weights.append([(j, min(end, (j + 1) * target) - max(start, j * target))
                            for j in range(start // target, (end - 1) // target + 1)])
        return weights, source
    scale = 2 * target
    weights = []
    for i in range(target):
        left, fraction = divmod((2 * i + 1) * source - target, scale)
        if left < 0 or left >= source - 1:
            weights.append([(max(0, min(left, source - 1)), scale)])
        else:
            weights.append([(left, scale - fraction), (left + 1, fraction)])
    return weights, scale


def resize_rgba(pixels: bytes, size: tuple[int, int], dimensions: tuple[int, int]) -> bytes:
    """Downsample by area and upscale with linear interpolation in premultiplied alpha."""
    if size == dimensions:
        return pixels
    width, height = size
    x_weights, x_scale = _axis_weights(width, dimensions[0])
    y_weights, y_scale = _axis_weights(height, dimensions[1])
    area = x_scale * y_scale
    output = bytearray()
    for vertical in y_weights:
        scanlines = [(4 * width * y, weight) for y, weight in vertical]
        for horizontal in x_weights:
            red = green = blue = alpha = 0
            for start, y_weight in scanlines:
                for x, x_weight in horizontal:
                    at = start + 4 * x
                    weighted_alpha = pixels[at + 3] * x_weight * y_weight
                    alpha += weighted_alpha
                    red += pixels[at] * weighted_alpha
                    green += pixels[at + 1] * weighted_alpha
                    blue += pixels[at + 2] * weighted_alpha
            if alpha:
                output.extend(((red + alpha // 2) // alpha, (green + alpha // 2) // alpha,
                               (blue + alpha // 2) // alpha, (alpha + area // 2) // area))
            else:
                output.extend(b'\0' * 4)
    return bytes(output)
