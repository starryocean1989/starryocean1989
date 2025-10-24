# -*- coding: utf-8 -*-
"""
统一负载均衡器（核心）

LoadBalancer是整个智能负载机制的核心，负责协调各个组件：
- SystemMetricsMonitor: 获取系统监控指标
- ResourcePressureEvaluator: 评估资源压力
- DynamicConfigCalculator: 计算最优配置

使用模式：
1. 单例模式：全局唯一实例，避免重复初始化
2. 实时评估：每次任务执行前评估系统状态
3. 智能缓存：3秒内的相同任务使用缓存配置
"""

import logging
import threading
import time
from typing import Any, Dict, Optional

from vnpy.event import EventEngine

from .tasks import BaseTask
from .monitors import SystemMetricsMonitor
from .evaluators import ResourcePressureEvaluator
from .configs import DynamicConfigCalculator


class LoadBalancer:
    """统一负载均衡器（单例）

    核心功能：
    - 获取系统监控指标（混合模式：事件订阅 + ZMQ查询）
    - 评估资源压力（基于系统监控指标.md的评分模型）
    - 计算最优配置（根据任务类型和资源压力）
    - 智能缓存（减少评估开销）

    使用示例：
        # 初始化（单例，只会执行一次）
        load_balancer = LoadBalancer(event_engine)

        # 定义任务
        task = MyTask("my_task")

        # 获取动态配置
        config = load_balancer.get_optimal_config(task)

        # 使用配置执行任务
        result = task.execute(config)

    特性：
    - 单例模式：全局唯一实例
    - 线程安全：使用锁保护缓存
    - 智能缓存：相同任务3秒内使用缓存
    - 多层fallback：监控失败时自动降级
    """

    _instance: Optional["LoadBalancer"] = None
    _lock = threading.Lock()

    def __new__(cls, event_engine: Optional[EventEngine] = None):
        """单例模式实现

        Args:
            event_engine: vnpy事件引擎（仅首次初始化时需要）

        Returns:
            LoadBalancer唯一实例
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    cls._instance = instance
        return cls._instance

    def __init__(self, event_engine: Optional[EventEngine] = None):
        """初始化LoadBalancer

        注意：由于单例模式，此方法只会在首次创建时执行。

        Args:
            event_engine: vnpy事件引擎（用于订阅监控事件）
        """
        # 避免重复初始化
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self.logger = logging.getLogger(__name__)

        # 初始化组件
        self.metrics_monitor = SystemMetricsMonitor(event_engine)
        self.evaluator = ResourcePressureEvaluator()
        self.config_calculator = DynamicConfigCalculator(self.evaluator)

        # 配置缓存（减少评估频率）
        # 格式：{task_name: (config, timestamp)}
        self._config_cache: Dict[str, tuple] = {}
        self._cache_ttl = 3.0  # 缓存生命周期（秒）
        self._cache_lock = threading.Lock()

        # 统计信息
        self._eval_count = 0
        self._cache_hit_count = 0

        self.logger.info("✅ LoadBalancer初始化完成")

    def get_optimal_config(self, task: BaseTask, force_realtime: bool = False) -> Dict[str, Any]:
        """获取任务的最优配置（实时评估）

        工作流程：
        1. 检查缓存（force_realtime=False时）
        2. 获取系统监控指标
        3. 评估资源压力
        4. 计算最优配置
        5. 缓存结果

        Args:
            task: 任务对象（继承自BaseTask）
            force_realtime: 是否强制实时评估（忽略缓存）
                True: 关键决策时使用，直接ZMQ查询监控数据
                False: 常规使用，优先使用缓存

        Returns:
            最优配置字典，包含：
            - 网络任务：processes, coroutines_per_process, total_connections等
            - 本地任务：max_workers, batch_size, use_multiprocessing等
            - 通用字段：pressure_score, bottleneck, scale_factor, reason等
        """
        # 检查缓存
        if not force_realtime:
            cached_config = self._get_cached_config(task.name)
            if cached_config is not None:
                with self._cache_lock:
                    self._cache_hit_count += 1
                self.logger.debug(f"📦 使用缓存配置: {task.name}")
                return cached_config

        # 实时评估
        start_time = time.time()
        with self._cache_lock:
            self._eval_count += 1

        try:
            # 1. 获取监控指标（关键决策时强制实时查询）
            metrics = self.metrics_monitor.get_metrics(force_realtime=force_realtime)

            # 2. 评估资源压力
            pressure_eval = self.evaluator.evaluate(metrics)

            # 3. 计算最优配置
            config = self.config_calculator.calculate_for_task(task, pressure_eval)

            # 4. 缓存结果
            self._cache_config(task.name, config)

            # 5. 记录日志
            elapsed = (time.time() - start_time) * 1000
            self.logger.info(
                f"🎯 [{task.name}] 配置评估完成（{elapsed:.1f}ms）\n"
                f"   压力评分: {pressure_eval['pressure_score']}/100\n"
                f"   瓶颈维度: {pressure_eval['bottleneck']}\n"
                f"   缩放因子: {pressure_eval['scale_factor']}\n"
                f"   配置: {self._format_config(config)}\n"
                f"   原因: {pressure_eval['reason']}"
            )

            return config

        except Exception as e:
            self.logger.error(f"配置评估失败: {e}", exc_info=True)
            # 返回默认配置（保守策略）
            return self._get_default_config(task)

    def _get_cached_config(self, task_name: str) -> Optional[Dict[str, Any]]:
        """获取缓存的配置

        Args:
            task_name: 任务名称

        Returns:
            缓存的配置字典，如果缓存不存在或过期则返回None
        """
        with self._cache_lock:
            if task_name not in self._config_cache:
                return None

            cached_config, cached_time = self._config_cache[task_name]

            # 检查缓存是否过期
            if time.time() - cached_time > self._cache_ttl:
                # 缓存过期，删除
                del self._config_cache[task_name]
                return None

            return cached_config.copy()

    def _cache_config(self, task_name: str, config: Dict[str, Any]):
        """缓存配置

        Args:
            task_name: 任务名称
            config: 配置字典
        """
        with self._cache_lock:
            self._config_cache[task_name] = (config.copy(), time.time())

    def _format_config(self, config: Dict[str, Any]) -> str:
        """格式化配置为可读字符串

        Args:
            config: 配置字典

        Returns:
            格式化的字符串
        """
        # 提取关键字段
        key_fields = []

        if "processes" in config:
            # 网络任务
            key_fields.append(
                f"{config['processes']}进程 × {config['coroutines_per_process']}协程 = "
                f"{config['total_connections']}连接"
            )
        elif "max_workers" in config:
            # 本地任务
            key_fields.append(f"{config['max_workers']}工作线程, " f"批量{config['batch_size']}")

        return ", ".join(key_fields) if key_fields else str(config)

    def _get_default_config(self, task: BaseTask) -> Dict[str, Any]:
        """获取默认配置（保守策略）

        Args:
            task: 任务对象

        Returns:
            默认配置字典
        """
        from .tasks import TaskType

        if task.metrics.task_type == TaskType.NETWORK:
            # 网络任务：保守配置（4进程×10协程=40连接）
            return {
                "processes": 4,
                "coroutines_per_process": 10,
                "total_connections": 40,
                "estimated_memory_mb": 20.0,
                "pressure_score": 70.0,
                "bottleneck": "unknown",
                "scale_factor": 1.0,
                "emergency": False,
                "reason": "使用默认配置（评估失败）",
            }
        else:
            # 本地任务：保守配置（4工作线程，批量50）
            return {
                "max_workers": 4,
                "batch_size": 50,
                "use_multiprocessing": False,
                "pressure_score": 70.0,
                "bottleneck": "unknown",
                "scale_factor": 1.0,
                "emergency": False,
                "reason": "使用默认配置（评估失败）",
            }

    def clear_cache(self):
        """清空配置缓存

        在系统状态发生显著变化时可以调用此方法强制重新评估。
        """
        with self._cache_lock:
            cache_size = len(self._config_cache)
            self._config_cache.clear()

        self.logger.info(f"LoadBalancer缓存已清空（清除{cache_size}个缓存）")

    def get_stats(self) -> Dict[str, Any]:
        """获取LoadBalancer统计信息

        Returns:
            统计信息字典
        """
        with self._cache_lock:
            cache_size = len(self._config_cache)
            total_requests = self._eval_count + self._cache_hit_count
            cache_hit_rate = (
                self._cache_hit_count / total_requests * 100 if total_requests > 0 else 0
            )

        return {
            "eval_count": self._eval_count,
            "cache_hit_count": self._cache_hit_count,
            "cache_hit_rate": round(cache_hit_rate, 2),
            "cache_size": cache_size,
            "cache_ttl": self._cache_ttl,
        }

    def close(self):
        """关闭LoadBalancer，释放资源"""
        if hasattr(self, "metrics_monitor"):
            self.metrics_monitor.close()

        self.logger.info("LoadBalancer已关闭")
