"""God24: experimental 8-row chest display patch (not combat, not icon).

PS1 MIPS R3000A has one instruction load delay. Move the row type LBU
into the preceding LHU's load-delay slot, loading $at instead of $v0.
ADDIU uses the ready LHU result; the SH that writes sprite position is
not moved or altered. Mask $at to 0x17, then SLTIU $v0,$at,20.
Types 0..23 retain existing semantics; 24 becomes a monster in this
specific visual test. Types 25..31 must be forbidden in this experiment.
"""
from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterable

from .core import ModError
from .ps1_god24_chest import SOURCE_SHA256

AT = 0x222F4
ORIGINAL = (
    0x96020004,  # lhu   v0,4(s0)
    0x00000000,  # nop / load delay for v0
    0x24420088,  # addiu v0,v0,0x88
    0xA6020004,  # sh    v0,4(s0), sprite position
    0x92220002,  # lbu   v0,2(s1), card type
    0x00000000,  # nop / load delay for v0
    0x2C420014,  # sltiu v0,v0,20
    0x1040002E,  # beq   v0,zero,0x80031BCC
    0x02002021,  # addu  a0,s0,zero / branch delay
    0x02802821,  # addu  a1,s4,zero
    0x00003021,  # addu  a2,zero,zero
)
PATCHED = (
    0x96020004,  # lhu   v0,4(s0) unchanged
    0x92210002,  # lbu   at,2(s1) fills v0 load delay
    0x24420088,  # addiu v0,v0,0x88 fills at load delay
    0xA6020004,  # sh    v0,4(s0) unchanged
    0x30210017,  # andi  at,at,0x17
    0x00000000,  # nop
    0x2C220014,  # sltiu v0,at,20
    0x1040002E,  # beq unchanged
    0x02002021,  # branch delay unchanged
    0x02802821,
    0x00003021,
)
CHANGED=(1,4,6)


def inspect(exe: bytes) -> dict:
    """Readback of actual SLUS opcodes, not a claim of ePSXe behavior."""
    if exe[:8]!=b'PS-X EXE' or len(exe)<AT+len(ORIGINAL)*4:
        return {'status':'fora_do_arquivo','aplicadas':0,'instrucoes':[]}
    words=struct.unpack_from('<'+str(len(ORIGINAL))+'I',exe,AT)
    result=[]
    for i in CHANGED:
        word=words[i]
        state=('patch_presente' if word==PATCHED[i] else
               'original_sem_patch' if word==ORIGINAL[i] else
               'opcode_divergente')
        result.append({'offset_slus':f'0x{AT+i*4:X}',
                       'antes':f'0x{ORIGINAL[i]:08X}',
                       'esperado':f'0x{PATCHED[i]:08X}',
                       'encontrado':f'0x{word:08X}','estado':state})
    unchanged=all(words[i]==ORIGINAL[i]
                  for i in range(len(ORIGINAL)) if i not in CHANGED)
    n=sum(row['estado']=='patch_presente' for row in result)
    if not unchanged or any(row['estado']=='opcode_divergente' for row in result):
        status='sequencia_divergente'
    elif n==3:
        status='aplicado_3_de_3'
    elif n==0:
        status='nao_aplicado_0_de_3'
    else:
        status=f'parcial_{n}_de_3'
    return {'status':status,'aplicadas':n,'instrucoes':result,
            'load_delay_preservado':True,
            'branch_preservado':unchanged,'validado_epsxe':False}


def apply(original_exe: bytes, edited_exe: bytes,
          card_types: Iterable[int], *,
          source_sha256: str = SOURCE_SHA256) -> tuple[bytes,dict]:
    """Fail-closed patch restricted to a signed source SLUS and 0..24 types."""
    if (original_exe[:8]!=b'PS-X EXE' or edited_exe[:8]!=b'PS-X EXE'
            or len(original_exe)!=len(edited_exe)):
        raise ModError('God24 lista: SLUS inválido ou tamanho incompatível.')
    if hashlib.sha256(original_exe).hexdigest()!=source_sha256:
        raise ModError('God24 lista: SHA-256 do SLUS original não corresponde.')
    types=list(card_types)
    if not types or 24 not in types or any(type(t) is not int or
                                            t<0 or t>24 for t in types):
        raise ModError('God24 lista: exige tipo 24 e proíbe tipos 25–31.')
    if any(((t&0x17)<20)!=(t<20 or t==24) for t in range(25)):
        raise ModError('God24 lista: regra de classificação não preservada.')
    if (inspect(original_exe)['status']!='nao_aplicado_0_de_3' or
            inspect(edited_exe)['status']!='nao_aplicado_0_de_3'):
        raise ModError('God24 lista: sequência de 11 opcodes não corresponde '
                       'ao diagnóstico. Nenhum BIN foi alterado.')
    out=bytearray(edited_exe)
    for i in CHANGED:
        struct.pack_into('<I',out,AT+i*4,PATCHED[i])
    report=inspect(out)
    if report['status']!='aplicado_3_de_3':
        raise ModError('God24 lista: erro na releitura dos 3 opcodes.')
    locations=set()
    for i in CHANGED:
        locations.update(range(AT+i*4,AT+i*4+4))
    if any(a!=b for index,(a,b) in enumerate(zip(out,edited_exe))
           if index not in locations):
        raise ModError('God24 lista: alteração fora da região autorizada.')
    report.update({
        'funcao':'func_80031874',
        'status':'aplicado_3_de_3',
        'tipos_0_23_preservados':True,
        'tipo_24_visual_experimental':True,
        'icone_de_tipo_instalado':False,
        'invocacao_e_combate_modificados':False,
        'validado_epsxe':False,
        'aviso':'Somente ATK/DEF da lista de oito linhas. '
                'Confirmar resultado no ePSXe; ícone e combate pendentes.',
    })
    return bytes(out),report
