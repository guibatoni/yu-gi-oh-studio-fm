"""Extrator de recursos conhecidos da versão norte-americana de Forbidden Memories.

Lê exclusivamente bytes fornecidos pelo usuário. Os mapeamentos de bancos de texto,
registros de imagens e offsets são provenientes da pesquisa de engenharia reversa
publicada no projeto Yu-Gi-Oh! Forbidden Memories Re-Decomp/PC (MIT), em especial
notes/pc-build.md, tools/pc/text_listing.py e tools/pc/extract_images.py.
Implementação independente e limitada aos formatos descritos. Respeita limites de
arquivos, não decodifica código desconhecido como texto e não escreve no disco PS1.
"""
from __future__ import annotations

import csv
import hashlib
import json
import struct
import unicodedata
import zlib
from pathlib import Path

CARD_COUNT = 722
EXE_START = 0x80010000
EXE_HEADER = 0x800
BANK_NAMES = 0x801D0000
BANK_DESC = 0x801C0000
BANK_DIALOG = 0x801B0000
NAME_TABLE = 0x801D5800
STRING_TABLE = 0x801C0000
GLYPH_TABLE = 0x801D9000
GLYPH_COUNT = 0x5C
WA_SECTOR = 2048

class ExtractionError(ValueError):
    pass


def exe_pos(address: int, data: bytes, count: int = 1) -> int:
    pos = address - EXE_START + EXE_HEADER
    if pos < 0 or count < 0 or pos + count > len(data):
        raise ExtractionError(f'Endereço do executável fora dos limites: 0x{address:08X} + {count}')
    return pos


def exe_block(raw: bytes, addr: int, size: int) -> bytes:
    return raw[exe_pos(addr,raw,size):exe_pos(addr,raw,size)+size]


def exe_u16(raw: bytes, addr: int) -> int:
    return struct.unpack_from('<H',raw,exe_pos(addr,raw,2))[0]


def glyph_map(exe: bytes) -> tuple[dict[int,str],list[str]]:
    cmap = {0:' '}
    warn = []
    # Quase todas as cartas em inglês usam caracteres simples e glifos Shift-JIS.
    overrides = {0x1B:"'",0x40:'"',0x27:'«',0x28:'»',0x30:'-',0x47:'·'}
    for code in range(1,GLYPH_COUNT):
        sjis = struct.unpack('<I',exe_block(exe,GLYPH_TABLE+code*4,4))[0] & 0xFFFF
        if not sjis: continue
        if code in overrides:
            cmap[code]=overrides[code]
            continue
        try:
            cmap[code]=unicodedata.normalize('NFKC',bytes((sjis>>8,sjis&0xff)).decode('shift_jis'))
        except (ValueError,UnicodeDecodeError) as e:
            cmap[code]='�'
            warn.append(f'Glifo 0x{code:02X}: Shift-JIS não decodificado ({sjis:04X})')
    return cmap,warn

F8_OPERANDS = {
 0x00:1,0x01:1,0x02:1,0x03:5,0x04:1,0x05:2,0x06:2,0x07:2,
 0x08:0,0x09:0,0x0A:1,0x0B:1,0x0C:1,0x0D:6,0x0E:2,0x11:1,0x12:0,
 0x13:0,0x14:1,0x15:1,0x16:0,0x19:1,0x1A:0,0x1B:1,0x1C:1,
 0x1D:1,0x1E:1,0x1F:1,0x20:1,0x21:2,0x22:1,0x25:0,
 0x27:2,0x28:2,0x29:0,0x2A:0,
}


def decode_text(exe: bytes, bank: int, offset: int, cmap:dict[int,str], *, limit: int=1024) -> tuple[str,list[str]]:
    """Decodifica uma sequência linear; comandos de salto/call são preservados como marcas.

    O texto não é reconstruído por fluxo de controle como no extrator de listagens
    completo: em caso de salto, registra o destino e encerra o trecho de modo seguro.
    """
    if not (0 < offset < 0x10000):
        return '', [f'Offset não utilizável: 0x{offset:04X}']
    try:
        memory = exe_block(exe,bank,0x10000)
    except ExtractionError as e:
        return '',[str(e)]
    text=[]; warnings=[]; p=offset
    while 0 <= p < len(memory) and p-offset < limit:
        c=memory[p]; p+=1
        if c < 0xF0:
            text.append(cmap.get(c, f'{{g {c:02X}}}'))
        elif c <= 0xF5:
            if p >= len(memory): break
            text.append(f'{{g {((c-0xF0)<<8) | memory[p]:03X}}}')
            p+=1
        elif c==0xF6:
            text.append(f'{{fx {memory[p:p+2].hex(" ")}}}');p+=2
        elif c==0xF7:
            if p >= len(memory): break
            state=memory[p];p+=1
            nargs={0x05:2,0x0B:6,0x0F:2,0x10:2}.get(state & 0x1f,0)
            if state & 0x1f == 0x05 and p+1 < len(memory) and (memory[p]|memory[p+1]<<8)&0x8000: nargs=5
            raw=memory[p:p+nargs];p+=len(raw)
            text.append(f'{{state {state:02X} {raw.hex(" ")}}}')
        elif c==0xF8:
            if p >= len(memory):break
            ctrl=memory[p];p+=1
            if ctrl in (0x17,0x18):
                text.append(f'{{f8 {ctrl:02X} salto}}')
                break
            nargs=F8_OPERANDS.get(ctrl)
            if nargs is None:
                warnings.append(f'F8 {ctrl:02X} desconhecido a 0x{p-2:04X}')
                text.append(f'{{F8 {ctrl:02X} ?}}')
                break
            if ctrl==0x0F: nargs=1+(2 if p < len(memory) and memory[p]&0x3f else 0)
            if ctrl==0x10: nargs=2+(2 if p+1 < len(memory) and memory[p+1]&0x80 else 0)
            text.append(f'{{f8 {ctrl:02X} {memory[p:p+nargs].hex(" ")}}}')
            p+=nargs
            if ctrl in (0x28,0x2A): break
        elif c==0xF9:
            if p+1 >= len(memory):break
            flags=memory[p]|(memory[p+1]<<8);p+=2
            if flags&0x4000:
                text.append(f'{{set {flags:04X}}}')
            else:
                target=int.from_bytes(memory[p:p+2],'little');p+=2
                text.append(f'{{if {flags:04X} L{target:04X}}}')
        elif c==0xFA:
            text.append('{page}')
        elif c==0xFB:
            if p >= len(memory):break
            opt=memory[p];p+=1
            text.append(f'{{choice {opt:02X}}}')
            if opt&0x08:p+=1
            if opt&0x80:
                warnings.append('Comando de escolhas ramificadas: extração linear parcial')
                break
        elif c in (0xFC,0xFD):
            if p+1 >= len(memory):break
            target=int.from_bytes(memory[p:p+2],'little');p+=2
            text.append('{'+('call' if c==0xFC else 'jump')+f' L{target:04X}'+'}')
            if c==0xFD: break
        elif c==0xFE:
            text.append('\n')
        else:
            return ''.join(text).strip(), warnings
    if p-offset >= limit:
        warnings.append(f'Texto interrompido por limite de segurança {limit} bytes')
    elif p >= len(memory):
        warnings.append('Texto interrompido por fim de banco')
    return ''.join(text).strip(), warnings


def extract_texts(exe:bytes) -> tuple[dict[str,list[dict]],list[str]]:
    if not exe.startswith(b'PS-X EXE'):
        raise ExtractionError('Executável inválido, esperado cabeçalho PS-X EXE')
    glyphs,warns=glyph_map(exe)
    names=[]; desc=[]; other=[]; card_names={}; card_desc={}
    # Nomes: 0x360 entradas, inclui 722 cartas e outros nomes do jogo.
    for idx in range(0x360):
        off=exe_u16(exe,NAME_TABLE+idx*2)
        text,problems=decode_text(exe,BANK_NAMES,off,glyphs,limit=220)
        entry={'codigo':f'{0x8000+idx:04X}','id':idx,'texto':text,'origem':'SLUS: banco de nomes',
               'endereco':f'0x{BANK_NAMES+off:08X}' if off else '',
               'avisos':' | '.join(problems)}
        names.append(entry)
        if 1<=idx<=CARD_COUNT:card_names[idx]=text
    # Descrições: códigos D100 até D3FF; algumas entradas após as cartas.
    for idx in range(0x100,0x400):
        off=exe_u16(exe,STRING_TABLE+idx*2)
        text,problems=decode_text(exe,BANK_DESC,off,glyphs,limit=1024)
        cid=idx-0x100
        desc.append({'codigo':f'{0xD000+idx:04X}','id':cid,'texto':text,
                     'origem':'SLUS: banco de descrições','endereco':f'0x{BANK_DESC+off:08X}' if off else '',
                     'avisos':' | '.join(problems)})
        if 1<=cid<=CARD_COUNT:card_desc[cid]=text
    # Menus e diálogos: índices 000-0FF e 500-5F9.
    for idx in list(range(0x100))+list(range(0x400,0x4FA)):
        off=exe_u16(exe,STRING_TABLE+idx*2)
        bank=BANK_DIALOG
        text,problems=decode_text(exe,bank,off,glyphs,limit=2048)
        code=idx if idx<0x100 else idx+0x100
        other.append({'codigo':f'{code:04X}', 'tipo':'menu' if idx<0x100 else 'historia',
                      'texto':text,'origem':'SLUS: banco de diálogos',
                      'endereco':f'0x{bank+off:08X}' if off else '',
                      'avisos':' | '.join(problems)})
    rows=[]
    for cid in range(1,CARD_COUNT+1):
        rows.append({'id':cid,'nome':card_names.get(cid,''), 'descricao':card_desc.get(cid,''),
                     'nome_origem':f'8000+{cid:04X}', 'descricao_codigo':f'{0xD100+cid:04X}',
                     'nome_presente':int(bool(card_names.get(cid,''))),
                     'descricao_presente':int(bool(card_desc.get(cid,'')))})
    metrics={
        'nomes_cartas':sum(bool(r['nome']) for r in rows),
        'descricoes_cartas':sum(bool(r['descricao']) for r in rows),
        'strings_nomes':len(names),'strings_descricoes':len(desc),'strings_menu_historia':len(other),
        'avisos_nomes':sum(bool(x['avisos']) for x in names),
        'avisos_descricoes':sum(bool(x['avisos']) for x in desc),
        'avisos_menu_historia':sum(bool(x['avisos']) for x in other),
    }
    # Não repetir centenas de avisos em GUI; todos estão em CSV de proveniência.
    if metrics['nomes_cartas']<CARD_COUNT:
        warns.append(f'Nem todos os nomes foram decodificados: {metrics["nomes_cartas"]}/{CARD_COUNT}')
    if metrics['descricoes_cartas']<CARD_COUNT:
        warns.append(f'Nem todas as descrições foram decodificadas: {metrics["descricoes_cartas"]}/{CARD_COUNT}')
    return {'nomes_descricoes':rows,'textos_nomes':names,'textos_descricoes':desc,
            'textos_menu_historia':other,'metricas_texto':[metrics]},warns


def _colors(data:bytes,pos:int,count:int) -> list[bytes]:
    if pos<0 or pos+count*2>len(data):
        raise ExtractionError(f'Paleta fora do arquivo WA a 0x{pos:X}')
    colors=[]
    for v in struct.unpack_from('<'+'H'*count,data,pos):
        if not v: colors.append(bytes((0,0,0,0)))
        else:
            r=v & 31;g=(v>>5)&31;b=(v>>10)&31
            colors.append(bytes((r<<3|r>>2,g<<3|g>>2,b<<3|b>>2,255)))
    return colors


def _indexed_png_bytes(data:bytes, offset:int, words:int, height:int, palette:list[bytes]) -> bytes:
    width=words*2
    if offset<0 or offset+words*2*height>len(data):
        raise ExtractionError(f'Imagem fora de WA_MRG: 0x{offset:X}')
    # Cada par de bytes armazena dois pixels indexados (8 bits por pixel).
    pixels=data[offset:offset+words*2*height]
    rgba=b''.join(palette[b] if b<len(palette) else bytes((0,0,0,0)) for b in pixels)
    row_len=width*4
    scanlines=b''.join(b'\x00'+rgba[i:i+row_len] for i in range(0,len(rgba),row_len))
    def chunk(kind:bytes,payload:bytes):
        return len(payload).to_bytes(4,'big')+kind+payload+(zlib.crc32(kind+payload)&0xffffffff).to_bytes(4,'big')
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+
            chunk(b'IDAT',zlib.compress(scanlines,6))+chunk(b'IEND',b''))


def _art_image(data:bytes,at:int,words:int,rows:int,pal_at:int,pal_count:int):
    return _indexed_png_bytes(data,at,words,rows,_colors(data,pal_at,pal_count))


def export_visuals(wa:bytes,output:Path, *, include_strips:bool=False, include_portraits:bool=True,
                   progress=None) -> tuple[dict[str,int],list[dict],list[str]]:
    """722 artes 102×96, 722 miniaturas 40×32, e 65 retratos 48×48.

    As faixas laterais e inferiores das cartas são opt-in porque os bancos
    modificados nem sempre preservam todos os recursos. Falhas por registro
    são reportadas, sem abortar a importação das outras imagens.
    """
    output=Path(output)
    path_cards=output/'cartas'; path_small=output/'miniaturas'; path_portraits=output/'retratos'
    for p in (path_cards,path_small,path_portraits):p.mkdir(parents=True,exist_ok=True)
    manifest=[];errors=[]
    metrics={'artes':0,'miniaturas':0,'faixas':0,'retratos':0,'cenas_historia':0}
    for cid in range(1,CARD_COUNT+1):
        cardbase=((cid-1)*7+722)*WA_SECTOR
        thumb=(cid-1)*WA_SECTOR
        operations=[('arte',cardbase,0x33,0x60,cardbase+0x2640,256,path_cards/f'{cid:03d}.png'),
                    ('miniatura',thumb,20,32,thumb+0x500,64,path_small/f'{cid:03d}.png')]
        if include_strips:
            operations.extend([
                ('faixa_inferior',cardbase+0x2840,0x18,0x0E,cardbase+0x2640,256,path_cards/f'{cid:03d}_faixa.png'),
                ('faixa_lateral',cardbase+0x2AE0,0x08,0x58,cardbase+0x2640,256,path_cards/f'{cid:03d}_lateral.png')])
        for kind,offset,words,rows,pal,n,out in operations:
            try:
                image=_art_image(wa,offset,words,rows,pal,n)
                out.write_bytes(image)
                metrics['artes' if kind=='arte' else 'miniaturas' if kind=='miniatura' else 'faixas']+=1
                manifest.append({'tipo':kind,'id':cid,'arquivo':str(out.relative_to(output)).replace('\\','/'),
                                 'origem':'DATA/WA_MRG.MRG','offset':f'0x{offset:X}',
                                 'paleta_offset':f'0x{pal:X}', 'largura':words*2,'altura':rows,
                                 'sha256_png':hashlib.sha256(image).hexdigest()})
            except (ExtractionError, OSError,IndexError) as e:
                errors.append(f'carta {cid:03d} {kind}: {e}')
        if progress and cid in (1,100,200,300,400,500,600,700,722):progress(f'Artes e miniaturas: {cid}/722')
    if include_portraits:
        for name,base,count in [('campanha',0xF35000,25),('duelo_livre',0xF55000,40)]:
            for idx in range(count):
                off=base+idx*0x980
                out=path_portraits/f'{name}_{idx:02d}.png'
                try:
                    image=_art_image(wa,off,24,48,off+0x900,64)
                    out.write_bytes(image)
                    metrics['retratos']+=1
                    manifest.append({'tipo':'retrato','id':idx,'grupo':name,'arquivo':str(out.relative_to(output)).replace('\\','/'),
                                     'origem':'DATA/WA_MRG.MRG','offset':f'0x{off:X}',
                                     'paleta_offset':f'0x{off+0x900:X}',
                                     'largura':48,'altura':48,'sha256_png':hashlib.sha256(image).hexdigest()})
                except (ExtractionError, OSError) as e:
                    errors.append(f'retrato {name} {idx:02d}: {e}')
    # Cenas do modo história: registros de 33, 81 e 113 setores.
    # A paleta 8bpp ocupa o último setor do registro. Cada coluna é formada
    # por 16 setores (128 px x 256 px). Montagem em imagem lateral para visualização.
    scene_dir=output/'cenas_historia'
    scene_dir.mkdir(parents=True,exist_ok=True)
    for mode,(sectors,first,count) in enumerate(((0x21,0,50),(0x51,0x672,42),(0x71,0x13BC,13))):
        columns=(sectors-1)//16
        for idx in range(count):
            off=(0x21D5+first+idx*sectors)*WA_SECTOR
            color_off=off+(sectors-1)*WA_SECTOR
            name=f'cena_m{mode}_{idx:02d}.png'
            try:
                palette=_colors(wa,color_off,256)
                # A estrutura armazena uma coluna por vez, concatenadas horizontalmente.
                pictures=[wa[off+k*32768:off+(k+1)*32768] for k in range(columns)]
                if any(len(x)!=32768 for x in pictures):
                    raise ExtractionError('Bloco de história incompleto')
                width=128*columns
                rows=[]
                for y in range(256):
                    row=b''.join(pictures[k][y*128:(y+1)*128] for k in range(columns))
                    rows.append(b'\x00'+b''.join(palette[p] for p in row))
                def chunk(kind,payload):
                    return len(payload).to_bytes(4,'big')+kind+payload+(zlib.crc32(kind+payload)&0xffffffff).to_bytes(4,'big')
                png=(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,256,8,6,0,0,0))+
                     chunk(b'IDAT',zlib.compress(b''.join(rows),6))+chunk(b'IEND',b''))
                path=scene_dir/name
                path.write_bytes(png)
                metrics['cenas_historia']+=1
                manifest.append({'tipo':'cena_historia','id':idx,'modo':mode,'arquivo':str(path.relative_to(output)).replace('\\','/'),
                                 'origem':'DATA/WA_MRG.MRG','offset':f'0x{off:X}',
                                 'paleta_offset':f'0x{color_off:X}', 'largura':width,'altura':256,
                                 'sha256_png':hashlib.sha256(png).hexdigest(),
                                 'nota':'Representação técnica das colunas; variações visuais podem depender do motor'})
            except (ExtractionError,OSError) as e:
                errors.append(f'cena {mode}:{idx:02d}: {e}')
        if progress:progress(f'Cenas da história: modo {mode+1}/3')
    return metrics,manifest,errors


def write_semicolon_csv(path:Path, rows:list[dict]):
    if not rows:return
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter=';',extrasaction='ignore')
        writer.writeheader();writer.writerows(rows)


def prepare_full_catalog(base:Path,texts:list[dict], *, preserve_edits=True) -> dict:
    """Enriquece cartas.csv com textos; não modifica dados numéricos ou fusões.
    Retorna estatísticas e salva uma cópia de auditoria pré-enriquecimento.
    """
    from .core import _read_csv, _write_csv
    cards_path=base/'cartas.csv'
    if not cards_path.is_file():raise ExtractionError('A pasta do projeto não tem cartas.csv')
    rows=_read_csv(cards_path)
    if len(rows)!=CARD_COUNT or {int(r['id']) for r in rows}!=set(range(1,CARD_COUNT+1)):
        raise ExtractionError('A base não contém 722 cartas únicas e válidas')
    oldhash=hashlib.sha256(cards_path.read_bytes()).hexdigest()
    lookup={int(r['id']):r for r in texts}
    merged=0
    for row in rows:
        src=lookup[int(row['id'])]
        for k in ('nome','descricao'):
            if src.get(k) and not row.get(k):
                row[k]=src[k];merged+=1
            elif k not in row:
                row[k]=''
    if merged:
        backup=base/'cartas_antes_textos.csv'
        if not backup.exists():backup.write_bytes(cards_path.read_bytes())
        _write_csv(cards_path,rows)
    return {'campos_adicionados':merged,'sha256_anterior':oldhash,
            'sha256_atual':hashlib.sha256(cards_path.read_bytes()).hexdigest()}


def build_full_report(base:Path, results:dict, metrics:dict, visuals:dict, warnings:list[str], source:dict) -> dict:
    return {'schema':1,'status':'extraido_de_bytes_locais_nao_validado_in_game',
            'sistema':'Yu-Gi-Oh Forbidden Memories SLUS-01411','fonte':source,
            'contagens_tabelas':{k:len(v) for k,v in results.items() if isinstance(v,list)},
            'textos':metrics,'visuais':visuals,'avisos':warnings,
            'politica_fusoes':'somente leitura; nenhum byte alterado',
            'efeitos_novos':'simulação no editor; sem patch no motor de PS1',
            'observacoes':['Descodificação de textos ramificados é parcial; observar CSV de proveniência',
                           'Textos decodificados não foram confirmados in-game',
                           'Imagens decodificadas de offsets documentados para a edição USA; mods podem diferir']}
