@echo off
echo ========================================
echo 干净启动应用（先清理再启动）
echo ========================================
echo.

echo [步骤1] 关闭所有旧进程...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM pythonw.exe 2>nul
echo   ✓ 旧进程已清理

echo.
echo [步骤2] 等待2秒...
timeout /t 2 /nobreak >nul
echo   ✓ 等待完成

echo.
echo [步骤3] 清空旧日志（保留备份）...
if exist logs\terminal_v0.50.log (
    copy /Y logs\terminal_v0.50.log logs\terminal_v0.50.log.backup >nul 2>&1
    echo. > logs\terminal_v0.50.log
    echo   ✓ 日志已重置（旧日志备份到 .log.backup）
)

echo.
echo [步骤4] 启动应用...
echo ========================================
echo.
venv310\Scripts\python.exe start.py

