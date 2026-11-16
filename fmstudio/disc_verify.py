"""Auditoria da tabela de cartas no arquivo BIN/CUE realmente selecionado."""
from __future__ import annotations
import hashlib
import struct
from pathlib import Path
from .core import ModError, god24_experiment_enabled
from .disc import DiscReader, DiscError
from .tables import decode_cards, CARD_COUNT

FIELDS = ('ataque', 'defesa', 'tipo_id', 'atributo_id', 'nivel',
          'guardian_1_id', 'guardian_2_id')


def inspect_god24_chest_mips(exe: bytes) -> dict:
    """Verifica patches em bytes do SLUS, não sua execução no ePSXe."""
    from .ps1_god24_chest import OLD, NEW, SITES
    checked=[]
    for offset,pattern,name in SITES:
        if offset<4 or offset+16>len(exe):
            status='fora_do_arquivo'
            current=None
        else:
            words=struct.unpack_from('<5I',exe,offset-4)
            current=words[1]
            if words==pattern:
                status='original_sem_patch'
            elif words==pattern[:1]+(NEW,)+pattern[2:]:
                status='patch_presente'
            else:
                status='sequencia_divergente'
        checked.append({'rotina':name,'offset_slus':f'0x{offset:X}',
                        'estado':status,
                        'opcode_lido':f'0x{current:08X}' if current is not None else None,
                        'opcode_original':f'0x{OLD:08X}',
                        'opcode_esperado':f'0x{NEW:08X}'})
    states=[item['estado'] for item in checked]
    if all(x=='patch_presente' for x in states):
        overall='aplicado_2_de_2'
    elif all(x=='original_sem_patch' for x in states):
        overall='nao_aplicado_0_de_2'
    elif all(x in ('patch_presente','original_sem_patch') for x in states):
        overall='parcial_1_de_2'
    else:
        overall='opcodes_desconhecidos'
    return {'status':overall,'pontos':checked,
            'total_aplicados':sum(x=='patch_presente' for x in states),
            'validado_no_epsxe':False,
            'aviso':'Bytes do arquivo selecionado; não indica qual BIN o ePSXe executa.'}


def verify_image_stats(project, source):
    try:
        with DiscReader(Path(source)) as image:
            entries = {e.path.upper():e for e in image.files() if not e.is_dir}
            if 'SLUS_014.11' not in entries:
                raise ModError('SLUS_014.11 ausente do disco.')
            exe = b''.join(image.read_entry(entries['SLUS_014.11']))
            cards, _ = decode_cards(exe)
            image_path = str(image.path.resolve())
    except DiscError as exc:
        raise ModError(f'Imagem de disco inválida: {exc}') from exc
    result = []
    for key, edits in sorted(getattr(project, 'edits', {}).items(),
                             key=lambda pair:int(pair[0])):
        cid = int(key)
        if cid < 1 or cid > CARD_COUNT:
            continue
        requested = project.get(cid)
        original = project.cards[cid]
        if (int(requested.get('tipo_id',0)) >= 24 and
                not god24_experiment_enabled(project,cid)) or int(requested.get('atributo_id',0)) > 5:
            if set(edits) & set(FIELDS):
                raise ModError(f'Carta #{cid:03d}: tipo/atributo incompatível com '
                               'o motor PS1. Não é seguro omitir esta carta da '
                               'verificação da imagem.')
            continue
        fields = {}
        for field in FIELDS:
            if field not in edits:
                continue
            want = int(requested[field])
            was = int(original[field])
            if want == was:
                continue
            got = int(cards[cid-1][field])
            fields[field] = {'base':was,'projeto':want,'bin':got,'ok':got==want}
        if fields:
            result.append({'id':cid,'nome':str(requested.get('nome','')),
                           'campos':fields,
                           'ok':all(f['ok'] for f in fields.values())})
    experimental=[r['id'] for r in result
                  if god24_experiment_enabled(project,r['id'])]
    card_types_24=[{'id':c['id'],'ataque':c['ataque'],'defesa':c['defesa']}
                   for c in cards if c['tipo_id']==24]
    config=getattr(project,'metadata',{}) or {}
    cid=config.get('ps1_god_type_test_card_id')
    tested=cards[cid-1] if type(cid) is int and 1<=cid<=CARD_COUNT else None
    chest=inspect_god24_chest_mips(exe)
    return {'imagem':image_path,'sha256_slus':hashlib.sha256(exe).hexdigest(),
            'god24_mascaras_bau':chest,
            'god24_teste_bau_ativado_no_projeto':bool(config.get('ps1_god_chest_preview')),
            'god24_total_cartas_no_bin':len(card_types_24),
            'god24_cartas_no_bin':card_types_24[:25],
            'god24_carta_teste_no_bin':(
                {'id':cid,'tipo_id':tested['tipo_id'],'ataque':tested['ataque'],
                 'defesa':tested['defesa']} if tested else None),
            'god24_tipo_gravado_e_verificado':experimental,
            'god24_aviso':'Byte tipo 24 verificado; comportamento no ePSXe NÃO confirmado.' if experimental else '',
            'total':len(result),'corretas':sum(r['ok'] for r in result),
            'divergentes':sum(not r['ok'] for r in result),'cartas':result}


def describe(result):
    text = [f'Imagem selecionada: {result["imagem"]}', '',
            f'Cartas numéricas conferidas: {result["total"]}',
            f'Corretas: {result["corretas"]} | Divergentes: {result["divergentes"]}']
    if result.get('god24_tipo_gravado_e_verificado'):
        text.append('God 24 gravado como 5 bits: SIM (experimental). '
                    'O jogo pode não reconhecer como monstro; validar no ePSXe.')
    if result.get('god24_total_cartas_no_bin') or result.get('god24_teste_bau_ativado_no_projeto'):
        status=result['god24_mascaras_bau']
        text.append('\nGOD24 — MÁSCARAS MIPS NO BIN/CUE SELECIONADO:')
        text.append('  '+status['status']+' ('+str(status['total_aplicados'])+'/2)')
        for site in status['pontos']:
            text.append('  '+site['rotina']+' em '+site['offset_slus']+
                        ': '+str(site['opcode_lido'])+' — '+site['estado'])
        tw=result.get('god24_carta_teste_no_bin')
        if tw:
            text.append(f"  Carta #{tw['id']:03d}: tipo {tw['tipo_id']}, "
                        f"ATK {tw['ataque']}, DEF {tw['defesa']}")
        if status['status']=='aplicado_2_de_2':
            text.append('  As máscaras estão no BIN. Se ATK/DEF continuam '
                        'ocultos no ePSXe, confirme o BIN aberto e verifique '
                        'outros caminhos de desenho.')
        else:
            text.append('  As duas máscaras NÃO estão aplicadas nesta imagem. '
                        'Ative o teste de baú e gere uma nova cópia.')
    for card in result['cartas'][:10]:
        text.append(f'\n#{card["id"]:03d} {card["nome"]}: '
                    + ('OK' if card['ok'] else 'DIVERGENTE'))
        for field,info in card['campos'].items():
            text.append(f'  {field}: original {info["base"]}, projeto {info["projeto"]}, BIN {info["bin"]}')
    if len(result['cartas']) > 10:
        text.append(f'\n... mais {len(result["cartas"])-10} cartas no relatório.')
    text.append('\nA conferência só valida o arquivo selecionado; não identifica o que o ePSXe executou.')
    return '\n'.join(text)
