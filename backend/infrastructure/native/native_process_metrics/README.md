# -*- coding: utf-8 -*-
# native_process_metrics 扩展

该扩展通过 Windows 原生 API 采集系统与进程指标，提供 `get_system_metrics()` 与 `get_process_snapshot()` 两个接口，减少 Python 层依赖 `psutil` 所造成的开销。

## 功能

- **get_system_metrics()**：返回 CPU、内存、磁盘占用、网络字节、进程数量等信息（单次调用即可获得）。
- **get_process_snapshot(pid)**：
  - `pid > 0` 时返回指定进程的 CPU 使用率、内存、句柄数、I/O 计数、可执行路径等。
  - `pid == 0` 时返回系统聚合信息（进程总数、线程总数占位字段）。

## 编译

```bash
cd backend/infrastructure/native/native_process_metrics
python setup.py build_ext --inplace
```

> 需要 Windows 平台、Visual Studio Build Tools、Windows SDK。
> 也可在 `backend/infrastructure/native` 目录执行 `compile_all.bat`，脚本会顺序构建全部扩展（含本模块），遇到错误自动暂停。

## Python API

```python
from native_process_metrics import (
    get_system_metrics,
    get_process_snapshot,
    PROCESS_METRICS_AVAILABLE,
)

if PROCESS_METRICS_AVAILABLE:
    print(get_system_metrics())
    print(get_process_snapshot(0))
```


