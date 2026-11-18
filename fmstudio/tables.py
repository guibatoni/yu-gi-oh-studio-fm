"""Leitor SOMENTE LEITURA das tabelas da edição USA SLUS-01411.

Não grava SLUS, WA_MRG ou imagens de disco. Os offsets foram documentados por
pesquisas independentes de decompilação e pelo FM Editor.
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

CARD_COUNT = 722
DUELIST_COUNT = 40
POOL_TOTAL = 2048
EXE_DELTA = 0x8000F800
STATS_ADDR = 0x801D4244
LEVEL_ADDR = 0x801D5332
WA_TERRAIN_BASE = 0xB63000
TERRAIN_STRIDE = 0x75800
TERRAIN_COPIES = 7
FUSION_OFF, FUSION_LEN = 0x24800, 0x10000
EQUIP_OFF, EQUIP_LEN = 0x22000, 0x2800
RITUAL_OFF, RITUAL_LEN = 0x34800, 0x800
DUELIST_BASE = 0xE99800
DUELIST_STRIDE = 0x1800
POOL_OFFSETS = {"deck": 0x000, "pow": 0x5B4, "bcd": 0xB68, "tec": 0x111C}
STARTER_OFFSETS = (0xF92BD4, 0xFBDBD4)
STARTER_STRIDE = 0x5B8
STARTER_POOLS = 7
STARTER_SIZE = STARTER_STRIDE * STARTER_POOLS
DECK_SIZE = 40
PASSWORD_BASE = 0xFB9800
TYPE_NAMES = (
    "Dragon", "Spellcaster", "Zombie", "Warrior", "Beast-Warrior", "Beast",
    "Winged Beast", "Fiend", "Fairy", "Insect", "Dinosaur", "Reptile", "Fish",
    "Sea Serpent", "Machine", "Thunder", "Aqua", "Pyro", "Rock", "Plant",
    "Magic", "Trap", "Ritual", "Equip", "God",
)
ATTR_NAMES = ("Light", "Dark", "Earth", "Water", "Fire", "Wind")
RETAIL_STAR_NAMES = ("", "Mars", "Jupiter", "Saturn", "Uranus", "Pluto", "Neptune", "Mercury", "Sun", "Moon", "Venus")
# 11–15 may occur in imported data. Preserve them as reserved values.
SUPREME = 16
STAR_NAMES = RETAIL_STAR_NAMES + ("",) * 5 + ("Supreme",)
# Nomes da grade retail, documentados externamente; NÃO decodificados desta imagem.
DUELIST_NAMES_REFERENCE = (
    "Unused", "Simon Muran", "Teana", "Jono", "Villager 1", "Villager 2", "Villager 3", "Seto", "Heishin",
    "Rex Raptor", "Weevil Underwood", "Mai Valentine", "Bandit Keith", "Shadi", "Yami Bakura", "Pegasus",
    "Isis", "Kaiba", "Mage Soldier", "Jono 2nd", "Teana 2nd", "Ocean Mage", "High Mage Secmeton",
    "Forest Mage", "High Mage Anubisius", "Mountain Mage", "High Mage Atenza", "Desert Mage",
    "High Mage Martis", "Meadow Mage", "High Mage Kepura", "Labyrinth Mage", "Seto 2nd", "Guardian Sebek",
    "Guardian Neku", "Heishin 2nd", "Seto 3rd", "DarkNite", "Nitemare", "Duel Master K"
)


def _need(data: bytes, offset: int, size: int, description: str) -> None:
    if offset < 0 or offset + size > len(data):
        raise ValueError(f"{description}: intervalo 0x{offset:X}..0x{offset+size:X} excede arquivo de {len(data)} bytes")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def decode_cards(slus: bytes, *, capacity: int = CARD_COUNT, level_address: int = LEVEL_ADDR) -> tuple[list[dict], list[str]]:
    if slus[:8] != b"PS-X EXE":
        raise ValueError("SLUS_014.11 não possui cabeçalho PS-X EXE válido")
    first = STATS_ADDR - EXE_DELTA
    _need(slus, first, capacity * 4, "tabela de estatísticas")
    _need(slus, level_address - EXE_DELTA + capacity, 1, "tabela de níveis")
    cards, notes = [], []
    for cid in range(1, capacity + 1):
        raw = struct.unpack_from("<I", slus, first + (cid - 1) * 4)[0]
        lv_attr = slus[level_address - EXE_DELTA + cid]
        type_id, attr = (raw >> 26) & 31, lv_attr >> 4
        s1, s2 = (raw >> 22) & 15, (raw >> 18) & 15
        cards.append({
            "id": cid, "ataque": (raw & 511) * 10, "defesa": ((raw >> 9) & 511) * 10,
            "tipo_id": type_id, "tipo_referencia": TYPE_NAMES[type_id] if type_id < len(TYPE_NAMES) else "(não mapeado)",
            "atributo_id": attr, "atributo_referencia": ATTR_NAMES[attr] if attr < len(ATTR_NAMES) else "(não mapeado)",
            "nivel": lv_attr & 15, "guardian_1_id": s1,
            "guardian_1_referencia": RETAIL_STAR_NAMES[s1] if s1 < len(RETAIL_STAR_NAMES) else "(não mapeado)",
            "guardian_2_id": s2, "guardian_2_referencia": RETAIL_STAR_NAMES[s2] if s2 < len(RETAIL_STAR_NAMES) else "(não mapeado)",
            "valor_hex": f"{raw:08X}", "offset_no_slus": f"0x{first + (cid - 1) * 4:X}",
        })
    weird = sum(1 for c in cards if c["tipo_id"] > 23 or c["atributo_id"] > 5)
    if weird:
        notes.append(f"{weird} carta(s) com tipo/atributo fora do catálogo retail; pode ser modificação ou mapeamento diferente")
    return cards, notes


def decode_fusions(table: bytes) -> tuple[list[dict], int]:
    _need(table, 0, (CARD_COUNT + 1) * 2, "índice de fusões")
    pairs: dict[tuple[int, int], tuple[int, bool]] = {}
    for a in range(CARD_COUNT + 1):
        off = struct.unpack_from("<H", table, a * 2)[0]
        if not off or off >= len(table):
            continue
        p = off
        count = table[p]
        if count == 0:
            if p + 1 >= len(table):
                continue
            count = 0x1FF - table[p + 1]
            p += 1
        p += 1
        while count > 0 and p + 5 <= len(table):
            g = table[p]
            for k, (sp, sr) in enumerate(((8, 6), (4, 2))):
                partner = ((g << sp) & 0x300) | table[p + 1 + 2 * k]
                result = ((g << sr) & 0x300) | table[p + 2 + 2 * k]
                if not (1 <= partner <= CARD_COUNT and 1 <= result <= CARD_COUNT):
                    continue
                key = (min(a, partner), max(a, partner))
                if partner < a or key in pairs:
                    continue
                # Em tabelas retail, a segunda combinação em grupos ímpares pode
                # ser uma leitura excedente do motor, não receita intencional.
                pairs[key] = (result, k == 1 and count == 1)
            p += 5
            count -= 2
    rows = [
        {"material_1": a, "material_2": b, "resultado": result, "possivel_glitch": int(glitch)}
        for (a, b), (result, glitch) in sorted(pairs.items())
    ]
    return rows, sum(r["possivel_glitch"] for r in rows)


def decode_equips(table: bytes) -> list[dict]:
    rows, seen, p = [], set(), 0
    while p + 4 <= len(table):
        equip, n = struct.unpack_from("<HH", table, p)
        if equip == 0:
            break
        p += 4
        if p + n * 2 > len(table):
            raise ValueError("tabela de equipamentos: registro ultrapassa o fim do bloco")
        if equip not in seen:
            seen.add(equip)
            for i in range(n):
                monster = struct.unpack_from("<H", table, p + 2*i)[0]
                if monster:
                    rows.append({"equipamento_id": equip, "monstro_id": monster})
        p += n * 2
    return rows


def decode_rituals(table: bytes) -> list[dict]:
    rows, seen = [], set()
    for p in range(0, len(table) - 9, 10):
        ritual, a, b, c, result = struct.unpack_from("<5H", table, p)
        if ritual == 0:
            break
        if ritual not in seen:
            rows.append({"ritual_id": ritual, "tributo_1": a, "tributo_2": b, "tributo_3": c, "resultado": result})
            seen.add(ritual)
    return rows


def decode_pools(wa: bytes) -> tuple[list[dict], list[dict], list[str]]:
    _need(wa, DUELIST_BASE, DUELIST_STRIDE * DUELIST_COUNT, "blocos de duelistas")
    rows, summaries, notes = [], [], []
    for d in range(DUELIST_COUNT):
        for kind, off in POOL_OFFSETS.items():
            at = DUELIST_BASE + d * DUELIST_STRIDE + off
            weights = struct.unpack_from("<722H", wa, at)
            total = sum(weights)
            positive = sum(w > 0 for w in weights)
            summaries.append({"duelista_id": d, "duelista_nome_referencia": DUELIST_NAMES_REFERENCE[d],
                              "grupo": kind, "peso_total": total, "cartas_com_peso": positive,
                              "total_esperado_retail": POOL_TOTAL})
            if total != POOL_TOTAL:
                notes.append(f"duelista {d} / grupo {kind}: soma dos pesos {total} (retail: {POOL_TOTAL})")
            for cid, weight in enumerate(weights, 1):
                if weight:
                    rows.append({"duelista_id": d, "duelista_nome_referencia": DUELIST_NAMES_REFERENCE[d],
                                 "grupo": kind, "carta_id": cid, "peso": weight,
                                 "fracao_teorica_sobre_2048_pct": round(100 * weight / POOL_TOTAL, 5)})
    return rows, summaries, notes


def decode_passwords(wa: bytes) -> list[dict]:
    _need(wa, PASSWORD_BASE, (CARD_COUNT + 1) * 8, "tabela de passwords")
    rows = []
    for cid in range(1, CARD_COUNT + 1):
        cost, encoded = struct.unpack_from("<II", wa, PASSWORD_BASE + cid * 8)
        bcd = all(((encoded >> (4 * n)) & 15) <= 9 for n in range(8))
        pwd = f"{encoded:08x}" if encoded != 0xFFFFFFFE and bcd else ""
        rows.append({"carta_id": cid, "custo_starchips": cost, "password": pwd,
                     "password_valido_bcd": int(bcd and encoded != 0xFFFFFFFE)})
    return rows


def decode_starters(wa: bytes) -> list[dict]:
    """Read the seven weighted Name Entry rows when both disc copies agree."""
    first, second = STARTER_OFFSETS
    block = wa[first:first + STARTER_SIZE]
    if len(block) != STARTER_SIZE or block != wa[second:second + STARTER_SIZE]:
        return []
    rows = []
    for pool in range(STARTER_POOLS):
        draws, *weights = struct.unpack_from(f'<{CARD_COUNT + 1}H', block, pool * STARTER_STRIDE)
        if draws > DECK_SIZE or weights[-2:] != [0, 0] or (draws and sum(weights) != POOL_TOTAL):
            return []
        rows.extend({'grupo': pool, 'compras': draws, 'carta_id': cid, 'peso': weight}
                    for cid, weight in enumerate(weights, 1) if weight)
    if sum({row['grupo']: row['compras'] for row in rows}.values()) != DECK_SIZE:
        return []
    return rows


def decode_all(slus: bytes, wa: bytes) -> tuple[dict, list[str]]:
    cards, notes = decode_cards(slus)
    _need(wa, WA_TERRAIN_BASE, (TERRAIN_COPIES - 1) * TERRAIN_STRIDE + RITUAL_OFF + RITUAL_LEN, "pacotes de campo")
    start = WA_TERRAIN_BASE
    fusion = wa[start + FUSION_OFF:start + FUSION_OFF + FUSION_LEN]
    equip = wa[start + EQUIP_OFF:start + EQUIP_OFF + EQUIP_LEN]
    ritual = wa[start + RITUAL_OFF:start + RITUAL_OFF + RITUAL_LEN]
    for copy in range(1, TERRAIN_COPIES):
        at = WA_TERRAIN_BASE + copy * TERRAIN_STRIDE
        for key, off, blob in (("fusões", FUSION_OFF, fusion), ("equips", EQUIP_OFF, equip), ("rituais", RITUAL_OFF, ritual)):
            if wa[at + off:at + off + len(blob)] != blob:
                notes.append(f"cópia {copy} do campo apresenta tabela diferente de {key}; CSV reflete a cópia 0")
    fusions, glitch_count = decode_fusions(fusion)
    equips, rituals = decode_equips(equip), decode_rituals(ritual)
    pools, pool_summary, pool_notes = decode_pools(wa)
    notes.extend(pool_notes)
    passwords = decode_passwords(wa)
    if glitch_count:
        notes.append(f"{glitch_count} fusões sinalizadas como possível leitura excedente (glitch); revisar antes de editar")
    return {"cartas": cards, "fusoes": fusions, "equipamentos": equips,
            "rituais": rituals, "decks_drops": pools,
            "resumo_duelistas": pool_summary, "decks_iniciais": decode_starters(wa),
            "senhas": passwords}, notes
