# -*- coding: utf-8 -*-
"""
网络工具模块

提供网络连通性测试,端口扫描等功能.
"""

import socket
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class NetworkTester:
    """网络测试器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)


class PortScanner:
    """端口扫描器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)


class SSLValidator:
    """SSL验证器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)


def test_connectivity(host: str, port: int = 80) -> bool:
    """测试连通性"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except (socket.error, OSError):
        return False


def scan_ports(host: str, ports: List[int]) -> List[Dict[str, Any]]:
    """扫描端口"""
    results = []
    for port in ports:
        is_open = test_connectivity(host, port)
        results.append({"port": port, "open": is_open})
    return results


__all__ = [
    "NetworkTester",
    "PortScanner",
    "SSLValidator",
    "test_connectivity",
    "scan_ports",
]
