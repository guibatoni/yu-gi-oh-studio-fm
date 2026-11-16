"""Teste opt-in de God24 na seleção da mão do duelo (PS1 MIPS).

A v1.4.18 corrigiu ATK/DEF no baú, mas God24 ainda entra no fluxo de
carta especial. Este patch modifica SOMENTE 4 máscaras de tipo na função
DuelScene_UpdateHandActions. Tipo gravado no SLUS permanece 24; nesta
rotina a máscara local normaliza 24 -> 16 antes do teste <20.
A CLASSIFICAÇÃO monstro/não-monstro de 0..23 não muda; os tipos 8..15
são normalizados TEMPORARIAMENTE para 0..7 dentro do registrador local.
Isso deve ser testado no emulador quanto a efeitos indiretos.
25..31 ficam expressamente proibidos.

NÃO modifica DuelScene_UpdateCardPlacement nem afirma invocação,
ataque ou fusão funcionando no ePSXe.
"""
from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterable

from .core import ModError
from .ps1_god24_chest import SOURCE_SHA256

OLD_LOW_BITS = 0x1F
NEW_LOW_BITS = 0x17
SITES = (
    # (offset REAL no SLUS, janela de 5 instruções iniciada em offset-8, nome)
    # Endereço RAM = offset SLUS + EXE_DELTA (0x8000F800).
    # A v1.4.20 omitiu 0x800 (cabeçalho PS-X EXE) nesses quatro offsets.
    (0xCA14, (0x00000000, 0x00021683, 0x3042001F,
              0x28420014, 0x10400009), "decisao_inicial_da_mao"),
    (0xCC00, (0x00000000, 0x00021683, 0x3050001F,
              0x2A020014, 0x1440000F), "confirmar_carta_na_mao"),
    (0xD1FC, (0x00000000, 0x00021683, 0x3050001F,
              0x2A020014, 0x14400003), "decisao_apos_escolha"),
    (0xD534, (0x00000000, 0x00021683, 0x3050001F,
              0x2A020014, 0x1440001D), "selecionar_colocacao"),
)


def _new_word(old: int) -> int:
    assert old & 0xFFFF == OLD_LOW_BITS
    return (old & 0xFFFF0000) | NEW_LOW_BITS


def inspect(exe: bytes) -> dict:
    points = []
    for offset, context, name in SITES:
        start = offset - 8
        if exe[:8] != b"PS-X EXE" or start < 0 or start + 20 > len(exe):
            status = "fora_do_arquivo"
            word = None
        else:
            words = struct.unpack_from("<5I", exe, start)
            word = words[2]
            if words == context:
                status = "original_sem_patch"
            elif words == context[:2] + (_new_word(context[2]),) + context[3:]:
                status = "patch_presente"
            else:
                status = "sequencia_divergente"
        points.append({
            "rotina": name, "offset_slus": f"0x{offset:X}",
            "estado": status,
            "opcode_original": f"0x{context[2]:08X}",
            "opcode_esperado": f"0x{_new_word(context[2]):08X}",
            "opcode_lido": f"0x{word:08X}" if word is not None else None,
        })
    ok = sum(p["estado"] == "patch_presente" for p in points)
    states = [p["estado"] for p in points]
    if all(x == "patch_presente" for x in states):
        state = "aplicado_4_de_4"
    elif all(x == "original_sem_patch" for x in states):
        state = "nao_aplicado_0_de_4"
    elif all(x in ("patch_presente", "original_sem_patch") for x in states):
        state = f"parcial_{ok}_de_4"
    else:
        state = "sequencia_divergente"
    return {
        "status": state, "quantidade_aplicada": ok, "instrucoes": points,
        "valida_emulador": False, "mips_duelo_parcial": True,
        "alteracao_campo_ou_combate": False,
        "observacao": "A seleção da mão foi modificada no BIN, "
                      "mas a invocação e o combate ainda precisam de teste no ePSXe.",
    }


def apply(original_exe: bytes, edited_exe: bytes,
          card_types: Iterable[int], *,
          source_sha256: str = SOURCE_SHA256) -> tuple[bytes, dict]:
    if (original_exe[:8] != b"PS-X EXE" or edited_exe[:8] != b"PS-X EXE"
            or len(original_exe) != len(edited_exe)):
        raise ModError("God24 mão: SLUS incompatível ou tamanho diferente.")
    if hashlib.sha256(original_exe).hexdigest() != source_sha256:
        raise ModError("God24 mão: SHA-256 da origem não corresponde ao perfil.")
    kinds = list(card_types)
    if (not kinds or 24 not in kinds
            or any(type(k) is not int or not 0 <= k <= 24 for k in kinds)):
        raise ModError("God24 mão: exige God (24) e recusa tipos 25–31.")
    for kind in range(25):
        normalized=kind & NEW_LOW_BITS
        if (normalized < 20) != (kind < 20 or kind == 24):
            raise ModError("God24 mão: a classificação de monstro foi alterada.")
        if kind in (20,21,22,23) and normalized != kind:
            raise ModError("God24 mão: as categorias especiais foram alteradas.")
    original_state=inspect(original_exe)
    edited_state=inspect(edited_exe)
    if (original_state["status"] != "nao_aplicado_0_de_4"
            or edited_state["status"] != "nao_aplicado_0_de_4"):
        conflicting=[
            f"{p['rotina']} {p['offset_slus']}: {p['opcode_lido'] or 'fora do arquivo'}"
            for p in edited_state["instrucoes"]
            if p["estado"]!="original_sem_patch"
        ]
        reason="; ".join(conflicting) or edited_state["status"]
        raise ModError(
            "God24 mão: sequência MIPS original diferente do diagnóstico "
            f"({reason}). Nenhum BIN foi modificado; utilize o mod de origem "
            "validado, não uma imagem de teste já alterada.")
    copy = bytearray(edited_exe)
    changed = set()
    for offset, context, _ in SITES:
        struct.pack_into("<I", copy, offset, _new_word(context[2]))
        changed.update(range(offset, offset + 4))
    report = inspect(bytes(copy))
    if report["status"] != "aplicado_4_de_4":
        raise ModError("God24 mão: falha de releitura dos quatro opcodes.")
    if any(a != b for i, (a, b) in enumerate(zip(copy, edited_exe))
           if i not in changed):
        raise ModError("God24 mão: alteração fora dos quatro opcodes previstos.")
    report.update({
        "status": "aplicado_4_de_4",
        "tipo_no_slus_continua_24": True,
        "classes_originais_0_a_23_inalteradas": True,
        "sem_jumps_ou_delay_slots_alterados": True,
        "objetivo": "Experimentar God24 no caminho de monstro da mão.",
        "invocacao_confirmada_no_epsxe": False,
    })
    return bytes(copy), report
