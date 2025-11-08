# -*- coding: utf-8 -*-
import pytest
import sys
from pathlib import Path

# 添加测试目录到sys.path
_TEST_DIR = Path(__file__).resolve().parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

from mock_tcp_server import MockTCPServer

netprobe = pytest.importorskip("native_netprobe")


def test_single_connection_returns_dict():
    """测试连接超时的情况
    
    连接到一个不可达的IP,验证超时机制能够正常工作。
    修复后的C扩展应该能在指定超时时间内返回。
    """
    # 使用TEST-NET-1保留地址(192.0.2.0/24),这个地址永远不会响应
    import time
    start = time.time()
    result = netprobe.test_connection("192.0.2.1", 80, timeout=0.5)
    elapsed = time.time() - start
    
    assert "status" in result
    assert "ping_ms" in result
    assert result["host"] == "192.0.2.1"
    assert result["port"] == 80
    # 连接应该超时
    assert result["status"] == "timeout"
    assert result["ping_ms"] == -1.0
    # 验证超时时间合理(0.5s +/- 0.2s余量)
    assert 0.4 < elapsed < 0.8, f"超时时间异常: {elapsed:.2f}s"


def test_batch_connection_summary():
    """测试批量连接超时
    
    批量连接多个不可达的IP,验证超时机制和并发处理。
    """
    import time
    # 使用TEST-NET保留地址
    servers = [
        ("192.0.2.1", 80),
        ("192.0.2.2", 80)
    ]
    start = time.time()
    summary = netprobe.batch_test_connections(servers, timeout=0.5, max_concurrent=2)
    elapsed = time.time() - start
    
    assert summary["total"] == 2
    assert len(summary["results"]) == 2
    # 验证每个结果都包含必要的字段
    for result in summary["results"]:
        assert "status" in result
        assert "host" in result
        assert "port" in result
        # 应该都超时
        assert result["status"] == "timeout"
    # 验证总超时时间合理(并发执行应该接近0.5s)
    assert 0.4 < elapsed < 0.8, f"总超时时间异常: {elapsed:.2f}s"


def test_netprobe_module_available():
    """仅测试netprobe模块是否可以成功导入"""
    # C扩展返回的是整敷01而不是布尔值True,但bool(1) == True
    assert bool(netprobe.NETPROBE_AVAILABLE) is True, "netprobe模块应该可用"

