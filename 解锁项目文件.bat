@echo off
chcp 65001 >nul
title 项目文件解锁工具
echo.
echo ============================================================
echo 项目文件解锁工具
echo ============================================================
echo.

"%~dp0venv310\Scripts\python.exe" "%~dp0解锁项目文件.py"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo 按任意键退出...
    pause >nul
) else (
    echo.
    echo 发生错误，退出代码: %ERRORLEVEL%
    echo 按任意键退出...
    pause >nul
    exit /b %ERRORLEVEL%
)

