@echo off
set "ROOT=%~dp0"
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%ROOT%web\launch.ps1"
exit /b 0
