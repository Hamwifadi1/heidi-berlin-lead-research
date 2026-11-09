@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto setup
echo Starting up to 10 company candidates. Results will be newly generated.
".venv\Scripts\python.exe" main.py run --limit 10 --max-pages 4 --max-queries 2 --max-directory-links 400
echo.
echo Batch completed or stopped. Check the above messages and data\output.
pause
exit /b %ERRORLEVEL%
:setup
echo [ERROR] Run 0_SETUP.bat first.
pause
exit /b 1
