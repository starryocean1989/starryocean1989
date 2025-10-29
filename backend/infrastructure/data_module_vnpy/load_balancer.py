# -*- coding: utf-8 -*-
"""
LoadBalancer 统一模块（极限合并版）

集成了负载均衡的所有功能，包括：
- 核心架构、任务定义、策略配置
- 监控评估、压力分析、告警管理
- 执行层、进程池、流式处理
- 队列系统、资源管理、智能调优
- 服务器池管理、参数调优、监控服务

合并来源：
lb_core.py, lb_monitoring.py, lb_execution.py, queue_system.py,
server_pool_manager.py, parameter_tuning.py, resource_management.py,
loadbalancer_service.py, intelligent_adaptive_tuner.py

总行数：约7,270行
合并日期：2025-10-26
"""

from __future__ import annotations

# ==================== 统一导入声明 ====================
import asyncio
import logging
import math
import multiprocessing
import platform
import queue
import random
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from multiprocessing import get_context
from pathlib import Path
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    Union,
)

import pandas as pd
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from vnpy.event import Event, EventEngine

# AsyncTdxHq_API导入（用于ConnectionLifecycleManager）
from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API


# ==============================================================================
# 第1部分：基础定义（任务类型、资源配置、任务基类）
# ==============================================================================


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
        """
        pass

    @abstractmethod
    def execute(self, config: Dict[str, Any]) -> Any:
        """执行任务

        子类必须实现此方法，使用LoadBalancer提供的动态配置执行任务。
        """
        pass


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
        """定义网络任务的默认指标"""
        return TaskMetrics(
            task_name=self.name,
            task_type=TaskType.NETWORK,
            resource_profile=ResourceProfile.NETWORK_IO_INTENSIVE,
            critical_metrics=["network_speed", "packet_loss_rate", "concurrent_task_count"],
            estimated_duration=0,
            estimated_memory_mb=0,
            estimated_connections=0,
        )


class IPODownloadTask(NetworkTask):
    """IPO日期下载任务

    特点：
    - 单个品种单个请求（不像K线需要多周期）
    - 网络IO密集，CPU开销小
    - 可容忍较高并发度
    """

    def __init__(self, name: str, total_symbols: int):
        super().__init__(name)
        self.total_symbols = total_symbols
        self.task_type = "ipo_download"

    def estimate_task_count(self) -> int:
        """估算任务数量（IPO是单次请求）"""
        return self.total_symbols

    def estimate_io_intensity(self) -> float:
        """估算IO强度（0-1），IPO下载是IO密集型"""
        return 0.9  # 高IO强度

    def estimate_cpu_intensity(self) -> float:
        """估算CPU强度（0-1），IPO下载CPU开销小"""
        return 0.1  # 低CPU强度

    def execute(self, config: Dict[str, Any]) -> Any:
        """执行IPO下载任务（占位方法）

        实际执行由MultiProcessStockFetcher.download_ipo_dates_multiprocess()完成
        """
        pass


class LocalProcessingTask(BaseTask):
    """本地数据处理任务基类

    用于本地数据处理任务，如：
    - 数据质量扫描
    - 通达信本地文件读取
    - 数据预加载
    - 数据查询与融合
    """

    def _define_metrics(self) -> TaskMetrics:
        """定义本地处理任务的默认指标"""
        return TaskMetrics(
            task_name=self.name,
            task_type=TaskType.LOCAL_PROCESSING,
            resource_profile=ResourceProfile.DISK_IO_INTENSIVE,
            critical_metrics=["disk_io_speed", "average_io_latency_ms", "cpu_percent"],
            estimated_duration=0,
            estimated_memory_mb=0,
            estimated_workers=1,
        )


# ==============================================================================
# 第2部分：核心算法（策略配置、阈值计算、动态配置、智能调优）
# ==============================================================================


class ModelConfig:
    """执行模型配置（数据类）"""

    def __init__(
        self,
        max_workers: int = 4,
        batch_size: int = 1000,
        use_multiprocessing: bool = False,
        processes: Optional[int] = None,
        coroutines_per_process: Optional[int] = None,
        **kwargs,
    ):
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.use_multiprocessing = use_multiprocessing
        self.processes = processes
        self.coroutines_per_process = coroutines_per_process
        self.extra = kwargs

    def __repr__(self):
        if self.processes:
            return (
                f"ModelConfig(processes={self.processes}, "
                f"coroutines_per_process={self.coroutines_per_process}, "
                f"batch_size={self.batch_size})"
            )
        return (
            f"ModelConfig(max_workers={self.max_workers}, "
            f"batch_size={self.batch_size}, "
            f"multiprocessing={self.use_multiprocessing})"
        )


class AdjustmentStrategy:
    """动态调整策略（数据类）"""

    def __init__(
        self,
        aggressive_decrease: bool = False,
        increase_step: float = 0.20,
        decrease_step: float = 0.30,
    ):
        self.aggressive_decrease = aggressive_decrease
        self.increase_step = increase_step
        self.decrease_step = decrease_step

    def __repr__(self):
        return (
            f"AdjustmentStrategy(aggressive={self.aggressive_decrease}, "
            f"+{self.increase_step:.0%}, -{self.decrease_step:.0%})"
        )


class ExecutionPlan:
    """执行计划（数据类）

    包含执行模型类型、初始配置和调整策略。
    """

    def __init__(
        self,
        model_type: str,
        initial_config: ModelConfig,
        adjustment_strategy: AdjustmentStrategy,
        reason: str = "",
    ):
        self.model_type = model_type
        self.initial_config = initial_config
        self.adjustment_strategy = adjustment_strategy
        self.reason = reason

    def __repr__(self):
        return (
            f"ExecutionPlan(model={self.model_type}, "
            f"config={self.initial_config}, "
            f"strategy={self.adjustment_strategy})"
        )


# -------------------- 自适应阈值计算器 --------------------


class AdaptiveThresholdCalculator:
    """自适应配置计算器（简化版）

    核心功能：计算基于硬件短板的保守起始配置
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cpu_count = multiprocessing.cpu_count()

        if HAS_PSUTIL:
            mem_info = psutil.virtual_memory()
            self.total_memory_gb = mem_info.total / (1024**3)
            self.disk_type = self._detect_disk_type()
        else:
            self.total_memory_gb = 8.0
            self.disk_type = "hdd"

        self.logger.info(
            "✅ AdaptiveThresholdCalculator初始化: " "CPU=%d核心, 内存=%.1fGB, 磁盘=%s",
            self.cpu_count,
            self.total_memory_gb,
            self.disk_type,
        )

    def _detect_disk_type(self) -> str:
        """检测磁盘类型（SSD或HDD）"""
        return "ssd"  # 简化：假设是SSD

    def calculate_conservative_baseline(self) -> Dict[str, Any]:
        """计算短板50%的保守起始配置（核心方法）"""
        cpu_score = self._evaluate_cpu_capacity()
        memory_score = self._evaluate_memory_capacity()
        disk_score = self._evaluate_disk_capacity()

        resource_scores = {
            "cpu": cpu_score,
            "memory": memory_score,
            "disk": disk_score,
        }

        bottleneck_score = min(cpu_score, memory_score, disk_score)

        if bottleneck_score == cpu_score:
            bottleneck_resource = "cpu"
        elif bottleneck_score == memory_score:
            bottleneck_resource = "memory"
        else:
            bottleneck_resource = "disk"

        theoretical_max_workers = int(bottleneck_score * self.cpu_count / 100)
        base_workers = max(2, int(theoretical_max_workers * 0.5))
        base_workers = min(base_workers, self.cpu_count)
        base_workers = max(base_workers, 2)

        if bottleneck_resource == "memory":
            batch_size = 1000
        elif bottleneck_resource == "disk":
            batch_size = 2000
        else:
            batch_size = 2000

        result = {
            "base_workers": base_workers,
            "bottleneck_resource": bottleneck_resource,
            "resource_scores": resource_scores,
            "batch_size": batch_size,
        }

        self.logger.info(
            "🎯 短板50%%保守配置: workers=%d, 短板=%s(%.0f分), batch=%d",
            base_workers,
            bottleneck_resource,
            bottleneck_score,
            batch_size,
        )

        return result

    def _evaluate_cpu_capacity(self) -> float:
        """评估CPU理论容量（0-100分）"""
        if self.cpu_count >= 32:
            return 100.0
        elif self.cpu_count >= 16:
            return 90.0
        elif self.cpu_count >= 12:
            return 80.0
        elif self.cpu_count >= 8:
            return 70.0
        elif self.cpu_count >= 6:
            return 60.0
        elif self.cpu_count >= 4:
            return 50.0
        else:
            return 40.0

    def _evaluate_memory_capacity(self) -> float:
        """评估内存理论容量（0-100分）"""
        if self.total_memory_gb >= 64:
            return 100.0
        elif self.total_memory_gb >= 32:
            return 90.0
        elif self.total_memory_gb >= 24:
            return 80.0
        elif self.total_memory_gb >= 16:
            return 70.0
        elif self.total_memory_gb >= 12:
            return 60.0
        elif self.total_memory_gb >= 8:
            return 50.0
        else:
            return 40.0

    def _evaluate_disk_capacity(self) -> float:
        """评估磁盘理论容量（0-100分）"""
        if self.disk_type == "ssd":
            return 90.0
        else:
            return 60.0

    def get_hardware_profile(self) -> Dict[str, Any]:
        """获取硬件配置档案"""
        profile = {
            "cpu_count": self.cpu_count,
            "total_memory_gb": self.total_memory_gb,
            "disk_type": self.disk_type,
            "hardware_tier": self._get_hardware_tier(),
        }
        return profile

    def _get_hardware_tier(self) -> str:
        """判断硬件档次"""
        if self.cpu_count >= 16 and self.total_memory_gb >= 32:
            return "high"
        elif self.cpu_count >= 8 and self.total_memory_gb >= 16:
            return "medium"
        elif self.cpu_count >= 4 and self.total_memory_gb >= 8:
            return "low"
        else:
            return "entry"


# 全局单例
_global_calculator = None


def get_adaptive_calculator() -> AdaptiveThresholdCalculator:
    """获取全局自适应配置计算器（单例模式）"""
    global _global_calculator
    if _global_calculator is None:
        _global_calculator = AdaptiveThresholdCalculator()
    return _global_calculator


class AdaptiveBatchSizeCalculator:
    """自适应批次大小计算器（占位类，实际实现在第4部分）"""

    def calculate(
        self, task_count: int, io_type: str = "disk", memory_pressure: float = 50.0
    ) -> int:
        """计算自适应批次大小"""
        # 简化实现，实际逻辑在第4部分
        if memory_pressure > 70:
            return min(50, task_count)
        elif memory_pressure > 40:
            return min(100, task_count)
        else:
            return min(200, task_count)


# -------------------- 执行策略决策器 --------------------


class ExecutionPolicy:
    """执行策略决策器

    职责：
    - 根据任务特征选择执行模型
    - 根据资源压力计算初始配置
    - 提供动态调整策略
    """

    SAFE_ZONE_LOWER = 65.0
    SAFE_ZONE_UPPER = 75.0
    INCREASE_STEP = 0.05
    DECREASE_STEP = 0.10
    CHECK_INTERVAL = 1.5
    MIN_ADJUSTMENT_INTERVAL = 3.0

    def __init__(self, enable_adaptive_baseline: bool = True):
        """初始化执行策略决策器"""
        self.logger = logging.getLogger(__name__)
        self.cpu_count = multiprocessing.cpu_count()

        if HAS_PSUTIL:
            self.total_memory_gb = psutil.virtual_memory().total / (1024**3)
        else:
            self.total_memory_gb = 8.0

        if enable_adaptive_baseline:
            self.adaptive_calculator = AdaptiveThresholdCalculator()
            self.baseline = self.adaptive_calculator.calculate_conservative_baseline()
            self.logger.info(
                "✅ 已启用自适应短板50%%基线：workers=%d, 短板=%s",
                self.baseline["base_workers"],
                self.baseline["bottleneck_resource"],
            )
        else:
            self.adaptive_calculator = None
            self.baseline = {
                "base_workers": max(2, int(self.cpu_count * 0.7)),
                "bottleneck_resource": "balanced",
                "batch_size": 2000,
            }

        self.batch_calculator = AdaptiveBatchSizeCalculator()

        self.logger.info(
            "✅ ExecutionPolicy初始化完成（CPU=%d, 内存=%.1fGB, 区间阈值=%.1f-%.1f%%）",
            self.cpu_count,
            self.total_memory_gb,
            self.SAFE_ZONE_LOWER,
            self.SAFE_ZONE_UPPER,
        )

    def select_execution_plan(self, task: Any, resource_pressure: Any) -> ExecutionPlan:
        """选择执行计划（核心决策方法）"""
        profile = task.resource_profile if hasattr(task, "resource_profile") else None
        io_type = profile.io_type if profile else "disk"
        estimated_count = (
            profile.estimated_count if profile and hasattr(profile, "estimated_count") else 5000
        )

        bottleneck = resource_pressure.bottleneck
        score = resource_pressure.score
        scale = resource_pressure.scale_suggestion

        self.logger.debug(
            "决策输入: 任务IO类型=%s, 品种数=%d, 瓶颈=%s, 压力=%.1f%%, 缩放=%.2f",
            io_type,
            estimated_count,
            bottleneck,
            score,
            scale,
        )

        if io_type == "network":
            return self._plan_for_network_task(bottleneck, score, scale, estimated_count)
        elif io_type == "disk":
            return self._plan_for_disk_task(bottleneck, score, scale, estimated_count)
        elif io_type == "memory":
            return self._plan_for_memory_task(bottleneck, score, scale, estimated_count)
        else:
            return self._plan_for_disk_task(bottleneck, score, scale, estimated_count)

    def _calculate_optimal_batch_size(
        self, memory_pressure: float, task_count: int, io_type: str = "disk"
    ) -> int:
        """计算最优批次大小"""
        batch_size = self.batch_calculator.calculate(
            task_count=task_count, io_type=io_type, memory_pressure=memory_pressure
        )
        return batch_size

    def _plan_for_disk_task(
        self, bottleneck: str, score: float, _scale: float, estimated_count: int
    ) -> ExecutionPlan:
        """磁盘IO密集任务决策（多进程优化版）"""
        base_processes = self.baseline["base_workers"]

        memory_pressure = 50.0
        if HAS_PSUTIL:
            try:
                memory_pressure = psutil.virtual_memory().percent
            except Exception:
                pass

        batch_size = self._calculate_optimal_batch_size(
            memory_pressure, estimated_count, io_type="disk"
        )
        processes = base_processes

        if score < self.SAFE_ZONE_LOWER:
            processes = min(8, self.cpu_count, int(base_processes * 1.1))
            reason = "低压力起始：%d进程，批次%d（压力%.1f%% < %.1f%%）" % (
                processes,
                batch_size,
                score,
                self.SAFE_ZONE_LOWER,
            )
        elif score > self.SAFE_ZONE_UPPER:
            processes = max(2, int(base_processes * 0.9))
            reason = "高压力起始：%d进程，批次%d（压力%.1f%% > %.1f%%）" % (
                processes,
                batch_size,
                score,
                self.SAFE_ZONE_UPPER,
            )
        else:
            reason = "安全区起始：%d进程，批次%d（压力%.1f%%，区间%.1f-%.1f%%）" % (
                processes,
                batch_size,
                score,
                self.SAFE_ZONE_LOWER,
                self.SAFE_ZONE_UPPER,
            )

        if bottleneck == "disk":
            reason += " [磁盘瓶颈:多进程IO]"
        elif bottleneck == "memory":
            reason += " [内存瓶颈:小批次%d]" % batch_size

        adjustment = AdjustmentStrategy(
            aggressive_decrease=False,
            increase_step=self.INCREASE_STEP,
            decrease_step=self.DECREASE_STEP,
        )

        config = ModelConfig(
            max_workers=processes,
            batch_size=batch_size,
            use_multiprocessing=True,
        )

        return ExecutionPlan(
            model_type="MultiProcessBatch",
            initial_config=config,
            adjustment_strategy=adjustment,
            reason=reason,
        )

    def _plan_for_network_task(
        self, bottleneck: str, score: float, _scale: float, _estimated_count: int
    ) -> ExecutionPlan:
        """网络IO密集任务决策（多进程+协程优化版）"""
        processes = min(8, max(2, self.cpu_count // 2))
        base_coroutines = 100

        if score < self.SAFE_ZONE_LOWER:
            coroutines = int(base_coroutines * 1.2)
            reason = "%d进程（固定）×%d协程（压力%.1f%% < %.1f%%）" % (
                processes,
                coroutines,
                score,
                self.SAFE_ZONE_LOWER,
            )
        elif score > self.SAFE_ZONE_UPPER:
            coroutines = int(base_coroutines * 0.8)
            reason = "%d进程（固定）×%d协程（压力%.1f%% > %.1f%%）" % (
                processes,
                coroutines,
                score,
                self.SAFE_ZONE_UPPER,
            )
        else:
            coroutines = base_coroutines
            reason = "%d进程（固定）×%d协程（压力%.1f%%，区间%.1f-%.1f%%）" % (
                processes,
                coroutines,
                score,
                self.SAFE_ZONE_LOWER,
                self.SAFE_ZONE_UPPER,
            )

        if bottleneck == "network":
            reason += " [网络瓶颈:保守协程数]"
        elif bottleneck == "cpu":
            reason += " [CPU瓶颈:减少进程数]"
            processes = max(2, processes // 2)

        adjustment = AdjustmentStrategy(
            aggressive_decrease=False,
            increase_step=self.INCREASE_STEP,
            decrease_step=self.DECREASE_STEP,
        )

        config = ModelConfig(
            max_workers=processes,
            batch_size=1000,
            use_multiprocessing=True,
            processes=processes,
            coroutines_per_process=coroutines,
        )

        return ExecutionPlan(
            model_type="MultiProcessAsync",
            initial_config=config,
            adjustment_strategy=adjustment,
            reason=reason,
        )

    def _plan_for_memory_task(
        self, bottleneck: str, score: float, scale: float, _estimated_count: int
    ) -> ExecutionPlan:
        """内存受限任务决策"""
        base_batch_size = 100

        if bottleneck == "memory":
            batch_size = max(50, int(base_batch_size * scale * 0.5))
            adjustment = AdjustmentStrategy(
                aggressive_decrease=True,
                increase_step=0.10,
                decrease_step=0.40,
            )
            reason = "内存瓶颈，流式处理：批次%d（压力%.1f%%）" % (batch_size, score)
        else:
            batch_size = max(100, int(base_batch_size * scale))
            adjustment = AdjustmentStrategy(
                aggressive_decrease=False,
                increase_step=0.20,
                decrease_step=0.30,
            )
            reason = "流式处理：批次%d（压力%.1f%%）" % (batch_size, score)

        config = ModelConfig(
            max_workers=1,
            batch_size=batch_size,
            use_multiprocessing=False,
        )

        return ExecutionPlan(
            model_type="StreamProcessing",
            initial_config=config,
            adjustment_strategy=adjustment,
            reason=reason,
        )


# -------------------- 动态配置计算器 --------------------


class DynamicConfigCalculator:
    """动态配置计算器

    根据资源压力和任务特征，计算最优的并发配置参数。

    v3.3新增：基于event_loop_lag的并发决策
    """

    def __init__(self, evaluator):
        """初始化配置计算器"""
        self.evaluator = evaluator
        self.logger = logging.getLogger(__name__)

    def make_concurrency_decision(
        self,
        task: BaseTask,
        pressure: ResourcePressure,
        event_loop_lag_ms: Optional[float] = None,
        current_processes: int = 1,
        current_coroutines: int = 10,
    ) -> Dict[str, Any]:
        """基于资源压力与event_loop_lag的并发决策（v3.3新增）

        决策优先级：
        1. 资源限制触发（超出高阈值/紧急）→ 优先降低协程
        2. 资源处于低负载区 → 优先增加协程
        3. 出现协程排队（event_loop_lag > 20ms）→ 增加进程
        4. 其他情况 → 保持

        Args:
            task: 任务对象
            pressure: 资源压力对象
            event_loop_lag_ms: 事件循环延迟（毫秒）
            current_processes: 当前进程数
            current_coroutines: 当前每进程协程数

        Returns:
            {
                'action': 'INCREASE_PROCESS' | 'DECREASE_COROUTINE' | 'INCREASE_COROUTINE' | 'HOLD',
                'reason': str,
                'suggested_processes': int,
                'suggested_coroutines_per_process': int,
                'lag_ms': float,
                'pressure_score': float,
            }
        """
        cpu_cores = multiprocessing.cpu_count()

        # 1️⃣ 优先处理资源限制：触发高阈值或紧急状态时先降协程
        resource_overloaded = (
            pressure.emergency or pressure.above_high_threshold or (pressure.scale_suggestion < 1.0)
        )
        if resource_overloaded:
            suggested_coroutines = max(5, int(current_coroutines * 0.8))
            return {
                "action": "DECREASE_COROUTINE",
                "reason": pressure.reason or f"资源压力{pressure.score:.1f}，优先减少协程",
                "suggested_processes": current_processes,
                "suggested_coroutines_per_process": suggested_coroutines,
                "lag_ms": event_loop_lag_ms or 0,
                "pressure_score": pressure.score,
            }

        # 2️⃣ 资源充裕时优先增加协程
        low_load = pressure.below_low_threshold or pressure.scale_suggestion > 1.0
        if low_load and (event_loop_lag_ms is None or event_loop_lag_ms < 10):
            suggested_coroutines = current_coroutines + 5  # 移除上限，允许真正的高并发测试
            lag_desc = (
                f"且事件循环流畅({event_loop_lag_ms:.1f}ms)"
                if event_loop_lag_ms is not None
                else ""
            )
            return {
                "action": "INCREASE_COROUTINE",
                "reason": f"系统处于低负载(压力{pressure.score:.1f}){lag_desc}，优先增加协程",
                "suggested_processes": current_processes,
                "suggested_coroutines_per_process": suggested_coroutines,
                "lag_ms": event_loop_lag_ms or 0,
                "pressure_score": pressure.score,
            }

        # 3️⃣ lag触发协程排队，尝试增加进程（进程数受CPU限制）
        if event_loop_lag_ms is not None and event_loop_lag_ms > 20:
            suggested_processes = min(current_processes + 1, cpu_cores)
            return {
                "action": "INCREASE_PROCESS",
                "reason": f"事件循环延迟{event_loop_lag_ms:.1f}ms，协程排队，尝试增加进程",
                "suggested_processes": suggested_processes,
                "suggested_coroutines_per_process": current_coroutines,
                "lag_ms": event_loop_lag_ms,
                "pressure_score": pressure.score,
            }

        # 4️⃣ 默认保持当前配置
        return {
            "action": "HOLD",
            "reason": f"当前配置合理(压力{pressure.score:.1f}, lag={event_loop_lag_ms or 0:.1f}ms)",
            "suggested_processes": current_processes,
            "suggested_coroutines_per_process": current_coroutines,
            "lag_ms": event_loop_lag_ms or 0,
            "pressure_score": pressure.score,
        }

    def calculate_for_task(self, task: BaseTask, pressure_eval: Dict[str, Any]) -> Dict[str, Any]:
        """为特定任务计算最优配置"""
        scale_factor = pressure_eval["scale_factor"]
        bottleneck = pressure_eval["bottleneck"]

        if task.metrics.task_type == TaskType.NETWORK:
            base_config = self._calculate_network_task_config(task, scale_factor, bottleneck)
        else:
            base_config = self._calculate_local_task_config(task, scale_factor, bottleneck)

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
        self, task: BaseTask, scale_factor: float, bottleneck: str
    ) -> Dict[str, Any]:
        """计算网络任务配置"""
        cpu_cores = multiprocessing.cpu_count()

        if HAS_PSUTIL:
            memory = psutil.virtual_memory()
            available_memory_gb = memory.available / (1024**3)
        else:
            available_memory_gb = 8.0

        estimated_connections = task.metrics.estimated_connections
        if estimated_connections == 0:
            estimated_connections = min(cpu_cores * 40, 640)

        target_connections = int(estimated_connections * scale_factor)
        target_connections = max(10, target_connections)

        if bottleneck == "network":
            target_connections = int(target_connections * 0.7)
        elif bottleneck == "cpu":
            pass

        if bottleneck == "cpu":
            processes = min(max(4, cpu_cores // 2), 8)
        else:
            processes = min(max(4, cpu_cores), 8)

        coroutines_per_process = max(10, target_connections // processes)
        actual_connections = processes * coroutines_per_process

        estimated_memory_mb = actual_connections * 0.5
        max_safe_memory_mb = available_memory_gb * 1024 * 0.3

        if estimated_memory_mb > max_safe_memory_mb:
            actual_connections = int(max_safe_memory_mb / 0.5)
            coroutines_per_process = max(10, actual_connections // processes)
            estimated_memory_mb = actual_connections * 0.5

        config = {
            "processes": processes,
            "coroutines_per_process": coroutines_per_process,
            "total_connections": actual_connections,
            "estimated_memory_mb": round(estimated_memory_mb, 2),
        }

        return config

    def _calculate_local_task_config(
        self, _task: BaseTask, scale_factor: float, bottleneck: str
    ) -> Dict[str, Any]:
        """计算本地处理任务配置"""
        cpu_cores = multiprocessing.cpu_count()

        if bottleneck == "disk":
            base_workers = cpu_cores
            target_workers = max(2, int(base_workers * scale_factor))
            batch_size = min(5000, int(1000 / max(0.2, scale_factor)))
        elif bottleneck == "cpu":
            target_workers = max(2, int(cpu_cores * scale_factor * 0.5))
            batch_size = 500
        elif bottleneck == "memory":
            target_workers = max(2, int(cpu_cores * 0.5))
            batch_size = max(50, int(500 * scale_factor))
        else:
            target_workers = min(cpu_cores, int(cpu_cores * scale_factor))
            batch_size = 5000

        target_workers = min(target_workers, cpu_cores)
        use_multiprocessing = target_workers > 8

        config = {
            "max_workers": target_workers,
            "batch_size": batch_size,
            "use_multiprocessing": use_multiprocessing,
        }

        return config


# -------------------- 智能自适应调优器 --------------------


class IntelligentAdaptiveTuner:
    """智能自适应调优器

    多维压力评分 + 趋势分析 + 抖动保护 的并发调节器。

    说明：
    - 保持零依赖，不引入重型ML库；趋势用EMA与P95近似；
    - 输入来自监控进程 system 字段的新增四类子系统指标；
    - 输出包含并发建议与理由摘要；
    """

    def __init__(
        self,
        base_async_workers: int = 2000,
        base_thread_workers: int = 50,
        base_process_workers: int = 16,
        weights: Optional[Dict[str, float]] = None,
        ema_alpha: float = 0.2,
        adjust_step_max: float = 0.25,  # 单步最大调整比例
        deadband: float = 0.05,  # 死区，避免小抖动
        cooldown_sec: float = 2.0,  # 调整冷却时间
    ) -> None:
        self.base_async_workers = base_async_workers
        self.base_thread_workers = base_thread_workers
        self.base_process_workers = base_process_workers

        self.weights = weights or {
            "cpu": 0.35,
            "memory": 0.25,
            "storage": 0.25,
            "network": 0.15,
        }

        self.ema_alpha = ema_alpha
        self.adjust_step_max = adjust_step_max
        self.deadband = deadband
        self.cooldown_sec = cooldown_sec

        self._pressure_ema: Optional[float] = None
        self._history: Deque[float] = deque(maxlen=60)  # 约一分钟窗口
        self._last_scale: float = 1.0
        self._last_adjust_ts: float = 0.0

    def _norm(self, value: Optional[float], hi: float) -> float:
        if value is None:
            return 0.0
        if hi <= 0:
            return 0.0
        return max(0.0, min(1.0, value / hi))

    def _score_cpu(self, sys_data: Dict[str, Any]) -> float:
        cpu_percent = float(sys_data.get("cpu_percent", 0.0))
        cpu_load = self._norm(cpu_percent, 100.0)

        detailed = sys_data.get("cpu_detailed", {}) or {}
        ctx = detailed.get("context_switches_per_sec")
        intr = detailed.get("interrupts_per_sec")
        # 经验上大于几万/秒说明系统调度压力大，做归一近似
        ctx_load = self._norm(ctx, 50000.0)
        intr_load = self._norm(intr, 20000.0)

        # 加权求和
        return min(1.0, 0.6 * cpu_load + 0.25 * ctx_load + 0.15 * intr_load)

    def _score_memory(self, sys_data: Dict[str, Any]) -> float:
        mem_percent = float(sys_data.get("memory_percent", 0.0))
        mem_load = self._norm(mem_percent, 100.0)
        mem_sub = sys_data.get("memory_subsystem", {}) or {}
        swap_in = mem_sub.get("swap_in_kbps")
        swap_out = mem_sub.get("swap_out_kbps")
        swap_load = max(self._norm(swap_in, 256000.0), self._norm(swap_out, 256000.0))  # 250MB/s
        return min(1.0, 0.8 * mem_load + 0.2 * swap_load)

    def _score_storage(self, sys_data: Dict[str, Any]) -> float:
        st = sys_data.get("storage_subsystem", {}) or {}
        disks = st.get("disks", {}) or {}
        latency_scores = []
        for info in disks.values():
            lat = info.get("average_io_latency_ms")
            if lat is not None:
                latency_scores.append(self._norm(lat, 50.0))  # 50ms 为高风险上限
        return max(latency_scores) if latency_scores else 0.0

    def _score_network(self, sys_data: Dict[str, Any]) -> float:
        net = sys_data.get("network_subsystem", {}) or {}
        loss_in = float(net.get("packet_loss_rate_in", 0.0))
        loss_out = float(net.get("packet_loss_rate_out", 0.0))
        # 1% 丢包即高危
        return max(self._norm(loss_in, 1.0), self._norm(loss_out, 1.0))

    def _calc_pressure(self, sys_data: Dict[str, Any]) -> float:
        cpu = self._score_cpu(sys_data)
        mem = self._score_memory(sys_data)
        sto = self._score_storage(sys_data)
        net = self._score_network(sys_data)

        pressure = (
            cpu * self.weights["cpu"]
            + mem * self.weights["memory"]
            + sto * self.weights["storage"]
            + net * self.weights["network"]
        )

        # EMA 平滑
        self._pressure_ema = (
            pressure
            if self._pressure_ema is None
            else (self.ema_alpha * pressure + (1 - self.ema_alpha) * self._pressure_ema)
        )
        self._history.append(pressure)
        return max(0.0, min(1.0, self._pressure_ema))

    def _suggest_scale(self, pressure: float) -> float:
        # 简单策略曲线：压力低→放大，压力高→缩小
        if pressure < 0.2:
            target = 1.4
        elif pressure < 0.4:
            target = 1.2
        elif pressure < 0.6:
            target = 1.0
        elif pressure < 0.8:
            target = 0.8
        else:
            target = 0.6

        # 死区与最大步长限制
        delta = target - self._last_scale
        if abs(delta) < self.deadband:
            target = self._last_scale
        else:
            step = max(-self.adjust_step_max, min(self.adjust_step_max, delta))
            target = self._last_scale + step

        # 冷却时间限制
        now = time.time()
        if now - self._last_adjust_ts < self.cooldown_sec:
            target = self._last_scale

        return max(0.3, min(1.6, target))

    def suggest(self, system_metrics: Dict[str, Any]) -> Dict[str, Any]:
        pressure = self._calc_pressure(system_metrics or {})
        scale = self._suggest_scale(pressure)

        self._last_adjust_ts = time.time()
        self._last_scale = scale

        return {
            "scale_factor": round(scale, 2),
            "async_workers": max(100, int(self.base_async_workers * scale)),
            "thread_workers": max(5, int(self.base_thread_workers * scale)),
            "process_workers": max(2, int(self.base_process_workers * scale)),
            "pressure_score": round(float(pressure), 3),
        }


# ==============================================================================
# 第3部分：监控评估系统（SystemMetricsMonitor、ResourcePressureEvaluator、指标收集、性能告警）
# ==============================================================================


class LagMonitor:
    """通用事件循环延迟监控工具（v3.4新增）

    功能：
    1. 测量asyncio事件循环的调度延迟（schedule lag）
    2. 测量回调响应延迟（callback lag）
    3. 统计pending tasks数量（协程排队指标）
    4. 计算综合延迟（考虑排队压力）
    5. 通过queue上报指标到主进程

    使用场景：
    - TDX本地数据读取
    - K线网络下载
    - 本地数据感知下载
    - 任何需要监控协程性能的场景

    使用方法：
    ```python
    # 在worker进程的异步函数中启动监控
    lag_task = asyncio.create_task(
        LagMonitor.monitor_and_report(
            result_queue=result_queue,
            worker_id=worker_id,
            stop_event=stop_event,
            interval_seconds=0.3
        )
    )

    # 任务结束时取消监控
    await LagMonitor.cancel_monitor(lag_task)
    ```
    """

    @staticmethod
    async def monitor_and_report(
        metrics_queue,  # 🆕 v3.5: 改为独立的metrics_queue
        worker_id: int,
        stop_event,
        interval_seconds: float = 0.3,
        queue_pressure_factor: float = 10.0,
        pending_threshold: int = 100,
    ):
        """在worker进程中持续监控event_loop_lag并通过独立队列上报

        v3.5改进：使用独立的metrics_queue，与数据结果队列分离，防止阻塞

        Args:
            metrics_queue: 用于上报指标的独立multiprocessing.Queue
            worker_id: worker进程ID
            stop_event: 停止信号（multiprocessing.Event）
            interval_seconds: 监控间隔（秒），默认0.3秒
            queue_pressure_factor: 排队压力系数，默认10.0（每100个pending任务贡献10ms）
            pending_threshold: pending任务计算阈值，默认100
        """
        import asyncio
        import time

        while not stop_event.is_set():
            try:
                # 1. 获取当前事件循环和任务统计
                loop = asyncio.get_running_loop()
                all_tasks = asyncio.all_tasks(loop)
                pending_count = sum(1 for t in all_tasks if not t.done() and not t.cancelled())
                done_count = sum(1 for t in all_tasks if t.done())

                # 2. 测量调度延迟（schedule lag）
                schedule_start = time.perf_counter()
                await asyncio.sleep(0)
                schedule_lag_ms = (time.perf_counter() - schedule_start) * 1000

                # 3. 测量回调延迟（callback lag）
                callback_start = time.perf_counter()
                callback_done = asyncio.Future()

                def callback_measure():
                    if not callback_done.done():
                        callback_done.set_result(time.perf_counter() - callback_start)

                loop.call_soon(callback_measure)

                try:
                    callback_lag_s = await asyncio.wait_for(callback_done, timeout=1.0)
                    callback_lag_ms = callback_lag_s * 1000
                except asyncio.TimeoutError:
                    # 超时说明事件循环严重阻塞
                    callback_lag_ms = 1000.0

                # 4. 计算排队压力（queue pressure）
                # 公式：(pending_count / pending_threshold) * queue_pressure_factor
                # 例如：500个pending任务 / 100 * 10 = 50ms
                queue_pressure_ms = (pending_count / pending_threshold) * queue_pressure_factor

                # 5. 计算综合延迟
                # lag = max(调度延迟, 回调延迟) + 排队压力
                lag_ms = max(schedule_lag_ms, callback_lag_ms) + queue_pressure_ms

                # 6. 通过result_queue上报指标（使用特殊标记）
                lag_data = {
                    "lag_ms": round(lag_ms, 3),
                    "pending_tasks": pending_count,
                    "done_tasks": done_count,
                    "total_tasks": len(all_tasks),
                    "schedule_lag_ms": round(schedule_lag_ms, 3),
                    "callback_lag_ms": round(callback_lag_ms, 3),
                    "queue_pressure_ms": round(queue_pressure_ms, 3),
                    "timestamp": time.time(),
                }

                # 🔧 v3.5: 使用独立的metrics_queue（非阻塞）
                try:
                    metrics_queue.put_nowait(("__LAG_METRICS__", worker_id, lag_data))
                except:
                    # queue满了就跳过这次上报，lag监控不应阻塞主任务
                    pass

                # 7. 等待下一次监控
                await asyncio.sleep(interval_seconds)

            except Exception as e:
                # 监控失败不应该影响主任务
                try:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(f"[Worker-{worker_id}] lag监控失败: {e}")
                except:
                    pass
                await asyncio.sleep(1.0)

    @staticmethod
    async def cancel_monitor(lag_monitor_task):
        """取消lag监控任务

        Args:
            lag_monitor_task: asyncio.Task对象
        """
        if lag_monitor_task and not lag_monitor_task.done():
            lag_monitor_task.cancel()
            try:
                await lag_monitor_task
            except asyncio.CancelledError:
                pass

    @staticmethod
    def process_lag_message(
        msg: tuple,
        load_balancer,
        logger=None,
        warn_threshold_ms: float = 20.0,
    ) -> bool:
        """在主进程中处理lag指标消息

        Args:
            msg: 从queue接收的消息tuple
            load_balancer: LoadBalancer实例
            logger: 日志记录器（可选）
            warn_threshold_ms: 警告阈值（毫秒），超过此值记录警告

        Returns:
            bool: 如果是lag消息返回True，否则返回False
        """
        # 识别lag指标消息
        if not (isinstance(msg, tuple) and len(msg) == 3 and msg[0] == "__LAG_METRICS__"):
            return False

        _, worker_id, lag_data = msg
        lag_ms = lag_data.get("lag_ms", 0)
        pending_tasks = lag_data.get("pending_tasks", 0)

        # 更新resource_monitor的lag缓存
        if load_balancer and hasattr(load_balancer, "resource_monitor"):
            monitor = load_balancer.resource_monitor
            source = f"Worker-{worker_id}"
            monitor._event_loop_lag_cache[source] = lag_ms
            monitor._event_loop_lag_history.append((lag_ms, source))
            monitor._last_lag_update = time.time()

            # 如果lag较大，记录警告
            if lag_ms > warn_threshold_ms and logger:
                logger.warning(
                    f"⚠️ Worker-{worker_id} 事件循环拥堵: "
                    f"lag={lag_ms:.1f}ms, pending_tasks={pending_tasks}"
                )

        return True


class SystemMetricsMonitor:
    """系统监控指标获取器（优化后的纯事件订阅模式）

    特性：
    - 事件订阅：订阅SystemManagerService推送的监控事件（每1秒自动推送并覆盖缓存）
    - 缓存策略：永远使用最后一次缓存（即使较旧也比默认值准确）
    - 警告机制：10秒TTL仅用于检测推送异常，不会拒绝使用缓存
    - 智能fallback：仅在缓存完全未初始化时使用默认值
    - 线程安全：使用锁保护缓存
    - ZMQ查询已废弃：不再主动查询监控进程，避免超时和卡死
    """

    def __init__(self, event_engine: Optional[EventEngine] = None):
        """初始化监控指标获取器"""
        self.event_engine = event_engine
        self.logger = logging.getLogger(__name__)

        self._cached_metrics: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()
        self._cache_timestamp = 0.0
        # ✅ TTL仅用于警告阈值（不会拒绝使用缓存）
        # SystemManagerService正常1秒推送，降级3秒推送
        # 如果超过10秒未更新，说明可能有问题（会输出警告但仍继续使用缓存）
        self._event_cache_ttl = 10.0
        self._direct_sample_interval = 0.2
        self._last_disk_counters: Dict[str, Dict[str, float]] = {}
        self._last_disk_sample_ts: Optional[float] = None

        if event_engine:
            self._subscribe_events()
            self.logger.info(
                "✅ SystemMetricsMonitor初始化完成（事件订阅模式，TTL=%ds）",
                int(self._event_cache_ttl),
            )
        else:
            self.logger.warning("⚠️ SystemMetricsMonitor未提供EventEngine，将使用默认值")

    def _subscribe_events(self):
        """订阅系统监控事件（后台被动更新）"""
        if not self.event_engine:
            return

        try:
            from backend.infrastructure.system_vnpy.system_toolkit import (
                EVENT_SYSTEM_METRICS,
                EVENT_HARDWARE_SENSORS,
            )

            self.event_engine.register(EVENT_SYSTEM_METRICS, self._on_system_metrics_event)
            self.event_engine.register(EVENT_HARDWARE_SENSORS, self._on_hardware_sensors_event)

            self.logger.debug("已订阅系统监控事件")

        except ImportError:
            self.logger.warning("无法导入monitoring_events，事件订阅失败")

    def _on_system_metrics_event(self, event: Event):
        """接收系统指标事件（原子更新缓存）"""
        with self._cache_lock:
            if "system" not in self._cached_metrics:
                self._cached_metrics["system"] = {}

            self._cached_metrics["system"] = event.data
            self._cache_timestamp = time.time()

            self.logger.debug("✅ 收到系统指标事件更新，缓存已刷新")

    def _on_hardware_sensors_event(self, event: Event):
        """接收硬件传感器事件（原子更新缓存）"""
        with self._cache_lock:
            if "hardware" not in self._cached_metrics:
                self._cached_metrics["hardware"] = {}

            self._cached_metrics["hardware"] = event.data

            self.logger.debug("✅ 收到硬件传感器事件更新")

    def get_metrics(self, force_realtime: bool = False) -> Dict[str, Any]:
        """获取监控指标（纯事件订阅模式）

        SystemManagerService每1秒自动推送事件，缓存会自动刷新。
        即使缓存较旧，也会继续使用（比默认值更准确）。

        Args:
            force_realtime: 已废弃，保留参数仅为兼容性
        """
        if force_realtime:
            self.logger.debug("忽略force_realtime参数（已废弃ZMQ查询）")

        with self._cache_lock:
            # 如果有缓存，直接使用（无论多久前更新的）
            if self._cached_metrics:
                cache_age = time.time() - self._cache_timestamp if self._cache_timestamp > 0 else 0

                # ✅ 只在缓存很旧时输出警告，但仍然使用
                if cache_age > self._event_cache_ttl:
                    self.logger.warning(
                        "⚠️ 监控缓存较旧（%.1f秒前更新），SystemManagerService可能未正常推送",
                        cache_age,
                    )
                else:
                    self.logger.debug("✅ 使用事件缓存（%.1f秒前更新）", cache_age)

                return self._cached_metrics.copy()

            # 缓存为空（从未收到过事件），尝试直接读取或使用默认值
            if self._cache_timestamp == 0:
                self.logger.warning(
                    "监控缓存未初始化（从未收到SystemManagerService推送），尝试直接读取"
                )
                # 尝试直接用psutil读取（用于测试环境）
                return self._read_direct_metrics()
            else:
                self.logger.warning("监控缓存为空但timestamp存在（异常状态），使用默认值")
            return self._get_default_metrics()

    def _read_direct_metrics(self) -> Dict[str, Any]:
        """直接读取系统指标（用于测试环境无监控进程时）"""
        try:
            if not HAS_PSUTIL:
                raise ImportError("psutil not available")

            start = time.time()

            # 非阻塞模式（interval=None）：返回自上次调用以来的平均值
            # 第一次调用返回0.0，之后返回实际值
            cpu_start = time.time()
            cpu_percent = psutil.cpu_percent(interval=self._direct_sample_interval)
            per_cpu = psutil.cpu_percent(interval=None, percpu=True)
            cpu_elapsed = (time.time() - cpu_start) * 1000

            mem_start = time.time()
            virtual_mem = psutil.virtual_memory()
            memory_percent = virtual_mem.percent
            mem_elapsed = (time.time() - mem_start) * 1000

            disk_metrics: Dict[str, Any] = {}
            io_start = time.time()
            io_counters = psutil.disk_io_counters(perdisk=True)
            io_elapsed = (time.time() - io_start) * 1000
            now = time.time()
            prev_snapshot = self._last_disk_counters
            prev_ts = self._last_disk_sample_ts

            if io_counters:
                dt = now - prev_ts if prev_ts else None
                for disk_name, stats in io_counters.items():
                    info = {
                        "queue_depth": 0.0,
                        "average_io_latency_ms": 0.0,
                        "util_percent": 0.0,
                    }

                    stats_dict = stats._asdict()
                    busy_time = float(stats_dict.get("busy_time", 0.0))
                    read_time = float(stats_dict.get("read_time", 0.0))
                    write_time = float(stats_dict.get("write_time", 0.0))
                    read_count = float(stats_dict.get("read_count", 0.0))
                    write_count = float(stats_dict.get("write_count", 0.0))

                    if dt and dt > 0 and disk_name in prev_snapshot:
                        prev = prev_snapshot[disk_name]
                        busy_delta = max(0.0, busy_time - prev.get("busy_time", 0.0))
                        util_percent = min(100.0, max(0.0, (busy_delta / (dt * 1000.0)) * 100.0))
                        info["util_percent"] = round(util_percent, 2)

                        read_ops = max(0.0, read_count - prev.get("read_count", 0.0))
                        write_ops = max(0.0, write_count - prev.get("write_count", 0.0))
                        total_ops = read_ops + write_ops
                        io_time_delta = max(
                            0.0,
                            (read_time - prev.get("read_time", 0.0))
                            + (write_time - prev.get("write_time", 0.0)),
                        )
                        if total_ops > 0:
                            info["average_io_latency_ms"] = round(io_time_delta / total_ops, 2)

                        if util_percent >= 95.0:
                            info["queue_depth"] = round(max(0.0, (util_percent - 95.0) / 5.0), 3)

                    disk_metrics[disk_name] = info

                self._last_disk_counters = {
                    disk_name: {
                        "busy_time": float(stats._asdict().get("busy_time", 0.0)),
                        "read_time": float(stats._asdict().get("read_time", 0.0)),
                        "write_time": float(stats._asdict().get("write_time", 0.0)),
                        "read_count": float(stats._asdict().get("read_count", 0.0)),
                        "write_count": float(stats._asdict().get("write_count", 0.0)),
                    }
                    for disk_name, stats in io_counters.items()
                }
                self._last_disk_sample_ts = now

            total_elapsed = (time.time() - start) * 1000

            self.logger.info(
                "⏱️ 直接读取指标耗时: 总%.1fms (CPU:%.1fms, 内存:%.1fms, I/O:%.1fms) | CPU=%.1f%%, 内存=%.1f%%",
                total_elapsed,
                cpu_elapsed,
                mem_elapsed,
                io_elapsed,
                cpu_percent,
                memory_percent,
            )

            return {
                "system": {
                    "cpu_percent": cpu_percent,
                    "per_cpu_percent": per_cpu,
                    "memory_percent": memory_percent,
                    "disk_percent": 30.0,
                    "cpu_detailed": {
                        "context_switches_per_sec": 5000.0,
                    },
                    "memory_subsystem": {
                        "swap_in_kbps": 0.0,
                        "swap_out_kbps": 0.0,
                    },
                    "storage_subsystem": {
                        "disks": disk_metrics
                        or {
                            "default": {
                                "average_io_latency_ms": 5.0,
                                "queue_depth": 0.0,
                                "util_percent": 0.0,
                            }
                        }
                    },
                    "network_subsystem": {
                        "packet_loss_rate_in": 0.001,
                    },
                }
            }
        except Exception as e:
            self.logger.error("直接读取失败: %s，使用默认值", e)
        return self._get_default_metrics()

    def _get_default_metrics(self) -> Dict[str, Any]:
        """获取默认指标（假设系统空闲，便于测试动态调整）"""
        return {
            "system": {
                "cpu_percent": 30.0,  # 低于CPU_LOWER_LIMIT(75%)
                "memory_percent": 30.0,  # 低于MEMORY_LOWER_LIMIT(65%)
                "disk_percent": 30.0,
                "cpu_detailed": {
                    "context_switches_per_sec": 5000.0,
                },
                "memory_subsystem": {
                    "swap_in_kbps": 0.0,
                    "swap_out_kbps": 0.0,
                },
                "storage_subsystem": {
                    "disks": {
                        "default": {
                            "average_io_latency_ms": 5.0,
                        }
                    }
                },
                "network_subsystem": {
                    "packet_loss_rate_in": 0.001,
                },
            }
        }

    def close(self):
        """关闭监控器，释放资源"""
        # ZMQ资源已不再使用，无需清理
        self.logger.info("SystemMetricsMonitor已关闭")


class ResourcePressure:
    """资源压力评估结果（数据类）"""

    def __init__(
        self,
        score: float,
        bottleneck: str,
        below_low_threshold: bool,
        above_high_threshold: bool,
        scale_suggestion: float,
        cpu_score: float,
        memory_score: float,
        disk_score: float,
        network_score: float,
        swap_active: bool,
        emergency: bool,
        reason: str,
    ):
        self.score = score
        self.bottleneck = bottleneck
        self.below_low_threshold = below_low_threshold
        self.above_high_threshold = above_high_threshold
        self.scale_suggestion = scale_suggestion

        self.cpu_score = cpu_score
        self.memory_score = memory_score
        self.disk_score = disk_score
        self.network_score = network_score

        self.swap_active = swap_active
        self.emergency = emergency
        self.reason = reason

    def __repr__(self):
        return (
            f"ResourcePressure(score={self.score:.1f}, bottleneck={self.bottleneck}, "
            f"low={self.below_low_threshold}, high={self.above_high_threshold}, "
            f"scale={self.scale_suggestion:.2f})"
        )


class ResourceMonitor:
    """资源监控器（整合监控+评估+双阈值检测）

    v3.3新增：集成event_loop_lag_ms监控
    """

    def __init__(
        self,
        event_engine: Optional[EventEngine] = None,
        low_threshold: float = 35.0,
        high_threshold: float = 70.0,
    ):
        """初始化资源监控器"""
        self.logger = logging.getLogger(__name__)

        self.metrics_monitor = SystemMetricsMonitor(event_engine)
        self.evaluator = ResourcePressureEvaluator()

        self.low_threshold = low_threshold
        self.high_threshold = high_threshold

        # 🆕 v3.3: event_loop_lag监控
        self.event_engine = event_engine
        self._event_loop_lag_cache: Dict[str, float] = {}  # {source: lag_ms}
        self._event_loop_lag_history: Deque[Tuple[float, str]] = deque(
            maxlen=100
        )  # (lag_ms, source)
        self._last_lag_update = 0.0

        # 订阅协程性能指标事件
        if event_engine:
            from ..events import EVENT_ASYNCIO_METRICS

            event_engine.register(EVENT_ASYNCIO_METRICS, self._on_asyncio_metrics)

        self.logger.info(
            "✅ ResourceMonitor初始化完成（低阈值=%.1f%%, 高阈值=%.1f%%）",
            low_threshold,
            high_threshold,
        )

    def get_current_pressure(self, force_realtime: bool = False) -> ResourcePressure:
        """获取当前资源压力（核心方法）"""
        metrics = self.metrics_monitor.get_metrics(force_realtime=force_realtime)
        eval_result = self.evaluator.evaluate(metrics)

        score = eval_result["pressure_score"]
        below_low = score < self.low_threshold
        above_high = score > self.high_threshold

        pressure = ResourcePressure(
            score=score,
            bottleneck=eval_result["bottleneck"],
            below_low_threshold=below_low,
            above_high_threshold=above_high,
            scale_suggestion=eval_result["scale_factor"],
            cpu_score=eval_result["cpu_score"],
            memory_score=eval_result["memory_score"],
            disk_score=eval_result["disk_score"],
            network_score=eval_result["network_score"],
            swap_active=eval_result["swap_active"],
            emergency=eval_result["emergency"],
            reason=eval_result["reason"],
        )

        self.logger.debug(
            "资源压力: %.1f%% (%s瓶颈), 低阈值=%s, 高阈值=%s",
            score,
            eval_result["bottleneck"],
            below_low,
            above_high,
        )

        return pressure

    def _on_asyncio_metrics(self, event: Event):
        """处理协程性能指标事件（事件回调）

        事件数据格式：
        {
            'event_loop_lag_ms': 15.2,
            'source': 'TdxDynamicExecutor',
            'timestamp': '2025-10-26T...'
        }
        """
        try:
            data = event.data
            lag_ms = data.get("event_loop_lag_ms", 0)
            source = data.get("source", "unknown")

            # 更新缓存
            self._event_loop_lag_cache[source] = lag_ms
            self._event_loop_lag_history.append((lag_ms, source))
            self._last_lag_update = time.time()

            # 严重拥堵时记录警告
            if lag_ms > 20:
                self.logger.warning(f"⚠️ 事件循环严重拥堵: {source} lag={lag_ms:.1f}ms")
        except Exception as e:
            self.logger.error(f"处理asyncio指标事件失败: {e}")

    def get_event_loop_lag(self) -> Optional[float]:
        """获取当前最大的事件循环延迟（毫秒）

        Returns:
            最近的最大延迟值，如果没有数据则返回None
        """
        if not self._event_loop_lag_cache:
            return None

        # 返回所有模块中的最大延迟
        return max(self._event_loop_lag_cache.values())

    def get_event_loop_lag_by_source(self) -> Dict[str, float]:
        """获取各模块的事件循环延迟

        Returns:
            {source: lag_ms} 字典
        """
        return self._event_loop_lag_cache.copy()

    def close(self):
        """关闭监控器，释放资源"""
        # 取消事件订阅
        if self.event_engine:
            try:
                from ..events import EVENT_ASYNCIO_METRICS

                self.event_engine.unregister(EVENT_ASYNCIO_METRICS, self._on_asyncio_metrics)
            except Exception as e:
                self.logger.debug(f"取消事件订阅失败: {e}")

        self.metrics_monitor.close()
        self.logger.info("ResourceMonitor已关闭")


# -------------------- 资源压力评估器 --------------------


class ResourcePressureEvaluator:
    """资源压力评估器（基于系统监控指标.md的评分模型）

    使用木桶理论模型评估系统资源压力：
    - 系统性能 = min(CPU性能, 内存性能, 磁盘性能, 网络性能)
    - 瓶颈 = 得分最低的维度

    新增：资源上下限融合
    - 触及上限（任一资源）→ 拒绝任务并降并发
    - 触及下限（所有资源）→ 提升并发
    """

    # 资源上下限配置（各资源独立）
    CPU_LOWER_LIMIT = 75.0  # CPU下限（%）
    CPU_UPPER_LIMIT = 85.0  # CPU上限（%）
    MEMORY_LOWER_LIMIT = 65.0  # 内存下限（%）
    MEMORY_UPPER_LIMIT = 75.0  # 内存上限（%）

    # 磁盘队列深度阈值（按磁盘类型，仅上限）
    QUEUE_DEPTH_LIMITS = {
        "hdd": {"upper": 2, "growth_rate_warn": 0.5},
        "ssd": {"upper": 2, "growth_rate_warn": 0.5},
        "nvme": {"upper": 4, "growth_rate_warn": 1.0},
    }

    DISK_UTILIZATION_LIMITS = {
        "hdd": {"warning": 80.0, "critical": 90.0},
        "ssd": {"warning": 85.0, "critical": 95.0},
        "nvme": {"warning": 90.0, "critical": 98.0},
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # 记录历史队列深度（用于计算增长率）
        self._queue_history: Dict[str, List[tuple]] = {}  # {disk_name: [(timestamp, queue_depth)]}

    def _evaluate_resource_status(
        self, current_value: float, lower_limit: float, upper_limit: float, resource_name: str
    ) -> Dict[str, Any]:
        """评估单个资源的状态

        Args:
            current_value: 当前资源使用率（%）
            lower_limit: 下限（%）
            upper_limit: 上限（%）
            resource_name: 资源名称（用于日志）

        Returns:
            Dict包含 action 和 reason
            - action: "reject"（触及上限）, "increase"（低于下限）, "hold"（正常）
        """
        if current_value >= upper_limit:
            return {
                "action": "reject",
                "reason": f"{resource_name}使用率{current_value:.1f}%触及上限{upper_limit:.1f}%",
            }
        elif current_value < lower_limit:
            return {
                "action": "increase",
                "reason": f"{resource_name}使用率{current_value:.1f}%低于下限{lower_limit:.1f}%",
            }
        else:
            return {
                "action": "hold",
                "reason": f"{resource_name}使用率{current_value:.1f}%在正常范围",
            }

    def _evaluate_disk_status(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """评估磁盘状态（队列深度增长率监控，v2.5.1优化）

        策略优化：
        1. 去掉下限 - 队列深度不用于"提升并发"判断
        2. 监控增长率 - 队列深度>0且上升快时提前降并发
        3. 双重保护 - 延迟作为紧急熔断

        Args:
            metrics: 系统监控指标

        Returns:
            Dict包含 action 和 reason
        """
        system = metrics.get("system", {})
        storage_subsystem = system.get("storage_subsystem", {})
        disks = storage_subsystem.get("disks", {})

        if not disks:
            return {"action": "hold", "reason": "磁盘监控数据不可用"}

        current_time = time.time()
        warning_reason: Optional[str] = None

        # 检查所有物理磁盘
        for disk_name, disk_info in disks.items():
            disk_type = disk_info.get("disk_type", "ssd").lower()
            queue_depth = disk_info.get("queue_depth")
            util_percent = disk_info.get("util_percent")
            io_latency = disk_info.get("average_io_latency_ms", 0)

            # ==== 策略1：队列深度上限判断 ====
            if queue_depth is not None:
                limits = self.QUEUE_DEPTH_LIMITS.get(disk_type, self.QUEUE_DEPTH_LIMITS["ssd"])
                queue_upper = limits["upper"]
                growth_rate_warn = limits["growth_rate_warn"]

                # 上限判断：队列深度>0 → 立即拒绝（有任何排队都说明IO有压力）
                if queue_depth > queue_upper:
                    return {
                        "action": "reject",
                        "reason": f"磁盘{disk_name}({disk_type.upper()})队列深度{queue_depth:.1f}超过上限{queue_upper}（有IO排队）",
                    }

                # ==== 策略2：队列增长率监控（提前预警）====
                if queue_depth > 0:
                    if disk_name not in self._queue_history:
                        self._queue_history[disk_name] = []

                    history = self._queue_history[disk_name]
                    history.append((current_time, queue_depth))
                    history[:] = [(t, q) for t, q in history if current_time - t <= 3.0]

                    if len(history) >= 2:
                        oldest_time, oldest_queue = history[0]
                        time_delta = current_time - oldest_time
                        queue_delta = queue_depth - oldest_queue

                        if time_delta > 0:
                            growth_rate = queue_delta / time_delta

                            if growth_rate > growth_rate_warn:
                                remaining = queue_upper - queue_depth
                                eta_seconds = (
                                    remaining / growth_rate if growth_rate > 0 else float("inf")
                                )

                                return {
                                    "action": "reject",
                                    "reason": f"磁盘{disk_name}({disk_type.upper()})队列快速累积(当前{queue_depth:.1f}，增长率{growth_rate:.1f}/秒，预计{eta_seconds:.1f}秒后达上限)",
                                }
                else:
                    if disk_name in self._queue_history:
                        self._queue_history[disk_name].clear()

            elif util_percent is not None:
                util_limits = self.DISK_UTILIZATION_LIMITS.get(
                    disk_type, self.DISK_UTILIZATION_LIMITS["ssd"]
                )
                critical = util_limits["critical"]
                warning = util_limits["warning"]
                if util_percent >= critical:
                    return {
                        "action": "reject",
                        "reason": f"磁盘{disk_name}({disk_type.upper()})利用率{util_percent:.1f}%超过临界阈值{critical:.1f}%",
                    }
                elif util_percent >= warning and warning_reason is None:
                    warning_reason = f"磁盘{disk_name}({disk_type.upper()})利用率{util_percent:.1f}%接近上限{critical:.1f}%"

            # ==== 策略3：延迟熔断（紧急保护）====
            if io_latency:
                if disk_type == "hdd":
                    latency_emergency = 100.0
                elif disk_type == "nvme":
                    latency_emergency = 10.0
                else:
                    latency_emergency = 50.0

                if io_latency >= latency_emergency:
                    return {
                        "action": "reject",
                        "reason": f"磁盘{disk_name}({disk_type.upper()})IO延迟{io_latency:.1f}ms触发紧急熔断",
                    }

            # ==== Fallback：队列深度不可用时，使用延迟判断 ====
            if queue_depth is None and io_latency:
                if disk_type == "hdd":
                    latency_upper = 50.0
                elif disk_type == "nvme":
                    latency_upper = 5.0
                else:
                    latency_upper = 20.0

                if io_latency >= latency_upper:
                    return {
                        "action": "reject",
                        "reason": f"磁盘{disk_name}({disk_type.upper()})IO延迟{io_latency:.1f}ms过高（队列深度不可用）",
                    }

        # 所有磁盘正常
        return {"action": "hold", "reason": warning_reason or "磁盘状态正常"}

    def evaluate(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """评估当前资源压力（融合上下限判断）"""
        system = metrics.get("system", {})

        cpu_percent = system.get("cpu_percent", 0)
        memory_percent = system.get("memory_percent", 0)

        memory_subsystem = system.get("memory_subsystem", {})
        swap_in = memory_subsystem.get("swap_in_kbps", 0)
        swap_out = memory_subsystem.get("swap_out_kbps", 0)

        # ==== 新增：上下限判断 ====
        # 评估各资源状态
        cpu_status = self._evaluate_resource_status(
            cpu_percent, self.CPU_LOWER_LIMIT, self.CPU_UPPER_LIMIT, "CPU"
        )
        memory_status = self._evaluate_resource_status(
            memory_percent, self.MEMORY_LOWER_LIMIT, self.MEMORY_UPPER_LIMIT, "内存"
        )
        disk_status = self._evaluate_disk_status(metrics)

        # 综合决策：任一资源触及上限 → 拒绝+降并发
        reject_reasons = []
        if cpu_status["action"] == "reject":
            reject_reasons.append(cpu_status["reason"])
        if memory_status["action"] == "reject":
            reject_reasons.append(memory_status["reason"])
        if disk_status["action"] == "reject":
            reject_reasons.append(disk_status["reason"])

        if reject_reasons:
            reason = "; ".join(reject_reasons)
            self.logger.warning("⚠️ 资源触及上限，拒绝任务: %s", reason)
            return {
                "action": "reject",
                "adjustment": -1,  # 每个进程减少1个协程
                "pressure_score": 90.0,
                "bottleneck": "overload",
                "scale_factor": 0.3,
                "cpu_score": 0,
                "memory_score": 0,
                "disk_score": 0,
                "network_score": 0,
                "swap_active": swap_in > 0 or swap_out > 0,
                "emergency": True,
                "reason": reason,
            }

        # CPU或内存任一低于下限，且其他资源没有触发降协程 → 提升并发
        # 注意：只要有一个资源低于下限就增加，但不能有资源触发reject
        if (
            cpu_status["action"] == "increase" or memory_status["action"] == "increase"
        ) and disk_status[
            "action"
        ] != "reject":  # 磁盘不能触发reject
            increase_reasons = []
            if cpu_status["action"] == "increase":
                increase_reasons.append(cpu_status["reason"])
            if memory_status["action"] == "increase":
                increase_reasons.append(memory_status["reason"])

            reason = "; ".join(increase_reasons)
            self.logger.info("✅ CPU或内存低于下限且无资源过载，可提升并发: %s", reason)
            return {
                "action": "increase",
                "adjustment": +1,  # 每个进程增加1个协程
                "pressure_score": 40.0,
                "bottleneck": "underutilized",
                "scale_factor": 1.3,
                "cpu_score": 40,
                "memory_score": 30,
                "disk_score": 15,
                "network_score": 15,
                "swap_active": False,
                "emergency": False,
                "reason": reason,
            }

        # 上下限都未触发 → 保持当前并发
        swap_active = swap_in > 0 or swap_out > 0
        self.logger.debug(
            "资源在正常区间，保持当前并发 (CPU=%.1f%%, 内存=%.1f%%)", cpu_percent, memory_percent
        )
        return {
            "action": "hold",
            "adjustment": 0,
            "pressure_score": 50.0,  # 中间值
            "bottleneck": "balanced",
            "scale_factor": 1.0,
            "cpu_score": 0,
            "memory_score": 0,
            "disk_score": 0,
            "network_score": 0,
            "swap_active": swap_active,
            "emergency": False,
            "reason": "资源在正常区间，保持当前并发",
        }


# -------------------- 指标收集器 --------------------


@dataclass
class LBTaskMetrics:
    """单个任务的指标（避免与TaskMetrics冲突，添加LB前缀）"""

    task_id: str
    task_type: str
    start_time: float
    end_time: Optional[float] = None
    success: bool = False
    error: Optional[str] = None
    batch_size: int = 0
    worker_count: int = 0


@dataclass
class AggregatedMetrics:
    """聚合指标"""

    timestamp: datetime
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    avg_execution_time: float = 0.0
    avg_batch_size: float = 0.0
    avg_worker_count: float = 0.0
    pool_utilization: float = 0.0
    adjustment_count: int = 0
    queue_length: int = 0
    custom_metrics: Dict[str, Any] = field(default_factory=dict)


class LoadBalancerMetricsCollector:
    """LoadBalancer指标采集器"""

    def __init__(self, name: str, max_history: int = 1000, aggregation_window: int = 60):
        """初始化指标采集器"""
        self.name = name
        self.logger = logging.getLogger(__name__)

        self._tasks: Deque[LBTaskMetrics] = deque(maxlen=max_history)
        self._lock = threading.Lock()

        self._max_history = max_history
        self._aggregation_window = aggregation_window

        self._current_tasks: Dict[str, LBTaskMetrics] = {}
        self._adjustment_count = 0
        self._queue_length = 0

        self._start_time = time.time()

    def start_task(
        self,
        task_type: str,
        task_id: Optional[str] = None,
        batch_size: int = 0,
        worker_count: int = 0,
    ) -> str:
        """开始跟踪任务"""
        if task_id is None:
            task_id = "%s_%d" % (task_type, int(time.time() * 1000))

        task = LBTaskMetrics(
            task_id=task_id,
            task_type=task_type,
            start_time=time.time(),
            batch_size=batch_size,
            worker_count=worker_count,
        )

        with self._lock:
            self._current_tasks[task_id] = task

        return task_id

    def end_task(self, task_id: str, success: bool = True, error: Optional[str] = None):
        """结束任务跟踪"""
        with self._lock:
            if task_id not in self._current_tasks:
                self.logger.warning("未找到任务: %s", task_id)
                return

            task = self._current_tasks.pop(task_id)
            task.end_time = time.time()
            task.success = success
            task.error = error

            self._tasks.append(task)

    def record_adjustment(
        self,
        adjustment_type: str,
        old_value: Any,
        new_value: Any,
        reason: Optional[str] = None,
    ):
        """记录动态调整"""
        with self._lock:
            self._adjustment_count += 1

        self.logger.debug(
            "记录调整: %s, %s -> %s, 原因: %s",
            adjustment_type,
            old_value,
            new_value,
            reason or "N/A",
        )

    def update_queue_length(self, length: int):
        """更新队列长度"""
        with self._lock:
            self._queue_length = length

    def get_metrics(self, window_seconds: Optional[int] = None) -> AggregatedMetrics:
        """获取聚合指标"""
        with self._lock:
            if window_seconds is None:
                cutoff_time = 0
            else:
                cutoff_time = time.time() - window_seconds

            relevant_tasks = [t for t in self._tasks if t.end_time and t.end_time >= cutoff_time]

            if not relevant_tasks:
                return AggregatedMetrics(
                    timestamp=datetime.now(),
                    queue_length=self._queue_length,
                    adjustment_count=self._adjustment_count,
                )

            total_tasks = len(relevant_tasks)
            successful_tasks = sum(1 for t in relevant_tasks if t.success)
            failed_tasks = total_tasks - successful_tasks

            execution_times = [
                t.end_time - t.start_time for t in relevant_tasks if t.end_time is not None
            ]
            avg_execution_time = (
                sum(execution_times) / len(execution_times) if execution_times else 0.0
            )

            batch_sizes = [t.batch_size for t in relevant_tasks if t.batch_size > 0]
            avg_batch_size = sum(batch_sizes) / len(batch_sizes) if batch_sizes else 0.0

            worker_counts = [t.worker_count for t in relevant_tasks if t.worker_count > 0]
            avg_worker_count = sum(worker_counts) / len(worker_counts) if worker_counts else 0.0

            max_workers = max(worker_counts) if worker_counts else 1
            pool_utilization = (avg_worker_count / max_workers * 100) if max_workers > 0 else 0.0

            return AggregatedMetrics(
                timestamp=datetime.now(),
                total_tasks=total_tasks,
                successful_tasks=successful_tasks,
                failed_tasks=failed_tasks,
                avg_execution_time=avg_execution_time,
                avg_batch_size=avg_batch_size,
                avg_worker_count=avg_worker_count,
                pool_utilization=pool_utilization,
                adjustment_count=self._adjustment_count,
                queue_length=self._queue_length,
            )

    def get_task_success_rate(self, window_seconds: Optional[int] = None) -> float:
        """获取任务成功率"""
        metrics = self.get_metrics(window_seconds)
        if metrics.total_tasks == 0:
            return 100.0
        return (metrics.successful_tasks / metrics.total_tasks) * 100

    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        metrics = self.get_metrics()
        uptime = time.time() - self._start_time

        return {
            "name": self.name,
            "uptime_seconds": uptime,
            "total_tasks": metrics.total_tasks,
            "success_rate": self.get_task_success_rate(),
            "avg_execution_time": metrics.avg_execution_time,
            "avg_batch_size": metrics.avg_batch_size,
            "pool_utilization": metrics.pool_utilization,
            "adjustment_count": metrics.adjustment_count,
            "queue_length": metrics.queue_length,
        }

    def reset(self):
        """重置指标"""
        with self._lock:
            self._tasks.clear()
            self._current_tasks.clear()
            self._adjustment_count = 0
            self._queue_length = 0
            self._start_time = time.time()

        self.logger.info("指标已重置")


def create_metrics_collector(name: str) -> LoadBalancerMetricsCollector:
    """便捷函数：创建指标采集器"""
    return LoadBalancerMetricsCollector(name=name)


# -------------------- 性能告警管理器 --------------------


class AlertLevel(Enum):
    """告警级别"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(Enum):
    """告警类型"""

    EXECUTION_TIME = "execution_time"
    FAILURE_RATE = "failure_rate"
    MEMORY_PRESSURE = "memory_pressure"
    QUEUE_BACKLOG = "queue_backlog"
    POOL_UTILIZATION = "pool_utilization"


@dataclass
class AlertRule:
    """告警规则"""

    name: str
    alert_type: AlertType
    level: AlertLevel
    condition: Callable[[AggregatedMetrics], bool]
    message_template: str


@dataclass
class Alert:
    """告警"""

    rule_name: str
    alert_type: AlertType
    level: AlertLevel
    message: str
    timestamp: datetime
    metrics: Dict


class PerformanceAlertManager:
    """性能告警管理器"""

    def __init__(self, metrics_collector: LoadBalancerMetricsCollector):
        """初始化告警管理器"""
        self.metrics_collector = metrics_collector
        self.logger = logging.getLogger(__name__)

        self._rules: List[AlertRule] = []
        self._callbacks: List[Callable[[Alert], None]] = []
        self._alert_history: List[Alert] = []

        self._add_default_rules()

    def _add_default_rules(self):
        """添加默认告警规则"""
        self.add_rule(
            AlertRule(
                name="执行时间过长",
                alert_type=AlertType.EXECUTION_TIME,
                level=AlertLevel.WARNING,
                condition=lambda m: m.avg_execution_time > 60.0,
                message_template="平均执行时间: {avg_execution_time:.2f}秒，超过60秒阈值",
            )
        )

        self.add_rule(
            AlertRule(
                name="任务失败率高",
                alert_type=AlertType.FAILURE_RATE,
                level=AlertLevel.ERROR,
                condition=lambda m: (m.total_tasks > 0 and (m.failed_tasks / m.total_tasks) > 0.1),
                message_template="失败率: {failure_rate:.1f}%，超过10%阈值",
            )
        )

        self.add_rule(
            AlertRule(
                name="队列积压",
                alert_type=AlertType.QUEUE_BACKLOG,
                level=AlertLevel.WARNING,
                condition=lambda m: m.queue_length > 100,
                message_template="队列长度: {queue_length}，超过100阈值",
            )
        )

        self.add_rule(
            AlertRule(
                name="进程池利用率低",
                alert_type=AlertType.POOL_UTILIZATION,
                level=AlertLevel.INFO,
                condition=lambda m: m.pool_utilization > 0 and m.pool_utilization < 30.0,
                message_template="进程池利用率: {pool_utilization:.1f}%，低于30%",
            )
        )

        self.add_rule(
            AlertRule(
                name="进程池利用率高",
                alert_type=AlertType.POOL_UTILIZATION,
                level=AlertLevel.WARNING,
                condition=lambda m: m.pool_utilization > 90.0,
                message_template="进程池利用率: {pool_utilization:.1f}%，超过90%阈值",
            )
        )

    def add_rule(self, rule: AlertRule):
        """添加告警规则"""
        self._rules.append(rule)
        self.logger.info("添加告警规则: %s", rule.name)

    def remove_rule(self, rule_name: str):
        """移除告警规则"""
        self._rules = [r for r in self._rules if r.name != rule_name]
        self.logger.info("移除告警规则: %s", rule_name)

    def check_alerts(self, window_seconds: Optional[int] = None) -> List[Alert]:
        """检查告警"""
        metrics = self.metrics_collector.get_metrics(window_seconds)

        alerts = []
        for rule in self._rules:
            try:
                if rule.condition(metrics):
                    metrics_dict = {
                        "avg_execution_time": metrics.avg_execution_time,
                        "failure_rate": (
                            (metrics.failed_tasks / metrics.total_tasks * 100)
                            if metrics.total_tasks > 0
                            else 0.0
                        ),
                        "queue_length": metrics.queue_length,
                        "pool_utilization": metrics.pool_utilization,
                    }

                    message = rule.message_template.format(**metrics_dict)

                    alert = Alert(
                        rule_name=rule.name,
                        alert_type=rule.alert_type,
                        level=rule.level,
                        message=message,
                        timestamp=datetime.now(),
                        metrics=metrics_dict,
                    )

                    alerts.append(alert)
                    self._alert_history.append(alert)

                    for callback in self._callbacks:
                        try:
                            callback(alert)
                        except Exception as e:
                            self.logger.error("告警回调失败: %s", str(e), exc_info=True)

            except Exception as e:
                self.logger.error("检查规则'%s'时出错: %s", rule.name, str(e), exc_info=True)

        return alerts

    def register_callback(self, callback: Callable[[Alert], None]):
        """注册告警回调"""
        self._callbacks.append(callback)
        self.logger.info("注册告警回调")

    def unregister_callback(self, callback: Callable[[Alert], None]):
        """取消注册告警回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            self.logger.info("取消注册告警回调")

    def get_alert_history(
        self,
        limit: Optional[int] = None,
        level: Optional[AlertLevel] = None,
        alert_type: Optional[AlertType] = None,
    ) -> List[Alert]:
        """获取告警历史"""
        filtered = self._alert_history

        if level:
            filtered = [a for a in filtered if a.level == level]

        if alert_type:
            filtered = [a for a in filtered if a.alert_type == alert_type]

        if limit:
            filtered = filtered[-limit:]

        return filtered

    def clear_history(self):
        """清空告警历史"""
        self._alert_history.clear()
        self.logger.info("告警历史已清空")


def create_alert_manager(
    metrics_collector: LoadBalancerMetricsCollector,
) -> PerformanceAlertManager:
    """便捷函数：创建告警管理器"""
    return PerformanceAlertManager(metrics_collector)


def log_alert_callback(alert: Alert):
    """日志告警回调"""
    logger = logging.getLogger(__name__)

    if alert.level == AlertLevel.CRITICAL:
        logger.critical("[ALERT] %s: %s", alert.rule_name, alert.message)
    elif alert.level == AlertLevel.ERROR:
        logger.error("[ALERT] %s: %s", alert.rule_name, alert.message)
    elif alert.level == AlertLevel.WARNING:
        logger.warning("[ALERT] %s: %s", alert.rule_name, alert.message)
    else:
        logger.info("[ALERT] %s: %s", alert.rule_name, alert.message)


# ==============================================================================
# 第4部分：执行层（执行模型、进程池、批次优化、流式处理）
# ==============================================================================


# -------------------- 任务单元和结果 --------------------


class TaskUnit:
    """任务单元（数据类）

    表示一个可独立执行的最小任务单元。
    """

    def __init__(self, unit_id: str, data: Any, processor: Optional[Callable] = None):
        self.unit_id = unit_id  # 单元ID（用于追踪）
        self.data = data  # 单元数据
        self.processor = processor  # 处理函数（可选）

    def __repr__(self):
        return f"TaskUnit(id={self.unit_id})"


class TaskResult:
    """任务结果（数据类）"""

    def __init__(self, unit_id: str, success: bool, data: Any = None, error: Optional[str] = None):
        self.unit_id = unit_id
        self.success = success
        self.data = data
        self.error = error

    def __repr__(self):
        status = "✓" if self.success else "✗"
        return f"TaskResult({status} {self.unit_id})"


# -------------------- 执行模型基类 --------------------


class ExecutionModel(ABC):
    """执行模型基类（所有模型必须实现）

    核心功能：
    - 批量执行任务单元
    - 动态并发调整（基于资源压力）
    - 进度回调
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    def execute_with_monitoring(
        self,
        task_units: List[TaskUnit],
        config: Any,  # ModelConfig对象
        resource_monitor: Any,  # ResourceMonitor对象
        adjustment_strategy: Any,  # AdjustmentStrategy对象
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[TaskResult]:
        """带监控的执行（核心方法）

        执行流程：
        1. 按初始配置启动工作池
        2. 每处理N个单元，检查资源压力
        3. 压力 < 35% → 增加并发（+20%）
        4. 压力 > 70% → 降低并发（-30% 或 -50%）
        5. 调整后继续执行

        Args:
            task_units: 任务单元列表
            config: 初始配置（ModelConfig）
            resource_monitor: 资源监控器（ResourceMonitor）
            adjustment_strategy: 调整策略（AdjustmentStrategy）
            progress_callback: 进度回调 callback(completed, total)

        Returns:
            任务结果列表
        """
        raise NotImplementedError("子类必须实现execute_with_monitoring方法")


# -------------------- MultiProcessAsyncModel --------------------


class MultiProcessAsyncModel(ExecutionModel):
    """多进程+多协程模型（网络IO密集任务）

    特点：
    - 多进程绕过GIL
    - 每进程独立asyncio事件循环
    - 固定进程数，动态调整协程数

    用途：
    - K线下载
    - IPO日期下载

    动态调整策略：
    - 固定进程数（启动时基于CPU核心数确定）
    - 只调整协程数（基于资源压力）
    - 监控频率：1.5秒检查一次
    - 调整幅度：+5%增加，-10%减少
    """

    # 固定区间阈值（与ExecutionPolicy保持一致）
    SAFE_ZONE_LOWER = 65.0
    SAFE_ZONE_UPPER = 75.0

    # 低幅度调整步长
    INCREASE_STEP = 0.05  # 5%
    DECREASE_STEP = 0.10  # 10%

    # 高频调整配置
    CHECK_INTERVAL = 1.5  # 检查间隔1.5秒
    MIN_ADJUSTMENT_INTERVAL = 3.0  # 最小调整间隔3秒

    def __init__(self):
        super().__init__()

        # 执行状态（实例变量）
        self._stop_flag = threading.Event()
        self._adjustment_lock = threading.Lock()
        self._last_adjustment_time = 0.0

        # 当前配置（动态）
        self._fixed_processes = 0  # 固定进程数（启动时确定）
        self._current_coroutines = 0  # 动态协程数
        self._min_coroutines = 10
        self._max_coroutines: Optional[int] = None  # None 表示不设上限，由负载器动态调节

        # 资源监控器（在execute_with_monitoring中设置）
        self._resource_monitor = None

        # 调整统计
        self._adjustment_count = 0
        self._increase_count = 0
        self._decrease_count = 0

        self.logger.info("✅ MultiProcessAsyncModel 初始化完成（多进程+协程版）")

    def execute_with_monitoring(
        self,
        task_units: List[TaskUnit],
        config: Any,
        resource_monitor: Any,
        adjustment_strategy: Any,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[TaskResult]:
        """执行任务（带动态协程数调整）"""
        if not task_units:
            self.logger.warning("任务单元列表为空，跳过执行")
            return []

        self.logger.info(
            "🚀 开始执行网络IO任务：%s个单元，初始配置: %s进程×%s协程",
            len(task_units),
            config.processes,
            config.coroutines_per_process,
        )

        # 设置资源监控器和固定配置
        self._resource_monitor = resource_monitor
        self._fixed_processes = config.processes
        self._current_coroutines = config.coroutines_per_process

        # 重置停止标志
        self._stop_flag.clear()

        # 启动独立监控线程
        monitor_thread = threading.Thread(
            target=self._adjustment_monitor_thread,
            name="MultiProcessAsync-Monitor",
            daemon=True,
        )
        monitor_thread.start()

        results = []

        try:
            # 使用multiprocessing.Pool执行任务
            total_tasks = len(task_units)
            tasks_per_process = (total_tasks + self._fixed_processes - 1) // self._fixed_processes

            self.logger.debug(
                "分配任务：%s个任务 → %s个进程（每进程约%s个任务）",
                total_tasks,
                self._fixed_processes,
                tasks_per_process,
            )

            # 分批任务
            task_batches = []
            for i in range(0, total_tasks, tasks_per_process):
                batch = task_units[i : i + tasks_per_process]
                task_batches.append((batch, self._current_coroutines))

            # 使用进程池执行
            with multiprocessing.Pool(processes=self._fixed_processes) as pool:
                batch_results = pool.map(_process_async_batch, task_batches)

                # 合并结果
                for batch_result in batch_results:
                    results.extend(batch_result)

                # 报告进度
                if progress_callback:
                    progress_callback(len(results), total_tasks)

            self.logger.info(
                "✅ 任务执行完成：共%s个结果，调整次数%s次", len(results), self._adjustment_count
            )

            return results

        except Exception as e:
            self.logger.error("任务执行失败: %s", e, exc_info=True)
            return results

        finally:
            # 停止监控线程
            self._stop_flag.set()
            monitor_thread.join(timeout=2.0)

            self.logger.info(
                "📊 执行统计: 调整%s次(增加%s次, 减少%s次)",
                self._adjustment_count,
                self._increase_count,
                self._decrease_count,
            )

    def _adjustment_monitor_thread(self):
        """独立监控线程（高频检查并动态调整协程数）"""
        self.logger.debug("🎯 启动协程数动态调整监控线程")

        while not self._stop_flag.is_set():
            try:
                # 每1.5秒检查一次
                self._stop_flag.wait(self.CHECK_INTERVAL)

                if self._stop_flag.is_set():
                    break

                # 获取当前资源压力
                if self._resource_monitor is None:
                    continue

                pressure = self._resource_monitor.get_current_pressure()

                # 区间阈值判断
                if pressure.score < self.SAFE_ZONE_LOWER:
                    # 低于安全区下沿（<65%）：低幅度增加
                    self._try_increase_coroutines(pressure)

                elif pressure.score > self.SAFE_ZONE_UPPER:
                    # 高于安全区上沿（>75%）：低幅度降低
                    self._try_decrease_coroutines(pressure)

            except Exception as e:
                self.logger.error("监控线程异常: %s", e, exc_info=True)

        self.logger.debug("✅ 监控线程已停止")

    def _try_increase_coroutines(self, pressure):
        """尝试增加协程数（+5%）"""
        with self._adjustment_lock:
            if not self._can_adjust():
                return

            old_coroutines = self._current_coroutines
            new_coroutines = int(old_coroutines * (1 + self.INCREASE_STEP))
            if self._max_coroutines is not None:
                new_coroutines = min(new_coroutines, self._max_coroutines)

            if new_coroutines > old_coroutines:
                self._current_coroutines = new_coroutines
                self._last_adjustment_time = time.time()
                self._adjustment_count += 1
                self._increase_count += 1

                self.logger.info(
                    "⬆️  增加协程数: %s → %s (压力%.1f%% < %.0f%%)",
                    old_coroutines,
                    new_coroutines,
                    pressure.score,
                    self.SAFE_ZONE_LOWER,
                )

    def _try_decrease_coroutines(self, pressure):
        """尝试减少协程数（-10%）"""
        with self._adjustment_lock:
            if not self._can_adjust():
                return

            old_coroutines = self._current_coroutines
            new_coroutines = int(old_coroutines * (1 - self.DECREASE_STEP))
            new_coroutines = max(new_coroutines, self._min_coroutines)

            if new_coroutines < old_coroutines:
                self._current_coroutines = new_coroutines
                self._last_adjustment_time = time.time()
                self._adjustment_count += 1
                self._decrease_count += 1

                self.logger.info(
                    "⬇️  减少协程数: %s → %s (压力%.1f%% > %.0f%%)",
                    old_coroutines,
                    new_coroutines,
                    pressure.score,
                    self.SAFE_ZONE_UPPER,
                )

    def _can_adjust(self) -> bool:
        """检查是否可以调整（防抖机制）"""
        current_time = time.time()
        time_since_last = current_time - self._last_adjustment_time
        return time_since_last >= self.MIN_ADJUSTMENT_INTERVAL


# -------------------- PersistentProcessPool --------------------


class PersistentProcessPool:
    """持久化进程池（支持动态调整）

    核心特性：
    - 单例模式：全局唯一进程池
    - 延迟初始化：首次使用时才创建
    - 动态调整：支持resize()动态调整进程数
    - 线程安全：多线程环境下安全使用
    """

    _instance = None  # type: Optional[PersistentProcessPool]
    _lock = threading.Lock()

    def __init__(self):
        """初始化持久化进程池（不要直接调用，请使用get_instance()）"""
        self.logger = logging.getLogger(__name__)
        self._pool: Optional["multiprocessing.Pool"] = None
        self._current_size = 0
        self._initialized = False
        self._pool_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "PersistentProcessPool":
        """获取单例实例（线程安全）"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def initialize(self, processes: Optional[int] = None, force: bool = False) -> bool:
        """初始化进程池"""
        with self._pool_lock:
            if self._initialized and not force:
                self.logger.debug("进程池已初始化(%s进程)，跳过初始化", self._current_size)
                return True

            if processes is None:
                processes = min(multiprocessing.cpu_count(), 8)

            try:
                if self._pool is not None:
                    self.logger.info("关闭旧进程池(%s进程)...", self._current_size)
                    self._pool.close()
                    self._pool.join()

                self.logger.info("创建持久化进程池: %s进程", processes)
                self._pool = multiprocessing.Pool(processes=processes)
                self._current_size = processes
                self._initialized = True

                return True
            except Exception as e:
                self.logger.error("初始化进程池失败: %s", e, exc_info=True)
                self._pool = None
                self._current_size = 0
                self._initialized = False
                return False

    def resize(self, new_size: int) -> bool:
        """动态调整进程池大小"""
        with self._pool_lock:
            if new_size == self._current_size:
                self.logger.debug("进程数未变化(%s)，跳过调整", new_size)
                return True

            self.logger.info("调整进程池大小: %s → %s进程", self._current_size, new_size)
            return self.initialize(processes=new_size, force=True)

    def map(self, func, iterable, chunksize=None):
        """使用进程池执行map操作"""
        with self._pool_lock:
            if not self._initialized or self._pool is None:
                self.logger.warning("进程池未初始化，自动初始化...")
                if not self.initialize():
                    raise RuntimeError("进程池初始化失败")

            if self._pool is None:
                raise RuntimeError("进程池初始化后仍为None")

            return self._pool.map(func, iterable, chunksize=chunksize)

    def is_initialized(self) -> bool:
        """检查进程池是否已初始化"""
        with self._pool_lock:
            return self._initialized and self._pool is not None

    def get_size(self) -> int:
        """获取当前进程池大小"""
        with self._pool_lock:
            return self._current_size

    def shutdown(self, wait: bool = True):
        """关闭进程池并释放资源"""
        with self._pool_lock:
            if self._pool is not None:
                self.logger.info("关闭持久化进程池(%s进程)...", self._current_size)
                try:
                    self._pool.close()
                    if wait:
                        self._pool.join()
                except Exception as e:
                    self.logger.error("关闭进程池异常: %s", e, exc_info=True)
                finally:
                    self._pool = None
                    self._current_size = 0
                    self._initialized = False


# -------------------- MultiProcessBatchModel --------------------


class MultiProcessBatchModel(ExecutionModel):
    """多进程+批处理模型（磁盘IO密集任务）

    特点：
    - 多进程绕过GIL
    - 批量处理减少进程间通信开销
    - 使用持久化进程池
    - 动态调整进程数

    用途：
    - 品种数据扫描
    - 品种日期读取
    """

    SAFE_ZONE_LOWER = 65.0
    SAFE_ZONE_UPPER = 75.0
    INCREASE_STEP = 0.05
    DECREASE_STEP = 0.10
    CHECK_INTERVAL = 1.5
    MIN_ADJUSTMENT_INTERVAL = 3.0

    def __init__(self):
        super().__init__()
        self._stop_flag = threading.Event()
        self._adjustment_lock = threading.Lock()
        self._last_adjustment_time = 0.0
        self._current_processes = 0
        self._min_processes_limit = 2
        self._max_processes_limit = min(multiprocessing.cpu_count(), 8)
        self._resource_monitor = None
        self._adjustment_count = 0
        self._increase_count = 0
        self._decrease_count = 0
        self._process_pool = PersistentProcessPool.get_instance()
        self._pool_initialized = False

        self.logger.info("✅ MultiProcessBatchModel 初始化完成（使用持久化进程池）")

    def execute_with_monitoring(
        self,
        task_units: List[TaskUnit],
        config: Any,
        resource_monitor: Any,
        adjustment_strategy: Any,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[TaskResult]:
        """执行任务（带动态进程数调整）"""
        if not task_units:
            self.logger.warning("任务单元列表为空，跳过执行")
            return []

        self.logger.info(
            "🚀 开始执行磁盘IO任务：%s个单元，初始配置: %s进程，批次大小%s",
            len(task_units),
            config.max_workers,
            config.batch_size,
        )

        self._resource_monitor = resource_monitor
        self._current_processes = config.max_workers
        batch_size = config.batch_size

        # 初始化持久化进程池
        if not self._pool_initialized or not self._process_pool.is_initialized():
            self.logger.info("🔧 初始化持久化进程池: %s进程", self._current_processes)
            self._process_pool.initialize(processes=self._current_processes)
            self._pool_initialized = True
        else:
            if self._process_pool.get_size() != self._current_processes:
                self.logger.info(
                    "🔧 调整持久化进程池大小: %s → %s进程",
                    self._process_pool.get_size(),
                    self._current_processes,
                )
                self._process_pool.resize(self._current_processes)

        self._stop_flag.clear()

        # 启动监控线程
        monitor_thread = threading.Thread(
            target=self._adjustment_monitor_thread, name="MultiProcessBatch-Monitor", daemon=True
        )
        monitor_thread.start()

        results = []

        try:
            total_tasks = len(task_units)
            completed = 0
            batch_count = 0

            for i in range(0, total_tasks, batch_size):
                batch = task_units[i : i + batch_size]
                batch_count += 1

                self.logger.debug(
                    "处理批次 %s: %s个任务(%s/%s已完成, %s进程)",
                    batch_count,
                    len(batch),
                    completed,
                    total_tasks,
                    self._current_processes,
                )

                batch_results = self._process_pool.map(_process_task_unit, batch)
                results.extend(batch_results)

                completed += len(batch)

                if progress_callback:
                    progress_callback(completed, total_tasks)

                percent = int((completed / total_tasks) * 100)
                self.logger.info(
                    "  进度: %s/%s (%s%%), 当前%s进程",
                    completed,
                    total_tasks,
                    percent,
                    self._current_processes,
                )

            self.logger.info(
                "✅ 任务执行完成：共%s个结果，调整次数%s次", len(results), self._adjustment_count
            )
            return results

        except Exception as e:
            self.logger.error("任务执行失败: %s", e, exc_info=True)
            return results

        finally:
            self._stop_flag.set()
            monitor_thread.join(timeout=2.0)

            self.logger.info(
                "📊 执行统计: 调整%s次(增加%s次, 减少%s次)",
                self._adjustment_count,
                self._increase_count,
                self._decrease_count,
            )

    def _adjustment_monitor_thread(self):
        """独立监控线程"""
        self.logger.debug("🎯 启动进程数动态调整监控线程")

        while not self._stop_flag.is_set():
            try:
                self._stop_flag.wait(self.CHECK_INTERVAL)

                if self._stop_flag.is_set():
                    break

                if self._resource_monitor is None:
                    continue

                pressure = self._resource_monitor.get_current_pressure()

                if pressure.score < self.SAFE_ZONE_LOWER:
                    self._try_increase_processes(pressure)
                elif pressure.score > self.SAFE_ZONE_UPPER:
                    self._try_decrease_processes(pressure)

            except Exception as e:
                self.logger.error("监控线程异常: %s", e, exc_info=True)

        self.logger.debug("✅ 监控线程已停止")

    def _try_increase_processes(self, pressure):
        """尝试增加进程数"""
        with self._adjustment_lock:
            if not self._can_adjust():
                return

            old_processes = self._current_processes
            new_processes = int(old_processes * (1 + self.INCREASE_STEP))
            new_processes = min(new_processes, self._max_processes_limit)

            if new_processes > old_processes:
                self._current_processes = new_processes
                self._last_adjustment_time = time.time()
                self._adjustment_count += 1
                self._increase_count += 1

                try:
                    self._process_pool.resize(new_processes)
                except Exception as e:
                    self.logger.error("调整进程池大小失败: %s", e)

                self.logger.info(
                    "⬆️  增加进程数: %s → %s (压力%.1f%% < %.0f%%)",
                    old_processes,
                    new_processes,
                    pressure.score,
                    self.SAFE_ZONE_LOWER,
                )

    def _try_decrease_processes(self, pressure):
        """尝试减少进程数"""
        with self._adjustment_lock:
            if not self._can_adjust():
                return

            old_processes = self._current_processes
            new_processes = int(old_processes * (1 - self.DECREASE_STEP))
            new_processes = max(new_processes, self._min_processes_limit)

            if new_processes < old_processes:
                self._current_processes = new_processes
                self._last_adjustment_time = time.time()
                self._adjustment_count += 1
                self._decrease_count += 1

                try:
                    self._process_pool.resize(new_processes)
                except Exception as e:
                    self.logger.error("调整进程池大小失败: %s", e)

                self.logger.info(
                    "⬇️  减少进程数: %s → %s (压力%.1f%% > %.0f%%)",
                    old_processes,
                    new_processes,
                    pressure.score,
                    self.SAFE_ZONE_UPPER,
                )

    def _can_adjust(self) -> bool:
        """检查是否可以调整"""
        current_time = time.time()
        time_since_last = current_time - self._last_adjustment_time
        return time_since_last >= self.MIN_ADJUSTMENT_INTERVAL


# -------------------- 辅助函数 --------------------


def _process_task_unit(task_unit: TaskUnit) -> TaskResult:
    """处理单个任务单元（顶层函数，用于multiprocessing.Pool.map）"""
    # 优化原因：统一子进程日志格式
    # 问题：子进程使用标准logging.getLogger，日志输出到stderr，与主进程日志格式不统一
    # 解决：为每个子进程创建带PID的logger，日志会自动被主进程的loghub拦截并路由到AI日志文件
    # 效果：1) 子进程日志输出到logs/ai/目录 2) 可追踪每个进程的执行过程 3) 日志格式统一
    import logging

    logger = logging.getLogger(f"load_balancer.subprocess.{multiprocessing.current_process().pid}")

    try:
        logger.debug(f"处理任务单元: {task_unit.unit_id}")
        if task_unit.processor:
            result_data = task_unit.processor(task_unit.data)
            return TaskResult(unit_id=task_unit.unit_id, success=True, data=result_data)
        else:
            return TaskResult(unit_id=task_unit.unit_id, success=True, data=task_unit.data)
    except Exception as e:
        logger.error(f"处理任务单元失败: {e}", exc_info=True)
        return TaskResult(unit_id=task_unit.unit_id, success=False, error=str(e))


def _process_async_batch(batch_info: tuple) -> List[TaskResult]:
    """处理异步任务批次（顶层函数，用于multiprocessing.Pool.map）

    每个进程运行一个asyncio事件循环，并发执行多个协程。
    """
    # 优化原因：统一子进程日志格式（与_process_task_unit保持一致）
    # 问题：多进程异步任务的日志散落在stderr，难以追踪和调试
    # 解决：为每个子进程初始化logger，命名包含PID便于区分不同进程
    # 效果：服务器池测速等异步任务的日志都会归集到AI日志文件，便于排查问题
    import logging

    logger = logging.getLogger(f"load_balancer.subprocess.{multiprocessing.current_process().pid}")

    task_units, coroutines_count = batch_info
    logger.debug(f"处理异步任务批次: {len(task_units)} 个任务，协程数={coroutines_count}")

    async def process_task_async(task_unit: TaskUnit) -> TaskResult:
        """异步处理单个任务单元"""
        try:
            if task_unit.processor:
                # 如果processor是协程函数
                if asyncio.iscoroutinefunction(task_unit.processor):
                    result_data = await task_unit.processor(task_unit.data)
                else:
                    # 如果是普通函数，在线程池中运行避免阻塞
                    loop = asyncio.get_event_loop()
                    result_data = await loop.run_in_executor(
                        None, task_unit.processor, task_unit.data
                    )
                return TaskResult(unit_id=task_unit.unit_id, success=True, data=result_data)
            else:
                return TaskResult(unit_id=task_unit.unit_id, success=True, data=task_unit.data)
        except Exception as e:
            return TaskResult(unit_id=task_unit.unit_id, success=False, error=str(e))

    async def run_batch():
        """运行批次任务（限制并发协程数）"""
        semaphore = asyncio.Semaphore(coroutines_count)

        async def limited_process(task_unit):
            async with semaphore:
                return await process_task_async(task_unit)

        tasks = [limited_process(unit) for unit in task_units]
        return await asyncio.gather(*tasks)

    # 运行事件循环
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(run_batch())
        loop.close()
        return results
    except Exception as e:
        return [
            TaskResult(unit_id=unit.unit_id, success=False, error=str(e)) for unit in task_units
        ]


# -------------------- StreamProcessingModel --------------------


class StreamProcessingModel(ExecutionModel):
    """流式处理模型（内存受限任务）

    特点：
    - 小批次流式处理
    - 动态调整批次大小
    - 低内存占用
    """

    def __init__(self):
        super().__init__()
        self.logger.info("✅ StreamProcessingModel 初始化完成")

    def execute_with_monitoring(
        self,
        task_units: List[TaskUnit],
        config: Any,
        resource_monitor: Any,
        adjustment_strategy: Any,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[TaskResult]:
        """执行任务（流式处理）"""
        total_units = len(task_units)
        if total_units == 0:
            return []

        self.logger.info("开始流式处理：%s个单元，批次%s", total_units, config.batch_size)

        current_batch_size = config.batch_size
        results: List[TaskResult] = []
        completed_count = 0
        adjustment_count = 0

        batch_start = 0
        batch_index = 0

        while batch_start < total_units:
            batch_end = min(batch_start + current_batch_size, total_units)
            batch = task_units[batch_start:batch_end]

            self.logger.debug(
                "流式批次 %s: %s 个单元(%s-%s/%s)",
                batch_index + 1,
                len(batch),
                batch_start + 1,
                batch_end,
                total_units,
            )

            # 单线程处理批次
            for unit in batch:
                try:
                    result_data = self._process_unit(unit)
                    result = TaskResult(
                        unit_id=unit.unit_id,
                        success=True,
                        data=result_data,
                    )
                except Exception as e:
                    result = TaskResult(
                        unit_id=unit.unit_id,
                        success=False,
                        error=str(e),
                    )

                results.append(result)
                completed_count += 1

                if progress_callback:
                    progress_callback(completed_count, total_units)

            # 动态调整批次大小
            batch_index += 1
            batch_start = batch_end

            if batch_start < total_units:
                pressure = resource_monitor.get_current_pressure()

                if pressure.below_low_threshold:
                    new_batch_size = int(
                        current_batch_size * (1 + adjustment_strategy.increase_step)
                    )

                    if new_batch_size > current_batch_size:
                        self.logger.info(
                            "🚀 压力低(%.1f%%)，增大批次: %s → %s",
                            pressure.score,
                            current_batch_size,
                            new_batch_size,
                        )
                        current_batch_size = new_batch_size
                        adjustment_count += 1

                elif pressure.above_high_threshold:
                    new_batch_size = max(
                        10, int(current_batch_size * (1 - adjustment_strategy.decrease_step))
                    )

                    if new_batch_size < current_batch_size:
                        self.logger.warning(
                            "⚠️ 内存压力高(%.1f%%)，减小批次: %s → %s",
                            pressure.score,
                            current_batch_size,
                            new_batch_size,
                        )
                        current_batch_size = new_batch_size
                        adjustment_count += 1

        success_count = sum(1 for r in results if r.success)
        self.logger.info(
            "流式处理完成：%s/%s 成功, 动态调整 %s 次", success_count, total_units, adjustment_count
        )

        return results

    def _process_unit(self, unit: TaskUnit) -> Any:
        """处理单个任务单元"""
        if unit.processor:
            return unit.processor(unit.data)
        else:
            return unit.data


# -------------------- 自适应批次计算器（完整实现）--------------------


class AdaptiveBatchSizeCalculatorFull:
    """自适应批次大小计算器（完整版）

    根据任务类型、系统资源和任务规模动态计算最优批次大小。
    """

    # 基准批次大小（按IO类型）
    BASELINE_BATCH_SIZES = {
        "disk": 50,
        "network": 100,
        "memory": 20,
        "cpu": 30,
    }

    # 内存压力阈值
    MEMORY_LOW_THRESHOLD = 40.0
    MEMORY_MEDIUM_THRESHOLD = 70.0

    # 任务数量阈值
    TASK_COUNT_SMALL = 100
    TASK_COUNT_MEDIUM = 1000

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._history: Dict[str, list] = {}

    def calculate(
        self,
        task_count: int,
        io_type: str = "disk",
        memory_pressure: Optional[float] = None,
        min_batch: int = 10,
        max_batch: int = 200,
    ) -> int:
        """计算最优批次大小"""
        if memory_pressure is None:
            memory_pressure = self._get_memory_pressure()

        base_batch = self.BASELINE_BATCH_SIZES.get(io_type, 50)
        batch_size = self._adjust_for_memory(base_batch, memory_pressure)
        batch_size = self._adjust_for_task_count(batch_size, task_count)
        batch_size = max(min_batch, min(batch_size, max_batch))
        batch_size = min(batch_size, task_count)

        self.logger.debug(
            "计算批次大小: 任务数=%s, IO类型=%s, 内存压力=%.1f%% → 批次=%s",
            task_count,
            io_type,
            memory_pressure,
            batch_size,
        )

        return batch_size

    def _get_memory_pressure(self) -> float:
        """获取当前内存压力"""
        if HAS_PSUTIL:
            try:
                return psutil.virtual_memory().percent
            except Exception as e:
                self.logger.warning("获取内存压力失败: %s", e)
        return 50.0

    def _adjust_for_memory(self, base_batch: int, memory_pressure: float) -> int:
        """根据内存压力调整批次大小"""
        if memory_pressure < self.MEMORY_LOW_THRESHOLD:
            factor = 1.2
        elif memory_pressure < self.MEMORY_MEDIUM_THRESHOLD:
            factor = 1.0
        else:
            overpressure = memory_pressure - self.MEMORY_MEDIUM_THRESHOLD
            factor = max(0.4, 1.0 - (overpressure / 30.0) * 0.6)

        return int(base_batch * factor)

    def _adjust_for_task_count(self, batch_size: int, task_count: int) -> int:
        """根据任务总数调整批次大小"""
        if task_count < self.TASK_COUNT_SMALL:
            factor = 2.0
            adjusted = int(batch_size * factor)
            return min(adjusted, task_count // 2 if task_count > 2 else task_count)
        elif task_count < self.TASK_COUNT_MEDIUM:
            return batch_size
        else:
            factor = 0.9
            return int(batch_size * factor)


# -------------------- 流式处理组件 --------------------


class ChunkReader:
    """分块读取器

    支持从大文件中逐块读取数据，减少内存占用。
    """

    def __init__(
        self,
        file_path: Union[str, Path],
        chunk_size: int = 10000,
        file_format: str = "parquet",
    ):
        self.logger = logging.getLogger(__name__)
        self.file_path = Path(file_path)
        self.chunk_size = chunk_size
        self.file_format = file_format.lower()

    def read_chunks(self) -> Generator[pd.DataFrame, None, None]:
        """逐块读取文件"""
        if not self.file_path.exists():
            self.logger.error("文件不存在: %s", self.file_path)
            return

        try:
            if self.file_format == "parquet":
                yield from self._read_parquet_chunks()
            elif self.file_format == "csv":
                yield from self._read_csv_chunks()
            else:
                self.logger.error("不支持的文件格式: %s", self.file_format)
                return

        except Exception as e:
            self.logger.error("读取文件失败 %s: %s", self.file_path, e, exc_info=True)

    def _read_parquet_chunks(self) -> Generator[pd.DataFrame, None, None]:
        """读取Parquet文件块"""
        try:
            df = pd.read_parquet(self.file_path)
            total_rows = len(df)

            for start_idx in range(0, total_rows, self.chunk_size):
                end_idx = min(start_idx + self.chunk_size, total_rows)
                chunk = df.iloc[start_idx:end_idx].copy()
                yield chunk

        except Exception as e:
            self.logger.error("读取Parquet文件失败: %s", e)
            raise

    def _read_csv_chunks(self) -> Generator[pd.DataFrame, None, None]:
        """读取CSV文件块"""
        try:
            for chunk in pd.read_csv(self.file_path, chunksize=self.chunk_size):
                yield chunk

        except Exception as e:
            self.logger.error("读取CSV文件失败: %s", e)
            raise


class StreamAggregator:
    """流式聚合器

    在处理过程中进行增量聚合，减少内存占用。
    """

    def __init__(self, aggregation_type: str = "sum"):
        self.logger = logging.getLogger(__name__)
        self.aggregation_type = aggregation_type
        self._count = 0
        self._sum = 0.0
        self._min: float = float("inf")
        self._max: float = float("-inf")
        self._custom_data: List[Any] = []

    def _reset(self):
        """重置聚合状态"""
        self._count = 0
        self._sum = 0.0
        self._min = float("inf")
        self._max = float("-inf")
        self._custom_data = []

    def add(self, value: Any):
        """添加值到聚合器"""
        self._count += 1

        if isinstance(value, (int, float)):
            self._sum += value
            self._min = min(self._min, value)
            self._max = max(self._max, value)
        elif isinstance(value, dict):
            self._custom_data.append(value)
        else:
            self._custom_data.append(value)

    def get_result(self) -> Dict[str, Any]:
        """获取聚合结果"""
        result: Dict[str, Any] = {"count": self._count}

        if self.aggregation_type == "sum":
            result["sum"] = float(self._sum)
        elif self.aggregation_type == "mean":
            result["mean"] = float(self._sum / self._count if self._count > 0 else 0.0)
        elif self.aggregation_type == "min":
            result["min"] = None if self._min == float("inf") else float(self._min)
        elif self.aggregation_type == "max":
            result["max"] = None if self._max == float("-inf") else float(self._max)
        elif self.aggregation_type == "custom":
            result["data"] = list(self._custom_data)

        return result


class EnhancedStreamProcessor:
    """增强型流式处理器

    组合ChunkReader和StreamAggregator，提供完整的流式处理能力。
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def process_file(
        self,
        file_path: Union[str, Path],
        processor_func: Callable[[pd.DataFrame], Any],
        aggregation_type: str = "count",
        chunk_size: int = 10000,
        file_format: str = "parquet",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """流式处理文件"""
        self.logger.info("开始流式处理文件: %s, 块大小: %s", file_path, chunk_size)

        reader = ChunkReader(file_path=file_path, chunk_size=chunk_size, file_format=file_format)
        aggregator = StreamAggregator(aggregation_type=aggregation_type)

        chunk_count = 0
        total_rows = 0

        try:
            for chunk in reader.read_chunks():
                chunk_count += 1
                chunk_rows = len(chunk)
                total_rows += chunk_rows

                self.logger.debug("处理块 %s: %s 行", chunk_count, chunk_rows)

                try:
                    result = processor_func(chunk)
                    aggregator.add(result)
                except Exception as e:
                    self.logger.error("处理块 %s 失败: %s", chunk_count, e)
                    aggregator.add({"error": str(e)})

                if progress_callback and chunk_count % 10 == 0:
                    progress_callback(chunk_count, -1)

            result = aggregator.get_result()
            result["total_chunks"] = chunk_count
            result["total_rows"] = total_rows

            self.logger.info(
                "✅ 流式处理完成: %s块, %s行, 聚合结果: %s",
                chunk_count,
                total_rows,
                result.get("count", 0),
            )

            return result

        except Exception as e:
            self.logger.error("流式处理失败: %s", e, exc_info=True)
            return {"error": str(e), "total_chunks": chunk_count, "total_rows": total_rows}

    def process_dataframe_stream(
        self,
        df: pd.DataFrame,
        processor_func: Callable[[pd.DataFrame], Any],
        chunk_size: int = 10000,
        aggregation_type: str = "count",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """流式处理DataFrame"""
        self.logger.info("开始流式处理DataFrame: %s行, 块大小: %s", len(df), chunk_size)

        aggregator = StreamAggregator(aggregation_type=aggregation_type)

        total_rows = len(df)
        chunk_count = 0

        try:
            for start_idx in range(0, total_rows, chunk_size):
                end_idx = min(start_idx + chunk_size, total_rows)
                chunk = df.iloc[start_idx:end_idx]
                chunk_count += 1

                self.logger.debug(
                    "处理块 %s: 行%s-%s (%s行)", chunk_count, start_idx, end_idx, len(chunk)
                )

                try:
                    result = processor_func(chunk)
                    aggregator.add(result)
                except Exception as e:
                    self.logger.error("处理块 %s 失败: %s", chunk_count, e)
                    aggregator.add({"error": str(e)})

                if progress_callback:
                    progress_callback(end_idx, total_rows)

            result = aggregator.get_result()
            result["total_chunks"] = chunk_count
            result["total_rows"] = total_rows

            self.logger.info("✅ 流式处理完成: %s块, %s行", chunk_count, total_rows)

            return result

        except Exception as e:
            self.logger.error("流式处理失败: %s", e, exc_info=True)
            return {"error": str(e), "total_chunks": chunk_count, "total_rows": total_rows}


# -------------------- 便捷访问函数 --------------------


def get_process_pool() -> PersistentProcessPool:
    """获取全局持久化进程池实例"""
    return PersistentProcessPool.get_instance()


def get_adaptive_batch_calculator() -> AdaptiveBatchSizeCalculatorFull:
    """获取全局自适应批次计算器实例"""
    global _global_batch_calculator
    if _global_batch_calculator is None:
        _global_batch_calculator = AdaptiveBatchSizeCalculatorFull()
    return _global_batch_calculator


_global_batch_calculator: Optional[AdaptiveBatchSizeCalculatorFull] = None


# ==============================================================================
# 第5部分：队列系统（任务队列、QThread Worker、调度器、队列门面）
# ==============================================================================


# -------------------- 任务队列核心 --------------------


class TaskPriority(Enum):
    """任务优先级枚举

    优先级说明：
    - URGENT: UI交互触发的小任务（如单品种查询）
    - HIGH: 用户主动请求的任务（如增量下载）
    - NORMAL: 后台维护任务（如数据质量扫描）
    - LOW: 延迟任务（如历史数据补全）
    """

    URGENT = 0  # 紧急任务
    HIGH = 1  # 高优先级
    NORMAL = 2  # 普通优先级
    LOW = 3  # 低优先级


class TaskStatus(Enum):
    """任务状态枚举"""

    QUEUED = "queued"  # 已入队
    RUNNING = "running"  # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


@dataclass
class TaskMetadata:
    """任务元数据

    记录任务的完整信息，用于追踪和监控。
    """

    task_id: str
    task_units: List[TaskUnit]
    priority: TaskPriority
    status: TaskStatus
    submit_time: float = field(default_factory=time.time)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    results: Optional[List[TaskResult]] = None
    error: Optional[str] = None

    @property
    def wait_time(self) -> float:
        """获取等待时间（秒）"""
        if self.start_time is None:
            return time.time() - self.submit_time
        return self.start_time - self.submit_time

    @property
    def execution_time(self) -> Optional[float]:
        """获取执行时间（秒）"""
        if self.start_time is None:
            return None
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def total_time(self) -> float:
        """获取总时间（秒）"""
        end = self.end_time or time.time()
        return end - self.submit_time


class TaskQueue:
    """线程安全的任务队列

    特性：
    - 基于优先级队列（PriorityQueue）
    - 线程安全（使用锁保护）
    - 任务注册表（追踪所有任务）
    - 支持任务取消
    """

    def __init__(self, maxsize: int = 10000):
        """初始化任务队列

        Args:
            maxsize: 队列最大容量
        """
        self._queue = queue.PriorityQueue(maxsize=maxsize)
        self._task_registry: Dict[str, TaskMetadata] = {}
        self._lock = threading.Lock()
        self._task_id_counter = 0
        self.logger = logging.getLogger(__name__)

    def submit(
        self, task_units: List[TaskUnit], priority: TaskPriority = TaskPriority.NORMAL
    ) -> str:
        """提交任务到队列（线程安全）

        Args:
            task_units: 任务单元列表
            priority: 任务优先级

        Returns:
            str: 任务ID
        """
        with self._lock:
            # 生成任务ID
            self._task_id_counter += 1
            task_id = f"task_{self._task_id_counter}_{int(time.time())}"

            # 创建任务元数据
            metadata = TaskMetadata(
                task_id=task_id,
                task_units=task_units,
                priority=priority,
                status=TaskStatus.QUEUED,
            )

            # 注册任务
            self._task_registry[task_id] = metadata

            # 入队（优先级值越小越优先）
            self._queue.put((priority.value, task_id, task_units))

            self.logger.info(
                "📥 任务已提交: %s, 优先级=%s, 单元数=%d, 队列长度=%d",
                task_id,
                priority.name,
                len(task_units),
                self.qsize(),
            )

            return task_id

    def get(self, block: bool = True, timeout: Optional[float] = None) -> tuple:
        """从队列获取任务（线程安全）

        Args:
            block: 是否阻塞等待
            timeout: 超时时间（秒）

        Returns:
            tuple: (task_id, task_units)

        Raises:
            queue.Empty: 队列为空且不阻塞时
        """
        _priority_value, task_id, task_units = self._queue.get(block=block, timeout=timeout)

        # 更新任务状态
        with self._lock:
            if task_id in self._task_registry:
                metadata = self._task_registry[task_id]
                metadata.status = TaskStatus.RUNNING
                metadata.start_time = time.time()

        return task_id, task_units

    def mark_completed(self, task_id: str, results: List[TaskResult]):
        """标记任务为已完成

        Args:
            task_id: 任务ID
            results: 任务结果列表
        """
        with self._lock:
            if task_id in self._task_registry:
                metadata = self._task_registry[task_id]
                metadata.status = TaskStatus.COMPLETED
                metadata.end_time = time.time()
                metadata.results = results

                self.logger.info(
                    "✅ 任务完成: %s, 等待=%.2fs, 执行=%.2fs",
                    task_id,
                    metadata.wait_time,
                    metadata.execution_time,
                )

    def mark_failed(self, task_id: str, error: str):
        """标记任务为失败

        Args:
            task_id: 任务ID
            error: 错误信息
        """
        with self._lock:
            if task_id in self._task_registry:
                metadata = self._task_registry[task_id]
                metadata.status = TaskStatus.FAILED
                metadata.end_time = time.time()
                metadata.error = error

                self.logger.error("❌ 任务失败: %s, 错误=%s", task_id, error)

    def cancel(self, task_id: str) -> bool:
        """取消任务（仅对未开始的任务有效）

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功取消
        """
        with self._lock:
            if task_id in self._task_registry:
                metadata = self._task_registry[task_id]
                if metadata.status == TaskStatus.QUEUED:
                    metadata.status = TaskStatus.CANCELLED
                    metadata.end_time = time.time()
                    self.logger.info("🚫 任务已取消: %s", task_id)
                    return True
        return False

    def qsize(self) -> int:
        """获取队列长度"""
        return self._queue.qsize()

    def get_metadata(self, task_id: str) -> Optional[TaskMetadata]:
        """获取任务元数据

        Args:
            task_id: 任务ID

        Returns:
            Optional[TaskMetadata]: 任务元数据，不存在返回None
        """
        with self._lock:
            return self._task_registry.get(task_id)

    def get_all_metadata(self) -> Dict[str, TaskMetadata]:
        """获取所有任务元数据（副本）"""
        with self._lock:
            return self._task_registry.copy()

    def get_metrics(self) -> Dict[str, Any]:
        """获取队列统计指标

        Returns:
            Dict[str, Any]: 统计指标字典
        """
        with self._lock:
            total_tasks = len(self._task_registry)
            status_counts = {status: 0 for status in TaskStatus}
            priority_counts = {priority: 0 for priority in TaskPriority}

            wait_times = []
            execution_times = []

            for metadata in self._task_registry.values():
                status_counts[metadata.status] += 1
                priority_counts[metadata.priority] += 1

                if metadata.start_time is not None:
                    wait_times.append(metadata.wait_time)
                    if metadata.end_time is not None:
                        execution_times.append(metadata.execution_time)

            return {
                "queue_length": self.qsize(),
                "total_tasks": total_tasks,
                "status_counts": {s.value: count for s, count in status_counts.items()},
                "priority_counts": {p.name: count for p, count in priority_counts.items()},
                "avg_wait_time": sum(wait_times) / len(wait_times) if wait_times else 0,
                "avg_execution_time": (
                    sum(execution_times) / len(execution_times) if execution_times else 0
                ),
            }


# -------------------- QThread Worker --------------------


class QTaskWorker(QObject):
    """基于PySide6 QObject的任务Worker

    在独立的QThread中运行，从队列获取任务并执行。
    通过Signal/Slot机制与主线程通信，确保线程安全。
    """

    # 信号定义
    task_started = Signal(str)  # 任务开始 (task_id)
    task_progress = Signal(str, int, int)  # 任务进度 (task_id, completed, total)
    task_completed = Signal(str, list)  # 任务完成 (task_id, results)
    task_failed = Signal(str, str)  # 任务失败 (task_id, error)

    def __init__(self, task_queue: TaskQueue, execution_callback: Callable):
        """初始化Worker

        Args:
            task_queue: 任务队列
            execution_callback: 执行回调函数，签名为 (task_units) -> List[TaskResult]
        """
        super().__init__()
        self.task_queue = task_queue
        self.execution_callback = execution_callback
        self.is_running = False
        self.logger = logging.getLogger(__name__)

    @Slot()
    def run(self):
        """运行Worker（在QThread中调用）

        循环从队列获取任务并执行，直到停止。
        """
        self.is_running = True
        self.logger.info("🚀 TaskWorker 已启动")

        while self.is_running:
            try:
                # 从队列获取任务（阻塞等待，超时1秒）
                task_id, task_units = self.task_queue.get(block=True, timeout=1.0)

                # 发送任务开始信号
                self.task_started.emit(task_id)
                self.logger.info("🔄 开始执行任务: %s, 单元数=%d", task_id, len(task_units))

                # 执行任务
                try:
                    results = self.execution_callback(
                        task_units,
                        progress_callback=lambda c, t: self.task_progress.emit(task_id, c, t),
                    )

                    # 标记完成
                    self.task_queue.mark_completed(task_id, results)
                    self.task_completed.emit(task_id, results)

                except Exception as e:
                    error_msg = str(e)
                    self.logger.error("❌ 任务执行失败: %s, %s", task_id, error_msg, exc_info=True)

                    # 标记失败
                    self.task_queue.mark_failed(task_id, error_msg)
                    self.task_failed.emit(task_id, error_msg)

            except queue.Empty:
                # 队列为空，继续等待
                continue
            except Exception as e:
                self.logger.error("Worker异常: %s", str(e), exc_info=True)

        self.logger.info("✅ TaskWorker 已停止")

    def stop(self):
        """停止Worker"""
        self.is_running = False


class TaskQueueManager:
    """任务队列管理器

    管理任务队列和多个Worker线程。
    协调任务提交、执行和结果收集。
    """

    def __init__(self, max_workers: int = 4, queue_maxsize: int = 10000):
        """初始化管理器

        Args:
            max_workers: 最大Worker数量
            queue_maxsize: 队列最大容量
        """
        self.task_queue = TaskQueue(maxsize=queue_maxsize)
        self.max_workers = max_workers
        self.workers: List[QTaskWorker] = []
        self.threads: List[QThread] = []
        self.is_running = False
        self.logger = logging.getLogger(__name__)

        # 性能统计
        self._start_time = 0.0
        self._completed_tasks = 0

    def start(self, execution_callback: Callable):
        """启动管理器

        Args:
            execution_callback: 执行回调函数
        """
        if self.is_running:
            self.logger.warning("任务队列管理器已在运行")
            return

        self.logger.info("🚀 启动任务队列管理器: %d个Worker", self.max_workers)
        self.is_running = True
        self._start_time = time.time()

        # 创建Worker和线程
        for i in range(self.max_workers):
            # 创建Worker
            worker = QTaskWorker(self.task_queue, execution_callback)

            # 创建线程
            thread = QThread()
            worker.moveToThread(thread)

            # 连接信号
            thread.started.connect(worker.run)
            worker.task_completed.connect(self._on_task_completed)
            worker.task_failed.connect(self._on_task_failed)

            # 保存引用
            self.workers.append(worker)
            self.threads.append(thread)

            # 启动线程
            thread.start()
            self.logger.debug("Worker-%d 已启动", i)

    def stop(self):
        """停止管理器"""
        if not self.is_running:
            return

        self.logger.info("🛑 停止任务队列管理器...")
        self.is_running = False

        # 停止所有Worker
        for worker in self.workers:
            worker.stop()

        # 等待所有线程结束
        for thread in self.threads:
            thread.quit()
            thread.wait(5000)  # 最多等待5秒（毫秒）

        self.workers.clear()
        self.threads.clear()

        self.logger.info("✅ 任务队列管理器已停止")

    def submit_task(
        self, task_units: List[TaskUnit], priority: TaskPriority = TaskPriority.NORMAL
    ) -> str:
        """提交任务

        Args:
            task_units: 任务单元列表
            priority: 任务优先级

        Returns:
            str: 任务ID
        """
        return self.task_queue.submit(task_units, priority)

    def get_metrics(self) -> Dict[str, Any]:
        """获取管理器统计指标

        Returns:
            Dict[str, Any]: 统计指标字典
        """
        queue_metrics = self.task_queue.get_metrics()

        # 计算吞吐量
        elapsed = time.time() - self._start_time
        throughput = self._completed_tasks / elapsed if elapsed > 0 else 0

        return {
            **queue_metrics,
            "workers": self.max_workers,
            "completed_tasks": self._completed_tasks,
            "throughput": throughput,  # 任务/秒
        }

    @Slot(str, list)
    def _on_task_completed(self, task_id: str, _results: List[TaskResult]):
        """任务完成回调"""
        self._completed_tasks += 1
        self.logger.debug("✅ 任务完成: %s, 总计完成%d个任务", task_id, self._completed_tasks)

    @Slot(str, str)
    def _on_task_failed(self, task_id: str, error: str):
        """任务失败回调"""
        self.logger.error("❌ 任务失败: %s, 错误=%s", task_id, error)


# -------------------- 智能调度器 --------------------


@dataclass
class ExecutionStrategy:
    """执行策略配置

    定义任务的执行方式和资源限制。
    """

    mode: str  # 执行模式：'direct' 或 'queued'
    max_workers: int  # 最大Worker数量
    priority: TaskPriority  # 任务优先级
    resource_limits: str  # 资源限制级别：'strict', 'moderate', 'relaxed'

    def __repr__(self):
        return (
            f"ExecutionStrategy(mode={self.mode}, workers={self.max_workers}, "
            f"priority={self.priority.name}, limits={self.resource_limits})"
        )


class AdaptiveScheduler:
    """自适应调度器

    根据任务规模动态决定执行策略：
    - 小任务（<100）：直接执行，保证UI响应
    - 中等任务（100-1000）：队列执行，平衡模式
    - 大任务（>1000）：队列执行，效率优先
    """

    # 任务规模阈值
    SMALL_TASK_THRESHOLD = 100
    MEDIUM_TASK_THRESHOLD = 1000

    def __init__(self):
        """初始化调度器"""
        self.logger = logging.getLogger(__name__)
        self.logger.info("✅ 自适应调度器已初始化")

    def decide_execution_strategy(self, task_batch: List[TaskUnit]) -> ExecutionStrategy:
        """决定执行策略

        Args:
            task_batch: 任务批次

        Returns:
            ExecutionStrategy: 执行策略
        """
        task_count = len(task_batch)

        if task_count < self.SMALL_TASK_THRESHOLD:
            # 小任务：保证UI响应
            strategy = ExecutionStrategy(
                mode="direct",  # 直接执行，不排队
                max_workers=2,  # 限制并发
                priority=TaskPriority.URGENT,
                resource_limits="strict",  # 严格限制
            )
            self.logger.info("📋 小任务调度 (%d个单元): %s", task_count, strategy)

        elif task_count < self.MEDIUM_TASK_THRESHOLD:
            # 中等任务：平衡模式
            strategy = ExecutionStrategy(
                mode="queued", max_workers=4, priority=TaskPriority.HIGH, resource_limits="moderate"
            )
            self.logger.info("📋 中等任务调度 (%d个单元): %s", task_count, strategy)

        else:
            # 大任务：效率优先
            strategy = ExecutionStrategy(
                mode="queued",
                max_workers=8,
                priority=TaskPriority.NORMAL,
                resource_limits="relaxed",  # 宽松限制
            )
            self.logger.info("📋 大任务调度 (%d个单元): %s", task_count, strategy)

        return strategy

    def get_resource_limit_multiplier(self, resource_limits: str) -> dict:
        """获取资源限制乘数

        Args:
            resource_limits: 资源限制级别

        Returns:
            dict: 限制乘数 {'cpu': x, 'memory': y}
        """
        if resource_limits == "strict":
            # 严格限制：基准值的60%
            return {"cpu": 0.6, "memory": 0.6}
        elif resource_limits == "moderate":
            # 适中限制：基准值的100%
            return {"cpu": 1.0, "memory": 1.0}
        elif resource_limits == "relaxed":
            # 宽松限制：基准值的150%
            return {"cpu": 1.5, "memory": 1.5}
        else:
            # 默认：适中
            return {"cpu": 1.0, "memory": 1.0}

    def should_use_queue(self, task_count: int) -> bool:
        """判断是否应该使用队列

        Args:
            task_count: 任务数量

        Returns:
            bool: 是否使用队列
        """
        return task_count >= self.SMALL_TASK_THRESHOLD

    def estimate_execution_time(self, task_count: int, avg_unit_time: float = 0.1) -> float:
        """估算任务执行时间

        Args:
            task_count: 任务数量
            avg_unit_time: 平均单元执行时间（秒）

        Returns:
            float: 预估执行时间（秒）
        """
        # 创建虚拟任务列表用于估算
        dummy_units = [
            TaskUnit(unit_id=f"dummy_{i}", data=None) for i in range(min(task_count, 10))
        ]
        strategy = self.decide_execution_strategy(dummy_units)

        # 根据Worker数量估算并行执行时间
        parallel_time = (task_count * avg_unit_time) / strategy.max_workers

        # 加上队列开销（队列模式）
        queue_overhead = 1.0 if strategy.mode == "queued" else 0.0

        return parallel_time + queue_overhead


class PriorityScheduler:
    """优先级调度器

    基于任务优先级进行调度决策。
    """

    def __init__(self):
        """初始化调度器"""
        self.logger = logging.getLogger(__name__)

    def assign_priority(
        self, task_count: int, is_user_triggered: bool = False, is_urgent: bool = False
    ) -> TaskPriority:
        """分配任务优先级

        Args:
            task_count: 任务数量
            is_user_triggered: 是否用户触发
            is_urgent: 是否紧急

        Returns:
            TaskPriority: 任务优先级
        """
        # 紧急任务（UI交互）
        if is_urgent or (is_user_triggered and task_count < 10):
            return TaskPriority.URGENT

        # 高优先级（用户请求）
        if is_user_triggered:
            return TaskPriority.HIGH

        # 普通优先级（后台任务）
        if task_count < 1000:
            return TaskPriority.NORMAL

        # 低优先级（大规模后台任务）
        return TaskPriority.LOW


class HybridScheduler:
    """混合调度器

    结合自适应调度和优先级调度。
    """

    def __init__(self):
        """初始化混合调度器"""
        self.adaptive_scheduler = AdaptiveScheduler()
        self.priority_scheduler = PriorityScheduler()
        self.logger = logging.getLogger(__name__)

        self.logger.info("✅ 混合调度器已初始化")

    def schedule(
        self, task_batch: List[TaskUnit], is_user_triggered: bool = False, is_urgent: bool = False
    ) -> tuple:
        """调度任务

        Args:
            task_batch: 任务批次
            is_user_triggered: 是否用户触发
            is_urgent: 是否紧急

        Returns:
            tuple: (ExecutionStrategy, TaskPriority)
        """
        task_count = len(task_batch)

        # 决定执行策略
        strategy = self.adaptive_scheduler.decide_execution_strategy(task_batch)

        # 分配优先级
        priority = self.priority_scheduler.assign_priority(task_count, is_user_triggered, is_urgent)

        # 如果紧急任务，覆盖策略
        if is_urgent:
            strategy.priority = TaskPriority.URGENT
            strategy.mode = "direct"  # 紧急任务直接执行
        else:
            strategy.priority = priority

        self.logger.info(
            "🎯 任务调度完成: %d个单元, 策略=%s, 优先级=%s",
            task_count,
            strategy.mode,
            priority.name,
        )

        return strategy, priority


# -------------------- 队列门面 --------------------


class LoadBalancerQueueFacade:
    """LoadBalancer队列化门面（简化使用）

    单例模式，提供统一的任务提交和管理接口。
    自动进行调度决策和资源限制。
    """

    _instance: Optional["LoadBalancerQueueFacade"] = None
    _lock = threading.Lock()  # Initialize lock immediately

    @classmethod
    def get_instance(cls) -> "LoadBalancerQueueFacade":
        """获取单例实例

        Returns:
            LoadBalancerQueueFacade: 单例实例
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        """初始化门面（私有构造函数）"""
        if self.__class__._instance is not None:
            raise RuntimeError("请使用 get_instance() 获取单例实例")

        self.logger = logging.getLogger(__name__)

        # 核心组件
        self.queue_manager: Optional[TaskQueueManager] = None
        self.resource_limiter = None  # 从resource_management初始化
        self.scheduler = HybridScheduler()

        # 运行状态
        self.is_running = False
        self.execution_callback: Optional[Callable] = None

        # 统计信息
        self._submitted_count = 0
        self._rejected_count = 0

        self.logger.info("✅ LoadBalancerQueueFacade 已初始化")

    def initialize(
        self,
        execution_callback: Callable,
        max_workers: int = 4,
        queue_maxsize: int = 10000,
        enable_windows_job: bool = False,
        small_task_cpu_limit: float = 30.0,
        large_task_cpu_limit: float = 80.0,
        small_task_memory_limit: float = 50.0,
        large_task_memory_limit: float = 70.0,
        task_size_threshold: int = 1000,
    ):
        """初始化门面组件

        Args:
            execution_callback: 执行回调函数
            max_workers: 最大Worker数量
            queue_maxsize: 队列最大容量
            enable_windows_job: 是否启用Windows Job Objects
            small_task_cpu_limit: 小任务CPU限制（%）
            large_task_cpu_limit: 大任务CPU限制（%）
            small_task_memory_limit: 小任务内存限制（%）
            large_task_memory_limit: 大任务内存限制（%）
            task_size_threshold: 任务规模阈值
        """
        if self.is_running:
            self.logger.warning("⚠️ LoadBalancerQueueFacade已在运行")
            return

        self.logger.info("🔧 初始化 LoadBalancerQueueFacade...")

        # 创建队列管理器
        self.queue_manager = TaskQueueManager(max_workers=max_workers, queue_maxsize=queue_maxsize)

        # 创建资源限制器（直接引用，同文件内）
        self.resource_limiter = HybridResourceLimiter(
            enable_windows_job=enable_windows_job,
            enable_app_level=True,
            small_task_cpu_limit=small_task_cpu_limit,
            large_task_cpu_limit=large_task_cpu_limit,
            small_task_memory_limit=small_task_memory_limit,
            large_task_memory_limit=large_task_memory_limit,
            task_size_threshold=task_size_threshold,
        )

        # 保存执行回调
        self.execution_callback = execution_callback

        self.logger.info("✅ LoadBalancerQueueFacade 初始化完成")

    def start(self):
        """启动门面服务"""
        if self.is_running:
            self.logger.warning("⚠️ LoadBalancerQueueFacade已在运行")
            return

        if self.queue_manager is None or self.execution_callback is None:
            raise RuntimeError("请先调用 initialize() 初始化门面")

        self.logger.info("🚀 启动 LoadBalancerQueueFacade...")

        # 启动队列管理器
        self.queue_manager.start(self.execution_callback)

        self.is_running = True
        self.logger.info("✅ LoadBalancerQueueFacade 已启动")

    def stop(self):
        """停止门面服务"""
        if not self.is_running:
            return

        self.logger.info("🛑 停止 LoadBalancerQueueFacade...")

        # 停止队列管理器
        if self.queue_manager:
            self.queue_manager.stop()

        # 清理资源限制器
        if self.resource_limiter:
            self.resource_limiter.cleanup()

        self.is_running = False
        self.logger.info("✅ LoadBalancerQueueFacade 已停止")

    def submit_task_batch(
        self,
        task_units: List[TaskUnit],
        priority: Optional[TaskPriority] = None,
        is_user_triggered: bool = False,
        is_urgent: bool = False,
        check_limits: bool = True,
    ) -> Optional[str]:
        """提交任务批次（自动判断执行策略）

        Args:
            task_units: 任务单元列表
            priority: 任务优先级（None=自动决策）
            is_user_triggered: 是否用户触发
            is_urgent: 是否紧急
            check_limits: 是否检查资源限制

        Returns:
            Optional[str]: 任务ID，如果被拒绝则返回None
        """
        if not self.is_running:
            self.logger.error("❌ LoadBalancerQueueFacade未启动")
            return None

        if not task_units:
            self.logger.warning("⚠️ 任务单元列表为空")
            return None

        task_count = len(task_units)

        # 1. 调度决策
        strategy, auto_priority = self.scheduler.schedule(task_units, is_user_triggered, is_urgent)

        # 使用指定优先级或自动决策的优先级
        final_priority = priority if priority is not None else auto_priority

        # 2. 资源限制检查（已移至LoadBalancer）
        # 注意：资源限制逻辑已集成到 LoadBalancer.get_optimal_config_with_adjustment()
        # 实际的资源上下限判断和并发调整会在任务执行时进行
        # check_limits 参数保留用于向后兼容，但不再执行实际检查
        if check_limits:
            self.logger.debug("资源限制检查已由LoadBalancer统一处理")

        # 3. 提交任务
        if self.queue_manager is None:
            self.logger.error("❌ 队列管理器未初始化")
            return None

        if strategy.mode == "direct":
            # 直接执行模式（小任务）
            self.logger.info("🚀 直接执行模式: %d个单元", task_count)
            # 注意：直接模式需要在调用方直接调用execution_callback
            # 这里仍然通过队列提交，但使用最高优先级
            task_id = self.queue_manager.submit_task(task_units, TaskPriority.URGENT)
        else:
            # 队列执行模式
            task_id = self.queue_manager.submit_task(task_units, final_priority)

        self._submitted_count += 1

        self.logger.info(
            "📥 任务已提交: %s, 模式=%s, 优先级=%s, 单元数=%d",
            task_id,
            strategy.mode,
            final_priority.name,
            task_count,
        )

        return task_id

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            Optional[TaskStatus]: 任务状态，不存在返回None
        """
        if self.queue_manager is None:
            return None

        metadata = self.queue_manager.task_queue.get_metadata(task_id)
        return metadata.status if metadata else None

    def cancel_task(self, task_id: str) -> bool:
        """取消任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功取消
        """
        if self.queue_manager is None:
            return False

        return self.queue_manager.task_queue.cancel(task_id)

    def get_queue_metrics(self) -> Dict:
        """获取队列统计指标

        Returns:
            Dict: 统计指标
        """
        if self.queue_manager is None:
            return {}

        metrics = self.queue_manager.get_metrics()
        metrics["submitted_count"] = self._submitted_count
        metrics["rejected_count"] = self._rejected_count

        return metrics

    def get_current_queue_length(self) -> int:
        """获取当前队列长度

        Returns:
            int: 队列长度
        """
        if self.queue_manager is None:
            return 0
        return self.queue_manager.task_queue.qsize()


def get_queue_facade() -> LoadBalancerQueueFacade:
    """获取队列门面单例

    Returns:
        LoadBalancerQueueFacade: 单例实例
    """
    return LoadBalancerQueueFacade.get_instance()


# ==============================================================================
# 第6部分：资源管理（资源限制配置、Job Objects、应用层限制器、Qt监控）
# ==============================================================================


# -------------------- 资源限制配置 --------------------


@dataclass
class ResourceLimitConfig:
    """资源限制配置"""

    cpu_percent: float  # CPU限制（百分比）
    memory_percent: float  # 内存限制（百分比）


# -------------------- Windows Job Objects 限制器 --------------------


class WindowsJobObjectLimiter:
    """Windows Job Objects资源限制器（仅Windows可用）

    使用Windows Job Objects API实现硬性资源限制。
    需要安装 pywin32 包。
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.is_available = False
        self.hjob = None

        # 检查是否为Windows平台
        if platform.system() != "Windows":
            self.logger.warning("⚠️ Windows Job Objects仅支持Windows平台")
            return

        # 尝试导入pywin32
        try:
            import win32job  # type: ignore
            import win32api  # type: ignore
            import win32con  # type: ignore

            self.win32job = win32job
            self.win32api = win32api
            self.win32con = win32con
            self.is_available = True
            self.logger.info("✅ Windows Job Objects可用")
        except ImportError:
            self.logger.warning(
                "⚠️ Windows Job Objects不可用: 缺少pywin32包\n安装方法: pip install pywin32"
            )

    def create_job(
        self, cpu_rate: int = 80, memory_limit_mb: int = 4096, job_name: str = "LoadBalancerJob"
    ) -> bool:
        """创建Windows Job Object并设置限制

        Args:
            cpu_rate: CPU限制百分比（1-100）
            memory_limit_mb: 内存限制（MB）
            job_name: Job对象名称

        Returns:
            bool: 是否成功创建
        """
        if not self.is_available:
            return False

        try:
            # 创建Job对象
            self.hjob = self.win32job.CreateJobObject(None, job_name)

            # 设置CPU限制（需要Windows 8+）
            try:
                cpu_info = self.win32job.JOBOBJECT_CPU_RATE_CONTROL_INFORMATION()  # type: ignore
                cpu_info.ControlFlags = (  # type: ignore
                    self.win32job.JOB_OBJECT_CPU_RATE_CONTROL_ENABLE  # type: ignore
                    | self.win32job.JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP  # type: ignore
                )
                cpu_info.CpuRate = cpu_rate * 100  # type: ignore  # 转换为basis points
                self.win32job.SetInformationJobObject(  # type: ignore
                    self.hjob, self.win32job.JobObjectCpuRateControlInformation, cpu_info  # type: ignore
                )
                self.logger.info("✅ CPU限制已设置: %d%%", cpu_rate)
            except Exception as e:
                self.logger.warning("⚠️ CPU限制设置失败（需要Windows 8+）: %s", str(e))

            # 设置内存限制
            limits = self.win32job.JOBOBJECT_EXTENDED_LIMIT_INFORMATION()  # type: ignore
            limits.ProcessMemoryLimit = memory_limit_mb * 1024 * 1024  # type: ignore
            limits.BasicLimitInformation.LimitFlags = self.win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY  # type: ignore
            self.win32job.SetInformationJobObject(  # type: ignore
                self.hjob, self.win32job.JobObjectExtendedLimitInformation, limits  # type: ignore
            )
            self.logger.info("✅ 内存限制已设置: %dMB", memory_limit_mb)

            return True

        except Exception as e:
            self.logger.error("❌ 创建Job Object失败: %s", str(e), exc_info=True)
            return False

    def assign_process(self, pid: int) -> bool:
        """将进程分配到Job

        Args:
            pid: 进程ID

        Returns:
            bool: 是否成功分配
        """
        if not self.is_available or self.hjob is None:
            return False

        try:
            hprocess = self.win32api.OpenProcess(
                self.win32con.PROCESS_SET_QUOTA | self.win32con.PROCESS_TERMINATE, False, pid
            )
            self.win32job.AssignProcessToJobObject(self.hjob, hprocess)
            self.logger.info("✅ 进程%d已分配到Job", pid)
            return True
        except Exception as e:
            self.logger.error("❌ 分配进程到Job失败: %s", str(e), exc_info=True)
            return False

    def close(self):
        """关闭Job Object"""
        if self.hjob is not None:
            try:
                self.win32api.CloseHandle(self.hjob)
                self.logger.info("✅ Job Object已关闭")
            except Exception as e:
                self.logger.error("❌ 关闭Job Object失败: %s", str(e))
            finally:
                self.hjob = None


# -------------------- 应用层资源限制器 --------------------


class ApplicationLevelLimiter:
    """应用层资源监控和限制（软限制）

    基于实时资源监控，当资源使用超过限制时阻止任务执行。
    支持根据任务规模使用不同的限制策略。
    """

    def __init__(
        self,
        small_task_cpu_limit: float = 80.0,
        large_task_cpu_limit: float = 80.0,
        small_task_memory_limit: float = 70.0,
        large_task_memory_limit: float = 70.0,
        task_size_threshold: int = 1000,
        # 磁盘I/O限制参数（v2.5.0：使用队列深度）
        disk_hdd_queue_limit: int = 16,
        disk_ssd_queue_limit: int = 32,
        disk_nvme_queue_limit: int = 64,
        disk_hdd_latency_critical: float = 100.0,
        disk_ssd_latency_critical: float = 50.0,
        disk_nvme_latency_critical: float = 10.0,
    ):
        """初始化应用层限制器

        Args:
            small_task_cpu_limit: 小任务CPU限制（%）
            large_task_cpu_limit: 大任务CPU限制（%）
            small_task_memory_limit: 小任务内存限制（%）
            large_task_memory_limit: 大任务内存限制（%）
            task_size_threshold: 任务规模阈值（小任务vs大任务）
            disk_hdd_queue_limit: HDD磁盘队列深度限制
            disk_ssd_queue_limit: SSD磁盘队列深度限制
            disk_nvme_queue_limit: NVMe磁盘队列深度限制
            disk_hdd_latency_critical: HDD延迟熔断阈值（ms）
            disk_ssd_latency_critical: SSD延迟熔断阈值（ms）
            disk_nvme_latency_critical: NVMe延迟熔断阈值（ms）
        """
        self.small_task_limits = ResourceLimitConfig(
            cpu_percent=small_task_cpu_limit, memory_percent=small_task_memory_limit
        )
        self.large_task_limits = ResourceLimitConfig(
            cpu_percent=large_task_cpu_limit, memory_percent=large_task_memory_limit
        )
        self.task_size_threshold = task_size_threshold

        # 磁盘限制配置（按磁盘类型，v2.5.0：使用队列深度）
        self.disk_limits = {
            "hdd": {
                "queue_limit": disk_hdd_queue_limit,
                "latency_critical": disk_hdd_latency_critical,
            },
            "ssd": {
                "queue_limit": disk_ssd_queue_limit,
                "latency_critical": disk_ssd_latency_critical,
            },
            "nvme": {
                "queue_limit": disk_nvme_queue_limit,
                "latency_critical": disk_nvme_latency_critical,
            },
        }

        self.logger = logging.getLogger(__name__)

        self.logger.info(
            "✅ 应用层限制器已初始化:\n"
            "  小任务(<%d): CPU<%.1f%%, MEM<%.1f%%\n"
            "  大任务(>=%d): CPU<%.1f%%, MEM<%.1f%%\n"
            "  磁盘限制(队列深度): HDD<%d(%.1fms), SSD<%d(%.1fms), NVMe<%d(%.1fms)",
            task_size_threshold,
            small_task_cpu_limit,
            small_task_memory_limit,
            task_size_threshold,
            large_task_cpu_limit,
            large_task_memory_limit,
            disk_hdd_queue_limit,
            disk_hdd_latency_critical,
            disk_ssd_queue_limit,
            disk_ssd_latency_critical,
            disk_nvme_queue_limit,
            disk_nvme_latency_critical,
        )

    def check_disk_limits(self, current_metrics: Dict[str, Any]) -> tuple:
        """检查磁盘限制（基于队列深度，v2.5.0）

        Args:
            current_metrics: 当前监控指标，包含 storage_subsystem

        Returns:
            tuple: (is_allowed: bool, reason: str)
        """
        try:
            # 获取存储子系统指标
            storage = current_metrics.get("storage_subsystem", {})
            disks = storage.get("disks", {})

            if not disks:
                # 没有磁盘数据，允许执行
                return True, "无磁盘监控数据"

            # 检查所有物理磁盘
            for disk_name, disk_info in disks.items():
                disk_type = disk_info.get("disk_type", "ssd")
                queue_depth = disk_info.get("queue_depth")
                io_latency = disk_info.get("average_io_latency_ms", 0)

                # 获取该磁盘类型的限制
                limits = self.disk_limits.get(disk_type, self.disk_limits["ssd"])

                # 优先检查队列深度限制
                if queue_depth is not None and queue_depth > limits["queue_limit"]:
                    reason = (
                        f"磁盘{disk_name}({disk_type.upper()})队列深度超限: "
                        f"{queue_depth:.1f} > {limits['queue_limit']}"
                    )
                    self.logger.warning("⚠️ %s", reason)
                    return False, reason

                # 检查IO延迟熔断（紧急保护）
                if io_latency and io_latency > limits["latency_critical"]:
                    reason = (
                        f"磁盘{disk_name}({disk_type.upper()})IO延迟触发紧急熔断: "
                        f"{io_latency:.1f}ms > {limits['latency_critical']:.1f}ms"
                    )
                    self.logger.warning("⚠️ %s", reason)
                    return False, reason

            return True, "磁盘资源正常"

        except Exception as e:
            self.logger.debug("检查磁盘限制失败: %s", e)
            # 异常时允许执行，避免阻塞业务
            return True, "磁盘检查异常，跳过"

    def check_limits(self, task_size: int, current_metrics: Dict[str, float]) -> tuple:
        """检查是否超限（根据任务规模使用不同限制）

        Args:
            task_size: 任务大小（单元数）
            current_metrics: 当前资源指标 {'cpu_percent': x, 'memory_percent': y, 'storage_subsystem': {...}}

        Returns:
            tuple: (is_allowed: bool, reason: str)
        """
        # 根据任务规模选择限制
        limits = (
            self.small_task_limits
            if task_size < self.task_size_threshold
            else self.large_task_limits
        )

        task_type = "小任务" if task_size < self.task_size_threshold else "大任务"

        # 检查CPU限制
        cpu_usage = current_metrics.get("cpu_percent", 0)
        if cpu_usage > limits.cpu_percent:
            reason = f"{task_type}CPU超限: {cpu_usage:.1f}% > {limits.cpu_percent:.1f}%"
            self.logger.warning("⚠️ %s", reason)
            return False, reason

        # 检查内存限制
        memory_usage = current_metrics.get("memory_percent", 0)
        if memory_usage > limits.memory_percent:
            reason = f"{task_type}内存超限: {memory_usage:.1f}% > {limits.memory_percent:.1f}%"
            self.logger.warning("⚠️ %s", reason)
            return False, reason

        # 新增：检查磁盘限制
        disk_allowed, disk_reason = self.check_disk_limits(current_metrics)
        if not disk_allowed:
            return False, disk_reason

        return True, "资源在限制内"

    def get_limits(self, task_size: int) -> ResourceLimitConfig:
        """获取任务的资源限制配置

        Args:
            task_size: 任务大小

        Returns:
            ResourceLimitConfig: 资源限制配置
        """
        return (
            self.small_task_limits
            if task_size < self.task_size_threshold
            else self.large_task_limits
        )


# -------------------- PySide6 资源监控器 --------------------


class QResourceMonitor(QObject):
    """PySide6友好的资源监控器

    使用QTimer定期检查资源使用情况，通过Signal通知UI。
    不阻塞主线程，确保UI响应性。
    """

    # 信号定义
    resource_updated = Signal(dict)  # 资源更新 {'cpu': x, 'memory': y, ...}
    limit_exceeded = Signal(str)  # 超限警告

    def __init__(self, check_interval_ms: int = 500):
        """初始化资源监控器

        Args:
            check_interval_ms: 检查间隔（毫秒）
        """
        super().__init__()
        self.check_interval_ms = check_interval_ms
        self.logger = logging.getLogger(__name__)

        # 创建定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check_resources)

        # 限制器（可选）
        self.limiter: Optional[ApplicationLevelLimiter] = None

        # 当前任务大小（用于限制检查）
        self.current_task_size = 0

    def start(self):
        """启动监控"""
        self.timer.start(self.check_interval_ms)
        self.logger.info("🚀 资源监控已启动 (间隔%dms)", self.check_interval_ms)

    def stop(self):
        """停止监控"""
        self.timer.stop()
        self.logger.info("✅ 资源监控已停止")

    def set_limiter(self, limiter: ApplicationLevelLimiter):
        """设置限制器

        Args:
            limiter: 应用层限制器
        """
        self.limiter = limiter

    def set_current_task_size(self, task_size: int):
        """设置当前任务大小（用于限制检查）

        Args:
            task_size: 任务大小
        """
        self.current_task_size = task_size

    def _check_resources(self):
        """检查资源使用情况（定时器回调）"""
        try:
            if not HAS_PSUTIL:
                return

            # 获取资源使用率
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_percent = psutil.virtual_memory().percent

            metrics = {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "timestamp": time.time(),
            }

            # 发送更新信号
            self.resource_updated.emit(metrics)

            # 检查限制（如果设置了限制器）
            if self.limiter and self.current_task_size > 0:
                is_allowed, reason = self.limiter.check_limits(self.current_task_size, metrics)
                if not is_allowed:
                    self.limit_exceeded.emit(reason)

        except Exception as e:
            self.logger.error("❌ 资源检查失败: %s", str(e), exc_info=True)


# -------------------- 混合资源限制器 --------------------


class HybridResourceLimiter:
    """混合资源限制器

    集成多种限制策略，提供统一的接口。
    优先使用硬限制（Windows Job Objects），回退到软限制（应用层监控）。
    """

    def __init__(
        self, enable_windows_job: bool = True, enable_app_level: bool = True, **app_level_kwargs
    ):
        """初始化混合限制器

        Args:
            enable_windows_job: 是否启用Windows Job Objects
            enable_app_level: 是否启用应用层限制
            **app_level_kwargs: 应用层限制器参数
        """
        self.logger = logging.getLogger(__name__)

        # Windows Job Objects限制器
        self.windows_limiter: Optional[WindowsJobObjectLimiter] = None
        if enable_windows_job:
            self.windows_limiter = WindowsJobObjectLimiter()

        # 应用层限制器
        self.app_limiter: Optional[ApplicationLevelLimiter] = None
        if enable_app_level:
            self.app_limiter = ApplicationLevelLimiter(**app_level_kwargs)

        self.logger.info(
            "✅ 混合资源限制器已初始化:\n  Windows Job Objects: %s\n  应用层限制: %s",
            "启用" if enable_windows_job else "禁用",
            "启用" if enable_app_level else "禁用",
        )

    def setup_job_limits(self, cpu_rate: int = 80, memory_limit_mb: int = 4096) -> bool:
        """设置Windows Job限制

        Args:
            cpu_rate: CPU限制百分比
            memory_limit_mb: 内存限制（MB）

        Returns:
            bool: 是否成功设置
        """
        if self.windows_limiter:
            return self.windows_limiter.create_job(cpu_rate, memory_limit_mb)
        return False

    def check_limits(self, task_size: int, current_metrics: Dict[str, float]) -> tuple:
        """检查资源限制

        Args:
            task_size: 任务大小
            current_metrics: 当前资源指标

        Returns:
            tuple: (is_allowed: bool, reason: str)
        """
        # 应用层限制检查
        if self.app_limiter:
            return self.app_limiter.check_limits(task_size, current_metrics)

        # 如果没有限制器，默认允许
        return True, "无限制"

    def cleanup(self):
        """清理资源"""
        if self.windows_limiter:
            self.windows_limiter.close()
        self.logger.info("✅ 资源限制器已清理")


# ==============================================================================
# 第7部分：服务器池管理（ServerPoolManager、便捷函数）
# ==============================================================================


# -------------------- 服务器池管理器 --------------------


def _is_ipv6(ip: str) -> bool:
    """
    判断IP地址是否为IPv6

    Args:
        ip: IP地址字符串

    Returns:
        bool: True=IPv6, False=IPv4
    """
    return ":" in ip or ip.startswith("[")


def _get_all_servers() -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]:
    """
    获取所有服务器列表（合并HQ_HOSTS_ALL和BROKER_SERVERS_7709），并分为IPv4和IPv6两个池

    Returns:
        Tuple[ipv4_servers, ipv6_servers]: IPv4和IPv6服务器列表
    """
    from backend.infrastructure.tdx_asyncio.constants import (
        HQ_HOSTS_ALL,
        BROKER_SERVERS_7709,
    )

    # 使用集合来去重（基于ip:port）
    server_set = set()
    ipv4_servers = []
    ipv6_servers = []

    # 合并所有服务器列表
    all_server_lists = [
        HQ_HOSTS_ALL,
        BROKER_SERVERS_7709,
    ]

    for server_list in all_server_lists:
        if not server_list:
            continue
        for item in server_list:
            if not item or len(item) < 2:
                continue
            # 处理(name, ip, port)格式
            if len(item) == 3:
                _, ip, port = item
            # 处理(ip, port)格式
            elif len(item) == 2:
                ip, port = item[0], item[1]  # 显式索引避免类型推断问题
            else:
                continue

            # 去重：使用ip:port作为唯一标识
            key = f"{ip}:{port}"
            if key not in server_set:
                server_set.add(key)
                # 根据IP类型分类
                if _is_ipv6(ip):
                    ipv6_servers.append((ip, port))
                else:
                    ipv4_servers.append((ip, port))

    return ipv4_servers, ipv6_servers


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

        # ✅ 日志统一由 LoggingHub 处理，不再手动添加handler
        # 这样避免了日志重复输出的问题

        # 运行状态
        self._running = False
        self._starting = False  # 🔧 新增：防止多次并发启动
        self._start_lock = threading.Lock()  # 🔧 新增：启动锁
        self._start_time: Optional[datetime] = None
        self._cache_date: Optional[str] = None  # 缓存日期

        # 多进程相关
        self._processes: List[Any] = []  # 支持不同上下文的Process类型（spawn/fork等）
        self._sorted_servers_ipv4: List[Tuple[str, int]] = []  # 存储排序后的IPv4服务器结果
        self._sorted_servers_ipv6: List[Tuple[str, int]] = []  # 存储排序后的IPv6服务器结果
        # 向后兼容：合并两个池
        self._sorted_servers: List[Tuple[str, int]] = []  # 存储合并后的服务器结果

        # 配置参数（这些配置来自config_manager，这里使用默认值）
        self.test_timeout = 2.0
        self.max_fail_time = 2.0
        # 动态获取所有服务器的实际数量（合并HQ_HOSTS_ALL和BROKER_SERVERS_7709）
        ipv4_servers, ipv6_servers = _get_all_servers()
        self.server_count = len(ipv4_servers) + len(ipv6_servers)
        self.max_coroutines_per_process: Optional[int] = None  # None 表示单进程可覆盖全部服务器

        # 缓存文件配置
        self._cache_file = "server_pool_cache.json"

        chunk_size = self.max_coroutines_per_process or self.server_count or 1
        num_processes = math.ceil(self.server_count / chunk_size)
        self.logger.debug("服务器池管理器初始化完成（多进程模式）")
        self.logger.debug(f"配置: {self.server_count}个服务器 → {num_processes}个进程")

    def start(self) -> bool:
        """启动服务器池管理器（验证缓存 + 按需测速）

        流程：
        1. 加载缓存文件
        2. 验证缓存日期（次日0时失效）
        3. 如果有效：跳过测速，直接使用（<100ms）
        4. 如果失效/不存在：重新测速并更新缓存（~7秒）

        Returns:
            bool: 是否启动成功（缓存可用或测速完成）
        """
        # 🔧 修复：使用锁防止多次并发启动
        with self._start_lock:
            if self._running:
                self.logger.debug("服务器池管理器已在运行，跳过启动")
                return True

            if self._starting:
                self.logger.debug("服务器池管理器正在启动中，等待完成...")
                # 等待其他线程完成启动
                import time

                max_wait = 30  # 最多等待30秒
                waited = 0
                while self._starting and waited < max_wait:
                    time.sleep(0.1)
                    waited += 0.1
                return self._running

            # 标记为正在启动
            self._starting = True

        try:
            # 1. 尝试加载缓存
            cache_data_ipv4, cache_data_ipv6, cache_date, is_valid = self.load_server_cache()

            # 2. 强制检查缓存是否为当天（使用网络时间）
            from backend.infrastructure.data_module_vnpy.utils.network_time import get_real_date

            today = get_real_date().isoformat()  # 使用网络时间

            # 如果缓存日期不是今天，强制失效
            if cache_date and cache_date != today:
                is_valid = False
                self.logger.warning(
                    "服务器池缓存非当天（%s != %s），强制重新测速", cache_date, today
                )

            if cache_data_ipv4 is not None and cache_data_ipv6 is not None and is_valid:
                # ✅ 缓存有效且是当天，跳过测速
                self._sorted_servers_ipv4 = cache_data_ipv4
                self._sorted_servers_ipv6 = cache_data_ipv6
                self._sorted_servers = cache_data_ipv4 + cache_data_ipv6  # 向后兼容
                self._cache_date = cache_date
                self._running = True
                self._start_time = datetime.now()

                # ✅ 同步更新server_count为实际的所有服务器数量（合并HQ_HOSTS_ALL和BROKER_SERVERS_7709）
                ipv4_servers, ipv6_servers = _get_all_servers()
                self.server_count = len(ipv4_servers) + len(ipv6_servers)

                self.logger.info("✅ 服务器池缓存有效（%s），跳过测速", cache_date)
                self.logger.info("   IPv4服务器：%d个", len(self._sorted_servers_ipv4))
                self.logger.info("   IPv6服务器：%d个", len(self._sorted_servers_ipv6))
                self.logger.info("   总服务器：%d个", len(self._sorted_servers))

                # 推送服务器状态事件
                self._push_server_status_event()

                return True

            elif (cache_data_ipv4 is not None or cache_data_ipv6 is not None) and not is_valid:
                # ⚠️ 缓存失效，需要重新测速
                self.logger.warning("⚠️ 服务器池缓存已过期（%s），正在重新测速...", cache_date)
            else:
                # ⚠️ 缓存不存在
                self.logger.warning("⚠️ 服务器池缓存不存在，正在首次测速...")

            # 2. 执行测速
            success = self._start_multiprocess()

            if success:
                # 3. 保存缓存
                self.save_server_cache(self._sorted_servers_ipv4, self._sorted_servers_ipv6)
                self.logger.info(
                    "✅ 服务器池测速完成，缓存已更新", extra={"log_type": "stage_node"}
                )
                self.logger.info(
                    "   IPv4服务器：%d个",
                    len(self._sorted_servers_ipv4),
                    extra={"log_type": "stage_node"},
                )
                self.logger.info(
                    "   IPv6服务器：%d个",
                    len(self._sorted_servers_ipv6),
                    extra={"log_type": "stage_node"},
                )

            return success

        except Exception as e:
            self.logger.error("启动服务器池管理器失败：%s", e, exc_info=True)
            self._running = False
            return False
        finally:
            # 🔧 确保清除启动标志
            self._starting = False

    def _test_server_pool(
        self, servers: List[Tuple[str, int]], pool_name: str
    ) -> Dict[Tuple[str, int], float]:
        """测速单个服务器池（IPv4或IPv6）

        Args:
            servers: 要测试的服务器列表
            pool_name: 池名称（用于日志）

        Returns:
            Dict[server_tuple, score]: 测速结果字典
        """
        # 按配置分配服务器到不同进程
        chunk_size = self.max_coroutines_per_process or len(servers) or 1

        server_chunks = []
        for i in range(0, len(servers), chunk_size):
            chunk = servers[i : i + chunk_size]
            server_chunks.append(chunk)

        num_processes = len(server_chunks)

        self.logger.info(
            "测速%s池: %d个服务器分配到%d个进程",
            pool_name,
            len(servers),
            num_processes,
            extra={"log_type": "stage_node"},
        )

        # 创建共享内存存储结果
        ctx = get_context("spawn")
        manager = ctx.Manager()
        shared_results = manager.dict()
        self.logger.info("[%s] 共享内存管理器已创建", pool_name, extra={"log_type": "stage_node"})

        # 启动测速进程
        processes = []
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
                name=f"{pool_name}Test-{i+1}",
            )
            self.logger.info(
                "[%s] 启动子进程%d，负责%d个服务器",
                pool_name,
                i + 1,
                len(chunk),
                extra={"log_type": "stage_node"},
            )
            p.start()
            processes.append(p)

        # 等待所有进程完成（设置超时避免卡死）
        timeout_per_process = 180  # 每个进程最多等待3分钟
        for i, p in enumerate(processes):
            self.logger.info("[%s] 等待子进程%d完成...", pool_name, i + 1)
            p.join(timeout=timeout_per_process)
            if p.is_alive():
                self.logger.error(
                    "[%s] 子进程%d超时（>%ds），强制终止",
                    pool_name,
                    i + 1,
                    timeout_per_process,
                    extra={"log_type": "stage_node"},
                )
                p.terminate()
                p.join(timeout=5)
            else:
                self.logger.info("[%s] 子进程%d已完成", pool_name, i + 1)

        # 返回结果
        result_dict = dict(shared_results)
        self.logger.info(
            "[%s] 测速完成，收集到%d个结果",
            pool_name,
            len(result_dict),
            extra={"log_type": "stage_node"},
        )
        return result_dict

    def _start_multiprocess(self) -> bool:
        """多进程模式启动

        将服务器列表分配到多个进程，每个进程最多处理50个服务器。
        分别测速IPv4和IPv6服务器。

        Returns:
            bool: 是否启动成功
        """
        import time

        start_time = time.time()

        # 获取服务器列表（合并HQ_HOSTS_ALL和BROKER_SERVERS_7709），分为IPv4和IPv6
        ipv4_servers, ipv6_servers = _get_all_servers()

        # ✅ 记录原始和去重后的服务器数量
        from backend.infrastructure.tdx_asyncio.constants import HQ_HOSTS_ALL, BROKER_SERVERS_7709

        original_count = len(HQ_HOSTS_ALL) + len(BROKER_SERVERS_7709)
        self.server_count = len(ipv4_servers) + len(ipv6_servers)  # 去重后的数量
        self._original_server_count = original_count  # 保存原始数量用于日志

        self.logger.info(
            "准备测试 %d 个IPv4服务器 + %d 个IPv6服务器（去重后共%d个，原始%d个）",
            len(ipv4_servers),
            len(ipv6_servers),
            self.server_count,
            original_count,
        )

        # 分别测速IPv4和IPv6
        all_results = {}

        # 测速IPv4
        if ipv4_servers:
            self.logger.info("开始测速IPv4服务器池...", extra={"log_type": "stage_node"})
            ipv4_results = self._test_server_pool(ipv4_servers, "IPv4")
            self.logger.info(
                "IPv4测速返回%d个结果", len(ipv4_results), extra={"log_type": "stage_node"}
            )
            all_results.update(ipv4_results)

        # 测速IPv6
        if ipv6_servers:
            self.logger.info("开始测速IPv6服务器池...", extra={"log_type": "stage_node"})
            ipv6_results = self._test_server_pool(ipv6_servers, "IPv6")
            self.logger.info(
                "IPv6测速返回%d个结果", len(ipv6_results), extra={"log_type": "stage_node"}
            )
            all_results.update(ipv6_results)

        if not all_results:
            self.logger.error("❌ 所有进程测速失败，没有可用服务器")
            self._running = False
            return False

        # 分离IPv4和IPv6结果
        ipv4_available = []
        ipv6_available = []

        for server_tuple, score in all_results.items():
            ip, port = server_tuple
            if _is_ipv6(ip):
                ipv6_available.append((server_tuple, score))
            else:
                ipv4_available.append((server_tuple, score))

        # 按响应时间排序（从小到大）
        ipv4_available.sort(key=lambda x: x[1])
        ipv6_available.sort(key=lambda x: x[1])

        self._sorted_servers_ipv4 = [server for server, _ in ipv4_available]
        self._sorted_servers_ipv6 = [server for server, _ in ipv6_available]
        self._sorted_servers = self._sorted_servers_ipv4 + self._sorted_servers_ipv6  # 向后兼容

        elapsed = time.time() - start_time

        self._running = True
        self._start_time = datetime.now()

        # 输出统计信息（添加stage_node标记确保terminal输出）
        self.logger.info("=" * 60, extra={"log_type": "stage_node"})
        self.logger.info("✅ 多进程测速完成！", extra={"log_type": "stage_node"})
        self.logger.info("   总耗时: %.0fms", elapsed * 1000, extra={"log_type": "stage_node"})
        self.logger.info(
            "   测试服务器: %d个（去重后）", self.server_count, extra={"log_type": "stage_node"}
        )
        self.logger.info("   成功连接: %d个", len(all_results), extra={"log_type": "stage_node"})
        self.logger.info(
            "   失败: %d个", self.server_count - len(all_results), extra={"log_type": "stage_node"}
        )
        self.logger.info(
            "   IPv4: 测试%d个, 成功%d个 (%.1f%%)",
            len(ipv4_servers),
            len(self._sorted_servers_ipv4),
            len(self._sorted_servers_ipv4) / len(ipv4_servers) * 100 if ipv4_servers else 0,
            extra={"log_type": "stage_node"},
        )
        self.logger.info(
            "   IPv6: 测试%d个, 成功%d个 (%.1f%%)",
            len(ipv6_servers),
            len(self._sorted_servers_ipv6),
            len(self._sorted_servers_ipv6) / len(ipv6_servers) * 100 if ipv6_servers else 0,
            extra={"log_type": "stage_node"},
        )
        if self._sorted_servers_ipv4:
            self.logger.info(
                "   IPv4最快: %s:%d",
                self._sorted_servers_ipv4[0][0],
                self._sorted_servers_ipv4[0][1],
            )
        if self._sorted_servers_ipv6:
            self.logger.info(
                "   IPv6最快: %s:%d",
                self._sorted_servers_ipv6[0][0],
                self._sorted_servers_ipv6[0][1],
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
        """在子进程中运行服务器测速（静态方法）

        Args:
            process_id: 进程ID
            servers: 要测试的服务器列表
            shared_results: 共享内存字典，存储测速结果
            test_timeout: 单个服务器测试超时
            max_fail_time: 最大失败时间
        """
        import logging
        from backend.infrastructure.tdx_asyncio import AsyncSmartIPPool

        # 子进程需要独立初始化LogHub（子进程无法访问父进程的LogHub实例）
        # 但我们可以使用基本的logger，日志会通过共享的AI日志文件输出
        logger = logging.getLogger(f"load_balancer.subprocess.{process_id}")
        logger.setLevel(logging.DEBUG)

        # 如果logger还没有handler，添加一个StreamHandler用于AI日志捕获
        if not logger.handlers:
            import sys

            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                "[子进程%(process)d-%(name)s] %(levelname)s - %(message)s",
                defaults={"process": process_id},
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

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

                # 保存结果到共享内存（只保存成功的服务器）
                success_count = 0
                failed_count = 0
                for server, score in scores.items():
                    if score <= max_fail_time:
                        # 只将成功的服务器加入共享结果
                        shared_results[server] = score
                        success_count += 1
                    else:
                        failed_count += 1

                logger.info(
                    "[进程%d] 测速完成: 测试 %d 个, 可用 %d 个, 失败 %d 个",
                    process_id + 1,
                    len(servers),
                    success_count,
                    failed_count,
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
        """停止服务器池管理器

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

    def get_servers(
        self, count: Optional[int] = None, pool_type: str = "ipv4"
    ) -> List[Tuple[str, int]]:
        """获取排序后的服务器列表（保持原顺序）

        Args:
            count: 返回的服务器数量，None表示返回所有
            pool_type: 池类型，"ipv4"或"ipv6"，默认"ipv4"

        Returns:
            按速度排序的服务器列表 [(ip, port), ...]

        Raises:
            RuntimeError: 服务器池未运行或获取失败
        """
        # 自动初始化：如果未运行，尝试启动
        if not self._running:
            self.logger.info("服务器池未初始化，正在自动启动...")
            self.start()

        if not self._running:
            error_msg = "服务器池缓存不可用！\n请在系统管理中点击'测速服务器'按钮重新测速。"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 根据pool_type选择对应的池
        if pool_type == "ipv6":
            selected_servers = self._sorted_servers_ipv6
        else:
            selected_servers = self._sorted_servers_ipv4

        if not selected_servers:
            error_msg = (
                f"{pool_type.upper()}服务器列表为空！\n请在系统管理中点击'测速服务器'按钮进行测速。"
            )
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        return selected_servers[:count] if count else selected_servers

    def get_servers_shuffled(
        self, count: Optional[int] = None, pool_type: str = "ipv4"
    ) -> List[Tuple[str, int]]:
        """获取打乱顺序的服务器列表（推荐用于下载）

        每次调用都会重新打乱顺序，实现负载均衡。

        Args:
            count: 返回的服务器数量，None表示返回所有
            pool_type: 池类型，"ipv4"或"ipv6"，默认"ipv4"

        Returns:
            随机顺序的服务器列表 [(ip, port), ...]

        Raises:
            RuntimeError: 服务器池缓存不可用
        """
        if not self._running:
            error_msg = "服务器池缓存不可用！请先测速服务器。"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 根据pool_type选择对应的池
        if pool_type == "ipv6":
            selected_servers = self._sorted_servers_ipv6
        else:
            selected_servers = self._sorted_servers_ipv4

        if not selected_servers:
            error_msg = f"{pool_type.upper()}服务器列表为空！请先测速服务器。"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 打乱顺序（每次调用都重新打乱）
        servers = selected_servers.copy()
        random.shuffle(servers)

        return servers[:count] if count else servers

    def get_best_server(self, pool_type: str = "ipv4") -> Tuple[str, int]:
        """获取最快的服务器

        Args:
            pool_type: 池类型，"ipv4"或"ipv6"，默认"ipv4"

        Returns:
            最快的服务器 (ip, port)

        Raises:
            RuntimeError: 服务器池未运行或获取失败
        """
        if not self._running:
            error_msg = "服务器池未运行！请确保在应用启动时调用了 server_pool_manager.start()"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 根据pool_type选择对应的池
        if pool_type == "ipv6":
            selected_servers = self._sorted_servers_ipv6
        else:
            selected_servers = self._sorted_servers_ipv4

        if not selected_servers:
            error_msg = f"{pool_type.upper()}服务器列表为空，测速可能失败"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        return selected_servers[0]

    def get_stats(self) -> Dict:
        """获取服务器池统计信息

        Returns:
            统计字典，包含IPv4和IPv6的统计信息
        """
        stats = {
            "running": self._running,
            "uptime": 0,
            "total": self.server_count,
            "available": len(self._sorted_servers),
            "unavailable": self.server_count - len(self._sorted_servers),
            "mode": "multiprocess",
            "ipv4_available": len(self._sorted_servers_ipv4),
            "ipv6_available": len(self._sorted_servers_ipv6),
        }

        # 计算运行时长
        if self._start_time:
            stats["uptime"] = (datetime.now() - self._start_time).total_seconds()

        return stats

    def is_running(self) -> bool:
        """检查服务器池是否运行中并有可用服务器

        Returns:
            bool: 是否运行中且有可用服务器（IPv4或IPv6）
        """
        return self._running and (
            len(self._sorted_servers_ipv4) > 0 or len(self._sorted_servers_ipv6) > 0
        )

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
                "ipv4_available": len(self._sorted_servers_ipv4),
                "ipv6_available": len(self._sorted_servers_ipv6),
                "status": "available" if self._running else "stopped",
                "timestamp": datetime.now().isoformat(),
                "cache_date": self._cache_date,
            }

            event = Event("EVENT_SERVER_POOL_STATUS", event_data)
            event_engine.put(event)

            self.logger.info(
                "📢 推送服务器状态事件: IPv4=%d个, IPv6=%d个 (可用=%d/%d)",
                event_data["ipv4_available"],
                event_data["ipv6_available"],
                event_data["available"],
                event_data["total"],
                extra={"log_type": "stage_node"},
            )
        except Exception as e:
            self.logger.warning("推送服务器状态失败: %s", e)

    # ==================== 缓存管理 ====================

    def load_server_cache(
        self,
    ) -> Tuple[
        Optional[List[Tuple[str, int]]], Optional[List[Tuple[str, int]]], Optional[str], bool
    ]:
        """加载服务器池缓存（支持IPv4和IPv6双池）

        Returns:
            Tuple[ipv4_servers, ipv6_servers, cache_date, is_valid]
        """
        try:
            from backend.infrastructure.data_module_vnpy.cache_manager import DailyCacheManager

            data, cache_date, is_valid = DailyCacheManager.load_with_validation(
                self._cache_file, validate_date=True
            )

            if data:
                # 新格式：{"ipv4": [[ip, port], ...], "ipv6": [[ip, port], ...]}
                if isinstance(data, dict) and "ipv4" in data and "ipv6" in data:
                    ipv4_servers = [tuple(server) for server in data["ipv4"]]
                    ipv6_servers = [tuple(server) for server in data["ipv6"]]
                    return ipv4_servers, ipv6_servers, cache_date, is_valid
                # 旧格式（向后兼容）：[[ip, port], ...]
                elif isinstance(data, list):
                    servers = [tuple(server) for server in data]
                    # 分离IPv4和IPv6
                    ipv4_servers = [s for s in servers if not _is_ipv6(s[0])]
                    ipv6_servers = [s for s in servers if _is_ipv6(s[0])]
                    return ipv4_servers, ipv6_servers, cache_date, is_valid

            return None, None, None, False

        except Exception as e:
            self.logger.error("加载服务器池缓存失败: %s", e, exc_info=True)
            return None, None, None, False

    def save_server_cache(
        self, ipv4_servers: List[Tuple[str, int]], ipv6_servers: List[Tuple[str, int]]
    ) -> bool:
        """保存服务器池缓存（IPv4和IPv6双池）

        Args:
            ipv4_servers: IPv4服务器列表
            ipv6_servers: IPv6服务器列表

        Returns:
            bool: 是否保存成功
        """
        try:
            from backend.infrastructure.data_module_vnpy.cache_manager import DailyCacheManager

            # 转换为可JSON序列化的格式
            server_data = {
                "ipv4": [[ip, port] for ip, port in ipv4_servers],
                "ipv6": [[ip, port] for ip, port in ipv6_servers],
            }

            # 保存缓存（带日期）
            success = DailyCacheManager.save_with_date(server_data, self._cache_file)

            if success:
                self._cache_date = DailyCacheManager.get_today()
                self.logger.info(
                    "服务器池缓存已保存: IPv4=%d个, IPv6=%d个 (仅保存测试通过的服务器)",
                    len(ipv4_servers),
                    len(ipv6_servers),
                    extra={"log_type": "stage_node"},
                )

            return success

        except Exception as e:
            self.logger.error("保存服务器池缓存失败: %s", e, exc_info=True)
            return False

    def is_cache_valid(self) -> bool:
        """检查缓存是否有效

        Returns:
            bool: True=有效，False=失效
        """
        try:
            from backend.infrastructure.data_module_vnpy.cache_manager import DailyCacheManager

            return DailyCacheManager.is_cache_valid(self._cache_date)
        except Exception:
            return False


# -------------------- 全局单例实例 --------------------


server_pool_manager = ServerPoolManager()


# -------------------- 便捷函数 --------------------


def get_best_servers(count: int = 10, pool_type: str = "ipv4") -> List[Tuple[str, int]]:
    """获取最快的N个服务器（便捷函数）

    Args:
        count: 返回的服务器数量
        pool_type: 池类型，"ipv4"或"ipv6"，默认"ipv4"
    """
    return server_pool_manager.get_servers(count=count, pool_type=pool_type)


def get_best_server(pool_type: str = "ipv4") -> Optional[Tuple[str, int]]:
    """获取最快的服务器（便捷函数）

    Args:
        pool_type: 池类型，"ipv4"或"ipv6"，默认"ipv4"
    """
    return server_pool_manager.get_best_server(pool_type=pool_type)


def get_all_servers(pool_type: str = "ipv4") -> List[Tuple[str, int]]:
    """获取所有排序后的服务器（便捷函数）

    Args:
        pool_type: 池类型，"ipv4"或"ipv6"，默认"ipv4"
    """
    return server_pool_manager.get_servers(pool_type=pool_type)


def get_verified_servers_random(
    count: Optional[int] = None, pool_type: str = "ipv4"
) -> List[Tuple[str, int]]:
    """获取已验证的服务器（随机排列）- 便捷函数

    Args:
        count: 返回的服务器数量
        pool_type: 池类型，"ipv4"或"ipv6"，默认"ipv4"
    """
    import random

    # 尝试获取已测速的服务器
    if server_pool_manager.is_running():
        try:
            servers = server_pool_manager.get_servers(pool_type=pool_type)
            servers_copy = servers.copy()
            random.shuffle(servers_copy)
            servers = servers_copy

            if count is not None:
                servers = servers[:count]

            return servers
        except Exception:
            pass

    # Fallback: 从constants.py获取所有服务器并随机打乱（使用指定类型的池）
    ipv4_servers, ipv6_servers = _get_all_servers()
    servers = (ipv6_servers if pool_type == "ipv6" else ipv4_servers).copy()
    random.shuffle(servers)

    if count is not None:
        servers = servers[:count]

    return servers


def get_verified_servers(
    count: Optional[int] = None, shuffle: bool = True, pool_type: str = "ipv4"
) -> List[Tuple[str, int]]:
    """获取已测速的可用服务器并随机打乱顺序

    Args:
        count: 返回的服务器数量
        shuffle: 是否打乱顺序
        pool_type: 池类型，"ipv4"或"ipv6"，默认"ipv4"
    """
    logger = logging.getLogger(__name__)

    try:
        # 使用指定类型的池
        if pool_type == "ipv6":
            selected_servers = server_pool_manager._sorted_servers_ipv6
        else:
            selected_servers = server_pool_manager._sorted_servers_ipv4

        if server_pool_manager.is_running() and selected_servers:
            servers = selected_servers.copy()
            logger.debug(
                "使用server_pool_manager的测速缓存: %d个%s可用服务器",
                len(servers),
                pool_type.upper(),
            )
        else:
            raise RuntimeError(
                f"{pool_type.upper()}服务器池缓存不可用！请手动测速：\n"
                "1. 打开数据中心\n"
                "2. 点击【重新测速】按钮\n"
                "3. 等待测速完成后重试"
            )
    except RuntimeError:
        raise
    except Exception as e:
        logger.error("获取服务器池缓存失败: %s", e)
        raise RuntimeError(
            f"{pool_type.upper()}服务器池缓存异常！请手动测速：\n"
            "1. 打开数据中心\n"
            "2. 点击【重新测速】按钮\n"
            "3. 等待测速完成后重试"
        )

    if shuffle:
        random.shuffle(servers)

    if count is not None:
        servers = servers[:count]

    logger.info("获取到%d个已测速%s服务器（随机排列=%s）", len(servers), pool_type.upper(), shuffle)

    return servers


def get_random_servers(
    count: Optional[int] = None, pool_type: str = "ipv4"
) -> List[Tuple[str, int]]:
    """获取随机排列的服务器（快捷方式）

    Args:
        count: 返回的服务器数量
        pool_type: 池类型，"ipv4"或"ipv6"，默认"ipv4"
    """
    return get_verified_servers(count=count, shuffle=True, pool_type=pool_type)


# -------------------- 服务器池测速任务 --------------------


class ServerPoolTestTask(NetworkTask):
    """服务器池测速任务"""

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
            estimated_duration=10,
            estimated_memory_mb=30,
            estimated_connections=150,
        )

    def execute(self, config: Dict[str, Any]) -> Any:
        """执行服务器池测速"""
        pass


# ==============================================================================
# 第8部分：参数调优（ParameterSet、ParameterTuner、预定义参数组合）
# ==============================================================================


# -------------------- 数据类 --------------------


@dataclass
class ParameterSet:
    """参数组合"""

    name: str
    safe_zone_lower: float
    safe_zone_upper: float
    increase_step: float
    decrease_step: float
    batch_size_disk: int
    batch_size_network: int
    check_interval: float
    min_adjustment_interval: float


@dataclass
class PerformanceMetrics:
    """性能指标"""

    execution_time: float  # 执行时间（秒）
    cpu_usage: float  # CPU使用率（%）
    memory_usage: float  # 内存使用率（%）
    throughput: float  # 吞吐量（任务/秒）
    adjustment_count: int  # 动态调整次数
    success_rate: float  # 成功率（%）


@dataclass
class TuningResult:
    """调优结果"""

    parameter_set: ParameterSet
    metrics: PerformanceMetrics
    score: float  # 综合得分


# -------------------- 参数调优器 --------------------


class ParameterTuner:
    """参数调优器

    使用A/B测试框架自动化测试不同参数组合。
    """

    def __init__(self):
        """初始化参数调优器"""
        self.logger = logging.getLogger(__name__)

    def run_tuning(
        self,
        parameter_sets: List[ParameterSet],
        test_workload: Any,
        iterations: int = 3,
    ) -> List[TuningResult]:
        """运行参数调优"""
        self.logger.info("=" * 80)
        self.logger.info(
            "开始参数调优：%d个参数组合，每个%d次迭代", len(parameter_sets), iterations
        )
        self.logger.info("=" * 80)

        results = []

        for param_set in parameter_sets:
            self.logger.info("\n测试参数组合: %s", param_set.name)
            self.logger.info(
                "  安全区间: %.0f-%.0f%%", param_set.safe_zone_lower, param_set.safe_zone_upper
            )
            self.logger.info(
                "  调整步长: +%.0f%% / -%.0f%%",
                param_set.increase_step * 100,
                param_set.decrease_step * 100,
            )
            self.logger.info(
                "  批次基线: disk=%d, network=%d",
                param_set.batch_size_disk,
                param_set.batch_size_network,
            )

            # 运行多次迭代并取平均值
            iteration_metrics = []
            for i in range(iterations):
                self.logger.info("  迭代 %d/%d...", i + 1, iterations)
                metrics = self._run_single_test(param_set, test_workload)
                iteration_metrics.append(metrics)

            # 计算平均指标
            avg_metrics = self._average_metrics(iteration_metrics)

            # 计算综合得分
            score = self._calculate_score(avg_metrics)

            result = TuningResult(parameter_set=param_set, metrics=avg_metrics, score=score)
            results.append(result)

            self.logger.info("  ✅ 完成: 得分=%.2f, 时间=%.2fs", score, avg_metrics.execution_time)

        self.logger.info("\n" + "=" * 80)
        self.logger.info("参数调优完成")
        self.logger.info("=" * 80)

        return results

    def _run_single_test(self, param_set: ParameterSet, test_workload: Any) -> PerformanceMetrics:
        """运行单次测试"""
        if not HAS_PSUTIL:
            return PerformanceMetrics(
                execution_time=0.0,
                cpu_usage=0.0,
                memory_usage=0.0,
                throughput=0.0,
                adjustment_count=0,
                success_rate=0.0,
            )

        # 记录起始状态
        start_time = time.time()
        start_cpu = float(psutil.cpu_percent(interval=0.1))
        start_memory = float(psutil.virtual_memory().percent)

        # 运行测试工作负载
        try:
            result = test_workload(param_set)
            success_rate = 100.0
            adjustment_count = result.get("adjustment_count", 0)
        except Exception as e:
            self.logger.error("测试失败: %s", e)
            result = {"task_count": 0, "adjustment_count": 0}
            success_rate = 0.0
            adjustment_count = 0

        # 记录结束状态
        end_time = time.time()
        end_cpu = float(psutil.cpu_percent(interval=0.1))
        end_memory = float(psutil.virtual_memory().percent)

        # 计算指标
        execution_time = end_time - start_time
        cpu_usage = (start_cpu + end_cpu) / 2.0
        memory_usage = (start_memory + end_memory) / 2.0
        throughput = result.get("task_count", 0) / execution_time if execution_time > 0 else 0.0

        return PerformanceMetrics(
            execution_time=execution_time,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            throughput=throughput,
            adjustment_count=adjustment_count,
            success_rate=success_rate,
        )

    def _average_metrics(self, metrics_list: List[PerformanceMetrics]) -> PerformanceMetrics:
        """计算平均指标"""
        if not metrics_list:
            return PerformanceMetrics(
                execution_time=0.0,
                cpu_usage=0.0,
                memory_usage=0.0,
                throughput=0.0,
                adjustment_count=0,
                success_rate=0.0,
            )

        return PerformanceMetrics(
            execution_time=sum(m.execution_time for m in metrics_list) / len(metrics_list),
            cpu_usage=sum(m.cpu_usage for m in metrics_list) / len(metrics_list),
            memory_usage=sum(m.memory_usage for m in metrics_list) / len(metrics_list),
            throughput=sum(m.throughput for m in metrics_list) / len(metrics_list),
            adjustment_count=int(sum(m.adjustment_count for m in metrics_list) / len(metrics_list)),
            success_rate=sum(m.success_rate for m in metrics_list) / len(metrics_list),
        )

    def _calculate_score(self, metrics: PerformanceMetrics) -> float:
        """计算综合得分"""
        # 时间得分：基于相对速度
        time_score = max(0, 100 - (metrics.execution_time / 0.1))

        # 吞吐量得分：每个任务/秒得5分
        throughput_score = min(100, metrics.throughput * 5)

        # 资源使用得分：使用率越低越好
        cpu_score = max(0, 100 - metrics.cpu_usage)
        memory_score = max(0, 100 - metrics.memory_usage)

        # 成功率得分
        success_score = metrics.success_rate

        # 加权综合得分
        score = (
            time_score * 0.4
            + throughput_score * 0.3
            + cpu_score * 0.1
            + memory_score * 0.1
            + success_score * 0.1
        )

        return score

    def get_best_parameters(self, results: List[TuningResult]) -> ParameterSet:
        """获取最佳参数组合"""
        if not results:
            raise ValueError("没有调优结果")

        best_result = max(results, key=lambda r: r.score)

        self.logger.info("\n" + "=" * 80)
        self.logger.info("🏆 最佳参数组合: %s", best_result.parameter_set.name)
        self.logger.info("=" * 80)
        self.logger.info("综合得分: %.2f", best_result.score)
        self.logger.info("性能指标:")
        self.logger.info("  执行时间: %.2fs", best_result.metrics.execution_time)
        self.logger.info("  吞吐量: %.2f 任务/秒", best_result.metrics.throughput)
        self.logger.info("  CPU使用: %.1f%%", best_result.metrics.cpu_usage)
        self.logger.info("  内存使用: %.1f%%", best_result.metrics.memory_usage)
        self.logger.info("  成功率: %.1f%%", best_result.metrics.success_rate)

        return best_result.parameter_set

    def generate_report(self, results: List[TuningResult]) -> str:
        """生成调优报告"""
        # 按得分排序
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)

        report = ["# 参数调优报告\n"]
        report.append("## 测试结果排名\n")
        report.append("| 排名 | 参数组合 | 综合得分 | 执行时间 | 吞吐量 | CPU | 内存 | 成功率 |\n")
        report.append("|------|---------|---------|---------|-------|-----|------|--------|\n")

        for i, result in enumerate(sorted_results, 1):
            m = result.metrics
            report.append(
                f"| {i} | {result.parameter_set.name} | {result.score:.2f} | "
                f"{m.execution_time:.2f}s | {m.throughput:.2f} | "
                f"{m.cpu_usage:.1f}% | {m.memory_usage:.1f}% | {m.success_rate:.1f}% |\n"
            )

        report.append("\n## 最佳参数配置\n\n")
        best = sorted_results[0]
        report.append("```python\n")
        for key, value in asdict(best.parameter_set).items():
            if key != "name":
                report.append(f"{key.upper()} = {value}\n")
        report.append("```\n")

        return "".join(report)


# -------------------- 预定义参数组合 --------------------


def get_default_parameter_sets() -> List[ParameterSet]:
    """获取默认的参数组合"""
    return [
        ParameterSet(
            name="当前默认",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
        ParameterSet(
            name="保守",
            safe_zone_lower=60.0,
            safe_zone_upper=70.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=30,
            batch_size_network=80,
            check_interval=2.0,
            min_adjustment_interval=5.0,
        ),
        ParameterSet(
            name="激进",
            safe_zone_lower=70.0,
            safe_zone_upper=80.0,
            increase_step=0.10,
            decrease_step=0.15,
            batch_size_disk=100,
            batch_size_network=150,
            check_interval=1.0,
            min_adjustment_interval=2.0,
        ),
        ParameterSet(
            name="平衡",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.08,
            decrease_step=0.12,
            batch_size_disk=70,
            batch_size_network=120,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
    ]


def create_parameter_tuner() -> ParameterTuner:
    """便捷函数：创建参数调优器"""
    return ParameterTuner()


# ==============================================================================
# 第9部分：监控服务和LoadBalancer主类
# ==============================================================================


# -------------------- LoadBalancer监控服务 --------------------


_SERVICE_INSTANCE: Optional["LoadBalancerMonitoringService"] = None


class LoadBalancerMonitoringService:
    """LoadBalancer监控服务

    单例服务，提供统一的LoadBalancer监控能力。
    """

    def __init__(self, name: str = "global_loadbalancer"):
        """初始化监控服务"""
        self.logger = logging.getLogger(__name__)
        self.name = name

        # 创建指标采集器（直接引用同文件内的类）
        self.metrics_collector = LoadBalancerMetricsCollector(name=name)

        # 创建告警管理器
        self.alert_manager = PerformanceAlertManager(self.metrics_collector)

        # 注册默认告警回调
        self.alert_manager.register_callback(log_alert_callback)

        # 是否启用
        self._enabled = True

        self.logger.info("LoadBalancer监控服务已初始化: %s", name)

    # ==================== 任务跟踪 ====================

    def start_task(
        self,
        task_type: str,
        task_id: Optional[str] = None,
        batch_size: int = 0,
        worker_count: int = 0,
    ) -> str:
        """开始跟踪任务"""
        if not self._enabled:
            return task_id or ""

        return self.metrics_collector.start_task(
            task_type=task_type,
            task_id=task_id,
            batch_size=batch_size,
            worker_count=worker_count,
        )

    def end_task(
        self,
        task_id: str,
        success: bool = True,
        error: Optional[str] = None,
    ):
        """结束任务跟踪"""
        if not self._enabled:
            return

        self.metrics_collector.end_task(task_id=task_id, success=success, error=error)

    def record_adjustment(
        self,
        adjustment_type: str,
        old_value: Any,
        new_value: Any,
        reason: Optional[str] = None,
    ):
        """记录动态调整"""
        if not self._enabled:
            return

        self.metrics_collector.record_adjustment(
            adjustment_type=adjustment_type,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
        )

    def update_queue_length(self, length: int):
        """更新队列长度"""
        if not self._enabled:
            return

        self.metrics_collector.update_queue_length(length)

    # ==================== 指标和告警 ====================

    def get_metrics(self, window_seconds: Optional[int] = None) -> Dict[str, Any]:
        """获取聚合指标"""
        if not self._enabled:
            return {}

        metrics = self.metrics_collector.get_metrics(window_seconds)

        return {
            "timestamp": metrics.timestamp.isoformat(),
            "total_tasks": metrics.total_tasks,
            "successful_tasks": metrics.successful_tasks,
            "failed_tasks": metrics.failed_tasks,
            "success_rate": (
                metrics.successful_tasks / metrics.total_tasks * 100
                if metrics.total_tasks > 0
                else 100.0
            ),
            "avg_execution_time": metrics.avg_execution_time,
            "avg_batch_size": metrics.avg_batch_size,
            "avg_worker_count": metrics.avg_worker_count,
            "pool_utilization": metrics.pool_utilization,
            "adjustment_count": metrics.adjustment_count,
            "queue_length": metrics.queue_length,
        }

    def check_alerts(self, window_seconds: Optional[int] = None) -> list:
        """检查告警"""
        if not self._enabled:
            return []

        alerts = self.alert_manager.check_alerts(window_seconds)

        return [
            {
                "rule_name": alert.rule_name,
                "level": alert.level.value,
                "message": alert.message,
                "timestamp": alert.timestamp.isoformat(),
                "metrics": alert.metrics,
            }
            for alert in alerts
        ]

    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        if not self._enabled:
            return {"enabled": False}

        return self.metrics_collector.get_performance_summary()

    # ==================== 服务控制 ====================

    def enable(self):
        """启用监控"""
        self._enabled = True
        self.logger.info("LoadBalancer监控已启用")

    def disable(self):
        """禁用监控"""
        self._enabled = False
        self.logger.info("LoadBalancer监控已禁用")

    def reset(self):
        """重置指标"""
        if not self._enabled:
            return

        self.metrics_collector.reset()
        self.alert_manager.clear_history()
        self.logger.info("LoadBalancer监控指标已重置")


def get_loadbalancer_service(name: str = "global_loadbalancer") -> LoadBalancerMonitoringService:
    """获取LoadBalancer监控服务实例（单例）"""
    global _SERVICE_INSTANCE

    if _SERVICE_INSTANCE is None:
        _SERVICE_INSTANCE = LoadBalancerMonitoringService(name=name)

    return _SERVICE_INSTANCE


def reset_loadbalancer_service():
    """重置LoadBalancer监控服务实例"""
    global _SERVICE_INSTANCE
    _SERVICE_INSTANCE = None


# -------------------- LoadBalancer主类 --------------------


class LoadBalancer:
    """统一负载均衡器（单例）

    核心功能：
    - 获取系统监控指标（纯事件订阅模式）
    - 评估资源压力（基于系统监控指标.md的评分模型）
    - 计算最优配置（根据任务类型和资源压力）
    - 智能缓存（减少评估开销）
    """

    _instance: Optional["LoadBalancer"] = None
    _lock = threading.Lock()

    def __new__(cls, event_engine: Optional[EventEngine] = None):
        """单例模式实现"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    cls._instance = instance
        return cls._instance

    def __init__(self, event_engine: Optional[EventEngine] = None):
        """初始化LoadBalancer"""
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self.logger = logging.getLogger(__name__)

        # v3.3: 使用ResourceMonitor（集成了event_loop_lag监控）
        self.resource_monitor = ResourceMonitor(event_engine=event_engine)

        # 保留旧的引用以兼容现有代码
        self.metrics_monitor = self.resource_monitor.metrics_monitor
        self.evaluator = self.resource_monitor.evaluator

        self.config_calculator = DynamicConfigCalculator(self.evaluator)

        self._config_cache: Dict[str, tuple] = {}
        self._cache_ttl = 3.0
        self._extended_cache_ttl = 10.0
        self._cache_lock = threading.Lock()

        self._eval_count = 0
        self._cache_hit_count = 0
        self._running = False
        self._updater_thread: Optional[threading.Thread] = None

        # 新增：并发调整历史
        self._concurrency_history = []
        self._last_adjustment_time = 0
        self._min_adjustment_interval = 0.3  # 0.3秒监控周期

        # 新增：配置应用状态跟踪
        self._current_status = "idle"  # idle | adjusting | applied | rejected

        self.logger.info("✅ LoadBalancer初始化完成（支持动态并发调整 + event_loop_lag监控）")

    def get_optimal_config(
        self, task: BaseTask, force_realtime: bool = False, extended_cache: bool = False
    ) -> Dict[str, Any]:
        """获取任务的最优配置（实时评估）"""
        if not force_realtime:
            cached_config = self._get_cached_config(task.name, extended_cache)
            if cached_config is not None:
                with self._cache_lock:
                    self._cache_hit_count += 1
                self.logger.debug("📦 使用缓存配置: %s", task.name)
                return cached_config

        self._set_status("adjusting")
        start_time = time.time()
        with self._cache_lock:
            self._eval_count += 1

        try:
            metrics = self.metrics_monitor.get_metrics(force_realtime=force_realtime)
            pressure_eval = self.evaluator.evaluate(metrics)
            config = self.config_calculator.calculate_for_task(task, pressure_eval)

            # 根据任务类型调整策略
            if hasattr(task, "task_type") and task.task_type == "ipo_download":
                # IPO下载：IO密集，可以更高并发
                # 每进程协程数增加50%
                coroutines_per_process = config.get("coroutines_per_process", 10)
                coroutines_per_process = min(int(coroutines_per_process * 1.5), 50)  # 但不超过50
                config["coroutines_per_process"] = coroutines_per_process
                self.logger.info("IPO下载任务优化：每进程协程数调整为 %d", coroutines_per_process)

            self._cache_config(task.name, config, extended_cache)

            elapsed = (time.time() - start_time) * 1000
            self.logger.info(
                "🎯 [%s] 配置评估完成（%.1fms）\n"
                "   压力评分: %d/100\n"
                "   瓶颈维度: %s\n"
                "   缩放因子: %.2f\n"
                "   配置: %s\n"
                "   原因: %s",
                task.name,
                elapsed,
                pressure_eval["pressure_score"],
                pressure_eval["bottleneck"],
                pressure_eval["scale_factor"],
                self._format_config(config),
                pressure_eval["reason"],
            )

            self._set_status("applied")
            return config

        except Exception as e:
            self.logger.error("配置评估失败: %s", str(e), exc_info=True)
            self._set_status("rejected")
            return self._get_default_config(task)

    def get_concurrency_decision_with_lag(
        self,
        task: BaseTask,
        current_processes: int = 1,
        current_coroutines: int = 10,
        force_realtime: bool = False,
    ) -> Dict[str, Any]:
        """基于event_loop_lag和资源压力做并发决策（v3.3新增）

        结合事件循环延迟和资源压力，智能决定增加进程、增加协程还是减少协程。

        Args:
            task: 任务对象
            current_processes: 当前进程数
            current_coroutines: 当前每进程协程数
            force_realtime: 是否强制实时评估

        Returns:
            {
                'action': 'INCREASE_PROCESS' | 'DECREASE_COROUTINE' | 'INCREASE_COROUTINE' | 'HOLD',
                'reason': str,
                'suggested_processes': int,
                'suggested_coroutines_per_process': int,
                'lag_ms': float,
                'pressure_score': float,
            }
        """
        try:
            # 1. 获取event_loop_lag
            event_loop_lag = self.resource_monitor.get_event_loop_lag()

            # 2. 获取资源压力
            pressure = self.resource_monitor.get_current_pressure(force_realtime=force_realtime)

            # 3. 调用配置计算器做决策
            decision = self.config_calculator.make_concurrency_decision(
                task=task,
                pressure=pressure,
                event_loop_lag_ms=event_loop_lag,
                current_processes=current_processes,
                current_coroutines=current_coroutines,
            )

            # 4. 记录决策日志
            if decision["action"] != "HOLD":
                self.logger.info(
                    "🔧 [%s] 并发决策: %s\n"
                    "   原因: %s\n"
                    "   当前: %d进程 × %d协程\n"
                    "   建议: %d进程 × %d协程\n"
                    "   延迟: %.1fms | 压力: %.1f",
                    task.name,
                    decision["action"],
                    decision["reason"],
                    current_processes,
                    current_coroutines,
                    decision["suggested_processes"],
                    decision["suggested_coroutines_per_process"],
                    decision["lag_ms"],
                    decision["pressure_score"],
                )

            return decision

        except Exception as e:
            self.logger.error("并发决策失败: %s", str(e), exc_info=True)
            return {
                "action": "HOLD",
                "reason": f"决策失败: {e}",
                "suggested_processes": current_processes,
                "suggested_coroutines_per_process": current_coroutines,
                "lag_ms": 0,
                "pressure_score": 0,
            }

    def get_optimal_config_with_adjustment(
        self,
        task: BaseTask,
        current_concurrency: int,
        force_realtime: bool = False,
        processes: int = 1,
    ) -> Dict[str, Any]:
        """获取最优配置并进行动态并发调整"""
        start_time = time.time()
        with self._cache_lock:
            self._eval_count += 1

        try:
            # 1. 获取监控指标
            metrics = self.metrics_monitor.get_metrics(force_realtime=force_realtime)

            # 2. 评估资源压力（包含上下限判断）
            eval_result = self.evaluator.evaluate(metrics)

            # 3. 根据评估结果调整并发
            now = time.time()
            action = eval_result.get("action", "hold")
            adjustment = eval_result.get("adjustment", 0)

            new_concurrency = current_concurrency
            rejected = False

            # 检查是否需要调整（受最小间隔限制）
            if now - self._last_adjustment_time >= self._min_adjustment_interval:
                # adjustment表示每个进程的调整量，需要乘以进程数得到总调整量
                total_adjustment = adjustment * processes

                if action == "reject":
                    # 拒绝新任务，降低并发
                    new_concurrency = max(1, current_concurrency + total_adjustment)
                    rejected = True
                    self.logger.warning(
                        "⚠️ 拒绝任务并降并发: %d → %d (每进程%+d, %d进程), 原因: %s",
                        current_concurrency,
                        new_concurrency,
                        adjustment,
                        processes,
                        eval_result["reason"],
                    )
                    self._concurrency_history.append(
                        {
                            "time": now,
                            "action": "reject",
                            "old": current_concurrency,
                            "new": new_concurrency,
                            "reason": eval_result["reason"],
                        }
                    )
                    self._last_adjustment_time = now

                elif action == "increase":
                    # 提升并发
                    new_concurrency = current_concurrency + total_adjustment
                    self.logger.info(
                        "✅ 提升并发: %d → %d (每进程%+d, %d进程), 原因: %s",
                        current_concurrency,
                        new_concurrency,
                        adjustment,
                        processes,
                        eval_result["reason"],
                    )
                    self._concurrency_history.append(
                        {
                            "time": now,
                            "action": "increase",
                            "old": current_concurrency,
                            "new": new_concurrency,
                            "reason": eval_result["reason"],
                        }
                    )
                    self._last_adjustment_time = now

                elif action == "decrease":
                    # 降低并发（但不拒绝）
                    new_concurrency = max(1, current_concurrency + total_adjustment)
                    self.logger.info(
                        "⚠️ 降低并发: %d → %d (每进程%+d, %d进程), 原因: %s",
                        current_concurrency,
                        new_concurrency,
                        adjustment,
                        processes,
                        eval_result["reason"],
                    )
                    self._concurrency_history.append(
                        {
                            "time": now,
                            "action": "decrease",
                            "old": current_concurrency,
                            "new": new_concurrency,
                            "reason": eval_result["reason"],
                        }
                    )
                    self._last_adjustment_time = now
                else:
                    # hold - 保持当前并发
                    self.logger.debug("保持当前并发: %d", current_concurrency)
            else:
                # 在最小间隔内，不调整
                self.logger.debug(
                    "距离上次调整不足%.1f秒，跳过本次调整", self._min_adjustment_interval
                )

            # 4. 计算完整配置
            config = self.config_calculator.calculate_for_task(task, eval_result)

            # 5. 添加调整结果和当前metrics
            config["rejected"] = rejected
            config["new_concurrency"] = new_concurrency
            config["current_concurrency"] = current_concurrency
            config["action"] = action
            config["adjustment"] = adjustment
            # 从嵌套结构中提取指标
            system = metrics.get("system", {})
            config["cpu_percent"] = system.get("cpu_percent", 0)
            config["memory_percent"] = system.get("memory_percent", 0)
            # 磁盘队列深度（取最大值）
            storage = metrics.get("system", {}).get("storage_subsystem", {}).get("disks", {})
            disk_queue_depth = 0.0
            disk_util_percent = 0.0
            for disk_info in storage.values():
                queue = disk_info.get("queue_depth", 0)
                if queue and queue > disk_queue_depth:
                    disk_queue_depth = queue
                util = disk_info.get("util_percent")
                if util and util > disk_util_percent:
                    disk_util_percent = util
            config["disk_queue_depth"] = disk_queue_depth
            config["disk_util_percent"] = disk_util_percent

            elapsed = (time.time() - start_time) * 1000
            self.logger.info(
                "🎯 [%s] 动态调整评估完成（%.1fms）\n"
                "   压力评分: %d/100\n"
                "   动作: %s\n"
                "   并发: %d → %d\n"
                "   原因: %s",
                task.name,
                elapsed,
                eval_result["pressure_score"],
                action,
                current_concurrency,
                new_concurrency,
                eval_result["reason"],
            )

            return config

        except Exception as e:
            self.logger.error("动态调整评估失败: %s", str(e), exc_info=True)
            # 失败时返回保守配置
            return {
                "rejected": False,
                "new_concurrency": current_concurrency,
                "current_concurrency": current_concurrency,
                "action": "hold",
                "adjustment": 0,
                "reason": f"评估失败: {e}",
                **self._get_default_config(task),
            }

    def _get_cached_config(
        self, task_name: str, _extended: bool = False
    ) -> Optional[Dict[str, Any]]:
        """获取缓存的配置"""
        with self._cache_lock:
            if task_name not in self._config_cache:
                return None

            cached_config, cached_time, is_extended = self._config_cache[task_name]
            ttl = self._extended_cache_ttl if is_extended else self._cache_ttl

            if time.time() - cached_time > ttl:
                del self._config_cache[task_name]
                return None

            return cached_config.copy()

    def _cache_config(self, task_name: str, config: Dict[str, Any], extended: bool = False):
        """缓存配置"""
        with self._cache_lock:
            self._config_cache[task_name] = (config.copy(), time.time(), extended)

    def get_current_status(self) -> str:
        """获取当前配置应用状态

        Returns:
            状态字符串: "idle" | "adjusting" | "applied" | "rejected"
        """
        return getattr(self, "_current_status", "idle")

    def _set_status(self, status: str):
        """设置当前状态

        Args:
            status: 状态字符串 (idle/adjusting/applied/rejected)
        """
        self._current_status = status

    def _format_config(self, config: Dict[str, Any]) -> str:
        """格式化配置为可读字符串"""
        key_fields = []

        if "processes" in config:
            key_fields.append(
                "%d进程 × %d协程 = %d连接"
                % (
                    config["processes"],
                    config["coroutines_per_process"],
                    config["total_connections"],
                )
            )
        elif "max_workers" in config:
            key_fields.append("%d工作线程, 批量%d" % (config["max_workers"], config["batch_size"]))

        return ", ".join(key_fields) if key_fields else str(config)

    def _get_default_config(self, task: BaseTask) -> Dict[str, Any]:
        """获取默认配置（保守策略）"""
        if task.metrics.task_type == TaskType.NETWORK:
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
        """清空配置缓存"""
        with self._cache_lock:
            cache_size = len(self._config_cache)
            self._config_cache.clear()
        self.logger.info("LoadBalancer缓存已清空（清除%d个缓存）", cache_size)

    def get_stats(self) -> Dict[str, Any]:
        """获取LoadBalancer统计信息"""
        with self._cache_lock:
            cache_size = len(self._config_cache)
            total_requests = self._eval_count + self._cache_hit_count
            cache_hit_rate = (
                self._cache_hit_count / total_requests * 100 if total_requests > 0 else 0
            )
            adjustment_count = len(self._concurrency_history)

        return {
            "eval_count": self._eval_count,
            "cache_hit_count": self._cache_hit_count,
            "cache_hit_rate": round(cache_hit_rate, 2),
            "cache_size": cache_size,
            "cache_ttl": self._cache_ttl,
            "extended_cache_ttl": self._extended_cache_ttl,
            "background_updater_running": self._running,
            "adjustment_count": adjustment_count,
        }

    def get_adjustment_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取并发调整历史"""
        with self._cache_lock:
            history = self._concurrency_history.copy()

        if limit and len(history) > limit:
            history = history[-limit:]

        return history

    def clear_adjustment_history(self):
        """清空并发调整历史"""
        with self._cache_lock:
            self._concurrency_history.clear()
        self.logger.info("并发调整历史已清空")

    def close(self):
        """关闭LoadBalancer，释放资源"""
        if hasattr(self, "metrics_monitor"):
            self.metrics_monitor.close()
        self.logger.info("LoadBalancer已关闭")


# ==============================================================================
# 全局单例获取函数（保持API兼容）
# ==============================================================================


_GLOBAL_LOADBALANCER: Optional[LoadBalancer] = None


def get_load_balancer(force_reinit: bool = False) -> LoadBalancer:
    """获取全局LoadBalancer实例（单例）

    Args:
        force_reinit: 是否强制重新初始化（默认False）

    Returns:
        LoadBalancer: 全局单例实例
    """
    global _GLOBAL_LOADBALANCER

    if force_reinit or _GLOBAL_LOADBALANCER is None:
        from backend.core.base import get_event_engine

        event_engine = get_event_engine()
        _GLOBAL_LOADBALANCER = LoadBalancer(event_engine=event_engine)

    return _GLOBAL_LOADBALANCER


# ==============================================================================
# 模块导出列表（__all__）
# ==============================================================================


__all__ = [
    # 第1部分：任务定义
    "TaskType",
    "ResourceProfile",
    "TaskMetrics",
    "BaseTask",
    "NetworkTask",
    "LocalProcessingTask",
    # 第2部分：策略配置
    "ModelConfig",
    "AdjustmentStrategy",
    "ExecutionPlan",
    "AdaptiveThresholdCalculator",
    "get_adaptive_calculator",
    "ExecutionPolicy",
    "DynamicConfigCalculator",
    # 第3部分：监控评估
    "LagMonitor",
    "SystemMetricsMonitor",
    "ResourcePressure",
    "ResourceMonitor",
    "ResourcePressureEvaluator",
    "LoadBalancerMetricsCollector",
    "PerformanceAlertManager",
    "Alert",
    "AlertLevel",
    "AlertRule",
    "log_alert_callback",
    "create_metrics_collector",
    "create_alert_manager",
    # 第4部分：执行层
    "TaskUnit",
    "TaskResult",
    "ExecutionModel",
    "MultiProcessAsyncModel",
    "PersistentProcessPool",
    "MultiProcessBatchModel",
    "StreamProcessingModel",
    "AdaptiveBatchSizeCalculatorFull",
    "ChunkReader",
    "StreamAggregator",
    "EnhancedStreamProcessor",
    "get_process_pool",
    "get_adaptive_batch_calculator",
    # 第5部分：队列系统
    "TaskPriority",
    "TaskStatus",
    "TaskMetadata",
    "TaskQueue",
    "QTaskWorker",
    "TaskQueueManager",
    "ExecutionStrategy",
    "AdaptiveScheduler",
    "PriorityScheduler",
    "HybridScheduler",
    "LoadBalancerQueueFacade",
    "get_queue_facade",
    # 第6部分：资源管理
    "ResourceLimitConfig",
    "WindowsJobObjectLimiter",
    "ApplicationLevelLimiter",
    "QResourceMonitor",
    "HybridResourceLimiter",
    # 第7部分：服务器池
    "ServerPoolManager",
    "server_pool_manager",
    "get_best_servers",
    "get_best_server",
    "get_all_servers",
    "get_verified_servers_random",
    "get_verified_servers",
    "get_random_servers",
    "ServerPoolTestTask",
    # 第8部分：参数调优
    "ParameterSet",
    "PerformanceMetrics",
    "TuningResult",
    "ParameterTuner",
    "get_default_parameter_sets",
    "create_parameter_tuner",
    # 第9部分：服务层和核心类
    "LoadBalancerMonitoringService",
    "get_loadbalancer_service",
    "reset_loadbalancer_service",
    "LoadBalancer",
    "get_load_balancer",
    # 智能调优器
    "IntelligentAdaptiveTuner",
    # 第10部分：进程池与连接管理
    "DynamicProcessPool",
    "ConnectionLifecycleManager",
]


# ==============================================================================
# 第11部分：进程池与连接管理（v3.7新增 - DynamicProcessPool + ConnectionLifecycleManager）
# ==============================================================================


# -------------------- 动态进程池管理器 --------------------


class DynamicProcessPool:
    """运行时动态增减进程的进程池管理器（v3.6集成）

    核心功能：
    1. 支持运行时增加进程（创建新worker并启动）
    2. 支持运行时减少进程（优雅停止worker）
    3. 所有worker从共享task_queue拉取任务
    4. 支持独立的result_queue和metrics_queue

    使用方式：
    ```python
    pool = DynamicProcessPool(
        initial_processes=4,
        worker_function=my_worker_process,
        shared_queues={
            'task_queue': task_queue,
            'result_queue': result_queue,
            'metrics_queue': metrics_queue,
        },
        worker_kwargs={'param1': value1, ...}
    )

    await pool.start()
    await pool.adjust_processes(6)  # 动态调整
    await pool.stop()
    ```
    """

    def __init__(
        self,
        initial_processes: int,
        worker_function: Callable,
        shared_queues: Dict[str, Any],
        worker_kwargs: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """初始化动态进程池

        Args:
            initial_processes: 初始进程数
            worker_function: worker进程入口函数
            shared_queues: 共享队列字典，必须包含：
                - task_queue: 任务队列
                - result_queue: 结果队列
                - metrics_queue: 监控指标队列
                可选：
                - progress_queue: 进度队列
                - config_queue: 配置队列
            worker_kwargs: 传递给worker函数的其他参数
            logger: 日志记录器
        """
        self.initial_processes = initial_processes
        self.worker_function = worker_function
        self.shared_queues = shared_queues
        self.worker_kwargs = worker_kwargs or {}
        self.logger = logger or logging.getLogger(__name__)

        # 进程管理
        self.processes: List[multiprocessing.Process] = []
        self.next_worker_id = 0
        self.stop_event: Optional[multiprocessing.Event] = None

        # 验证必需的队列
        required_queues = ["task_queue", "result_queue", "metrics_queue"]
        for queue_name in required_queues:
            if queue_name not in shared_queues:
                raise ValueError(f"缺少必需的队列: {queue_name}")

    async def start(self):
        """启动初始进程池"""
        self.logger.info("=" * 80)
        self.logger.info(f"🚀 启动动态进程池: {self.initial_processes}个进程")
        self.logger.info("=" * 80)

        # 创建停止事件
        ctx = multiprocessing.get_context("spawn")
        self.stop_event = ctx.Event()

        # 启动初始进程
        for _ in range(self.initial_processes):
            self._create_and_start_worker()

        self.logger.info(f"✅ {len(self.processes)}个worker进程已启动")

    def _create_and_start_worker(self) -> multiprocessing.Process:
        """创建并启动一个新的worker进程"""
        worker_id = self.next_worker_id
        self.next_worker_id += 1

        # 准备worker参数
        worker_args = {
            "worker_id": worker_id,
            "stop_event": self.stop_event,
            **self.shared_queues,
            **self.worker_kwargs,
        }

        # 创建进程
        p = multiprocessing.Process(
            target=self.worker_function, kwargs=worker_args, name=f"Worker-{worker_id}"
        )
        p.start()
        self.processes.append(p)

        self.logger.info(f"✅ 创建新worker进程: Worker-{worker_id} (PID: {p.pid})")
        return p

    async def adjust_processes(self, target_count: int):
        """动态调整进程数量

        Args:
            target_count: 目标进程数
        """
        current_count = len([p for p in self.processes if p.is_alive()])

        if target_count == current_count:
            return

        if target_count > current_count:
            # 增加进程
            to_add = target_count - current_count
            self.logger.info(f"📈 增加进程: {current_count} → {target_count} (+{to_add})")

            for _ in range(to_add):
                self._create_and_start_worker()
                await asyncio.sleep(0.1)  # 短暂延迟，避免同时创建大量进程

            self.logger.info(
                f"✅ 进程增加完成，当前活跃进程: {len([p for p in self.processes if p.is_alive()])}"
            )

        elif target_count < current_count:
            # 减少进程（优雅停止）
            to_remove = current_count - target_count
            self.logger.info(f"📉 减少进程: {current_count} → {target_count} (-{to_remove})")

            alive_processes = [p for p in self.processes if p.is_alive()]
            to_stop = alive_processes[target_count:]

            # 记录待停止的进程
            for p in to_stop:
                self.logger.info(f"🔻 标记进程待停止: {p.name} (PID: {p.pid})")

            # 保留前target_count个活跃进程
            self.processes = alive_processes[:target_count]

            self.logger.info(f"✅ 进程减少标记完成，保留进程数: {len(self.processes)}")
            self.logger.info("   注意：被移除的进程将在完成当前任务后自然退出")

    def get_active_process_count(self) -> int:
        """获取当前活跃进程数"""
        return len([p for p in self.processes if p.is_alive()])

    async def stop(self, timeout: float = 5.0):
        """停止所有进程

        Args:
            timeout: 等待进程结束的超时时间（秒）
        """
        self.logger.info("=" * 80)
        self.logger.info("🛑 停止动态进程池")
        self.logger.info("=" * 80)

        # 设置停止事件
        if self.stop_event:
            self.stop_event.set()

        # 等待所有进程结束
        alive_count = len([p for p in self.processes if p.is_alive()])
        self.logger.info(f"等待{alive_count}个进程结束（超时{timeout}秒）...")

        for p in self.processes:
            if p.is_alive():
                p.join(timeout=timeout / len(self.processes))
                if p.is_alive():
                    self.logger.warning(f"⚠️ 进程{p.name}未能在超时内结束，强制终止")
                    p.terminate()
                    p.join(timeout=1.0)

        self.logger.info("✅ 所有进程已停止")

    def get_status(self) -> Dict[str, Any]:
        """获取进程池状态"""
        alive_processes = [p for p in self.processes if p.is_alive()]
        return {
            "total_processes": len(self.processes),
            "alive_processes": len(alive_processes),
            "dead_processes": len(self.processes) - len(alive_processes),
            "next_worker_id": self.next_worker_id,
            "process_pids": [p.pid for p in alive_processes],
        }


# -------------------- 连接生命周期管理器 --------------------


class ConnectionLifecycleManager:
    """连接生命周期管理器（v3.7新增）

    提供标准化的连接创建、健康检查、清理流程，
    供所有worker函数使用，确保资源正确管理，
    彻底解决 socket.send() raised exception 问题。

    核心功能：
    1. 批量创建连接（带超时和健康检查）
    2. 批量关闭连接（带超时和详细统计）
    3. 连接健康检查
    4. 统一的错误处理和日志记录

    设计原则：
    - 不维护连接池（因为asyncio连接无法跨进程共享）
    - 提供工具方法（由worker在进程内调用）
    - 确保资源一定被释放

    使用方式：
    ```python
    # 在worker函数内部
    conn_manager = ConnectionLifecycleManager(worker_id, logger)

    try:
        # 创建连接
        connections = await conn_manager.create_connections(
            servers=server_list,
            timeout=5.0,
            health_check=True
        )

        # 使用连接进行业务逻辑
        # ...

    finally:
        # 确保连接被关闭
        stats = await conn_manager.close_all_connections(timeout=3.0)
    ```
    """

    def __init__(self, worker_id: int, logger: Optional[logging.Logger] = None):
        """初始化连接生命周期管理器

        Args:
            worker_id: Worker进程ID（用于日志）
            logger: 日志记录器
        """
        self.worker_id = worker_id
        self.logger = logger or logging.getLogger(__name__)
        self.created_connections: List[AsyncTdxHq_API] = []

    async def create_connections(
        self,
        servers: List[Tuple[str, int]],
        timeout: float = 5.0,
        health_check: bool = True,
        health_check_timeout: float = 2.0,
    ) -> List[AsyncTdxHq_API]:
        """批量创建连接（带健康检查）

        Args:
            servers: 服务器列表 [(ip, port), ...]
            timeout: 连接超时时间
            health_check: 是否进行健康检查
            health_check_timeout: 健康检查超时时间

        Returns:
            成功创建的连接列表
        """
        self.logger.info(f"Worker {self.worker_id} 开始创建 {len(servers)} 个连接...")

        async def create_single_connection(server: Tuple[str, int]) -> Optional[AsyncTdxHq_API]:
            """创建单个连接（带健康检查）"""
            try:
                # 创建连接（带超时）
                client = await asyncio.wait_for(
                    AsyncTdxHq_API.factory(server, timeout=timeout), timeout=timeout + 2
                )

                if not client:
                    return None

                # 健康检查（可选）
                if health_check:
                    try:
                        # 发送一个轻量级请求测试连接
                        test_result = await asyncio.wait_for(
                            client.get_finance_info(1, "600000"), timeout=health_check_timeout
                        )

                        if test_result is None:
                            # 连接虽然建立但返回无效数据
                            self.logger.debug(
                                f"Worker {self.worker_id} 连接 {server} "
                                f"健康检查失败（返回None）"
                            )
                            await asyncio.wait_for(client.close(), timeout=2.0)
                            return None

                        return client

                    except asyncio.TimeoutError:
                        self.logger.debug(f"Worker {self.worker_id} 连接 {server} " f"健康检查超时")
                        await asyncio.wait_for(client.close(), timeout=2.0)
                        return None
                    except Exception as e:
                        self.logger.debug(
                            f"Worker {self.worker_id} 连接 {server} "
                            f"健康检查失败: {type(e).__name__}"
                        )
                        await asyncio.wait_for(client.close(), timeout=2.0)
                        return None
                else:
                    return client

            except asyncio.TimeoutError:
                self.logger.debug(f"Worker {self.worker_id} 连接 {server} 创建超时")
                return None
            except Exception as e:
                self.logger.debug(
                    f"Worker {self.worker_id} 连接 {server} 创建失败: " f"{type(e).__name__}: {e}"
                )
                return None

        # 并发创建所有连接
        connection_results = await asyncio.gather(
            *[create_single_connection(server) for server in servers], return_exceptions=True
        )

        # 过滤出成功的连接
        connections: List[AsyncTdxHq_API] = []
        for result in connection_results:
            if result and not isinstance(result, Exception):
                connections.append(result)
                self.created_connections.append(result)

        success_rate = len(connections) / len(servers) * 100 if servers else 0
        self.logger.info(
            f"Worker {self.worker_id} 连接创建完成: "
            f"{len(connections)}/{len(servers)} ({success_rate:.1f}%)"
        )

        if len(connections) == 0:
            self.logger.error(f"Worker {self.worker_id} ❌ 所有连接创建失败！")
        elif success_rate < 50:
            self.logger.warning(
                f"Worker {self.worker_id} ⚠️ 连接成功率低于50%，" f"可能存在网络问题"
            )

        return connections

    async def close_all_connections(self, timeout: float = 3.0) -> Dict[str, Any]:
        """关闭所有已创建的连接（带超时和统计）

        Args:
            timeout: 单个连接关闭的超时时间

        Returns:
            关闭统计信息 {"success": int, "timeout": int, "error": int}
        """
        if not self.created_connections:
            self.logger.debug(f"Worker {self.worker_id} 无需关闭连接")
            return {"success": 0, "timeout": 0, "error": 0}

        self.logger.info(
            f"Worker {self.worker_id} 开始关闭 {len(self.created_connections)} 个连接..."
        )

        async def close_single_connection(
            conn: AsyncTdxHq_API, index: int
        ) -> Tuple[int, str, Optional[str]]:
            """关闭单个连接（带超时和错误记录）

            Returns:
                (索引, 状态, 错误信息)
            """
            try:
                await asyncio.wait_for(conn.close(), timeout=timeout)
                return (index, "success", None)
            except asyncio.TimeoutError:
                return (index, "timeout", f"close timeout after {timeout}s")
            except Exception as e:
                return (index, "error", f"{type(e).__name__}: {e}")

        # 并发关闭所有连接
        close_results = await asyncio.gather(
            *[close_single_connection(conn, i) for i, conn in enumerate(self.created_connections)],
            return_exceptions=True,
        )

        # 统计结果
        stats = {"success": 0, "timeout": 0, "error": 0}
        timeout_indices = []
        error_details = []

        for result in close_results:
            if isinstance(result, Exception):
                stats["error"] += 1
                error_details.append(f"unexpected: {result}")
            else:
                index, status, error = result
                stats[status] += 1
                if status == "timeout":
                    timeout_indices.append(index)
                elif status == "error":
                    error_details.append(f"conn#{index}: {error}")

        # 记录详细日志
        if stats["success"] == len(self.created_connections):
            self.logger.info(
                f"Worker {self.worker_id} ✅ 所有 {stats['success']} " f"个连接已安全关闭"
            )
        else:
            self.logger.warning(
                f"Worker {self.worker_id} 连接关闭完成: "
                f"成功{stats['success']}/{len(self.created_connections)}, "
                f"超时{stats['timeout']}, "
                f"错误{stats['error']}"
            )

            if timeout_indices:
                shown = timeout_indices[:5]
                more = len(timeout_indices) - 5
                self.logger.warning(
                    f"  超时连接索引: {shown}" + (f" ...({more}个更多)" if more > 0 else "")
                )

            if error_details:
                shown = error_details[:5]
                more = len(error_details) - 5
                for detail in shown:
                    self.logger.warning(f"  错误: {detail}")
                if more > 0:
                    self.logger.warning(f"  ...还有{more}个错误")

        # 清空连接列表
        self.created_connections.clear()

        return stats
