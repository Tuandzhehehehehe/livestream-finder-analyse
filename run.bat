@echo off
chcp 65001 >nul
title AI Livestream Finder
cd /d "%~dp0"

echo ===================================================
echo 🎯 Đang khởi động AI Livestream Finder...
echo ===================================================

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

start "" "http://localhost:8501/"

python -m streamlit run dashboard\streamlit_app.py
pause
