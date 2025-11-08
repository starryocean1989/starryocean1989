# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

socket_metrics = pytest.importorskip("backend.infrastructure.native.native_socket_metrics")


@pytest.mark.skipif(
    not socket_metrics.SOCKET_METRICS_AVAILABLE,
    reason="native_socket_metrics 扩展不可用",
)
def test_get_socket_metrics_structure():
    metrics = socket_metrics.get_socket_metrics()
    expected_keys = {
        "recv_buffer_size_avg",
        "send_buffer_size_avg",
        "recv_buffer_size_max",
        "send_buffer_size_max",
        "recv_buffer_size_min",
        "send_buffer_size_min",
        "recv_buffer_usage_ratio",
        "send_buffer_usage_ratio",
        "total_connections",
        "tcp_connections",
        "established_connections",
    }
    assert expected_keys.issubset(metrics.keys())
    assert metrics["total_connections"] >= 0
    assert metrics["established_connections"] >= 0

