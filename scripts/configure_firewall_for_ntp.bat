@echo off
chcp 65001 >nul
echo ====================================================================
echo Windows防火墙NTP配置工具
echo ====================================================================
echo.
echo 此脚本将配置Windows防火墙允许UDP 123端口(NTP)出站
echo 需要管理员权限运行
echo.
echo ====================================================================

:: 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ 错误: 需要管理员权限
    echo.
    echo 请右键点击此脚本，选择"以管理员身份运行"
    echo.
    pause
    exit /b 1
)

echo ✅ 已获取管理员权限
echo.

:: 方案1: 为Python.exe添加出站规则
echo [步骤1] 为Python添加UDP出站规则...
echo.

:: 获取Python路径
set PYTHON_PATH=%~dp0..\venv310\Scripts\python.exe
if not exist "%PYTHON_PATH%" (
    set PYTHON_PATH=python.exe
)

echo Python路径: %PYTHON_PATH%
echo.

:: 删除可能存在的旧规则
netsh advfirewall firewall delete rule name="Python NTP UDP Outbound" >nul 2>&1

:: 添加新规则 - 允许Python的UDP出站
netsh advfirewall firewall add rule ^
    name="Python NTP UDP Outbound" ^
    dir=out ^
    action=allow ^
    protocol=udp ^
    remoteport=123 ^
    program="%PYTHON_PATH%" ^
    description="允许Python程序进行NTP时间同步(UDP 123端口出站)" ^
    enable=yes

if %errorLevel% equ 0 (
    echo ✅ 已添加Python UDP出站规则
) else (
    echo ⚠️ 添加规则失败，可能已存在或路径错误
)
echo.

:: 方案2: 通用UDP 123出站规则(可选)
echo [步骤2] 添加通用NTP出站规则(可选)...
echo.

:: 删除可能存在的旧规则
netsh advfirewall firewall delete rule name="NTP Client UDP Outbound" >nul 2>&1

:: 添加通用规则
netsh advfirewall firewall add rule ^
    name="NTP Client UDP Outbound" ^
    dir=out ^
    action=allow ^
    protocol=udp ^
    remoteport=123 ^
    description="允许所有程序的NTP客户端请求(UDP 123端口出站)" ^
    enable=yes

if %errorLevel% equ 0 (
    echo ✅ 已添加通用NTP出站规则
) else (
    echo ⚠️ 添加规则失败
)
echo.

:: 显示当前规则
echo [步骤3] 查看已添加的防火墙规则...
echo.
netsh advfirewall firewall show rule name="Python NTP UDP Outbound"
echo.
netsh advfirewall firewall show rule name="NTP Client UDP Outbound"
echo.

echo ====================================================================
echo 配置完成！
echo ====================================================================
echo.
echo 已添加的防火墙规则:
echo   1. Python NTP UDP Outbound - 允许Python程序UDP出站到123端口
echo   2. NTP Client UDP Outbound - 允许所有程序UDP出站到123端口
echo.
echo 测试建议:
echo   运行测试脚本验证: python scripts\test_ntp_tcp_vs_udp.py
echo.
echo 如需删除规则，可运行:
echo   netsh advfirewall firewall delete rule name="Python NTP UDP Outbound"
echo   netsh advfirewall firewall delete rule name="NTP Client UDP Outbound"
echo.
pause
