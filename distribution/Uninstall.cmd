@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Uninstall.ps1" %*
if errorlevel 1 echo Uninstall did not complete. Read the error above.
pause
