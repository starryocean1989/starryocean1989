# -*- coding: utf-8 -*-
"""
错误处理模块.

提供统一的错误处理和管理功能.
"""

import logging
from enum import Enum
from typing import Callable, Dict, Optional

try:
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QMessageBox

    HAS_QT = True
    HAS_SIGNALS = True
except ImportError:
    HAS_QT = False
    HAS_SIGNALS = False


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
        self.timestamp = timestamp or __import__("time").time()
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
