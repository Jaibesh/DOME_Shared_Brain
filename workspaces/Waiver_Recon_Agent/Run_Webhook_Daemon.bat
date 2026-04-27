@echo off
title Waiver Webhook Daemon (Specialized Webhooks)
echo Starting Specialized Webhook Daemon...
echo Running from: %~dp0
cd backend

if exist venv goto :activate_venv

echo Creating virtual environment (first run setup)...
python -m venv venv
call venv\Scripts\activate.bat
echo Installing dependencies...
pip install -r requirements.txt
goto :run_bot

:activate_venv
call venv\Scripts\activate.bat

:run_bot
python waiver_webhook_daemon.py
pause
