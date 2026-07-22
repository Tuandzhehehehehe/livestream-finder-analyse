@echo off
cd /d %~dp0
title AI Livestream Finder

echo ===================================================
echo AI Livestream Finder is starting...
echo ===================================================

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

start "" "http://localhost:8501/"

python -m streamlit run dashboard\streamlit_app.py
pause
