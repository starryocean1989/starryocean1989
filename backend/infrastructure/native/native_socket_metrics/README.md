# -*- coding: utf-8 -*-
# native_socket_metrics 扩展

面向 Windows 的网络指标采集扩展，封装 `GetExtendedTcpTable` 等 API，提供轻量级 Socket/带宽统计；扩展缺失时自动回退 `psutil`。

## 功能概述

- `get_socket_metrics()`：返回当前活跃连接数、监听端口以及收发字节累计值。
- `SOCKET_METRICS_AVAILABLE`：指示扩展是否可用，便于调用方降级。
- 内部缓存了上次采样结果，可实现环比统计。

## 编译

```bash
cd backend/infrastructure/native/native_socket_metrics
python setup.py build_ext --inplace
```

> 建议通过 `backend/infrastructure/native/compile_all.bat` 一键构建，脚本会顺序编译全部扩展（含本模块），并在失败时暂停打印日志。

## 测试

```bash
pytest backend/infrastructure/native/native_socket_metrics/tests/test_socket_metrics.py -v
```

## 依赖

- Windows 平台、Python 3.8+。
- Visual Studio Build Tools、Windows SDK。
- 可选：psutil（作为降级方案的数据来源）。


