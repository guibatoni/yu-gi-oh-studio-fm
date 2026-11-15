@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 app.py
) else (
  python app.py
)
if errorlevel 1 (
 echo.
 echo O aplicativo nao iniciou. Confirme Python 3 e Tkinter instalados.
 pause
)
endlocal
