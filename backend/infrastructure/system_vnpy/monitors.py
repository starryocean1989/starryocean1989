# -*- coding: utf-8 -*-
"""
监控模块 - 系统/进程监控和独立监控进程.

v0.50重构：合并system_monitor.py + process_monitor.py + monitor_process.py

包含：
- SystemMonitor: 系统资源监控（CPU、内存、磁盘、网络）
- ResourceMonitor: 资源阈值监控
- HardwareMonitor: 硬件传感器监控
- ProcessMonitor: 进程识别和指标采集
- BottleneckAnalyzer: 瓶颈分析
- MonitoringProcess: 独立监控进程（通过ZeroMQ与主进程通信）
"""

import logging
import os
import platform
import threading
import time
import zmq
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)

# 尝试导入psutil,如果没有则使用基础实现
try:
    import psutil
    from psutil._common import sdiskio, snetio

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil模块未安装,将使用基础系统监控功能")


# =============================================================================
# 常量定义
# =============================================================================


class DiskType:
    """磁盘类型常量."""

    HDD = "hdd"
    SSD = "ssd"
    NVME = "nvme"
    UNKNOWN = "unknown"


# 磁盘类型对应的I/O阈值 (KB/s)
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
    bottleneck_percent: float  # 瓶颈项的使用率
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

    def _detect_disk_type(self, device_name: str) -> str:
        """检测单个磁盘的类型.

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
                                for keyword in ["SSD", "SOLID STATE", "NVME"]
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
            logger.error("获取磁盘类型信息失败: %s", e)

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
                # None表示返回自上次调用以来的CPU使用率，不阻塞
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

    def get_disk_io_speed(self) -> Dict[str, Dict[str, Any]]:
        """获取各磁盘I/O速度 (MB/s).

        Returns:
            Dict: 各磁盘的读写速度和类型信息，格式: {
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

            # 获取所有磁盘分区
            partitions = psutil.disk_partitions()
            io_speeds = {}

            # 获取磁盘类型信息
            disks_info = self.get_disks_with_types()

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
                        read_speed_kbps = read_speed_mbps * 1024
                        write_speed_kbps = write_speed_mbps * 1024

                        # 使用挂载点作为key（更友好）
                        mount_point = partition.mountpoint

                        # 获取该磁盘的类型和阈值信息
                        disk_info = disks_info.get(mount_point, {})
                        disk_type = disk_info.get("type", DiskType.UNKNOWN)
                        read_threshold = disk_info.get("read_threshold_kbps", 400000)
                        write_threshold = disk_info.get("write_threshold_kbps", 300000)

                        io_speeds[mount_point] = {
                            "read_speed": round(read_speed_mbps, 2),
                            "write_speed": round(write_speed_mbps, 2),
                            "read_speed_kbps": round(read_speed_kbps, 2),
                            "write_speed_kbps": round(write_speed_kbps, 2),
                            "disk_type": disk_type,
                            "read_threshold": read_threshold,
                            "write_threshold": write_threshold,
                        }

                except (PermissionError, OSError) as e:
                    logger.debug("无法获取磁盘 %s 的I/O速度: %s", partition.device, e)
                    continue

            return io_speeds

        except Exception as e:
            logger.error("获取磁盘I/O速度失败: %s", e)
            return {}

    async def get_disk_io_speed_async(self) -> Dict[str, Dict[str, Any]]:
        """获取各磁盘I/O速度 (MB/s) - 异步版本.

        Returns:
            Dict: 各磁盘的读写速度，格式: {"C:": {"read_speed": 50.2, "write_speed": 30.1}, ...}
        """
        try:
            if not HAS_PSUTIL:
                return {}

            # 导入asyncio
            import asyncio

            # 获取所有磁盘分区
            partitions = psutil.disk_partitions()
            io_speeds = {}

            # 获取磁盘类型信息
            disks_info = self.get_disks_with_types()

            # 获取第一次I/O计数
            io_counters_1: Any = psutil.disk_io_counters(perdisk=True)
            await asyncio.sleep(0.1)  # 异步等待100ms
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
                        read_speed_kbps = read_speed_mbps * 1024
                        write_speed_kbps = write_speed_mbps * 1024

                        # 使用挂载点作为key（更友好）
                        mount_point = partition.mountpoint

                        # 获取该磁盘的类型和阈值信息
                        disk_info = disks_info.get(mount_point, {})
                        disk_type = disk_info.get("type", DiskType.UNKNOWN)
                        read_threshold = disk_info.get("read_threshold_kbps", 400000)
                        write_threshold = disk_info.get("write_threshold_kbps", 300000)

                        io_speeds[mount_point] = {
                            "read_speed": round(read_speed_mbps, 2),
                            "write_speed": round(write_speed_mbps, 2),
                            "read_speed_kbps": round(read_speed_kbps, 2),
                            "write_speed_kbps": round(write_speed_kbps, 2),
                            "disk_type": disk_type,
                            "read_threshold": read_threshold,
                            "write_threshold": write_threshold,
                        }

                except (PermissionError, OSError) as e:
                    logger.debug("无法获取磁盘 %s 的I/O速度: %s", partition.device, e)
                    continue

            return io_speeds

        except Exception as e:
            logger.error("获取磁盘I/O速度失败(异步): %s", e)
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

    def get_cpu_os_detailed(self) -> Dict[str, Any]:
        """获取更细粒度的CPU/OS指标（尽力而为，跨平台容错）.

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

                scale = 10.0  # 0.1s → 每秒
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
            logger.error("获取CPU/OS详细指标失败: %s", e)
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

            # 近似：通过 swap_memory 的 sin/sout（Linux为主）
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
            logger.error("获取内存子系统指标失败: %s", e)
            return {}

    def get_storage_subsystem_metrics(self) -> Dict[str, Any]:
        """获取存储子系统指标（队列深度不可跨平台，返回None；平均延迟近似估计）."""
        try:
            if not HAS_PSUTIL:
                return {}

            io1: Any = psutil.disk_io_counters(perdisk=True)
            time.sleep(0.1)
            io2: Any = psutil.disk_io_counters(perdisk=True)
            if not io1 or not io2:
                return {}

            disks: Dict[str, Any] = {}
            for k in io1.keys():
                if k not in io2:
                    continue
                try:
                    a1 = io1[k]
                    a2 = io2[k]
                    read_ios = max(0, a2.read_count - a1.read_count)
                    write_ios = max(0, a2.write_count - a1.write_count)
                    read_bytes = max(0, a2.read_bytes - a1.read_bytes)
                    write_bytes = max(0, a2.write_bytes - a1.write_bytes)

                    # psutil 在部分平台提供 read_time / write_time（毫秒）
                    read_time_ms = getattr(a2, "read_time", 0) - getattr(a1, "read_time", 0)
                    write_time_ms = getattr(a2, "write_time", 0) - getattr(a1, "write_time", 0)
                    io_ops = max(1, read_ios + write_ios)
                    avg_latency_ms = None
                    try:
                        total_time_ms = max(0, read_time_ms + write_time_ms)
                        avg_latency_ms = total_time_ms / float(io_ops)
                    except Exception:
                        avg_latency_ms = None

                    avg_read_size = (read_bytes / read_ios) if read_ios > 0 else None
                    avg_write_size = (write_bytes / write_ios) if write_ios > 0 else None

                    disks[k] = {
                        "average_io_latency_ms": (
                            round(avg_latency_ms, 2) if avg_latency_ms is not None else None
                        ),
                        "queue_depth": None,  # 无法跨平台获取
                        "avg_read_size_bytes": int(avg_read_size) if avg_read_size else None,
                        "avg_write_size_bytes": int(avg_write_size) if avg_write_size else None,
                    }
                except Exception:
                    continue

            return {"disks": disks}
        except Exception as e:
            logger.error("获取存储子系统指标失败: %s", e)
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
            logger.error("获取网络子系统指标失败: %s", e)
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
            logger.error("获取网络速度失败(异步): %s", e)
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
        # 🚀 使用纯Python监控器（无需外部软件）
        try:
            from backend.infrastructure.system_vnpy.hardware_temp import get_pure_hardware_monitor

            self._pure_monitor = get_pure_hardware_monitor()
            logger.info("✅ 纯Python温度监控初始化成功")
        except Exception as e:
            logger.warning("纯Python温度监控初始化失败: %s", e)
            self._pure_monitor = None

    def get_temperature_wmi(self) -> Dict[str, Any]:
        """通过WMI获取温度信息（保留兼容性，优先使用纯Python方案）."""
        # 🚀 优先使用纯Python监控器
        if self._pure_monitor:
            try:
                temps = self._pure_monitor.get_all_temperatures()
                if temps:
                    return temps
            except Exception as e:
                logger.debug("纯Python温度监控失败，回退到WMI: %s", e)

        # Fallback: 旧的WMI方案（LibreHardwareMonitor）
        try:
            import wmi
            import pythoncom

            # 初始化COM
            pythoncom.CoInitialize()

            try:
                # 连接到 LibreHardwareMonitor WMI namespace
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
                pythoncom.CoUninitialize()

        except Exception as e:
            logger.debug("WMI温度读取失败: %s", e)
            return {}

    def get_temperature_info(self) -> Dict[str, Any]:
        """获取温度信息（优先纯Python，fallback到WMI和psutil）."""
        # 🚀 方案1: 纯Python监控器（推荐）
        if self._pure_monitor:
            try:
                temps = self._pure_monitor.get_all_temperatures()
                if temps:
                    return temps
            except Exception as e:
                logger.debug("纯Python温度监控失败: %s", e)

        # 方案2: WMI（LibreHardwareMonitor）
        temp_info = self.get_temperature_wmi()
        if temp_info:
            return temp_info

        # 方案3: psutil（Linux/某些Windows配置）
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
                logger.debug("psutil不支持温度传感器（正常）")
                return {}

        except (OSError, ImportError) as e:
            logger.debug("获取温度信息失败: %s", e)
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
        self, process_id: str, process_name: str = "", process_type: str = ""
    ) -> Optional[ProcessMetrics]:
        """获取进程的性能指标.

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
            # None或0表示返回自上次调用以来的CPU使用率，不阻塞
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
        self.context = zmq.Context()

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
                        logger.error("接收服务状态失败: %s", e)

                # 4. 处理查询请求（持续监听，不会错过）
                if self.rep_socket in socks:
                    try:
                        _ = self.rep_socket.recv_json(zmq.NOBLOCK)
                        self.rep_socket.send_json(self.cached_data, zmq.NOBLOCK)
                        logger.debug("已响应监控数据查询")
                    except zmq.Again:
                        pass
                    except Exception as e:
                        logger.error("处理查询失败: %s", e)

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
            logger.error("采集进程指标失败: %s", e)
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
    推送的业务指标，存储在内存队列中，提供统计摘要。

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

        self.logger.info("业务指标采集器已初始化（窗口大小: %d秒）", window_size)

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

    def get_metric_history(self, metric_type: str, duration_sec: int = 60) -> List[Dict[str, Any]]:
        """获取指定指标的历史数据.

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
    """获取业务指标采集器的全局单例."""
    global _business_metrics_collector_instance
    if _business_metrics_collector_instance is None:
        with _collector_lock:
            if _business_metrics_collector_instance is None:
                _business_metrics_collector_instance = BusinessMetricsCollector()
    return _business_metrics_collector_instance
