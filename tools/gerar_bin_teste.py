"""Gerar cópia BIN/CUE para testes de estatísticas no ePSXe.

Exemplo:
  python tools/gerar_bin_teste.py --projeto C:\\ModFM --bin C:\\Jogos\\Original.bin
A cópia fica em <projeto>/exportacao/teste_ps1/.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fmstudio.core import Project, ModError
from fmstudio.disc_build import build_test_disc


def main():
    parser=argparse.ArgumentParser(description='Gerar cópia BIN/CUE com ATK/DEF/nível/atributo de cartas existentes.')
    parser.add_argument('--projeto',required=True,type=Path,help='Pasta com projeto.json')
    parser.add_argument('--bin',required=True,type=Path,help='Imagem BIN ou CUE usada na importação')
    args=parser.parse_args()
    try:
        result=build_test_disc(Project.open(args.projeto),args.bin)
    except (ModError,OSError,ValueError) as exc:
        print('Não foi possível gerar cópia:',exc,file=sys.stderr)
        return 1
    print('BIN de teste criado:',result['bin'])
    print('CUE de teste criado:',result['cue'])
    print('Setores alterados:',result['setores_modificados'])
    print('Novos efeitos NÃO são aplicados ao PS1.')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
