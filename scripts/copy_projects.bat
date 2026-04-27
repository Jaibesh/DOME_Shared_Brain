@echo off
echo Copying projects to DOME_CORE workspaces...

set SRC=C:\Users\justu\Documents\Agentic_workflows_epic4x4adventures\Waiver_systems
set DST=C:\DOME_CORE\workspaces
set EXCLUDEDIRS=venv .venv __pycache__ node_modules .git screenshots logs webhook_cache webhook_sniffer

echo.
echo [1/6] MPWR_Payment_Agent...
robocopy "%SRC%\MPWR_Payment_Agent" "%DST%\MPWR_Payment_Agent" /E /XD %EXCLUDEDIRS% /XF .env *.pyc /NFL /NDL /NJH /NJS /NC /NS /NP
echo DONE

echo [2/6] MPWR_Update_Cancel_Agent...
robocopy "%SRC%\MPWR_Update_Cancel_Agent" "%DST%\MPWR_Update_Cancel_Agent" /E /XD %EXCLUDEDIRS% /XF .env *.pyc /NFL /NDL /NJH /NJS /NC /NS /NP
echo DONE

echo [3/6] Waiver_Dashboard...
robocopy "%SRC%\Waiver_Dashboard" "%DST%\Waiver_Dashboard" /E /XD %EXCLUDEDIRS% /XF .env *.pyc /NFL /NDL /NJH /NJS /NC /NS /NP
echo DONE

echo [4/6] Waiver_Recon_Agent...
robocopy "%SRC%\Waiver_Recon_Agent" "%DST%\Waiver_Recon_Agent" /E /XD %EXCLUDEDIRS% /XF .env *.pyc /NFL /NDL /NJH /NJS /NC /NS /NP
echo DONE

echo [5/6] shared...
robocopy "%SRC%\shared" "%DST%\shared" /E /XD %EXCLUDEDIRS% /XF .env *.pyc /NFL /NDL /NJH /NJS /NC /NS /NP
echo DONE

echo [6/6] scripts...
robocopy "%SRC%\scripts" "%DST%\scripts" /E /XD %EXCLUDEDIRS% /XF .env *.pyc /NFL /NDL /NJH /NJS /NC /NS /NP
echo DONE

echo.
echo === ALL PROJECTS COPIED ===
