# -*- coding: utf-8 -*-
# native_scheduler 模块

## 概述

`native_scheduler` 提供面向交易端调度场景的高性能任务调度组件，包含两层能力：

1. `NativeScheduler`：多类别任务队列 + 线程池执行器，支持队列容量控制与并发限流。
2. `NativeCronScheduler`：基于原生调度器封装的轻量级定时任务管理，支持 `interval` / `cron` / `date` 三类触发方式。

模块默认加载 `_native_scheduler` C 扩展；若编译缺失，则自动回退至 Python 实现（使用 `ThreadPoolExecutor`），保持接口一致，保障测试与降级运行。

## 核心特性

- ✅ **按类别限流**：`register_category` 可为不同业务队列配置独立的 `queue_capacity` 与 `max_workers`。
- ✅ **线程安全提交**：任务提交、统计、关停全程通过原生锁保护，支持高并发调用。
- ✅ **定时任务**：`NativeCronScheduler` 提供 interval/cron/date 触发器，内部使用小顶堆维护下一次执行时间。
- ✅ **可控降级**：通过环境变量 `NATIVE_SCHEDULER_FORCE_NATIVE=1` / `NATIVE_SCHEDULER_FORCE_PY=1` 强制选择实现，接口层暴露 `USING_NATIVE_CORE` 方便监控。

## API 快速上手

```python
from backend.infrastructure.native.native_scheduler import NativeScheduler
from backend.infrastructure.native.native_threadpool import NativeThreadPool

scheduler = NativeScheduler(executor_factory=NativeThreadPool)
scheduler.register_category("download", queue_capacity=1024, max_workers=4)

def fetch(symbol: str) -> str:
    # ... 请求数据 ...
    return symbol

future = scheduler.submit("download", fetch, ("rb2405",), {})
result = future.result(timeout=1.0)

stats = scheduler.stats()      # -> {"download": {"queue_size": 0, "max_workers": 4}}
scheduler.shutdown()
```

### 定时任务示例

```python
from datetime import datetime, timedelta
from backend.infrastructure.native.native_scheduler import NativeCronScheduler

cron = NativeCronScheduler(max_workers=2, queue_capacity=128)

cron.add_job(print, "interval", seconds=5, args=("heartbeat",), id="hb")
cron.add_job(print, "cron", hour=9, minute=30, second=0, args=("market-open",), id="market")
cron.add_job(print, "date", run_date=datetime.now() + timedelta(seconds=10), args=("once",))
```

## 编译

```powershell
cd backend/infrastructure/native/native_scheduler
python setup.py build_ext --inplace
```

推荐执行 `backend/infrastructure/native/compile_all.bat`，脚本第 23 步会自动构建 `native_scheduler`。

## 测试

- 单元测试：`python -m pytest backend/infrastructure/native/native_scheduler/tests/test_native_scheduler.py -v`
- 集成测试：`python -m pytest backend/infrastructure/native/tests/test_native_process_metrics.py -v`（验证与监控模块联动）

## 诊断与监控

- `SCHEDULER_AVAILABLE`：始终为 `True`，表示至少存在回退实现。
- `USING_NATIVE_CORE`：指示当前是否运行在原生扩展上，建议记录至统一日志。
- `NativeScheduler.stats()`：返回每个类别的队列长度与并发限制，可用于定时采样。
- **日志集成**：已集成 NativeLogBridge，支持任务提交、执行、调度失败的结构化日志记录。
  - C 层：类别注册失败、任务提交异常、线程池调度失败、任务执行错误等关键事件。
  - Python 层：使用 `@native_call_guard` 装饰器捕获包装层异常，统一接口层提供结构化日志。

---

**最后更新**：2025-11-08

