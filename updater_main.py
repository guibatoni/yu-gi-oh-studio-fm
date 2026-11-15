"""Atualizador autônomo; exibe progresso enquanto o editor está fechado."""
from __future__ import annotations
import ctypes
import os
import queue
import sys
import threading
import traceback
from pathlib import Path
from fmstudio.updates import run_updater_cli


def _save_log(message: str):
    root = Path(os.getenv('LOCALAPPDATA') or Path.home()) / 'FM-Mod-Studio' / 'logs'
    try:
        root.mkdir(parents=True, exist_ok=True)
        (root / 'atualizador.log').write_text(message,encoding='utf-8')
    except OSError:
        pass


def main():
    # A interface fica responsiva durante o download. É o único processo
    # que atualiza os arquivos após o aplicativo original ser encerrado.
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
        root = tk.Tk()
        root.title('Yu-Gi-Oh Studio Card FM — Atualizando')
        root.geometry('410x150')
        root.resizable(False,False)
        body = ttk.Frame(root,padding=18)
        body.pack(fill='both',expand=True)
        ttk.Label(body,text='Atualizando o FM Mod Studio',font=('Segoe UI',13,'bold')).pack(anchor='w')
        ttk.Label(body,text='Baixando, verificando e instalando na mesma pasta.').pack(anchor='w',pady=(9,12))
        bar = ttk.Progressbar(body,mode='indeterminate',length=370)
        bar.pack(fill='x')
        bar.start(14)
        root.protocol('WM_DELETE_WINDOW',lambda: None)
        pending: queue.Queue = queue.Queue()

        def work():
            try:
                run_updater_cli()
                pending.put(('ok',''))
            except Exception as exc:
                pending.put(('error',f'{exc}\n\n{traceback.format_exc()}'))

        def poll():
            try:
                status, msg = pending.get_nowait()
            except queue.Empty:
                root.after(200,poll)
                return
            bar.stop()
            if status == 'error':
                _save_log(msg)
                messagebox.showerror('Falha na atualização',msg[:1800],parent=root)
            root.destroy()
        threading.Thread(target=work,daemon=True).start()
        root.after(200,poll)
        root.mainloop()
        return 0
    except Exception as exc:
        msg=f'Erro no atualizador: {exc}\n\n{traceback.format_exc()}'
        _save_log(msg)
        if os.name == 'nt':
            ctypes.windll.user32.MessageBoxW(None,msg[:2200],'FM Mod Studio — Atualizador',0x10)
        else:
            print(msg,file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
