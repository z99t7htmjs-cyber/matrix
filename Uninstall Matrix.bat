@echo off
title Uninstall Matrix
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\uninstall.ps1"
echo.
pause
