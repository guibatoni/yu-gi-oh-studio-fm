"""Aplica um pacote de MOD (mods/<nome>/mod.json) num projeto do Studio FM.

Uso (sem gravar nada, só conferir):
    python tools/aplicar_mod.py "D:\\caminho\\do\\projeto"

Aplicar de verdade (faz backup do projeto.json antes):
    python tools/aplicar_mod.py "D:\\caminho\\do\\projeto" --aplicar --inicial 1

Depois abra o projeto no Studio e use "Gerar jogo BIN/CUE".
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fmstudio.core import ModError, Project  # noqa: E402
from fmstudio.mod_pack import (apply_mod, describe, fit_native_space, load_pack, plan_mod,  # noqa: E402
                               rules_snapshot)

DEFAULT_PACK = ROOT / 'mods' / 'eclipse_do_farao' / 'mod.json'


def main(argv=None):
    parser = argparse.ArgumentParser(description='Aplica um pacote de MOD do Studio FM num projeto.')
    parser.add_argument('projeto', type=Path, help='Pasta do projeto (onde fica projeto.json)')
    parser.add_argument('--mod', type=Path, default=DEFAULT_PACK, help='Arquivo mod.json do pacote')
    parser.add_argument('--inicial', default='1',
                        help='Deck inicial gravado no PS1: número (1–6) ou nome. Os 6 ficam no Studio.')
    parser.add_argument('--aplicar', action='store_true', help='Grava no projeto (sem isso, só confere)')
    parser.add_argument('--estrito', action='store_true', help='Recusa aplicar se houver carta não encontrada')
    parser.add_argument('--manter-efeitos', action='store_true',
                        help='Mantém efeitos já existentes em cartas que o mod não usa')
    parser.add_argument('--novo', action='store_true',
                        help='Cria um projeto NOVO na pasta indicada e importa o --bin (não mexe em outros projetos)')
    parser.add_argument('--bin', type=Path, help='Imagem original Drop x15 (.bin/.cue) usada com --novo')
    parser.add_argument('--nome', default=None, help='Nome do projeto novo (padrão: nome do mod)')
    args = parser.parse_args(argv)

    try:
        pack = load_pack(args.mod)
        if args.novo:
            if not args.bin or not args.bin.is_file():
                raise ModError('Use --bin com o caminho da imagem Drop x15 para criar o projeto novo.')
            if (args.projeto / 'projeto.json').exists():
                print(f'Projeto já existe em {args.projeto}; usando o que está lá.')
            else:
                if args.projeto.exists() and any(args.projeto.iterdir()):
                    raise ModError(f'A pasta {args.projeto} não está vazia; escolha uma pasta nova.')
                created = Project.create(args.projeto, args.nome or pack['nome'])
                print(f'Importando {args.bin.name} para o projeto novo (o arquivo original não é alterado)...')
                created.import_disc(args.bin)
                print(f'Projeto novo criado em {args.projeto}')
        project = Project.open(args.projeto)
        if args.aplicar:
            if args.estrito:
                preview = plan_mod(project, pack, starter=args.inicial)
                if preview.report.missing:
                    print(describe(preview, project, pack))
                    print('\nModo estrito: corrija os nomes acima no mod.json e rode de novo.')
                    return 2
            plan, mod_plan, _ = apply_mod(project, pack, starter=args.inicial,
                                          keep_other_effects=args.manter_efeitos)
            text = describe(plan, project, pack, mod_plan)
            (Path(args.projeto) / 'relatorio_mod.txt').write_text(text, encoding='utf-8')
            print(text)
            print(f'\nMod aplicado. Relatório salvo em {Path(args.projeto) / "relatorio_mod.txt"}')
            print('Abra o projeto no Studio e clique em "Gerar jogo BIN/CUE".')
        else:
            plan = plan_mod(project, pack, starter=args.inicial)
            mod_plan, _ = fit_native_space(project, plan, pack, rules_snapshot(project, plan, pack))
            print(describe(plan, project, pack, mod_plan))
            print('\nNada foi gravado. Rode de novo com --aplicar para gravar no projeto.')
    except ModError as exc:
        print(f'ERRO: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
