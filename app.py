"""Inicia o editor gráfico no Windows (Python 3.10+ e Tkinter)."""
import os
import sys


def _selftest(path):
    """Usado pelo CI no .exe empacotado: confere se módulos carregados por nome entraram no pacote."""
    import json
    from fmstudio import i18n, translate  # noqa: F401
    i18n.set_language('en')
    result = {'catalogo': len(i18n.catalog()), 'salvar_en': i18n.t('Salvar'),
              'molduras_ja': i18n.t('Molduras', 'ja')}
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False)


if __name__ == '__main__':
    if os.environ.get('FMSTUDIO_SELFTEST'):
        _selftest(os.environ['FMSTUDIO_SELFTEST'])
        sys.exit(0)
    from fmstudio.gui import run
    run()
