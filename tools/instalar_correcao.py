"""Atualiza para v0.9.0 uma instalação Python anterior do Studio.

Usa o pacote Source local com checksum, sem precisar GitHub/Internet.
A pasta do projeto não é alterada.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fmstudio.updates import (
    SOURCE_BUNDLE_NAME, SOURCE_SUM_NAME, UpdateError,
    install_archive, parse_checksum, validate_archive,
)


def patch(destination: Path) -> str:
    dest = destination.expanduser().resolve()
    if not (dest / 'app.py').is_file() or not (dest / 'fmstudio/gui.py').is_file():
        raise UpdateError('A pasta selecionada não contém uma instalação Python do FM Studio.')
    package = ROOT / SOURCE_BUNDLE_NAME
    manifest = ROOT / SOURCE_SUM_NAME
    if not package.is_file() or not manifest.is_file():
        raise UpdateError('Pacote de correção ausente. Extraia todo o ZIP v0.9.0.')
    sha = hashlib.sha256(package.read_bytes()).hexdigest()
    expected = parse_checksum(manifest.read_text(encoding='ascii'), bundle=SOURCE_BUNDLE_NAME)
    if sha != expected:
        raise UpdateError('Pacote de correção não confere com checksum SHA-256.')
    validate_archive(package, kind='source')
    install_archive(package, dest, kind='source')
    return f'Studio v0.9.0 instalado em {dest}. Seus projetos não foram modificados.'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dest', type=Path, help='Pasta de uma instalação Python anterior do Studio.')
    args = parser.parse_args(argv)
    try:
        if args.dest is None:
            import tkinter as tk
            from tkinter import filedialog, messagebox
            window = tk.Tk()
            window.withdraw()
            folder = filedialog.askdirectory(title='Selecione a pasta da versão antiga do FM Studio')
            if not folder:
                return 0
            result = patch(Path(folder))
            messagebox.showinfo('Correção instalada', result, parent=window)
            window.destroy()
        else:
            print(patch(args.dest))
        return 0
    except Exception as exc:
        print('Falha na correção:', exc, file=sys.stderr)
        if args.dest is None:
            try:
                import tkinter.messagebox as mb
                mb.showerror('Erro ao atualizar', str(exc))
            except Exception:
                pass
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
