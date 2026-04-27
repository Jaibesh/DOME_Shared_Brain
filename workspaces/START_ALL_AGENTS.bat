@echo off
echo ===================================================
echo     DOME 4.0 - MASTER AGENT STARTUP SCRIPT
echo ===================================================
echo.
echo Starting all sub-agents in independent windows...
echo.

:: 1. Start Creator Agent
echo [1/5] Starting MPWR Reservation (Creator) Agent...
start "Creator Agent" cmd /k "cd C:\DOME_CORE\workspaces\MPWR_Reservation_Agent && python main.py"

:: 2. Start Updater Agent
echo [2/5] Starting MPWR Update/Cancel Agent...
start "Updater Agent" cmd /k "cd C:\DOME_CORE\workspaces\MPWR_Update_Cancel_Agent && python main.py"

:: 3. Start Payment Agent
echo [3/5] Starting MPWR Payment Agent...
start "Payment Agent" cmd /k "cd C:\DOME_CORE\workspaces\MPWR_Payment_Agent && python main.py"

:: 4. Start Waiver Recon Agent
echo [4/5] Starting Waiver Reconciliation Agent...
start "Waiver Agent" cmd /k "cd C:\DOME_CORE\workspaces\Waiver_Recon_Agent\backend && python main.py"

:: 5. Start Dashboard API
echo [5/5] Starting Operations Dashboard Backend...
start "Dashboard Backend" cmd /k "cd C:\DOME_CORE\workspaces\dashboard\backend && python main.py"

echo.
echo ===================================================
echo ✅ All agents have been dispatched!
echo Please verify each terminal window to ensure they have initialized.
echo To gracefully shutdown an agent, click its window and press Ctrl+C.
echo ===================================================
pause
