@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ========================================
REM 星辰金融终端 - 新架构版启动脚本
REM ========================================

REM 检查管理员权限（自动提权）
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [WARN] 检测到当前没有管理员权限
    echo.
    echo 提示: 正在自动请求管理员权限...
    echo      如果出现UAC提示，请点击是 以继续
    echo.
    
    REM 自动请求管理员权限并启动新的管理员实例
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    
    REM 提权成功后会启动新的管理员实例，当前实例退出
    timeout /t 1 /nobreak >nul
    exit /b 0
)

title 星辰金融终端 v5.0 - 新架构启动中...

echo.
echo ╔════════════════════════════════════════╗
echo ║     星辰金融终端 v5.0                  ║
echo ║     新架构启动模式                       ║
echo ╚════════════════════════════════════════╝
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"

echo [✓] 项目根目录: %PROJECT_ROOT%
echo.

REM ========================================
REM 步骤1: 清理残留进程
REM ========================================

echo [步骤 1/5] 清理残留进程...
echo.

REM 使用PowerShell清理残留进程
echo [清理] 使用PowerShell检查并清理残留进程...
powershell -ExecutionPolicy Bypass -Command "& {$cleaned = 0; Get-Process python -ErrorAction SilentlyContinue | ForEach-Object { try { $cmdline = (Get-WmiObject Win32_Process -Filter \"ProcessId = $($_.Id)\").CommandLine; if ($cmdline) { if ($cmdline -match 'monitor_system\.py') { Write-Host \"[清理] 发现旧监控进程 (PID=$($_.Id))，正在终止...\"; Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; if ($?) { Write-Host \"[OK] 已终止旧监控进程 (PID=$($_.Id))\"; $cleaned = 1 } } elseif ($cmdline -match 'start_new\.py|start_async_fixed\.py') { Write-Host \"[清理] 发现残留主进程 (PID=$($_.Id))，正在终止...\"; Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; if ($?) { Write-Host \"[OK] 已终止残留主进程 (PID=$($_.Id))\"; $cleaned = 1 } } } } catch { } }; if ($cleaned -eq 0) { Write-Host \"[OK] 未发现残留进程\" } else { Write-Host \"[OK] 已清理残留进程，等待资源释放...\"; Start-Sleep -Seconds 2 } }"

REM 检查端口占用情况
echo [清理] 检查端口占用情况...
powershell -ExecutionPolicy Bypass -Command "& {$ports = Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 5557,5558,5559 -and $_.State -eq 'Listen' }; if ($ports) { $ports | ForEach-Object { $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; if ($proc) { Write-Host \"[警告] 端口 $($_.LocalPort) 被进程 $($_.OwningProcess) ($($proc.ProcessName)) 占用\" } } } else { Write-Host \"[OK] 监控端口未被占用\" } }"

echo [OK] 进程清理完成
echo.

REM ========================================
REM 步骤2: 检查Python环境
REM ========================================

echo [步骤 2/5] 检查Python环境...

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
    echo [步骤 3/5] 激活虚拟环境...
    call "%VENV_ACTIVATE%"
    if errorlevel 1 (
        echo [✗] 错误: 虚拟环境激活失败
        goto :error_exit
    )
    echo [✓] 虚拟环境已激活
) else (
    echo [步骤 3/5] 跳过虚拟环境（使用系统Python）
)

echo.

REM ========================================
REM 检查必要文件
REM ========================================

echo [步骤 4/5] 检查必要文件...

set "MISSING_FILES="

if not exist "start_new.py" (
    echo [✗] 缺少文件: start_new.py
    set "MISSING_FILES=1"
)

if not exist "backend\startup" (
    echo [✗] 缺少目录: backend\startup
    set "MISSING_FILES=1"
)

if not exist "backend\startup\orchestrator.py" (
    echo [✗] 缺少文件: backend\startup\orchestrator.py
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

echo [步骤 5/5] 启动应用程序...
echo.
echo ========================================
echo   应用程序运行中...
echo   使用新架构: StartupOrchestrator
echo   如需退出，请关闭主窗口或按Ctrl+C
echo ========================================
echo.

REM 更改标题
title 星辰金融终端 v5.0 - 新架构运行中

REM 启动Python脚本
"%PYTHON_EXE%" start_new.py

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
    echo    - 检查日志文件: logs\ai\application_startup_*.log
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

