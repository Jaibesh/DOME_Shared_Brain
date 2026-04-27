@echo off
title MPOWR Waiver Recon Automation
echo Starting MPOWR Waiver Automation...
echo Running from: %~dp0
cd backend

if exist venv goto :activate_venv

echo Creating virtual environment (first run setup)...
python -m venv venv
call venv\Scripts\activate.bat
echo Installing dependencies...
pip install -r requirements.txt
echo Installing Playwright Browsers...
playwright install chromium
goto :run_bot

:activate_venv
call venv\Scripts\activate.bat

:run_bot
venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
