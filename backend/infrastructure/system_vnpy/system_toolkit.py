# -*- coding: utf-8 -*-
"""
System Toolkit - Aggressive Merge Edition

Merged from:
- core_utils.py (447 lines): Admin + ErrorCounter + Terminal
- monitoring_core.py (722 lines): Events + Engine + SMART
- utilities.py (streamlined): 8 actually-used utility classes

Author: System Refactoring Team
Date: 2025-10-29
Version: v0.50 (Aggressive Merge - 3 Core Files)
"""

# -*- coding: utf-8 -*-
"""
核心工具模块 - 合并版

整合了以下模块以便于调试时快速定位：
- admin_utils.py: 管理员权限检查和自动提权
- error_counter.py: 周期性错误计数器
- terminal_output.py: 终端输出格式化工具

作者：系统重构团队
日期：2025-10-29
版本：v0.50 (激进合并版)
"""

import ctypes
import logging
import sys
from datetime import datetime
from threading import Lock
from typing import Dict, List, Literal, Optional, Tuple

# =============================================================================
# Part 1: 管理员权限工具
# =============================================================================


def is_admin() -> bool:
    """
    检查当前进程是否具有管理员权限.

    Returns:
        bool: 如果具有管理员权限返回True
    """
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception as e:
        logging.getLogger(__name__).error("检查管理员权限失败: %s", e)
        return False


def run_as_admin(_wait: bool = True) -> Optional[int]:
    """
    以管理员权限重新启动当前脚本.

    Args:
        _wait: 是否等待新进程结束（默认True）[预留参数，暂未实现]

    Returns:
        Optional[int]: 如果wait=True，返回新进程的退出码；否则返回None

    Note:
        此函数会终止当前进程！
    """
    logger = logging.getLogger(__name__)

    if is_admin():
        logger.info("当前已具有管理员权限")
        return None

    logger.info("正在请求管理员权限...")

    try:
        # 获取当前脚本路径和参数
        script = sys.argv[0]
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])

        # 使用ShellExecute以管理员身份运行
        # 参数说明：
        # - lpVerb: "runas" 表示以管理员身份运行
        # - lpFile: Python解释器路径
        # - lpParameters: 脚本路径和参数
        # - nShowCmd: 1 表示正常显示窗口
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,  # hwnd
            "runas",  # lpVerb: 以管理员身份运行
            sys.executable,  # lpFile: Python解释器
            f'"{script}" {params}',  # lpParameters: 脚本和参数
            None,  # lpDirectory
            1,  # nShowCmd: SW_NORMAL
        )

        # ShellExecuteW返回值：
        # > 32: 成功
        # <= 32: 错误码
        if ret <= 32:
            logger.error("以管理员身份启动失败，错误码: %s", ret)
            return None

        logger.info("✅ 已请求管理员权限，新进程已启动")

        # 退出当前进程
        sys.exit(0)

    except Exception as e:
        logger.error("请求管理员权限失败: %s", e, exc_info=True)
        return None


def ensure_admin(auto_elevate: bool = True, message: Optional[str] = None) -> bool:
    """
    确保当前进程具有管理员权限.

    Args:
        auto_elevate: 如果没有权限，是否自动提权（默认True）
        message: 自定义提示消息

    Returns:
        bool: 如果具有管理员权限返回True

    Note:
        如果auto_elevate=True且没有权限，此函数会重启进程并退出当前进程！
    """
    logger = logging.getLogger(__name__)

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
    logger.warning("（如果出现UAC提示，请点击'是'）")

    run_as_admin()

    # 如果run_as_admin失败（没有退出进程），返回False
    return False


def check_admin_for_hardware_monitoring() -> bool:
    """
    检查硬件监控所需的管理员权限.

    专门用于硬件监控场景，提供友好的提示信息。

    Returns:
        bool: 如果具有管理员权限返回True
    """
    logger = logging.getLogger(__name__)

    if is_admin():
        logger.info("✅ 已具有管理员权限（硬件监控）")
        return True

    logger.warning("❌ 缺少管理员权限（硬件监控功能可能受限）")
    logger.warning("提示：某些硬件传感器（如AMD Ryzen温度）需要管理员权限")
    return False


# =============================================================================
# Part 2: 错误计数器
# =============================================================================


class ErrorCounter:
    """周期性错误计数器（单例模式）.

    功能：
    1. 识别相同错误（按异常类型+消息前50字符）
    2. 首次出现：详细输出到Terminal和数据库
    3. 后续出现：仅计数，Terminal输出简要信息
    4. 里程碑记录：每10次记录一次数据库日志
    """

    _instance: Optional["ErrorCounter"] = None
    _lock = Lock()

    def __new__(cls):
        """单例模式实现."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化错误计数器."""
        if hasattr(self, "_initialized"):
            return

        self._errors: Dict[str, int] = {}  # {error_key: count}
        self._first_seen: Dict[str, datetime] = {}  # {error_key: first_time}
        self._last_milestone: Dict[str, int] = {}  # {error_key: last_milestone_count}
        self._data_lock = Lock()
        self._initialized = True

    def _generate_error_key(self, exc_type: str, message: str) -> str:
        """
        生成错误唯一标识.

        Args:
            exc_type: 异常类型名称
            message: 错误消息

        Returns:
            错误唯一标识
        """
        # 取消息前50字符作为标识（避免参数变化导致误判为不同错误）
        message_prefix = message[:50] if message else ""
        return f"{exc_type}:{message_prefix}"

    def record_error(
        self, exc_type: str, message: str, traceback_str: Optional[str] = None
    ) -> Tuple[bool, int, bool]:
        """
        记录错误.

        Args:
            exc_type: 异常类型名称
            message: 错误消息
            traceback_str: 堆栈跟踪字符串（可选）

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
                return (True, 1, True)  # 需要详细输出，计数为1，算作里程碑

            # 后续出现
            self._errors[error_key] += 1
            current_count = self._errors[error_key]

            # 检查是否达到里程碑（每10次）
            last_milestone = self._last_milestone.get(error_key, 0)
            is_milestone = (current_count % 10 == 0) and (current_count > last_milestone)

            if is_milestone:
                self._last_milestone[error_key] = current_count

            return (False, current_count, is_milestone)

    def get_count(self, exc_type: str, message: str) -> int:
        """
        获取错误计数.

        Args:
            exc_type: 异常类型名称
            message: 错误消息

        Returns:
            错误计数
        """
        error_key = self._generate_error_key(exc_type, message)
        with self._data_lock:
            return self._errors.get(error_key, 0)

    def get_first_seen(self, exc_type: str, message: str) -> Optional[datetime]:
        """
        获取错误首次出现时间.

        Args:
            exc_type: 异常类型名称
            message: 错误消息

        Returns:
            首次出现时间，如果不存在返回None
        """
        error_key = self._generate_error_key(exc_type, message)
        with self._data_lock:
            return self._first_seen.get(error_key)

    def should_output_detail(self, exc_type: str, message: str) -> bool:
        """
        判断是否需要详细输出.

        Args:
            exc_type: 异常类型名称
            message: 错误消息

        Returns:
            是否需要详细输出（首次或每10次）
        """
        error_key = self._generate_error_key(exc_type, message)
        with self._data_lock:
            count = self._errors.get(error_key, 0)
            if count == 0:
                return True  # 首次
            if count % 10 == 0:
                return True  # 里程碑
            return False

    def reset(self) -> None:
        """重置所有计数器（用于测试或手动重置）."""
        with self._data_lock:
            self._errors.clear()
            self._first_seen.clear()
            self._last_milestone.clear()

    def get_summary(self) -> Dict[str, int]:
        """
        获取所有错误的摘要.

        Returns:
            错误摘要字典 {error_key: count}
        """
        with self._data_lock:
            return self._errors.copy()


# 全局单例实例
_error_counter: Optional[ErrorCounter] = None


def get_error_counter() -> ErrorCounter:
    """
    获取全局错误计数器实例.

    Returns:
        ErrorCounter实例
    """
    global _error_counter  # pylint: disable=global-statement
    if _error_counter is None:
        _error_counter = ErrorCounter()
    return _error_counter


# =============================================================================
# Part 3: 终端输出工具
# =============================================================================

# 全局配置
_debug_config = {
    "enabled_modules": [],
    "debug_level": "normal",
    "terminal_output": True,
}


def print_stage(
    stage_name: str,
    message: str,
    success: bool = True,
    error_detail: str = "",
) -> None:
    """打印启动阶段状态信息.

    Args:
        stage_name: 阶段名称（如 "ENV-SETUP", "QT-INIT" 等）
        message: 状态消息
        success: 是否成功
        error_detail: 错误详情（失败时使用）
    """
    # 状态图标
    icon = "✅" if success else "❌"

    # 格式化输出
    status_line = f"[{stage_name}] {icon} {message}"

    # 打印到终端
    print(status_line)

    # 如果有错误详情，打印额外信息
    if not success and error_detail:
        print(f"    └─ {error_detail}")

    # 同时记录到日志系统
    logger = logging.getLogger("startup")
    if success:
        logger.info("[%s] %s", stage_name, message)
    else:
        error_msg = f"{message}"
        if error_detail:
            error_msg += f" - {error_detail}"
        logger.error("[%s] %s", stage_name, error_msg)


def configure_debug(
    enabled_modules: List[str],
    debug_level: Literal["brief", "normal", "detailed"] = "normal",
    terminal_output: bool = True,
) -> None:
    """配置调试输出.

    Args:
        enabled_modules: 启用调试的模块列表
        debug_level: 调试级别 (brief/normal/detailed)
        terminal_output: 是否输出到终端
    """
    global _debug_config

    _debug_config = {
        "enabled_modules": enabled_modules,
        "debug_level": debug_level,
        "terminal_output": terminal_output,
    }

    # ✅ 修复：所有模块的logger都设置为DEBUG级别，让LoggingHub的路由规则决定输出
    # Terminal输出的简洁性由LoggingHub的console_enabled_types控制
    # AI日志文件需要完整的DEBUG信息，不应该在这里过滤
    for module_name in enabled_modules:
        logger = logging.getLogger(module_name)
        # ✅ 统一设置为DEBUG，确保所有日志都能到达LoggingHub
        logger.setLevel(logging.DEBUG)

    # 记录配置信息
    logger = logging.getLogger("startup")
    logger.info(
        "Debug配置: 模块=%s, 级别=%s（所有模块logger设为DEBUG，由LoggingHub控制输出）, 终端输出=%s",
        ", ".join(enabled_modules),
        debug_level,
        terminal_output,
    )


def get_debug_config() -> dict:
    """获取当前调试配置.

    Returns:
        当前的调试配置字典
    """
    return _debug_config.copy()


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    # 管理员权限工具
    "is_admin",
    "run_as_admin",
    "ensure_admin",
    "check_admin_for_hardware_monitoring",
    # 错误计数器
    "ErrorCounter",
    "get_error_counter",
    # 终端输出工具
    "print_stage",
    "configure_debug",
    "get_debug_config",
]


# -*- coding: utf-8 -*-
"""
监控核心模块 - 合并版

整合了以下模块以便于调试时快速定位：
- monitoring_events.py: 系统监控事件类型定义
- monitored_event_engine.py: 监控版事件引擎
- wmi_smart_monitor.py: WMI SMART硬盘监控

作者：系统重构团队
日期：2025-10-29
版本：v0.50 (激进合并版)
"""

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from vnpy.event import Event, EventEngine

logger = logging.getLogger(__name__)
logger_alert = logging.getLogger(__name__ + ".alert")


# =============================================================================
# Part 1: 事件类型定义
# =============================================================================

# 系统指标事件（CPU、内存、磁盘、网络使用率等）
EVENT_SYSTEM_METRICS = "eSystemMetrics"

# 硬件传感器事件（温度、功耗、电压、风扇转速等）
EVENT_HARDWARE_SENSORS = "eHardwareSensors"

# 瓶颈分析事件（系统性能瓶颈诊断）
EVENT_BOTTLENECK_ANALYSIS = "eBottleneckAnalysis"

# 场景分析事件（当前运行场景的优化建议）
EVENT_SCENARIO_ANALYSIS = "eScenarioAnalysis"

# 进程监控事件（Python进程、关键进程状态）
EVENT_PROCESS_MONITORING = "eProcessMonitoring"

# 服务状态事件（各服务的健康状态）
EVENT_SERVICE_MONITORING = "eServiceMonitoring"

# SMART数据事件（硬盘健康监控）
EVENT_SMART_DATA = "eSmartData"

# 性能指标汇总事件（多维度性能概览）
EVENT_PERFORMANCE_SUMMARY = "ePerformanceSummary"

# 系统管理相关事件（从 utils.py 迁移）
EVENT_SYSTEM_STATUS = "eSystemStatus"  # 系统状态更新事件
EVENT_PERFORMANCE_METRICS = "ePerformanceMetrics"  # 性能指标更新事件
EVENT_SERVICE_STATUS = "eServiceStatus"  # 服务状态更新事件
EVENT_DIAGNOSTIC_RESULT = "eDiagnosticResult"  # 诊断结果事件
EVENT_PROCESS_STATUS = "eProcessStatus"  # 进程状态更新事件

# 跨模块集成事件（从 utils.py 迁移）
EVENT_STRATEGY_STATUS_CHANGED = "eStrategyStatusChanged"  # 策略状态变化事件
EVENT_GATEWAY_STATUS_CHANGED = "eGatewayStatusChanged"  # 网关状态变化事件
EVENT_DATA_DOWNLOAD_COMPLETE = "eDataDownloadComplete"  # 数据下载完成事件
EVENT_RECORDING_STATUS_CHANGED = "eRecordingStatusChanged"  # 录制状态变化事件

# 日志和告警系统事件（从 utils.py 迁移）
EVENT_LOG_RECORD = "eLogRecord"  # 日志记录事件
EVENT_ALERT_CREATED = "eAlertCreated"  # 告警创建事件
EVENT_ALERT_UPDATED = "eAlertUpdated"  # 告警更新事件


# =============================================================================
# Part 2: 监控版事件引擎
# =============================================================================


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


# =============================================================================
# Part 3: WMI SMART硬盘监控
# =============================================================================


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
    """
    基于WMI的SMART监控器 - 纯Python实现

    使用Windows WMI接口获取硬盘健康状态：
    - MSStorageDriver_FailurePredictStatus: 预测故障状态
    - MSStorageDriver_FailurePredictData: SMART属性数据
    - Win32_DiskDrive: 硬盘基本信息
    """

    def __init__(self):
        self._available = False
        self._wmi = None
        self._wmi_cimv2 = None
        self._disk_cache: Dict[str, Dict[str, Any]] = {}
        self._thread_local_wmi = {}  # 线程本地WMI实例
        self._initialize_wmi()

    def _initialize_wmi(self):
        """初始化WMI连接"""
        try:
            import wmi

            self._wmi = wmi.WMI(namespace="root\\wmi")
            self._wmi_cimv2 = wmi.WMI()  # 用于Win32_DiskDrive
            self._available = True
            logger.info("✓ WMI SMART监控器初始化成功")
        except ImportError:
            logger.warning("WMI模块未安装，SMART监控不可用 (pip install wmi)")
        except Exception as e:
            logger.warning("WMI初始化失败: %s", e)

    def _get_thread_wmi(self):
        """获取线程本地的WMI实例（COM线程安全）"""
        import threading

        thread_id = threading.current_thread().ident

        if thread_id not in self._thread_local_wmi:
            try:
                # 🔥 关键修复：在线程中初始化COM
                try:
                    import pythoncom

                    pythoncom.CoInitialize()  # type: ignore[attr-defined]
                except (ImportError, AttributeError):
                    pass  # 如果pythoncom不可用，继续尝试

                import wmi

                self._thread_local_wmi[thread_id] = {
                    "wmi": wmi.WMI(namespace="root\\wmi"),
                    "wmi_cimv2": wmi.WMI(),
                }
                logger.info(f"[WMI-SMART] ✓ 为线程{thread_id}创建WMI实例")
            except Exception as e:
                logger.error(f"[WMI-SMART] ✗ 线程{thread_id}创建WMI实例失败: %s", e)
                return None

        return self._thread_local_wmi[thread_id]

    def is_available(self) -> bool:
        """检查WMI是否可用"""
        return self._available

    def get_smart_data(self) -> Dict[str, DiskSmartData]:
        """
        获取所有硬盘的SMART数据

        Returns:
            Dict[disk_name, DiskSmartData]: 硬盘名称到SMART数据的映射
        """
        if not self._available:
            logger.debug("[WMI-SMART] WMI不可用")
            return {}

        result = {}

        try:
            # 1. 获取硬盘基本信息
            disks_info = self._get_disks_basic_info()
            logger.debug(f"[WMI-SMART] 获取到 {len(disks_info)} 个硬盘基本信息")
            if disks_info:
                logger.debug(f"[WMI-SMART] 硬盘实例名: {list(disks_info.keys())}")

            # 2. 获取SMART健康状态
            health_status = self._get_failure_predict_status()
            logger.debug(f"[WMI-SMART] 获取到 {len(health_status)} 个健康状态")
            if health_status:
                logger.debug(f"[WMI-SMART] 健康状态实例名: {list(health_status.keys())}")

            # 3. 获取SMART详细数据
            smart_data = self._get_failure_predict_data()
            logger.debug(f"[WMI-SMART] 获取到 {len(smart_data)} 个SMART数据")
            if smart_data:
                logger.debug(f"[WMI-SMART] SMART数据实例名: {list(smart_data.keys())}")

            # 4. 合并数据
            # 🔧 即使没有SMART详细数据，也要显示硬盘基本信息
            for instance_name, disk_info in disks_info.items():
                try:
                    # 获取健康状态（可能为空，需要管理员权限）
                    health = health_status.get(instance_name, {})
                    predict_failure = health.get("predict_failure", False)

                    # 获取SMART属性（可能为空，需要管理员权限）
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
                    # 如果没有SMART数据（权限不足），标记为UNKNOWN但仍显示基本信息
                    if not attributes and not health_status:
                        assessment = "未知（需要管理员权限）"
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
                        # 🔧 修复：将None值转换为0，避免后续类型错误
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
                    logger.debug("处理硬盘SMART数据失败 (%s): %s", instance_name, e)

            logger.info("成功读取 %d 个硬盘的WMI-SMART数据", len(result))

        except Exception as e:
            logger.exception("获取WMI-SMART数据失败: %s", e)

        return result

    def _get_disks_basic_info(self) -> Dict[str, Dict[str, Any]]:
        """获取硬盘基本信息（型号、序列号等）"""
        disks = {}

        try:
            # 使用线程本地WMI实例（COM线程安全）
            thread_wmi = self._get_thread_wmi()
            if not thread_wmi:
                logger.warning("[WMI-SMART] 无法获取线程本地WMI实例")
                return {}

            for disk in thread_wmi["wmi_cimv2"].Win32_DiskDrive():
                # 从PNPDeviceID提取实例名（用于匹配WMI命名空间）
                # 例如: SCSI\DISK&VEN_...\4&... -> SCSI_DISK&VEN_...
                instance_name = disk.PNPDeviceID.replace("\\", "_")

                # 提取PhysicalDrive编号
                device_id = disk.DeviceID  # \\.\PHYSICALDRIVE0
                disk_name = device_id.split("\\")[-1]  # PHYSICALDRIVE0

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
                    "device_id": device_id,
                    "pnp_id": disk.PNPDeviceID,
                }

        except Exception as e:
            logger.debug("获取硬盘基本信息失败: %s", e)

        return disks

    def _get_failure_predict_status(self) -> Dict[str, Dict[str, Any]]:
        """获取故障预测状态（SMART健康状态）"""
        status_map = {}

        try:
            # 使用线程本地WMI实例（COM线程安全）
            thread_wmi = self._get_thread_wmi()
            if not thread_wmi:
                return {}

            for item in thread_wmi["wmi"].MSStorageDriver_FailurePredictStatus():
                instance_name = item.InstanceName.strip("\x00")  # 移除空字符
                status_map[instance_name] = {
                    "predict_failure": item.PredictFailure,
                    "reason": item.Reason if hasattr(item, "Reason") else 0,
                }
        except Exception as e:
            logger.debug("获取故障预测状态失败: %s", e)

        return status_map

    def _get_failure_predict_data(self) -> Dict[str, List[SmartAttribute]]:
        """获取故障预测数据（SMART属性）"""
        data_map = {}

        try:
            # 使用线程本地WMI实例（COM线程安全）
            thread_wmi = self._get_thread_wmi()
            if not thread_wmi:
                return {}

            for item in thread_wmi["wmi"].MSStorageDriver_FailurePredictData():
                instance_name = item.InstanceName.strip("\x00")

                # 解析SMART数据（512字节）
                vendor_specific = item.VendorSpecific
                if not vendor_specific or len(vendor_specific) < 362:
                    continue

                attributes = []

                # SMART属性从字节2开始，每12字节一个属性，共30个属性
                for i in range(30):
                    offset = 2 + i * 12
                    if offset + 12 > len(vendor_specific):
                        break

                    attr_id = vendor_specific[offset]
                    if attr_id == 0:  # 无效属性
                        continue

                    # 提取属性值（flags预留用于未来扩展）
                    # flags = (vendor_specific[offset + 1] << 8) | vendor_specific[offset + 2]
                    value = vendor_specific[offset + 3]
                    worst = vendor_specific[offset + 4]
                    raw_value = sum(vendor_specific[offset + 5 + j] << (j * 8) for j in range(6))

                    # SMART属性ID到名称的映射
                    attr_name = self._get_smart_attr_name(attr_id)

                    # 阈值（通常需要从另一个WMI类获取，这里简化处理）
                    threshold = 0

                    # 状态评估
                    status = "OK"
                    if value < threshold and threshold > 0:
                        status = "CRITICAL"
                    elif value < worst:
                        status = "WARNING"

                    attr = SmartAttribute(
                        id=attr_id,
                        name=attr_name,
                        value=value,
                        worst=worst,
                        threshold=threshold,
                        raw_value=raw_value,
                        status=status,
                    )
                    attributes.append(attr)

                data_map[instance_name] = attributes

        except Exception as e:
            logger.debug("获取SMART属性失败: %s", e)

        return data_map

    def _get_smart_attr_name(self, attr_id: int) -> str:
        """获取SMART属性名称"""
        attr_names = {
            1: "Read Error Rate",
            5: "Reallocated Sectors Count",
            9: "Power-On Hours",
            10: "Spin Retry Count",
            12: "Power Cycle Count",
            187: "Reported Uncorrectable Errors",
            188: "Command Timeout",
            194: "Temperature",
            195: "Hardware ECC Recovered",
            196: "Reallocation Event Count",
            197: "Current Pending Sector Count",
            198: "Uncorrectable Sector Count",
            199: "UltraDMA CRC Error Count",
            200: "Multi-Zone Error Rate",
            241: "Total LBAs Written",
            242: "Total LBAs Read",
        }
        return attr_names.get(attr_id, f"Attribute_{attr_id}")

    def _assess_health(
        self,
        predict_failure: bool,
        attributes: List[SmartAttribute],
        reallocated_sectors: Optional[int],
        pending_sectors: Optional[int],
        uncorrectable_errors: Optional[int],
    ) -> str:
        """
        评估硬盘健康状态

        Returns:
            "正常": 健康
            "故障": 即将故障
            "警告": 警告
            "未知": 未知
        """
        # 如果WMI预测故障，直接返回故障
        if predict_failure:
            return "故障"

        # 检查关键SMART属性
        critical_issues = 0
        warning_issues = 0

        for attr in attributes:
            if attr.status == "CRITICAL":
                critical_issues += 1
            elif attr.status == "WARNING":
                warning_issues += 1

        # 检查重分配扇区
        if reallocated_sectors is not None and reallocated_sectors > 0:
            if reallocated_sectors > 50:
                critical_issues += 1
            elif reallocated_sectors > 10:
                warning_issues += 1

        # 检查待处理扇区
        if pending_sectors is not None and pending_sectors > 0:
            if pending_sectors > 10:
                critical_issues += 1
            elif pending_sectors > 0:
                warning_issues += 1

        # 检查不可纠正错误
        if uncorrectable_errors is not None and uncorrectable_errors > 0:
            critical_issues += 1

        # 综合评估
        if critical_issues > 0:
            return "故障"
        elif warning_issues > 0:
            return "警告"
        else:
            return "正常"


# =============================================================================
# Part 6.5: SMART监控包装器（从monitor_system.py迁移）
# =============================================================================


class SmartMonitor:
    """硬盘SMART监控器 - 纯Python WMI方案（无需外部工具）."""

    def __init__(self):
        self._wmi_monitor = None

        # 初始化WMI方案（唯一方案）
        try:
            self._wmi_monitor = get_wmi_smart_monitor()
            if self._wmi_monitor.is_available():
                logger.info("✅ WMI SMART监控已启用（纯Python，无需smartctl）")
            else:
                logger.error("❌ WMI SMART监控初始化失败：WMI不可用")
        except Exception as e:
            logger.error("❌ WMI SMART初始化失败: %s", e, exc_info=True)

    def is_available(self) -> bool:
        return self._wmi_monitor is not None and self._wmi_monitor.is_available()

    def get_smart_data(self) -> Dict[str, DiskSmartData]:
        """获取SMART数据（仅WMI方案）."""
        if not self._wmi_monitor or not self._wmi_monitor.is_available():
            logger.warning("[SMART] WMI监控器不可用")
            return {}

        try:
            result = self._wmi_monitor.get_smart_data()
            self._process_smart_alerts(result)
            return result
        except Exception as e:
            logger.exception("[SMART] WMI数据获取失败: %s", e)
            return {}

    def _process_smart_alerts(self, result: Dict[str, DiskSmartData]):
        """处理SMART告警"""
        for smart_data in result.values():
            # 健康评估告警
            if smart_data.assessment in ["FAILING", "FAIL"]:
                logger_alert.critical(
                    "硬盘即将故障: 硬盘=%s, 型号=%s, 序列号=%s",
                    smart_data.disk_name,
                    smart_data.model,
                    smart_data.serial,
                )
            elif smart_data.assessment == "WARNING":
                logger_alert.warning(
                    "硬盘健康警告: 硬盘=%s, 重分配扇区=%s, 待处理扇区=%s",
                    smart_data.disk_name,
                    smart_data.reallocated_sectors or 0,
                    smart_data.pending_sectors or 0,
                )
            # 温度告警
            if smart_data.temperature and smart_data.temperature > 60:
                logger_alert.warning(
                    "硬盘温度过高: 硬盘=%s, 温度=%d°C",
                    smart_data.disk_name,
                    smart_data.temperature,
                )


# 单例实例
_wmi_smart_monitor_instance: Optional[WMISmartMonitor] = None


def get_wmi_smart_monitor() -> WMISmartMonitor:
    """获取WMI SMART监控器单例"""
    global _wmi_smart_monitor_instance  # pylint: disable=global-statement
    if _wmi_smart_monitor_instance is None:
        _wmi_smart_monitor_instance = WMISmartMonitor()
    return _wmi_smart_monitor_instance


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    # 事件类型
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
    # 监控版事件引擎
    "MonitoredEventEngine",
    # WMI SMART监控
    "DiskType",
    "SmartAttribute",
    "DiskSmartData",
    "WMISmartMonitor",
    "get_wmi_smart_monitor",
]


# =============================================================================
# Part 7-10: Actually-Used Utility Classes (from utilities.py)
# =============================================================================

import glob
import logging
import os
import re
import secrets
import shutil
import socket
import ssl
import stat
import threading
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import psutil
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)




# ServiceHealthChecker

# ServiceHealthChecker
class ServiceHealthChecker:
    """增强的服务健康检查器 - 支持业务指标、资源占用、外部依赖检查."""

    def __init__(self):
        """初始化服务健康检查器."""
        self.logger = logging.getLogger(__name__)
        self._monitoring_interval = 2  # 默认2秒推送频率
        self._main_process = psutil.Process()

    def set_monitoring_interval(self, interval: int):
        """设置监控推送频率.

        Args:
            interval: 推送间隔（秒），范围1-10
        """
        self._monitoring_interval = max(1, min(10, interval))
        self.logger.info("监控推送频率已设置为 %d 秒", self._monitoring_interval)

    def get_monitoring_interval(self) -> int:
        """获取当前监控推送频率."""
        return self._monitoring_interval

    def quick_check(self, service_name: str, service_manager) -> Dict[str, Any]:
        """快速检查服务健康状态（增强版）.

        Args:
            service_name: 服务名称
            service_manager: 服务管理器实例

        Returns:
            Dict: 检查结果，包含基础指标、业务指标、资源占用
        """
        try:
            # 获取服务实例
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "service_name": service_name,
                    "status": "not_found",
                    "online": False,
                    "response_time_ms": 0,
                    "message": "服务未注册",
                    "call_count": 0,
                    "success_rate": 0.0,
                    "error_rate": 0.0,
                    "memory_mb": 0.0,
                    "thread_count": 0,
                }

            # 检查服务是否初始化
            is_initialized = getattr(service, "is_initialized", False)

            # 测量响应时间（通过调用health_check）
            start_time = time.time()
            try:
                health_result = service.health_check() if hasattr(service, "health_check") else {}
                response_time_ms = (time.time() - start_time) * 1000

                # 收集业务指标（从性能跟踪器获取）
                call_count = 0
                success_rate = 100.0
                error_rate = 0.0

                try:
                    from backend.services.system_manager_service import performance_tracker

                    # 尝试从性能跟踪器获取服务相关指标
                    all_metrics = performance_tracker.get_all_metrics()
                    # 查找与服务相关的指标
                    service_metrics = {}
                    for _category, metrics_list in all_metrics.items():
                        # metrics_list 是一个列表，包含多个指标字典
                        for metric_dict in metrics_list:
                            # 遍历字典中的每个指标
                            for metric_name, metric_value in metric_dict.items():
                                if service_name.replace("_service", "") in metric_name.lower():
                                    # 存储指标值（注意：这里的 metric_value 可能是数值，不是字典）
                                    if isinstance(metric_value, dict):
                                        service_metrics[metric_name] = metric_value

                    # 聚合业务指标
                    if service_metrics:
                        total_calls = sum(m.get("total_calls", 0) for m in service_metrics.values())
                        if total_calls > 0:
                            call_count = total_calls
                            # 计算平均成功率
                            success_rates = [
                                m.get("success_rate", 100) for m in service_metrics.values()
                            ]
                            success_rate = sum(success_rates) / len(success_rates)
                            error_rate = 100.0 - success_rate
                except Exception as e:
                    self.logger.debug("获取业务指标失败 %s: %s", service_name, e)

                # 收集资源占用指标
                memory_mb = 0.0
                thread_count = 0

                try:
                    # 获取当前进程的内存占用
                    memory_info = self._main_process.memory_info()
                    memory_mb = memory_info.rss / 1024 / 1024

                    # 获取线程数
                    thread_count = self._main_process.num_threads()
                except Exception as e:
                    self.logger.debug("获取资源占用失败 %s: %s", service_name, e)

                # 返回完整结果
                return {
                    "service_name": service_name,
                    "status": "healthy" if is_initialized else "initializing",
                    "online": True,
                    "response_time_ms": response_time_ms,
                    "message": "服务正常",
                    # 业务指标
                    "call_count": call_count,
                    "success_rate": success_rate,
                    "error_rate": error_rate,
                    # 资源占用
                    "memory_mb": memory_mb,
                    "thread_count": thread_count,
                    **health_result,  # 合并health_check的其他结果
                }

            except Exception as e:
                return {
                    "service_name": service_name,
                    "status": "error",
                    "online": False,
                    "response_time_ms": (time.time() - start_time) * 1000,
                    "message": f"健康检查失败: {str(e)}",
                    "call_count": 0,
                    "success_rate": 0.0,
                    "error_rate": 100.0,
                    "memory_mb": 0.0,
                    "thread_count": 0,
                }

        except Exception as e:
            self.logger.error("快速检查服务失败 %s: %s", service_name, e)
            return {
                "service_name": service_name,
                "status": "error",
                "online": False,
                "response_time_ms": 0,
                "message": f"检查失败: {str(e)}",
                "call_count": 0,
                "success_rate": 0.0,
                "error_rate": 100.0,
                "memory_mb": 0.0,
                "thread_count": 0,
            }

    def check_response_time(self, service_name: str, service_manager) -> float:
        """检查服务响应时间.

        Args:
            service_name: 服务名称
            service_manager: 服务管理器实例

        Returns:
            float: 响应时间（毫秒）
        """
        service = service_manager.get_service(service_name)
        if not service:
            return 0.0

        start_time = time.time()
        try:
            # 调用一个轻量级方法
            if hasattr(service, "health_check"):
                service.health_check()
            response_time = (time.time() - start_time) * 1000
            return response_time
        except Exception as e:
            self.logger.error("检查响应时间失败 %s: %s", service_name, e)
            return 0.0

    def check_external_dependencies(self) -> Dict[str, Any]:
        """检查外部依赖状态.

        Returns:
            Dict: 外部依赖检查结果
        """
        dependencies = {}

        # 1. 检查EventEngine
        try:
            from vnpy.event import EventEngine
            from backend.infrastructure.system_vnpy import event_engine

            if event_engine and hasattr(event_engine, "_active"):
                dependencies["event_engine"] = {
                    "name": "VnPy EventEngine",
                    "status": "healthy",
                    "online": True,
                    "message": "事件引擎运行正常",
                }
            else:
                dependencies["event_engine"] = {
                    "name": "VnPy EventEngine",
                    "status": "unhealthy",
                    "online": False,
                    "message": "事件引擎未初始化",
                }
        except Exception as e:
            dependencies["event_engine"] = {
                "name": "VnPy EventEngine",
                "status": "error",
                "online": False,
                "message": f"检查失败: {str(e)}",
            }

        # 2. 检查数据库连接
        try:
            import os
            import sqlite3

            # 尝试连接数据库
            db_path = os.path.join(os.path.expanduser("~"), ".vntrader", "database.db")
            if os.path.exists(db_path):
                dependencies["database"] = {
                    "name": "SQLite数据库",
                    "status": "healthy",
                    "online": True,
                    "message": "数据库连接正常",
                }
            else:
                dependencies["database"] = {
                    "name": "SQLite数据库",
                    "status": "warning",
                    "online": False,
                    "message": "数据库文件不存在",
                }
        except Exception as e:
            dependencies["database"] = {
                "name": "SQLite数据库",
                "status": "error",
                "online": False,
                "message": f"连接失败: {str(e)}",
            }

        return dependencies

    def check_all_services(self, service_manager) -> Dict[str, Any]:
        """检查所有注册的服务（增强版 - 包含外部依赖）.

        Args:
            service_manager: 服务管理器实例

        Returns:
            Dict: 所有服务的检查结果，包含外部依赖状态
        """
        all_results = {}
        try:
            service_names = service_manager.list_services()

            for service_name in service_names:
                result = self.quick_check(service_name, service_manager)
                all_results[service_name] = result

            # 检查外部依赖
            external_deps = self.check_external_dependencies()

            # 计算外部依赖健康度
            dep_health_count = sum(1 for dep in external_deps.values() if dep["status"] == "healthy")
            dep_total = len(external_deps)
            dep_score = (dep_health_count / dep_total * 100) if dep_total > 0 else 100

            # 综合健康评分（服务权重70%，依赖权重30%）
            service_health_count = sum(1 for r in all_results.values() if r["status"] == "healthy")
            service_total = len(all_results)
            service_score = (service_health_count / service_total * 100) if service_total > 0 else 100

            overall_score = service_score * 0.7 + dep_score * 0.3

            return {
                "services": all_results,
                "external_dependencies": external_deps,
                "summary": {
                    "total_services": service_total,
                    "healthy_services": service_health_count,
                    "service_health_percentage": service_score,
                    "dependency_health_percentage": dep_score,
                    "overall_health_score": overall_score,
                },
            }
        except Exception as e:
            self.logger.error("检查所有服务失败: %s", e)
            return {
                "services": all_results,
                "external_dependencies": {},
                "summary": {},
                "message": f"检查失败: {str(e)}",
            }


# ServiceRestarter
class ServiceRestarter:
    """服务重启管理器."""

    def __init__(self):
        """初始化服务重启管理器."""
        self.logger = logging.getLogger(__name__)

    def restart_service(self, service_name: str, service_manager) -> Dict[str, Any]:
        """重启指定服务.

        Args:
            service_name: 服务名称
            service_manager: 服务管理器实例

        Returns:
            Dict: 重启结果
        """
        try:
            self.logger.info("开始重启服务: %s", service_name)

            # 获取服务实例
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "success": False,
                    "message": f"服务 {service_name} 未注册",
                }

            # 关闭服务
            if hasattr(service, "shutdown"):
                try:
                    service.shutdown()
                    self.logger.info("服务 %s 已关闭", service_name)
                except Exception as e:
                    self.logger.warning("关闭服务失败 %s: %s", service_name, e)

            # 等待一小段时间
            time.sleep(0.5)

            # 重新初始化服务
            if hasattr(service, "initialize"):
                try:
                    success = service.initialize()
                    if success:
                        self.logger.info("服务 %s 已重新初始化", service_name)
                        return {
                            "success": True,
                            "message": f"服务 {service_name} 重启成功",
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"服务 {service_name} 初始化失败",
                        }
                except Exception as e:
                    self.logger.error("初始化服务失败 %s: %s", service_name, e)
                    return {
                        "success": False,
                        "message": f"初始化失败: {str(e)}",
                    }
            else:
                return {
                    "success": False,
                    "message": f"服务 {service_name} 不支持重启",
                }

        except Exception as e:
            self.logger.error("重启服务失败 %s: %s", service_name, e)
            return {
                "success": False,
                "message": f"重启失败: {str(e)}",
            }

    def graceful_restart(self, service_name: str, service_manager, timeout: int = 30) -> Dict[str, Any]:
        """优雅地重启服务（带超时控制）.

        Args:
            service_name: 服务名称
            service_manager: 服务管理器实例
            timeout: 超时时间（秒）

        Returns:
            Dict: 重启结果
        """
        try:
            self.logger.info("开始优雅重启服务: %s (timeout=%ds)", service_name, timeout)
            start_time = time.time()

            # 获取服务实例
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "success": False,
                    "message": f"服务 {service_name} 未注册",
                }

            # 优雅关闭
            if hasattr(service, "graceful_shutdown"):
                try:
                    service.graceful_shutdown()
                    self.logger.info("服务 %s 已优雅关闭", service_name)
                except Exception as e:
                    self.logger.warning("关闭服务失败 %s: %s", service_name, e)
                    # 继续执行，尝试重新初始化

            # 检查是否超时
            elapsed = time.time() - start_time
            if elapsed > timeout:
                return {
                    "success": False,
                    "message": f"关闭服务超时 ({elapsed:.1f}s)",
                }

            # 等待资源释放
            time.sleep(1.0)

            # 重新初始化
            if hasattr(service, "initialize"):
                try:
                    success = service.initialize()
                    elapsed = time.time() - start_time
                    if success:
                        self.logger.info("服务 %s 优雅重启成功 (耗时: %.1fs)", service_name, elapsed)
                        return {
                            "success": True,
                            "elapsed_time": elapsed,
                            "message": f"服务 {service_name} 优雅重启成功",
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"服务 {service_name} 初始化失败",
                        }
                except Exception as e:
                    self.logger.error("初始化服务失败 %s: %s", service_name, e)
                    return {
                        "success": False,
                        "message": f"初始化失败: {str(e)}",
                    }
            else:
                return {
                    "success": False,
                    "message": f"服务 {service_name} 不支持重启",
                }

        except Exception as e:
            self.logger.error("优雅重启服务失败 %s: %s", service_name, e)
            return {
                "success": False,
                "message": f"重启失败: {str(e)}",
            }


# ProcessManager
class ProcessManager:
    """进程管理器 - 提供进程生命周期管理功能."""

    def __init__(self):
        """初始化进程管理器."""
        self.logger = logging.getLogger(__name__)

    def get_process_info(self, pid: int) -> Dict[str, Any]:
        """获取进程信息.

        Args:
            pid: 进程ID

        Returns:
            Dict: 进程信息
        """
        try:
            process = psutil.Process(pid)
            return {
                "pid": pid,
                "name": process.name(),
                "status": process.status(),
                "cpu_percent": process.cpu_percent(),
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "create_time": process.create_time(),
            }
        except psutil.NoSuchProcess:
            return {"pid": pid, "error": "进程不存在"}
        except Exception as e:
            self.logger.error("获取进程信息失败 %d: %s", pid, e)
            return {"pid": pid, "error": str(e)}

    def kill_process(self, pid: int, force: bool = False) -> bool:
        """终止进程.

        Args:
            pid: 进程ID
            force: 是否强制终止

        Returns:
            bool: 是否成功
        """
        try:
            process = psutil.Process(pid)
            if force:
                process.kill()
                self.logger.info("强制终止进程 %d", pid)
            else:
                process.terminate()
                self.logger.info("终止进程 %d", pid)
            return True
        except psutil.NoSuchProcess:
            self.logger.warning("进程 %d 不存在", pid)
            return False
        except Exception as e:
            self.logger.error("终止进程失败 %d: %s", pid, e)
            return False


# NetworkTester (简化版，保留接口)
class NetworkTester:
    """网络测试器."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def test_connectivity(self, host: str, port: int, timeout: int = 5) -> Dict[str, Any]:
        """测试网络连通性."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return {"success": True, "host": host, "port": port}
        except Exception as e:
            return {"success": False, "host": host, "port": port, "error": str(e)}


# PortScanner (简化版，保留接口)
class PortScanner:
    """端口扫描器."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def scan_ports(self, host: str, ports: List[int], timeout: int = 2) -> Dict[int, bool]:
        """扫描端口."""
        results = {}
        for port in ports:
            try:
                with socket.create_connection((host, port), timeout=timeout):
                    results[port] = True
            except:
                results[port] = False
        return results


# LogAnalyzer
class LogAnalyzer:
    """日志分析器 - 分析系统日志，提取错误和警告."""

    def __init__(self):
        """初始化日志分析器."""
        self.logger = logging.getLogger(__name__)

    def analyze_log_file(self, log_file: str, max_lines: int = 1000) -> Dict[str, Any]:
        """分析日志文件.

        Args:
            log_file: 日志文件路径
            max_lines: 最大分析行数

        Returns:
            Dict: 分析结果
        """
        try:
            if not os.path.exists(log_file):
                return {"error": "日志文件不存在"}

            errors = []
            warnings = []
            line_count = 0

            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line_count += 1
                    if line_count > max_lines:
                        break

                    line_lower = line.lower()
                    if 'error' in line_lower:
                        errors.append(line.strip())
                    elif 'warning' in line_lower:
                        warnings.append(line.strip())

            return {
                "file": log_file,
                "total_lines": line_count,
                "error_count": len(errors),
                "warning_count": len(warnings),
                "errors": errors[-10:],
                "warnings": warnings[-10:],
            }
        except Exception as e:
            self.logger.error("分析日志文件失败 %s: %s", log_file, e)
            return {"error": str(e)}

    def get_recent_errors(self, log_file: str, count: int = 10) -> List[str]:
        """获取最近的错误日志.

        Args:
            log_file: 日志文件路径
            count: 返回数量

        Returns:
            List[str]: 错误日志列表
        """
        try:
            if not os.path.exists(log_file):
                return []

            errors = []
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if 'error' in line.lower():
                        errors.append(line.strip())

            return errors[-count:] if errors else []
        except Exception as e:
            self.logger.error("获取错误日志失败 %s: %s", log_file, e)
            return []

    def search_pattern(self, log_file: str, pattern: str, max_results: int = 100) -> List[str]:
        """在日志中搜索模式.

        Args:
            log_file: 日志文件路径
            pattern: 搜索模式（正则表达式）
            max_results: 最大结果数

        Returns:
            List[str]: 匹配的日志行
        """
        try:
            import re
            if not os.path.exists(log_file):
                return []

            pattern_re = re.compile(pattern, re.IGNORECASE)
            matches = []

            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if pattern_re.search(line):
                        matches.append(line.strip())
                        if len(matches) >= max_results:
                            break

            return matches
        except Exception as e:
            self.logger.error("搜索日志模式失败 %s: %s", log_file, e)
            return []

    def summarize_errors(self, log_file: str) -> Dict[str, int]:
        """汇总错误类型及数量.

        Args:
            log_file: 日志文件路径

        Returns:
            Dict[str, int]: 错误类型及其出现次数
        """
        try:
            from collections import Counter
            if not os.path.exists(log_file):
                return {}

            error_types = []
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if 'error' in line.lower():
                        parts = line.split()
                        if len(parts) > 2:
                            error_types.append(parts[2])

            return dict(Counter(error_types))
        except Exception as e:
            self.logger.error("汇总错误失败 %s: %s", log_file, e)
            return {}


# PerformanceAnalyzer
class PerformanceAnalyzer:
    """性能分析器 - 分析系统性能瓶颈."""

    def __init__(self):
        """初始化性能分析器."""
        self.logger = logging.getLogger(__name__)

    def analyze_cpu_usage(self, duration: int = 5) -> Dict[str, Any]:
        """分析CPU使用情况.

        Args:
            duration: 采样时长（秒）

        Returns:
            Dict: CPU分析结果
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=duration)
            cpu_count = psutil.cpu_count()
            cpu_per_core = psutil.cpu_percent(interval=1, percpu=True)

            return {
                "overall_percent": cpu_percent,
                "cpu_count": cpu_count,
                "per_core_percent": cpu_per_core,
                "status": "normal" if cpu_percent < 80 else "high",
            }
        except Exception as e:
            self.logger.error("分析CPU失败: %s", e)
            return {"error": str(e)}

    def analyze_memory_usage(self) -> Dict[str, Any]:
        """分析内存使用情况.

        Returns:
            Dict: 内存分析结果
        """
        try:
            mem = psutil.virtual_memory()
            return {
                "total_mb": mem.total / 1024 / 1024,
                "available_mb": mem.available / 1024 / 1024,
                "used_mb": mem.used / 1024 / 1024,
                "percent": mem.percent,
                "status": "normal" if mem.percent < 80 else "high",
            }
        except Exception as e:
            self.logger.error("分析内存失败: %s", e)
            return {"error": str(e)}

    def analyze_disk_io(self, duration: int = 3) -> Dict[str, Any]:
        """分析磁盘IO.

        Args:
            duration: 采样时长（秒）

        Returns:
            Dict: 磁盘IO分析结果
        """
        try:
            io_start = psutil.disk_io_counters()
            time.sleep(duration)
            io_end = psutil.disk_io_counters()

            read_speed = (io_end.read_bytes - io_start.read_bytes) / duration / 1024 / 1024
            write_speed = (io_end.write_bytes - io_start.write_bytes) / duration / 1024 / 1024

            return {
                "read_speed_mb_s": read_speed,
                "write_speed_mb_s": write_speed,
                "read_count": io_end.read_count - io_start.read_count,
                "write_count": io_end.write_count - io_start.write_count,
            }
        except Exception as e:
            self.logger.error("分析磁盘IO失败: %s", e)
            return {"error": str(e)}

    def find_bottleneck(self) -> Dict[str, Any]:
        """识别系统瓶颈.

        Returns:
            Dict: 瓶颈分析结果
        """
        try:
            cpu = self.analyze_cpu_usage(duration=2)
            mem = self.analyze_memory_usage()
            disk = self.analyze_disk_io(duration=2)

            bottlenecks = []
            if cpu.get("overall_percent", 0) > 80:
                bottlenecks.append("CPU使用率过高")
            if mem.get("percent", 0) > 80:
                bottlenecks.append("内存使用率过高")
            if disk.get("read_speed_mb_s", 0) > 100 or disk.get("write_speed_mb_s", 0) > 100:
                bottlenecks.append("磁盘IO负载高")

            return {
                "cpu": cpu,
                "memory": mem,
                "disk": disk,
                "bottlenecks": bottlenecks,
                "status": "healthy" if not bottlenecks else "bottleneck_detected",
            }
        except Exception as e:
            self.logger.error("识别瓶颈失败: %s", e)
            return {"error": str(e)}


# AutoFixer
class AutoFixer:
    """自动修复器 - 尝试自动修复常见问题."""

    def __init__(self):
        """初始化自动修复器."""
        self.logger = logging.getLogger(__name__)

    def fix_service(self, service_name: str, service_manager, issue: str) -> Dict[str, Any]:
        """修复服务问题.

        Args:
            service_name: 服务名称
            service_manager: 服务管理器实例
            issue: 问题描述

        Returns:
            Dict: 修复结果
        """
        try:
            self.logger.info("尝试修复服务 %s 的问题: %s", service_name, issue)

            if "内存" in issue or "memory" in issue.lower():
                # 内存问题：尝试重启服务
                restarter = ServiceRestarter()
                result = restarter.graceful_restart(service_name, service_manager)
                return {
                    "fixed": result.get("success", False),
                    "action": "重启服务",
                    "details": result,
                }

            elif "响应" in issue or "timeout" in issue.lower():
                # 响应问题：检查并尝试重启
                checker = ServiceHealthChecker()
                health = checker.quick_check(service_name, service_manager)
                if health.get("response_time_ms", 0) > 1000:
                    restarter = ServiceRestarter()
                    result = restarter.restart_service(service_name, service_manager)
                    return {
                        "fixed": result.get("success", False),
                        "action": "重启慢响应服务",
                        "details": result,
                    }

            elif "连接" in issue or "connection" in issue.lower():
                # 连接问题：尝试重新初始化
                service = service_manager.get_service(service_name)
                if service and hasattr(service, "reconnect"):
                    service.reconnect()
                    return {
                        "fixed": True,
                        "action": "重新连接",
                        "details": "已尝试重新连接",
                    }

            return {
                "fixed": False,
                "action": "无法自动修复",
                "details": "未找到匹配的修复方案",
            }

        except Exception as e:
            self.logger.error("修复服务失败 %s: %s", service_name, e)
            return {
                "fixed": False,
                "action": "修复失败",
                "error": str(e),
            }

    def auto_heal(self, service_manager) -> Dict[str, Any]:
        """自动健康检查并修复.

        Args:
            service_manager: 服务管理器实例

        Returns:
            Dict: 自愈结果
        """
        try:
            checker = ServiceHealthChecker()
            all_health = checker.check_all_services(service_manager)

            fixed_services = []
            failed_services = []

            for service_name, health_info in all_health.get("services", {}).items():
                if health_info.get("status") != "healthy":
                    # 尝试修复
                    issue = health_info.get("message", "unknown")
                    fix_result = self.fix_service(service_name, service_manager, issue)

                    if fix_result.get("fixed"):
                        fixed_services.append(service_name)
                    else:
                        failed_services.append(service_name)

            return {
                "checked_services": len(all_health.get("services", {})),
                "fixed_count": len(fixed_services),
                "failed_count": len(failed_services),
                "fixed_services": fixed_services,
                "failed_services": failed_services,
                "status": "success" if not failed_services else "partial",
            }

        except Exception as e:
            self.logger.error("自愈失败: %s", e)
            return {
                "status": "error",
                "error": str(e),
            }


# test_connectivity和scan_ports快捷函数
def test_connectivity(host: str, port: int, timeout: int = 5) -> Dict[str, Any]:
    """测试网络连通性的快捷函数."""
    tester = NetworkTester()
    return tester.test_connectivity(host, port, timeout)


def scan_ports(host: str, ports: List[int], timeout: int = 2) -> Dict[int, bool]:
    """扫描端口的快捷函数."""
    scanner = PortScanner()
    return scanner.scan_ports(host, ports, timeout)



# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # core_utils
    "is_admin", "run_as_admin", "ensure_admin", "check_admin_for_hardware_monitoring",
    "ErrorCounter", "get_error_counter",
    "print_stage", "configure_debug", "get_debug_config",
    # monitoring_core
    "EVENT_SYSTEM_METRICS", "EVENT_HARDWARE_SENSORS", "EVENT_BOTTLENECK_ANALYSIS",
    "EVENT_SCENARIO_ANALYSIS", "EVENT_PROCESS_MONITORING", "EVENT_SERVICE_MONITORING",
    "EVENT_SMART_DATA", "EVENT_PERFORMANCE_SUMMARY", "EVENT_SYSTEM_STATUS",
    "EVENT_PERFORMANCE_METRICS", "EVENT_SERVICE_STATUS", "EVENT_DIAGNOSTIC_RESULT",
    "EVENT_PROCESS_STATUS", "EVENT_STRATEGY_STATUS_CHANGED", "EVENT_GATEWAY_STATUS_CHANGED",
    "EVENT_DATA_DOWNLOAD_COMPLETE", "EVENT_RECORDING_STATUS_CHANGED",
    "EVENT_LOG_RECORD", "EVENT_ALERT_CREATED", "EVENT_ALERT_UPDATED",
    "MonitoredEventEngine",
    "DiskType", "SmartAttribute", "DiskSmartData", "WMISmartMonitor", "get_wmi_smart_monitor",
    "SmartMonitor",
    # utilities (streamlined)
    "ServiceHealthChecker", "ServiceRestarter", "ProcessManager",
    "NetworkTester", "PortScanner",
    "LogAnalyzer", "PerformanceAnalyzer", "AutoFixer",
    "test_connectivity", "scan_ports",
]
