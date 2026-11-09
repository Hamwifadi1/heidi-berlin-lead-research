@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto setup
".venv\Scripts\python.exe" main.py export
pause
exit /b %ERRORLEVEL%
:setup
echo [ERROR] Run 0_SETUP.bat first.
pause
exit /b 1
