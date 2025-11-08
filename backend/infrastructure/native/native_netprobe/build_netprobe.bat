@echo off
cd /d C:\Users\USER\Desktop\terminal_v0.50\backend\infrastructure\native\native_netprobe
echo 正在编译 native_netprobe...
C:\Users\USER\Desktop\terminal_v0.50\venv310\Scripts\python.exe setup.py build_ext --inplace
if %ERRORLEVEL% EQU 0 (
    echo 编译成功！
    dir *.pyd
) else (
    echo 编译失败，错误代码: %ERRORLEVEL%
)
pause
