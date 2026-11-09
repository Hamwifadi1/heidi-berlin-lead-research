@echo off
setlocal
cd /d "%~dp0"
echo Heidi AI Lead Research - CLEAN setup
echo ====================================
python --version
if errorlevel 1 goto failed
if exist ".venv\Scripts\python.exe" goto install
python -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
if exist ".env" goto success
copy /Y ".env.example" ".env" >nul
:success
echo.
echo [SUCCESS] Installed Python dependencies; no research or old data imported.
echo Next: run 1_EDIT_API_KEYS.bat
pause
exit /b 0
:failed
echo.
echo [ERROR] Setup failed. Run this batch from PowerShell to see details.
pause
exit /b 1
