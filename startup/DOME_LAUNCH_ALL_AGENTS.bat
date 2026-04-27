@echo off
title DOME Master Switch
echo Launching all DOME Agents...
start "Creator Bot" cmd /c "C:\DOME_CORE\startup\DOME_01_Agent_Creator.bat"
start "Updater Bot" cmd /c "C:\DOME_CORE\startup\DOME_02_Agent_Updater.bat"
start "Payment Bot" cmd /c "C:\DOME_CORE\startup\DOME_03_Agent_Payment.bat"
start "Waiver Recon Bot" cmd /c "C:\DOME_CORE\startup\DOME_04_Agent_Waiver.bat"
echo All agents launched in separate windows!
pause
