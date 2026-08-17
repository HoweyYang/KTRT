@echo off
chcp 65001 >nul
cd /d "%~dp0"
title KillTimeRecitationTool

rem ??????????????????? KTRT.vbs????????? KTRT.exe?

where python >nul 2>nul
if errorlevel 1 (
  echo [KTRT] Python not found. Please install Python 3.10+ and check "Add to PATH".
  pause
  exit /b 1
)

if not exist venv (
  echo [KTRT] First run: creating virtual environment and installing dependencies...
  python -m venv venv
  call venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
) else (
  call venv\Scripts\activate.bat
)

python launcher.py
echo.
echo [KTRT] App stopped. You may close this window.
pause
