@echo off
:: -*- coding: utf-8 -*-
REM 编译所有 native C 扩展模块
REM 使用方法: compile_all.bat

setlocal EnableDelayedExpansion

set TOTAL_STEPS=28
set STEP=1

echo ========================================
echo 编译所有 Native C 扩展模块
echo ========================================
echo.

REM 获取脚本所在目录
cd /d %~dp0

call :build_module native_compute native_compute
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_serialization native_serialization
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_conversion native_conversion
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_vnpy_conversion native_vnpy_conversion
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_dataframe_ops native_dataframe_ops
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_finance_ops native_finance_ops
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_statistics native_statistics
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_iocp native_iocp
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_fs native_fs
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_ipc native_ipc
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_gil native_gil
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_collections native_collections
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_queue native_queue
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_memory native_memory
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_socket_metrics native_socket_metrics
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_process_metrics native_process_metrics
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_load_balancer native_load_balancer
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_netprobe native_netprobe
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_smart_monitor native_smart_monitor
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_log_pipeline native_log_pipeline
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_rpc_bridge native_rpc_bridge
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_async native_async
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_scheduler native_scheduler
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_threadpool native_threadpool
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_symbol_index native_symbol_index
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_indicator native_indicator
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module native_calendar native_calendar
if %ERRORLEVEL% NEQ 0 goto :FAILED
call :build_module "..\..\..\ui\native_extensions\native_qhighlighter" native_qhighlighter optional
if %ERRORLEVEL% NEQ 0 goto :FAILED

goto :SUCCESS

:build_module
set "MODULE_DIR=%~1"
set "MODULE_NAME=%~2"
set "MODULE_OPTION=%~3"

echo [%STEP%/%TOTAL_STEPS%] 编译 %MODULE_NAME%...
if "%MODULE_DIR%"=="" (
    echo ❌ 未提供 %MODULE_NAME% 的路径
    exit /b 1
)
if not exist "%MODULE_DIR%\setup.py" (
    if /I "%MODULE_OPTION%"=="optional" (
        echo ⚠️ 未找到 %MODULE_NAME%\setup.py，跳过
        echo.
        set /a STEP+=1
        exit /b 0
    ) else (
        echo ❌ 未找到 %MODULE_NAME%\setup.py
        exit /b 1
    )
)

pushd "%MODULE_DIR%" >nul
call :run_python_build "%MODULE_NAME%"
set "RESULT=%ERRORLEVEL%"
popd >nul
if %RESULT% NEQ 0 exit /b %RESULT%
echo.
set /a STEP+=1
exit /b 0

:run_python_build
set "MODULE_NAME=%~1"
python setup.py build_ext --inplace
if %ERRORLEVEL% EQU 0 (
    echo ✅ %MODULE_NAME% 编译成功
    exit /b 0
)
echo ⚠️ %MODULE_NAME% 首次编译失败（可能是已有文件被占用），尝试使用临时输出目录...
python setup.py build_ext --build-temp build\temp --build-lib build\lib
if %ERRORLEVEL% NEQ 0 (
    echo ❌ %MODULE_NAME% 编译失败
    exit /b 1
)
echo ✅ %MODULE_NAME% 编译成功（使用临时输出目录 build\lib）
exit /b 0

:SUCCESS
echo ========================================
echo ✅ 所有模块编译完成！
echo ========================================
echo.
echo 提示：native_compute 新增了日期批量处理功能
echo      - batch_validate_iso_dates: 批量验证 ISO 日期格式
echo      - batch_compare_dates: 批量比较日期
echo.
echo 提示：native_indicator_core 默认自动启用，设置 ENABLE_NATIVE_INDICATOR_AVX2=1 可开启 AVX2 优化
echo.
echo 提示：UI 原生高亮可通过 native_qhighlighter 扩展加速，若需关闭请设置 NATIVE_QHIGHLIGHTER=0
echo.
pause
endlocal
exit /b 0

:FAILED
echo.
echo ❌ 编译过程已终止。
pause
endlocal
exit /b 1
