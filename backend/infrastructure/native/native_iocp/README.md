# -*- coding: utf-8 -*-
# Native IOCP扩展模块

## 概述

提供基于Windows IOCP（完成端口）的异步文件I/O和批量文件操作。

### 核心特性

- ✅ **异步文件I/O**：使用Windows IOCP API，不依赖线程池
- ✅ **批量文件操作**：批量文件存在检查、删除、统计信息
- ✅ **高性能目录遍历**：使用Windows FindFirstFile API

## 编译

```bash
cd backend/infrastructure/native/native_iocp
python setup.py build_ext --inplace
```

## API

### 异步文件I/O

```python
import asyncio
from backend.infrastructure.native.native_iocp import aopen

async def main():
    async with await aopen('file.txt', 'rb') as f:
        data = await f.read()
```

### 批量文件操作

```python
from backend.infrastructure.native.native_iocp import (
    batch_file_exists,
    batch_file_delete,
    batch_file_stat,
    fast_dir_walk,
    fast_dir_list,
)

# 批量检查文件是否存在
files = ['file1.txt', 'file2.txt']
exists = batch_file_exists(files)

# 批量删除文件
deleted_count = batch_file_delete(files)

# 批量获取文件统计信息
stats = batch_file_stat(files)

# 目录遍历
result = fast_dir_walk('C:\\path\\to\\dir')
dirs, files = result[0][1], result[0][2]

# 目录列表
items = fast_dir_list('C:\\path\\to\\dir')
```

## 注意事项

- 仅支持Windows平台
- 批量操作减少Python调用开销
- 目录遍历使用Windows FindFirstFile API

