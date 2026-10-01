@echo off
title Journal-bot instellen
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" telegram_instellen.py
) else (
  python telegram_instellen.py
)
pause
