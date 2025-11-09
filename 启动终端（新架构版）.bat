@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ========================================
REM 星辰金融终端 - 新架构版启动脚本
REM ========================================

REM 默认启用静默模式，避免在Python阶段日志输出前刷屏
set "QUIET_MODE=1"

if defined QUIET_MODE goto :quiet_mode_entry

REM 🔧 优化控制台显示：设置窗口大小、缓冲区与字体大小，重点改善行间距
REM 设置窗口大小：140列，50行（提供更大的显示区域）
mode con: cols=140 lines=50 >nul 2>&1

REM 🔧 扩展屏幕缓冲区高度，恢复鼠标滚动历史查看能力
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $rawUI = (Get-Host).UI.RawUI; $window = $rawUI.WindowSize; $buffer = $rawUI.BufferSize; $buffer.Width = [Math]::Max($window.Width, 160); $buffer.Height = [Math]::Max($buffer.Height, 9000); $rawUI.BufferSize = $buffer; $window.Width = 140; $window.Height = 50; $rawUI.WindowSize = $window } catch { }" >nul 2>&1

REM 🔧 使用PowerShell设置控制台字体大小（通过注册表，重点增加行间距）
REM 注意：增大字体可以间接增加行间距，因为行间距与字体大小成正比
REM FontSize值说明：1048576 = 16pt, 1179648 = 18pt, 1310720 = 20pt, 1441792 = 22pt
REM 使用20pt字体以确保足够的行间距（字体越大，行间距越大）
REM 注意：字体设置需要新窗口才能生效，当前窗口可能仍使用旧设置
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; try { $regPath = 'HKCU:\Console'; if (-not (Test-Path $regPath)) { New-Item -Path $regPath -Force | Out-Null }; $fontSize = 1310720; Set-ItemProperty -Path $regPath -Name 'FontSize' -Value $fontSize -Type DWord -ErrorAction SilentlyContinue; Set-ItemProperty -Path $regPath -Name 'FontFamily' -Value 54 -Type DWord -ErrorAction SilentlyContinue; Set-ItemProperty -Path $regPath -Name 'FontWeight' -Value 400 -Type DWord -ErrorAction SilentlyContinue; Set-ItemProperty -Path $regPath -Name 'FaceName' -Value 'Consolas' -Type String -ErrorAction SilentlyContinue } catch { }" >nul 2>&1

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

REM 🔧 再次设置控制台窗口大小（提权后可能重置了窗口属性）
mode con: cols=140 lines=50 >nul 2>&1

REM 🔧 重新扩展缓冲区高度，防止管理员模式下丢失滚动能力
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $rawUI = (Get-Host).UI.RawUI; $window = $rawUI.WindowSize; $buffer = $rawUI.BufferSize; $buffer.Width = [Math]::Max($window.Width, 160); $buffer.Height = [Math]::Max($buffer.Height, 9000); $rawUI.BufferSize = $buffer; $window.Width = 140; $window.Height = 50; $rawUI.WindowSize = $window } catch { }" >nul 2>&1

REM 🔧 再次设置字体大小（提权后需要重新设置，确保行间距足够）
REM 使用20pt字体以确保足够的行间距（字体越大，行间距越大）
REM 注意：字体设置需要新窗口才能生效，如果当前窗口字体仍小，请关闭重新打开
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; try { $regPath = 'HKCU:\Console'; if (-not (Test-Path $regPath)) { New-Item -Path $regPath -Force | Out-Null }; $fontSize = 1310720; Set-ItemProperty -Path $regPath -Name 'FontSize' -Value $fontSize -Type DWord -ErrorAction SilentlyContinue; Set-ItemProperty -Path $regPath -Name 'FontFamily' -Value 54 -Type DWord -ErrorAction SilentlyContinue; Set-ItemProperty -Path $regPath -Name 'FontWeight' -Value 400 -Type DWord -ErrorAction SilentlyContinue; Set-ItemProperty -Path $regPath -Name 'FaceName' -Value 'Consolas' -Type String -ErrorAction SilentlyContinue } catch { }" >nul 2>&1

title 星辰金融终端 v5.0 - 新架构启动中...

REM 🔧 行间距优化说明
REM 注意：Windows控制台的行间距主要由字体大小决定
REM 已设置20pt字体（FontSize=1310720），这将显著增加行间距
REM 如果行间距仍然不够，可以通过以下方式进一步调整：
REM 1. 右键点击窗口标题栏 -> 属性 -> 字体 -> 选择更大的字体（如22pt或24pt）
REM 2. 按住Ctrl键并滚动鼠标滚轮来动态调整字体大小
REM 3. 字体大小设置会保存，下次打开时会自动应用

REM 🔧 在每个输出后添加空行，增加视觉行间距
echo.
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
echo.

REM ========================================
REM 步骤1: 清理残留进程
REM ========================================

echo [步骤 1/5] 清理残留进程...
echo.
echo.

REM 使用PowerShell清理残留进程
echo [清理] 使用PowerShell检查并清理残留进程...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; $cleaned = 0; Get-Process python -ErrorAction SilentlyContinue | ForEach-Object { try { $cmdline = (Get-WmiObject Win32_Process -Filter \"ProcessId = $($_.Id)\").CommandLine; if ($cmdline) { if ($cmdline -match 'monitor_system\.py') { Write-Host \"[清理] 发现旧监控进程 (PID=$($_.Id))，正在终止...\"; Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; if ($?) { Write-Host \"[OK] 已终止旧监控进程 (PID=$($_.Id))\"; $cleaned = 1 } } elseif ($cmdline -match 'start_new\.py|start_async_fixed\.py') { Write-Host \"[清理] 发现残留主进程 (PID=$($_.Id))，正在终止...\"; Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; if ($?) { Write-Host \"[OK] 已终止残留主进程 (PID=$($_.Id))\"; $cleaned = 1 } } } } catch { } }; if ($cleaned -eq 0) { Write-Host \"[OK] 未发现残留进程\" } else { Write-Host \"[OK] 已清理残留进程，等待资源释放...\"; Start-Sleep -Seconds 2 }"

REM 检查端口占用情况
echo [清理] 检查端口占用情况...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; $ports = Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 5557,5558,5559 -and $_.State -eq 'Listen' }; if ($ports) { $ports | ForEach-Object { $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; if ($proc) { Write-Host \"[警告] 端口 $($_.LocalPort) 被进程 $($_.OwningProcess) ($($proc.ProcessName)) 占用\" } } } else { Write-Host \"[OK] 监控端口未被占用\" }"

echo [OK] 进程清理完成
echo.
echo.

REM ========================================
REM 步骤2: 检查Python环境
REM ========================================

echo [步骤 2/5] 检查Python环境...
echo.

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
echo.

REM ========================================
REM 检查必要文件
REM ========================================

echo [步骤 4/5] 检查必要文件...
echo.

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
echo.

REM ========================================
REM 启动应用程序
REM ========================================

echo [步骤 5/5] 启动应用程序...
echo.
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
    echo 提示:
    echo    - 检查日志文件: logs\application_startup_*.log
    echo    - 检查终端输出的错误信息
    echo    - 如果问题持续，请查看 logs\ 目录下的其他日志
    goto :error_exit
)

REM ========================================
REM 错误退出处理
REM ========================================

:quiet_mode_entry
cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"
set "PYTHON_EXE=%PROJECT_ROOT%\venv310\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

REM 静默执行进程清理和端口检测
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; $cleaned = 0; Get-Process python -ErrorAction SilentlyContinue | ForEach-Object { try { $cmdline = (Get-WmiObject Win32_Process -Filter \"ProcessId = $($_.Id)\").CommandLine; if ($cmdline) { if ($cmdline -match 'monitor_system\.py') { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; if ($?) { $cleaned = 1 } } elseif ($cmdline -match 'start_new\.py|start_async_fixed\.py') { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; if ($?) { $cleaned = 1 } } } } catch { } }; if ($cleaned -ne 0) { Start-Sleep -Seconds 2 }" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 5557,5558,5559 -and $_.State -eq 'Listen' } | ForEach-Object { try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch { } }" >nul 2>&1

"%PYTHON_EXE%" start_new.py
exit /b %ERRORLEVEL%

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
