@echo off
rem Studio FM: tabela de quests com o pegador v2 (salva os registradores e
rem congela o jogo na tela preta). Depois do congelamento, salve um save state
rem no ePSXe (F1) e envie o arquivo da pasta "sstates". Somente diagnostico.
set FMSTUDIO_DIAGNOSTICO_QUEST_RA=2
cd /d "%~dp0"
if exist "FM-Mod-Studio.exe" (
    start "" "FM-Mod-Studio.exe"
) else (
    start "" pythonw FM_Mod_Studio.pyw
)
