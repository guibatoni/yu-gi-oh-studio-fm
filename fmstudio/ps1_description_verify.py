"""Auditoria read-only das descrições realmente presentes em um BIN/CUE do PS1.

Compara bytes apontados pela tabela D100+ID do executável com o texto
editado no Studio. O resultado não comprova que um menu do emulador exibe
essa tela; comprova apenas a gravação e a resolução do ponteiro no BIN.
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from .core import ModError
from .deep_extract import BANK_DESC, STRING_TABLE, decode_text, exe_pos, glyph_map
from .disc import DiscReader, DiscError
from .ps1_content import _encode_description
from .ps1_god24_chest import SOURCE_SHA256
from .ps1_text import MAX_TEXT_BYTES, _measure, compile_description, preview_description
from .tables import CARD_COUNT

def _card_capacity(exe):
    from .ps1_expansion import inspect_expansion
    expansion = inspect_expansion(exe)
    return expansion['capacidade'] if expansion['status'] == 'aplicado' else CARD_COUNT


def _description_bytes(exe: bytes, cid: int):
    """Lê o ponteiro real D100+ID; não depende da posição original do texto."""
    if not exe.startswith(b'PS-X EXE'):
        raise ModError('O BIN não contém um executável PS-X reconhecido.')
    if not 1 <= cid <= _card_capacity(exe):
        raise ModError('O ID não pertence ao catálogo nativo confirmado neste BIN/CUE.')
    try:
        ptr = exe_pos(STRING_TABLE + 2 * (0x100 + cid), exe, 2)
        offset = struct.unpack_from('<H', exe, ptr)[0]
        if not 0 < offset < 0x10000:
            raise ModError(f'Carta #{cid}: ponteiro de descrição vazio ou inválido.')
        start = exe_pos(BANK_DESC + offset, exe, 1)
    except (ValueError, struct.error) as exc:
        raise ModError(f'Carta #{cid}: tabela de descrições fora do executável.') from exc
    limit = min(MAX_TEXT_BYTES, 0x10000 - offset, len(exe) - start)
    raw = exe[start:start + limit]
    end = raw.find(b'\xff')
    if end < 0:
        raise ModError(f'Carta #{cid}: descrição sem terminador PS1.')
    return raw[:end], offset, start


def inspect_exe_description(exe: bytes, cid: int, desired: str, cards: dict,
                            *, original_exe: bytes | None = None,
                            native_profile: bool = False) -> dict:
    """Lê o texto inteiro, a prévia ou a ausência de descrição na imagem."""
    result = {'id': int(cid), 'status': 'divergente', 'motivo': ''}
    if not 1 <= cid <= _card_capacity(exe):
        result.update(status='somente_studio',
                      motivo='O ID não pertence ao catálogo nativo confirmado neste BIN/CUE.')
        return result
    try:
        actual, address, file_offset = _description_bytes(exe, cid)
        result.update(ponteiro=f'0x{address:04X}',
                      offset_exe=file_offset,
                      sha256_texto_bin=hashlib.sha256(actual).hexdigest())
        cmap, _ = glyph_map(exe)
        visible, warnings = decode_text(exe, BANK_DESC, address, cmap, limit=MAX_TEXT_BYTES)
        result['texto_no_bin'] = visible
        if warnings:
            result['avisos_leitura'] = warnings
        if cid > CARD_COUNT and not actual and desired.strip():
            result.update(status='sem_texto', motivo='A carta nova está sem descrição nesta imagem. '
                          'O texto completo está no projeto.')
            return result
        if native_profile:
            expected, _, reflowed = compile_description(desired, cmap, cards)
        else:
            expected = _encode_description(desired.replace('\r\n', '\n'), cmap, cards)
            reflowed = False
        result['sha256_texto_esperado'] = hashlib.sha256(expected).hexdigest()
        if native_profile:
            if cid > CARD_COUNT and actual != expected and actual == preview_description(expected, cmap, len(actual)):
                _measure(actual)
                result.update(status='resumida', motivo='A prévia gravada no BIN corresponde ao início '
                              'da descrição. O Studio guarda o texto completo.')
                return result
            _measure(expected)
        if actual == expected:
            result.update(status='aplicada', quebras_reorganizadas=reflowed,
                          motivo='O BIN contém o texto completo com as quebras de linha reorganizadas.'
                          if reflowed else 'Texto salvo no Studio coincide com os bytes e o ponteiro do BIN.')
        else:
            stock = None
            if original_exe is not None:
                try:
                    stock = _description_bytes(original_exe, cid)[0]
                except ModError:
                    pass
            if stock is not None and actual == stock:
                result.update(status='original',
                              motivo='O BIN ainda contém a descrição original da carta.')
            else:
                result.update(status='divergente',
                              motivo='O BIN contém texto diferente do salvo no Studio.')
    except (ModError, ValueError) as exc:
        result.update(status='incompativel', motivo=str(exc))
    return result


def scan_disc_descriptions(project, image: Path, *, ids=None) -> dict:
    """Lê somente o SLUS do BIN/CUE selecionado, sem alterar ROM ou projeto."""
    image = Path(image).resolve()
    if ids is None:
        ids = [int(cid) for cid, changes in project.edits.items()
               if 'descricao' in changes]
        ids += [int(cid) for cid in getattr(project, 'new_cards', {})
                if int(cid) > CARD_COUNT and project.get(int(cid)).get('descricao')]
    ids = sorted({int(cid) for cid in ids})
    with DiscReader(image) as reader:
        entries = {entry.path.upper(): entry for entry in reader.files() if not entry.is_dir}
        if 'SLUS_014.11' not in entries:
            raise ModError('Não foi encontrado SLUS_014.11 no BIN/CUE escolhido.')
        exe = b''.join(reader.read_entry(entries['SLUS_014.11']))
        bin_path = reader.path.resolve()
    base = project.folder / 'base' / 'source_SLUS_014.11'
    stock = base.read_bytes() if base.is_file() else None
    native = (stock is not None and
              hashlib.sha256(stock).hexdigest() == SOURCE_SHA256)
    cards = {cid: project.get(cid) for cid in project.cards}
    results = [
        inspect_exe_description(exe, cid, cards[cid].get('descricao', ''), cards,
                                original_exe=stock, native_profile=native)
        for cid in ids if cid in cards
    ]
    counts = {status: sum(row['status'] == status for row in results)
              for status in ('aplicada', 'original', 'divergente',
                             'incompativel', 'somente_studio', 'resumida', 'sem_texto')}
    return {
        'imagem_analisada': str(bin_path),
        'sha256_slus_bin': hashlib.sha256(exe).hexdigest(),
        'perfil_drop_x15': native,
        'total': len(results),
        'contagens': counts,
        'cartas': results,
        'observacao': ('O diagnóstico confere o texto no executável, não a '
                       'disponibilidade da tela de informações em cada mod/ePSXe.'),
    }
