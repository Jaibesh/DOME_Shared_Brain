@echo off
echo ============================================
echo   Epic 4x4 Operations Dashboard (Frontend)
echo   Starting User Interface on port 5173...
echo ============================================
echo.

cd /d "%~dp0frontend"
npm run dev
pause
