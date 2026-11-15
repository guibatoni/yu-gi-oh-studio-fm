"""Gerar cópia BIN/CUE para testes parciais no ePSXe.

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
    parser=argparse.ArgumentParser(description='Gerar BIN/CUE experimental com estatísticas, textos curtos e artes originais.')
    parser.add_argument('--projeto',required=True,type=Path,help='Pasta com projeto.json')
    parser.add_argument('--bin',required=True,type=Path,help='Imagem BIN ou CUE usada na importação')
    parser.add_argument('--exigir-completo',action='store_true',help='Recusa geração se houver qualquer função sem suporte PS1')
    args=parser.parse_args()
    try:
        result=build_test_disc(Project.open(args.projeto),args.bin,require_complete=args.exigir_completo)
    except (ModError,OSError,ValueError) as exc:
        print('Não foi possível gerar cópia:',exc,file=sys.stderr)
        return 1
    print('BIN de teste criado:',result['bin'])
    print('CUE de teste criado:',result['cue'])
    print('Setores alterados:',result['setores_modificados'])
    print('Textos curtos gravados:',len(result['nomes_aplicados'])+len(result['descricoes_aplicadas']))
    print('Regiões de artes gravadas:',len(result['artes_aplicadas']))
    print('Funções sem rotina PS1:',len(result['recursos_pendentes']))
    print('Novos efeitos NÃO são executados no PS1.')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
