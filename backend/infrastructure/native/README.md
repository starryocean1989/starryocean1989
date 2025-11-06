# -*- coding: utf-8 -*-
# Native扩展包集合

## 概述

本目录包含一系列高性能C扩展包，用于解决Python在特定场景下的性能瓶颈。所有包均针对Windows平台优化，使用Windows原生API实现，提供比纯Python实现更优的性能。

## 包列表

### 1. native_gil - GIL管理和无锁数据结构

提供底层的GIL管理工具、无锁数据结构和高性能同步原语。

**核心功能**：
- GIL释放/恢复接口
- 无锁队列（LockFreeQueue）
- 无锁哈希表（LockFreeHashMap）
- 高性能事件/条件变量

**文档**：[native_gil/README.md](./native_gil/README.md)

---

### 2. native_memory - 内存操作

提供高性能内存操作功能，包括零拷贝内存视图、内存池和批量操作。

**核心功能**：
- 零拷贝内存操作（ZeroCopyMemory）
- 线程安全内存池（MemoryPool）
- 批量内存分配/释放

**文档**：[native_memory/README.md](./native_memory/README.md)

---

### 3. native_serialization - 序列化

提供高性能序列化功能，包括批量序列化/反序列化。

**核心功能**：
- 批量序列化/反序列化
- 零拷贝序列化
- 减少Python调用开销

**文档**：[native_serialization/README.md](./native_serialization/README.md)

---

### 4. native_iocp - 异步文件I/O

提供基于Windows IOCP（完成端口）的异步文件I/O和批量文件操作。

**核心功能**：
- 真正的异步文件I/O（不使用线程池）
- 批量文件操作（存在检查、删除、统计）
- 高性能目录遍历

**文档**：[native_iocp/README.md](./native_iocp/README.md)

---

### 5. native_ipc - 异步跨进程通信

提供基于Windows IOCP + Named Pipe的异步跨进程通信。

**核心功能**：
- 异步跨进程通信
- 基于Named Pipe + IOCP
- 完全对标native_iocp的架构

**文档**：[native_ipc/README.md](./native_ipc/README.md)

---

### 6. native_conversion - 类型转换

提供高性能类型转换和字符串操作功能。

**核心功能**：
- 批量类型转换（int、float、str、bytes等）
- 批量字符串编码/解码
- 减少Python调用开销

**文档**：[native_conversion/README.md](./native_conversion/README.md)

---

### 7. native_collections - 高性能容器

提供高性能数据结构，包括LRU缓存和优先级队列。

**核心功能**：
- 高性能LRU缓存（HighPerfLRUCache）
- 高性能优先级队列（HighPerfPriorityQueue）
- C实现的双向链表/链表

**文档**：[native_collections/README.md](./native_collections/README.md)

---

### 8. native_compute - 数值计算

提供高性能数值运算和哈希计算功能。

**核心功能**：
- 批量数值运算（add、multiply、square等）
- 批量哈希计算（md5、sha1、sha256等）
- 减少Python调用开销

**文档**：[native_compute/README.md](./native_compute/README.md)

---

## 编译要求

### 前置条件

- Windows平台
- Python 3.8+
- Visual Studio Build Tools（或完整Visual Studio）
- Windows SDK
- Python开发头文件（通常包含在Python安装中）

### 编译所有包

```bash
# 进入native目录
cd backend/infrastructure/native

# 编译所有包（需要在每个包目录下执行）
cd native_gil && python setup.py build_ext --inplace && cd ..
cd native_memory && python setup.py build_ext --inplace && cd ..
cd native_serialization && python setup.py build_ext --inplace && cd ..
cd native_iocp && python setup.py build_ext --inplace && cd ..
cd native_ipc && python setup.py build_ext --inplace && cd ..
cd native_conversion && python setup.py build_ext --inplace && cd ..
cd native_collections && python setup.py build_ext --inplace && cd ..
cd native_compute && python setup.py build_ext --inplace && cd ..
```

### 编译单个包

```bash
cd backend/infrastructure/native/<包名>
python setup.py build_ext --inplace
```

## 使用示例

### 统一导入

```python
from backend.infrastructure.native import (
    # GIL管理
    LockFreeQueue, LockFreeHashMap,
    HighPerfEvent, HighPerfCondition,

    # 内存操作
    ZeroCopyMemory, MemoryPool,
    batch_alloc, batch_free,

    # 序列化
    batch_serialize, batch_deserialize,

    # 文件操作
    aopen, batch_file_exists, fast_dir_walk,

    # IPC
    AsyncIPCPipe, aopen_server, aopen_client,

    # 类型转换
    batch_convert, batch_encode, batch_decode,

    # 容器
    HighPerfLRUCache, HighPerfPriorityQueue,

    # 计算
    batch_compute, batch_hash,
)
```

### 快速开始

```python
# 无锁队列
from backend.infrastructure.native.native_gil import LockFreeQueue
queue = LockFreeQueue(10)
queue.put(1)
item = queue.get()

# 零拷贝内存
from backend.infrastructure.native.native_memory import ZeroCopyMemory
data = bytearray(b"Hello, World!")
mem = ZeroCopyMemory(data)
view = mem.view()

# 批量序列化
from backend.infrastructure.native.native_serialization import batch_serialize
data = [1, 2, 3, {"key": "value"}]
serialized = batch_serialize(data)

# 异步文件I/O
import asyncio
from backend.infrastructure.native.native_iocp import aopen

async def main():
    async with await aopen('file.txt', 'rb') as f:
        data = await f.read()

asyncio.run(main())
```

## 性能优势

所有包都使用C扩展实现，相比纯Python实现具有以下优势：

- **无锁数据结构**：减少锁竞争，提高并发性能
- **批量操作**：减少Python调用开销
- **零拷贝操作**：减少内存拷贝开销
- **内存池**：减少频繁分配/释放开销
- **原生异步I/O**：不使用线程池，真正的异步I/O

## 测试

运行所有测试：

```bash
cd backend/infrastructure/native
python -m pytest tests/ -v
```

运行单个包测试：

```bash
python -m pytest backend/infrastructure/native/tests/test_native_gil.py -v
python -m pytest backend/infrastructure/native/tests/test_native_memory.py -v
```

## 注意事项

1. **平台限制**：所有包仅支持Windows平台
2. **编译要求**：需要编译C扩展才能使用
3. **Python版本**：需要Python 3.8+
4. **内存管理**：使用C扩展时需要注意内存管理，避免内存泄漏
5. **线程安全**：各包提供的数据结构和操作都是线程安全的

## 目录结构

```
native/
├── README.md                    # 本文件
├── __init__.py                  # 统一导入点
├── native_gil/                  # GIL管理和无锁数据结构
├── native_memory/              # 内存操作
├── native_serialization/        # 序列化
├── native_iocp/                 # 异步文件I/O
├── native_ipc/                  # 异步跨进程通信
├── native_conversion/           # 类型转换
├── native_collections/          # 高性能容器
├── native_compute/              # 数值计算
└── tests/                       # 测试套件
    ├── test_native_gil.py
    ├── test_native_memory.py
    ├── test_all.py
    └── benchmark.py
```

## 相关文档

- [native.md](../../../native.md) - 详细的性能问题分析和解决方案
- 各包的README.md - 各包的详细文档

## 许可证

MIT License

---

**最后更新**: 2025-11-06

