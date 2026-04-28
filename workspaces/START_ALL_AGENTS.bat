@echo off
echo ===================================================
echo     DOME 4.0 - MASTER AGENT STARTUP SCRIPT
echo ===================================================
echo.
echo Starting all sub-agents in independent windows...
echo.

:: 1. Start Creator Agent
echo [1/6] Starting MPWR Reservation (Creator) Agent...
start "Creator Agent" cmd /k "cd C:\DOME_CORE\workspaces\MPWR_Reservation_Agent && python main.py"

:: 2. Start Updater Agent
echo [2/6] Starting MPWR Update/Cancel Agent...
start "Updater Agent" cmd /k "cd C:\DOME_CORE\workspaces\MPWR_Update_Cancel_Agent && python main.py"

:: 3. Start Payment Agent
echo [3/6] Starting MPWR Payment Agent...
start "Payment Agent" cmd /k "cd C:\DOME_CORE\workspaces\MPWR_Payment_Agent && python main.py"

:: 4. Start Waiver Recon System
echo [4/6] Starting Waiver Recon (Core) Agent...
start "Waiver Recon Agent" cmd /k "cd C:\DOME_CORE\workspaces\Waiver_Recon_Agent\backend && python main.py"

:: 5. Start Waiver Link Agent
echo [5/6] Starting Waiver Link (QR) Agent...
start "Waiver Link Agent" cmd /k "cd C:\DOME_CORE\workspaces\Waiver_Recon_Agent\backend && python waiver_link_daemon.py"

:: 6. Start Waiver Webhook Agent
echo [6/6] Starting Waiver Webhook (TripWorks) Agent...
start "Waiver Webhook Agent" cmd /k "cd C:\DOME_CORE\workspaces\Waiver_Recon_Agent\backend && python waiver_webhook_daemon.py"

:: 7. Start Service Work Order Agent
echo [7/7] Starting Service Work Order Agent...
start "Service Work Order Agent" cmd /k "cd C:\DOME_CORE\workspaces\Service_Work_Order_Agent && python main.py"

echo.
echo ===================================================
echo ✅ All agents have been dispatched!
echo Please verify each terminal window to ensure they have initialized.
echo To gracefully shutdown an agent, click its window and press Ctrl+C.
echo ===================================================
pause
