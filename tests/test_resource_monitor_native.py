# -*- coding: utf-8 -*-
import time

import pytest

from backend.infrastructure.data_module_vnpy.load_balancer import ResourceMonitor


@pytest.fixture(autouse=True)
def _enable_native_env(monkeypatch):
    monkeypatch.setenv("NATIVE_RESOURCE_MONITOR", "1")
    yield


def test_resource_monitor_prefers_native(monkeypatch):
    monitor = ResourceMonitor()
    monitor._use_native = True
    monitor._native_disabled_reason = None
    monitor._native_degraded = False

    snapshots = [
        {
            "timestamp": time.time(),
            "cpu_percent": 10.0,
            "memory_percent": 20.0,
            "disk_percent": 5.0,
            "net_sent_bytes": 1_000.0,
            "net_recv_bytes": 2_000.0,
        },
        {
            "timestamp": time.time() + 1.0,
            "cpu_percent": 15.0,
            "memory_percent": 25.0,
            "disk_percent": 8.0,
            "net_sent_bytes": 3_000.0,
            "net_recv_bytes": 6_000.0,
        },
    ]

    monitor._native_get_system_metrics = lambda: snapshots.pop(0)

    first = monitor.get_metrics()
    assert first.source == "native"

    second = monitor.get_metrics()
    assert second.source == "native"
    assert second.cpu_percent == pytest.approx(15.0)
    assert second.memory_percent == pytest.approx(25.0)
    assert second.disk_io_percent == pytest.approx(8.0)


def test_resource_monitor_fallback_on_error(monkeypatch):
    monitor = ResourceMonitor()
    monitor._use_native = True
    monitor._native_degraded = False
    monitor._native_disabled_reason = None

    def _raise():
        raise RuntimeError("boom")

    monitor._native_get_system_metrics = _raise

    metrics = monitor.get_metrics()
    assert metrics.source == "psutil"
    assert monitor._use_native is False

