@echo off
title DOME Agent: Waiver Recon
color 0D
echo ======================================================================
echo    ____   ___   __  ___  ____    _      __ ______  ___   ___  ______ 
echo   / __ \ / _ \ /  ^|/  / / __ \  ^| ^| /^| / // __/  ^|/  /  / _ \/_  __/ 
echo  / /_/ // // // /^|_/ / / /_/ /  ^| ^|/ ^|/ // _/ / /^|_/ / / ___/ / /    
echo /_____//____//_/  /_/  \____/   ^|__/^|__//___//_/  /_/ /_/    /_/     
echo                                                                      
echo [AGENT: WAIVER]  -- Compliance ^& QR Link Scraper --
echo ======================================================================
echo [INFO]  Initializing DOME Core Tether...
echo [INFO]  Registering with Cloud Registry...
echo [INFO]  Connecting to Supabase...
echo.
echo STATUS  : Online ^& Polling
echo INTERVAL: Dynamic APScheduler
echo LOGS    : C:\DOME_CORE\workspaces\Waiver_Recon_Agent\logs\
echo ======================================================================
cd /d C:\DOME_CORE\workspaces\Waiver_Recon_Agent\backend
call ..\..\..\.venv\Scripts\activate.bat
python main.py
pause
