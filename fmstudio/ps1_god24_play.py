"""Roteamento experimental de God24 na mão e na colocação do PS1.

Perfil do SLUS de Drop x15. As janelas são reescritas no próprio lugar,
com os destinos e delay slots dos desvios originais. O jogo continua
lendo e armazenando o identificador de tipo de cinco bits.
"""
from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterable
from dataclasses import dataclass

from .core import ModError
from .ps1_god24_chest import SOURCE_SHA256
from .tables import EXE_DELTA

# sllv desloca pelos cinco bits baixos do tipo. O bit 31 do resultado
# vale 1 para 20–23 e 25–31. Para 0–19 e 24, o resultado não é negativo.
SPECIAL_TYPE_BITS = 0x0F7F


@dataclass(frozen=True)
class Site:
    offset: int
    phase: str
    label: str
    original: tuple[int, ...]
    replacement: tuple[int, ...]


def _immediate(op: int, source: int, target: int, value: int) -> int:
    return op << 26 | source << 21 | target << 16 | value


def _shift_left_type(type_reg: int, bits_reg: int, result_reg: int) -> int:
    return type_reg << 21 | bits_reg << 16 | result_reg << 11 | 0x04


def _branch_by_sign(branch: int) -> int:
    # O classificador original devolvia zero para cartas especiais.
    # Na nova sequência, um valor negativo indica a mesma categoria.
    positive = int(branch >> 26 == 5)
    return _immediate(1, 2, positive, branch & 0xFFFF)


def _hand_site(offset: int, label: str, branch: int, delay: int, *,
               keep_type_in_s0: bool = True) -> Site:
    type_reg = 16 if keep_type_in_s0 else 2
    bits_reg = 2 if keep_type_in_s0 else 3
    original = (
        0x8C420000, 0, 0x00021683,                     # lw; load delay; sra
        _immediate(12, 2, type_reg, 31),              # andi tipo, v0, 31
        _immediate(10, type_reg, 2, 20),              # slti v0, tipo, 20
        branch, delay,
    )
    replacement = (
        _immediate(35, 2, type_reg, 0),               # lw tipo, 0(v0)
        _immediate(13, 0, bits_reg, SPECIAL_TYPE_BITS),  # load delay independente
        type_reg << 16 | type_reg << 11 | 26 << 6 | 2,  # srl tipo, tipo, 26
        _immediate(12, type_reg, type_reg, 31),        # mantém o tipo exato em s0
        _shift_left_type(type_reg, bits_reg, 2),
        _branch_by_sign(branch), delay,
    )
    # No primeiro ponto v1 só tinha o endereço da tabela, já consumido.
    # Os outros pontos voltam a ler s0 para distinguir Equip e Armadilha.
    return Site(offset, 'mao', label, original, replacement)


def _placement_site(offset: int, phase: str, label: str, load: int,
                    branch: int, delay: int) -> Site:
    # O byte 0x68 vem do campo de tipo de cinco bits. Nestas janelas,
    # at está livre e v0 é consumido pelo desvio antes de ser reescrito.
    original = (load, 0, 0x2C420014, branch, delay)
    replacement = (
        load,
        _immediate(13, 0, 1, SPECIAL_TYPE_BITS),      # load delay independente
        _shift_left_type(2, 1, 2),
        _branch_by_sign(branch), delay,
    )
    return Site(offset, phase, label, original, replacement)


SITES = (
    _hand_site(0xCA08, 'seleção inicial', 0x10400009, 0x3C02800F,
               keep_type_in_s0=False),
    _hand_site(0xCBF4, 'confirmação na mão', 0x1440000F, 0x3C028002),
    _hand_site(0xD1F0, 'posição da carta', 0x14400003, 0x24020015),
    _hand_site(0xD528, 'saída da mão', 0x1440001D, 0),
    _placement_site(0xA64C, 'colocacao', 'carta única', 0x90420068,
                    0x10400002, 0x24020001),
    _placement_site(0xB32C, 'colocacao', 'carta restante', 0x90820068,
                    0x10400007, 0),
    _placement_site(0xB594, 'colocacao', 'primeiro slot', 0x90420068,
                    0x10400008, 0x26109EF0),
    _placement_site(0xB5B0, 'colocacao', 'segundo slot', 0x90420068,
                    0x14400002, 0),
    _placement_site(0xB760, 'colocacao', 'ordem do segundo slot', 0x90620068,
                    0x14400009, 0),
    _placement_site(0xB774, 'colocacao', 'ordem do primeiro slot', 0x92220068,
                    0x10400004, 0),
    _placement_site(0xB854, 'colocacao', 'entrada no campo', 0x90620068,
                    0x10400010, 0x24024008),
    _placement_site(0xB9CC, 'confirmacao', 'posição e estrela predefinidas',
                    0x92220068, 0x1040001C, 0x3C02801A),
    _placement_site(0xBB10, 'confirmacao', 'escolha de estrela guardiã',
                    0x92220068, 0x1040004C, 0x24020003),
)


def _code_end(exe: bytes) -> int:
    if len(exe) < 0x800 or exe[:8] != b'PS-X EXE':
        return 0
    address, size = struct.unpack_from('<II', exe, 0x18)
    if address != EXE_DELTA + 0x800 or not size or size % 4 or 0x800 + size > len(exe):
        return 0
    return 0x800 + size


def inspect(exe: bytes) -> dict:
    code_end = _code_end(exe)
    phases = {
        phase: {'aplicados': 0, 'total': 0}
        for phase in ('mao', 'colocacao', 'confirmacao')
    }
    points = []
    for site in SITES:
        length = len(site.original)
        words = (struct.unpack_from(f'<{length}I', exe, site.offset)
                 if site.offset + length * 4 <= code_end else ())
        if words == site.replacement:
            state = 'patch_presente'
        elif words == site.original:
            state = 'original_sem_patch'
        else:
            state = 'sequencia_divergente' if words else 'fora_do_segmento'
        phase = phases[site.phase]
        phase['total'] += 1
        phase['aplicados'] += state == 'patch_presente'
        points.append({
            'etapa': site.phase,
            'rotina': site.label,
            'offset_slus': f'0x{site.offset:X}',
            'endereco_ram': f'0x{site.offset + EXE_DELTA:08X}',
            'estado': state,
            'opcodes_lidos': [f'0x{word:08X}' for word in words],
        })
    applied = sum(phase['aplicados'] for phase in phases.values())
    if applied == len(SITES):
        status = 'aplicado'
    elif any(p['estado'] in ('sequencia_divergente', 'fora_do_segmento') for p in points):
        status = 'assinatura_divergente'
    else:
        status = 'parcial' if applied else 'original'
    return {
        'status': status,
        'pontos_aplicados': applied,
        'total_pontos': len(SITES),
        'etapas': phases,
        'pontos': points,
        'validado_no_epsxe': False,
    }


def apply(original_exe: bytes, edited_exe: bytes, card_types: Iterable[int],
          *, source_sha256: str = SOURCE_SHA256) -> tuple[bytes, dict]:
    if len(original_exe) != len(edited_exe):
        raise ModError('God24 em duelo: tamanho do SLUS divergente.')
    if hashlib.sha256(original_exe).hexdigest() != source_sha256:
        raise ModError('God24 em duelo: SHA-256 do SLUS original fora do perfil Drop x15.')
    kinds = tuple(card_types)
    if 24 not in kinds or any(type(kind) is not int or not 0 <= kind <= 24 for kind in kinds):
        raise ModError('God24 em duelo: exige uma carta God24 e tipos dentro de 0–24.')

    for image in (original_exe, edited_exe):
        report = inspect(image)
        conflicts = [p['offset_slus'] for p in report['pontos']
                     if p['estado'] != 'original_sem_patch']
        if conflicts:
            raise ModError('God24 em duelo: assinatura MIPS inesperada em '
                           + ', '.join(conflicts) + '. Selecione o BIN de origem.')

    patched = bytearray(edited_exe)
    for site in SITES:
        struct.pack_into(f'<{len(site.replacement)}I', patched, site.offset,
                         *site.replacement)
    result = bytes(patched)
    report = inspect(result)
    if report['status'] != 'aplicado':
        raise ModError('God24 em duelo: a releitura das instruções falhou.')
    return result, report
