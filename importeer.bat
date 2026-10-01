@echo off
title CBR Journal -- signalen importeren
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo   [FOUT] Geen omgeving gevonden. Start eerst START-JOURNAL.bat minstens
  echo          een keer ^(die maakt de omgeving aan^), en probeer dit dan opnieuw.
  pause
  goto :eof
)

call ".venv\Scripts\activate.bat"
python importeer_signalen.py
echo.
pause
