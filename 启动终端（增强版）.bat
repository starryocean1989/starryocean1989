@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ========================================
REM 星辰金融终端 - 增强版启动脚本
REM ========================================

title 星辰金融终端 v5.0 - 启动中...

echo.
echo ╔════════════════════════════════════════╗
echo ║     星辰金融终端 v5.0                  ║
echo ║     异步启动模式                       ║
echo ╚════════════════════════════════════════╝
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"

echo [✓] 项目根目录: %PROJECT_ROOT%
echo.

REM ========================================
REM 检查Python环境
REM ========================================

echo [步骤 1/4] 检查Python环境...

REM 优先使用虚拟环境
set "PYTHON_EXE="
if exist "venv310\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\venv310\Scripts\python.exe"
    set "VENV_ACTIVATE=%PROJECT_ROOT%\venv310\Scripts\activate.bat"
    echo [✓] 找到虚拟环境: venv310
) else (
    REM 尝试使用系统Python
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=python"
        echo [!] 虚拟环境不存在，使用系统Python
    ) else (
        echo [✗] 错误: 未找到Python环境
        echo     请确保已安装Python或创建虚拟环境 venv310
        goto :error_exit
    )
)

REM 验证Python版本
echo [✓] Python路径: %PYTHON_EXE%
"%PYTHON_EXE%" --version
if errorlevel 1 (
    echo [✗] 错误: Python无法正常运行
    goto :error_exit
)

echo.

REM ========================================
REM 激活虚拟环境
REM ========================================

if defined VENV_ACTIVATE (
    echo [步骤 2/4] 激活虚拟环境...
    call "%VENV_ACTIVATE%"
    if errorlevel 1 (
        echo [✗] 错误: 虚拟环境激活失败
        goto :error_exit
    )
    echo [✓] 虚拟环境已激活
) else (
    echo [步骤 2/4] 跳过虚拟环境（使用系统Python）
)

echo.

REM ========================================
REM 检查必要文件
REM ========================================

echo [步骤 3/4] 检查必要文件...

set "MISSING_FILES="

if not exist "start_async_fixed.py" (
    echo [✗] 缺少文件: start_async_fixed.py
    set "MISSING_FILES=1"
)

if not exist "backend" (
    echo [✗] 缺少目录: backend
    set "MISSING_FILES=1"
)

if not exist "ui" (
    echo [✗] 缺少目录: ui
    set "MISSING_FILES=1"
)

if defined MISSING_FILES (
    echo [✗] 错误: 缺少必要的文件或目录
    goto :error_exit
)

echo [✓] 所有必要文件存在
echo.

REM ========================================
REM 启动应用程序
REM ========================================

echo [步骤 4/4] 启动应用程序...
echo.
echo ========================================
echo   应用程序运行中...
echo   如需退出，请关闭主窗口或按Ctrl+C
echo ========================================
echo.

REM 更改标题
title 星辰金融终端 v5.0 - 运行中

REM 启动Python脚本
"%PYTHON_EXE%" start_async_fixed.py

REM 捕获退出码
set EXIT_CODE=%ERRORLEVEL%

echo.
echo ========================================

if %EXIT_CODE% equ 0 (
    echo [✓] 程序正常退出
    title 星辰金融终端 v5.0 - 已退出
    timeout /t 2 /nobreak >nul
    exit /b 0
) else (
    echo [✗] 程序异常退出 ^(错误代码: %EXIT_CODE%^)
    echo.
    echo 💡 提示:
    echo    - 检查日志文件: logs\async_start.log
    echo    - 检查终端输出的错误信息
    echo    - 如果问题持续，请查看 logs\ 目录下的其他日志
    goto :error_exit
)

REM ========================================
REM 错误退出处理
REM ========================================

:error_exit
echo.
echo ========================================
echo [✗] 启动失败
echo ========================================
echo.
echo 按任意键退出...
pause >nul
exit /b 1

endlocal

