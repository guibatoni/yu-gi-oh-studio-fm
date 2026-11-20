"""Idiomas da interface do Studio (sem Tkinter).

O português do Brasil é o idioma-fonte: cada texto da interface é procurado no
catálogo e, se não houver tradução, aparece em português. Os catálogos ficam em
módulos ``i18n_cat_*.py`` (``ENTRIES = {texto_pt: (en, de, it, ja, zh, ko)}``)
para entrarem no executável sem arquivos de dados extras.
"""
from __future__ import annotations

LANGUAGES = {
    'pt': 'Português (Brasil)',
    'en': 'English',
    'de': 'Deutsch',
    'it': 'Italiano',
    'ja': '日本語',
    'zh': '中文（简体）',
    'ko': '한국어',
}
ORDER = ('en', 'de', 'it', 'ja', 'zh', 'ko')

_catalog: dict[str, tuple] | None = None
_language = 'pt'


def catalog() -> dict[str, tuple]:
    global _catalog
    if _catalog is None:
        # Imports estáticos: o PyInstaller só empacota módulos que enxerga no código
        # (com importlib dinâmico o executável ficava sem traduções).
        from . import (i18n_cat_a, i18n_cat_b, i18n_cat_c, i18n_cat_d, i18n_cat_e, i18n_cat_f,
                       i18n_cat_g, i18n_cat_h)
        merged = {}
        for module in (i18n_cat_a, i18n_cat_b, i18n_cat_c, i18n_cat_d, i18n_cat_e, i18n_cat_f,
                       i18n_cat_g, i18n_cat_h):
            merged.update(module.ENTRIES)
        _catalog = merged
    return _catalog


def set_language(code: str) -> str:
    global _language
    _language = code if code in LANGUAGES else 'pt'
    return _language


def language() -> str:
    return _language


def translate(text: str, code: str | None = None) -> str:
    """Tradução exata do texto (espaços nas pontas preservados); sem entrada, devolve o original."""
    code = code or _language
    if code == 'pt' or not isinstance(text, str) or not text.strip():
        return text
    stripped = text.strip()
    entry = catalog().get(stripped)
    if not entry:
        return text
    value = entry[ORDER.index(code)]
    if not value:
        return text
    start = text[:len(text) - len(text.lstrip())]
    end = text[len(text.rstrip()):]
    return f'{start}{value}{end}'


t = translate


def coverage(code: str, texts) -> float:
    texts = [x.strip() for x in texts if isinstance(x, str) and x.strip()]
    if not texts:
        return 1.0
    index = ORDER.index(code)
    table = catalog()
    return sum(1 for x in texts if x in table and table[x][index]) / len(texts)
