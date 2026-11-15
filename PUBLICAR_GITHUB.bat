@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0PUBLICAR_GITHUB.ps1"
if errorlevel 1 (
 echo.
 echo Publicacao nao concluida. Verifique os avisos acima.
)
pause
