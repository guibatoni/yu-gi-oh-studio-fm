"""Preparador EXPERIMENTAL do hook de tipo God24 no motor PS1.

Não executa automaticamente nem identifica espaço livre por adivinhação.
Exige SHA da imagem original, janela MIPS coincidente e cave previamente
auditado pelo desenvolvedor. Opera somente em bytes copiados na memória.

O JAL de func_80037FF4 chama DuelEffect_AppendEntry para tipo e stars.
Um trampoline filtra pelo opcode do stream: kind=0 e ID=24. Não altera
opcodes de Guardian Stars (kind=1 e kind=2). O código-fonte de referência
é o Forbidden Memories recompilado (func_80037DA4).
"""
from __future__ import annotations

import hashlib
import struct

from .core import ModError
from .tables import EXE_DELTA

KNOWN_SOURCE_SHA256 = '7412689c12618f90144e8b90839f1f47d2813cc20b42675f2506d8e125fa6b03'
KNOWN_TYPE_WINDOW_SHA256 = 'c335fb3d7fd4630dd80beb5698b64bc0d15ace6f6603d0c3467e339fffa258c8'
ICON_SLOTS = frozenset((0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F, 0x30))
SITE_RAM = 0x80037FF4
SITE_OFFSET = SITE_RAM-EXE_DELTA
ORIGINAL_JAL = 0x0C00DB05
ORIGINAL_DELAY = 0x02002021  # addu a0,s0,zero
ORIGINAL_TARGET = 0x80036C14
WINDOW_START = 0x80037DA4-EXE_DELTA
WINDOW_SIZE = 0x280


def _i(op:int,rs:int,rt:int,imm:int)->int:
    return (op<<26)|(rs<<21)|(rt<<16)|(imm&0xffff)


def _r(rs:int,rt:int,rd:int,shamt:int,funct:int)->int:
    return (rs<<21)|(rt<<16)|(rd<<11)|(shamt<<6)|funct


def _jump(op:int,address:int)->int:
    if address&3 or not 0x80000000<=address<=0x8fffffff:
        raise ModError('God24: endereço de destino J/JAL inválido.')
    return op<<26 | ((address>>2)&0x03ffffff)


def god24_hook_words(icon_slot:int)->tuple[int,...]:
    """19 instruções R3000A, sem alterar $ra e com load-delay explícito."""
    if type(icon_slot) is not int or icon_slot not in ICON_SLOTS:
        raise ModError('God24: slot de ícone 0x27–0x30 não suportado.')
    return (
        _i(9,0,9,24),              # addiu t1,zero,24
        _i(5,5,9,15),              # bne a1,t1,retorno
        0,                         # branch delay
        _i(36,4,8,0x58),          # lbu t0,0x58(a0): stream_58
        0,                         # load delay do PS1
        _r(0,8,8,2,0),            # sll t0,t0,2
        _r(8,4,8,0,0x21),         # addu t0,t0,a0
        _i(35,8,8,0),             # lw t0,0(t0): cursor stream
        0,                         # load delay
        _i(4,8,0,7),              # beq t0,zero,retorno
        0,                         # branch delay
        _i(36,8,8,-1),            # lbu t0,-1(t0): opcode da entrada
        0,                         # load delay
        _i(12,8,8,15),            # andi t0,t0,0xF: kind
        _i(5,8,0,2),              # bne t0,zero,retorno (stars 1,2)
        0,                         # branch delay
        _i(9,0,5,icon_slot),      # addiu a1,zero,slot novo
        _jump(2,ORIGINAL_TARGET),  # j func_80036C14 (tail-call)
        0,                         # delay do jump
    )


def probe_god24_hook(exe:bytes,slot:int,cave_offset:int|None=None,
                     *,source_sha256:str=KNOWN_SOURCE_SHA256,
                     window_sha256:str=KNOWN_TYPE_WINDOW_SHA256)->dict:
    """Diagnostica candidato; NÃO declara que uma região zero está livre."""
    words=god24_hook_words(slot)
    report={'status':'incompativel','aplicado':False,'slot':slot,
            'site':f'0x{SITE_OFFSET:X}',
            'destino_original':f'0x{ORIGINAL_TARGET:08X}',
            'bytes_codigo':len(words)*4,
            'execucao_ePSXe_validada':False,
            'cave_validado_externamente':False}
    if len(exe)<SITE_OFFSET+8 or exe[:8]!=b'PS-X EXE':
        report['motivo']='PS-X EXE ausente ou truncado'
        return report
    t_addr,t_size=struct.unpack_from('<II',exe,0x18)
    if t_addr!=EXE_DELTA+0x800 or not t_size or t_size%4 or t_size>len(exe)-0x800:
        report['motivo']='Cabeçalho do segmento carregado incompatível'
        return report
    if hashlib.sha256(exe).hexdigest()!=source_sha256:
        report['motivo']='SHA do SLUS não coincide com o perfil explicitamente aprovado'
        return report
    if hashlib.sha256(exe[WINDOW_START:WINDOW_START+WINDOW_SIZE]).hexdigest()!=window_sha256:
        report['motivo']='Função de ícone modificada; assinatura MIPS não coincide'
        return report
    op,delay=struct.unpack_from('<II',exe,SITE_OFFSET)
    if (op,delay)!=(ORIGINAL_JAL,ORIGINAL_DELAY):
        report['motivo']='JAL ou delay slot diferente do relatório; nada será sobrescrito'
        return report
    report['status']='assinatura_confirmada_sem_cave_aprovado'
    report['motivo']='Validação de um endereço livre exige auditoria externa da região e de suas referências'
    if cave_offset is None:
        return report
    if type(cave_offset) is not int or cave_offset&3:
        report['status']='incompativel'
        report['motivo']='Offset do cave deve ser alinhado em 4 bytes'
        return report
    if not (0x800<=cave_offset and cave_offset+len(words)*4<=0x800+t_size):
        report['status']='incompativel'
        report['motivo']='Cave fora do segmento de código carregado'
        return report
    cave_ram=EXE_DELTA+cave_offset
    if cave_offset<=SITE_OFFSET+8 and cave_offset+len(words)*4>SITE_OFFSET:
        report['status']='incompativel'
        report['motivo']='Cave sobrepõe chamada original'
        return report
    if any(exe[cave_offset:cave_offset+len(words)*4]):
        report['status']='incompativel'
        report['motivo']='Cave contém bytes de jogo; não sobrescrever'
        return report
    if (cave_ram>>28)!=(SITE_RAM>>28):
        report['status']='incompativel'
        report['motivo']='Cave fora da região de JAL'
        return report
    # Desvio estático já existente para dentro do cave: recusa conservadora.
    lo,hi=cave_ram,cave_ram+len(words)*4
    for off in range(0x800,0x800+t_size,4):
        pc=EXE_DELTA+off
        word=struct.unpack_from('<I',exe,off)[0]
        op=word>>26
        if op in (2,3):
            target=((pc+4)&0xf0000000)|((word&0x03ffffff)<<2)
        elif op in (4,5,6,7,20,21):
            imm=word&0xffff
            target=(pc+4+((imm if imm<0x8000 else imm-0x10000)<<2))&0xffffffff
        else:
            continue
        if lo<=target<hi:
            report['status']='incompativel'
            report['motivo']='Destino de jump/branch existente dentro do cave'
            return report
    report.update(status='candidato_zero_nao_comprovado_livre',
                  cave=f'0x{cave_offset:X}',cave_ram=f'0x{cave_ram:08X}',
                  motivo='Bytes zerados e sem salto direto detectado, mas podem '
                         'ser usados por código indireto, dados ou overlay')
    return report


def patch_god24_hook(exe:bytes,slot:int,cave_offset:int,
                     *,auditoria_externa_confirmada:bool=False,
                     source_sha256:str=KNOWN_SOURCE_SHA256,
                     window_sha256:str=KNOWN_TYPE_WINDOW_SHA256)->tuple[bytes,dict]:
    """Patch de cópia SEPARADA; caller deve autorizar cave externamente.

    Não deve ser chamado pelo botão Gerar BIN/CUE até teste real de cave,
    VRAM, registradores, slots e execução em emulador.
    """
    report=probe_god24_hook(exe,slot,cave_offset,
                            source_sha256=source_sha256,
                            window_sha256=window_sha256)
    if report['status']!='candidato_zero_nao_comprovado_livre':
        raise ModError('God24: '+report.get('motivo','assinatura incompatível'))
    if auditoria_externa_confirmada is not True:
        raise ModError('God24: cave sem auditoria independente; hook desativado.')
    cave_ram=EXE_DELTA+cave_offset
    words=god24_hook_words(slot)
    out=bytearray(exe)
    struct.pack_into('<I',out,SITE_OFFSET,_jump(3,cave_ram))
    struct.pack_into('<'+str(len(words))+'I',out,cave_offset,*words)
    modified=set(range(SITE_OFFSET,SITE_OFFSET+4))
    modified.update(range(cave_offset,cave_offset+4*len(words)))
    if (len(out)!=len(exe) or
            any(a!=b for i,(a,b) in enumerate(zip(exe,out)) if i not in modified)
            or struct.unpack_from('<I',out,SITE_OFFSET+4)[0]!=ORIGINAL_DELAY):
        raise ModError('God24: verificação de regiões preservadas falhou.')
    report.update(status='patch_em_copia_experimental_sem_validacao_epsxe',
                  aplicado=True,
                  cave_validado_externamente=True,
                  sha256_antes=hashlib.sha256(exe).hexdigest(),
                  sha256_depois=hashlib.sha256(out).hexdigest(),
                  instrucao_chamada=f'0x{_jump(3,cave_ram):08X}',
                  delay_slot_preservado=True)
    return bytes(out),report
