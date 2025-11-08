# -*- coding: utf-8 -*-
# Native GIL扩展模块

## 概述

提供底层的GIL管理工具、无锁数据结构和高性能同步原语。

### 核心特性

- ✅ **GIL管理**：释放/恢复GIL接口
- ✅ **无锁数据结构**：LockFreeQueue、LockFreeHashMap
- ✅ **高性能同步**：HighPerfEvent、HighPerfCondition
- ✅ **线程安全数据结构**：ThreadSafeQueue、ThreadSafeCounter

## 编译

```bash
cd backend/infrastructure/native/native_gil
python setup.py build_ext --inplace
```

> 亦可在 `backend/infrastructure/native` 目录执行 `compile_all.bat`，脚本会顺序编译全部扩展（含本模块），遇到错误自动暂停便于排查。

## API

### 无锁数据结构

```python
from backend.infrastructure.native.native_gil import LockFreeQueue, LockFreeHashMap

# 无锁队列
queue = LockFreeQueue(10)
queue.put(1)
item = queue.get()

# 无锁哈希表
hmap = LockFreeHashMap(10)
hmap.set("key", "value")
value = hmap.get("key")
```

### 高性能同步原语

```python
from backend.infrastructure.native.native_gil import HighPerfEvent, HighPerfCondition

# 高性能事件
event = HighPerfEvent()
event.set()
event.wait()

# 高性能条件变量
cond = HighPerfCondition()
cond.notify()
cond.notify_all()
```

### GIL管理

```python
from backend.infrastructure.native.native_gil import release_gil, restore_gil

tstate = release_gil()
# 执行CPU密集型任务
restore_gil(tstate)
```

## 注意事项

- 仅支持Windows平台
- 无锁数据结构适用于高并发场景
- 使用内存屏障确保内存可见性
