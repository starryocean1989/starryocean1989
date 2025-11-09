# -*- coding: utf-8 -*-
# native_log_pipeline 扩展

原生日志管线模块，为高频日志写入提供锁自由合并、批量刷写与降级控制能力。

## 功能概述

- `Pipeline.install(...)`：构建线程安全的原生缓冲区，可配置批量阈值、刷写间隔、SQLite 路径与回调函数。
- `_repeat` 自动去重：相同级别/模块/消息的连续日志只保留一条，并记录重复次数。
- SQLite 批量写入：若传入 `sqlite_path`，原生层会直接执行 `executemany`，避免 Python 多次调用。
- 回调桥接：刷新时先写入 SQLite，再调用 `fallback(batch)` 与 `event_callback(batch)`，用于日志分发或共享内存上报。
- 运行统计：`stats()` 返回推送/刷新/错误等指标，支持运维监控。
- **日志桥接**：集成统一日志系统，C层flush操作自动记录统计信息和错误。
- **监控告警**：`PipelineMonitor` 定期检查健康状态，异常时自动触发告警。

## 编译

```bash
cd backend/infrastructure/native/native_log_pipeline
python setup.py build_ext --inplace
```

或使用统一脚本：

```bash
cd backend/infrastructure/native
.\compile_all.bat
```

## Python API

### 基础用法

```python
import native_log_pipeline

def sqlite_fallback(batch):
    # 回退逻辑（示例）
    for item in batch:
        pass

pipeline = native_log_pipeline.install(
    batch_size=256,
    flush_ms=1500,
    fallback=sqlite_fallback,
    sqlite_path="data/terminal.db",
    enable_logging=True,  # 启用C层日志输出
)

pipeline.push({"timestamp": 1700000000, "level": "INFO", "message": "启动完成"})
pipeline.flush(force=True)
print(pipeline.stats())
native_log_pipeline.flush_and_close(pipeline)
```

### 带监控的高级用法

```python
import native_log_pipeline

# 创建带监控的pipeline
pipeline, monitor = native_log_pipeline.install_with_monitor(
    batch_size=256,
    flush_ms=1500,
    sqlite_path="data/terminal.db",
    enable_logging=True,
    enable_monitor=True,
    monitor_check_interval=60.0,  # 每60秒检查一次
    monitor_error_threshold=10,   # 错误阈值
)

try:
    # 使用pipeline
    pipeline.push({"timestamp": 1700000000, "level": "INFO", "message": "系统启动"})

    # 监控会自动运行并在检测到异常时告警
    # ...

finally:
    # 安全关闭
    if monitor:
        monitor.stop()
    native_log_pipeline.flush_and_close(pipeline)
```

### 手动监控

```python
import native_log_pipeline

pipeline = native_log_pipeline.install(sqlite_path="data/terminal.db")

# 创建监控器
monitor = native_log_pipeline.PipelineMonitor(
    pipeline,
    check_interval=30.0,    # 每30秒检查
    error_threshold=5,      # 降低错误阈值
)

# 启动监控
monitor.start()

try:
    # 使用pipeline...
    pass
finally:
    monitor.stop()
```

> 默认配置通过 `NATIVE_LOG_PIPELINE_BATCH`、`NATIVE_LOG_PIPELINE_FLUSH_MS` 环境变量在 Python 封装层读取。

## 日志桥接功能

C层会自动记录以下事件：
- **Flush完成**：记录批量大小、总计推送/刷新次数
- **Flush失败**：区分SQLite错误和回调错误，提供详细上下文

日志通过统一日志系统输出，可在日志中心查看和告警。

## 监控告警功能

`PipelineMonitor` 提供以下监控能力：
- **定期健康检查**：默认每60秒检查一次pipeline状态
- **错误率监控**：检测SQLite错误和回调错误率
- **Flush失败检测**：监控连续flush失败次数
- **智能告警**：带冷却机制，避免告警风暴
- **结构化日志**：所有告警包含详细的诊断信息

监控指标包括：
- `sqlite_errors`: SQLite写入错误总数
- `fallback_errors`: 回调函数错误总数
- `total_flushed`: 成功flush的记录总数
- `total_flush_calls`: flush调用次数

## 测试

```bash
pytest backend/infrastructure/native/tests/test_native_log_pipeline.py
```

测试覆盖压缩逻辑、SQLite 写入、回退失败后的自动重排等关键路径。
