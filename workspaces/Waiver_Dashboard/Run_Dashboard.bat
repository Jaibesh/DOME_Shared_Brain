@echo off
echo ============================================
echo  Epic 4x4 Operations Dashboard
echo  Starting backend on port 8001...
echo  (MPWR webhook uses port 8000)
echo ============================================
echo.

REM Navigate to backend
cd /d "%~dp0backend"

REM Activate venv if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Start the FastAPI server on port 8001
echo [*] Starting FastAPI server on port 8001...
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

pause
