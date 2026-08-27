#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "[1/3] Creating virtual environment..."
    python3 -m venv .venv
fi

echo "[2/3] Installing dependencies..."
.venv/bin/python -m pip install -r requirements.txt

echo "[3/3] Starting Graham Stock Screener at http://localhost:8501 ..."
.venv/bin/python -m streamlit run app.py
