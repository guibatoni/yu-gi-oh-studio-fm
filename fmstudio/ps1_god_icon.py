"""Protótipo gráfico de ícone Deus no PS1.

Inspeciona somente os dez slots endereçáveis 0x27–0x30 da segunda
página de glifos: nunca sobrescreve dados não nulos do MOD. O código
F8 0B correspondente é gravado na descrição de uma carta na CÓPIA BIN,
não substitui o ícone de tipo nem implementa God 24 como monstro.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

from .core import ModError
from .deep_extract import exe_pos, BANK_DESC, STRING_TABLE

WA_SECTOR = 2048
ICON_SHEET_SECTOR = 0x16A0
ICON_PALETTE_SECTOR = 0x16C0
GLYPH_INDEX = 0x29
# func_80035E20: F8 0B de 0x22 a 0x30 => u=(slot*16)-0x210;
# v=128, tpage=0xB, CLUT x=0x200,y=0xFC. A partir de 0x31
# u=256 sai da página de textura. Códigos até 0x26 são retail.
FREE_SLOT_CANDIDATES = (0x29, 0x27, 0x28, 0x2A, 0x2B, 0x2C, 0x2D,
                        0x2E, 0x2F, 0x30)
GLYPH_U = 128
GLYPH_V = 128
WIDTH = HEIGHT = 16
ROW_BYTES = 128
PALETTE_OFFSET = ICON_PALETTE_SECTOR * WA_SECTOR + 4 * 512
TOKEN_BYTES = bytes((0xF8, 0x0B, GLYPH_INDEX))


class NoFreeGodIconSlot(ModError):
    """Nenhuma célula 16x16 comprovadamente vazia; não tocar no WA do MOD."""


def icon_cell_start(slot: int) -> int:
    """Offset dos pixels do código F8 0B XX na segunda página da fonte."""
    if type(slot) is not int or slot not in FREE_SLOT_CANDIDATES:
        raise ModError('Ícone Deus: código de glifo fora dos slots 0x27–0x30 permitidos.')
    u=slot*16-0x210
    if u < 0 or u+WIDTH > 256:
        raise ModError('Ícone Deus: UV excede o banco de textura do PS1.')
    return ICON_SHEET_SECTOR * WA_SECTOR + GLYPH_V*ROW_BYTES + u//2


def glyph_rows(wa: bytes, slot: int = GLYPH_INDEX) -> list[bytes]:
    first=icon_cell_start(slot)
    last=first+(HEIGHT-1)*ROW_BYTES+8
    if len(wa)<last:
        raise ModError('WA_MRG.MRG não contém a segunda página de ícones do boot.')
    return [wa[first+y*ROW_BYTES:first+y*ROW_BYTES+8]
            for y in range(HEIGHT)]


def find_god_icon_slot(wa: bytes, desired: list[bytes]) -> tuple[int,str]:
    """Seleciona slot vazio; conteúdo igual ao desejado pode ser reutilizado."""
    if len(desired)!=HEIGHT or any(len(row)!=8 for row in desired):
        raise ModError('Ícone Deus: imagem indexada 16x16 inválida.')
    for slot in FREE_SLOT_CANDIDATES:
        rows=glyph_rows(wa,slot)
        if rows==desired:
            return slot,'ja_presente'
        if all(not any(row) for row in rows):
            return slot,'livre'
    labels=', '.join(f'0x{x:02X}' for x in FREE_SLOT_CANDIDATES)
    raise NoFreeGodIconSlot('Nenhuma célula 16x16 vazia na fonte deste MOD '
                            f'({labels}). Gráficos existentes preservados.')


def decode_god_png(image_path: Path) -> list[tuple[int, int, int, int]]:
    """Decodifica PNG RGBA 16x16 sem Pillow, com CRC e limites estritos."""
    try:
        raw=Path(image_path).read_bytes()
    except OSError as exc:
        raise ModError('Ícone Deus PNG ausente no aplicativo.') from exc
    if len(raw)>262144 or raw[:8]!=b'\x89PNG\r\n\x1a\n':
        raise ModError('Ícone Deus: PNG inválido ou maior que o limite seguro.')
    offset=8
    header=None
    parts=[]
    seen_data=False
    ended=False
    while offset<len(raw):
        if len(raw)-offset<12:
            raise ModError('Ícone Deus: bloco PNG incompleto.')
        length=struct.unpack_from('>I',raw,offset)[0]
        offset+=4
        if length>262144 or offset+8+length>len(raw):
            raise ModError('Ícone Deus: tamanho de bloco PNG inválido.')
        kind=raw[offset:offset+4]
        offset+=4
        data=raw[offset:offset+length]
        offset+=length
        crc=struct.unpack_from('>I',raw,offset)[0]
        offset+=4
        if (zlib.crc32(kind+data)&0xFFFFFFFF)!=crc:
            raise ModError('Ícone Deus: CRC PNG incorreto.')
        if kind==b'IHDR':
            if header is not None or seen_data or length!=13:
                raise ModError('Ícone Deus: cabeçalho PNG inválido.')
            w,h,depth,color,comp,filt,interlace=struct.unpack('>IIBBBBB',data)
            if (w,h,depth,color,comp,filt,interlace)!=(16,16,8,6,0,0,0):
                raise ModError('Ícone Deus: esperado PNG RGBA 16x16, 8 bits, sem entrelaçamento.')
            header=data
        elif kind==b'IDAT':
            if header is None:
                raise ModError('Ícone Deus: dados PNG sem cabeçalho.')
            seen_data=True
            parts.append(data)
        elif kind==b'IEND':
            if length or header is None or not seen_data:
                raise ModError('Ícone Deus: encerramento PNG inválido.')
            ended=True
            break
        elif kind[:1] and not (kind[0]&0x20):
            raise ModError('Ícone Deus: bloco PNG obrigatório não suportado.')
    if not ended or offset!=len(raw) or not parts:
        raise ModError('Ícone Deus: arquivo PNG incompleto.')
    expected=16*(1+16*4)
    try:
        inflater=zlib.decompressobj()
        expanded=inflater.decompress(b''.join(parts),expected+1)
        expanded+=inflater.flush(expected+1-len(expanded))
    except zlib.error as exc:
        raise ModError('Ícone Deus: dados compactados PNG inválidos.') from exc
    if (not inflater.eof or inflater.unused_data or inflater.unconsumed_tail
            or len(expanded)!=expected):
        raise ModError('Ícone Deus: dados PNG excedem ou não completam 16x16 RGBA.')
    pixels=[]
    previous=bytearray(64)
    pos=0
    for _ in range(16):
        method=expanded[pos]
        pos+=1
        row=bytearray(expanded[pos:pos+64])
        pos+=64
        if method not in (0,1,2,3,4):
            raise ModError('Ícone Deus: filtro PNG desconhecido.')
        for i in range(64):
            left=row[i-4] if i>=4 else 0
            above=previous[i]
            corner=previous[i-4] if i>=4 else 0
            if method==0:
                predict=0
            elif method==1:
                predict=left
            elif method==2:
                predict=above
            elif method==3:
                predict=(left+above)//2
            else:
                p=left+above-corner
                da,db,dc=abs(p-left),abs(p-above),abs(p-corner)
                predict=left if da<=db and da<=dc else above if db<=dc else corner
            row[i]=(row[i]+predict)&255
        pixels.extend(tuple(row[i:i+4]) for i in range(0,64,4))
        previous=row
    return pixels


def god_glyph_rows(wa: bytes, image_path: Path, *,
                   palette_offset: int = PALETTE_OFFSET) -> list[bytes]:
    """Converte o símbolo 16x16 para as cores de uma CLUT original de 4 bits."""
    if palette_offset < 0 or palette_offset + 32 > len(wa):
        raise ModError('Paleta original de ícones ausente no WA_MRG.MRG.')
    pixels=decode_god_png(Path(image_path))
    palette = struct.unpack_from('<16H', wa, palette_offset)
    available = [i for i in range(1, 16) if palette[i] != 0]
    if not available:
        raise ModError('Paleta de ícones está vazia; não há cores para o teste.')
    def rgb(value):
        return ((value & 31) * 255 // 31,
                ((value >> 5) & 31) * 255 // 31,
                ((value >> 10) & 31) * 255 // 31)
    rgb_palette = {index: rgb(palette[index]) for index in available}
    def closest(pixel):
        if pixel[3] < 128:
            return 0
        return min(available, key=lambda i: sum(
            (pixel[ch] - rgb_palette[i][ch]) ** 2 for ch in range(3)))
    idx = [closest(pixel) for pixel in pixels]
    if not any(idx):
        raise ModError('Ícone Deus sem pixels visíveis após aplicar a paleta.')
    desired = []
    for y in range(HEIGHT):
        row = bytes(idx[y*16 + x] | (idx[y*16 + x+1] << 4)
                    for x in range(0, 16, 2))
        desired.append(row)
    return desired


def patch_god_glyph(wa: bytes, image_path: Path) -> tuple[bytes, dict]:
    """Pinta apenas um slot comprovadamente vazio, com a paleta do próprio jogo."""
    desired=god_glyph_rows(wa,image_path)
    slot,condition=find_god_icon_slot(wa,desired)
    token=f'F8 0B {slot:02X}'
    if condition=='ja_presente':
        return wa, {'codigo':token,'slot':slot,
                     'status':'ja_presente','offsets_wa':[]}
    out=bytearray(wa)
    changes=[]
    first=icon_cell_start(slot)
    for y,row in enumerate(desired):
        off=first+y*ROW_BYTES
        out[off:off+8]=row
        changes.append(off)
    if glyph_rows(out,slot)!=desired:
        raise ModError('Falha ao reler o ícone Deus gravado no WA.')
    return bytes(out), {'codigo':token,'slot':slot,
                        'status':'glifo_inserido_em_celula_vazia',
                        'offsets_wa':changes,
                        'aviso':'Slot escolhido após verificar pixels vazios. '
                                'É um teste em texto, não cria tipo God 24.'}


def patch_god_icon_description(exe: bytes, card_id: int,
                               slot: int = GLYPH_INDEX) -> tuple[bytes, dict]:
    """Troca 3 GLIFOS iniciais pelo slot escolhido, apenas no BIN de TESTE.

    Os textos e descrições no projeto continuam intocados. A exigência de
    slot exclusivo protege textos compartilhados. A versão original do jogo
    não é sobrescrita: esta função só recebe cópias em memória.
    """
    if isinstance(card_id, bool) or not isinstance(card_id, int) or not 1 <= card_id <= 722:
        raise ModError('Teste de Deus exige carta original com ID 1–722.')
    icon_cell_start(slot)  # Garante UV endereçável antes de gravar o token.
    token=bytes((0xF8,0x0B,slot))
    code=f'F8 0B {slot:02X}'
    if exe[:8] != b'PS-X EXE':
        raise ModError('SLUS inválido para testar ícone Deus.')
    ptr = exe_pos(STRING_TABLE, exe, 0x400 * 2)
    offsets = [struct.unpack_from('<H',exe,ptr+2*i)[0]
               for i in range(0x100,0x400)]
    offset = offsets[card_id]
    if not offset or offsets.count(offset) != 1:
        raise ModError('Descrição da carta sem espaço exclusivo para teste de ícone God.')
    ceiling = min((x for x in offsets if x > offset), default=0x10000)
    start = exe_pos(BANK_DESC+offset, exe, 3)
    if start + 3 > exe_pos(BANK_DESC+ceiling,exe,0):
        raise ModError('Descrição curta demais para inserir ícone Deus.')
    first = exe[start:start+3]
    if first == token:
        return exe, {'carta_id':card_id,'status':'ja_presente',
                     'codigo':code,'offset_slus':f'0x{start:X}'}
    if len(first) != 3 or any(b >= 0xF0 for b in first) or 0xFF in first:
        raise ModError('A descrição começa com controles especiais ou menos '
                       'de três caracteres; o teste God foi bloqueado.')
    # O restante do texto é preservado byte a byte. Os 3 caracteres iniciais
    # são substituídos SOMENTE na cópia de teste, com permissão explícita.
    patched = bytearray(exe)
    patched[start:start+3] = token
    if patched[start:start+3] != token:
        raise ModError('Falha na verificação do código do ícone Deus.')
    return bytes(patched), {
        'carta_id':card_id,'status':'icone_inserido_no_texto_do_card',
        'codigo':code,'offset_slus':f'0x{start:X}',
        'bytes_substituidos':first.hex(),
        'aviso':'Primeiros 3 caracteres da descrição foram substituídos apenas '
                'na cópia do BIN. Tipo original permanece inalterado.'
    }


def try_patch_god_icon(wa: bytes, exe: bytes, card_id: int,
                       image_path: Path) -> tuple[bytes,bytes,dict]:
    """Insere glifo e descrição juntos, ou omite SÓ o ícone se não houver slot.

    Não ignora erros de PNG, paleta, texto ou corrupção do disco. Um MOD sem
    slot livre continua elegível para teste separado do tipo God 24/ATK.
    """
    try:
        icon_data, glyph=patch_god_glyph(wa,image_path)
    except NoFreeGodIconSlot as exc:
        return wa,exe,{
            'card_id':card_id,'status':'icone_nao_inserido_sem_espaco_livre',
            'motivo':str(exc),
            'aviso':'Não inserimos ícone nem mudamos a descrição. '
                    'Gravações de tipo/ATK independentes continuam possíveis.'}
    text_data,description=patch_god_icon_description(
        exe,card_id,slot=glyph['slot'])
    return icon_data,text_data,{
        'card_id':card_id,'status':'prototipo_visual_pendente_epsxe',
        'glifo':glyph,'descricao_temporaria':description,
        'aviso':'Símbolo inserido na descrição; tipo God 24 ainda '
                'não é um monstro validado no motor original.'}


def god_icon_asset() -> Path:
    import sys
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return root / 'assets' / 'icons' / 'god.png'
