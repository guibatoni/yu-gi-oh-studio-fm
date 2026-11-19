@echo off
rem Abre o Studio FM gerando a tabela de quests com o pegador de crash.
rem Use SOMENTE para descobrir a origem do erro "Opcode 1b UNK (PC 001aae78)".
rem O BIN/CUE gerado assim e apenas para diagnostico: nao distribua.
set FMSTUDIO_DIAGNOSTICO_QUEST_RA=1
cd /d "%~dp0"
if exist "FM-Mod-Studio.exe" (
    start "" "FM-Mod-Studio.exe"
) else (
    start "" pythonw FM_Mod_Studio.pyw
)
