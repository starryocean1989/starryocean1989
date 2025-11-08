# -*- coding: utf-8 -*-
# Native Memory扩展模块

## 概述

提供高性能内存操作功能，包括零拷贝内存视图、内存池和批量操作。

### 核心特性

- ✅ **零拷贝内存操作**：使用Py_buffer实现零拷贝视图
- ✅ **内存池**：预分配内存池，减少分配/释放开销
- ✅ **批量操作**：批量内存分配/释放

## 编译

```bash
cd backend/infrastructure/native/native_memory
python setup.py build_ext --inplace
```

> 建议通过 `backend/infrastructure/native/compile_all.bat` 一键构建，脚本会按顺序编译全部扩展（含本模块），并在失败时暂停以便排查。

## API

### 零拷贝内存

```python
from backend.infrastructure.native.native_memory import ZeroCopyMemory

# 使用bytearray（可写缓冲区）
data = bytearray(b"Hello, World!")
mem = ZeroCopyMemory(data)
view = mem.view()  # 零拷贝视图
size = mem.get_size()
copy_data = mem.copy()
```

### 内存池

```python
from backend.infrastructure.native.native_memory import MemoryPool

pool = MemoryPool(1024, 10)  # size, count
obj = pool.alloc()
pool.free(obj)
size = pool.size()
capacity = pool.capacity()
```

### 批量操作

```python
from backend.infrastructure.native.native_memory import batch_alloc, batch_free

objects = batch_alloc(10, 1024)  # count, size
batch_free(objects)
```

## 注意事项

- 仅支持Windows平台
- ZeroCopyMemory需要使用可写缓冲区（如bytearray）
- 内存池使用Windows临界区保证线程安全
