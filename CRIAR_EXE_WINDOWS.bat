@echo off
setlocal
cd /d "%~dp0"
python -m pip install --upgrade pyinstaller pillow
if errorlevel 1 goto :erro
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "FM-Mod-Studio" app.py
if errorlevel 1 goto :erro
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "FM-Mod-Studio-Updater" updater_main.py
if errorlevel 1 goto :erro
copy /y INICIAR.bat dist\ >nul
copy /y LEIA-ME.txt dist\ >nul
echo.
echo Aplicativo e atualizador criados na pasta dist.
echo Execute dist\INICIAR.bat
pause
exit /b 0
:erro
echo Falha na compilacao. Verifique o erro acima.
pause
exit /b 1
