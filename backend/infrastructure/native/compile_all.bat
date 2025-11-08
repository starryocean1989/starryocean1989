@echo off
:: -*- coding: utf-8 -*-
REM 编译所有 native C 扩展模块
REM 使用方法: compile_all.bat

echo ========================================
echo 编译所有 Native C 扩展模块
echo ========================================
echo.

REM 获取脚本所在目录
cd /d %~dp0

REM --------------------------------------------------
REM 1. native_compute
echo [1/22] 编译 native_compute...
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

REM 2. native_serialization
echo [2/22] 编译 native_serialization...
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

REM 3. native_conversion
echo [3/22] 编译 native_conversion...
cd native_conversion
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_conversion 编译失败
    pause
    exit /b 1
)
echo ✅ native_conversion 编译成功
cd ..
echo.

REM 4. native_vnpy_conversion
echo [4/22] 编译 native_vnpy_conversion...
cd native_vnpy_conversion
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_vnpy_conversion 编译失败
    pause
    exit /b 1
)
echo ✅ native_vnpy_conversion 编译成功
cd ..
echo.

REM 5. native_dataframe_ops
echo [5/22] 编译 native_dataframe_ops...
cd native_dataframe_ops
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_dataframe_ops 编译失败
    pause
    exit /b 1
)
echo ✅ native_dataframe_ops 编译成功
cd ..
echo.

REM 6. native_finance_ops
echo [6/22] 编译 native_finance_ops...
cd native_finance_ops
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_finance_ops 编译失败
    pause
    exit /b 1
)
echo ✅ native_finance_ops 编译成功
cd ..
echo.

REM 7. native_statistics
echo [7/22] 编译 native_statistics...
cd native_statistics
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_statistics 编译失败
    pause
    exit /b 1
)
echo ✅ native_statistics 编译成功
cd ..
echo.

REM 8. native_iocp
echo [8/23] 编译 native_iocp...
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

REM 9. native_fs
echo [9/23] 编译 native_fs...
cd native_fs
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_fs 编译失败
    pause
    exit /b 1
)
echo ✅ native_fs 编译成功
cd ..
echo.

REM 10. native_ipc
echo [10/23] 编译 native_ipc...
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

REM 11. native_gil
echo [11/23] 编译 native_gil...
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

REM 12. native_collections
echo [12/23] 编译 native_collections...
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

REM 13. native_memory
echo [13/23] 编译 native_memory...
cd native_memory
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_memory 编译失败
    pause
    exit /b 1
)
echo ✅ native_memory 编译成功
cd ..
echo.

REM 14. native_socket_metrics
echo [14/23] 编译 native_socket_metrics...
cd native_socket_metrics
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_socket_metrics 编译失败
    pause
    exit /b 1
)
echo ✅ native_socket_metrics 编译成功
cd ..
echo.

REM 15. native_process_metrics
echo [15/23] 编译 native_process_metrics...
cd native_process_metrics
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_process_metrics 编译失败
    pause
    exit /b 1
)
echo ✅ native_process_metrics 编译成功
cd ..
echo.

REM 16. native_netprobe
echo [16/23] 编译 native_netprobe...
cd native_netprobe
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_netprobe 编译失败
    pause
    exit /b 1
)
echo ✅ native_netprobe 编译成功
cd ..
echo.

REM 17. native_smart_monitor
echo [17/23] 编译 native_smart_monitor...
cd native_smart_monitor
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_smart_monitor 编译失败
    pause
    exit /b 1
)
echo ✅ native_smart_monitor 编译成功
cd ..
echo.

REM 18. native_log_pipeline
echo [18/23] 编译 native_log_pipeline...
cd native_log_pipeline
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_log_pipeline 编译失败
    pause
    exit /b 1
)
echo ✅ native_log_pipeline 编译成功
cd ..
echo.

REM 19. native_rpc_bridge
echo [19/23] 编译 native_rpc_bridge...
cd native_rpc_bridge
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_rpc_bridge 编译失败
    pause
    exit /b 1
)
echo ✅ native_rpc_bridge 编译成功
cd ..
echo.

REM 20. native_async
echo [20/23] 编译 native_async...
cd native_async
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_async 编译失败
    pause
    exit /b 1
)
echo ✅ native_async 编译成功
cd ..
echo.

REM 21. native_symbol_index
echo [21/23] 编译 native_symbol_index...
cd native_symbol_index
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_symbol_index 编译失败
    pause
    exit /b 1
)
echo ✅ native_symbol_index 编译成功
cd ..
echo.

REM 22. native_indicator
echo [22/23] 编译 native_indicator...
cd native_indicator
python setup.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo ❌ native_indicator 编译失败
    cd..
    pause
    exit /b 1
)
echo ✅ native_indicator 编译成功
cd ..
echo.

REM 23. native_qhighlighter (UI 扩展)
echo [23/23] 编译 native_qhighlighter...
pushd ..\..\..\ui\native_extensions\native_qhighlighter >nul
if exist setup.py (
    python setup.py build_ext --inplace
    if %ERRORLEVEL% NEQ 0 (
        echo ❌ native_qhighlighter 编译失败
        popd >nul
        pause
        exit /b 1
    )
    echo ✅ native_qhighlighter 编译成功
) else (
    echo ⚠️ 未找到 native_qhighlighter/setup.py，跳过
)
popd >nul
echo.

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
