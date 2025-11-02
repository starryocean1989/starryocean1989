# -*- coding: utf-8 -*-
# IOCP (完成端口) 使用指南

## 什么是 IOCP？

IOCP (I/O Completion Port, 完成端口) 是 Windows 平台上的高性能异步 I/O 机制，通过线程池与异步 I/O 结合，能够高效处理大量并发连接。

## Python 中的 IOCP 使用

### 方法1: 使用 asyncio 的 ProactorEventLoop（推荐）

在 Windows 上，Python 的 `asyncio` 提供了 `ProactorEventLoop`，它基于 IOCP 实现。

#### 启用 ProactorEventLoop

```python
import asyncio
import platform

# Windows 平台自动使用 ProactorEventLoop（基于 IOCP）
if platform.system() == "Windows":
    # Python 3.8+ 默认使用 ProactorEventLoop
    # 如果需要显式设置：
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    print("✅ 已启用 ProactorEventLoop (基于 IOCP)")
```

#### 使用示例

```python
# -*- coding: utf-8 -*-
import asyncio
import platform

async def example_async_io():
    """异步 I/O 示例 - 自动使用 IOCP (Windows)"""
    # 网络 I/O
    reader, writer = await asyncio.open_connection('example.com', 80)
    writer.write(b'GET / HTTP/1.0\r\n\r\n')
    await writer.drain()
    data = await reader.read(100)
    writer.close()
    await writer.wait_closed()

    # 文件 I/O (需要使用 aiofiles)
    # import aiofiles
    # async with aiofiles.open('file.txt', 'r') as f:
    #     content = await f.read()

    return data

if __name__ == "__main__":
    if platform.system() == "Windows":
        # 确保使用 ProactorEventLoop
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    result = asyncio.run(example_async_io())
    print(f"收到数据: {result[:50]}...")
```

### 方法2: 使用 aiofiles（异步文件 I/O）

**重要说明**：`aiofiles` **并不直接使用 IOCP**，而是通过线程池执行同步文件操作。

```python
# -*- coding: utf-8 -*-
import asyncio
import aiofiles

async def read_file_async():
    """异步文件读取 - 使用线程池（非 IOCP）"""
    # aiofiles 内部使用 loop.run_in_executor() 在线程池中执行同步文件操作
    async with aiofiles.open('data.txt', 'r', encoding='utf-8') as f:
        content = await f.read()
    return content

async def write_file_async():
    """异步文件写入 - 使用线程池（非 IOCP）"""
    async with aiofiles.open('output.txt', 'w', encoding='utf-8') as f:
        await f.write('Hello, aiofiles!')

# 运行
asyncio.run(read_file_async())
```

**aiofiles 的实现机制**：
- 所有文件操作都通过 `loop.run_in_executor()` 在线程池中执行
- 即使是 Windows + ProactorEventLoop，文件 I/O 仍然使用线程池
- 优点：跨平台兼容，实现简单
- 缺点：需要线程开销，不是真正的异步 I/O

### 方法3: 使用 ctypes 直接调用 Windows API（高级）

如果需要更底层的控制，可以直接调用 Windows API：

```python
# -*- coding: utf-8 -*-
"""
使用 ctypes 直接调用 Windows IOCP API
注意：这是高级用法，一般不推荐，asyncio 已经封装得很好了
"""
import ctypes
from ctypes import wintypes

# Windows API 常量
INVALID_HANDLE_VALUE = -1
FILE_FLAG_OVERLAPPED = 0x40000000

# Windows API 函数
kernel32 = ctypes.windll.kernel32

# CreateIoCompletionPort
kernel32.CreateIoCompletionPort.argtypes = [
    wintypes.HANDLE,  # FileHandle
    wintypes.HANDLE,  # ExistingCompletionPort
    wintypes.ULONG,   # CompletionKey
    wintypes.DWORD    # NumberOfConcurrentThreads
]
kernel32.CreateIoCompletionPort.restype = wintypes.HANDLE

# GetQueuedCompletionStatus
kernel32.GetQueuedCompletionStatus.argtypes = [
    wintypes.HANDLE,      # CompletionPort
    wintypes.LPDWORD,     # lpNumberOfBytes
    wintypes.PULONG,      # lpCompletionKey
    ctypes.POINTER(wintypes.OVERLAPPED),  # lpOverlapped
    wintypes.DWORD        # dwMilliseconds
]
kernel32.GetQueuedCompletionStatus.restype = wintypes.BOOL

def create_iocp(num_threads=0):
    """
    创建 IOCP 完成端口

    Args:
        num_threads: 并发线程数，0 表示使用 CPU 核心数

    Returns:
        IOCP 句柄
    """
    h_iocp = kernel32.CreateIoCompletionPort(
        INVALID_HANDLE_VALUE,  # 创建新的完成端口
        None,                  # 无现有端口
        0,                     # CompletionKey
        num_threads            # 并发线程数
    )

    if h_iocp == INVALID_HANDLE_VALUE:
        raise OSError(f"创建 IOCP 失败: {ctypes.get_last_error()}")

    return h_iocp

# 示例：创建 IOCP
# h_iocp = create_iocp()
# 注意：实际使用需要配合异步文件/网络操作
```

## 项目中当前使用的情况

### 当前事件循环策略

项目中使用的是 `WindowsSelectorEventLoopPolicy`，这是因为：

1. **跨平台一致性**: SelectorEventLoop 在 Windows/Linux 上都可用
2. **native_ipc兼容性**: native_ipc（Windows Named Pipe + IOCP）可与SelectorEventLoop配合使用

```python:backend/infrastructure/system_vnpy/monitor_system.py
# Windows使用SelectorEventLoop策略（native_ipc已完全替换ZMQ）
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    logger.info("✅ 已设置Windows SelectorEventLoop策略")
```

### 何时使用 IOCP？

**使用 ProactorEventLoop (IOCP) 的场景**：
- ✅ 纯异步网络 I/O（如 `tdx_asyncio`）
- ✅ 异步文件 I/O（使用 `aiofiles`）
- ✅ 高性能文件处理
- ✅ 不需要 ZMQ 的场景（ZMQ已完全移除，项目已使用native_ipc）

**使用 SelectorEventLoop 的场景**：
- ✅ 需要跨平台一致性
- ✅ 需要跨平台一致性
- ✅ 使用某些旧版异步库

## 推荐方案

### 1. 对于纯异步网络 I/O（推荐）

```python
# -*- coding: utf-8 -*-
import asyncio
import platform

# ZMQ已完全移除，项目使用native_ipc（Windows Named Pipe + IOCP）
# 可以根据需要选择事件循环策略
if platform.system() == "Windows":
    # 项目目前使用SelectorEventLoop（跨平台一致性）
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # 如果需要更高性能，可以使用ProactorEventLoop（仅Windows）
    # asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
```

### 2. 使用 aiofiles 进行文件 I/O（使用线程池）

项目中已经在使用 `aiofiles`：

```python
# requirements.txt 中已有：
# aiofiles>=23.1.0  # 异步文件I/O，用于混合异步架构
```

使用时：

```python
import aiofiles

async def example():
    # aiofiles 使用线程池执行同步文件操作
    async with aiofiles.open('file.txt', 'r', encoding='utf-8') as f:
        content = await f.read()
```

**重要**：`aiofiles` 使用线程池，**不是真正的 IOCP 异步 I/O**。

## 关键问题：asyncio 文件 I/O 是否需要线程池？

### 答案：是的，必须使用线程池

**原因**：
1. **Python 标准库限制**：Python 的标准库 `open()`、`read()`、`write()` 等都是**同步阻塞**的
2. **asyncio 不支持文件 I/O**：即使使用 `ProactorEventLoop`（IOCP），asyncio 只对**网络 I/O** 使用 IOCP
3. **文件 I/O 仍需要线程池**：无论是 Windows 还是 Linux，文件 I/O 都需要通过 `run_in_executor()` 在线程池中执行

### ProactorEventLoop 的 IOCP 支持范围

```
✅ 网络 I/O（socket）：使用 IOCP
❌ 文件 I/O：不支持，仍需要线程池
```

### 示例对比

```python
import asyncio

# ✅ 网络 I/O：使用 IOCP（Windows ProactorEventLoop）
async def network_io():
    reader, writer = await asyncio.open_connection('example.com', 80)
    # 这里使用 IOCP，不需要线程池

# ❌ 文件 I/O：必须使用线程池
async def file_io_with_threadpool():
    loop = asyncio.get_event_loop()

    # 方式1：使用 run_in_executor
    def read_file():
        with open('file.txt', 'r') as f:
            return f.read()

    content = await loop.run_in_executor(None, read_file)

    # 方式2：使用 aiofiles（内部也是 run_in_executor）
    import aiofiles
    async with aiofiles.open('file.txt', 'r') as f:
        content = await f.read()  # 内部使用 run_in_executor
```

### 真正的 IOCP 文件 I/O（高级）

如果需要真正的 IOCP 文件 I/O，需要直接调用 Windows API：

```python
# 使用 Windows API + OVERLAPPED I/O
# 这需要 ctypes 调用 kernel32.dll 的函数
# 不推荐，因为实现复杂且需要手动管理完成端口
```

## 性能对比

| 方案 | Windows 性能 | 说明 |
|------|-------------|------|
| ProactorEventLoop + 网络 I/O | ⭐⭐⭐⭐⭐ | 基于 IOCP，性能最优 |
| ProactorEventLoop + 文件 I/O | ⭐⭐⭐ | 使用线程池，性能中等 |
| SelectorEventLoop | ⭐⭐⭐ | 基于 select，跨平台通用 |
| 同步 I/O | ⭐ | 性能最差 |

## 总结

1. **网络 I/O**：
   - Windows + ProactorEventLoop：✅ 使用 IOCP，无需线程池
   - Linux：使用 epoll/kqueue，无需线程池

2. **文件 I/O**：
   - **所有平台都必须使用线程池**（通过 `run_in_executor` 或 `aiofiles`）
   - 即使是 Windows + ProactorEventLoop，文件 I/O 仍然需要线程池
   - **无法实现真正的异步文件 I/O**（除非直接调用系统 API）

3. **推荐做法**：
   - 网络 I/O：使用 `asyncio.open_connection()`（自动使用 IOCP/epoll）
   - 文件 I/O：使用 `aiofiles` 或 `run_in_executor()`（使用线程池）
   - 需要跨平台一致性：使用 SelectorEventLoop

4. **项目现状**：
   - 使用 SelectorEventLoop（跨平台一致性，native_ipc已完全替换ZMQ）
   - 文件 I/O 通过 `aiofiles` 使用线程池
   - 网络 I/O 使用 asyncio（不依赖事件循环类型）

## 相关库

- **asyncio**: Python 标准库，支持 IOCP（通过 ProactorEventLoop，仅网络 I/O）
- **aiofiles**: 异步文件 I/O，使用线程池（不是 IOCP）
- **aiohttp**: 异步 HTTP 客户端/服务器，自动使用最佳事件循环（网络 I/O）
- **native_ipc**: Windows Named Pipe + IOCP，已完全替换ZMQ，可与SelectorEventLoop配合使用

## 关键结论

**回答你的问题**：是的，asyncio 在本地磁盘 I/O 中**必须使用线程池**，否则无法实现多协程异步。

**原因**：
1. Python 标准库的文件操作（`open()`、`read()`、`write()`）都是同步阻塞的
2. asyncio 只对网络 I/O（socket）提供真正的异步支持（Windows 使用 IOCP，Linux 使用 epoll）
3. 文件 I/O **无论什么平台、什么事件循环，都必须使用线程池**
4. `aiofiles` 库的实现就是在后台使用 `run_in_executor()` 执行同步文件操作

**无法绕过线程池的情况**：
- ❌ 无法通过 ProactorEventLoop（IOCP）实现真正的异步文件 I/O
- ❌ 无法通过 SelectorEventLoop 实现真正的异步文件 I/O
- ✅ 只能通过线程池 + 同步文件操作来"模拟"异步文件 I/O

## 参考资料

- [Python asyncio 文档](https://docs.python.org/3/library/asyncio-eventloop.html)
- [Windows ProactorEventLoop](https://docs.python.org/3/library/asyncio-eventloop.html#windows)
- [IOCP 官方文档](https://docs.microsoft.com/en-us/windows/win32/fileio/i-o-completion-ports)

