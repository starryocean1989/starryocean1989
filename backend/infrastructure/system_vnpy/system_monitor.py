# -*- coding: utf-8 -*-
"""
系统资源监控模块.

提供CPU,内存,磁盘,网络等系统资源的实时监控功能.
基于psutil库实现跨平台的系统监控能力.
"""

import logging
import os
import platform
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Union, cast

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

        # 🚀 性能优化：初始化CPU采样（建立baseline）
        # 第一次调用cpu_percent()建立基线，后续调用interval=None才有意义
        if HAS_PSUTIL:
            try:
                psutil.cpu_percent(interval=None)
            except Exception:
                pass

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
                # None表示返回自上次调用以来的CPU使用率，不阻塞
                cpu_percent_raw = psutil.cpu_percent(interval=None)
                # 确保返回值是float类型（而不是list）
                cpu_percent = float(cpu_percent_raw) if not isinstance(cpu_percent_raw, list) else 0.0

                # 内存使用率
                memory = psutil.virtual_memory()

                # 磁盘使用率（带超时保护）
                disk: Any = None
                try:
                    # 使用较短的超时避免阻塞
                    import signal
                    def timeout_handler(signum: int, frame: Any) -> None:
                        raise TimeoutError("磁盘使用率获取超时")

                    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(2)  # 2秒超时
                    disk = psutil.disk_usage("/")
                    signal.alarm(0)  # 取消闹钟
                    signal.signal(signal.SIGALRM, old_handler)
                except (TimeoutError, OSError, AttributeError):
                    # 如果超时或失败，使用默认值
                    logger.debug("磁盘使用率获取失败，使用默认值")
                    disk = type('DiskUsage', (), {'used': 50 * 1024 * 1024 * 1024, 'total': 100 * 1024 * 1024 * 1024})()

                # 网络流量
                network: Any = None
                try:
                    network = psutil.net_io_counters()
                except (OSError, AttributeError):
                    # 如果失败，使用默认值
                    logger.debug("网络流量获取失败，使用默认值")
                    network = type('NetIO', (), {'bytes_sent': 1024 * 1024, 'bytes_recv': 2048 * 1024})()

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
        """获取CPU详细信息."""
        try:
            if HAS_PSUTIL:
                cpu_freq = psutil.cpu_freq()
                cpu_times: Any = psutil.cpu_times()

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
                    },
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

    def get_disk_io_speed(self) -> Dict[str, Dict[str, float]]:
        """获取各磁盘I/O速度 (MB/s).

        Returns:
            Dict: 各磁盘的读写速度，格式: {"C:": {"read_speed": 50.2, "write_speed": 30.1}, ...}
        """
        try:
            if not HAS_PSUTIL:
                return {}

            # 获取所有磁盘分区
            partitions = psutil.disk_partitions()
            io_speeds = {}

            # 获取第一次I/O计数
            io_counters_1: Any = psutil.disk_io_counters(perdisk=True)
            time.sleep(0.1)  # 等待100ms
            io_counters_2: Any = psutil.disk_io_counters(perdisk=True)

            if not io_counters_1 or not io_counters_2:
                return {}

            # 计算每个磁盘的I/O速度
            for partition in partitions:
                try:
                    # 在Windows上，使用设备名（去除反斜杠）
                    # 例如：\\?\Volume{...} 或 C:\
                    device = partition.device

                    # Windows磁盘设备名处理
                    if platform.system() == "Windows":
                        # 对于形如 "C:\" 的设备，提取盘符
                        if ":" in device:
                            disk_key = device.split(":")[0]
                        else:
                            continue
                    else:
                        # Linux/Unix使用完整设备名
                        disk_key = device.replace("/dev/", "")

                    # 查找对应的I/O计数器
                    # 在Windows上，psutil返回的key可能是 "PhysicalDrive0" 等
                    # 我们需要通过分区映射到物理磁盘
                    found_counter = None
                    for counter_key in io_counters_1.keys():
                        # 简单匹配策略
                        if disk_key in counter_key or counter_key in disk_key:
                            found_counter = counter_key
                            break

                    if not found_counter:
                        # 尝试使用物理磁盘编号
                        if found_counter is None and len(io_counters_1) > 0:
                            # 使用第一个物理磁盘作为默认值
                            found_counter = list(io_counters_1.keys())[0]

                    if (
                        found_counter
                        and found_counter in io_counters_1
                        and found_counter in io_counters_2
                    ):
                        counter_1 = io_counters_1[found_counter]
                        counter_2 = io_counters_2[found_counter]

                        # 计算读写速度 (字节/秒 -> MB/秒)
                        read_bytes_diff = counter_2.read_bytes - counter_1.read_bytes
                        write_bytes_diff = counter_2.write_bytes - counter_1.write_bytes

                        read_speed_mbps = (read_bytes_diff / 0.1) / (1024 * 1024)  # 0.1秒间隔
                        write_speed_mbps = (write_bytes_diff / 0.1) / (1024 * 1024)

                        # 使用挂载点作为key（更友好）
                        mount_point = partition.mountpoint
                        io_speeds[mount_point] = {
                            "read_speed": round(read_speed_mbps, 2),
                            "write_speed": round(write_speed_mbps, 2),
                        }

                except (PermissionError, OSError) as e:
                    logger.debug("无法获取磁盘 %s 的I/O速度: %s", partition.device, e)
                    continue

            return io_speeds

        except Exception as e:
            logger.error("获取磁盘I/O速度失败: %s", e)
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
            # 这里使用一个保守的估算
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
            logger.error("获取网络速度失败: %s", e)
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

    def get_temperature_info(self) -> Dict[str, Any]:
        """获取温度信息."""
        try:
            if not HAS_PSUTIL:
                return {}

            # 使用try-except处理平台兼容性问题
            try:
                temps = psutil.sensors_temperatures()  # type: ignore
                temp_info = {}

                for name, entries in temps.items():
                    temp_info[name] = []
                    for entry in entries:
                        temp_info[name].append(
                            {
                                "label": entry.label or "Unknown",
                                "current": entry.current,
                                "high": entry.high,
                                "critical": entry.critical,
                            }
                        )

                return temp_info
            except AttributeError:
                logger.warning("当前平台不支持温度传感器")
                return {}

        except (OSError, ImportError) as e:
            logger.warning("获取温度信息失败(可能不支持): %s", e)
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
