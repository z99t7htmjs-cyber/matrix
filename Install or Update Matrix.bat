@echo off
title Install or Update Matrix
rem Double-click this file to install Matrix, or to update it to this version.
rem The real work happens in installer\install.ps1 (PowerShell, easier to read).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install.ps1"
echo.
pause
