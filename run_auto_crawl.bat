@echo off
chcp 65001 >nul
title AI Livestream Finder - Auto Crawler
echo ===================================================
echo 🤖 Đang khởi động AI Livestream Auto Crawler...
echo ===================================================

cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python auto_crawl.py --interval 2
pause
