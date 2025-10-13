@echo off
chcp 65001 >nul
REM 星辰金融终端 - 启动脚本
REM 使用异步启动模式，UI优先显示

echo ========================================
echo    星辰金融终端 v5.0
echo ========================================
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 检查虚拟环境是否存在
if not exist "venv310\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境 venv310
    echo 请先安装虚拟环境或使用系统Python
    pause
    exit /b 1
)

echo [1/3] 激活虚拟环境...
call venv310\Scripts\activate.bat
if errorlevel 1 (
    echo [错误] 虚拟环境激活失败
    pause
    exit /b 1
)

echo [2/3] 启动应用程序（异步模式）...
echo.
python start_async_fixed.py
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [3/3] 程序正常退出
) else (
    echo [3/3] 程序异常退出，错误代码: %EXIT_CODE%
)

REM 如果有错误，暂停以查看错误信息
if %EXIT_CODE% neq 0 (
    echo.
    echo 按任意键退出...
    pause >nul
)

exit /b %EXIT_CODE%

