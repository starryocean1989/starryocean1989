# Native Modules Build Guide

This folder contains pybind11-based C++ modules to accelerate critical paths without changing the existing architecture.

Modules:
- `dataconverter`: Fast conversion of raw records to vnpy-friendly bar field dicts.
- `metrics`: Fast computation of Sharpe ratio and maximum drawdown.
- `alert`: Fast evaluation of simple threshold/comparison rules.

## 构建与开发

详见各子目录下的 `README.md` 与 `setup.py` 文件说明。如果你需要一次性编译所有 C 扩展，可以运行仓库根目录下的：

```powershell
./backend/infrastructure/native/compile_all.bat
```

## Native 日志桥接

- Python 层入口：`backend.infrastructure.native.logging_bridge`
  - `install_native_logging_bridge()`：配置日志等级映射与自定义 handler。
  - `log_from_native()`：供 C 扩展直接调用的统一日志入口。
  - `native_call_guard` / `native_async_call_guard`：包装 Python 封装函数，兜底捕获异常并输出结构化日志。
- 接入指南：
  1. 在 C 扩展源文件中包含 `native_log_bridge.h`，并使用 `NATIVE_LOG_ERROR` 等宏替换原有 `fprintf`/`printf` 日志。
  2. 在 Python 包装层（如 `async_ipc.py`）使用守护装饰器或手动调用 `log_from_native`，确保异常不被吞噬。
  3. 可选：通过 `install_native_logging_bridge(handler=...)` 注入自定义统计逻辑，或结合 `LoggingHub` 输出到统一日志系统。

巡检脚本：
- `python scripts/check_native_logging.py --verbose`
  - 检查 Python 封装是否引入 `logging_bridge`/`native_call_guard`。
  - 扫描 C/C++ 源码是否引用 `native_log_bridge`。
  - 执行核心模块冒烟调用并捕获桥接日志。

> 当前阶段已完成 `native_process_metrics` 的桥接接入；后续将继续将 `native_ipc` 与核心并发组件迁移至该日志桥接体系，其余模块按改造方案逐步接入。

## Build

On Windows with Python and a C++ compiler (MSVC) installed:

1. From the repository root, you can run either:
   - `backend\infrastructure\native\compile_newmodules.bat` (快速仅构建新增模块 native_dataconverter/native_metrics/native_alert)
   - `backend\infrastructure\native\compile_all.bat` (完整构建，包含全部原生模块；注意其中包含交互提示与暂停)

Each script installs Python dependencies (pybind11, setuptools, wheel) and builds the modules in-place.

## Usage

- DataConverter (Python):
  - `from backend.infrastructure.data_module_vnpy.data_converter import convert_records_to_vnpy_bars`
  - Convert list-of-dicts records into `vnpy.BarData` objects (best-effort) or field dicts when vnpy is not available.
  - Note: The Python wrapper attempts to load the native `.pyd` from `backend/infrastructure/native/native_dataconverter` automatically if not on `sys.path`.

- Metrics (Python):
  - `import native_metrics`
  - `native_metrics.compute_sharpe(returns, risk_free_rate=0.0)`
  - `native_metrics.compute_max_drawdown(equity_curve)`
  - Note: `backend/services/backtest_optimizer.py` wrapper can auto-load the `.pyd` under `backend/infrastructure/native/native_metrics` when not globally installed.

- AlertEngine (Python):
  - `from backend.services.alert_engine import AlertEngine`
  - `engine.set_rules([{"id":"r1","field":"close","op":">","value":100.0}, ...])`
  - `alerts = engine.evaluate(records)`
  - Note: The `AlertEngine` wrapper auto-loads the `.pyd` under `backend/infrastructure/native/native_alert` if import fails.

## Notes

- Modules are designed to be optional accelerations; fallbacks exist for environments without a compiler.
- No architectural changes are required; integrations remain at the Python level.

## Quick Tests

From repository root:
- `python backend\services\test_native_dataconverter_integration.py`
- `python backend\services\test_alert_engine_basic.py`
- `python backend\services\test_backtest_optimizer_basic.py`

These tests validate both native and pure-Python fallback paths without requiring a full VnPy runtime.
