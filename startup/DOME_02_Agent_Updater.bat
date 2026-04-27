@echo off
title DOME Agent: Updater
color 0E
echo ======================================================================
echo    ____   ___   __  ___  ____    _      __ ______  ___   ___  ______ 
echo   / __ \ / _ \ /  ^|/  / / __ \  ^| ^| /^| / // __/  ^|/  /  / _ \/_  __/ 
echo  / /_/ // // // /^|_/ / / /_/ /  ^| ^|/ ^|/ // _/ / /^|_/ / / ___/ / /    
echo /_____//____//_/  /_/  \____/   ^|__/^|__//___//_/  /_/ /_/    /_/     
echo                                                                      
echo [AGENT: UPDATER]  -- TripWorks Synchronization Engine --
echo ======================================================================
echo [INFO]  Initializing DOME Core Tether...
echo [INFO]  Registering with Cloud Registry...
echo [INFO]  Connecting to Supabase...
echo.
echo STATUS  : Online ^& Polling
echo INTERVAL: Every 15 seconds
echo LOGS    : C:\DOME_CORE\workspaces\MPWR_Update_Cancel_Agent\logs\
echo ======================================================================
cd /d C:\DOME_CORE\workspaces\MPWR_Update_Cancel_Agent
call ..\..\.venv\Scripts\activate.bat
python main.py
pause
