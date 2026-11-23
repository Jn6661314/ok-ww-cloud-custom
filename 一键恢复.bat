@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\ok-ww\data\apps\ok-ww\python\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0restore.py" %*
echo.
pause
