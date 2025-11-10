# -*- coding: utf-8 -*-
"""native_statistics 扩展与 AdaptiveThresholdManager 集成测试.

测试覆盖:
1. 原生 StreamingMetricHandle 更新+快照统计
2. AdaptiveThresholdManager 使用原生句柄的阈值学习
3. 数量不足时的默认阈值回退
4. 原生句柄异常后的 Python 回退路径
"""

from __future__ import annotations

import math
import time
from typing import Dict, List, cast

import pytest

from backend.infrastructure.native.native_statistics import (
    STATISTICS_AVAILABLE,
    create_streaming_metric,
    StreamingMetricHandle,
)
from backend.infrastructure.system_vnpy.monitor_system import (
    AdaptiveThresholdManager,
    ThresholdConfig,
)


@pytest.mark.skipif(not STATISTICS_AVAILABLE, reason="native_statistics 扩展未编译")
def test_streaming_metric_handle_basic_statistics() -> None:
    handle: StreamingMetricHandle = create_streaming_metric(window_size=10)
    samples = [float(i) for i in range(10)]
    for value in samples:
        handle.update(value)

    snapshot = handle.snapshot()
    assert snapshot["sample_count"] == 10

    mean_val = cast(float, snapshot["mean"])
    assert math.isclose(mean_val, 4.5, rel_tol=1e-6)

    stddev_val = cast(float, snapshot["stddev"])
    assert math.isclose(stddev_val, math.sqrt(8.25), rel_tol=1e-6)

    p95_val = cast(float, snapshot["p95"])
    assert p95_val >= 8.0

    p99_val = cast(float, snapshot["p99"])
    assert p99_val >= 9.0


@pytest.mark.skipif(not STATISTICS_AVAILABLE, reason="native_statistics 扩展未编译")
def test_adaptive_threshold_manager_native_path(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = AdaptiveThresholdManager()

    config = ThresholdConfig(
        metric_name="cpu_load",
        default_warning=70.0,
        default_critical=90.0,
        min_samples=5,
        window_size=20,
    )
    manager.register_metric(config)

    base_samples = [50.0, 55.0, 60.0, 65.0, 70.0, 75.0]
    for sample in base_samples:
        manager.learn_baseline("cpu_load", sample)

    for _ in range(3):
        manager.learn_baseline("cpu_load", 80.0)
        time.sleep(0.01)

    thresholds = manager.get_all_thresholds()["cpu_load"]
    assert thresholds["using_default"] is False
    assert thresholds["sample_count"] >= len(base_samples) + 3
    assert thresholds["warning"] >= config.default_warning
    assert thresholds["critical"] >= config.default_critical


@pytest.mark.skipif(not STATISTICS_AVAILABLE, reason="native_statistics 扩展未编译")
def test_adaptive_threshold_manager_native_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = AdaptiveThresholdManager()

    config = ThresholdConfig(
        metric_name="io_latency",
        default_warning=20.0,
        default_critical=30.0,
        min_samples=5,
        window_size=10,
    )
    manager.register_metric(config)

    def raise_error(_: float) -> None:
        raise RuntimeError("mock native failure")

    handle = manager._statistics_handles.get("io_latency")
    assert handle is not None

    monkeypatch.setattr(handle, "update", raise_error)

    for idx in range(6):
        manager.learn_baseline("io_latency", float(idx) + 1.0)

    assert "io_latency" not in manager._statistics_handles

    thresholds = manager.get_all_thresholds().get("io_latency")
    assert thresholds is not None
    assert thresholds["using_default"] is True
    assert thresholds["sample_count"] == 6

    warning = manager.get_threshold("io_latency", "warning")
    assert warning == pytest.approx(config.default_warning)


@pytest.mark.skipif(not STATISTICS_AVAILABLE, reason="native_statistics 扩展未编译")
def test_adaptive_threshold_manager_low_samples() -> None:
    manager = AdaptiveThresholdManager()
    config = ThresholdConfig(
        metric_name="mem_usage",
        default_warning=75.0,
        default_critical=90.0,
        min_samples=10,
        window_size=20,
    )
    manager.register_metric(config)

    for value in [40.0, 50.0, 60.0]:
        manager.learn_baseline("mem_usage", value)

    thresholds = manager.get_all_thresholds()["mem_usage"]
    assert thresholds["using_default"] is True
    assert thresholds["sample_count"] == 3
    assert manager.get_threshold("mem_usage", "warning") == config.default_warning
    assert manager.get_threshold("mem_usage", "critical") == config.default_critical
