@echo off
chcp 65001 > nul
cd /d "%~dp0"
title AI Livestream Finder

echo =========================================================
echo       HE THONG TIM KIEM VA DANH GIA LIVESTREAM
echo =========================================================
echo.

:: 1. Kiem tra Python tren he thong
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Python tren may cua ban!
    echo Vui long cai dat Python 3.10+ va tich chon "Add Python to PATH".
    pause
    exit /b
)

:: 2. Kiem tra va tao moi truong ao (.venv) cuc bo ngay trong thu muc du an
if not exist ".venv\Scripts\python.exe" (
    echo [THONG BAO] Dang tao moi truong ao (.venv) cuc bo trong thu muc du an...
    python -m venv .venv
    if errorlevel 1 (
        echo [LOI] Khong the tao .venv! Vui long kiem tra lai Python.
        pause
        exit /b
    )
    echo [THANH CONG] Da tao xong moi truong ao .venv cuc bo!
    echo.
)

:: 3. CHUYEN DIEN: Goi truc tiep file python.exe NAM TRONG .venv
:: Dam bao 100% thu vien duoc cai vao .venv cua thu muc, HOAN TOAN KHONG DANG KY HOAC DUNG TOAN CUC (Global)
echo [1/3] Dang cai dat tat ca thu vien VAO TRONG THU MUC .venv...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [LOI] Khong the cai dat cac thu vien vao .venv!
    pause
    exit /b
)

echo [2/3] Dang cai dat trinh duyet Playwright Chromium cho .venv...
".venv\Scripts\python.exe" -m playwright install chromium

:: 4. Kiem tra file cau hinh .env
echo.
if not exist ".env" (
    echo [CANH BAO] Khong tim thay file cau hinh .env!
    echo Dang khoi tao file .env mau...
    (
        echo # GROQ / GEMINI / OPENAI API KEY
        echo GROQ_API_KEY=
        echo GEMINI_API_KEY=
        echo OPENAI_API_KEY=
        echo.
        echo # YOUTUBE DATA API V3 KEY (TUY CHON)
        echo YOUTUBE_API_KEY=
    ) > .env
    echo [HUONG DAN] Vui long mo file .env va dien API Key truoc khi su dung!
    echo.
)

:: 5. Mo trinh duyet va khoi chay bang python.exe CUA .venv
echo [3/3] Dang khoi chay giao dien Dashboard tu .venv...
start "" "http://localhost:8501/"

".venv\Scripts\python.exe" -m streamlit run dashboard\streamlit_app.py

pause
