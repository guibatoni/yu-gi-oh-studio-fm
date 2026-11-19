"""Teste informativo (CI): o Google Tradutor preserva os marcadores ⟦n⟧? Não falha o build."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fmstudio import translate as tr

sample = 'Esta carta recebe {color:amarelo}+500 ATK{/color} para cada {card:12} no campo.'
for target in ('en', 'de', 'it', 'ja', 'zh', 'ko'):
    try:
        print(target, '→', tr.translate_description(sample, target, for_ps1=False))
    except tr.TranslationError as exc:
        print(target, '→ FALHOU:', exc)
