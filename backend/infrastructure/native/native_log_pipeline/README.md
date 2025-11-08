# -*- coding: utf-8 -*-
# native_log_pipeline 扩展

原生日志管线模块，为高频日志写入提供锁自由合并、批量刷写与降级控制能力。

## 功能概述

- `Pipeline.install(...)`：构建线程安全的原生缓冲区，可配置批量阈值、刷写间隔、SQLite 路径与回调函数。
- `_repeat` 自动去重：相同级别/模块/消息的连续日志只保留一条，并记录重复次数。
- SQLite 批量写入：若传入 `sqlite_path`，原生层会直接执行 `executemany`，避免 Python 多次调用。
- 回调桥接：刷新时先写入 SQLite，再调用 `fallback(batch)` 与 `event_callback(batch)`，用于日志分发或共享内存上报。
- 运行统计：`stats()` 返回推送/刷新/错误等指标，支持运维监控。

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
)

pipeline.push({"timestamp": 1700000000, "level": "INFO", "message": "启动完成"})
pipeline.flush(force=True)
print(pipeline.stats())
native_log_pipeline.flush_and_close(pipeline)
```

> 默认配置通过 `NATIVE_LOG_PIPELINE_BATCH`、`NATIVE_LOG_PIPELINE_FLUSH_MS` 环境变量在 Python 封装层读取。

## 测试

```bash
pytest backend/infrastructure/native/tests/test_native_log_pipeline.py
```

测试覆盖压缩逻辑、SQLite 写入、回退失败后的自动重排等关键路径。
