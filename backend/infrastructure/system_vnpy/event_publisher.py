# -*- coding: utf-8 -*-
"""
事件发布模块.

基于vnpy EventEngine实现系统指标的实时推送.
"""

import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SystemMetricsPublisher:
    """系统指标发布器 - 基于vnpy EventEngine."""

    def __init__(self, event_engine, system_monitor):
        """初始化系统指标发布器.

        Args:
            event_engine: vnpy EventEngine实例
            system_monitor: SystemMonitor实例
        """
        self.logger = logging.getLogger(__name__)
        self.event_engine = event_engine
        self.system_monitor = system_monitor

        # 发布控制
        self._publishing = False
        self._publish_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 发布间隔（秒）
        self._interval = 2

        # 上次发布的数据（用于变化检测）
        self._last_metrics: Dict[str, Any] = {}

    def start_publishing(self, interval: int = 2):
        """开始定期发布系统指标.

        Args:
            interval: 发布间隔（秒）
        """
        if self._publishing:
            self.logger.warning("系统指标发布器已在运行")
            return

        self._interval = interval
        self._publishing = True
        self._stop_event.clear()

        # 启动发布线程
        self._publish_thread = threading.Thread(
            target=self._publishing_loop,
            daemon=True,
            name="SystemMetricsPublisher",
        )
        self._publish_thread.start()

        self.logger.info("系统指标发布器已启动，间隔: %d秒", interval)

    def stop_publishing(self):
        """停止发布系统指标."""
        if not self._publishing:
            return

        self._publishing = False
        self._stop_event.set()

        # 等待线程结束
        if self._publish_thread and self._publish_thread.is_alive():
            self._publish_thread.join(timeout=5)

        self.logger.info("系统指标发布器已停止")

    def _publishing_loop(self):
        """发布循环."""
        while self._publishing and not self._stop_event.is_set():
            try:
                # 采集并发布系统状态
                self._collect_and_publish_system_status()

                # 等待下次发布
                self._stop_event.wait(self._interval)

            except Exception as e:
                self.logger.error("发布系统指标失败: %s", e)
                time.sleep(self._interval)

    def _collect_and_publish_system_status(self):
        """采集并发布系统状态."""
        try:
            # 采集系统资源使用情况
            resource_usage = self.system_monitor.get_resource_usage()

            # 采集磁盘I/O速度
            disk_io_speed = {}
            try:
                disk_io_speed = self.system_monitor.get_disk_io_speed()
            except Exception as e:
                self.logger.debug("获取磁盘I/O速度失败: %s", e)

            # 采集网络速度
            network_speed = {}
            try:
                network_speed = self.system_monitor.get_network_speed()
            except Exception as e:
                self.logger.debug("获取网络速度失败: %s", e)

            # 组装系统状态数据
            system_status = {
                "cpu_percent": resource_usage.cpu_percent,
                "memory_percent": resource_usage.memory_percent,
                "disk_percent": resource_usage.disk_percent,
                "network_sent": resource_usage.network_sent,
                "network_recv": resource_usage.network_recv,
                "process_count": resource_usage.process_count,
                "load_average": resource_usage.load_average,
                "timestamp": resource_usage.timestamp.isoformat(),
                "disk_io_speed": disk_io_speed,
                "network_speed": network_speed,
            }

            # 发布事件
            self.publish_system_status(system_status)

        except Exception as e:
            self.logger.error("采集系统状态失败: %s", e)

    def publish_system_status(self, metrics: Dict[str, Any]):
        """发布系统状态事件.

        Args:
            metrics: 系统指标数据
        """
        try:
            if not self.event_engine:
                return

            # 从backend.core.utils导入事件类型
            try:
                from backend.core.utils import EVENT_SYSTEM_STATUS
            except ImportError:
                # 如果还没定义，使用字符串常量
                EVENT_SYSTEM_STATUS = "eSystemStatus"

            # 创建事件
            from vnpy.event import Event

            event = Event(EVENT_SYSTEM_STATUS, metrics)

            # 发布事件
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("发布系统状态事件失败: %s", e)

    def publish_performance_metrics(self, metrics: Dict[str, Any]):
        """发布性能指标事件.

        Args:
            metrics: 性能指标数据
        """
        try:
            if not self.event_engine:
                return

            # 从backend.core.utils导入事件类型
            try:
                from backend.core.utils import EVENT_PERFORMANCE_METRICS
            except ImportError:
                # 如果还没定义，使用字符串常量
                EVENT_PERFORMANCE_METRICS = "ePerformanceMetrics"

            # 创建事件
            from vnpy.event import Event

            event = Event(EVENT_PERFORMANCE_METRICS, metrics)

            # 发布事件
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("发布性能指标事件失败: %s", e)

    def publish_service_status(self, status: Dict[str, Any]):
        """发布服务状态事件.

        Args:
            status: 服务状态数据
        """
        try:
            if not self.event_engine:
                return

            # 从backend.core.utils导入事件类型
            try:
                from backend.core.utils import EVENT_SERVICE_STATUS
            except ImportError:
                # 如果还没定义，使用字符串常量
                EVENT_SERVICE_STATUS = "eServiceStatus"

            # 创建事件
            from vnpy.event import Event

            event = Event(EVENT_SERVICE_STATUS, status)

            # 发布事件
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("发布服务状态事件失败: %s", e)

    def publish_diagnostic_result(self, result: Dict[str, Any]):
        """发布诊断结果事件.

        Args:
            result: 诊断结果数据
        """
        try:
            if not self.event_engine:
                return

            # 从backend.core.utils导入事件类型
            try:
                from backend.core.utils import EVENT_DIAGNOSTIC_RESULT
            except ImportError:
                # 如果还没定义，使用字符串常量
                EVENT_DIAGNOSTIC_RESULT = "eDiagnosticResult"

            # 创建事件
            from vnpy.event import Event

            event = Event(EVENT_DIAGNOSTIC_RESULT, result)

            # 发布事件
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("发布诊断结果事件失败: %s", e)

    @property
    def is_publishing(self) -> bool:
        """是否正在发布."""
        return self._publishing


class ProcessMetricsPublisher:
    """进程监控发布器 - 定期采集并发布进程指标和瓶颈分析."""

    def __init__(self, event_engine, process_monitor, bottleneck_analyzer):
        """初始化进程监控发布器.

        Args:
            event_engine: vnpy EventEngine实例
            process_monitor: ProcessMonitor实例
            bottleneck_analyzer: BottleneckAnalyzer实例
        """
        self.logger = logging.getLogger(__name__)
        self.event_engine = event_engine
        self.process_monitor = process_monitor
        self.bottleneck_analyzer = bottleneck_analyzer

        # 发布控制
        self._publishing = False
        self._publish_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 发布间隔（秒）
        self._interval = 2

        # 瓶颈分析结果缓存（进程ID -> (结果, 时间戳)）
        self._bottleneck_cache: Dict[str, tuple] = {}
        self._cache_ttl = 1  # 缓存有效期1秒

    def start_publishing(self, interval: int = 2):
        """开始定期发布进程指标.

        Args:
            interval: 发布间隔（秒）
        """
        if self._publishing:
            self.logger.warning("进程监控发布器已在运行")
            return

        self._interval = interval
        self._publishing = True
        self._stop_event.clear()

        # 启动发布线程
        self._publish_thread = threading.Thread(
            target=self._publishing_loop,
            daemon=True,
            name="ProcessMetricsPublisher",
        )
        self._publish_thread.start()

        self.logger.info("进程监控发布器已启动，间隔: %d秒", interval)

    def stop_publishing(self):
        """停止发布进程指标."""
        if not self._publishing:
            return

        self._publishing = False
        self._stop_event.set()

        # 等待线程结束
        if self._publish_thread and self._publish_thread.is_alive():
            self._publish_thread.join(timeout=5)

        self.logger.info("进程监控发布器已停止")

    def _publishing_loop(self):
        """发布循环."""
        while self._publishing and not self._stop_event.is_set():
            try:
                # 采集并发布进程状态
                self._collect_and_publish_process_status()

                # 等待下次发布
                self._stop_event.wait(self._interval)

            except Exception as e:
                self.logger.error("发布进程指标失败: %s", e)
                time.sleep(self._interval)

    def _collect_and_publish_process_status(self):
        """采集并发布进程状态."""
        try:
            # 识别所有关键进程
            processes = self.process_monitor.identify_processes()

            if not processes:
                self.logger.debug("未识别到关键进程")
                return

            # 采集进程指标和瓶颈分析
            process_data = []
            for proc_info in processes:
                try:
                    process_id = proc_info["id"]
                    process_name = proc_info["name"]
                    process_type = proc_info["type"]

                    # 获取进程指标
                    metrics = self.process_monitor.get_process_metrics(
                        process_id, process_name, process_type
                    )

                    if not metrics:
                        continue

                    # 检查缓存是否有效
                    cached_result = None
                    if process_id in self._bottleneck_cache:
                        cached_result, cache_time = self._bottleneck_cache[process_id]
                        if time.time() - cache_time > self._cache_ttl:
                            cached_result = None  # 缓存过期

                    # 瓶颈分析（使用缓存或重新计算）
                    if cached_result:
                        bottleneck_result = cached_result
                    else:
                        bottleneck_result = self.bottleneck_analyzer.analyze_by_type(metrics)
                        self._bottleneck_cache[process_id] = (bottleneck_result, time.time())

                    # 组装进程数据
                    process_data.append(
                        {
                            "process_id": process_id,
                            "process_name": process_name,
                            "process_type": process_type,
                            "status": metrics.status,
                            "cpu_percent": metrics.cpu_percent,
                            "memory_mb": metrics.memory_mb,
                            "memory_percent": metrics.memory_percent,
                            "disk_read_mbps": metrics.disk_read_mbps,
                            "disk_write_mbps": metrics.disk_write_mbps,
                            "network_recv_mbps": metrics.network_recv_mbps,
                            "network_send_mbps": metrics.network_send_mbps,
                            "timestamp": metrics.timestamp.isoformat(),
                            # 瓶颈分析
                            "bottleneck": bottleneck_result.bottleneck,
                            "bottleneck_percent": bottleneck_result.bottleneck_percent,
                            "bottleneck_details": bottleneck_result.details,
                            "bottleneck_suggestion": bottleneck_result.suggestion,
                        }
                    )

                except Exception as e:
                    self.logger.error("采集进程指标失败 [%s]: %s", proc_info.get("name"), e)
                    continue

            if process_data:
                # 发布事件
                self.publish_process_status(
                    {
                        "processes": process_data,
                        "total_count": len(process_data),
                        "timestamp": time.time(),
                    }
                )

        except Exception as e:
            self.logger.error("采集进程状态失败: %s", e)

    def publish_process_status(self, status: Dict[str, Any]):
        """发布进程状态事件.

        Args:
            status: 进程状态数据
        """
        try:
            if not self.event_engine:
                return

            # 导入事件类型
            from backend.core.utils import EVENT_PROCESS_STATUS
            from vnpy.event import Event

            # 创建事件
            event = Event(EVENT_PROCESS_STATUS, status)

            # 发布事件
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("发布进程状态事件失败: %s", e)

    @property
    def is_publishing(self) -> bool:
        """是否正在发布."""
        return self._publishing


# 导出类
__all__ = [
    "SystemMetricsPublisher",
    "ProcessMetricsPublisher",
]
