@echo off
rem Powerwall history downloader. Code written by Claude Opus 5.5 (Anthropic) using Claude Code. MIT License.
rem Double-click to download your Powerwall history. Extra options can be added
rem after the file name in a terminal, e.g.  "Download Powerwall history.bat" --start 2024-01-01

setlocal
set "VENV=%LOCALAPPDATA%\powerwall-history\venv"

if exist "%VENV%\Scripts\python.exe" goto update
echo First run: setting up a private Python environment (takes a minute)...
python -m venv "%VENV%"
if errorlevel 1 goto nopython

:update
rem Always fetch the latest pypowerwall: it is where fixes for Tesla's login changes arrive.
echo Checking for updates...
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -q -U -r "%~dp0requirements.txt"
if errorlevel 1 echo WARNING: could not update packages; trying with the installed ones.

"%VENV%\Scripts\python.exe" "%~dp0powerwall_history.py" %*
echo.
pause
exit /b

:nopython
echo.
echo Could not run Python. Install it from https://www.python.org/downloads/
echo (tick "Add python.exe to PATH" during setup), then run this file again.
pause
exit /b 1
