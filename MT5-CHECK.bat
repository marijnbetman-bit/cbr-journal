@echo off
title MT5-check
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo   Start eerst een keer START-JOURNAL.bat, die maakt de omgeving aan.
  pause
  goto :eof
)
".venv\Scripts\python.exe" -c "import MetaTrader5" >nul 2>&1 || ".venv\Scripts\python.exe" -m pip install MetaTrader5
".venv\Scripts\python.exe" mt5_check.py
pause
