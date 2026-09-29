# Installs or updates Matrix for the current Windows user. No administrator rights needed.
#
#   Program  -> %LOCALAPPDATA%\Programs\Matrix  (replaced on every update)
#   Data     -> %LOCALAPPDATA%\Matrix           (never touched by updates)
#
# Steps: find Python, stop a running Matrix, copy the program, install psutil,
# create Start menu and desktop shortcuts, set up auto-start, start Matrix.

$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $PSScriptRoot
$target = Join-Path $env:LOCALAPPDATA 'Programs\Matrix'
$script = Join-Path $target 'server\matrix_server.py'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'

function Step($text) { Write-Host "`n> $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "  $text" -ForegroundColor Green }
function Warn($text) { Write-Host "  $text" -ForegroundColor Yellow }

Write-Host '============================================' -ForegroundColor DarkCyan
Write-Host '  MATRIX  -  install / update' -ForegroundColor Cyan
Write-Host '============================================' -ForegroundColor DarkCyan

# 1. Python ------------------------------------------------------------------------
Step 'Looking for Python'
$python = $null
foreach ($cmd in 'python', 'py') {
    try {
        $exe = & $cmd -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) { $python = "$exe".Trim(); break }
    } catch { }
}
if (-not $python) {
    Write-Host '  Python 3 was not found.' -ForegroundColor Red
    Write-Host '  Install it from python.org (tick "Add python.exe to PATH"), then run this again.'
    Start-Process 'https://www.python.org/downloads/'
    exit 1
}
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { $pythonw = $python }
Ok "Found $python"

# 2. Stop a running Matrix (old versions too) ------------------------------------------
Step 'Stopping Matrix if it is running'
$running = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*matrix_server.py*' }
foreach ($p in $running) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
if ($running) { Start-Sleep -Seconds 1; Ok "Stopped $(@($running).Count) running copy(ies)" } else { Ok 'Not running' }

# 3. Copy the program ------------------------------------------------------------------
Step "Copying Matrix to $target"
if ((Resolve-Path $source).Path -ne $target) {
    robocopy "$source" "$target" /MIR /XD __pycache__ .git /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Copying files failed (robocopy code $LASTEXITCODE)." }
    Ok 'Program files updated'
} else {
    Ok 'Already running from the install folder'
}

# 4. psutil (live CPU, memory and disk readings) ------------------------------------------
Step 'Installing helper libraries (psutil for live readings, Pillow for screenshots)'
# pip prints harmless warnings to stderr; don't let those stop the installer.
$ErrorActionPreference = 'Continue'
& $python -m pip install --user --disable-pip-version-check --quiet --upgrade psutil pillow 2>&1 | Out-Null
$pipOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = 'Stop'
if ($pipOk) { Ok 'psutil and Pillow ready' } else { Warn 'Could not install them; live vitals or screenshots may be off. Try: python -m pip install psutil pillow' }

# 5. Shortcuts -----------------------------------------------------------------------------
Step 'Creating shortcuts'
try {
    $shell = New-Object -ComObject WScript.Shell
    $places = @(
        @{ Dir = [Environment]::GetFolderPath('Programs'); Name = 'Matrix.lnk' },
        @{ Dir = [Environment]::GetFolderPath('Desktop'); Name = 'Matrix.lnk' }
    )
    foreach ($place in $places) {
        $link = $shell.CreateShortcut((Join-Path $place.Dir $place.Name))
        $link.TargetPath = $pythonw
        $link.Arguments = "`"$script`" --open"
        $link.WorkingDirectory = $target
        $link.IconLocation = (Join-Path $target 'icons\matrix.ico')
        $link.Description = 'Matrix: live command center for your PC and network'
        $link.Save()
    }
    $uninstall = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Programs')) 'Uninstall Matrix.lnk'))
    $uninstall.TargetPath = Join-Path $target 'Uninstall Matrix.bat'
    $uninstall.WorkingDirectory = $target
    $uninstall.Save()
    Ok 'Start menu and desktop shortcuts created'
} catch {
    Warn "Could not create shortcuts: $($_.Exception.Message)"
}

# 6. Auto-start ------------------------------------------------------------------------------
Step 'Start with Windows'
$existing = (Get-ItemProperty $runKey -Name Matrix -ErrorAction SilentlyContinue).Matrix
if ($existing) {
    $flag = if ($existing -like '*--open*') { '--open' } else { '--background' }
    Set-ItemProperty $runKey -Name Matrix -Value "`"$pythonw`" `"$script`" $flag"
    Ok 'Already on (refreshed for this version)'
} else {
    $answer = Read-Host '  Start Matrix quietly in the background when you sign in? [Y/n]'
    if ($answer -notmatch '^[Nn]') {
        Set-ItemProperty $runKey -Name Matrix -Value "`"$pythonw`" `"$script`" --background"
        Ok 'On. You can change this any time in Matrix > Settings.'
    } else {
        Ok 'Off. You can turn it on in Matrix > Settings.'
    }
}

# 7. Start ----------------------------------------------------------------------------------------
Step 'Starting Matrix'
Start-Process -FilePath $pythonw -ArgumentList "`"$script`" --open" -WorkingDirectory $target
Ok 'Matrix is opening in its own window.'

Write-Host "`nDone. From now on, open Matrix from the Start menu or the desktop icon." -ForegroundColor Green
Write-Host "Your data (device names, settings) lives in $env:LOCALAPPDATA\Matrix and is kept across updates."
Write-Host 'To update later: download the new version and double-click "Install or Update Matrix" again.'
Write-Host 'You can delete the downloaded folder now.'
