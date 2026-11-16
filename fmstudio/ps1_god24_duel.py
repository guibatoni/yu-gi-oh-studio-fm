"""God24 duel routing investigation (read-only).

Retail DuelScene_UpdateHandActions treats kinds >=20 as non-monster.
The diagnostic inspects loaded SLUS and never rewrites it.
"""
from __future__ import annotations
import hashlib
import struct
from .tables import EXE_DELTA

REGIONS = {
    "mao": ("DuelScene_UpdateHandActions", 0x8001BD88, 0x14B8),
    "fileira": ("func_8001B938", 0x8001B938, 0x1B8),
    "uso_carta_especial": ("DuelScene_UpdateCardUse", 0x80019608, 0x400),
    "colocacao": ("DuelScene_UpdateCardPlacement", 0x80019D18, 0x13B4),
    "campo": ("DuelScene_UpdateFieldActions", 0x8001D670, 0x1600),
    "registro": ("Duel_SetupCardRecord", 0x800249E0, 0x23C),
}


def _instruction(word, pc):
    op = word >> 26
    rs, rt = (word >> 21) & 31, (word >> 16) & 31
    immediate = word & 65535
    signed = immediate if immediate < 32768 else immediate - 65536
    out = {"pc": f"0x{pc:08X}", "word": f"0x{word:08X}",
           "rs": rs, "rt": rt, "kind": "other"}
    if op in (10, 11):
        out.update(kind="slti" if op == 10 else "sltiu", imm=signed)
    elif op in (8, 9):
        out.update(kind="addi" if op == 8 else "addiu", imm=signed)
    elif op == 12:
        out.update(kind="andi", imm=immediate)
    elif op == 0 and (word & 63) == 2:
        out.update(kind="srl", shamt=(word >> 6) & 31,
                   rd=(word >> 11) & 31)
    elif op in (4, 5, 6, 7):
        out.update(kind={4:"beq",5:"bne",6:"blez",7:"bgtz"}[op],
                   target=f"0x{((pc+4+(signed << 2)) & 0xFFFFFFFF):08X}",
                   delay_slot=True)
    elif op in (2, 3):
        out.update(kind="jal" if op == 3 else "j",
                   target=f"0x{(((pc+4)&0xF0000000)|((word & 0x3FFFFFF) << 2)):08X}",
                   delay_slot=True)
    elif word == 0:
        out["kind"] = "nop"
    return out


def _candidate(item):
    kind, imm = item["kind"], item.get("imm")
    if kind in ("slti", "sltiu") and imm in (20,21,22,23,24,25):
        return "limite_monstro" if imm == 20 else "tipo_especial"
    if kind in ("addiu", "addi") and imm in (-20,-21,-22,-23,-24):
        return "comparacao_por_subtracao"
    if kind == "andi" and imm == 31:
        return "mascara_tipo_5_bits"
    if kind == "srl" and item.get("shamt") == 26:
        return "extracao_tipo_5_bits"
    return None


def analyze_god24_duel(exe: bytes, maximum_per_region: int = 48) -> dict:
    report = {
        "status": "somente_leitura",
        "tipo_deus": 24,
        "tipo_24_tratado_como_monstro_no_motor_retail": False,
        "patch_mips_duelo_aplicado": False,
        "tipo_carta_original_preservado": True,
        "rotinas": {},
        "alerta": "Mudar 20 para 25 transforma Magia, Equip, Trap e Ritual em monstros; "
                  "o patch exige condicao exclusiva para God24 e validacao no ePSXe."
    }
    if len(exe) < 0x800 or exe[:8] != b"PS-X EXE":
        report["status"] = "slus_invalido"
        return report
    t_addr, t_size = struct.unpack_from("<II", exe, 0x18)
    if (t_addr != EXE_DELTA + 0x800 or not t_size or t_size % 4
            or t_size + 0x800 > len(exe)):
        report["status"] = "segmento_invalido"
        return report
    report["sha256_slus"] = hashlib.sha256(exe).hexdigest()
    for label, (name, addr, size) in REGIONS.items():
        offset = addr - EXE_DELTA
        row = {"funcao": name, "pc": f"0x{addr:08X}",
               "offset_slus": f"0x{offset:X}", "encontrados": 0,
               "amostras": []}
        if offset < 0x800 or offset + size > t_size + 0x800:
            row["status"] = "fora_segmento"
            report["rotinas"][label] = row
            continue
        block = exe[offset:offset+size]
        words = struct.unpack("<" + str(size//4) + "I", block)
        row["sha256_regiao"] = hashlib.sha256(block).hexdigest()
        row["status"] = "amostrado_sem_patch"
        for index, word in enumerate(words):
            decoded = _instruction(word, addr+index*4)
            category = _candidate(decoded)
            if category is None:
                continue
            row["encontrados"] += 1
            if len(row["amostras"]) >= maximum_per_region:
                continue
            near = []
            for j in range(max(0,index-12),min(len(words),index+13)):
                entry = _instruction(words[j],addr+j*4)
                entry["offset_slus"] = f"0x{offset+j*4:X}"
                entry["foco"] = j==index
                near.append(entry)
            row["amostras"].append({
                "categoria": category,
                "instrucao": decoded,
                "contexto_mips": near
            })
        row["truncado"] = row["encontrados"] > len(row["amostras"])
        report["rotinas"][label] = row
    report["proximo_patch"] = (
        "Use Verificar BIN/CUE na cópia gerada para conferir os pontos "
        "da mão, fileira, colocação, confirmação e exibição.")
    return report
