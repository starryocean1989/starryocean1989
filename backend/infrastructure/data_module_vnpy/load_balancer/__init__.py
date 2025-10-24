# -*- coding: utf-8 -*-
"""
统一负载均衡模块

提供智能负载管理，根据系统资源动态调整任务并发配置。

核心组件：
- LoadBalancer: 统一负载均衡器（单例）
- BaseTask, NetworkTask, LocalProcessingTask: 任务基类
- SystemMetricsMonitor: 系统监控指标获取器
- ResourcePressureEvaluator: 资源压力评估器
- DynamicConfigCalculator: 动态配置计算器

使用示例：
    from backend.infrastructure.data_module_vnpy.load_balancer import (
        LoadBalancer,
        NetworkTask,
        TaskMetrics,
        TaskType,
        ResourceProfile,
    )

    # 定义任务
    class MyTask(NetworkTask):
        def _define_metrics(self):
            return TaskMetrics(
                task_name="my_task",
                task_type=TaskType.NETWORK,
                resource_profile=ResourceProfile.NETWORK_IO_INTENSIVE,
                critical_metrics=["network_speed"],
                estimated_connections=100,
            )

        def execute(self, config):
            # 使用动态配置执行任务
            pass

    # 使用LoadBalancer
    load_balancer = LoadBalancer(event_engine)
    task = MyTask("my_task")
    config = load_balancer.get_optimal_config(task)
    result = task.execute(config)
"""

from .tasks import (
    BaseTask,
    NetworkTask,
    LocalProcessingTask,
    TaskType,
    ResourceProfile,
    TaskMetrics,
)
from .monitors import SystemMetricsMonitor
from .evaluators import ResourcePressureEvaluator
from .configs import DynamicConfigCalculator
from .core import LoadBalancer
from .server_pool_manager import ServerPoolManager

__all__ = [
    "LoadBalancer",
    "BaseTask",
    "NetworkTask",
    "LocalProcessingTask",
    "TaskType",
    "ResourceProfile",
    "TaskMetrics",
    "SystemMetricsMonitor",
    "ResourcePressureEvaluator",
    "DynamicConfigCalculator",
    "ServerPoolManager",
]
