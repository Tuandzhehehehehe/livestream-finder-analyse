@echo off
cd /d "%~dp0"
title AI Livestream Finder & Evaluator

echo =========================================================
echo       AI LIVESTREAM FINDER & AGENT EVALUATOR
echo =========================================================
echo.

:: 1. Kiem tra Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python tren may cua ban!
    echo Vui long cai dat Python 3.10+ tu https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 2. Kiem tra va tao moi truong ao .venv
if not exist ".venv\Scripts\python.exe" (
    echo [THONG BAO] Dang tao moi truong ao .venv...
    python -m venv .venv
)

:: 3. Kiem tra & cai dat requirements
if not exist ".venv\.installed" (
    echo [THONG BAO] Dang cai dat thu vien va Playwright Chromium...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    ".venv\Scripts\python.exe" -m playwright install chromium
    echo installed > ".venv\.installed"
    echo [THANH CONG] Da cai dat xong tat ca thu vien!
    echo.
)

:: 4. Kiem tra file .env
if not exist ".env" (
    echo [CANH BAO] Dang tao file .env mau...
    echo GROQ_API_KEY=> .env
    echo GEMINI_API_KEY=>> .env
    echo OPENAI_API_KEY=>> .env
    echo YOUTUBE_API_KEY=>> .env
    echo [HUONG DAN] Vui long mo file .env va dien API Key neu can dung them LLM ngoai!
    echo.
)

:: 5. Khoi chay Dashboard
echo [THANH CONG] Dang khoi chay giao dien Web Dashboard...
start "" "http://localhost:8501/"
".venv\Scripts\python.exe" -m streamlit run dashboard\streamlit_app.py

pause
