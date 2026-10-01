@echo off
title CBR Journal
setlocal enabledelayedexpansion
cd /d "%~dp0"
set PORT=8010

if not exist "app\main.py" goto wrongdir
if exist "cbr-journal\app\main.py" goto genest

for /f "tokens=2 delims== " %%v in ('findstr /b /c:"VERSIE = " app\main.py') do set VER=%%v
cls
echo.
echo   ================================================
echo     CBR JOURNAL   versie %VER%
echo   ================================================
echo     Map: %CD%
echo.

rem Eenmalig een snelkoppeling op het bureaublad zetten.
if not exist ".snelkoppeling-gemaakt" (
  call :maaksnelkoppeling
  echo. > ".snelkoppeling-gemaakt"
)

python --version >nul 2>&1
if errorlevel 1 goto nopython

if not exist ".venv" (
  echo   Eenmalig: omgeving aanmaken...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"

python -c "import uvicorn" >nul 2>&1
if not errorlevel 1 goto run
echo   Eenmalig: pakketten installeren, even geduld...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt

:run
python -c "import json;json.load(open('journal_config.json',encoding='utf-8'))" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   [FOUT] journal_config.json is kapot ^(tikfout: komma, aanhalingsteken of dubbele punt^).
  echo          Zonder deze instellingen werken MT5 en Telegram NIET.
  python -c "import json;json.load(open('journal_config.json',encoding='utf-8'))"
  echo.
  pause
)
rem MT5-koppeling (22 sep 2026): het pakket dat je trades uit MetaTrader leest.
python -c "import MetaTrader5" >nul 2>&1
if errorlevel 1 (
  echo   Eenmalig: MetaTrader-koppeling installeren...
  python -m pip install MetaTrader5 >nul 2>&1
)
python -c "import MetaTrader5" >nul 2>&1
if errorlevel 1 echo   [LET OP] MetaTrader-pakket niet gelukt. De journal werkt, alleen zonder MT5-koppeling.
python -c "import truststore" >nul 2>&1
if errorlevel 1 python -m pip install truststore >nul 2>&1
python -c "import fpdf" >nul 2>&1
if errorlevel 1 (
  echo   Eenmalig: PDF-pakket installeren...
  python -m pip install fpdf2 >nul 2>&1
)
echo   Journal draait op http://localhost:%PORT%
echo   MT5-koppeling: kijkt elke 30 sec in MetaTrader. Status: lampje rechtsboven.
echo   Sluit dit venster om te stoppen.
echo.
if /i not "%~1"=="autostart" start "" http://localhost:%PORT%
python -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
echo.
echo   Server gestopt.
pause
goto :eof

:maaksnelkoppeling
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0snelkoppeling.ps1" >nul 2>&1
if exist "%USERPROFILE%\Desktop\CBR Journal.lnk" (
  echo   Snelkoppeling "CBR Journal" op je bureaublad gezet.
  echo.
)
goto :eof

:genest
echo.
echo   [LET OP] Er staat een map cbr-journal BINNEN deze map.
echo   De zip is een niveau te diep uitgepakt; je draait de oude versie.
echo   Pak de zip opnieuw uit in de map ERBOVEN.
echo.
pause
goto :eof

:wrongdir
echo   [FOUT] Dit bestand staat op de verkeerde plek. Zet het in de map
echo          naast de mappen app en static.
pause
goto :eof

:nopython
echo   [FOUT] Python niet gevonden. Installeer Python 3.10 of nieuwer en
echo          vink "Add Python to PATH" aan tijdens de installatie.
echo          https://www.python.org/downloads/
pause
goto :eof
