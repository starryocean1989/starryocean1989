# -*- coding: utf-8 -*-
"""监控系统核心模块 - 完整合并版（monitor_core.py + monitors.py）.


包含所有监控核心组件，方便调试：
- Part 1-6: 来自 monitor_core.py（监控进程V2核心）
- Part 7-10: 来自 monitors.py（系统/进程监控和业务指标）

调试提示：单文件可完整查看调用栈，所有核心逻辑都在此文件


提示：调试时优先在以下位置设置断点
- MonitoringProcessV2.start() - 进程启动入口
- MonitoringProcessV2._evaluate_alerts() - 告警评估
- AdaptiveThresholdManager._update_threshold() - 阈值更新
- SmartMonitor.get_smart_data() - SMART采集
"""

import asyncio
import json
import logging
import os
import platform
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple

import numpy as np
import zmq
import zmq.asyncio

# ==================== 日志配置 ====================
# 创建专用logger（模块级别，监控进程独立）
logger = logging.getLogger("monitor_process")
logger_alert = logging.getLogger("monitor_process.alert")
logger_sensor = logging.getLogger("monitor_process.sensor")
logger_zmq = logging.getLogger("monitor_process.zmq")

# 尝试导入psutil,如果没有则使用基础实现
try:
    import psutil
    from psutil._common import sdiskio, snetio

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil模块未安装,将使用基础系统监控功能")

# 尝试导入WMI（Windows Management Instrumentation）
try:
    import wmi

    HAS_WMI = True
except ImportError:
    HAS_WMI = False
    logger.debug("WMI模块未安装，将使用简化磁盘检测")

# 网络测速功能使用自研模块（基于公共测速站点，无第三方依赖）
# 导入将在 BandwidthMonitor 类中按需进行

# 从 system_toolkit 导入 SMART 相关类
from backend.infrastructure.system_vnpy.system_toolkit import (
    DiskSmartData,
    SmartMonitor,
)

# =============================================================================
# Part 1: 数据结构和配置
# =============================================================================


@dataclass
class ThresholdConfig:
    """阈值配置."""

    metric_name: str
    default_warning: Optional[float] = None
    default_critical: Optional[float] = None
    min_samples: int = 100
    window_size: int = 1440
    warning_formula: str = "p95_plus_half_std"
    critical_formula: str = "p99_plus_std"
    default_weight: float = 0.3
    learned_weight: float = 0.7


@dataclass
class ThresholdResult:
    """阈值结果."""

    metric_name: str
    warning_threshold: Optional[float]
    critical_threshold: Optional[float]
    sample_count: int
    mean: Optional[float]
    stddev: Optional[float]
    p95: Optional[float]
    p99: Optional[float]
    using_default: bool
    last_updated: datetime


# SmartAttribute 和 DiskSmartData 已从 system_toolkit 导入

# =============================================================================
# Part 2: 自适应阈值管理器
# =============================================================================


class AdaptiveThresholdManager:
    """自适应阈值管理器 - 基于滑动窗口统计学习."""

    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self._metric_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1440))
        self._configs: Dict[str, ThresholdConfig] = {}
        self._current_thresholds: Dict[str, ThresholdResult] = {}
        self._last_update_time: Dict[str, float] = {}
        self._update_interval = 3600
        logger.info("自适应阈值管理器初始化完成")

    def register_metric(self, config: ThresholdConfig):
        self._configs[config.metric_name] = config
        logger.info(
            "注册指标: %s (默认警告=%s, 默认严重=%s)",
            config.metric_name,
            config.default_warning,
            config.default_critical,
        )

    def learn_baseline(self, metric_name: str, value: float):
        if metric_name not in self._configs:
            return
        self._metric_history[metric_name].append(value)
        last_update = self._last_update_time.get(metric_name, 0)
        if time.time() - last_update >= self._update_interval:
            self._update_threshold(metric_name)

    def get_threshold(self, metric_name: str, severity: str) -> Optional[float]:
        if metric_name not in self._configs:
            return None
        if metric_name in self._current_thresholds:
            result = self._current_thresholds[metric_name]
            if severity == "warning":
                return result.warning_threshold
            elif severity == "critical":
                return result.critical_threshold
        config = self._configs[metric_name]
        if severity == "warning":
            return config.default_warning
        elif severity == "critical":
            return config.default_critical
        return None

    def get_all_thresholds(self) -> Dict[str, Dict[str, Any]]:
        """获取所有指标动态阈值.

        Returns:
            {
                "cpu_percent": {
                    "warning": 85.5,
                    "critical": 95.2,
                    "p95": 82.3,
                    "p99": 94.1,
                    "sample_count": 500,
                    "using_default": False
                },
                ...
            }
        """
        result = {}
        for metric_name, threshold_result in self._current_thresholds.items():
            result[metric_name] = {
                "warning": threshold_result.warning_threshold,
                "critical": threshold_result.critical_threshold,
                "p95": threshold_result.p95,
                "p99": threshold_result.p99,
                "sample_count": threshold_result.sample_count,
                "using_default": threshold_result.using_default,
                "last_updated": (
                    threshold_result.last_updated.isoformat()
                    if threshold_result.last_updated
                    else None
                ),
            }
        return result

    def _update_threshold(self, metric_name: str):
        config = self._configs[metric_name]
        history = list(self._metric_history[metric_name])
        sample_count = len(history)

        if sample_count < config.min_samples:
            logger.debug(
                "阈值学习: 指标=%s, 样本不足=%d/%d (使用默认阈值)",
                metric_name,
                sample_count,
                config.min_samples,
            )
            logger.debug(
                "阈值学习: 指标=%s, 样本不足=%d/%d (使用默认阈值)",
                metric_name,
                sample_count,
                config.min_samples,
            )
            result = ThresholdResult(
                metric_name=metric_name,
                warning_threshold=config.default_warning,
                critical_threshold=config.default_critical,
                sample_count=sample_count,
                mean=None,
                stddev=None,
                p95=None,
                p99=None,
                using_default=True,
                last_updated=datetime.now(),
            )
            self._current_thresholds[metric_name] = result
            self._last_update_time[metric_name] = time.time()
            return

        try:
            mean = float(np.mean(history))
            stddev = float(np.std(history))
            p95 = float(np.percentile(history, 95))
            p99 = float(np.percentile(history, 99))
        except Exception as e:
            logger.exception("计算统计量失败 (%s): %s", metric_name, e)
            return

        warning_learned = self._calculate_threshold(p95, p99, stddev, config.warning_formula)
        critical_learned = self._calculate_threshold(p95, p99, stddev, config.critical_formula)

        warning_threshold = self._blend_threshold(
            config.default_warning, warning_learned, config.default_weight, config.learned_weight
        )
        critical_threshold = self._blend_threshold(
            config.default_critical, critical_learned, config.default_weight, config.learned_weight
        )

        result = ThresholdResult(
            metric_name=metric_name,
            warning_threshold=warning_threshold,
            critical_threshold=critical_threshold,
            sample_count=sample_count,
            mean=mean,
            stddev=stddev,
            p95=p95,
            p99=p99,
            using_default=False,
            last_updated=datetime.now(),
        )

        self._current_thresholds[metric_name] = result
        self._last_update_time[metric_name] = time.time()

        # 详细学习过程日志
        logger.info(
            "阈值学习完成: 指标=%s, 样本=%d, "
            "均值=%.2f, 标准差=%.2f, P95=%.2f, P99=%.2f, "
            "告警阈值=%.2f->%.2f, 严重阈值=%.2f->%.2f",
            metric_name,
            sample_count,
            mean,
            stddev,
            p95,
            p99,
            config.default_warning or 0,
            warning_threshold or 0,
            config.default_critical or 0,
            critical_threshold or 0,
        )

        if self.db_manager:
            self._save_to_database(result)

    def _calculate_threshold(self, p95: float, p99: float, stddev: float, formula: str) -> float:
        if formula == "p95_plus_half_std":
            return p95 + 0.5 * stddev
        elif formula == "p99_plus_std":
            return p99 + 1.0 * stddev
        return p95

    def _blend_threshold(
        self,
        default_value: Optional[float],
        learned_value: float,
        default_weight: float,
        learned_weight: float,
    ) -> Optional[float]:
        if default_value is None:
            return learned_value
        total_weight = default_weight + learned_weight
        return (default_value * default_weight + learned_value * learned_weight) / total_weight

    def _save_to_database(self, result: ThresholdResult):
        if not self.db_manager:
            return
        try:
            self.db_manager.execute_update(
                """INSERT OR REPLACE INTO adaptive_thresholds
                (metric_name, mean, stddev, p95, p99, sample_count,
                 last_updated, threshold_warning, threshold_critical)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.metric_name,
                    result.mean,
                    result.stddev,
                    result.p95,
                    result.p99,
                    result.sample_count,
                    result.last_updated.isoformat(),
                    result.warning_threshold,
                    result.critical_threshold,
                ),
            )
        except Exception as e:
            logger.exception("保存阈值将数据库失败: %s", e)

    def load_from_database(self):
        if not self.db_manager:
            return
        try:
            rows = self.db_manager.execute_query("SELECT * FROM adaptive_thresholds")
            for row in rows:
                result = ThresholdResult(
                    metric_name=row["metric_name"],
                    warning_threshold=row["threshold_warning"],
                    critical_threshold=row["threshold_critical"],
                    sample_count=row["sample_count"],
                    mean=row["mean"],
                    stddev=row["stddev"],
                    p95=row["p95"],
                    p99=row["p99"],
                    using_default=False,
                    last_updated=datetime.fromisoformat(row["last_updated"]),
                )
                self._current_thresholds[result.metric_name] = result
            logger.info("从数据库加载了 %d 个阈值配置", len(rows))
        except Exception as e:
            logger.exception("从数据库加载阈值失败: %s", e)


# =============================================================================
# Part 3: 硬盘SMART监控（已迁移到 system_toolkit.py）
# =============================================================================
# SmartMonitor 类已迁移到 system_toolkit.py，在文件顶部导入


# =============================================================================
# Part 4: 硬件监控器工厂
# =============================================================================


class HardwareMonitorFactory:
    """硬件监控器工厂 - 强制使用LibreHardwareMonitor."""
    
    _instance = None  # 单例实例

    @staticmethod
    def create_monitor():
        """创建硬件监控器（必须使用LibreHardwareMonitor Extended）.

        Returns:
            ExtendedLHMWrapper实例或None（如果不可用）
        """
        try:
            from backend.infrastructure.system_vnpy.librehardwaremonitor.lhm_extended import (
                ExtendedLHMWrapper,
            )

            monitor = ExtendedLHMWrapper()
            if monitor.is_available():
                logger.info("✅ 使用 LibreHardwareMonitor Extended")
                # 保存单例实例
                HardwareMonitorFactory._instance = monitor
                return monitor
            else:
                logger.error("❌ LibreHardwareMonitor 不可用，请确保：")
                logger.error("   1. 已安装 pythonnet: pip install pythonnet")
                logger.error("   2. LibreHardwareMonitor.dll 在正确路径")
                logger.error("   3. 以管理员权限运行程序")
                return None
        except Exception as e:
            logger.exception("❌ LibreHardwareMonitor 初始化失败: %s", e)
            logger.error("   硬件监控功能将不可用")
            return None
    
    @staticmethod
    def get_instance():
        """获取硬件监控器单例实例.
        
        Returns:
            ExtendedLHMWrapper实例或None
        """
        return HardwareMonitorFactory._instance


def get_hardware_monitor_instance():
    """获取硬件监控器实例（全局访问函数）.
    
    Returns:
        ExtendedLHMWrapper实例或None
    """
    return HardwareMonitorFactory.get_instance()


# =============================================================================
# Part 5: 系统分析器（从独立文件合并）
# =============================================================================


class SystemBottleneckAnalyzer:
    """系统级瓶颈分析引擎（从 bottleneck_analyzer.py 合并）.

    基于木桶理论，评估系统各维度性能，识别短板。
    评分规则：
    - CPU维度: 40分满分
    - 内存维度: 30分满分
    - 磁盘I/O维度: 15分满分
    - 网络维度: 15分满分
    - 总分: 100分

    瓶颈判断：得分最低维度即为瓶颈
    """

    def __init__(self):
        """初始化瓶颈分析器."""
        self.logger = logging.getLogger(__name__)

        # 评分权重配置
        self.weights = {
            "cpu": 40,
            "memory": 30,
            "disk": 15,
            "network": 15,
        }

        # 严重程度阈值
        self.severity_thresholds = {
            "critical": 50,  # <50分 = 严重瓶颈
            "warning": 70,  # 50-70分 = 压力大
            "normal": 85,  # 70-85分 = 正常
            # >85分 = 性能充足
        }

    def analyze(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """分析系统瓶颈.

        Args:
            metrics: 系统指标数据，包含system, process等字段

        Returns:
            {
                "total_score": 75,  # 综合评分 0-100
                "bottleneck_dimension": "disk_io",  # 瓶颈维度
                "scores": {
                    "cpu": 35,
                    "memory": 25,
                    "disk": 10,
                    "network": 15
                },
                "details": {
                    "cpu": {"usage": 85, "context_switches": 60000, ...},
                    "memory": {...},
                    "disk": {...},
                    "network": {...}
                },
                "suggestions": ["使用SSD", "减少并发I/O"],
                "severity": "warning"  # normal/warning/critical
            }
        """
        try:
            # 提取系统指标
            system_metrics = metrics.get("system", {})

            # 计算各维度得分
            cpu_score, cpu_details = self._calculate_cpu_score(system_metrics)
            memory_score, memory_details = self._calculate_memory_score(system_metrics)
            disk_score, disk_details = self._calculate_disk_score(system_metrics)
            network_score, network_details = self._calculate_network_score(system_metrics)

            scores = {
                "cpu": cpu_score,
                "memory": memory_score,
                "disk": disk_score,
                "network": network_score,
            }

            details = {
                "cpu": cpu_details,
                "memory": memory_details,
                "disk": disk_details,
                "network": network_details,
            }

            # 总分
            total_score = sum(scores.values())

            # 识别瓶颈维度（得分最低）
            bottleneck_dimension = min(scores.keys(), key=lambda k: scores[k])

            # 判断严重程度
            severity = self._get_severity(total_score)

            # 生成优化建议
            suggestions = self._generate_suggestions(
                bottleneck_dimension, details[bottleneck_dimension], system_metrics
            )

            # 计算自适应并发缩放因子（0.3-1.6范围）
            adaptive_scale_factor = 0.3 + (total_score / 100) * 1.3

            return {
                "total_score": round(total_score, 1),
                "bottleneck_dimension": bottleneck_dimension,
                "scores": {k: round(v, 1) for k, v in scores.items()},
                "details": details,
                "suggestions": suggestions,
                "severity": severity,
                "analysis_time": metrics.get("timestamp", ""),
                "adaptive_scale_factor": round(adaptive_scale_factor, 2),
            }

        except Exception as e:
            self.logger.error("瓶颈分析失败: %s", e, exc_info=True)
            # 返回默认安全值
            return {
                "total_score": 100,
                "bottleneck_dimension": "balanced",
                "scores": {"cpu": 40, "memory": 30, "disk": 15, "network": 15},
                "details": {},
                "suggestions": ["分析过程出错，请检查日志"],
                "severity": "normal",
                "error": str(e),
            }

    def _calculate_cpu_score(self, metrics: Dict) -> tuple[float, Dict]:
        """计算CPU维度得分（满分40）.

        评分因素：
        1. CPU使用率 (权重0.6)
        2. 上下文切换频率 (权重0.4)
        """
        cpu_percent = metrics.get("cpu_percent", 0)

        # 获取CPU详细指标
        cpu_detailed = metrics.get("cpu_detailed", {})
        context_switches = cpu_detailed.get("context_switches_per_sec", 0)

        # CPU使用率评分 (0-100% -> 24-0分)
        cpu_usage_score = 24 * (1 - cpu_percent / 100)

        # 上下文切换评分 (0-100K -> 16-0分)
        ctx_switch_score = 16 * (1 - min(context_switches / 100000, 1))

        total = cpu_usage_score + ctx_switch_score

        details = {
            "cpu_percent": cpu_percent,
            "context_switches_per_sec": context_switches,
            "usage_score": round(cpu_usage_score, 1),
            "context_switch_score": round(ctx_switch_score, 1),
        }

        return max(0, min(40, total)), details

    def _calculate_memory_score(self, metrics: Dict) -> tuple[float, Dict]:
        """计算内存维度得分（满分30）.

        评分因素：
        1. 内存使用率 (权重0.6)
        2. 交换活动 (权重0.4, swap活动=0分)
        """
        memory_percent = metrics.get("memory_percent", 0)

        # 获取内存子系统指标
        memory_subsystem = metrics.get("memory_subsystem", {})
        swap_in = memory_subsystem.get("swap_in_kbps", 0)
        swap_out = memory_subsystem.get("swap_out_kbps", 0)
        has_swap = swap_in > 0 or swap_out > 0

        # 内存使用率评分 (0-100% -> 18-0分)
        memory_usage_score = 18 * (1 - memory_percent / 100)

        # 交换活动评分 (有swap=0分, 无swap=12分)
        swap_score = 0 if has_swap else 12

        total = memory_usage_score + swap_score

        details = {
            "memory_percent": memory_percent,
            "swap_in_kbps": swap_in,
            "swap_out_kbps": swap_out,
            "has_swap_activity": has_swap,
            "usage_score": round(memory_usage_score, 1),
            "swap_score": swap_score,
        }

        return max(0, min(30, total)), details

    def _calculate_disk_score(self, metrics: Dict) -> tuple[float, Dict]:
        """计算磁盘I/O维度得分（满分15）.

        评分因素：
        1. I/O延迟 (权重1.0)
        """
        # 获取存储子系统指标
        storage_subsystem = metrics.get("storage_subsystem", {})
        disks = storage_subsystem.get("disks", {})

        # 取所有磁盘平均延迟
        latencies = []
        for disk_info in disks.values():
            latency = disk_info.get("average_io_latency_ms", 0)
            if latency > 0:
                latencies.append(latency)

        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        # I/O延迟评分 (0-50ms -> 15-0分)
        # <10ms=满分, 10-20ms=正常, >20ms=瓶颈, >50ms=0分
        latency_score = 15 * (1 - min(avg_latency / 50, 1))

        details = {
            "average_io_latency_ms": round(avg_latency, 2),
            "disk_count": len(disks),
            "latency_score": round(latency_score, 1),
        }

        return max(0, min(15, latency_score)), details

    def _calculate_network_score(self, metrics: Dict) -> tuple[float, Dict]:
        """计算网络维度得分（满分15）.

        评分因素：
        1. 丢包率 (权重1.0)
        """
        # 获取网络子系统指标
        network_subsystem = metrics.get("network_subsystem", {})
        loss_in = network_subsystem.get("packet_loss_rate_in", 0)
        loss_out = network_subsystem.get("packet_loss_rate_out", 0)
        max_loss = max(loss_in, loss_out)

        # 丢包率评分 (0-5% -> 15-0分)
        # <0.5%=满分, 0.5-2%=正常, >2%=瓶颈, >5%=0分
        loss_score = 15 * (1 - min(max_loss / 0.05, 1))

        details = {
            "packet_loss_rate_in": loss_in,
            "packet_loss_rate_out": loss_out,
            "max_packet_loss": max_loss,
            "loss_score": round(loss_score, 1),
        }

        return max(0, min(15, loss_score)), details

    def _get_severity(self, total_score: float) -> str:
        """根据总分判断严重程度."""
        if total_score < self.severity_thresholds["critical"]:
            return "critical"
        elif total_score < self.severity_thresholds["warning"]:
            return "warning"
        elif total_score < self.severity_thresholds["normal"]:
            return "normal"
        else:
            return "good"

    def _generate_suggestions(
        self, bottleneck: str, details: Dict, system_metrics: Dict
    ) -> List[str]:
        """生成优化建议.

        Args:
            bottleneck: 瓶颈维度
            details: 该维度详细信息
            system_metrics: 完整系统指标
        """
        suggestions = []

        if bottleneck == "cpu":
            cpu_percent = details.get("cpu_percent", 0)
            ctx_switches = details.get("context_switches_per_sec", 0)

            if cpu_percent > 85:
                suggestions.append("CPU使用率过高，建议优化算法复杂度或使用多进程并行")
            if ctx_switches > 50000:
                suggestions.append("上下文切换频繁，建议减少线程数或使用协程")
            if cpu_percent > 70:
                suggestions.append("考虑降低数据处理并发数")

        elif bottleneck == "memory":
            memory_percent = details.get("memory_percent", 0)
            has_swap = details.get("has_swap_activity", False)

            if has_swap:
                suggestions.append("⚠️ 检测到内存交换活动，严重影响性能，立即降低负载50%")
                suggestions.append("检查是否存在内存泄漏")
                suggestions.append("考虑增加物理内存")
            elif memory_percent > 85:
                suggestions.append("内存使用率过高，建议减少数据缓存或分批处理")

        elif bottleneck == "disk":
            latency = details.get("average_io_latency_ms", 0)

            if latency > 20:
                suggestions.append("磁盘I/O延迟过高，建议使用SSD")
                suggestions.append("减少磁盘I/O操作或降低I/O并发数")
                suggestions.append("检查SMART状态，排除硬盘故障")
            if latency > 10:
                suggestions.append("使用异步I/O或增加缓冲")

        elif bottleneck == "network":
            max_loss = details.get("max_packet_loss", 0)

            if max_loss > 0.02:
                suggestions.append("网络丢包率过高，检查网络质量")
                suggestions.append("考虑切换更稳定网络或服务器")
            if max_loss > 0.005:
                suggestions.append("网络存在波动，建议添加重试机制")

        if not suggestions:
            suggestions.append("系统性能均衡，无明显瓶颈")

        return suggestions


class ScenarioAnalyzer:
    """量化场景分析器（从 scenario_analyzer.py 合并）.

    识别当前运行主要量化场景，并提供场景特定瓶颈分析和优化建议。
    支持5大量化场景：数据下载、实时行情、策略回测、策略编写、实盘交易。
    """

    def __init__(self, business_metrics=None):
        """初始化场景分析器.

        Args:
            business_metrics: 业务指标采集器（可选，用于获取业务指标）
        """
        self.logger = logging.getLogger(__name__)
        self.business_metrics = business_metrics

        # 场景关键字映射
        self.scenario_keywords = {
            "data_download": ["download", "数据下载", "历史数据", "tdx", "akshare"],
            "realtime_market": ["market", "行情", "tick", "websocket", "quote"],
            "backtest": ["backtest", "回测", "策略回测", "strategy"],
            "strategy_edit": ["编辑", "编译", "ide", "code"],
            "live_trading": ["trading", "交易", "gateway", "order", "实盘"],
        }

        # 场景显示名称
        self.scenario_names = {
            "data_download": "数据下载",
            "realtime_market": "实时行情",
            "backtest": "策略回测",
            "strategy_edit": "策略编写",
            "live_trading": "实盘交易",
            "idle": "空闲",
        }

    def detect_scenario(self, process_data: List[Dict]) -> str:
        """检测当前主要场景.

        Args:
            process_data: 进程列表数据

        Returns:
            场景标识: data_download / realtime_market / backtest /
                     strategy_edit / live_trading / idle
        """
        try:
            if not process_data:
                return "idle"

            # 统计各场景进程数和CPU占用
            scenario_scores = {
                "data_download": 0,
                "realtime_market": 0,
                "backtest": 0,
                "strategy_edit": 0,
                "live_trading": 0,
            }

            for proc in process_data:
                proc_name = proc.get("name", "").lower()
                proc_type = proc.get("type", "").lower()
                cpu_percent = proc.get("cpu_percent", 0)

                # 根据进程名和类型评分
                for scenario, keywords in self.scenario_keywords.items():
                    for keyword in keywords:
                        if keyword in proc_name or keyword in proc_type:
                            # 评分 = 1 + CPU占用权重
                            scenario_scores[scenario] += 1 + (cpu_percent / 100)
                            break

            # 返回得分最高场景
            if max(scenario_scores.values()) > 0:
                return max(scenario_scores.keys(), key=lambda k: scenario_scores[k])
            else:
                return "idle"

        except Exception as e:
            self.logger.error("场景检测失败: %s", e)
            return "idle"

    def analyze_scenario(self, scenario: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """场景专项分析.

        Args:
            scenario: 场景标识
            metrics: 系统指标数据

        Returns:
            {
                "scenario": "data_download",
                "scenario_name": "数据下载",
                "bottleneck_metrics": ["network_speed", "disk_io"],
                "current_values": {...},
                "thresholds": {...},
                "is_bottleneck": True,
                "bottleneck_reason": "网络带宽接近上限",
                "optimization_hints": [...]
            }
        """
        try:
            system_metrics = metrics.get("system", {})

            if scenario == "data_download":
                return self._analyze_download_scenario(system_metrics)
            elif scenario == "realtime_market":
                return self._analyze_realtime_scenario(system_metrics)
            elif scenario == "backtest":
                return self._analyze_backtest_scenario(system_metrics)
            elif scenario == "strategy_edit":
                return self._analyze_strategyedit_scenario(system_metrics)
            elif scenario == "live_trading":
                return self._analyze_trading_scenario(system_metrics)
            else:
                return self._analyze_idle_scenario(system_metrics)

        except Exception as e:
            self.logger.error("场景分析失败: %s", e, exc_info=True)
            return {
                "scenario": scenario,
                "scenario_name": self.scenario_names.get(scenario, "未知"),
                "error": str(e),
            }

    def _analyze_download_scenario(self, metrics: Dict) -> Dict[str, Any]:
        """分析数据下载场景."""
        network_speed = metrics.get("network_speed", {})
        disk_io = metrics.get("disk_io_speed", {})
        storage_subsystem = metrics.get("storage_subsystem", {})

        download_mbps = network_speed.get("download_kbps", 0) / 1024
        write_mbps = disk_io.get("write_mbps", 0)

        # 获取平均I/O延迟
        disks = storage_subsystem.get("disks", {})
        latencies = [d.get("average_io_latency_ms", 0) for d in disks.values()]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        # 从业务指标获取下载并发数
        download_concurrency = 8  # 默认值
        if self.business_metrics:
            download_concurrency = self.business_metrics.get_latest_value(
                "download_concurrency", default=8
            )

        current_values = {
            "network_download_mbps": round(download_mbps, 2),
            "disk_write_mbps": round(write_mbps, 2),
            "io_latency_ms": round(avg_latency, 2),
            "download_concurrency": download_concurrency,
        }

        # 瓶颈判断
        is_bottleneck = False
        bottleneck_reason = ""
        hints = []

        if download_mbps < 50 and write_mbps > download_mbps * 1.5:
            is_bottleneck = True
            bottleneck_reason = "网络带宽是瓶颈（磁盘写入能力充足）"
            hints.append("升级网络带宽或使用CDN")
            hints.append("考虑多线程下载")
        elif avg_latency > 20:
            is_bottleneck = True
            bottleneck_reason = "磁盘I/O延迟过高"
            hints.append("使用SSD提升写入性能")
            hints.append("减少下载并发数以降低I/O压力")
        elif write_mbps < 50:
            is_bottleneck = True
            bottleneck_reason = "磁盘写入速度较慢"
            hints.append("检查磁盘性能，考虑升级")
        else:
            hints.append("下载性能正常")

        return {
            "scenario": "data_download",
            "scenario_name": "数据下载",
            "bottleneck_metrics": ["network_download_mbps", "disk_write_mbps", "io_latency_ms"],
            "current_values": current_values,
            "thresholds": {
                "network_download_mbps": {"warning": 50, "critical": 20},
                "disk_write_mbps": {"warning": 50, "critical": 20},
                "io_latency_ms": {"warning": 10, "critical": 20},
            },
            "is_bottleneck": is_bottleneck,
            "bottleneck_reason": bottleneck_reason,
            "optimization_hints": hints,
        }

    def _analyze_realtime_scenario(self, metrics: Dict) -> Dict[str, Any]:
        """分析实时行情场景."""
        cpu_detailed = metrics.get("cpu_detailed", {})
        network_subsystem = metrics.get("network_subsystem", {})

        ctx_switches = cpu_detailed.get("context_switches_per_sec", 0)
        loss_in = network_subsystem.get("packet_loss_rate_in", 0)

        # 从业务指标获取事件队列深度和处理延迟
        event_queue_depth = 0  # 默认值
        processing_latency = 0  # 默认值
        if self.business_metrics:
            event_queue_depth = self.business_metrics.get_latest_value("event_queue_depth", default=0)
            processing_latency = self.business_metrics.get_latest_value(
                "event_processing_latency_ms", default=0
            )

        current_values = {
            "event_queue_depth": event_queue_depth,
            "processing_latency_ms": processing_latency,
            "context_switches_per_sec": int(ctx_switches),
            "packet_loss_rate": round(loss_in * 100, 3),
        }

        # 瓶颈判断
        is_bottleneck = False
        bottleneck_reason = ""
        hints = []

        if event_queue_depth > 1000:
            is_bottleneck = True
            bottleneck_reason = "事件队列积压，消费能力不足"
            hints.append("增加事件处理线程数")
            hints.append("优化事件处理逻辑")
        elif ctx_switches > 50000:
            is_bottleneck = True
            bottleneck_reason = "上下文切换频繁，调度压力大"
            hints.append("减少线程数或使用协程")
        elif loss_in > 0.005:
            is_bottleneck = True
            bottleneck_reason = "网络丢包率偏高"
            hints.append("检查网络质量，考虑切换服务器")
        else:
            hints.append("行情处理性能正常")

        return {
            "scenario": "realtime_market",
            "scenario_name": "实时行情",
            "bottleneck_metrics": [
                "event_queue_depth",
                "processing_latency_ms",
                "packet_loss_rate",
            ],
            "current_values": current_values,
            "thresholds": {
                "event_queue_depth": {"warning": 1000, "critical": 5000},
                "processing_latency_ms": {"warning": 50, "critical": 100},
                "packet_loss_rate": {"warning": 0.5, "critical": 2.0},
            },
            "is_bottleneck": is_bottleneck,
            "bottleneck_reason": bottleneck_reason,
            "optimization_hints": hints,
        }

    def _analyze_backtest_scenario(self, metrics: Dict) -> Dict[str, Any]:
        """分析策略回测场景."""
        cpu_percent = metrics.get("cpu_percent", 0)
        memory_percent = metrics.get("memory_percent", 0)
        memory_subsystem = metrics.get("memory_subsystem", {})

        swap_in = memory_subsystem.get("swap_in_kbps", 0)
        swap_out = memory_subsystem.get("swap_out_kbps", 0)

        # 从业务指标获取K线计算时间（当前暂无此指标，使用默认值）
        kline_calc_time = 0  # 默认值

        current_values = {
            "cpu_percent": round(cpu_percent, 1),
            "memory_percent": round(memory_percent, 1),
            "swap_activity_kbps": round(swap_in + swap_out, 1),
            "kline_calc_time_ms": kline_calc_time,
        }

        # 瓶颈判断
        is_bottleneck = False
        bottleneck_reason = ""
        hints = []

        if swap_in > 0 or swap_out > 0:
            is_bottleneck = True
            bottleneck_reason = "⚠️ 内存交换活动，严重影响吞吐速度"
            hints.append("立即减少回测数据量或降低并发数")
            hints.append("检查是否存在内存泄漏")
        elif cpu_percent > 85:
            is_bottleneck = True
            bottleneck_reason = "CPU负载过高，计算密集"
            hints.append("降低回测并发数")
            hints.append("优化策略算法复杂度")
        elif memory_percent > 85:
            is_bottleneck = True
            bottleneck_reason = "内存使用率过高"
            hints.append("分批回测或减少数据缓存")
        else:
            hints.append("回测性能正常")
            hints.append(
                f"建议并发缩放因子: {self._suggest_scale_factor(cpu_percent, memory_percent)}"
            )

        return {
            "scenario": "backtest",
            "scenario_name": "策略回测",
            "bottleneck_metrics": ["cpu_percent", "memory_percent", "swap_activity_kbps"],
            "current_values": current_values,
            "thresholds": {
                "cpu_percent": {"warning": 80, "critical": 90},
                "memory_percent": {"warning": 80, "critical": 90},
                "swap_activity_kbps": {"warning": 0, "critical": 1000},
            },
            "is_bottleneck": is_bottleneck,
            "bottleneck_reason": bottleneck_reason,
            "optimization_hints": hints,
        }

    def _analyze_strategyedit_scenario(self, metrics: Dict) -> Dict[str, Any]:
        """分析策略编写场景."""
        cpu_percent = metrics.get("cpu_percent", 0)
        memory_percent = metrics.get("memory_percent", 0)

        current_values = {
            "cpu_percent": round(cpu_percent, 1),
            "memory_percent": round(memory_percent, 1),
        }

        # 策略编写通常负载较低
        hints = ["策略编写场景，系统负载正常"]

        return {
            "scenario": "strategy_edit",
            "scenario_name": "策略编写",
            "bottleneck_metrics": ["cpu_percent", "memory_percent"],
            "current_values": current_values,
            "thresholds": {
                "cpu_percent": {"warning": 60, "critical": 80},
                "memory_percent": {"warning": 70, "critical": 85},
            },
            "is_bottleneck": False,
            "bottleneck_reason": "",
            "optimization_hints": hints,
        }

    def _analyze_trading_scenario(self, metrics: Dict) -> Dict[str, Any]:
        """分析实盘交易场景."""
        network_subsystem = metrics.get("network_subsystem", {})
        cpu_temp = metrics.get("temperature", {}).get("cpu", 0)

        loss_in = network_subsystem.get("packet_loss_rate_in", 0)

        # 从业务指标获取订单响应时间和交易队列长度（当前暂无此指标，使用默认值）
        order_response_ms = 0  # 默认值
        trading_queue_len = 0  # 默认值

        current_values = {
            "order_response_time_ms": order_response_ms,
            "trading_queue_length": trading_queue_len,
            "packet_loss_rate": round(loss_in * 100, 3),
            "cpu_temperature": round(cpu_temp, 1),
        }

        # 瓶颈判断
        is_bottleneck = False
        bottleneck_reason = ""
        hints = []

        if order_response_ms > 500:
            is_bottleneck = True
            bottleneck_reason = "订单响应延迟过高"
            hints.append("优化交易通道，减少网络延迟")
        elif loss_in > 0.005:
            is_bottleneck = True
            bottleneck_reason = "网络丢包率偏高，可能影响订单"
            hints.append("检查网络稳定性")
        elif cpu_temp > 80:
            is_bottleneck = True
            bottleneck_reason = "CPU温度过高，可能降频"
            hints.append("改善散热，避免影响交易稳定性")
        else:
            hints.append("交易系统运行稳定")

        return {
            "scenario": "live_trading",
            "scenario_name": "实盘交易",
            "bottleneck_metrics": ["order_response_time_ms", "packet_loss_rate", "cpu_temperature"],
            "current_values": current_values,
            "thresholds": {
                "order_response_time_ms": {"warning": 500, "critical": 1000},
                "packet_loss_rate": {"warning": 0.5, "critical": 2.0},
                "cpu_temperature": {"warning": 80, "critical": 90},
            },
            "is_bottleneck": is_bottleneck,
            "bottleneck_reason": bottleneck_reason,
            "optimization_hints": hints,
        }

    def _analyze_idle_scenario(self, metrics: Dict) -> Dict[str, Any]:
        """分析空闲场景."""
        return {
            "scenario": "idle",
            "scenario_name": "空闲",
            "bottleneck_metrics": [],
            "current_values": {},
            "thresholds": {},
            "is_bottleneck": False,
            "bottleneck_reason": "",
            "optimization_hints": ["系统当前空闲"],
        }

    def _suggest_scale_factor(self, cpu_percent: float, memory_percent: float) -> float:
        """根据CPU和内存使用率建议并发缩放因子."""
        if cpu_percent > 85 or memory_percent > 85:
            return 0.7
        elif cpu_percent > 70 or memory_percent > 70:
            return 0.9
        elif cpu_percent < 40 and memory_percent < 50:
            return 1.3
        elif cpu_percent < 60 and memory_percent < 65:
            return 1.1
        else:
            return 1.0


# =============================================================================
# Part 6: 监控进程V2主类（混合并发架构）
# =============================================================================


class MonitoringProcessV2:
    """监控进程V2 - 混合并发架构.

    架构:
    - 主事件循环 (asyncio): ZMQ通信、快速指标采集
    - 阻塞任务线程池: 硬件传感器采集、SMART查询
    - 数据库写入协程: 批量持久化

    调试提示:
    - 设置断点在 start() 查看启动流程
    - 设置断点在 _evaluate_alerts() 查看告警评估
    - 设置断点在 _hardware_collector_thread() 查看硬件采集
    """

    def __init__(self, db_path: str = "data/terminal.db", parent_pid: Optional[int] = None):
        self.running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # ✅ 初始化logger（使用模块级logger）
        self.logger = logger

        # 父进程监控（防止成为孤儿进程）
        import os

        if parent_pid is None:
            self.parent_pid = os.getppid()  # 如果未提供，则自动获取
        else:
            self.parent_pid = parent_pid  # 使用传入父进程PID

        logger.info(
            "[PARENT-MONITOR] 父进程PID（主应用）: %d, 当前进程PID（监控进程）: %d",
            self.parent_pid,
            os.getpid(),
        )

        # 基础配置初始化完成
        logger.debug(
            "基础配置初始化: db_path=%s, parent_pid=%d, current_pid=%d",
            db_path,
            self.parent_pid,
            os.getpid(),
        )

        # ZMQ通信
        self.zmq_context: Optional[zmq.asyncio.Context] = None
        self.push_socket: Optional[zmq.asyncio.Socket] = None
        self.rep_socket: Optional[zmq.asyncio.Socket] = None
        self.pull_socket: Optional[zmq.asyncio.Socket] = None

        # 数据缓存
        self.monitoring_data = {
            "system": {},
            "hardware": {},
            "process": {},
            "service": {},
            "smart": {},
        }

        # 监控工具
        # 监控工具（所有类已在本文件中定义，无需导入）
        # SystemMonitor, ProcessMonitor等已在本文件Part 7-10中定义

        # 创建监控组件
        logger.debug("开始创建监控组件")

        self.system_monitor = SystemMonitor()
        self.process_monitor = ProcessMonitor()
        self.process_bottleneck_analyzer = ProcessBottleneckAnalyzer()  # 进程级瓶颈分析器
        self.system_bottleneck_analyzer = SystemBottleneckAnalyzer()  # 系统级瓶颈分析器（本地）
        self.business_metrics_collector = get_business_metrics_collector()  # 业务指标采集器
        self.scenario_analyzer = ScenarioAnalyzer(self.business_metrics_collector)  # 场景分析器（注入业务指标）
        # ✅ 优化：延迟创建硬件监控器（避免阻塞启动，在_initialize_components中异步创建）
        self.hardware_monitor = None  # 将在start()中后台异步创建
        self.smart_monitor = SmartMonitor()

        # 告警和阈值
        self.adaptive_threshold: Optional[AdaptiveThresholdManager] = None

        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="MonitorWorker")

        # 协程启动屏障（确保所有协程都完成初始化）
        self.coroutine_ready_events: Dict[str, asyncio.Event] = {}

        # 数据库写入队列
        self.db_write_queue: Optional[asyncio.Queue] = None
        self.db_path = db_path

        # 线程间通信队列
        self.hardware_queue: Optional[asyncio.Queue] = None
        self.smart_queue: Optional[asyncio.Queue] = None
        self.smart_trigger_event: Optional[asyncio.Event] = None

        # 采集间隔
        self.fast_interval = 1  # 系统、进程
        self.slow_interval = 5  # 硬件传感器

        # 后台测试任务追踪（避免阻塞REP socket）
        self._background_bandwidth_task: Optional[asyncio.Task] = None

        logger.info("MonitoringProcessV2 初始化完成（硬件监控器将在start()中后台创建）")
        logger.debug(
            "初始化完成: fast_interval=%d, slow_interval=%d",
            self.fast_interval,
            self.slow_interval,
        )

    async def _check_and_cleanup_old_process(self):
        """检查并清理占用端口旧监控进程（基于端口检测，不依赖文件）."""
        try:
            import psutil

            # 🔧 关键修复：直接检查端口占用，不依赖文件记录
            # 检查默认端口5557是否被占用
            target_ports = [5555, 5556, 5557]  # 监控进程使用三个端口

            killed_any = False
            for port in target_ports:
                # 查找占用该端口进程
                for conn in psutil.net_connections(kind="inet"):
                    if conn.laddr.port == port and conn.status == "LISTEN":
                        pid = conn.pid
                        if not pid:
                            continue

                        # 检查是否是当前进程
                        current_pid = __import__("os").getpid()
                        if pid == current_pid:
                            continue

                        try:
                            proc = psutil.Process(pid)
                            cmdline = " ".join(proc.cmdline())

                            # 检查是否是监控进程
                            if "monitor_process_entry" in cmdline or "monitor_core" in cmdline:
                                logger.warning(
                                    "[清理] 发现旧监控进程占用端口%d (PID=%d)，正在终止...",
                                    port,
                                    pid,
                                )
                                proc.terminate()

                                # 等待进程退出
                                try:
                                    proc.wait(timeout=3)
                                    logger.info("[清理] ✅ 旧监控进程 (PID=%d) 已正常终止", pid)
                                    killed_any = True
                                except psutil.TimeoutExpired:
                                    logger.warning("[清理] 旧进程未响应，强制杀死...")
                                    proc.kill()
                                    logger.info("[清理] ✅ 旧监控进程 (PID=%d) 已强制终止", pid)
                                    killed_any = True
                            else:
                                logger.warning(
                                    "[清理] 端口%d被PID=%d占用，但不是监控进程: %s",
                                    port,
                                    pid,
                                    cmdline[:100],
                                )
                        except psutil.NoSuchProcess:
                            logger.debug("[清理] 进程 PID=%d 已不存在", pid)
                        except psutil.AccessDenied:
                            logger.warning("[清理] 无权限访问进程 PID=%d", pid)

                        # 只处理第一个占用进程
                        break

            # 如果杀死了进程，等待端口释放
            if killed_any:
                logger.info("[清理] 等待端口释放...")
                await asyncio.sleep(1.0)  # 等待1秒确保端口完全释放
                logger.info("[清理] ✅ 端口清理完成")
            else:
                logger.info("[清理] 未发现需要清理旧监控进程")

        except Exception as e:
            logger.error("[清理] 清理旧进程时出错: %s", e, exc_info=True)
            # 不抛出异常，继续启动流程

    async def start(self):
        """启动监控进程（异步主入口）- DEBUG入口点."""
        self.running = True
        self.loop = asyncio.get_event_loop()

        logger.info("=" * 60)
        logger.info("监控进程V2 启动")
        logger.info("=" * 60)
        logger.debug("启动监控进程")

        try:
            logger.debug("开始初始化组件（ZMQ、数据库等）")
            await self._initialize_components()
            logger.debug("组件初始化完成，开始启动协程")

            # 创建启动事件
            self.coroutine_ready_events = {
                "zmq_handler": asyncio.Event(),
                "fast_metrics": asyncio.Event(),
                "db_writer": asyncio.Event(),
                "alert_eval": asyncio.Event(),
                "parent_watcher": asyncio.Event(),
            }

            self._start_worker_threads()

            # 创建所有协程任务
            tasks = [
                asyncio.create_task(self.zmq_handler(), name="zmq_handler"),
                asyncio.create_task(self.fast_metrics_collector(), name="fast_metrics"),
                asyncio.create_task(self.db_writer_loop(), name="db_writer"),
                asyncio.create_task(self.alert_evaluator_loop(), name="alert_eval"),
                asyncio.create_task(self.parent_process_watcher(), name="parent_watcher"),
            ]

            # 等待所有协程完成初始化（最多等待5秒）
            logger.info("[INIT] 等待所有协程启动...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        *[event.wait() for event in self.coroutine_ready_events.values()]
                    ),
                    timeout=5.0,
                )
                logger.info("[INIT] ✅ 所有协程已就绪")

                # 更新就绪信号为Level 2
                try:
                    from pathlib import Path

                    signal_file = Path("logs/monitor_ready.signal")
                    if signal_file.exists():
                        with open(signal_file, "r", encoding="utf-8") as f:
                            ready_signal = json.load(f)

                        ready_signal["status"] = "fully_ready"
                        ready_signal["level"] = 2
                        ready_signal["coroutines_ready_at"] = time.time()

                        with open(signal_file, "w", encoding="utf-8") as f:
                            json.dump(ready_signal, f, ensure_ascii=False, indent=2)
                            f.flush()
                            os.fsync(f.fileno())

                        logger.info("[INIT] ✓ 就绪信号已更新（Level 2: 功能完整）")
                except Exception as e:
                    logger.warning("[INIT] 更新就绪信号失败: %s", e)

                logger.debug(
                    "所有协程已就绪: 协程数量=%d, 协程列表=%s",
                    len(tasks),
                    list(self.coroutine_ready_events.keys()),
                )

            except asyncio.TimeoutError:
                logger.error("[INIT] ❌ 协程启动超时！")
                ready = [
                    name for name, event in self.coroutine_ready_events.items() if event.is_set()
                ]
                not_ready = [
                    name
                    for name, event in self.coroutine_ready_events.items()
                    if not event.is_set()
                ]
                logger.error(f"[INIT] 已就绪: {ready}")
                logger.error(f"[INIT] 未就绪: {not_ready}")
                raise

            # ⚠️ 禁用启动时自动带宽测试（避免Ookla限流）
            # 用户可通过UI手动触发测试
            # asyncio.create_task(self._test_bandwidth_on_startup())

            # 初始化并启动延迟监控器（门户网站池，每10秒自动测试）
            logger.info("[LATENCY] 开始初始化延迟监控器...")
            await self.system_monitor.latency_monitor.initialize_servers()
            await self.system_monitor.latency_monitor.start_auto_test()
            logger.info("[LATENCY] ✅ 延迟监控器已启动")

            # 等待所有协程，return_exceptions=True 防止单个协程异常导致整个进程退出
            # 同时监控任务是否意外退出
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 检查是否有任务意外退出
            for i, result in enumerate(results):
                task_name = tasks[i].get_name()
                if isinstance(result, Exception):
                    logger.error(
                        f"[TASK-EXIT] ❌ 任务 {task_name} 异常退出: {result}", exc_info=result
                    )
                elif result is not None:
                    logger.warning(f"[TASK-EXIT] ⚠️  任务 {task_name} 意外返回: {result}")

        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")
        except Exception as e:
            logger.error("监控进程异常: %s", e, exc_info=True)
        finally:
            await self.stop()

    async def _initialize_components(self):
        """初始化组件 - DEBUG检查点."""
        logger.info("[INIT] 初始化组件...")

        # 初始化ZMQ
        self.zmq_context = zmq.asyncio.Context()
        ctx: zmq.asyncio.Context = self.zmq_context  # 为类型检查器提供非None保证

        # 读取配置（端口退避）
        try:
            from backend.core.config import get_settings

            _settings = get_settings()
            fallback_enabled = bool(getattr(_settings.monitor, "port_fallback_enabled", True))
            fallback_base = int(getattr(_settings.monitor, "port_fallback_base", 5565))
            fallback_span = int(getattr(_settings.monitor, "port_fallback_span", 3))
            bind_addr = str(getattr(_settings.monitor, "bind_addr", "127.0.0.1"))
        except Exception:
            # 配置不可用时使用默认值
            fallback_enabled = True
            fallback_base = 5565
            fallback_span = 3
            bind_addr = "127.0.0.1"

        # 🔧 新增：检查并清理占用端口旧进程
        await self._check_and_cleanup_old_process()

        # 候选端口组：优先默认，其次退避组（base, base+1, base+2）
        default_group: Tuple[int, int, int] = (5555, 5556, 5557)
        candidate_groups: List[Tuple[int, int, int]] = [default_group]
        if fallback_enabled:
            # 根据 fallback_span 生成偏移列表（至少3）
            span = max(3, int(fallback_span))
            offsets = list(range(span))
            candidate_groups.append(
                (
                    fallback_base + offsets[0],
                    fallback_base + offsets[1],
                    fallback_base + offsets[2],
                )
            )

        # 工具函数：创建同一个socket（局部变量，成功后再赋值给 self）
        def _create_socket_group() -> (
            Tuple[zmq.asyncio.Socket, zmq.asyncio.Socket, zmq.asyncio.Socket]
        ):
            push_sock = ctx.socket(zmq.PUSH)
            push_sock.setsockopt(zmq.LINGER, 0)
            pull_sock = ctx.socket(zmq.PULL)
            pull_sock.setsockopt(zmq.LINGER, 0)
            rep_sock = ctx.socket(zmq.REP)
            rep_sock.setsockopt(zmq.LINGER, 0)
            return push_sock, pull_sock, rep_sock

        # 初始化变量
        chosen_group: Optional[Tuple[int, int, int]] = None
        last_error = None

        for group in candidate_groups:
            p_push, p_pull, p_rep = group
            push_sock, pull_sock, rep_sock = _create_socket_group()
            try:
                # 严格顺序：PUSH -> PULL -> REP
                push_sock.bind(f"tcp://{bind_addr}:{p_push}")
                pull_sock.bind(f"tcp://{bind_addr}:{p_pull}")
                rep_sock.bind(f"tcp://{bind_addr}:{p_rep}")
                chosen_group = group
                # 绑定成功后再赋给实例属性
                self.push_socket = push_sock
                self.pull_socket = pull_sock
                self.rep_socket = rep_sock
                break
            except zmq.error.ZMQError as e:
                last_error = e
                logger.error(
                    "[ZMQ] 端口组绑定失败 push=%d pull=%d rep=%d: %s",
                    p_push,
                    p_pull,
                    p_rep,
                    e,
                )
                # 下一组前先清理
                try:
                    push_sock.close(linger=0)
                    pull_sock.close(linger=0)
                    rep_sock.close(linger=0)
                except Exception:
                    pass
                await asyncio.sleep(0.1)
                continue
            except Exception as e:
                last_error = e
                logger.error("[ZMQ] 端口组异常: %s", e)
                try:
                    push_sock.close(linger=0)
                    pull_sock.close(linger=0)
                    rep_sock.close(linger=0)
                except Exception:
                    pass
                await asyncio.sleep(0.1)
                continue

        if not chosen_group:
            # 未能绑定任何端口组
            if last_error:
                raise last_error
            raise RuntimeError("ZMQ端口绑定失败（未知原因）")

        # 写入生效端口文件
        try:
            import os
            from datetime import datetime as _dt

            os.makedirs("logs", exist_ok=True)
            ports_info = {
                "pid": __import__("os").getpid(),
                "timestamp": _dt.now().isoformat(),
                "alert_push": chosen_group[0],
                "status_pull": chosen_group[1],
                "query_rep": chosen_group[2],
                "bind_addr": bind_addr,
            }
            with open("logs/monitor_ports.json", "w", encoding="utf-8") as f:
                json.dump(ports_info, f, ensure_ascii=False, indent=2)
            logger.info(
                "[ZMQ] ✅ 生效端口: push=%d pull=%d rep=%d (退避启用=%s)",
                chosen_group[0],
                chosen_group[1],
                chosen_group[2],
                str(fallback_enabled),
            )
        except Exception as e:
            logger.warning("[ZMQ] 写入生效端口文件失败: %s", e)

        # 创建就绪信号文件（主进程等待此文件）
        try:
            from pathlib import Path

            ready_signal = {
                "pid": os.getpid(),
                "timestamp": time.time(),
                "status": "ports_ready",  # Level 1: 端口就绪
                "level": 1,  # 就绪级别
                "ports": {
                    "alert_push": chosen_group[0],
                    "status_pull": chosen_group[1],
                    "query_rep": chosen_group[2],
                },
                "bind_addr": bind_addr,
            }

            signal_file = Path("logs/monitor_ready.signal")
            with open(signal_file, "w", encoding="utf-8") as f:
                json.dump(ready_signal, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())  # 强制写入磁盘

            logger.info("[ZMQ] ✓ 就绪信号文件已创建（Level 1: 端口就绪）")
        except Exception as e:
            logger.warning("[ZMQ] 创建就绪信号文件失败: %s", e)

        logger.info(
            "[ZMQ] 所有socket已配置（push=%d, pull=%d, rep=%d）",
            chosen_group[0],
            chosen_group[1],
            chosen_group[2],
        )

        # ✅ 优化：在后台异步创建硬件监控器（避免阻塞主循环）
        if self.hardware_monitor is None:
            logger.info("[INIT] 开始后台初始化硬件监控器（LibreHardwareMonitor可能需要30-60秒）...")

            def _create_hardware_monitor():
                """在后台线程中创建硬件监控器"""
                import time

                start_time = time.time()
                try:
                    monitor = HardwareMonitorFactory.create_monitor()
                    elapsed = time.time() - start_time
                    logger.info("[INIT] ✅ 硬件监控器初始化完成（耗时: %.1fs）", elapsed)
                    return monitor
                except Exception as e:
                    logger.error("[INIT] ❌ 硬件监控器初始化失败: %s", e)
                    return None

            # 在后台线程池中创建（不阻塞主循环）
            loop = asyncio.get_event_loop()
            self.hardware_monitor = await loop.run_in_executor(
                self.executor, _create_hardware_monitor
            )

            if self.hardware_monitor:
                logger.info("[INIT] ✅ 硬件监控器已就绪，功能完整")
            else:
                logger.warning(
                    "[INIT] ⚠️ 硬件监控器初始化失败，系统将以降级模式运行（无硬件温度监控）"
                )

        # 初始化队列
        self.db_write_queue = asyncio.Queue()
        self.hardware_queue = asyncio.Queue()
        self.smart_queue = asyncio.Queue()
        self.smart_trigger_event = asyncio.Event()

        # 初始化自适应阈值管理器
        from backend.services.database_adapter import get_db_manager

        db_manager = get_db_manager()
        self.adaptive_threshold = AdaptiveThresholdManager(db_manager)

        # 注册监控指标
        self._register_metrics()
        self.adaptive_threshold.load_from_database()

        # 注意：监控进程日志已通过 ZMQ 告警端口 (5555) 推送到主进程
        # 不需要单独的日志代理

        logger.info("[INIT] ✅ 组件初始化完成")

    def _register_metrics(self):
        """注册监控指标."""
        if not self.adaptive_threshold:
            return

        metrics = [
            ("cpu_temp", 80.0, 90.0),
            ("gpu_temp", 85.0, 95.0),
            ("cpu_power", 95.0, 125.0),
            ("cpu_percent", 85.0, 95.0),
            ("memory_percent", 85.0, 95.0),
        ]

        for name, warning, critical in metrics:
            self.adaptive_threshold.register_metric(
                ThresholdConfig(
                    metric_name=name, default_warning=warning, default_critical=critical
                )
            )

        logger.info("[THRESHOLD] 已注册 %d 个监控指标", len(metrics))

    def _start_worker_threads(self):
        """启动工作线程."""
        logger.info("[WORKERS] 启动工作线程...")
        self.executor.submit(self._hardware_collector_thread)
        self.executor.submit(self._smart_collector_thread)
        logger.info("[WORKERS] ✅ 工作线程已启动")

    def _hardware_collector_thread(self):
        """硬件传感器采集线程 - DEBUG断点位置."""
        logger.info("[HARDWARE-THREAD] 硬件传感器采集线程启动")

        while self.running:
            try:
                start_time = time.time()

                if self.hardware_monitor:
                    if hasattr(self.hardware_monitor, "get_all_sensor_data"):
                        sensor_data = self.hardware_monitor.get_all_sensor_data()
                    else:
                        # ExtendedLHMWrapper doesn't have get_temperature_info, use get_all_sensor_data
                        sensor_data = {}
                        logger.warning("Hardware monitor doesn't have get_all_sensor_data method")

                    if self.loop and sensor_data and self.hardware_queue:
                        asyncio.run_coroutine_threadsafe(
                            self.hardware_queue.put(sensor_data), self.loop
                        )

                elapsed = time.time() - start_time
                sleep_time = max(0, self.slow_interval - elapsed)
                time.sleep(sleep_time)

            except Exception as e:
                logger.exception("[HARDWARE-THREAD] 采集失败: %s", e)
                time.sleep(self.slow_interval)

        logger.info("[HARDWARE-THREAD] 硬件传感器采集线程停止")

    def _smart_collector_thread(self):
        """SMART采集线程（事件触发模式）."""
        logger.info("[SMART-THREAD] SMART采集线程启动（按需触发模式）")

        # 启动时采集一次
        self._collect_smart_once()
        logger.info("[SMART-THREAD] 启动时SMART采集完成，进入事件等待模式")

        # 进入事件等待循环
        while self.running:
            try:
                if self.loop and self.smart_trigger_event:
                    # 等待触发事件（60秒超时仅用于检查running状态）
                    future = asyncio.run_coroutine_threadsafe(
                        asyncio.wait_for(self.smart_trigger_event.wait(), timeout=60), self.loop
                    )
                    try:
                        future.result(timeout=61)
                        if self.smart_trigger_event.is_set():
                            logger.info("[SMART] 收到触发信号，开始采集")
                            self.smart_trigger_event.clear()
                            self._collect_smart_once()
                    except Exception:
                        # 超时不是错误，继续等待
                        pass
                else:
                    time.sleep(5)
            except Exception as e:
                logger.exception("[SMART-THREAD] 错误: %s", e)
                time.sleep(5)

        logger.info("[SMART-THREAD] SMART采集线程停止")

    def _collect_smart_once(self):
        """采集一次SMART数据."""
        try:
            if not self.smart_monitor.is_available():
                logger.warning("[SMART] pySMART不可用")
                return

            logger.info("[SMART] 开始采集SMART数据...")
            start_time = time.time()
            smart_data = self.smart_monitor.get_smart_data()
            elapsed = time.time() - start_time
            logger.info("[SMART] ✅ 采集完成，耗时%.2fs，%d个硬盘", elapsed, len(smart_data))

            if self.loop and smart_data and self.smart_queue:
                asyncio.run_coroutine_threadsafe(self.smart_queue.put(smart_data), self.loop)
        except Exception as e:
            logger.exception("[SMART] 采集失败: %s", e)

    async def zmq_handler(self):
        """ZMQ通信处理."""
        logger.info("[ZMQ] 通信处理协程启动")

        # 先标记协程已就绪（在任何可能阻塞的操作之前）
        if "zmq_handler" in self.coroutine_ready_events:
            self.coroutine_ready_events["zmq_handler"].set()
            logger.info("[ZMQ] ✅ 协程就绪")

        try:
            # 在协程外部创建Poller（只创建一次）
            logger.debug("[ZMQ] 创建Poller...")
            poller = zmq.asyncio.Poller()
            logger.debug("[ZMQ] 注册rep_socket...")
            poller.register(self.rep_socket, zmq.POLLIN)
            logger.debug("[ZMQ] 注册pull_socket...")
            poller.register(self.pull_socket, zmq.POLLIN)
            logger.debug("[ZMQ] Poller初始化完成")

            logger.info("[ZMQ] 开始主循环（self.running=%s）", self.running)
            while self.running:
                try:
                    logger.debug("[ZMQ] 等待poll...")
                    socks = dict(await poller.poll(timeout=100))
                    logger.debug("[ZMQ] poll返回: %d个socket", len(socks))

                    if self.rep_socket in socks:
                        await self._handle_query_request()
                    if self.pull_socket in socks:
                        await self._handle_service_status()

                except Exception as e:
                    logger.error("[ZMQ] 处理错误: %s", e, exc_info=True)
                    await asyncio.sleep(0.1)

            logger.warning("[ZMQ] ⚠️  while循环退出（self.running=%s）", self.running)

        except Exception as e:
            logger.error("[ZMQ] ❌ 协程异常退出: %s", e, exc_info=True)
        finally:
            logger.info("[ZMQ] 通信处理协程停止")

    async def _handle_query_request(self):
        """处理查询请求."""
        if not self.rep_socket:
            return

        try:
            request = await self.rep_socket.recv_json()
            action = request.get("action", "get_data")

            if action == "get_data":
                # 构建响应，包含动态阈值数据和并发任务数
                response = {"timestamp": datetime.now().isoformat(), **self.monitoring_data}
                if self.adaptive_threshold:
                    response["thresholds"] = self.adaptive_threshold.get_all_thresholds()
                # 添加并发任务数
                try:
                    concurrent_tasks = self.business_metrics_collector.get_concurrent_tasks()
                    response["concurrent_tasks"] = concurrent_tasks
                except Exception:
                    response["concurrent_tasks"] = {
                        "download": 0,
                        "backtest": 0,
                        "trading": 0,
                        "total": 0,
                    }
                await self.rep_socket.send_json(response)
            elif action == "trigger_smart":
                if self.smart_trigger_event:
                    self.smart_trigger_event.set()
                await self.rep_socket.send_json({"status": "success"})
            elif action == "test_bandwidth_full":
                # 手动触发完整带宽测试（后台任务模式，避免阻塞REP socket）
                try:
                    # 检查是否已有测试在运行
                    if self._background_bandwidth_task and not self._background_bandwidth_task.done():
                        logger.warning("[BANDWIDTH] 测试已在运行中，拒绝新请求")
                        await self.rep_socket.send_json({
                            "status": "testing",
                            "message": "带宽测试正在进行中，请稍后查询结果"
                        })
                    else:
                        # 创建后台任务（不await）
                        self._background_bandwidth_task = asyncio.create_task(
                            self.system_monitor.bandwidth_monitor.test_bandwidth_full_async()
                        )
                        logger.info("[ZMQ] ✅ 带宽测试后台任务已启动（不阻塞REP socket）")
                        await self.rep_socket.send_json({
                            "status": "started",
                            "message": "带宽测试已启动，预计30-60秒完成，请通过get_bandwidth查询结果"
                        })

                        # 添加任务完成回调（用于日志）
                        def on_bandwidth_done(task):
                            try:
                                result = task.result()
                                if result:
                                    logger.info(f"[ZMQ] ✅ 带宽测试后台任务完成：{result}")
                                else:
                                    logger.warning(f"[ZMQ] ⚠️ 带宽测试后台任务返回None")
                            except Exception as e:
                                logger.error(f"[ZMQ] ❌ 带宽测试后台任务异常：{e}", exc_info=True)

                        self._background_bandwidth_task.add_done_callback(on_bandwidth_done)

                except Exception as e:
                    logger.error(f"[ZMQ] 启动带宽测试失败：{e}", exc_info=True)
                    await self.rep_socket.send_json({"status": "error", "message": str(e)})
            elif action == "retry_latency":
                # 重新初始化延迟监控器（用于重试按钮）
                try:
                    logger.info("[ZMQ] 收到延迟监控重试请求")
                    await self.system_monitor.latency_monitor.retry_initialize()
                    await self.rep_socket.send_json({
                        "status": "success",
                        "message": "延迟监控器已重新初始化"
                    })
                except Exception as e:
                    logger.error(f"[ZMQ] 重试延迟监控失败：{e}", exc_info=True)
                    await self.rep_socket.send_json({"status": "error", "message": str(e)})
            elif action == "get_bandwidth":
                # 获取最新带宽结果（包含完整测试和延迟测试）
                try:
                    result = self.system_monitor.get_bandwidth_info()
                    logger.debug(f"[ZMQ] get_bandwidth返回：{result}")
                    await self.rep_socket.send_json({"status": "success", "data": result})
                except Exception as e:
                    logger.error(f"[ZMQ] get_bandwidth失败：{e}", exc_info=True)
                    await self.rep_socket.send_json({"status": "error", "message": str(e)})
            elif action == "get_all":
                # 获取所有监控数据（包含带宽信息）
                try:
                    response = {
                        "status": "success",
                        "data": {
                            "system": self.monitoring_data.get("system", {}),
                            "hardware": self.monitoring_data.get("hardware", {}),
                            "process": self.monitoring_data.get("process", {}),
                            "bandwidth": self.system_monitor.get_bandwidth_info(),
                        },
                    }
                    await self.rep_socket.send_json(response)
                except Exception as e:
                    await self.rep_socket.send_json({"status": "error", "message": str(e)})
            else:
                await self.rep_socket.send_json({"error": f"Unknown action: {action}"})
        except Exception as e:
            logger.error("[ZMQ] 处理查询失败: %s", e)
            try:
                await self.rep_socket.send_json({"error": str(e)})
            except Exception:
                pass

    async def _handle_service_status(self):
        """处理服务状态推送."""
        if not self.pull_socket:
            return

        try:
            status = await self.pull_socket.recv_json()
            self.monitoring_data["service"] = status
            logger.debug("[ZMQ] 收到服务状态更新")
        except Exception as e:
            logger.exception("[ZMQ] 接收服务状态失败: %s", e)

    async def fast_metrics_collector(self):
        """快速指标采集 - DEBUG断点位置."""
        logger.info("[FAST-METRICS] 快速指标采集协程启动")

        # 标记协程已就绪
        if "fast_metrics" in self.coroutine_ready_events:
            self.coroutine_ready_events["fast_metrics"].set()
            logger.info("[FAST-METRICS] ✅ 协程就绪")

        try:
            logger.info("[FAST-METRICS] 开始主循环（self.running=%s）", self.running)
            while self.running:
                try:
                    start_time = time.time()

                    # 采集系统指标 - 异步
                    t1 = time.time()
                    logger.debug("[FAST-METRICS] 开始采集系统指标...")
                    system_metrics = await self._collect_system_metrics()
                    logger.debug("[FAST-METRICS] 系统指标采集完成")
                    self.monitoring_data["system"] = system_metrics
                    # logger.debug("[PERF] 系统指标采集耗时: %.3fs", time.time() - t1)  # 🔧 已优化：降低输出频率

                    # 学习基线
                    if self.adaptive_threshold:
                        self.adaptive_threshold.learn_baseline(
                            "cpu_percent", system_metrics.get("cpu_percent", 0)
                        )
                        self.adaptive_threshold.learn_baseline(
                            "memory_percent", system_metrics.get("memory_percent", 0)
                        )

                    # 采集进程监控 - 异步
                    t2 = time.time()
                    process_metrics = await self._collect_process_metrics()
                    self.monitoring_data["process"] = process_metrics
                    # logger.debug("[PERF] 进程指标采集耗时: %.3fs", time.time() - t2)  # 🔧 已优化：降低输出频率

                    # 检查硬件队列
                    if self.hardware_queue and not self.hardware_queue.empty():
                        hardware_data = await self.hardware_queue.get()
                        self.monitoring_data["hardware"] = hardware_data
                        self._learn_hardware_baselines(hardware_data)

                    # 检查SMART队列
                    if self.smart_queue and not self.smart_queue.empty():
                        smart_data = await self.smart_queue.get()
                        self.monitoring_data["smart"] = self._serialize_smart_data(smart_data)

                    # 新增：执行瓶颈分析和场景分析
                    t3 = time.time()
                    analysis_result = await self._perform_analysis()
                    self.monitoring_data["analysis"] = analysis_result
                    # logger.debug("[PERF] 瓶颈分析耗时: %.3fs", time.time() - t3)  # 🔧 已优化：降低输出频率

                    # 将数据加入数据库写入队列
                    await self._queue_for_database()

                    # 总耗时统计
                    total_time = time.time() - start_time
                    # logger.debug("[PERF] 总采集耗时: %.3fs", total_time)  # 🔧 已优化：降低输出频率

                    elapsed = time.time() - start_time
                    sleep_time = max(0, self.fast_interval - elapsed)
                    await asyncio.sleep(sleep_time)

                except Exception as e:
                    logger.error("[FAST-METRICS] 采集失败: %s", e, exc_info=True)
                    await asyncio.sleep(self.fast_interval)

            logger.warning("[FAST-METRICS] ⚠️  while循环退出（self.running=%s）", self.running)

        except Exception as e:
            logger.error("[FAST-METRICS] ❌ 协程异常退出: %s", e, exc_info=True)
        finally:
            logger.info("[FAST-METRICS] 快速指标采集协程停止")

    async def _collect_system_metrics(self) -> Dict[str, Any]:
        """采集系统指标（异步版本）。"""
        try:
            # 在executor中执行阻塞psutil调用
            loop = asyncio.get_event_loop()
            resource_usage = await loop.run_in_executor(
                self.executor, self.system_monitor.get_resource_usage
            )

            # 并发执行IO速度采集（都是async方法）
            disk_io_speed, network_speed = await asyncio.gather(
                self.system_monitor.get_disk_io_speed_async(),
                self.system_monitor.get_network_speed_async(),
            )

            # 在executor中采集新增子系统指标（避免阻塞事件循环）
            cpu_os_detailed, cpu_info, memory_subsystem, storage_subsystem, network_subsystem = (
                await asyncio.gather(
                    loop.run_in_executor(self.executor, self.system_monitor.get_cpu_os_detailed),
                    loop.run_in_executor(self.executor, self.system_monitor.get_cpu_info),
                    loop.run_in_executor(
                        self.executor, self.system_monitor.get_memory_subsystem_metrics
                    ),
                    loop.run_in_executor(
                        self.executor, self.system_monitor.get_storage_subsystem_metrics
                    ),
                    loop.run_in_executor(
                        self.executor, self.system_monitor.get_network_subsystem_metrics
                    ),
                )
            )

            # 合并 cpu_os_detailed 和 cpu_info 为完整的 cpu_detailed
            cpu_detailed = {**cpu_os_detailed, **cpu_info}

            # 诊断日志：确认 cpu_frequency 数据采集成功
            if "cpu_frequency" in cpu_detailed:
                freq = cpu_detailed["cpu_frequency"]
                if freq.get("max", 0) > 0:
                    logger.debug(
                        f"[CPU频率] current={freq.get('current', 0):.0f}MHz, "
                        f"max={freq.get('max', 0):.0f}MHz, "
                        f"ratio={freq.get('current', 0) / freq.get('max', 1) * 100:.1f}%"
                    )

            return {
                "timestamp": datetime.now().isoformat(),
                "cpu_percent": resource_usage.cpu_percent,
                "memory_percent": resource_usage.memory_percent,
                "disk_percent": resource_usage.disk_percent,
                "network_sent": resource_usage.network_sent,
                "network_recv": resource_usage.network_recv,
                "process_count": resource_usage.process_count,
                "load_average": resource_usage.load_average,
                "disk_io_speed": disk_io_speed,
                "network_speed": network_speed,
                "cpu_detailed": cpu_detailed,
                "memory_subsystem": memory_subsystem,
                "storage_subsystem": storage_subsystem,
                "network_subsystem": network_subsystem,
            }
        except Exception as e:
            logger.error("采集系统指标失败: %s", e)
            return {}

    async def _collect_process_metrics(self) -> Dict[str, Any]:
        """采集进程指标（异步版本）."""
        try:
            # 在executor中执行阻塞进程识别
            loop = asyncio.get_event_loop()
            all_processes = await loop.run_in_executor(
                self.executor, self.process_monitor.identify_processes
            )

            python_processes = [
                p
                for p in all_processes
                if p.get("type") in ["python", "trading", "download", "backtest"]
            ]

            bottlenecks = []
            for proc in python_processes[:5]:
                try:
                    # 在executor中执行阻塞进程指标获取
                    metrics = await loop.run_in_executor(
                        self.executor,
                        self.process_monitor.get_process_metrics,
                        proc.get("id", ""),
                        proc.get("name", ""),
                        proc.get("type", ""),
                    )
                    if metrics:
                        result = self.process_bottleneck_analyzer.find_bottleneck(metrics)
                        if result.has_bottleneck:
                            bottlenecks.append(
                                {
                                    "pid": proc.get("id"),
                                    "name": proc.get("name"),
                                    "type": result.bottleneck,
                                    "info": result.details,
                                }
                            )
                except Exception:
                    pass

            return {
                "timestamp": datetime.now().isoformat(),
                "python_processes": python_processes[:10],
                "bottlenecks": bottlenecks,
                "process_count": len(python_processes),
            }
        except Exception as e:
            logger.exception("采集进程指标失败: %s", e)
            return {}

    async def _perform_analysis(self) -> Dict[str, Any]:
        """执行瓶颈分析和场景分析.

        Returns:
            {
                "bottleneck": {
                    "total_score": 75,
                    "bottleneck_dimension": "disk_io",
                    "scores": {...},
                    "suggestions": [...]
                },
                "scenario": {
                    "scenario": "data_download",
                    "scenario_name": "数据下载",
                    "bottleneck_metrics": [...],
                    "optimization_hints": [...]
                }
            }
        """
        try:
            loop = asyncio.get_event_loop()

            # 在executor中执行分析（避免阻塞事件循环）
            bottleneck_result, scenario_result = await asyncio.gather(
                loop.run_in_executor(
                    self.executor,
                    self.system_bottleneck_analyzer.analyze,
                    self.monitoring_data,
                ),
                loop.run_in_executor(
                    self.executor,
                    self._analyze_scenario_wrapper,
                ),
            )

            return {
                "bottleneck": bottleneck_result,
                "scenario": scenario_result,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error("执行分析失败: %s", e, exc_info=True)
            return {
                "bottleneck": {},
                "scenario": {},
                "error": str(e),
            }

    def _analyze_scenario_wrapper(self) -> Dict[str, Any]:
        """场景分析包装器（用于executor执行）."""
        try:
            # 检测当前场景
            process_data = self.monitoring_data.get("process", {}).get("python_processes", [])
            current_scenario = self.scenario_analyzer.detect_scenario(process_data)

            # 分析场景
            scenario_result = self.scenario_analyzer.analyze_scenario(
                current_scenario, self.monitoring_data
            )

            return scenario_result
        except Exception as e:
            logger.error("场景分析失败: %s", e)
            return {
                "scenario": "unknown",
                "error": str(e),
            }

    def _learn_hardware_baselines(self, hardware_data: Dict[str, Dict]):
        """学习硬件指标基线."""
        if not self.adaptive_threshold:
            return

        try:
            # CPU温度
            if "temperature" in hardware_data:
                for device, sensors in hardware_data["temperature"].items():
                    if "CPU" in device or "processor" in device.lower():
                        if sensors and len(sensors) > 0:
                            cpu_temp = sensors[0].get("current")
                            if cpu_temp:
                                self.adaptive_threshold.learn_baseline("cpu_temp", cpu_temp)
                                break

            # GPU温度
            if "temperature" in hardware_data:
                for device, sensors in hardware_data["temperature"].items():
                    if "GPU" in device or "NVIDIA" in device or "AMD" in device:
                        if sensors and len(sensors) > 0:
                            gpu_temp = sensors[0].get("current")
                            if gpu_temp:
                                self.adaptive_threshold.learn_baseline("gpu_temp", gpu_temp)
                                break

            # CPU功耗
            if "power" in hardware_data:
                for device, sensors in hardware_data["power"].items():
                    if "CPU" in device or "Package" in device:
                        if sensors and len(sensors) > 0:
                            cpu_power = sensors[0].get("current")
                            if cpu_power:
                                self.adaptive_threshold.learn_baseline("cpu_power", cpu_power)
                                break
        except Exception as e:
            logger.debug("学习硬件基线失败: %s", e)

    def _serialize_smart_data(self, smart_data: Dict) -> Dict[str, Any]:
        """序列化SMART数据."""
        result = {}
        for disk_name, data in smart_data.items():
            result[disk_name] = {
                "model": data.model,
                "serial": data.serial,
                "capacity": data.capacity,
                "assessment": data.assessment,
                "temperature": data.temperature,
                "power_on_hours": data.power_on_hours,
                # 🔧 修复：二次防御，确保None值转换为0
                "reallocated_sectors": (
                    data.reallocated_sectors if data.reallocated_sectors is not None else 0
                ),
                "pending_sectors": data.pending_sectors if data.pending_sectors is not None else 0,
                "uncorrectable_errors": (
                    data.uncorrectable_errors if data.uncorrectable_errors is not None else 0
                ),
                "timestamp": data.timestamp.isoformat(),
            }
        return result

    async def _queue_for_database(self):
        """将监控数据加入数据库写入队列."""
        try:
            if not hasattr(self, "_db_save_counter"):
                self._db_save_counter = 0

            self._db_save_counter += 1

            if self._db_save_counter >= 5:
                self._db_save_counter = 0

                records = []
                timestamp = datetime.now()

                system_data = self.monitoring_data.get("system", {})
                if system_data:
                    records.append(
                        {
                            "timestamp": timestamp,
                            "metric_type": "system",
                            "metric_name": "cpu_percent",
                            "value": system_data.get("cpu_percent", 0),
                            "unit": "%",
                        }
                    )
                    records.append(
                        {
                            "timestamp": timestamp,
                            "metric_type": "system",
                            "metric_name": "memory_percent",
                            "value": system_data.get("memory_percent", 0),
                            "unit": "%",
                        }
                    )

                hardware_data = self.monitoring_data.get("hardware", {})
                if hardware_data:
                    temp_data = hardware_data.get("temperature", {})
                    for device, sensors in temp_data.items():
                        if "CPU" in device and sensors:
                            records.append(
                                {
                                    "timestamp": timestamp,
                                    "metric_type": "hardware",
                                    "metric_name": "cpu_temp",
                                    "value": sensors[0].get("current", 0),
                                    "unit": "°C",
                                    "metadata": json.dumps({"device": device}),
                                }
                            )
                            break

                    power_data = hardware_data.get("power", {})
                    for device, sensors in power_data.items():
                        if "CPU" in device and sensors:
                            records.append(
                                {
                                    "timestamp": timestamp,
                                    "metric_type": "hardware",
                                    "metric_name": "cpu_power",
                                    "value": sensors[0].get("current", 0),
                                    "unit": "W",
                                    "metadata": json.dumps({"device": device}),
                                }
                            )
                            break

                if self.db_write_queue:
                    for record in records:
                        await self.db_write_queue.put(record)

        except Exception as e:
            logger.exception("加入数据库队列失败: %s", e)

    async def db_writer_loop(self):
        """数据库写入循环."""
        logger.info("[DB-WRITER] 数据库写入协程启动")

        # 标记协程已就绪
        if "db_writer" in self.coroutine_ready_events:
            self.coroutine_ready_events["db_writer"].set()
            logger.info("[DB-WRITER] ✅ 协程就绪")

        try:
            batch = []
            batch_size = 100
            flush_interval = 300
            last_flush_time = time.time()

            while self.running:
                try:
                    if not self.db_write_queue:
                        await asyncio.sleep(1)
                        continue

                    try:
                        item = await asyncio.wait_for(self.db_write_queue.get(), timeout=5)
                        batch.append(item)
                    except asyncio.TimeoutError:
                        pass

                    current_time = time.time()
                    should_flush = len(batch) >= batch_size or (
                        batch and current_time - last_flush_time >= flush_interval
                    )

                    if should_flush:
                        await self._flush_to_database(batch)
                        batch.clear()
                        last_flush_time = current_time

                except Exception as e:
                    logger.exception("[DB-WRITER] 错误: %s", e)
                    await asyncio.sleep(1)

            if batch:
                await self._flush_to_database(batch)

        except Exception as e:
            logger.error("[DB-WRITER] ❌ 协程异常退出: %s", e, exc_info=True)
        finally:
            logger.info("[DB-WRITER] 数据库写入协程停止")

    async def _flush_to_database(self, batch: List[Dict]):
        """批量写入数据库."""
        if not batch:
            return

        try:
            from backend.services.database_adapter import get_db_manager

            db_manager = get_db_manager()

            for record in batch:
                db_manager.execute_update(
                    """INSERT INTO monitoring_history
                    (timestamp, metric_type, metric_name, value, unit, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        record["timestamp"].isoformat(),
                        record["metric_type"],
                        record["metric_name"],
                        record["value"],
                        record.get("unit", ""),
                        record.get("metadata", ""),
                    ),
                )

            logger.info("[DB-WRITER] ✅ 批量写入 %d 条记录", len(batch))

        except Exception as e:
            logger.error("[DB-WRITER] 批量写入失败: %s", e)

    async def alert_evaluator_loop(self):
        """告警评估循环 - DEBUG断点位置."""
        logger.info("[ALERT-EVAL] 告警评估协程启动")

        # 标记协程已就绪
        if "alert_eval" in self.coroutine_ready_events:
            self.coroutine_ready_events["alert_eval"].set()
            logger.info("[ALERT-EVAL] ✅ 协程就绪")

        try:
            while self.running:
                try:
                    await asyncio.sleep(self.fast_interval)
                    alerts = await self._evaluate_alerts()
                    for alert in alerts:
                        await self._push_alert(alert)
                except Exception as e:
                    logger.exception("[ALERT-EVAL] 评估失败: %s", e)
                    await asyncio.sleep(self.fast_interval)

        except Exception as e:
            logger.error("[ALERT-EVAL] ❌ 协程异常退出: %s", e, exc_info=True)
        finally:
            logger.info("[ALERT-EVAL] 告警评估协程停止")

    async def parent_process_watcher(self):
        """监控父进程是否存活，防止成为孤儿进程."""
        logger.info("[PARENT-WATCHER] 父进程监控协程启动")

        # 标记协程已就绪
        if "parent_watcher" in self.coroutine_ready_events:
            self.coroutine_ready_events["parent_watcher"].set()
            logger.info("[PARENT-WATCHER] ✅ 协程就绪")

        import psutil

        try:
            while self.running:
                try:
                    # 每10秒检查一次父进程
                    await asyncio.sleep(10)

                    # 检查父进程是否存在
                    if not psutil.pid_exists(self.parent_pid):
                        logger.error(
                            "[PARENT-WATCHER] ❌ 父进程(PID:%d)已死亡，监控进程即将退出...",
                            self.parent_pid,
                        )
                        # 父进程已死，主动退出以避免成为孤儿进程
                        self.running = False
                        break

                    # 额外验证：检查父进程是否是预期进程
                    try:
                        parent = psutil.Process(self.parent_pid)
                        if not parent.is_running():
                            logger.error(
                                "[PARENT-WATCHER] ❌ 父进程(PID:%d)已停止运行，监控进程即将退出...",
                                self.parent_pid,
                            )
                            self.running = False
                            break
                    except psutil.NoSuchProcess:
                        logger.error(
                            "[PARENT-WATCHER] ❌ 父进程(PID:%d)不存在，监控进程即将退出...",
                            self.parent_pid,
                        )
                        self.running = False
                        break

                except Exception as e:
                    logger.error("[PARENT-WATCHER] 检查失败: %s", e)
                    await asyncio.sleep(10)

        except Exception as e:
            logger.error("[PARENT-WATCHER] ❌ 协程异常退出: %s", e, exc_info=True)
        finally:
            logger.info("[PARENT-WATCHER] 父进程监控协程停止")

    async def _test_bandwidth_on_startup(self):
        """启动时测试完整带宽（延迟5秒后执行）

        注意：已禁用，避免启动时网络请求过多
        """
        await asyncio.sleep(5)
        try:
            result = await self.system_monitor.bandwidth_monitor.test_bandwidth_full_async()
            if result:
                logger.info(
                    f"启动带宽测试完成: 下载 {result['download_mbps']:.2f}Mbps, "
                    f"延迟 {result['ping_ms']:.2f}ms"
                )
        except Exception as e:
            logger.warning(f"启动带宽测试失败: {e}")

    async def _evaluate_alerts(self) -> List[Dict[str, Any]]:
        """评估告警规则 - DEBUG核心逻辑."""
        alerts = []

        if not self.adaptive_threshold:
            return alerts

        try:
            system_data = self.monitoring_data.get("system", {})
            hardware_data = self.monitoring_data.get("hardware", {})

            # CPU使用率告警
            cpu_percent = system_data.get("cpu_percent")
            if cpu_percent:
                warning_threshold = self.adaptive_threshold.get_threshold("cpu_percent", "warning")
                critical_threshold = self.adaptive_threshold.get_threshold(
                    "cpu_percent", "critical"
                )

                if critical_threshold and cpu_percent >= critical_threshold:
                    alerts.append(
                        self._create_alert(
                            "cpu_percent_critical",
                            "critical",
                            f"CPU使用率严重过高: {cpu_percent:.1f}%",
                            {"cpu_percent": cpu_percent, "threshold": critical_threshold},
                        )
                    )
                elif warning_threshold and cpu_percent >= warning_threshold:
                    alerts.append(
                        self._create_alert(
                            "cpu_percent_warning",
                            "warning",
                            f"CPU使用率过高: {cpu_percent:.1f}%",
                            {"cpu_percent": cpu_percent, "threshold": warning_threshold},
                        )
                    )

            # CPU温度告警
            temp_data = hardware_data.get("temperature", {})
            for device, sensors in temp_data.items():
                if "CPU" in device and sensors:
                    cpu_temp = sensors[0].get("current")
                    if cpu_temp:
                        warning_threshold = self.adaptive_threshold.get_threshold(
                            "cpu_temp", "warning"
                        )
                        critical_threshold = self.adaptive_threshold.get_threshold(
                            "cpu_temp", "critical"
                        )

                        if critical_threshold and cpu_temp >= critical_threshold:
                            alerts.append(
                                self._create_alert(
                                    "cpu_temp_critical",
                                    "critical",
                                    f"CPU温度严重过高: {cpu_temp:.1f}°C",
                                    {
                                        "cpu_temp": cpu_temp,
                                        "threshold": critical_threshold,
                                        "device": device,
                                    },
                                )
                            )
                        elif warning_threshold and cpu_temp >= warning_threshold:
                            alerts.append(
                                self._create_alert(
                                    "cpu_temp_warning",
                                    "warning",
                                    f"CPU温度过高: {cpu_temp:.1f}°C",
                                    {
                                        "cpu_temp": cpu_temp,
                                        "threshold": warning_threshold,
                                        "device": device,
                                    },
                                )
                            )
                    break

            # 风扇停转告警
            fan_data = hardware_data.get("fan", {})
            for device, sensors in fan_data.items():
                for sensor in sensors:
                    rpm = sensor.get("current", 0)
                    if "CPU" in sensor.get("label", "") and rpm < 500:
                        cpu_temp = None
                        for dev, temp_sensors in temp_data.items():
                            if "CPU" in dev and temp_sensors:
                                cpu_temp = temp_sensors[0].get("current")
                                break

                        if cpu_temp and cpu_temp > 50:
                            alerts.append(
                                self._create_alert(
                                    "fan_stopped_critical",
                                    "critical",
                                    f"散热风扇停转: {sensor.get('label')} (CPU温度: {cpu_temp:.1f}°C)",
                                    {"fan_rpm": rpm, "cpu_temp": cpu_temp, "device": device},
                                )
                            )

        except Exception as e:
            logger.error("评估告警失败: %s", e)

        return alerts

    def _create_alert(
        self, rule_id: str, severity: str, message: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建告警对象."""
        return {
            "type": "alert",
            "alert_id": f"{rule_id}_{int(time.time())}",
            "rule_id": rule_id,
            "severity": severity,
            "message": message,
            "context": context,
            "timestamp": datetime.now().isoformat(),
        }

    async def _push_alert(self, alert: Dict[str, Any]):
        """推送告警将主进程."""
        if not self.push_socket:
            return

        try:
            await self.push_socket.send_json(alert)
            logger.info("[ALERT] 推送告警: %s", alert["message"])
        except Exception as e:
            logger.exception("[ALERT] 推送失败: %s", e)

    async def stop(self):
        """停止监控进程."""
        logger.info("正在停止监控进程...")
        self.running = False

        # 先关闭socket，再关闭context
        if self.push_socket:
            try:
                self.push_socket.close(linger=0)
            except Exception as e:
                logger.debug("关闭push_socket异常: %s", e)

        if self.rep_socket:
            try:
                self.rep_socket.close(linger=0)
            except Exception as e:
                logger.debug("关闭rep_socket异常: %s", e)

        if self.pull_socket:
            try:
                self.pull_socket.close(linger=0)
            except Exception as e:
                logger.debug("关闭pull_socket异常: %s", e)

        if self.zmq_context:
            try:
                self.zmq_context.term()
            except Exception as e:
                logger.debug("关闭zmq_context异常: %s", e)

        # 等待线程池关闭
        try:
            self.executor.shutdown(wait=True)
        except Exception as e:
            logger.debug("关闭executor异常: %s", e)

        if self.hardware_monitor and hasattr(self.hardware_monitor, "close"):
            try:
                self.hardware_monitor.close()
            except Exception as e:
                logger.debug("关闭hardware_monitor异常: %s", e)

        logger.info("监控进程已停止")


# =============================================================================
# Part 7-10: 系统/进程监控和业务指标（来自 monitors.py）
# =============================================================================

# 常量定义
# =============================================================================


class DiskType:
    """磁盘类型常量."""

    HDD = "hdd"
    SSD = "ssd"
    NVME = "nvme"
    UNKNOWN = "unknown"


# 磁盘类型对应I/O阈值 (KB/s)
DISK_THRESHOLDS = {
    DiskType.HDD: {"read": 100000, "write": 80000},  # 100 MB/s, 80 MB/s
    DiskType.SSD: {"read": 400000, "write": 300000},  # 400 MB/s, 300 MB/s
    DiskType.NVME: {"read": 2000000, "write": 1500000},  # 2000 MB/s, 1500 MB/s
    DiskType.UNKNOWN: {"read": 400000, "write": 300000},  # 默认使用SSD阈值
}


# =============================================================================
# 数据类定义
# =============================================================================


@dataclass
class SystemInfo:
    """系统信息."""

    platform: str
    platform_version: str
    architecture: str
    hostname: str
    cpu_count: int
    cpu_count_logical: int
    memory_total: int
    disk_total: int
    network_interfaces: List[str]
    boot_time: datetime


@dataclass
class ResourceUsage:
    """资源使用情况."""

    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_sent: int
    network_recv: int
    process_count: int
    load_average: List[float]
    timestamp: datetime


@dataclass
class ProcessMetrics:
    """进程指标数据类."""

    process_id: str  # 进程/线程标识
    process_name: str  # 进程/线程名称
    process_type: str  # 进程类型: download | data_io | backtest | trading | unknown
    status: str  # 状态: running | idle | stopped
    cpu_percent: float  # CPU使用率 (%)
    memory_mb: float  # 内存占用 (MB)
    memory_percent: float  # 内存使用率 (%)
    disk_read_mbps: float  # 磁盘读取速度 (MB/s)
    disk_write_mbps: float  # 磁盘写入速度 (MB/s)
    network_recv_mbps: float  # 网络接收速度 (MB/s)
    network_send_mbps: float  # 网络发送速度 (MB/s)
    timestamp: datetime  # 采集时间


@dataclass
class BottleneckResult:
    """瓶颈分析结果."""

    process_id: str
    process_name: str
    process_type: str
    bottleneck: str  # cpu | memory | disk_io | network | balanced
    bottleneck_percent: float  # 瓶颈项使用率
    details: str  # 详细描述
    suggestion: str  # 优化建议
    metrics: ProcessMetrics  # 原始指标数据

    @property
    def has_bottleneck(self) -> bool:
        """是否存在瓶颈."""
        return self.bottleneck != "balanced"


# Protocol定义（用于类型检查）
if HAS_PSUTIL:

    class DiskIOCounters(Protocol):
        """磁盘IO计数器协议."""

        read_bytes: int
        write_bytes: int

    class NetIOCounters(Protocol):
        """网络IO计数器协议."""

        bytes_recv: int
        bytes_sent: int


# =============================================================================
# 系统监控器
# =============================================================================


# =============================================================================
# 运营商带宽监控器
# =============================================================================


class BandwidthMonitor:
    """网络带宽监控器（基于自研测速方案）

    使用公共测速站点进行延迟和下载速度测试，无需第三方测速库。
    支持用户自定义配置测速服务器，无限流风险。
    """

    def __init__(self):
        """初始化带宽监控器（仅负责带宽测试，延迟测试已分离到LatencyMonitor）"""
        self._last_full_result: Optional[Dict[str, Any]] = None
        self._full_test_time: Optional[datetime] = None
        self._testing = False
        self._last_error: str = ""

        # 测速策略配置（仅带宽测试相关）
        self._bandwidth_timeout: int = 10
        self._bandwidth_max_retries: int = 3

        # 加载测速服务器配置
        self._server_configs: List[Dict[str, Any]] = []
        self._load_server_config()

        logger.info("[BANDWIDTH-INIT] 带宽监控器初始化完成（自研测速方案）")

    def _load_server_config(self):
        """加载测速服务器配置（仅加载国内服务器）"""
        import os
        import yaml

        config_file = "backend/infrastructure/system_vnpy/config/speedtest_servers.yaml"

        try:
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)

                # 确保config是字典类型
                if not isinstance(config, dict):
                    logger.warning(f"[BANDWIDTH-CONFIG] 配置文件格式错误，使用默认配置")
                    self._use_default_config()
                    return

                # 加载默认服务器（仅加载category='domestic'的服务器）
                servers = config.get('servers', []) or []
                enabled_servers = [
                    s for s in servers
                    if isinstance(s, dict)
                    and s.get('enabled', True)
                    and s.get('category') == 'domestic'
                ]

                # 加载用户自定义服务器（仅加载category='domestic'的服务器）
                custom_servers = config.get('custom_servers', []) or []
                enabled_custom = [
                    s for s in custom_servers
                    if isinstance(s, dict)
                    and s.get('enabled', True)
                    and s.get('category') == 'domestic'
                ]

                self._server_configs = enabled_servers + enabled_custom

                # 加载策略配置（仅带宽测试相关）
                strategy = config.get('strategy', {}) or {}
                if isinstance(strategy, dict):
                    self._bandwidth_timeout = strategy.get('bandwidth_timeout', 10)
                    self._bandwidth_max_retries = strategy.get('bandwidth_max_retries', 3)

                logger.info(f"[BANDWIDTH-CONFIG] 加载 {len(self._server_configs)} 个国内测速服务器")
                for i, server in enumerate(self._server_configs[:3], 1):
                    logger.info(f"  [{i}] {server.get('name')} - {server.get('category')}")
                logger.info(
                    f"[BANDWIDTH-CONFIG] 策略配置: "
                    f"带宽测试(超时={self._bandwidth_timeout}秒, 重试={self._bandwidth_max_retries}次)"
                )
            else:
                logger.warning(f"[BANDWIDTH-CONFIG] 配置文件不存在: {config_file}，使用默认配置")
                self._use_default_config()

        except Exception as e:
            logger.error(f"[BANDWIDTH-CONFIG] 加载配置失败: {e}，使用默认配置")
            self._use_default_config()

    def _use_default_config(self):
        """使用默认配置（当配置文件不存在或加载失败时，仅使用国内服务器）"""
        self._server_configs = [
            {
                'name': '阿里云镜像站',
                'category': 'domestic',
                'ping_url': 'https://mirrors.aliyun.com',
                'download_url': 'https://mirrors.aliyun.com/alpine/v3.19/releases/x86_64/alpine-standard-3.19.1-x86_64.iso',
                'timeout': 10,
                'enabled': True
            },
            {
                'name': '腾讯云镜像站',
                'category': 'domestic',
                'ping_url': 'https://mirrors.cloud.tencent.com',
                'download_url': 'https://mirrors.cloud.tencent.com/alpine/v3.19/releases/x86_64/alpine-standard-3.19.1-x86_64.iso',
                'timeout': 10,
                'enabled': True
            }
        ]
        logger.info(f"[BANDWIDTH-CONFIG] 使用默认配置: {len(self._server_configs)} 个国内服务器")


    def test_bandwidth_full(self) -> Optional[Dict[str, Any]]:
        """完整带宽测试（包含延迟和下载速度）

        注意：自研方案不支持上传速度测试，返回结果中 upload_mbps 为 0

        Returns:
            测试结果字典，包含下载速度、延迟
        """
        if self._testing:
            logger.warning("带宽测试正在进行中，请稍后再试")
            self._last_error = "测试正在进行中，请稍后再试"
            return None

        # 导入AI日志流程管理器
        from backend.infrastructure.system_vnpy.unified_log_system import (
            ai_log_process,
            ProcessNames
        )

        try:
            self._testing = True

            # 检查服务器配置
            if not self._server_configs:
                logger.error("[BANDWIDTH] 服务器配置为空，无法进行测试")
                self._last_error = "服务器配置为空"
                return None

            logger.info(f"[BANDWIDTH] 准备开始测试，服务器池大小: {len(self._server_configs)}")

            # 使用AI日志流程上下文管理器，生成独立AI日志文件
            # 添加异常处理，确保即使AI日志初始化失败也不影响测试
            try:
                with ai_log_process(
                    ProcessNames.NETWORK_SPEEDTEST_BANDWIDTH,
                    metadata={
                        "test_type": "full",
                        "max_retries": self._bandwidth_max_retries,
                        "timeout": self._bandwidth_timeout,
                        "server_count": len(self._server_configs)
                    }
                ):
                    logger.info("开始完整带宽测试（预计耗时10-15秒）...")

                    # 导入自研测速模块
                    from backend.infrastructure.system_vnpy.speedtest_native import NetworkSpeedTester

                    # 创建测速器
                    tester = NetworkSpeedTester(timeout=self._bandwidth_timeout)

                    # 添加时间追踪
                    test_start_time = datetime.now()
                    logger.info(f"[BANDWIDTH] 开始完整带宽测试（随机选择+重试策略），开始时间: {test_start_time.strftime('%H:%M:%S')}")

                    # 使用随机选择+重试策略的带宽测试
                    result_data = tester.test_bandwidth_with_random_retry(
                        server_configs=self._server_configs,
                        max_retries=self._bandwidth_max_retries,
                        timeout=self._bandwidth_timeout
                    )

                    test_elapsed = (datetime.now() - test_start_time).total_seconds()
                    logger.info(f"[BANDWIDTH] 完整带宽测试耗时: {test_elapsed:.2f}秒")

                    # 关闭测速器
                    tester.close()

                    # 处理测试结果
                    if result_data.get('status') == 'success':
                        # 组装结果（保持与原API兼容）
                        result = {
                            "download_mbps": result_data.get('download_mbps', 0),
                            "upload_mbps": 0,  # 自研方案不支持上传测速
                            "ping_ms": result_data.get('ping_ms', 0),
                            "test_time": result_data.get('test_time'),
                            "test_type": "full",
                            "server_name": result_data.get('server_name', 'Unknown')
                        }

                        self._last_full_result = result
                        self._full_test_time = datetime.now()

                        attempt = result_data.get('attempt', 1)
                        logger.info(
                            f"✅ 完整带宽测试完成: 下载 {result['download_mbps']}Mbps, "
                            f"延迟 {result['ping_ms']}ms, 服务器 {result['server_name']} (第{attempt}次尝试)"
                        )
                        logger.info(f"[SPEEDTEST-SAVE] 保存完整测速结果: {result}")

                        return result
                    else:
                        # 测试失败
                        error_msg = result_data.get('error', '所有测速服务器均不可用')
                        logger.error(f"❌ 完整带宽测试失败: {error_msg}")
                        self._last_error = error_msg

                        result = {
                            "download_mbps": -1,
                            "upload_mbps": -1,
                            "ping_ms": -1,
                            "test_time": datetime.now().isoformat(),
                            "test_type": "full",
                            "error": error_msg
                        }
                        self._last_full_result = result
                        self._full_test_time = datetime.now()

                        return result
            except Exception as ai_log_error:
                # AI日志初始化失败，继续执行测试（降级模式）
                logger.warning(f"[BANDWIDTH] AI日志初始化失败，继续测试（降级模式）: {ai_log_error}")

                logger.info("开始完整带宽测试（预计耗时10-15秒）...")

                # 导入自研测速模块
                from backend.infrastructure.system_vnpy.speedtest_native import NetworkSpeedTester

                # 创建测速器
                tester = NetworkSpeedTester(timeout=self._bandwidth_timeout)

                # 添加时间追踪
                test_start_time = datetime.now()
                logger.info(f"[BANDWIDTH] 开始完整带宽测试（随机选择+重试策略），开始时间: {test_start_time.strftime('%H:%M:%S')}")

                # 使用随机选择+重试策略的带宽测试
                result_data = tester.test_bandwidth_with_random_retry(
                    server_configs=self._server_configs,
                    max_retries=self._bandwidth_max_retries,
                    timeout=self._bandwidth_timeout
                )

                test_elapsed = (datetime.now() - test_start_time).total_seconds()
                logger.info(f"[BANDWIDTH] 完整带宽测试耗时: {test_elapsed:.2f}秒")

                # 关闭测速器
                tester.close()

                # 处理测试结果
                if result_data.get('status') == 'success':
                    # 组装结果（保持与原API兼容）
                    result = {
                        "download_mbps": result_data.get('download_mbps', 0),
                        "upload_mbps": 0,  # 自研方案不支持上传测速
                        "ping_ms": result_data.get('ping_ms', 0),
                        "test_time": result_data.get('test_time'),
                        "test_type": "full",
                        "server_name": result_data.get('server_name', 'Unknown')
                    }

                    self._last_full_result = result
                    self._full_test_time = datetime.now()

                    attempt = result_data.get('attempt', 1)
                    logger.info(
                        f"✅ 完整带宽测试完成: 下载 {result['download_mbps']}Mbps, "
                        f"延迟 {result['ping_ms']}ms, 服务器 {result['server_name']} (第{attempt}次尝试)"
                    )
                    logger.info(f"[SPEEDTEST-SAVE] 保存完整测速结果: {result}")

                    return result
                else:
                    # 测试失败
                    error_msg = result_data.get('error', '所有测速服务器均不可用')
                    logger.error(f"❌ 完整带宽测试失败: {error_msg}")
                    self._last_error = error_msg

                    result = {
                        "download_mbps": -1,
                        "upload_mbps": -1,
                        "ping_ms": -1,
                        "test_time": datetime.now().isoformat(),
                        "test_type": "full",
                        "error": error_msg
                    }
                    self._last_full_result = result
                    self._full_test_time = datetime.now()

                    return result

        except Exception as e:
            logger.error(f"❌ 完整带宽测试失败: {e}", exc_info=True)
            self._last_error = str(e)
            return None

        finally:
            self._testing = False

    async def test_bandwidth_full_async(self) -> Optional[Dict[str, Any]]:
        """完整带宽测试（异步版本）.

        Returns:
            测试结果字典
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.test_bandwidth_full)

    def get_last_full_result(self) -> Optional[Dict[str, Any]]:
        """获取最新完整测试结果.

        Returns:
            最新完整测试结果，如果未测试则返回None
        """
        return self._last_full_result


class LatencyMonitor:
    """延迟测试监控器（使用门户网站池，自动测试）

    使用门户网站、视频网站、体育网站等形成服务器池。
    启动时并发测试所有服务器连通性，生成可用服务器表缓存。
    之后每10秒自动测试一次延迟，随机选择服务器。
    """

    def __init__(self):
        """初始化延迟监控器"""
        self._available_servers: List[Dict[str, Any]] = []
        self._all_servers: List[Dict[str, Any]] = []

        # 使用get_root()获取项目根目录，缓存文件放在data/cache目录下
        root_path = self._get_root()
        cache_dir = root_path / "data" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._server_cache_file = str(cache_dir / "ping_servers_cache.json")

        self._last_ping_result: Optional[Dict[str, Any]] = None
        self._last_ping_time: Optional[datetime] = None
        self._auto_test_task: Optional[asyncio.Task] = None
        self._running = False
        self._test_interval = 10  # 10秒间隔
        self._timeout = 5  # 默认超时5秒
        self._network_disconnected = False  # 无网络连接标志

        # 加载服务器配置
        self._load_server_config()

        logger.info("[LATENCY-INIT] 延迟监控器初始化完成（门户网站池）")

    def _get_root(self) -> Path:
        """获取项目根目录路径

        Returns:
            项目根目录的Path对象
        """
        # 通过当前文件的路径向上查找项目根目录
        # monitor_system.py 位于 backend/infrastructure/system_vnpy/
        # 需要向上3级到达项目根目录
        current_file = Path(__file__)
        root_path = current_file.parent.parent.parent.parent
        return root_path

    def _load_server_config(self):
        """加载延迟测试服务器配置"""
        import yaml

        config_file = "backend/infrastructure/system_vnpy/config/ping_servers.yaml"

        try:
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)

                if not isinstance(config, dict):
                    logger.warning(f"[LATENCY-CONFIG] 配置文件格式错误，使用默认配置")
                    self._use_default_config()
                    return

                # 加载所有启用的服务器
                servers = config.get('servers', []) or []
                self._all_servers = [
                    s for s in servers
                    if isinstance(s, dict) and s.get('enabled', True)
                ]

                logger.info(f"[LATENCY-CONFIG] 加载 {len(self._all_servers)} 个延迟测试服务器")
            else:
                logger.warning(f"[LATENCY-CONFIG] 配置文件不存在: {config_file}，使用默认配置")
                self._use_default_config()
        except Exception as e:
            logger.error(f"[LATENCY-CONFIG] 加载配置失败: {e}，使用默认配置")
            self._use_default_config()

    def _use_default_config(self):
        """使用默认配置（当配置文件不存在或加载失败时）"""
        # 使用一些常见门户网站作为默认
        self._all_servers = [
            {
                'name': '百度',
                'category': 'portal',
                'ping_url': 'https://www.baidu.com',
                'timeout': 5,
                'enabled': True
            },
            {
                'name': '网易',
                'category': 'portal',
                'ping_url': 'https://www.163.com',
                'timeout': 5,
                'enabled': True
            },
            {
                'name': '搜狐',
                'category': 'portal',
                'ping_url': 'https://www.sohu.com',
                'timeout': 5,
                'enabled': True
            }
        ]
        logger.info(f"[LATENCY-CONFIG] 使用默认配置: {len(self._all_servers)} 个服务器")

    def _load_cache(self) -> bool:
        """加载文件缓存（如果当天有效）"""
        try:
            if not os.path.exists(self._server_cache_file):
                return False

            with open(self._server_cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            cache_date = cache_data.get('date')
            today = datetime.now().strftime('%Y-%m-%d')

            if cache_date == today:
                self._available_servers = cache_data.get('servers', [])
                logger.info(f"[LATENCY-CACHE] 加载缓存成功: {len(self._available_servers)} 个可用服务器（日期: {cache_date}）")
                return True
            else:
                logger.info(f"[LATENCY-CACHE] 缓存已过期（缓存日期: {cache_date}, 今天: {today}），将重新测试")
                return False
        except Exception as e:
            logger.warning(f"[LATENCY-CACHE] 加载缓存失败: {e}")
            return False

    def _save_cache(self):
        """保存可用服务器缓存到文件"""
        try:
            os.makedirs(os.path.dirname(self._server_cache_file), exist_ok=True)

            cache_data = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'servers': self._available_servers
            }

            with open(self._server_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            logger.info(f"[LATENCY-CACHE] 保存缓存成功: {len(self._available_servers)} 个可用服务器")
        except Exception as e:
            logger.warning(f"[LATENCY-CACHE] 保存缓存失败: {e}")

    async def _test_single_latency(self, server: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """测试单个服务器延迟（异步）"""
        from backend.infrastructure.system_vnpy.speedtest_native import NetworkSpeedTester

        ping_url = server.get('ping_url')
        if not ping_url:
            return None

        timeout = server.get('timeout', self._timeout)

        try:
            # 在线程池中执行同步测试（避免阻塞事件循环）
            loop = asyncio.get_event_loop()
            tester = NetworkSpeedTester(timeout=timeout, use_browser_headers=True)

            def sync_test():
                return tester.test_latency_browser_mode(ping_url)

            result = await loop.run_in_executor(None, sync_test)
            tester.close()

            if result and result.get('status') == 'success':
                return {
                    'server': server,
                    'ping_ms': result.get('ping_ms'),
                    'url': ping_url
                }
            return None
        except Exception as e:
            logger.debug(f"[LATENCY-TEST] 测试失败 {server.get('name')}: {e}")
            return None

    async def initialize_servers(self):
        """启动时并发测试所有服务器连通性，生成可用服务器表"""
        logger.info(f"[LATENCY-INIT] 开始初始化服务器池（共{len(self._all_servers)}个服务器）")

        # 1. 尝试加载文件缓存
        if self._load_cache():
            logger.info(f"[LATENCY-INIT] 使用缓存，可用服务器: {len(self._available_servers)} 个")
            return

        # 2. 并发测试所有服务器（无限制并发）
        logger.info(f"[LATENCY-INIT] 开始并发测试所有服务器连通性...")
        start_time = time.time()

        # 创建所有测试任务
        tasks = [self._test_single_latency(server) for server in self._all_servers]

        # 并发执行所有测试
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 筛选可用的服务器
        available = []
        for result in results:
            if isinstance(result, dict) and result:
                available.append(result['server'])

        elapsed = time.time() - start_time
        logger.info(f"[LATENCY-INIT] 连通性测试完成（耗时{elapsed:.2f}秒）: {len(available)}/{len(self._all_servers)} 个服务器可用")

        # 3. 如果所有服务器都不可用，尝试降级使用镜像站
        if not available:
            logger.warning("[LATENCY-INIT] 所有门户网站都不可用，尝试降级使用镜像站...")
            available = await self._fallback_to_mirrors()

        # 4. 更新可用服务器列表
        self._available_servers = available

        # 5. 如果仍然没有可用服务器，标记为无网络连接
        if not self._available_servers:
            logger.error("[LATENCY-INIT] 所有服务器都不可用，判断为本机已脱离网络")
            self._network_disconnected = True
        else:
            self._network_disconnected = False
            # 保存缓存
            self._save_cache()

    async def _fallback_to_mirrors(self) -> List[Dict[str, Any]]:
        """降级使用镜像站作为延迟测试源"""
        # 从speedtest_servers.yaml加载镜像站
        import yaml

        config_file = "backend/infrastructure/system_vnpy/config/speedtest_servers.yaml"
        fallback_servers = []

        try:
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)

                # 确保config是字典类型
                if not isinstance(config, dict):
                    logger.warning("[LATENCY-FALLBACK] 配置文件格式错误")
                    return []

                servers = config.get('servers', []) or []
                mirror_servers = [
                    {
                        'name': s.get('name', 'Unknown'),
                        'category': 'mirror',
                        'ping_url': s.get('ping_url'),
                        'timeout': s.get('timeout', 5),
                        'enabled': True
                    }
                    for s in servers
                    if isinstance(s, dict) and s.get('enabled', True) and s.get('ping_url')
                ]

                # 测试镜像站连通性
                tasks = [self._test_single_latency(server) for server in mirror_servers]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, dict) and result:
                        fallback_servers.append(result['server'])

                logger.info(f"[LATENCY-FALLBACK] 镜像站连通性测试: {len(fallback_servers)}/{len(mirror_servers)} 个可用")
        except Exception as e:
            logger.warning(f"[LATENCY-FALLBACK] 降级到镜像站失败: {e}")

        return fallback_servers

    async def start_auto_test(self):
        """启动自动延迟测试循环"""
        if self._running:
            logger.warning("[LATENCY-AUTO] 自动测试已在运行中")
            return

        if not self._available_servers:
            logger.warning("[LATENCY-AUTO] 没有可用服务器，无法启动自动测试")
            self._network_disconnected = True
            return

        self._running = True
        logger.info(f"[LATENCY-AUTO] 启动自动延迟测试（间隔{self._test_interval}秒，可用服务器{len(self._available_servers)}个）")

        # 创建后台任务
        self._auto_test_task = asyncio.create_task(self._auto_test_loop())

    async def _auto_test_loop(self):
        """自动测试循环"""
        while self._running:
            try:
                if not self._available_servers:
                    logger.warning("[LATENCY-AUTO] 可用服务器池为空，暂停测试")
                    self._network_disconnected = True
                    await asyncio.sleep(self._test_interval)
                    continue

                # 随机选择一个服务器
                import random
                selected_server = random.choice(self._available_servers)

                # 测试延迟
                result = await self._test_single_latency(selected_server)

                if result:
                    # 测试成功
                    self._last_ping_result = {
                        "ping_ms": result['ping_ms'],
                        "test_time": datetime.now().isoformat(),
                        "test_type": "auto",
                        "server_name": selected_server.get('name', 'Unknown')
                    }
                    self._last_ping_time = datetime.now()
                    self._network_disconnected = False
                    logger.debug(f"[LATENCY-AUTO] ✅ 延迟测试成功: {result['ping_ms']}ms ({selected_server.get('name')})")
                else:
                    # 测试失败，可能网络断开
                    logger.warning(f"[LATENCY-AUTO] ❌ 延迟测试失败: {selected_server.get('name')}")
                    # 不立即标记为无网络，可能只是这个服务器暂时不可用

                # 等待下一次测试
                await asyncio.sleep(self._test_interval)

            except asyncio.CancelledError:
                logger.info("[LATENCY-AUTO] 自动测试循环被取消")
                break
            except Exception as e:
                logger.error(f"[LATENCY-AUTO] 自动测试循环异常: {e}", exc_info=True)
                await asyncio.sleep(self._test_interval)

    async def retry_initialize(self):
        """重新初始化服务器池（用于重试按钮）"""
        logger.info("[LATENCY-RETRY] 重新初始化服务器池...")
        self._network_disconnected = False
        await self.initialize_servers()

        # 如果初始化成功且有可用服务器，重启自动测试
        if self._available_servers and not self._running:
            await self.start_auto_test()
        elif self._running:
            # 如果已经在运行，重启循环
            self._running = False
            if self._auto_test_task:
                self._auto_test_task.cancel()
            await self.start_auto_test()

    def stop(self):
        """停止自动测试"""
        self._running = False
        if self._auto_test_task:
            self._auto_test_task.cancel()
        logger.info("[LATENCY-AUTO] 自动延迟测试已停止")

    def get_last_ping_result(self) -> Optional[Dict[str, Any]]:
        """获取最新延迟测试结果"""
        return self._last_ping_result

    def is_network_disconnected(self) -> bool:
        """检查是否无网络连接"""
        return self._network_disconnected

    def get_available_server_count(self) -> int:
        """获取可用服务器数量"""
        return len(self._available_servers)


class SystemMonitor:
    """系统监控器."""

    def __init__(self):
        """初始化系统监控器."""
        self.monitoring = False
        self.history = []
        self.max_history = 1000

        # 🚀 性能优化：初始化CPU采样（建立baseline）
        # 第一次调用cpu_percent()建立基线，后续调用interval=None才有意义
        if HAS_PSUTIL:
            try:
                psutil.cpu_percent(interval=None)
            except Exception:
                pass

        # 磁盘类型缓存
        self._disk_type_cache: Dict[str, str] = {}

        # 添加带宽监控器（仅负责带宽测试）
        self.bandwidth_monitor = BandwidthMonitor()

        # 添加延迟监控器（负责延迟测试）
        self.latency_monitor = LatencyMonitor()

    def get_bandwidth_info(self) -> Dict[str, Any]:
        """获取运营商带宽信息（返回缓存结果）.

        Returns:
            包含完整测试和延迟测试结果字典
        """
        full_result = self.bandwidth_monitor.get_last_full_result()
        ping_result = self.latency_monitor.get_last_ping_result()
        network_disconnected = self.latency_monitor.is_network_disconnected()

        result = {
            "full_test": (
                full_result
                if full_result
                else {
                    "download_mbps": None,
                    "upload_mbps": None,
                    "ping_ms": None,
                    "status": "未测试",
                }
            ),
            "ping_test": ping_result if ping_result else {"ping_ms": None, "status": "未测试"},
            "network_disconnected": network_disconnected,  # 无网络连接标志
        }

        # 🔥 测速专用日志（详细）
        logger.info(f"[SPEEDTEST-DATA] get_bandwidth_info返回数据:")
        logger.info(f"  - full_test: {full_result}")
        logger.info(f"  - ping_test: {ping_result}")
        logger.info(f"  - network_disconnected: {network_disconnected}")

        return result

    def _detect_disk_type(self, device_name: str) -> str:
        """检测单个磁盘类型.

        Args:
            device_name: 设备名（Windows: PhysicalDrive0, Linux: sda）

        Returns:
            磁盘类型：hdd/ssd/nvme/unknown
        """
        # 检查缓存
        if device_name in self._disk_type_cache:
            return self._disk_type_cache[device_name]

        disk_type = DiskType.UNKNOWN

        try:
            system = platform.system()

            if system == "Windows":
                # Windows平台使用WMI
                try:
                    import wmi

                    c = wmi.WMI()
                    for disk in c.Win32_DiskDrive():
                        # 匹配设备名
                        if device_name in disk.DeviceID or disk.DeviceID in device_name:
                            # NVMe检测
                            if disk.InterfaceType and "NVMe" in disk.InterfaceType:
                                disk_type = DiskType.NVME
                            # SSD检测（通过型号名称）
                            elif disk.Model and any(
                                keyword in disk.Model.upper()
                                for keyword in ["SSD", "SOLID STATE", "NVME", "PSSD"]
                            ):
                                disk_type = DiskType.SSD
                            # HDD检测
                            elif disk.MediaType and "fixed" in disk.MediaType.lower():
                                disk_type = DiskType.HDD
                            break
                except ImportError:
                    logger.debug("WMI模块未安装，无法检测磁盘类型")
                except Exception as e:
                    logger.debug("Windows磁盘类型检测失败: %s", e)

            elif system == "Linux":
                # Linux平台检测
                from pathlib import Path

                # NVMe检测（通过设备名）
                if device_name.startswith("nvme"):
                    disk_type = DiskType.NVME
                else:
                    # 通过rotational文件判断
                    rotational_path = Path(f"/sys/block/{device_name}/queue/rotational")
                    if rotational_path.exists():
                        try:
                            with open(rotational_path, "r", encoding="utf-8") as f:
                                value = f.read().strip()
                                if value == "0":
                                    disk_type = DiskType.SSD
                                elif value == "1":
                                    disk_type = DiskType.HDD
                        except (IOError, PermissionError) as e:
                            logger.debug("读取rotational文件失败: %s", e)

        except Exception as e:
            logger.debug("检测磁盘类型失败 (%s): %s", device_name, e)

        # 缓存结果
        self._disk_type_cache[device_name] = disk_type
        return disk_type

    def get_physical_disks_info(self) -> Dict[str, Dict[str, Any]]:
        """获取物理磁盘信息（使用WMI区分物理磁盘和逻辑分区）

        Returns:
            {
                "PhysicalDrive0": {
                    "device_id": "\\\\.\\PHYSICALDRIVE0",
                    "disk_type": "ssd",  # hdd/ssd/nvme
                    "is_system_disk": True,  # C:所在磁盘
                    "partitions": ["C:", "D:"],
                    "interface_type": "NVMe",
                    "size_bytes": 512000000000,
                }
            }
        """
        physical_disks = {}

        try:
            system = platform.system()

            if system == "Windows" and HAS_WMI and HAS_PSUTIL:
                # 使用WMI获取物理磁盘信息
                try:
                    c = wmi.WMI()

                    # 获取所有物理磁盘
                    for disk in c.Win32_DiskDrive():
                        # 从DeviceID提取磁盘编号: \\.\PHYSICALDRIVE0 -> PhysicalDrive0
                        device_id = disk.DeviceID
                        if "PHYSICALDRIVE" in device_id.upper():
                            # 提取并标准化为驼峰式格式 (与psutil一致)
                            raw_name = device_id.split("\\")[-1]  # PHYSICALDRIVE0
                            if raw_name.upper().startswith("PHYSICALDRIVE"):
                                disk_num = raw_name.upper().replace("PHYSICALDRIVE", "")
                                disk_name = f"PhysicalDrive{disk_num}"
                            else:
                                disk_name = raw_name
                        else:
                            continue

                        # 检测磁盘类型
                        disk_type = DiskType.UNKNOWN
                        if disk.InterfaceType and "NVMe" in disk.InterfaceType:
                            disk_type = DiskType.NVME
                        elif disk.Model and any(
                            keyword in disk.Model.upper()
                            for keyword in ["SSD", "SOLID STATE", "NVME", "PSSD"]
                        ):
                            disk_type = DiskType.SSD
                        else:
                            # 未检测将SSD关键词，默认为HDD（机械硬盘）
                            disk_type = DiskType.HDD

                        # 获取该物理磁盘分区
                        partitions = []
                        for partition in disk.associators("Win32_DiskDriveToDiskPartition"):
                            for logical_disk in partition.associators(
                                "Win32_LogicalDiskToPartition"
                            ):
                                partitions.append(logical_disk.DeviceID)  # C:, D:, etc.

                        # 判断是否为系统盘
                        # 方案1a: 检查是否包含C:分区
                        is_system_disk = "C:" in partitions

                        # 方案2afallback：如果没有C:盘，检查系统目录
                        if not is_system_disk and partitions:
                            try:
                                import os

                                system_drive = os.environ.get("SystemDrive", "C:")
                                is_system_disk = system_drive in partitions
                            except Exception:
                                pass

                        physical_disks[disk_name] = {
                            "device_id": device_id,
                            "disk_type": disk_type,
                            "is_system_disk": is_system_disk,
                            "partitions": partitions,
                            "interface_type": disk.InterfaceType or "Unknown",
                            "size_bytes": int(disk.Size) if disk.Size else 0,
                        }

                except Exception as e:
                    logger.warning("WMI获取物理磁盘信息失败: %s，将使用简化方案", e)

            # 如果WMI失败或非Windows系统，使用简化方案
            if not physical_disks and HAS_PSUTIL:
                # 简化方案：通过psutil获取基本信息
                partitions = psutil.disk_partitions()
                processed_disks = set()

                for partition in partitions:
                    if not partition.fstype:
                        continue

                    # 简化磁盘名称映射
                    if system == "Windows":
                        # 假设所有分区在同一个物理磁盘（PhysicalDrive0）
                        disk_name = "PhysicalDrive0"
                    else:
                        # Linux: 从/dev/sda1提取sda
                        disk_name = partition.device.split("/")[-1].rstrip("0123456789")

                    if disk_name not in processed_disks:
                        disk_type = self._detect_disk_type(disk_name)

                        # 收集该磁盘所有分区
                        disk_partitions = []
                        for p in partitions:
                            if system == "Windows":
                                disk_partitions.append(p.device.rstrip("\\"))
                            elif disk_name in p.device:
                                disk_partitions.append(p.mountpoint)

                        # 判断是否系统盘
                        is_system_disk = False
                        if system == "Windows":
                            is_system_disk = "C:" in disk_partitions
                        else:
                            is_system_disk = "/" in disk_partitions

                        physical_disks[disk_name] = {
                            "device_id": disk_name,
                            "disk_type": disk_type,
                            "is_system_disk": is_system_disk,
                            "partitions": disk_partitions,
                            "interface_type": "Unknown",
                            "size_bytes": 0,
                        }

                        processed_disks.add(disk_name)

        except Exception as e:
            logger.error("获取物理磁盘信息失败: %s", e)

        return physical_disks

    def get_disks_with_types(self) -> Dict[str, Dict[str, Any]]:
        """获取所有磁盘及其类型信息.

        Returns:
            字典格式：{
                "C:\\": {
                    "type": "nvme",
                    "mount": "C:\\",
                    "read_threshold_kbps": 2000000,
                    "write_threshold_kbps": 1500000
                },
                ...
            }
        """
        disks_info = {}

        try:
            if not HAS_PSUTIL:
                return disks_info

            partitions = psutil.disk_partitions()
            system = platform.system()

            for partition in partitions:
                try:
                    # 跳过虚拟文件系统
                    if not partition.fstype:
                        continue
                    if system == "Linux" and partition.fstype in ["squashfs", "tmpfs"]:
                        continue

                    mount_point = partition.mountpoint
                    device = partition.device

                    # 提取物理磁盘设备名
                    if system == "Windows":
                        # Windows: 尝试从WMI获取物理磁盘编号
                        # 简化处理：假设第一个物理磁盘
                        device_name = "PhysicalDrive0"
                    else:
                        # Linux: 从 /dev/sda1 提取 sda
                        device_name = device.split("/")[-1].rstrip("0123456789")

                    # 检测磁盘类型
                    disk_type = self._detect_disk_type(device_name)

                    # 获取对应阈值
                    thresholds = DISK_THRESHOLDS.get(disk_type, DISK_THRESHOLDS[DiskType.UNKNOWN])

                    disks_info[mount_point] = {
                        "type": disk_type,
                        "mount": mount_point,
                        "device": device,
                        "read_threshold_kbps": thresholds["read"],
                        "write_threshold_kbps": thresholds["write"],
                    }

                except (PermissionError, OSError) as e:
                    logger.debug("无法访问磁盘 %s: %s", partition.device, e)
                    continue

        except Exception as e:
            logger.exception("获取磁盘类型信息失败: %s", e)

        return disks_info

    def get_system_info(self) -> SystemInfo:
        """获取系统基本信息."""
        try:
            if HAS_PSUTIL:
                # 获取网络接口
                network_interfaces = list(psutil.net_if_addrs().keys())

                # 获取磁盘总空间
                disk_usage = psutil.disk_usage("/")

                return SystemInfo(
                    platform=platform.system(),
                    platform_version=platform.version(),
                    architecture=platform.architecture()[0],
                    hostname=platform.node(),
                    cpu_count=psutil.cpu_count(logical=False) or 1,
                    cpu_count_logical=psutil.cpu_count(logical=True) or 1,
                    memory_total=psutil.virtual_memory().total,
                    disk_total=disk_usage.total,
                    network_interfaces=network_interfaces,
                    boot_time=datetime.fromtimestamp(psutil.boot_time()),
                )
            else:
                # 基础实现
                return SystemInfo(
                    platform=platform.system(),
                    platform_version=platform.version(),
                    architecture=platform.architecture()[0],
                    hostname=platform.node(),
                    cpu_count=os.cpu_count() or 1,
                    cpu_count_logical=os.cpu_count() or 1,
                    memory_total=1024 * 1024 * 1024,  # 1GB 默认值
                    disk_total=100 * 1024 * 1024 * 1024,  # 100GB 默认值
                    network_interfaces=["eth0"],
                    boot_time=datetime.now(),
                )
        except (OSError, AttributeError, ImportError) as e:
            logger.error("获取系统信息失败: %s", e)
            raise

    def get_resource_usage(self) -> ResourceUsage:
        """获取资源使用情况."""
        try:
            if HAS_PSUTIL:
                # CPU使用率
                # 🚀 性能优化：使用interval=None（非阻塞模式）
                # interval=1会阻塞线程1秒！严重影响性能
                # None表示返回自上次调用以来CPU使用率，不阻塞
                cpu_percent_raw = psutil.cpu_percent(interval=None)
                # 确保返回值是float类型（而不是list）
                cpu_percent = (
                    float(cpu_percent_raw) if not isinstance(cpu_percent_raw, list) else 0.0
                )

                # 内存使用率
                memory = psutil.virtual_memory()

                # 磁盘使用率（简化版，移除signal处理避免Windows兼容问题）
                disk: Any = None
                try:
                    disk = psutil.disk_usage("/")
                except (OSError, AttributeError):
                    # 如果失败，使用默认值
                    logger.debug("磁盘使用率获取失败，使用默认值")
                    disk = type(
                        "DiskUsage",
                        (),
                        {"used": 50 * 1024 * 1024 * 1024, "total": 100 * 1024 * 1024 * 1024},
                    )()

                # 网络流量
                network: Any = None
                try:
                    network = psutil.net_io_counters()
                except (OSError, AttributeError):
                    # 如果失败，使用默认值
                    logger.debug("网络流量获取失败，使用默认值")
                    network = type(
                        "NetIO", (), {"bytes_sent": 1024 * 1024, "bytes_recv": 2048 * 1024}
                    )()

                # 进程数量（带超时保护）
                process_count = 150  # 默认值
                try:
                    # 只获取前100个进程，避免过多
                    pids = psutil.pids()[:100]
                    process_count = len(pids)
                except (OSError, AttributeError):
                    logger.debug("进程数量获取失败，使用默认值")

                # 负载平均值(Linux/Unix)
                load_average = []
                try:
                    load_average = list(psutil.getloadavg())
                except (AttributeError, OSError):
                    # Windows不支持getloadavg
                    load_average = [0.0, 0.0, 0.0]

                return ResourceUsage(
                    cpu_percent=cpu_percent,
                    memory_percent=memory.percent,
                    disk_percent=(disk.used / disk.total) * 100 if disk else 45.0,
                    network_sent=network.bytes_sent if network else 1024 * 1024,
                    network_recv=network.bytes_recv if network else 2048 * 1024,
                    process_count=process_count,
                    load_average=load_average,
                    timestamp=datetime.now(),
                )
            else:
                # 基础实现(无psutil时返回默认值)
                return ResourceUsage(
                    cpu_percent=25.0,
                    memory_percent=60.0,
                    disk_percent=45.0,
                    network_sent=1024 * 1024,
                    network_recv=2048 * 1024,
                    process_count=150,
                    load_average=[0.5, 0.4, 0.3],
                    timestamp=datetime.now(),
                )
        except (OSError, AttributeError, ImportError) as e:
            logger.error("获取资源使用情况失败: %s", e)
            raise

    def get_cpu_info(self) -> Dict[str, Any]:
        """获取CPU详细信息.
        
        频率获取策略（优先级从高到低）:
        1. LibreHardwareMonitor: 从硬件监控器获取CPU最大频率（可能包含Turbo Boost上限）
        2. psutil: 获取基础频率（Windows上通常是基础频率，不是Turbo Boost上限）
        3. 默认值: 如果都不可用，使用默认值
        """
        try:
            # 首先尝试从LibreHardwareMonitor获取CPU最大频率（可能包含Turbo Boost）
            # 注意：SystemMonitor是独立类，需要通过全局单例或参数传递访问硬件监控器
            # 使用HardwareMonitorFactory获取单例实例（如果可用）
            max_freq_from_lhm = None
            try:
                # 尝试通过全局方式获取硬件监控器（如果MonitoringProcessV2已初始化）
                # 这里使用HardwareMonitorFactory的单例模式
                hardware_monitor = HardwareMonitorFactory.get_instance()
                
                if hardware_monitor and hardware_monitor.is_available():
                    sensor_data = hardware_monitor.get_all_sensor_data()
                    clock_sensors = sensor_data.get("clock", {})
                    
                    # 查找CPU相关的时钟传感器
                    cpu_max_freqs = []
                    import math
                    for device_name, sensors in clock_sensors.items():
                        # 检查是否是CPU设备（名称包含CPU或处理器相关关键词）
                        if any(keyword in device_name.lower() for keyword in ["cpu", "processor", "ryzen", "intel", "core"]):
                            for sensor in sensors:
                                max_val = sensor.get("max")
                                if max_val is not None and not math.isnan(max_val) and max_val > 0:
                                    cpu_max_freqs.append(max_val)
                    
                    if cpu_max_freqs:
                        max_freq_from_lhm = max(cpu_max_freqs)
                        logger.debug(f"[CPU-FREQ] 从LibreHardwareMonitor获取最大频率: {max_freq_from_lhm:.2f} MHz")
            except Exception as e:
                logger.debug(f"[CPU-FREQ] 从LibreHardwareMonitor获取频率失败: {e}")
            
            if HAS_PSUTIL:
                # 获取CPU频率（返回单个对象，而非列表）
                cpu_freq: Any = psutil.cpu_freq()  # scpufreq 对象或 None
                cpu_times: Any = psutil.cpu_times()

                # 优先使用LibreHardwareMonitor的最大频率（如果可用且更高）
                max_freq = cpu_freq.max if cpu_freq else 0
                if max_freq_from_lhm and max_freq_from_lhm > max_freq:
                    max_freq = max_freq_from_lhm
                    logger.debug(f"[CPU-FREQ] 使用LibreHardwareMonitor的最大频率（可能包含Turbo Boost）: {max_freq:.2f} MHz")
                elif max_freq_from_lhm:
                    logger.debug(f"[CPU-FREQ] LibreHardwareMonitor频率({max_freq_from_lhm:.2f}MHz)不高于psutil({max_freq:.2f}MHz)，使用psutil值")

                return {
                    "cpu_count_physical": psutil.cpu_count(logical=False),
                    "cpu_count_logical": psutil.cpu_count(logical=True),
                    "cpu_percent_per_core": psutil.cpu_percent(percpu=True),
                    "cpu_frequency": {
                        "current": cpu_freq.current if cpu_freq else 0,
                        "min": cpu_freq.min if cpu_freq else 0,
                        "max": max_freq,  # 可能包含Turbo Boost上限（如果LibreHardwareMonitor可用）
                    },
                    "cpu_times": {
                        "user": cpu_times.user,
                        "system": cpu_times.system,
                        "idle": cpu_times.idle,
                    },
                }
            else:
                # 如果没有psutil，使用LibreHardwareMonitor的值或默认值
                max_freq = max_freq_from_lhm if max_freq_from_lhm else 3000
                
                return {
                    "cpu_count_physical": os.cpu_count() or 1,
                    "cpu_count_logical": os.cpu_count() or 1,
                    "cpu_percent_per_core": [25.0],
                    "cpu_frequency": {
                        "current": 2400,
                        "min": 1000,
                        "max": max_freq,
                    },
                    "cpu_times": {
                        "user": 1000.0,
                        "system": 500.0,
                        "idle": 5000.0,
                    },
                }
        except (OSError, AttributeError, ImportError) as e:
            logger.error("获取CPU信息失败: %s", e)
            return {}

    def get_memory_info(self) -> Dict[str, Any]:
        """获取内存详细信息."""
        try:
            if HAS_PSUTIL:
                virtual_memory = psutil.virtual_memory()
                swap_memory = psutil.swap_memory()

                return {
                    "virtual_memory": {
                        "total": virtual_memory.total,
                        "available": virtual_memory.available,
                        "used": virtual_memory.used,
                        "free": virtual_memory.free,
                        "percent": virtual_memory.percent,
                    },
                    "swap_memory": {
                        "total": swap_memory.total,
                        "used": swap_memory.used,
                        "free": swap_memory.free,
                        "percent": swap_memory.percent,
                    },
                }
            else:
                return {
                    "virtual_memory": {
                        "total": 8 * 1024 * 1024 * 1024,
                        "available": 4 * 1024 * 1024 * 1024,
                        "used": 4 * 1024 * 1024 * 1024,
                        "free": 4 * 1024 * 1024 * 1024,
                        "percent": 50.0,
                    },
                    "swap_memory": {
                        "total": 2 * 1024 * 1024 * 1024,
                        "used": 512 * 1024 * 1024,
                        "free": 1.5 * 1024 * 1024 * 1024,
                        "percent": 25.0,
                    },
                }
        except (OSError, AttributeError, ImportError) as e:
            logger.error("获取内存信息失败: %s", e)
            return {}

    def get_disk_info(self) -> Dict[str, Any]:
        """获取磁盘详细信息."""
        try:
            if not HAS_PSUTIL:
                return {
                    "C:": {
                        "mountpoint": "C:",
                        "fstype": "NTFS",
                        "total": 100 * 1024 * 1024 * 1024,
                        "used": 50 * 1024 * 1024 * 1024,
                        "free": 50 * 1024 * 1024 * 1024,
                        "percent": 50.0,
                    }
                }

            disk_partitions = psutil.disk_partitions()
            disk_info = {}

            for partition in disk_partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_info[partition.device] = {
                        "mountpoint": partition.mountpoint,
                        "fstype": partition.fstype,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": (usage.used / usage.total) * 100,
                    }
                except PermissionError:
                    continue

            # 磁盘IO统计
            disk_io: Any = psutil.disk_io_counters()
            if disk_io:
                disk_info["io_counters"] = {
                    "read_count": disk_io.read_count,
                    "write_count": disk_io.write_count,
                    "read_bytes": disk_io.read_bytes,
                    "write_bytes": disk_io.write_bytes,
                }

            return disk_info
        except (OSError, AttributeError, ImportError) as e:
            logger.error("获取磁盘信息失败: %s", e)
            return {}

    def get_network_info(self) -> Dict[str, Any]:
        """获取网络详细信息."""
        try:
            network_info = {}

            # 网络接口信息
            net_if_addrs = psutil.net_if_addrs()
            net_if_stats = psutil.net_if_stats()

            for interface, addresses in net_if_addrs.items():
                interface_info = {"addresses": [], "stats": {}}

                # 地址信息
                for addr in addresses:
                    interface_info["addresses"].append(
                        {
                            "family": str(addr.family),
                            "address": addr.address,
                            "netmask": addr.netmask,
                            "broadcast": addr.broadcast,
                        }
                    )

                # 统计信息
                if interface in net_if_stats:
                    stats = net_if_stats[interface]
                    interface_info["stats"] = {
                        "isup": stats.isup,
                        "duplex": str(stats.duplex),
                        "speed": stats.speed,
                        "mtu": stats.mtu,
                    }

                network_info[interface] = interface_info

            # 网络IO统计
            net_io: Any = psutil.net_io_counters()
            if net_io:
                network_info["io_counters"] = {
                    "bytes_sent": net_io.bytes_sent,
                    "bytes_recv": net_io.bytes_recv,
                    "packets_sent": net_io.packets_sent,
                    "packets_recv": net_io.packets_recv,
                    "errin": net_io.errin,
                    "errout": net_io.errout,
                    "dropin": net_io.dropin,
                    "dropout": net_io.dropout,
                }

            return network_info
        except (OSError, AttributeError, ImportError) as e:
            logger.error("获取网络信息失败: %s", e)
            return {}

    def get_disk_io_speed(self) -> Dict[str, Dict[str, Any]]:
        """获取各磁盘I/O速度 (MB/s).

        Returns:
            Dict: 各磁盘读写速度和类型信息，格式: {
                "C:\\": {
                    "read_speed": 50.2,
                    "write_speed": 30.1,
                    "read_speed_kbps": 51200,
                    "write_speed_kbps": 30800,
                    "disk_type": "nvme",
                    "read_threshold": 2000000,
                    "write_threshold": 1500000
                },
                ...
            }
        """
        try:
            if not HAS_PSUTIL:
                return {}

            io_speeds = {}

            # 获取物理磁盘信息
            physical_disks = self.get_physical_disks_info()

            # 获取第一次I/O计数
            io_counters_1: Any = psutil.disk_io_counters(perdisk=True)
            time.sleep(0.1)  # 等待100ms
            io_counters_2: Any = psutil.disk_io_counters(perdisk=True)

            if not io_counters_1 or not io_counters_2:
                return {}

            # 直接遍历物理磁盘I/O计数器
            for disk_name, counter_1 in io_counters_1.items():
                try:
                    if disk_name not in io_counters_2:
                        continue

                    counter_2 = io_counters_2[disk_name]

                    # 计算读写速度 (字节/秒 -> MB/秒)
                    read_bytes_diff = counter_2.read_bytes - counter_1.read_bytes
                    write_bytes_diff = counter_2.write_bytes - counter_1.write_bytes

                    read_speed_mbps = (read_bytes_diff / 0.1) / (1024 * 1024)  # 0.1秒间隔
                    write_speed_mbps = (write_bytes_diff / 0.1) / (1024 * 1024)
                    read_speed_kbps = read_speed_mbps * 1024
                    write_speed_kbps = write_speed_mbps * 1024

                    # 获取该物理磁盘详细信息
                    physical_disk_info = physical_disks.get(disk_name, {})
                    disk_type = physical_disk_info.get("disk_type", DiskType.UNKNOWN)
                    partitions = physical_disk_info.get("partitions", [])
                    is_system_disk = physical_disk_info.get("is_system_disk", False)

                    # 获取阈值信息
                    thresholds = DISK_THRESHOLDS.get(disk_type, DISK_THRESHOLDS[DiskType.UNKNOWN])

                    # 转换为友好中文显示名称
                    if disk_name.startswith("PhysicalDrive"):
                        disk_num = disk_name.replace("PhysicalDrive", "")
                        display_name = f"物理磁盘{disk_num}"
                    else:
                        display_name = disk_name

                    io_speeds[display_name] = {
                        "read_speed": round(read_speed_mbps, 2),
                        "write_speed": round(write_speed_mbps, 2),
                        "read_speed_kbps": round(read_speed_kbps, 2),
                        "write_speed_kbps": round(write_speed_kbps, 2),
                        "disk_type": disk_type,
                        "read_threshold": thresholds["read"],
                        "write_threshold": thresholds["write"],
                        "partitions": partitions,
                        "is_system_disk": is_system_disk,
                        "physical_name": disk_name,  # 保留原始名称用于调试
                    }

                except (PermissionError, OSError) as e:
                    logger.debug("无法获取磁盘 %s I/O速度: %s", disk_name, e)
                    continue

            return io_speeds

        except Exception as e:
            logger.exception("获取磁盘I/O速度失败: %s", e)
            return {}

    async def get_disk_io_speed_async(self) -> Dict[str, Dict[str, Any]]:
        """获取各磁盘I/O速度 (MB/s) - 异步版本.

        Returns:
            Dict: 各磁盘读写速度，格式: {"C:": {"read_speed": 50.2, "write_speed": 30.1}, ...}
        """
        try:
            if not HAS_PSUTIL:
                return {}

            # 导入asyncio
            import asyncio

            io_speeds = {}

            # 获取物理磁盘信息
            physical_disks = self.get_physical_disks_info()

            # 获取第一次I/O计数
            io_counters_1: Any = psutil.disk_io_counters(perdisk=True)
            await asyncio.sleep(0.1)  # 异步等待100ms
            io_counters_2: Any = psutil.disk_io_counters(perdisk=True)

            if not io_counters_1 or not io_counters_2:
                return {}

            # 直接遍历物理磁盘I/O计数器
            for disk_name, counter_1 in io_counters_1.items():
                try:
                    if disk_name not in io_counters_2:
                        continue

                    counter_2 = io_counters_2[disk_name]

                    # 计算读写速度 (字节/秒 -> MB/秒)
                    read_bytes_diff = counter_2.read_bytes - counter_1.read_bytes
                    write_bytes_diff = counter_2.write_bytes - counter_1.write_bytes

                    read_speed_mbps = (read_bytes_diff / 0.1) / (1024 * 1024)  # 0.1秒间隔
                    write_speed_mbps = (write_bytes_diff / 0.1) / (1024 * 1024)
                    read_speed_kbps = read_speed_mbps * 1024
                    write_speed_kbps = write_speed_mbps * 1024

                    # 获取该物理磁盘详细信息
                    physical_disk_info = physical_disks.get(disk_name, {})
                    disk_type = physical_disk_info.get("disk_type", DiskType.UNKNOWN)
                    partitions = physical_disk_info.get("partitions", [])
                    is_system_disk = physical_disk_info.get("is_system_disk", False)

                    # 获取阈值信息
                    thresholds = DISK_THRESHOLDS.get(disk_type, DISK_THRESHOLDS[DiskType.UNKNOWN])

                    # 转换为友好中文显示名称
                    if disk_name.startswith("PhysicalDrive"):
                        disk_num = disk_name.replace("PhysicalDrive", "")
                        display_name = f"物理磁盘{disk_num}"
                    else:
                        display_name = disk_name

                    io_speeds[display_name] = {
                        "read_speed": round(read_speed_mbps, 2),
                        "write_speed": round(write_speed_mbps, 2),
                        "read_speed_kbps": round(read_speed_kbps, 2),
                        "write_speed_kbps": round(write_speed_kbps, 2),
                        "disk_type": disk_type,
                        "read_threshold": thresholds["read"],
                        "write_threshold": thresholds["write"],
                        "partitions": partitions,
                        "is_system_disk": is_system_disk,
                        "physical_name": disk_name,  # 保留原始名称用于调试
                    }

                except (PermissionError, OSError) as e:
                    logger.debug("无法获取磁盘 %s I/O速度: %s", disk_name, e)
                    continue

            return io_speeds

        except Exception as e:
            logger.exception("获取磁盘I/O速度失败(异步): %s", e)
            return {}

    def get_network_speed(self) -> Dict[str, Any]:
        """获取网络速度和带宽占用.

        Returns:
            Dict: 网络速度信息，格式:
            {
                "upload_speed_kbps": 1024.5,
                "download_speed_kbps": 5120.8,
                "bandwidth_percent": 45.2,
                "interface": "以太网"
            }
        """
        try:
            if not HAS_PSUTIL:
                return {}

            # 获取第一次网络I/O计数
            net_io_1: Any = psutil.net_io_counters()
            time.sleep(0.1)  # 等待100ms
            net_io_2: Any = psutil.net_io_counters()

            if not net_io_1 or not net_io_2:
                return {}

            # 计算上传/下载速度 (字节/秒 -> KB/秒)
            upload_bytes_diff = net_io_2.bytes_sent - net_io_1.bytes_sent
            download_bytes_diff = net_io_2.bytes_recv - net_io_1.bytes_recv

            upload_speed_kbps = (upload_bytes_diff / 0.1) / 1024  # 0.1秒间隔
            download_speed_kbps = (download_bytes_diff / 0.1) / 1024

            # 估算带宽占用百分比（假设1Gbps网卡 = 125MB/s = 128000KB/s）
            # 这里使用一个保守估算
            total_speed_kbps = upload_speed_kbps + download_speed_kbps
            assumed_bandwidth_kbps = 128000  # 1Gbps网卡

            # 尝试获取实际网卡速度
            try:
                net_if_stats = psutil.net_if_stats()
                for interface, stats in net_if_stats.items():
                    if stats.isup and stats.speed > 0:
                        # speed单位是Mbps，转换为KBps
                        assumed_bandwidth_kbps = stats.speed * 1024 / 8
                        break
            except Exception:
                pass

            bandwidth_percent = (
                (total_speed_kbps / assumed_bandwidth_kbps * 100)
                if assumed_bandwidth_kbps > 0
                else 0
            )

            # 获取主要网络接口名称
            interface_name = "未知"
            try:
                net_if_stats = psutil.net_if_stats()
                for interface, stats in net_if_stats.items():
                    if stats.isup:
                        interface_name = interface
                        break
            except Exception:
                pass

            return {
                "upload_speed_kbps": round(upload_speed_kbps, 2),
                "download_speed_kbps": round(download_speed_kbps, 2),
                "bandwidth_percent": round(bandwidth_percent, 2),
                "interface": interface_name,
            }

        except Exception as e:
            logger.exception("获取网络速度失败: %s", e)
            return {}

    def get_cpu_os_detailed(self) -> Dict[str, Any]:
        """获取更细粒度CPU/OS指标（尽力而为，跨平台容错）.

        返回:
            {
                "interrupts_per_sec": float|None,
                "context_switches_per_sec": float|None,
                "syscalls_per_sec": float|None,
                "soft_interrupts_per_sec": float|None,
                "steal_time_percent": float|None,
            }
        """
        try:
            if not HAS_PSUTIL:
                return {}

            # 采样两次，估算每秒速率
            cpu_stats_1: Any = getattr(psutil, "cpu_stats", lambda: None)()
            cpu_times_1: Any = psutil.cpu_times() if hasattr(psutil, "cpu_times") else None
            time.sleep(0.1)
            cpu_stats_2: Any = getattr(psutil, "cpu_stats", lambda: None)()
            cpu_times_2: Any = psutil.cpu_times() if hasattr(psutil, "cpu_times") else None

            result: Dict[str, Any] = {}

            if cpu_stats_1 and cpu_stats_2:
                # 字段可能不存在，需容错
                def diff(key: str) -> Optional[int]:
                    try:
                        v1 = getattr(cpu_stats_1, key)
                        v2 = getattr(cpu_stats_2, key)
                        return int(v2 - v1)
                    except Exception:
                        return None

                interrupts = diff("interrupts")
                ctx_switches = diff("ctx_switches")
                syscalls = diff("syscalls")
                soft_interrupts = diff("soft_interrupts")

                scale = 10.0  # 0.1s ↔ 每秒
                result.update(
                    {
                        "interrupts_per_sec": (
                            (interrupts * scale) if interrupts is not None else None
                        ),
                        "context_switches_per_sec": (
                            (ctx_switches * scale) if ctx_switches is not None else None
                        ),
                        "syscalls_per_sec": (syscalls * scale) if syscalls is not None else None,
                        "soft_interrupts_per_sec": (
                            (soft_interrupts * scale) if soft_interrupts is not None else None
                        ),
                    }
                )

            # steal time（仅部分平台提供）
            try:
                if (
                    cpu_times_1
                    and cpu_times_2
                    and hasattr(cpu_times_1, "steal")
                    and hasattr(cpu_times_2, "steal")
                ):
                    steal_delta = float(cpu_times_2.steal - cpu_times_1.steal)
                    # 0.1s 时间窗，转换为百分比估计（近似）
                    result["steal_time_percent"] = max(0.0, min(100.0, (steal_delta / 0.1) * 100.0))
                else:
                    result["steal_time_percent"] = None
            except Exception:
                result["steal_time_percent"] = None

            return result
        except Exception as e:
            logger.exception("获取CPU/OS详细指标失败: %s", e)
            return {}

    def get_memory_subsystem_metrics(self) -> Dict[str, Any]:
        """获取内存子系统指标（尽力而为，跨平台容错）.

        返回:
            {
                "page_faults_per_sec": float|None,
                "swap_in_kbps": float|None,
                "swap_out_kbps": float|None,
                "cache_hit_ratio": float|None,
                "memory_bandwidth_kbps": float|None,
            }
        """
        try:
            if not HAS_PSUTIL:
                return {}

            # 近似：通过 swap_memory  sin/sout（Linux为主）
            swap1: Any = psutil.swap_memory()
            time.sleep(0.1)
            swap2: Any = psutil.swap_memory()

            swap_in_kbps = None
            swap_out_kbps = None
            try:
                if hasattr(swap1, "sin") and hasattr(swap2, "sin"):
                    sin_diff = max(0, int(swap2.sin - swap1.sin))
                    swap_in_kbps = (sin_diff / 0.1) / 1024.0
                if hasattr(swap1, "sout") and hasattr(swap2, "sout"):
                    sout_diff = max(0, int(swap2.sout - swap1.sout))
                    swap_out_kbps = (sout_diff / 0.1) / 1024.0
            except Exception:
                pass

            # page faults（系统级跨平台不可得，返回None）
            # cache 命中率与内存带宽跨平台不可得，返回None
            return {
                "page_faults_per_sec": None,
                "swap_in_kbps": round(swap_in_kbps, 2) if swap_in_kbps is not None else None,
                "swap_out_kbps": round(swap_out_kbps, 2) if swap_out_kbps is not None else None,
                "cache_hit_ratio": None,
                "memory_bandwidth_kbps": None,
            }
        except Exception as e:
            logger.exception("获取内存子系统指标失败: %s", e)
            return {}

    def get_storage_subsystem_metrics(self) -> Dict[str, Any]:
        """获取存储子系统指标（按物理磁盘组织，使用WMI队列深度）."""
        try:
            if not HAS_PSUTIL:
                return {}

            # 获取物理磁盘信息
            physical_disks_info = self.get_physical_disks_info()

            # 获取I/O计数器（用于计算延迟，保留作为紧急熔断指标）
            io1: Any = psutil.disk_io_counters(perdisk=True)
            time.sleep(0.1)
            io2: Any = psutil.disk_io_counters(perdisk=True)

            if not io1 or not io2:
                return {}

            # 按物理磁盘组织数据
            physical_disks: Dict[str, Any] = {}

            for disk_name, disk_info in physical_disks_info.items():
                try:
                    # 在Windows上，psutilkey可能是 "PhysicalDrive0" 或需要映射
                    io_key = None
                    for k in io1.keys():
                        if disk_name.lower() in k.lower() or k.lower() in disk_name.lower():
                            io_key = k
                            break

                    if not io_key or io_key not in io2:
                        # 没有找将对应I/O计数器，使用默认值
                        physical_disks[disk_name] = {
                            "disk_type": disk_info["disk_type"],
                            "is_system_disk": disk_info["is_system_disk"],
                            "partitions": disk_info["partitions"],
                            "average_io_latency_ms": None,
                            "queue_depth": None,
                            "avg_queue_depth": None,
                            "avg_read_size_bytes": None,
                            "avg_write_size_bytes": None,
                        }
                        continue

                    a1 = io1[io_key]
                    a2 = io2[io_key]

                    # 计算I/O操作数
                    read_ios = max(0, a2.read_count - a1.read_count)
                    write_ios = max(0, a2.write_count - a1.write_count)
                    read_bytes = max(0, a2.read_bytes - a1.read_bytes)
                    write_bytes = max(0, a2.write_bytes - a1.write_bytes)

                    # 计算平均I/O延迟（仅作为紧急熔断指标）
                    read_time_ms = getattr(a2, "read_time", 0) - getattr(a1, "read_time", 0)
                    write_time_ms = getattr(a2, "write_time", 0) - getattr(a1, "write_time", 0)
                    io_ops = max(1, read_ios + write_ios)

                    avg_latency_ms = None
                    try:
                        total_time_ms = max(0, read_time_ms + write_time_ms)
                        avg_latency_ms = total_time_ms / float(io_ops)
                    except Exception:
                        avg_latency_ms = None

                    # 计算平均读写大小
                    avg_read_size = (read_bytes / read_ios) if read_ios > 0 else None
                    avg_write_size = (write_bytes / write_ios) if write_ios > 0 else None

                    physical_disks[disk_name] = {
                        "disk_type": disk_info["disk_type"],
                        "is_system_disk": disk_info["is_system_disk"],
                        "partitions": disk_info["partitions"],
                        "average_io_latency_ms": (
                            round(avg_latency_ms, 2) if avg_latency_ms is not None else None
                        ),
                        "queue_depth": None,  # 稍后通过WMI填充
                        "avg_queue_depth": None,  # 稍后通过WMI填充
                        "avg_read_size_bytes": int(avg_read_size) if avg_read_size else None,
                        "avg_write_size_bytes": int(avg_write_size) if avg_write_size else None,
                    }

                except Exception as e:
                    logger.debug("处理磁盘 %s 指标失败: %s", disk_name, e)
                    # 至少返回基本信息
                    physical_disks[disk_name] = {
                        "disk_type": disk_info["disk_type"],
                        "is_system_disk": disk_info["is_system_disk"],
                        "partitions": disk_info["partitions"],
                        "average_io_latency_ms": None,
                        "queue_depth": None,
                        "avg_queue_depth": None,
                        "avg_read_size_bytes": None,
                        "avg_write_size_bytes": None,
                    }

            # 通过WMI获取队列深度（Windows独有）
            if HAS_WMI and platform.system() == "Windows":
                try:
                    c = wmi.WMI()
                    wmi_disks = c.Win32_PerfFormattedData_PerfDisk_PhysicalDisk()

                    for wmi_disk in wmi_disks:
                        if wmi_disk.Name == "_Total":
                            continue

                        # WMIName格式："0 C: D:" 或 "0 C:"
                        # 提取磁盘编号（第一个字符）
                        wmi_name = wmi_disk.Name
                        disk_index = wmi_name.split()[0] if wmi_name else None

                        if disk_index is None:
                            continue

                        # 映射将PhysicalDrive名称
                        physical_drive_name = f"PhysicalDrive{disk_index}"

                        if physical_drive_name in physical_disks:
                            # 获取队列深度
                            current_queue = getattr(wmi_disk, "CurrentDiskQueueLength", None)
                            avg_queue = getattr(wmi_disk, "AvgDiskQueueLength", None)

                            if current_queue is not None:
                                physical_disks[physical_drive_name]["queue_depth"] = float(
                                    current_queue
                                )
                            if avg_queue is not None:
                                physical_disks[physical_drive_name]["avg_queue_depth"] = float(
                                    avg_queue
                                )

                            logger.debug(
                                "WMI队列深度 %s: current=%s, avg=%s",
                                physical_drive_name,
                                current_queue,
                                avg_queue,
                            )

                except Exception as e:
                    logger.debug("WMI获取队列深度失败（将使用None）: %s", e)

            return {"disks": physical_disks}

        except Exception as e:
            logger.exception("获取存储子系统指标失败: %s", e)
            return {}

    def get_network_subsystem_metrics(self) -> Dict[str, Any]:
        """获取网络子系统指标（重传/RTT跨平台不可得，尽力估计丢包率）."""
        try:
            if not HAS_PSUTIL:
                return {}

            n1: Any = psutil.net_io_counters()
            time.sleep(0.1)
            n2: Any = psutil.net_io_counters()
            if not n1 or not n2:
                return {}

            dropin = max(0, getattr(n2, "dropin", 0) - getattr(n1, "dropin", 0))
            dropout = max(0, getattr(n2, "dropout", 0) - getattr(n1, "dropout", 0))
            pin = max(1, getattr(n2, "packets_recv", 0) - getattr(n1, "packets_recv", 0))
            pout = max(1, getattr(n2, "packets_sent", 0) - getattr(n1, "packets_sent", 0))

            loss_in = dropin / float(pin) if pin > 0 else 0.0
            loss_out = dropout / float(pout) if pout > 0 else 0.0

            return {
                "packet_loss_rate_in": round(loss_in * 100, 4),
                "packet_loss_rate_out": round(loss_out * 100, 4),
                "tcp_retransmissions_per_sec": None,  # 无直接跨平台指标
                "rtt_ms": None,  # 不做主动探测
            }
        except Exception as e:
            logger.exception("获取网络子系统指标失败: %s", e)
            return {}

    async def get_network_speed_async(self) -> Dict[str, Any]:
        """获取网络速度和带宽占用 - 异步版本.

        Returns:
            Dict: 网络速度信息，格式:
            {
                "upload_speed_kbps": 1024.5,
                "download_speed_kbps": 5120.8,
                "bandwidth_percent": 45.2,
                "interface": "以太网"
            }
        """
        try:
            if not HAS_PSUTIL:
                return {}

            # 导入asyncio
            import asyncio

            # 获取第一次网络I/O计数
            net_io_1: Any = psutil.net_io_counters()
            await asyncio.sleep(0.1)  # 异步等待100ms
            net_io_2: Any = psutil.net_io_counters()

            if not net_io_1 or not net_io_2:
                return {}

            # 计算上传/下载速度 (字节/秒 -> KB/秒)
            upload_bytes_diff = net_io_2.bytes_sent - net_io_1.bytes_sent
            download_bytes_diff = net_io_2.bytes_recv - net_io_1.bytes_recv

            upload_speed_kbps = (upload_bytes_diff / 0.1) / 1024  # 0.1秒间隔
            download_speed_kbps = (download_bytes_diff / 0.1) / 1024

            # 估算带宽占用百分比（假设1Gbps网卡 = 125MB/s = 128000KB/s）
            # 这里使用一个保守估算
            total_speed_kbps = upload_speed_kbps + download_speed_kbps
            assumed_bandwidth_kbps = 128000  # 1Gbps网卡

            # 尝试获取实际网卡速度
            try:
                net_if_stats = psutil.net_if_stats()
                for interface, stats in net_if_stats.items():
                    if stats.isup and stats.speed > 0:
                        # speed单位是Mbps，转换为KBps
                        assumed_bandwidth_kbps = stats.speed * 1024 / 8
                        break
            except Exception:
                pass

            bandwidth_percent = (
                (total_speed_kbps / assumed_bandwidth_kbps * 100)
                if assumed_bandwidth_kbps > 0
                else 0
            )

            # 获取主要网络接口名称
            interface_name = "未知"
            try:
                net_if_stats = psutil.net_if_stats()
                for interface, stats in net_if_stats.items():
                    if stats.isup:
                        interface_name = interface
                        break
            except Exception:
                pass

            return {
                "upload_speed_kbps": round(upload_speed_kbps, 2),
                "download_speed_kbps": round(download_speed_kbps, 2),
                "bandwidth_percent": round(bandwidth_percent, 2),
                "interface": interface_name,
            }

        except Exception as e:
            logger.exception("获取网络速度失败(异步): %s", e)
            return {}

    def get_process_list(self, sort_by: str = "cpu_percent") -> List[Dict[str, Any]]:
        """获取进程列表."""
        try:
            if not HAS_PSUTIL:
                # 返回默认数据(无psutil时)
                return [
                    {
                        "pid": 1,
                        "name": "python",
                        "cpu_percent": 25.0,
                        "memory_percent": 15.0,
                        "memory_mb": 256.0,
                        "status": "running",
                    },
                    {
                        "pid": 2,
                        "name": "chrome",
                        "cpu_percent": 15.0,
                        "memory_percent": 20.0,
                        "memory_mb": 512.0,
                        "status": "running",
                    },
                    {
                        "pid": 3,
                        "name": "system",
                        "cpu_percent": 5.0,
                        "memory_percent": 10.0,
                        "memory_mb": 128.0,
                        "status": "running",
                    },
                ]

            processes = []

            for proc in psutil.process_iter(
                ["pid", "name", "cpu_percent", "memory_percent", "status"]
            ):
                try:
                    # 使用 cast 来告诉类型检查器 proc 是 Any 类型
                    proc_any: Any = proc
                    proc_info: Any = proc_any.info
                    proc_info["memory_mb"] = proc_any.memory_info().rss / 1024 / 1024
                    processes.append(proc_info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # 排序
            if sort_by in ["cpu_percent", "memory_percent", "memory_mb"]:
                processes.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

            return processes[:50]  # 返回前50个进程
        except (OSError, AttributeError, ImportError) as e:
            logger.error("获取进程列表失败: %s", e)
            return []


class ResourceMonitor:
    """资源监控器."""

    def __init__(
        self,
        threshold_cpu: float = 80.0,
        threshold_memory: float = 80.0,
        threshold_disk: float = 90.0,
    ):
        """初始化资源监控器."""
        self.threshold_cpu = threshold_cpu
        self.threshold_memory = threshold_memory
        self.threshold_disk = threshold_disk
        self.alerts = []

    def check_thresholds(self, usage: ResourceUsage) -> List[Dict[str, Any]]:
        """检查阈值告警."""
        alerts = []

        if usage.cpu_percent > self.threshold_cpu:
            alerts.append(
                {
                    "type": "cpu_high",
                    "level": "warning",
                    "message": f"CPU使用率过高: {usage.cpu_percent:.1f}%",
                    "threshold": self.threshold_cpu,
                    "current": usage.cpu_percent,
                    "timestamp": usage.timestamp,
                }
            )

        if usage.memory_percent > self.threshold_memory:
            alerts.append(
                {
                    "type": "memory_high",
                    "level": "warning",
                    "message": f"内存使用率过高: {usage.memory_percent:.1f}%",
                    "threshold": self.threshold_memory,
                    "current": usage.memory_percent,
                    "timestamp": usage.timestamp,
                }
            )

        if usage.disk_percent > self.threshold_disk:
            alerts.append(
                {
                    "type": "disk_high",
                    "level": "critical",
                    "message": f"磁盘使用率过高: {usage.disk_percent:.1f}%",
                    "threshold": self.threshold_disk,
                    "current": usage.disk_percent,
                    "timestamp": usage.timestamp,
                }
            )

        # 保存告警历史
        self.alerts.extend(alerts)

        return alerts


class HardwareMonitor:
    """硬件监控器."""

    def __init__(self):
        """初始化硬件监控器."""
        pass  # 简化初始化，仅保留WMI方案

    def get_temperature_wmi(self) -> Dict[str, Any]:
        """通过WMI获取温度信息（LibreHardwareMonitor）."""
        # WMI方案（LibreHardwareMonitor）
        try:
            import wmi
            import pythoncom

            # 初始化COM
            pythoncom.CoInitialize()  # type: ignore[attr-defined]

            try:
                # 连接将 LibreHardwareMonitor WMI namespace
                w = wmi.WMI(namespace="root\\LibreHardwareMonitor")
                sensors = w.Sensor()

                temp_info = {}
                for sensor in sensors:
                    if sensor.SensorType == "Temperature":
                        # 提取设备类型（CPU/GPU等）
                        parent = sensor.Parent if hasattr(sensor, "Parent") else "Unknown"
                        device_type = parent.split("/")[-1] if "/" in parent else parent

                        if device_type not in temp_info:
                            temp_info[device_type] = []

                        temp_info[device_type].append(
                            {
                                "label": sensor.Name,
                                "current": round(sensor.Value, 1),
                                "high": (
                                    round(sensor.Max, 1)
                                    if hasattr(sensor, "Max") and sensor.Max
                                    else None
                                ),
                                "critical": None,
                            }
                        )

                return temp_info

            finally:
                pythoncom.CoUninitialize()  # type: ignore[attr-defined]

        except Exception as e:
            logger.debug("WMI温度读取失败: %s", e)
            return {}

    def get_temperature_info(self) -> Dict[str, Any]:
        """获取温度信息（WMI方案）."""
        # 使用WMI方案（LibreHardwareMonitor）
        temp_info = self.get_temperature_wmi()
        if temp_info:
            return temp_info

        # 如果WMI不可用，返回空字典
        return {}

    def get_fan_info(self) -> Dict[str, Any]:
        """获取风扇信息."""
        try:
            if not HAS_PSUTIL:
                return {}

            # 使用try-except处理平台兼容性问题
            try:
                fans = psutil.sensors_fans()  # type: ignore
                fan_info = {}

                for name, entries in fans.items():
                    fan_info[name] = []
                    for entry in entries:
                        fan_info[name].append(
                            {
                                "label": entry.label or "Unknown",
                                "current": entry.current,
                            }
                        )

                return fan_info
            except AttributeError:
                logger.warning("当前平台不支持风扇传感器")
                return {}

        except (OSError, ImportError) as e:
            logger.warning("获取风扇信息失败(可能不支持): %s", e)
            return {}

    def get_battery_info(self) -> Dict[str, Any]:
        """获取电池信息."""
        try:
            battery = psutil.sensors_battery()
            if battery:
                return {
                    "percent": battery.percent,
                    "secsleft": battery.secsleft,
                    "power_plugged": battery.power_plugged,
                }
            return {}
        except (OSError, AttributeError, ImportError) as e:
            logger.warning("获取电池信息失败(可能不支持): %s", e)
            return {}


# =============================================================================
# 进程监控器
# =============================================================================


class ProcessMonitor:
    """进程监控器 - 自动识别和监控关键进程."""

    def __init__(self):
        """初始化进程监控器."""
        self.logger = logging.getLogger(__name__)

        # 进程识别关键词
        self.process_keywords = {
            "download": ["download", "fetch", "mootdx", "股票下载", "数据下载"],
            "data_io": ["tdx_reader", "data_io", "数据读取", "数据保存", "TdxReader"],
            "backtest": ["backtest", "BacktestEngine", "回测", "策略回测"],
            "trading": ["trading", "send_order", "TradingEngine", "交易执行", "下单"],
        }

        # 进程指标历史（用于计算速率）
        self._metrics_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._lock = threading.Lock()

        # 缓存主进程信息
        if HAS_PSUTIL:
            self._main_process = psutil.Process()
            self._last_disk_io: Optional[sdiskio] = psutil.disk_io_counters()  # type: ignore[assignment]
            self._last_net_io: Optional[snetio] = psutil.net_io_counters()  # type: ignore[assignment]
            self._last_check_time = time.time()

            # 🚀 性能优化：初始化CPU采样（建立baseline）
            # 第一次调用cpu_percent()建立基线，后续调用interval=None才有意义
            try:
                self._main_process.cpu_percent(interval=None)
            except Exception:
                pass

    def identify_processes(self) -> List[Dict[str, Any]]:
        """识别所有关键进程.

        Returns:
            List: 进程信息列表
        """
        processes = []

        try:
            # 1. 识别当前进程所有线程
            threads = []
            for thread in threading.enumerate():
                thread_info = {
                    "id": f"thread_{thread.ident}",
                    "name": thread.name,
                    "type": self._identify_process_type(thread.name),
                    "is_alive": thread.is_alive(),
                }
                threads.append(thread_info)
                processes.append(thread_info)

            # 2. 识别子进程（如果有）
            if HAS_PSUTIL:
                try:
                    children = self._main_process.children(recursive=True)
                    for child in children:
                        try:
                            child_info = {
                                "id": f"process_{child.pid}",
                                "name": child.name(),
                                "type": self._identify_process_type(child.name()),
                                "is_alive": child.is_running(),
                            }
                            processes.append(child_info)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                except Exception as e:
                    self.logger.debug("获取子进程失败: %s", e)

            self.logger.debug("识别将 %d 个进程", len(processes))
            return processes

        except Exception as e:
            self.logger.exception("识别进程失败: %s", e)
            return []

    def _identify_process_type(self, process_name: str) -> str:
        """根据进程名称识别进程类型.

        Args:
            process_name: 进程/线程名称

        Returns:
            str: 进程类型
        """
        name_lower = process_name.lower()

        for process_type, keywords in self.process_keywords.items():
            for keyword in keywords:
                if keyword.lower() in name_lower:
                    return process_type

        return "unknown"

    def get_process_metrics(
        self, process_id: str, process_name: str = "", process_type: str = ""
    ) -> Optional[ProcessMetrics]:
        """获取进程性能指标.

        Args:
            process_id: 进程ID
            process_name: 进程名称
            process_type: 进程类型

        Returns:
            Optional[ProcessMetrics]: 进程指标，如果获取失败返回None
        """
        if not HAS_PSUTIL:
            return None

        try:
            current_time = time.time()
            time_delta = current_time - self._last_check_time

            if time_delta < 0.1:  # 避免频繁采集
                time_delta = 0.1

            # 获取CPU和内存指标
            # 🚀 性能优化：使用interval=None（非阻塞模式）
            # interval=0.1会阻塞线程0.1秒，在高频监控时会严重影响性能
            # None或0表示返回自上次调用以来CPU使用率，不阻塞
            cpu_percent = self._main_process.cpu_percent(interval=None)
            memory_info = self._main_process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            memory_percent = self._main_process.memory_percent()

            # 获取磁盘IO指标
            disk_read_mbps = 0.0
            disk_write_mbps = 0.0
            try:
                current_disk_io: Optional[sdiskio] = psutil.disk_io_counters()  # type: ignore[assignment]
                if current_disk_io and self._last_disk_io:
                    read_bytes = current_disk_io.read_bytes - self._last_disk_io.read_bytes
                    write_bytes = current_disk_io.write_bytes - self._last_disk_io.write_bytes
                    disk_read_mbps = (read_bytes / time_delta) / (1024 * 1024)
                    disk_write_mbps = (write_bytes / time_delta) / (1024 * 1024)
                    self._last_disk_io = current_disk_io  # type: ignore[assignment]
            except Exception as e:
                self.logger.debug("获取磁盘IO失败: %s", e)

            # 获取网络IO指标
            network_recv_mbps = 0.0
            network_send_mbps = 0.0
            try:
                current_net_io: Optional[snetio] = psutil.net_io_counters()  # type: ignore[assignment]
                if current_net_io and self._last_net_io:
                    recv_bytes = current_net_io.bytes_recv - self._last_net_io.bytes_recv
                    sent_bytes = current_net_io.bytes_sent - self._last_net_io.bytes_sent
                    network_recv_mbps = (recv_bytes / time_delta) / (1024 * 1024)
                    network_send_mbps = (sent_bytes / time_delta) / (1024 * 1024)
                    self._last_net_io = current_net_io  # type: ignore[assignment]
            except Exception as e:
                self.logger.debug("获取网络IO失败: %s", e)

            self._last_check_time = current_time

            # 确定进程状态
            status = "running" if cpu_percent > 1.0 else "idle"

            metrics = ProcessMetrics(
                process_id=process_id,
                process_name=process_name,
                process_type=process_type,
                status=status,
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                memory_percent=memory_percent,
                disk_read_mbps=disk_read_mbps,
                disk_write_mbps=disk_write_mbps,
                network_recv_mbps=network_recv_mbps,
                network_send_mbps=network_send_mbps,
                timestamp=datetime.now(),
            )

            # 保存历史数据
            with self._lock:
                history = self._metrics_history[process_id]
                history.append(
                    {
                        "timestamp": current_time,
                        "cpu": cpu_percent,
                        "memory": memory_mb,
                        "disk_read": disk_read_mbps,
                        "disk_write": disk_write_mbps,
                        "network_recv": network_recv_mbps,
                        "network_send": network_send_mbps,
                    }
                )
                # 只保留最近100个数据点
                if len(history) > 100:
                    history.pop(0)

            return metrics

        except Exception as e:
            self.logger.exception("获取进程指标失败 [%s]: %s", process_id, e)
            return None

    def monitor_process(
        self, process_id: str, process_name: str, process_type: str
    ) -> Optional[ProcessMetrics]:
        """持续监控单个进程（简化版，返回当前指标）.

        Args:
            process_id: 进程ID
            process_name: 进程名称
            process_type: 进程类型

        Returns:
            Optional[ProcessMetrics]: 当前进程指标
        """
        return self.get_process_metrics(process_id, process_name, process_type)

    def get_metrics_history(self, process_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取进程指标历史数据.

        Args:
            process_id: 进程ID
            limit: 返回数量限制

        Returns:
            List: 历史数据列表
        """
        with self._lock:
            history = self._metrics_history.get(process_id, [])
            return history[-limit:]


class ProcessBottleneckAnalyzer:
    """进程级瓶颈分析器 - 采用"最短木板"原理识别进程瓶颈."""

    def __init__(self):
        """初始化瓶颈分析器."""
        self.logger = logging.getLogger(__name__)

        # 理论最大值（用于计算使用率）
        self.theoretical_limits = {
            "cpu_percent": 100.0,  # CPU使用率上限
            "memory_percent": 100.0,  # 内存使用率上限
            "disk_io_mbps": 150.0,  # 假设HDD写入速度上限150MB/s（SSD会更高）
            "network_mbps": 100.0,  # 假设千兆网络理论速度100MB/s
        }

        # 瓶颈阈值（超过此值认为存在瓶颈）
        self.bottleneck_thresholds = {
            "cpu": 70.0,
            "memory": 70.0,
            "disk_io": 60.0,  # 磁盘IO更容易成为瓶颈
            "network": 50.0,
        }

    def analyze_download_process(self, metrics: ProcessMetrics) -> BottleneckResult:
        """分析数据下载进程瓶颈.

        数据下载关注：网络速度 vs 磁盘IO写入速度
        """
        return self.find_bottleneck(metrics, focus_areas=["network", "disk_io"])

    def analyze_data_io_process(self, metrics: ProcessMetrics) -> BottleneckResult:
        """分析数据读写进程瓶颈.

        数据读写关注：磁盘IO vs CPU解析 vs 内存缓冲
        """
        return self.find_bottleneck(metrics, focus_areas=["disk_io", "cpu", "memory"])

    def analyze_backtest_process(self, metrics: ProcessMetrics) -> BottleneckResult:
        """分析回测进程瓶颈.

        回测关注：CPU计算 vs 内存访问 vs 数据IO
        """
        return self.find_bottleneck(metrics, focus_areas=["cpu", "memory", "disk_io"])

    def analyze_trading_process(self, metrics: ProcessMetrics) -> BottleneckResult:
        """分析交易执行进程瓶颈.

        交易执行关注：网络延迟 vs CPU处理时间
        """
        return self.find_bottleneck(metrics, focus_areas=["network", "cpu"])

    def find_bottleneck(
        self,
        metrics: ProcessMetrics,
        focus_areas: Optional[List[str]] = None,
    ) -> BottleneckResult:
        """通用瓶颈识别 - 找将限制进程速度"最短木板".

        Args:
            metrics: 进程指标
            focus_areas: 关注领域列表，None表示关注所有领域

        Returns:
            BottleneckResult: 瓶颈分析结果
        """
        if focus_areas is None:
            focus_areas = ["cpu", "memory", "disk_io", "network"]

        # 计算各项指标使用率（相对于理论最大值）
        usage_rates: dict[str, float] = {}

        if "cpu" in focus_areas:
            usage_rates["cpu"] = min(metrics.cpu_percent, 100.0)

        if "memory" in focus_areas:
            usage_rates["memory"] = min(metrics.memory_percent, 100.0)

        if "disk_io" in focus_areas:
            # 磁盘IO取读写速度最大值
            max_disk_speed = max(metrics.disk_read_mbps, metrics.disk_write_mbps)
            disk_usage_percent = (max_disk_speed / self.theoretical_limits["disk_io_mbps"]) * 100
            usage_rates["disk_io"] = min(disk_usage_percent, 100.0)

        if "network" in focus_areas:
            # 网络取收发速度最大值
            max_network_speed = max(metrics.network_recv_mbps, metrics.network_send_mbps)
            network_usage_percent = (
                max_network_speed / self.theoretical_limits["network_mbps"]
            ) * 100
            usage_rates["network"] = min(network_usage_percent, 100.0)

        # 找出使用率最高项（最短木板）
        if not usage_rates:
            # 没有可分析指标
            return BottleneckResult(
                process_id=metrics.process_id,
                process_name=metrics.process_name,
                process_type=metrics.process_type,
                bottleneck="balanced",
                bottleneck_percent=0.0,
                details="暂无足够数据进行分析",
                suggestion="继续监控以收集更多数据",
                metrics=metrics,
            )

        bottleneck_type = max(usage_rates, key=lambda x: usage_rates.get(x, 0.0))
        bottleneck_percent = usage_rates[bottleneck_type]

        # 判断是否真存在瓶颈
        threshold = self.bottleneck_thresholds.get(bottleneck_type, 70.0)

        if bottleneck_percent < threshold:
            # 所有指标都未达将瓶颈阈值，系统均衡
            return BottleneckResult(
                process_id=metrics.process_id,
                process_name=metrics.process_name,
                process_type=metrics.process_type,
                bottleneck="balanced",
                bottleneck_percent=max(usage_rates.values()),
                details=f"系统运行均衡，最高使用率为 {max(usage_rates.values()):.1f}%",
                suggestion="系统运行良好，继续保持",
                metrics=metrics,
            )

        # 生成详细描述和建议
        details, suggestion = self._generate_bottleneck_info(
            bottleneck_type, bottleneck_percent, metrics
        )

        return BottleneckResult(
            process_id=metrics.process_id,
            process_name=metrics.process_name,
            process_type=metrics.process_type,
            bottleneck=bottleneck_type,
            bottleneck_percent=bottleneck_percent,
            details=details,
            suggestion=suggestion,
            metrics=metrics,
        )

    def _generate_bottleneck_info(
        self, bottleneck_type: str, percent: float, metrics: ProcessMetrics
    ) -> tuple:
        """生成瓶颈详细信息和优化建议.

        Args:
            bottleneck_type: 瓶颈类型
            percent: 使用率百分比
            metrics: 进程指标

        Returns:
            tuple: (详细描述, 优化建议)
        """
        if bottleneck_type == "cpu":
            details = f"CPU使用率达将 {metrics.cpu_percent:.1f}%，处理器计算能力已接近极限"
            suggestion = (
                "建议：1) 优化算法降低计算复杂度 2) 启用多进程并行处理 3) 使用缓存减少重复计算"
            )

        elif bottleneck_type == "memory":
            details = f"内存使用率达将 {metrics.memory_percent:.1f}%，内存容量不足"
            suggestion = "建议：1) 启用数据分页加载 2) 及时释放不用对象 3) 使用生成器代替列表 4) 扩展物理内存"

        elif bottleneck_type == "disk_io":
            max_speed = max(metrics.disk_read_mbps, metrics.disk_write_mbps)
            io_type = "写入" if metrics.disk_write_mbps > metrics.disk_read_mbps else "读取"
            details = f"磁盘IO{io_type}速度达将 {max_speed:.1f}MB/s，磁盘吞吐量已接近极限"
            suggestion = (
                "建议：1) 使用SSD固态硬盘替代机械硬盘 2) 启用批量读写减少IO次数 3) 使用异步IO操作"
            )

        elif bottleneck_type == "network":
            max_speed = max(metrics.network_recv_mbps, metrics.network_send_mbps)
            net_type = "下载" if metrics.network_recv_mbps > metrics.network_send_mbps else "上传"
            details = f"网络{net_type}速度达将 {max_speed:.1f}MB/s，网络带宽已接近极限"
            suggestion = (
                "建议：1) 升级网络带宽 2) 启用数据压缩 3) 使用多线程并发下载 4) 优化网络请求策略"
            )

        else:
            details = f"检测将瓶颈：{bottleneck_type} ({percent:.1f}%)"
            suggestion = "建议查看详细日志以获取更多信息"

        return details, suggestion

    def analyze_by_type(self, metrics: ProcessMetrics) -> BottleneckResult:
        """根据进程类型自动选择分析方法.

        Args:
            metrics: 进程指标

        Returns:
            BottleneckResult: 瓶颈分析结果
        """
        if metrics.process_type == "download":
            return self.analyze_download_process(metrics)
        elif metrics.process_type == "data_io":
            return self.analyze_data_io_process(metrics)
        elif metrics.process_type == "backtest":
            return self.analyze_backtest_process(metrics)
        elif metrics.process_type == "trading":
            return self.analyze_trading_process(metrics)
        else:
            # 未知类型，使用通用分析
            return self.find_bottleneck(metrics)


# =============================================================================
# 独立监控进程
# =============================================================================


class MonitoringProcess:
    """监控进程主类 - 独立进程，通过ZeroMQ与主进程通信."""

    def __init__(self):
        """初始化监控进程."""
        self.running = False
        self.interval = 2  # 推送间隔（秒）
        self.latest_service_status = {}

        # ZeroMQ上下文
        self.context = zmq.asyncio.Context()

        # PULL socket：接收服务状态
        self.pull_socket = self.context.socket(zmq.PULL)
        self.pull_socket.bind("tcp://127.0.0.1:5555")
        self.pull_socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms超时

        # REP socket：响应监控数据查询
        self.rep_socket = self.context.socket(zmq.REP)
        self.rep_socket.bind("tcp://127.0.0.1:5557")
        self.rep_socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms超时

        # 缓存最新监控数据
        self.cached_data = {"system": {}, "process": {}, "service": {}}

        # 创建监控工具
        self.system_monitor = SystemMonitor()
        self.process_monitor = ProcessMonitor()
        self.bottleneck_analyzer = ProcessBottleneckAnalyzer()

        logger.info("监控进程初始化完成")
        logger.info("  - PULL端口: tcp://127.0.0.1:5555（接收服务状态）")
        logger.info("  - REP端口: tcp://127.0.0.1:5557（响应数据查询）")

    def start(self):
        """启动监控循环（使用Poller持续监听）."""
        self.running = True
        logger.info("监控进程启动，推送间隔: %d秒", self.interval)

        # 创建Poller同时监听多个socket
        poller = zmq.Poller()
        poller.register(self.rep_socket, zmq.POLLIN)  # 监听查询请求
        poller.register(self.pull_socket, zmq.POLLIN)  # 监听服务状态

        last_collect_time = 0

        try:
            while self.running:
                current_time = time.time()

                # 1. 检查是否需要采集数据（定时）
                if current_time - last_collect_time >= self.interval:
                    logger.debug("开始采集监控数据...")

                    # 采集系统指标
                    system_metrics = self._collect_system_metrics()

                    # 采集进程指标
                    process_metrics = self._collect_process_metrics()

                    # 更新缓存
                    self.cached_data = {
                        "system": system_metrics,
                        "process": process_metrics,
                        "service": self.latest_service_status,
                    }

                    last_collect_time = current_time
                    logger.debug("监控数据已更新")

                # 2. 非阻塞检查socket事件（100ms超时）
                # 这样可以持续处理查询请求，而不会错过
                socks = dict(poller.poll(100))

                # 3. 处理服务状态更新
                if self.pull_socket in socks:
                    try:
                        message = self.pull_socket.recv_json(zmq.NOBLOCK)
                        self.latest_service_status = message
                        logger.debug("收到服务状态更新")
                    except zmq.Again:
                        pass
                    except Exception as e:
                        logger.exception("接收服务状态失败: %s", e)

                # 4. 处理查询请求（持续监听，不会错过）
                if self.rep_socket in socks:
                    try:
                        _ = self.rep_socket.recv_json(zmq.NOBLOCK)
                        self.rep_socket.send_json(self.cached_data, zmq.NOBLOCK)
                        logger.debug("已响应监控数据查询")
                    except zmq.Again:
                        pass
                    except Exception as e:
                        logger.exception("处理查询失败: %s", e)

        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")
        except Exception as e:
            logger.error("监控进程异常: %s", e, exc_info=True)
        finally:
            self.stop()

    def _collect_system_metrics(self) -> Dict[str, Any]:
        """采集系统指标（包含温度）."""
        try:
            resource_usage = self.system_monitor.get_resource_usage()
            disk_io_speed = self.system_monitor.get_disk_io_speed()
            network_speed = self.system_monitor.get_network_speed()

            # 获取硬件温度信息
            hardware_monitor = HardwareMonitor()
            temperature_info = hardware_monitor.get_temperature_info()

            return {
                "timestamp": datetime.now().isoformat(),
                "cpu_percent": resource_usage.cpu_percent,
                "memory_percent": resource_usage.memory_percent,
                "disk_percent": resource_usage.disk_percent,
                "network_sent": resource_usage.network_sent,
                "network_recv": resource_usage.network_recv,
                "process_count": resource_usage.process_count,
                "load_average": resource_usage.load_average,
                "disk_io_speed": disk_io_speed,
                "network_speed": network_speed,
                "temperature": temperature_info,  # 🌡️ 新增：温度信息
            }
        except Exception as e:
            logger.error("采集系统指标失败: %s", e)
            return {}

    def _collect_process_metrics(self) -> Dict[str, Any]:
        """采集进程指标."""
        try:
            # 识别所有进程
            all_processes = self.process_monitor.identify_processes()

            # 只保留Python相关进程
            python_processes = [
                p
                for p in all_processes
                if p.get("type") in ["python", "trading", "download", "backtest"]
            ]

            # 瓶颈分析（简化版）
            bottlenecks = []
            for proc in python_processes[:5]:  # 只分析前5个进程
                try:
                    metrics = self.process_monitor.get_process_metrics(
                        proc.get("id", ""), proc.get("name", ""), proc.get("type", "")
                    )
                    if metrics:
                        result = self.bottleneck_analyzer.find_bottleneck(metrics)
                        if result.has_bottleneck:
                            bottlenecks.append(
                                {
                                    "pid": proc.get("id"),
                                    "name": proc.get("name"),
                                    "type": result.bottleneck,
                                    "info": result.details,
                                }
                            )
                except Exception:
                    pass

            return {
                "timestamp": datetime.now().isoformat(),
                "python_processes": python_processes[:10],  # 只取前10个
                "bottlenecks": bottlenecks,
                "process_count": len(python_processes),
            }
        except Exception as e:
            logger.exception("采集进程指标失败: %s", e)
            return {}

    def stop(self):
        """停止监控进程."""
        self.running = False
        self.pull_socket.close()
        self.rep_socket.close()
        self.context.term()
        logger.info("监控进程已停止")


# =============================================================================
# 便捷函数
# =============================================================================


def get_system_info() -> SystemInfo:
    """获取系统信息."""
    monitor = SystemMonitor()
    return monitor.get_system_info()


def get_resource_usage() -> ResourceUsage:
    """获取资源使用情况."""
    monitor = SystemMonitor()
    return monitor.get_resource_usage()


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    # 数据类
    "SystemInfo",
    "ResourceUsage",
    "ProcessMetrics",
    "BottleneckResult",
    # 系统监控
    "SystemMonitor",
    "ResourceMonitor",
    "HardwareMonitor",
    # 进程监控
    "ProcessMonitor",
    "ProcessBottleneckAnalyzer",  # 重命名
    # 独立监控进程
    "MonitoringProcess",
    # 业务指标采集
    "BusinessMetricsCollector",
    "get_business_metrics_collector",
    # 便捷函数
    "get_system_info",
    "get_resource_usage",
]


# =============================================================================
# 业务指标采集器（从 business_metrics_collector.py 合并）
# =============================================================================


class BusinessMetricsCollector:
    """业务指标采集器（从 business_metrics_collector.py 合并）.

    接收各业务服务（data_center_service, trading_gateway_service等）
    推送业务指标，存储在内存队列中，提供统计摘要。

    TODO: 后续优化
    1. 实现时序数据库存储（InfluxDB/Prometheus）
    2. 在各业务服务中埋点并推送指标
    3. 实现P95/P99等统计指标
    """

    def __init__(self, window_size: int = 300):
        """初始化业务指标采集器.

        Args:
            window_size: 时间窗口大小（秒），默认5分钟
        """
        self.logger = logging.getLogger(__name__)
        self.window_size = window_size

        # 指标存储：{metric_type: deque[(timestamp, value, metadata)]}
        self._metrics_storage: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._lock = threading.Lock()

        # 并发任务计数器
        self._concurrent_tasks: Dict[str, int] = {
            "download": 0,
            "backtest": 0,
            "trading": 0,
            "total": 0,
        }
        self._task_lock = threading.Lock()

        self.logger.info("业务指标采集器已初始化，窗口大小: %d秒", window_size)

    def record_metric(self, metric_type: str, value: float, metadata: Optional[Dict] = None):
        """记录业务指标.

        Args:
            metric_type: 指标类型，如 'event_queue_depth', 'order_response_time_ms'
            value: 指标值
            metadata: 额外元数据（可选），如 {'gateway': 'ctp', 'symbol': 'IF2401'}

        Examples:
            >>> collector.record_metric('event_queue_depth', 1500)
            >>> collector.record_metric('order_response_time_ms', 250, {'gateway': 'ctp'})
        """
        timestamp = time.time()

        with self._lock:
            self._metrics_storage[metric_type].append((timestamp, value, metadata or {}))

        # 暂时只记录日志
        self.logger.debug("记录业务指标: %s = %.2f, metadata=%s", metric_type, value, metadata)

    def increment_task(self, task_type: str = "total"):
        """增加任务计数.

        Args:
            task_type: 任务类型 ("download", "backtest", "trading", "total")
        """
        with self._task_lock:
            if task_type in self._concurrent_tasks:
                self._concurrent_tasks[task_type] += 1
            self._concurrent_tasks["total"] += 1

    def decrement_task(self, task_type: str = "total"):
        """减少任务计数.

        Args:
            task_type: 任务类型 ("download", "backtest", "trading", "total")
        """
        with self._task_lock:
            if task_type in self._concurrent_tasks:
                self._concurrent_tasks[task_type] = max(0, self._concurrent_tasks[task_type] - 1)
            self._concurrent_tasks["total"] = max(0, self._concurrent_tasks["total"] - 1)

    def get_concurrent_tasks(self) -> Dict[str, int]:
        """获取当前并发任务数.

        Returns:
            {"download": 0, "backtest": 0, "trading": 0, "total": 0}
        """
        with self._task_lock:
            return self._concurrent_tasks.copy()

    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取业务指标摘要.

        Returns:
            {
                "event_queue_depth": {
                    "current": 150,
                    "avg": 120,
                    "max": 500,
                    "p95": 350,
                    "sample_count": 300
                },
                "order_response_time_ms": {
                    ...
                },
                ...
            }
        """
        summary = {}
        current_time = time.time()
        window_start = current_time - self.window_size

        with self._lock:
            for metric_type, data_queue in self._metrics_storage.items():
                # 过滤时间窗口
                windowed_data = [
                    (ts, val, meta) for ts, val, meta in data_queue if ts >= window_start
                ]

                if not windowed_data:
                    continue

                values = [val for _, val, _ in windowed_data]

                # 计算P95/P99（纯Python实现）
                sorted_values = sorted(values)
                n = len(sorted_values)
                p95_index = int(n * 0.95) if n > 0 else 0
                p99_index = int(n * 0.99) if n > 0 else 0

                summary[metric_type] = {
                    "current": values[-1] if values else 0,
                    "avg": sum(values) / len(values) if values else 0,
                    "max": max(values) if values else 0,
                    "min": min(values) if values else 0,
                    "sample_count": len(values),
                    "p95": sorted_values[p95_index] if sorted_values else 0,
                    "p99": sorted_values[p99_index] if sorted_values else 0,
                }

        return summary

    def get_latest_value(self, metric_type: str, default: float = 0) -> float:
        """获取指定指标最新值.

        Args:
            metric_type: 指标类型
            default: 默认值（如果没有数据）

        Returns:
            最新指标值，如果没有数据则返回default

        Examples:
            >>> collector.get_latest_value('event_queue_depth', default=0)
            150
        """
        with self._lock:
            data_queue = self._metrics_storage.get(metric_type)
            if not data_queue or len(data_queue) == 0:
                return default

            # 返回最新值（队列最后一个元素）
            _, latest_value, _ = data_queue[-1]
            return latest_value

    def get_metric_history(self, metric_type: str, duration_sec: int = 60) -> List[Dict[str, Any]]:
        """获取指定指标历史数据.

        Args:
            metric_type: 指标类型
            duration_sec: 时间范围（秒）

        Returns:
            [
                {"timestamp": 1234567890.0, "value": 150, "metadata": {...}},
                ...
            ]
        """
        history = []
        current_time = time.time()
        start_time = current_time - duration_sec

        with self._lock:
            if metric_type in self._metrics_storage:
                for ts, val, meta in self._metrics_storage[metric_type]:
                    if ts >= start_time:
                        history.append(
                            {
                                "timestamp": ts,
                                "value": val,
                                "metadata": meta,
                            }
                        )

        return history

    def clear_metrics(self, metric_type: Optional[str] = None):
        """清理指标数据.

        Args:
            metric_type: 指定指标类型，None表示清理所有
        """
        with self._lock:
            if metric_type:
                if metric_type in self._metrics_storage:
                    self._metrics_storage[metric_type].clear()
                    self.logger.info("已清理指标: %s", metric_type)
            else:
                self._metrics_storage.clear()
                self.logger.info("已清理所有业务指标")


# 全局单例
_business_metrics_collector_instance: Optional[BusinessMetricsCollector] = None
_collector_lock = threading.Lock()


def get_business_metrics_collector() -> BusinessMetricsCollector:
    """获取业务指标采集器全局单例."""
    global _business_metrics_collector_instance
    if _business_metrics_collector_instance is None:
        with _collector_lock:
            if _business_metrics_collector_instance is None:
                _business_metrics_collector_instance = BusinessMetricsCollector()
    return _business_metrics_collector_instance


__all__ = [
    # 从 monitor_core.py (Part 1-6)
    "MonitoringProcessV2",
    "AdaptiveThresholdManager",
    "SmartMonitor",
    "HardwareMonitorFactory",
    "ThresholdConfig",
    "ThresholdResult",
    "DiskSmartData",
    "SystemBottleneckAnalyzer",
    "ScenarioAnalyzer",
    # 从 monitors.py (Part 7-10)
    "SystemInfo",
    "ResourceUsage",
    "ProcessMetrics",
    "BottleneckResult",
    "SystemMonitor",
    "ResourceMonitor",
    "HardwareMonitor",
    "ProcessMonitor",
    "ProcessBottleneckAnalyzer",
    "MonitoringProcess",
    "BusinessMetricsCollector",
    "get_system_info",
    "get_resource_usage",
    "get_business_metrics_collector",
]


# =============================================================================
# Part 4: 独立进程入口（合并自 monitor_process_entry.py）
# =============================================================================


def main():
    """监控进程入口函数（可作为独立进程运行）."""
    import logging
    import sys

    # 配置日志（仅Terminal输出）
    # 确保stdout使用UTF-8编码（Python 3.7+）
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    stream_handler = logging.StreamHandler(sys.stdout)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[stream_handler],
    )
    logger = logging.getLogger("MonitorProcess")

    logger.info("=" * 60)
    logger.info("独立监控进程启动（V2 - 混合并发架构）")
    logger.info("=" * 60)

    try:
        import asyncio
        import os
        import platform

        # Windows需要使用SelectorEventLoop以支持ZMQ asyncio
        if platform.system() == "Windows":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            logger.info("✅ 已设置Windows SelectorEventLoop策略")

        logger.info("正在创建MonitoringProcessV2实例...")

        # 获取父进程PID（主应用的PID）
        parent_pid = os.getppid()
        logger.info(
            f"[PARENT-PID] 父进程PID（主应用）: {parent_pid}, 当前进程PID（监控进程）: {os.getpid()}"
        )

        monitor = MonitoringProcessV2(parent_pid=parent_pid)
        logger.info("✅ MonitoringProcessV2实例创建成功")

        logger.info("正在启动监控进程主循环...")
        # 创建新的事件循环并使用当前策略
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(monitor.start())
        finally:
            loop.close()

    except KeyboardInterrupt:
        logger.info("收到中断信号")
    except Exception as e:
        logger.error("❌ 监控进程启动失败: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
