# -*- coding: utf-8 -*-
"""
核心工具模块 - 合并版本.

整合了以下模块的功能：
- logging_utils: 日志工具
- error_handler: 错误处理
- performance_tracker: 性能跟踪
- alert_engine: 告警引擎
- utils: 通用工具函数

提供统一的工具函数接口，减少文件碎片化，优化调试体验。
"""

# =============================================================================
# Part 1: 日志工具 (来自 logging_utils.py)
# =============================================================================

import logging
import logging.handlers
from pathlib import Path
from typing import Optional, Any, Dict, Callable, List, Deque
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from collections import deque
import threading
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import time

import requests

# Qt支持检测（用于错误处理和桌面通知）
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


class LoggerMixin:
    """日志混合类."""

    @property
    def logger(self) -> logging.Logger:
        """获取日志器."""
        name = self.__class__.__name__
        return logging.getLogger(name)


def setup_logging(
    name: str = "terminal", level: str = "INFO", log_file: Optional[str] = None
) -> logging.Logger:
    """
    设置日志配置.

    Args:
        name: 日志器名称
        level: 日志级别
        log_file: 日志文件路径

    Returns:
        配置好的日志器
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器（如果指定）
    if log_file:
        try:
            # 确保日志目录存在
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - " "%(filename)s:%(lineno)d - %(message)s"
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except OSError as e:
            logger.warning("无法创建日志文件处理器: %s", e)

    return logger


def get_logger(name: str) -> logging.Logger:
    """获取日志器."""
    return logging.getLogger(name)


# =============================================================================
# Part 2: 错误处理 (来自 error_handler.py)
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
        self._error_history: list[ErrorInfo] = []
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

                def connect(self, callback):  # pylint: disable=unused-argument
                    """连接信号."""
                    del callback

                def emit(self, *args):  # pylint: disable=unused-argument
                    """发出信号."""
                    del args

            self.error_occurred = MockSignal()
            self.error_resolved = MockSignal()
            self.retry_scheduled = MockSignal()

    def register_handler(self, category: ErrorCategory, handler: Callable):
        """注册错误处理器."""
        self._handlers[category.value] = handler

    def handle_error(
        self,
        error_id: str,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        max_retries: int = 1,
        callback: Optional[Callable] = None,
        parent_widget=None,
    ) -> bool:
        """处理错误.

        Args:
            error_id: 错误ID
            message: 错误消息
            category: 错误类别
            severity: 错误严重程度
            max_retries: 最大重试次数
            callback: 回调函数
            parent_widget: 父窗口部件

        Returns:
            是否处理成功
        """
        error_info = ErrorInfo(error_id, message, category, severity)

        # 添加到历史记录
        self._error_history.append(error_info)

        # 限制历史记录数量
        if len(self._error_history) > 1000:
            self._error_history = self._error_history[-500:]

        # 调用特定处理器
        if category.value in self._handlers:
            try:
                handler = self._handlers[category.value]
                return handler(error_info, max_retries, callback, parent_widget)
            except (AttributeError, TypeError) as e:
                self.logger.error("错误处理器执行失败: %s", e)

        # 默认处理
        return self._default_error_handler(error_info, max_retries, callback, parent_widget)

    def _default_error_handler(  # pylint: disable=unused-argument
        self,
        error_info: ErrorInfo,
        max_retries: int,  # noqa: U100
        callback: Optional[Callable],
        parent_widget,
    ) -> bool:
        """默认错误处理器."""
        self.logger.error(
            "[%s] %s: %s",
            error_info.category.value,
            error_info.error_id,
            error_info.message,
        )

        # 根据严重程度决定是否显示对话框
        if error_info.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            if HAS_QT and parent_widget:
                QMessageBox.critical(
                    parent_widget,
                    "错误",
                    f"{error_info.error_id}: {error_info.message}",
                    QMessageBox.StandardButton.Ok,
                )
            else:
                print(f"错误: {error_info.error_id}: {error_info.message}")

        # 执行回调
        if callback:
            try:
                callback(error_info)
            except (AttributeError, TypeError, ValueError) as e:
                self.logger.error("错误回调执行失败: %s", e)

        return False

    def get_error_history(self, limit: int = 100) -> list[ErrorInfo]:
        """获取错误历史."""
        return self._error_history[-limit:] if self._error_history else []

    def clear_error_history(self):
        """清空错误历史."""
        self._error_history.clear()
        self.logger.info("错误历史已清空")

    def get_error_status(self):
        """获取错误状态."""
        categories = {}
        severities = {}

        for error in self._error_history:
            # 统计类别
            cat = error.category.value if hasattr(error.category, "value") else str(error.category)
            categories[cat] = categories.get(cat, 0) + 1

            # 统计严重程度
            sev = error.severity.value if hasattr(error.severity, "value") else str(error.severity)
            severities[sev] = severities.get(sev, 0) + 1

        return {
            "error_categories": categories,
            "error_severities": severities,
            "active_errors": len(self._error_history),
            "suppressed_errors": 0,
            "circuit_breakers": 0,
        }

    def resolve_error(self, error_id: str):
        """解决错误."""
        self.logger.info("解决错误: %s", error_id)
        # 从历史记录中移除错误
        self._error_history = [e for e in self._error_history if e.error_id != error_id]
        # 发出信号
        self.error_resolved.emit(error_id)  # type: ignore

    class Suppressor:
        """错误抑制器类."""

        def clear_suppression(self, error_id=None):
            """清除抑制."""
            if error_id:
                print(f"清除抑制: {error_id}")
            else:
                print("清除所有抑制")

    @property
    def suppressor(self):
        """获取抑制器."""
        return self.Suppressor()


# 全局错误处理器实例
error_handler = ErrorHandler()


# =============================================================================
# Part 3: 性能跟踪 (来自 performance_tracker.py)
# =============================================================================


class PerformanceMetrics:
    """性能指标数据结构."""

    def __init__(self, category: str):
        """初始化性能指标.

        Args:
            category: 指标分类 (data_processing/strategy_execution/trading_execution)
        """
        self.category = category
        self.total_calls = 0
        self.total_time = 0.0
        self.min_time = float("inf")
        self.max_time = 0.0
        self.recent_times: Deque[float] = deque(maxlen=100)  # 保留最近100次记录
        self.error_count = 0
        self.last_update = datetime.now()

    def record(self, execution_time: float, success: bool = True):
        """记录一次执行.

        Args:
            execution_time: 执行时间（秒）
            success: 是否成功
        """
        self.total_calls += 1
        if success:
            self.total_time += execution_time
            self.min_time = min(self.min_time, execution_time)
            self.max_time = max(self.max_time, execution_time)
            self.recent_times.append(execution_time)
        else:
            self.error_count += 1
        self.last_update = datetime.now()

    def get_avg_time_ms(self) -> float:
        """获取平均执行时间（毫秒）."""
        if self.total_calls == 0:
            return 0.0
        # 使用最近的记录计算平均值（更准确反映当前性能）
        if len(self.recent_times) > 0:
            return sum(self.recent_times) / len(self.recent_times) * 1000
        return 0.0

    def get_success_rate(self) -> float:
        """获取成功率."""
        if self.total_calls == 0:
            return 100.0
        return ((self.total_calls - self.error_count) / self.total_calls) * 100

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        return {
            "category": self.category,
            "total_calls": self.total_calls,
            "avg_time_ms": self.get_avg_time_ms(),
            "min_time_ms": self.min_time * 1000 if self.min_time != float("inf") else 0.0,
            "max_time_ms": self.max_time * 1000,
            "error_count": self.error_count,
            "success_rate": self.get_success_rate(),
            "last_update": self.last_update.isoformat(),
        }


class PerformanceTracker:
    """性能跟踪器（单例）.

    用于跟踪和收集系统各模块的性能指标。
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """创建单例实例."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化性能跟踪器."""
        if not hasattr(self, "_initialized"):
            self.logger = logging.getLogger(__name__)
            self.metrics: Dict[str, PerformanceMetrics] = {}
            self._lock = threading.Lock()
            self._initialized = True

    def track(self, metric_name: str, category: str):
        """性能跟踪装饰器.

        Args:
            metric_name: 指标名称
            category: 指标分类 (data_processing/strategy_execution/trading_execution)

        Returns:
            Callable: 装饰器函数

        Example:
            @performance_tracker.track("query_local_data", "data_processing")
            def query_data(self, symbol):
                # 函数实现
                pass
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                success = True
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    success = False
                    raise e
                finally:
                    execution_time = time.time() - start_time
                    self._record_metric(metric_name, category, execution_time, success)

            return wrapper

        return decorator

    def _record_metric(self, metric_name: str, category: str, execution_time: float, success: bool):
        """记录指标数据.

        Args:
            metric_name: 指标名称
            category: 指标分类
            execution_time: 执行时间（秒）
            success: 是否成功
        """
        with self._lock:
            if metric_name not in self.metrics:
                self.metrics[metric_name] = PerformanceMetrics(category)
            self.metrics[metric_name].record(execution_time, success)

    def record_manual(
        self, metric_name: str, category: str, execution_time: float, success: bool = True
    ):
        """手动记录指标（用于无法使用装饰器的场景）.

        Args:
            metric_name: 指标名称
            category: 指标分类
            execution_time: 执行时间（秒）
            success: 是否成功
        """
        self._record_metric(metric_name, category, execution_time, success)

    def get_metrics_by_category(self, category: str) -> Dict[str, Dict[str, Any]]:
        """获取指定分类的所有指标.

        Args:
            category: 指标分类

        Returns:
            Dict: 指标数据字典
        """
        with self._lock:
            result = {}
            for metric_name, metric in self.metrics.items():
                if metric.category == category:
                    result[metric_name] = metric.to_dict()
            return result

    def get_all_metrics(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """获取所有分类的指标.

        Returns:
            Dict: 按分类组织的所有指标数据
        """
        with self._lock:
            result: Dict[str, Dict[str, Any]] = {
                "data_processing": {},
                "strategy_execution": {},
                "trading_execution": {},
            }
            for metric_name, metric in self.metrics.items():
                category = metric.category
                if category in result:
                    result[category][metric_name] = metric.to_dict()
            return result

    def reset(self):
        """重置所有指标."""
        with self._lock:
            self.metrics.clear()
            self.logger.info("性能指标已重置")

    def reset_category(self, category: str):
        """重置指定分类的指标.

        Args:
            category: 指标分类
        """
        with self._lock:
            metrics_to_remove = [
                name for name, metric in self.metrics.items() if metric.category == category
            ]
            for name in metrics_to_remove:
                del self.metrics[name]
            self.logger.info("性能指标已重置: %s", category)


# 全局单例实例
performance_tracker = PerformanceTracker()


# =============================================================================
# Part 4: 告警引擎 (来自 alert_engine.py)
# =============================================================================


class AlertSeverity(Enum):
    """告警严重程度."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """告警状态."""

    NEW = "new"  # 新建
    ACKNOWLEDGED = "acknowledged"  # 已确认
    IN_PROGRESS = "in_progress"  # 处理中
    RESOLVED = "resolved"  # 已解决
    IGNORED = "ignored"  # 已忽略


class NotificationType(Enum):
    """通知类型."""

    DESKTOP = "desktop"  # 桌面通知
    EMAIL = "email"  # 邮件通知
    WEBHOOK = "webhook"  # Webhook通知
    LOG = "log"  # 日志通知


class AlertRule:
    """告警规则."""

    def __init__(
        self,
        rule_id: str,
        name: str,
        condition: str,
        severity: AlertSeverity,
        enabled: bool = True,
        priority: int = 0,
        group: str = "default",
        description: str = "",
        notification_types: Optional[List[NotificationType]] = None,
    ):
        """初始化告警规则.

        Args:
            rule_id: 规则ID
            name: 规则名称
            condition: 条件表达式（Python表达式）
            severity: 严重程度
            enabled: 是否启用
            priority: 优先级（数字越大优先级越高）
            group: 规则分组
            description: 描述
            notification_types: 通知类型列表
        """
        self.rule_id = rule_id
        self.name = name
        self.condition = condition
        self.severity = severity
        self.enabled = enabled
        self.priority = priority
        self.group = group
        self.description = description
        self.notification_types = notification_types or [NotificationType.LOG]
        self.created_at = datetime.now()
        self.last_triggered: Optional[datetime] = None
        self.trigger_count = 0

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """评估规则条件.

        Args:
            context: 评估上下文（包含变量值）

        Returns:
            bool: 规则是否满足
        """
        if not self.enabled:
            return False

        try:
            # 安全的表达式评估（仅允许基本运算和比较）
            # 安全措施：
            # 1. 清空__builtins__防止访问危险函数
            # 2. 只提供有限的基本数学函数
            # 3. 通过safe_namespace限制可用变量和函数
            safe_namespace = {
                "__builtins__": {},
                "abs": abs,
                "min": min,
                "max": max,
                "len": len,
                "round": round,
            }
            safe_namespace.update(context)

            # 评估条件表达式（使用eval是因为条件可能是动态表达式）
            result = eval(self.condition, safe_namespace)  # noqa: S307

            if result:
                self.last_triggered = datetime.now()
                self.trigger_count += 1

            return bool(result)

        except Exception as e:
            logging.error("规则评估失败 %s: %s", self.name, str(e))
            return False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "condition": self.condition,
            "severity": self.severity.value,
            "enabled": self.enabled,
            "priority": self.priority,
            "group": self.group,
            "description": self.description,
            "notification_types": [nt.value for nt in self.notification_types],
            "created_at": self.created_at.isoformat(),
            "last_triggered": self.last_triggered.isoformat() if self.last_triggered else None,
            "trigger_count": self.trigger_count,
        }


class Alert:
    """告警实例."""

    def __init__(
        self,
        alert_id: str,
        rule: AlertRule,
        message: str,
        context: Dict[str, Any],
    ):
        """初始化告警实例.

        Args:
            alert_id: 告警ID
            rule: 触发的规则
            message: 告警消息
            context: 告警上下文
        """
        self.alert_id = alert_id
        self.rule = rule
        self.message = message
        self.context = context
        self.status = AlertStatus.NEW
        self.severity = rule.severity
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.acknowledged_at: Optional[datetime] = None
        self.resolved_at: Optional[datetime] = None
        self.notes: List[str] = []

    def acknowledge(self, note: str = ""):
        """确认告警."""
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = datetime.now()
        self.updated_at = datetime.now()
        if note:
            self.notes.append(f"[确认] {note}")

    def start_progress(self, note: str = ""):
        """开始处理."""
        self.status = AlertStatus.IN_PROGRESS
        self.updated_at = datetime.now()
        if note:
            self.notes.append(f"[处理中] {note}")

    def resolve(self, note: str = ""):
        """解决告警."""
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.now()
        self.updated_at = datetime.now()
        if note:
            self.notes.append(f"[已解决] {note}")

    def ignore(self, note: str = ""):
        """忽略告警."""
        self.status = AlertStatus.IGNORED
        self.updated_at = datetime.now()
        if note:
            self.notes.append(f"[已忽略] {note}")

    def add_note(self, note: str):
        """添加备注."""
        self.notes.append(f"[备注] {note}")
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        return {
            "alert_id": self.alert_id,
            "rule_id": self.rule.rule_id,
            "rule_name": self.rule.name,
            "message": self.message,
            "severity": self.severity.value,
            "status": self.status.value,
            "context": self.context,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "notes": self.notes,
        }


class AlertEngine:
    """告警引擎（单例）."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """创建单例实例."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化告警引擎."""
        if not hasattr(self, "_initialized"):
            self.logger = logging.getLogger(__name__)
            self.rules: Dict[str, AlertRule] = {}
            self.alerts: Dict[str, Alert] = {}
            self.alert_history: List[Alert] = []
            self._lock = threading.Lock()
            self._alert_counter = 0
            self._suppression_window = 300  # 5分钟抑制窗口
            self._last_alerts: Dict[str, datetime] = {}  # 用于告警抑制
            self._initialized = True

            # 通知配置
            self.notification_config = {
                "email": {
                    "enabled": False,
                    "smtp_server": "",
                    "smtp_port": 587,
                    "username": "",
                    "password": "",
                    "from_addr": "",
                    "to_addrs": [],
                },
                "webhook": {
                    "enabled": False,
                    "url": "",
                    "headers": {},
                },
            }

    def add_rule(self, rule: AlertRule) -> bool:
        """添加规则.

        Args:
            rule: 告警规则

        Returns:
            bool: 是否成功
        """
        with self._lock:
            if rule.rule_id in self.rules:
                self.logger.warning("规则已存在: %s", rule.rule_id)
                return False
            self.rules[rule.rule_id] = rule
            self.logger.info("规则已添加: %s", rule.name)
            return True

    def update_rule(self, rule_id: str, **kwargs) -> bool:
        """更新规则.

        Args:
            rule_id: 规则ID
            **kwargs: 要更新的属性

        Returns:
            bool: 是否成功
        """
        with self._lock:
            if rule_id not in self.rules:
                self.logger.warning("规则不存在: %s", rule_id)
                return False

            rule = self.rules[rule_id]
            for key, value in kwargs.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)

            self.logger.info("规则已更新: %s", rule.name)
            return True

    def delete_rule(self, rule_id: str) -> bool:
        """删除规则.

        Args:
            rule_id: 规则ID

        Returns:
            bool: 是否成功
        """
        with self._lock:
            if rule_id not in self.rules:
                return False
            del self.rules[rule_id]
            self.logger.info("规则已删除: %s", rule_id)
            return True

    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """获取规则.

        Args:
            rule_id: 规则ID

        Returns:
            Optional[AlertRule]: 规则对象
        """
        return self.rules.get(rule_id)

    def get_all_rules(self, group: Optional[str] = None) -> List[AlertRule]:
        """获取所有规则.

        Args:
            group: 规则分组（可选）

        Returns:
            List[AlertRule]: 规则列表
        """
        if group:
            return [r for r in self.rules.values() if r.group == group]
        return list(self.rules.values())

    def evaluate_rules(self, context: Dict[str, Any]) -> List[Alert]:
        """评估所有规则.

        Args:
            context: 评估上下文

        Returns:
            List[Alert]: 触发的告警列表
        """
        triggered_alerts = []

        # 按优先级排序规则
        sorted_rules = sorted(self.rules.values(), key=lambda r: r.priority, reverse=True)

        for rule in sorted_rules:
            if rule.evaluate(context):
                # 检查告警抑制
                if self._should_suppress(rule.rule_id):
                    continue

                # 创建告警
                alert = self._create_alert(rule, context)
                triggered_alerts.append(alert)

                # 发送通知
                self._send_notifications(alert)

        return triggered_alerts

    def _should_suppress(self, rule_id: str) -> bool:
        """检查是否应该抑制告警.

        Args:
            rule_id: 规则ID

        Returns:
            bool: 是否应该抑制
        """
        if rule_id in self._last_alerts:
            last_time = self._last_alerts[rule_id]
            if datetime.now() - last_time < timedelta(seconds=self._suppression_window):
                return True

        self._last_alerts[rule_id] = datetime.now()
        return False

    def _create_alert(self, rule: AlertRule, context: Dict[str, Any]) -> Alert:
        """创建告警实例.

        Args:
            rule: 触发的规则
            context: 告警上下文

        Returns:
            Alert: 告警实例
        """
        with self._lock:
            self._alert_counter += 1
            alert_id = f"alert_{self._alert_counter}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        message = f"{rule.name}: {rule.description}"

        alert = Alert(alert_id, rule, message, context)

        with self._lock:
            self.alerts[alert_id] = alert
            self.alert_history.append(alert)

            # 限制历史记录大小
            if len(self.alert_history) > 1000:
                self.alert_history = self.alert_history[-500:]

        return alert

    def _send_notifications(self, alert: Alert):
        """发送告警通知.

        Args:
            alert: 告警实例
        """
        for notification_type in alert.rule.notification_types:
            try:
                if notification_type == NotificationType.LOG:
                    self._send_log_notification(alert)
                elif notification_type == NotificationType.EMAIL:
                    self._send_email_notification(alert)
                elif notification_type == NotificationType.WEBHOOK:
                    self._send_webhook_notification(alert)
                elif notification_type == NotificationType.DESKTOP:
                    self._send_desktop_notification(alert)
            except Exception as e:
                self.logger.error("发送通知失败 [%s]: %s", notification_type.value, str(e))

    def _send_log_notification(self, alert: Alert):
        """发送日志通知."""
        log_level = {
            AlertSeverity.INFO: logging.INFO,
            AlertSeverity.WARNING: logging.WARNING,
            AlertSeverity.ERROR: logging.ERROR,
            AlertSeverity.CRITICAL: logging.CRITICAL,
        }.get(alert.severity, logging.INFO)

        self.logger.log(
            log_level,
            "[告警] %s - %s (规则: %s)",
            alert.severity.value.upper(),
            alert.message,
            alert.rule.name,
        )

    def _send_email_notification(self, alert: Alert):
        """发送邮件通知."""
        config = self.notification_config["email"]
        if not config["enabled"]:
            return

        msg = MIMEMultipart()
        msg["From"] = config["from_addr"]
        msg["To"] = ", ".join(config["to_addrs"])
        msg["Subject"] = f"[{alert.severity.value.upper()}] {alert.message}"

        body = f"""
告警通知

规则: {alert.rule.name}
严重程度: {alert.severity.value}
消息: {alert.message}
时间: {alert.created_at.isoformat()}
上下文: {json.dumps(alert.context, indent=2, ensure_ascii=False)}
"""

        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
                server.starttls()
                server.login(config["username"], config["password"])
                server.send_message(msg)
        except Exception as e:
            self.logger.error("发送邮件失败: %s", str(e))

    def _send_webhook_notification(self, alert: Alert):
        """发送Webhook通知."""
        config = self.notification_config["webhook"]
        if not config["enabled"]:
            return

        payload = {
            "alert_id": alert.alert_id,
            "rule_name": alert.rule.name,
            "severity": alert.severity.value,
            "message": alert.message,
            "created_at": alert.created_at.isoformat(),
            "context": alert.context,
        }

        try:
            response = requests.post(
                config["url"], json=payload, headers=config.get("headers", {}), timeout=10
            )
            response.raise_for_status()
        except Exception as e:
            self.logger.error("发送Webhook失败: %s", str(e))

    def _send_desktop_notification(self, alert: Alert):
        """发送桌面通知（需要PyQt集成）."""
        # 这里需要与UI层集成，暂时记录日志
        self.logger.info("[桌面通知] %s - %s", alert.severity.value.upper(), alert.message)

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """获取告警.

        Args:
            alert_id: 告警ID

        Returns:
            Optional[Alert]: 告警实例
        """
        return self.alerts.get(alert_id)

    def get_active_alerts(self) -> List[Alert]:
        """获取活动告警（未解决/未忽略）."""
        return [
            alert
            for alert in self.alerts.values()
            if alert.status not in [AlertStatus.RESOLVED, AlertStatus.IGNORED]
        ]

    def get_alert_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        severity: Optional[AlertSeverity] = None,
        status: Optional[AlertStatus] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """查询告警历史.

        Args:
            start_time: 开始时间
            end_time: 结束时间
            severity: 严重程度过滤
            status: 状态过滤
            limit: 返回数量限制

        Returns:
            List[Alert]: 告警列表
        """
        filtered = self.alert_history

        if start_time:
            filtered = [a for a in filtered if a.created_at >= start_time]
        if end_time:
            filtered = [a for a in filtered if a.created_at <= end_time]
        if severity:
            filtered = [a for a in filtered if a.severity == severity]
        if status:
            filtered = [a for a in filtered if a.status == status]

        # 按创建时间倒序排序
        filtered.sort(key=lambda a: a.created_at, reverse=True)

        return filtered[:limit]

    def acknowledge_alert(self, alert_id: str, note: str = "") -> bool:
        """确认告警.

        Args:
            alert_id: 告警ID
            note: 备注

        Returns:
            bool: 是否成功
        """
        alert = self.alerts.get(alert_id)
        if not alert:
            return False

        alert.acknowledge(note)
        self.logger.info("告警已确认: %s", alert_id)
        return True

    def resolve_alert(self, alert_id: str, note: str = "") -> bool:
        """解决告警.

        Args:
            alert_id: 告警ID
            note: 备注

        Returns:
            bool: 是否成功
        """
        alert = self.alerts.get(alert_id)
        if not alert:
            return False

        alert.resolve(note)
        self.logger.info("告警已解决: %s", alert_id)
        return True

    def ignore_alert(self, alert_id: str, note: str = "") -> bool:
        """忽略告警.

        Args:
            alert_id: 告警ID
            note: 备注

        Returns:
            bool: 是否成功
        """
        alert = self.alerts.get(alert_id)
        if not alert:
            return False

        alert.ignore(note)
        self.logger.info("告警已忽略: %s", alert_id)
        return True

    def configure_notifications(self, notification_type: NotificationType, config: Dict[str, Any]):
        """配置通知系统.

        Args:
            notification_type: 通知类型
            config: 配置参数
        """
        if notification_type == NotificationType.EMAIL:
            self.notification_config["email"].update(config)
        elif notification_type == NotificationType.WEBHOOK:
            self.notification_config["webhook"].update(config)

        self.logger.info("通知配置已更新: %s", notification_type.value)


# 全局单例实例
alert_engine = AlertEngine()


# 预定义规则模板
ALERT_RULE_TEMPLATES = {
    "cpu_high": {
        "name": "CPU使用率过高",
        "condition": "cpu_percent > {threshold}",
        "severity": AlertSeverity.WARNING,
        "description": "CPU使用率超过阈值",
    },
    "memory_high": {
        "name": "内存使用率过高",
        "condition": "memory_percent > {threshold}",
        "severity": AlertSeverity.WARNING,
        "description": "内存使用率超过阈值",
    },
    "disk_high": {
        "name": "磁盘使用率过高",
        "condition": "disk_percent > {threshold}",
        "severity": AlertSeverity.ERROR,
        "description": "磁盘使用率超过阈值",
    },
    "order_failed": {
        "name": "订单失败率过高",
        "condition": "order_fail_rate > {threshold}",
        "severity": AlertSeverity.CRITICAL,
        "description": "订单失败率超过阈值",
    },
    "strategy_error": {
        "name": "策略执行错误",
        "condition": "strategy_error_count > {threshold}",
        "severity": AlertSeverity.ERROR,
        "description": "策略执行错误次数超过阈值",
    },
}


def create_rule_from_template(
    template_name: str, rule_id: str, threshold: float, **kwargs
) -> AlertRule:
    """从模板创建规则.

    Args:
        template_name: 模板名称
        rule_id: 规则ID
        threshold: 阈值
        **kwargs: 其他参数

    Returns:
        AlertRule: 规则对象
    """
    template = ALERT_RULE_TEMPLATES.get(template_name)
    if not template:
        raise ValueError(f"未知模板: {template_name}")

    # 类型检查已通过上面的 if not template 确保
    assert isinstance(template, dict)  # 帮助 mypy 理解类型

    condition = str(template["condition"]).format(threshold=threshold)

    return AlertRule(
        rule_id=rule_id,
        name=str(template["name"]),
        condition=condition,
        severity=(
            AlertSeverity(template["severity"])
            if isinstance(template["severity"], str)
            else template["severity"]
        ),
        description=str(template["description"]),
        **kwargs,
    )


# =============================================================================
# Part 5: 通用工具函数 (来自 backend/utils/utils.py)
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

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值."""
        if key not in self._cache:
            return None

        value, expire_time = self._cache[key]

        # 检查是否过期
        if datetime.now() > expire_time:
            del self._cache[key]
            return None

        return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """设置缓存值."""
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        expire_time = datetime.now() + timedelta(seconds=ttl)
        self._cache[key] = (value, expire_time)

    def delete(self, key: str) -> bool:
        """删除缓存."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """清空缓存."""
        self._cache.clear()

    def size(self) -> int:
        """获取缓存大小."""
        return len(self._cache)


def format_number(value: float, precision: int = 2) -> str:
    """格式化数字."""
    return f"{value:.{precision}f}"


def truncate_string(text: str, max_length: int = 100) -> str:
    """截断字符串."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


# =============================================================================
# 导出的公共接口
# =============================================================================

__all__ = [
    # 日志工具
    "LoggerMixin",
    "setup_logging",
    "get_logger",
    # 错误处理
    "ErrorCategory",
    "ErrorSeverity",
    "ErrorInfo",
    "ErrorHandler",
    "error_handler",
    # 性能跟踪
    "PerformanceMetrics",
    "PerformanceTracker",
    "performance_tracker",
    # 告警引擎
    "AlertSeverity",
    "AlertStatus",
    "NotificationType",
    "AlertRule",
    "Alert",
    "AlertEngine",
    "alert_engine",
    "ALERT_RULE_TEMPLATES",
    "create_rule_from_template",
    # 通用工具
    "success_response",
    "error_response",
    "validate_required_fields",
    "validate_symbol",
    "validate_date_range",
    "SimpleCache",
    "format_number",
    "truncate_string",
]
