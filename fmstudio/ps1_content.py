"""Patches PS1 de nomes, descrições e artes.

Não expande tabelas nem modifica o motor. Tudo usa offsets documentados para
SLUS-01411 e é verificado contra a base importada.
"""
from __future__ import annotations

import struct
from pathlib import Path
import re
from .core import ModError
from .deep_extract import BANK_NAMES, BANK_DESC, NAME_TABLE, STRING_TABLE, glyph_map, exe_pos
from .tables import CARD_COUNT

WA_SECTOR = 2048


def _encode_name(text: str, cmap: dict[int, str]) -> bytes:
    lookup: dict[str, int] = {}
    for code, ch in cmap.items():
        if code < 0xF0 and len(ch) == 1:
            lookup.setdefault(ch, code)
    encoded = bytearray()
    for ch in text:
        if ch not in lookup:
            raise ModError(f'Caractere {ch!r} não existe na fonte original do PS1.')
        encoded.append(lookup[ch])
    return bytes(encoded)


def name_patch_info(exe: bytes, cid: int, new_name: str) -> tuple[int, bytes]:
    """Patch in-place; nunca aumenta a string nem toca nomes compartilhados."""
    if not 1 <= cid <= CARD_COUNT:
        raise ModError('Cartas acima de 722 ainda não existem no motor PS1.')
    if not exe.startswith(b'PS-X EXE'):
        raise ModError('Executável PS-X EXE inválido.')
    ptr_base = exe_pos(NAME_TABLE, exe, 0x360 * 2)
    offsets = [struct.unpack_from('<H',exe,ptr_base + i * 2)[0] for i in range(0x360)]
    offset = offsets[cid]
    if not offset or offsets.count(offset) != 1:
        raise ModError('Nome original sem slot exclusivo; alteração bloqueada.')
    at = exe_pos(BANK_NAMES + offset, exe, 1)
    # Não ultrapassar o banco, nem a próxima string conhecida.
    upper = min((x for x in offsets if x > offset), default=0x10000)
    original = exe[at:at + min(upper-offset, 256)]
    end = original.find(b'\xff')
    if end < 0 or any(b >= 0xF0 for b in original[:end]):
        raise ModError('Nome com controle/terminador não simples; requer compilador de textos completo.')
    try:
        cmap,_ = glyph_map(exe)
        new_bytes = _encode_name(new_name, cmap)
    except (ValueError, UnicodeError) as exc:
        raise ModError(f'Fonte não pode ser lida: {exc}') from exc
    if len(new_bytes) > end:
        raise ModError(f'Nome precisa de {len(new_bytes)} glifos; slot PS1 tem {end}. Encurte o nome ou aguarde realocação.')
    return at, new_bytes + b'\xff'


def patch_names(exe: bytes, changes: dict[int, str]) -> tuple[bytes, list[dict]]:
    result=bytearray(exe)
    entries=[]
    for cid,name in sorted(changes.items()):
        offset, patch=name_patch_info(exe, int(cid), str(name))
        old=bytes(result[offset:offset+len(patch)])
        if old == patch:
            continue
        result[offset:offset+len(patch)]=patch
        entries.append({'id':int(cid),'offset_exe':offset,'bytes':len(patch)})
    return bytes(result),entries


def patch_card_art(wa: bytes, cid: int, png: Path, *, options=None,
                   verified_layout: bool = False) -> tuple[bytes, list[dict]]:
    """Grava a arte e miniaturas sem tocar no título ou em cartas vizinhas."""
    from .ps1_image_optimizer import render_card

    if not 1 <= cid <= CARD_COUNT:
        raise ModError('Artes de cartas adicionais exigem expansão de arquivos do PS1.')
    base = ((cid - 1) * 7 + CARD_COUNT) * WA_SECTOR
    thumb = (cid - 1) * WA_SECTOR
    output = render_card(Path(png), wa[base:base + 7 * WA_SECTOR],
                         wa[thumb:thumb + WA_SECTOR], options,
                         verified_layout=verified_layout)
    result = bytearray(wa)
    modified = []
    for kind, offset, payload, report in output.regions(base, thumb):
        end = offset + len(payload)
        if result[offset:end] != payload:
            result[offset:end] = payload
            modified.append({'id': cid, 'regiao': kind, 'offset_wa': offset,
                             'bytes': len(payload), 'otimizacao': report})
    return bytes(result), modified


def patch_card_titles(wa: bytes, names: dict[int, str]) -> tuple[bytes, list[int]]:
    """Update the separate title texture after the executable name was written."""
    from .ps1_card_title import TITLE_BYTES, TITLE_OFFSET, title_bitmap
    from .ps1_image_optimizer import has_mirrored_thumbnail

    result = bytearray(wa)
    written = []
    for cid, name in sorted(names.items()):
        if not 1 <= cid <= CARD_COUNT:
            continue
        art = ((cid - 1) * 7 + CARD_COUNT) * WA_SECTOR
        thumb = (cid - 1) * WA_SECTOR
        if not has_mirrored_thumbnail(wa[art:art + 7 * WA_SECTOR], wa[thumb:thumb + WA_SECTOR]):
            continue
        start = art + TITLE_OFFSET
        result[start:start + TITLE_BYTES] = title_bitmap(name)
        written.append(cid)
    return bytes(result), written


_TEXT_CONTROL = re.compile(r'\{(f8 0[AB] [0-9A-Fa-f]{2}|color:[a-z]+|/color|card:[0-9]+|icon:[a-z0-9_]+)\}')


def _encode_description(value: str, cmap:dict[int,str], cards:dict[int,dict], *,
                        icon_codes=None, normalize=None) -> bytes:
    """Compila glifos, quebras de linha e comandos de cor/ícone F8."""
    from .richtext import TEXT_COLORS
    from .expanded import display_name
    encoded=bytearray();where=0
    def append_plain(part):
        if normalize is not None:
            part = normalize(part)
        for ch in part:
            if ch=='\n':encoded.append(0xFE)
            else:encoded.extend(_encode_name(ch,cmap))
    for m in _TEXT_CONTROL.finditer(value):
        if '{' in value[where:m.start()] or '}' in value[where:m.start()]:
            raise ModError('Descrição contém token desconhecido: requer compilador expandido.')
        append_plain(value[where:m.start()])
        token=m.group(1)
        if token.startswith('color:'):
            name=token[6:]
            if name not in TEXT_COLORS:raise ModError('Cor desconhecida no texto do PS1.')
            encoded.extend([0xF8,0x0A,TEXT_COLORS[name][0]])
        elif token=='/color':encoded.extend([0xF8,0x0A,0])
        elif token.startswith('card:'):
            cid=int(token[5:]);name=display_name(cid,cards)
            append_plain(name)
        elif token.startswith('icon:'):
            name=token[5:]
            if not icon_codes or name not in icon_codes:
                raise ModError(f'Ícone {name!r} exige a extensão de descrições PS1.')
            encoded.extend([0xF8,0x0B,icon_codes[name]])
        else:
            op,ctrl,arg=token.split()
            code=int(arg,16)
            if ctrl=='0A' and code>6:raise ModError('Código de cor fora da paleta retail.')
            if ctrl=='0B' and code>0x28:raise ModError('Ícone não pertence à fonte original do PS1.')
            encoded.extend([0xF8,int(ctrl,16),code])
        where=m.end()
    tail=value[where:]
    if '{' in tail or '}' in tail:
        raise ModError('Descrição contém ícone/controle não suportado no PS1.')
    append_plain(tail)
    return bytes(encoded)


def description_slot(exe:bytes,cid:int) -> tuple[int,int]:
    """Retorna a posição e a capacidade segura de uma descrição linear."""
    if not 1<=cid<=CARD_COUNT:raise ModError('Descrição de carta virtual requer expansão do motor.')
    table_start=exe_pos(STRING_TABLE,exe,0x400*2)
    offsets=[struct.unpack_from('<H',exe,table_start+2*i)[0] for i in range(0x100,0x400)]
    offset=offsets[cid]
    if not offset or offsets.count(offset)!=1:
        raise ModError('Descrição sem slot exclusivo no banco de texto.')
    upper=min((x for x in offsets if x>offset),default=0x10000)
    at=exe_pos(BANK_DESC+offset,exe,1)
    old=exe[at:at+min(upper-offset,2048)]
    # Aceitar texto original apenas linear (glifos, F8 de cor/tipo, NL).
    end=0;p=0
    while p<len(old):
        op=old[p]
        if op==0xFF:
            end=p;break
        if op<=0xEF or op==0xFE:p+=1;continue
        if op==0xF8 and p+2<len(old) and old[p+1] in (0x0A,0x0B):p+=3;continue
        raise ModError('Descrição original contém controle/ramificação; edição não é segura.')
    else:raise ModError('Descrição original sem terminador em espaço livre.')
    return at,end


def description_patch_info(exe:bytes,cid:int,description:str,cards:dict[int,dict]) -> tuple[int,bytes]:
    """Somente troca strings lineares curtas no próprio slot de descrição."""
    at,end=description_slot(exe,cid)
    cmap,_=glyph_map(exe)
    raw=_encode_description(description,cmap,cards)
    if len(raw)>end:
        raise ModError(f'Descrição usa {len(raw)} bytes; slot original permite {end}.')
    return at,raw+b'\xff'


def patch_descriptions(exe:bytes,changes:dict[int,str],cards:dict[int,dict]) -> tuple[bytes,list[dict]]:
    result=bytearray(exe);entries=[]
    for cid,text in sorted(changes.items()):
        offset,part=description_patch_info(exe,int(cid),text,cards)
        if bytes(result[offset:offset+len(part)])!=part:
            result[offset:offset+len(part)]=part
            entries.append({'id':int(cid),'offset_exe':offset,'bytes':len(part)})
    return bytes(result),entries
