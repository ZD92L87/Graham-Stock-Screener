@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
)

echo [2/3] Installing dependencies...
.venv\Scripts\python.exe -m pip install -r requirements.txt

echo [3/3] Starting Graham Stock Screener at http://localhost:8501 ...
.venv\Scripts\python.exe -m streamlit run app.py

endlocal
