# -*- coding: utf-8 -*-
import os
import pytest

native_metrics = pytest.importorskip("native_process_metrics")


def test_fallback_system_metrics():
    metrics = native_metrics.get_system_metrics(use_native=False)
    assert "cpu_percent" in metrics
    assert "memory_percent" in metrics
    assert "process_count" in metrics
    assert "net_sent_bytes" in metrics
    assert "net_recv_bytes" in metrics
    assert isinstance(metrics["load_average"], list)


def test_fallback_process_snapshot():
    snapshot = native_metrics.get_process_snapshot(os.getpid(), use_native=False)
    assert snapshot["pid"] == os.getpid()
    assert "cpu_percent" in snapshot


@pytest.mark.skipif(
    not native_metrics.PROCESS_METRICS_AVAILABLE,
    reason="native extension not available in current environment",
)
def test_native_metrics_available():
    system_metrics = native_metrics.get_system_metrics(use_native=True)
    expected_keys = {
        "cpu_percent",
        "memory_percent",
        "disk_percent",
        "net_sent_bytes",
        "net_recv_bytes",
        "process_count",
        "timestamp",
        "load_average",
    }
    assert expected_keys.issubset(system_metrics.keys())

    aggregate = native_metrics.get_process_snapshot(0, use_native=True)
    assert "aggregate" in aggregate

