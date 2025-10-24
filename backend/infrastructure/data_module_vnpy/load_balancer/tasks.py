# -*- coding: utf-8 -*-
"""
任务基类和具体任务类

定义了任务的抽象接口和常见任务类型。所有需要智能负载管理的任务都应继承这些基类。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List


class TaskType(Enum):
    """任务类型"""

    NETWORK = "network"  # 网络请求任务
    LOCAL_PROCESSING = "local"  # 本地数据处理任务


class ResourceProfile(Enum):
    """资源特征类型"""

    NETWORK_IO_INTENSIVE = "network_io_intensive"
    DISK_IO_INTENSIVE = "disk_io_intensive"
    CPU_INTENSIVE = "cpu_intensive"
    MEMORY_INTENSIVE = "memory_intensive"
    MIXED = "mixed"


@dataclass
class TaskMetrics:
    """任务关键指标

    定义任务的资源需求和特征，用于LoadBalancer计算最优配置。

    Attributes:
        task_name: 任务名称（唯一标识）
        task_type: 任务类型（网络/本地处理）
        resource_profile: 资源特征类型
        critical_metrics: 关键瓶颈指标名称列表
        estimated_duration: 预计耗时（秒）
        estimated_memory_mb: 预计内存消耗（MB）
        estimated_connections: 预计网络连接数（仅网络任务）
        estimated_workers: 预计工作线程/进程数（仅本地任务）
    """

    task_name: str
    task_type: TaskType
    resource_profile: ResourceProfile
    critical_metrics: List[str]
    estimated_duration: float
    estimated_memory_mb: float
    estimated_connections: int = 0
    estimated_workers: int = 1


class BaseTask(ABC):
    """任务基类

    所有需要智能负载管理的任务都应继承此类。

    子类需要实现：
    - _define_metrics(): 定义任务的资源需求和特征
    - execute(): 执行任务（使用LoadBalancer提供的动态配置）
    """

    def __init__(self, name: str):
        """初始化任务

        Args:
            name: 任务名称（应该唯一）
        """
        self.name = name
        self.metrics = self._define_metrics()

    @abstractmethod
    def _define_metrics(self) -> TaskMetrics:
        """定义任务指标

        子类必须实现此方法，返回TaskMetrics对象描述任务特征。

        Returns:
            TaskMetrics对象
        """
        ...

    @abstractmethod
    def execute(self, config: Dict[str, Any]) -> Any:
        """执行任务

        子类必须实现此方法，使用LoadBalancer提供的动态配置执行任务。

        Args:
            config: LoadBalancer计算的动态配置字典
                网络任务包含：processes, coroutines_per_process, total_connections等
                本地任务包含：max_workers, batch_size, use_multiprocessing等

        Returns:
            任务执行结果
        """
        ...


class NetworkTask(BaseTask):
    """网络请求任务基类

    用于需要网络连接的任务，如：
    - 服务器池测速
    - K线数据批量下载
    - IPO日期下载
    - 品种列表获取
    - 实时行情轮询
    """

    def _define_metrics(self) -> TaskMetrics:
        """定义网络任务的默认指标

        子类应该重写此方法，提供更具体的指标。
        """
        return TaskMetrics(
            task_name=self.name,
            task_type=TaskType.NETWORK,
            resource_profile=ResourceProfile.NETWORK_IO_INTENSIVE,
            critical_metrics=[
                "network_speed",
                "packet_loss_rate",
                "concurrent_task_count",
            ],
            estimated_duration=0,
            estimated_memory_mb=0,
            estimated_connections=0,
        )


class LocalProcessingTask(BaseTask):
    """本地数据处理任务基类

    用于本地数据处理任务，如：
    - 数据质量扫描
    - 通达信本地文件读取
    - 数据预加载
    - 数据查询与融合
    """

    def _define_metrics(self) -> TaskMetrics:
        """定义本地处理任务的默认指标

        子类应该重写此方法，提供更具体的指标。
        """
        return TaskMetrics(
            task_name=self.name,
            task_type=TaskType.LOCAL_PROCESSING,
            resource_profile=ResourceProfile.DISK_IO_INTENSIVE,
            critical_metrics=[
                "disk_io_speed",
                "average_io_latency_ms",
                "cpu_percent",
            ],
            estimated_duration=0,
            estimated_memory_mb=0,
            estimated_workers=1,
        )
