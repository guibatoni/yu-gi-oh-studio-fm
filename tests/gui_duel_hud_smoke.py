"""Smoke: opção do HUD de duelo novo em Config. MOD e janela de prévia."""
import tkinter as tk

from fmstudio.gui import Studio

root = Studio()
try:
    root.update()
    editor = root.mod_editor
    assert editor.ps1_hud_new.get() is False
    editor.save_ps1_hud()                       # sem projeto: continua desligado
    assert editor.ps1_hud_new.get() is False
    before = set(editor.winfo_children())
    editor.preview_ps1_hud()
    root.update()
    windows = [w for w in editor.winfo_children() if isinstance(w, tk.Toplevel) and w not in before]
    assert windows, 'janela de prévia não abriu'
    windows[0].destroy()
    print('ok: HUD de duelo (opção e prévia)')
finally:
    root.destroy()
