# -*- coding: utf-8 -*-
# Native 扩展包集合

## 概述

本目录汇总了 21 个 Windows 优化的 C/C++ 扩展包，覆盖无锁容器、异步 IO、数据转换、指标采集等关键路径；所有模块均可通过 `compile_all.bat` 一键重建，并在失败时回退到纯 Python 方案，确保业务不中断。

## 模块一览

| 序号 | 模块 | 核心能力 | 文档 |
| --- | --- | --- | --- |
| 1 | `native_gil` | GIL 管理、无锁队列/哈希、同步原语 | [native_gil/README.md](./native_gil/README.md) |
| 2 | `native_memory` | 零拷贝内存、线程安全内存池 | [native_memory/README.md](./native_memory/README.md) |
| 3 | `native_serialization` | 批量序列化与零拷贝反序列化 | [native_serialization/README.md](./native_serialization/README.md) |
| 4 | `native_conversion` | 基础类型批量转换、字符串编解码 | [native_conversion/README.md](./native_conversion/README.md) |
| 5 | `native_vnpy_conversion` | VnPy Tick/Bar/订单批量转换 | [native_vnpy_conversion/README.md](./native_vnpy_conversion/README.md) |
| 6 | `native_compute` | 批量数值/哈希运算 | [native_compute/README.md](./native_compute/README.md) |
| 7 | `native_dataframe_ops` | DataFrame/数组批量算子 | [native_dataframe_ops/README.md](./native_dataframe_ops/README.md) |
| 8 | `native_finance_ops` | 量化指标、金融统计批处理 | [native_finance_ops/README.md](./native_finance_ops/README.md) |
| 9 | `native_collections` | LRU、优先队列、链表 | [native_collections/README.md](./native_collections/README.md) |
| 10 | `native_iocp` | IOCP 文件异步读写/目录遍历 | [native_iocp/README.md](./native_iocp/README.md) |
| 11 | `native_fs` | 目录变更原生监控（ReadDirectoryChangesW） | [native_fs/README.md](./native_fs/README.md) |
| 12 | `native_ipc` | IOCP + Named Pipe 异步 IPC | [native_ipc/README.md](./native_ipc/README.md) |
| 13 | `native_netprobe` | IOCP ConnectEx 网络探测 | [native_netprobe/README.md](./native_netprobe/README.md) |
| 14 | `native_socket_metrics` | TCP 连接、带宽利用率采集 | [native_socket_metrics/README.md](./native_socket_metrics/README.md) |
| 15 | `native_process_metrics` | 系统/进程 CPU、内存、IO 统计 | [native_process_metrics/README.md](./native_process_metrics/README.md) |
| 16 | `native_smart_monitor` | SMART 温度/健康采集 | [native_smart_monitor/README.md](./native_smart_monitor/README.md) |
| 17 | `native_log_pipeline` | 日志批量缓冲、SQLite 落盘 | [native_log_pipeline/README.md](./native_log_pipeline/README.md) |
| 18 | `native_async` | 异步任务归约、进度切片 | [native_async/README.md](./native_async/README.md) |
| 19 | `native_symbol_index` | LockFree 品种索引、查询加速 | [native_symbol_index/README.md](./native_symbol_index/README.md) |
| 20 | `native_indicator` | 技术指标计算（MACD/RSI 等） | [native_indicator/README.md](./native_indicator/README.md) |
| 21 | `native_rpc_bridge` | 多语言 RPC 桥接、数据通道 | [native_rpc_bridge/README.md](./native_rpc_bridge/README.md) |

> UI 侧的 `native_qhighlighter` 位于 `ui/native_extensions`，由脚本末尾额外构建。

## 统一特性

- **Windows 原生 API**：利用 IOCP、PDH、Named Pipe、QueryPerformanceCounter 等系统能力。
- **锁粒度最小化**：核心路径使用 `LockFreeHashMap` / `LockFreeQueue`，跨进程通信配合环形缓冲。
- **降级机制**：模块通过 `*_AVAILABLE` 常量告知状态；不可用时自动回退 Python 实现。
- **测试矩阵**：`backend/infrastructure/native/tests` 覆盖核心模块的单元/集成/性能基准（部分扩展待补充专用用例）。
- **一键构建**：`compile_all.bat` 顺序编译 20 个扩展（含 UI 高亮），遇到错误立即中止并打印日志。

## 编译要求

### 前置条件

- Windows平台
- Python 3.8+
- Visual Studio Build Tools（或完整Visual Studio）
- Windows SDK
- Python开发头文件（通常包含在Python安装中）

### 编译所有包

```bash
# 进入 native 目录
cd backend/infrastructure/native

# 一键编译（推荐，遇错即停）
compile_all.bat
```

脚本共 22 步：前 21 步依次构建当前目录内全部扩展，第 22 步进入 `ui/native_extensions/native_qhighlighter` 完成 UI 原生高亮编译。若任一步失败，脚本会打印错误并暂停，便于定位。

### 编译单个包

```bash
cd backend/infrastructure/native/<包名>
python setup.py build_ext --inplace
```

如需额外依赖（例如 `pybind11`），请提前安装：

```bash
python -m pip install pybind11
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
├── native_fs/                   # 目录变更监控
├── native_ipc/                  # 异步跨进程通信
├── native_conversion/           # 类型转换
├── native_collections/          # 高性能容器
├── native_compute/              # 数值计算
├── native_dataframe_ops/        # DataFrame 批量算子
├── native_finance_ops/          # 金融指标批处理
├── native_process_metrics/      # 进程/系统指标
├── native_socket_metrics/       # Socket 指标（网络）
├── native_netprobe/             # 网络探测
├── native_log_pipeline/         # 日志批处理
├── native_async/                # 异步任务归约
├── native_symbol_index/         # 品种索引构建
├── native_indicator/            # 技术指标计算
├── native_rpc_bridge/           # RPC 桥接
├── native_vnpy_conversion/      # VnPy 数据转换
└── tests/                       # 测试套件
    ├── test_native_indicator.py
    ├── test_native_log_pipeline.py
    ├── test_native_netprobe.py
    ├── test_native_process_metrics.py
    └── test_native_vnpy_conversion.py
```

## 相关文档

- [native.md](../../../native.md) - 详细的性能问题分析和解决方案
- 各包的README.md - 各包的详细文档

## 许可证

MIT License

---

**最后更新**: 2025-11-08

