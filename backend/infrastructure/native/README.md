# Native 模块总览（v1.5）

所有 `backend/infrastructure/native/` 下的模块均基于 pybind11 / C++ 实现，用于在 **三进程启动架构** 与 **数据/监控核心路径** 中提供可选的性能加速。仓库默认提供 Python 回退逻辑，未编译时功能不会缺失，只会降低性能并在日志中输出降级提示。

---

## 🧩 模块分类与作用

| 类别 | 代表模块 | 主要能力 | 典型调用方 |
| --- | --- | --- | --- |
| 并发与调度 | `native_threadpool`, `native_scheduler`, `native_gil`, `native_queue` | 原生线程池、类别限流、无锁队列、HighPerfEvent | `backend/startup/native_support.NativeStartupRuntime`, `data_module_vnpy.core_engine` |
| 进程通信与 I/O | `native_ipc`, `native_iocp`, `native_serialization`, `native_fs`, `native_log_pipeline`, `native_log_bridge` | Windows Named Pipe + IOCP、零拷贝序列化、批量日志刷写 | `backend/startup/workers/*`, `system_vnpy.monitor_system`, `LoggingInitStage` |
| 数据处理与指标 | `native_dataconverter`, `native_vnpy_conversion`, `native_dataframe_ops`, `native_compute`, `native_finance_ops`, `native_indicator`, `native_data_quality`, `native_async` | 批量行情/指标计算、异步归约、金融指标 | `data_module_vnpy.*`, `services/strategy_center`, `MarketBoardService` |
| 资源监控与运维 | `native_process_metrics`, `native_socket_metrics`, `native_netprobe`, `native_smart_monitor`, `native_statistics`, `native_load_balancer` | 系统指标采集、网络探测、SMART、滑动统计 | `system_vnpy.monitor_system`, `MonitorLauncherWorker`, `LoadBalancer` |
| 辅助扩展 | `native_collections`, `native_memory`, `native_conversion`, `native_calendar`, `native_alert`, `native_metrics` | LRU/优先队列、零拷贝内存池、日期/日历、告警引擎、绩效指标 | `data_module_vnpy`, `services/system_manager`, `services/backtest_optimizer` |

各子目录内附带 `README.md` / `tests/` / `setup.py`，记录详细 API 与构建说明。推荐从上表定位需求再查阅对应子模块文档。

---

## 🚀 启动架构中的原生组件

- **阶段 1-3 日志桥接**：`LoggingInitStage` 自动加载 `native_log_pipeline`，并通过 `logging_bridge` 将 monitor/data 子进程日志串入 `LoggingHub`。
- **阶段 3 进程编排**：`ProcessOrchestrator` 使用 `native_ipc` 与 `HighPerfEvent` 实现 2 秒心跳；`MonitorLauncherWorker` / `DataLauncherWorker` 会在启动子进程时注入 `LOGGING_QUEUE_TOKEN`。
- **服务后台初始化**：`NativeStartupRuntime` 结合 `native_threadpool`、`native_scheduler` 与 `native_gil.high_perf_event`，在后台执行 `ServiceInitializer` 的重量级任务，同时通过 `service_tracker.snapshot()` 回传 ready/pending/failed。
- **缓存验证**：数据进程的 8 步验证链路广泛使用 `native_async`, `native_collections`, `native_serialization`, `native_iocp`。

> ⚙️ **环境变量**：大多数模块支持 `DISABLE_*` 或 `NATIVE_*` 开关，例如 `NATIVE_VNPY_CONVERSION=0`、`FORCE_PY_LOAD_BALANCER=1`。可在 `start_new.py` 或部署脚本中按需覆盖。

---

## 🔄 构建与清单

1. 安装 MSVC（Visual Studio Build Tools 或完整 VS）并激活对应命令行环境。
2. 在项目根目录执行：
   ```powershell
   # 全量构建（建议首次执行）
   .\backend\infrastructure\native\compile_all.bat

   # 仅增量构建新增模块（如升级后新增目录）
   .\backend\infrastructure\native\compile_newmodules.bat
   ```
3. 每个目录的 `setup.py` 均支持独立构建，例如：
   ```powershell
   cd backend\infrastructure\native\native_ipc
   python setup.py build_ext --inplace
   ```
4. 如需清理旧产物，可删除各子目录下的 `build/`、`*.pyd` 文件或执行 `python setup.py clean`.

> 📦 **编译输出路径**：默认生成的 `.pyd` 与 `*.dll` 会保留在子目录下，`PYTHONPATH` 通过 `backend.infrastructure.native.__init__` 自动补齐，无需手动安装到 site-packages。

---

## 🧪 自检脚本

- `python scripts/check_native_logging.py --verbose`：验证日志桥接是否启用。
- `python tests/test_native_*`：仓库已提供核心集成测试，例如：
  - `tests/test_native_rpc_bridge.py`
  - `tests/test_native_async_reduce.py`
  - `tests/test_resource_monitor_native.py`
  - `tests/test_native_dataframe_filter_symbols.py`

> 建议在 CI/手动升级原生模块后运行相关测试，确保 Python 回退路径与原生路径行为一致。

---

## 📝 集成注意事项

1. **可选加速**：所有模块均提供 `try/except ImportError` 回退，调用方需在日志中记录降级提示，但不应直接崩溃。
2. **日志规范**：若模块执行关键逻辑，应通过 `logging_bridge.native_call_guard` 或在 C++ 中使用 `native_log_bridge.h` 的日志宏，确保输出进入统一日志系统。
3. **ABI 与 Python 版本**：当前仓库默认构建目标为 CPython 3.10 x64；升级 Python 版本时需重新编译。
4. **性能 Profile**：`backend/infrastructure/native/match_cache.py` 与 `native_collections/tests/` 提供示例 Benchmark，可用于验证编译产物性能。
5. **部署建议**：生产环境打包时请确保将 `.pyd` 与对应 `*.dll` 一并发布，避免运行时降级。

---

## 📚 相关文档

- `backend/startup/README.md`：说明原生线程池与 ProcessOrchestrator 如何与启动流程协作。
- `backend/infrastructure/data_module_vnpy/README.md`：记录数据进程中原生扩展的使用矩阵。
- `backend/infrastructure/system_vnpy/系统监控完整集成指南.md`：介绍监控进程与原生监控模块的组合。
- `docs/2.底层被调用功能包介绍文档/`：包含部分模块的深入架构说明。

如需新增原生模块，请参考现有目录结构（README + setup.py + tests），并在本文件更新模块分类表。

