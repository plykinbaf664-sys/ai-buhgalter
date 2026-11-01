@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0BUILD.ps1" %*
exit /b %errorlevel%
