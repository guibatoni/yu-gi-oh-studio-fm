@echo off
setlocal
cd /d "%~dp0"
echo.
echo FM MOD STUDIO - CORRECAO LOCAL DO ATUALIZADOR v0.6.2
echo Feche a versao antiga antes de continuar.
echo Na janela de escolha, selecione a PASTA onde app.py esta instalado.
echo Nao selecione a pasta do projeto MOD nem a pasta da ROM.
echo.
pause
where py >nul 2>nul
if not errorlevel 1 (
  py -3 tools\instalar_correcao.py
) else (
  python tools\instalar_correcao.py
)
if errorlevel 1 (
  echo.
  echo Erro ao corrigir. Verifique a pasta selecionada e o aviso acima.
  pause
  exit /b 1
)
echo.
echo Correcao concluida. Abra a pasta anterior do Studio e inicie normalmente.
pause
