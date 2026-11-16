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


# Endereços de referência US SLUS-01411; MODs podem alterar cada rotina.
GOD_ICON_RENDER_SITES = {
    'tipo_na_lista': ('func_80037DA4', 0x80037DA4, 0x280),
    'sprite_tipo': ('func_80031574', 0x80031574, 0x17C),
    'renderizador_glifos': ('func_80035E20', 0x80035E20, 0x240),
}


def diagnose_god_type_icon(exe: bytes) -> dict:
    """Read-only: contexto para futuro patch de God24 sem afetar stars."""
    result={
        'status':'diagnostico_sem_hook_de_tipo',
        'tipo_god':24,
        'primeira_guardian_star_indice':0x17+1,
        'mesmo_indice_no_renderizador_original':True,
        'referencias':{},
        'aviso':'Um ícone na descrição não muda o ícone de tipo no baú. '
                'O índice 24 também representa a primeira Guardian Star; '
                'não sobrescrever a textura original.',
        'pendencia':'Requer um hook somente no caminho de tipo e um sprite '
                   'exclusivo; não foi instalado nenhum patch MIPS de ícone.'}
    if exe[:8]!=b'PS-X EXE':
        result['status']='executavel_invalido'
        return result
    for key,(name,ram,size) in GOD_ICON_RENDER_SITES.items():
        offset=ram-EXE_DELTA
        if offset<0 or offset+size>len(exe):
            result['referencias'][key]={'nome':name,'status':'janela_ausente'}
            continue
        region=exe[offset:offset+size]
        words=[struct.unpack_from('<I',region,4*i)[0] for i in range(12)]
        result['referencias'][key]={
            'nome':name,
            'status':'amostra_sem_validacao' if sum(x!=0 for x in words)>=4
                      else 'amostra_vazia_ou_alterada',
            'endereco_retail':f'0x{ram:08X}',
            'offset_slus':f'0x{offset:X}',
            'sha256_regiao':hashlib.sha256(region).hexdigest(),
            'primeiras_instrucoes':[f'0x{x:08X}' for x in words]}
    return result


# Impressões digitais enviadas no diagnóstico anterior do projeto yugioh teste.
# Servem somente para comparação; não autorizam um hook MIPS.
GOD_ICON_REFERENCE_HASHES = {
    'tipo_na_lista':'c335fb3d7fd4630dd80beb5698b64bc0d15ace6f6603d0c3467e339fffa258c8',
    'sprite_tipo':'5d89cbea3338fd8c2d244c16d2930a8027ce9b88a032659373aadf0ded83c6d8',
    'renderizador_glifos':'0ffcbe2407d7efa89f2d1ab05a0346a5ca47bb6bcb7655dfa5d0d8dd09e389c4',
}
GOD_ICON_TEXT_APPEND_RAM = 0x80036C14


def scan_god24_render_calls(exe: bytes) -> dict:
    """Leitura de JAL, atraso (delay slot) e assinaturas nas rotinas de ícone.

    Todos os dados vêm do executável importado; NENHUMA escrita na ISO.
    Uma ocorrência JAL não demonstra que o registrador de tipo esteja vivo.
    """
    out={
        'status':'somente_leitura_sem_hook',
        'caminho_compartilhado_com_guardian_stars':True,
        'caminho_do_tipo_deve_ser_isolado':True,
        'executavel_sha256':hashlib.sha256(exe).hexdigest(),
        'rotinas':{},
        'hook_aplicado':False,
    }
    if len(exe)<0x800 or exe[:8]!=b'PS-X EXE':
        out['status']='cabecalho_invalido'
        return out
    base,segment_size=struct.unpack_from('<II',exe,0x18)
    if (base!=EXE_DELTA+0x800 or not segment_size or segment_size%4
            or segment_size>len(exe)-0x800):
        out['status']='segmento_codigo_nao_validado'
        return out
    for key,(name,ram,span) in GOD_ICON_RENDER_SITES.items():
        offset=ram-EXE_DELTA
        if offset<0x800 or offset+span>0x800+segment_size:
            out['rotinas'][key]={
                'nome':name,'status':'fora_do_segmento_codigo'}
            continue
        buf=exe[offset:offset+span]
        digest=hashlib.sha256(buf).hexdigest()
        words=struct.unpack('<'+str(span//4)+'I',buf)
        callsites=[]
        count=0
        for index,word in enumerate(words):
            if word>>26!=3:
                continue
            pc=ram+index*4
            target=((pc+4)&0xF0000000)|((word&0x03FFFFFF)<<2)
            if target!=GOD_ICON_TEXT_APPEND_RAM:
                continue
            count+=1
            if len(callsites)>=16:
                continue
            lo=max(0,index-10)
            hi=min(len(words),index+7)
            callsites.append({
                'endereco_ram':f'0x{pc:08X}',
                'offset_slus':f'0x{offset+index*4:X}',
                'opcode':f'0x{word:08X}',
                'delay_slot':(f'0x{words[index+1]:08X}'
                              if index+1<len(words) else None),
                'contexto_opcodes':[{
                    'endereco_ram':f'0x{ram+i*4:08X}',
                    'word':f'0x{words[i]:08X}',
                    'call':i==index,'delay':i==index+1}
                    for i in range(lo,hi)],
            })
        out['rotinas'][key]={
            'nome':name,'status':'janela_lida_sem_hook_validado',
            'endereco_ram':f'0x{ram:08X}',
            'hash_sha256':digest,
            'coincide_relatorio_anterior':digest==GOD_ICON_REFERENCE_HASHES.get(key),
            'total_chamadas_glifo':count,
            'chamadas_ate_16':callsites,
            'chamadas_excedem_amostragem':count>len(callsites),
        }
    comparable=[v.get('coincide_relatorio_anterior') for v in out['rotinas'].values()]
    out['comparacao_com_relatorio_anterior']=(
        'todas_tres_regioes_coincidem'
        if len(comparable)==3 and all(comparable)
        else 'hash_diferente_ou_regiao_ausente')
    out['aviso']='Índice God24 coincide com Guardian Star 1. '
    out['aviso']+='Nenhum desvio pode ser gravado sem validar o caminho tipo, '
    out['aviso']+='delay slots, destino, ABI e espaço de código no SLUS real.'
    return out



# Caminhos separados de apresentação, classificação e jogabilidade.
# Endereços/limites consultados no mapa SLUS-01411 de Forbidden Memories
# recompilado. Uma assinatura não é autorização para injetar código.
GOD24_MONSTER_SITES={
    'bau_atk_def': ('CardList_RenderDeckBoxStats',0x80060B38,0x338,
                    'O baú só desenha ATK/DEF para tipos 00–19.'),
    'classificacao_linha': ('func_80060E70',0x80060E70,0x198,
                            'Escolhe o layout monstro ou não-monstro.'),
    'criacao_registro_duelo': ('Duel_SetupCardRecord',0x800249E0,0x23C,
                               'Prepara a carta no campo e dados de terreno.'),
    'bonus_de_terreno': ('Duel_GetTerrainBoost',0x8002497C,0x64,
                         'Tabela retail de terreno só comporta 20 tipos.'),
    'colocacao_carta': ('DuelScene_UpdateCardPlacement',0x80019D18,0x13B4,
                        'Fluxo de invocação/colocação no duelo.'),
    'acoes_de_campo': ('DuelScene_UpdateFieldActions',0x8001D670,0x1600,
                       'Operações de campo e condições do turno.'),
    'icone_carta': ('func_80031574',0x80031574,0x17C,
                    'Desenha ícone do tipo na tela da carta.'),
    'icone_texto': ('func_80037DA4',0x80037DA4,0x280,
                    'Compartilha símbolos de tipo e Guardian Stars.'),
}
GOD24_MONSTER_LIMIT = 20


def _god24_compare_entries(raw: bytes, address: int, offset: int,
                            max_candidates: int = 24) -> tuple[int,list[dict]]:
    """Busca somente padrões de IMEDIATO 20 (candidatos, não prova de fluxo).

    Não tenta gravar nem alterar limiares 20->25: isso converteria
    Magia/Armadilha/Ritual/Equip em criaturas.
    """
    words=struct.unpack('<'+str(len(raw)//4)+'I',raw)
    found=[]
    total=0
    for i,word in enumerate(words):
        op=word>>26
        imm=word&0xffff
        # slti/sltiu ...,20: forma comum de "tipo < 20".
        # addiu ..., -20: forma possível de comparação com CARD_TYPE_MAGIC.
        if not ((op in (10,11) and imm==20) or
                (op in (8,9) and imm==0xFFEC)):
            continue
        total+=1
        if len(found)>=max_candidates:
            continue
        left=max(0,i-5)
        right=min(len(words),i+7)
        excerpt=[]
        for j in range(left,right):
            w=words[j]
            p=address+j*4
            opcode=w>>26
            record={'pc':f'0x{p:08X}',
                    'offset_slus':f'0x{offset+j*4:X}',
                    'word':f'0x{w:08X}',
                    'foco':j==i,
                    'delay_apos_comparacao':False}
            if opcode in (4,5,6,7):
                immediate=w&0xffff
                signed=immediate if immediate<0x8000 else immediate-0x10000
                record['ramo_destino']=f'0x{((p+4+(signed<<2))&0xFFFFFFFF):08X}'
                record['ramo_condicional']=True
                if j+1<right:
                    record['delay_slot_ram']=f'0x{p+4:08X}'
            elif opcode in (2,3):
                record['salto_destino']=f'0x{(((p+4)&0xF0000000)|((w&0x03FFFFFF)<<2)):08X}'
            excerpt.append(record)
        found.append({
            'pc':f'0x{address+i*4:08X}',
            'offset_slus':f'0x{offset+i*4:X}',
            'opcode':f'0x{word:08X}',
            'familia':('slti' if op==10 else 'sltiu' if op==11 else
                       'addi_-20' if op==8 else 'addiu_-20'),
            'reg_origem':(word>>21)&31,
            'reg_destino':(word>>16)&31,
            'contexto':excerpt,
            'aviso':'Possível teste de classe; é necessário rastrear os '
                    'registradores e o caminho de execução no ePSXe.'})
    return total,found


def diagnose_god24_monster_classification(exe: bytes) -> dict:
    """Inspeciona o caso God24 sem alterar bytes nem assumir suporte retail."""
    result={
        'status':'somente_leitura',
        'tipo_solicitado':24,
        'limite_retail_monstro':GOD24_MONSTER_LIMIT,
        'atk_def_armazenados_podem_ficar_ocultos':True,
        'tipo_24_funciona_como_monstro_ps1':False,
        'icone_deus_de_tipo_instalado':False,
        'escrita_no_slus':False,
        'alerta':'Tipo 24 é >=20: o motor original não o classifica como '
                 'monstro. Trocar sltiu 20 por 25 NÃO é seguro, pois incluiria '
                 'os quatro tipos de cartas não-monstro. Cada caminho requer '
                 'uma condição exclusiva para God24, preservando as categorias 20–23.',
        'rotinas':{},
    }
    if len(exe)<0x800 or exe[:8]!=b'PS-X EXE':
        result['status']='executavel_psx_invalido'
        return result
    load,code_size=struct.unpack_from('<II',exe,0x18)
    if (load!=EXE_DELTA+0x800 or not code_size or code_size%4
            or 0x800+code_size>len(exe)):
        result['status']='segmento_mips_invalido'
        return result
    result['sha256_executavel']=hashlib.sha256(exe).hexdigest()
    result['segmento_mips']={'ram':f'0x{load:08X}','tamanho':code_size}
    total=0
    for key,(name,ram,size,description) in GOD24_MONSTER_SITES.items():
        offset=ram-EXE_DELTA
        entry={'funcao':name,'endereco_ram':f'0x{ram:08X}',
               'offset_slus':f'0x{offset:X}','motivo':description}
        if offset<0x800 or offset+size>0x800+code_size:
            entry.update(status='fora_segmento_carregado',
                         comparacoes_imediato_20_total=0,
                         comparacoes_imediato_20=[])
        else:
            chunk=exe[offset:offset+size]
            count,sites=_god24_compare_entries(chunk,ram,offset)
            total+=count
            entry.update(status='assinatura_nao_validada_analise_estatica',
                         hash_sha256=hashlib.sha256(chunk).hexdigest(),
                         bytes_regiao=size,
                         comparacoes_imediato_20_total=count,
                         comparacoes_imediato_20=sites)
        result['rotinas'][key]=entry
    result['comparacoes_imediato_20_total']=total
    result['cobertura']='amostragem_estatica_nao_exaustiva'
    result['proximo_passo']='Verificar os predicados de monstro em cada '
                           'região com o SLUS real, fluxo eABI; inserir '
                           'um teste ==24 exclusivo com código validado e '
                           'preservar os tipos 20–23. Validar no ePSXe.'
    return result


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
        'versao_perfil':4,'alvo':'SLUS_014.11 (PS1 MIPS)',
        'sha256_executavel_origem':hashlib.sha256(exe).hexdigest(),
        'funcoes_encontradas':scan_effect_sites(exe),
        'amostras_instrucoes_mips':{alias:inspect_function_instructions(exe,alias)
                                    for alias in SITES},
        'referencias_chamadas_mips':scan_direct_mips_calls(exe),
        'diagnostico_icone_tipo_god':diagnose_god_type_icon(exe),
        'chamadas_mips_icone_tipo_god':scan_god24_render_calls(exe),
        'diagnostico_god24_classe_monstro':diagnose_god24_monster_classification(exe),
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
