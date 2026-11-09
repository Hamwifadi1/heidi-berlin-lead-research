@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto setup
echo Starting up to 50 company candidates. Existing THIS-project results will be preserved.
".venv\Scripts\python.exe" main.py run --limit 50 --max-pages 4 --max-queries 4 --max-directory-links 400
echo.
echo Batch completed or stopped. Check the above messages and data\output.
pause
exit /b %ERRORLEVEL%
:setup
echo [ERROR] Run 0_SETUP.bat first.
pause
exit /b 1
