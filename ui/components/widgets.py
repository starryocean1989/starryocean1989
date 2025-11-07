# -*- coding: utf-8 -*-
"""UI组件合集 - 基础组件、Dashboard组件和Monaco编辑器.

本文件整合了以下组件：
1. 基础框架：
   - ErrorCategory: 错误分类枚举
   - ErrorSeverity: 错误严重程度枚举
   - BaseWidget: 基础Widget基类

2. Dashboard组件：
   - MetricCard: 大数字指标卡片
   - MiniSparkline: 迷你趋势图
   - GaugeWidget: 半圆仪表盘
   - StatusIndicator: 状态指示器
   - CompactTable: 紧凑型表格

3. Monaco编辑器：
   - LineNumberArea: 行号显示区域
   - PythonHighlighter: Python语法高亮器
   - MonacoEditorWidget: Monaco编辑器增强版
"""
import logging
import os
import re
from collections import deque, namedtuple
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.components.theme_system import DashboardTheme

try:
    from native_qhighlighter import NativePythonHighlighter  # type: ignore

    NATIVE_QHIGHLIGHTER_AVAILABLE = True
except Exception:  # noqa: BLE001 - 仅用于探测
    NativePythonHighlighter = None  # type: ignore
    NATIVE_QHIGHLIGHTER_AVAILABLE = False


def _should_use_native_highlighter() -> bool:
    """根据环境变量决定是否启用原生高亮器."""

    if not NATIVE_QHIGHLIGHTER_AVAILABLE:
        return False

    value = os.getenv("NATIVE_QHIGHLIGHTER", "1").strip().lower()
    return value not in {"0", "false", "off"}


# ==================== 第1部分：基础框架 ====================


class ErrorCategory(Enum):
    """错误分类枚举."""

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
        import time

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
        self.logger = logging.getLogger("ui.components.error_handler")
        self._error_history: List[ErrorInfo] = []
        self._handlers: Dict[str, Callable] = {}

        # 添加信号支持
        from PySide6.QtCore import Signal

        self.error_occurred = Signal(object)  # ErrorInfo
        self.error_resolved = Signal(str)  # error_id
        self.retry_scheduled = Signal(str, float)  # error_id, delay

    def register_handler(self, error_category: str, handler: Callable):
        """注册错误处理函数."""
        self._handlers[error_category] = handler
        self.logger.debug("已注册错误处理函数: %s", error_category)

    def handle_error(self, error: ErrorInfo, auto_retry: bool = True) -> bool:
        """处理错误."""
        self._error_history.append(error)

        # 记录错误日志
        severity_mapping = {
            ErrorSeverity.LOW: logging.INFO,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL,
        }
        log_level = severity_mapping.get(error.severity, logging.WARNING)

        # 根据严重性选择log_type
        if error.severity == ErrorSeverity.CRITICAL:
            log_type = "SYSTEM"
        elif error.severity == ErrorSeverity.HIGH:
            log_type = "ALERT"
        else:
            log_type = "SYSTEM"

        self.logger.log(
            log_level,
            "UI错误处理: 类别=%s, 严重性=%s, ID=%s, 消息=%s, 重试=%d/%d",
            error.category.value,
            error.severity.value,
            error.error_id,
            error.message,
            error.retry_count,
            error.max_retries,
            extra={"log_type": log_type},
            exc_info=(log_level >= logging.ERROR)
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
                self.logger.error(
                    "UI错误处理器异常: 类别=%s, 处理器错误=%s",
                    error.category.value,
                    str(e),
                    extra={"log_type": "SYSTEM"},
                    exc_info=True
                )
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
        """显示错误对话框."""
        try:
            QMessageBox.critical(
                None,
                f"错误 - {error.severity.value.upper()}",
                f"类别: {error.category.value}\n\n{error.message}",
            )
        except (RuntimeError, AttributeError) as e:
            self.logger.error("显示错误对话框失败: %s", e, extra={"log_type": "SYSTEM"}, exc_info=True)

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

        self.logger.info(
            "错误统计: 总计=%d, 类别=%s, 严重程度=%s",
            len(self._error_history),
            ", ".join(f"{k}={v}" for k, v in by_category.items()),
            ", ".join(f"{k}={v}" for k, v in by_severity.items()),
        )

        return {
            "total": len(self._error_history),
            "by_category": by_category,
            "by_severity": by_severity,
        }


# 全局错误处理器实例
_error_handler: Optional[ErrorHandler] = None
_error_handler_lock = None  # 延迟初始化


def get_error_handler() -> ErrorHandler:
    """获取全局错误处理器实例."""
    global _error_handler, _error_handler_lock

    if _error_handler is None:
        import threading

        if _error_handler_lock is None:
            _error_handler_lock = threading.Lock()

        with _error_handler_lock:
            if _error_handler is None:
                _error_handler = ErrorHandler()

    return _error_handler


class BaseWidget(QWidget):
    """基础控件基类."""

    # 信号定义
    error_occurred = Signal(str)  # 错误信号
    info_message = Signal(str)  # 信息信号
    data_updated = Signal(dict)  # 数据更新信号

    def __init__(self, parent=None, title: str = ""):
        """初始化基础控件.

        Args:
            parent: 父控件
            title: 窗口标题
        """
        super().__init__(parent)
        self.title = title
        # ✅ 使用ui.components前缀
        self._logger = logging.getLogger(f"ui.components.{self.__class__.__name__.lower()}")
        self._is_initialized = False
        self._update_timer: Optional[QTimer] = None

        # 设置窗口标志
        self.setWindowFlags(Qt.WindowType.Widget)

        # 初始化UI
        self.setup_ui()
        self.connect_signals()

        self._is_initialized = True
        self._logger.info("%s 初始化完成", self.__class__.__name__)

    @property
    def logger(self):
        """获取日志器."""
        return self._logger

    @logger.setter
    def logger(self, value):
        """设置日志器."""
        self._logger = value

    def setup_ui(self):
        """设置用户界面 - 子类必须实现."""
        raise NotImplementedError("子类必须实现 setup_ui 方法")

    def connect_signals(self):
        """连接信号槽 - 子类可以重写."""
        # pylint: disable=unnecessary-pass
        pass

    def show_error(
        self,
        message: str,
        title: str = "错误",
        error_id: Optional[str] = None,
        category: Any = ErrorCategory.UI,
        severity: Any = ErrorSeverity.MEDIUM,
        max_retries: int = 1,
        retry_callback: Optional[Callable[..., Any]] = None,
    ):
        """显示错误信息 - 使用统一错误处理器."""
        error_id = error_id or f"{self.__class__.__name__}_{hash(message)}"

        # 使用统一错误处理器
        error_handler = get_error_handler()
        error_info = ErrorInfo(
            error_id=error_id,
            message=f"{title}: {message}",
            category=category,
            severity=severity,
            max_retries=max_retries,
        )
        handled = error_handler.handle_error(error_info, auto_retry=(max_retries > 0))

        # 记录到本地日志
        self._logger.error("%s: %s", title, message, extra={"log_type": "SYSTEM"})
        self.error_occurred.emit(message)

        return handled

    def show_warning(self, message: str, title: str = "警告"):
        """显示警告信息（非阻塞版本）.

        🚀 修复UI卡死问题：使用非阻塞方式显示警告
        - 记录到日志（立即生效）
        - 通过QTimer.singleShot延迟弹窗（不阻塞调用线程）
        - 或者可以选择不弹窗，只记录日志
        """
        self._logger.warning("%s: %s", title, message, extra={"log_type": "SYSTEM"})

        # 🚀 方案1：使用QTimer延迟显示（非阻塞）
        # QTimer.singleShot(0, lambda: QMessageBox.warning(self, title, message, QMessageBox.StandardButton.Ok))

        # 🚀 方案2：只记录日志，不弹窗（推荐，避免打断用户操作）
        # 如果确实需要弹窗，请手动调用 QMessageBox.warning
        pass

    def show_info(self, message: str, title: str = "信息"):
        """显示信息（非阻塞版本）.

        🚀 修复UI卡死问题：使用非阻塞方式显示信息
        - 记录到日志（立即生效）
        - 发射Signal供其他组件处理
        - 不使用模态对话框阻塞UI
        """
        self._logger.info("%s: %s", title, message)

        # 🚀 方案1：使用QTimer延迟显示（非阻塞）
        # QTimer.singleShot(0, lambda: QMessageBox.information(self, title, message, QMessageBox.StandardButton.Ok))

        # 🚀 方案2：只记录日志+发射信号，不弹窗（推荐）
        self.info_message.emit(message)

    def show_question(self, message: str, title: str = "确认") -> bool:
        """显示确认对话框."""
        self._logger.info("用户确认: %s", message)

        reply = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        return reply == QMessageBox.StandardButton.Yes

    def start_update_timer(
        self, interval: int = 1000, callback: Optional[Callable[..., Any]] = None
    ):
        """启动更新定时器."""
        if not callback:
            return

        self.stop_update_timer()

        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(callback)
        self._update_timer.start(interval)
        self._logger.debug("定时器已启动，间隔: %sms", interval)

    def stop_update_timer(self):
        """停止更新定时器."""
        if self._update_timer:
            if self._update_timer.isActive():
                self._update_timer.stop()
            self._update_timer = None

    def update_data(self, data: Dict[str, Any]):
        """更新数据 - 子类可以重写."""
        self.data_updated.emit(data)

    def resizeEvent(self, event):  # pylint: disable=invalid-name
        """窗口大小改变事件."""
        super().resizeEvent(event)
        if self._is_initialized:
            self.on_resize(event.size())

    def on_resize(self, _size):  # noqa: U101
        """窗口大小改变回调 - 子类可以重写."""
        # pylint: disable=unnecessary-pass
        pass

    def closeEvent(self, event):  # pylint: disable=invalid-name
        """窗口关闭事件."""
        # 停止定时器
        self.stop_update_timer()

        # 调用子类清理方法
        self.on_close()

        super().closeEvent(event)

    def on_close(self):
        """关闭回调 - 子类可以重写."""
        # pylint: disable=unnecessary-pass
        pass

    def set_title(self, title: str):
        """设置窗口标题."""
        self.title = title
        parent = self.parent()
        if isinstance(parent, QWidget) and hasattr(parent, "setWindowTitle"):
            parent.setWindowTitle(title)

    def get_title(self) -> str:
        """获取窗口标题."""
        return self.title

    def is_initialized(self) -> bool:
        """检查是否已初始化."""
        return self._is_initialized


# ==================== 第2部分：Dashboard组件 ====================


class MetricCard(QWidget):
    """大数字指标卡片组件.

    显示单个指标的当前值，带迷你趋势图（可选）。
    """

    def __init__(
        self,
        title: str,
        value: str = "--",
        unit: str = "",
        icon: str = "",
        color: Optional[str] = None,
        show_sparkline: bool = True,
        parent: Optional[QWidget] = None,
    ):
        """初始化指标卡片.

        Args:
            title: 指标标题
            value: 指标值
            unit: 单位
            icon: 图标（emoji或文字）
            color: 自定义颜色
            show_sparkline: 是否显示迷你趋势图
            parent: 父组件
        """
        super().__init__(parent)
        self.title = title
        self.color = color or DashboardTheme.get_metric_color(title)

        # 设置固定高度（优化版：增加高度以容纳所有内容）
        self.setFixedHeight(125)
        self.setStyleSheet(DashboardTheme.get_card_style())

        # 主布局（优化版：增加间距避免拥挤）
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # 标题行（图标 + 标题）
        title_layout = QHBoxLayout()
        title_layout.setSpacing(5)

        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 16px;")
            title_layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setStyleSheet(DashboardTheme.get_metric_label_style())
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        layout.addLayout(title_layout)

        # 数值行（大数字 + 单位）
        value_layout = QHBoxLayout()
        value_layout.setSpacing(4)

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {self.color};")
        value_layout.addWidget(self.value_label)

        if unit:
            unit_label = QLabel(unit)
            unit_label.setStyleSheet(
                f"font-size: 11px; color: {DashboardTheme.COLORS['text_dim']}; padding-top: 6px;"
            )
            unit_label.setAlignment(Qt.AlignmentFlag.AlignBottom)
            value_layout.addWidget(unit_label)

        value_layout.addStretch()
        layout.addLayout(value_layout)

        # 迷你趋势图（可选）
        if show_sparkline:
            self.sparkline = MiniSparkline(max_points=60, color=self.color, parent=self)
            layout.addWidget(self.sparkline)
        else:
            self.sparkline = None
            layout.addStretch()

    def update_value(self, value, numeric_value: Optional[float] = None):
        """更新指标值.

        Args:
            value: 显示的值（字符串或数值）
            numeric_value: 数值（用于趋势图，如value是数值则自动使用）
        """
        # 如果value是数值，自动转换为字符串并用于趋势图
        if isinstance(value, (int, float)):
            if numeric_value is None:
                numeric_value = float(value)
            self.value_label.setText(f"{value:.1f}")
        else:
            self.value_label.setText(str(value))

        if self.sparkline and numeric_value is not None:
            self.sparkline.add_point(numeric_value)


class MiniSparkline(QWidget):
    """迷你趋势图组件（无坐标轴的简单折线图）."""

    def __init__(
        self,
        max_points: int = 60,
        color: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        """初始化迷你趋势图.

        Args:
            max_points: 最大数据点数
            color: 线条颜色
            parent: 父组件
        """
        super().__init__(parent)
        self.max_points = max_points
        self.color = QColor(color or DashboardTheme.COLORS["primary"])
        self.data_points: deque = deque(maxlen=max_points)

        # 设置固定高度（优化版：减小高度为数值留出更多空间）
        self.setFixedHeight(35)
        self.setMinimumWidth(100)

    def add_point(self, value: float):
        """添加数据点.

        Args:
            value: 数据值
        """
        self.data_points.append(value)
        self.update()

    def paintEvent(self, event):
        """绘制事件."""
        if len(self.data_points) < 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 设置线条
        pen = QPen(self.color, 2)
        painter.setPen(pen)

        # 计算绘制区域
        width = self.width()
        height = self.height()
        padding = 5

        # 计算数据范围
        data_list = list(self.data_points)
        min_val = min(data_list)
        max_val = max(data_list)
        value_range = max_val - min_val if max_val > min_val else 1

        # 绘制折线
        for i in range(len(data_list) - 1):
            x1 = padding + (i / (len(data_list) - 1)) * (width - 2 * padding)
            y1 = (
                height - padding - ((data_list[i] - min_val) / value_range) * (height - 2 * padding)
            )
            x2 = padding + ((i + 1) / (len(data_list) - 1)) * (width - 2 * padding)
            y2 = (
                height
                - padding
                - ((data_list[i + 1] - min_val) / value_range) * (height - 2 * padding)
            )
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))


class GaugeWidget(QWidget):
    """半圆仪表盘组件（用于显示0-100分数）."""

    def __init__(
        self,
        max_value: int = 100,
        thresholds: Optional[Dict[str, int]] = None,
        warning: Optional[int] = None,
        critical: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        """初始化仪表盘.

        Args:
            max_value: 最大值
            thresholds: 阈值配置 {"warning": 60, "critical": 80} (优先级低于warning/critical参数)
            warning: 警告阈值（简化参数）
            critical: 严重阈值（简化参数）
            parent: 父组件
        """
        super().__init__(parent)
        self.max_value = max_value
        self.current_value = 0

        # 优先使用warning/critical参数，其次使用thresholds字典
        if warning is not None or critical is not None:
            self.thresholds = {
                "warning": warning if warning is not None else 60,
                "critical": critical if critical is not None else 80,
            }
        else:
            self.thresholds = thresholds or {"warning": 60, "critical": 80}

        # 设置固定尺寸
        self.setFixedSize(80, 50)

    def set_value(self, value: float):
        """设置当前值.

        Args:
            value: 当前值
        """
        self.current_value = max(0, min(value, self.max_value))
        self.update()

    def paintEvent(self, event):
        """绘制事件."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        center_x = width // 2
        center_y = height - 5
        radius = min(width, height * 2) - 10

        # 绘制背景弧
        pen = QPen(QColor(DashboardTheme.COLORS["border"]), 8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(
            center_x - radius // 2,
            center_y - radius // 2,
            radius,
            radius,
            0,
            180 * 16,
        )

        # 确定颜色
        if self.current_value >= self.thresholds.get("critical", 80):
            color = DashboardTheme.COLORS["error"]
        elif self.current_value >= self.thresholds.get("warning", 60):
            color = DashboardTheme.COLORS["warning"]
        else:
            color = DashboardTheme.COLORS["success"]

        # 绘制值弧
        pen = QPen(QColor(color), 8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        span_angle = int((self.current_value / self.max_value) * 180 * 16)
        painter.drawArc(
            center_x - radius // 2,
            center_y - radius // 2,
            radius,
            radius,
            0,
            span_angle,
        )

        # 绘制中心文字
        painter.setPen(QColor(DashboardTheme.COLORS["text_primary"]))
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
            f"{int(self.current_value)}",
        )


class StatusIndicator(QWidget):
    """状态指示器组件（彩色圆点 + 文字）."""

    def __init__(
        self,
        status: str = "normal",
        text: str = "",
        parent: Optional[QWidget] = None,
    ):
        """初始化状态指示器.

        Args:
            status: 状态 (normal, warning, error, critical)
            text: 状态文字
            parent: 父组件
        """
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # 状态圆点
        self.dot_label = QLabel("●")
        self.dot_label.setStyleSheet(
            f"font-size: 16px; color: {DashboardTheme.get_status_color(status)};"
        )
        layout.addWidget(self.dot_label)

        # 状态文字
        self.text_label = QLabel(text)
        self.text_label.setStyleSheet(
            f"font-size: 13px; color: {DashboardTheme.COLORS['text_primary']};"
        )
        layout.addWidget(self.text_label)

        layout.addStretch()

    def update_status(self, status: str, text: str):
        """更新状态.

        Args:
            status: 状态
            text: 状态文字
        """
        self.dot_label.setStyleSheet(
            f"font-size: 16px; color: {DashboardTheme.get_status_color(status)};"
        )
        self.text_label.setText(text)


class CompactTable(QTableWidget):
    """紧凑型表格组件（自动应用主题样式）."""

    def __init__(
        self,
        rows: int = 0,
        columns: int = 0,
        row_height: int = 26,
        parent: Optional[QWidget] = None,
    ):
        """初始化紧凑型表格.

        Args:
            rows: 初始行数
            columns: 列数
            row_height: 行高
            parent: 父组件
        """
        super().__init__(rows, columns, parent)
        self.row_height = row_height

        # 应用主题样式
        self.setStyleSheet(DashboardTheme.get_compact_table_style())

        # 设置表格属性
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(row_height)
        self.setShowGrid(True)

    def auto_color_by_threshold(
        self, row: int, col: int, value: float, thresholds: Dict[str, float]
    ):
        """根据阈值自动设置单元格颜色.

        Args:
            row: 行索引
            col: 列索引
            value: 数值
            thresholds: 阈值配置 {"warning": 60, "critical": 80}
        """
        item = self.item(row, col)
        if not item:
            return

        if value >= thresholds.get("critical", 90):
            item.setForeground(QColor(DashboardTheme.COLORS["error"]))
        elif value >= thresholds.get("warning", 75):
            item.setForeground(QColor(DashboardTheme.COLORS["warning"]))
        else:
            item.setForeground(QColor(DashboardTheme.COLORS["text_primary"]))


# ==================== 第3部分：Monaco编辑器 ====================

# Monaco兼容性标志
HAS_WEBENGINE = True


class LineNumberArea(QWidget):
    """行号显示区域."""

    def __init__(self, editor):
        """初始化行号区域."""
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        """建议大小."""
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        """绘制行号."""
        self.code_editor.line_number_area_paint_event(event)


class PythonHighlighter(QSyntaxHighlighter):
    """Python语法高亮器（Monaco暗色主题）."""

    def __init__(self, document):
        """初始化高亮器."""
        super().__init__(document)

        # Monaco暗色主题配色
        self.formats = {}

        # 关键字（蓝色）
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569CD6"))  # Monaco蓝色
        keyword_format.setFontWeight(QFont.Weight.Bold)
        self.formats["keyword"] = keyword_format

        # 字符串（橙色）
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#CE9178"))  # Monaco橙色
        self.formats["string"] = string_format

        # 注释（绿色）
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955"))  # Monaco绿色
        self.formats["comment"] = comment_format

        # 数字（浅绿）
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#B5CEA8"))  # Monaco浅绿
        self.formats["number"] = number_format

        # 函数/类（黄色）
        function_format = QTextCharFormat()
        function_format.setForeground(QColor("#DCDCAA"))  # Monaco黄色
        self.formats["function"] = function_format

        # 装饰器（黄色）
        decorator_format = QTextCharFormat()
        decorator_format.setForeground(QColor("#DCDCAA"))
        self.formats["decorator"] = decorator_format

        # Python关键字列表
        self.keywords = [
            "False",
            "None",
            "True",
            "and",
            "as",
            "assert",
            "async",
            "await",
            "break",
            "class",
            "continue",
            "def",
            "del",
            "elif",
            "else",
            "except",
            "finally",
            "for",
            "from",
            "global",
            "if",
            "import",
            "in",
            "is",
            "lambda",
            "nonlocal",
            "not",
            "or",
            "pass",
            "raise",
            "return",
            "try",
            "while",
            "with",
            "yield",
        ]

    def highlightBlock(self, text):
        """高亮代码块."""
        # 1. 高亮关键字
        for keyword in self.keywords:
            pattern = r"\b" + keyword + r"\b"
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), self.formats["keyword"])

        # 2. 高亮字符串
        # 三引号字符串
        for match in re.finditer(r'""".*?"""|\'\'\'.*?\'\'\'', text, re.DOTALL):
            self.setFormat(match.start(), match.end() - match.start(), self.formats["string"])

        # 单引号和双引号字符串
        for match in re.finditer(r'"[^"\\]*(\\.[^"\\]*)*"|\'[^\'\\]*(\\.[^\'\\]*)*\'', text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats["string"])

        # 3. 高亮注释
        for match in re.finditer(r"#[^\n]*", text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats["comment"])

        # 4. 高亮数字
        for match in re.finditer(r"\b\d+\.?\d*\b", text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats["number"])

        # 5. 高亮函数定义
        for match in re.finditer(r"\bdef\s+(\w+)", text):
            start = match.start(1)
            length = match.end(1) - start
            self.setFormat(start, length, self.formats["function"])

        # 6. 高亮类定义
        for match in re.finditer(r"\bclass\s+(\w+)", text):
            start = match.start(1)
            length = match.end(1) - start
            self.setFormat(start, length, self.formats["function"])

        # 7. 高亮装饰器
        for match in re.finditer(r"@\w+", text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats["decorator"])


class MonacoEditorWidget(QPlainTextEdit):
    """Monaco Editor增强版（Pygments语法高亮 + 行号）.

    功能：
    - Python语法高亮（Monaco暗色主题）
    - 行号显示
    - 当前行高亮
    - 自动缩进
    - Tab键支持
    - Monaco兼容API
    """

    # 信号（兼容Monaco）
    contentChanged = Signal(str)
    editorReady = Signal()

    def __init__(self, parent: Optional["QWidget"] = None):
        """初始化编辑器."""
        super().__init__(parent)

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info("🔍 [DEBUG] Monaco增强版初始化（Pygments语法高亮）")

        # Monaco兼容状态
        self._is_ready = True
        self._content = ""

        # 行号区域
        self.line_number_area = LineNumberArea(self)

        # 设置编辑器样式
        self._setup_editor_style()

        # 安装语法高亮器（优先使用原生实现）
        if _should_use_native_highlighter() and NativePythonHighlighter is not None:
            try:
                self.highlighter = NativePythonHighlighter(
                    self.document(), theme="monaco-dark"
                )
                self._using_native_highlighter = True
                self.logger.info("native_qhighlighter 已启用")
            except Exception as exc:  # noqa: BLE001
                self.logger.debug("native_qhighlighter 启用失败: %s", exc)
                self.highlighter = PythonHighlighter(self.document())
                self._using_native_highlighter = False
        else:
            self.highlighter = PythonHighlighter(self.document())
            self._using_native_highlighter = False

        # 连接信号
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.textChanged.connect(self._on_text_changed)

        # 初始化
        self.update_line_number_area_width(0)
        self.highlight_current_line()

        # 立即发送就绪信号
        self.editorReady.emit()

        self.logger.info("✓ Monaco增强版初始化完成（语法高亮已启用）")

    def _setup_editor_style(self):
        """设置编辑器样式（Monaco暗色主题）."""
        # 等宽字体
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        # Tab宽度为4个空格
        self.setTabStopDistance(40)

        # Monaco暗色主题
        self.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                padding-left: 5px;
                selection-background-color: #264f78;
                selection-color: #ffffff;
            }
        """
        )

        # 设置占位符
        self.setPlaceholderText("# -*- coding: utf-8 -*-\n# 在此编写策略代码...")

    # ==================== 行号功能 ====================

    def line_number_area_width(self):
        """计算行号区域宽度."""
        digits = len(str(max(1, self.blockCount())))
        space = 10 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def update_line_number_area_width(self, _):
        """更新行号区域宽度."""
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        """更新行号区域."""
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        """调整大小事件."""
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        """绘制行号."""
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#252526"))  # Monaco行号背景色

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#858585"))  # Monaco行号颜色
                painter.drawText(
                    0,
                    int(top),
                    self.line_number_area.width() - 5,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )

            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def highlight_current_line(self):
        """高亮当前行."""
        extra_selections = []

        if not self.isReadOnly():
            # 创建额外选择用于高亮当前行
            # 使用兼容的方式创建ExtraSelection
            try:
                # 尝试标准的PySide6方式
                selection = QTextEdit.ExtraSelection()
                selection.format = QTextCharFormat()  # type: ignore
                selection.cursor = self.textCursor()  # type: ignore
            except (AttributeError, TypeError):
                # 如果标准方式失败，使用兼容的方式
                ExtraSelection = namedtuple("ExtraSelection", ["format", "cursor"])
                selection = ExtraSelection(format=QTextCharFormat(), cursor=self.textCursor())

            # Monaco当前行颜色
            line_color = QColor("#2a2d2e")
            selection.format.setBackground(line_color)  # type: ignore
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)  # type: ignore
            selection.cursor.clearSelection()  # type: ignore

        self.setExtraSelections(extra_selections)

    # ==================== 自动缩进 ====================

    def keyPressEvent(self, event):
        """按键事件（支持自动缩进）."""
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            # 获取当前行的缩进
            cursor = self.textCursor()
            cursor.select(cursor.SelectionType.LineUnderCursor)
            line = cursor.selectedText()

            # 计算缩进级别
            indent = len(line) - len(line.lstrip())

            # 如果行末是冒号，增加缩进
            if line.rstrip().endswith(":"):
                indent += 4

            # 插入换行和缩进
            super().keyPressEvent(event)
            self.insertPlainText(" " * indent)
        else:
            super().keyPressEvent(event)

    # ==================== Monaco兼容API ====================

    def _on_text_changed(self):
        """文本变化事件."""
        self._content = self.toPlainText()
        self.contentChanged.emit(self._content)

    def setText(self, text: str):
        """设置文本（Monaco API）."""
        self.setPlainText(text)
        self._content = text

    def text(self) -> str:
        """获取文本（Monaco API）."""
        return self.toPlainText()

    def getText(self, callback):
        """异步获取文本（Monaco API）."""
        callback(self.toPlainText())

    def isReady(self) -> bool:
        """检查是否就绪（Monaco API）."""
        return self._is_ready

    def clear(self):
        """清空内容."""
        self.setPlainText("")

    # ==================== 断点管理（兼容API）====================

    def setBreakpoint(self, line_number: int):
        """设置断点（占位实现）."""
        return

    def getBreakpoints(self, callback):
        """获取断点（占位实现）."""
        callback([])

    def clearBreakpoints(self):
        """清除断点（占位实现）."""
        return

    # ==================== 只读模式 ====================

    def setReadOnly(self, readonly: bool):
        """设置只读状态（带样式变化）.

        Args:
            readonly: 是否只读
        """
        super().setReadOnly(readonly)

        if readonly:
            # 只读时使用更明显的灰色背景和边框
            self.setStyleSheet(
                """
                QPlainTextEdit {
                    background-color: #2a2a2a;
                    color: #d4d4d4;
                    border: 1px solid #555555;
                    padding-left: 5px;
                    selection-background-color: #264f78;
                    selection-color: #ffffff;
                }
            """
            )
            self.logger.info("编辑器设置为只读模式")
        else:
            # 恢复正常编辑模式样式
            self.setStyleSheet(
                """
                QPlainTextEdit {
                    background-color: #1e1e1e;
                    color: #d4d4d4;
                    border: none;
                    padding-left: 5px;
                    selection-background-color: #264f78;
                    selection-color: #ffffff;
                }
            """
            )
            self.logger.info("编辑器设置为编辑模式")


# ==================== 第3部分：带阈值的热力图组件 ====================


class ThresholdHeatmap(QWidget):
    """带阈值标记的热力图组件（深色极简风格）.

    显示单个指标的当前值，并在进度条上显示警告和严重阈值线。
    参考进程监控界面的整体设备监控组件设计。
    """

    def __init__(
        self,
        title: str,
        unit: str = "%",
        warning_threshold: float = 80.0,
        critical_threshold: float = 90.0,
        max_value: float = 100.0,
        parent: Optional[QWidget] = None,
    ):
        """初始化带阈值的热力图组件.

        Args:
            title: 指标标题
            unit: 单位
            warning_threshold: 警告阈值
            critical_threshold: 严重阈值
            max_value: 最大值（用于计算百分比）
            parent: 父组件
        """
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.max_value = max_value
        self.current_value = 0.0

        # 设置固定高度和最小宽度
        self.setMinimumHeight(60)
        self.setMaximumHeight(80)
        self.setMinimumWidth(200)

        # 深色背景样式
        self.setStyleSheet(
            """
            QWidget {
                background-color: #1E1E1E;
                border: 1px solid #333333;
                border-radius: 4px;
            }
        """
        )

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        # 标题和当前值（水平布局）
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 12px; color: #AAA; border: none;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.value_label = QLabel(f"0.0{unit}")
        self.value_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #FFF; border: none;"
        )
        header_layout.addWidget(self.value_label)

        layout.addLayout(header_layout)

        # 进度条（热力图）
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimumHeight(30)

        # 渐变色样式（绿→黄→红）
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                border: 2px solid #444;
                border-radius: 5px;
                background-color: #1E1E1E;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00FF00,
                    stop:0.5 #FFFF00,
                    stop:1 #FF0000
                );
            }
        """
        )

        layout.addWidget(self.progress_bar)

    def update_value(self, value: float):
        """更新当前值.

        Args:
            value: 当前值
        """
        self.current_value = value

        # 计算百分比
        percentage = min((value / self.max_value) * 100, 100) if self.max_value > 0 else 0

        # 更新显示
        self.value_label.setText(f"{value:.1f}{self.unit}")
        self.progress_bar.setValue(int(percentage))

        # 触发重绘（绘制阈值线）
        self.update()

    def paintEvent(self, event):
        """绘制事件（绘制阈值标记线）."""
        super().paintEvent(event)

        if self.max_value <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 获取进度条的几何位置
        bar_rect = self.progress_bar.geometry()

        # 计算阈值线的X坐标
        warning_percent = (self.warning_threshold / self.max_value) * 100
        critical_percent = (self.critical_threshold / self.max_value) * 100

        warning_x = bar_rect.x() + int((warning_percent / 100.0) * bar_rect.width())
        critical_x = bar_rect.x() + int((critical_percent / 100.0) * bar_rect.width())

        # 绘制警告阈值线（黄色）
        if 0 <= warning_percent <= 100:
            painter.setPen(QPen(QColor("#FFFF00"), 3))
            painter.drawLine(warning_x, bar_rect.y(), warning_x, bar_rect.y() + bar_rect.height())

        # 绘制严重阈值线（红色）
        if 0 <= critical_percent <= 100:
            painter.setPen(QPen(QColor("#FF0000"), 3))
            painter.drawLine(critical_x, bar_rect.y(), critical_x, bar_rect.y() + bar_rect.height())


# ==================== 第4部分：垂直热力图组件 ====================


class _HeatmapCanvas(QWidget):
    """热力图画布（内部类，用于绘制垂直热力条）."""

    def __init__(self, parent: "VerticalThresholdHeatmap"):
        """初始化画布.

        Args:
            parent: 父级VerticalThresholdHeatmap组件
        """
        super().__init__(parent)
        self.parent_heatmap = parent
        self.setStyleSheet("background-color: #2A2A2A; border: none;")
        self.setMinimumHeight(150)
        # 移除最大高度限制，让热力图自动伸展

    def paintEvent(self, event):
        """绘制垂直热力条."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return

        metrics_config = self.parent_heatmap.metrics_config
        metric_values = self.parent_heatmap.metric_values

        num_metrics = len(metrics_config)
        if num_metrics == 0:
            return

        # 计算每个热力条的宽度和间距（均匀分配）
        bar_spacing = 8
        total_spacing = bar_spacing * (num_metrics + 1)
        available_width = rect.width() - total_spacing
        bar_width = available_width // num_metrics  # 均匀分配宽度，无最小限制

        # 绘制每个指标的热力条
        for i, metric in enumerate(metrics_config):
            metric_key = metric["key"]
            current_value = metric_values.get(metric_key, 0.0)
            max_value = metric["max_value"]
            warning_threshold = metric.get("warning", 0)
            critical_threshold = metric.get("critical", 0)

            # 计算热力条位置（减少上下边距，让热力图充满空间）
            x_pos = bar_spacing + i * (bar_width + bar_spacing)
            bar_rect = QRect(x_pos, 5, bar_width, rect.height() - 10)

            # 绘制背景
            painter.setBrush(QColor("#1E1E1E"))
            painter.setPen(QPen(QColor("#555"), 1))
            painter.drawRoundedRect(bar_rect, 3, 3)

            # 计算填充高度（从下到上）
            fill_percent = min((current_value / max_value) * 100, 100) if max_value > 0 else 0
            fill_height = int((fill_percent / 100.0) * bar_rect.height())

            if fill_height > 0:
                # 创建垂直渐变（绿→黄→红，从下到上）
                from PySide6.QtGui import QLinearGradient

                gradient = QLinearGradient(
                    bar_rect.x(),
                    bar_rect.y() + bar_rect.height(),  # 底部
                    bar_rect.x(),
                    bar_rect.y(),  # 顶部
                )
                gradient.setColorAt(0.0, QColor("#00FF00"))  # 底部：绿色
                gradient.setColorAt(0.5, QColor("#FFFF00"))  # 中间：黄色
                gradient.setColorAt(1.0, QColor("#FF0000"))  # 顶部：红色

                # 绘制填充区域（从底部向上）
                fill_rect = QRect(
                    bar_rect.x(),
                    bar_rect.y() + bar_rect.height() - fill_height,
                    bar_rect.width(),
                    fill_height,
                )
                painter.setBrush(gradient)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(fill_rect, 3, 3)

            # 绘制阈值线（水平线）
            if warning_threshold > 0:
                warning_percent = (warning_threshold / max_value) * 100
                warning_y = (
                    bar_rect.y()
                    + bar_rect.height()
                    - int((warning_percent / 100.0) * bar_rect.height())
                )
                painter.setPen(QPen(QColor("#FFAA00"), 2, Qt.PenStyle.DashLine))
                painter.drawLine(
                    bar_rect.x(), warning_y, bar_rect.x() + bar_rect.width(), warning_y
                )

            if critical_threshold > 0:
                critical_percent = (critical_threshold / max_value) * 100
                critical_y = (
                    bar_rect.y()
                    + bar_rect.height()
                    - int((critical_percent / 100.0) * bar_rect.height())
                )
                painter.setPen(QPen(QColor("#FF0000"), 2, Qt.PenStyle.DashLine))
                painter.drawLine(
                    bar_rect.x(), critical_y, bar_rect.x() + bar_rect.width(), critical_y
                )


class VerticalThresholdHeatmap(QWidget):
    """垂直热力图组件（支持多指标并排显示，热力条从下到上填充）.

    用于系统状态监控的4个监控卡片，每个卡片显示多个相关指标。
    """

    def __init__(
        self,
        title: str,
        metrics: List[Dict[str, Any]],
        parent: Optional[QWidget] = None,
    ):
        """初始化垂直热力图组件.

        Args:
            title: 卡片标题
            metrics: 指标配置列表，每个指标包含:
                {
                    "key": str,  # 指标唯一标识
                    "label": str,  # 显示名称
                    "unit": str,  # 单位
                    "warning": float,  # 警告阈值
                    "critical": float,  # 严重阈值
                    "max_value": float,  # 最大值
                }
            parent: 父组件
        """
        super().__init__(parent)
        self.title = title
        self.metrics_config = metrics
        self.metric_values = {m["key"]: 0.0 for m in metrics}

        # 设置最小尺寸
        self.setMinimumHeight(200)
        self.setMinimumWidth(250)

        # 深色背景样式（增强边框）
        self.setStyleSheet(
            """
            QWidget {
                background-color: #1E1E1E;
                border: 2px solid #444444;
                border-radius: 6px;
            }
            """
        )

        # 主布局 - 紧凑布局，减小边距和间距
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 6, 10, 6)
        self.main_layout.setSpacing(4)

        # 标题 - 减小字体
        title_label = QLabel(title)
        title_label.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #E0E0E0; border: none;"
        )
        self.main_layout.addWidget(title_label)

        # 热力条绘制区域（使用专用画布）
        self.heatmap_area = _HeatmapCanvas(self)
        self.main_layout.addWidget(self.heatmap_area, 1)  # stretch=1，占据剩余空间

        # 指标数值显示区域 - 紧凑布局
        self.values_layout = QHBoxLayout()
        self.values_layout.setSpacing(5)
        self.value_labels = {}

        for metric in metrics:
            value_container = QWidget()
            value_container.setStyleSheet("border: none;")
            value_layout = QVBoxLayout(value_container)
            value_layout.setContentsMargins(0, 0, 0, 0)
            value_layout.setSpacing(1)

            # 指标名称 - 减小字体
            name_label = QLabel(metric["label"])
            name_label.setStyleSheet("font-size: 10px; color: #AAA; border: none;")
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value_layout.addWidget(name_label)

            # 指标数值 - 减小字体
            value_label = QLabel(f"0.0{metric['unit']}")
            value_label.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #FFF; border: none;"
            )
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value_layout.addWidget(value_label)

            self.value_labels[metric["key"]] = value_label
            self.values_layout.addWidget(value_container)

        self.main_layout.addLayout(self.values_layout)

    def update_metric(self, metric_key: str, value: float):
        """更新指标值.

        Args:
            metric_key: 指标key
            value: 当前值
        """
        if metric_key in self.metric_values:
            self.metric_values[metric_key] = value

            # 更新数值标签
            if metric_key in self.value_labels:
                metric_config = next(
                    (m for m in self.metrics_config if m["key"] == metric_key), None
                )
                if metric_config:
                    unit = metric_config["unit"]
                    self.value_labels[metric_key].setText(f"{value:.1f}{unit}")

            # 触发重绘
            self.heatmap_area.update()

    def update_metrics(self, values: Dict[str, float]):
        """批量更新多个指标.

        Args:
            values: 指标key到值的映射
        """
        for key, value in values.items():
            if key in self.metric_values:
                self.metric_values[key] = value

                # 更新数值标签
                if key in self.value_labels:
                    metric_config = next((m for m in self.metrics_config if m["key"] == key), None)
                    if metric_config:
                        unit = metric_config["unit"]
                        self.value_labels[key].setText(f"{value:.1f}{unit}")

        # 触发重绘
        self.heatmap_area.update()
