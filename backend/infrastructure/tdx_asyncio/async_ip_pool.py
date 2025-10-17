# -*- coding: utf-8 -*-
"""
异步IP池管理模块

纯异步实现IP池管理，借鉴pytdx设计但完全异步化：
- 动态测速排序服务器
- 自动剔除故障服务器
- 支持随机和智能两种策略
- 零线程开销，全异步实现

作者：[项目名称]
版本：2.0
"""

import asyncio
import time
from typing import List, Tuple, Optional, Dict
from collections import OrderedDict

from .async_hq import AsyncTdxHq_API
from .logger import logger


class AsyncIPPool:
    """
    异步IP池基类

    核心约束：
    - 纯异步实现，无线程
    - 使用asyncio.create_task()后台监控
    - 保持服务器顺序动态更新
    """

    def __init__(self, servers: List[Tuple[str, int]]):
        """
        初始化IP池

        :param servers: 服务器列表 [(ip, port), ...]
        """
        self.servers = servers

    async def get_servers(self) -> List[Tuple[str, int]]:
        """
        获取服务器列表

        :return: 服务器列表
        """
        return self.servers


class AsyncRandomIPPool(AsyncIPPool):
    """
    随机IP池：每次随机打乱服务器顺序

    用途：负载均衡，避免总是使用同一批服务器
    """

    async def get_servers(self) -> List[Tuple[str, int]]:
        """
        获取随机打乱的服务器列表
        """
        import random
        shuffled = self.servers.copy()
        random.shuffle(shuffled)
        return shuffled


class AsyncSmartIPPool(AsyncIPPool):
    """
    智能IP池：动态测速排序服务器

    特性：
    - 后台任务定期测速（非阻塞）
    - 按响应时间排序
    - 自动剔除故障服务器（响应时间>10秒）
    - 默认10分钟更新一次
    - 支持自定义测速间隔和超时
    """

    def __init__(
        self,
        servers: List[Tuple[str, int]],
        update_interval: float = 600.0,  # 10分钟
        test_timeout: float = 2.0,
        max_fail_time: float = 10.0  # 超过此时间视为不可用
    ):
        """
        初始化智能IP池

        :param servers: 服务器列表
        :param update_interval: 更新间隔（秒）
        :param test_timeout: 单个服务器测试超时（秒）
        :param max_fail_time: 最大失败时间（秒）
        """
        super().__init__(servers)
        self.update_interval = update_interval
        self.test_timeout = test_timeout
        self.max_fail_time = max_fail_time

        # 服务器响应时间记录 {server: response_time}
        self.server_scores: Dict[Tuple[str, int], float] = {}

        # 排序后的服务器列表（按速度排序）
        self.sorted_servers: List[Tuple[str, int]] = servers.copy()

        # 后台任务控制
        self._monitor_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        logger.info(f"智能IP池初始化: {len(servers)}个服务器, 更新间隔{update_interval}秒")

    async def start(self):
        """
        启动后台监控任务

        开始定期测速和排序
        """
        if self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            logger.info("智能IP池监控任务已启动")

    async def stop(self):
        """
        停止后台监控任务
        """
        if self._monitor_task:
            self._stop_event.set()
            await self._monitor_task
            self._monitor_task = None
            logger.info("智能IP池监控任务已停止")

    async def _monitor_loop(self):
        """
        后台监控循环（纯异步）

        定期测试所有服务器并排序
        """
        logger.debug("IP池监控循环启动")

        while not self._stop_event.is_set():
            try:
                await self._test_all_servers()
                await self._sort_servers()

                # 等待下次更新（可中断）
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.update_interval
                    )
                except asyncio.TimeoutError:
                    # 超时，继续下一轮测试
                    pass

            except Exception as e:
                logger.error(f"IP池监控循环异常: {e}")
                # 异常时等待1分钟后重试
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=60.0
                    )
                except asyncio.TimeoutError:
                    pass

        logger.debug("IP池监控循环结束")

    async def _test_all_servers(self):
        """
        并发测试所有服务器（纯异步）

        使用asyncio.gather并发测试，提升效率
        """
        logger.debug(f"开始测试{len(self.servers)}个服务器")

        # 创建测试任务
        tasks = [
            self._test_single_server(server)
            for server in self.servers
        ]

        # 并发执行所有测试
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        logger.debug(f"服务器测试完成: {success_count}/{len(self.servers)}个成功")

    async def _test_single_server(self, server: Tuple[str, int]):
        """
        最优服务器测速算法（融合三版本优点）

        融合特性：
        1. pytdx：真实请求测速，验证数据完整性（>800条）
        2. mootdx：perf_counter精确计时，多种测试方法
        3. 现有：纯异步实现，后台监控

        测试流程：
        1. 精确计时开始（perf_counter）
        2. 连接测试（timeout=0.7秒，快速失败）
        3. API调用（get_security_list验证真实服务质量）
        4. 数据验证（len(result) > 800，防止半死服务器）
        5. 精确计时结束

        :param server: (ip, port) 元组
        :return: 测试结果（成功返回响应时间，失败返回None）
        """
        ip, port = server

        # 使用perf_counter精确计时（毫秒级精度）
        start_time = time.perf_counter()

        try:
            # 创建客户端并测试连接（快速超时0.7秒，来自pytdx）
            client = await AsyncTdxHq_API.factory(
                server=server,
                timeout=0.7,  # pytdx推荐：快速超时，避免等待过久
                heartbeat=False,
                raise_exception=False
            )

            if client:
                try:
                    # 真实API请求验证（来自pytdx.util.best_ip）
                    # 调用get_security_list而非简单心跳，确保服务器真正可用
                    result = await client.get_security_list(0, 1)

                    # 数据完整性验证（pytdx核心逻辑）
                    if result is not None and len(result) > 800:
                        # 数据完整，服务器健康
                        response_time = time.perf_counter() - start_time

                        # 记录响应时间（毫秒级精度，来自mootdx）
                        self.server_scores[server] = response_time

                        # 智能分级日志
                        if response_time < 0.1:
                            level = "优秀"
                        elif response_time < 0.5:
                            level = "良好"
                        elif response_time < 2.0:
                            level = "可用"
                        else:
                            level = "较慢"

                        logger.debug(f"服务器 {ip}:{port} [{level}] 响应: {response_time*1000:.2f}ms, 数据: {len(result)}条")
                        return response_time
                    else:
                        # 数据不完整，标记为不可用（pytdx核心逻辑）
                        self.server_scores[server] = self.max_fail_time + 1
                        logger.debug(f"服务器 {ip}:{port} 数据不完整: {len(result) if result else 0}条")
                        return None

                finally:
                    await client.close()
            else:
                # 连接失败
                self.server_scores[server] = self.max_fail_time + 1
                logger.debug(f"服务器 {ip}:{port} 连接失败")
                return None

        except asyncio.TimeoutError:
            # 超时（快速失败机制）
            self.server_scores[server] = self.max_fail_time + 1
            logger.debug(f"服务器 {ip}:{port} 测试超时(>0.7s)")
            return None

        except Exception as e:
            # 其他异常
            self.server_scores[server] = self.max_fail_time + 1
            logger.debug(f"服务器 {ip}:{port} 测试异常: {e}")
            return None

    async def _sort_servers(self):
        """
        按响应时间排序服务器

        将可用服务器按速度排序，不可用的排在后面或剔除
        """
        # 过滤掉不可用的服务器（响应时间>max_fail_time秒）
        available_servers = [
            (server, score) for server, score in self.server_scores.items()
            if score <= self.max_fail_time
        ]

        if not available_servers:
            logger.warning("无可用服务器，保持原有列表")
            return

        # 按响应时间排序（从小到大）
        available_servers.sort(key=lambda x: x[1])

        # 更新排序列表
        self.sorted_servers = [server for server, _ in available_servers]

        logger.debug(f"服务器重新排序完成，最快服务器: {self.sorted_servers[0] if self.sorted_servers else '无'}")

    async def get_servers(self) -> List[Tuple[str, int]]:
        """
        获取排序后的服务器列表

        :return: 按速度排序的服务器列表（最快的在前）
        """
        return self.sorted_servers if self.sorted_servers else self.servers

    async def get_best_server(self) -> Optional[Tuple[str, int]]:
        """
        获取最快的服务器

        :return: 最快的服务器，如果无可用服务器则返回None
        """
        servers = await self.get_servers()
        return servers[0] if servers else None

    async def get_server_stats(self) -> Dict[str, int]:
        """
        获取服务器统计信息

        :return: 统计字典
        """
        total = len(self.servers)
        available = len([s for s in self.server_scores.values() if s <= self.max_fail_time])
        unavailable = total - available

        return {
            "total": total,
            "available": available,
            "unavailable": unavailable
        }


# ==================== 使用示例 ====================

async def example_usage():
    """
    使用示例
    """
    from .constants import HQ_HOSTS_ALL

    # 1. 创建随机IP池（负载均衡）
    random_pool = AsyncRandomIPPool(HQ_HOSTS_ALL[:10])
    random_servers = await random_pool.get_servers()
    print(f"随机排序的前3个服务器: {random_servers[:3]}")

    # 2. 创建智能IP池（动态测速）
    smart_pool = AsyncSmartIPPool(
        servers=HQ_HOSTS_ALL[:20],
        update_interval=300.0,  # 5分钟更新
        test_timeout=2.0
    )

    # 启动监控
    await smart_pool.start()

    # 等待第一次测速完成
    await asyncio.sleep(15)

    # 获取最快服务器
    best_server = await smart_pool.get_best_server()
    print(f"当前最快服务器: {best_server}")

    # 获取排序后的服务器列表
    sorted_servers = await smart_pool.get_servers()
    print(f"排序后的前5个服务器: {sorted_servers[:5]}")

    # 获取统计信息
    stats = await smart_pool.get_server_stats()
    print(f"服务器状态: {stats}")

    # 停止监控
    await smart_pool.stop()


if __name__ == "__main__":
    # 运行示例（仅用于测试）
    asyncio.run(example_usage())
