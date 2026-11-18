"""Otimizador de imagens indexadas PS1: Pillow opcional, pixels e CLUT verificáveis.

Compatibilidade: jamais sobrescreve uma CLUT de registros originais.
Novas CLUTs só são permitidas em registros privados acrescentados pela
expansão nativa, onde arte e miniatura possuem sua própria cópia.
"""
from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from .core import ModError
from .png_pixels import read_png, resize_rgba

ART_SIZE = (102, 96)
THUMB_SIZE = (40, 32)
LIMITS = {"arte": (ART_SIZE, 256), "miniatura": (THUMB_SIZE, 64),
          "icone": ((16, 16), 16)}
MODES = ("automatico", "maxima_fidelidade", "compatibilidade", "personalizado")
PALETTES = ("automatico", "compatibilidade", "seguro", "personalizada")
FILTERS = ("automatico", "lanczos", "bicubic", "bilinear", "nearest", "box")
DITHERS = ("automatico", "nenhum", "floyd", "bayer2", "bayer4", "bayer8")


@dataclass(frozen=True)
class ImageOptions:
    enabled: bool = True
    mode: str = "automatico"
    palette: str = "automatico"
    resample: str = "automatico"
    dither: str = "automatico"
    intensity: float = 0.38
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    gamma: float = 1.0
    sharpness: float = 1.0
    denoise: bool = False

    @classmethod
    def from_mapping(cls, data=None):
        if isinstance(data, ImageOptions):
            return data
        data = data or {}
        if not isinstance(data, dict):
            raise ModError("Configuração de imagens PS1 inválida.")
        items = {name: data[name] for name in cls.__dataclass_fields__ if name in data}
        try:
            options = cls(**items)
            if (options.mode not in MODES or options.palette not in PALETTES
                or options.resample not in FILTERS or options.dither not in DITHERS
                or type(options.enabled) is not bool or type(options.denoise) is not bool):
                raise ValueError("opção desconhecida")
            for label, value, lo, hi in (
                ("intensity", options.intensity, 0, 1),
                ("brightness", options.brightness, .7, 1.3),
                ("contrast", options.contrast, .7, 1.3),
                ("saturation", options.saturation, .7, 1.3),
                ("gamma", options.gamma, .7, 1.4),
                ("sharpness", options.sharpness, .7, 1.5)):
                if not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
                    raise ValueError(f"{label}: permitido entre {lo} e {hi}")
        except (TypeError, ValueError) as exc:
            raise ModError(f"Configuração de imagens PS1: {exc}") from exc
        return options


def rgb555(word: int) -> tuple[int, int, int, int]:
    """Sem STP como alpha: o bit 15 é modo de blend do PS1, não alpha PNG."""
    if word == 0:
        return (0, 0, 0, 0)
    return tuple((level << 3) | (level >> 2)
                 for level in (((word >> shift) & 31) for shift in (0, 5, 10))) + (255,)


def pack_rgb555(r: int, g: int, b: int) -> int:
    value = ((r * 31 + 127) // 255 |
             ((g * 31 + 127) // 255) << 5 |
             ((b * 31 + 127) // 255) << 10)
    # 0000h é o texel transparente no renderer existente.
    # Evitar bit STP em paletas novas: preto puro vira quase preto.
    return value or 1


def clut_words(record: bytes, offset: int, colors: int) -> tuple[int, ...]:
    if offset < 0 or offset + colors * 2 > len(record):
        raise ModError("CLUT fora dos limites do registro WA_MRG.")
    return struct.unpack_from("<" + "H" * colors, record, offset)


def rgba_from_indices(indices: bytes, clut: tuple[int, ...]) -> bytes:
    colors = [rgb555(c) for c in clut]
    if any(index >= len(colors) for index in indices):
        raise ModError("Índice de cor fora da CLUT do recurso PS1.")
    return b"".join(bytes(colors[index]) for index in indices)


def png_rgba(pixels: bytes, size: tuple[int, int]) -> bytes:
    """PNG RGBA sem Pillow para prévia exatamente igual à CLUT/index final."""
    width, height = size
    if len(pixels) != width * height * 4:
        raise ModError("Prévia RGBA com tamanho incorreto.")
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    raw = b"".join(b"\0" + pixels[y * width * 4:(y + 1) * width * 4]
                   for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _pillow():
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        return Image, ImageEnhance, ImageFilter, ImageOps
    except ImportError:
        return None


def _scaled_rgba(path: Path, size: tuple[int, int], options: ImageOptions):
    """Renderiza com proporção preservada, fundo transparente e filtros suaves."""
    lib = _pillow()
    if lib is None:
        try:
            width, height, source = read_png(path)
        except (OSError, ValueError) as exc:
            raise ModError(f"PNG {path.name}: {exc}") from exc
        if not options.enabled or options.mode == "compatibilidade":
            return resize_rgba(source, (width, height), size), ("Pillow ausente: redução por área/bilinear.",)
        ratio = min(size[0] / width, size[1] / height)
        dimensions = (max(1, min(size[0], round(width * ratio))),
                      max(1, min(size[1], round(height * ratio))))
        data = resize_rgba(source, (width, height), dimensions)
        output = bytearray(size[0] * size[1] * 4)
        x0, y0 = (size[0] - dimensions[0]) // 2, (size[1] - dimensions[1]) // 2
        for y in range(dimensions[1]):
            begin = 4 * ((y + y0) * size[0] + x0)
            output[begin:begin + dimensions[0] * 4] = data[y * dimensions[0] * 4:(y + 1) * dimensions[0] * 4]
        return bytes(output), ("Pillow ausente: preservada a proporção, sem filtros adicionais.",)

    Image, Enhance, ImageFilter, ImageOps = lib
    try:
        with Image.open(path) as source:
            if source.width * source.height > 16_777_216 or max(source.size) > 16384:
                raise ModError("Imagem acima do limite seguro de 16.777.216 pixels.")
            source.load()
            img = source.convert("RGBA")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ModError(f"PNG {path.name}: {exc}") from exc
    legacy = not options.enabled or options.mode == "compatibilidade"
    if not legacy:
        # Ajustes adaptativos brandos apenas no Automático: não reinterpretar
        # a iluminação dramática de uma imagem em Máxima fidelidade.
        if options.mode == "automatico":
            sample = img.copy()
            sample.thumbnail((64, 64))
            rgb = sample.getdata()
            values = [(r, g, b) for r, g, b, a in rgb if a >= 128]
            if values:
                luma = [(.2126*r+.7152*g+.0722*b) for r,g,b in values]
                avg = sum(luma) / len(luma)
                spread = (sum((v-avg)**2 for v in luma) / len(luma)) ** .5
                if avg < 57 and spread < 50:
                    img = Enhance.Brightness(img).enhance(1.055)
                elif avg > 215 and spread < 45:
                    img = Enhance.Brightness(img).enhance(.965)
                if spread < 30 and 65 < avg < 195:
                    img = Enhance.Contrast(img).enhance(1.035)
                chroma = sum(max(c)-min(c) for c in values) / len(values)
                if chroma < 28 and spread > 25:
                    img = Enhance.Color(img).enhance(1.025)
        if options.mode == "personalizado":
            if options.denoise:
                img = img.filter(ImageFilter.MedianFilter(3))
            for adjustment, factor in ((Enhance.Brightness, options.brightness),
                                       (Enhance.Contrast, options.contrast),
                                       (Enhance.Color, options.saturation),
                                       (Enhance.Sharpness, options.sharpness)):
                if factor != 1.0:
                    img = adjustment(img).enhance(factor)
            if options.gamma != 1.0:
                curve = [max(0, min(255, round(255 * ((i/255) ** (1/options.gamma)))))
                         for i in range(256)]
                r, g, b, a = img.split()
                img = Image.merge("RGBA", (r.point(curve), g.point(curve),
                                           b.point(curve), a))
        if options.mode in ("automatico", "personalizado") and img.width > size[0] * 2:
            img = img.filter(ImageFilter.UnsharpMask(radius=.6, percent=55, threshold=3))
    method = options.resample
    if method == "automatico":
        ratio = max(img.width / size[0], img.height / size[1])
        method = "box" if ratio >= 5 and size == THUMB_SIZE else "lanczos"
    filters = {"lanczos": Image.Resampling.LANCZOS,
               "bicubic": Image.Resampling.BICUBIC,
               "bilinear": Image.Resampling.BILINEAR,
               "nearest": Image.Resampling.NEAREST,
               "box": Image.Resampling.BOX}
    if legacy:
        return img.resize(size, filters[method]).tobytes(), ()
    # ImageOps.contain mantém a arte inteira; não recorta elementos importantes.
    result = ImageOps.contain(img, size, method=filters[method])
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(result, ((size[0] - result.width) // 2,
                                    (size[1] - result.height) // 2))
    return canvas.tobytes(), ()


def _bayer(n: int) -> list[list[int]]:
    matrix = [[0]]
    while len(matrix) < n:
        m = len(matrix)
        matrix = [[4 * matrix[y % m][x % m] + (0 if y < m and x < m else
                   2 if y < m else 3 if x < m else 1)
                   for x in range(m * 2)] for y in range(m * 2)]
    return matrix


def _choose_dither(pixels: bytes, width: int, height: int, options: ImageOptions) -> str:
    if options.dither != "automatico":
        return options.dither
    # Gradientes suaves justificam difusão; ícones e silhuetas não.
    if width <= 16:
        return "nenhum"
    total = 0
    smooth = 0
    for y in range(0, height, max(1, height // 24)):
        for x in range(1, width, max(1, width // 24)):
            a = (y * width + x) * 4
            b = a - 4
            if pixels[a + 3] < 128 or pixels[b + 3] < 128:
                continue
            diff = sum(abs(pixels[a + j] - pixels[b + j]) for j in range(3)) / 3
            smooth += 2 <= diff <= 24
            total += 1
    return "bayer4" if total and smooth / total > .22 else "nenhum"


def _palette_from_image(pixels: bytes, limit: int) -> tuple[int, ...] | None:
    lib = _pillow()
    if not lib:
        return None
    Image = lib[0]
    rgb = [tuple(pixels[i:i + 3]) for i in range(0, len(pixels), 4)
           if pixels[i + 3] >= 128]
    if not rgb:
        return None
    strip = Image.new("RGB", (len(rgb), 1))
    strip.putdata(rgb)
    quantized = strip.quantize(colors=min(limit - 1, 255),
                               method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    color_counts = quantized.getcolors(maxcolors=len(rgb) + 1) or []
    palette = quantized.getpalette()
    words = [0]
    for _, idx in sorted(color_counts, reverse=True):
        word = pack_rgb555(*palette[idx * 3:idx * 3 + 3])
        if word not in words:
            words.append(word)
        if len(words) == limit:
            break
    return tuple(words + [0] * (limit - len(words)))


def _index_rgba(pixels: bytes, size: tuple[int, int], clut: tuple[int, ...],
                dither: str, strength: float, *, legacy: bool = False):
    w, h = size
    colors = [(i, rgb555(value)[:3]) for i, value in enumerate(clut) if value != 0]
    if not colors:
        raise ModError("CLUT sem cores visíveis; operação bloqueada.")
    result = bytearray(w * h)
    errors = [[0.0, 0.0, 0.0] for _ in range(w * h)] if dither == "floyd" else None
    bayer = _bayer(int(dither[-1])) if dither.startswith("bayer") else None
    nearest_cache = {}
    accum = 0.0
    samples = 0
    for y in range(h):
        for x in range(w):
            idx = y * w + x
            p = idx * 4
            if pixels[p + 3] < 128:
                continue
            rgb = [pixels[p + k] for k in range(3)]
            if errors is not None:
                rgb = [max(0, min(255, v + errors[idx][k])) for k, v in enumerate(rgb)]
            if bayer is not None:
                n = len(bayer)
                shift = (bayer[y % n][x % n] + .5) / (n*n) - .5
                rgb = [max(0, min(255, v + shift * 24 * strength)) for v in rgb]
            key = tuple(int(v) for v in rgb)
            choice = nearest_cache.get(key)
            if choice is None:
                choice = min(colors, key=lambda c:
                             (1 if legacy else 3)*(rgb[0]-c[1][0])**2 +
                             (1 if legacy else 6)*(rgb[1]-c[1][1])**2 +
                             (1 if legacy else 2)*(rgb[2]-c[1][2])**2)
                if len(nearest_cache) < 65536:
                    nearest_cache[key] = choice
            index, actual = choice
            result[idx] = index
            accum += sum((pixels[p + k] - actual[k]) ** 2 for k in range(3))
            samples += 3
            if errors is not None:
                delta = [(rgb[k]-actual[k]) * strength for k in range(3)]
                for ox, oy, scale in ((1, 0, 7/16), (-1, 1, 3/16),
                                      (0, 1, 5/16), (1, 1, 1/16)):
                    nx, ny = x + ox, y + oy
                    if 0 <= nx < w and ny < h and pixels[(ny*w+nx)*4+3] >= 128:
                        target = errors[ny*w+nx]
                        for k in range(3):
                            target[k] += delta[k] * scale
    rmse = math.sqrt(accum / samples) if samples else 0.0
    return bytes(result), rmse


@dataclass
class RenderedResource:
    indices: bytes
    clut: tuple[int, ...]
    preview_rgba: bytes
    source_rgba: bytes
    size: tuple[int, int]
    report: dict = field(default_factory=dict)

    def preview_png(self) -> bytes:
        return png_rgba(self.preview_rgba, self.size)


@dataclass
class RenderedCard:
    art: RenderedResource
    thumbnail: RenderedResource

    def diagnostics(self):
        return {"arte": self.art.report, "miniatura": self.thumbnail.report}


def render_resource(png: Path, original_clut: tuple[int, ...],
                    size: tuple[int, int], options=None, *,
                    private_clut: bool = False) -> RenderedResource:
    opts = ImageOptions.from_mapping(options)
    if len(original_clut) not in (16, 64, 256):
        raise ModError("Número de entradas de CLUT não é suportado.")
    raw, warnings = _scaled_rgba(Path(png), size, opts)
    requested = opts.palette
    replace = (private_clut and opts.enabled and opts.mode != "compatibilidade"
               and requested in ("automatico", "seguro", "personalizada"))
    new_clut = _palette_from_image(raw, len(original_clut)) if replace else None
    clut = new_clut if new_clut is not None else original_clut
    if clut[0] != 0 and any(raw[i] < 128 for i in range(3, len(raw), 4)):
        raise ModError("O índice zero desta CLUT é opaco; transparência não pode "
                       "ser gravada sem alterar uma paleta compartilhada.")
    if not private_clut and requested in ("seguro", "personalizada"):
        warnings += ("CLUT original preservada: não foi comprovada exclusividade; "
                     "a troca de paleta foi bloqueada.",)
    if replace and new_clut is None:
        warnings += ("Paleta privada mantida: otimização adaptativa requer Pillow "
                     "e pixels opacos na imagem.",)
    method = "nenhum" if not opts.enabled or opts.mode == "compatibilidade" else _choose_dither(
        raw, size[0], size[1], opts)
    strength = opts.intensity if method != "nenhum" else 0
    mapped, rmse = _index_rgba(raw, size, clut, method, strength,
                               legacy=not opts.enabled or opts.mode == "compatibilidade")
    if rmse > 65:
        warnings += ("Aviso: paleta original distante das cores do PNG (perda alta de fidelidade).",)
    decoded = rgba_from_indices(mapped, clut)
    used = len(set(mapped))
    return RenderedResource(
        mapped, clut, decoded, raw, size,
        {"resolucao": f"{size[0]}x{size[1]}", "cores_usadas": used,
         "cores_clut": len(clut), "rmse_rgb": round(rmse, 2),
         "fidelidade_indicativa": round(max(0, 100 - rmse * .75), 1),
         "dithering": method,
         "paleta": "privada_adaptativa" if new_clut is not None else "original_preservada",
         "pillow": _pillow() is not None, "avisos": list(warnings)})


def render_card(png: Path, art_record: bytes, thumb_record: bytes, options=None, *,
                private_clut: bool = False) -> RenderedCard:
    """Mesmos pixels/CLUT para prévia e exportação, sem alterar regiões adjacentes."""
    # Projetos antigos sem configuração continuam pixel-identical no modo
    # legível original. Novos imports registram automatico por padrão.
    if options is None:
        options = {"enabled": False, "mode": "compatibilidade",
                   "palette": "compatibilidade", "dither": "nenhum"}
    art_clut = clut_words(art_record, 0x2640, 256)
    thumb_clut = clut_words(thumb_record, 0x500, 64)
    return RenderedCard(
        art=render_resource(png, art_clut, ART_SIZE, options, private_clut=private_clut),
        thumbnail=render_resource(png, thumb_clut, THUMB_SIZE, options, private_clut=private_clut))
