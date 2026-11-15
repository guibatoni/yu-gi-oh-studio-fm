"""Cria fonte versionada para Releases (sem MODs, ROMs, projetos ou backups)."""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fmstudio.updates import SOURCE_FILES, SOURCE_BUNDLE_NAME, SOURCE_SUM_NAME, validate_archive


def build(out: Path) -> str:
    paths = sorted(SOURCE_FILES)
    missing = [name for name in paths if not (ROOT / name).is_file()]
    if missing:
        raise ValueError('Arquivos ausentes para pacote fonte: ' + ', '.join(missing))
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for name in paths:
            zipped.write(ROOT / name, arcname=name)
    validate_archive(out, kind='source')
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    (out.parent / SOURCE_SUM_NAME).write_text(sha + '  ' + SOURCE_BUNDLE_NAME + '\n', encoding='ascii')
    return sha


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=ROOT / SOURCE_BUNDLE_NAME)
    args = p.parse_args()
    print('Pacote fonte criado com sucesso. SHA256:', build(args.out))
