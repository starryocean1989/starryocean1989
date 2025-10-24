# -*- coding: utf-8 -*-
"""
动态配置计算器

根据资源压力评估结果和任务特征，计算最优的并发配置。

配置策略：
- 网络任务：processes × coroutines_per_process = total_connections
- 本地任务：max_workers, batch_size, use_multiprocessing

考虑因素：
- 系统资源（CPU核心数、可用内存）
- 资源压力（缩放因子、瓶颈维度）
- 任务特征（预估连接数/工作数）
- 内存限制（每连接0.5MB，不超过可用内存30%）
"""

import logging
import multiprocessing as mp
from typing import Any, Dict

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from .tasks import BaseTask, NetworkTask, LocalProcessingTask, TaskType


class DynamicConfigCalculator:
    """动态配置计算器

    根据资源压力和任务特征，计算最优的并发配置参数。

    特性：
    - 基于任务类型（网络/本地）选择不同计算策略
    - 应用资源压力缩放因子
    - 根据瓶颈维度微调配置
    - 内存安全检查（防止OOM）
    """

    def __init__(self, evaluator):
        """初始化配置计算器

        Args:
            evaluator: ResourcePressureEvaluator实例
        """
        self.evaluator = evaluator
        self.logger = logging.getLogger(__name__)

    def calculate_for_task(self, task: BaseTask, pressure_eval: Dict[str, Any]) -> Dict[str, Any]:
        """为特定任务计算最优配置

        Args:
            task: 任务对象
            pressure_eval: 资源压力评估结果

        Returns:
            动态配置字典
        """
        scale_factor = pressure_eval["scale_factor"]
        bottleneck = pressure_eval["bottleneck"]

        # 根据任务类型选择计算策略
        if task.metrics.task_type == TaskType.NETWORK:
            if not isinstance(task, NetworkTask):
                self.logger.warning(f"任务{task.name}声明为网络任务但不是NetworkTask子类")
            base_config = self._calculate_network_task_config(
                task, scale_factor, bottleneck  # type: ignore
            )
        else:
            if not isinstance(task, LocalProcessingTask):
                self.logger.warning(f"任务{task.name}声明为本地任务但不是LocalProcessingTask子类")
            base_config = self._calculate_local_task_config(
                task, scale_factor, bottleneck  # type: ignore
            )

        # 添加压力评估信息
        base_config.update(
            {
                "pressure_score": pressure_eval["pressure_score"],
                "bottleneck": bottleneck,
                "scale_factor": scale_factor,
                "emergency": pressure_eval["emergency"],
                "reason": pressure_eval["reason"],
            }
        )

        return base_config

    def _calculate_network_task_config(
        self, task: NetworkTask, scale_factor: float, bottleneck: str
    ) -> Dict[str, Any]:
        """计算网络任务配置

        Args:
            task: 网络任务对象
            scale_factor: 并发缩放因子
            bottleneck: 瓶颈维度

        Returns:
            配置字典：{processes, coroutines_per_process, total_connections, estimated_memory_mb}
        """
        # 获取系统资源
        cpu_cores = mp.cpu_count()

        if HAS_PSUTIL:
            memory = psutil.virtual_memory()
            available_memory_gb = memory.available / (1024**3)
        else:
            available_memory_gb = 8.0  # 默认假设8GB
            self.logger.warning("psutil未安装，使用默认可用内存8GB")

        # 获取任务的预计连接数
        estimated_connections = task.metrics.estimated_connections

        if estimated_connections == 0:
            # 未预估，使用默认策略
            estimated_connections = min(cpu_cores * 40, 640)

        # 应用缩放因子
        target_connections = int(estimated_connections * scale_factor)
        target_connections = max(10, target_connections)  # 最少10个连接

        # 根据瓶颈类型调整
        if bottleneck == "network":
            # 网络瓶颈：减少连接数避免加重网络压力
            target_connections = int(target_connections * 0.7)
            self.logger.debug("检测到网络瓶颈，连接数减少至70%")
        elif bottleneck == "cpu":
            # CPU瓶颈：减少进程数，保持总连接数
            self.logger.debug("检测到CPU瓶颈，将减少进程数")

        # 计算进程数和协程数
        # 进程数：最少4个，最多16个，不超过CPU核心数
        if bottleneck == "cpu":
            processes = min(max(4, cpu_cores // 2), 16)
        else:
            processes = min(max(4, cpu_cores), 16)

        # 每进程协程数
        coroutines_per_process = max(10, target_connections // processes)

        # 重新计算实际连接数
        actual_connections = processes * coroutines_per_process

        # 内存限制检查
        estimated_memory_mb = actual_connections * 0.5  # 每连接0.5MB
        max_safe_memory_mb = available_memory_gb * 1024 * 0.3  # 最多使用30%可用内存

        if estimated_memory_mb > max_safe_memory_mb:
            # 内存不足，降低并发
            self.logger.warning(
                f"内存不足（预计{estimated_memory_mb:.1f}MB > "
                f"安全值{max_safe_memory_mb:.1f}MB），降低连接数"
            )
            actual_connections = int(max_safe_memory_mb / 0.5)
            coroutines_per_process = max(10, actual_connections // processes)
            estimated_memory_mb = actual_connections * 0.5

        config = {
            "processes": processes,
            "coroutines_per_process": coroutines_per_process,
            "total_connections": actual_connections,
            "estimated_memory_mb": round(estimated_memory_mb, 2),
        }

        self.logger.debug(
            f"网络任务配置: {processes}进程 × {coroutines_per_process}协程 = "
            f"{actual_connections}连接, 预计内存{estimated_memory_mb:.1f}MB"
        )

        return config

    def _calculate_local_task_config(
        self, task: LocalProcessingTask, scale_factor: float, bottleneck: str
    ) -> Dict[str, Any]:
        """计算本地处理任务配置

        Args:
            task: 本地处理任务对象
            scale_factor: 并发缩放因子
            bottleneck: 瓶颈维度

        Returns:
            配置字典：{max_workers, batch_size, use_multiprocessing}
        """
        # 获取系统资源
        cpu_cores = mp.cpu_count()

        if HAS_PSUTIL:
            # available_memory_gb暂未使用，保留用于未来优化
            # memory = psutil.virtual_memory()
            # available_memory_gb = memory.available / (1024**3)
            pass
        else:
            self.logger.warning("psutil未安装")

        # 获取任务预计工作数
        estimated_workers = task.metrics.estimated_workers

        if estimated_workers == 0:
            estimated_workers = min(cpu_cores, 16)

        # 应用缩放因子
        target_workers = int(estimated_workers * scale_factor)
        target_workers = max(1, min(target_workers, cpu_cores))

        # 根据瓶颈类型调整
        if bottleneck == "disk":
            # 磁盘瓶颈：减少并发避免加重I/O压力
            target_workers = int(target_workers * 0.6)
            batch_size = 50  # 减小批量大小
            self.logger.debug("检测到磁盘瓶颈，工作数减少至60%，批量大小50")
        elif bottleneck == "memory":
            # 内存瓶颈：减少批量大小
            batch_size = 50
            self.logger.debug("检测到内存瓶颈，批量大小减少至50")
        else:
            batch_size = 200

        # 是否使用多进程（工作数>8时使用）
        use_multiprocessing = target_workers > 8

        config = {
            "max_workers": target_workers,
            "batch_size": batch_size,
            "use_multiprocessing": use_multiprocessing,
        }

        self.logger.debug(
            f"本地任务配置: {target_workers}工作线程/进程, "
            f"批量{batch_size}, 多进程={use_multiprocessing}"
        )

        return config
