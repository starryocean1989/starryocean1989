# -*- coding: utf-8 -*-
"""
系统监控指标获取器

混合模式监控：
- 事件订阅：后台被动接收SystemManagerService推送的监控事件（低延迟）
- ZMQ查询：关键决策时主动查询监控进程（实时数据）
- 多层fallback：事件 → ZMQ → 缓存 → 默认值
"""

import logging
import threading
import time
from typing import Any, Dict, Optional

try:
    import zmq

    HAS_ZMQ = True
except ImportError:
    HAS_ZMQ = False

from vnpy.event import Event, EventEngine


class SystemMetricsMonitor:
    """系统监控指标获取器（混合模式）

    特性：
    - 事件订阅：订阅SystemManagerService推送的监控事件，后台被动更新缓存
    - ZMQ查询：关键决策时直接查询监控进程，获取最新数据
    - 智能fallback：事件缓存过期时自动切换到ZMQ查询
    - 线程安全：使用锁保护缓存

    使用示例：
        monitor = SystemMetricsMonitor(event_engine)

        # 常规查询（使用事件缓存）
        metrics = monitor.get_metrics(force_realtime=False)

        # 关键决策（强制实时查询）
        metrics = monitor.get_metrics(force_realtime=True)
    """

    def __init__(self, event_engine: Optional[EventEngine] = None):
        """初始化监控指标获取器

        Args:
            event_engine: vnpy事件引擎（可选）
                如果提供，则订阅监控事件；否则只使用ZMQ查询
        """
        self.event_engine = event_engine
        self.logger = logging.getLogger(__name__)

        # 事件订阅缓存（后台更新）
        self._cached_metrics: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()
        self._cache_timestamp = 0.0

        # ZMQ客户端（按需查询）
        self._zmq_context: Optional[Any] = None
        self._zmq_socket: Optional[Any] = None

        # 启动事件订阅
        if event_engine:
            self._subscribe_events()
            self.logger.info("✅ SystemMetricsMonitor初始化完成（事件订阅模式）")
        else:
            self.logger.info("✅ SystemMetricsMonitor初始化完成（仅ZMQ查询模式）")

    def _subscribe_events(self):
        """订阅系统监控事件（后台被动更新）"""
        if not self.event_engine:
            return

        try:
            from backend.core.monitoring_events import (
                EVENT_SYSTEM_METRICS,
                EVENT_HARDWARE_SENSORS,
            )

            self.event_engine.register(EVENT_SYSTEM_METRICS, self._on_system_metrics_event)
            self.event_engine.register(EVENT_HARDWARE_SENSORS, self._on_hardware_sensors_event)

            self.logger.debug("已订阅系统监控事件")

        except ImportError:
            self.logger.warning("无法导入monitoring_events，事件订阅失败")

    def _on_system_metrics_event(self, event: Event):
        """接收系统指标事件"""
        with self._cache_lock:
            self._cached_metrics["system"] = event.data
            self._cache_timestamp = time.time()
            self.logger.debug("收到系统指标事件更新")

    def _on_hardware_sensors_event(self, event: Event):
        """接收硬件传感器事件"""
        with self._cache_lock:
            self._cached_metrics["hardware"] = event.data
            self.logger.debug("收到硬件传感器事件更新")

    def get_metrics(self, force_realtime: bool = False) -> Dict[str, Any]:
        """获取监控指标

        策略：
        1. force_realtime=True: 强制ZMQ实时查询（关键决策时使用）
        2. force_realtime=False: 使用事件缓存，超时则fallback到ZMQ

        Args:
            force_realtime: 是否强制实时查询（通过ZMQ）

        Returns:
            系统监控指标字典，包含：
            - system: 系统资源指标（cpu_percent, memory_percent等）
            - hardware: 硬件传感器数据（可选）
        """
        # 关键决策时刻：使用ZMQ实时查询
        if force_realtime:
            self.logger.debug("强制实时查询监控数据（ZMQ）")
            return self._query_via_zmq()

        # 常规情况：使用事件订阅缓存
        with self._cache_lock:
            # 如果缓存从未更新过（_cache_timestamp=0），直接使用ZMQ查询
            if self._cache_timestamp == 0:
                self.logger.debug("监控缓存未初始化，使用ZMQ查询")
                return self._query_via_zmq()

            # 缓存超过3秒则fallback到ZMQ查询
            cache_age = time.time() - self._cache_timestamp
            if cache_age > 3.0:
                self.logger.warning("监控缓存过期（%.1f秒），fallback到ZMQ查询", cache_age)
                return self._query_via_zmq()

            # 缓存有效
            if not self._cached_metrics:
                self.logger.warning("事件缓存为空，尝试ZMQ查询")
                return self._query_via_zmq()

            return self._cached_metrics.copy()

    def _query_via_zmq(self) -> Dict[str, Any]:
        """通过ZMQ实时查询监控数据

        连接到监控进程的ZMQ REP端口（5557），发送查询请求。

        Returns:
            监控数据字典，如果查询失败则返回缓存或默认值
        """
        if not HAS_ZMQ:
            self.logger.error("ZMQ库未安装，无法查询监控数据")
            return self._get_fallback_metrics()

        try:
            # 初始化ZMQ客户端
            if not self._zmq_socket:
                self._init_zmq_client()

            # 确保socket已初始化
            if not self._zmq_socket:
                self.logger.error("ZMQ socket初始化失败")
                return self._get_fallback_metrics()

            # 发送查询请求
            self._zmq_socket.send_json({"action": "get_data"})
            data = self._zmq_socket.recv_json()

            # 更新缓存
            with self._cache_lock:
                self._cached_metrics = data
                self._cache_timestamp = time.time()

            self.logger.debug("ZMQ查询成功")
            return data

        except zmq.Again:
            self.logger.error("ZMQ查询超时")
            return self._get_fallback_metrics()

        except Exception as e:
            self.logger.error("ZMQ查询失败: %s", e)
            return self._get_fallback_metrics()

    def _init_zmq_client(self):
        """初始化ZMQ客户端"""
        if not HAS_ZMQ:
            return

        try:
            self._zmq_context = zmq.Context()
            socket = self._zmq_context.socket(zmq.REQ)
            socket.connect("tcp://127.0.0.1:5557")
            socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1秒超时
            socket.setsockopt(zmq.SNDTIMEO, 1000)
            self._zmq_socket = socket
            self.logger.info("ZMQ客户端初始化完成（连接到监控进程 5557端口）")

        except Exception as e:
            self.logger.error("ZMQ客户端初始化失败: %s", e)
            self._zmq_socket = None

    def _get_fallback_metrics(self) -> Dict[str, Any]:
        """获取fallback指标

        优先返回缓存（即使过期），否则返回默认值。

        Returns:
            监控指标字典
        """
        # 优先使用缓存（即使过期）
        with self._cache_lock:
            if self._cached_metrics:
                self.logger.warning("使用过期缓存作为fallback")
                return self._cached_metrics.copy()

        # 最后使用默认值
        self.logger.warning("使用默认值作为fallback")
        return self._get_default_metrics()

    def _get_default_metrics(self) -> Dict[str, Any]:
        """获取默认指标（假设系统正常）

        Returns:
            默认监控指标字典
        """
        return {
            "system": {
                "cpu_percent": 50.0,
                "memory_percent": 50.0,
                "disk_percent": 50.0,
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
        if self._zmq_socket:
            try:
                self._zmq_socket.close()
            except Exception as e:
                self.logger.warning("关闭ZMQ socket失败: %s", e)

        if self._zmq_context:
            try:
                self._zmq_context.term()
            except Exception as e:
                self.logger.warning("终止ZMQ context失败: %s", e)

        self.logger.info("SystemMetricsMonitor已关闭")
