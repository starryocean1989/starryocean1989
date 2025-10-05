@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo 🚀 星辰金融终端启动器 (Windows)
echo ==========================================

REM 检查Python环境
echo 🔍 检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python未安装或不在PATH中
    echo 请确保Python已安装并添加到系统PATH
    pause
    exit /b 1
)

REM 检查虚拟环境
echo 🔍 检查虚拟环境...
if not exist "venv310\Scripts\activate.bat" (
    echo ❌ 虚拟环境不存在
    echo 请运行: python -m venv venv310
    pause
    exit /b 1
)

REM 设置窗口标题和大小
title 星辰金融终端启动器
mode con: cols=80 lines=25

echo ✅ 环境检查通过

REM 启动选项菜单
:menu
echo.
echo 🎯 请选择启动模式:
echo.
echo 1. 完整启动 (推荐) - 启动后端+UI+监控
echo 2. 快速启动 - 仅启动必要服务
echo 3. 开发模式 - 启用调试和热更新
echo 4. 诊断模式 - 检查系统状态
echo 5. 退出
echo.

set /p choice="请输入选择 (1-5): "

if "%choice%"=="1" goto full_start
if "%choice%"=="2" goto quick_start
if "%choice%"=="3" goto dev_start
if "%choice%"=="4" goto diagnostic
if "%choice%"=="5" goto exit

echo ❌ 无效选择，请重新输入
goto menu

:full_start
echo.
echo 🏃‍♂️ 执行完整启动...
echo ==========================================
python start_terminal.py
goto end

:quick_start
echo.
echo ⚡ 执行快速启动...
echo ==========================================
python start_terminal.py quick
goto end

:dev_start
echo.
echo 🔧 执行开发模式启动...
echo ==========================================
echo 启用热更新和调试模式...
python -c "
import sys
sys.argv = ['start_terminal.py', '--dev']
exec(open('start_terminal.py').read())
"
goto end

:diagnostic
echo.
echo 🔍 执行系统诊断...
echo ==========================================
python -c "
import sys
sys.path.insert(0, '.')
from start_terminal import TerminalLauncher

launcher = TerminalLauncher()
diagnostics = launcher.run_diagnostics()

print('📊 系统诊断结果:')
print('=' * 30)
for key, value in diagnostics.items():
    if key == 'import_error':
        continue
    status = '✅' if value else '❌'
    print(f'{status} {key}: {value}')

if not diagnostics.get('import_error'):
    print()
    print('🎉 所有检查通过！')
else:
    print()
    print('❌ 发现问题:')
    print(diagnostics['import_error'])
"
pause
goto menu

:exit
echo.
echo 👋 感谢使用星辰金融终端启动器！
pause
exit /b 0

:end
