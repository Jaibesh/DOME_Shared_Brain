@echo off
title Waiver Link Scraper Agent
echo ============================================================
echo   Epic 4x4 Adventures - Waiver Link Scraper
echo   Standalone process for QR Code and Join URL extraction
echo ============================================================
echo Running from: %~dp0
cd backend

if exist venv goto :activate_venv

echo.
echo First run setup: Creating virtual environment...
python -m venv venv
call venv\Scripts\activate.bat
echo Installing dependencies...
pip install -r requirements.txt
echo Installing Playwright Chromium browser...
playwright install chromium
goto :run_bot

:activate_venv
call venv\Scripts\activate.bat

:run_bot
echo.
echo Starting Waiver Link Scraper Daemon...
venv\Scripts\python.exe waiver_link_daemon.py
pause
