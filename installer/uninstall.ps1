# Removes Matrix for the current user: stops it, removes auto-start and shortcuts,
# deletes the program folder, and (only if you say so) your data folder.

$ErrorActionPreference = 'SilentlyContinue'
$target = Join-Path $env:LOCALAPPDATA 'Programs\Matrix'
$data = Join-Path $env:LOCALAPPDATA 'Matrix'

Write-Host 'Uninstalling Matrix...' -ForegroundColor Cyan

Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*matrix_server.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Host '  Stopped Matrix'

Remove-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name Matrix
Write-Host '  Removed auto-start'

$programs = [Environment]::GetFolderPath('Programs')
Remove-Item (Join-Path $programs 'Matrix.lnk'), (Join-Path $programs 'Uninstall Matrix.lnk'),
            (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Matrix.lnk')
Write-Host '  Removed shortcuts'

$answer = Read-Host "  Also delete your device names and settings in $data? [y/N]"
if ($answer -match '^[Yy]') { Remove-Item $data -Recurse -Force; Write-Host '  Deleted your data' }
else { Write-Host '  Kept your data (reinstalling Matrix will pick it up again)' }

# This script runs from inside the program folder, so delete it a moment after we exit.
Start-Process cmd -ArgumentList "/c timeout /t 2 >nul & rmdir /s /q `"$target`"" -WindowStyle Hidden
Write-Host 'Matrix has been removed.' -ForegroundColor Green
