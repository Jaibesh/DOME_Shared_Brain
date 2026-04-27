@echo off
cd /d "%~dp0"
title MPWR Reservation Agent
echo Starting MPWR Reservation Booking Daemon...

if exist venv goto :activate_venv

echo Creating virtual environment (first run setup)...
python -m venv venv
call venv\Scripts\activate
echo Installing dependencies...
pip install -r requirements.txt
echo Installing Playwright Browsers...
playwright install chromium
goto :run_bot

:activate_venv
call venv\Scripts\activate

:run_bot
echo Starting Main Daemon...
python main.py
pause
