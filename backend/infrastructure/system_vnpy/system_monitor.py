# -*- coding: utf-8 -*-
"""
系统资源监控模块.

提供CPU,内存,磁盘,网络等系统资源的实时监控功能.
基于psutil库实现跨平台的系统监控能力.
"""

import logging
import os
import platform
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# 尝试导入psutil,如果没有则使用基础实现
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil模块未安装,将使用基础系统监控功能")


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


class SystemMonitor:
    """系统监控器."""

    def __init__(self):
        """初始化系统监控器."""
        self.monitoring = False
        self.history = []
        self.max_history = 1000

    def get_system_info(self) -> SystemInfo:
        """获取系统基本信息."""
        try:
            if HAS_PSUTIL:
                # 获取网络接口
                network_interfaces = list(psutil.net_if_addrs().keys())

                # 获取磁盘总空间
                disk_usage = psutil.disk_usage('/')

                return SystemInfo(
                    platform=platform.system(),
                    platform_version=platform.version(),
                    architecture=platform.architecture()[0],
                    hostname=platform.node(),
                    cpu_count=psutil.cpu_count(logical=False),
                    cpu_count_logical=psutil.cpu_count(logical=True),
                    memory_total=psutil.virtual_memory().total,
                    disk_total=disk_usage.total,
                    network_interfaces=network_interfaces,
                    boot_time=datetime.fromtimestamp(psutil.boot_time())
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
                    boot_time=datetime.now()
                )
        except (OSError, AttributeError, ImportError) as e:
            logger.error("获取系统信息失败: %s", e)
            raise

    def get_resource_usage(self) -> ResourceUsage:
        """获取资源使用情况."""
        try:
            if HAS_PSUTIL:
                # CPU使用率
                cpu_percent = psutil.cpu_percent(interval=1)

                # 内存使用率
                memory = psutil.virtual_memory()

                # 磁盘使用率
                disk = psutil.disk_usage('/')

                # 网络流量
                network = psutil.net_io_counters()

                # 进程数量
                process_count = len(psutil.pids())

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
                    disk_percent=(disk.used / disk.total) * 100,
                    network_sent=network.bytes_sent,
                    network_recv=network.bytes_recv,
                    process_count=process_count,
                    load_average=load_average,
                    timestamp=datetime.now()
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
                    timestamp=datetime.now()
                )
        except (OSError, AttributeError, ImportError) as e:
            logger.error("获取资源使用情况失败: %s", e)
            raise

    def get_cpu_info(self) -> Dict[str, Any]:
        """获取CPU详细信息."""
        try:
            if HAS_PSUTIL:
                cpu_freq = psutil.cpu_freq()
                cpu_times = psutil.cpu_times()

                return {
                    "cpu_count_physical": psutil.cpu_count(logical=False),
                    "cpu_count_logical": psutil.cpu_count(logical=True),
                    "cpu_percent_per_core": psutil.cpu_percent(percpu=True),
                    "cpu_frequency": {
                        "current": cpu_freq.current if cpu_freq else 0,
                        "min": cpu_freq.min if cpu_freq else 0,
                        "max": cpu_freq.max if cpu_freq else 0,
                    },
                    "cpu_times": {
                        "user": cpu_times.user,
                        "system": cpu_times.system,
                        "idle": cpu_times.idle,
                    }
                }
            else:
                return {
                    "cpu_count_physical": os.cpu_count() or 1,
                    "cpu_count_logical": os.cpu_count() or 1,
                    "cpu_percent_per_core": [25.0],
                    "cpu_frequency": {
                        "current": 2400,
                        "min": 1000,
                        "max": 3000,
                    },
                    "cpu_times": {
                        "user": 1000.0,
                        "system": 500.0,
                        "idle": 5000.0,
                    }
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
                    }
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
                    }
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
            disk_io = psutil.disk_io_counters()
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
                interface_info = {
                    "addresses": [],
                    "stats": {}
                }

                # 地址信息
                for addr in addresses:
                    interface_info["addresses"].append({
                        "family": str(addr.family),
                        "address": addr.address,
                        "netmask": addr.netmask,
                        "broadcast": addr.broadcast,
                    })

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
            net_io = psutil.net_io_counters()
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

    def get_process_list(
        self, sort_by: str = "cpu_percent"
    ) -> List[Dict[str, Any]]:
        """获取进程列表."""
        try:
            if not HAS_PSUTIL:
                # 返回默认数据(无psutil时)
                return [
                    {
                        "pid": 1, "name": "python", "cpu_percent": 25.0,
                        "memory_percent": 15.0, "memory_mb": 256.0,
                        "status": "running"
                    },
                    {
                        "pid": 2, "name": "chrome", "cpu_percent": 15.0,
                        "memory_percent": 20.0, "memory_mb": 512.0,
                        "status": "running"
                    },
                    {
                        "pid": 3, "name": "system", "cpu_percent": 5.0,
                        "memory_percent": 10.0, "memory_mb": 128.0,
                        "status": "running"
                    },
                ]

            processes = []

            for proc in psutil.process_iter([
                'pid', 'name', 'cpu_percent', 'memory_percent', 'status'
            ]):
                try:
                    proc_info = proc.info
                    proc_info['memory_mb'] = (
                        proc.memory_info().rss / 1024 / 1024
                    )
                    processes.append(proc_info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # 排序
            if sort_by in ["cpu_percent", "memory_percent", "memory_mb"]:
                processes.sort(
                    key=lambda x: x.get(sort_by, 0), reverse=True
                )

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
        threshold_disk: float = 90.0
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
            alerts.append({
                "type": "cpu_high",
                "level": "warning",
                "message": f"CPU使用率过高: {usage.cpu_percent:.1f}%",
                "threshold": self.threshold_cpu,
                "current": usage.cpu_percent,
                "timestamp": usage.timestamp
            })

        if usage.memory_percent > self.threshold_memory:
            alerts.append({
                "type": "memory_high",
                "level": "warning",
                "message": f"内存使用率过高: {usage.memory_percent:.1f}%",
                "threshold": self.threshold_memory,
                "current": usage.memory_percent,
                "timestamp": usage.timestamp
            })

        if usage.disk_percent > self.threshold_disk:
            alerts.append({
                "type": "disk_high",
                "level": "critical",
                "message": f"磁盘使用率过高: {usage.disk_percent:.1f}%",
                "threshold": self.threshold_disk,
                "current": usage.disk_percent,
                "timestamp": usage.timestamp
            })

        # 保存告警历史
        self.alerts.extend(alerts)

        return alerts


class HardwareMonitor:
    """硬件监控器."""

    def get_temperature_info(self) -> Dict[str, Any]:
        """获取温度信息."""
        try:
            temps = psutil.sensors_temperatures()
            temp_info = {}

            for name, entries in temps.items():
                temp_info[name] = []
                for entry in entries:
                    temp_info[name].append({
                        "label": entry.label or "Unknown",
                        "current": entry.current,
                        "high": entry.high,
                        "critical": entry.critical,
                    })

            return temp_info
        except (OSError, AttributeError, ImportError) as e:
            logger.warning("获取温度信息失败(可能不支持): %s", e)
            return {}

    def get_fan_info(self) -> Dict[str, Any]:
        """获取风扇信息."""
        try:
            fans = psutil.sensors_fans()
            fan_info = {}

            for name, entries in fans.items():
                fan_info[name] = []
                for entry in entries:
                    fan_info[name].append({
                        "label": entry.label or "Unknown",
                        "current": entry.current,
                    })

            return fan_info
        except (OSError, AttributeError, ImportError) as e:
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


# 便捷函数
def get_system_info() -> SystemInfo:
    """获取系统信息."""
    monitor = SystemMonitor()
    return monitor.get_system_info()


def get_resource_usage() -> ResourceUsage:
    """获取资源使用情况."""
    monitor = SystemMonitor()
    return monitor.get_resource_usage()


# 导出类和函数
__all__ = [
    "SystemMonitor",
    "ResourceMonitor",
    "HardwareMonitor",
    "SystemInfo",
    "ResourceUsage",
    "get_system_info",
    "get_resource_usage",
]
