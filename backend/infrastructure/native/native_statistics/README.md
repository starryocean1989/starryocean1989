# -*- coding: utf-8 -*-
# native_statistics 模块

## 概述

`native_statistics` 提供滑动窗口增量统计的 C 扩展实现，围绕监控数据场景定制，具备如下特性：

- 无锁环形缓冲区：支持高频写入的常数时间更新。
- 增量统计：实时维护样本数、均值、方差及分位估计。
- 快照接口：一次性复制窗口数据，使用快速选择算法获取分位数。
- Python 回退：Native 扩展不可用时同名 Python 实现自动接管。

## 编译

```bash
cd backend/infrastructure/native/native_statistics
python setup.py build_ext --inplace
```

推荐使用 `backend/infrastructure/native/compile_all.bat` 一键编译所有扩展，本模块在序号 `[7/22]`。

## 主要 API

```python
from backend.infrastructure.native.native_statistics import (
    STATISTICS_AVAILABLE,
    create_streaming_metric,
    StreamingMetricHandle,
)

handle = create_streaming_metric(window_size=1440)
handle.update(1.5)
handle.extend([2.0, 3.0])
stats = handle.snapshot()
```

### StreamingMetricHandle

- `update(value: float)`：写入单个样本。
- `extend(values: Iterable[float])`：批量写入样本。
- `reset()`：清空窗口。
- `snapshot()`：返回包含 `sample_count`、`mean`、`stddev`、`p95`、`p99` 的统计字典。
- `window_size` 属性：当前窗口大小。

## Python 回退

当原生模块导入失败时，`STATISTICS_AVAILABLE` 为 `False`，模块会暴露纯 Python 版本的 `StreamingMetricHandle`，保持接口一致，使上层逻辑无感知。

## 日志与降级

上层在 `AdaptiveThresholdManager.register_metric` 内检测 `STATISTICS_AVAILABLE`，优先创建原生句柄：

- 创建成功：以 DEBUG 级别记录“创建原生统计句柄”。
- 创建失败或更新/快照异常：输出异常日志并移除句柄，自动回退到 Python deque。
- 回退路径：持续使用既有 NumPy 计算，并保持 WARNING/INFO/DEBUG 日志与原实现一致。
- 降级恢复：一旦 Python 路径被触发，直到进程重新注册指标为止都会保留回退状态。

## 注意事项

- 仅支持 Windows 平台。
- 默认窗口大小 1440，可在创建句柄时指定。
- 分位数计算使用快速选择算法（Quickselect）。
- 原生实现使用轻量级自旋锁避免 GIL 抢占，确保高频更新安全。
