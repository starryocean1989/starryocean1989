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
        max_fail_time: float = 10.0,  # 超过此时间视为不可用
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
        # 🔥 关键：初始化为空列表，必须等待首次测速完成后才有数据
        self.sorted_servers: List[Tuple[str, int]] = []

        # 后台任务控制
        self._monitor_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        logger.info(f"智能IP池初始化: {len(servers)}个候选服务器, 更新间隔{update_interval}秒")
        logger.info("注意: sorted_servers 初始为空，必须等待首次测速完成后才有数据")

    async def start(self):
        """
        启动后台监控任务

        开始定期测速和排序
        """
        if self._monitor_task is None:
            # 🔥 关键：启动时先清空 sorted_servers，确保在测速完成前为空
            self.sorted_servers = []
            logger.info("🔍 智能IP池：开始首次服务器速度分析（异步进行）...")
            logger.info(f"⏳ 正在并发测试 {len(self.servers)} 个服务器，预计耗时10-30秒")

            try:
                # 执行首次测速和排序
                await self._test_all_servers()
                await self._sort_servers()

                if self.sorted_servers:
                    logger.info(
                        f"✅ 智能IP池：服务器分析完成！"
                        f"可用服务器: {len(self.sorted_servers)}个，"
                        f"最快: {self.sorted_servers[0][0]}:{self.sorted_servers[0][1]}"
                    )
                    logger.info("💡 现在可以安全使用下载功能了")
                else:
                    logger.error("❌ 智能IP池：服务器分析完成，但没有可用服务器！")
                    logger.error("⚠️  下载功能将不可用，请检查网络连接")
            except Exception as e:
                logger.error(f"❌ 智能IP池：首次测速失败: {e}")
                logger.error("⚠️  服务器测速异常，下载功能将不可用")
                # 🔥 关键：失败时保持 sorted_servers 为空，强制阻止下载

            # 启动后台监控任务
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            logger.info("🔄 智能IP池：后台持续监控已启动（定期重新评估服务器速度）")

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
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.update_interval)
                except asyncio.TimeoutError:
                    # 超时，继续下一轮测试
                    pass

            except Exception as e:
                logger.error(f"IP池监控循环异常: {e}")
                # 异常时等待1分钟后重试
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=60.0)
                except asyncio.TimeoutError:
                    pass

        logger.debug("IP池监控循环结束")

    async def _test_all_servers(self):
        """
        并发测试所有服务器（纯异步）

        使用asyncio.gather并发测试，提升效率
        分批测试，每批最多20个，避免资源竞争
        """
        total_servers = len(self.servers)
        logger.info(f"📊 开始测试 {total_servers} 个服务器...")

        # 🔥 关键改进：分批测试，避免一次性并发过多
        batch_size = 20  # 每批最多20个服务器
        all_results = []

        for batch_start in range(0, total_servers, batch_size):
            batch_end = min(batch_start + batch_size, total_servers)
            batch = self.servers[batch_start:batch_end]

            logger.info(f"   测试进度: {batch_start+1}-{batch_end}/{total_servers}")

            # 创建测试任务
            tasks = [self._test_single_server(server) for server in batch]

            # 并发执行批次测试
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            all_results.extend(batch_results)

        # 处理结果
        success_count = sum(
            1 for r in all_results if not isinstance(r, Exception) and r is not None
        )
        logger.info(f"✅ 服务器测试完成: {success_count}/{total_servers} 个可用")

    async def _test_single_server(self, server: Tuple[str, int]):
        """
        服务器测速算法（简化版：仅TCP连接测试）

        测试流程：
        1. 精确计时开始（perf_counter）
        2. TCP连接测试（timeout=2秒，添加整体超时保护）
        3. 记录连接响应时间

        :param server: (ip, port) 元组
        :return: 测试结果（成功返回响应时间，失败返回None）
        """
        ip, port = server

        # 使用perf_counter精确计时（毫秒级精度）
        start_time = time.perf_counter()

        try:
            # 🔥 关键改进：为整个测试过程添加超时保护（防止卡死）
            # 创建客户端并测试TCP连接
            client = await asyncio.wait_for(
                AsyncTdxHq_API.factory(
                    server=server,
                    timeout=self.test_timeout * 0.8,  # 稍微小于总超时
                    heartbeat=False,
                    raise_exception=False,
                ),
                timeout=self.test_timeout,
            )

            if client:
                # TCP连接成功，记录响应时间
                response_time = time.perf_counter() - start_time

                # 记录响应时间
                self.server_scores[server] = response_time

                # 智能分级日志
                if response_time < 0.1:
                    level = "优秀"
                elif response_time < 0.3:
                    level = "良好"
                elif response_time < 0.7:
                    level = "可用"
                else:
                    level = "较慢"

                logger.debug(f"服务器 {ip}:{port} [{level}] TCP连接: {response_time*1000:.2f}ms")

                # 关闭连接
                await client.close()
                return response_time
            else:
                # 连接失败
                self.server_scores[server] = self.max_fail_time + 1
                logger.debug(f"服务器 {ip}:{port} TCP连接失败")
                return None

        except asyncio.TimeoutError:
            # 超时（快速失败机制）
            self.server_scores[server] = self.max_fail_time + 1
            logger.debug(f"服务器 {ip}:{port} TCP连接超时(>{self.test_timeout}s)")
            return None

        except Exception as e:
            # 其他异常
            self.server_scores[server] = self.max_fail_time + 1
            logger.debug(f"服务器 {ip}:{port} TCP连接异常: {e}")
            return None

    async def _sort_servers(self):
        """
        按响应时间排序服务器

        将可用服务器按速度排序，不可用的排在后面或剔除
        """
        # 过滤掉不可用的服务器（响应时间>max_fail_time秒）
        available_servers = [
            (server, score)
            for server, score in self.server_scores.items()
            if score <= self.max_fail_time
        ]

        if not available_servers:
            logger.warning("无可用服务器，保持原有列表")
            return

        # 按响应时间排序（从小到大）
        available_servers.sort(key=lambda x: x[1])

        # 更新排序列表
        self.sorted_servers = [server for server, _ in available_servers]

        logger.debug(
            f"服务器重新排序完成，最快服务器: {self.sorted_servers[0] if self.sorted_servers else '无'}"
        )

    async def test_once(self) -> Dict[Tuple[str, int], float]:
        """
        一次性测速所有服务器（公开接口）

        适用场景：
        - 外部已有持续监控机制（如多进程定期测速）
        - 只需要获取一次测速结果

        Returns:
            Dict[server, response_time]: 测速结果字典

        示例：
            pool = AsyncSmartIPPool(servers)
            scores = await pool.test_once()
            # 外部自己处理排序和过滤
        """
        await self._test_all_servers()
        await self._sort_servers()
        return self.server_scores.copy()

    async def get_sorted_servers_with_scores(self) -> List[Tuple[Tuple[str, int], float]]:
        """
        获取排序后的服务器及其响应时间（公开接口）

        Returns:
            List[(server, response_time)]: 按响应时间排序的列表

        示例：
            sorted_results = await pool.get_sorted_servers_with_scores()
            for (ip, port), score in sorted_results:
                if score <= 2.0:  # 只要2秒内的
                    print(f"{ip}:{port} - {score:.2f}s")
        """
        if not self.sorted_servers:
            return []

        return [
            (server, self.server_scores.get(server, float("inf"))) for server in self.sorted_servers
        ]

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

        return {"total": total, "available": available, "unavailable": unavailable}


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
        servers=HQ_HOSTS_ALL[:20], update_interval=300.0, test_timeout=2.0  # 5分钟更新
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
