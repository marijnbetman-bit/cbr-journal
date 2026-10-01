@echo off
title CBR Journal - installeren op de VPS
setlocal enabledelayedexpansion
cd /d "%~dp0"
echo.
echo   ================================================
echo     CBR JOURNAL OP DE VPS INSTALLEREN
echo   ================================================
echo     Map: %CD%
echo.
python --version >nul 2>&1
if errorlevel 1 (
  echo   [FOUT] Python niet gevonden. Installeer Python 3.11 van python.org
  echo          en vink "Add Python to PATH" aan. Start dit daarna opnieuw.
  pause
  goto :eof
)

echo   1/4  Wachtwoord voor de journal
echo        Op een server met een publiek IP moet er een wachtwoord op.
if defined JOURNAL_WACHTWOORD (
  echo        Er staat al een wachtwoord ingesteld. Enter = houden.
)
set /p PW="       Nieuw wachtwoord (leeg = niet wijzigen): "
if not "%PW%"=="" (
  setx JOURNAL_WACHTWOORD "%PW%" >nul
  set JOURNAL_WACHTWOORD=%PW%
  echo        Opgeslagen.
)
echo.

echo   2/4  Welke MetaTrader 5 hoort bij je Vantage-account?
set N=0
for %%p in ("C:\Program Files" "C:\Program Files (x86)" "%APPDATA%\MetaQuotes") do (
  for /f "delims=" %%f in ('dir /s /b "%%~p\terminal64.exe" 2^>nul') do (
    set /a N+=1
    set "T!N!=%%f"
    echo        !N!^) %%f
  )
)
if %N%==0 echo        Geen MT5 automatisch gevonden.
set /p KEUS="       Nummer, of plak het volledige pad naar terminal64.exe van je Vantage-MT5: "
set "TPAD=!T%KEUS%!"
if "!TPAD!"=="" set "TPAD=%KEUS%"
if not exist "!TPAD!" (
  echo        [FOUT] "!TPAD!" bestaat niet. Start dit script opnieuw.
  pause
  goto :eof
)
echo        Gekozen: !TPAD!
python -c "import json,sys;p='journal_config.json';c=json.load(open(p,encoding='utf-8'));c.setdefault('mt5',{})['terminal_pad']=sys.argv[1];json.dump(c,open(p,'w',encoding='utf-8'),indent=1,ensure_ascii=False)" "!TPAD!"
echo.

echo   3/4  Pakketten installeren (eenmalig, paar minuten)...
if not exist ".venv" python -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
python -m pip install MetaTrader5 fpdf2 >nul 2>&1
echo.

echo   4/4  Autostart aanzetten (start bij inloggen op de VPS)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\CBR Journal.lnk'); $s.TargetPath='%~dp0START-JOURNAL.bat'; $s.Arguments='autostart'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.Save()"
echo.
echo   ================================================
echo     Klaar. Nu:
echo      - zorg dat MT5 open staat en ingelogd is (ook MT5 op autostart zetten)
echo      - start START-JOURNAL.bat
echo      - check in Telegram: /status  (MT5: verbonden)
echo      - ZET DE JOURNAL OP JE LAPTOP UIT (AUTOSTART-UIT.bat), anders
echo        vechten twee bots om hetzelfde Telegram-account.
echo   ================================================
echo.
pause
