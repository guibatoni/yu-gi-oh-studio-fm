"""Auditoria da tabela de cartas no arquivo BIN/CUE realmente selecionado."""
from __future__ import annotations
import hashlib
import struct
from pathlib import Path
from .core import ModError, ps1_god24_card_ids, ps1_supports_god24
from .disc import DiscReader, DiscError
from .expanded import GOD_TYPE_ID
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
    from .ps1_god24_display import inspect as inspect_god_display
    from .ps1_runtime import compile_effects, verify_effects
    from .ps1_mod import compile_mod, verify_executable, verify_wa, wa_sha
    config=getattr(project,'metadata',{}) or {}
    profile=ps1_supports_god24(project)
    mod_plan=compile_mod(project,profile=profile,
                         wa_verified=bool(config.get('edicao_mod') and wa_sha(project)))
    wa=b''
    try:
        with DiscReader(Path(source)) as image:
            entries = {e.path.upper():e for e in image.files() if not e.is_dir}
            if 'SLUS_014.11' not in entries:
                raise ModError('SLUS_014.11 ausente do disco.')
            exe = b''.join(image.read_entry(entries['SLUS_014.11']))
            cards, _ = decode_cards(exe)
            god_display = inspect_god_display(exe)
            if god_display['status'] == 'aguardando_textura' or mod_plan.needs_wa:
                entry = entries.get('DATA/WA_MRG.MRG')
                wa = b''.join(image.read_entry(entry)) if entry else b''
            if god_display['status'] == 'aguardando_textura':
                god_display = inspect_god_display(exe, wa)
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
        if requested.get('virtual'):
            continue
        original = project.cards[cid]
        typ=int(requested.get('tipo_id',0))
        if (typ > GOD_TYPE_ID or (typ == GOD_TYPE_ID and not profile)
                or int(requested.get('atributo_id',0)) > 5):
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
    card_types_24=[{'id':c['id'],'ataque':c['ataque'],'defesa':c['defesa']}
                   for c in cards if c['tipo_id']==GOD_TYPE_ID]
    expected_gods=ps1_god24_card_ids(project)
    actual_gods={c['id'] for c in card_types_24}
    verified_gods=[cid for cid in expected_gods if cid in actual_gods]
    god24_enabled=profile and bool(expected_gods)
    plan=compile_effects(project,profile,fixed_decks=mod_plan.fixed_decks,
                         fusions=mod_plan.fusions)
    original = None
    project_folder = getattr(project, 'folder', None)
    if plan.data and project_folder is not None:
        original_exe = project_folder / 'base' / 'source_SLUS_014.11'
        if original_exe.is_file():
            original = original_exe.read_bytes()
    runtime = verify_effects(exe, plan, original=original)
    opening_lock, life=verify_executable(exe,mod_plan)
    tested=cards[expected_gods[0]-1] if expected_gods else None
    chest=inspect_god24_chest_mips(exe)
    from .ps1_god24_chest import audit_god24_build_deck_rows
    row_renderer=audit_god24_build_deck_rows(exe)
    from .ps1_god24_hand import inspect as inspect_hand_god
    from .ps1_god24_play import inspect as inspect_duel_god
    duel_patch=inspect_duel_god(exe)
    legacy_hand_patch=inspect_hand_god(exe)
    hand=duel_patch['etapas']['mao']
    if hand['aplicados'] == hand['total']:
        legacy_hand_patch={'status':'substituido_pelo_patch_de_duelo',
                           'quantidade_aplicada':0,'instrucoes':[]}
    return {'imagem':image_path,'sha256_slus':hashlib.sha256(exe).hexdigest(),
            'god24_mascaras_bau':chest,
            'god24_renderizador_lista_bau':row_renderer,
            'god24_mascara_da_mao':legacy_hand_patch,
            'god24_roteamento_duelo':duel_patch,
            'god24_exibicao_tipo':god_display,
            'efeitos_nativos_ps1':runtime,
            'edicao_do_mod_ps1':{'bloqueio_turno_inicial':opening_lock if profile else None,
                                'lp':life,'tabelas':verify_wa(wa,mod_plan)},
            'god24_teste_mao_ativado_no_projeto':god24_enabled,
            'god24_teste_bau_ativado_no_projeto':god24_enabled,
            'god24_cartas_esperadas':expected_gods,
            'god24_tipos_conferem':actual_gods==set(expected_gods),
            'god24_total_cartas_no_bin':len(card_types_24),
            'god24_cartas_no_bin':card_types_24[:25],
            'god24_carta_teste_no_bin':(
                {'id':tested['id'],'tipo_id':tested['tipo_id'],'ataque':tested['ataque'],
                 'defesa':tested['defesa']} if tested else None),
            'god24_tipo_gravado_e_verificado':verified_gods,
            'god24_aviso':'Tipo 24 conferido na tabela do BIN.' if verified_gods else '',
            'total':len(result),'corretas':sum(r['ok'] for r in result),
            'divergentes':sum(not r['ok'] for r in result),'cartas':result}


def describe(result):
    text = [f'Imagem selecionada: {result["imagem"]}', '',
            f'Cartas numéricas conferidas: {result["total"]}',
            f'Corretas: {result["corretas"]} | Divergentes: {result["divergentes"]}']
    runtime=result.get('efeitos_nativos_ps1',{})
    if runtime.get('status')=='aplicado':
        text.append(f'Efeitos nativos conferidos na cópia: {runtime["quantidade"]}.')
        fusions = runtime.get('fusoes', [])
        if fusions:
            text.append(f'Fusões personalizadas conferidas no BIN: {len(fusions)}.')
            for row in fusions[:5]:
                text.append(f'  #{row["material_1"]:03d} + #{row["material_2"]:03d} → #{row["resultado"]:03d}')
        if runtime.get('decks_fixos'):
            ids = ', '.join(f'#{opponent:02d}' for opponent in runtime['decks_fixos'])
            text.append(f'Decks fixos de 40 cartas conferidos para os duelistas {ids}.')
        if runtime.get('nomes_tier'):
            text.append(f'Cores de tier conferidas nos nomes de {runtime["nomes_tier"]} cartas.')
        if runtime.get('drops_do_deck'):
            text.append(f'Drops do próprio deck conferidos para {len(runtime["drops_do_deck"])} duelista(s).')
        prefix = runtime.get('password_id_prefix')
        if prefix is not None:
            text.append(f'Passwords por ID usam {prefix:05d} + os três dígitos do ID da carta.')
    elif runtime.get('status')=='divergente':
        text.append('As regras nativas desta cópia divergem do projeto. Gere outro BIN/CUE.')
    mod=result.get('edicao_do_mod_ps1',{})
    if mod.get('bloqueio_turno_inicial') is True:
        text.append('Trava de ataque no primeiro turno conferida no executável.')
    elif mod.get('bloqueio_turno_inicial') is False:
        text.append('A trava de ataque no primeiro turno diverge do projeto. Gere outro BIN/CUE com a base original.')
    if not mod.get('lp',True) or not mod.get('tabelas',True):
        text.append('Os LP ou as tabelas de duelistas desta cópia divergem do projeto.')
    if result.get('god24_tipo_gravado_e_verificado'):
        text.append(f'God 24 gravado em {len(result["god24_tipo_gravado_e_verificado"])} carta(s).')
    if not result.get('god24_tipos_conferem',True):
        text.append('As cartas do tipo God no BIN divergem do projeto. Gere uma nova cópia.')
    if result.get('god24_total_cartas_no_bin') or result.get('god24_teste_bau_ativado_no_projeto'):
        status=result['god24_mascaras_bau']
        text.append('\nGOD24 — MÁSCARAS MIPS NO BIN/CUE SELECIONADO:')
        text.append('  '+status['status']+' ('+str(status['total_aplicados'])+'/2)')
        display=result.get('god24_exibicao_tipo',{})
        if display.get('icone_instalado'):
            text.append('  Tipo God e ícone conferidos no BIN. Veja os detalhes da carta com Triângulo.')
        elif result.get('god24_teste_bau_ativado_no_projeto'):
            text.append('  Exibição do tipo God pendente. Gere uma nova cópia a partir do BIN de origem.')
        duel=result['god24_roteamento_duelo']
        if result.get('god24_teste_mao_ativado_no_projeto') or duel['pontos_aplicados']:
            labels={'mao':'mão','fileira':'fileira de monstros','colocacao':'colocação',
                    'confirmacao':'confirmação','exibicao':'exibição'}
            phases=', '.join(f"{labels[name]} {phase['aplicados']}/{phase['total']}"
                             for name,phase in duel['etapas'].items())
            text.append(f"  GOD24 EM DUELO ({duel['status']}): {phases}.")
            if duel['status']=='aplicado':
                text.append('  Patch conferido no BIN. Valide a jogada no ePSXe.')
            elif duel['status']=='parcial' and not duel['etapas']['fileira']['aplicados']:
                text.append('  Esta cópia ainda não tem a correção da fileira de monstros. '
                            'Gere outro BIN/CUE a partir do disco de origem.')
        if result['god24_mascara_da_mao']['quantidade_aplicada']:
            text.append('  Detectado o teste anterior, limitado à mão. '
                        'Gere uma nova cópia para testar a colocação.')
        rows=result['god24_renderizador_lista_bau']
        text.append('  RENDERIZADOR REAL DAS LINHAS: func_80031874 — '+rows['status'])
        row_test=rows.get('god24_patch_lista',{})
        text.append('  PATCH DA LISTA DE OITO LINHAS: '+
                    row_test.get('status','indisponível'))
        for item in row_test.get('instrucoes',[]):
            text.append('    '+item['offset_slus']+' = '+
                        item['encontrado']+' ('+item['estado']+')')
        text.append('  Comparações tipo<20 nesta rotina: '+
                    str(rows.get('total_comparacoes_imediato_20','indisponível')))
        for candidate in rows['potenciais_comparacoes_tipo_20'][:3]:
            text.append('    Candidato '+candidate['pc']+
                        ', offset '+candidate['offset_slus']+
                        ', opcode '+candidate['opcode'])
        for site in status['pontos']:
            text.append('  '+site['rotina']+' em '+site['offset_slus']+
                        ': '+str(site['opcode_lido'])+' — '+site['estado'])
        tw=result.get('god24_carta_teste_no_bin')
        if tw:
            text.append(f"  Carta #{tw['id']:03d}: tipo {tw['tipo_id']}, "
                        f"ATK {tw['ataque']}, DEF {tw['defesa']}")
        if status['status']=='aplicado_2_de_2':
            if row_test.get('status')=='aplicado_3_de_3':
                text.append('  2/2 máscaras e 3/3 opcodes confirmados no BIN. '
                            'Verifique os atributos no ePSXe.')
            else:
                text.append('  As duas máscaras não alteram func_80031874. '
                            'Aplique o patch da lista e gere outro BIN.')
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
