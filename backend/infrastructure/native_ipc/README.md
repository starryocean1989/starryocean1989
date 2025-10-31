# 原生IOCP异步IPC

## 概述

本模块提供基于Windows IOCP（完成端口）+ Named Pipe的真正的异步跨进程通信，**不使用线程池**。

### 核心特性

- ✅ **真正的异步IPC**：直接使用Windows Named Pipe + IOCP API，不依赖线程池
- ✅ **高性能**：无线程切换开销，适合高并发跨进程通信场景
- ✅ **架构对标**：完全对标 `native_iocp` 的三层架构和API风格
- ✅ **基础能力导向**：仅提供底层通信原语，不实现高级模式（REQ/REP、PUB/SUB等由上层实现）

## 编译

### 前置要求

- Windows平台
- Python 3.8+
- Visual Studio Build Tools（或完整Visual Studio）
- Windows SDK
- Python开发头文件（通常包含在Python安装中）

### 编译步骤

1. 进入模块目录：
```bash
cd backend/infrastructure/native_ipc
```

2. 编译C扩展：
```bash
python setup.py build_ext --inplace
```

3. 验证编译：
```bash
python -c "import ipc_async; print('IPC extension loaded successfully')"
```

### 编译错误排查

如果编译失败，请检查：
1. Visual Studio Build Tools是否已安装
2. Windows SDK是否已安装
3. Python开发头文件是否可用（通常在Python安装目录的`include`文件夹）
4. 环境变量`INCLUDE`和`LIB`是否正确设置

## 使用

### 基础使用示例

#### 服务端示例

```python
import asyncio
from backend.infrastructure.native_ipc import AsyncIPCPipe

async def server():
    # 创建服务端管道
    async with AsyncIPCPipe.server("monitor_service") as pipe:
        print("服务端：等待客户端请求...")
        request = await pipe.read()
        print(f"服务端：收到请求 {request}")
        
        response = b"response_data"
        await pipe.write(response)
        print("服务端：已发送响应")

asyncio.run(server())
```

#### 客户端示例

```python
import asyncio
from backend.infrastructure.native_ipc import AsyncIPCPipe

async def client():
    # 连接到服务端管道
    async with AsyncIPCPipe.client("monitor_service") as pipe:
        request = b"request_data"
        await pipe.write(request)
        print("客户端：已发送请求")
        
        response = await pipe.read()
        print(f"客户端：收到响应 {response}")

asyncio.run(client())
```

### 使用简化API

```python
import asyncio
from backend.infrastructure.native_ipc import aopen_server, aopen_client

async def server():
    async with aopen_server("monitor_service") as pipe:
        data = await pipe.read()
        await pipe.write(b"ACK")

async def client():
    async with aopen_client("monitor_service") as pipe:
        await pipe.write(b"request")
        response = await pipe.read()
```

### 并发通信示例

#### 服务端处理多个客户端

```python
async def handle_client(pipe_name: str):
    async with AsyncIPCPipe.server(pipe_name) as pipe:
        request = await pipe.read()
        print(f"处理请求: {request}")
        await pipe.write(b"ACK")

async def server_multi():
    tasks = []
    for i in range(10):
        pipe_name = f"monitor_service_{i}"
        task = asyncio.create_task(handle_client(pipe_name))
        tasks.append(task)
    
    await asyncio.gather(*tasks)

asyncio.run(server_multi())
```

#### 客户端并发发送

```python
async def send_request(pipe_name: str, data: bytes):
    async with AsyncIPCPipe.client(pipe_name) as pipe:
        await pipe.write(data)
        response = await pipe.read()
        return response

async def client_multi():
    tasks = []
    for i in range(10):
        pipe_name = f"monitor_service_{i}"
        task = asyncio.create_task(send_request(pipe_name, f"data_{i}".encode()))
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    print(f"收到 {len(results)} 个响应")

asyncio.run(client_multi())
```

### 检查可用性

```python
from backend.infrastructure.native_ipc import IPC_AVAILABLE

if IPC_AVAILABLE:
    print("IPC可用")
else:
    print("IPC不可用，请编译C扩展")
```

## 架构

### 组件层次（对标native_iocp）

```
Python API层 (async_ipc.py)
    ↓ AsyncIPCPipe类
事件循环集成 (ipc_loop.py)
    ↓ IPCEventLoopExtension
C扩展层 (ipc_async.c)
    ↓ IPCAsyncPipe对象
Windows API层
    ↓ Named Pipe + IOCP
```

### 工作流程

1. **创建管道**：
   - 服务端：使用`CreateNamedPipe` with `FILE_FLAG_OVERLAPPED`
   - 客户端：使用`CreateFile` 打开管道
2. **创建IOCP**：使用`CreateIoCompletionPort`
3. **关联管道**：将管道句柄关联到IOCP
4. **异步操作**：使用`ReadFile`/`WriteFile` with `OVERLAPPED`
5. **等待完成**：通过事件对象和`GetOverlappedResult`获取完成通知
6. **唤醒协程**：完成时通过asyncio事件循环唤醒Future

## 性能对比

### vs 传统线程池方案

| 特性 | native_ipc (IOCP) | 传统线程池 |
|------|-------------------|------------|
| **线程开销** | 无 | 有（线程池） |
| **内存占用** | 低 | 较高（线程栈） |
| **延迟** | 低 | 中等 |
| **并发能力** | 高 | 中等 |
| **跨平台** | 仅Windows | 全平台 |

### vs native_iocp

| 维度 | native_iocp | native_ipc |
|------|-------------|------------|
| **应用场景** | 异步文件I/O | 跨进程通信 |
| **底层机制** | 文件句柄 + IOCP | 命名管道 + IOCP |
| **API风格** | AsyncIOCPFile | AsyncIPCPipe |
| **核心方法** | read/write | read/write |
| **性能特性** | 相同（都使用IOCP） | 相同（都使用IOCP） |

## 注意事项

⚠️ **使用建议**：

- 本模块仅提供底层通信原语，适合作为高级通信模式的基础
- 仅支持点对点双向通信，单个服务端管道对应单个客户端连接
- 上层可以基于此实现REQ/REP、PUB/SUB等高级模式
- Windows平台专属，暂不支持跨平台

⚠️ **当前实现状态**：

1. **C扩展已实现**：基本的IOCP IPC功能
2. **asyncio集成**：使用优化轮询机制（1ms间隔）
3. **完成通知机制**：通过Windows事件对象和asyncio集成

## 故障排查

### 导入错误

```
ImportError: cannot import name 'ipc_async'
```

**解决方案**：需要编译C扩展：
```bash
cd backend/infrastructure/native_ipc
python setup.py build_ext --inplace
```

### 编译错误

**错误**：`无法打开包含文件: "Python.h"`

**解决方案**：安装Python开发头文件，或设置正确的`INCLUDE`路径。

### 运行时错误

**错误**：`Pipe not opened`

**解决方案**：确保在使用`read`/`write`前调用`server()`或`client()`工厂方法，或使用`async with`。

**错误**：`Pipe not connected`

**解决方案**：
- 服务端：确保客户端已连接（`ConnectNamedPipe`完成）
- 客户端：确保服务端管道已创建

## API参考

### AsyncIPCPipe类

#### 工厂方法

- `AsyncIPCPipe.server(pipe_name: str) -> AsyncIPCPipe`
  - 创建服务端管道

- `AsyncIPCPipe.client(pipe_name: str) -> AsyncIPCPipe`
  - 连接到服务端管道

#### 实例方法

- `async read(size: int = 4096) -> bytes`
  - 异步读取数据

- `async write(data: bytes) -> int`
  - 异步写入数据

- `async close() -> None`
  - 关闭管道

#### 上下文管理器

支持`async with`语法，自动管理资源。

### 简化API

- `aopen_server(pipe_name: str) -> AsyncIPCPipe`
  - 创建服务端管道（简化API）

- `aopen_client(pipe_name: str) -> AsyncIPCPipe`
  - 连接到服务端管道（简化API）

## 未来改进

### 功能扩展

- [ ] 多客户端连接支持（单服务端支持多个客户端）
- [ ] 消息边界支持（`PIPE_TYPE_MESSAGE`模式）
- [ ] 连接超时和自动重连
- [ ] 安全性增强（ACL权限控制）
- [ ] 数据加密传输

### 上层模式实现

基于 `native_ipc` 底层能力，可以在上层实现：

- REQ/REP模式（请求-响应）
- PUB/SUB模式（发布-订阅）
- ROUTER/DEALER模式（路由）
- RPC框架
- 消息队列
- 事件总线

### 跨平台支持

- [ ] Linux支持（Unix Domain Socket + io_uring）
- [ ] macOS支持（Unix Domain Socket + kqueue）

## 参考资料

- [Windows Named Pipe文档](https://docs.microsoft.com/en-us/windows/win32/ipc/named-pipes)
- [Windows IOCP文档](https://docs.microsoft.com/en-us/windows/win32/fileio/i-o-completion-ports)
- [Python asyncio文档](https://docs.python.org/3/library/asyncio.html)
- [Python C扩展开发](https://docs.python.org/3/extending/extending.html)

## 许可证

MIT License
