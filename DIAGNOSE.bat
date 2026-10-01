@echo off
title CBR Journal - diagnose
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (".venv\Scripts\python.exe" diagnose.py) else (python diagnose.py)
echo.
pause
