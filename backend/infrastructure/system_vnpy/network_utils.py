# -*- coding: utf-8 -*-
"""
网络工具模块.

提供网络连通性测试,端口扫描等功能.
"""

import logging
import socket
import ssl
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class NetworkTester:
    """网络测试器."""

    def __init__(self):
        """初始化网络测试器."""
        self.logger = logging.getLogger(__name__)

    def test_host(self, host: str, port: int = 80) -> bool:
        """测试主机连通性."""
        return test_connectivity(host, port)

    def ping(self, host: str) -> bool:
        """Ping主机（简单版本）."""
        return test_connectivity(host, 80)


class PortScanner:
    """端口扫描器."""

    def __init__(self):
        """初始化端口扫描器."""
        self.logger = logging.getLogger(__name__)

    def scan(self, host: str, ports: List[int]) -> List[Dict[str, Any]]:
        """扫描指定端口."""
        return scan_ports(host, ports)

    def scan_range(
        self, host: str, start_port: int, end_port: int
    ) -> List[Dict[str, Any]]:
        """扫描端口范围."""
        ports = list(range(start_port, end_port + 1))
        return self.scan(host, ports)


class SSLValidator:
    """SSL验证器."""

    def __init__(self):
        """初始化SSL验证器."""
        self.logger = logging.getLogger(__name__)

    def validate_ssl_cert(self, host: str, port: int = 443) -> Dict[str, Any]:
        """验证SSL证书."""
        try:
            context = ssl.create_default_context()
            with (
                socket.create_connection((host, port)) as sock,
                context.wrap_socket(sock, server_hostname=host) as ssock,
            ):
                cert = ssock.getpeercert()
                return {"valid": True, "cert_info": cert, "host": host, "port": port}
        except (ssl.SSLError, OSError) as e:
            return {"valid": False, "error": str(e), "host": host, "port": port}

    def check_ssl_expiry(self, host: str, port: int = 443) -> Dict[str, Any]:
        """检查SSL证书到期时间."""
        try:
            context = ssl.create_default_context()
            with (
                socket.create_connection((host, port)) as sock,
                context.wrap_socket(sock, server_hostname=host) as ssock,
            ):
                cert = ssock.getpeercert()
                if cert is None:
                    return {
                        "valid": False,
                        "error": "No certificate information available",
                        "host": host,
                        "port": port,
                    }

                expiry_date = cert.get("notAfter")
                if expiry_date and isinstance(expiry_date, str):
                    expiry = datetime.strptime(expiry_date, "%b %d %H:%M:%S %Y %Z")
                    return {
                        "valid": True,
                        "expiry_date": expiry,
                        "days_until_expiry": (expiry - datetime.now()).days,
                        "host": host,
                        "port": port,
                    }
                else:
                    return {
                        "valid": False,
                        "error": "No expiry date found in certificate",
                        "host": host,
                        "port": port,
                    }
        except (ssl.SSLError, OSError, ValueError) as e:
            return {"valid": False, "error": str(e), "host": host, "port": port}


def test_connectivity(host: str, port: int = 80) -> bool:
    """测试连通性."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except OSError:
        return False


def scan_ports(host: str, ports: List[int]) -> List[Dict[str, Any]]:
    """扫描端口."""
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
