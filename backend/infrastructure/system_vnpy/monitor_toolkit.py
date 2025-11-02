# -*- coding: utf-8 -*-
"""
Monitor Toolkit - 监控工具集

核心职责:
- 提供监控相关的工具类和辅助功能
- 工具类独立性强,可单独测试
- 支持同步和异步接口

文件组织(AI Debug友好):
- Part 1: 管理员权限工具
- Part 2: 错误计数器
- Part 3: SMART监控
- Part 4: 事件定义
- Part 5: 监控版事件引擎
- Part 6: 服务工具
- Part 7: 性能分析
- Part 8: 网络工具

Author: System Refactoring Team
Date: 2025-01-09
Version: v1.0 (Complete Refactor)
"""

import ctypes
import logging
import socket
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Literal, Optional, Tuple

# VnPy导入
try:
    from vnpy.event import Event, EventEngine
except ImportError:
    EventEngine = object  # type: ignore[misc,assignment]
    Event = object  # type: ignore[misc,assignment]

# 日志配置
logger = logging.getLogger("monitor_toolkit")

# ==============================================================================
# Part 1: 管理员权限工具
# ==============================================================================


def is_admin() -> bool:
    """检查当前进程是否具有管理员权限

    Returns:
        bool: 如果具有管理员权限返回True
    """
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception as e:
        logger.error(f"检查管理员权限失败: {e}")
        return False


def run_as_admin(_wait: bool = True) -> Optional[int]:
    """以管理员权限重新启动当前脚本

    Args:
        _wait: 是否等待新进程结束(默认True)[预留参数,暂未实现]

    Returns:
        Optional[int]: 如果wait=True,返回新进程的退出码;否则返回None

    Note:
        此函数会终止当前进程!
    """
    if is_admin():
        logger.info("当前已具有管理员权限")
        return None

    logger.info("正在请求管理员权限...")

    try:
        # 获取当前脚本路径和参数
        script = sys.argv[0]
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])

        # 使用ShellExecute以管理员身份运行
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,  # hwnd
            "runas",  # lpVerb: 以管理员身份运行
            sys.executable,  # lpFile: Python解释器
            f'"{script}" {params}',  # lpParameters: 脚本和参数
            None,  # lpDirectory
            1,  # nShowCmd: SW_NORMAL
        )

        # ShellExecuteW返回值: > 32: 成功, <= 32: 错误码
        if ret <= 32:
            logger.error(f"以管理员身份启动失败,错误码: {ret}")
            return None

        logger.info("✅ 已请求管理员权限,新进程已启动")

        # 退出当前进程
        sys.exit(0)

    except Exception as e:
        logger.error(f"请求管理员权限失败: {e}", exc_info=True)
        return None


def ensure_admin(auto_elevate: bool = True, message: Optional[str] = None) -> bool:
    """确保当前进程具有管理员权限

    Args:
        auto_elevate: 如果没有权限,是否自动提权(默认True)
        message: 自定义提示消息

    Returns:
        bool: 如果具有管理员权限返回True

    Note:
        如果auto_elevate=True且没有权限,此函数会重启进程并退出当前进程!
    """
    if is_admin():
        return True

    if message:
        logger.warning(message)
    else:
        logger.warning("=" * 80)
        logger.warning("⚠️  此应用需要管理员权限才能访问硬件传感器")
        logger.warning("=" * 80)

    if not auto_elevate:
        logger.warning("\n请以管理员身份运行此程序。")
        return False

    logger.warning("\n正在请求管理员权限...")
    logger.warning("(如果出现UAC提示,请点击'是')")

    run_as_admin()

    # 如果run_as_admin失败(没有退出进程),返回False
    return False


def check_admin_for_hardware_monitoring() -> bool:
    """检查硬件监控所需的管理员权限

    专门用于硬件监控场景,提供友好的提示信息。

    Returns:
        bool: 如果具有管理员权限返回True
    """
    if is_admin():
        logger.info("✅ 已具有管理员权限(硬件监控)")
        return True

    logger.warning("❌ 缺少管理员权限(硬件监控功能可能受限)")
    logger.warning("提示: 某些硬件传感器(如AMD Ryzen温度)需要管理员权限")
    return False


# ==============================================================================
# Part 2: 错误计数器
# ==============================================================================


class ErrorCounter:
    """周期性错误计数器(单例模式)

    功能:
    1. 识别相同错误(按异常类型+消息前50字符)
    2. 首次出现: 详细输出到Terminal和数据库
    3. 后续出现: 仅计数,Terminal输出简要信息
    4. 里程碑记录: 每10次记录一次数据库日志
    """

    _instance: Optional["ErrorCounter"] = None
    _lock = Lock()

    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化错误计数器"""
        if hasattr(self, "_initialized"):
            return

        self._errors: Dict[str, int] = {}  # {error_key: count}
        self._first_seen: Dict[str, datetime] = {}  # {error_key: first_time}
        self._last_milestone: Dict[str, int] = {}  # {error_key: last_milestone_count}
        self._data_lock = Lock()
        self._initialized = True

    def _generate_error_key(self, exc_type: str, message: str) -> str:
        """生成错误唯一标识

        Args:
            exc_type: 异常类型名称
            message: 错误消息

        Returns:
            错误唯一标识
        """
        # 取消息前50字符作为标识(避免参数变化导致误判为不同错误)
        message_prefix = message[:50] if message else ""
        return f"{exc_type}:{message_prefix}"

    def record_error(
        self, exc_type: str, message: str, traceback_str: Optional[str] = None
    ) -> Tuple[bool, int, bool]:
        """记录错误

        Args:
            exc_type: 异常类型名称
            message: 错误消息
            traceback_str: 堆栈跟踪字符串(可选)

        Returns:
            (是否需要详细输出, 当前计数, 是否达到里程碑)
        """
        error_key = self._generate_error_key(exc_type, message)

        with self._data_lock:
            # 首次出现
            if error_key not in self._errors:
                self._errors[error_key] = 1
                self._first_seen[error_key] = datetime.now()
                self._last_milestone[error_key] = 0
                return (True, 1, True)  # 需要详细输出,计数为1,算作里程碑

            # 后续出现
            self._errors[error_key] += 1
            current_count = self._errors[error_key]

            # 检查是否达到里程碑(每10次)
            last_milestone = self._last_milestone.get(error_key, 0)
            is_milestone = (current_count % 10 == 0) and (current_count > last_milestone)

            if is_milestone:
                self._last_milestone[error_key] = current_count

            return (False, current_count, is_milestone)

    def get_count(self, exc_type: str, message: str) -> int:
        """获取错误计数

        Args:
            exc_type: 异常类型名称
            message: 错误消息

        Returns:
            错误计数
        """
        error_key = self._generate_error_key(exc_type, message)
        with self._data_lock:
            return self._errors.get(error_key, 0)

    def reset(self) -> None:
        """重置所有计数器(用于测试或手动重置)"""
        with self._data_lock:
            self._errors.clear()
            self._first_seen.clear()
            self._last_milestone.clear()

    def get_summary(self) -> Dict[str, int]:
        """获取所有错误的摘要

        Returns:
            错误摘要字典 {error_key: count}
        """
        with self._data_lock:
            return self._errors.copy()


# 全局单例实例
_error_counter: Optional[ErrorCounter] = None


def get_error_counter() -> ErrorCounter:
    """获取全局错误计数器实例

    Returns:
        ErrorCounter实例
    """
    global _error_counter
    if _error_counter is None:
        _error_counter = ErrorCounter()
    return _error_counter


# ==============================================================================
# Part 3: SMART监控
# ==============================================================================


class DiskType(Enum):
    """硬盘类型枚举"""

    UNKNOWN = "unknown"
    HDD = "hdd"
    SSD = "ssd"
    NVME = "nvme"


@dataclass
class SmartAttribute:
    """SMART属性"""

    id: int
    name: str
    value: int
    worst: int
    threshold: int
    raw_value: int
    status: str  # OK, WARNING, CRITICAL


@dataclass
class DiskSmartData:
    """硬盘SMART数据"""

    disk_name: str
    model: str
    serial: str
    capacity: str
    interface: str
    assessment: str  # PASS, FAIL, UNKNOWN
    temperature: Optional[int] = None
    power_on_hours: Optional[int] = None
    reallocated_sectors: Optional[int] = None
    pending_sectors: Optional[int] = None
    uncorrectable_errors: Optional[int] = None
    attributes: Optional[List[SmartAttribute]] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.attributes is None:
            self.attributes = []
        if self.timestamp is None:
            self.timestamp = datetime.now()


class WMISmartMonitor:
    """基于WMI的SMART监控器 - 纯Python实现

    使用Windows WMI接口获取硬盘健康状态:
    - MSStorageDriver_FailurePredictStatus: 预测故障状态
    - MSStorageDriver_FailurePredictData: SMART属性数据
    - Win32_DiskDrive: 硬盘基本信息
    """

    def __init__(self):
        self._available = False
        self._wmi = None
        self._wmi_cimv2 = None
        self._thread_local_wmi = {}  # 线程本地WMI实例
        self._initialize_wmi()

    def _initialize_wmi(self):
        """初始化WMI连接"""
        try:
            import wmi

            self._wmi = wmi.WMI(namespace="root\\wmi")
            self._wmi_cimv2 = wmi.WMI()  # 用于Win32_DiskDrive
            self._available = True
            logger.info("✅ WMI SMART监控器初始化成功")
        except ImportError:
            logger.warning("WMI模块未安装,SMART监控不可用 (pip install wmi)")
        except Exception as e:
            logger.warning(f"WMI初始化失败: {e}")

    def _get_thread_wmi(self):
        """获取线程本地的WMI实例(COM线程安全)"""
        import threading

        thread_id = threading.current_thread().ident

        if thread_id not in self._thread_local_wmi:
            try:
                # 在线程中初始化COM
                try:
                    import pythoncom

                    pythoncom.CoInitialize()  # type: ignore[attr-defined]
                except (ImportError, AttributeError):
                    pass  # 如果pythoncom不可用,继续尝试

                import wmi

                self._thread_local_wmi[thread_id] = {
                    "wmi": wmi.WMI(namespace="root\\wmi"),
                    "wmi_cimv2": wmi.WMI(),
                }
                logger.debug(f"为线程{thread_id}创建WMI实例")
            except Exception as e:
                logger.error(f"线程{thread_id}创建WMI实例失败: {e}")
                return None

        return self._thread_local_wmi[thread_id]

    def is_available(self) -> bool:
        """检查WMI是否可用"""
        return self._available

    def get_smart_data(self) -> Dict[str, DiskSmartData]:
        """获取所有硬盘的SMART数据

        Returns:
            Dict[disk_name, DiskSmartData]: 硬盘名称到SMART数据的映射
        """
        if not self._available:
            logger.debug("WMI不可用")
            return {}

        result = {}

        try:
            # 1. 获取硬盘基本信息
            disks_info = self._get_disks_basic_info()

            # 2. 获取SMART健康状态
            health_status = self._get_failure_predict_status()

            # 3. 获取SMART详细数据
            smart_data = self._get_failure_predict_data()

            # 4. 合并数据
            for instance_name, disk_info in disks_info.items():
                try:
                    # 获取健康状态(可能为空,需要管理员权限)
                    health = health_status.get(instance_name, {})
                    predict_failure = health.get("predict_failure", False)

                    # 获取SMART属性(可能为空,需要管理员权限)
                    attributes = smart_data.get(instance_name, [])

                    # 解析关键SMART属性
                    temperature = None
                    power_on_hours = None
                    reallocated_sectors = None
                    pending_sectors = None
                    uncorrectable_errors = None

                    for attr in attributes:
                        if attr.id == 194:  # Temperature
                            temperature = attr.raw_value
                        elif attr.id == 9:  # Power On Hours
                            power_on_hours = attr.raw_value
                        elif attr.id == 5:  # Reallocated Sectors Count
                            reallocated_sectors = attr.raw_value
                        elif attr.id == 197:  # Current Pending Sector Count
                            pending_sectors = attr.raw_value
                        elif attr.id == 187 or attr.id == 188:  # Uncorrectable Errors
                            uncorrectable_errors = attr.raw_value

                    # 评估健康状态
                    if not attributes and not health_status:
                        assessment = "未知(需要管理员权限)"
                    else:
                        assessment = self._assess_health(
                            predict_failure,
                            attributes,
                            reallocated_sectors,
                            pending_sectors,
                            uncorrectable_errors,
                        )

                    # 构建SMART数据对象
                    smart_data_obj = DiskSmartData(
                        disk_name=disk_info.get("name", instance_name),
                        model=disk_info.get("model", "Unknown"),
                        serial=disk_info.get("serial", "Unknown"),
                        capacity=disk_info.get("capacity", "Unknown"),
                        interface=disk_info.get("interface", "Unknown"),
                        assessment=assessment,
                        temperature=temperature,
                        power_on_hours=power_on_hours,
                        reallocated_sectors=(
                            reallocated_sectors if reallocated_sectors is not None else 0
                        ),
                        pending_sectors=pending_sectors if pending_sectors is not None else 0,
                        uncorrectable_errors=(
                            uncorrectable_errors if uncorrectable_errors is not None else 0
                        ),
                        attributes=attributes,
                        timestamp=datetime.now(),
                    )

                    result[disk_info.get("name", instance_name)] = smart_data_obj

                except Exception as e:
                    logger.debug(f"处理硬盘SMART数据失败 ({instance_name}): {e}")

            logger.info(f"成功读取 {len(result)} 个硬盘的WMI-SMART数据")

        except Exception as e:
            logger.error(f"获取WMI-SMART数据失败: {e}", exc_info=True)

        return result

    def _get_disks_basic_info(self) -> Dict[str, Dict[str, Any]]:
        """获取硬盘基本信息(型号、序列号等)"""
        disks = {}

        try:
            thread_wmi = self._get_thread_wmi()
            if not thread_wmi:
                logger.warning("无法获取线程本地WMI实例")
                return {}

            for disk in thread_wmi["wmi_cimv2"].Win32_DiskDrive():
                instance_name = disk.PNPDeviceID.replace("\\", "_")
                device_id = disk.DeviceID
                disk_name = device_id.split("\\")[-1]

                # 检测硬盘类型
                disk_type = DiskType.UNKNOWN
                if disk.InterfaceType and "NVMe" in disk.InterfaceType:
                    disk_type = DiskType.NVME
                elif disk.Model and any(
                    kw in disk.Model.upper() for kw in ["SSD", "SOLID STATE", "NVME"]
                ):
                    disk_type = DiskType.SSD
                else:
                    disk_type = DiskType.HDD

                # 格式化容量
                capacity = "Unknown"
                if disk.Size:
                    capacity_gb = int(disk.Size) / (1024**3)
                    capacity = f"{capacity_gb:.1f} GB"

                disks[instance_name] = {
                    "name": disk_name,
                    "model": disk.Model or "Unknown",
                    "serial": disk.SerialNumber.strip() if disk.SerialNumber else "Unknown",
                    "capacity": capacity,
                    "interface": disk.InterfaceType or "Unknown",
                    "disk_type": disk_type.value,
                }

        except Exception as e:
            logger.debug(f"获取硬盘基本信息失败: {e}")

        return disks

    def _get_failure_predict_status(self) -> Dict[str, Dict[str, Any]]:
        """获取故障预测状态(SMART健康状态)"""
        status_map = {}

        try:
            thread_wmi = self._get_thread_wmi()
            if not thread_wmi:
                return {}

            for item in thread_wmi["wmi"].MSStorageDriver_FailurePredictStatus():
                instance_name = item.InstanceName.strip("\x00")
                status_map[instance_name] = {
                    "predict_failure": item.PredictFailure,
                    "reason": item.Reason if hasattr(item, "Reason") else 0,
                }
        except Exception as e:
            logger.debug(f"获取故障预测状态失败: {e}")

        return status_map

    def _get_failure_predict_data(self) -> Dict[str, List[SmartAttribute]]:
        """获取故障预测数据(SMART属性)"""
        data_map = {}

        try:
            thread_wmi = self._get_thread_wmi()
            if not thread_wmi:
                return {}

            for item in thread_wmi["wmi"].MSStorageDriver_FailurePredictData():
                instance_name = item.InstanceName.strip("\x00")
                vendor_specific = item.VendorSpecific

                # 解析SMART属性
                attributes = self._parse_smart_attributes(vendor_specific)
                data_map[instance_name] = attributes

        except Exception as e:
            logger.debug(f"获取故障预测数据失败: {e}")

        return data_map

    def _parse_smart_attributes(self, vendor_specific: bytes) -> List[SmartAttribute]:
        """解析SMART属性数据"""
        attributes = []

        try:
            # SMART属性结构: 每个属性12字节
            for i in range(0, len(vendor_specific), 12):
                if i + 12 > len(vendor_specific):
                    break

                attr_data = vendor_specific[i : i + 12]

                attr_id = attr_data[0]
                if attr_id == 0:  # 跳过无效属性
                    continue

                # 解析属性值
                current_value = attr_data[3]
                worst_value = attr_data[4]
                raw_value = int.from_bytes(attr_data[5:11], byteorder="little")
                threshold = attr_data[1]

                # 评估状态
                if current_value <= threshold:
                    status = "CRITICAL"
                elif worst_value <= threshold:
                    status = "WARNING"
                else:
                    status = "OK"

                # SMART属性名称映射
                attr_name = self._get_smart_attr_name(attr_id)

                attributes.append(
                    SmartAttribute(
                        id=attr_id,
                        name=attr_name,
                        value=current_value,
                        worst=worst_value,
                        threshold=threshold,
                        raw_value=raw_value,
                        status=status,
                    )
                )

        except Exception as e:
            logger.debug(f"解析SMART属性失败: {e}")

        return attributes

    @staticmethod
    def _get_smart_attr_name(attr_id: int) -> str:
        """获取SMART属性名称"""
        names = {
            1: "Read Error Rate",
            5: "Reallocated Sectors Count",
            9: "Power-On Hours",
            12: "Power Cycle Count",
            187: "Reported Uncorrectable Errors",
            188: "Command Timeout",
            194: "Temperature",
            197: "Current Pending Sector Count",
            198: "Offline Uncorrectable Sector Count",
        }
        return names.get(attr_id, f"Unknown ({attr_id})")

    @staticmethod
    def _assess_health(
        predict_failure: bool,
        attributes: List[SmartAttribute],
        reallocated: Optional[int],
        pending: Optional[int],
        uncorrectable: Optional[int],
    ) -> str:
        """评估硬盘健康状态"""
        if predict_failure:
            return "故障预测失败"

        # 检查关键属性
        if uncorrectable and uncorrectable > 0:
            return "严重警告(无法校正扇区)"

        if reallocated and reallocated > 5:
            return "警告(重分配扇区过多)"

        if pending and pending > 5:
            return "警告(待映射扇区过多)"

        # 检查任何CRITICAL状态的属性
        for attr in attributes:
            if attr.status == "CRITICAL":
                return f"严重警告({attr.name})"

        return "正常"


# WMI SMART监控器全局实例
_wmi_smart_monitor: Optional[WMISmartMonitor] = None


def get_wmi_smart_monitor() -> WMISmartMonitor:
    """获取WMI SMART监控器全局实例"""
    global _wmi_smart_monitor
    if _wmi_smart_monitor is None:
        _wmi_smart_monitor = WMISmartMonitor()
    return _wmi_smart_monitor


class SmartMonitor:
    """SMART监控器(带告警)

    封装WMISmartMonitor,提供告警功能
    """

    def __init__(self):
        self.wmi_monitor = get_wmi_smart_monitor()

    def get_smart_data_with_alerts(self) -> Dict[str, Any]:
        """获取SMART数据并生成告警

        Returns:
            包含SMART数据和告警的字典
        """
        smart_data = self.wmi_monitor.get_smart_data()

        alerts = []
        for disk_name, data in smart_data.items():
            # 检查评估结果
            if "故障" in data.assessment or "警告" in data.assessment:
                alerts.append(
                    {
                        "disk": disk_name,
                        "level": "CRITICAL" if "故障" in data.assessment else "WARNING",
                        "message": data.assessment,
                        "details": {
                            "model": data.model,
                            "reallocated_sectors": data.reallocated_sectors,
                            "pending_sectors": data.pending_sectors,
                            "uncorrectable_errors": data.uncorrectable_errors,
                        },
                    }
                )

        return {"smart_data": smart_data, "alerts": alerts}


# ==============================================================================
# Part 4: 事件定义
# ==============================================================================

# 系统指标事件(CPU、内存、磁盘、网络使用率等)
EVENT_SYSTEM_METRICS = "eSystemMetrics"

# 硬件传感器事件(温度、功耗、电压、风扇转速等)
EVENT_HARDWARE_SENSORS = "eHardwareSensors"

# 瓶颈分析事件(系统性能瓶颈诊断)
EVENT_BOTTLENECK_ANALYSIS = "eBottleneckAnalysis"

# 场景分析事件(当前运行场景的优化建议)
EVENT_SCENARIO_ANALYSIS = "eScenarioAnalysis"

# 进程监控事件(Python进程、关键进程状态)
EVENT_PROCESS_MONITORING = "eProcessMonitoring"

# 服务状态事件(各服务的健康状态)
EVENT_SERVICE_MONITORING = "eServiceMonitoring"

# SMART数据事件(硬盘健康监控)
EVENT_SMART_DATA = "eSmartData"

# 性能指标汇总事件(多维度性能概览)
EVENT_PERFORMANCE_SUMMARY = "ePerformanceSummary"

# 系统管理相关事件
EVENT_SYSTEM_STATUS = "eSystemStatus"  # 系统状态更新事件
EVENT_PERFORMANCE_METRICS = "ePerformanceMetrics"  # 性能指标更新事件
EVENT_SERVICE_STATUS = "eServiceStatus"  # 服务状态更新事件
EVENT_DIAGNOSTIC_RESULT = "eDiagnosticResult"  # 诊断结果事件
EVENT_PROCESS_STATUS = "eProcessStatus"  # 进程状态更新事件

# 跨模块集成事件
EVENT_STRATEGY_STATUS_CHANGED = "eStrategyStatusChanged"  # 策略状态变化事件
EVENT_GATEWAY_STATUS_CHANGED = "eGatewayStatusChanged"  # 网关状态变化事件
EVENT_DATA_DOWNLOAD_COMPLETE = "eDataDownloadComplete"  # 数据下载完成事件
EVENT_RECORDING_STATUS_CHANGED = "eRecordingStatusChanged"  # 录制状态变化事件

# 日志和告警系统事件
EVENT_LOG_RECORD = "eLogRecord"  # 日志记录事件
EVENT_ALERT_CREATED = "eAlertCreated"  # 告警创建事件
EVENT_ALERT_UPDATED = "eAlertUpdated"  # 告警更新事件


# ==============================================================================
# Part 5: 监控版事件引擎
# ==============================================================================


class MonitoredEventEngine(EventEngine):
    """带监控的事件引擎

    扩展功能:
    1. 记录事件队列深度
    2. 记录事件处理延迟
    3. 上报到BusinessMetricsCollector

    使用方式:
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

        # 业务指标采集器(外部注入)
        self._business_metrics = None

        # 本地采样缓存(用于统计)
        self._queue_depth_samples = deque(maxlen=100)
        self._latency_samples = deque(maxlen=100)

        # 统计信息
        self._total_events_processed = 0
        self._last_report_time = time.time()
        self._report_interval = 5.0  # 每5秒输出一次统计(可选)

        logger.info("✅ MonitoredEventEngine已初始化(支持队列深度和延迟监控)")

    def set_business_metrics_collector(self, collector):
        """设置业务指标采集器

        Args:
            collector: BusinessMetricsCollector实例
        """
        self._business_metrics = collector
        logger.info("✅ BusinessMetricsCollector已注入到MonitoredEventEngine")

    def put(self, event: "Event"):  # type: ignore[override]
        """重写put方法,记录入队时间和队列深度

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
                # 静默失败,不影响事件处理
                logger.debug(f"上报event_queue_depth失败: {e}")

        # 3. 记录入队时间(用于后续计算延迟)
        event._enqueue_time = time.time()

        # 4. 调用父类方法(实际入队)
        super().put(event)

    def _process(self, event: "Event"):  # type: ignore[override]
        """重写_process方法,记录处理延迟

        Args:
            event: 事件对象
        """
        # 1. 计算处理延迟(毫秒)
        if hasattr(event, "_enqueue_time"):
            latency_ms = (time.time() - event._enqueue_time) * 1000
            self._latency_samples.append(latency_ms)

            # 2. 上报延迟到监控系统
            if self._business_metrics:
                try:
                    self._business_metrics.record_metric(
                        "event_processing_latency_ms", latency_ms
                    )
                except Exception as e:
                    # 静默失败
                    logger.debug(f"上报event_processing_latency_ms失败: {e}")

        # 3. 更新统计
        self._total_events_processed += 1

        # 4. 定期输出统计信息(可选)
        self._maybe_report_stats()

        # 5. 调用父类方法(实际处理)
        super()._process(event)

    def _maybe_report_stats(self):
        """定期输出统计信息(每5秒)"""
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
            "avg_queue_depth": sum(self._queue_depth_samples)
            / len(self._queue_depth_samples),
            "avg_latency_ms": sum(self._latency_samples) / len(self._latency_samples),
            "max_queue_depth": max(self._queue_depth_samples),
            "max_latency_ms": max(self._latency_samples),
            "current_queue_depth": self._queue.qsize(),
        }


# ==============================================================================
# Part 6: 服务工具
# ==============================================================================


class ServiceHealthChecker:
    """服务健康检查器

    功能:
    - 调用次数统计
    - 响应时间监控
    - 成功率计算
    """

    def __init__(self):
        self._stats: Dict[str, Dict[str, Any]] = {}

    def record_call(self, service_name: str, success: bool, response_time: float):
        """记录服务调用

        Args:
            service_name: 服务名称
            success: 是否成功
            response_time: 响应时间(秒)
        """
        if service_name not in self._stats:
            self._stats[service_name] = {
                "total": 0,
                "success": 0,
                "failed": 0,
                "total_response_time": 0.0,
            }

        stats = self._stats[service_name]
        stats["total"] += 1

        if success:
            stats["success"] += 1
        else:
            stats["failed"] += 1

        stats["total_response_time"] += response_time

    def get_health_status(self, service_name: str) -> Dict[str, Any]:
        """获取服务健康状态

        Args:
            service_name: 服务名称

        Returns:
            健康状态字典
        """
        if service_name not in self._stats:
            return {"status": "unknown", "message": "无调用记录"}

        stats = self._stats[service_name]
        total = stats["total"]
        success = stats["success"]

        success_rate = (success / total * 100) if total > 0 else 0
        avg_response_time = (
            stats["total_response_time"] / total if total > 0 else 0
        )

        # 评估健康状态
        if success_rate >= 90 and avg_response_time < 1.0:
            status = "healthy"
        elif success_rate >= 90:
            status = "degraded"
        else:
            status = "unhealthy"

        return {
            "status": status,
            "success_rate": success_rate,
            "avg_response_time": avg_response_time,
            "total_calls": total,
            "success_calls": success,
            "failed_calls": stats["failed"],
        }


class ServiceRestarter:
    """服务重启管理器"""

    def __init__(self):
        self._restart_counts: Dict[str, int] = {}

    def should_restart(self, service_name: str, health_status: Dict[str, Any]) -> bool:
        """判断是否应该重启服务

        Args:
            service_name: 服务名称
            health_status: 健康状态

        Returns:
            是否应该重启
        """
        # 连续5次检查失败
        if health_status["failed_calls"] >= 5:
            return True

        # 成功率低于50%
        if health_status["success_rate"] < 50:
            return True

        return False

    def record_restart(self, service_name: str):
        """记录重启次数

        Args:
            service_name: 服务名称
        """
        if service_name not in self._restart_counts:
            self._restart_counts[service_name] = 0

        self._restart_counts[service_name] += 1


# ==============================================================================
# Part 7: 性能分析
# ==============================================================================


class PerformanceAnalyzer:
    """性能瓶颈分析器"""

    @staticmethod
    def analyze_bottleneck(metrics: Dict[str, float]) -> Dict[str, Any]:
        """分析性能瓶颈

        Args:
            metrics: 性能指标

        Returns:
            瓶颈分析结果
        """
        cpu_usage = metrics.get("cpu_percent", 0)
        memory_usage = metrics.get("memory_percent", 0)
        disk_io_usage = metrics.get("disk_io_percent", 0)

        # 木桶理论: 找最短的板
        bottleneck_resource = "cpu"
        bottleneck_value = cpu_usage

        if memory_usage > bottleneck_value:
            bottleneck_resource = "memory"
            bottleneck_value = memory_usage

        if disk_io_usage > bottleneck_value:
            bottleneck_resource = "disk_io"
            bottleneck_value = disk_io_usage

        return {
            "bottleneck_resource": bottleneck_resource,
            "bottleneck_value": bottleneck_value,
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "disk_io_usage": disk_io_usage,
        }


class LogAnalyzer:
    """日志分析器"""

    @staticmethod
    def analyze_error_patterns(logs: List[str]) -> Dict[str, int]:
        """分析错误模式

        Args:
            logs: 日志列表

        Returns:
            错误模式统计
        """
        error_patterns = {}

        for log in logs:
            if "ERROR" in log or "CRITICAL" in log:
                # 提取错误类型(简单实现)
                if ":" in log:
                    error_type = log.split(":")[0]
                    error_patterns[error_type] = error_patterns.get(error_type, 0) + 1

        return error_patterns


# ==============================================================================
# Part 8: 网络工具
# ==============================================================================


class NetworkTester:
    """网络连通性测试器"""

    @staticmethod
    def test_connectivity(host: str, port: int, timeout: float = 3.0) -> bool:
        """测试网络连通性

        Args:
            host: 主机地址
            port: 端口号
            timeout: 超时时间(秒)

        Returns:
            是否连通
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception as e:
            logger.debug(f"网络连通性测试失败: {e}")
            return False


class PortScanner:
    """端口扫描器"""

    @staticmethod
    def scan_ports(host: str, ports: List[int], timeout: float = 1.0) -> Dict[int, bool]:
        """扫描端口

        Args:
            host: 主机地址
            ports: 端口列表
            timeout: 超时时间(秒)

        Returns:
            端口状态字典
        """
        results = {}

        for port in ports:
            results[port] = NetworkTester.test_connectivity(host, port, timeout)

        return results


# ==============================================================================
# 便捷函数
# ==============================================================================


def test_connectivity(host: str, port: int, timeout: float = 3.0) -> bool:
    """测试网络连通性(便捷函数)"""
    return NetworkTester.test_connectivity(host, port, timeout)


def scan_ports(host: str, ports: List[int], timeout: float = 1.0) -> Dict[int, bool]:
    """扫描端口(便捷函数)"""
    return PortScanner.scan_ports(host, ports, timeout)


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    # Part 1: 管理员权限工具
    "is_admin",
    "run_as_admin",
    "ensure_admin",
    "check_admin_for_hardware_monitoring",
    # Part 2: 错误计数器
    "ErrorCounter",
    "get_error_counter",
    # Part 3: SMART监控
    "DiskType",
    "SmartAttribute",
    "DiskSmartData",
    "WMISmartMonitor",
    "get_wmi_smart_monitor",
    "SmartMonitor",
    # Part 4: 事件定义
    "EVENT_SYSTEM_METRICS",
    "EVENT_HARDWARE_SENSORS",
    "EVENT_BOTTLENECK_ANALYSIS",
    "EVENT_SCENARIO_ANALYSIS",
    "EVENT_PROCESS_MONITORING",
    "EVENT_SERVICE_MONITORING",
    "EVENT_SMART_DATA",
    "EVENT_PERFORMANCE_SUMMARY",
    "EVENT_SYSTEM_STATUS",
    "EVENT_PERFORMANCE_METRICS",
    "EVENT_SERVICE_STATUS",
    "EVENT_DIAGNOSTIC_RESULT",
    "EVENT_PROCESS_STATUS",
    "EVENT_STRATEGY_STATUS_CHANGED",
    "EVENT_GATEWAY_STATUS_CHANGED",
    "EVENT_DATA_DOWNLOAD_COMPLETE",
    "EVENT_RECORDING_STATUS_CHANGED",
    "EVENT_LOG_RECORD",
    "EVENT_ALERT_CREATED",
    "EVENT_ALERT_UPDATED",
    # Part 5: 监控版事件引擎
    "MonitoredEventEngine",
    # Part 6: 服务工具
    "ServiceHealthChecker",
    "ServiceRestarter",
    # Part 7: 性能分析
    "PerformanceAnalyzer",
    "LogAnalyzer",
    # Part 8: 网络工具
    "NetworkTester",
    "PortScanner",
    "test_connectivity",
    "scan_ports",
]
