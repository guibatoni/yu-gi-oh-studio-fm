"""Preferências da interface (janela, barra lateral, painéis, seção, recentes).

Ficam fora do projeto do MOD, num JSON do usuário, e nunca alteram arquivos do
projeto nem o formato de serialização dele. Qualquer erro de leitura volta para
os padrões — a interface nunca deixa de abrir por causa deste arquivo.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RECENT_LIMIT = 8
DEFAULTS = {
    'geometria': '1390x825',
    'maximizada': False,
    'barra_recolhida': False,
    'biblioteca_visivel': True,
    'largura_biblioteca': 327,
    'secao': 'inicio',
    'recentes': [],
    'filtros_cartas': {},
}


def prefs_path() -> Path:
    override = os.environ.get('FMSTUDIO_UI_PREFS')
    if override:
        return Path(override)
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming')
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return base / 'FM Studio' / 'interface.json'


def _clean(raw) -> dict:
    prefs = {key: (list(value) if isinstance(value, list) else
                   dict(value) if isinstance(value, dict) else value)
             for key, value in DEFAULTS.items()}
    if not isinstance(raw, dict):
        return prefs
    for key, default in DEFAULTS.items():
        value = raw.get(key, default)
        if isinstance(default, bool):
            prefs[key] = bool(value)
        elif isinstance(default, int):
            try:
                prefs[key] = max(180, min(900, int(value)))
            except (TypeError, ValueError):
                pass
        elif isinstance(default, str):
            if isinstance(value, str) and value:
                prefs[key] = value
        elif isinstance(default, list):
            if isinstance(value, list):
                prefs[key] = [str(item) for item in value if isinstance(item, str)][:RECENT_LIMIT]
        elif isinstance(default, dict):
            if isinstance(value, dict):
                prefs[key] = {str(k): str(v) for k, v in value.items() if isinstance(v, (str, int))}
    return prefs


def load(path: Path | None = None) -> dict:
    path = path or prefs_path()
    try:
        return _clean(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return _clean({})


def save(prefs: dict, path: Path | None = None) -> bool:
    path = path or prefs_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(_clean(prefs), ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)
        return True
    except OSError:
        return False


def remember_project(prefs: dict, folder) -> list[str]:
    folder = str(Path(folder))
    recent = [item for item in prefs.get('recentes', []) if item != folder]
    prefs['recentes'] = [folder, *recent][:RECENT_LIMIT]
    return prefs['recentes']


def forget_project(prefs: dict, folder) -> list[str]:
    folder = str(Path(folder))
    prefs['recentes'] = [item for item in prefs.get('recentes', []) if item != folder]
    return prefs['recentes']


def valid_geometry(text: str) -> bool:
    import re
    match = re.fullmatch(r'(\d+)x(\d+)([+-]-?\d+)?([+-]-?\d+)?', text or '')
    return bool(match) and int(match.group(1)) >= 600 and int(match.group(2)) >= 400
