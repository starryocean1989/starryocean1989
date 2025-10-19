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
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from multiprocessing import Process, Manager

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from backend.infrastructure.tdx_asyncio import (
    AsyncSmartIPPool,
    HQ_HOSTS_ALL,
)
from backend.infrastructure.tdx_asyncio.constants import BROKER_SERVERS_7709

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

                # 执行测速（使用公开接口）
                scores = await pool.test_once()

                # 保存结果到共享内存
                success_count = 0
                for server, score in scores.items():
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


class AdaptiveDownloadConfig:
    """
    自适应下载配置计算器

    根据系统资源和可用服务器数量，自动计算最优配置：
    - 进程数
    - 每进程协程数
    - 总连接数
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
        计算最优配置

        Args:
            task_count: 任务数量（用于小任务优化，None表示大任务场景）
            min_processes: 最小进程数（默认4）
            max_processes: 最大进程数（None表示不限制）
            min_coroutines_per_process: 每进程最小协程数（默认30）
            max_coroutines_per_process: 每进程最大协程数（默认40）
            memory_per_connection_mb: 每个连接的内存消耗（MB）

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

        # 1. 获取系统资源
        cpu_cores = multiprocessing.cpu_count()

        if HAS_PSUTIL:
            available_memory_gb = psutil.virtual_memory().available / (1024**3)
        else:
            # 没有psutil，假设有4GB可用内存
            available_memory_gb = 4.0
            logger.warning("未安装psutil，假设可用内存为4GB")

        # 2. 获取可用服务器数量
        available_servers = len(BROKER_SERVERS_7709)

        # 3. 计算进程数
        # 原则：不超过CPU核心数，同时考虑服务器数量
        max_processes_by_cpu = cpu_cores
        max_processes_by_servers = max(
            min_processes, available_servers // max_coroutines_per_process
        )

        if max_processes is not None:
            processes = min(max_processes_by_cpu, max_processes_by_servers, max_processes)
        else:
            processes = min(max_processes_by_cpu, max_processes_by_servers)

        processes = max(processes, min_processes)  # 至少min_processes个进程

        # 4. 计算每进程协程数
        # 原则：充分利用可用服务器，但不超过上限
        optimal_coroutines = available_servers // processes
        coroutines_per_process = min(
            max(optimal_coroutines, min_coroutines_per_process), max_coroutines_per_process
        )

        # 5. 计算总连接数
        total_connections = processes * coroutines_per_process

        # 确保不超过可用服务器数
        if total_connections > available_servers:
            # 调整：减少协程数以匹配服务器数量
            coroutines_per_process = available_servers // processes
            total_connections = processes * coroutines_per_process
            logger.warning(
                f"连接数({total_connections})已调整以匹配可用服务器数({available_servers})"
            )

        # 6. 根据任务数量优化配置（新增）
        if task_count is not None and task_count > 0:
            # 小任务优化：避免启动过多worker
            if task_count <= 10:
                # 1-10个任务：单进程处理
                processes = 1
                coroutines_per_process = min(task_count, max_coroutines_per_process)
                total_connections = coroutines_per_process
                logger.info(f"小任务优化: {task_count}个任务 → 1进程×{coroutines_per_process}协程")

            elif task_count <= 100:
                # 11-100个任务：动态计算进程数
                optimal_processes = max(1, min(processes, (task_count + 29) // 30))
                processes = optimal_processes
                coroutines_per_process = min(
                    (task_count + processes - 1) // processes, max_coroutines_per_process
                )
                total_connections = processes * coroutines_per_process
                logger.info(
                    f"中等任务优化: {task_count}个任务 → {processes}进程×{coroutines_per_process}协程"
                )

            else:
                # 100+任务：使用标准配置，但不超过任务数
                if total_connections > task_count:
                    # 缩减到略大于任务数（预留20%冗余）
                    optimal_connections = int(task_count * 1.2)
                    processes = max(
                        min_processes, optimal_connections // max_coroutines_per_process
                    )
                    coroutines_per_process = optimal_connections // processes
                    total_connections = processes * coroutines_per_process
                    logger.info(
                        f"大任务优化: {task_count}个任务 → 缩减至{total_connections}连接 "
                        f"({processes}进程×{coroutines_per_process}协程)"
                    )

        # 7. 内存检查
        estimated_memory_mb = total_connections * memory_per_connection_mb
        estimated_memory_gb = estimated_memory_mb / 1024

        if estimated_memory_gb > available_memory_gb * 0.8:  # 不超过80%可用内存
            # 内存不足，减少连接数
            safe_connections = int((available_memory_gb * 0.8 * 1024) / memory_per_connection_mb)
            coroutines_per_process = safe_connections // processes
            total_connections = processes * coroutines_per_process
            logger.warning(f"内存限制：调整连接数至{total_connections}以确保系统稳定")

        # 8. 生成配置说明
        reasons = []
        reasons.append(f"基于{cpu_cores}核CPU")
        reasons.append(f"{available_memory_gb:.1f}GB可用内存")
        reasons.append(f"{available_servers}个可用服务器")

        if task_count is not None:
            reasons.append(f"{task_count}个任务")

        if total_connections < available_servers:
            reasons.append(f"使用{total_connections}/{available_servers}个服务器")
        else:
            reasons.append(f"充分利用所有{available_servers}个服务器")

        reason = "，".join(reasons)

        config = {
            "cpu_cores": cpu_cores,
            "available_memory_gb": round(available_memory_gb, 2),
            "available_servers": available_servers,
            "processes": processes,
            "coroutines_per_process": coroutines_per_process,
            "total_connections": total_connections,
            "estimated_memory_mb": round(estimated_memory_mb, 2),
            "task_count": task_count,
            "reason": reason,
        }

        logger.info("=" * 60)
        logger.info("【自适应配置】计算完成")
        logger.info("  CPU核心: %d", cpu_cores)
        logger.info("  可用内存: %.2f GB", available_memory_gb)
        logger.info("  可用服务器: %d", available_servers)
        if task_count is not None:
            logger.info("  任务数量: %d", task_count)
        logger.info("  推荐进程数: %d", processes)
        logger.info("  每进程协程: %d", coroutines_per_process)
        logger.info("  总连接数: %d", total_connections)
        logger.info("  预计内存: %.2f MB", estimated_memory_mb)
        logger.info("=" * 60)

        return config

    @staticmethod
    def get_verified_servers(
        count: Optional[int] = None, shuffle: bool = True
    ) -> List[Tuple[str, int]]:
        """
        从constants.py获取已验证的7709服务器并随机打乱顺序

        Args:
            count: 需要的服务器数量，None表示返回所有
            shuffle: 是否随机打乱顺序（默认True）

        Returns:
            服务器列表 [(ip, port), ...]
        """
        logger = logging.getLogger(__name__)

        # 从BROKER_SERVERS_7709提取IP和端口
        # BROKER_SERVERS_7709格式: [(name, ip, port), ...]
        servers = [(ip, port) for name, ip, port in BROKER_SERVERS_7709]

        # 随机打乱顺序
        if shuffle:
            servers_copy = servers.copy()
            random.shuffle(servers_copy)
            servers = servers_copy

        # 返回指定数量
        if count is not None:
            servers = servers[:count]

        logger.info(f"获取到{len(servers)}个已验证服务器（随机排列={shuffle}）")

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
