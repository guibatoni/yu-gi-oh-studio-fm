"""Economia PS1 do Studio: visibilidade do baú, preços e estrelas por vitória.

Nenhuma configuração é aplicada à imagem original; patches somente em cópia
com proveniência validada e assinaturas de instruções do SLUS Drop x15.
"""
from __future__ import annotations

import struct

from .core import ModError
from .tables import CARD_COUNT, EXE_DELTA, PASSWORD_BASE

CHEST_VISIBILITY_KEY = "ps1_chest_show_all"
PASSWORD_PRICES_KEY = "ps1_password_prices"
DUEL_STARS_KEY = "ps1_starchips_per_win"
PRICE_LIMIT = 999_999
STAR_LIMIT = 255  # O resultado armazena as estrelas ganhas em um byte.
REWARD_PC = 0x80021C34
REWARD_ORIGINAL = 0x24420001  # addiu v0,v0,1 (rank + 1)
REWARD_STORE_PC = 0x80021C38
REWARD_STORE = 0xA062003A  # sb v0,0x3A(v1)
REWARD_LOAD_PC = 0x80021ED4
REWARD_LOAD = 0x9043003A  # lbu v1,0x3A(v0)


def _validate_price(cid, amount):
    if isinstance(cid, bool) or isinstance(amount, bool):
        raise ModError("ID e custo precisam ser números inteiros.")
    try:
        number, cost = int(cid), int(amount)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ModError("ID da carta e custo em estrelas precisam ser inteiros.") from exc
    if str(number) != str(cid).strip() and not isinstance(cid, int):
        raise ModError("ID de carta inválido.")
    if str(cost) != str(amount).strip() and not isinstance(amount, int):
        raise ModError("Custo em estrelas deve ser um número inteiro sem decimais.")
    if not 1 <= number <= 740:
        raise ModError("Preços PS1 aceitam cartas de ID 1 a 740.")
    if not 0 <= cost <= PRICE_LIMIT:
        raise ModError(f"Custo em estrelas deve ficar entre 0 e {PRICE_LIMIT:,}.")
    return number, cost


def price_overrides(project):
    raw = project.metadata.get(PASSWORD_PRICES_KEY, {})
    if not isinstance(raw, dict):
        raise ModError("A tabela de custos no projeto está corrompida.")
    result = {}
    for cid, value in raw.items():
        number, amount = _validate_price(cid, value)
        result[number] = amount
    return result


def fixed_win_reward(project):
    raw = project.metadata.get(DUEL_STARS_KEY)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= STAR_LIMIT:
        raise ModError(f"Estrelas por vitória devem ficar entre 1 e {STAR_LIMIT}.")
    return raw


def chest_show_all(project):
    value = project.metadata.get(CHEST_VISIBILITY_KEY, True)
    if type(value) is not bool:
        raise ModError("A opção de visibilidade do baú está inválida.")
    return value


def _save_change(project, updates):
    before = project.metadata
    project.metadata = {**before, **updates}
    try:
        project.save()
    except Exception:
        project.metadata = before
        raise


def set_chest_show_all(project, enabled):
    if type(enabled) is not bool:
        raise ModError("Escolha ativar ou desativar a visualização do baú.")
    _save_change(project, {CHEST_VISIBILITY_KEY: enabled})


def set_password_price(project, cid, amount):
    number, cost = _validate_price(cid, amount)
    if number not in project.cards or project.cards[number].get("virtual") and number <= CARD_COUNT:
        raise ModError(f"Carta #{number} indisponível para Password no PS1.")
    raw = price_overrides(project)
    raw[number] = cost
    _save_change(project, {PASSWORD_PRICES_KEY: {str(k): v for k, v in sorted(raw.items())}})


def reset_password_price(project, cid):
    number = int(cid)
    raw = price_overrides(project)
    raw.pop(number, None)
    _save_change(project, {PASSWORD_PRICES_KEY: {str(k): v for k, v in sorted(raw.items())}})


def set_win_reward(project, stars):
    if stars is not None:
        if isinstance(stars, bool) or not isinstance(stars, int) or not 1 <= stars <= STAR_LIMIT:
            raise ModError(f"Estrelas fixas por vitória: use 1 a {STAR_LIMIT}.")
    _save_change(project, {DUEL_STARS_KEY: stars})


def apply_password_prices(wa, prices, *, card_capacity=CARD_COUNT):
    """Atualiza somente o u32 de preço; não modifica o password BCD adjacente."""
    if not prices:
        return wa, []
    out = bytearray(wa)
    changed = []
    for cid, price in sorted(prices.items()):
        number, cost = _validate_price(cid, price)
        if number > card_capacity:
            raise ModError(f"Carta #{number} não possui registro Password neste WA.")
        offset = PASSWORD_BASE + number * 8
        if offset + 8 > len(out):
            raise ModError(f"WA_MRG truncado na tabela Password #{number}.")
        before, password = struct.unpack_from("<II", out, offset)
        if before == 0xFFFFFFFF or password == 0xFFFFFFFF:
            raise ModError(f"Password #{number} é um registro terminador; gravação recusada.")
        struct.pack_into("<I", out, offset, cost)
        changed.append({"id": number, "antes": before, "estrelas": cost, "offset_wa": offset})
    return bytes(out), changed


def read_prices(wa, ids, *, expanded=False):
    """Lê custos no disco final (18 miniaturas expandem os offsets do WA)."""
    offset_shift = (740 - CARD_COUNT) * 2048 if expanded else 0
    result = {}
    for cid in ids:
        cid = int(cid)
        offset = PASSWORD_BASE + cid * 8 + offset_shift
        if not 1 <= cid <= (740 if expanded else CARD_COUNT) or offset + 8 > len(wa):
            raise ModError(f"Registro de estrelas da carta #{cid} ausente do BIN.")
        result[cid] = struct.unpack_from("<I", wa, offset)[0]
    return result


def _reward_offset(exe):
    off = REWARD_PC - EXE_DELTA
    if not exe.startswith(b"PS-X EXE") or off + 4 > len(exe):
        raise ModError("O executável não contém o ponto de estrelas da vitória.")
    if struct.unpack_from("<I", exe, REWARD_STORE_PC - EXE_DELTA)[0] != REWARD_STORE:
        raise ModError("O resultado do duelo diverge do motor Drop x15 (store).")
    if struct.unpack_from("<I", exe, REWARD_LOAD_PC - EXE_DELTA)[0] != REWARD_LOAD:
        raise ModError("O resultado do duelo diverge do motor Drop x15 (load).")
    return off


def reward_status(exe):
    offset = _reward_offset(exe)
    word = struct.unpack_from("<I", exe, offset)[0]
    if word == REWARD_ORIGINAL:
        return {"status": "original_por_rank", "estrelas": None}
    if word & 0xFFFF0000 == 0x24020000 and 1 <= (word & 0xFFFF) <= STAR_LIMIT:
        return {"status": "fixo", "estrelas": word & 0xFFFF}
    return {"status": "divergente", "opcode": f"0x{word:08X}", "estrelas": None}


def patch_win_reward(exe, stars):
    """Substitui apenas addiu v0,v0,1 por addiu v0,zero,N.

    O jogo escreve o resultado no byte +0x3A e depois soma esse byte ao
    saldo de Star Chips. Limite explícito 255 para evitar overflow de 8 bits.
    """
    offset = _reward_offset(exe)
    before = reward_status(exe)
    if before["status"] == "divergente":
        raise ModError("A instrução de ganho de estrelas não corresponde ao Drop x15.")
    if stars is None:
        if before["status"] != "original_por_rank":
            raise ModError("Restaurar ganho por rank exige BIN original não modificado.")
        return exe, before
    if isinstance(stars, bool) or not isinstance(stars, int) or not 1 <= stars <= STAR_LIMIT:
        raise ModError(f"Estrelas fixas por vitória exigem um valor entre 1 e {STAR_LIMIT}.")
    if before["status"] == "fixo" and before["estrelas"] != stars:
        raise ModError("O BIN já contém ganho de estrelas diferente do solicitado.")
    patched = bytearray(exe)
    struct.pack_into("<I", patched, offset, 0x24020000 | stars)
    return bytes(patched), reward_status(patched)
