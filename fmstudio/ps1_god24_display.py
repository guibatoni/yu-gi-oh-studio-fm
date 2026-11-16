"""Rótulo e ícone nativos do tipo God 24 no perfil SLUS de Drop x15."""
from __future__ import annotations

import hashlib
import struct

from .core import ModError
from .ps1_god24_chest import SOURCE_SHA256
from .ps1_god_icon import HEIGHT, PALETTE_OFFSET, ROW_BYTES, WA_SECTOR, god_glyph_rows, god_icon_asset
from .tables import EXE_DELTA

# func_80037DA4: a operação sobre o tipo tem kind=0. As estrelas seguem
# para suas rotinas originais, inclusive Marte (índice 0x18).
TYPE_RAM = 0x80037E20
TYPE_ORIGINAL = (
    0x3083000F, 0x24020001, 0x10620017, 0x00002821, 0x28620002,
    0x10400005, 0x24020002, 0x10600007, 0x30820080, 0x0800DFC4,
    0, 0x10620020, 0x30820080, 0x0800DFC4, 0, 0x3C02801D,
    0x87830430, 0x24424244, 0x2463FFFF, 0x00031880, 0x00621821,
    0x8C620000, 0, 0x00021683, 0x0800DFC3, 0x3045001F,
)
TYPE_PATCHED = (
    0x3083000F,  # andi v1,a0,15: kind do comando
    0x10600007,  # beq v1,zero,0x80037E44: tipo
    0x24020001,  # addiu v0,zero,1
    0x10620016,  # beq v1,v0,0x80037E88: estrela 1
    0x24020002,  # addiu v0,zero,2
    0x10620026,  # beq v1,v0,0x80037ED0: estrela 2
    0x00002821,  # addu a1,zero,zero: valor padrão original
    0x0800DFC4,  # j 0x80037F10
    0x30820080,  # andi v0,a0,0x80: texto ou sprite
    0x3C02801D,  # lui v0,0x801D
    0x87830430,  # lh v1,0x430(gp): carta selecionada
    0x24424240,  # addiu v0,v0,0x4240: tabela menos uma entrada
    0x00031880,  # sll v1,v1,2
    0x00621821,  # addu v1,v1,v0
    0x8C620000,  # lw v0,0(v1): estatísticas
    0x24030018,  # addiu v1,zero,24 no load delay
    0x00022E82,  # srl a1,v0,26
    0x30A5001F,  # andi a1,a1,31: tipo real
    0x14A30029,  # bne a1,v1,0x80037F10: tipo original
    0x30820080,  # andi v0,a0,0x80
    0x10400027,  # beq v0,zero,0x80037F10: exibir o ícone God
    0x24050031,  # addiu a1,zero,0x31: código exclusivo do sprite
    0x0800DFC4,  # j 0x80037F10: exibir o nome God
    0x24050027,  # addiu a1,zero,0x27: string 0x8327
    0, 0,
)

# func_80035E20: saída comum em 0x800362A8. O glifo God usa tpage 0xA
# e (u=0, v=192) na página de boot, com a CLUT original (608, 252).
SPRITE_RAM = 0x80036084
SPRITE_ORIGINAL = (
    0x8FA30034, 0x2402000B, 0xA462000C, 0x9242FFFA, 0x8FB10034,
    0xAEC20000, 0x28420022, 0x14400011, 0x24020080, 0x92C30000,
    0xA222000F, 0x24020200, 0xA6220010, 0x240200FC, 0xA6220012,
    0x24020050, 0x00031900, 0x2463FDF0, 0xA223000E, 0x306300FF,
    0x14620074, 0, 0x24020210, 0x0800D8AA, 0xA6220010,
    0x92C20000, 0, 0x30420007,
)
SPRITE_PATCHED = (
    0x8FB10034,  # lw s1,0x34(sp): sprite 16x16
    0x2402000B,  # addiu v0,zero,0xB
    0xA622000C,  # sh v0,0xC(s1): tpage original
    0x9243FFFA,  # lbu v1,-6(s2): código do ícone
    0x3C0600FC,  # lui a2,0xFC: metade alta da palavra da CLUT
    0xAEC30000,  # sw v1,0(s6): mantém o temporário do renderizador
    0x2C620022,  # sltiu v0,v1,0x22
    0x14400013,  # bne v0,zero,0x800360F0: tipos/estrelas originais
    0x34C60200,  # ori a2,a2,0x200: CLUT padrão (512, 252)
    0x24020031,  # addiu v0,zero,0x31
    0x14620005,  # bne v1,v0,0x800360C4: símbolos dos botões
    0x3C04C000,  # lui a0,0xC000: UV (0, 192)
    0x3484000A,  # ori a0,a0,0xA: tpage God
    0x34C60060,  # ori a2,a2,0x60: CLUT God (608, 252)
    0x0800D83A,  # j 0x800360E8: CLUT e saída comum
    0xAE24000C,  # sw a0,0xC(s1): tpage e UV em campos adjacentes
    0x00031900,  # sll v1,v1,4
    0x2463FDF0,  # addiu v1,v1,-0x210
    0x306300FF,  # andi v1,v1,0xFF: U original
    0x38620050,  # xori v0,v1,0x50
    0x2C420001,  # sltiu v0,v0,1: primeira metade de Start
    0x00021100,  # sll v0,v0,4
    0x00C23025,  # or a2,a2,v0: CLUT alternativa original
    0x34638000,  # ori v1,v1,0x8000: V=128
    0xA623000E,  # sh v1,0xE(s1): UV dos botões
    0x0800D8AA,  # j 0x800362A8: posicionar o sprite
    0xAE260010,  # sw a2,0x10(s1): x e y da CLUT
    0x30620007,  # andi v0,v1,7: a ramificação baixa já tem o código em v1
)

# 0x8327 é um alias de Dragon inalcançável pelo campo de 4 bits das estrelas.
# O novo texto fica no preenchimento entre as strings e a tabela de glifos.
NAME_POINTER = 0x801D5E4E - EXE_DELTA
NAME_OFFSET = 0x801D8F00 - EXE_DELTA
NAME = b'\x29\x04\x0C\xFF'  # God + terminador na fonte original
REGIONS = (
    (TYPE_RAM - EXE_DELTA, struct.pack('<26I', *TYPE_ORIGINAL),
     struct.pack('<26I', *TYPE_PATCHED)),
    (SPRITE_RAM - EXE_DELTA, struct.pack('<28I', *SPRITE_ORIGINAL),
     struct.pack('<28I', *SPRITE_PATCHED)),
    (NAME_POINTER, struct.pack('<H', 0x8ACE), struct.pack('<H', 0x8F00)),
    (NAME_OFFSET, bytes(len(NAME)), NAME),
)
ICON_OFFSET = 0x1690 * WA_SECTOR + 192 * ROW_BYTES
ICON_ROWS = tuple(ICON_OFFSET + y * ROW_BYTES for y in range(HEIGHT))
GOLD_PALETTE = PALETTE_OFFSET + 0xC0


def _pixels(wa: bytes) -> list[bytes]:
    return [wa[offset:offset + 8] for offset in ICON_ROWS]


def _god_pixels(wa: bytes) -> list[bytes]:
    return god_glyph_rows(wa, god_icon_asset(), palette_offset=GOLD_PALETTE)


def inspect(exe: bytes, wa: bytes | None = None) -> dict:
    """Confere o código, o nome e a textura da imagem selecionada."""
    regions = [exe[offset:offset + len(before)] for offset, before, _ in REGIONS]
    status = 'assinatura_divergente'
    if exe.startswith(b'PS-X EXE'):
        if regions == [after for _, _, after in REGIONS]:
            if wa is None:
                status = 'aguardando_textura'
            else:
                try:
                    status = 'aplicado' if _pixels(wa) == _god_pixels(wa) else 'textura_divergente'
                except ModError:
                    status = 'textura_divergente'
        elif regions == [before for _, before, _ in REGIONS]:
            status = 'original'
    return {'status': status, 'nome': 'God' if status == 'aplicado' else None,
            'icone_instalado': status == 'aplicado', 'validado_no_epsxe': False}


def apply(original_exe: bytes, exe: bytes, wa: bytes, *,
          source_sha256: str = SOURCE_SHA256) -> tuple[bytes, bytes, dict]:
    """Instala a exibição em cópias, dentro das janelas do executável auditado."""
    if hashlib.sha256(original_exe).hexdigest() != source_sha256:
        raise ModError('Tipo God: SLUS de origem fora do perfil Drop x15.')
    if (len(original_exe) != len(exe) or inspect(original_exe)['status'] != 'original'
            or inspect(exe)['status'] != 'original'):
        raise ModError('Tipo God: código ou banco de nomes com assinatura divergente.')

    pixels = _god_pixels(wa)
    old_pixels = _pixels(wa)
    if old_pixels != [b'\0' * 8] * HEIGHT:
        raise ModError('Tipo God: célula 16x16 na textura do boot está ocupada.')

    out_exe = bytearray(exe)
    for offset, _, after in REGIONS:
        out_exe[offset:offset + len(after)] = after
    out_wa = bytearray(wa)
    for offset, row in zip(ICON_ROWS, pixels):
        out_wa[offset:offset + len(row)] = row

    result_exe, result_wa = bytes(out_exe), bytes(out_wa)
    report = inspect(result_exe, result_wa)
    if report['status'] != 'aplicado':
        raise ModError('Tipo God: falha na conferência do nome ou do ícone.')
    return result_exe, result_wa, report
