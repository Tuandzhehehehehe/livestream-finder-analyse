@echo off
chcp 65001 >nul
title AI Livestream Finder - Dashboard
echo ===================================================
echo 🎯 Đang khởi động AI Livestream Finder Dashboard...
echo ===================================================

cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python -m streamlit run dashboard\streamlit_app.py
pause
