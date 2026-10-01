# Zet een snelkoppeling "CBR Journal" op het bureaublad.
$map = Split-Path -Parent $MyInvocation.MyCommand.Path
$bureaublad = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $bureaublad 'CBR Journal.lnk'
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($lnk)
$s.TargetPath = Join-Path $map 'START-JOURNAL.bat'
$s.WorkingDirectory = $map
$s.IconLocation = "$env:SystemRoot\System32\SHELL32.dll,13"
$s.Description = 'CBR Trading Journal - lokaal'
$s.Save()
Write-Host "Snelkoppeling gezet: $lnk"
