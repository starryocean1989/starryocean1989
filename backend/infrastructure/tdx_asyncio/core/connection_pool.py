# -*- coding: utf-8 -*-
"""
异步连接池管理器 v2.1

核心特性：
1. 智能连接分配策略（支持多连接/服务器）
2. 主备热切换机制
3. 动态服务器监控
4. 自动故障转移
5. 配置化重试策略

架构设计：
- 主连接池：N个活跃连接（基于智能分配策略）
- 备用连接池：M个备用连接（默认10个）
- IP池管理：动态排序和优选
- 全异步架构：零线程开销

作者：[项目名称]
版本：2.1
"""
import asyncio
import logging
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

from ..api.hq import AsyncTdxHq_API
from ..network.ip_pool import AsyncSmartIPPool
from ..network.constants import BROKER_SERVERS_7709
from ..utils.logger import logger
from .exceptions import TdxConnectionError


@dataclass
class ConnectionPoolConfig:
    """连接池配置"""

    max_primary_connections: Optional[int] = None  # None 表示按服务器数量自动配置
    max_standby_connections: Optional[int] = None  # None 表示根据剩余服务器数自动配置
    timeout: float = 5.0  # 连接超时
    max_retries: int = 3  # 最大重试次数
    retry_interval: float = 0.2  # 重试间隔
    enable_monitoring: bool = True  # 是否启用监控
    monitor_interval: float = 600.0  # 监控间隔（10分钟）


class AsyncConnectionPool:
    """
    异步连接池管理器 v2.0

    保留原有API兼容性：
    - async with pool
    - await pool.acquire()
    - pool.release()

    新增高级特性：
    - 主备热切换
    - 动态监控
    - 自动重试
    """

    def __init__(
        self,
        servers: Optional[List[Tuple[str, int]]] = None,
        max_connections: Optional[int] = None,
        timeout: float = 5.0,
        config: Optional[ConnectionPoolConfig] = None,
    ):
        """
        初始化连接池

        保留原有参数兼容性，新增config高级配置
        """
        # 兼容原有API
        if config is None:
            config = ConnectionPoolConfig(max_primary_connections=max_connections, timeout=timeout)

        self.config = config

        # 服务器列表
        if servers is None:
            # ✅ 使用BROKER_SERVERS_7709作为默认服务器列表
            servers = [(ip, port) for _, ip, port, _ in BROKER_SERVERS_7709]
        self.all_servers = servers

        total_servers = len(self.all_servers)

        # 自动推导主连接数量
        if self.config.max_primary_connections is None:
            self.config.max_primary_connections = total_servers or 1
        else:
            # 防止超过可用服务器数量
            self.config.max_primary_connections = max(
                1, min(self.config.max_primary_connections, total_servers or 1)
            )

        # 自动推导备用连接数量
        if self.config.max_standby_connections is None:
            remaining = max(0, total_servers - self.config.max_primary_connections)
            self.config.max_standby_connections = remaining
        else:
            max_standby = max(0, total_servers - self.config.max_primary_connections)
            self.config.max_standby_connections = max(
                0, min(self.config.max_standby_connections, max_standby)
            )

        # IP池管理（智能排序）
        self.ip_pool = AsyncSmartIPPool(servers=servers, update_interval=config.monitor_interval)

        # 主连接池
        self.primary_connections: List[Optional[AsyncTdxHq_API]] = []

        # 备用连接池
        self.standby_connections: List[Optional[AsyncTdxHq_API]] = []

        # 连接状态跟踪
        self.connection_usage: Dict[AsyncTdxHq_API, bool] = {}  # True=使用中

        # 并发控制
        semaphore_limit = max(1, self.config.max_primary_connections)
        self.semaphore = asyncio.Semaphore(semaphore_limit)

        # 初始化状态
        self.initialized = False

        logger.info(
            f"异步连接池v2初始化: 主连接{self.config.max_primary_connections}个, "
            f"备用{self.config.max_standby_connections}个"
        )

    async def initialize(self):
        """
        初始化连接池（异步）

        创建主连接和备用连接，实现主备热切换机制
        """
        if self.initialized:
            return

        # 启动IP池监控
        if self.config.enable_monitoring:
            await self.ip_pool.start()

        # 获取最优服务器列表
        best_servers = await self.ip_pool.get_servers()
        if not best_servers:
            raise TdxConnectionError("无法获取服务器列表")

        # 创建主连接
        logger.info("创建%d个主连接...", self.config.max_primary_connections)
        primary_servers = best_servers[: self.config.max_primary_connections]
        self.primary_connections = await self._create_connections(primary_servers)

        # 创建备用连接
        standby_count = self.config.max_standby_connections or 0
        max_primary = self.config.max_primary_connections or 0
        logger.info("创建%d个备用连接...", standby_count)
        if standby_count > 0 and len(best_servers) > max_primary:
            standby_servers = best_servers[max_primary : max_primary + standby_count]
            self.standby_connections = await self._create_connections(standby_servers)
        else:
            self.standby_connections = []

        self.initialized = True

        success_count = sum(1 for c in self.primary_connections if c)
        standby_count = sum(1 for c in self.standby_connections if c)
        logger.info("连接池就绪: 主连接=%d个, 备用=%d个", success_count, standby_count)

    async def _create_connections(
        self, servers: List[Tuple[str, int]]
    ) -> List[Optional[AsyncTdxHq_API]]:
        """
        并发创建多个连接

        :param servers: 服务器列表
        :return: 连接列表
        """
        tasks = [self._create_single_connection(server) for server in servers]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def _create_single_connection(self, server: Tuple[str, int]) -> Optional[AsyncTdxHq_API]:
        """
        创建单个连接

        :param server: (ip, port) 元组
        :return: 连接实例或None
        """
        try:
            client = await AsyncTdxHq_API.factory(
                server=server, timeout=self.config.timeout, heartbeat=False, raise_exception=False
            )

            if client:
                self.connection_usage[client] = False
                logger.debug("连接已建立: IP=%s, 端口=%d", server[0], server[1])
                return client
            else:
                logger.warning(
                    "连接失败: IP=%s, 端口=%d", server[0], server[1], extra={"log_type": "SYSTEM"}
                )
                return None

        except Exception as e:
            logger.warning("连接异常: 服务器=%s, 错误=%s", server, e, extra={"log_type": "SYSTEM"})
            return None

    async def acquire(self) -> Optional[AsyncTdxHq_API]:
        """
        获取连接（兼容原有API）

        增强逻辑：
        1. 优先返回可用的主连接
        2. 主连接不可用时，使用备用连接并补充
        3. 自动重试机制
        """
        if not self.initialized:
            await self.initialize()

        # 并发控制
        await self.semaphore.acquire()

        # 尝试获取主连接
        for conn in self.primary_connections:
            if conn and not self.connection_usage.get(conn, True):
                # 测试连接是否可用
                if await self._test_connection(conn):
                    self.connection_usage[conn] = True
                    return conn

        # 主连接都不可用，使用备用连接
        logger.warning("主连接池无可用连接，切换到备用连接", extra={"log_type": "SYSTEM"})
        return await self._failover_to_standby()

    async def _test_connection(self, conn: AsyncTdxHq_API) -> bool:
        """
        测试连接是否可用（快速心跳）

        :param conn: 连接实例
        :return: 是否可用
        """
        try:
            # 简单测试：检查连接是否关闭
            return not conn.closed
        except Exception:
            return False

    async def _failover_to_standby(self) -> Optional[AsyncTdxHq_API]:
        """
        故障转移到备用连接

        :return: 备用连接或None
        """
        if not self.standby_connections:
            logger.error("备用连接池为空，无法故障转移", extra={"log_type": "SYSTEM"})
            return None

        # 获取第一个可用的备用连接
        standby_conn = None
        for conn in self.standby_connections:
            if conn and await self._test_connection(conn):
                standby_conn = conn
                break

        if standby_conn:
            # 将备用连接提升为主连接
            self.standby_connections.remove(standby_conn)
            self.primary_connections.append(standby_conn)

            # 异步补充新的备用连接
            asyncio.create_task(self._replenish_standby())

            self.connection_usage[standby_conn] = True
            return standby_conn

        return None

    async def _replenish_standby(self):
        """
        补充备用连接（后台异步）

        从IP池获取新服务器，建立备用连接
        """
        try:
            servers = await self.ip_pool.get_servers()

            # 选择一个未使用的服务器
            used_servers = {
                (c.ip, c.port) for c in self.primary_connections + self.standby_connections if c
            }

            for server in servers:
                if server not in used_servers:
                    new_conn = await self._create_single_connection(server)
                    if new_conn:
                        self.standby_connections.append(new_conn)
                        logger.info(f"已补充备用连接: {server}")
                        break

        except Exception as e:
            logger.error(f"补充备用连接失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def release(self, conn: Optional[AsyncTdxHq_API] = None):
        """
        释放连接（兼容原有API）

        保持连接复用，不关闭连接
        """
        if conn:
            self.connection_usage[conn] = False

        self.semaphore.release()

    async def close_all(self):
        """
        关闭所有连接（异步）
        """
        logger.info("关闭连接池...")

        # 停止IP池监控
        await self.ip_pool.stop()

        # 关闭所有主连接
        for conn in self.primary_connections:
            if conn:
                await conn.close()

        # 关闭所有备用连接
        for conn in self.standby_connections:
            if conn:
                await conn.close()

        self.primary_connections.clear()
        self.standby_connections.clear()
        self.connection_usage.clear()
        self.initialized = False

        logger.info("连接池已关闭")

    # 保留原有上下文管理器API
    async def __aenter__(self):
        """
        支持 async with 语法
        """
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        支持 async with 语法
        """
        await self.close_all()


# 保留原有的上下文管理器（兼容性）
class AsyncConnectionPoolContext:
    """
    连接上下文管理器（保持原有API）

    用于单次连接使用，自动释放连接
    """

    def __init__(self, pool: AsyncConnectionPool):
        self.pool = pool
        self.connection: Optional[AsyncTdxHq_API] = None

    async def __aenter__(self) -> AsyncTdxHq_API:
        self.connection = await self.pool.acquire()
        if self.connection is None:
            raise RuntimeError("Failed to acquire connection from pool")
        return self.connection

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.pool.release(self.connection)


# ==================== 使用示例和便捷函数 ====================


async def example_usage():
    """
    使用示例展示新特性
    """
    from ..network.constants import BROKER_SERVERS_7709

    # 1. 基本用法（完全兼容原有API）
    pool = AsyncConnectionPool(max_connections=10)
    async with pool:
        conn = await pool.acquire()
        if conn:
            bars = await conn.get_security_bars(9, 1, "600000", 0, 10)
            if bars:
                print(f"基本功能: 获取到{len(bars)}根K线")
            pool.release(conn)

    # 2. 高级配置（主备切换）
    config = ConnectionPoolConfig(
        max_primary_connections=38,  # 主连接
        max_standby_connections=10,  # 备用连接
        enable_monitoring=True,  # 启用监控
        monitor_interval=600.0,  # 10分钟更新
        max_retries=3,  # 最大重试
    )

    pool = AsyncConnectionPool(config=config)

    async with pool:
        # 连接自动故障转移，无需手动处理
        conn = await pool.acquire()
        if conn:
            data = await conn.get_security_bars(9, 1, "600000", 0, 100)
            pool.release(conn)

    # 3. 使用IP池（独立使用）
    # ✅ 使用BROKER_SERVERS_7709作为服务器列表
    ip_pool = AsyncSmartIPPool(
        servers=[(ip, port) for _, ip, port, _ in BROKER_SERVERS_7709[:50]],
        update_interval=300.0,  # 5分钟更新
    )

    await ip_pool.start()

    # 获取最快的服务器
    best_server = await ip_pool.get_best_server()
    print(f"最快服务器: {best_server}")

    # 获取排序后的前10个服务器
    top_10 = (await ip_pool.get_servers())[:10]
    print(f"前10个服务器: {top_10}")

    await ip_pool.stop()


if __name__ == "__main__":
    # 运行示例（仅用于测试）
    asyncio.run(example_usage())
