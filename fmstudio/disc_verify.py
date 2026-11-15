"""Auditoria da tabela de cartas no arquivo BIN/CUE realmente selecionado."""
from __future__ import annotations
import hashlib
from pathlib import Path
from .core import ModError
from .disc import DiscReader, DiscError
from .tables import decode_cards, CARD_COUNT

FIELDS = ('ataque', 'defesa', 'tipo_id', 'atributo_id', 'nivel',
          'guardian_1_id', 'guardian_2_id')


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
        if int(requested.get('tipo_id',0)) >= 24 or int(requested.get('atributo_id',0)) > 5:
            continue  # Dados experimentais não graváveis no motor original
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
    return {'imagem':image_path,'sha256_slus':hashlib.sha256(exe).hexdigest(),
            'total':len(result),'corretas':sum(r['ok'] for r in result),
            'divergentes':sum(not r['ok'] for r in result),'cartas':result}


def describe(result):
    text = [f'Imagem selecionada: {result["imagem"]}', '',
            f'Cartas numéricas conferidas: {result["total"]}',
            f'Corretas: {result["corretas"]} | Divergentes: {result["divergentes"]}']
    for card in result['cartas'][:10]:
        text.append(f'\n#{card["id"]:03d} {card["nome"]}: '
                    + ('OK' if card['ok'] else 'DIVERGENTE'))
        for field,info in card['campos'].items():
            text.append(f'  {field}: original {info["base"]}, projeto {info["projeto"]}, BIN {info["bin"]}')
    if len(result['cartas']) > 10:
        text.append(f'\n... mais {len(result["cartas"])-10} cartas no relatório.')
    text.append('\nA conferência só valida o arquivo selecionado; não identifica o que o ePSXe executou.')
    return '\n'.join(text)
