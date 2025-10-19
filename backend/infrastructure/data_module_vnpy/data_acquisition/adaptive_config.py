# -*- coding: utf-8 -*-
"""
自适应下载配置模块

根据系统资源（CPU、内存）和可用服务器数量，
动态计算最优的下载配置参数。

版本: 1.0
更新: 2025-10-19
"""

import logging
import multiprocessing
import random
from typing import Dict, List, Tuple, Optional

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from backend.infrastructure.tdx_asyncio.constants import BROKER_SERVERS_7709


logger = logging.getLogger(__name__)


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
            "task_count": task_count,  # 新增
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


# 便捷函数
def get_adaptive_config() -> Dict:
    """获取自适应配置（快捷方式）"""
    return AdaptiveDownloadConfig.calculate_optimal_config()


def get_adaptive_config_for_tasks(task_count: int) -> Dict:
    """根据任务数量获取自适应配置（新增）"""
    return AdaptiveDownloadConfig.calculate_optimal_config(task_count=task_count)


def get_random_servers(count: Optional[int] = None) -> List[Tuple[str, int]]:
    """获取随机排列的服务器（快捷方式）"""
    return AdaptiveDownloadConfig.get_verified_servers(count=count, shuffle=True)
