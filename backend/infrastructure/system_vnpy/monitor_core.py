# -*- coding: utf-8 -*-
"""监控进程核心模块 - 完整合并版（debug友好）.

本文件包含监控进程V2的所有核心组件，方便调试时：
1. 单文件设置断点，查看完整调用栈
2. 快速定位问题所在模块
3. 理解组件间的协作关系

包含模块：
├── Part 1: 数据结构和配置
├── Part 2: 自适应阈值管理器
├── Part 3: 硬盘SMART监控
├── Part 4: 硬件监控器工厂
└── Part 5: 监控进程V2主类（混合并发架构）

作者提示：调试时优先在以下位置设置断点
- MonitoringProcessV2.start() - 进程启动入口
- MonitoringProcessV2._evaluate_alerts() - 告警评估
- AdaptiveThresholdManager._update_threshold() - 阈值更新
- SmartMonitor.get_smart_data() - SMART采集
"""

import asyncio
import json
import logging
import platform
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import zmq
import zmq.asyncio

logger = logging.getLogger(__name__)


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


@dataclass
class SmartAttribute:
    """SMART属性."""

    id: int
    name: str
    value: int
    worst: int
    threshold: int
    raw_value: int
    status: str


@dataclass
class DiskSmartData:
    """硬盘SMART数据."""

    disk_name: str
    model: str
    serial: str
    capacity: str
    interface: str
    assessment: str
    temperature: Optional[int]
    power_on_hours: Optional[int]
    reallocated_sectors: Optional[int]
    pending_sectors: Optional[int]
    uncorrectable_errors: Optional[int]
    attributes: List[SmartAttribute]
    timestamp: datetime


# =============================================================================
# Part 2: 自适应阈值管理器
# =============================================================================


class AdaptiveThresholdManager:
    """自适应阈值管理器 - 基于滑动窗口的统计学习."""

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
        """获取所有指标的动态阈值.

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
            logger.error("计算统计量失败 (%s): %s", metric_name, e)
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

        logger.info(
            "更新阈值 [%s]: warning=%.2f, critical=%.2f (样本=%d)",
            metric_name,
            warning_threshold or 0,
            critical_threshold or 0,
            sample_count,
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
            logger.error("保存阈值到数据库失败: %s", e)

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
            logger.error("从数据库加载阈值失败: %s", e)


# =============================================================================
# Part 3: 硬盘SMART监控
# =============================================================================


class SmartMonitor:
    """硬盘SMART监控器 - 使用pySMART库."""

    def __init__(self):
        self._has_pysmart = False
        self._Device = None
        try:
            from pySMART import Device  # type: ignore

            self._Device = Device
            self._has_pysmart = True
            logger.info("✅ pySMART 可用")
        except ImportError:
            logger.warning("pySMART 未安装，SMART监控不可用")
        except Exception as e:
            logger.warning("pySMART 初始化失败: %s", e)

    def is_available(self) -> bool:
        return self._has_pysmart

    def get_smart_data(self) -> Dict[str, DiskSmartData]:
        if not self._has_pysmart:
            return {}
        result = {}
        try:
            disks = self._get_disk_list()
            for disk_name in disks:
                try:
                    smart_data = self._read_disk_smart(disk_name)
                    if smart_data:
                        result[disk_name] = smart_data
                except Exception as e:
                    logger.error("读取硬盘SMART失败 (%s): %s", disk_name, e)
            logger.info("成功读取 %d 个硬盘的SMART数据", len(result))
        except Exception as e:
            logger.error("获取硬盘列表失败: %s", e)
        return result

    def _get_disk_list(self) -> List[str]:
        if not self._Device:
            return []

        system = platform.system()
        if system == "Windows":
            disks = []
            for i in range(10):
                disk_name = f"/dev/pd{i}"
                try:
                    device = self._Device(disk_name)
                    if device and device.name:
                        disks.append(disk_name)
                except Exception:
                    break
            return disks
        elif system == "Linux":
            disks = []
            for letter in "abcdefghijklmnopqrstuvwxyz":
                disk_name = f"/dev/sd{letter}"
                try:
                    device = self._Device(disk_name)
                    if device and device.name:
                        disks.append(disk_name)
                except Exception:
                    continue
            return disks
        return []

    def _read_disk_smart(self, disk_name: str) -> Optional[DiskSmartData]:
        if not self._Device:
            return None

        try:
            device = self._Device(disk_name)
            if not device:
                return None

            model = str(device.model) if device.model else "Unknown"
            serial = str(device.serial) if device.serial else "Unknown"
            capacity = str(device.capacity) if device.capacity else "Unknown"
            interface = str(device.interface) if device.interface else "Unknown"
            assessment = str(device.assessment) if device.assessment else "UNKNOWN"

            temperature = None
            power_on_hours = None
            reallocated_sectors = None
            pending_sectors = None
            uncorrectable_errors = None
            attributes = []

            if device.attributes and hasattr(device.attributes, "items"):
                for attr_id, attr in device.attributes.items():  # type: ignore
                    try:
                        smart_attr = SmartAttribute(
                            id=int(attr_id),
                            name=str(attr.name) if hasattr(attr, "name") else f"Attr_{attr_id}",
                            value=int(attr.value) if hasattr(attr, "value") else 0,
                            worst=int(attr.worst) if hasattr(attr, "worst") else 0,
                            threshold=int(attr.thresh) if hasattr(attr, "thresh") else 0,
                            raw_value=int(attr.raw) if hasattr(attr, "raw") else 0,
                            status="OK",
                        )
                        if smart_attr.value < smart_attr.threshold:
                            smart_attr.status = "CRITICAL"
                        elif smart_attr.value < smart_attr.worst:
                            smart_attr.status = "WARNING"
                        attributes.append(smart_attr)

                        if attr_id == 194:
                            temperature = smart_attr.raw_value
                        elif attr_id == 9:
                            power_on_hours = smart_attr.raw_value
                        elif attr_id == 5:
                            reallocated_sectors = smart_attr.raw_value
                        elif attr_id == 197:
                            pending_sectors = smart_attr.raw_value
                        elif attr_id == 187:
                            uncorrectable_errors = smart_attr.raw_value
                    except Exception as e:
                        logger.debug("解析SMART属性失败 (%s): %s", attr_id, e)

            return DiskSmartData(
                disk_name=disk_name,
                model=model,
                serial=serial,
                capacity=capacity,
                interface=interface,
                assessment=assessment,
                temperature=temperature,
                power_on_hours=power_on_hours,
                reallocated_sectors=reallocated_sectors,
                pending_sectors=pending_sectors,
                uncorrectable_errors=uncorrectable_errors,
                attributes=attributes,
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error("读取SMART数据失败 (%s): %s", disk_name, e)
            return None


# =============================================================================
# Part 4: 硬件监控器工厂
# =============================================================================


class HardwareMonitorFactory:
    """硬件监控器工厂 - 强制使用LibreHardwareMonitor."""

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
                return monitor
            else:
                logger.error("❌ LibreHardwareMonitor 不可用，请确保：")
                logger.error("   1. 已安装 pythonnet: pip install pythonnet")
                logger.error("   2. LibreHardwareMonitor.dll 在正确路径")
                logger.error("   3. 以管理员权限运行程序")
                return None
        except Exception as e:
            logger.error("❌ LibreHardwareMonitor 初始化失败: %s", e)
            logger.error("   硬件监控功能将不可用")
            return None


# =============================================================================
# Part 5: 系统分析器（从独立文件合并）
# =============================================================================


class SystemBottleneckAnalyzer:
    """系统级瓶颈分析引擎（从 bottleneck_analyzer.py 合并）.

    基于木桶理论，评估系统各维度的性能，识别短板。
    评分规则：
    - CPU维度: 40分满分
    - 内存维度: 30分满分
    - 磁盘I/O维度: 15分满分
    - 网络维度: 15分满分
    - 总分: 100分

    瓶颈判断：得分最低的维度即为瓶颈
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

        # 取所有磁盘的平均延迟
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
            details: 该维度的详细信息
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
                suggestions.append("⚠️ 检测到内存交换活动，严重影响性能！立即降低负载50%")
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
                suggestions.append("考虑切换更稳定的网络或服务器")
            if max_loss > 0.005:
                suggestions.append("网络存在波动，建议添加重试机制")

        if not suggestions:
            suggestions.append("系统性能均衡，无明显瓶颈")

        return suggestions


class ScenarioAnalyzer:
    """量化场景分析器（从 scenario_analyzer.py 合并）.

    识别当前运行的主要量化场景，并提供场景特定的瓶颈分析和优化建议。
    支持5大量化场景：数据下载、实时行情、策略回测、策略编写、实盘交易。
    """

    def __init__(self):
        """初始化场景分析器."""
        self.logger = logging.getLogger(__name__)

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

            # 统计各场景的进程数和CPU占用
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

            # 返回得分最高的场景
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

        # TODO: 从业务指标获取下载并发数
        download_concurrency = 8  # 默认值

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

        # TODO: 从业务指标获取事件队列深度和处理延迟
        event_queue_depth = 0  # 默认值，需要业务埋点
        processing_latency = 0  # 默认值

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

        # TODO: 从业务指标获取K线计算时间
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
            bottleneck_reason = "⚠️ 内存交换活动，严重影响回测速度"
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

        # TODO: 从业务指标获取订单响应时间和交易队列长度
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

        # 父进程监控（防止成为孤儿进程）
        import os

        if parent_pid is None:
            self.parent_pid = os.getppid()  # 如果未提供，则自动获取
        else:
            self.parent_pid = parent_pid  # 使用传入的父进程PID

        logger.info(
            "[PARENT-MONITOR] 父进程PID（主应用）: %d, 当前进程PID（监控进程）: %d",
            self.parent_pid,
            os.getpid(),
        )

        # 🔥 Debug: 初始化步骤1 - 基础配置
        try:
            from backend.core.debug_logger import get_debug_logger

            self.debug_logger = get_debug_logger("monitor")
            self.debug_logger.debug_init_step(
                "基础配置",
                {
                    "db_path": db_path,
                    "parent_pid": self.parent_pid,
                    "current_pid": os.getpid(),
                },
            )
        except Exception:
            pass  # Debug日志失败不影响功能

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
        from backend.infrastructure.system_vnpy.monitors import (
            SystemMonitor,
            ProcessMonitor,
            ProcessBottleneckAnalyzer,
            get_business_metrics_collector,
        )

        # SystemBottleneckAnalyzer 和 ScenarioAnalyzer 已在本文件中定义

        # 🔥 Debug: 初始化步骤2 - 创建监控组件
        try:
            self.debug_logger.debug_init_step("开始创建监控组件")
        except Exception:
            pass

        self.system_monitor = SystemMonitor()
        self.process_monitor = ProcessMonitor()
        self.process_bottleneck_analyzer = ProcessBottleneckAnalyzer()  # 进程级瓶颈分析器
        self.system_bottleneck_analyzer = SystemBottleneckAnalyzer()  # 系统级瓶颈分析器（本地）
        self.scenario_analyzer = ScenarioAnalyzer()  # 场景分析器（本地）
        self.business_metrics_collector = get_business_metrics_collector()  # 业务指标采集器
        self.hardware_monitor = HardwareMonitorFactory.create_monitor()
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

        logger.info("MonitoringProcessV2 初始化完成")

        # 🔥 Debug: 初始化完成
        try:
            self.debug_logger.debug_init_step(
                "初始化完成",
                {
                    "fast_interval": self.fast_interval,
                    "slow_interval": self.slow_interval,
                },
            )
        except Exception:
            pass

    async def _check_and_cleanup_old_process(self):
        """检查并清理占用端口的旧监控进程（基于端口检测，不依赖文件）."""
        try:
            import psutil
            
            # 🔧 关键修复：直接检查端口占用，不依赖文件记录
            # 检查默认端口5557是否被占用
            target_ports = [5555, 5556, 5557]  # 监控进程使用的三个端口
            
            killed_any = False
            for port in target_ports:
                # 查找占用该端口的进程
                for conn in psutil.net_connections(kind='inet'):
                    if conn.laddr.port == port and conn.status == 'LISTEN':
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
                                    port, pid
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
                                    port, pid, cmdline[:100]
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
                logger.info("[清理] 未发现需要清理的旧监控进程")
                
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

        # 🔥 Debug: 启动流程开始
        try:
            self.debug_logger.debug_init_step("启动监控进程")
        except Exception:
            pass

        try:
            # 🔥 Debug: 组件初始化
            try:
                self.debug_logger.debug_init_step("开始初始化组件（ZMQ、数据库等）")
            except Exception:
                pass

            await self._initialize_components()

            # 🔥 Debug: 组件初始化完成
            try:
                self.debug_logger.debug_init_step("组件初始化完成，开始启动协程")
            except Exception:
                pass

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

                # 🔥 Debug: 所有协程就绪
                try:
                    self.debug_logger.debug_init_step(
                        "所有协程已就绪",
                        {
                            "协程数量": len(tasks),
                            "协程列表": list(self.coroutine_ready_events.keys()),
                        },
                    )
                except Exception:
                    pass

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

                # 🔥 Debug: 协程启动超时
                try:
                    self.debug_logger.debug_exception(
                        "协程启动超时",
                        TimeoutError(f"已就绪: {ready}, 未就绪: {not_ready}"),
                        {"ready": ready, "not_ready": not_ready},
                    )
                except Exception:
                    pass

                raise

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

                    # 🔥 Debug: 任务异常退出
                    try:
                        self.debug_logger.debug_exception(
                            f"任务 {task_name} 异常退出", result, {"task_name": task_name}
                        )
                    except Exception:
                        pass

                elif result is not None:
                    logger.warning(f"[TASK-EXIT] ⚠️  任务 {task_name} 意外返回: {result}")

        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")
        except Exception as e:
            logger.error("监控进程异常: %s", e, exc_info=True)

            # 🔥 Debug: 监控进程异常
            try:
                self.debug_logger.debug_exception("监控进程异常", e)
            except Exception:
                pass
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

        # 🔧 新增：检查并清理占用端口的旧进程
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

        # 工具函数：创建一组三个socket（局部变量，成功后再赋给 self）
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

        logger.info(
            "[ZMQ] 所有socket已配置（push=%d, pull=%d, rep=%d）",
            chosen_group[0],
            chosen_group[1],
            chosen_group[2],
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
                logger.error("[HARDWARE-THREAD] 采集失败: %s", e)
                time.sleep(self.slow_interval)

        logger.info("[HARDWARE-THREAD] 硬件传感器采集线程停止")

    def _smart_collector_thread(self):
        """SMART采集线程."""
        logger.info("[SMART-THREAD] SMART采集线程启动")
        self._collect_smart_once()

        while self.running:
            try:
                if self.loop and self.smart_trigger_event:
                    future = asyncio.run_coroutine_threadsafe(
                        asyncio.wait_for(self.smart_trigger_event.wait(), timeout=5), self.loop
                    )
                    try:
                        future.result(timeout=6)
                        if self.smart_trigger_event.is_set():
                            self.smart_trigger_event.clear()
                            self._collect_smart_once()
                    except Exception:
                        pass
                else:
                    time.sleep(5)
            except Exception as e:
                logger.error("[SMART-THREAD] 错误: %s", e)
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
            logger.error("[SMART] 采集失败: %s", e)

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
                await self.rep_socket.send_json({"success": True})
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
            logger.error("[ZMQ] 接收服务状态失败: %s", e)

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
                    logger.debug("[FAST-METRICS] ===== 开始新一轮采集 =====")

                    # 采集系统指标 - 异步
                    t1 = time.time()
                    logger.debug("[FAST-METRICS] 开始采集系统指标...")
                    system_metrics = await self._collect_system_metrics()
                    logger.debug("[FAST-METRICS] 系统指标采集完成")
                    self.monitoring_data["system"] = system_metrics
                    logger.debug("[PERF] 系统指标采集耗时: %.3fs", time.time() - t1)

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
                    logger.debug("[PERF] 进程指标采集耗时: %.3fs", time.time() - t2)

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
                    logger.debug("[PERF] 瓶颈分析耗时: %.3fs", time.time() - t3)

                    # 将数据加入数据库写入队列
                    await self._queue_for_database()

                    # 总耗时统计
                    total_time = time.time() - start_time
                    logger.debug("[PERF] 总采集耗时: %.3fs", total_time)

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
            # 在executor中执行阻塞的psutil调用
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
            cpu_detailed, memory_subsystem, storage_subsystem, network_subsystem = (
                await asyncio.gather(
                    loop.run_in_executor(self.executor, self.system_monitor.get_cpu_os_detailed),
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
            # 在executor中执行阻塞的进程识别
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
                    # 在executor中执行阻塞的进程指标获取
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
            logger.error("采集进程指标失败: %s", e)
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
                "reallocated_sectors": data.reallocated_sectors,
                "pending_sectors": data.pending_sectors,
                "uncorrectable_errors": data.uncorrectable_errors,
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
            logger.error("加入数据库队列失败: %s", e)

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
                    logger.error("[DB-WRITER] 错误: %s", e)
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
                    logger.error("[ALERT-EVAL] 评估失败: %s", e)
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

                    # 额外验证：检查父进程是否是预期的进程
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
        """推送告警到主进程."""
        if not self.push_socket:
            return

        try:
            await self.push_socket.send_json(alert)
            logger.info("[ALERT] 推送告警: %s", alert["message"])
        except Exception as e:
            logger.error("[ALERT] 推送失败: %s", e)

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


def main():
    """监控进程入口函数."""
    import sys
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("logs/monitor_process.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    monitor = MonitoringProcessV2()

    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        logger.info("收到中断信号")
    except Exception as e:
        logger.error("监控进程异常退出: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


__all__ = [
    "MonitoringProcessV2",
    "AdaptiveThresholdManager",
    "SmartMonitor",
    "HardwareMonitorFactory",
    "ThresholdConfig",
    "ThresholdResult",
    "DiskSmartData",
]
