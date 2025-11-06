# -*- coding: utf-8 -*-
# Native IPC扩展模块

## 概述

提供基于Windows IOCP（完成端口）+ Named Pipe的异步跨进程通信。

### 核心特性

- ✅ **异步IPC**：使用Windows Named Pipe + IOCP API，不依赖线程池
- ✅ **高性能**：无线程切换开销，适合高并发跨进程通信
- ✅ **完全对标**：与native_iocp的三层架构和API风格一致

## 编译

```bash
cd backend/infrastructure/native/native_ipc
python setup.py build_ext --inplace
```

## API

### 基础使用

```python
import asyncio
from backend.infrastructure.native.native_ipc import AsyncIPCPipe

# 服务端
async def server():
    async with AsyncIPCPipe.server("pipe_name") as pipe:
        data = await pipe.read()
        await pipe.write(b"response")

# 客户端
async def client():
    async with AsyncIPCPipe.client("pipe_name") as pipe:
        await pipe.write(b"request")
        response = await pipe.read()
```

### 简化API

```python
from backend.infrastructure.native.native_ipc import aopen_server, aopen_client

async def server():
    async with aopen_server("pipe_name") as pipe:
        data = await pipe.read()

async def client():
    async with aopen_client("pipe_name") as pipe:
        await pipe.write(b"data")
```

## 注意事项

- 仅支持Windows平台
- 单服务端对应单客户端连接
- 字节流模式（暂不支持消息模式）
