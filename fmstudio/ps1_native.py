"""Efeitos nativos graváveis no jogo PS1: rituais, traps e terreno.

Esses três grupos reutilizam dados que o motor stock já lê. Não criam
handlers MIPS novos. Cada alteração requer formato conhecido e conserva
arquivos/tabelas/offsets originais.
"""
from __future__ import annotations

import struct
from .core import ModError
from .tables import (
    CARD_COUNT, EXE_DELTA, RITUAL_OFF, RITUAL_LEN,
    TERRAIN_COPIES, TERRAIN_STRIDE, WA_TERRAIN_BASE,
)

TRAP_IDS = (681, 682, 683, 684, 685, 686)
TRAP_ADDRESS = 0x8009AF24
TRAP_RETAIL = bytes((5, 10, 15, 20, 30, 255))
TERRAIN_ADDRESS = 0x800909D4
TERRAIN_COUNT = 6
MONSTER_TYPES = 20
TERRAIN_LENGTH = TERRAIN_COUNT * MONSTER_TYPES


def _number(value, label: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ModError(f'{label} precisa ser número inteiro.') from exc
    if not minimum <= number <= maximum:
        raise ModError(f'{label} precisa estar entre {minimum} e {maximum}.')
    return number


def _ritual_records(block: bytes):
    if len(block) != RITUAL_LEN:
        raise ModError('Tamanho da tabela de rituais não reconhecido.')
    offset = 0
    records = {}
    while offset + 2 <= RITUAL_LEN:
        card = struct.unpack_from('<H', block, offset)[0]
        if card == 0:
            return records, offset + 2
        if offset + 10 > RITUAL_LEN:
            raise ModError('Registro de Ritual ultrapassa a área reservada.')
        values = struct.unpack_from('<5H', block, offset)
        if (card > CARD_COUNT or card in records
                or any(value > CARD_COUNT for value in values[1:])):
            raise ModError('Tabela de rituais contém registros incompatíveis.')
        records[card] = (offset, tuple(values[1:]))
        offset += 10
    raise ModError('Tabela de rituais não tem terminador.')


def read_rituals(wa: bytes) -> dict[int, tuple[int, int, int, int]]:
    start = WA_TERRAIN_BASE + RITUAL_OFF
    if start + RITUAL_LEN > len(wa):
        raise ModError('WA_MRG.MRG não contém tabela de Ritual completa.')
    records, _ = _ritual_records(wa[start:start + RITUAL_LEN])
    return {card: values for card, (_, values) in records.items()}


def patch_rituals(wa: bytes, changes: dict) -> tuple[bytes, list[dict]]:
    """Altera somente os 8 bytes de uma receita original nas sete cópias.

    Mantém o ID do Ritual, número de registros, terminador e padding intactos.
    """
    if not changes:
        return wa, []
    source_blocks = []
    for terrain in range(TERRAIN_COPIES):
        start = WA_TERRAIN_BASE + terrain * TERRAIN_STRIDE + RITUAL_OFF
        if start + RITUAL_LEN > len(wa):
            raise ModError('WA_MRG.MRG não contém todas as tabelas Ritual.')
        source_blocks.append(wa[start:start + RITUAL_LEN])
    if any(block != source_blocks[0] for block in source_blocks[1:]):
        raise ModError('Rituais diferem entre terrenos; patch bloqueado.')

    records, _ = _ritual_records(source_blocks[0])
    plan = {}
    for key, values in changes.items():
        ritual = _number(key, 'ID do Ritual', 1, CARD_COUNT)
        if not isinstance(values, (list, tuple)) or len(values) != 4:
            raise ModError('Ritual precisa de exatamente 3 tributos e 1 resultado.')
        recipe = tuple(_number(v, 'ID do material/resultado', 1, CARD_COUNT)
                       for v in values)
        if ritual not in records:
            raise ModError(f'Ritual #{ritual:03d} não existe na tabela original; '
                           'adicionar novos rituais exige ampliação específica.')
        plan[ritual] = recipe

    original = source_blocks[0]
    changed = []
    edited = bytearray(wa)
    for ritual, recipe in sorted(plan.items()):
        offset, was = records[ritual]
        if recipe == was:
            continue
        for terrain in range(TERRAIN_COPIES):
            absolute = WA_TERRAIN_BASE + terrain * TERRAIN_STRIDE + RITUAL_OFF + offset + 2
            edited[absolute:absolute + 8] = struct.pack('<4H', *recipe)
        changed.append({'ritual_id': ritual, 'antes': list(was),
                        'depois': list(recipe), 'copias': TERRAIN_COPIES})
    if not changed:
        return wa, []
    modified = bytes(edited)
    for terrain in range(TERRAIN_COPIES):
        at = WA_TERRAIN_BASE + terrain * TERRAIN_STRIDE + RITUAL_OFF
        new = modified[at:at + RITUAL_LEN]
        decoded, _ = _ritual_records(new)
        if len(decoded) != len(records):
            raise ModError('Conferência de rituais falhou: quantidade alterada.')
        for ritual, recipe in plan.items():
            if decoded[ritual][1] != recipe:
                raise ModError('Conferência falhou: receita não corresponde ao projeto.')
    return modified, changed


def read_trap_thresholds(exe: bytes) -> dict[int, int]:
    start = TRAP_ADDRESS - EXE_DELTA
    if start < 0 or start + len(TRAP_IDS) > len(exe):
        raise ModError('SLUS_014.11 é pequeno demais para limiares de Trap.')
    return {trap: int(exe[start + i]) * 100
            for i, trap in enumerate(TRAP_IDS)}


def patch_trap_thresholds(exe: bytes, changes: dict) -> tuple[bytes, list[dict]]:
    """Grava apenas seis bytes documentados, em centenas de ATK.

    Para não aplicar valores em versões cujo motor já foi redirecionado
    para um formato u16 diferente, exige a tabela retail exata na origem.
    """
    if not changes:
        return exe, []
    start = TRAP_ADDRESS - EXE_DELTA
    if start < 0 or start + 6 > len(exe):
        raise ModError('Região dos limiares Trap ausente do executável.')
    if exe[start:start + 6] != TRAP_RETAIL:
        raise ModError('Limiar Trap diferente do layout original (6 bytes). '
                       'Esta versão pode usar uma rotina MIPS modificada; '
                       'patch automático bloqueado.')
    values = list(TRAP_RETAIL)
    for key, value in changes.items():
        trap = _number(key, 'ID de Trap', 681, 686)
        threshold = _number(value, 'ATK que ativa Trap', 100, 25500)
        if threshold % 100:
            raise ModError('Limiar de Trap precisa ser múltiplo de 100.')
        values[trap - 681] = threshold // 100
    if values != sorted(values):
        raise ModError('Os seis limiares precisam ficar em ordem crescente. '
                       'A rotina seleciona as armadilhas por faixa de ATK.')
    output = bytearray(exe)
    output[start:start + 6] = bytes(values)
    mods = [{'trap_id':card, 'antes':int(TRAP_RETAIL[i]) * 100,
             'depois':values[i] * 100}
            for i,card in enumerate(TRAP_IDS)
            if values[i] != TRAP_RETAIL[i]]
    return (bytes(output), mods) if mods else (exe, [])


def read_terrain_boosts(exe: bytes) -> dict[tuple[int, int], int]:
    """(terreno 1-6, tipo 0-19) -> pontos de bônus (ATK/DEF)."""
    start = TERRAIN_ADDRESS - EXE_DELTA
    if start < 0 or start + TERRAIN_LENGTH > len(exe):
        raise ModError('Tabela de bônus de terreno ausente do SLUS.')
    table = exe[start:start + TERRAIN_LENGTH]
    return {(terrain, type_id): struct.unpack('<b', table[type_id * 6 + terrain - 1:type_id * 6 + terrain])[0] * 10
            for type_id in range(MONSTER_TYPES) for terrain in range(1, 7)}


def patch_terrain_boosts(exe: bytes, changes: dict) -> tuple[bytes, list[dict]]:
    """Grava a tabela stock de bônus por terreno/tipo (uma unidade = 10 pontos).

    Rejeita bases cuja tabela não se pareça com a stock, porque mods podem
    redirecionar Duel_GetTerrainBoost para outra região.
    """
    if not changes:
        return exe, []
    start = TERRAIN_ADDRESS - EXE_DELTA
    if start < 0 or start + TERRAIN_LENGTH > len(exe):
        raise ModError('Tabela de campo não foi encontrada no executável.')
    old = exe[start:start + TERRAIN_LENGTH]
    signed = struct.unpack('<120b', old)
    if not all(v in (-50, 0, 50) for v in signed) or not any(signed):
        raise ModError('Tabela de terreno não corresponde ao padrão ±500 original. '
                       'MOD pode utilizar tabela própria; patch bloqueado.')
    clean = {}
    for key,value in changes.items():
        if not isinstance(key, str) or ':' not in key:
            raise ModError('Terreno/tipo deve ser informado como "terreno:tipo".')
        left,right = key.split(':',1)
        terrain = _number(left,'Terreno',1,6)
        type_id = _number(right,'Tipo',0,19)
        bonus = _number(value,'Bônus do terreno',-1200,1200)
        if bonus % 10:
            raise ModError('Bônus do campo precisa ser múltiplo de 10.')
        clean[(terrain,type_id)] = bonus
    modified = bytearray(exe)
    done=[]
    for (terrain,type_id),bonus in sorted(clean.items()):
        at = start + type_id * 6 + terrain - 1
        was = struct.unpack_from('<b',exe,at)[0] * 10
        if was == bonus:
            continue
        struct.pack_into('<b',modified,at,bonus // 10)
        done.append({'terreno':terrain,'tipo_id':type_id,'antes':was,'depois':bonus})
    return (bytes(modified),done) if done else (exe,[])
