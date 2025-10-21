@echo off
chcp 65001 >nul
echo ========================================
echo 清理项目锁定文件
echo ========================================
echo.

REM 步骤1: 停止所有Python进程
echo [步骤1/4] 停止所有Python进程...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM pythonw.exe 2>nul
timeout /t 2 /nobreak >nul
echo ✓ Python进程已停止
echo.

REM 步骤2: 清理__pycache__目录
echo [步骤2/4] 清理__pycache__目录...
for /d /r . %%d in (__pycache__) do @if exist "%%d" (
    echo 删除: %%d
    rd /s /q "%%d" 2>nul
)
echo ✓ __pycache__目录已清理
echo.

REM 步骤3: 清理.pyc文件
echo [步骤3/4] 清理.pyc文件...
del /s /q *.pyc 2>nul
echo ✓ .pyc文件已清理
echo.

REM 步骤4: 清理临时文件
echo [步骤4/4] 清理临时文件...
del /s /q *.pyo 2>nul
del /s /q .pytest_cache 2>nul
del /s /q .mypy_cache 2>nul
echo ✓ 临时文件已清理
echo.

echo ========================================
echo ✅ 清理完成！
echo ========================================
echo.
echo 提示：如果仍然无法复制文件，请：
echo 1. 关闭所有打开项目的IDE（VSCode/PyCharm等）
echo 2. 重启Windows资源管理器
echo 3. 使用管理员权限运行此脚本
echo.
pause



