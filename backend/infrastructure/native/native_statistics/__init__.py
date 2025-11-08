# -*- coding: utf-8 -*-
"""Streaming statistics native extension facade with Python fallback."""

from __future__ import annotations

import math
from bisect import bisect_left
from typing import Dict, Iterable, List, Optional

__all__ = [
    "STATISTICS_AVAILABLE",
    "StreamingMetricHandle",
    "create_streaming_metric",
]

try:  # pragma: no cover - native 导入失败时自动回退
    from .native_statistics import (  # type: ignore[F401]
        STATISTICS_AVAILABLE,
        StreamingMetricHandle as _NativeStreamingMetricHandle,
    )
except Exception:  # pragma: no cover
    STATISTICS_AVAILABLE = False

    class StreamingMetricHandle:
        """纯 Python 版本的滑动窗口统计实现."""

        def __init__(self, window_size: int = 1440) -> None:
            if window_size <= 0:
                raise ValueError("window_size must be positive")
            self._window_size = int(window_size)
            self._values: List[float] = []
            self._sorted: List[float] = []
            self._sum: float = 0.0
            self._sumsq: float = 0.0

        @property
        def window_size(self) -> int:
            return self._window_size

        def __len__(self) -> int:
            return len(self._values)

        def update(self, value: float) -> None:
            value = float(value)
            if len(self._values) == self._window_size:
                removed = self._values.pop(0)
                self._sum -= removed
                self._sumsq -= removed * removed
                idx = bisect_left(self._sorted, removed)
                if 0 <= idx < len(self._sorted):
                    # 容忍浮点误差，向附近查找
                    tolerance = max(1e-9, abs(removed) * 1e-9)
                    lo = idx
                    hi = idx
                    while lo > 0 and abs(self._sorted[lo - 1] - removed) <= tolerance:
                        lo -= 1
                    while hi + 1 < len(self._sorted) and abs(self._sorted[hi + 1] - removed) <= tolerance:
                        hi += 1
                    target = None
                    for pos in range(lo, hi + 1):
                        if abs(self._sorted[pos] - removed) <= tolerance:
                            target = pos
                            break
                    if target is None:
                        target = min(idx, len(self._sorted) - 1)
                    self._sorted.pop(target)
                else:
                    raise ValueError("failed to remove value from sorted buffer")
            self._values.append(value)
            insert_pos = bisect_left(self._sorted, value)
            self._sorted.insert(insert_pos, value)
            self._sum += value
            self._sumsq += value * value

        def extend(self, values: Iterable[float]) -> None:
            for item in values:
                self.update(float(item))

        def reset(self) -> None:
            self._values.clear()
            self._sorted.clear()
            self._sum = 0.0
            self._sumsq = 0.0

        def snapshot(self) -> Dict[str, Optional[float]]:
            count = len(self._values)
            if count == 0:
                return {
                    "sample_count": 0,
                    "mean": None,
                    "stddev": None,
                    "p95": None,
                    "p99": None,
                }
            mean = self._sum / count
            variance = max(self._sumsq / count - mean * mean, 0.0)
            stddev = math.sqrt(variance)
            p95 = self._percentile(0.95, count)
            p99 = self._percentile(0.99, count)
            return {
                "sample_count": count,
                "mean": mean,
                "stddev": stddev,
                "p95": p95,
                "p99": p99,
            }

        def _percentile(self, ratio: float, count: int) -> float:
            if count == 0:
                return math.nan
            index = max(0, min(count - 1, int(math.floor(ratio * (count - 1)))))
            return self._sorted[index]

    def create_streaming_metric(window_size: int = 1440) -> StreamingMetricHandle:
        return StreamingMetricHandle(window_size=window_size)

else:  # 导入成功，直接导出原生实现

    class StreamingMetricHandle(_NativeStreamingMetricHandle):
        """向外暴露的 StreamingMetricHandle 类型."""

    def create_streaming_metric(window_size: int = 1440) -> StreamingMetricHandle:
        return StreamingMetricHandle(window_size=window_size)

__all__.append("create_streaming_metric")
