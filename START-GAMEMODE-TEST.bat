@echo off
title CBR Journal v2 - game mode (TEST)
cd /d "%~dp0"
rem Testversie van journal v2 (game mode). Raakt de live journal NIET:
rem   - eigen poort 8011, alleen op deze computer
rem   - verse KOPIE van je data uit C:\Dev\cbr-journal (alleen lezen)
rem   - geen MT5-koppeling en geen Telegram (CBR_GEEN_MT5=1)
if not exist "app\game.py" (
  echo   Dit bestand hoort in de map van journal v2. Gestopt.
  pause
  goto :eof
)
if not exist "..\cbr-journal\cbr_journal.db" (
  echo   Live journal-map niet gevonden: ..\cbr-journal. Gestopt.
  pause
  goto :eof
)
set PY=..\cbr-journal\.venv\Scripts\python.exe
echo.
echo   Verse kopie van je data maken...
"%PY%" kopie_testdata.py
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "127.0.0.1:8011" ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
set CBR_GEEN_MT5=1
echo   Game mode (test) draait op http://127.0.0.1:8011/game
echo   Sluit dit venster om te stoppen. Je live journal blijft hier buiten.
echo.
start "" http://127.0.0.1:8011/game
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8011
pause
