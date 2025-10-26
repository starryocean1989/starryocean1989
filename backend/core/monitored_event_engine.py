# -*- coding: utf-8 -*-
"""
监控版事件引擎

扩展VNPy的EventEngine，增加队列深度和处理延迟监控能力。
"""

import time
import logging
from collections import deque

from vnpy.event import EventEngine, Event


logger = logging.getLogger(__name__)


class MonitoredEventEngine(EventEngine):
    """带监控的事件引擎

    扩展功能：
    1. 记录事件队列深度
    2. 记录事件处理延迟
    3. 上报到BusinessMetricsCollector

    使用方式：
        # 创建监控版引擎
        event_engine = MonitoredEventEngine()

        # 注入业务指标采集器
        from backend.infrastructure.system_vnpy import get_business_metrics_collector
        collector = get_business_metrics_collector()
        event_engine.set_business_metrics_collector(collector)
    """

    def __init__(self):
        """初始化监控版事件引擎"""
        super().__init__()

        # 业务指标采集器（外部注入）
        self._business_metrics = None

        # 本地采样缓存（用于统计）
        self._queue_depth_samples = deque(maxlen=100)
        self._latency_samples = deque(maxlen=100)

        # 统计信息
        self._total_events_processed = 0
        self._last_report_time = time.time()
        self._report_interval = 5.0  # 每5秒输出一次统计（可选）

        logger.info("✅ MonitoredEventEngine已初始化（支持队列深度和延迟监控）")

    def set_business_metrics_collector(self, collector):
        """设置业务指标采集器

        Args:
            collector: BusinessMetricsCollector实例
        """
        self._business_metrics = collector
        logger.info("✅ BusinessMetricsCollector已注入到MonitoredEventEngine")

    def put(self, event: Event):
        """重写put方法，记录入队时间和队列深度

        Args:
            event: 事件对象
        """
        # 1. 记录队列深度
        queue_depth = self._queue.qsize()
        self._queue_depth_samples.append(queue_depth)

        # 2. 上报队列深度到监控系统
        if self._business_metrics:
            try:
                self._business_metrics.record_metric("event_queue_depth", queue_depth)
            except Exception as e:
                # 静默失败，不影响事件处理
                logger.debug(f"上报event_queue_depth失败: {e}")

        # 3. 记录入队时间（用于后续计算延迟）
        event._enqueue_time = time.time()  # type: ignore[attr-defined]

        # 4. 调用父类方法（实际入队）
        super().put(event)

    def _process(self, event: Event):
        """重写_process方法，记录处理延迟

        Args:
            event: 事件对象
        """
        # 1. 计算处理延迟（毫秒）
        if hasattr(event, "_enqueue_time"):
            latency_ms = (time.time() - event._enqueue_time) * 1000  # type: ignore[attr-defined]
            self._latency_samples.append(latency_ms)

            # 2. 上报延迟到监控系统
            if self._business_metrics:
                try:
                    self._business_metrics.record_metric("event_processing_latency_ms", latency_ms)
                except Exception as e:
                    # 静默失败
                    logger.debug(f"上报event_processing_latency_ms失败: {e}")

        # 3. 更新统计
        self._total_events_processed += 1

        # 4. 定期输出统计信息（可选）
        self._maybe_report_stats()

        # 5. 调用父类方法（实际处理）
        super()._process(event)

    def _maybe_report_stats(self):
        """定期输出统计信息（每5秒）"""
        current_time = time.time()
        elapsed = current_time - self._last_report_time

        if elapsed >= self._report_interval:
            # 计算统计数据
            avg_queue_depth = (
                sum(self._queue_depth_samples) / len(self._queue_depth_samples)
                if self._queue_depth_samples
                else 0
            )
            avg_latency_ms = (
                sum(self._latency_samples) / len(self._latency_samples)
                if self._latency_samples
                else 0
            )

            logger.debug(
                f"📊 EventEngine统计: "
                f"总处理 {self._total_events_processed} 事件, "
                f"平均队列深度 {avg_queue_depth:.1f}, "
                f"平均延迟 {avg_latency_ms:.2f}ms"
            )

            self._last_report_time = current_time

    def get_statistics(self) -> dict:
        """获取当前统计信息

        Returns:
            dict: 统计信息字典
        """
        if not self._queue_depth_samples or not self._latency_samples:
            return {
                "total_events_processed": self._total_events_processed,
                "avg_queue_depth": 0,
                "avg_latency_ms": 0,
                "max_queue_depth": 0,
                "max_latency_ms": 0,
            }

        return {
            "total_events_processed": self._total_events_processed,
            "avg_queue_depth": sum(self._queue_depth_samples) / len(self._queue_depth_samples),
            "avg_latency_ms": sum(self._latency_samples) / len(self._latency_samples),
            "max_queue_depth": max(self._queue_depth_samples),
            "max_latency_ms": max(self._latency_samples),
            "current_queue_depth": self._queue.qsize(),
        }
