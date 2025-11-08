# -*- coding: utf-8 -*-
# native_netprobe 扩展

基于 Winsock + IOCP 的原生网络探测扩展，提供高并发的连接探测能力。

## 功能特性

- `test_connection(host, port, timeout=3.0)`：尝试在超时时间内建立 TCP 连接，返回毫秒级 RTT 与状态信息（success/timeout/error）。
- `batch_test_connections(servers, timeout=3.0, max_concurrent=32)`：
  - 使用 IOCP 并发发起探测，可配置最大并发数。
  - 返回结果列表、成功/超时/错误统计以及任务总耗时。
  - 失败时包含 WinSock 错误码，便于上层路由告警。
- 默认在模块初始化时调用 `WSAStartup`，无需在 Python 层重复初始化。

## 编译

```bash
cd backend/infrastructure/native/native_netprobe
python setup.py build_ext --inplace
```

> 需要 Windows 平台、Visual Studio Build Tools、Windows SDK。
> 也可在 `backend/infrastructure/native` 目录执行 `compile_all.bat`，脚本会顺序构建全部扩展（含本模块），遇到错误自动暂停。

## Python API

```python
from native_netprobe import NETPROBE_AVAILABLE, batch_test_connections

if NETPROBE_AVAILABLE:
    servers = [("1.1.1.1", 53), ("www.baidu.com", 443)]
    summary = batch_test_connections(servers, timeout=1.0, max_concurrent=16)
    print(summary["results"])
```


