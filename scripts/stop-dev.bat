@echo off
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\launcher.ps1" -Action Stop
exit /b %errorlevel%
