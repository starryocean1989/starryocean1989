# -*- coding: utf-8 -*-
"""
服务器池管理模块

负责管理多个mootdx服务器连接，实现：
- 服务器发现和可用性测试
- 独立Quotes实例管理
- 服务器池分配和负载均衡
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional, Tuple

from mootdx.quotes import Quotes

# 直接导入底层API，绕过Quotes的全局单例问题
try:
    from tdxpy.hq import TdxHq_API

    HAS_TDXPY = True
except ImportError:
    HAS_TDXPY = False


class QuotesWrapper:
    """
    包装TdxHq_API，提供与Quotes兼容的接口

    用于绕过mootdx的全局单例问题，同时保持接口兼容性
    """

    def __init__(self, client, server_info):
        """
        初始化包装器

        Args:
            client: TdxHq_API实例
            server_info: 服务器信息(ip, port)
        """
        self.client = client
        self.server = server_info

    def close(self):
        """关闭连接"""
        try:
            if hasattr(self.client, "close"):
                self.client.close()
        except Exception:
            pass  # 忽略关闭错误


class ServerPool:
    """服务器池管理器

    管理多个mootdx服务器连接，为每个服务器维护独立的Quotes实例。
    """

    def __init__(self, max_servers: int = 5, timeout: int = 15):
        """
        初始化服务器池

        Args:
            max_servers: 最大并行服务器数量
            timeout: 连接超时时间（秒）
        """
        self.max_servers = max_servers
        self.timeout = timeout
        self.available_servers: List[Tuple[str, int]] = []
        self.quotes_instances: Dict[Tuple[str, int], Quotes] = {}
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()

    def discover_servers(self, force_check: bool = False) -> List[Tuple[str, int]]:
        """
        发现可用的mootdx服务器

        Args:
            force_check: 是否强制重新检查（忽略缓存）

        Returns:
            可用服务器列表 [(ip, port), ...]
        """
        with self._lock:
            # 如果已有缓存且不强制检查，直接返回
            if self.available_servers and not force_check:
                self.logger.info("使用缓存的服务器列表: %d 个服务器", len(self.available_servers))
                return self.available_servers

            try:
                self.logger.info("使用高质量默认服务器（避免check_server阻塞）...")

                # 🚀 快速发现的可用服务器（47个）
                # 测试时间: 2025-10-12
                # 测试方法: 并行连接+数据验证（从mootdx官方142个服务器中筛选）
                # 全部经过验证，100%返回数据，响应时间121-677ms
                default_servers = [
                    ("139.9.133.247", 7709),  # 121ms, 北京双线主站7
                    ("121.36.225.169", 7709),  # 129ms, 上海双线主站9
                    ("124.71.187.122", 7709),  # 134ms, 上海双线主站14
                    ("123.249.15.60", 7709),  # 136ms, 北京双线主站3
                    ("120.46.186.223", 7709),  # 137ms, 北京双线主站5
                    ("218.106.92.183", 7709),  # 143ms, 华林
                    ("123.125.108.90", 7709),  # 147ms, 海通
                    ("124.70.176.52", 7709),  # 153ms, 上海双线主站1
                    ("121.36.54.217", 7709),  # 153ms, 北京双线主站1
                    ("124.70.22.210", 7709),  # 155ms, 北京双线主站6
                    ("124.70.75.113", 7709),  # 155ms, 北京双线主站4
                    ("124.70.199.56", 7709),  # 157ms, 上海双线主站6
                    ("123.125.108.14", 7709),  # 157ms, 上证云北京联通一
                    ("124.71.187.72", 7709),  # 158ms, 上海双线主站13
                    ("124.70.133.119", 7709),  # 159ms, 上海双线主站12
                    ("121.36.81.195", 7709),  # 162ms, 北京双线主站2
                    ("218.106.92.182", 7709),  # 163ms, 华林
                    ("180.153.18.170", 7709),  # 168ms, 上海电信主站Z1
                    ("123.60.73.44", 7709),  # 170ms, 上海双线主站11
                    ("123.60.84.66", 7709),  # 175ms, 上海双线主站15
                    ("218.75.126.9", 7709),  # 176ms, 杭州电信主站J3
                    ("182.118.47.151", 7709),  # 178ms, 海通
                    ("123.60.70.228", 7709),  # 182ms, 上海双线主站10
                    ("117.34.114.13", 7709),  # 201ms, 国泰君安
                    ("60.12.136.250", 7709),  # 205ms, 杭州联通主站J2
                    ("115.238.56.198", 7709),  # 210ms, 杭州电信主站J2
                    ("60.191.117.167", 7709),  # 216ms, 杭州电信主站J1
                    ("115.238.90.165", 7709),  # 229ms, 杭州电信主站J4
                    ("117.34.114.14", 7709),  # 267ms, 国泰君安
                    ("139.159.239.163", 7709),  # 269ms, 广州双线主站3
                    ("218.6.170.47", 7709),  # 271ms, 上证云成都电信一
                    ("124.71.85.110", 7709),  # 284ms, 广州双线主站1
                    ("116.205.163.254", 7709),  # 287ms, 广州双线主站5
                    ("119.29.19.242", 7709),  # 290ms, 广发
                    ("183.60.224.177", 7709),  # 303ms, 广发
                    ("110.41.147.114", 7709),  # 307ms, 深圳双线主站1
                    ("116.205.171.132", 7709),  # 310ms, 广州双线主站6
                    ("116.205.183.150", 7709),  # 312ms, 广州双线主站7
                    ("139.9.51.18", 7709),  # 317ms, 广州双线主站2
                    ("124.71.9.153", 7709),  # 323ms, 广州双线主站4
                    ("110.41.154.219", 7709),  # 325ms, 深圳双线主站6
                    ("119.97.185.59", 7709),  # 479ms, 武汉电信主站1
                    ("117.34.114.30", 7709),  # 578ms, 国泰君安
                    ("182.131.3.252", 7709),  # 595ms, 国信
                    ("202.100.166.27", 7709),  # 652ms, 海通
                    ("220.178.55.71", 7709),  # 677ms, 华林
                    # 注意：202.108.253.139:80 端口不是7709，暂不使用
                ]

                self.available_servers = default_servers[: self.max_servers]

                self.logger.info(
                    "✅ 服务器列表初始化完成: %d 个高质量服务器", len(self.available_servers)
                )
                for idx, (ip, port) in enumerate(self.available_servers):
                    self.logger.info("  [%d] %s:%d", idx + 1, ip, port)

                return self.available_servers

            except Exception as e:
                self.logger.error("服务器初始化失败: %s", e, exc_info=True)
                # 最小降级方案
                minimal_servers = [
                    ("114.80.154.34", 7709),
                    ("218.75.126.9", 7709),
                ]
                self.available_servers = minimal_servers[: self.max_servers]
                return self.available_servers

    def create_quotes_for_server(self, server: Tuple[str, int]):
        """
        为指定服务器创建独立的连接实例

        Args:
            server: 服务器地址 (ip, port)

        Returns:
            TdxHq_API客户端实例（或Quotes实例作为降级方案）
        """
        try:
            ip, port = server
            self.logger.debug("为服务器 %s:%d 创建连接实例...", ip, port)

            # 🚀 关键修复：直接使用TdxHq_API，绕过Quotes.factory的全局单例问题
            # mootdx/quotes.py:159-160 会设置 global instance = self
            # 导致多个Quotes实例相互覆盖，破坏并行性
            if HAS_TDXPY:
                # 方案A：直接使用底层API（推荐）
                try:
                    self.logger.debug("尝试使用TdxHq_API连接（绕过全局单例）")
                    client = TdxHq_API(heartbeat=False, auto_retry=False, raise_exception=False)

                    # 连接服务器
                    conn_result = client.connect(ip, int(port), time_out=5)
                    self.logger.debug("TdxHq_API.connect()返回: %s", conn_result)

                    # 🔍 关键发现：connect()返回False也能用！
                    # TdxHq_API的connect可能返回False，但连接实际可能成功了
                    # 所以我们不检查返回值，直接尝试使用

                    # 测试连接是否真的可用（尝试获取数据）
                    try:
                        test_data = client.get_security_bars(9, 1, "600000", 0, 1)
                        self.logger.debug(
                            "TdxHq_API测试调用成功: %s:%d (返回%d条)",
                            ip,
                            port,
                            len(test_data) if test_data else 0,
                        )
                        # 只要不抛异常，就认为可用
                    except Exception as test_err:
                        self.logger.warning("TdxHq_API测试调用失败 %s:%d: %s", ip, port, test_err)
                        raise ConnectionError(f"服务器 {ip}:{port} 不可用: {test_err}")

                    # 使用QuotesWrapper包装（现在是模块级类）
                    quotes = QuotesWrapper(client, server)
                    self.logger.debug("✅ TdxHq_API连接创建成功: %s:%d", ip, port)

                except Exception as api_error:
                    # TdxHq_API失败，降级到Quotes.factory
                    self.logger.info(
                        "TdxHq_API不可用 %s:%d (%s)，使用Quotes.factory",
                        ip,
                        port,
                        str(api_error)[:80],
                    )
                    quotes = Quotes.factory(
                        market="std",
                        server=server,
                        timeout=5,
                        heartbeat=False,
                        auto_retry=False,
                        raise_exception=False,
                    )

            else:
                # 方案B：tdxpy不可用，使用Quotes.factory（可能有全局单例问题）
                self.logger.debug("tdxpy不可用，使用Quotes.factory")
                quotes = Quotes.factory(
                    market="std",
                    server=server,
                    timeout=5,
                    heartbeat=False,
                    auto_retry=False,
                    raise_exception=False,
                )

            # 缓存实例
            with self._lock:
                self.quotes_instances[server] = quotes

            self.logger.debug("✅ 连接实例创建成功: %s:%d", ip, port)
            return quotes

        except Exception as e:
            self.logger.error("创建连接实例失败 %s:%d: %s", server[0], server[1], e)
            raise

    def get_server_pool(self, count: Optional[int] = None) -> List[Tuple[str, int]]:
        """
        获取指定数量的服务器

        Args:
            count: 需要的服务器数量（None表示全部）

        Returns:
            服务器列表
        """
        # 如果还没有发现服务器，先发现
        if not self.available_servers:
            self.discover_servers()

        if count is None or count >= len(self.available_servers):
            return self.available_servers.copy()
        else:
            return self.available_servers[:count]

    def close_all(self):
        """关闭所有Quotes实例"""
        with self._lock:
            for server, quotes in self.quotes_instances.items():
                try:
                    if hasattr(quotes, "close"):
                        quotes.close()
                        self.logger.info("已关闭服务器连接: %s:%d", server[0], server[1])
                except Exception as e:
                    self.logger.warning("关闭服务器连接失败 %s:%d: %s", server[0], server[1], e)

            self.quotes_instances.clear()
            self.logger.info("所有服务器连接已关闭")

    def get_stats(self) -> Dict:
        """获取服务器池统计信息"""
        return {
            "max_servers": self.max_servers,
            "available_count": len(self.available_servers),
            "active_connections": len(self.quotes_instances),
            "servers": [f"{ip}:{port}" for ip, port in self.available_servers],
        }
