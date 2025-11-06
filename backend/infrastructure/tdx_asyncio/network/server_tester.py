# -*- coding: utf-8 -*-
"""
通达信服务器测速工具

提供服务器响应时间测试功能:
- 单服务器测速
- 批量服务器测速
- 服务器排序与筛选
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple

from ..api.hq import AsyncTdxHq_API

logger = logging.getLogger(__name__)


# ==============================================================================
# 服务器测速器
# ==============================================================================


class ServerTester:
    """通达信服务器测速器

    功能:
    - 测试服务器响应时间
    - 批量并发测速
    - 自动筛选可用服务器

    示例:
        >>> tester = ServerTester()
        >>> # 测试单个服务器
        >>> response_time = await tester.test_server('121.14.110.210', 7709)
        >>> print(f"响应时间: {response_time:.3f}秒")
        >>>
        >>> # 批量测试
        >>> servers = [('121.14.110.210', 7709), ('119.147.212.81', 7709)]
        >>> results = await tester.batch_test_servers(servers)
        >>> print(results)
    """

    def __init__(self, timeout: float = 10.0, max_concurrent: int = 50):
        """初始化测速器

        Args:
            timeout: 单个服务器测试超时时间(秒)
            max_concurrent: 最大并发测试数
        """
        self.timeout = timeout
        self.max_concurrent = max_concurrent

    async def test_server(
        self, ip: str, port: int, timeout: Optional[float] = None
    ) -> Optional[float]:
        """测试单个服务器响应时间

        Args:
            ip: 服务器IP
            port: 服务器端口
            timeout: 超时时间(秒),如果为None则使用默认值

        Returns:
            响应时间(秒),失败返回None
        """
        if timeout is None:
            timeout = self.timeout

        start_time = time.time()
        api = None

        try:
            # 创建连接
            api = AsyncTdxHq_API()

            # 测试连接(带超时)
            connected = await asyncio.wait_for(
                api.connect(ip, port, time_out=timeout), timeout=timeout
            )

            if not connected:
                logger.debug(f"服务器连接失败: {ip}:{port}")
                return None

            # 测试查询(获取股票列表)
            result = await asyncio.wait_for(
                api.get_security_list(market=1, start=0), timeout=timeout
            )

            if not result:
                logger.debug(f"服务器查询失败: {ip}:{port}")
                return None

            # 计算响应时间
            elapsed = time.time() - start_time
            logger.debug(f"服务器测速成功: {ip}:{port}, 响应时间: {elapsed:.3f}秒")
            return elapsed

        except asyncio.TimeoutError:
            logger.debug(f"服务器测速超时: {ip}:{port}")
            return None
        except Exception as e:
            logger.debug(f"服务器测速异常: {ip}:{port}, 错误: {e}")
            return None
        finally:
            # 关闭连接
            if api is not None:
                try:
                    await api.disconnect()
                except Exception:
                    pass

    async def batch_test_servers(
        self,
        servers: List[Tuple[str, int]],
        max_concurrent: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> Dict[Tuple[str, int], float]:
        """批量测试服务器

        Args:
            servers: 服务器列表 [(ip, port), ...]
            max_concurrent: 最大并发数,如果为None则使用默认值
            timeout: 超时时间(秒),如果为None则使用默认值

        Returns:
            {(ip, port): response_time} 字典,失败的服务器不包含在结果中

        示例:
            >>> tester = ServerTester()
            >>> servers = [
            >>>     ('121.14.110.210', 7709),
            >>>     ('119.147.212.81', 7709),
            >>>     ('113.105.73.88', 7709),
            >>> ]
            >>> results = await tester.batch_test_servers(servers, max_concurrent=20)
            >>> # 按响应时间排序
            >>> sorted_servers = sorted(results.items(), key=lambda x: x[1])
            >>> for (ip, port), response_time in sorted_servers[:10]:
            >>>     print(f"{ip}:{port} - {response_time:.3f}秒")
        """
        if max_concurrent is None:
            max_concurrent = self.max_concurrent

        if timeout is None:
            timeout = self.timeout

        if not servers:
            return {}

        logger.info(f"开始批量测速: {len(servers)}个服务器, 并发数: {max_concurrent}")

        # 分批测试(避免资源竞争)
        results = {}
        batch_size = max_concurrent

        for i in range(0, len(servers), batch_size):
            batch = servers[i : i + batch_size]

            # 创建测试任务
            tasks = []
            for ip, port in batch:
                task = self.test_server(ip, port, timeout)
                tasks.append((ip, port, task))

            # 并发执行
            batch_results = await asyncio.gather(
                *[task for _, _, task in tasks], return_exceptions=True
            )

            # 收集结果
            for (ip, port, _), result in zip(tasks, batch_results):
                if isinstance(result, Exception):
                    logger.debug(f"服务器测速异常: {ip}:{port}, 错误: {result}")
                elif result is not None:
                    results[(ip, port)] = result

            logger.debug(
                f"批次测速完成: {i // batch_size + 1}/{(len(servers) + batch_size - 1) // batch_size}, "
                f"成功: {len([r for r in batch_results if r is not None and not isinstance(r, Exception)])}/{len(batch)}"
            )

        logger.info(f"批量测速完成: 成功 {len(results)}/{len(servers)} 个服务器")
        return results

    async def get_fastest_servers(
        self,
        servers: List[Tuple[str, int]],
        top_n: int = 10,
        max_concurrent: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> List[Tuple[Tuple[str, int], float]]:
        """获取最快的N个服务器

        Args:
            servers: 服务器列表 [(ip, port), ...]
            top_n: 返回前N个最快的服务器
            max_concurrent: 最大并发数
            timeout: 超时时间(秒)

        Returns:
            [((ip, port), response_time), ...] 列表,按响应时间升序排序

        示例:
            >>> tester = ServerTester()
            >>> servers = [...]  # 服务器列表
            >>> fastest = await tester.get_fastest_servers(servers, top_n=10)
            >>> for (ip, port), response_time in fastest:
            >>>     print(f"{ip}:{port} - {response_time:.3f}秒")
        """
        # 批量测速
        results = await self.batch_test_servers(servers, max_concurrent, timeout)

        # 按响应时间排序
        sorted_results = sorted(results.items(), key=lambda x: x[1])

        # 返回前N个
        return sorted_results[:top_n]

    async def filter_available_servers(
        self,
        servers: List[Tuple[str, int]],
        max_response_time: float = 10.0,
        max_concurrent: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> List[Tuple[str, int]]:
        """筛选可用服务器

        Args:
            servers: 服务器列表 [(ip, port), ...]
            max_response_time: 最大响应时间(秒),超过此时间的服务器被过滤
            max_concurrent: 最大并发数
            timeout: 超时时间(秒)

        Returns:
            可用服务器列表 [(ip, port), ...]

        示例:
            >>> tester = ServerTester()
            >>> servers = [...]  # 服务器列表
            >>> available = await tester.filter_available_servers(
            >>>     servers,
            >>>     max_response_time=5.0  # 只保留5秒内响应的服务器
            >>> )
            >>> print(f"可用服务器: {len(available)}/{len(servers)}")
        """
        # 批量测速
        results = await self.batch_test_servers(servers, max_concurrent, timeout)

        # 筛选响应时间符合要求的服务器
        available = [
            server for server, response_time in results.items() if response_time <= max_response_time
        ]

        logger.info(
            f"服务器筛选完成: 可用 {len(available)}/{len(servers)} 个 "
            f"(响应时间 ≤ {max_response_time}秒)"
        )

        return available


# ==============================================================================
# 便捷函数
# ==============================================================================


async def test_server(ip: str, port: int, timeout: float = 10.0) -> Optional[float]:
    """测试单个服务器响应时间(便捷函数)

    Args:
        ip: 服务器IP
        port: 服务器端口
        timeout: 超时时间(秒)

    Returns:
        响应时间(秒),失败返回None
    """
    tester = ServerTester(timeout=timeout)
    return await tester.test_server(ip, port)


async def batch_test_servers(
    servers: List[Tuple[str, int]], max_concurrent: int = 50, timeout: float = 10.0
) -> Dict[Tuple[str, int], float]:
    """批量测试服务器(便捷函数)

    Args:
        servers: 服务器列表 [(ip, port), ...]
        max_concurrent: 最大并发数
        timeout: 超时时间(秒)

    Returns:
        {(ip, port): response_time} 字典
    """
    tester = ServerTester(timeout=timeout, max_concurrent=max_concurrent)
    return await tester.batch_test_servers(servers)


async def get_fastest_servers(
    servers: List[Tuple[str, int]], top_n: int = 10, max_concurrent: int = 50, timeout: float = 10.0
) -> List[Tuple[Tuple[str, int], float]]:
    """获取最快的N个服务器(便捷函数)

    Args:
        servers: 服务器列表 [(ip, port), ...]
        top_n: 返回前N个最快的服务器
        max_concurrent: 最大并发数
        timeout: 超时时间(秒)

    Returns:
        [((ip, port), response_time), ...] 列表
    """
    tester = ServerTester(timeout=timeout, max_concurrent=max_concurrent)
    return await tester.get_fastest_servers(servers, top_n)


# ==============================================================================
# 导出
# ==============================================================================

__all__ = [
    "ServerTester",
    "test_server",
    "batch_test_servers",
    "get_fastest_servers",
]
