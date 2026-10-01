@echo off
title Autostart aanzetten
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\CBR Journal.lnk'); $s.TargetPath='%~dp0START-JOURNAL.bat'; $s.Arguments='autostart'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.Save()"
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\CBR Journal.lnk" (
  echo.
  echo   Klaar. De journal start voortaan vanzelf, geminimaliseerd, als je inlogt,
  echo   en leest dan meteen je trades uit MetaTrader. Uitzetten: AUTOSTART-UIT.bat
) else (
  echo   Het lukte niet om de snelkoppeling te maken.
)
echo.
pause
