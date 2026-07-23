@echo off
cd /d "%~dp0"
title AI Livestream Finder

echo =========================================================
echo       HE THONG TIM KIEM VA DANH GIA LIVESTREAM
echo =========================================================
echo.

:: 1. Kiem tra Python
python --version >nul 2>&1
if %errorlevel% neq 0 goto :NO_PYTHON

:: 2. Kiem tra va tao moi truong ao .venv
if not exist ".venv\Scripts\python.exe" goto :CREATE_VENV
goto :CHECK_INSTALLATION

:CREATE_VENV
echo [THONG BAO] Dang tao moi truong ao .venv...
python -m venv .venv
if %errorlevel% neq 0 goto :VENV_ERROR
echo [THANH CONG] Da tao xong moi truong ao .venv!
echo.

:CHECK_INSTALLATION
if exist ".venv\.installed" goto :CHECK_ENV

echo [THONG BAO] Dang cai dat tat ca thu vien vao .venv...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if %errorlevel% neq 0 goto :PIP_ERROR

echo [THONG BAO] Dang cai dat Playwright Chromium...
".venv\Scripts\python.exe" -m playwright install chromium
echo installed > ".venv\.installed"
echo [THANH CONG] Da cai dat xong tat ca thu vien!
echo.

:CHECK_ENV
if exist ".env" goto :START_APP

echo [CANH BAO] Dang tao file .env mau...
echo GROQ_API_KEY=> .env
echo GEMINI_API_KEY=>> .env
echo OPENAI_API_KEY=>> .env
echo YOUTUBE_API_KEY=>> .env
echo [HUONG DAN] Vui long mo file .env va dien API Key truoc khi su dung!
echo.

:START_APP
echo [THANH CONG] Dang khoi chay giao dien Web Dashboard...
start "" "http://localhost:8501/"

".venv\Scripts\python.exe" -m streamlit run dashboard\streamlit_app.py
if %errorlevel% neq 0 goto :RUN_ERROR
goto :END

:NO_PYTHON
echo [LOI] Khong tim thay Python tren may cua ban!
echo Vui long cai dat Python 3.10+ va tich chon "Add Python to PATH".
echo.
pause
exit /b

:VENV_ERROR
echo [LOI] Khong the tao moi truong ao .venv!
echo.
pause
exit /b

:PIP_ERROR
echo [LOI] Khong the cai dat cac thu vien phu thuoc!
echo.
pause
exit /b

:RUN_ERROR
echo.
echo [LOI] Ung dung gap loi khi khoi chay!
pause
exit /b

:END
pause
