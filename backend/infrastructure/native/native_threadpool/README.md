# -*- coding: utf-8 -*-
# native_threadpool 模块

## 概述

`native_threadpool` 提供面向高频小任务的原生线程池，封装统一的 `NativeThreadPool` 与 `NativeFuture` 接口。模块优先加载 `_native_threadpool` C 扩展，若编译缺失则自动回退至 `ThreadPoolExecutor` 实现，确保在开发、CI、生产环境下均可无缝使用。

## 核心特性

- ✅ **轻量线程池**：原生实现使用固定工作线程 + 无锁任务队列，减少 GIL 竞争与上下文切换。
- ✅ **Future 兼容**：`NativeFuture` 对齐 `concurrent.futures.Future` 行为，支持 `result() / exception() / add_done_callback()`。
- ✅ **上下文管理器**：线程池支持 `with NativeThreadPool(...)` 语法，自动回收资源。
- ✅ **降级透明**：`THREADPOOL_AVAILABLE` 暴露原生扩展状态，回退层保持一致 API，保证测试可运行。

## API 快速上手

```python
from backend.infrastructure.native.native_threadpool import NativeThreadPool, THREADPOOL_AVAILABLE

with NativeThreadPool(max_workers=8) as pool:
    futures = [pool.submit(pow, i, 2) for i in range(10)]
    results = [f.result(timeout=1.0) for f in futures]

print(results)
print("native threadpool ready:", THREADPOOL_AVAILABLE)
```

- `submit(fn, *args, **kwargs)`：提交任务，返回 `NativeFuture`。
- `shutdown(wait=True)`：优雅关闭线程池；在 `with` 语法块结束时自动调用。

## 编译

```powershell
cd backend/infrastructure/native/native_threadpool
python setup.py build_ext --inplace
```

推荐执行 `backend/infrastructure/native/compile_all.bat`，脚本第 24 步将自动编译 `native_threadpool`。

## 测试

```powershell
python -m pytest backend/infrastructure/native/native_threadpool/tests/test_native_threadpool.py -v
```

该用例覆盖任务执行顺序、异常传播等关键路径。

## 诊断要点

- 使用 `THREADPOOL_AVAILABLE` 将原生可用性写入统一日志。
- 当任务执行异常时，可通过 `NativeFuture.exception()` 捕获原始错误，便于回传至上层监控。
- **日志集成**：已集成 NativeLogBridge，支持任务提交、执行、失败的结构化日志记录。
  - C 层：线程创建失败、任务执行异常、资源分配错误等关键事件。
  - Python 层：使用 `@native_call_guard` 装饰器捕获包装层异常，回退实现提供基础日志。

---

**最后更新**：2025-11-08

