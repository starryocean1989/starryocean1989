# -*- coding: utf-8 -*-
# native_queue 模块

## 概述

`native_queue` 提供基于 C 扩展实现的高性能队列，面向网关撮合、日志汇聚等需要高频入队/出队的场景。模块在导入时优先加载 `_native_queue` 扩展，若编译缺失则自动回退至线程安全的 Python 版本，保持 API 一致性，便于在 CI 或开发机上快速验证。

## 核心特性

- ✅ **动态扩容环形缓冲**：默认容量 1024，满载时按倍数扩容，避免频繁分配。
- ✅ **线程安全**：内部使用原生自旋锁，`push`/`pop`/`clear` 等操作均可在多线程场景下安全调用。
- ✅ **零 GC 压力**：队列槽位持有 PyObject* 引用，出队即释放，保持稳定延迟。
- ✅ **降级透明**：`QUEUE_AVAILABLE` 标志可检测原生实现是否可用；回退实现基于 `collections.deque` + `threading.Lock`。

## API 快速上手

```python
from backend.infrastructure.native.native_queue import NativeQueue, QUEUE_AVAILABLE

queue = NativeQueue(capacity=4096)
queue.push({"symbol": "rb2405", "price": 3800})
queue.push({"symbol": "rb2405", "price": 3810})

item = queue.pop()            # -> dict
length = queue.size()         # -> 当前元素个数
queue.clear()                 # 清空队列

print("native queue ready:", QUEUE_AVAILABLE)
```

- `push(item)`：入队任意 Python 对象，返回 `None`。
- `pop()`：出队一个元素；队列为空时返回 `None`。
- `size()` / `__len__()`：返回当前元素数量。
- `clear()`：清空并复位读写指针。

## 编译

```powershell
cd backend/infrastructure/native/native_queue
python setup.py build_ext --inplace
```

推荐通过 `backend/infrastructure/native/compile_all.bat` 统一构建，该脚本会在第 13 步自动编译 `native_queue`。

## 测试

单模块测试：

```powershell
python -m pytest backend/infrastructure/native/native_queue/tests/test_native_queue.py -v
```

集成测试（包含其他原生模块）：

```powershell
python -m pytest backend/infrastructure/native/tests/test_native_collections.py -v
python -m pytest tests/test_native_async_reduce.py -v  # 验证跨模块使用
```

## 监控与诊断

- 通过 `QUEUE_AVAILABLE` 判断原生扩展是否可用，记录到统一日志。
- 队列对象实现了 `__repr__`，在日志或调试输出时可直接查看当前 `size` 和 `capacity`。
- **日志集成**：已集成 NativeLogBridge，支持队列扩容、操作异常的结构化日志记录。
  - C 层：缓冲区扩容失败等关键事件。
  - Python 层：使用 `@native_call_guard` 装饰器捕获包装层异常，回退实现提供基础日志。

---

**最后更新**：2025-11-08

