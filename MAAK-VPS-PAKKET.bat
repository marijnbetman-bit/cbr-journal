@echo off
title CBR Journal - VPS-pakket maken
cd /d "%~dp0"
echo.
echo   ================================================
echo     VPS-PAKKET MAKEN
echo   ================================================
echo.
echo   Sluit EERST het journal-venster (zwart venster "CBR Journal"),
echo   anders kan de database half gekopieerd worden.
echo.
netstat -ano | findstr /r /c:":8010 .*LISTENING" >nul
if not errorlevel 1 (
  echo   [LET OP] De journal draait nog op poort 8010. Sluit hem en start dit opnieuw.
  echo.
  pause
  goto :eof
)
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm"') do set STAMP=%%d
set TMPD=%TEMP%\cbr-vps-%STAMP%\journal
for /f "delims=" %%d in ('powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"') do set DESK=%%d
if not exist "%DESK%" set DESK=%~dp0.
set ZIP=%DESK%\CBR-journal-VPS-%STAMP%.zip
echo   Kopieren (zonder .venv, back-ups en oude .bak-bestanden)...
robocopy "%~dp0." "%TMPD%" /E /NFL /NDL /NJH /NJS /NP ^
  /XD .venv __pycache__ backups "Claude outputs" _archief_ui ^
  /XF *.bak* *.backup-* .snelkoppeling-gemaakt *.pyc *.zip >nul
echo   Inpakken naar je bureaublad...
powershell -NoProfile -Command "Compress-Archive -Path '%TMPD%' -DestinationPath '%ZIP%' -Force"
rmdir /s /q "%TEMP%\cbr-vps-%STAMP%" >nul 2>&1
if exist "%ZIP%" (
  echo.
  echo   Klaar:  %ZIP%
  echo.
  echo   Volgende stap: kopieer deze zip naar je VPS (via Extern bureaublad:
  echo   kopieren/plakken werkt gewoon) en volg LEESMIJ-VPS.md.
) else (
  echo   [FOUT] Inpakken mislukt. Probeerde: %ZIP%
)
echo.
pause
