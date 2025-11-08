# -*- coding: utf-8 -*-
import pytest

netprobe = pytest.importorskip("native_netprobe")


def test_single_connection_returns_dict():
    result = netprobe.test_connection("127.0.0.1", 65534, timeout=0.1)
    assert "status" in result
    assert "ping_ms" in result
    assert result["host"] == "127.0.0.1"
    assert result["port"] == 65534


def test_batch_connection_summary():
    servers = [("127.0.0.1", 65534), ("192.0.2.1", 65535)]
    summary = netprobe.batch_test_connections(servers, timeout=0.1, max_concurrent=2)
    assert summary["total"] == 2
    assert len(summary["results"]) == 2

