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
import re
from collections import deque, namedtuple
from enum import Enum
from typing import Any, Callable, Dict, Optional

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
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.core.utils import ErrorInfo, get_error_handler
from ui.components.theme_system import DashboardTheme


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
    """错误严重程度枚举."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


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
        # 使用私有属性避免与LoggerMixin的logger属性冲突
        self._logger = logging.getLogger(self.__class__.__name__)
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
        self._logger.error("%s: %s", title, message)
        self.error_occurred.emit(message)

        return handled

    def show_warning(self, message: str, title: str = "警告"):
        """显示警告信息."""
        self._logger.warning("%s: %s", title, message)

        QMessageBox.warning(self, title, message, QMessageBox.StandardButton.Ok)

    def show_info(self, message: str, title: str = "信息"):
        """显示信息."""
        self._logger.info("%s: %s", title, message)

        # 显示信息弹窗
        QMessageBox.information(self, title, message, QMessageBox.StandardButton.Ok)

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

        # 设置固定高度（紧凑版）
        self.setFixedHeight(105)
        self.setStyleSheet(DashboardTheme.get_card_style())

        # 主布局（紧凑版）
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

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
        self.value_label.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {self.color};")
        value_layout.addWidget(self.value_label)

        if unit:
            unit_label = QLabel(unit)
            unit_label.setStyleSheet(
                f"font-size: 13px; color: {DashboardTheme.COLORS['text_dim']}; padding-top: 8px;"
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

        # 设置固定高度
        self.setFixedHeight(40)
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

        # 安装语法高亮器
        self.highlighter = PythonHighlighter(self.document())

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
                ExtraSelection = namedtuple('ExtraSelection', ['format', 'cursor'])
                selection = ExtraSelection(
                    format=QTextCharFormat(),
                    cursor=self.textCursor()
                )

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
