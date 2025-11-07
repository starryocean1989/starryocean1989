@echo off
REM 编译所有native C扩展模块
REM 使用方法: compile_all.bat

echo ========================================
echo 编译所有Native C扩展模块
echo ========================================
echo.

REM 获取脚本所在目录
cd /d %~dp0

REM 编译native_compute
echo [1/6] 编译 native_compute...
cd native_compute
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_compute 编译失败
    pause
    exit /b 1
)
echo ✅ native_compute 编译成功
cd ..
echo.

REM 编译native_serialization
echo [2/6] 编译 native_serialization...
cd native_serialization
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_serialization 编译失败
    pause
    exit /b 1
)
echo ✅ native_serialization 编译成功
cd ..
echo.

REM 编译native_iocp
echo [3/6] 编译 native_iocp...
cd native_iocp
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_iocp 编译失败
    pause
    exit /b 1
)
echo ✅ native_iocp 编译成功
cd ..
echo.

REM 编译native_ipc
echo [4/6] 编译 native_ipc...
cd native_ipc
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_ipc 编译失败
    pause
    exit /b 1
)
echo ✅ native_ipc 编译成功
cd ..
echo.

REM 编译native_gil
echo [5/6] 编译 native_gil...
cd native_gil
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_gil 编译失败
    pause
    exit /b 1
)
echo ✅ native_gil 编译成功
cd ..
echo.

REM 编译native_collections
echo [6/6] 编译 native_collections...
cd native_collections
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_collections 编译失败
    pause
    exit /b 1
)
echo ✅ native_collections 编译成功
cd ..
echo.

echo ========================================
echo ✅ 所有模块编译完成！
echo ========================================
echo.
echo 提示：native_compute 新增了日期批量处理功能
echo      - batch_validate_iso_dates: 批量验证ISO日期格式
echo      - batch_compare_dates: 批量比较日期
echo.
pause
