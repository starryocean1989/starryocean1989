# -*- coding: utf-8 -*-
"""
两阶段重试连接池 v2.1

基于 AsyncConnectionPool 实现，保留所有连接池特性：
- 批量创建连接
- 连接生命周期管理
- 连接复用
- 主备热切换
- 动态监控

同时添加两阶段重试机制：
- 阶段1：IPv4+IPv6混合池，最多10次尝试，使用智能连接分配策略
- 阶段2：IPv4最快30%服务器，最多5次尝试，使用智能连接分配策略
- 自动排除已尝试的服务器

智能连接分配策略（v2.1新增）：
- 每个服务器可创建多个连接（受限于max_connections字段）
- 优先分配给高容量服务器（max_connections为19和20）
- 总连接数 = 所有活跃服务器max_connections累加

作者：[项目名称]
版本：2.1
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..api.hq import AsyncTdxHq_API
from ..core.connection_pool import AsyncConnectionPool, ConnectionPoolConfig
from ..utils.logger import logger


class RetryConnectionPool:
    """
    带两阶段重试的连接池包装器 v2.1

    基于 AsyncConnectionPool，保留所有连接池特性：
    - 批量创建连接
    - 连接复用
    - 主备热切换
    - 动态监控

    两阶段重试机制：
    - 阶段1: IPv4+IPv6混合池，最多10次尝试，使用智能连接分配策略
    - 阶段2: IPv4最快30%服务器，最多5次尝试，使用智能连接分配策略

    智能连接分配策略（v2.1新增）：
    - 每个服务器可创建多个连接（受限于max_connections字段）
    - 优先分配给高容量服务器（max_connections为19和20）
    - 总连接数 = 所有活跃服务器max_connections累加
    """

    def __init__(
        self,
        server_pool_manager,
        phase1_max_attempts: int = 10,
        phase2_max_attempts: int = 5,
        connection_timeout: float = 5.0,
        enable_connection_pool: bool = True,
        max_connections: Optional[int] = None,
    ):
        """
        初始化重试连接池

        Args:
            server_pool_manager: ServerPoolManager 实例
            phase1_max_attempts: 阶段1最大尝试次数
            phase2_max_attempts: 阶段2最大尝试次数
            connection_timeout: 连接超时时间（秒）
            enable_connection_pool: 是否启用连接池（默认True，保留所有连接池特性）
            max_connections: 最大连接数限制（None=自动计算，指定值=限制总连接数，用于步骤4等场景）
        """
        self.server_pool_manager = server_pool_manager
        self.phase1_max_attempts = phase1_max_attempts
        self.phase2_max_attempts = phase2_max_attempts
        self.connection_timeout = connection_timeout
        self.enable_connection_pool = enable_connection_pool
        self.max_connections = max_connections  # 最大连接数限制

        # 连接池实例（按需初始化）
        self.phase1_pool: Optional[AsyncConnectionPool] = None
        self.phase2_pool: Optional[AsyncConnectionPool] = None

        # 连接池初始化标志
        self._phase1_pool_initialized = False
        self._phase2_pool_initialized = False

        # 连接池初始化锁
        self._init_lock = asyncio.Lock()

    async def _ensure_phase1_pool(self):
        """确保阶段1连接池已初始化"""
        if self._phase1_pool_initialized:
            return

        async with self._init_lock:
            if self._phase1_pool_initialized:
                return

            if not self.enable_connection_pool:
                self._phase1_pool_initialized = True
                return

            # 获取混合服务器列表
            servers_list = self.server_pool_manager.get_mixed_servers(shuffle=False, exclude=None)
            if not servers_list:
                logger.warning(
                    "[RETRY-POOL] 阶段1: 无可用服务器，连接池创建失败",
                    extra={"log_type": "SYSTEM"}
                )
                self._phase1_pool_initialized = True
                return

            # ✅ 使用智能连接分配策略
            if self.max_connections is not None:
                # 如果指定了最大连接数限制，使用限制值
                total_connections_needed = self.max_connections
                logger.debug(
                    f"[RETRY-POOL] 阶段1: 使用指定的连接数限制={total_connections_needed}",
                    extra={"log_type": "SYSTEM"}
                )

                # 当指定max_connections时，使用简单的分配策略：选择最快的N个服务器，每个1个连接
                connection_allocations = []
                for i, s in enumerate(servers_list[:total_connections_needed]):
                    connection_allocations.append((s['ip'], s['port'], 1))

                logger.debug(
                    f"[RETRY-POOL] 阶段1: 限制模式，选择最快{len(connection_allocations)}个服务器，每个1个连接",
                    extra={"log_type": "SYSTEM"}
                )
            else:
                # 计算总连接数需求：直接累加所有活跃服务器的max_connections
                total_connections_needed = self.server_pool_manager.calculate_total_max_connections()

                # 使用智能分配策略分配连接
                connection_allocations = self.server_pool_manager.allocate_connections_intelligently(
                    total_connections=total_connections_needed,
                    exclude=None
                )

            if not connection_allocations:
                logger.warning(
                    "[RETRY-POOL] 阶段1: 智能连接分配失败，连接池创建失败",
                    extra={"log_type": "SYSTEM"}
                )
                self._phase1_pool_initialized = True
                return

            # 根据分配结果创建连接列表
            # 每个服务器创建指定数量的连接（受限于max_connections）
            expanded_servers = []
            for ip, port, conn_count in connection_allocations:
                # 为每个服务器创建conn_count个连接
                for _ in range(conn_count):
                    expanded_servers.append((ip, port))

            servers = expanded_servers

            # 计算连接池大小（所有分配连接数之和）
            max_connections = len(servers)  # 总连接数 = 智能分配后的连接数之和

            # 创建阶段1连接池
            config = ConnectionPoolConfig(
                max_primary_connections=max_connections,
                max_standby_connections=min(10, max(0, len(servers) - max_connections)),
                timeout=self.connection_timeout,
                enable_monitoring=True,
            )

            self.phase1_pool = AsyncConnectionPool(
                servers=servers,
                config=config
            )

            # 初始化连接池（异步）
            await self.phase1_pool.initialize()

            self._phase1_pool_initialized = True

            # 统计分配信息（使用servers_list中的max_connections信息）
            servers_dict = {f"{s['ip']}:{s['port']}": s for s in servers_list}
            high_cap_count = 0
            high_cap_connections = 0

            for ip, port, cnt in connection_allocations:
                key = f"{ip}:{port}"
                if key in servers_dict:
                    max_conn = servers_dict[key].get('max_connections', 20)
                    if max_conn in [19, 20]:
                        high_cap_count += 1
                        high_cap_connections += cnt

            logger.info(
                f"[RETRY-POOL] 阶段1连接池已初始化（智能分配策略）: "
                f"总连接数={max_connections}, 涉及服务器={len(connection_allocations)}, "
                f"高容量服务器(19/20)={high_cap_count}个, 高容量连接={high_cap_connections}个",
                extra={"log_type": "SYSTEM"}
            )

    async def _ensure_phase2_pool(self):
        """确保阶段2连接池已初始化"""
        if self._phase2_pool_initialized:
            return

        async with self._init_lock:
            if self._phase2_pool_initialized:
                return

            if not self.enable_connection_pool:
                self._phase2_pool_initialized = True
                return

            # 获取最快30%服务器列表
            servers_list = self.server_pool_manager.get_top_30_percent_ipv4_servers(
                shuffle=False, exclude=None
            )
            if not servers_list:
                logger.warning(
                    "[RETRY-POOL] 阶段2: 无可用服务器，连接池创建失败",
                    extra={"log_type": "SYSTEM"}
                )
                self._phase2_pool_initialized = True
                return

            # ✅ 阶段2也使用智能连接分配策略
            # 阶段2使用更少的连接数（最快30%服务器，连接数约为阶段1的30%）
            # 阶段2使用最快30%服务器，所以连接数约为阶段1的30%
            # 计算阶段2服务器的总max_connections，然后取30%
            num_phase2_servers = len(servers_list)
            # 累加阶段2服务器的max_connections
            phase2_total_max_connections = sum(s.get('max_connections', 20) for s in servers_list)
            total_connections_needed = int(phase2_total_max_connections * 0.3)

            # 使用智能分配策略分配连接（排除非阶段2的服务器）
            # 获取阶段2服务器的IP:Port列表
            phase2_server_keys = [f"{s['ip']}:{s['port']}" for s in servers_list]

            # 获取所有服务器并过滤出阶段2服务器
            all_servers = self.server_pool_manager.get_mixed_servers(shuffle=False, exclude=None)
            phase2_servers_dict = {f"{s['ip']}:{s['port']}": s for s in all_servers if f"{s['ip']}:{s['port']}" in phase2_server_keys}

            # 直接为阶段2服务器分配连接（使用智能策略的逻辑）
            # 先按max_connections分组
            servers_high_capacity = []
            servers_other = []

            for s in servers_list:
                max_conn = s.get('max_connections', 20)
                if max_conn in [19, 20]:
                    servers_high_capacity.append(s)
                else:
                    servers_other.append(s)

            # 初始化连接分配
            connection_map = {}
            for s in servers_list:
                key = f"{s['ip']}:{s['port']}"
                connection_map[key] = (s['ip'], s['port'], 0)

            remaining = total_connections_needed

            # 第一阶段：每个服务器至少1个连接
            for s in servers_list:
                if remaining <= 0:
                    break
                key = f"{s['ip']}:{s['port']}"
                ip, port, current = connection_map[key]
                connection_map[key] = (ip, port, current + 1)
                remaining -= 1

            # 第二阶段：优先分配给19和20的服务器
            while remaining > 0 and servers_high_capacity:
                available_high = [
                    s for s in servers_high_capacity
                    if connection_map[f"{s['ip']}:{s['port']}"][2] < s.get('max_connections', 20)
                ]
                if not available_high:
                    break
                for s in available_high:
                    if remaining <= 0:
                        break
                    key = f"{s['ip']}:{s['port']}"
                    ip, port, current = connection_map[key]
                    connection_map[key] = (ip, port, current + 1)
                    remaining -= 1

            # 第三阶段：分配给其他服务器
            while remaining > 0 and servers_other:
                available_other = [
                    s for s in servers_other
                    if connection_map[f"{s['ip']}:{s['port']}"][2] < s.get('max_connections', 20)
                ]
                if not available_other:
                    break
                for s in available_other:
                    if remaining <= 0:
                        break
                    key = f"{s['ip']}:{s['port']}"
                    ip, port, current = connection_map[key]
                    connection_map[key] = (ip, port, current + 1)
                    remaining -= 1

            # 根据分配结果创建连接列表
            expanded_servers = []
            for ip, port, conn_count in connection_map.values():
                if conn_count > 0:
                    for _ in range(conn_count):
                        expanded_servers.append((ip, port))

            servers = expanded_servers

            # 计算连接池大小（所有分配连接数之和）
            max_connections = len(servers)  # 总连接数 = 智能分配后的连接数之和

            # 创建阶段2连接池
            config = ConnectionPoolConfig(
                max_primary_connections=max_connections,
                max_standby_connections=min(5, max(0, len(servers) - max_connections)),
                timeout=self.connection_timeout,
                enable_monitoring=True,
            )

            self.phase2_pool = AsyncConnectionPool(
                servers=servers,
                config=config
            )

            # 初始化连接池（异步）
            await self.phase2_pool.initialize()

            self._phase2_pool_initialized = True

            # 统计分配信息
            high_cap_count = len([s for s in servers_list if s.get('max_connections', 20) in [19, 20]])
            high_cap_connections = sum(conn_count for ip, port, conn_count in connection_map.values()
                                      if any(s['ip'] == ip and s['port'] == port and s.get('max_connections', 20) in [19, 20]
                                             for s in servers_list))

            logger.info(
                f"[RETRY-POOL] 阶段2连接池已初始化（智能分配策略）: "
                f"总连接数={max_connections}, 涉及服务器={len([c for c in connection_map.values() if c[2] > 0])}, "
                f"高容量服务器(19/20)={high_cap_count}个, 高容量连接={high_cap_connections}个",
                extra={"log_type": "SYSTEM"}
            )

    async def execute_with_retry(
        self,
        task_func: Callable[[AsyncTdxHq_API], Any],
        attempted_servers: List[str],
        scenario: str = "download",
    ) -> Tuple[Optional[Any], bool]:
        """
        执行带重试的任务

        Args:
            task_func: 任务函数，接受 AsyncTdxHq_API 作为参数，返回结果
            attempted_servers: 已尝试服务器列表（格式：["ip:port", ...]），会被更新
            scenario: 场景标识（用于日志）

        Returns:
            (result, success): 结果和是否成功
        """
        # 阶段1: 混合池重试
        logger.debug(
            f"[RETRY-POOL] 开始阶段1重试（混合池）: 已尝试={len(attempted_servers)}个服务器",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        result = await self._phase1_retry(task_func, attempted_servers, scenario)
        if result is not None:
            logger.info(
                f"[RETRY-POOL] ✅ 阶段1成功: 已尝试={len(attempted_servers)}个服务器",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            return result, True

        # 阶段2: 最快30%服务器重试
        logger.info(
            f"[RETRY-POOL] ⚠️ 阶段1失败，进入阶段2（最快30%池）: 已尝试={len(attempted_servers)}个服务器",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        result = await self._phase2_retry(task_func, attempted_servers, scenario)
        if result is not None:
            logger.info(
                f"[RETRY-POOL] ✅ 阶段2成功: 已尝试={len(attempted_servers)}个服务器",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            return result, True

        # 两个阶段都失败
        logger.warning(
            f"[RETRY-POOL] ❌ 两阶段重试均失败: 总计尝试={len(attempted_servers)}个服务器",
            extra={"log_type": "ALERT", "scenario": scenario}
        )
        return None, False

    async def _phase1_retry(
        self,
        task_func: Callable[[AsyncTdxHq_API], Any],
        attempted_servers: List[str],
        scenario: str,
    ) -> Optional[Any]:
        """阶段1重试：混合池（使用连接池）"""
        remaining_attempts = self.phase1_max_attempts

        # 确保连接池已初始化
        if self.enable_connection_pool:
            await self._ensure_phase1_pool()

        while remaining_attempts > 0:
            # 获取混合服务器池（排除已尝试的）
            servers = self.server_pool_manager.get_mixed_servers(
                shuffle=True,
                exclude=attempted_servers if attempted_servers else None
            )

            if not servers:
                logger.debug(
                    f"[RETRY-POOL] 阶段1: 无可用服务器（已排除{len(attempted_servers)}个）",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                break

            # 尝试每个服务器直到成功或全部失败
            for server_info in servers:
                if remaining_attempts <= 0:
                    break

                server_key = f"{server_info['ip']}:{server_info['port']}"
                result = await self._try_single_server_with_pool(
                    task_func,
                    server_info,
                    attempted_servers,
                    scenario,
                    phase=1,
                    pool=self.phase1_pool if self.enable_connection_pool else None,
                )

                remaining_attempts -= 1

                if result is not None:
                    return result

                # 服务器已添加到 attempted_servers，继续下一个
                logger.debug(
                    f"[RETRY-POOL] 阶段1: 服务器 {server_key} 失败，剩余尝试={remaining_attempts}",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )

            # 如果所有可用服务器都尝试过了，退出
            if not servers:
                break

        return None

    async def _phase2_retry(
        self,
        task_func: Callable[[AsyncTdxHq_API], Any],
        attempted_servers: List[str],
        scenario: str,
    ) -> Optional[Any]:
        """阶段2重试：最快30%服务器（使用连接池）"""
        remaining_attempts = self.phase2_max_attempts

        # 确保连接池已初始化
        if self.enable_connection_pool:
            await self._ensure_phase2_pool()

        while remaining_attempts > 0:
            # 获取最快30%服务器（排除已尝试的）
            servers = self.server_pool_manager.get_top_30_percent_ipv4_servers(
                shuffle=True,
                exclude=attempted_servers if attempted_servers else None
            )

            if not servers:
                logger.debug(
                    f"[RETRY-POOL] 阶段2: 无可用服务器（已排除{len(attempted_servers)}个）",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                break

            # 尝试每个服务器直到成功或全部失败
            for server_info in servers:
                if remaining_attempts <= 0:
                    break

                server_key = f"{server_info['ip']}:{server_info['port']}"
                result = await self._try_single_server_with_pool(
                    task_func,
                    server_info,
                    attempted_servers,
                    scenario,
                    phase=2,
                    pool=self.phase2_pool if self.enable_connection_pool else None,
                )

                remaining_attempts -= 1

                if result is not None:
                    return result

                # 服务器已添加到 attempted_servers，继续下一个
                logger.debug(
                    f"[RETRY-POOL] 阶段2: 服务器 {server_key} 失败，剩余尝试={remaining_attempts}",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )

            # 如果所有可用服务器都尝试过了，退出
            if not servers:
                break

        return None

    async def _try_single_server_with_pool(
        self,
        task_func: Callable[[AsyncTdxHq_API], Any],
        server_info: Dict[str, Any],
        attempted_servers: List[str],
        scenario: str,
        phase: int,
        pool: Optional[AsyncConnectionPool] = None,
    ) -> Optional[Any]:
        """
        尝试单个服务器（优先使用连接池，失败时创建临时连接）

        Args:
            task_func: 任务函数
            server_info: 服务器信息 {"ip": ..., "port": ..., "name": ..., "ping_time": ...}
            attempted_servers: 已尝试服务器列表（会被更新）
            scenario: 场景标识
            phase: 当前阶段（1或2）
            pool: 连接池实例（如果启用连接池）

        Returns:
            任务结果，失败返回 None
        """
        server_key = f"{server_info['ip']}:{server_info['port']}"
        server_name = server_info.get('name', server_key)

        # 记录尝试
        attempted_servers.append(server_key)

        # 优先使用连接池
        if pool and self.enable_connection_pool:
            return await self._try_with_connection_pool(
                task_func, server_info, attempted_servers, scenario, phase, pool
            )

        # 连接池未启用或不可用，创建临时连接
        return await self._try_with_temp_connection(
            task_func, server_info, attempted_servers, scenario, phase
        )

    async def _try_with_connection_pool(
        self,
        task_func: Callable[[AsyncTdxHq_API], Any],
        server_info: Dict[str, Any],
        attempted_servers: List[str],
        scenario: str,
        phase: int,
        pool: AsyncConnectionPool,
    ) -> Optional[Any]:
        """使用连接池尝试服务器"""
        server_key = f"{server_info['ip']}:{server_info['port']}"
        server_name = server_info.get('name', server_key)

        # 从连接池中获取匹配的连接（最多尝试3次，避免无限循环）
        max_pool_attempts = 3
        conn = None

        for _ in range(max_pool_attempts):
            conn = await pool.acquire()
            if conn is None:
                # 连接池无可用连接，回退到临时连接
                logger.debug(
                    f"[RETRY-POOL] 阶段{phase}: 连接池无可用连接，回退到临时连接: {server_key}",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                return await self._try_with_temp_connection(
                    task_func, server_info, attempted_servers, scenario, phase
                )

            # 检查连接是否匹配目标服务器
            conn_key = f"{conn.ip}:{conn.port}"
            if conn_key == server_key:
                # 匹配，使用这个连接
                break
            else:
                # 不匹配，释放连接，尝试下一个
                pool.release(conn)
                conn = None

        # 如果3次都没找到匹配的连接，回退到临时连接
        if conn is None:
            logger.debug(
                f"[RETRY-POOL] 阶段{phase}: 连接池中未找到匹配的连接，回退到临时连接: {server_key}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            return await self._try_with_temp_connection(
                task_func, server_info, attempted_servers, scenario, phase
            )

        # 使用连接池连接执行任务
        try:
            logger.debug(
                f"[RETRY-POOL] 阶段{phase}: 使用连接池连接 {server_name} ({server_key}), "
                f"延迟={server_info.get('ping_time', 0):.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 执行任务
            result = await task_func(conn)

            # 检查结果有效性
            if result is None:
                logger.debug(
                    f"[RETRY-POOL] 阶段{phase}: 服务器 {server_key} 任务返回 None",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                return None

            # 成功
            logger.debug(
                f"[RETRY-POOL] 阶段{phase}: 服务器 {server_key} 任务成功（连接池）",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            return result

        except Exception as e:
            logger.debug(
                f"[RETRY-POOL] 阶段{phase}: 服务器 {server_key} 异常: {type(e).__name__}: {e}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            return None
        finally:
            # 释放连接到连接池（复用）
            if conn:
                pool.release(conn)

    async def _try_with_temp_connection(
        self,
        task_func: Callable[[AsyncTdxHq_API], Any],
        server_info: Dict[str, Any],
        attempted_servers: List[str],
        scenario: str,
        phase: int,
    ) -> Optional[Any]:
        """创建临时连接尝试服务器（连接池不可用时的回退方案）"""
        server_key = f"{server_info['ip']}:{server_info['port']}"
        server_name = server_info.get('name', server_key)

        api = None
        try:
            logger.debug(
                f"[RETRY-POOL] 阶段{phase}: 创建临时连接 {server_name} ({server_key}), "
                f"延迟={server_info.get('ping_time', 0):.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 创建连接
            api = AsyncTdxHq_API()
            connected = await asyncio.wait_for(
                api.connect(server_info['ip'], server_info['port']),
                timeout=self.connection_timeout
            )

            if not connected:
                logger.debug(
                    f"[RETRY-POOL] 阶段{phase}: 服务器 {server_key} 连接失败",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                return None

            # 执行任务
            result = await task_func(api)

            # 检查结果有效性
            if result is None:
                logger.debug(
                    f"[RETRY-POOL] 阶段{phase}: 服务器 {server_key} 任务返回 None",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                return None

            # 成功
            logger.debug(
                f"[RETRY-POOL] 阶段{phase}: 服务器 {server_key} 任务成功（临时连接）",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            return result

        except asyncio.TimeoutError:
            logger.debug(
                f"[RETRY-POOL] 阶段{phase}: 服务器 {server_key} 连接超时",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            return None
        except Exception as e:
            logger.debug(
                f"[RETRY-POOL] 阶段{phase}: 服务器 {server_key} 异常: {type(e).__name__}: {e}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            return None
        finally:
            # 确保连接关闭（临时连接不复用）
            if api:
                try:
                    await api.disconnect()
                except Exception:
                    pass

    async def close_all(self):
        """关闭所有连接池"""
        if self.phase1_pool:
            try:
                await self.phase1_pool.close_all()
            except Exception as e:
                logger.warning(
                    f"[RETRY-POOL] 关闭阶段1连接池失败: {e}",
                    extra={"log_type": "SYSTEM"}
                )

        if self.phase2_pool:
            try:
                await self.phase2_pool.close_all()
            except Exception as e:
                logger.warning(
                    f"[RETRY-POOL] 关闭阶段2连接池失败: {e}",
                    extra={"log_type": "SYSTEM"}
                )
