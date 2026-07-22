@echo off
chcp 65001 >nul
title AI Livestream Finder Launcher
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

:menu
cls
echo ===============================================================
echo                🎯 AI LIVESTREAM FINDER 🎯
echo ===============================================================
echo.
echo  [1] 🚀 Chạy Giao diện Web (Streamlit Dashboard)
echo  [2] 🤖 Chạy Tự động Crawler định kỳ (Auto Crawler)
echo  [3] ⚡ Chạy Benchmark Hiệu năng & Token Waste
echo  [4] 🪙 Theo dõi Token AI Realtime
echo  [5] 🚪 Thoát
echo.
echo ===============================================================
set /p choice="Nhập lựa chọn của bạn [1-5]: "

if "%choice%"=="1" (
    echo.
    echo Đang mở Streamlit Dashboard...
    python -m streamlit run dashboard\streamlit_app.py
    pause
    goto menu
)

if "%choice%"=="2" (
    echo.
    echo Đang chạy Auto Crawler...
    python auto_crawl.py --interval 2
    pause
    goto menu
)

if "%choice%"=="3" (
    echo.
    echo Đang chạy Benchmark...
    python benchmark.py
    pause
    goto menu
)

if "%choice%"=="4" (
    echo.
    echo Đang theo dõi Token Usage...
    python track_tokens.py
    pause
    goto menu
)

if "%choice%"=="5" (
    exit /b
)

echo.
echo ❌ Lựa chọn không hợp lệ, vui lòng thử lại!
timeout /t 2 >nul
goto menu
