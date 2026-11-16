"""God24: patch opcional das DUAS comparações de monstro no baú PS1.

O diagnóstico v1.4.14 contém, em ambas as rotinas:
  andi v0,v0,31
  slti v0,v0,20
Somente o ANDI é alterado para máscara 0x17. Isto preserva a
classificação dos tipos 0..23 e faz o 24 passar como monstro. Tipos
25..31 são recusados, pois a máscara classificaria incorretamente
alguns deles. Nenhum delay slot, branch, code cave ou carta é movido.
Não implementa monstro God24 em combate nem desenha novo ícone.
"""
from __future__ import annotations
import hashlib
import struct
from collections.abc import Iterable
from .core import ModError

SOURCE_SHA256='7412689c12618f90144e8b90839f1f47d2813cc20b42675f2506d8e125fa6b03'
OLD=0x3042001F
NEW=0x30420017
SITES=(
    (0x51500,(0x00021683,OLD,0x28420014,0x10400045,0x3C030080),'ATK/DEF do baú'),
    (0x51728,(0x00021683,OLD,0x28420014,0x14400002,0x02C02821),'layout da linha'),
)


def visible_as_monster(kind:int, *, preview:bool=False)->bool:
    return (kind & (0x17 if preview else 0x1F)) < 20


def patch_god24_chest_preview(original_exe:bytes, patched_exe:bytes,
                              card_types:Iterable[int], *,
                              source_sha256:str=SOURCE_SHA256)->tuple[bytes,dict]:
    """Patcher de bytes em memória, sem alterar arquivo de origem."""
    if original_exe[:8]!=b'PS-X EXE' or patched_exe[:8]!=b'PS-X EXE':
        raise ModError('God24 baú: cabeçalho PS-X EXE ausente.')
    if len(original_exe)!=len(patched_exe):
        raise ModError('God24 baú: tamanho do SLUS alterado.')
    actual=hashlib.sha256(original_exe).hexdigest()
    if actual!=source_sha256:
        raise ModError('God24 baú: SHA do SLUS original difere do mod analisado.')
    types=list(card_types)
    if not types or any(type(k) is not int or k<0 or k>24 for k in types):
        raise ModError('God24 baú: tipo 25–31 ou valor inválido. Patch recusado.')
    if 24 not in types:
        raise ModError('God24 baú: não há cartas do tipo 24.')
    for kind in range(25):
        expected=kind<20 or kind==24
        if visible_as_monster(kind,preview=True)!=expected:
            raise ModError('God24 baú: máscara não preserva classificação.')
        if kind<24 and visible_as_monster(kind,preview=True)!=visible_as_monster(kind):
            raise ModError('God24 baú: outros tipos seriam alterados.')
    out=bytearray(patched_exe)
    points=[]
    for offset,context,name in SITES:
        start=offset-4
        if start<0 or start+20>len(out):
            raise ModError(f'God24 baú: {name} fora do SLUS.')
        before=struct.unpack_from('<5I',original_exe,start)
        current=struct.unpack_from('<5I',patched_exe,start)
        if before!=context or current!=context:
            raise ModError(f'God24 baú: assinatura MIPS incorreta em {name}.')
        struct.pack_into('<I',out,offset,NEW)
        points.append({'rotina':name,'offset_slus':f'0x{offset:X}',
                       'antes':f'0x{OLD:08X}','depois':f'0x{NEW:08X}'})
    allowed=set()
    for offset,_,_ in SITES:
        allowed.update(range(offset,offset+4))
        if struct.unpack_from('<I',out,offset)[0]!=NEW:
            raise ModError('God24 baú: falha na releitura de máscara.')
    if any(a!=b for i,(a,b) in enumerate(zip(out,patched_exe)) if i not in allowed):
        raise ModError('God24 baú: alteração fora das máscaras permitidas.')
    return bytes(out),{
        'status':'mascaras_bau_gravadas_pendente_epsxe',
        'pontos':points,'tipos_20_23_preservados':True,
        'tipo_deus_na_tabela_continua_24':True,
        'hook_injetado':False,'delay_slots_alterados':False,
        'icon_deus_instalado':False,'combate_alterado':False,
        'validado_epsxe':False,
        'hash_exe_antes':hashlib.sha256(patched_exe).hexdigest(),
        'hash_exe_depois':hashlib.sha256(out).hexdigest(),
        'aviso':'Somente baú. A exibição ainda precisa ser testada no ePSXe; '
                'ícone, invocação e combate continuam pendentes.'
    }
