@echo off
echo Starting MPWR Payment Agent...
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt
playwright install chromium
python main.py
pause
