"""Cópia de efeitos entre cartas sem perder alvos e demais parâmetros."""
from __future__ import annotations
import json
from .core import ModError, check_effect

PREFIX = "FM-STUDIO-EFFECTS/1\n"
MAX_EFFECTS = 255
MAX_CLIPBOARD = 200_000


def encode_effects(source_cid, effects):
    if not isinstance(source_cid, int) or source_cid < 1:
        raise ModError('Carta de origem inválida.')
    if not isinstance(effects, (list, tuple)) or not 1 <= len(effects) <= MAX_EFFECTS:
        raise ModError('Selecione entre 1 e 255 efeitos.')
    verified=[check_effect(entry) for entry in effects]
    return PREFIX + json.dumps({'source':source_cid, 'effects':verified},
                               ensure_ascii=False, separators=(',', ':'))


def decode_effects(raw):
    if not isinstance(raw, str) or not raw.startswith(PREFIX) or len(raw) > MAX_CLIPBOARD:
        raise ModError('A área de transferência não contém efeitos do Studio FM.')
    try:
        document=json.loads(raw[len(PREFIX):])
        source=document['source']
        entries=document['effects']
    except (ValueError,KeyError,TypeError) as exc:
        raise ModError('Lista de efeitos copiados está inválida.') from exc
    if type(source) is not int or source < 1:
        raise ModError('Origem do efeito inválida.')
    if not isinstance(entries,list) or not 1 <= len(entries) <= MAX_EFFECTS:
        raise ModError('Quantidade de efeitos copiados não suportada.')
    if not all(isinstance(item, dict) for item in entries):
        raise ModError('Os efeitos copiados devem conter registros válidos.')
    return source,[check_effect(item) for item in entries]


def merge_effects(existing, incoming, *, replace=False):
    """Prévia pura e imutável; cópias são independentes dos objetos de origem."""
    current=[] if replace else [check_effect(x) for x in existing]
    for entry in incoming:
        normalized=check_effect(entry)
        if normalized in current:
            raise ModError('A colagem duplicaria um efeito já cadastrado.')
        current.append(dict(normalized))
    return current


def reference_warnings(source_cid,target_cid,entries):
    notes=[]
    for entry in entries:
        ref=entry.get('carta_referencia_id')
        if ref is not None:
            notes.append(f'Referência fixa: carta #{ref}.')
            if ref == source_cid and target_cid != source_cid:
                notes.append('O efeito referencia a carta de origem; confirme se deseja manter esse vínculo.')
    return list(dict.fromkeys(notes))
