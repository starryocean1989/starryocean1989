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
class ServiceHealthChecker:
    """Ã¥Â¢ÂÃ¥Â¼ÂºÃ§ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂ¥Ã¥ÂºÂ·Ã¦Â£ÂÃ¦ÂÂ¥Ã¥ÂÂ¨ - Ã¦ÂÂ¯Ã¦ÂÂÃ¤Â¸ÂÃ¥ÂÂ¡Ã¦ÂÂÃ¦Â ÂÃ£ÂÂÃ¨ÂµÂÃ¦ÂºÂÃ¥ÂÂ Ã§ÂÂ¨Ã£ÂÂÃ¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂÃ¦Â£ÂÃ¦ÂÂ¥."""

    def __init__(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂ¥Ã¥ÂºÂ·Ã¦Â£ÂÃ¦ÂÂ¥Ã¥ÂÂ¨."""
        self.logger = logging.getLogger(__name__)
        self._monitoring_interval = 2  # Ã©Â»ÂÃ¨Â®Â¤2Ã§Â§ÂÃ¦ÂÂ¨Ã©ÂÂÃ©Â¢ÂÃ§ÂÂ
        self._main_process = psutil.Process()

    def set_monitoring_interval(self, interval: int):
        """Ã¨Â®Â¾Ã§Â½Â®Ã§ÂÂÃ¦ÂÂ§Ã¦ÂÂ¨Ã©ÂÂÃ©Â¢ÂÃ§ÂÂ.

        Args:
            interval: Ã¦ÂÂ¨Ã©ÂÂÃ©ÂÂ´Ã©ÂÂÃ¯Â¼ÂÃ§Â§ÂÃ¯Â¼ÂÃ¯Â¼ÂÃ¨ÂÂÃ¥ÂÂ´1-10
        """
        self._monitoring_interval = max(1, min(10, interval))
        self.logger.info("Ã§ÂÂÃ¦ÂÂ§Ã¦ÂÂ¨Ã©ÂÂÃ©Â¢ÂÃ§ÂÂÃ¥Â·Â²Ã¨Â®Â¾Ã§Â½Â®Ã¤Â¸Âº %d Ã§Â§Â", self._monitoring_interval)

    def get_monitoring_interval(self) -> int:
        """Ã¨ÂÂ·Ã¥ÂÂÃ¥Â½ÂÃ¥ÂÂÃ§ÂÂÃ¦ÂÂ§Ã¦ÂÂ¨Ã©ÂÂÃ©Â¢ÂÃ§ÂÂ."""
        return self._monitoring_interval

    def quick_check(self, service_name: str, service_manager) -> Dict[str, Any]:
        """Ã¥Â¿Â«Ã©ÂÂÃ¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂ¥Ã¥ÂºÂ·Ã§ÂÂ¶Ã¦ÂÂÃ¯Â¼ÂÃ¥Â¢ÂÃ¥Â¼ÂºÃ§ÂÂÃ¯Â¼Â.

        Args:
            service_name: Ã¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂÃ§Â§Â°
            service_manager: Ã¦ÂÂÃ¥ÂÂ¡Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨Ã¥Â®ÂÃ¤Â¾Â

        Returns:
            Dict: Ã¦Â£ÂÃ¦ÂÂ¥Ã§Â»ÂÃ¦ÂÂÃ¯Â¼ÂÃ¥ÂÂÃ¥ÂÂ«Ã¥ÂÂºÃ§Â¡ÂÃ¦ÂÂÃ¦Â ÂÃ£ÂÂÃ¤Â¸ÂÃ¥ÂÂ¡Ã¦ÂÂÃ¦Â ÂÃ£ÂÂÃ¨ÂµÂÃ¦ÂºÂÃ¥ÂÂ Ã§ÂÂ¨
        """
        try:
            # Ã¨ÂÂ·Ã¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥Â®ÂÃ¤Â¾Â
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "service_name": service_name,
                    "status": "not_found",
                    "online": False,
                    "response_time_ms": 0,
                    "message": "Ã¦ÂÂÃ¥ÂÂ¡Ã¦ÂÂªÃ¦Â³Â¨Ã¥ÂÂ",
                    "call_count": 0,
                    "success_rate": 0.0,
                    "error_rate": 0.0,
                    "memory_mb": 0.0,
                    "thread_count": 0,
                }

            # Ã¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂÃ¥ÂÂ¡Ã¦ÂÂ¯Ã¥ÂÂ¦Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂ
            is_initialized = getattr(service, "is_initialized", False)

            # Ã¦ÂµÂÃ©ÂÂÃ¥ÂÂÃ¥ÂºÂÃ¦ÂÂ¶Ã©ÂÂ´Ã¯Â¼ÂÃ©ÂÂÃ¨Â¿ÂÃ¨Â°ÂÃ§ÂÂ¨health_checkÃ¯Â¼Â
            start_time = time.time()
            try:
                health_result = service.health_check() if hasattr(service, "health_check") else {}
                response_time_ms = (time.time() - start_time) * 1000

                # Ã¦ÂÂ¶Ã©ÂÂÃ¤Â¸ÂÃ¥ÂÂ¡Ã¦ÂÂÃ¦Â ÂÃ¯Â¼ÂÃ¤Â»ÂÃ¦ÂÂ§Ã¨ÂÂ½Ã¨Â·ÂÃ¨Â¸ÂªÃ¥ÂÂ¨Ã¨ÂÂ·Ã¥ÂÂÃ¯Â¼Â
                call_count = 0
                success_rate = 100.0
                error_rate = 0.0

                try:
                    from backend.services.system_manager_service import performance_tracker

                    # Ã¥Â°ÂÃ¨Â¯ÂÃ¤Â»ÂÃ¦ÂÂ§Ã¨ÂÂ½Ã¨Â·ÂÃ¨Â¸ÂªÃ¥ÂÂ¨Ã¨ÂÂ·Ã¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã§ÂÂ¸Ã¥ÂÂ³Ã¦ÂÂÃ¦Â Â
                    all_metrics = performance_tracker.get_all_metrics()
                    # Ã¦ÂÂ¥Ã¦ÂÂ¾Ã¤Â¸ÂÃ¦ÂÂÃ¥ÂÂ¡Ã§ÂÂ¸Ã¥ÂÂ³Ã§ÂÂÃ¦ÂÂÃ¦Â Â
                    service_metrics = {}
                    for _category, metrics_list in all_metrics.items():
                        # metrics_list Ã¦ÂÂ¯Ã¤Â¸ÂÃ¤Â¸ÂªÃ¥ÂÂÃ¨Â¡Â¨Ã¯Â¼ÂÃ¥ÂÂÃ¥ÂÂ«Ã¥Â¤ÂÃ¤Â¸ÂªÃ¦ÂÂÃ¦Â ÂÃ¥Â­ÂÃ¥ÂÂ¸
                        for metric_dict in metrics_list:
                            # Ã©ÂÂÃ¥ÂÂÃ¥Â­ÂÃ¥ÂÂ¸Ã¤Â¸Â­Ã§ÂÂÃ¦Â¯ÂÃ¤Â¸ÂªÃ¦ÂÂÃ¦Â Â
                            for metric_name, metric_value in metric_dict.items():
                                if service_name.replace("_service", "") in metric_name.lower():
                                    # Ã¥Â­ÂÃ¥ÂÂ¨Ã¦ÂÂÃ¦Â ÂÃ¥ÂÂ¼Ã¯Â¼ÂÃ¦Â³Â¨Ã¦ÂÂÃ¯Â¼ÂÃ¨Â¿ÂÃ©ÂÂÃ§ÂÂ metric_value Ã¥ÂÂ¯Ã¨ÂÂ½Ã¦ÂÂ¯Ã¦ÂÂ°Ã¥ÂÂ¼Ã¯Â¼ÂÃ¤Â¸ÂÃ¦ÂÂ¯Ã¥Â­ÂÃ¥ÂÂ¸Ã¯Â¼Â
                                    if isinstance(metric_value, dict):
                                        service_metrics[metric_name] = metric_value

                    # Ã¨ÂÂÃ¥ÂÂÃ¤Â¸ÂÃ¥ÂÂ¡Ã¦ÂÂÃ¦Â Â
                    if service_metrics:
                        total_calls = sum(m.get("total_calls", 0) for m in service_metrics.values())
                        if total_calls > 0:
                            call_count = total_calls
                            # Ã¨Â®Â¡Ã§Â®ÂÃ¥Â¹Â³Ã¥ÂÂÃ¦ÂÂÃ¥ÂÂÃ§ÂÂ
                            success_rates = [
                                m.get("success_rate", 100) for m in service_metrics.values()
                            ]
                            success_rate = sum(success_rates) / len(success_rates)
                            error_rate = 100.0 - success_rate
                except Exception as e:
                    self.logger.debug("Ã¨ÂÂ·Ã¥ÂÂÃ¤Â¸ÂÃ¥ÂÂ¡Ã¦ÂÂÃ¦Â ÂÃ¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)

                # Ã¦ÂÂ¶Ã©ÂÂÃ¨ÂµÂÃ¦ÂºÂÃ¥ÂÂ Ã§ÂÂ¨Ã¦ÂÂÃ¦Â Â
                memory_mb = 0.0
                thread_count = 0

                try:
                    # Ã¨ÂÂ·Ã¥ÂÂÃ¥Â½ÂÃ¥ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ§ÂÂÃ¥ÂÂÃ¥Â­ÂÃ¥ÂÂ Ã§ÂÂ¨
                    memory_info = self._main_process.memory_info()
                    memory_mb = memory_info.rss / (1024 * 1024)

                    # Ã¨ÂÂ·Ã¥ÂÂÃ§ÂºÂ¿Ã§Â¨ÂÃ¦ÂÂ°
                    thread_count = threading.active_count()
                except Exception as e:
                    self.logger.debug("Ã¨ÂÂ·Ã¥ÂÂÃ¨ÂµÂÃ¦ÂºÂÃ¥ÂÂ Ã§ÂÂ¨Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)

                return {
                    "service_name": service_name,
                    "status": "online",
                    "online": True,
                    "initialized": is_initialized,
                    "response_time_ms": round(response_time_ms, 2),
                    "health_details": health_result,
                    "message": "Ã¦ÂÂÃ¥ÂÂ¡Ã¦Â­Â£Ã¥Â¸Â¸",
                    # Ã¤Â¸ÂÃ¥ÂÂ¡Ã¦ÂÂÃ¦Â Â
                    "call_count": call_count,
                    "success_rate": round(success_rate, 2),
                    "error_rate": round(error_rate, 2),
                    # Ã¨ÂµÂÃ¦ÂºÂÃ¥ÂÂ Ã§ÂÂ¨
                    "memory_mb": round(memory_mb, 2),
                    "thread_count": thread_count,
                }
            except Exception as e:
                response_time_ms = (time.time() - start_time) * 1000
                return {
                    "service_name": service_name,
                    "status": "error",
                    "online": False,
                    "response_time_ms": round(response_time_ms, 2),
                    "message": f"Ã¥ÂÂ¥Ã¥ÂºÂ·Ã¦Â£ÂÃ¦ÂÂ¥Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
                    "call_count": 0,
                    "success_rate": 0.0,
                    "error_rate": 100.0,
                    "memory_mb": 0.0,
                    "thread_count": 0,
                }

        except Exception as e:
            self.logger.error("Ã¥Â¿Â«Ã©ÂÂÃ¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
            return {
                "service_name": service_name,
                "status": "error",
                "online": False,
                "response_time_ms": 0,
                "message": f"Ã¦Â£ÂÃ¦ÂÂ¥Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
                "call_count": 0,
                "success_rate": 0.0,
                "error_rate": 100.0,
                "memory_mb": 0.0,
                "thread_count": 0,
            }

    def check_response_time(self, service_name: str, service_manager) -> float:
        """Ã¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂÃ¥ÂºÂÃ¦ÂÂ¶Ã©ÂÂ´.

        Args:
            service_name: Ã¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂÃ§Â§Â°
            service_manager: Ã¦ÂÂÃ¥ÂÂ¡Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨Ã¥Â®ÂÃ¤Â¾Â

        Returns:
            float: Ã¥ÂÂÃ¥ÂºÂÃ¦ÂÂ¶Ã©ÂÂ´Ã¯Â¼ÂÃ¦Â¯Â«Ã§Â§ÂÃ¯Â¼Â
        """
        try:
            service = service_manager.get_service(service_name)
            if not service:
                return -1.0

            start_time = time.time()

            # Ã¨Â°ÂÃ§ÂÂ¨Ã¤Â¸ÂÃ¤Â¸ÂªÃ¨Â½Â»Ã©ÂÂÃ§ÂºÂ§Ã¦ÂÂ¹Ã¦Â³Â
            if hasattr(service, "health_check"):
                service.health_check()

            response_time_ms = (time.time() - start_time) * 1000
            return round(response_time_ms, 2)

        except Exception as e:
            self.logger.error("Ã¦Â£ÂÃ¦ÂÂ¥Ã¥ÂÂÃ¥ÂºÂÃ¦ÂÂ¶Ã©ÂÂ´Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
            return -1.0

    def check_external_dependencies(self) -> Dict[str, Any]:
        """Ã¦Â£ÂÃ¦ÂÂ¥Ã¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂÃ§ÂÂ¶Ã¦ÂÂ.

        Returns:
            Dict: Ã¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂÃ¦Â£ÂÃ¦ÂÂ¥Ã§Â»ÂÃ¦ÂÂ
        """
        dependencies = {}

        # 1. Ã¦Â£ÂÃ¦ÂÂ¥EventEngine
        try:
            from backend.core.base import get_event_engine

            event_engine = get_event_engine()
            if event_engine:
                dependencies["event_engine"] = {
                    "name": "VnPy EventEngine",
                    "status": "online",
                    "online": True,
                    "message": "Ã¤ÂºÂÃ¤Â»Â¶Ã¥Â¼ÂÃ¦ÂÂÃ¨Â¿ÂÃ¨Â¡ÂÃ¦Â­Â£Ã¥Â¸Â¸",
                }
            else:
                dependencies["event_engine"] = {
                    "name": "VnPy EventEngine",
                    "status": "offline",
                    "online": False,
                    "message": "Ã¤ÂºÂÃ¤Â»Â¶Ã¥Â¼ÂÃ¦ÂÂÃ¦ÂÂªÃ¥ÂÂÃ¥Â§ÂÃ¥ÂÂ",
                }
        except Exception as e:
            dependencies["event_engine"] = {
                "name": "VnPy EventEngine",
                "status": "error",
                "online": False,
                "message": f"Ã¦Â£ÂÃ¦ÂÂ¥Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
            }

        # 2. Ã¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂÃ¨Â¿ÂÃ¦ÂÂ¥
        try:
            import sqlite3

            from backend.infrastructure.data_module_vnpy.data_module import config_manager

            db_file = config_manager.get_db_file()
            if db_file.exists():
                # Ã¥Â°ÂÃ¨Â¯ÂÃ¨Â¿ÂÃ¦ÂÂ¥Ã¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂ
                conn = sqlite3.connect(str(db_file), timeout=1)
                conn.close()
                dependencies["database"] = {
                    "name": "SQLiteÃ¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂ",
                    "status": "online",
                    "online": True,
                    "message": "Ã¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂÃ¨Â¿ÂÃ¦ÂÂ¥Ã¦Â­Â£Ã¥Â¸Â¸",
                }
            else:
                dependencies["database"] = {
                    "name": "SQLiteÃ¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂ",
                    "status": "offline",
                    "online": False,
                    "message": "Ã¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂÃ¦ÂÂÃ¤Â»Â¶Ã¤Â¸ÂÃ¥Â­ÂÃ¥ÂÂ¨",
                }
        except Exception as e:
            dependencies["database"] = {
                "name": "SQLiteÃ¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂ",
                "status": "error",
                "online": False,
                "message": f"Ã¨Â¿ÂÃ¦ÂÂ¥Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
            }

        return dependencies

    def check_all_services(self, service_manager) -> Dict[str, Any]:
        """Ã¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂÃ¦ÂÂÃ¦Â³Â¨Ã¥ÂÂÃ§ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¯Â¼ÂÃ¥Â¢ÂÃ¥Â¼ÂºÃ§ÂÂ - Ã¥ÂÂÃ¥ÂÂ«Ã¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂÃ¯Â¼Â.

        Args:
            service_manager: Ã¦ÂÂÃ¥ÂÂ¡Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨Ã¥Â®ÂÃ¤Â¾Â

        Returns:
            Dict: Ã¦ÂÂÃ¦ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã§ÂÂÃ¦Â£ÂÃ¦ÂÂ¥Ã§Â»ÂÃ¦ÂÂÃ¯Â¼ÂÃ¥ÂÂÃ¥ÂÂ«Ã¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂÃ§ÂÂ¶Ã¦ÂÂ
        """
        try:
            service_status = service_manager.get_service_status()
            results = []

            online_count = 0
            total_response_time = 0

            for service_name, _status in service_status.items():
                check_result = self.quick_check(service_name, service_manager)
                results.append(check_result)

                if check_result["online"]:
                    online_count += 1
                    total_response_time += check_result["response_time_ms"]

            total_count = len(results)
            health_score = (online_count / total_count * 100) if total_count > 0 else 0
            avg_response_time = (total_response_time / online_count) if online_count > 0 else 0

            # Ã¦Â£ÂÃ¦ÂÂ¥Ã¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂ
            external_dependencies = self.check_external_dependencies()

            # Ã¨Â®Â¡Ã§Â®ÂÃ¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂÃ¥ÂÂ¥Ã¥ÂºÂ·Ã¥ÂºÂ¦
            dep_online = sum(
                1 for dep in external_dependencies.values() if dep.get("online") is True
            )
            dep_total = len(external_dependencies)
            dep_health_score = (dep_online / dep_total * 100) if dep_total > 0 else 0

            # Ã§Â»Â¼Ã¥ÂÂÃ¥ÂÂ¥Ã¥ÂºÂ·Ã¨Â¯ÂÃ¥ÂÂÃ¯Â¼ÂÃ¦ÂÂÃ¥ÂÂ¡Ã¦ÂÂÃ©ÂÂ70%Ã¯Â¼ÂÃ¤Â¾ÂÃ¨ÂµÂÃ¦ÂÂÃ©ÂÂ30%Ã¯Â¼Â
            overall_health_score = health_score * 0.7 + dep_health_score * 0.3

            return {
                "success": True,
                "total_services": total_count,
                "online_services": online_count,
                "health_score": round(overall_health_score, 1),
                "service_health_score": round(health_score, 1),
                "dependency_health_score": round(dep_health_score, 1),
                "avg_response_time_ms": round(avg_response_time, 2),
                "services": results,
                "external_dependencies": external_dependencies,
            }

        except Exception as e:
            self.logger.error("Ã¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂÃ¦ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥: %s", e)
            return {
                "success": False,
                "message": f"Ã¦Â£ÂÃ¦ÂÂ¥Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
                "services": [],
                "external_dependencies": {},
            }




# ServiceRestarter
class ServiceRestarter:
    """Ã¦ÂÂÃ¥ÂÂ¡Ã©ÂÂÃ¥ÂÂ¯Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨."""

    def __init__(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã©ÂÂÃ¥ÂÂ¯Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨."""
        self.logger = logging.getLogger(__name__)

    def restart_service(self, service_name: str, service_manager) -> Dict[str, Any]:
        """Ã©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥Â®ÂÃ¦ÂÂÃ¥ÂÂ¡.

        Args:
            service_name: Ã¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂÃ§Â§Â°
            service_manager: Ã¦ÂÂÃ¥ÂÂ¡Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨Ã¥Â®ÂÃ¤Â¾Â

        Returns:
            Dict: Ã©ÂÂÃ¥ÂÂ¯Ã§Â»ÂÃ¦ÂÂ
        """
        try:
            self.logger.info("Ã¥Â¼ÂÃ¥Â§ÂÃ©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ¡: %s", service_name)

            # Ã¨ÂÂ·Ã¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥Â®ÂÃ¤Â¾Â
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "success": False,
                    "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¦ÂÂªÃ¦Â³Â¨Ã¥ÂÂ",
                }

            # Ã¥ÂÂ³Ã©ÂÂ­Ã¦ÂÂÃ¥ÂÂ¡
            if hasattr(service, "shutdown"):
                try:
                    service.shutdown()
                    self.logger.info("Ã¦ÂÂÃ¥ÂÂ¡ %s Ã¥Â·Â²Ã¥ÂÂ³Ã©ÂÂ­", service_name)
                except Exception as e:
                    self.logger.warning("Ã¥ÂÂ³Ã©ÂÂ­Ã¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)

            # Ã§Â­ÂÃ¥Â¾ÂÃ¤Â¸ÂÃ¥Â°ÂÃ¦Â®ÂµÃ¦ÂÂ¶Ã©ÂÂ´
            time.sleep(0.5)

            # Ã©ÂÂÃ¦ÂÂ°Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡
            if hasattr(service, "initialize"):
                try:
                    success = service.initialize()
                    if success:
                        self.logger.info("Ã¦ÂÂÃ¥ÂÂ¡ %s Ã¥Â·Â²Ã©ÂÂÃ¦ÂÂ°Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂ", service_name)
                        return {
                            "success": True,
                            "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ",
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥Â¤Â±Ã¨Â´Â¥",
                        }
                except Exception as e:
                    self.logger.error("Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
                    return {
                        "success": False,
                        "message": f"Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
                    }
            else:
                return {
                    "success": False,
                    "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¤Â¸ÂÃ¦ÂÂ¯Ã¦ÂÂÃ©ÂÂÃ¥ÂÂ¯",
                }

        except Exception as e:
            self.logger.error("Ã©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
            return {
                "success": False,
                "message": f"Ã©ÂÂÃ¥ÂÂ¯Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
            }

    def graceful_restart(
        self, service_name: str, service_manager, timeout: int = 30
    ) -> Dict[str, Any]:
        """Ã¤Â¼ÂÃ©ÂÂÃ¥ÂÂ°Ã©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ¡Ã¯Â¼ÂÃ¥Â¸Â¦Ã¨Â¶ÂÃ¦ÂÂ¶Ã¦ÂÂ§Ã¥ÂÂ¶Ã¯Â¼Â.

        Args:
            service_name: Ã¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂÃ§Â§Â°
            service_manager: Ã¦ÂÂÃ¥ÂÂ¡Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨Ã¥Â®ÂÃ¤Â¾Â
            timeout: Ã¨Â¶ÂÃ¦ÂÂ¶Ã¦ÂÂ¶Ã©ÂÂ´Ã¯Â¼ÂÃ§Â§ÂÃ¯Â¼Â

        Returns:
            Dict: Ã©ÂÂÃ¥ÂÂ¯Ã§Â»ÂÃ¦ÂÂ
        """
        try:
            self.logger.info("Ã¥Â¼ÂÃ¥Â§ÂÃ¤Â¼ÂÃ©ÂÂÃ©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ¡: %s (timeout=%ds)", service_name, timeout)

            start_time = time.time()

            # Ã¨ÂÂ·Ã¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥Â®ÂÃ¤Â¾Â
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "success": False,
                    "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¦ÂÂªÃ¦Â³Â¨Ã¥ÂÂ",
                }

            # Ã¤Â¼ÂÃ©ÂÂÃ¥ÂÂ³Ã©ÂÂ­
            if hasattr(service, "shutdown"):
                try:
                    service.shutdown()
                    self.logger.info("Ã¦ÂÂÃ¥ÂÂ¡ %s Ã¥Â·Â²Ã¤Â¼ÂÃ©ÂÂÃ¥ÂÂ³Ã©ÂÂ­", service_name)
                except Exception as e:
                    self.logger.warning("Ã¥ÂÂ³Ã©ÂÂ­Ã¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
                    # Ã§Â»Â§Ã§Â»Â­Ã¦ÂÂ§Ã¨Â¡ÂÃ¯Â¼ÂÃ¥Â°ÂÃ¨Â¯ÂÃ©ÂÂÃ¦ÂÂ°Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂ

            # Ã¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂ¯Ã¥ÂÂ¦Ã¨Â¶ÂÃ¦ÂÂ¶
            elapsed = time.time() - start_time
            if elapsed > timeout:
                return {
                    "success": False,
                    "message": f"Ã¥ÂÂ³Ã©ÂÂ­Ã¦ÂÂÃ¥ÂÂ¡Ã¨Â¶ÂÃ¦ÂÂ¶ ({elapsed:.1f}s)",
                }

            # Ã§Â­ÂÃ¥Â¾ÂÃ¨ÂµÂÃ¦ÂºÂÃ©ÂÂÃ¦ÂÂ¾
            time.sleep(1)

            # Ã©ÂÂÃ¦ÂÂ°Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂ
            if hasattr(service, "initialize"):
                try:
                    success = service.initialize()

                    elapsed = time.time() - start_time

                    if success:
                        self.logger.info(
                            "Ã¦ÂÂÃ¥ÂÂ¡ %s Ã¤Â¼ÂÃ©ÂÂÃ©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ (Ã¨ÂÂÃ¦ÂÂ¶: %.1fs)",
                            service_name,
                            elapsed,
                        )
                        return {
                            "success": True,
                            "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¤Â¼ÂÃ©ÂÂÃ©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ",
                            "elapsed_time": round(elapsed, 1),
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥Â¤Â±Ã¨Â´Â¥",
                            "elapsed_time": round(elapsed, 1),
                        }

                except Exception as e:
                    elapsed = time.time() - start_time
                    self.logger.error("Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
                    return {
                        "success": False,
                        "message": f"Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
                        "elapsed_time": round(elapsed, 1),
                    }
            else:
                return {
                    "success": False,
                    "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¤Â¸ÂÃ¦ÂÂ¯Ã¦ÂÂÃ©ÂÂÃ¥ÂÂ¯",
                }

        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error("Ã¤Â¼ÂÃ©ÂÂÃ©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
            return {
                "success": False,
                "message": f"Ã©ÂÂÃ¥ÂÂ¯Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
                "elapsed_time": round(elapsed, 1),
            }




# ProcessManager
class ProcessManager:
    """Ã¨Â¿ÂÃ§Â¨ÂÃ§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨ - Ã¦ÂÂÃ¤Â¾ÂÃ¨Â¿ÂÃ§Â¨ÂÃ§ÂÂÃ¥ÂÂ½Ã¥ÂÂ¨Ã¦ÂÂÃ§Â®Â¡Ã§ÂÂÃ¥ÂÂÃ¨ÂÂ½."""

    def __init__(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨."""
        self.logger = logging.getLogger(__name__)

    def get_process_info(self, pid: int) -> Dict[str, Any]:
        """Ã¨ÂÂ·Ã¥ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ¤Â¿Â¡Ã¦ÂÂ¯.

        Args:
            pid: Ã¨Â¿ÂÃ§Â¨ÂID

        Returns:
            Dict: Ã¨Â¿ÂÃ§Â¨ÂÃ¤Â¿Â¡Ã¦ÂÂ¯
        """
        try:
            import psutil

            process = psutil.Process(pid)
            return {
                "pid": pid,
                "name": process.name(),
                "status": process.status(),
                "cpu_percent": process.cpu_percent(),
                "memory_percent": process.memory_percent(),
                "create_time": process.create_time(),
            }
        except Exception as e:
            self.logger.error("Ã¨ÂÂ·Ã¥ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ¤Â¿Â¡Ã¦ÂÂ¯Ã¥Â¤Â±Ã¨Â´Â¥ (pid=%d): %s", pid, e)
            return {"pid": pid, "status": "unknown", "error": str(e)}

    def manage_process_lifecycle(self, action: str, params: Dict[str, Any]) -> bool:
        """Ã§Â®Â¡Ã§ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ§ÂÂÃ¥ÂÂ½Ã¥ÂÂ¨Ã¦ÂÂ.

        Args:
            action: Ã¦ÂÂÃ¤Â½ÂÃ§Â±Â»Ã¥ÂÂ (start, stop, restart, status)
            params: Ã¨Â¿ÂÃ§Â¨ÂÃ©ÂÂÃ§Â½Â®Ã¥ÂÂÃ¦ÂÂ°

        Returns:
            bool: Ã¦ÂÂÃ¤Â½ÂÃ¦ÂÂ¯Ã¥ÂÂ¦Ã¦ÂÂÃ¥ÂÂ

        Note:
            Ã¨Â¿ÂÃ¦ÂÂ¯Ã¤Â¸ÂÃ¤Â¸ÂªÃ¦Â¡ÂÃ¦ÂÂ¶Ã¦ÂÂ¹Ã¦Â³ÂÃ¯Â¼ÂÃ©ÂÂÃ¨Â¦ÂÃ¦Â Â¹Ã¦ÂÂ®Ã¥ÂÂ·Ã¤Â½ÂÃ©ÂÂÃ¦Â±ÂÃ¥Â®ÂÃ§ÂÂ°Ã¥Â®ÂÃ©ÂÂÃ§ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ§Â®Â¡Ã§ÂÂÃ©ÂÂ»Ã¨Â¾Â
        """
        self.logger.info("Ã¨Â¿ÂÃ§Â¨ÂÃ§ÂÂÃ¥ÂÂ½Ã¥ÂÂ¨Ã¦ÂÂÃ§Â®Â¡Ã§ÂÂÃ¦ÂÂÃ¤Â½Â: %s, Ã¥ÂÂÃ¦ÂÂ°: %s", action, params)
        raise NotImplementedError("Ã¨Â¿ÂÃ§Â¨ÂÃ§ÂÂÃ¥ÂÂ½Ã¥ÂÂ¨Ã¦ÂÂÃ§Â®Â¡Ã§ÂÂÃ©ÂÂÃ¨Â¦ÂÃ¥Â®ÂÃ§ÂÂ°Ã¥Â®ÂÃ©ÂÂÃ§ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ¦ÂÂ§Ã¥ÂÂ¶Ã©ÂÂ»Ã¨Â¾Â")




# LogAnalyzer
class LogAnalyzer:
    """日志分析器 - 智能分析错误模式."""

    def __init__(self):
        """初始化日志分析器."""
        self.logger = logging.getLogger(__name__)

        # 常见错误模式
        self.error_patterns = {
            "module_not_found": r"ModuleNotFoundError|ImportError",
            "connection_error": r"ConnectionError|ConnectionTimeout|ConnectionRefusedError",
            "timeout": r"TimeoutError|timeout",
            "permission": r"PermissionError|AccessDenied",
            "file_not_found": r"FileNotFoundError",
            "type_error": r"TypeError",
            "value_error": r"ValueError",
            "key_error": r"KeyError",
            "attribute_error": r"AttributeError",
            "memory_error": r"MemoryError|Out of memory",
        }

    def analyze_error_logs(self, log_file: str, hours: int = 24) -> Dict[str, Any]:
        """分析错误日志.

        Args:
            log_file: 日志文件路径
            hours: 分析最近多少小时的日志

        Returns:
            Dict: 分析结果
        """
        try:
            log_path = Path(log_file)
            if not log_path.exists():
                return {
                    "success": False,
                    "message": f"日志文件不存在: {log_file}",
                }

            # 读取日志
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                logs = f.readlines()

            # 时间过滤
            cutoff_time = datetime.now() - timedelta(hours=hours)
            filtered_logs = self._filter_by_time(logs, cutoff_time)

            # 识别错误模式
            error_patterns = self.identify_error_patterns(filtered_logs)

            # 统计错误频率
            error_counts = Counter([e["type"] for e in error_patterns])

            # 提取TOP错误
            top_errors = error_counts.most_common(10)

            return {
                "success": True,
                "total_errors": len(error_patterns),
                "error_types": len(error_counts),
                "top_errors": [
                    {"type": error_type, "count": count} for error_type, count in top_errors
                ],
                "error_patterns": error_patterns[:50],  # 最多返回50条
                "analysis_time": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("分析日志失败: %s", e)
            return {
                "success": False,
                "message": f"分析失败: {str(e)}",
            }

    def identify_error_patterns(self, logs: List[str]) -> List[Dict[str, Any]]:
        """识别错误模式.

        Args:
            logs: 日志行列表

        Returns:
            List: 错误模式列表
        """
        errors = []

        for i, line in enumerate(logs):
            # 检查是否包含ERROR或CRITICAL
            if "ERROR" not in line and "CRITICAL" not in line:
                continue

            # 匹配错误类型
            error_type = "unknown"
            for pattern_name, pattern in self.error_patterns.items():
                if re.search(pattern, line, re.IGNORECASE):
                    error_type = pattern_name
                    break

            # 提取时间戳
            timestamp = self._extract_timestamp(line)

            # 提取错误消息
            error_msg = line.strip()

            errors.append(
                {
                    "type": error_type,
                    "message": error_msg[:200],  # 限制长度
                    "timestamp": timestamp,
                    "line_number": i + 1,
                }
            )

        return errors

    def _filter_by_time(self, logs: List[str], cutoff_time: datetime) -> List[str]:
        """按时间过滤日志.

        Args:
            logs: 日志行列表
            cutoff_time: 截止时间

        Returns:
            List: 过滤后的日志
        """
        filtered = []
        for line in logs:
            timestamp = self._extract_timestamp(line)
            if timestamp:
                try:
                    log_time = datetime.fromisoformat(timestamp)
                    if log_time >= cutoff_time:
                        filtered.append(line)
                except (ValueError, TypeError):
                    # 无法解析时间，保留该行
                    filtered.append(line)
            else:
                # 没有时间戳，保留该行
                filtered.append(line)

        return filtered

    def _extract_timestamp(self, line: str) -> Optional[str]:
        """提取日志时间戳.

        Args:
            line: 日志行

        Returns:
            Optional[str]: 时间戳字符串
        """
        # 尝试匹配常见时间戳格式
        patterns = [
            r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}",  # 2025-01-01 12:00:00
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",  # 2025-01-01T12:00:00
        ]

        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(0).replace(" ", "T")

        return None




# PerformanceAnalyzer
class PerformanceAnalyzer:
    """性能分析器 - 识别瓶颈."""

    def __init__(self):
        """初始化性能分析器."""
        self.logger = logging.getLogger(__name__)

    def analyze_bottlenecks(self) -> List[Dict[str, Any]]:
        """分析性能瓶颈.

        Returns:
            List: 瓶颈列表
        """
        try:
            import psutil

            bottlenecks = []

            # CPU瓶颈检查
            cpu_percent: float = psutil.cpu_percent(interval=1, percpu=False)  # type: ignore[assignment]
            if cpu_percent > 80:
                bottlenecks.append(
                    {
                        "type": "cpu",
                        "severity": "high" if cpu_percent > 90 else "medium",
                        "current_value": cpu_percent,
                        "threshold": 80,
                        "description": f"CPU使用率过高: {cpu_percent:.1f}%",
                        "impact": "系统响应变慢，策略计算延迟增加",
                    }
                )

            # 内存瓶颈检查
            memory = psutil.virtual_memory()
            if memory.percent > 80:
                bottlenecks.append(
                    {
                        "type": "memory",
                        "severity": "high" if memory.percent > 90 else "medium",
                        "current_value": memory.percent,
                        "threshold": 80,
                        "description": f"内存使用率过高: {memory.percent:.1f}%",
                        "impact": "可能导致OOM错误，系统崩溃风险增加",
                    }
                )

            # 磁盘瓶颈检查
            disk = psutil.disk_usage("/")
            if disk.percent > 85:
                bottlenecks.append(
                    {
                        "type": "disk",
                        "severity": "high" if disk.percent > 95 else "medium",
                        "current_value": disk.percent,
                        "threshold": 85,
                        "description": f"磁盘使用率过高: {disk.percent:.1f}%",
                        "impact": "数据写入失败，日志丢失风险",
                    }
                )

            # 磁盘I/O瓶颈检查
            disk_io = psutil.disk_io_counters()
            if disk_io:
                # 检查I/O等待时间（如果可用）
                io_time_ms = getattr(disk_io, "busy_time", 0) / 1000  # 转换为秒
                if io_time_ms > 0:
                    bottlenecks.append(
                        {
                            "type": "disk_io",
                            "severity": "medium",
                            "current_value": io_time_ms,
                            "threshold": 0,
                            "description": "磁盘I/O繁忙",
                            "impact": "数据读写速度下降",
                        }
                    )

            # 网络瓶颈检查（简化版）
            net_io = psutil.net_io_counters()
            if net_io and hasattr(net_io, "errin") and hasattr(net_io, "errout"):
                # 检查错误包
                error_count: int = net_io.errin + net_io.errout  # type: ignore[attr-defined]

                if error_count > 100:
                    bottlenecks.append(
                        {
                            "type": "network",
                            "severity": "medium",
                            "current_value": error_count,
                            "threshold": 100,
                            "description": f"网络错误包数量: {error_count}",
                            "impact": "网络连接不稳定",
                        }
                    )

            return bottlenecks

        except Exception as e:
            self.logger.error("分析性能瓶颈失败: %s", e)
            return []

    def generate_optimization_suggestions(
        self, bottlenecks: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        """生成优化建议.

        Args:
            bottlenecks: 瓶颈列表（可选）

        Returns:
            List: 优化建议列表
        """
        if bottlenecks is None:
            bottlenecks = self.analyze_bottlenecks()

        suggestions = []

        # 根据瓶颈类型生成建议
        bottleneck_types = {b["type"] for b in bottlenecks}

        if "cpu" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 启用策略结果缓存，减少重复计算",
                    "2. 优化策略算法，降低计算复杂度",
                    "3. 考虑使用多进程并行处理",
                    "4. 检查是否有死循环或无限递归",
                ]
            )

        if "memory" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 启用数据分页加载，避免一次性加载大量数据",
                    "2. 及时释放不再使用的对象",
                    "3. 使用生成器代替列表减少内存占用",
                    "4. 检查是否存在内存泄漏",
                ]
            )

        if "disk" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 清理临时文件和日志文件",
                    "2. 启用日志轮转和自动清理",
                    "3. 将大文件迁移到其他磁盘",
                    "4. 考虑扩展磁盘容量",
                ]
            )

        if "disk_io" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 启用SSD固态硬盘提升I/O性能",
                    "2. 使用异步I/O操作",
                    "3. 批量读写减少I/O次数",
                    "4. 启用数据库连接池",
                ]
            )

        if "network" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 检查网络连接质量",
                    "2. 启用数据压缩减少传输量",
                    "3. 增加请求重试次数",
                    "4. 考虑使用CDN加速",
                ]
            )

        # 通用优化建议
        if not suggestions:
            suggestions = [
                "系统运行正常，暂无优化建议",
                "建议定期监控系统性能指标",
                "保持系统和依赖库的更新",
            ]

        return suggestions




# AutoFixer
class AutoFixer:
    """自动修复建议生成器."""

    def __init__(self):
        """初始化自动修复器."""
        self.logger = logging.getLogger(__name__)

    def suggest_fixes(self, issue_type: str) -> List[Dict[str, Any]]:
        """生成修复建议.

        Args:
            issue_type: 问题类型

        Returns:
            List: 修复建议列表
        """
        fixes = []

        if issue_type == "module_not_found":
            fixes.append(
                {
                    "title": "安装缺失的模块",
                    "command": "pip install <module_name>",
                    "description": "使用pip安装缺失的Python模块",
                    "auto_fixable": False,
                    "risk_level": "low",
                }
            )

        elif issue_type == "connection_error":
            fixes.extend(
                [
                    {
                        "title": "检查网络连接",
                        "command": "ping <target_host>",
                        "description": "检查目标主机是否可达",
                        "auto_fixable": False,
                        "risk_level": "low",
                    },
                    {
                        "title": "增加连接超时时间",
                        "command": None,
                        "description": "在配置中增加timeout参数",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                    {
                        "title": "启用连接重试",
                        "command": None,
                        "description": "启用自动重试机制",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                ]
            )

        elif issue_type == "permission":
            fixes.append(
                {
                    "title": "修改文件权限",
                    "command": "chmod 755 <file_path>",
                    "description": "给予文件适当的读写权限",
                    "auto_fixable": False,
                    "risk_level": "medium",
                }
            )

        elif issue_type == "file_not_found":
            fixes.extend(
                [
                    {
                        "title": "检查文件路径",
                        "command": None,
                        "description": "确认文件路径是否正确",
                        "auto_fixable": False,
                        "risk_level": "low",
                    },
                    {
                        "title": "创建缺失的目录",
                        "command": "mkdir -p <dir_path>",
                        "description": "创建必要的目录结构",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                ]
            )

        elif issue_type == "memory_error":
            fixes.extend(
                [
                    {
                        "title": "增加系统内存",
                        "command": None,
                        "description": "扩展物理内存或虚拟内存",
                        "auto_fixable": False,
                        "risk_level": "low",
                    },
                    {
                        "title": "启用内存优化",
                        "command": None,
                        "description": "启用数据分页和惰性加载",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                    {
                        "title": "清理内存缓存",
                        "command": None,
                        "description": "手动触发垃圾回收",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                ]
            )

        else:
            fixes.append(
                {
                    "title": "查看详细日志",
                    "command": None,
                    "description": "检查日志文件获取更多信息",
                    "auto_fixable": False,
                    "risk_level": "low",
                }
            )

        return fixes


# =============================================================================
# 网络工具
# =============================================================================


class NetworkTester:
    """网络测试器."""

    def __init__(self):
        """初始化网络测试器."""
        self.logger = logging.getLogger(__name__)

    def test_host(self, host: str, port: int = 80) -> bool:
        """测试主机连通性."""
        return test_connectivity(host, port)

    def ping(self, host: str) -> bool:
        """Ping主机（简单版本）."""
        return test_connectivity(host, 80)


class PortScanner:
    """端口扫描器."""

    def __init__(self):
        """初始化端口扫描器."""
        self.logger = logging.getLogger(__name__)

    def scan(self, host: str, ports: List[int]) -> List[Dict[str, Any]]:
        """扫描指定端口."""
        return scan_ports(host, ports)

    def scan_range(self, host: str, start_port: int, end_port: int) -> List[Dict[str, Any]]:
        """扫描端口范围."""
        ports = list(range(start_port, end_port + 1))
        return self.scan(host, ports)




# Helper functions
def test_connectivity(host: str, port: int = 80) -> bool:
    """测试连通性."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except OSError:
        return False


def scan_ports(host: str, ports: List[int]) -> List[Dict[str, Any]]:
    """扫描端口."""
    results = []
    for port in ports:
        is_open = test_connectivity(host, port)
        results.append({"port": port, "open": is_open})
    return results


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
