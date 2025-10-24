# -*- coding: utf-8 -*-
"""
服务器池管理器和自适应下载配置

包含：
1. 服务器池管理：多进程并行测速通达信服务器，提供最优服务器连接
2. 自适应下载配置：根据系统资源动态计算最优的下载配置参数

特性：
- 多进程并行测速（充分利用多核CPU，5-10秒完成）
- 自动排序和故障服务器剔除
- 线程安全
- 根据CPU、内存、任务数量自适应调整配置
"""

import asyncio
import logging
import math
import multiprocessing
import random
import threading
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime
from multiprocessing import get_context

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from backend.infrastructure.tdx_asyncio import AsyncSmartIPPool
from backend.infrastructure.tdx_asyncio.constants import BROKER_SERVERS_7709

from ..config import config_manager
from .core import LoadBalancer
from .tasks import (
    NetworkTask,
    TaskMetrics,
    TaskType,
    ResourceProfile,
)


class ServerPoolManager:
    """
    服务器池管理器 - 单例模式

    在应用启动时初始化并持续运行，为整个 data_module_vnpy 提供最优服务器。
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式：确保全局只有一个实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化服务器池管理器（单例，只会执行一次）"""
        # 避免重复初始化
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self.logger = logging.getLogger(__name__)

        # 🔥 关键修复：确保logger有handler，否则错误信息会被静默
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            self.logger.setLevel(logging.INFO)

        # 运行状态
        self._running = False
        self._start_time: Optional[datetime] = None
        self._cache_date: Optional[str] = None  # 缓存日期

        # 多进程相关
        self._processes: List[Any] = []  # 支持不同上下文的Process类型（spawn/fork等）
        self._sorted_servers: List[Tuple[str, int]] = []  # 存储排序后的服务器结果

        # 配置参数
        self.test_timeout = config_manager.get("chinastock.server_pool.test_timeout", 2.0)
        self.max_fail_time = config_manager.get("chinastock.server_pool.max_fail_time", 10.0)
        self.server_count = config_manager.get(
            "chinastock.server_pool.server_count", 132  # 使用所有可用服务器
        )
        self.max_coroutines_per_process = config_manager.get(
            "chinastock.server_pool.max_coroutines_per_process", 50  # 每进程最多50个协程
        )

        # 缓存文件配置
        self._cache_file = "server_pool_cache.json"

        num_processes = math.ceil(self.server_count / self.max_coroutines_per_process)
        self.logger.debug("服务器池管理器初始化完成（多进程模式）")  # INFO → DEBUG
        self.logger.debug(
            f"配置: {self.server_count}个服务器 → {num_processes}个进程"
        )  # INFO → DEBUG

    def start(self) -> bool:
        """
        启动服务器池管理器（验证缓存 + 按需测速）

        流程：
        1. 加载缓存文件
        2. 验证缓存日期（次日0时失效）
        3. 如果有效：跳过测速，直接使用（<100ms）
        4. 如果失效/不存在：重新测速并更新缓存（~7秒）

        Returns:
            bool: 是否启动成功（缓存可用或测速完成）
        """
        if self._running:
            self.logger.warning("服务器池管理器已在运行")
            return True

        try:
            # 1. 尝试加载缓存
            cache_data, cache_date, is_valid = self.load_server_cache()

            if cache_data and is_valid:
                # ✅ 缓存有效，跳过测速
                self._sorted_servers = cache_data
                self._cache_date = cache_date
                self._running = True
                self._start_time = datetime.now()

                # ✅ 同步更新server_count为实际的BROKER_SERVERS_7709数量
                self.server_count = len(BROKER_SERVERS_7709)

                self.logger.info("✅ 服务器池缓存有效（%s），跳过测速", cache_date)
                self.logger.info("   可用服务器：%d个", len(self._sorted_servers))

                # 推送服务器状态事件
                self._push_server_status_event()

                return True

            elif cache_data and not is_valid:
                # ⚠️ 缓存失效，需要重新测速
                self.logger.warning("⚠️ 服务器池缓存已过期（%s），正在重新测速...", cache_date)
            else:
                # ⚠️ 缓存不存在
                self.logger.warning("⚠️ 服务器池缓存不存在，正在首次测速...")

            # 2. 执行测速
            success = self._start_multiprocess()

            if success:
                # 3. 保存缓存
                self.save_server_cache(self._sorted_servers)
                self.logger.info("✅ 服务器池测速完成，缓存已更新")

            return success

        except Exception as e:
            self.logger.error("启动服务器池管理器失败：%s", e, exc_info=True)
            self._running = False
            return False

    def _start_multiprocess(self) -> bool:
        """
        多进程模式启动

        将服务器列表分配到多个进程，每个进程最多处理50个服务器。

        Returns:
            bool: 是否启动成功
        """
        import time

        start_time = time.time()

        # 获取服务器列表（使用BROKER_SERVERS_7709全量测试）
        all_servers = [(ip, port) for name, ip, port in BROKER_SERVERS_7709]

        # ✅ 更新server_count为实际测试的服务器数量
        self.server_count = len(all_servers)

        self.logger.info("准备测试 %d 个7709服务器", len(all_servers))

        # 按每进程50个服务器分配
        server_chunks = []
        for i in range(0, len(all_servers), self.max_coroutines_per_process):
            chunk = all_servers[i : i + self.max_coroutines_per_process]
            server_chunks.append(chunk)

        num_processes = len(server_chunks)

        self.logger.info("正在启动服务器池管理器（多进程模式），共%d个服务器...", len(all_servers))
        self.logger.debug("📊 服务器分配方案：")
        for i, chunk in enumerate(server_chunks):
            self.logger.debug("   进程%d: %d个服务器", i + 1, len(chunk))

        # 创建共享内存存储结果（使用spawn上下文）
        self.logger.debug("创建multiprocessing上下文（spawn模式）")
        ctx = get_context("spawn")
        manager = ctx.Manager()
        self.logger.debug("✓ Manager创建成功")
        shared_results = manager.dict()

        # 启动测速进程
        self._processes = []
        for i, chunk in enumerate(server_chunks):
            p = ctx.Process(
                target=self._test_servers_in_process,
                args=(
                    i,
                    chunk,
                    shared_results,
                    self.test_timeout,
                    self.max_fail_time,
                ),
                name=f"ServerTest-{i+1}",
            )
            p.start()
            self._processes.append(p)
            self.logger.debug("🚀 进程%d已启动（PID: %d）", i + 1, p.pid)

        # 等待所有进程完成
        self.logger.info("⏳ 等待%d个进程完成测速...", num_processes)
        for i, p in enumerate(self._processes):
            p.join()
            self.logger.info("✅ 进程%d完成", i + 1)

        # 合并结果并排序
        all_scores = dict(shared_results)

        if not all_scores:
            self.logger.error("❌ 所有进程测速失败，没有可用服务器")
            self._running = False
            return False

        # 过滤可用服务器（响应时间 <= max_fail_time）
        available_servers = [
            (server, score) for server, score in all_scores.items() if score <= self.max_fail_time
        ]

        if not available_servers:
            self.logger.error(
                f"❌ 测速完成，但没有可用服务器（全部响应时间 > {self.max_fail_time}秒）"
            )
            self._running = False
            return False

        # 按响应时间排序（从小到大）
        available_servers.sort(key=lambda x: x[1])
        self._sorted_servers = [server for server, _ in available_servers]

        elapsed = time.time() - start_time

        self._running = True
        self._start_time = datetime.now()

        # 输出统计信息
        self.logger.info("=" * 60)
        self.logger.info("✅ 多进程测速完成！")
        self.logger.info("   总耗时: %.0fms", elapsed * 1000)
        self.logger.info("   测试服务器: %d个", len(all_scores))
        self.logger.info("   可用服务器: %d个", len(available_servers))
        self.logger.info(
            "   最快服务器: %s:%d", self._sorted_servers[0][0], self._sorted_servers[0][1]
        )
        if len(self._sorted_servers) >= 3:
            self.logger.info(
                "   Top3: %s, %s, %s",
                self._sorted_servers[0][0],
                self._sorted_servers[1][0],
                self._sorted_servers[2][0],
            )
        self.logger.info("=" * 60)

        # 推送服务器状态更新事件
        self._push_server_status_event()

        return True

    @staticmethod
    def _test_servers_in_process(
        process_id: int,
        servers: List[Tuple[str, int]],
        shared_results: Dict,
        test_timeout: float,
        max_fail_time: float,
    ):
        """
        在子进程中运行服务器测速（静态方法）

        Args:
            process_id: 进程ID
            servers: 要测试的服务器列表
            shared_results: 共享内存字典，存储测速结果
            test_timeout: 单个服务器测试超时
            max_fail_time: 最大失败时间
        """
        import logging

        # 为子进程设置日志
        logger = logging.getLogger(f"ServerTest-{process_id}")

        async def run_tests():
            """异步测速任务"""
            try:
                logger.info("[进程%d] 开始测速 %d 个服务器", process_id + 1, len(servers))

                # 创建智能IP池
                pool = AsyncSmartIPPool(
                    servers=servers,
                    update_interval=600.0,  # 不需要后台更新
                    test_timeout=test_timeout,
                    max_fail_time=max_fail_time,
                )

                # 执行测速（使用公开接口）
                scores = await pool.test_once()

                # 保存结果到共享内存
                success_count = 0
                for server, score in scores.items():
                    shared_results[server] = score
                    if score <= max_fail_time:
                        success_count += 1

                logger.info(
                    "[进程%d] 测速完成: 测试 %d 个, 可用 %d 个",
                    process_id + 1,
                    len(servers),
                    success_count,
                )

            except Exception as e:
                logger.error("[进程%d] 测速异常: %s", process_id + 1, e, exc_info=True)

        # 创建新事件循环（每个进程独立）
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(run_tests())
        finally:
            loop.close()

    def stop(self):
        """
        停止服务器池管理器

        在应用关闭时调用。
        """
        if not self._running:
            return

        try:
            self.logger.info("正在停止服务器池管理器...")
            self._running = False

            # 清理测速进程
            if self._processes:
                self.logger.info("清理测速进程...")
                for p in self._processes:
                    if p.is_alive():
                        p.terminate()
                        p.join(timeout=2)
                self._processes.clear()

            self.logger.info("服务器池管理器已停止")

        except Exception as e:
            self.logger.error("停止服务器池管理器失败: %s", e, exc_info=True)

    # ==================== 公共接口 ====================

    def get_servers(self, count: Optional[int] = None) -> List[Tuple[str, int]]:
        """
        获取排序后的服务器列表（保持原顺序）

        Args:
            count: 返回的服务器数量，None表示返回所有

        Returns:
            按速度排序的服务器列表 [(ip, port), ...]

        Raises:
            RuntimeError: 服务器池未运行或获取失败
        """
        # 🔧 自动初始化：如果未运行，尝试启动
        if not self._running:
            self.logger.info("服务器池未初始化，正在自动启动...")
            self.start()

        if not self._running:
            error_msg = "服务器池缓存不可用！\n请在系统管理中点击'测速服务器'按钮重新测速。"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        if not self._sorted_servers:
            error_msg = "服务器列表为空！\n请在系统管理中点击'测速服务器'按钮进行测速。"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        return self._sorted_servers[:count] if count else self._sorted_servers

    def get_servers_shuffled(self, count: Optional[int] = None) -> List[Tuple[str, int]]:
        """
        获取打乱顺序的服务器列表（推荐用于下载）

        每次调用都会重新打乱顺序，实现负载均衡。

        Args:
            count: 返回的服务器数量，None表示返回所有

        Returns:
            随机顺序的服务器列表 [(ip, port), ...]

        Raises:
            RuntimeError: 服务器池缓存不可用
        """
        if not self._running or not self._sorted_servers:
            # 检查缓存是否失效
            if self._cache_date:
                from ..cache_manager import DailyCacheManager

                if not DailyCacheManager.is_cache_valid(self._cache_date):
                    error_msg = (
                        f"服务器池缓存已过期（生成日期：{self._cache_date}）！\n"
                        "为保证下载质量，请重新测速。\n\n"
                        "操作步骤：\n"
                        "1. 打开'系统管理'模块\n"
                        "2. 点击'测速服务器'按钮\n"
                        "3. 等待测速完成（约7秒）"
                    )
                else:
                    error_msg = (
                        "服务器池缓存不可用！\n\n"
                        "操作步骤：\n"
                        "1. 打开'系统管理'模块\n"
                        "2. 点击'测速服务器'按钮\n"
                        "3. 等待测速完成（约7秒）"
                    )
            else:
                error_msg = (
                    "服务器池缓存不存在，无法下载数据！\n\n"
                    "请点击'立即测速'按钮进行服务器测速。\n\n"
                    "操作步骤：\n"
                    "1. 打开'系统管理'模块\n"
                    "2. 点击'测速服务器'按钮\n"
                    "3. 等待测速完成（约7秒）"
                )

            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 打乱顺序（每次调用都重新打乱）
        servers = self._sorted_servers.copy()
        random.shuffle(servers)

        return servers[:count] if count else servers

    def get_servers_with_standby(self, standby_count: int = 30) -> Dict[str, Any]:
        """
        获取分层服务器列表：热备服务器 + 乱序服务器

        热备服务器从不同证券公司中选择最快的服务器，用于两段式下载的第二阶段。

        Args:
            standby_count: 热备服务器数量（默认30个）

        Returns:
            {
                "standby": [(ip, port), ...],  # 热备服务器（每个证券公司最快1个）
                "regular": [(ip, port), ...],  # 剩余乱序服务器
                "broker_map": {(ip, port): "券商名", ...}  # 服务器到券商的映射
            }

        Raises:
            RuntimeError: 服务器池未运行或获取失败
        """
        # 检查服务器池状态
        if not self._running or not self._sorted_servers:
            error_msg = "服务器池缓存不可用！请先测速服务器。"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 1. 从 BROKER_SERVERS_7709 构建券商映射
        broker_map = self._build_broker_map()

        # 2. 按券商分组已测速服务器
        broker_groups = self._group_servers_by_broker(broker_map)

        # 3. 每个券商选最快1个，最多选standby_count个
        standby_servers = self._select_standby_from_brokers(broker_groups, standby_count)

        # 4. 剩余服务器作为regular池
        standby_set = set(standby_servers)
        regular_servers = [s for s in self._sorted_servers if s not in standby_set]

        # 5. 打乱regular服务器顺序
        random.shuffle(regular_servers)

        self.logger.info("分层服务器分配完成:")
        self.logger.info(
            "  热备服务器: %d 个（来自 %d 个不同券商）",
            len(standby_servers),
            len(set(broker_map.get(s, "未知") for s in standby_servers)),
        )
        self.logger.info("  乱序服务器: %d 个", len(regular_servers))

        return {"standby": standby_servers, "regular": regular_servers, "broker_map": broker_map}

    def _build_broker_map(self) -> Dict[Tuple[str, int], str]:
        """
        从 BROKER_SERVERS_7709 构建服务器到券商的映射

        Returns:
            {(ip, port): "券商名", ...}
        """
        broker_map = {}
        for broker_name, ip, port in BROKER_SERVERS_7709:
            broker_map[(ip, port)] = broker_name
        return broker_map

    def _group_servers_by_broker(
        self, broker_map: Dict[Tuple[str, int], str]
    ) -> Dict[str, List[Tuple[str, int]]]:
        """
        按券商分组已测速服务器

        Args:
            broker_map: 服务器到券商的映射

        Returns:
            {券商名: [服务器列表], ...}
        """
        broker_groups: Dict[str, List[Tuple[str, int]]] = {}

        for server in self._sorted_servers:
            broker = broker_map.get(server, "未知")
            if broker not in broker_groups:
                broker_groups[broker] = []
            broker_groups[broker].append(server)

        self.logger.debug("券商分组完成: %d 个券商", len(broker_groups))
        return broker_groups

    def _select_standby_from_brokers(
        self, broker_groups: Dict[str, List[Tuple[str, int]]], standby_count: int
    ) -> List[Tuple[str, int]]:
        """
        从每个券商中选择最快的服务器作为热备

        Args:
            broker_groups: 按券商分组的服务器
            standby_count: 需要的热备服务器数量

        Returns:
            热备服务器列表
        """
        standby_servers = []

        # 每个券商选最快的1个（第一个就是最快的，因为已排序）
        for broker, servers in broker_groups.items():
            if len(standby_servers) >= standby_count:
                break
            if servers:  # 确保有服务器
                standby_servers.append(servers[0])
                self.logger.debug(
                    "选择热备服务器: %s - %s:%d", broker, servers[0][0], servers[0][1]
                )

        self.logger.info(
            "热备服务器选择完成: %d/%d 个（实际可用券商数）", len(standby_servers), standby_count
        )

        return standby_servers

    def get_best_server(self) -> Tuple[str, int]:
        """
        获取最快的服务器

        Returns:
            最快的服务器 (ip, port)

        Raises:
            RuntimeError: 服务器池未运行或获取失败
        """
        if not self._running:
            error_msg = "服务器池未运行！请确保在应用启动时调用了 server_pool_manager.start()"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        if not self._sorted_servers:
            error_msg = "服务器列表为空，测速可能失败"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        return self._sorted_servers[0]

    def get_stats(self) -> Dict:
        """
        获取服务器池统计信息

        Returns:
            统计字典:
            {
                "total": 总服务器数,
                "available": 可用服务器数,
                "unavailable": 不可用服务器数,
                "running": 是否运行中,
                "uptime": 运行时长（秒）,
                "mode": "multiprocess"
            }
        """
        stats = {
            "running": self._running,
            "uptime": 0,
            "total": self.server_count,
            "available": len(self._sorted_servers),
            "unavailable": self.server_count - len(self._sorted_servers),
            "mode": "multiprocess",
        }

        # 计算运行时长
        if self._start_time:
            stats["uptime"] = (datetime.now() - self._start_time).total_seconds()

        return stats

    def is_running(self) -> bool:
        """
        检查服务器池是否运行中并有可用服务器

        Returns:
            bool: 是否运行中且有可用服务器
        """
        return self._running and len(self._sorted_servers) > 0

    def _push_server_status_event(self):
        """推送服务器状态更新事件（vnpy事件）"""
        try:
            from vnpy.event import Event
            from backend.core.base import get_event_engine

            event_engine = get_event_engine()
            if not event_engine:
                self.logger.debug("事件引擎不可用，跳过状态推送")
                return

            # 构建事件数据
            event_data = {
                "available": len(self._sorted_servers),
                "total": self.server_count,
                "status": "available" if self._running else "stopped",
                "timestamp": datetime.now().isoformat(),
                "cache_date": self._cache_date,
            }

            event = Event("EVENT_SERVER_POOL_STATUS", event_data)
            event_engine.put(event)

            self.logger.info(
                "📢 推送服务器状态事件: %d/%d 可用", event_data["available"], event_data["total"]
            )
        except Exception as e:
            self.logger.warning("推送服务器状态失败: %s", e)

    # ==================== 缓存管理 ====================

    def load_server_cache(self) -> Tuple[Optional[List[Tuple[str, int]]], Optional[str], bool]:
        """
        加载服务器池缓存

        Returns:
            Tuple[servers, cache_date, is_valid]:
            - servers: 服务器列表（None表示不存在）
            - cache_date: 缓存日期
            - is_valid: 是否有效
        """
        try:
            from ..cache_manager import DailyCacheManager

            data, cache_date, is_valid = DailyCacheManager.load_with_validation(
                self._cache_file, validate_date=True
            )

            if data:
                # 数据格式：[[ip, port], ...]
                servers = [tuple(server) for server in data]
                return servers, cache_date, is_valid

            return None, None, False

        except Exception as e:
            self.logger.error("加载服务器池缓存失败: %s", e, exc_info=True)
            return None, None, False

    def save_server_cache(self, servers: List[Tuple[str, int]]) -> bool:
        """
        保存服务器池缓存

        Args:
            servers: 服务器列表

        Returns:
            bool: 是否保存成功
        """
        try:
            from ..cache_manager import DailyCacheManager

            # 转换为可JSON序列化的格式
            server_data = [[ip, port] for ip, port in servers]

            # 保存缓存（带日期）
            success = DailyCacheManager.save_with_date(server_data, self._cache_file)

            if success:
                self._cache_date = DailyCacheManager.get_today()
                self.logger.info("服务器池缓存已保存: %d个服务器", len(servers))

            return success

        except Exception as e:
            self.logger.error("保存服务器池缓存失败: %s", e, exc_info=True)
            return False

    def is_cache_valid(self) -> bool:
        """
        检查缓存是否有效

        Returns:
            bool: True=有效，False=失效
        """
        try:
            from ..cache_manager import DailyCacheManager

            return DailyCacheManager.is_cache_valid(self._cache_date)
        except Exception:
            return False


# ==================== 全局单例实例 ====================

# 全局单例实例（供其他模块导入使用）
server_pool_manager = ServerPoolManager()


# ==================== 便捷函数 ====================


def get_best_servers(count: int = 10) -> List[Tuple[str, int]]:
    """
    获取最快的N个服务器（便捷函数）

    Args:
        count: 返回的服务器数量

    Returns:
        服务器列表 [(ip, port), ...]
    """
    return server_pool_manager.get_servers(count=count)


def get_best_server() -> Optional[Tuple[str, int]]:
    """
    获取最快的服务器（便捷函数）

    Returns:
        最快的服务器 (ip, port)
    """
    return server_pool_manager.get_best_server()


def get_all_servers() -> List[Tuple[str, int]]:
    """
    获取所有排序后的服务器（便捷函数）

    Returns:
        服务器列表 [(ip, port), ...]
    """
    return server_pool_manager.get_servers()


def get_verified_servers_random(count: Optional[int] = None) -> List[Tuple[str, int]]:
    """
    获取已验证的服务器（随机排列）- 便捷函数

    此函数从constants.py的BROKER_SERVERS_7709获取服务器列表，
    并随机打乱顺序。如果server_pool_manager已运行且有测速结果，
    则优先使用测速后的服务器（保持质量优先但随机排列）。

    Args:
        count: 需要的服务器数量，None表示返回所有

    Returns:
        随机排列的服务器列表 [(ip, port), ...]

    使用场景:
        - 大规模下载任务需要随机分配服务器
        - 避免所有客户端同时访问相同服务器
        - 负载均衡
    """
    import random
    from backend.infrastructure.tdx_asyncio.constants import BROKER_SERVERS_7709

    # 尝试获取已测速的服务器
    if server_pool_manager.is_running():
        try:
            # 如果服务器池已运行，获取已测速的服务器
            servers = server_pool_manager.get_servers()
            # 随机打乱已测速的服务器
            servers_copy = servers.copy()
            random.shuffle(servers_copy)
            servers = servers_copy

            if count is not None:
                servers = servers[:count]

            return servers
        except Exception:
            # 如果获取失败，使用fallback方案
            pass

    # Fallback: 从constants.py获取所有服务器并随机打乱
    servers = [(ip, port) for name, ip, port in BROKER_SERVERS_7709]
    random.shuffle(servers)

    if count is not None:
        servers = servers[:count]

    return servers


# ==================== 自适应下载配置 ====================


class ServerPoolTestTask(NetworkTask):
    """服务器池测速任务

    用于多进程并行测速通达信服务器。
    """

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name="server_pool_test",
            task_type=TaskType.NETWORK,
            resource_profile=ResourceProfile.NETWORK_IO_INTENSIVE,
            critical_metrics=[
                "network_speed",
                "context_switches_per_sec",
                "cpu_percent",
            ],
            estimated_duration=10,  # 预计10秒
            estimated_memory_mb=30,  # 约30MB（3进程×50协程×0.2MB）
            estimated_connections=150,  # 默认3进程×50协程
        )

    def execute(self, config: Dict[str, Any]) -> Any:
        """执行服务器池测速

        注意：实际测速由ServerPoolManager内部执行，这里只是占位方法。
        """
        # 这个方法不会被直接调用，因为ServerPoolManager有自己的start()方法
        pass


class AdaptiveDownloadConfig:
    """
    自适应下载配置计算器（已弃用）

    注意：calculate_optimal_config方法已移除，请使用LoadBalancer代替：

    旧用法：
        config = AdaptiveDownloadConfig.calculate_optimal_config(task_count=5000)

    新用法：
        from .load_balancer import LoadBalancer
        task = KlineDownloadTask("kline_download")
        load_balancer = LoadBalancer(event_engine)
        config = load_balancer.get_optimal_config(task)

    保留方法：
    - get_verified_servers: 获取已测速的服务器列表
    - get_download_config_summary: 生成配置摘要字符串
    """

    @staticmethod
    def calculate_optimal_config(
        task_count: Optional[int] = None,
        min_processes: int = 4,
        max_processes: Optional[int] = None,
        min_coroutines_per_process: int = 30,
        max_coroutines_per_process: int = 40,
        memory_per_connection_mb: float = 0.5,  # 每个连接约0.5MB
    ) -> Dict:
        """
        计算最优配置（已弃用，现使用LoadBalancer）

        这是一个兼容性包装方法，内部调用LoadBalancer获取配置。
        建议新代码直接使用LoadBalancer。

        Args:
            task_count: 任务数量（用于小任务优化，None表示大任务场景）
            min_processes: 最小进程数（已忽略）
            max_processes: 最大进程数（已忽略）
            min_coroutines_per_process: 每进程最小协程数（已忽略）
            max_coroutines_per_process: 每进程最大协程数（已忽略）
            memory_per_connection_mb: 每个连接的内存消耗（已忽略）

        Returns:
            Dict 包含：
            - cpu_cores: CPU核心数
            - available_memory_gb: 可用内存（GB）
            - available_servers: 可用服务器数量
            - processes: 推荐进程数
            - coroutines_per_process: 每进程协程数
            - total_connections: 总连接数
            - task_count: 任务数量（如果提供）
            - reason: 配置原因说明
        """
        logger = logging.getLogger(__name__)
        logger.warning(
            "AdaptiveDownloadConfig.calculate_optimal_config已弃用，" "建议使用LoadBalancer"
        )

        # 使用LoadBalancer获取配置
        try:
            # ✅ 架构修复后：使用Qt原生线程体系，LoadBalancer可直接使用EventEngine
            # 不再需要线程检测，因为所有代码都在Qt线程体系中运行

            # 创建ServerPoolTestTask（而非直接实例化抽象类NetworkTask）
            task = ServerPoolTestTask("legacy_download")
            if task_count:
                # 更新预估连接数
                task.metrics.estimated_connections = min(task_count * 2, 640)

            load_balancer = LoadBalancer(event_engine=None)
            lb_config = load_balancer.get_optimal_config(task)

            # 转换为旧格式
            cpu_cores = multiprocessing.cpu_count()
            if HAS_PSUTIL:
                available_memory_gb = psutil.virtual_memory().available / (1024**3)
            else:
                available_memory_gb = 4.0

            available_servers = len(BROKER_SERVERS_7709)

            # 构造兼容格式的配置字典
            config = {
                "cpu_cores": cpu_cores,
                "available_memory_gb": round(available_memory_gb, 2),
                "available_servers": available_servers,
                "processes": lb_config.get("processes", 4),
                "coroutines_per_process": lb_config.get("coroutines_per_process", 40),
                "total_connections": lb_config.get("total_connections", 160),
                "estimated_memory_mb": lb_config.get("estimated_memory_mb", 80.0),
                "task_count": task_count,
                "reason": lb_config.get("reason", "基于LoadBalancer动态配置"),
            }

            logger.info("=" * 60)
            logger.info("【自适应配置】计算完成（使用LoadBalancer）")
            logger.info("  CPU核心: %d", cpu_cores)
            logger.info("  可用内存: %.2f GB", available_memory_gb)
            logger.info("  可用服务器: %d", available_servers)
            if task_count is not None:
                logger.info("  任务数量: %d", task_count)
            logger.info("  推荐进程数: %d", config["processes"])
            logger.info("  每进程协程: %d", config["coroutines_per_process"])
            logger.info("  总连接数: %d", config["total_connections"])
            logger.info("  预计内存: %.2f MB", config["estimated_memory_mb"])
            logger.info("  压力评分: %.1f/100", lb_config.get("pressure_score", 0))
            logger.info("  瓶颈维度: %s", lb_config.get("bottleneck", "unknown"))
            logger.info("=" * 60)

            return config

        except Exception as e:
            logger.error(f"LoadBalancer配置失败，使用默认值: {e}")
            # 降级方案：返回保守的默认配置
            cpu_cores = multiprocessing.cpu_count()
            if HAS_PSUTIL:
                available_memory_gb = psutil.virtual_memory().available / (1024**3)
            else:
                available_memory_gb = 4.0

            available_servers = len(BROKER_SERVERS_7709)

            return {
                "cpu_cores": cpu_cores,
                "available_memory_gb": round(available_memory_gb, 2),
                "available_servers": available_servers,
                "processes": 4,
                "coroutines_per_process": 40,
                "total_connections": 160,
                "estimated_memory_mb": 80.0,
                "task_count": task_count,
                "reason": "默认配置（LoadBalancer失败降级）",
            }

    @staticmethod
    def get_verified_servers(
        count: Optional[int] = None, shuffle: bool = True
    ) -> List[Tuple[str, int]]:
        """
        获取已测速的可用服务器并随机打乱顺序

        优先使用server_pool_manager的测速缓存，如果缓存不可用则抛出异常。

        Args:
            count: 需要的服务器数量，None表示返回所有
            shuffle: 是否随机打乱顺序（默认True）

        Returns:
            服务器列表 [(ip, port), ...]

        Raises:
            RuntimeError: 如果server_pool_manager未初始化或缓存失效
        """
        logger = logging.getLogger(__name__)

        # ✅ 优先使用server_pool_manager的测速缓存
        try:
            if server_pool_manager.is_running() and server_pool_manager._sorted_servers:
                servers = server_pool_manager._sorted_servers.copy()
                logger.debug("使用server_pool_manager的测速缓存: %d个可用服务器", len(servers))
            else:
                # ❌ 缓存不可用，抛出异常强制用户手动测速
                raise RuntimeError(
                    "服务器池缓存不可用！请手动测速：\n"
                    "1. 打开数据中心\n"
                    "2. 点击【重新测速】按钮\n"
                    "3. 等待测速完成后重试"
                )
        except RuntimeError:
            raise
        except Exception as e:
            logger.error("获取服务器池缓存失败: %s", e)
            raise RuntimeError(
                "服务器池缓存异常！请手动测速：\n"
                "1. 打开数据中心\n"
                "2. 点击【重新测速】按钮\n"
                "3. 等待测速完成后重试"
            )

        # 随机打乱顺序
        if shuffle:
            random.shuffle(servers)

        # 返回指定数量
        if count is not None:
            servers = servers[:count]

        logger.info("获取到%d个已测速服务器（随机排列=%s）", len(servers), shuffle)

        return servers

    @staticmethod
    def get_download_config_summary(config: Dict) -> str:
        """
        生成配置摘要字符串（用于日志和UI显示）

        Args:
            config: calculate_optimal_config()返回的配置字典

        Returns:
            格式化的配置摘要
        """
        summary = (
            f"进程数: {config['processes']} | "
            f"每进程协程: {config['coroutines_per_process']} | "
            f"总连接: {config['total_connections']} | "
            f"服务器: {config['available_servers']}"
        )
        return summary


# ==================== 便捷函数 ====================


def get_adaptive_config() -> Dict:
    """获取自适应配置（快捷方式）"""
    return AdaptiveDownloadConfig.calculate_optimal_config()


def get_adaptive_config_for_tasks(task_count: int) -> Dict:
    """根据任务数量获取自适应配置"""
    return AdaptiveDownloadConfig.calculate_optimal_config(task_count=task_count)


def get_random_servers(count: Optional[int] = None) -> List[Tuple[str, int]]:
    """获取随机排列的服务器（快捷方式）"""
    return AdaptiveDownloadConfig.get_verified_servers(count=count, shuffle=True)
