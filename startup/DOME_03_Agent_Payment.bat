@echo off
title DOME Agent: Payment
color 0B
echo ======================================================================
echo    ____   ___   __  ___  ____    _      __ ______  ___   ___  ______ 
echo   / __ \ / _ \ /  ^|/  / / __ \  ^| ^| /^| / // __/  ^|/  /  / _ \/_  __/ 
echo  / /_/ // // // /^|_/ / / /_/ /  ^| ^|/ ^|/ // _/ / /^|_/ / / ___/ / /    
echo /_____//____//_/  /_/  \____/   ^|__/^|__//___//_/  /_/ /_/    /_/     
echo                                                                      
echo [AGENT: PAYMENT]  -- Financial Settlement ^& Deposit Monitor --
echo ======================================================================
echo [INFO]  Initializing DOME Core Tether...
echo [INFO]  Registering with Cloud Registry...
echo [INFO]  Connecting to Supabase...
echo.
echo STATUS  : Online ^& Polling
echo INTERVAL: Every 5 minutes
echo LOGS    : C:\DOME_CORE\workspaces\MPWR_Payment_Agent\logs\
echo ======================================================================
cd /d C:\DOME_CORE\workspaces\MPWR_Payment_Agent
call ..\..\.venv\Scripts\activate.bat
python main.py
pause
