"""Tradução automática das descrições das cartas (tradutor online).

* Os comandos do Studio dentro do texto ({card:12}, {color:...}, {icon:...},
  {f8 ..}) são trocados por marcadores antes de enviar e restaurados depois. Se
  um marcador sumir na tradução, aquela carta fica sem tradução (nada é perdido).
* Nada é gravado aqui: o resultado vai para os rascunhos (pendências) e só é
  salvo com "Salvar projeto". O original de cada carta fica num JSON de backup.
* Sem dependências: só ``urllib``. Precisa de internet no PC do usuário.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .richtext import TOKEN

LANGUAGES = {
    'en': 'English (inglês)',
    'de': 'Deutsch (alemão)',
    'it': 'Italiano',
    'ja': '日本語 (japonês)',
    'zh': '中文 (chinês simplificado)',
    'ko': '한국어 (coreano)',
    'pt': 'Português',
}
DEEPL_CODES = {'en': 'EN-US', 'de': 'DE', 'it': 'IT', 'ja': 'JA', 'zh': 'ZH', 'ko': 'KO', 'pt': 'PT-BR'}
PROVIDERS = {
    'google': 'Google Tradutor (sem chave)',
    'deepl': 'DeepL (precisa de chave da API)',
    'mymemory': 'MyMemory (sem chave, limite diário)',
}
PS1_SAFE = str.maketrans({'ß': 'ss', 'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
                          '«': '"', '»': '"', '„': '"'})
MARK = re.compile(r'⟦\s*(\d+)\s*⟧')
TIMEOUT = 20


class TranslationError(Exception):
    pass


def protect(text: str) -> tuple[str, list[str]]:
    """Troca comandos do Studio por ⟦n⟧ (não traduzíveis)."""
    tokens = []

    def keep(match):
        tokens.append(match.group(0))
        return f'⟦{len(tokens) - 1}⟧'
    return TOKEN.sub(keep, text), tokens


def restore(text: str, tokens: list[str]) -> str:
    """Devolve os comandos; falha se algum marcador sumiu ou foi duplicado."""
    found = [int(n) for n in MARK.findall(text)]
    if sorted(found) != list(range(len(tokens))):
        raise TranslationError('o tradutor alterou os comandos de cor/ícone/carta do texto')
    return MARK.sub(lambda m: tokens[int(m.group(1))], text)


def prepare(text: str, *, keep_breaks: bool) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not keep_breaks:
        text = re.sub(r'\s*\n\s*', ' ', text)
    return text


def ps1_safe(text: str) -> str:
    """Adapta letras sem glifo na fonte do PS1 (ß→ss, ä→ae...). Acentos comuns já caem para a letra base no BIN."""
    return text.translate(PS1_SAFE)


def _get(url, data=None, headers=None):
    request = urllib.request.Request(url, data=data, headers={'User-Agent': 'FM-Studio', **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read().decode('utf-8')
    except OSError as exc:  # inclui URLError/HTTPError/timeout
        raise TranslationError(f'sem resposta do tradutor ({exc})') from exc


def parse_google(payload: str) -> str:
    try:
        data = json.loads(payload)
        return ''.join(part[0] for part in data[0] if part and part[0])
    except (ValueError, TypeError, IndexError) as exc:
        raise TranslationError('resposta inesperada do Google Tradutor') from exc


def translate_text(text: str, target: str, *, provider: str = 'google', api_key: str = '',
                   source: str = 'auto', fetch=None) -> str:
    """Traduz um texto já protegido. ``fetch(url, data, headers)`` permite testar sem rede."""
    fetch = fetch or _get
    if not text.strip():
        return text
    if provider == 'google':
        query = urllib.parse.urlencode({'client': 'gtx', 'sl': source, 'tl': target, 'dt': 't', 'q': text})
        return parse_google(fetch('https://translate.googleapis.com/translate_a/single?' + query, None, None))
    if provider == 'deepl':
        if not api_key.strip():
            raise TranslationError('informe a chave da API do DeepL')
        host = 'api-free.deepl.com' if api_key.strip().endswith(':fx') else 'api.deepl.com'
        form = {'text': text, 'target_lang': DEEPL_CODES[target]}
        if source != 'auto':
            form['source_lang'] = source.upper()
        body = urllib.parse.urlencode(form).encode()
        payload = fetch(f'https://{host}/v2/translate', body,
                        {'Authorization': f'DeepL-Auth-Key {api_key.strip()}',
                         'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            return json.loads(payload)['translations'][0]['text']
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise TranslationError('resposta inesperada do DeepL') from exc
    if provider == 'mymemory':
        pair = f'{"pt" if source == "auto" else source}|{target}'
        query = urllib.parse.urlencode({'q': text, 'langpair': pair})
        payload = fetch('https://api.mymemory.translated.net/get?' + query, None, None)
        try:
            data = json.loads(payload)
            if int(data.get('responseStatus', 200)) != 200:
                raise TranslationError(str(data.get('responseDetails') or 'limite do MyMemory'))
            return data['responseData']['translatedText']
        except (ValueError, KeyError, TypeError) as exc:
            raise TranslationError('resposta inesperada do MyMemory') from exc
    raise TranslationError(f'tradutor desconhecido: {provider}')


@dataclass
class Result:
    id: int
    original: str
    translated: str | None
    error: str = ''


def translate_description(text: str, target: str, *, provider='google', api_key='', keep_breaks=False,
                          for_ps1=True, fetch=None) -> str:
    protected, tokens = protect(prepare(text, keep_breaks=keep_breaks))
    if keep_breaks and '\n' in protected:
        lines = [translate_text(line, target, provider=provider, api_key=api_key, fetch=fetch) if line.strip() else line
                 for line in protected.split('\n')]
        translated = '\n'.join(lines)
    else:
        translated = translate_text(protected, target, provider=provider, api_key=api_key, fetch=fetch)
    translated = restore(translated, tokens)
    translated = re.sub(r'[ \t]+', ' ', translated).strip()
    return ps1_safe(translated) if for_ps1 else translated


def translate_many(items: dict[int, str], target: str, *, provider='google', api_key='', keep_breaks=False,
                   for_ps1=True, progress=None, cancelled=None, fetch=None, pause=0.15) -> list[Result]:
    """Traduz carta por carta. ``progress(feitas, total)``; ``cancelled()`` interrompe entre cartas."""
    results = []
    total = len(items)
    for done, (cid, text) in enumerate(sorted(items.items()), start=1):
        if cancelled and cancelled():
            break
        if not (text or '').strip():
            results.append(Result(cid, text or '', None, 'sem descrição'))
        else:
            try:
                results.append(Result(cid, text, translate_description(
                    text, target, provider=provider, api_key=api_key, keep_breaks=keep_breaks,
                    for_ps1=for_ps1, fetch=fetch)))
            except TranslationError as exc:
                results.append(Result(cid, text, None, str(exc)))
            if pause and fetch is None:
                time.sleep(pause)
        if progress:
            progress(done, total)
    return results


def backup_payload(results: list[Result], target: str, provider: str) -> dict:
    return {'idioma': target, 'tradutor': provider, 'gerado_em': time.strftime('%Y-%m-%d %H:%M:%S'),
            'originais': {str(r.id): r.original for r in results if r.translated is not None}}
