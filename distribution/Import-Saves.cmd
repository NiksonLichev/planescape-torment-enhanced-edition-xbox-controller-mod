@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Import-Saves.ps1" %*
if errorlevel 1 echo Save import did not complete. Read the error above.
pause
