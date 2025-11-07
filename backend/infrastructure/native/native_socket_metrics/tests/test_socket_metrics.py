# -*- coding: utf-8 -*-
"""native_socket_metrics 单元测试."""

import platform

import pytest

from backend.infrastructure.native.native_socket_metrics import (
    SOCKET_METRICS_AVAILABLE,
    get_socket_metrics,
)


WINDOWS = platform.system() == "Windows"


@pytest.mark.skipif(not (WINDOWS and SOCKET_METRICS_AVAILABLE), reason="native_socket_metrics 不可用")
def test_get_socket_metrics_returns_expected_structure():
    metrics = get_socket_metrics()
    assert isinstance(metrics, dict)
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


