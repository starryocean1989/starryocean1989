# -*- coding: utf-8 -*-
"""
系统监控服务.

集成psutil和system_vnpy提供系统监控功能。
"""

import logging
from typing import Any, Dict
from datetime import datetime

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("psutil未安装，系统监控功能受限")

logger = logging.getLogger(__name__)


class MonitoringService:
    """系统监控服务."""

    def __init__(self):
        """初始化监控服务."""
        self.psutil_available = PSUTIL_AVAILABLE
        logger.info("系统监控服务初始化完成，psutil可用: %s", self.psutil_available)

    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态."""
        try:
            if not self.psutil_available:
                return self._mock_system_status()

            # 使用psutil获取系统指标
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            net_io = psutil.net_io_counters()

            status = {
                "timestamp": datetime.now().isoformat(),
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used": memory.used,
                "memory_total": memory.total,
                "disk_percent": disk.percent,
                "disk_used": disk.used,
                "disk_total": disk.total,
                "network_sent": net_io.bytes_sent,
                "network_recv": net_io.bytes_recv,
                "process_count": len(psutil.pids()),
                "status": self._determine_status(
                    cpu_percent, memory.percent, disk.percent
                ),
            }

            logger.debug(
                "系统状态获取成功: CPU=%.1f%%, Memory=%.1f%%",
                cpu_percent,
                memory.percent,
            )
            return status

        except Exception as e:
            logger.error("获取系统状态失败: %s", e)
            raise

    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标."""
        try:
            if not self.psutil_available:
                return self._mock_performance_metrics()

            # TODO: 集成infrastructure/system_vnpy/performance_optimizer.py
            metrics = {
                "data_processing_rate": 1000,  # 每秒处理数据条数
                "strategy_execution_time": 0.05,  # 策略执行时间(秒)
                "trade_latency": 0.002,  # 交易延迟(秒)
                "memory_usage_mb": psutil.Process().memory_info().rss / 1024 / 1024,
                "cpu_time": psutil.Process().cpu_times(),
                "timestamp": datetime.now().isoformat(),
            }

            return metrics

        except Exception as e:
            logger.error("获取性能指标失败: %s", e)
            raise

    def _determine_status(
        self, cpu_percent: float, memory_percent: float, disk_percent: float
    ) -> str:
        """判断系统状态."""
        if cpu_percent > 90 or memory_percent > 90 or disk_percent > 90:
            return "critical"
        elif cpu_percent > 70 or memory_percent > 70 or disk_percent > 80:
            return "warning"
        else:
            return "normal"

    def _mock_system_status(self) -> Dict[str, Any]:
        """模拟系统状态（当psutil不可用时）."""
        return {
            "timestamp": datetime.now().isoformat(),
            "cpu_percent": 45.0,
            "memory_percent": 60.0,
            "disk_percent": 55.0,
            "network_sent": 1024000,
            "network_recv": 2048000,
            "process_count": 100,
            "status": "normal",
        }

    def _mock_performance_metrics(self) -> Dict[str, Any]:
        """模拟性能指标."""
        return {
            "data_processing_rate": 1000,
            "strategy_execution_time": 0.05,
            "trade_latency": 0.002,
            "timestamp": datetime.now().isoformat(),
        }


__all__ = ["MonitoringService"]
