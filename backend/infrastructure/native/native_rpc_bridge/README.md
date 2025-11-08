# -*- coding: utf-8 -*-
# native_rpc_bridge 扩展

多语言 RPC 桥接模块，负责在 C 扩展层封装共享内存队列、事件同步与序列化，加速 Python 与子进程（或外部语言）之间的通信。

## 功能概述

- `RpcBridge`：封装请求/响应双向通道，支持同步与异步调用。
- `publish(event, payload)`：向共享缓冲区写入事件并唤醒目标进程。
- `await_response(timeout_ms)`：阻塞等待对端返回结果，支持超时控制。
- Python 层若检测到扩展缺失，会回退到纯 Python IPC 实现。

## 编译

```bash
cd backend/infrastructure/native/native_rpc_bridge
python setup.py build_ext --inplace
```

> 推荐运行 `backend/infrastructure/native/compile_all.bat`，脚本会自动编译全部扩展（含本模块），并在遇到错误时暂停输出日志。

## 示例

```python
from native_rpc_bridge import RpcBridge

bridge = RpcBridge(buffer_size=65536)
bridge.publish("load-config", {"service": "strategy"})
reply = bridge.await_response(timeout_ms=500)
```

## 测试

目前尚未纳入公共 `pytest` 套件，可通过集成环境的跨进程调用脚本手动验证请求/响应往返延迟。

## 依赖

- Windows 平台、Python 3.8+。
- Visual Studio Build Tools、Windows SDK。
- numpy / struct（作为示例中 payload 序列化依赖）。


