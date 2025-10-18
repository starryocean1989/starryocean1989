# -*- coding: utf-8 -*-
"""
服务器池管理器

多进程并行测速通达信服务器，为 data_module_vnpy 提供最优服务器连接。

特性：
- 多进程并行测速（充分利用多核CPU，5-10秒完成）
- 自动排序和故障服务器剔除
- 线程安全
- 统计信息查询
"""

import asyncio
import logging
import math
import threading
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from multiprocessing import Process, Manager

from backend.infrastructure.tdx_asyncio import (
    AsyncSmartIPPool,
    HQ_HOSTS_ALL,
)

from .config import config_manager


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

        # 多进程相关
        self._processes: List[Process] = []
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

        num_processes = math.ceil(self.server_count / self.max_coroutines_per_process)
        self.logger.info("服务器池管理器初始化完成（多进程模式）")
        self.logger.info(f"配置: {self.server_count}个服务器 → {num_processes}个进程")

    def start(self) -> bool:
        """
        启动服务器池管理器（多进程模式）

        在应用启动时调用一次，使用多进程并行测速所有服务器。
        注意：此方法会同步等待测速完成（通常5-10秒）

        Returns:
            bool: 是否启动成功（返回True时测速已完成）
        """
        if self._running:
            self.logger.warning("服务器池管理器已在运行")
            return True

        try:
            return self._start_multiprocess()
        except Exception as e:
            self.logger.error(f"启动服务器池管理器失败: {e}", exc_info=True)
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

        # 获取服务器列表
        all_servers = [(h[1], h[2]) for h in HQ_HOSTS_ALL[: self.server_count]]

        # 按每进程50个服务器分配
        server_chunks = []
        for i in range(0, len(all_servers), self.max_coroutines_per_process):
            chunk = all_servers[i : i + self.max_coroutines_per_process]
            server_chunks.append(chunk)

        num_processes = len(server_chunks)

        self.logger.info("正在启动服务器池管理器（多进程模式）...")
        self.logger.info("📊 服务器分配方案：")
        for i, chunk in enumerate(server_chunks):
            self.logger.info("   进程%d: %d个服务器", i + 1, len(chunk))

        # 创建共享内存存储结果
        manager = Manager()
        shared_results = manager.dict()

        # 启动测速进程
        self._processes = []
        for i, chunk in enumerate(server_chunks):
            p = Process(
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
            self.logger.info(f"🚀 进程{i+1}已启动（PID: {p.pid}）")

        # 等待所有进程完成
        self.logger.info(f"⏳ 等待{num_processes}个进程完成测速...")
        for i, p in enumerate(self._processes):
            p.join()
            self.logger.info(f"✅ 进程{i+1}完成")

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
                logger.info(f"[进程{process_id+1}] 开始测速 {len(servers)} 个服务器")

                # 创建智能IP池
                pool = AsyncSmartIPPool(
                    servers=servers,
                    update_interval=600.0,  # 不需要后台更新
                    test_timeout=test_timeout,
                    max_fail_time=max_fail_time,
                )

                # 执行测速（不启动后台监控）
                await pool._test_all_servers()
                await pool._sort_servers()

                # 保存结果到共享内存
                success_count = 0
                for server, score in pool.server_scores.items():
                    shared_results[server] = score
                    if score <= max_fail_time:
                        success_count += 1

                logger.info(
                    f"[进程{process_id+1}] 测速完成: "
                    f"测试 {len(servers)} 个, 可用 {success_count} 个"
                )

            except Exception as e:
                logger.error(f"[进程{process_id+1}] 测速异常: {e}", exc_info=True)

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
            self.logger.error(f"停止服务器池管理器失败: {e}", exc_info=True)

    # ==================== 公共接口 ====================

    def get_servers(self, count: Optional[int] = None) -> List[Tuple[str, int]]:
        """
        获取排序后的服务器列表

        Args:
            count: 返回的服务器数量，None表示返回所有

        Returns:
            按速度排序的服务器列表 [(ip, port), ...]

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

        return self._sorted_servers[:count] if count else self._sorted_servers

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
            }

            event = Event("EVENT_SERVER_POOL_STATUS", event_data)
            event_engine.put(event)

            self.logger.info(
                "📢 推送服务器状态事件: %d/%d 可用", event_data["available"], event_data["total"]
            )
        except Exception as e:
            self.logger.warning("推送服务器状态失败: %s", e)


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
