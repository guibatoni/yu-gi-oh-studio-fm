"""Perfil MIPS e primeiro patch global experimental de regras do PS1.

Não injeta scripts de habilidades inéditas: gera um inventário verificável
das regiões que precisam de hooks e altera SOMENTE um slti/sltiu inequívoco
do limite GLOBAL de cópias no deck, se a assinatura dessa rotina for segura.
A configuração por CARTA do laboratório continua independente deste limite.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from .core import ModError
from .tables import EXE_DELTA

# Funções documentadas pela recompilação SLUS_014.11. São endereços da
# versão original, não promessas de endereços equivalentes em MODs.
SITES = {
    'atributos_dinamicos': ('Duel_CalcCardStats', 0x800170C8, 0x68),
    'remover_monstro': ('DuelCard_RemoveFromField', 0x80024954, 0x28),
    'acao_por_turno': ('DuelCard_CanActThisTurn', 0x8001700C, 0x28),
    'ataque_em_batalha': ('Duel_CalcBattleAttack', 0x8001EF1C, 0x5C),
    'combate': ('DuelScene_UpdateBattle', 0x8001F55C, 0x1378),
    'controle_campo': ('DuelScene_UpdateFieldActions', 0x8001D670, 0x1600),
    'colocacao_equip': ('DuelScene_UpdateCardPlacement', 0x80019D18, 0x13B4),
    'construcao_deck': ('BuildDeck_UpdateChestPaneInput', 0x800336F0, 0x1F4),
    'capacidade_deck': ('BuildDeck_HasOpenDeckSlot', 0x80033998, 0x38),
}
DECK_CODE_NAME = 'construcao_deck'

ACTION_GROUPS = {
    'atributos_dinamicos': frozenset({
        'aura_tipo', 'bonus_por_tipo', 'bonus_deck_tipo', 'bonus_por_carta_id',
        'bonus_cemiterio_tipo', 'equip_atk'}),
    'protecao': frozenset({
        'monstro_indestrutivel', 'monstro_imune_magia', 'monstro_imune_armadilha',
        'equip_indestrutivel', 'equip_imune_armadilha', 'equip_imune_magia_armadilha'}),
    'combate': frozenset({
        'ataques_multiplos','dano_perfurante','nao_bloqueavel',
        'perder_lp_por_ataque','ataque_primeiro_turno'}),
    'copias_deck': frozenset({'sem_limite_deck','limite_copias_deck'}),
}


def _range(exe: bytes, address: int, size: int) -> tuple[int, bytes]:
    if exe[:8] != b'PS-X EXE':
        raise ModError('Executável não possui cabeçalho PS-X EXE.')
    offset = address - EXE_DELTA
    if offset < 0 or offset + size > len(exe):
        raise ModError(f'Executável não contém região MIPS 0x{address:08X} '
                       f'(+0x{size:X}).')
    return offset, exe[offset:offset+size]



# Instrução retail corroborada: Duel_InitSideStates, SLUS+0x7DD0.
LP_INIT_OFFSET = 0x7DD0
LP_INIT_ORIGINAL = 0x24021F40  # addiu $v0,$zero,8000


def probe_initial_duel_lp(exe: bytes, value: int | None = None) -> dict:
    """Leitura apenas: exige a instrução retail exata antes de propor patch."""
    if value is not None:
        if (isinstance(value,bool) or not isinstance(value,int)
                or value<500 or value>9500 or value%500):
            raise ModError('LP inicial: use múltiplos de 500 entre 500 e 9500.')
    if len(exe)<LP_INIT_OFFSET+4 or exe[:8]!=b'PS-X EXE':
        return {'status':'incompativel','motivo':'SLUS PS-X EXE inválido ou truncado.'}
    original=struct.unpack_from('<I',exe,LP_INIT_OFFSET)[0]
    if original!=LP_INIT_ORIGINAL:
        return {'status':'incompativel',
                'instrucao_encontrada':f'0x{original:08X}',
                'motivo':'Opcode de inicialização de LP é diferente da versão retail; '
                         'não gravar neste MOD.'}
    return {'status':'retail_lp_detectado_sem_validacao_epsxe',
            'offset_slus':f'0x{LP_INIT_OFFSET:X}',
            'instrucao_original':f'0x{original:08X}',
            'lp_original':8000,'lp_solicitado':value,
            'aviso':'Apenas duelos normais. Modo 2 jogadores usa outra rotina.'}


def patch_initial_duel_lp(exe: bytes, value: int | None) -> tuple[bytes,list[dict]]:
    """Smoke test de alteração real MIPS sem realocação, só em cópia SLUS."""
    if value is None:
        return exe,[]
    proof=probe_initial_duel_lp(exe,value)
    if value==8000:
        return exe,[]
    if proof['status']!='retail_lp_detectado_sem_validacao_epsxe':
        raise ModError('Patch MIPS LP bloqueado: '+proof['motivo'])
    out=bytearray(exe)
    new=(LP_INIT_ORIGINAL&0xFFFF0000)|value
    struct.pack_into('<I',out,LP_INIT_OFFSET,new)
    if len(out)!=len(exe) or out[:LP_INIT_OFFSET]!=exe[:LP_INIT_OFFSET] or out[LP_INIT_OFFSET+4:]!=exe[LP_INIT_OFFSET+4:]:
        raise ModError('Patch LP alterou bytes fora da instrução permitida.')
    if struct.unpack_from('<I',out,LP_INIT_OFFSET)[0]!=new:
        raise ModError('Verificação de retorno da instrução LP falhou.')
    return bytes(out),[{'alteracao':'lp_inicial_duelo_normal',
                        'offset_slus':f'0x{LP_INIT_OFFSET:X}',
                        'instrucao_anterior':f'0x{LP_INIT_ORIGINAL:08X}',
                        'instrucao_nova':f'0x{new:08X}',
                        'lp_inicial':value,
                        'status':'patch_retail_experimental_epsxe_pendente',
                        'restricao':'Modo 2 jogadores não alterado.'}]


def scan_direct_mips_calls(exe: bytes) -> dict:
    """Read-only JAL references to known locations in a PS-X EXE code segment.

    Requires a credible executable header and a consistent original load base.
    This is an inventory of static candidates, NOT proof of a safe hook or
    proof that a function starts at the address listed in SITES.
    """
    if len(exe) < 0x800 or exe[:8] != b'PS-X EXE':
        return {'status':'segmento_invalido',
                'motivo':'Cabeçalho PS-X EXE ausente ou incompleto.',
                'por_funcao':{}}
    load_address, code_size = struct.unpack_from('<II', exe, 0x18)
    expected_load = EXE_DELTA + 0x800
    if load_address != expected_load:
        return {'status':'segmento_invalido',
                'motivo':'Endereço de carga incompatível com os offsets SLUS conhecidos: '
                         f'0x{load_address:08X} (esperado 0x{expected_load:08X}).',
                'por_funcao':{}}
    if not code_size or code_size % 4 or 0x800 + code_size > len(exe):
        return {'status':'segmento_invalido',
                'motivo':'Tamanho do segmento carregado ausente, desalinhado '
                         'ou superior aos bytes disponíveis.',
                'por_funcao':{}}
    addresses={definition[1]:alias for alias,definition in SITES.items()}
    references={alias:[] for alias in SITES}
    counts={alias:0 for alias in SITES}
    for offset in range(0x800, 0x800+code_size, 4):
        instruction=struct.unpack_from('<I',exe,offset)[0]
        if instruction>>26 != 3:  # JAL, chamadas indiretas JALR não são capturadas.
            continue
        pc=EXE_DELTA+offset
        destination=((pc+4)&0xF0000000)|((instruction&0x03FFFFFF)<<2)
        alias=addresses.get(destination)
        if alias is None:
            continue
        counts[alias]+=1
        if len(references[alias])<16:
            references[alias].append({'endereco_ram':f'0x{pc:08X}',
                                     'offset_slus':f'0x{offset:X}'})
    return {
        'status':'varredura_estatica_sem_hooks_validados',
        'segmento_ram':f'0x{load_address:08X}',
        'tamanho_segmento_bytes':code_size,
        'por_funcao':{
            alias:{'total_jal_diretos':counts[alias],
                   'locais_jal':references[alias],
                   'amostragem_limitada':counts[alias]>len(references[alias])}
            for alias in SITES
        },
        'aviso':'JAL encontrado é apenas referência estática: dados podem parecer instruções, '
                'chamadas JALR não aparecem, e MODs podem usar outros endereços. '
                'Não autoriza injeção automática MIPS.',
    }



def inspect_function_instructions(exe: bytes, alias: str, max_words: int = 20) -> dict:
    """Amostra MIPS sem execução: opcodes, ramificações e delay slots.

    NÃO valida injeção. Um bloco pode conter dados ou rotina redirecionada.
    """
    if alias not in SITES:
        raise ModError('Rotina MIPS desconhecida: '+str(alias))
    if isinstance(max_words,bool) or not isinstance(max_words,int) or not 1<=max_words<=48:
        raise ModError('Amostra MIPS deve conter entre 1 e 48 instruções.')
    function,address,size=SITES[alias]
    try:
        offset,raw=_range(exe,address,size)
    except ModError as exc:
        return {'funcao':function,'status':'incompativel','motivo':str(exc),
                'instrucoes':[]}
    count=min(max_words,len(raw)//4)
    branch_ops={4:'beq',5:'bne',6:'blez',7:'bgtz',20:'beql',21:'bnel'}
    mem_ops={32:'lb',33:'lh',35:'lw',36:'lbu',37:'lhu',
             40:'sb',41:'sh',43:'sw'}
    out=[]
    delay=False
    for i in range(count):
        word=struct.unpack_from('<I',raw,i*4)[0]
        pc=address+i*4
        op=word>>26
        rs=(word>>21)&31
        rt=(word>>16)&31
        imm=word&0xFFFF
        signed=imm if imm<0x8000 else imm-0x10000
        decoded='op_0x%02X'%op
        target=None
        delayed=False
        if word==0:
            decoded='nop'
        elif op==0:
            funct=word&63
            if funct==8:
                decoded='jr'; delayed=True
            elif funct==9:
                decoded='jalr'; delayed=True
            else:
                decoded='special_0x%02X'%funct
        elif op in (2,3):
            decoded='j' if op==2 else 'jal'
            target=((pc+4)&0xF0000000)|((word&0x03FFFFFF)<<2)
            delayed=True
        elif op in branch_ops:
            decoded=branch_ops[op]
            target=(pc+4+(signed<<2))&0xFFFFFFFF
            delayed=True
        elif op in mem_ops:
            decoded=mem_ops[op]
        elif op in (8,9,10,11,12,13,14,15):
            decoded={8:'addi',9:'addiu',10:'slti',11:'sltiu',
                     12:'andi',13:'ori',14:'xori',15:'lui'}[op]
        entry={'endereco_ram':'0x%08X'%pc,'offset_slus':'0x%X'%(offset+i*4),
               'opcode_hex':'0x%08X'%word,'mnemonico':decoded,
               'delay_slot':delay,'gera_delay_slot':delayed}
        if target is not None:
            entry['alvo_ram']='0x%08X'%target
        if decoded=='jr':
            entry['registrador_alvo']=rs
        if decoded in ('lb','lh','lw','lbu','lhu','sb','sh','sw'):
            entry['base_reg']=rs
            entry['data_reg']=rt
            entry['deslocamento']=signed
        out.append(entry)
        delay=delayed
    return {
        'funcao':function,'endereco_funcao':'0x%08X'%address,
        'status':'amostra_estatica_sem_hooks_validados',
        'instrucoes':out,
        'primeiro_opcode':'0x%08X'%struct.unpack_from('<I',raw,0)[0],
        'retorno_jr_ra_na_amostra':sum(
            rec['mnemonico']=='jr' and rec.get('registrador_alvo')==31
            for rec in out),
        'amostra_parcial':count<len(raw)//4,
        'aviso':'Desmontagem parcial: não é confirmação de limites da função, '
                'fluxo de controle nem espaço livre para código MIPS.',
    }


def scan_effect_sites(exe: bytes) -> dict:
    referencias=scan_direct_mips_calls(exe)
    sites={}
    for alias, (name,address,size) in SITES.items():
        try:
            offset, content=_range(exe,address,size)
            words=struct.unpack('<'+str(size//4)+'I',content[:size//4*4])
            active=sum(word not in (0,0xFFFFFFFF) for word in words)
            first=words[0] if words else 0
            sites[alias]={
                'funcao':name,'endereco_ram':f'0x{address:08X}',
                'offset_slus':f'0x{offset:X}','tamanho_bytes':size,
                'sha256_regiao':hashlib.sha256(content).hexdigest(),
                'primeira_instrucao':f'0x{first:08X}',
                'candidata_a_salto_mips':first>>26 in (2,3),
                'palavras_ativas':active,
                'status':'regiao_encontrada_sem_hook_validado' if active>=3
                         else 'regiao_ausente_ou_alterada',
                'prologo_classico_addiu_sp':(first & 0xFFFF0000)==0x27BD0000
                                              and (first & 0x8000)!=0,
                'referencias_jal':referencias.get('por_funcao',{}).get(alias,
                                   {'total_jal_diretos':None,'locais_jal':[],
                                    'diagnostico':'segmento de código inválido'}),
                'aviso_entrada':'Endereço de referência, não hook MIPS validado.',
            }
        except ModError as exc:
            sites[alias]={'funcao':name,'status':'fora_do_SLUS','erro':str(exc)}
    return sites


def _deck_cmp_candidates(exe: bytes) -> list[dict]:
    """Busca comparação <3 com branch adjacente na rotina de deck original.

    Não tenta localizar função relocalizada/hook; não supõe que qualquer
    instrução com constante 3 é o limite de cópias.
    """
    _,data=_range(exe,*SITES[DECK_CODE_NAME][1:])
    words=struct.unpack('<'+str(len(data)//4)+'I',data)
    candidates=[]
    for i,word in enumerate(words[:-2]):
        opcode=word>>26
        if opcode not in (10,11) or (word&0xFFFF)!=3:  # slti/sltiu <3
            continue
        rt=(word>>16)&31
        if rt==0: continue
        branches=[]
        for j in (1,2):
            nxt=words[i+j]
            op=nxt>>26
            if op in (4,5,20,21) and rt in (((nxt>>21)&31),((nxt>>16)&31)):
                branches.append(j)
        if branches:
            candidates.append({'address':SITES[DECK_CODE_NAME][1]+i*4,
                               'offset':SITES[DECK_CODE_NAME][1]-EXE_DELTA+i*4,
                               'opcode':opcode,'rt':rt,'branch_distance':branches[0],
                               'word':word})
    return candidates


def deck_global_patch_probe(exe: bytes, limit: int | None=None) -> dict:
    if limit is not None:
        try: limit=int(limit)
        except (TypeError,ValueError) as exc:
            raise ModError('Limite global precisa ser número inteiro.') from exc
        if not 1<=limit<=40:
            raise ModError('Limite global deve ser de 1 a 40 cópias por ID. '
                           'Deck total do PS1 continua fixo em 40 cartas.')
    try:
        _,data=_range(exe,*SITES[DECK_CODE_NAME][1:])
    except ModError as exc:
        return {'status':'incompativel','candidatos':[],'motivo':str(exc)}
    first=struct.unpack_from('<I',data,0)[0]
    if first>>26 in (2,3):
        return {'status':'incompativel','candidatos':[],
                'motivo':'BuildDeck_UpdateChestPaneInput parece redirecionada por J/JAL.'}
    matches=_deck_cmp_candidates(exe)
    if len(matches)!=1:
        return {'status':'incompativel','candidatos':[
            {'endereco_ram':f'0x{x["address"]:08X}',
             'offset_slus':f'0x{x["offset"]:X}'}
            for x in matches],
            'motivo':'Necessária uma única comparação slti/sltiu <3 seguida por branch. '
                     f'Encontradas: {len(matches)}. Sem alteração automática.'}
    m=matches[0]
    return {'status':'candidato_unico_experimental',
            'candidatos':[{'endereco_ram':f'0x{m["address"]:08X}',
                           'offset_slus':f'0x{m["offset"]:X}',
                           'instrucao_original':f'0x{m["word"]:08X}'}],
            'limite_atual':3,
            'limite_solicitado':limit,
            'aviso':'Candidato de instrução; código do MOD e comportamento real ainda precisam de teste em ePSXe. '
                    'Não altera limite físico de 40 cartas ou regra especial Exodia.'}


def patch_deck_global_limit(exe: bytes, limit: int | None) -> tuple[bytes,list[dict]]:
    if limit is None or str(limit)=='3':
        return exe,[]
    result=deck_global_patch_probe(exe,limit)
    if result['status']!='candidato_unico_experimental':
        raise ModError('Limite de cópias PS1: '+result['motivo'])
    candidate=_deck_cmp_candidates(exe)[0]
    old=candidate['word']
    new=(old&0xFFFF0000)|int(limit)
    offset=candidate['offset']
    out=bytearray(exe)
    struct.pack_into('<I',out,offset,new)
    if struct.unpack_from('<I',out,offset)[0]!=new or len(out)!=len(exe):
        raise ModError('Falha na verificação do patch global MIPS de deck.')
    changed=[i for i,(a,b) in enumerate(zip(exe,out)) if a!=b]
    if not all(offset<=i<offset+4 for i in changed):
        raise ModError('Alteração fora de comparação MIPS de deck.')
    return bytes(out),[{
        'funcao':SITES[DECK_CODE_NAME][0],
        'ram':f'0x{candidate["address"]:08X}',
        'offset_slus':f'0x{offset:X}',
        'instrucao_original':f'0x{old:08X}',
        'instrucao_modificada':f'0x{new:08X}',
        'limite_global_por_id':int(limit),
        'status':'experimental_sem_validacao_epsxe',
    }]


def analyze_project_effects(project) -> dict:
    """Relatório local sem prometer que o jogo executa habilidades da GUI."""
    base=project.folder/'base'/'source_SLUS_014.11'
    if not base.is_file():
        raise ModError('Vincule o SLUS_014.11 original ao projeto antes de analisar MIPS.')
    exe=base.read_bytes()
    grouped={name:[] for name in ACTION_GROUPS}
    unknown=[]
    for key,entries in sorted(project.effects.items(),key=lambda x:int(x[0])):
        for entry in entries:
            action=str(entry.get('acao',''))
            record={'carta_id':int(key),'acao':action,'parametros':dict(entry)}
            bucket=next((name for name,actions in ACTION_GROUPS.items()
                         if action in actions),None)
            if bucket:grouped[bucket].append(record)
            else:unknown.append(record)
    limit=project.metadata.get('ps1_deck_global_limit')
    return {
        'versao_perfil':1,'alvo':'SLUS_014.11 (PS1 MIPS)',
        'sha256_executavel_origem':hashlib.sha256(exe).hexdigest(),
        'funcoes_encontradas':scan_effect_sites(exe),
        'amostras_instrucoes_mips':{alias:inspect_function_instructions(exe,alias)
                                    for alias in SITES},
        'referencias_chamadas_mips':scan_direct_mips_calls(exe),
        'probe_lp_inicial':probe_initial_duel_lp(exe,project.metadata.get('ps1_starting_lp')),
        'perfil_limite_global_deck':deck_global_patch_probe(exe,limit),
        'grupos_programados_no_studio':grouped,
        'outros_efeitos':unknown,
        'habilidades_ineditas_gravadas_no_PS1':False,
        'aviso':'A presença da função na imagem não implementa um efeito. '
                'Auras, cemitério, proteções e ataques múltiplos ainda exigem '
                'rotinas MIPS, eventos e testes no emulador.',
    }


def save_project_effect_analysis(project) -> Path:
    result=analyze_project_effects(project)
    dest=project.folder/'exportacao'/'diagnostico_motor_efeitos_mips.json'
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return dest
