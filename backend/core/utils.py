# -*- coding: utf-8 -*-
"""
核心工具模块 - 精简版本.

提供通用工具函数，不包含日志、告警、性能等专用功能（这些已迁移到专用模块）。

迁移说明：
- 日志相关功能 → backend.core.logging_alert
- 告警相关功能 → backend.core.logging_alert
- 性能相关功能 → backend.core.system_monitoring
"""

import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
import threading
import logging

# Qt支持检测
try:
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QMessageBox

    HAS_QT = True
    HAS_SIGNALS = True
except ImportError:
    HAS_QT = False
    HAS_SIGNALS = False


# =============================================================================
# 事件类型定义 (用于vnpy EventEngine)
# =============================================================================

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

# 日志和告警系统事件（从logging_alert迁移）
EVENT_LOG_RECORD = "eLogRecord"  # 日志记录事件
EVENT_ALERT_CREATED = "eAlertCreated"  # 告警创建事件
EVENT_ALERT_UPDATED = "eAlertUpdated"  # 告警更新事件


# =============================================================================
# 错误处理
# =============================================================================


class ErrorCategory(Enum):
    """错误类别."""

    UI = "ui"
    SYSTEM = "system"
    NETWORK = "network"
    DATA = "data"
    VNPY = "vnpy"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """错误严重程度."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorInfo:
    """错误信息."""

    def __init__(
        self,
        error_id: str,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        timestamp: Optional[float] = None,
        retry_count: int = 0,
        max_retries: int = 3,
    ):
        """初始化错误信息."""
        self.error_id = error_id
        self.message = message
        self.category = category
        self.severity = severity
        self.timestamp = timestamp or time.time()
        self.retry_count = retry_count
        self.max_retries = max_retries


class ErrorHandler:
    """错误处理器."""

    def __init__(self):
        """初始化错误处理器."""
        self.logger = logging.getLogger(__name__)
        self._error_history: List[ErrorInfo] = []
        self._handlers: Dict[str, Callable] = {}

        # 添加信号支持
        if HAS_SIGNALS:
            self.error_occurred = Signal(object)  # ErrorInfo
            self.error_resolved = Signal(str)  # error_id
            self.retry_scheduled = Signal(str, float)  # error_id, delay
        else:
            # 创建模拟信号对象
            class MockSignal:
                """模拟信号类，用于非Qt环境."""

                def connect(self, func):
                    """模拟connect方法."""
                    pass

                def disconnect(self, func):
                    """模拟disconnect方法."""
                    pass

                def emit(self, *args, **kwargs):
                    """模拟emit方法."""
                    pass

            self.error_occurred = MockSignal()
            self.error_resolved = MockSignal()
            self.retry_scheduled = MockSignal()

    def register_handler(self, error_category: str, handler: Callable):
        """注册错误处理函数."""
        self._handlers[error_category] = handler
        self.logger.debug("已注册错误处理函数: %s", error_category)

    def handle_error(self, error: ErrorInfo, auto_retry: bool = True) -> bool:
        """处理错误."""
        self._error_history.append(error)

        # 记录错误日志
        log_level = logging.ERROR if error.severity == ErrorSeverity.HIGH else logging.WARNING
        self.logger.log(
            log_level, "错误 [%s/%s]: %s", error.category.value, error.severity.value, error.message
        )

        # 发射错误信号
        try:
            self.error_occurred.emit(error)  # type: ignore
        except (RuntimeError, AttributeError):
            pass

        # 调用自定义处理器
        handler = self._handlers.get(error.category.value)
        if handler:
            try:
                return handler(error)
            except Exception as e:
                self.logger.error("错误处理器异常: %s", e)
                return False

        # 默认自动重试逻辑
        if auto_retry and error.retry_count < error.max_retries:
            delay = min(2**error.retry_count, 60)  # 指数退避，最大60秒
            self.logger.info("将在 %s 秒后重试 (第 %s 次)", delay, error.retry_count + 1)

            try:
                self.retry_scheduled.emit(error.error_id, delay)  # type: ignore
            except (RuntimeError, AttributeError):
                pass

            return False

        return True

    def get_error_history(self, limit: int = 100) -> List[ErrorInfo]:
        """获取错误历史."""
        return self._error_history[-limit:]

    def get_errors_by_category(self, category: ErrorCategory) -> List[ErrorInfo]:
        """获取指定类别的错误."""
        return [e for e in self._error_history if e.category == category]

    def get_errors_by_severity(self, severity: ErrorSeverity) -> List[ErrorInfo]:
        """获取指定严重程度的错误."""
        return [e for e in self._error_history if e.severity == severity]

    def clear_history(self):
        """清空错误历史."""
        self._error_history.clear()
        self.logger.info("错误历史已清空")

    def show_error_dialog(self, error: ErrorInfo):
        """显示错误对话框（仅在Qt环境可用）."""
        if not HAS_QT:
            self.logger.warning("Qt不可用，无法显示错误对话框")
            return

        try:
            QMessageBox.critical(
                None,
                f"错误 - {error.severity.value.upper()}",
                f"类别: {error.category.value}\n\n{error.message}",
            )
        except (RuntimeError, AttributeError) as e:
            self.logger.error("显示错误对话框失败: %s", e)

    @property
    def total_errors(self) -> int:
        """总错误数量."""
        return len(self._error_history)

    @property
    def recent_errors(self) -> List[ErrorInfo]:
        """最近的错误（最多10个）."""
        return self._error_history[-10:]

    def get_error_summary(self) -> Dict[str, Any]:
        """获取错误摘要."""
        if not self._error_history:
            return {"total": 0, "by_category": {}, "by_severity": {}}

        by_category = {}
        by_severity = {}

        for error in self._error_history:
            cat = error.category.value
            sev = error.severity.value

            by_category[cat] = by_category.get(cat, 0) + 1
            by_severity[sev] = by_severity.get(sev, 0) + 1

        return {
            "total": len(self._error_history),
            "by_category": by_category,
            "by_severity": by_severity,
        }


# =============================================================================
# 通用工具函数
# =============================================================================


def success_response(data: Any = None, message: str = "success") -> Dict[str, Any]:
    """
    成功响应格式.

    Args:
        data: 返回数据
        message: 消息

    Returns:
        响应字典
    """
    return {
        "success": True,
        "message": message,
        "data": data,
        "timestamp": datetime.now().isoformat(),
    }


def error_response(
    message: str, error_code: Optional[str] = None, data: Any = None
) -> Dict[str, Any]:
    """
    错误响应格式.

    Args:
        message: 错误消息
        error_code: 错误代码
        data: 附加数据

    Returns:
        响应字典
    """
    return {
        "success": False,
        "message": message,
        "error_code": error_code,
        "data": data,
        "timestamp": datetime.now().isoformat(),
    }


def validate_required_fields(data: Dict[str, Any], required_fields: list) -> tuple:
    """
    验证必填字段.

    Args:
        data: 数据字典
        required_fields: 必填字段列表

    Returns:
        (是否有效, 错误消息)
    """
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        return False, f"缺少必填字段: {', '.join(missing_fields)}"

    return True, ""


def validate_symbol(symbol: str) -> bool:
    """验证品种代码格式."""
    if not symbol or len(symbol) < 2 or len(symbol) > 20:
        return False
    return True


def validate_date_range(start_date: Optional[datetime], end_date: Optional[datetime]) -> tuple:
    """验证日期范围."""
    if start_date and end_date and start_date > end_date:
        return False, "开始日期不能晚于结束日期"
    return True, ""


class SimpleCache:
    """简单的内存缓存."""

    def __init__(self, ttl_seconds: int = 300):
        """
        初始化缓存.

        Args:
            ttl_seconds: 缓存过期时间（秒）
        """
        self._cache: Dict[str, tuple] = {}  # key -> (value, expire_time)
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值."""
        with self._lock:
            if key not in self._cache:
                return None

            value, expire_time = self._cache[key]

            if time.time() > expire_time:
                del self._cache[key]
                return None

            return value

    def set(self, key: str, value: Any):
        """设置缓存值."""
        with self._lock:
            expire_time = time.time() + self.ttl_seconds
            self._cache[key] = (value, expire_time)

    def delete(self, key: str):
        """删除缓存."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def clear(self):
        """清空所有缓存."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """获取缓存数量."""
        with self._lock:
            return len(self._cache)


def format_number(value: float, precision: int = 2) -> str:
    """格式化数字."""
    return f"{value:.{precision}f}"


def truncate_string(text: str, max_length: int = 100) -> str:
    """截断字符串."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


# 全局错误处理器实例
_error_handler: Optional[ErrorHandler] = None
_error_handler_lock = threading.Lock()


def get_error_handler() -> ErrorHandler:
    """获取全局错误处理器实例."""
    global _error_handler
    if _error_handler is None:
        with _error_handler_lock:
            if _error_handler is None:
                _error_handler = ErrorHandler()
    return _error_handler


# =============================================================================
# 缓存系统（从system_monitoring迁移）
# =============================================================================

from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.core.models import UnifiedMarketData


class Cache:
    """通用缓存类（LRU + TTL）."""

    def __init__(self, max_size: int = 1000, ttl: int = 300):
        """初始化缓存.

        Args:
            max_size: 最大缓存大小
            ttl: 缓存过期时间（秒）
        """
        self.max_size = max_size
        self.ttl = ttl
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.RLock()
        self.logger = logging.getLogger(__name__)

    def get(self, key: str) -> Any:
        """获取缓存项."""
        with self._lock:
            if key not in self._cache:
                return None

            # 检查是否过期
            if time.time() - self._timestamps[key] > self.ttl:
                del self._cache[key]
                del self._timestamps[key]
                return None

            # 移动到最近使用位置（LRU）
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, key: str, value: Any):
        """添加缓存项."""
        with self._lock:
            # 如果已存在，先删除
            if key in self._cache:
                del self._cache[key]
                del self._timestamps[key]

            # 检查是否超过最大大小
            if len(self._cache) >= self.max_size:
                # 删除最老的项
                oldest_key, _ = self._cache.popitem(last=False)
                del self._timestamps[oldest_key]

            # 添加新项
            self._cache[key] = value
            self._timestamps[key] = time.time()

    def clear(self):
        """清空缓存."""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()

    def size(self) -> int:
        """获取缓存大小."""
        with self._lock:
            return len(self._cache)

    def cleanup_expired(self):
        """清理过期项."""
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key
                for key, timestamp in self._timestamps.items()
                if current_time - timestamp > self.ttl
            ]

            for key in expired_keys:
                del self._cache[key]
                del self._timestamps[key]

            if expired_keys:
                self.logger.debug("清理过期缓存项: %s 个", len(expired_keys))


class DataCache:
    """数据缓存管理器."""

    def __init__(self):
        """初始化数据缓存管理器."""
        self.market_data_cache = Cache(max_size=5000, ttl=300)  # 5分钟过期
        self.order_cache = Cache(max_size=1000, ttl=600)  # 10分钟过期
        self.position_cache = Cache(max_size=1000, ttl=300)  # 5分钟过期
        self.logger = logging.getLogger(__name__)

        # 启动定期清理线程
        cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        cleanup_thread.start()

    def _cleanup_loop(self):
        """定期清理过期缓存."""
        while True:
            try:
                time.sleep(60)  # 每分钟清理一次
                self.market_data_cache.cleanup_expired()
                self.order_cache.cleanup_expired()
                self.position_cache.cleanup_expired()
            except Exception as e:
                self.logger.error("缓存清理失败: %s", e)

    def cache_market_data(self, symbol: str, data: List["UnifiedMarketData"]):
        """缓存行情数据."""
        key = f"market_{symbol}"
        self.market_data_cache.put(key, data)

    def get_market_data(self, symbol: str) -> Optional[List["UnifiedMarketData"]]:
        """获取缓存的行情数据."""
        key = f"market_{symbol}"
        return self.market_data_cache.get(key)

    def cache_order(self, order_id: str, order: Any):
        """缓存订单."""
        key = f"order_{order_id}"
        self.order_cache.put(key, order)

    def get_order(self, order_id: str) -> Any:
        """获取缓存的订单."""
        key = f"order_{order_id}"
        return self.order_cache.get(key)

    def cache_position(self, symbol: str, position: Any):
        """缓存持仓."""
        key = f"position_{symbol}"
        self.position_cache.put(key, position)

    def get_position(self, symbol: str) -> Any:
        """获取缓存的持仓."""
        key = f"position_{symbol}"
        return self.position_cache.get(key)

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息."""
        return {
            "market_data_cache": {
                "size": self.market_data_cache.size(),
                "max_size": self.market_data_cache.max_size,
            },
            "order_cache": {
                "size": self.order_cache.size(),
                "max_size": self.order_cache.max_size,
            },
            "position_cache": {
                "size": self.position_cache.size(),
                "max_size": self.position_cache.max_size,
            },
        }


# =============================================================================
# 向后兼容：从system_manager导入（可选）
# =============================================================================

# 注意：logging和monitoring功能已迁移到services/system_manager/
# LoggerMixin已迁移到service_base.py
# Cache和DataCache已在本文件中定义
# 如需使用Alert和Performance功能，请从system_manager导入


# 导出接口
__all__ = [
    # 事件类型
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
    # 错误处理
    "ErrorCategory",
    "ErrorSeverity",
    "ErrorInfo",
    "ErrorHandler",
    "get_error_handler",
    # 缓存系统
    "Cache",
    "DataCache",
    # 工具函数
    "success_response",
    "error_response",
    "validate_required_fields",
    "validate_symbol",
    "validate_date_range",
    "SimpleCache",
    "format_number",
    "truncate_string",
]
