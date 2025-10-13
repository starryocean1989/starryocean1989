@echo off
REM 星辰金融终端 - 快速启动（无多余输出）
chcp 65001 >nul
cd /d "%~dp0"
call venv310\Scripts\activate.bat 2>nul
start "星辰金融终端" /B python start_async_fixed.py

