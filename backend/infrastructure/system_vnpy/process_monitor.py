# -*- coding: utf-8 -*-
"""
进程监控模块.

提供进程识别、指标采集、瓶颈分析功能。
"""

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


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
    bottleneck_percent: float  # 瓶颈项的使用率
    details: str  # 详细描述
    suggestion: str  # 优化建议
    metrics: ProcessMetrics  # 原始指标数据


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
        self._main_process = psutil.Process()
        self._last_disk_io = psutil.disk_io_counters()
        self._last_net_io = psutil.net_io_counters()
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
            # 1. 识别当前进程的所有线程
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

            self.logger.debug("识别到 %d 个进程", len(processes))
            return processes

        except Exception as e:
            self.logger.error("识别进程失败: %s", e)
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
        self, process_id: str, process_name: str, process_type: str
    ) -> Optional[ProcessMetrics]:
        """获取进程的性能指标.

        Args:
            process_id: 进程ID
            process_name: 进程名称
            process_type: 进程类型

        Returns:
            Optional[ProcessMetrics]: 进程指标，如果获取失败返回None
        """
        try:
            current_time = time.time()
            time_delta = current_time - self._last_check_time

            if time_delta < 0.1:  # 避免频繁采集
                time_delta = 0.1

            # 获取CPU和内存指标
            # 🚀 性能优化：使用interval=None（非阻塞模式）
            # interval=0.1会阻塞线程0.1秒，在高频监控时会严重影响性能
            # None或0表示返回自上次调用以来的CPU使用率，不阻塞
            cpu_percent = self._main_process.cpu_percent(interval=None)
            memory_info = self._main_process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            memory_percent = self._main_process.memory_percent()

            # 获取磁盘IO指标
            disk_read_mbps = 0.0
            disk_write_mbps = 0.0
            try:
                current_disk_io = psutil.disk_io_counters()
                if current_disk_io and self._last_disk_io:
                    read_bytes = current_disk_io.read_bytes - self._last_disk_io.read_bytes
                    write_bytes = current_disk_io.write_bytes - self._last_disk_io.write_bytes
                    disk_read_mbps = (read_bytes / time_delta) / (1024 * 1024)
                    disk_write_mbps = (write_bytes / time_delta) / (1024 * 1024)
                    self._last_disk_io = current_disk_io
            except Exception as e:
                self.logger.debug("获取磁盘IO失败: %s", e)

            # 获取网络IO指标
            network_recv_mbps = 0.0
            network_send_mbps = 0.0
            try:
                current_net_io = psutil.net_io_counters()
                if current_net_io and self._last_net_io:
                    recv_bytes = current_net_io.bytes_recv - self._last_net_io.bytes_recv
                    sent_bytes = current_net_io.bytes_sent - self._last_net_io.bytes_sent
                    network_recv_mbps = (recv_bytes / time_delta) / (1024 * 1024)
                    network_send_mbps = (sent_bytes / time_delta) / (1024 * 1024)
                    self._last_net_io = current_net_io
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
            self.logger.error("获取进程指标失败 [%s]: %s", process_id, e)
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


class BottleneckAnalyzer:
    """瓶颈分析器 - 采用"最短木板"原理识别进程瓶颈."""

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
        """通用瓶颈识别 - 找到限制进程速度的"最短木板".

        Args:
            metrics: 进程指标
            focus_areas: 关注的领域列表，None表示关注所有领域

        Returns:
            BottleneckResult: 瓶颈分析结果
        """
        if focus_areas is None:
            focus_areas = ["cpu", "memory", "disk_io", "network"]

        # 计算各项指标的使用率（相对于理论最大值）
        usage_rates: dict[str, float] = {}

        if "cpu" in focus_areas:
            usage_rates["cpu"] = min(metrics.cpu_percent, 100.0)

        if "memory" in focus_areas:
            usage_rates["memory"] = min(metrics.memory_percent, 100.0)

        if "disk_io" in focus_areas:
            # 磁盘IO取读写速度的最大值
            max_disk_speed = max(metrics.disk_read_mbps, metrics.disk_write_mbps)
            disk_usage_percent = (max_disk_speed / self.theoretical_limits["disk_io_mbps"]) * 100
            usage_rates["disk_io"] = min(disk_usage_percent, 100.0)

        if "network" in focus_areas:
            # 网络取收发速度的最大值
            max_network_speed = max(metrics.network_recv_mbps, metrics.network_send_mbps)
            network_usage_percent = (
                max_network_speed / self.theoretical_limits["network_mbps"]
            ) * 100
            usage_rates["network"] = min(network_usage_percent, 100.0)

        # 找出使用率最高的项（最短木板）
        if not usage_rates:
            # 没有可分析的指标
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

        # 判断是否真的存在瓶颈
        threshold = self.bottleneck_thresholds.get(bottleneck_type, 70.0)

        if bottleneck_percent < threshold:
            # 所有指标都未达到瓶颈阈值，系统均衡
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
            details = f"CPU使用率达到 {metrics.cpu_percent:.1f}%，处理器计算能力已接近极限"
            suggestion = (
                "建议：1) 优化算法降低计算复杂度 2) 启用多进程并行处理 3) 使用缓存减少重复计算"
            )

        elif bottleneck_type == "memory":
            details = f"内存使用率达到 {metrics.memory_percent:.1f}%，内存容量不足"
            suggestion = "建议：1) 启用数据分页加载 2) 及时释放不用的对象 3) 使用生成器代替列表 4) 扩展物理内存"

        elif bottleneck_type == "disk_io":
            max_speed = max(metrics.disk_read_mbps, metrics.disk_write_mbps)
            io_type = "写入" if metrics.disk_write_mbps > metrics.disk_read_mbps else "读取"
            details = f"磁盘IO{io_type}速度达到 {max_speed:.1f}MB/s，磁盘吞吐量已接近极限"
            suggestion = (
                "建议：1) 使用SSD固态硬盘替代机械硬盘 2) 启用批量读写减少IO次数 3) 使用异步IO操作"
            )

        elif bottleneck_type == "network":
            max_speed = max(metrics.network_recv_mbps, metrics.network_send_mbps)
            net_type = "下载" if metrics.network_recv_mbps > metrics.network_send_mbps else "上传"
            details = f"网络{net_type}速度达到 {max_speed:.1f}MB/s，网络带宽已接近极限"
            suggestion = (
                "建议：1) 升级网络带宽 2) 启用数据压缩 3) 使用多线程并发下载 4) 优化网络请求策略"
            )

        else:
            details = f"检测到瓶颈：{bottleneck_type} ({percent:.1f}%)"
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


# 导出类
__all__ = [
    "ProcessMonitor",
    "BottleneckAnalyzer",
    "ProcessMetrics",
    "BottleneckResult",
]
