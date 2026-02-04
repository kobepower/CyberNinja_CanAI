@echo off
REM CanAI Pro Launcher - Sets UTF-8 encoding for Windows
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
python main.py
pause
