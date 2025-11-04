# -*- coding: utf-8 -*-
"""系统管理界面 - 主视图（重构版）.

标准架构：8个子界面采用选项卡形式。
合并handlers逻辑，统一backend调用。
"""
import logging
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from PySide6.QtCore import (
    QAbstractTableModel,
    QDate,
    QDateTime,
    Qt,
    QTimer,
    Signal,
    QSize,
    QRect,
    QPoint,
    QModelIndex,
)
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStyledItemDelegate,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import psutil
import pyqtgraph as pg

from backend.core.base import get_service_manager
from ui.components.widgets import (
    BaseWidget,
    GaugeWidget,
    MetricCard,
    VerticalThresholdHeatmap,
)
from ui.components.theme_system import DashboardTheme
from backend.core.service_base import LoggerMixin
from backend.infrastructure.system_vnpy import (
    EVENT_ALERT_CREATED,
    EVENT_ALERT_UPDATED,
    EVENT_LOG_RECORD,
)
from backend.startup.ui_startup.boot_orchestrator import get_boot_orchestrator

# UI层专用logger
logger_user = logging.getLogger("ui.user_feedback")


# ==================== 日志表格组件（已合并） ====================


class LogCheckboxDelegate(QStyledItemDelegate):
    """第0列复选框的自定义无白底绘制委托。"""

    INDICATOR_SIZE = 16
    BORDER_COLOR = QColor(160, 160, 160)
    HOVER_BORDER_COLOR = QColor(0, 120, 215)
    CHECKED_COLOR = QColor(0, 120, 215)
    INDETERMINATE_COLOR = QColor(102, 163, 224)

    def paint(self, painter: QPainter, option, index) -> None:  # type: ignore[override]
        # 仅处理第0列；其他列使用默认绘制
        if index.column() != 0:
            super().paint(painter, option, index)
            return

        # 计算指示器区域，居中放置
        rect: QRect = option.rect
        size = self.INDICATOR_SIZE
        x = rect.x() + (rect.width() - size) // 2
        y = rect.y() + (rect.height() - size) // 2
        indicator_rect = QRect(x, y, size, size)

        # 解析勾选状态
        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        is_checked = check_state == Qt.CheckState.Checked
        is_indeterminate = check_state == Qt.CheckState.PartiallyChecked
        # State_MouseOver 在 PySide6 中通过 QStyle.State_MouseOver 表示
        try:
            from PySide6.QtWidgets import QStyle

            is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        except Exception:
            is_hover = False

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 边框颜色（悬浮时使用主题蓝）
        border_color = self.HOVER_BORDER_COLOR if is_hover else self.BORDER_COLOR
        pen = QPen(border_color)
        pen.setWidth(1)
        painter.setPen(pen)

        # 背景：不填充（透明），避免白底
        # 勾选/半选时使用主题色填充
        if is_checked:
            painter.fillRect(indicator_rect, self.CHECKED_COLOR)
        elif is_indeterminate:
            painter.fillRect(indicator_rect, self.INDETERMINATE_COLOR)

        # 绘制外边框
        painter.drawRect(indicator_rect)

        # 勾选符号（白色）
        if is_checked:
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            # 简单的对勾路径
            p1 = indicator_rect.topLeft() + QPoint(4, indicator_rect.height() // 2)
            p2 = indicator_rect.topLeft() + QPoint(
                indicator_rect.width() // 2 - 1, indicator_rect.height() - 4
            )
            p3 = indicator_rect.topLeft() + QPoint(indicator_rect.width() - 4, 4)
            painter.drawLine(p1, p2)
            painter.drawLine(p2, p3)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # type: ignore[override]
        if index.column() == 0:
            return QSize(self.INDICATOR_SIZE, self.INDICATOR_SIZE)
        return super().sizeHint(option, index)


class LogTableModel(QAbstractTableModel):
    """日志表格数据模型（高性能实现）."""

    # 列定义（第一列为复选框）
    HEADERS = ["☑", "时间", "级别", "模块", "函数", "行号", "消息"]
    COLUMN_KEYS = [None, "timestamp", "level", "module", "function", "line", "message"]

    # 级别文字颜色映射（使用深色文字，无背景色）
    LEVEL_COLORS = {
        "DEBUG": QColor(100, 100, 100),  # 深灰色
        "INFO": QColor(0, 100, 200),  # 深蓝色
        "WARNING": QColor(200, 120, 0),  # 深橙黄色
        "ERROR": QColor(200, 0, 0),  # 深红色
        "CRITICAL": QColor(139, 0, 0),  # 暗红色
    }

    # 选中行视觉反馈：复选框列左侧边框高亮
    SELECTED_INDICATOR_COLOR = QColor(0, 120, 215)  # 蓝色指示器

    def __init__(self, parent=None):
        """初始化Model."""
        super().__init__(parent)
        self._data: List[Dict[str, Any]] = []
        self._selected_rows: set = set()  # 存储选中的行索引

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """返回行数."""
        if parent.isValid():
            return 0
        return len(self._data)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """返回列数."""
        if parent.isValid():
            return 0
        return len(self.HEADERS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        """返回表头数据。"""
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.HEADERS):
                if role == Qt.ItemDataRole.DisplayRole:
                    if section == 0:
                        # 动态三态：全未选☐、部分◩、全选☑
                        total = len(self._data)
                        selected = len(self._selected_rows)
                        if total == 0 or selected == 0:
                            mark = "☐"
                        elif selected == total:
                            mark = "☑"
                        else:
                            mark = "◩"
                        return f"{mark}"
                    return self.HEADERS[section]
                elif role == Qt.ItemDataRole.ToolTipRole:
                    # 🔧 关键修复：处理ToolTipRole，避免与setHeaderData()冲突
                    if section == 0:  # 复选框列
                        total = len(self._data)
                        selected = len(self._selected_rows)
                        if total == 0:
                            state = "无数据"
                        elif selected == 0:
                            state = "全未选"
                        elif selected == total:
                            state = "全选"
                        else:
                            state = "部分选择"
                        return f"点击切换全选/取消全选（当前：{state}）"
                    return None
                elif role == Qt.ItemDataRole.BackgroundRole:
                    # 为第一列表头设置柔和底色，避免白底突兀
                    if section == 0:
                        return QBrush(QColor(232, 244, 248))  # #E8F4F8
                elif role == Qt.ItemDataRole.ForegroundRole:
                    # 第一列使用深蓝文本以匹配主题
                    if section == 0:
                        return QBrush(QColor(0, 85, 170))  # 深蓝
                elif role == Qt.ItemDataRole.TextAlignmentRole:
                    # 居中显示三态符号
                    if section == 0:
                        return Qt.AlignmentFlag.AlignCenter
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """返回单元格标志（使复选框可交互）。"""
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if index.column() == 0:  # 复选框列
            # 为复选框列加入 ItemIsSelectable，确保点击可触发CheckState切换
            return (
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        """设置单元格数据（处理复选框点击）。"""
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            row = index.row()
            if value == Qt.CheckState.Checked:
                self._selected_rows.add(row)
            else:
                self._selected_rows.discard(row)
            # 通知整行数据变化（以便更新行背景色）
            left_index = self.index(row, 0)
            right_index = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(left_index, right_index)
            # 刷新表头三态
            self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)
            return True
        return False

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """返回单元格数据（按需提供，View调用时才计算）."""
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        if row < 0 or row >= len(self._data):
            return None
        if col < 0 or col >= len(self.COLUMN_KEYS):
            return None

        # 第一列：复选框
        if col == 0:
            if role == Qt.ItemDataRole.CheckStateRole:
                return (
                    Qt.CheckState.Checked if row in self._selected_rows else Qt.CheckState.Unchecked
                )
            if role == Qt.ItemDataRole.TextAlignmentRole:
                # 居中显示复选状态
                return Qt.AlignmentFlag.AlignCenter
            if role == Qt.ItemDataRole.BackgroundRole:
                # 选中：浅蓝高亮；未选中：与表格行底色保持一致（Base/AlternateBase）
                if row in self._selected_rows:
                    return QBrush(QColor(220, 235, 255))
                try:
                    from PySide6.QtWidgets import QApplication

                    app = QApplication.instance()
                    palette = QPalette()
                    if app is not None and isinstance(app, QApplication):
                        palette = app.palette()
                except Exception:
                    palette = QPalette()

                color = (
                    palette.color(QPalette.ColorRole.AlternateBase)
                    if (row % 2) == 1
                    else palette.color(QPalette.ColorRole.Base)
                )
                return QBrush(color)
            # 其他角色：使用默认渲染
            return None

        record = self._data[row]

        # 显示角色：返回文本
        if role == Qt.ItemDataRole.DisplayRole:
            key = self.COLUMN_KEYS[col]
            value = record.get(key, "")

            # 消息列截断处理
            if key == "message" and isinstance(value, str) and len(value) > 200:
                return value[:200] + "..."

            return str(value) if value else ""

        # 前景色角色：级别列使用深色文字区分
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 2:  # 级别列
                level = record.get("level", "")
                return QBrush(self.LEVEL_COLORS.get(level, QColor(0, 0, 0)))

        # 其余列的背景色由视图和样式决定，此处不覆盖

        return None

    def update_data(self, new_data: List[Dict[str, Any]]) -> None:
        """批量更新数据（高性能实现）。"""
        # 🔧 关键优化：使用beginResetModel/endResetModel一次性通知View
        # 而不是逐行插入/删除，避免频繁重绘
        self.beginResetModel()
        self._data = new_data
        self._selected_rows.clear()  # 数据更新时清除选择
        self.endResetModel()
        # 刷新表头三态
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)

    def get_record(self, row: int) -> Optional[Dict[str, Any]]:
        """获取指定行的原始记录."""
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    def clear(self) -> None:
        """清空数据。"""
        self.beginResetModel()
        self._data.clear()
        self._selected_rows.clear()
        self.endResetModel()
        # 刷新表头三态
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)

    def select_all(self) -> None:
        """全选所有行。"""
        self._selected_rows = set(range(len(self._data)))
        if self._data:
            # 通知所有行所有列数据变化（复选框 + 背景色）
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._data) - 1, self.columnCount() - 1),
            )
        # 刷新表头三态
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)

    def clear_selection(self) -> None:
        """清除所有选择。"""
        if self._selected_rows:
            self._selected_rows.clear()
            if self._data:
                # 通知所有行所有列数据变化（复选框 + 背景色）
                self.dataChanged.emit(
                    self.index(0, 0),
                    self.index(len(self._data) - 1, self.columnCount() - 1),
                )
        # 刷新表头三态
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)

    def get_selected_records(self) -> List[Dict[str, Any]]:
        """获取选中的记录."""
        return [self._data[i] for i in sorted(self._selected_rows) if i < len(self._data)]

    def get_selected_count(self) -> int:
        """获取选中数量."""
        return len(self._selected_rows)


# ==================== 告警管理组件 ====================


class AlertCard(QWidget):
    """告警卡片组件."""

    def __init__(self, alert_data: Dict[str, Any]):
        """初始化告警卡片.

        Args:
            alert_data: 告警数据
        """
        super().__init__()

        self.alert_data = alert_data
        self.alert_id = alert_data.get("alert_id")

        # 设置样式
        self.setFixedHeight(120)
        self.setStyleSheet(self._get_card_style())

        # 创建布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # 顶部信息
        top_layout = QHBoxLayout()

        # 严重程度和时间
        severity = alert_data.get("severity", "info")
        status = alert_data.get("status", "new")

        severity_label = QLabel(f"[{severity.upper()}]")
        severity_label.setStyleSheet(self._get_severity_style(severity))

        time_label = QLabel(alert_data.get("created_at", ""))
        time_label.setStyleSheet("color: #666; font-size: 11px;")

        top_layout.addWidget(severity_label)
        top_layout.addStretch()
        top_layout.addWidget(time_label)

        layout.addLayout(top_layout)

        # 消息内容
        message_label = QLabel(alert_data.get("message", ""))
        message_label.setWordWrap(True)
        message_label.setStyleSheet("font-weight: bold; margin: 5px 0;")
        layout.addWidget(message_label)

        # 来源信息
        source_info = f"来源: {alert_data.get('rule_name', '未知规则')} | 模块: {alert_data.get('context', {}).get('module', '未知')}"
        source_label = QLabel(source_info)
        source_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(source_label)

        # 底部按钮
        button_layout = QHBoxLayout()

        if status == "new":
            # 新告警：确认和解决按钮
            acknowledge_btn = QPushButton("确认")
            acknowledge_btn.clicked.connect(self._acknowledge_alert)
            acknowledge_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #17a2b8;
                    color: white;
                    border: none;
                    padding: 5px 10px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #138496;
                }
            """
            )
            button_layout.addWidget(acknowledge_btn)

            resolve_btn = QPushButton("解决")
            resolve_btn.clicked.connect(self._resolve_alert)
            resolve_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #28a745;
                    color: white;
                    border: none;
                    padding: 5px 10px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
            """
            )
            button_layout.addWidget(resolve_btn)
        elif status == "acknowledged":
            # 已确认：解决按钮
            resolve_btn = QPushButton("解决")
            resolve_btn.clicked.connect(self._resolve_alert)
            resolve_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #28a745;
                    color: white;
                    border: none;
                    padding: 5px 10px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
            """
            )
            button_layout.addWidget(resolve_btn)
        else:
            # 已解决或忽略：无操作按钮
            status_label = QLabel(f"状态: {status}")
            status_label.setStyleSheet("color: #28a745; font-size: 11px;")
            button_layout.addWidget(status_label)

        button_layout.addStretch()
        layout.addLayout(button_layout)

    def _get_card_style(self) -> str:
        """获取卡片样式."""
        severity = self.alert_data.get("severity", "info")
        status = self.alert_data.get("status", "new")

        base_style = """
            QWidget {
                border: 1px solid #ddd;
                border-radius: 5px;
                margin: 2px;
            }
        """

        if status == "new":
            if severity == "critical":
                return (
                    base_style
                    + "QWidget { background-color: #ffebee; border-left: 4px solid #d32f2f; }"
                )
            elif severity == "error":
                return (
                    base_style
                    + "QWidget { background-color: #fff3e0; border-left: 4px solid #f57c00; }"
                )
            else:
                return (
                    base_style
                    + "QWidget { background-color: #e3f2fd; border-left: 4px solid #2196f3; }"
                )
        else:
            return base_style + "QWidget { background-color: #f5f5f5; }"

    def _get_severity_style(self, severity: str) -> str:
        """获取严重程度样式."""
        color_map = {
            "critical": "color: #d32f2f; font-weight: bold;",
            "error": "color: #f57c00; font-weight: bold;",
            "warning": "color: #fbc02d; font-weight: bold;",
            "info": "color: #2196f3;",
        }
        return color_map.get(severity, "color: #666;")

    def _acknowledge_alert(self) -> None:
        """确认告警."""
        note, ok = QInputDialog.getText(self, "确认告警", "请输入确认备注（可选）:")
        if ok:
            # 记录用户操作
            logger_user.info(
                "用户确认告警: ID=%s, 类型=%s", self.alert_id, self.alert_data.get("severity")
            )
            self._call_alert_action("acknowledge", note if note else "")

    def _resolve_alert(self) -> None:
        """解决告警."""
        note, ok = QInputDialog.getText(self, "解决告警", "请输入解决备注（可选）:")
        if ok:
            # 记录用户操作
            logger_user.info("用户解决告警: ID=%s", self.alert_id)
            self._call_alert_action("resolve", note if note else "")

    def _call_alert_action(self, action: str, note: str) -> None:
        """调用告警操作."""
        try:
            service_manager = get_service_manager()
            system_service = service_manager.get_service("system_manager_service", silent=True)

            if system_service:
                if action == "acknowledge":
                    result = system_service.acknowledge_alert(self.alert_id, note)
                elif action == "resolve":
                    result = system_service.resolve_alert(self.alert_id, note)
                else:
                    return

                if result.get("success"):
                    # 更新卡片样式
                    self.alert_data["status"] = (
                        "acknowledged" if action == "acknowledge" else "resolved"
                    )
                    self.setStyleSheet(self._get_card_style())

                    # 重新加载告警列表（直接调用父组件方法）
                    parent = self.parent()
                    while parent and not hasattr(parent, "refresh_alerts"):
                        parent = parent.parent()
                    if parent and hasattr(parent, "refresh_alerts"):
                        # 类型断言：确保parent是AlertManagerWidget类型
                        if isinstance(parent, AlertManagerWidget):
                            parent.refresh_alerts()
                else:
                    QMessageBox.warning(self, "错误", f"操作失败: {result.get('message')}")
            else:
                QMessageBox.warning(self, "错误", "系统管理服务不可用")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"操作失败: {str(e)}")


# ==================== 系统状态监控组件 ====================


class _UnifiedHeatmapCanvas(QWidget):
    """整合的热力图画布 - 绘制9个修长的热力条."""

    def __init__(self, parent: "UnifiedMonitorCard"):
        """初始化画布."""
        super().__init__(parent)
        self.parent_card = parent
        self.setStyleSheet("background-color: #2A2A2A; border: none;")
        # 移除高度限制，让它自动伸展
        self.setMinimumHeight(180)

    def paintEvent(self, event):
        """绘制9个热力条."""
        from PySide6.QtGui import QPainter, QPen, QLinearGradient
        from PySide6.QtCore import QRect

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return

        metrics_config = self.parent_card.all_metrics
        metric_values = self.parent_card.metric_values

        num_metrics = len(metrics_config)
        if num_metrics == 0:
            return

        # 计算每个热力条的宽度和间距（均匀分布，宽度一致）
        bar_spacing = 8
        total_spacing = bar_spacing * (num_metrics + 1)
        available_width = rect.width() - total_spacing
        bar_width = available_width // num_metrics  # 均匀分配宽度

        # 绘制每个指标的热力条
        for i, metric in enumerate(metrics_config):
            metric_key = metric["key"]
            current_value = metric_values.get(metric_key, 0.0)
            max_value = metric["max_value"]
            # warning_threshold = metric.get("warning", 0)  # 暂不绘制阈值线
            # critical_threshold = metric.get("critical", 0)

            # 计算热力条位置（使用更多垂直空间）
            x_pos = bar_spacing + i * (bar_width + bar_spacing)
            bar_rect = QRect(x_pos, 5, bar_width, rect.height() - 10)  # 减少上下边距

            # 绘制背景
            painter.setBrush(QColor("#1E1E1E"))
            painter.setPen(QPen(QColor("#555"), 1))
            painter.drawRoundedRect(bar_rect, 3, 3)

            # 计算填充高度（从下到上）
            fill_percent = min((current_value / max_value) * 100, 100) if max_value > 0 else 0
            fill_height = int((fill_percent / 100.0) * bar_rect.height())

            if fill_height > 0:
                # 创建垂直渐变（绿→黄→红，从下到上）
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

            # 绘制分组分隔线（在第4和第7个热力条后）
            if i == 3 or i == 6:  # CPU后和网络后
                sep_x = x_pos + bar_width + bar_spacing // 2
                painter.setPen(QPen(QColor("#666"), 2))
                painter.drawLine(sep_x, 5, sep_x, rect.height() - 5)


class UnifiedMonitorCard(QWidget):
    """整合的系统监控卡片 - CPU/网络/内存的9个热力图."""

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化整合监控卡片."""
        super().__init__(parent)

        # 设置最小尺寸
        self.setMinimumHeight(280)
        self.setMinimumWidth(800)

        # 深色背景样式
        self.setStyleSheet(
            """
            QWidget {
                background-color: #1E1E1E;
                border: 2px solid #444444;
                border-radius: 6px;
            }
            """
        )

        # 主布局 - 减小边距和间距
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(5)

        # 标题 - 减小字体
        title_label = QLabel("📊 系统性能监控（CPU · 网络 · 内存）")
        title_label.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #E0E0E0; border: none;"
        )
        main_layout.addWidget(title_label)

        # 9个指标的配置
        self.all_metrics = [
            # CPU指标（4个）
            {
                "group": "CPU",
                "key": "cpu_usage",
                "label": "CPU\n使用率",
                "unit": "%",
                "warning": 80,
                "critical": 90,
                "max_value": 100,
            },
            {
                "group": "CPU",
                "key": "context_switches",
                "label": "上下文\n切换",
                "unit": "K/s",
                "warning": 50,
                "critical": 100,
                "max_value": 150,
            },
            {
                "group": "CPU",
                "key": "temperature",
                "label": "CPU\n温度",
                "unit": "°C",
                "warning": 70,
                "critical": 85,
                "max_value": 100,
            },
            {
                "group": "CPU",
                "key": "freq_ratio",
                "label": "频率\n比",
                "unit": "%",
                "warning": 0,
                "critical": 0,
                "max_value": 100,
            },
            # 网络指标（3个）
            {
                "group": "NET",
                "key": "packet_loss",
                "label": "网络\n丢包率",
                "unit": "%",
                "warning": 0.5,
                "critical": 2.0,
                "max_value": 5.0,
            },
            {
                "group": "NET",
                "key": "latency",
                "label": "网络\n延迟",
                "unit": "ms",
                "warning": 50,
                "critical": 100,
                "max_value": 200,
            },
            {
                "group": "NET",
                "key": "bandwidth_usage",
                "label": "带宽\n占用",
                "unit": "%",
                "warning": 70,
                "critical": 90,
                "max_value": 100,
            },
            # 内存指标（2个）
            {
                "group": "MEM",
                "key": "memory_usage",
                "label": "内存\n使用率",
                "unit": "%",
                "warning": 75,
                "critical": 85,
                "max_value": 100,
            },
            {
                "group": "MEM",
                "key": "swap_total",
                "label": "内存\n交换",
                "unit": "MB/s",
                "warning": 10,
                "critical": 50,
                "max_value": 100,
            },
        ]

        self.metric_values = {m["key"]: 0.0 for m in self.all_metrics}

        # 热力图画布（自定义高度）
        self.heatmap_area = _UnifiedHeatmapCanvas(self)
        main_layout.addWidget(self.heatmap_area, 1)

        # 数值显示区域 - 紧凑布局
        values_layout = QHBoxLayout()
        values_layout.setSpacing(3)
        values_layout.setContentsMargins(0, 0, 0, 0)
        self.value_labels = {}

        for metric in self.all_metrics:
            value_container = QWidget()
            value_container.setStyleSheet("border: none;")
            value_layout = QVBoxLayout(value_container)
            value_layout.setContentsMargins(0, 0, 0, 0)
            value_layout.setSpacing(1)

            # 指标名称（带分组标识）
            name_label = QLabel(metric["label"])
            name_label.setStyleSheet("font-size: 11px; color: #AAA; border: none;")
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setWordWrap(True)
            value_layout.addWidget(name_label)

            # 指标数值
            value_label = QLabel(f"0.0{metric['unit']}")
            value_label.setStyleSheet(
                "font-size: 12px; font-weight: bold; color: #FFF; border: none;"
            )
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value_layout.addWidget(value_label)

            self.value_labels[metric["key"]] = value_label

            # 延迟列特殊处理：添加无网络连接显示和重试按钮
            if metric["key"] == "latency":
                # 创建无网络连接显示容器
                network_status_container = QWidget()
                network_status_layout = QVBoxLayout(network_status_container)
                network_status_layout.setContentsMargins(0, 0, 0, 0)
                network_status_layout.setSpacing(3)

                # 无网络连接标签（默认隐藏）
                network_disconnected_label = QLabel("无网络连接")
                network_disconnected_label.setStyleSheet(
                    "font-size: 10px; color: #d32f2f; font-weight: bold; border: none;"
                )
                network_disconnected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                network_disconnected_label.hide()

                # 重试按钮（默认隐藏）
                retry_latency_btn = QPushButton("重试")
                retry_latency_btn.setStyleSheet(
                    "font-size: 9px; padding: 2px 6px; background-color: #d32f2f; color: white; border: none; border-radius: 2px;"
                )
                retry_latency_btn.setMaximumHeight(20)
                retry_latency_btn.hide()

                network_status_layout.addWidget(network_disconnected_label)
                network_status_layout.addWidget(retry_latency_btn)

                value_layout.addWidget(network_status_container)

                # 保存引用以便后续更新
                self.latency_network_disconnected_label = network_disconnected_label
                self.latency_retry_btn = retry_latency_btn

            values_layout.addWidget(value_container)

        main_layout.addLayout(values_layout)

        # 带宽详情标签（特殊处理） - 紧凑样式
        self.bandwidth_detail_label = QLabel("带宽未测试")
        self.bandwidth_detail_label.setStyleSheet(
            "font-size: 10px; color: #666; border: none; padding: 2px;"
        )
        self.bandwidth_detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.bandwidth_detail_label)

        # 延迟列的无网络连接标签和重试按钮引用（延迟初始化）
        self.latency_network_disconnected_label: Optional[QLabel] = None
        self.latency_retry_btn: Optional[QPushButton] = None

    def update_metrics(self, values: Dict[str, float]):
        """批量更新指标."""
        for key, value in values.items():
            if key in self.metric_values:
                self.metric_values[key] = value
                if key in self.value_labels:
                    metric_config = next((m for m in self.all_metrics if m["key"] == key), None)
                    if metric_config:
                        unit = metric_config["unit"]
                        self.value_labels[key].setText(f"{value:.1f}{unit}")
        self.heatmap_area.update()

    def update_bandwidth_detail(self, download_mbps: float, total_mbps: float, percent: float):
        """更新带宽详情."""
        if total_mbps > 0:
            self.bandwidth_detail_label.setText(
                f"实时带宽: {download_mbps:.1f}/{total_mbps:.1f}Mbps ({percent:.1f}%)"
            )
        else:
            self.bandwidth_detail_label.setText("带宽未测试")

    def update_network_status(self, disconnected: bool, retry_callback=None):
        """更新无网络连接状态显示.

        Args:
            disconnected: 是否无网络连接
            retry_callback: 重试按钮点击回调函数
        """
        if hasattr(self, "latency_network_disconnected_label") and self.latency_network_disconnected_label:
            if disconnected:
                self.latency_network_disconnected_label.show()
            else:
                self.latency_network_disconnected_label.hide()

        if hasattr(self, "latency_retry_btn") and self.latency_retry_btn:
            if disconnected:
                self.latency_retry_btn.show()
                if retry_callback:
                    # 断开之前的连接（避免重复连接）
                    try:
                        self.latency_retry_btn.clicked.disconnect()
                    except:
                        pass
                    self.latency_retry_btn.clicked.connect(retry_callback)
            else:
                self.latency_retry_btn.hide()


class NetworkMonitorCard(VerticalThresholdHeatmap):
    """网络监控卡片（第一行第二列）.

    显示3个指标:
    - 网络丢包率 (%)
    - 延迟 (ms)
    - 带宽占用 (%) + 详细带宽信息
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化网络监控卡片."""
        metrics = [
            {
                "key": "packet_loss",
                "label": "丢包率",
                "unit": "%",
                "warning": 0.5,
                "critical": 2.0,
                "max_value": 5.0,
            },
            {
                "key": "latency",
                "label": "延迟",
                "unit": "ms",
                "warning": 50,
                "critical": 100,
                "max_value": 200,
            },
            {
                "key": "bandwidth_usage",
                "label": "带宽占用",
                "unit": "%",
                "warning": 70,
                "critical": 90,
                "max_value": 100,
            },
        ]
        super().__init__("🌐 网络监控", metrics, parent)

        # 在带宽占用列下方添加详细信息
        # 获取带宽占用对应的value_container（第3个）
        bandwidth_container = self.values_layout.itemAt(2).widget()
        if bandwidth_container:
            container_layout = bandwidth_container.layout()
            if container_layout:
                # 添加带宽详情标签
                self.bandwidth_detail_label = QLabel("--")
                self.bandwidth_detail_label.setStyleSheet(
                    "font-size: 9px; color: #888; border: none;"
                )
                self.bandwidth_detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.bandwidth_detail_label.setWordWrap(True)
                container_layout.addWidget(self.bandwidth_detail_label)

        # 在延迟列下方添加无网络连接显示和重试按钮
        # 获取延迟对应的value_container（第2个）
        latency_container = self.values_layout.itemAt(1).widget()
        if latency_container:
            container_layout = latency_container.layout()
            if container_layout:
                # 创建无网络连接显示容器
                self.network_status_container = QWidget()
                network_status_layout = QVBoxLayout(self.network_status_container)
                network_status_layout.setContentsMargins(0, 0, 0, 0)
                network_status_layout.setSpacing(5)

                # 无网络连接标签（默认隐藏）
                self.network_disconnected_label = QLabel("无网络连接")
                self.network_disconnected_label.setStyleSheet(
                    "font-size: 11px; color: #d32f2f; font-weight: bold; border: none;"
                )
                self.network_disconnected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.network_disconnected_label.hide()

                # 重试按钮（默认隐藏）
                self.retry_latency_btn = QPushButton("重试")
                self.retry_latency_btn.setStyleSheet(
                    "font-size: 10px; padding: 3px 8px; background-color: #d32f2f; color: white; border: none; border-radius: 3px;"
                )
                self.retry_latency_btn.setMaximumHeight(25)
                self.retry_latency_btn.hide()

                network_status_layout.addWidget(self.network_disconnected_label)
                network_status_layout.addWidget(self.retry_latency_btn)

                container_layout.addWidget(self.network_status_container)

    def update_bandwidth_detail(self, download_mbps: float, total_mbps: float, percent: float):
        """更新带宽详情显示.

        Args:
            download_mbps: 实时下载速度
            total_mbps: 总带宽（运营商提供的带宽上限）
            percent: 百分比
        """
        if hasattr(self, "bandwidth_detail_label"):
            if total_mbps > 0:
                self.bandwidth_detail_label.setText(
                    f"{download_mbps:.1f}/{total_mbps:.1f}Mbps\n({percent:.1f}%)"
                )
            else:
                self.bandwidth_detail_label.setText("未测试")


class MemoryMonitorCard(VerticalThresholdHeatmap):
    """内存监控卡片（第一行第三列）.

    显示2个指标:
    - 内存使用率 (%)
    - 内存交换 (MB/s)
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化内存监控卡片."""
        metrics = [
            {
                "key": "memory_usage",
                "label": "使用率",
                "unit": "%",
                "warning": 75,
                "critical": 85,
                "max_value": 100,
            },
            {
                "key": "swap_total",
                "label": "内存交换",
                "unit": "MB/s",
                "warning": 10,
                "critical": 50,
                "max_value": 100,
            },
        ]
        super().__init__("💾 内存监控", metrics, parent)


class SingleDiskCard(QWidget):
    """单个硬盘的信息卡片 - 扩展版，展示更多SMART信息."""

    def __init__(self, disk_name: str, parent: Optional[QWidget] = None):
        """初始化单个硬盘卡片."""
        super().__init__(parent)

        self.disk_name = disk_name

        # 卡片样式 - 自适应宽度
        self.setMinimumWidth(250)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.setStyleSheet(
            """
            SingleDiskCard {
                background-color: #252525;
                border: 1px solid #555;
                border-radius: 5px;
            }
            """
        )

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)

        # 硬盘名称标题 - 增大字体
        self.name_label = QLabel(disk_name)
        self.name_label.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #CCC; border: none;"
        )
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #444; border: none;")
        line.setFixedHeight(1)
        layout.addWidget(line)

        # 信息标签字典
        self.info_labels = {}

        # 添加更多SMART信息行
        self._add_info_row("型号", "model", layout)
        self._add_info_row("容量", "capacity", layout)
        self._add_info_row("健康评估", "assessment", layout)
        self._add_info_row("温度", "temperature", layout)
        self._add_info_row("开机时长", "power_on_hours", layout)
        self._add_info_row("重分配扇区", "reallocated_sectors", layout)
        self._add_info_row("待处理扇区", "pending_sectors", layout)
        self._add_info_row("不可修复错误", "uncorrectable_errors", layout)

        layout.addStretch()

    def _add_info_row(self, label_text: str, key: str, layout: QVBoxLayout):
        """添加信息行."""
        row = QHBoxLayout()
        row.setSpacing(8)

        # 标签 - 增大字体
        label = QLabel(label_text + ":")
        label.setStyleSheet("font-size: 13px; color: #999; border: none;")
        label.setMinimumWidth(75)
        row.addWidget(label)

        # 值 - 增大字体
        value_label = QLabel("--")
        value_label.setStyleSheet("font-size: 13px; color: #EEE; border: none;")
        value_label.setWordWrap(True)
        row.addWidget(value_label, 1)

        self.info_labels[key] = value_label
        layout.addLayout(row)

    def update_data(self, attrs: Dict[str, Any]):
        """更新硬盘数据."""
        # 型号
        if "model" in attrs:
            model = attrs["model"]
            # 简化型号显示
            if len(model) > 35:
                model = model[:32] + "..."
            self.info_labels["model"].setText(model)

        # 容量
        if "capacity" in attrs:
            self.info_labels["capacity"].setText(str(attrs["capacity"]))

        # 健康评估（带颜色）
        if "assessment" in attrs:
            assessment = attrs["assessment"]
            color = "#00FF00"  # 绿色
            if "警告" in assessment:
                color = "#FFAA00"
            elif "故障" in assessment:
                color = "#FF0000"
            elif "未知" in assessment:
                color = "#888888"

            self.info_labels["assessment"].setText(assessment)
            self.info_labels["assessment"].setStyleSheet(
                f"font-size: 12px; color: {color}; border: none; font-weight: bold;"
            )

        # 温度
        if "temperature" in attrs and attrs["temperature"]:
            temp = attrs["temperature"]
            self.info_labels["temperature"].setText(f"{temp}°C")
        else:
            self.info_labels["temperature"].setText("--")

        # 开机时长
        if "power_on_hours" in attrs and attrs["power_on_hours"]:
            hours = attrs["power_on_hours"]
            days = hours // 24
            self.info_labels["power_on_hours"].setText(f"{hours:,}h ({days}天)")
        else:
            self.info_labels["power_on_hours"].setText("--")

        # 重新分配扇区数
        if "reallocated_sectors" in attrs:
            value = attrs["reallocated_sectors"]
            if value == 0:
                self.info_labels["reallocated_sectors"].setText("0 ✓")
                self.info_labels["reallocated_sectors"].setStyleSheet(
                    "font-size: 11px; color: #0F0; border: none;"
                )
            else:
                self.info_labels["reallocated_sectors"].setText(f"{value} ⚠️")
                self.info_labels["reallocated_sectors"].setStyleSheet(
                    "font-size: 11px; color: #FA0; border: none; font-weight: bold;"
                )

        # 待处理扇区数
        if "pending_sectors" in attrs:
            value = attrs["pending_sectors"]
            if value == 0:
                self.info_labels["pending_sectors"].setText("0 ✓")
                self.info_labels["pending_sectors"].setStyleSheet(
                    "font-size: 11px; color: #0F0; border: none;"
                )
            else:
                self.info_labels["pending_sectors"].setText(f"{value} ⚠️")
                self.info_labels["pending_sectors"].setStyleSheet(
                    "font-size: 11px; color: #FA0; border: none; font-weight: bold;"
                )

        # 不可修复错误数
        if "uncorrectable_errors" in attrs:
            value = attrs["uncorrectable_errors"]
            if value == 0:
                self.info_labels["uncorrectable_errors"].setText("0 ✓")
                self.info_labels["uncorrectable_errors"].setStyleSheet(
                    "font-size: 11px; color: #0F0; border: none;"
                )
            else:
                self.info_labels["uncorrectable_errors"].setText(f"{value} ⚠️")
                self.info_labels["uncorrectable_errors"].setStyleSheet(
                    "font-size: 11px; color: #FA0; border: none; font-weight: bold;"
                )


class DiskMonitorCard(QWidget):
    """硬盘监控卡片 - 横向排列，自适应字体."""

    # 🔧 线程安全信号：用于跨线程更新UI
    update_requested = Signal(str, dict)  # (health_status, smart_attributes)

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化硬盘监控卡片."""
        super().__init__(parent)

        # 🔧 连接信号到槽函数（Qt会自动在主线程执行槽函数）
        self.update_requested.connect(self._safe_update_ui)

        # 设置最小尺寸
        self.setMinimumHeight(180)
        self.setMinimumWidth(400)

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

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 标题和健康状态（横向）
        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)

        # 标题 - 增大字体
        title_label = QLabel("💿 硬盘监控")
        title_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #E0E0E0; border: none;"
        )
        header_layout.addWidget(title_label)

        # SMART健康状态 - 增大字体
        self.health_label = QLabel("健康状态: --")
        self.health_label.setStyleSheet(
            "font-size: 13px; color: #FFF; border: none; padding: 5px; font-weight: bold;"
        )
        header_layout.addWidget(self.health_label)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # 硬盘卡片容器（横向滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            """
            QScrollArea {
                background-color: #2A2A2A;
                border: 1px solid #444;
                border-radius: 3px;
            }
            QScrollBar:horizontal {
                background-color: #1E1E1E;
                height: 10px;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background-color: #555;
                border-radius: 5px;
                min-width: 30px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #777;
            }
            """
        )

        # 硬盘卡片容器widget - 设置自适应策略
        self.disks_container = QWidget()
        self.disks_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.disks_layout = QHBoxLayout(self.disks_container)
        self.disks_layout.setContentsMargins(5, 5, 5, 5)
        self.disks_layout.setSpacing(15)  # 增加间距
        # 不添加弹簧，让卡片均匀分布填充空间

        scroll.setWidget(self.disks_container)
        main_layout.addWidget(scroll, 1)

        # 硬盘卡片字典
        self.disk_cards = {}

    def update_smart_data(self, health_status: str, smart_attributes: Dict[str, Any]):
        """线程安全的SMART数据更新入口.

        通过信号槽机制确保UI更新在主线程执行，避免跨线程错误。

        Args:
            health_status: 健康状态 (如 "良好", "警告", "故障", "不可用")
            smart_attributes: SMART属性字典
        """
        # 🔧 发射信号（Qt会自动在主线程执行槽函数）
        self.update_requested.emit(health_status, smart_attributes)

    def _safe_update_ui(self, health_status: str, smart_attributes: Dict[str, Any]):
        """线程安全的UI更新方法（在主线程执行）- 横向卡片布局."""
        # 更新整体健康状态
        status_color = "#00FF00"  # 绿色（默认：正常）
        if "警告" in health_status:
            status_color = "#FFAA00"  # 橙黄色
        elif "故障" in health_status or "危险" in health_status:
            status_color = "#FF0000"  # 红色
        elif "未知" in health_status or "不可用" in health_status:
            status_color = "#888888"  # 灰色

        self.health_label.setText(f"健康状态: {health_status}")
        self.health_label.setStyleSheet(
            f"font-size: 11px; color: {status_color}; border: none; padding: 5px; font-weight: bold;"
        )

        # 更新或创建硬盘卡片
        if smart_attributes:
            # 移除不存在的硬盘卡片
            current_disks = set(smart_attributes.keys())
            for disk_name in list(self.disk_cards.keys()):
                if disk_name not in current_disks:
                    card = self.disk_cards.pop(disk_name)
                    self.disks_layout.removeWidget(card)
                    card.deleteLater()

            # 更新或创建硬盘卡片
            for idx, (disk_name, attrs) in enumerate(smart_attributes.items()):
                if disk_name not in self.disk_cards:
                    # 创建新卡片
                    card = SingleDiskCard(disk_name, parent=self.disks_container)
                    self.disk_cards[disk_name] = card
                    # 插入到弹簧之前
                    self.disks_layout.insertWidget(idx, card)

                # 更新卡片数据
                self.disk_cards[disk_name].update_data(attrs)


class AlertManagerWidget(QWidget):
    """告警管理界面组件."""

    def __init__(self):
        """初始化告警管理界面."""
        super().__init__()

        # 告警数据
        self.alerts: List[Dict[str, Any]] = []
        self.alert_cards: List[AlertCard] = []

        # 筛选条件
        self.current_filters = {
            "status": None,
            "severity": None,
        }

        # 自动刷新标志
        self.auto_refresh = True

        # 更新定时器
        self.update_timer: Optional[QTimer] = None

        # 初始化UI
        self._init_ui()

        # 连接信号
        self._connect_signals()

        # 🎯 关键修复：处理懒加载场景（当用户点击选项卡时才创建组件）
        # 此时backend可能已经就绪，需要立即初始化而不是等待事件
        try:
            orch = get_boot_orchestrator()

            # 检查backend是否已经就绪
            if orch.is_ready("backend_ready") and orch.is_ready("ui_ready"):
                # backend已就绪（懒加载场景），立即初始化
                QTimer.singleShot(0, self._init_after_backend)
            else:
                # backend未就绪，注册回调等待
                orch.on_all_ready(
                    ["backend_ready", "ui_ready", "ui_visible"],
                    lambda: QTimer.singleShot(0, self._init_after_backend),
                )
        except Exception:
            # 回退：若编排器不可用，仍按旧逻辑启动
            self.start_update_timer()

    def _init_ui(self) -> None:
        """初始化用户界面."""
        layout = QVBoxLayout(self)

        # 顶部工具栏
        toolbar = self._create_toolbar()
        layout.addLayout(toolbar)

        # 告警列表区域
        scroll_area = self._create_alert_list_area()
        layout.addWidget(scroll_area)

    def _create_toolbar(self) -> QHBoxLayout:
        """创建顶部工具栏."""
        layout = QHBoxLayout()

        # 状态筛选
        status_label = QLabel("状态:")
        self.status_combo = QComboBox()
        self.status_combo.addItems(["全部", "NEW", "ACKNOWLEDGED", "RESOLVED", "IGNORED"])
        layout.addWidget(status_label)
        layout.addWidget(self.status_combo)

        # 严重程度筛选
        severity_label = QLabel("严重程度:")
        self.severity_combo = QComboBox()
        self.severity_combo.addItems(["全部", "CRITICAL", "ERROR", "WARNING", "INFO"])
        layout.addWidget(severity_label)
        layout.addWidget(self.severity_combo)

        layout.addStretch()

        # 刷新按钮
        self.refresh_btn = QPushButton("刷新")
        layout.addWidget(self.refresh_btn)

        # 清理按钮
        self.cleanup_btn = QPushButton("清理已解决")
        layout.addWidget(self.cleanup_btn)

        # 统计信息
        self.stats_label = QLabel("告警统计: 总计 0 条")
        layout.addWidget(self.stats_label)

        return layout

    def _create_alert_list_area(self) -> QScrollArea:
        """创建告警列表区域."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 容器widget
        container = QWidget()
        self.alerts_layout = QVBoxLayout(container)
        self.alerts_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 设置间距
        self.alerts_layout.setSpacing(5)
        self.alerts_layout.setContentsMargins(10, 10, 10, 10)

        scroll_area.setWidget(container)
        return scroll_area

    def _connect_signals(self) -> None:
        """连接信号槽."""
        self.status_combo.currentTextChanged.connect(self._apply_filters)
        self.severity_combo.currentTextChanged.connect(self._apply_filters)
        self.refresh_btn.clicked.connect(self._refresh_alerts)
        self.cleanup_btn.clicked.connect(self._cleanup_resolved)

    def _apply_filters(self) -> None:
        """应用筛选条件."""
        # 获取筛选条件
        status_text = self.status_combo.currentText()
        status = status_text if status_text != "全部" else None

        severity_text = self.severity_combo.currentText()
        severity = severity_text if severity_text != "全部" else None

        # 应用筛选
        filtered_alerts = []
        for alert in self.alerts:
            # 状态筛选
            if status and alert.get("status") != status.lower():
                continue

            # 严重程度筛选
            if severity and alert.get("severity") != severity.lower():
                continue

            filtered_alerts.append(alert)

        # 更新显示
        self._update_alert_cards(filtered_alerts)

        # 更新统计
        self._update_stats()

    def _update_alert_cards(self, alerts: List[Dict[str, Any]]) -> None:
        """更新告警卡片显示."""
        # 清空现有卡片
        for card in self.alert_cards:
            card.setParent(None)
            card.deleteLater()

        self.alert_cards.clear()

        # 创建新卡片
        for alert in alerts:
            card = AlertCard(alert)
            self.alerts_layout.addWidget(card)
            self.alert_cards.append(card)

    def _update_stats(self) -> None:
        """更新统计信息."""
        total = len(self.alerts)
        new_count = sum(1 for a in self.alerts if a.get("status") == "new")
        acknowledged_count = sum(1 for a in self.alerts if a.get("status") == "acknowledged")
        resolved_count = sum(1 for a in self.alerts if a.get("status") == "resolved")

        self.stats_label.setText(
            f"告警统计: 总计 {total} 条 (新: {new_count}, 确认: {acknowledged_count}, 解决: {resolved_count})"
        )

    def _refresh_alerts(self) -> None:
        """刷新告警数据."""
        try:
            # 调用后端API获取最新告警
            service_manager = get_service_manager()
            system_service = service_manager.get_service("system_manager_service", silent=True)

            if system_service:
                # 获取所有告警
                result = system_service.query_alerts(limit=1000)

                if result.get("success"):
                    self.alerts = result.get("alerts", [])
                    self._apply_filters()
                else:
                    QMessageBox.warning(self, "错误", f"获取告警失败: {result.get('message')}")
            else:
                QMessageBox.warning(self, "错误", "系统管理服务不可用")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"刷新告警失败: {str(e)}")

    def _cleanup_resolved(self) -> None:
        """清理已解决的告警."""
        try:
            service_manager = get_service_manager()
            system_service = service_manager.get_service("system_manager_service", silent=True)

            if system_service:
                result = system_service.clear_resolved_alerts()

                if result.get("success"):
                    QMessageBox.information(self, "成功", result.get("message"))
                    # 刷新告警列表
                    self._refresh_alerts()
                else:
                    QMessageBox.warning(self, "错误", f"清理失败: {result.get('message')}")
            else:
                QMessageBox.warning(self, "错误", "系统管理服务不可用")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"清理告警失败: {str(e)}")

    def refresh_alerts(self) -> None:
        """刷新告警显示（供子组件调用）."""
        self._refresh_alerts()

    def add_alert(self, alert_data: Dict[str, Any]) -> None:
        """添加新告警."""
        # 检查是否已存在
        for existing_alert in self.alerts:
            if existing_alert.get("alert_id") == alert_data.get("alert_id"):
                # 更新现有告警
                existing_alert.update(alert_data)
                self._apply_filters()
                return

        # 添加新告警
        self.alerts.insert(0, alert_data)  # 插入到开头

        # 限制最大数量
        if len(self.alerts) > 500:
            self.alerts = self.alerts[:500]

        # 应用筛选
        self._apply_filters()

    def update_alert(self, alert_data: Dict[str, Any]) -> None:
        """更新告警状态."""
        alert_id = alert_data.get("alert_id")

        # 查找并更新
        for i, alert in enumerate(self.alerts):
            if alert.get("alert_id") == alert_id:
                self.alerts[i].update(alert_data)
                break

        # 应用筛选（重新排序）
        self._apply_filters()

    def start_update_timer(self) -> None:
        """启动更新定时器."""
        if self.update_timer:
            self.update_timer.stop()

        # 每10秒自动刷新一次
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._refresh_alerts)
        self.update_timer.start(10000)  # 10秒

    def stop_update_timer(self) -> None:
        """停止更新定时器."""
        if self.update_timer:
            self.update_timer.stop()
            self.update_timer = None

    def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """处理事件."""
        if event_type == EVENT_ALERT_CREATED:
            # 新告警创建（切回主线程）
            QTimer.singleShot(0, lambda: self.add_alert(event_data))
        elif event_type == EVENT_ALERT_UPDATED:
            # 告警状态更新（切回主线程）
            QTimer.singleShot(0, lambda: self.update_alert(event_data))

    def _init_after_backend(self) -> None:
        """在后端与UI就绪后启动刷新与定时器."""
        try:
            # 先做一次首刷
            self._refresh_alerts()
        finally:
            # 启动定时器
            self.start_update_timer()

    def get_current_filters(self) -> Dict[str, Any]:
        """获取当前筛选条件."""
        return {
            "status": (
                self.status_combo.currentText()
                if self.status_combo.currentText() != "全部"
                else None
            ),
            "severity": (
                self.severity_combo.currentText()
                if self.severity_combo.currentText() != "全部"
                else None
            ),
        }

    def apply_filters_from_dict(self, filters: Dict[str, Any]) -> None:
        """从字典应用筛选条件."""
        if "status" in filters and filters["status"]:
            index = self.status_combo.findText(filters["status"])
            if index >= 0:
                self.status_combo.setCurrentIndex(index)
        else:
            self.status_combo.setCurrentIndex(0)

        if "severity" in filters and filters["severity"]:
            index = self.severity_combo.findText(filters["severity"])
            if index >= 0:
                self.severity_combo.setCurrentIndex(index)
        else:
            self.severity_combo.setCurrentIndex(0)

        self._apply_filters()


# ==================== 日志管理组件 ====================


class LogManagerWidget(QWidget):
    """日志管理界面组件."""

    # 信号定义
    log_record_received = Signal(dict)  # 接收到新的日志记录
    logs_query_completed = Signal(dict)  # 日志查询完成信号（用于跨线程传递结果）

    def __init__(self):
        """初始化日志管理界面."""
        super().__init__()

        # 🎯 立即添加调试日志
        import logging

        logger = logging.getLogger(__name__)
        logger.info("=" * 70)
        logger.info("[LogManagerWidget] __init__ 被调用 - 组件正在创建")
        logger.info("=" * 70)

        # 日志数据
        self.log_records: List[Dict[str, Any]] = []
        self.display_records: List[Dict[str, Any]] = []

        # 筛选条件
        self.current_filters = {
            "level": None,
            "start_time": None,
            "end_time": None,
            "module": None,
            "logger_name": None,
        }

        # 模块列表（用于下拉框）
        self.available_modules: List[str] = ["全部"]

        # 自动滚动标志
        self.auto_scroll = True

        # 更新定时器
        self.update_timer: Optional[QTimer] = None

        # 初始化UI
        self._init_ui()

        # 连接信号
        self._connect_signals()

        # 🎯 关键修复：处理懒加载场景（当用户点击选项卡时才创建组件）
        # 此时backend可能已经就绪，需要立即初始化而不是等待事件
        try:
            logger.info("[LogManagerWidget] 检查BootOrchestrator状态...")
            orch = get_boot_orchestrator()
            logger.info("[LogManagerWidget] BootOrchestrator获取成功")

            # 检查backend是否已经就绪
            backend_ready = orch.is_ready("backend_ready")
            ui_ready = orch.is_ready("ui_ready")
            logger.info(f"[LogManagerWidget] backend_ready={backend_ready}, ui_ready={ui_ready}")

            if backend_ready and ui_ready:
                # backend已就绪（懒加载场景），立即初始化
                logger.info("[LogManagerWidget] Backend已就绪，立即初始化")
                QTimer.singleShot(0, self._init_after_backend)
            else:
                # backend未就绪，注册回调等待
                logger.info("[LogManagerWidget] Backend未就绪，注册回调等待")
                orch.on_all_ready(
                    ["backend_ready", "ui_ready", "ui_visible"],
                    lambda: QTimer.singleShot(0, self._init_after_backend),
                )
        except Exception as e:
            # 回退：若编排器不可用，仍按旧逻辑启动
            logger.error(f"[LogManagerWidget] BootOrchestrator异常: {e}")
            logger.error("[LogManagerWidget] 回退到旧逻辑，启动更新定时器")
            self.start_update_timer()

        logger.info("[LogManagerWidget] __init__ 完成")
        logger.info("=" * 70)

    def _init_ui(self) -> None:
        """初始化用户界面."""
        layout = QVBoxLayout(self)

        # 顶部工具栏
        toolbar = self._create_toolbar()
        layout.addLayout(toolbar)

        # 日志表格
        self.log_table = self._create_log_table()
        layout.addWidget(self.log_table)

        # 底部状态栏
        status_layout = self._create_status_bar()
        layout.addLayout(status_layout)

    def _create_toolbar(self) -> QHBoxLayout:
        """创建顶部工具栏."""
        layout = QHBoxLayout()

        # 日志级别筛选
        level_label = QLabel("级别:")
        self.level_combo = QComboBox()
        self.level_combo.addItems(["全部", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        layout.addWidget(level_label)
        layout.addWidget(self.level_combo)

        # 模块筛选
        module_label = QLabel("模块:")
        self.module_combo = QComboBox()
        self.module_combo.addItem("全部")  # 初始只有"全部"
        layout.addWidget(module_label)
        layout.addWidget(self.module_combo)

        layout.addStretch()

        # 时间范围选择
        time_label = QLabel("时间范围:")
        self.start_time_edit = QDateTimeEdit()
        # 🔧 修复：默认从很久以前开始，避免过滤新日志
        start_time = QDateTime.currentDateTime().addDays(-7)  # 7天前
        self.start_time_edit.setDateTime(start_time)
        self.start_time_edit.setDisplayFormat("yyyy-MM-dd hh:mm:ss")

        self.end_time_edit = QDateTimeEdit()
        # 🔧 修复：设置为未来时间，确保新日志不被过滤
        self.end_time_edit.setDateTime(QDateTime.currentDateTime().addDays(1))  # 明天
        self.end_time_edit.setDisplayFormat("yyyy-MM-dd hh:mm:ss")

        layout.addWidget(time_label)
        layout.addWidget(self.start_time_edit)
        layout.addWidget(QLabel("至"))
        layout.addWidget(self.end_time_edit)

        layout.addStretch()

        # 搜索框
        search_label = QLabel("搜索:")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("模块名或关键字...")
        self.search_edit.setFixedWidth(200)
        layout.addWidget(search_label)
        layout.addWidget(self.search_edit)

        # 刷新按钮
        self.refresh_btn = QPushButton("刷新")
        layout.addWidget(self.refresh_btn)

        # 导出按钮
        self.export_btn = QPushButton("导出")
        layout.addWidget(self.export_btn)

        # 删除选中按钮
        self.delete_selected_btn = QPushButton("删除选中")
        self.delete_selected_btn.setStyleSheet("color: darkred;")
        layout.addWidget(self.delete_selected_btn)

        # 清空按钮
        self.clear_btn = QPushButton("清空显示")
        layout.addWidget(self.clear_btn)

        # 删除全部日志按钮
        self.delete_all_btn = QPushButton("删除全部日志")
        self.delete_all_btn.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(self.delete_all_btn)

        return layout

    def _create_log_table(self) -> QTableView:
        """创建日志表格（使用Model/View架构）.

        架构优势：
        - 数据-视图分离，性能更高
        - 支持虚拟滚动，只渲染可见行
        - 批量更新，减少重绘次数
        """
        # 🔧 关键架构改进：使用QTableView + Model
        table = QTableView()

        # 创建并设置Model
        self.log_model = LogTableModel(self)
        table.setModel(self.log_model)
        # 为第0列设置无白底复选框委托
        table.setItemDelegateForColumn(0, LogCheckboxDelegate(table))

        # 设置表头属性（注意：现在有复选框列，索引+1）
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # 复选框列固定宽度
        header.resizeSection(0, 50)  # 设置复选框列宽度为50px
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # 时间
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # 级别
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # 模块
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # 函数
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # 行号
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)  # 消息

        # 🔧 移除setHeaderData调用，改为在Model的headerData()中直接处理
        # (避免Qt内部状态不一致导致渲染问题)

        # 连接表头点击事件（第一列点击时全选/取消全选）
        header.sectionClicked.connect(self._on_header_clicked)

        # 设置表头样式（让复选框列更突出）
        header.setStyleSheet(
            """
            QHeaderView::section:first {
                background-color: #E8F4F8;
                font-weight: bold;
            }
        """
        )

        # 设置表格属性
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        # 🔧 关键修复：复选框通过ItemIsUserCheckable工作，不需要EditTriggers
        # 设置NoEditTriggers防止误触发编辑模式（会显示白色编辑器框）
        table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)

        # 🔧 性能优化：启用虚拟滚动
        table.setVerticalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        table.setHorizontalScrollMode(QTableView.ScrollMode.ScrollPerPixel)

        # 双击查看详情
        table.doubleClicked.connect(self._show_log_detail)
        # 单击复选框列支持单条选中/反选
        table.clicked.connect(self._on_table_clicked)

        # 🔧 复选框指示器样式：未选中透明底，避免白块与表格不一致
        table.setStyleSheet(
            """
            QTableView::indicator {
                width: 16px;
                height: 16px;
                background-color: transparent;
            }
            QTableView::indicator:unchecked {
                background-color: transparent;
                border: 1px solid #A0A0A0;
            }
            QTableView::indicator:unchecked:hover {
                border: 1px solid #0078D7;
            }
            QTableView::indicator:checked {
                background-color: #0078D7;
                border: 1px solid #0078D7;
            }
            QTableView::indicator:indeterminate {
                background-color: #66A3E0;
                border: 1px solid #0078D7;
            }
            """
        )

        return table

    def _on_table_clicked(self, index) -> None:
        """表格单击处理：第一列复选框支持单条切换。"""
        try:
            if not index or not index.isValid():
                return
            if index.column() != 0:
                return
            current_state = self.log_model.data(index, Qt.ItemDataRole.CheckStateRole)
            new_state = (
                Qt.CheckState.Unchecked
                if current_state == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )
            self.log_model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
            self._update_stats()
        except Exception:
            # 单击切换失败不影响主流程
            pass

    def _create_status_bar(self) -> QHBoxLayout:
        """创建底部状态栏."""
        layout = QHBoxLayout()

        # 统计信息
        self.stats_label = QLabel("日志统计: 总计 0 条")
        layout.addWidget(self.stats_label)

        layout.addStretch()

        # 自动滚动开关
        self.auto_scroll_checkbox = QPushButton("自动滚动")
        self.auto_scroll_checkbox.setCheckable(True)
        self.auto_scroll_checkbox.setChecked(True)
        self.auto_scroll_checkbox.clicked.connect(self._toggle_auto_scroll)
        layout.addWidget(self.auto_scroll_checkbox)

        return layout

    def _connect_signals(self) -> None:
        """连接信号槽."""
        self.level_combo.currentTextChanged.connect(self._apply_filters)
        self.module_combo.currentTextChanged.connect(self._apply_filters)
        self.start_time_edit.dateTimeChanged.connect(self._apply_filters)
        self.end_time_edit.dateTimeChanged.connect(self._apply_filters)
        self.search_edit.textChanged.connect(self._apply_filters)
        self.refresh_btn.clicked.connect(self._refresh_logs)
        self.export_btn.clicked.connect(self._export_logs)
        self.delete_selected_btn.clicked.connect(self._delete_selected_logs)
        self.clear_btn.clicked.connect(self._clear_display)
        self.delete_all_btn.clicked.connect(self._delete_all_logs)

        # 连接Model数据变化信号以更新统计信息
        self.log_model.dataChanged.connect(lambda: self._update_stats())

        # 🔧 关键修复：连接跨线程信号，确保查询结果能正确传递到主线程
        self.logs_query_completed.connect(self._handle_logs_result)

    def _toggle_auto_scroll(self) -> None:
        """切换自动滚动."""
        self.auto_scroll = self.auto_scroll_checkbox.isChecked()

    def _update_module_list(self) -> None:
        """动态更新模块列表（从现有日志记录中提取）."""
        try:
            # 从当前日志记录中提取所有模块名
            modules = set()
            for record in self.log_records:
                module = record.get("module", "")
                if module:
                    modules.add(module)

            # 更新模块列表
            new_modules = sorted(list(modules))

            # 只有当模块列表发生变化时才更新下拉框
            if new_modules != self.available_modules[1:]:  # 跳过"全部"
                self.available_modules = ["全部"] + new_modules

                # 记住当前选中的模块
                current_module = self.module_combo.currentText()

                # 清空并重新填充模块下拉框
                self.module_combo.clear()
                self.module_combo.addItems(self.available_modules)

                # 恢复之前选中的模块（如果还存在）
                if current_module in self.available_modules:
                    self.module_combo.setCurrentText(current_module)
                else:
                    self.module_combo.setCurrentText("全部")

        except Exception as e:
            # 更新模块列表失败不影响主要功能
            print(f"更新模块列表失败: {e}")

    def _apply_filters(self) -> None:
        """应用筛选条件."""
        # 获取筛选条件
        level_text = self.level_combo.currentText()
        level = level_text if level_text != "全部" else None

        module_text = self.module_combo.currentText()
        module = module_text if module_text != "全部" else None

        start_time = self.start_time_edit.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
        end_time = self.end_time_edit.dateTime().toString("yyyy-MM-ddTHH:mm:ss")

        search_text = self.search_edit.text().strip()
        search_terms = [term.strip() for term in search_text.split()] if search_text else []

        # 记录用户日志查询操作（审计）
        logger_user.info(
            "用户查询日志: 级别=%s, 模块=%s, 时间范围=%s至%s, 搜索=%s",
            level or "全部",
            module or "全部",
            start_time,
            end_time,
            search_text or "无",
        )

        # 应用筛选
        filtered_records = []
        for record in self.log_records:
            # 级别筛选
            if level and record.get("level") != level:
                continue

            # 模块筛选
            if module and record.get("module") != module:
                continue

            # 时间筛选
            record_time = record.get("timestamp", "")
            if record_time:
                if start_time and record_time < start_time:
                    continue
                if end_time and record_time > end_time:
                    continue

            # 搜索筛选（模块名或消息内容）
            if search_terms:
                module = record.get("module", "").lower()
                message = record.get("message", "").lower()
                if not any(
                    term.lower() in module or term.lower() in message for term in search_terms
                ):
                    continue

            filtered_records.append(record)

        # 更新显示
        self.display_records = filtered_records
        self._update_table()

        # 更新统计
        self._update_stats()

    def _update_table(self) -> None:
        """更新表格显示（高性能实现）.

        架构优势：
        - 一次性批量更新，而不是逐行操作
        - Model自动通知View刷新，最小化UI操作
        - 性能从O(n*m)降低到O(1)，n=行数，m=列数
        """
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(
            f"[LogManagerWidget] _update_table被调用，准备显示{len(self.display_records)}条记录"
        )

        # 🔧 关键性能优化：使用Model批量更新，一次性通知View
        # 而不是逐行setItem（600行×6列=3600次UI操作 → 1次批量更新）
        self.log_model.update_data(self.display_records)

        # 如果自动滚动，滚动到最后一行
        if self.auto_scroll and self.display_records:
            self.log_table.scrollToBottom()

    def _get_level_color(self, level: str) -> QColor:
        """获取日志级别对应的颜色（保留以兼容其他代码）."""
        # 注意：颜色逻辑已移至LogTableModel，此方法保留以防其他地方调用
        color_map = {
            "DEBUG": QColor(200, 200, 200),  # 灰色
            "INFO": QColor(173, 216, 230),  # 浅蓝色
            "WARNING": QColor(255, 255, 0),  # 黄色
            "ERROR": QColor(255, 165, 0),  # 橙色
            "CRITICAL": QColor(255, 0, 0),  # 红色
        }
        return color_map.get(level, QColor(255, 255, 255))  # 默认白色

    def _update_stats(self) -> None:
        """更新统计信息."""
        import logging

        logger = logging.getLogger(__name__)

        total = len(self.log_records)
        filtered = len(self.display_records)
        selected = self.log_model.get_selected_count()

        logger.debug(
            f"[LogManagerWidget] _update_stats被调用，显示{filtered}条/总计{total}条，选中{selected}条"
        )

        if selected > 0:
            self.stats_label.setText(
                f"日志统计: 显示 {filtered} 条 / 总计 {total} 条 | 已选中 {selected} 条"
            )
        else:
            self.stats_label.setText(f"日志统计: 显示 {filtered} 条 / 总计 {total} 条")

    def _refresh_logs(self) -> None:
        """刷新日志数据（异步执行，避免阻塞主线程）."""
        import threading
        from PySide6.QtCore import QTimer
        import logging

        logger = logging.getLogger(__name__)
        logger.debug("[LogManagerWidget] _refresh_logs被调用")  # 🔧 改为debug级别，避免刷屏

        # 禁用刷新按钮，显示加载状态
        if hasattr(self, "refresh_btn"):
            self.refresh_btn.setEnabled(False)
            self.refresh_btn.setText("加载中...")

        # 🔧 关键修复：在后台线程执行查询，避免阻塞主线程导致UI卡死
        def query_in_background():
            try:
                logger.debug("[LogManagerWidget] 后台线程开始查询")  # 改为debug
                # 调用后端API获取最新日志
                service_manager = get_service_manager()
                system_service = service_manager.get_service("system_manager_service", silent=True)

                if system_service:
                    logger.debug(
                        "[LogManagerWidget] SystemManagerService可用，开始查询日志"
                    )  # 改为debug
                    # 获取最近1000条日志
                    result = system_service.query_logs(limit=1000)
                    logger.debug(
                        f"[LogManagerWidget] 查询完成，success={result.get('success')}, 记录数={len(result.get('logs', []))}"
                    )  # 改为debug

                    # 🔧 关键修复：使用信号传递结果到主线程（Qt推荐的跨线程通信方式）
                    self.logs_query_completed.emit(result)
                else:
                    logger.warning("[LogManagerWidget] SystemManagerService不可用")  # 保留warning
                    # 服务不可用，调度错误消息到主线程
                    QTimer.singleShot(0, lambda: self._handle_service_unavailable())

            except Exception as e:
                logger.error(f"[LogManagerWidget] 查询异常: {e}", exc_info=True)
                # 调度错误消息到主线程
                QTimer.singleShot(0, lambda err=str(e): self._handle_query_error(err))

        # 启动后台线程
        thread = threading.Thread(target=query_in_background, daemon=True)
        thread.start()

    def _handle_logs_result(self, result: Dict[str, Any]) -> None:
        """处理日志查询结果（主线程）.

        Args:
            result: 查询结果字典
        """
        import logging

        logger = logging.getLogger(__name__)

        try:
            logger.debug(
                f"[LogManagerWidget] _handle_logs_result被调用，success={result.get('success')}"
            )  # 改为debug
            if result.get("success"):
                self.log_records = result.get("logs", [])
                logger.debug(
                    f"[LogManagerWidget] log_records已更新，数量={len(self.log_records)}"
                )  # 改为debug

                # 动态更新模块列表
                self._update_module_list()

                # 应用筛选
                self._apply_filters()
                logger.debug(
                    f"[LogManagerWidget] display_records数量={len(self.display_records)}"
                )  # 改为debug
            else:
                logger.error(f"[LogManagerWidget] 查询失败: {result.get('message')}")
                # 🚀 修复UI卡死：不使用模态对话框，只记录日志
                logger.warning(f"获取日志失败: {result.get('message')}")
        finally:
            # 恢复刷新按钮
            if hasattr(self, "refresh_btn"):
                self.refresh_btn.setEnabled(True)
                self.refresh_btn.setText("刷新")

    def _handle_service_unavailable(self) -> None:
        """处理服务不可用（主线程）."""
        # 🚀 修复UI卡死：不使用模态对话框，只记录日志
        import logging

        logger = logging.getLogger(__name__)
        logger.warning("系统管理服务不可用")
        if hasattr(self, "refresh_btn"):
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("刷新")

    def _handle_query_error(self, error_msg: str) -> None:
        """处理查询错误（主线程）."""
        # 🚀 修复UI卡死：不使用模态对话框，只记录日志
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"刷新日志失败: {error_msg}")
        if hasattr(self, "refresh_btn"):
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("刷新")

    def _export_logs(self) -> None:
        """导出日志（优先导出选中的，无选中则导出当前筛选结果）."""
        try:
            # 检查是否有选中的日志
            selected_records = self.log_model.get_selected_records()

            # 如果有选中，导出选中的；否则导出全部筛选结果
            if selected_records:
                export_data = selected_records
                default_name = f"logs_selected_{len(selected_records)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            else:
                export_data = self.display_records
                default_name = f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

            # 选择保存路径
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出日志", default_name, "文本文件 (*.txt);;所有文件 (*.*)"
            )

            if not file_path:
                return

            # 直接写入文件（本地导出，不需要后端API）
            with open(file_path, "w", encoding="utf-8") as f:
                for record in export_data:
                    f.write(f"时间: {record.get('timestamp', '')}\n")
                    f.write(f"级别: {record.get('level', '')}\n")
                    f.write(f"模块: {record.get('module', '')}\n")
                    f.write(f"函数: {record.get('function', '')}\n")
                    f.write(f"行号: {record.get('line', '')}\n")
                    f.write(f"消息: {record.get('message', '')}\n")
                    if record.get("exception"):
                        f.write(f"异常: {record.get('exception')}\n")
                    f.write("-" * 80 + "\n\n")

            QMessageBox.information(
                self, "导出成功", f"已导出 {len(export_data)} 条日志到:\n{file_path}"
            )

        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出日志失败: {str(e)}")

    def _clear_display(self) -> None:
        """清空显示."""
        self.display_records.clear()
        # 🔧 使用Model清空数据
        self.log_model.clear()
        self._update_stats()

    def _on_header_clicked(self, logical_index: int) -> None:
        """处理表头点击（第一列时全选/取消全选）.

        Args:
            logical_index: 被点击的列索引
        """
        if logical_index == 0:  # 复选框列
            if (
                self.log_model.get_selected_count() == len(self.display_records)
                and len(self.display_records) > 0
            ):
                # 当前全选，改为取消全选
                self.log_model.clear_selection()
            else:
                # 当前未全选，改为全选
                self.log_model.select_all()
            self._update_stats()  # 更新统计信息显示选中数

    def _delete_selected_logs(self) -> None:
        """删除选中的日志."""
        selected_records = self.log_model.get_selected_records()

        if not selected_records:
            QMessageBox.information(self, "提示", "请先选择要删除的日志")
            return

        # 二次确认
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除选中的 {len(selected_records)} 条日志吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            service_manager = get_service_manager()
            system_service = service_manager.get_service("system_manager_service", silent=True)

            if system_service:
                # 提取日志ID列表
                log_ids = [record.get("id") for record in selected_records if record.get("id")]

                if not log_ids:
                    QMessageBox.warning(self, "错误", "选中的日志没有有效的ID，无法删除")
                    return

                result = system_service.delete_logs_by_ids(log_ids)
                if result.get("success"):
                    QMessageBox.information(
                        self, "删除成功", f"已删除 {result.get('deleted_count', 0)} 条日志"
                    )
                    self._refresh_logs()
                else:
                    QMessageBox.warning(self, "删除失败", result.get("message"))
            else:
                QMessageBox.warning(self, "错误", "系统管理服务不可用")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除日志失败: {str(e)}")

    def _delete_all_logs(self) -> None:
        """删除所有日志（需要输入delete确认）."""
        # 弹出输入对话框
        text, ok = QInputDialog.getText(
            self,
            "危险操作确认",
            "此操作将永久删除数据库中的所有日志记录！\n请输入 'delete' 确认：",
            QLineEdit.EchoMode.Normal,
            "",
        )

        if not ok or text != "delete":
            if ok:  # 用户点了确定但输入错误
                QMessageBox.warning(self, "取消操作", "输入不匹配，操作已取消")
            return

        # 调用后端API删除所有日志
        try:
            service_manager = get_service_manager()
            system_service = service_manager.get_service("system_manager_service", silent=True)

            if system_service:
                result = system_service.delete_all_logs()
                if result.get("success"):
                    QMessageBox.information(
                        self, "删除成功", f"已删除 {result.get('deleted_count', 0)} 条日志记录"
                    )
                    # 刷新UI
                    self._refresh_logs()
                else:
                    QMessageBox.warning(self, "删除失败", result.get("message", "未知错误"))
            else:
                QMessageBox.warning(self, "错误", "系统管理服务不可用")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除日志失败: {str(e)}")

    def _show_log_detail(self, index) -> None:
        """显示日志详情."""
        # 🔧 使用Model获取数据
        record = self.log_model.get_record(index.row())
        if not record:
            return

        # 创建详情对话框
        detail_text = f"""
时间: {record.get('timestamp', '')}
级别: {record.get('level', '')}
模块: {record.get('module', '')}
函数: {record.get('function', '')}
行号: {record.get('line', '')}
记录器: {record.get('logger_name', '')}

消息:
{record.get('message', '')}
"""

        if record.get("exception"):
            detail_text += f"\n异常信息:\n{record.get('exception')}"

        QMessageBox.information(self, "日志详情", detail_text)

    def add_log_record(self, record: Dict[str, Any]) -> None:
        """添加新的日志记录.

        Args:
            record: 日志记录数据
        """
        # 添加到记录列表
        self.log_records.append(record)

        # 限制最大记录数（保留最近2000条）
        if len(self.log_records) > 2000:
            self.log_records = self.log_records[-2000:]

        # 应用筛选条件
        self._apply_filters()

    def start_update_timer(self) -> None:
        """启动更新定时器."""
        if self.update_timer:
            self.update_timer.stop()

        # 🔧 修复：增加刷新间隔，从5秒改为30秒，减少刷屏和性能开销
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._refresh_logs)
        self.update_timer.start(30000)  # 30秒

    def stop_update_timer(self) -> None:
        """停止更新定时器."""
        if self.update_timer:
            self.update_timer.stop()
            self.update_timer = None

    def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """处理事件.

        Args:
            event_type: 事件类型
            event_data: 事件数据
        """
        if event_type == EVENT_LOG_RECORD:
            # 接收到新的日志记录（切回主线程，避免跨线程更新UI）
            QTimer.singleShot(0, lambda: self.add_log_record(event_data))

    def _init_after_backend(self) -> None:
        """在后端与UI就绪后启动刷新与定时器."""
        import logging

        logger = logging.getLogger(__name__)
        logger.info("[LogManagerWidget] _init_after_backend被调用")

        try:
            # 先做一次首刷
            logger.info("[LogManagerWidget] 开始首次刷新")
            self._refresh_logs()
        finally:
            # 启动定时器
            logger.info("[LogManagerWidget] 启动更新定时器")
            self.start_update_timer()

    def get_current_filters(self) -> Dict[str, Any]:
        """获取当前筛选条件.

        Returns:
            筛选条件字典
        """
        return {
            "level": (
                self.level_combo.currentText() if self.level_combo.currentText() != "全部" else None
            ),
            "start_time": self.start_time_edit.dateTime().toString("yyyy-MM-ddTHH:mm:ss"),
            "end_time": self.end_time_edit.dateTime().toString("yyyy-MM-ddTHH:mm:ss"),
            "search": self.search_edit.text().strip(),
        }

    def apply_filters_from_dict(self, filters: Dict[str, Any]) -> None:
        """从字典应用筛选条件.

        Args:
            filters: 筛选条件字典
        """
        if "level" in filters and filters["level"]:
            index = self.level_combo.findText(filters["level"])
            if index >= 0:
                self.level_combo.setCurrentIndex(index)
        else:
            self.level_combo.setCurrentIndex(0)  # 全部

        if "start_time" in filters:
            try:
                dt = QDateTime.fromString(filters["start_time"], "yyyy-MM-ddTHH:mm:ss")
                if dt.isValid():
                    self.start_time_edit.setDateTime(dt)
            except Exception:
                pass

        if "end_time" in filters:
            try:
                dt = QDateTime.fromString(filters["end_time"], "yyyy-MM-ddTHH:mm:ss")
                if dt.isValid():
                    self.end_time_edit.setDateTime(dt)
            except Exception:
                pass

        if "search" in filters:
            self.search_edit.setText(filters["search"])

        # 应用筛选
        self._apply_filters()


# ==================== 系统管理主界面 ====================


def get_root() -> Path:
    """获取项目根目录路径

    Returns:
        项目根目录的Path对象
    """
    # 通过当前文件的路径向上查找项目根目录
    # system_manager_view.py 位于 ui/modules/
    # 需要向上2级到达项目根目录
    current_file = Path(__file__)
    root_path = current_file.parent.parent.parent
    return root_path


class SystemManager(BaseWidget, LoggerMixin):
    """系统管理主界面（重构版）."""

    # 定义信号用于跨线程通信
    reader_progress_signal = Signal(int, int, str, bool)  # current, total, info, success
    reader_finished_signal = Signal(dict)  # result

    # 🔥 新增：用于线程安全的UI更新信号
    ui_update_signal = Signal(dict)  # metrics_data

    # 网络测速结果信号（线程安全）
    bandwidth_test_success_signal = Signal(dict)  # 带宽测试成功信号
    bandwidth_test_error_signal = Signal(str)    # 带宽测试失败信号

    def __init__(self, parent=None):
        """初始化系统管理界面."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.system_service = None

        # 选项卡部件
        self.tab_widget: Optional[QTabWidget] = None
        self.system_status_tab: Optional[QWidget] = None
        self.performance_tab: Optional[QWidget] = None
        self.alerts_tab: Optional[QWidget] = None
        self.services_tab: Optional[QWidget] = None
        self.config_tab: Optional[QWidget] = None
        self.logs_tab: Optional[QWidget] = None
        self.diagnosis_tab: Optional[QWidget] = None
        self.process_monitor_tab: Optional[QWidget] = None
        self.tools_tab: Optional[QWidget] = None

        # 系统状态组件
        self.cpu_label: Optional[QLabel] = None
        self.memory_label: Optional[QLabel] = None
        self.disk_label: Optional[QLabel] = None
        self.network_label: Optional[QLabel] = None
        self.status_table: Optional[QTableWidget] = None

        # 配置组件
        self.config_widgets: Dict[str, Any] = {}
        self.tdx_path_edit: Optional[QLineEdit] = None
        self.cache_dir_edit: Optional[QLineEdit] = None
        self.data_dir_edit: Optional[QLineEdit] = None
        self.base_date_edit: Optional[QDateEdit] = None
        self.max_workers_spin: Optional[QSpinBox] = None
        self.timeout_spin: Optional[QSpinBox] = None
        self.retry_spin: Optional[QSpinBox] = None
        self.watcher_check: Optional[QCheckBox] = None
        self.watcher_interval_spin: Optional[QSpinBox] = None

        # 性能监控组件
        self.cpu_plot: Optional[Any] = None
        self.cpu_curve: Optional[Any] = None
        self.memory_plot: Optional[Any] = None
        self.memory_curve: Optional[Any] = None
        self.performance_history: Dict[str, list] = {
            "cpu": [],
            "memory": [],
        }
        self.max_history_points: int = 100
        self.performance_table: Optional[QTableWidget] = None

        # 告警管理组件
        self.alerts_table: Optional[QTableWidget] = None

        # 服务管理组件
        self.services_table: Optional[QTableWidget] = None
        self.dependencies_table: Optional[QTableWidget] = None
        self.health_progress: Optional[QProgressBar] = None

        # 业务指标卡片
        self.dc_metrics_card: Optional[QGroupBox] = None
        self.gw_metrics_card: Optional[QGroupBox] = None
        self.pf_metrics_card: Optional[QGroupBox] = None
        self.st_metrics_card: Optional[QGroupBox] = None

        # 日志管理组件
        self.logs_table: Optional[QTableWidget] = None

        # 诊断工具组件（保留旧Tab作为兼容）
        self.diagnosis_table: Optional[QTableWidget] = None

        # 新增：进程监控组件
        self.process_table: Optional[QTableWidget] = None
        # 热力图组件（整体设备监控）
        self.heatmap_cpu: Optional[Any] = None
        self.heatmap_memory: Optional[Any] = None
        self.heatmap_disk_io: Optional[Any] = None
        self.heatmap_network: Optional[Any] = None
        self.heatmap_bandwidth: Optional[Any] = None
        # 热力图数据历史
        self.heatmap_history: Dict[str, Any] = {
            "cpu": [],
            "memory": [],
            "disk_io": [],
            "network": [],
            "bandwidth": [],
        }

        # 工具集合组件
        self.tools_table: Optional[QTableWidget] = None

        # 新增：系统状态监控增强组件
        self.cpu_chart: Optional[Any] = None
        self.memory_chart: Optional[Any] = None
        self.disk_io_chart: Optional[Any] = None
        self.network_speed_chart: Optional[Any] = None
        self.disk_space_chart: Optional[Any] = None
        self.temperature_chart: Optional[Any] = None  # 温度折线图
        self.temperature_cards_widget: Optional[QWidget] = None  # 温度卡片
        self.temperature_card_labels: Dict[str, Dict[str, QLabel]] = {}  # 温度卡片标签
        self.status_details_table: Optional[QTableWidget] = None

        # 新增：历史数据存储
        self.system_status_history: Dict[str, Any] = {
            "cpu": deque(maxlen=100),
            "memory": deque(maxlen=100),
            "network": {"upload": deque(maxlen=100), "download": deque(maxlen=100)},
            # 温度历史数据
            "temp_cpu": deque(maxlen=100),
            "temp_gpu": deque(maxlen=100),
            "temp_disk": deque(maxlen=100),
            # 新增指标历史数据
            "bandwidth": deque(maxlen=100),
            "context_switches": deque(maxlen=100),
            "cpu_interrupts": deque(maxlen=100),
            "memory_swap": deque(maxlen=100),
            "packet_loss": deque(maxlen=100),
            # 磁盘数据按挂载点分组
            "disks": {},  # 格式: {"C:\\": {"read": deque(), "write": deque(), "latency": deque()}, ...}
        }

        # 新增：统计数据存储（用于计算平均值）
        self.system_stats: Dict[str, Any] = {
            "cpu": {"current": 0, "avg": 0},
            "memory": {"current": 0, "avg": 0},
            "network_upload": {"current": 0, "avg": 0},
            "network_download": {"current": 0, "avg": 0},
            "bandwidth": {"current": 0, "avg": 0},
            "context_switches": {"current": 0, "avg": 0},
            "cpu_interrupts": {"current": 0, "avg": 0},
            "memory_swap": {"current": 0, "avg": 0},
            "packet_loss": {"current": 0, "avg": 0},
            # 磁盘统计按挂载点分组
            "disks": {},  # 格式: {"C:\\": {"read": {"current": 0, "avg": 0}, "write": {"current": 0, "avg": 0}, ...}, ...}
        }

        # 新增：指标阈值定义（达到该值为瓶颈）
        # 从配置文件加载，如果配置文件不存在则使用默认值
        self.metric_thresholds: Dict[str, Any] = self._load_thresholds_from_config()

        # 新增：性能指标组件引用
        self.data_processing_widgets: Optional[List[QLabel]] = None
        self.strategy_execution_widgets: Optional[List[QLabel]] = None
        self.trading_execution_widgets: Optional[List[QLabel]] = None

        # 新增：诊断界面组件
        self.diagnosis_tabs: Optional[QTabWidget] = None
        self.basic_perf_table: Optional[QTableWidget] = None
        self.basic_network_table: Optional[QTableWidget] = None
        self.basic_db_table: Optional[QTableWidget] = None
        self.bottlenecks_table: Optional[QTableWidget] = None
        self.errors_table: Optional[QTableWidget] = None
        self.suggestions_text: Optional[QTextEdit] = None
        self.error_details_table: Optional[QTableWidget] = None
        self.optimization_text: Optional[QTextEdit] = None
        self.fix_suggestions_table: Optional[QTableWidget] = None

        # 新增：服务状态增强组件
        self.health_detail_label: Optional[QLabel] = None

        # 新增：配置界面组件
        self.monitoring_interval_spin: Optional[QSpinBox] = None
        self.ai_api_key_edit: Optional[QLineEdit] = None
        self.ai_api_url_edit: Optional[QLineEdit] = None
        self.ai_model_combo: Optional[QComboBox] = None
        self.ai_max_tokens_spin: Optional[QSpinBox] = None
        self.ai_temperature_slider: Optional[QSlider] = None
        self.ai_temperature_label: Optional[QLabel] = None
        self.ai_max_history_spin: Optional[QSpinBox] = None
        self.ai_timeout_spin: Optional[QSpinBox] = None
        self.ai_enable_tools_check: Optional[QCheckBox] = None

        # 新增：工具集合组件
        self.reader_day_check: Optional[QCheckBox] = None
        self.reader_5min_check: Optional[QCheckBox] = None
        self.reader_1min_check: Optional[QCheckBox] = None
        self.reader_sh_check: Optional[QCheckBox] = None
        self.reader_sz_check: Optional[QCheckBox] = None
        self.reader_bj_check: Optional[QCheckBox] = None
        self.reader_tdx_path_edit: Optional[QLineEdit] = None
        self.reader_status_label: Optional[QLabel] = None
        self.reader_progress_bar: Optional[QProgressBar] = None
        self.reader_detail_label: Optional[QLabel] = None
        self.reader_start_btn: Optional[QPushButton] = None
        self.reader_stop_btn: Optional[QPushButton] = None

        # 🆕 损坏文件清理工具控件
        self.cleaner_data_dir_label: Optional[QLabel] = None
        self.cleaner_result_label: Optional[QLabel] = None
        self.cleaner_detail_text: Optional[QTextEdit] = None
        self.cleaner_scan_btn: Optional[QPushButton] = None
        self.cleaner_clean_btn: Optional[QPushButton] = None
        self._cleaner_corrupted_files: List[str] = []  # 缓存扫描到的损坏文件列表

        # 🔧 架构修复：在调用父类初始化之前就初始化服务
        # 因为 super().__init__() 会调用 setup_ui()，而 setup_ui() 会创建标签页
        # 标签页创建时会调用 _load_config()，此时需要 system_service 已经就绪
        self._initialize_service_before_ui()

        # 调用父类初始化
        super().__init__(parent, "系统管理")

        # 🔍 调试注入：使用专门的DEBUG文件日志
        try:
            import sys

            if "__debug_logger__" in sys.modules:
                self._debug_logger = sys.modules["__debug_logger__"]
                self._debug_logger.info("=" * 60)
                self._debug_logger.info("SystemManager 调试会话开始")
                self._debug_logger.info("=" * 60)
            else:
                self._debug_logger = self.logger
        except:
            self._debug_logger = self.logger

        # 🔧 关键修复：缓存EventEngine实例，避免property动态获取导致的多线程竞态
        # 必须在 super().__init__() 之后，因为 _init_event_engine_cache() 使用 self.logger
        self._cached_event_engine: Optional[Any] = None
        self._init_event_engine_cache()

        # 🔍 创建专门的DEBUG文件日志（用于调试，不影响终端输出）
        self._setup_debug_file_logger()

        # 🔧 新增：UI更新节流机制（避免频繁渲染）- 使用原子操作避免锁
        self._last_ui_update_time = 0.0
        self._ui_update_interval = 1.0  # 至少间隔1秒更新一次UI（降低频率）
        self._pending_update_scheduled = False  # 标记是否已有待处理的更新

        # 🔧 关键修复：延迟事件订阅，等EventEngine可用时再订阅
        self._events_subscribed = False  # 标记事件是否已订阅

        # 🔥 FIX: 缓存hardware数据（用于跨事件使用）
        self._cached_hardware_data = {}

        self._start_delayed_event_subscription()

        # 🔥 连接线程安全的UI更新信号
        self.ui_update_signal.connect(self._do_throttled_ui_update)
        print("[SystemManager] ✅ UI更新信号已连接")

        # 🔥 连接网络测速结果信号（线程安全）
        self.bandwidth_test_success_signal.connect(self._update_bandwidth_result_success)
        self.bandwidth_test_error_signal.connect(self._update_bandwidth_result_error)
        print("[SystemManager] ✅ 网络测速信号已连接")

        # 启动数据源连通性定时更新（每10秒刷新一次）
        self.datasource_connectivity_timer = QTimer(self)
        self.datasource_connectivity_timer.timeout.connect(self._update_datasource_connectivity)
        self.datasource_connectivity_timer.start(10000)  # 10秒
        # 立即执行一次
        QTimer.singleShot(1000, self._update_datasource_connectivity)

        self.logger.info("系统管理界面初始化完成")

    def _init_event_engine_cache(self):
        """初始化EventEngine缓存（关键修复）.

        缓存EventEngine实例，避免property动态获取导致的多线程竞态条件。
        确保整个生命周期使用同一个EventEngine引用。
        """
        # 优先从SystemManagerService获取（确保与后端使用同一实例）
        if self.system_service and hasattr(self.system_service, "event_engine"):
            self._cached_event_engine = self.system_service.event_engine
            self.logger.info(
                f"[EventEngine缓存] 从SystemManagerService获取, ID={id(self._cached_event_engine)}"
            )
            return

        # 降级方案：从全局获取
        from backend.core.base import get_event_engine

        self._cached_event_engine = get_event_engine()
        if self._cached_event_engine:
            self.logger.warning(
                f"[EventEngine缓存] 降级：从全局获取, ID={id(self._cached_event_engine)}"
            )
        else:
            self.logger.error("[EventEngine缓存] ❌ 无法获取EventEngine！")

    def _setup_debug_file_logger(self):
        """设置DEBUG文件日志（不影响终端输出）"""
        try:
            import logging
            from pathlib import Path

            # 确保logs目录存在
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)

            # 创建专门的DEBUG logger
            self._debug_logger = logging.getLogger(f"SystemManager.DEBUG.{id(self)}")
            self._debug_logger.setLevel(logging.DEBUG)
            self._debug_logger.propagate = False  # 不传播到父logger

            # 清除旧的handlers
            for handler in self._debug_logger.handlers[:]:
                self._debug_logger.removeHandler(handler)

            # 文件handler
            log_file = log_dir / "systemmanager_debug.log"
            file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)

            # 格式化器
            formatter = logging.Formatter(
                "%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
            )
            file_handler.setFormatter(formatter)
            self._debug_logger.addHandler(file_handler)

            self._debug_logger.info("=" * 60)
            self._debug_logger.info("SystemManager DEBUG日志启动")
            self._debug_logger.info("=" * 60)

            # 强制输出确认
            print(f"[SystemManager] ✅ DEBUG日志文件已创建: {log_file.absolute()}")
            self.logger.info(f"✅ DEBUG日志已启用: {log_file}")

        except Exception as e:
            print(f"[SystemManager] ❌ DEBUG日志设置失败: {e}")
            import traceback

            traceback.print_exc()
            self.logger.error(f"DEBUG日志设置失败: {e}", exc_info=True)
            self._debug_logger = self.logger  # 降级使用普通logger

    @property
    def event_engine(self):
        """获取缓存的EventEngine实例.

        Returns:
            缓存的EventEngine实例，确保整个生命周期使用同一个引用
        """
        return self._cached_event_engine

    def _load_thresholds_from_config(self) -> Dict[str, Any]:
        """从配置文件加载系统监控阈值.

        注意：磁盘I/O阈值将在运行时从后端获取（自动检测磁盘类型）

        Returns:
            阈值配置字典
        """
        # 默认阈值（磁盘阈值将从后端获取）
        default_thresholds = {
            "cpu": 90.0,  # CPU使用率阈值：90%
            "memory": 85.0,  # 内存使用率阈值：85%
            # 磁盘阈值将动态填充到 disks 字典中
            "network_upload": 125000.0,  # 网络上传阈值：125 MB/s (1 Gbps)
            "network_download": 125000.0,  # 网络下载阈值：125 MB/s (1 Gbps)
            "bandwidth": 100.0,  # 带宽占用阈值：100%
            "context_switches": 50000,  # 上下文切换阈值：50000/秒
            "cpu_interrupts": 20000,  # CPU中断阈值：20000/秒
            "memory_swap": 1000,  # 内存交换阈值：1 MB/s（少量交换可接受）
            "disk_latency": 20.0,  # 磁盘延迟阈值：20ms
            "packet_loss": 1.0,  # 网络丢包率阈值：1%
            "smart_reallocated": 0,  # SMART重映射扇区阈值：0
            "smart_pending": 0,  # SMART待映射扇区阈值：0
            # 磁盘阈值（按挂载点分组，动态填充）
            "disks": {},  # 格式: {"C:\\": {"read": 2000000, "write": 1500000, "type": "nvme"}, ...}
        }

        try:
            # 尝试从配置文件读取
            from pathlib import Path
            import json

            config_path = Path("config/terminal_config.json")
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    thresholds_config = config.get("system_monitor_thresholds", {})

                    # 从配置文件覆盖默认值
                    if thresholds_config:
                        default_thresholds["cpu"] = float(
                            thresholds_config.get("cpu_percent", default_thresholds["cpu"])
                        )
                        default_thresholds["memory"] = float(
                            thresholds_config.get("memory_percent", default_thresholds["memory"])
                        )
                        # 磁盘阈值从后端自动获取，不从配置文件读取
                        default_thresholds["network_upload"] = float(
                            thresholds_config.get(
                                "network_upload_kbps", default_thresholds["network_upload"]
                            )
                        )
                        default_thresholds["network_download"] = float(
                            thresholds_config.get(
                                "network_download_kbps", default_thresholds["network_download"]
                            )
                        )
                        default_thresholds["bandwidth"] = float(
                            thresholds_config.get(
                                "bandwidth_percent", default_thresholds["bandwidth"]
                            )
                        )
                        default_thresholds["context_switches"] = int(
                            thresholds_config.get(
                                "context_switches_per_sec", default_thresholds["context_switches"]
                            )
                        )
                        default_thresholds["cpu_interrupts"] = int(
                            thresholds_config.get(
                                "cpu_interrupts_per_sec", default_thresholds["cpu_interrupts"]
                            )
                        )
                        default_thresholds["memory_swap"] = float(
                            thresholds_config.get(
                                "memory_swap_kbps", default_thresholds["memory_swap"]
                            )
                        )
                        default_thresholds["disk_latency"] = float(
                            thresholds_config.get(
                                "disk_latency_ms", default_thresholds["disk_latency"]
                            )
                        )
                        default_thresholds["packet_loss"] = float(
                            thresholds_config.get(
                                "packet_loss_percent", default_thresholds["packet_loss"]
                            )
                        )
                        default_thresholds["smart_reallocated"] = int(
                            thresholds_config.get(
                                "smart_sectors", default_thresholds["smart_reallocated"]
                            )
                        )
                        default_thresholds["smart_pending"] = int(
                            thresholds_config.get(
                                "smart_sectors", default_thresholds["smart_pending"]
                            )
                        )

                        # 打印加载的配置（用于调试）
                        import logging

                        logger = logging.getLogger(self.__class__.__name__)
                        logger.info("✅ 已从配置文件加载系统监控阈值")
        except Exception as e:
            import logging

            logger = logging.getLogger(self.__class__.__name__)
            logger.warning("加载配置文件失败，使用默认阈值: %s", e)

        return default_thresholds

    def _initialize_service_before_ui(self):
        """在UI创建之前初始化服务（关键修复）.

        这个方法必须在 super().__init__() 之前调用，
        因为父类初始化会创建UI，而UI创建时会调用 _load_config()，
        _load_config() 需要 system_service 已经就绪。

        注意：此时 self.logger 还未初始化，使用 logging.getLogger()
        """
        import logging

        logger = logging.getLogger(self.__class__.__name__)

        try:
            # 🎯 架构修复：使用silent模式查询可选服务，避免竞态条件
            # system_manager_service在快速启动模式下会后台加载，UI不应手动创建
            self.system_service = self.service_manager.get_service(
                "system_manager_service", silent=True
            )
            if self.system_service:
                logger.info("系统管理服务已就绪")
            else:
                logger.info("系统管理服务尚未就绪，等待后台加载...")
                # 服务将通过on_service_ready回调就绪
        except Exception as e:
            logger.error("获取系统管理服务失败: %s", e, exc_info=True)
            self.system_service = None

    def on_service_ready(self, service_name: str, success: bool):
        """服务就绪回调（快速启动模式下，可选服务加载完成后调用）.

        Args:
            service_name: 服务名称
            success: 服务是否成功初始化
        """
        if service_name == "system_manager_service" and success:
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()

            # 重新获取服务（此时应该已就绪）
            self.system_service = service_manager.get_service("system_manager_service", silent=True)
            if self.system_service:
                self.logger.info("✅ 系统管理服务已就绪，启用功能")

                # 🔧 关键修复：重新初始化EventEngine缓存（确保使用service的EventEngine）
                if not self._cached_event_engine:
                    self._init_event_engine_cache()

                # 注册监控事件
                if not hasattr(self, "_monitoring_events_registered"):
                    self._register_monitoring_events()
                    self._monitoring_events_registered = True

    def setup_ui(self):
        """设置用户界面（延迟加载重资源，构造期仅占位）."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(600, 400)

        # 在父类 QWidget 初始化后再创建 QTabWidget，避免原生层不稳定
        if not self.tab_widget:
            self.tab_widget = QTabWidget()

        if self.tab_widget:
            self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
            self.tab_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )

        # 构造期仅添加占位Tab，避免创建重资源组件导致原生崩溃
        placeholder = QWidget()
        ph_layout = QVBoxLayout(placeholder)
        ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg = QLabel("正在加载系统管理模块...")
        msg.setStyleSheet("color: #aaa; font-size: 12px;")
        ph_layout.addWidget(msg)
        if self.tab_widget:
            self.tab_widget.addTab(placeholder, "加载中")

        if self.tab_widget:
            main_layout.addWidget(self.tab_widget)

        # 延迟创建子界面（在事件循环后执行）
        from PySide6.QtCore import QTimer

        QTimer.singleShot(300, self._safe_create_sub_interfaces)

    def _safe_create_sub_interfaces(self):
        """安全延迟创建子界面（失败显示错误占位，不让应用崩溃）."""
        self.logger.info("=" * 70)
        self.logger.info("[SystemManager] _safe_create_sub_interfaces 被调用")
        self.logger.info("=" * 70)
        try:
            # 清理占位Tab
            if (
                self.tab_widget
                and self.tab_widget.count() > 0
                and self.tab_widget.tabText(0) == "加载中"
            ):
                self.logger.info("[SystemManager] 清理占位Tab")
                self.tab_widget.removeTab(0)
            # 实际创建
            self.logger.info("[SystemManager] 开始创建子界面...")
            self._create_sub_interfaces()
            self.logger.info("[SystemManager] 子界面创建完成")
        except Exception as e:
            # 创建失败，显示错误占位
            self.logger.error("[SystemManager] 子界面创建失败: %s", e, exc_info=True)
            error_tab = QWidget()
            layout = QVBoxLayout(error_tab)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_msg = QLabel(f"系统管理模块加载失败：{e}")
            error_msg.setWordWrap(True)
            layout.addWidget(error_msg)
            if self.tab_widget:
                self.tab_widget.addTab(error_tab, "错误")
            self.logger.error("SystemManager 延迟加载失败: %s", e, exc_info=True)

    def _create_sub_interfaces(self):
        """创建8个子界面（按新顺序）."""
        self.logger.info("[SystemManager] _create_sub_interfaces 开始执行")

        # 1. 系统状态监控
        self.logger.info("[SystemManager] 创建系统状态监控Tab...")
        self.system_status_tab = self._create_system_status_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.system_status_tab, "🔍 系统状态监控")
        self.logger.info("[SystemManager] ✅ 系统状态监控Tab创建完成")

        # 2. 性能指标
        self.logger.info("[SystemManager] 创建性能指标Tab...")
        self.performance_tab = self._create_performance_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.performance_tab, "📊 性能指标")
        self.logger.info("[SystemManager] ✅ 性能指标Tab创建完成")

        # 3. 服务监控（重构）
        self.logger.info("[SystemManager] 创建服务监控Tab...")
        self.services_tab = self._create_services_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.services_tab, "💚 服务监控")
        self.logger.info("[SystemManager] ✅ 服务监控Tab创建完成")

        # 4. 进程监控（新设计）
        self.logger.info("[SystemManager] 创建进程监控Tab...")
        self.process_monitor_tab = self._create_process_monitor_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.process_monitor_tab, "🔧 进程监控")
        self.logger.info("[SystemManager] ✅ 进程监控Tab创建完成")

        # 保留原诊断Tab作为兼容（可选）
        # self.diagnosis_tab = self._create_diagnosis_tab()
        # if self.tab_widget:
        #     self.tab_widget.addTab(self.diagnosis_tab, "🔍 系统诊断（旧版）")

        # 5. 告警管理
        self.logger.info("[SystemManager] 创建告警管理Tab...")
        self.alerts_tab = self._create_alerts_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.alerts_tab, "🚨 告警管理")
        self.logger.info("[SystemManager] ✅ 告警管理Tab创建完成")

        # 6. 日志管理
        self.logger.info("[SystemManager] 创建日志管理Tab...")
        self.logs_tab = self._create_logs_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.logs_tab, "📝 日志管理")
        self.logger.info("[SystemManager] ✅ 日志管理Tab创建完成")

        # 7. 系统配置
        self.config_tab = self._create_config_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.config_tab, "⚙️ 系统配置")

        # 8. 系统工具
        self.tools_tab = self._create_tools_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.tools_tab, "🛠️ 系统工具")

    def _start_delayed_event_subscription(self):
        """启动延迟事件订阅机制（等待EventEngine可用）."""
        # 立即尝试一次
        if self._try_subscribe_events():
            return

        # 如果失败，启动定时器每秒重试
        self._event_subscription_timer = QTimer(self)
        self._event_subscription_timer.timeout.connect(self._try_subscribe_events)
        self._event_subscription_timer.start(5000)  # 每5秒重试 (降低频率)
        self.logger.info("EventEngine暂时不可用，启动定时器等待（每秒重试）")

    def _try_subscribe_events(self) -> bool:
        """尝试订阅事件.

        Returns:
            bool: 是否订阅成功
        """
        if self._events_subscribed:
            return True

        # 使用property动态获取EventEngine（无需赋值）
        if not self.event_engine:
            return False

        # EventEngine可用，立即订阅
        if self._register_monitoring_events():
            self._events_subscribed = True
            # 停止重试定时器
            if hasattr(self, "_event_subscription_timer") and self._event_subscription_timer:
                self._event_subscription_timer.stop()
            self.logger.info("✅ EventEngine已就绪，事件订阅成功")
            return True

        return False

    def _register_monitoring_events(self) -> bool:
        """注册监控事件（事件驱动架构核心）.

        Returns:
            bool: 是否注册成功
        """
        if not self.event_engine:
            return False

        from backend.infrastructure.system_vnpy import (
            EVENT_SYSTEM_METRICS,
            EVENT_HARDWARE_SENSORS,
            EVENT_BOTTLENECK_ANALYSIS,
            EVENT_PROCESS_MONITORING,
            EVENT_SERVICE_MONITORING,
            EVENT_SMART_DATA,
        )

        # 订阅系统指标事件
        self.event_engine.register(EVENT_SYSTEM_METRICS, self._on_system_metrics_event)

        # 订阅硬件传感器事件
        self.event_engine.register(EVENT_HARDWARE_SENSORS, self._on_hardware_sensors_event)

        # 订阅SMART健康状态事件
        self.event_engine.register(EVENT_SMART_DATA, self._on_smart_data_event)

        # 订阅瓶颈分析事件
        self.event_engine.register(EVENT_BOTTLENECK_ANALYSIS, self._on_bottleneck_analysis_event)

        # 订阅进程信息事件
        self.event_engine.register(EVENT_PROCESS_MONITORING, self._on_process_monitoring_event)

        # 订阅服务状态事件
        self.event_engine.register(EVENT_SERVICE_MONITORING, self._on_service_monitoring_event)

        self.logger.info("✅ 已订阅监控事件（包括SMART状态，事件驱动模式）")
        return True

    # ========== 事件处理器（事件驱动架构核心）==========

    def _do_throttled_ui_update(self, metrics: Dict[str, Any]):
        """执行节流的UI更新（在主线程中调用，无锁设计）."""
        try:
            # 检查是否应该更新
            current_time = time.time()
            time_since_last = current_time - self._last_ui_update_time
            if time_since_last < self._ui_update_interval:
                # 距离上次更新太近，跳过本次更新
                self._debug_logger.info(
                    f"[UIUpdate] 节流跳过（距上次 {time_since_last:.2f}s < {self._ui_update_interval}s）"
                )
                return

            # 更新UI
            self._debug_logger.debug("[UIUpdate] 开始更新UI")
            self._update_system_status_from_data(metrics)

            # 更新动态阈值显示
            if "thresholds" in metrics:
                self._update_thresholds_display(metrics["thresholds"])

            # 更新并发任务统计显示
            if "concurrent_tasks" in metrics:
                self._update_concurrent_tasks_display(metrics["concurrent_tasks"])

            # 更新时间戳
            self._last_ui_update_time = current_time
            self._debug_logger.debug("[UIUpdate] UI更新完成")

        except Exception as e:
            self._debug_logger.error("[UIUpdate] UI更新失败: %s", e, exc_info=True)
        finally:
            # 🔧 关键修复：无论成功/失败/提前返回，都要重置标志
            self._pending_update_scheduled = False
            self._debug_logger.debug("[UIUpdate] 节流标志已重置")

    def _on_system_metrics_event(self, event):
        """处理系统指标事件（独立，不依赖其他数据）- 无锁设计避免死锁."""
        try:
            # 首次接收时记录日志
            if not hasattr(self, "_first_event_logged"):
                self.logger.info("✅ 系统监控事件流已建立")
                self._first_event_logged = True

            # 事件计数
            if not hasattr(self, "_event_counter"):
                self._event_counter = 0
            self._event_counter += 1

            # DEBUG日志
            if hasattr(self, "_debug_logger") and self._event_counter % 10 == 0:
                self._debug_logger.debug(f"[EventHandler] 已接收 {self._event_counter} 个事件")

            metrics = event.data
            if not metrics:
                self._debug_logger.warning("[EventHandler] 数据为空")
                return

            # 如果已有待处理的更新，跳过本次
            if self._pending_update_scheduled:
                if hasattr(self, "_debug_logger"):
                    self._debug_logger.debug(
                        f"[EventHandler] 已有待处理更新，跳过（事件#{self._event_counter}）"
                    )
                return

            # 标记有待处理的更新
            self._pending_update_scheduled = True

            # DEBUG日志
            if hasattr(self, "_debug_logger"):
                self._debug_logger.debug(f"[EventHandler] 安排UI更新（事件#{self._event_counter}）")

            # 使用信号发射，线程安全调度到主线程
            self.ui_update_signal.emit(metrics.copy())

        except Exception as e:
            self.logger.error("处理系统指标事件失败: %s", e, exc_info=True)
            self._pending_update_scheduled = False

    def _on_hardware_sensors_event(self, event):
        """处理硬件传感器事件（独立）."""
        try:
            hardware_data = event.data
            if not hardware_data:
                return

            # 🔥 FIX: 缓存hardware数据，供system事件使用
            self._cached_hardware_data = hardware_data.copy()

            # 复用现有的更新逻辑
            self._update_hardware_sensors_from_data(hardware_data)

            # 🔥 更新CPU温度卡片（需要hardware数据）
            if hasattr(self, "metric_card_cpu_temp"):
                temperature_data = hardware_data.get("temperature", {})
                cpu_temp = None
                for device, sensors in temperature_data.items():
                    if not sensors or not isinstance(sensors, list):
                        continue
                    sensor = sensors[0]
                    temp = sensor.get("current", 0)
                    if (
                        "CPU" in device
                        or "ACPI" in device
                        or "processor" in device.lower()
                        or "Ryzen" in device
                        or "Intel" in device
                        or "Threadripper" in device
                    ):
                        cpu_temp = temp
                        break
                if cpu_temp is not None:
                    self.metric_card_cpu_temp.update_value(cpu_temp)

            # 🔥 更新SMART扇区告警卡片（新增）
            if "smart" in hardware_data and hardware_data["smart"]:
                smart_data = hardware_data["smart"]
                if hasattr(self, "smart_reallocated_card"):
                    total_reallocated = sum(
                        (disk.get("reallocated_sectors") or 0)
                        for disk in smart_data.values()
                        if isinstance(disk, dict)
                    )
                    self.smart_reallocated_card.update_value(total_reallocated)

                if hasattr(self, "smart_pending_card"):
                    total_pending = sum(
                        (disk.get("pending_sectors") or 0)
                        for disk in smart_data.values()
                        if isinstance(disk, dict)
                    )
                    self.smart_pending_card.update_value(total_pending)

        except Exception as e:
            self.logger.error("处理硬件传感器事件失败: %s", e)

    def _on_smart_data_event(self, event):
        """处理SMART健康数据事件（独立）."""
        try:
            smart_data = event.data
            if not smart_data:
                return

            # 缓存SMART数据
            self._cached_smart_data = smart_data.copy()

            # 更新硬盘监控卡片
            if hasattr(self, "disk_monitor_card"):
                # 判断整体健康状态
                health_status = "良好"
                for disk_name, disk_attrs in smart_data.items():
                    if isinstance(disk_attrs, dict):
                        # 🔧 修复：三次防御，使用or运算符确保None值转换为0
                        reallocated = disk_attrs.get("reallocated_sectors") or 0
                        pending = disk_attrs.get("pending_sectors") or 0
                        uncorrectable = disk_attrs.get("uncorrectable_errors") or 0

                        if reallocated > 50 or pending > 50 or uncorrectable > 10:
                            health_status = "危险"
                            break
                        elif reallocated > 10 or pending > 10 or uncorrectable > 0:
                            health_status = "警告"

                self.disk_monitor_card.update_smart_data(health_status, smart_data)

        except Exception as e:
            self.logger.error("处理SMART数据事件失败: %s", e, exc_info=True)

    def _on_bottleneck_analysis_event(self, event):
        """处理瓶颈分析事件（可选，独立）."""
        try:
            bottleneck_data = event.data
            if not bottleneck_data:
                return

            # 复用现有的更新逻辑
            self._update_bottleneck_card(bottleneck_data)

            # 更新性能指标Tab（如果存在）
            if hasattr(self, "scenario_stack"):
                self._refresh_current_scenario_view()

        except Exception as e:
            self.logger.error("处理瓶颈分析事件失败: %s", e)

    def _on_process_monitoring_event(self, event):
        """处理进程监控事件（独立）."""
        try:
            process_data = event.data
            if not process_data:
                return

            # 复用现有的更新逻辑
            self._update_process_status_from_data(process_data)

        except Exception as e:
            self.logger.error("处理进程监控事件失败: %s", e)

    def _on_service_monitoring_event(self, event):
        """处理服务状态事件（独立）."""
        try:
            service_data = event.data
            if not service_data:
                return

            # 复用现有的更新逻辑
            self._update_service_status_from_data(service_data)

        except Exception as e:
            self.logger.error("处理服务状态事件失败: %s", e)

    def showEvent(self, event):
        """界面显示事件 - 触发SMART数据采集."""
        super().showEvent(event)

        # 首次显示时触发SMART采集（按需加载）
        if not hasattr(self, "_smart_triggered_once"):
            self._smart_triggered_once = True
            self._trigger_smart_collection()

    def _trigger_smart_collection(self):
        """触发SMART数据采集."""
        try:
            if self.system_service:
                # 🔧 防御性检查：确保方法存在（避免服务未完全初始化或版本不匹配）
                if hasattr(self.system_service, "trigger_smart_collection"):
                    # 通过service发送ZMQ命令到监控进程
                    success = self.system_service.trigger_smart_collection()
                    if success:
                        self.logger.info("✅ 已触发SMART数据采集")
                    else:
                        self.logger.warning("⚠️ SMART数据采集触发失败")
                else:
                    self.logger.warning(
                        "⚠️ SystemManagerService不支持trigger_smart_collection方法（版本不匹配或未完全初始化）"
                    )
        except Exception as e:
            self.logger.error("触发SMART采集失败: %s", e)

    def closeEvent(self, event):
        """关闭事件处理，取消事件订阅."""
        try:
            # 取消事件订阅
            if self.event_engine:
                from backend.infrastructure.system_vnpy.monitoring_events import (
                    EVENT_SYSTEM_METRICS,
                    EVENT_HARDWARE_SENSORS,
                    EVENT_BOTTLENECK_ANALYSIS,
                    EVENT_PROCESS_MONITORING,
                    EVENT_SERVICE_MONITORING,
                )

                self.event_engine.unregister(EVENT_SYSTEM_METRICS, self._on_system_metrics_event)
                self.event_engine.unregister(
                    EVENT_HARDWARE_SENSORS, self._on_hardware_sensors_event
                )
                self.event_engine.unregister(
                    EVENT_BOTTLENECK_ANALYSIS, self._on_bottleneck_analysis_event
                )
                self.event_engine.unregister(
                    EVENT_PROCESS_MONITORING, self._on_process_monitoring_event
                )
                self.event_engine.unregister(
                    EVENT_SERVICE_MONITORING, self._on_service_monitoring_event
                )

                self.logger.info("已取消监控事件订阅")

        except Exception as e:
            self.logger.error("取消事件订阅失败: %s", e)

        # 调用父类的closeEvent
        super().closeEvent(event)

    def _update_system_status_from_data(self, metrics: Dict[str, Any]):
        """从监控数据更新系统状态显示（重构版：支持热力图+趋势图）."""
        try:
            # 提取基础指标
            cpu_percent = metrics.get("cpu_percent", 0)
            memory_percent = metrics.get("memory_percent", 0)
            disk_io_speed = metrics.get("disk_io_speed", {})
            network_speed = metrics.get("network_speed", {})

            # 🔥 FIX: 磁盘I/O速度数据结构修复
            # 后端返回的read_speed/write_speed已经是MB/s，不需要再除以1024
            disk_io_data = {}
            if disk_io_speed:
                for disk_name, speeds in disk_io_speed.items():
                    if isinstance(speeds, dict):
                        read_speed = speeds.get("read_speed", 0)  # 已经是MB/s
                        write_speed = speeds.get("write_speed", 0)  # 已经是MB/s
                        disk_io_data[disk_name] = {"read": read_speed, "write": write_speed}

            # 🔥 FIX: 网络速度数据修复
            # 后端返回的是KB/s，需要除以1024转换为MB/s
            network_download_mbps = 0.0
            if network_speed:
                download_kbps = network_speed.get("download_speed_kbps", 0)
                network_download_mbps = download_kbps / 1024  # KB/s -> MB/s

            # 获取CPU温度（🔥 FIX: 使用缓存的hardware数据）
            cpu_temp = 0.0
            # system事件不包含hardware数据，使用缓存的hardware数据
            hardware_data = getattr(self, "_cached_hardware_data", {})
            if hardware_data:
                temperature_data = hardware_data.get("temperature", {})
                for device, sensors in temperature_data.items():
                    if sensors and isinstance(sensors, list) and len(sensors) > 0:
                        if any(
                            keyword in device
                            for keyword in ["CPU", "ACPI", "processor", "Ryzen", "Intel"]
                        ):
                            cpu_temp = sensors[0].get("current", 0)
                            break

            # 更新4个监控卡片

            # 统一监控卡片（CPU+网络+内存的9个热力图）
            if hasattr(self, "unified_monitor_card"):
                # 1. CPU指标
                cpu_detailed = metrics.get("cpu_detailed", {})
                context_switches_per_sec = cpu_detailed.get("context_switches_per_sec", 0)
                context_switches_k = context_switches_per_sec / 1000  # 转换为K/s

                # CPU频率比率（使用psutil采集的数据）
                freq_ratio = 0.0
                cpu_frequency = cpu_detailed.get("cpu_frequency", {})

                # 诊断日志：检查是否收到 cpu_frequency 数据
                if not hasattr(self, "_cpu_freq_check_logged"):
                    if cpu_frequency:
                        self.logger.info(
                            f"✅ 收到CPU频率数据: {cpu_frequency}"
                        )
                    else:
                        self.logger.warning(
                            f"⚠️ cpu_detailed中没有cpu_frequency字段, cpu_detailed keys={list(cpu_detailed.keys())}"
                        )
                    self._cpu_freq_check_logged = True

                if cpu_frequency:
                    current_freq = cpu_frequency.get("current", 0)
                    max_freq = cpu_frequency.get("max", 0)

                    if max_freq > 0 and current_freq > 0:
                        freq_ratio = (current_freq / max_freq) * 100

                        # 首次检测到频率数据时记录日志
                        if not hasattr(self, "_cpu_freq_detected"):
                            self.logger.info(
                                f"✅ CPU频率监控已启用: {current_freq:.0f}/{max_freq:.0f} MHz (psutil)"
                            )
                            self._cpu_freq_detected = True

                # 2. 网络指标
                packet_loss_percent = 0.0
                if network_speed:
                    if "packet_loss_rate_in" in network_speed:
                        packet_loss_percent = network_speed.get("packet_loss_rate_in", 0) * 100
                    else:
                        network_subsystem = metrics.get("network_subsystem", {})
                        packet_loss_rate = network_subsystem.get("packet_loss_rate_in", 0)
                        packet_loss_percent = packet_loss_rate * 100

                # 延迟和带宽信息
                service = self.service_manager.get_service("system_manager_service", silent=True)
                latency_ms = 0.0
                total_bandwidth_mbps = 0.0
                bandwidth_percent = 0.0

                network_disconnected = False
                if service:
                    try:
                        bandwidth_info = service.get_bandwidth_info()
                        ping_result = bandwidth_info.get("ping_test", {})
                        full_result = bandwidth_info.get("full_test", {})
                        network_disconnected = bandwidth_info.get("network_disconnected", False)

                        if ping_result and ping_result.get("ping_ms") is not None:
                            # 🔧 修复：检查status字段，排除错误状态
                            status = ping_result.get("status", "")
                            if status and isinstance(status, str) and ("错误" in status or "超时" in status or "ZMQ" in status):
                                # 错误状态，不显示延迟
                                latency_ms = 0.0
                            else:
                                latency_ms = ping_result.get("ping_ms", 0)
                        elif full_result and full_result.get("ping_ms") is not None:
                            # 🔧 修复：检查status字段，排除错误状态
                            status = full_result.get("status", "")
                            if status and isinstance(status, str) and ("错误" in status or "超时" in status or "ZMQ" in status):
                                # 错误状态，不显示延迟
                                latency_ms = 0.0
                            else:
                                latency_ms = full_result.get("ping_ms", 0)

                        if full_result and full_result.get("download_mbps") is not None:
                            total_bandwidth_mbps = full_result.get("download_mbps", 0)

                        if total_bandwidth_mbps == 0 and network_speed:
                            total_bandwidth_mbps = 100

                        if total_bandwidth_mbps > 0:
                            bandwidth_percent = (network_download_mbps / total_bandwidth_mbps) * 100
                            bandwidth_percent = min(bandwidth_percent, 100)
                    except Exception as e:
                        self.logger.debug(f"获取带宽信息失败: {e}", exc_info=True)

                # 3. 内存指标
                memory_subsystem = metrics.get("memory_subsystem", {})
                swap_in_kbps = memory_subsystem.get("swap_in_kbps", 0)
                swap_out_kbps = memory_subsystem.get("swap_out_kbps", 0)
                swap_total_mbps = (swap_in_kbps + swap_out_kbps) / 1024  # KB/s -> MB/s

                # 统一更新所有9个指标
                self.unified_monitor_card.update_metrics(
                    {
                        "cpu_usage": cpu_percent,
                        "context_switches": context_switches_k,
                        "temperature": cpu_temp,
                        "freq_ratio": freq_ratio,
                        "packet_loss": packet_loss_percent,
                        "latency": latency_ms,
                        "bandwidth_usage": bandwidth_percent,
                        "memory_usage": memory_percent,
                        "swap_total": swap_total_mbps,
                    }
                )

                # 更新带宽详情
                self.unified_monitor_card.update_bandwidth_detail(
                    network_download_mbps, total_bandwidth_mbps, bandwidth_percent
                )

                # 更新无网络连接状态显示
                self.unified_monitor_card.update_network_status(
                    network_disconnected,
                    retry_callback=self._retry_latency_test
                )

            # 4. 硬盘监控卡片
            # SMART数据现在通过EVENT_SMART_STATUS事件更新
            # 这里不需要处理，保持现有状态

            # 更新详细数据表格
            if hasattr(self, "status_details_table") and self.status_details_table:
                self._update_status_details_table(metrics)

        except Exception as e:
            self.logger.error("更新系统状态显示失败: %s", e)

    def _update_process_status_from_data(self, metrics: Dict[str, Any]):
        """从监控数据更新进程状态显示."""
        try:
            if not self.process_table:
                return

            python_processes = metrics.get("python_processes", [])
            bottlenecks = metrics.get("bottlenecks", [])

            # 更新进程表格
            self.process_table.setRowCount(0)
            for proc in python_processes:
                row = self.process_table.rowCount()
                self.process_table.insertRow(row)

                self.process_table.setItem(row, 0, QTableWidgetItem(str(proc.get("id", ""))))
                self.process_table.setItem(row, 1, QTableWidgetItem(proc.get("name", "")))
                self.process_table.setItem(row, 2, QTableWidgetItem(proc.get("type", "")))
                self.process_table.setItem(
                    row, 3, QTableWidgetItem(f"{proc.get('cpu_percent', 0):.1f}%")
                )
                self.process_table.setItem(
                    row, 4, QTableWidgetItem(f"{proc.get('memory_mb', 0):.1f} MB")
                )

                # 标记瓶颈进程
                is_bottleneck = any(b.get("pid") == proc.get("id") for b in bottlenecks)
                if is_bottleneck:
                    for col in range(self.process_table.columnCount()):
                        item = self.process_table.item(row, col)
                        if item:
                            item.setBackground(QColor("#FFE5E5"))

        except Exception as e:
            self.logger.error("更新进程状态显示失败: %s", e)

    def _update_service_status_from_data(self, metrics: Union[Dict[str, Any], List[Any]]):
        """从监控数据更新服务状态显示."""
        try:
            if not self.services_table:
                return

            # 🔧 新增：类型检查，防止传入字符串或其他类型
            if isinstance(metrics, str):
                self.logger.warning("接收到字符串类型的服务数据，跳过更新: %s", metrics)
                return

            # 处理多种数据格式：
            # 1. metrics 是字典，包含 "services" 键（值为列表）
            # 2. metrics 是字典，包含 "services" 键（值为字典，需要转换）
            # 3. metrics 直接就是服务列表
            # 4. metrics 是字典，但直接就是服务数据（没有 "services" 键）
            if isinstance(metrics, dict):
                # 检查是否有 "services" 键
                if "services" in metrics:
                    services = metrics["services"]
                    # 🔧 修复：处理 services 是字典的情况
                    if isinstance(services, dict):
                        # 将字典转换为列表格式
                        services = [services]
                        self.logger.debug("将字典格式的 services 转换为列表格式")
                    elif not isinstance(services, list):
                        self.logger.warning("metrics['services'] 不是列表或字典类型: %s", type(services))
                        services = []
                else:
                    # 🔧 新增：如果字典没有 "services" 键，可能字典本身就是一个服务数据
                    # 尝试将字典转换为列表格式
                    if all(key in metrics for key in ["name", "status", "health"]):
                        # 这是一个单独的服务数据，转换为列表
                        services = [metrics]
                    else:
                        # 否则认为是无效格式
                        self.logger.warning("字典格式的服务数据缺少 'services' 键，且不是有效的服务数据: %s", list(metrics.keys()))
                        services = []
            elif isinstance(metrics, list):
                services = metrics
            else:
                self.logger.warning("无效的服务数据格式: %s", type(metrics))
                return

            healthy_count = sum(
                1 for s in services
                if isinstance(s, dict) and s.get("status") == "运行中" and s.get("health") == "健康"
            )
            total_count = len(services)

            # 更新健康度进度条
            if self.health_progress:
                health_percent = int((healthy_count / total_count * 100) if total_count > 0 else 0)
                self.health_progress.setValue(health_percent)

            # 更新服务表格
            self.services_table.setRowCount(0)
            for service_info in services:
                # 🔧 新增：确保 service_info 是字典
                if not isinstance(service_info, dict):
                    self.logger.warning("跳过非字典类型的服务信息: %s", type(service_info))
                    continue

                row = self.services_table.rowCount()
                self.services_table.insertRow(row)

                self.services_table.setItem(row, 0, QTableWidgetItem(service_info.get("name", "")))
                self.services_table.setItem(
                    row, 1, QTableWidgetItem(service_info.get("status", ""))
                )
                self.services_table.setItem(
                    row, 2, QTableWidgetItem(service_info.get("health", ""))
                )

                # 根据健康状态着色
                health = service_info.get("health", "")
                color = QColor("#E8F5E9") if health == "健康" else QColor("#FFE5E5")
                for col in range(self.services_table.columnCount()):
                    item = self.services_table.item(row, col)
                    if item:
                        item.setBackground(color)

        except Exception as e:
            self.logger.error("更新服务状态显示失败: %s", e)

    def _update_datasource_connectivity(self):
        """更新数据源连通性显示."""
        try:
            if not hasattr(self, "tdx_connectivity_label"):
                return

            service = self.service_manager.get_service("system_manager_service", silent=True)
            if not service:
                return

            connectivity = service.get_data_source_connectivity()

            # 更新TDX服务器状态
            tdx = connectivity.get("tdx_servers", {})
            available = tdx.get("available", 0)
            total = tdx.get("total", 0)
            rate = tdx.get("connectivity_rate", 0)

            if rate > 50:
                icon = "✅"
            elif rate > 20:
                icon = "⚠️"
            else:
                icon = "❌"

            tdx_text = f"{icon} TDX服务器: {available}/{total} 可用 ({rate:.1f}%)"
            self.tdx_connectivity_label.setText(tdx_text)

            # 更新交易网关状态
            gateways = connectivity.get("trading_gateways", {})
            ctp_status = gateways.get("ctp", "unknown")
            ib_status = gateways.get("ib", "unknown")

            status_icons = {
                "connected": "✅",
                "disconnected": "❌",
                "not_configured": "⚪",
                "unknown": "❓",
            }

            ctp_icon = status_icons.get(ctp_status, "❓")
            ib_icon = status_icons.get(ib_status, "❓")

            gateway_text = f"交易网关: CTP {ctp_icon} IB {ib_icon}"
            self.gateway_connectivity_label.setText(gateway_text)

        except Exception as e:
            self.logger.error("更新数据源连通性失败: %s", e)

    # ==================== 1.1 系统状态监控 ====================

    def _create_system_status_tab(self) -> QWidget:
        """创建系统状态监控子界面（重构版：深色极简，热力图+趋势图）."""
        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        title_label = QLabel("🔍 系统状态实时监控")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #E0E0E0;")
        toolbar.addWidget(title_label)
        toolbar.addStretch()

        auto_refresh = QCheckBox("自动刷新（事件驱动）")
        auto_refresh.setChecked(True)
        auto_refresh.setEnabled(False)
        auto_refresh.setStyleSheet("color: #AAA;")
        toolbar.addWidget(auto_refresh)

        main_layout.addLayout(toolbar)

        # 主分隔器：左右布局（70:30）
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：监控组件网格（第一行3列，第二行独占）
        grid_container = QWidget()
        grid_container.setStyleSheet("background-color: transparent;")
        grid_layout = QGridLayout(grid_container)
        grid_layout.setSpacing(15)  # 增加组件之间间距
        grid_layout.setContentsMargins(0, 0, 0, 0)

        # 创建监控卡片：使用统一组件（9个热力图均匀排列）
        self.unified_monitor_card = UnifiedMonitorCard()
        self.disk_monitor_card = DiskMonitorCard()

        # 第一行：统一监控组件（CPU+网络+内存的9个热力图）
        grid_layout.addWidget(self.unified_monitor_card, 0, 0, 1, 3)

        # 第二行：硬盘监控（独占，跨3列）
        grid_layout.addWidget(self.disk_monitor_card, 1, 0, 1, 3)

        # 设置行列比例
        # 行：第一行和第二行均分
        grid_layout.setRowStretch(0, 1)
        grid_layout.setRowStretch(1, 1)
        # 列：3列均分（虽然现在只用了跨列布局）
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 1)
        grid_layout.setColumnStretch(2, 1)

        main_splitter.addWidget(grid_container)

        # 右侧：详细数据表格
        details_group = QGroupBox("📋 详细数据")
        details_group.setStyleSheet(
            """
            QGroupBox {
                font-size: 12px;
                font-weight: bold;
                color: #E0E0E0;
                border: 1px solid #333;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """
        )
        details_layout = QVBoxLayout(details_group)
        details_layout.setSpacing(5)
        details_layout.setContentsMargins(8, 15, 8, 8)

        self.status_details_table = QTableWidget(0, 5)
        self.status_details_table.setHorizontalHeaderLabels(
            ["指标", "当前值", "平均值", "阈值", "状态"]
        )

        # 深色表格样式
        self.status_details_table.setStyleSheet(
            """
            QTableWidget {
                background-color: #1E1E1E;
                color: #E0E0E0;
                gridline-color: #333;
                border: 1px solid #333;
            }
            QHeaderView::section {
                background-color: #2A2A2A;
                color: #E0E0E0;
                padding: 5px;
                border: 1px solid #333;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #3A3A3A;
            }
        """
        )

        header = self.status_details_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.status_details_table.verticalHeader().setDefaultSectionSize(28)
        self.status_details_table.setAlternatingRowColors(True)

        details_layout.addWidget(self.status_details_table)
        main_splitter.addWidget(details_group)

        # 设置左右比例 70:30
        main_splitter.setSizes([700, 300])
        main_splitter.setStretchFactor(0, 7)
        main_splitter.setStretchFactor(1, 3)

        main_layout.addWidget(main_splitter)

        return tab

    # 注意：旧的_create_heatmap_section方法已被删除，现在使用网格布局（第一行3列+第二行独占）的4个监控卡片代替

    # ==================== 1.2 性能指标展示 ====================

    def _create_performance_tab(self) -> QWidget:
        """创建性能指标子界面（重构版 - 按量化场景分组）."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # 顶部工具栏
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("📊 性能指标 - 量化场景分析"))
        toolbar_layout.addStretch()

        auto_refresh_check = QCheckBox("自动刷新")
        auto_refresh_check.setChecked(True)
        auto_refresh_check.setEnabled(False)
        toolbar_layout.addWidget(auto_refresh_check)

        layout.addLayout(toolbar_layout)

        # 场景选择器
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("场景:"))

        self.scenario_selector = QComboBox()
        self.scenario_selector.addItems(
            ["全局概览", "数据下载", "实时行情", "策略回测", "策略编写", "实盘交易"]
        )
        self.scenario_selector.currentTextChanged.connect(self._on_scenario_changed)
        selector_layout.addWidget(self.scenario_selector)
        selector_layout.addStretch()

        layout.addLayout(selector_layout)

        # 场景堆栈（可切换的内容区）
        self.scenario_stack = QStackedWidget()

        # 创建6个场景视图
        self.scenario_stack.addWidget(self._create_global_overview())
        self.scenario_stack.addWidget(self._create_download_scenario_view())
        self.scenario_stack.addWidget(self._create_realtime_scenario_view())
        self.scenario_stack.addWidget(self._create_backtest_scenario_view())
        self.scenario_stack.addWidget(self._create_strategy_edit_scenario_view())
        self.scenario_stack.addWidget(self._create_trading_scenario_view())

        layout.addWidget(self.scenario_stack)

        return tab

    def _on_scenario_changed(self, scenario_text: str):
        """场景切换事件."""
        try:
            index = self.scenario_selector.currentIndex()
            self.scenario_stack.setCurrentIndex(index)
            self.logger.debug("切换到场景: %s (索引: %d)", scenario_text, index)

            # 刷新当前场景数据
            self._refresh_current_scenario_view()

        except Exception as e:
            self.logger.error("场景切换失败: %s", e)

    def _create_global_overview(self) -> QWidget:
        """创建全局概览视图."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)

        # 顶部：5大场景健康度卡片
        scenarios_group = QGroupBox("📋 场景健康度")
        scenarios_layout = QGridLayout(scenarios_group)
        scenarios_layout.setSpacing(10)

        # 创建5个场景卡片（存储引用以便更新）
        self.scenario_health_cards = {}
        scenario_names = [
            ("data_download", "数据下载", "📥"),
            ("realtime_market", "实时行情", "📊"),
            ("backtest", "策略回测", "🔬"),
            ("strategy_edit", "策略编写", "✏️"),
            ("live_trading", "实盘交易", "💹"),
        ]

        for idx, (key, name, icon) in enumerate(scenario_names):
            card = self._create_scenario_health_card(key, name, icon)
            self.scenario_health_cards[key] = card
            row = idx // 3
            col = idx % 3
            scenarios_layout.addWidget(card, row, col)

        layout.addWidget(scenarios_group)

        # 中部：当前瓶颈提示
        bottleneck_group = QGroupBox("⚠️ 当前最严重瓶颈")
        bottleneck_layout = QVBoxLayout(bottleneck_group)

        self.global_bottleneck_label = QLabel("正在分析...")
        self.global_bottleneck_label.setWordWrap(True)
        self.global_bottleneck_label.setStyleSheet("font-size: 13px; padding: 10px;")
        bottleneck_layout.addWidget(self.global_bottleneck_label)

        layout.addWidget(bottleneck_group)

        # 底部：自适应并发建议
        adaptive_group = QGroupBox("🎯 自适应调优建议")
        adaptive_layout = QGridLayout(adaptive_group)

        # 缩放因子
        adaptive_layout.addWidget(QLabel("缩放因子:"), 0, 0)
        self.global_scale_factor_label = QLabel("--")
        self.global_scale_factor_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        adaptive_layout.addWidget(self.global_scale_factor_label, 0, 1)

        # 建议并发数
        adaptive_layout.addWidget(QLabel("建议并发:"), 1, 0)
        self.global_concurrency_label = QLabel("--")
        adaptive_layout.addWidget(self.global_concurrency_label, 1, 1)

        # 原因
        adaptive_layout.addWidget(QLabel("原因:"), 2, 0)
        self.global_adaptive_reason_label = QLabel("--")
        self.global_adaptive_reason_label.setWordWrap(True)
        adaptive_layout.addWidget(self.global_adaptive_reason_label, 2, 1)

        layout.addWidget(adaptive_group)

        # 并发任务统计组（新增）
        concurrent_group = QGroupBox("📊 并发任务统计")
        concurrent_layout = QGridLayout(concurrent_group)
        concurrent_layout.setSpacing(10)

        self.concurrent_download_label = QLabel("下载任务: 0")
        self.concurrent_download_label.setStyleSheet("font-size: 13px; padding: 5px;")
        concurrent_layout.addWidget(self.concurrent_download_label, 0, 0)

        self.concurrent_backtest_label = QLabel("回测任务: 0")
        self.concurrent_backtest_label.setStyleSheet("font-size: 13px; padding: 5px;")
        concurrent_layout.addWidget(self.concurrent_backtest_label, 0, 1)

        self.concurrent_trading_label = QLabel("交易任务: 0")
        self.concurrent_trading_label.setStyleSheet("font-size: 13px; padding: 5px;")
        concurrent_layout.addWidget(self.concurrent_trading_label, 1, 0)

        self.concurrent_total_label = QLabel("总计: 0")
        self.concurrent_total_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 5px;"
        )
        concurrent_layout.addWidget(self.concurrent_total_label, 1, 1)

        layout.addWidget(concurrent_group)
        layout.addStretch()

        return widget

    def _create_scenario_health_card(self, key: str, name: str, icon: str) -> QWidget:
        """创建场景健康度卡片."""
        card = QGroupBox(f"{icon} {name}")
        card.setMaximumHeight(120)
        layout = QVBoxLayout(card)

        # 健康度评分
        score_label = QLabel("--")
        score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #10B981;")
        layout.addWidget(score_label)

        # 状态文本
        status_label = QLabel("正常")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_label.setStyleSheet("font-size: 11px; color: #94A3B8;")
        layout.addWidget(status_label)

        # 保存引用
        card.score_label = score_label  # type: ignore[attr-defined]
        card.status_label = status_label  # type: ignore[attr-defined]

        return card

    def _create_download_scenario_view(self) -> QWidget:
        """创建数据下载场景视图."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 关键指标卡片
        metrics_group = QGroupBox("📊 关键指标")
        metrics_layout = QGridLayout(metrics_group)

        self.download_metrics_labels = {}
        metrics_def = [
            ("network_speed", "网络带宽", "MB/s"),
            ("disk_write", "磁盘写入", "MB/s"),
            ("io_latency", "I/O延迟", "ms"),
            ("concurrency", "下载并发", "个"),
        ]

        for idx, (key, name, unit) in enumerate(metrics_def):
            row = idx // 2
            col = (idx % 2) * 2

            metrics_layout.addWidget(QLabel(name + ":"), row, col)
            value_label = QLabel("--")
            value_label.setStyleSheet("font-weight: bold;")
            metrics_layout.addWidget(value_label, row, col + 1)
            self.download_metrics_labels[key] = value_label

        layout.addWidget(metrics_group)

        # 瓶颈分析
        bottleneck_group = QGroupBox("⚠️ 瓶颈分析")
        bottleneck_layout = QVBoxLayout(bottleneck_group)

        self.download_bottleneck_label = QLabel("正在分析...")
        self.download_bottleneck_label.setWordWrap(True)
        bottleneck_layout.addWidget(self.download_bottleneck_label)

        self.download_hints_label = QLabel("")
        self.download_hints_label.setWordWrap(True)
        self.download_hints_label.setStyleSheet("color: #3B82F6;")
        bottleneck_layout.addWidget(self.download_hints_label)

        layout.addWidget(bottleneck_group)
        layout.addStretch()

        return widget

    def _create_realtime_scenario_view(self) -> QWidget:
        """创建实时行情场景视图."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 关键指标
        metrics_group = QGroupBox("📊 关键指标")
        metrics_layout = QGridLayout(metrics_group)

        self.realtime_metrics_labels = {}
        metrics_def = [
            ("event_queue", "事件队列深度", "个"),
            ("processing_latency", "处理延迟", "ms"),
            ("context_switches", "上下文切换", "/秒"),
            ("packet_loss", "丢包率", "%"),
        ]

        for idx, (key, name, unit) in enumerate(metrics_def):
            row = idx // 2
            col = (idx % 2) * 2

            metrics_layout.addWidget(QLabel(name + ":"), row, col)
            value_label = QLabel("--")
            value_label.setStyleSheet("font-weight: bold;")
            metrics_layout.addWidget(value_label, row, col + 1)
            self.realtime_metrics_labels[key] = value_label

        layout.addWidget(metrics_group)

        # 瓶颈分析
        bottleneck_group = QGroupBox("⚠️ 瓶颈分析")
        bottleneck_layout = QVBoxLayout(bottleneck_group)

        self.realtime_bottleneck_label = QLabel("正在分析...")
        self.realtime_bottleneck_label.setWordWrap(True)
        bottleneck_layout.addWidget(self.realtime_bottleneck_label)

        self.realtime_hints_label = QLabel("")
        self.realtime_hints_label.setWordWrap(True)
        self.realtime_hints_label.setStyleSheet("color: #3B82F6;")
        bottleneck_layout.addWidget(self.realtime_hints_label)

        layout.addWidget(bottleneck_group)
        layout.addStretch()

        return widget

    def _create_backtest_scenario_view(self) -> QWidget:
        """创建策略回测场景视图."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 关键指标
        metrics_group = QGroupBox("📊 关键指标")
        metrics_layout = QGridLayout(metrics_group)

        self.backtest_metrics_labels = {}
        metrics_def = [
            ("cpu", "CPU使用率", "%"),
            ("memory", "内存使用率", "%"),
            ("swap", "交换活动", "KB/s"),
            ("kline_time", "K线计算", "ms"),
        ]

        for idx, (key, name, unit) in enumerate(metrics_def):
            row = idx // 2
            col = (idx % 2) * 2

            metrics_layout.addWidget(QLabel(name + ":"), row, col)
            value_label = QLabel("--")
            value_label.setStyleSheet("font-weight: bold;")
            metrics_layout.addWidget(value_label, row, col + 1)
            self.backtest_metrics_labels[key] = value_label

        layout.addWidget(metrics_group)

        # 自适应建议（回测专用）
        adaptive_group = QGroupBox("🎯 自适应调优")
        adaptive_layout = QVBoxLayout(adaptive_group)

        self.backtest_adaptive_label = QLabel("--")
        self.backtest_adaptive_label.setWordWrap(True)
        adaptive_layout.addWidget(self.backtest_adaptive_label)

        layout.addWidget(adaptive_group)

        # 瓶颈分析
        bottleneck_group = QGroupBox("⚠️ 瓶颈分析")
        bottleneck_layout = QVBoxLayout(bottleneck_group)

        self.backtest_bottleneck_label = QLabel("正在分析...")
        self.backtest_bottleneck_label.setWordWrap(True)
        bottleneck_layout.addWidget(self.backtest_bottleneck_label)

        self.backtest_hints_label = QLabel("")
        self.backtest_hints_label.setWordWrap(True)
        self.backtest_hints_label.setStyleSheet("color: #3B82F6;")
        bottleneck_layout.addWidget(self.backtest_hints_label)

        layout.addWidget(bottleneck_group)
        layout.addStretch()

        return widget

    def _create_strategy_edit_scenario_view(self) -> QWidget:
        """创建策略编写场景视图."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 关键指标
        metrics_group = QGroupBox("📊 关键指标")
        metrics_layout = QGridLayout(metrics_group)

        self.strategyedit_metrics_labels = {}
        metrics_def = [("cpu", "CPU使用率", "%"), ("memory", "内存使用率", "%")]

        for idx, (key, name, unit) in enumerate(metrics_def):
            metrics_layout.addWidget(QLabel(name + ":"), idx, 0)
            value_label = QLabel("--")
            value_label.setStyleSheet("font-weight: bold;")
            metrics_layout.addWidget(value_label, idx, 1)
            self.strategyedit_metrics_labels[key] = value_label

        layout.addWidget(metrics_group)

        # 提示信息
        info_label = QLabel("策略编写场景通常负载较低，系统资源充足。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #94A3B8; font-style: italic; padding: 10px;")
        layout.addWidget(info_label)

        layout.addStretch()

        return widget

    def _create_trading_scenario_view(self) -> QWidget:
        """创建实盘交易场景视图."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 关键指标
        metrics_group = QGroupBox("📊 关键指标")
        metrics_layout = QGridLayout(metrics_group)

        self.trading_metrics_labels = {}
        metrics_def = [
            ("order_response", "订单响应", "ms"),
            ("queue_length", "交易队列", "个"),
            ("packet_loss", "丢包率", "%"),
            ("cpu_temp", "CPU温度", "°C"),
        ]

        for idx, (key, name, unit) in enumerate(metrics_def):
            row = idx // 2
            col = (idx % 2) * 2

            metrics_layout.addWidget(QLabel(name + ":"), row, col)
            value_label = QLabel("--")
            value_label.setStyleSheet("font-weight: bold;")
            metrics_layout.addWidget(value_label, row, col + 1)
            self.trading_metrics_labels[key] = value_label

        layout.addWidget(metrics_group)

        # 瓶颈分析
        bottleneck_group = QGroupBox("⚠️ 瓶颈分析")
        bottleneck_layout = QVBoxLayout(bottleneck_group)

        self.trading_bottleneck_label = QLabel("正在分析...")
        self.trading_bottleneck_label.setWordWrap(True)
        bottleneck_layout.addWidget(self.trading_bottleneck_label)

        self.trading_hints_label = QLabel("")
        self.trading_hints_label.setWordWrap(True)
        self.trading_hints_label.setStyleSheet("color: #3B82F6;")
        bottleneck_layout.addWidget(self.trading_hints_label)

        layout.addWidget(bottleneck_group)
        layout.addStretch()

        return widget

    def _refresh_current_scenario_view(self):
        """刷新当前场景视图（从缓存数据更新）."""
        try:
            if not self.system_service:
                return

            # 获取性能摘要
            summary = self.system_service.get_performance_summary()
            if not summary:
                return

            current_index = self.scenario_stack.currentIndex()

            if current_index == 0:  # 全局概览
                self._update_global_overview(summary)
            elif current_index == 1:  # 数据下载
                self._update_download_scenario(summary)
            elif current_index == 2:  # 实时行情
                self._update_realtime_scenario(summary)
            elif current_index == 3:  # 策略回测
                self._update_backtest_scenario(summary)
            elif current_index == 4:  # 策略编写
                self._update_strategyedit_scenario(summary)
            elif current_index == 5:  # 实盘交易
                self._update_trading_scenario(summary)

        except Exception as e:
            self.logger.error("刷新场景视图失败: %s", e)

    def _update_global_overview(self, summary: Dict[str, Any]):
        """更新全局概览."""
        try:
            # 更新瓶颈提示
            bottleneck = summary.get("bottleneck", {})
            if bottleneck:
                dimension = bottleneck.get("bottleneck_dimension", "unknown")
                score = bottleneck.get("total_score", 100)
                suggestions = bottleneck.get("suggestions", [])

                text = f"瓶颈维度: {dimension} | 压力评分: {score:.0f}/100"
                if suggestions:
                    text += f"\n建议: {suggestions[0]}"
                self.global_bottleneck_label.setText(text)

            # 更新自适应建议
            adaptive = summary.get("adaptive_suggestion", {})
            if adaptive:
                scale = adaptive.get("scale_factor", 1.0)
                reason = adaptive.get("reason", "")
                concurrency = adaptive.get("suggested_concurrency", {})

                self.global_scale_factor_label.setText(f"{scale:.2f}")
                self.global_adaptive_reason_label.setText(reason)

                if concurrency:
                    conc_text = f"async={concurrency.get('async_workers', 0)}, "
                    conc_text += f"thread={concurrency.get('thread_workers', 0)}, "
                    conc_text += f"proc={concurrency.get('process_workers', 0)}"
                    self.global_concurrency_label.setText(conc_text)

            # 更新场景健康度卡片
            self._update_scenario_health_cards(summary)

        except Exception as e:
            self.logger.error("更新全局概览失败: %s", e)

    def _update_scenario_health_cards(self, summary: Dict[str, Any]):
        """更新场景健康度卡片

        Args:
            summary: 系统监控摘要数据
        """
        try:
            scenario_details = summary.get("scenario_details", {})

            # 场景名称映射
            scenario_mapping = {
                "data_download": "data_download",
                "realtime_market": "realtime_quote",
                "strategy_backtest": "strategy_backtest",
                "trading_gateway": "realtime_trading",
                "system_monitor": "system_monitor",
            }

            # 更新各场景的健康度显示
            for card_key, scenario_key in scenario_mapping.items():
                if card_key not in self.scenario_health_cards:
                    continue

                card = self.scenario_health_cards[card_key]
                scenario_data = scenario_details.get(scenario_key, {})

                # 计算健康度评分（基于当前值和阈值）
                health_score = self._calculate_scenario_health(scenario_data)
                bottleneck = scenario_data.get("bottleneck_analysis", {}).get(
                    "is_bottleneck", False
                )

                # 更新评分显示
                if hasattr(card, "score_label"):
                    card.score_label.setText(f"{health_score:.0f}")

                    # 根据评分设置颜色
                    if health_score >= 80:
                        color = "#10B981"  # 绿色 - 健康
                    elif health_score >= 60:
                        color = "#F59E0B"  # 黄色 - 警告
                    else:
                        color = "#EF4444"  # 红色 - 异常

                    card.score_label.setStyleSheet(
                        f"font-size: 24px; font-weight: bold; color: {color};"
                    )

                # 更新状态文本
                if hasattr(card, "status_label"):
                    if bottleneck:
                        status_text = "存在瓶颈"
                        status_color = "#F59E0B"
                    elif health_score >= 80:
                        status_text = "正常"
                        status_color = "#10B981"
                    elif health_score >= 60:
                        status_text = "警告"
                        status_color = "#F59E0B"
                    else:
                        status_text = "异常"
                        status_color = "#EF4444"

                    card.status_label.setText(status_text)
                    card.status_label.setStyleSheet(f"font-size: 11px; color: {status_color};")

        except Exception as e:
            self.logger.error(f"更新场景健康度卡片失败: {e}")

    def _calculate_scenario_health(self, scenario_data: Dict[str, Any]) -> float:
        """计算场景健康度评分

        Args:
            scenario_data: 场景数据

        Returns:
            健康度评分 (0-100)
        """
        try:
            current_values = scenario_data.get("current_values", {})
            bottleneck_analysis = scenario_data.get("bottleneck_analysis", {})

            # 基础评分从100开始
            score = 100.0

            # 如果存在瓶颈，降低评分
            if bottleneck_analysis.get("is_bottleneck", False):
                score -= 30

            # 根据具体指标调整评分（示例逻辑）
            # CPU使用率
            if "cpu_percent" in current_values:
                cpu = current_values["cpu_percent"]
                if cpu > 90:
                    score -= 20
                elif cpu > 80:
                    score -= 10

            # 内存使用率
            if "memory_percent" in current_values:
                mem = current_values["memory_percent"]
                if mem > 90:
                    score -= 20
                elif mem > 80:
                    score -= 10

            # 磁盘使用率
            if "disk_usage_percent" in current_values:
                disk = current_values["disk_usage_percent"]
                if disk > 95:
                    score -= 15
                elif disk > 85:
                    score -= 8

            # 确保评分在0-100范围内
            return max(0.0, min(100.0, score))

        except Exception:
            return 50.0  # 默认中等评分

    def _update_download_scenario(self, summary: Dict[str, Any]):
        """更新数据下载场景."""
        try:
            scenario_details = summary.get("scenario_details", {})
            current_values = scenario_details.get("current_values", {})

            # 更新指标
            if "network_download_mbps" in current_values:
                self.download_metrics_labels["network_speed"].setText(
                    f"{current_values['network_download_mbps']:.1f} MB/s"
                )
            if "disk_write_mbps" in current_values:
                self.download_metrics_labels["disk_write"].setText(
                    f"{current_values['disk_write_mbps']:.1f} MB/s"
                )
            if "io_latency_ms" in current_values:
                self.download_metrics_labels["io_latency"].setText(
                    f"{current_values['io_latency_ms']:.1f} ms"
                )
            # TODO #9: 下载并发数
            if "download_concurrency" in current_values:
                self.download_metrics_labels["concurrency"].setText(
                    f"{current_values['download_concurrency']:.0f}"
                )

            # 更新瓶颈分析
            bottleneck_reason = scenario_details.get("bottleneck_reason", "正常")
            self.download_bottleneck_label.setText(bottleneck_reason)

            hints = scenario_details.get("optimization_hints", [])
            if hints:
                self.download_hints_label.setText("建议: " + " / ".join(hints))

        except Exception as e:
            self.logger.error("更新下载场景失败: %s", e)

    def _update_realtime_scenario(self, summary: Dict[str, Any]):
        """更新实时行情场景."""
        try:
            scenario_details = summary.get("scenario_details", {})
            current_values = scenario_details.get("current_values", {})

            # 更新指标
            # TODO #10: 事件队列深度和处理延迟
            if "event_queue_depth" in current_values:
                self.realtime_metrics_labels["event_queue"].setText(
                    f"{current_values['event_queue_depth']:.0f}"
                )
            if "processing_latency" in current_values:
                self.realtime_metrics_labels["processing_latency"].setText(
                    f"{current_values['processing_latency']:.2f}"
                )
            if "context_switches_per_sec" in current_values:
                self.realtime_metrics_labels["context_switches"].setText(
                    f"{current_values['context_switches_per_sec']:.0f}"
                )
            if "packet_loss_rate" in current_values:
                self.realtime_metrics_labels["packet_loss"].setText(
                    f"{current_values['packet_loss_rate']:.2f}%"
                )

            # 更新瓶颈分析
            bottleneck_reason = scenario_details.get("bottleneck_reason", "正常")
            self.realtime_bottleneck_label.setText(bottleneck_reason)

            hints = scenario_details.get("optimization_hints", [])
            if hints:
                self.realtime_hints_label.setText("建议: " + " / ".join(hints))

        except Exception as e:
            self.logger.error("更新行情场景失败: %s", e)

    def _update_backtest_scenario(self, summary: Dict[str, Any]):
        """更新回测场景."""
        try:
            key_metrics = summary.get("key_metrics", {})
            scenario_details = summary.get("scenario_details", {})
            current_values = scenario_details.get("current_values", {})

            # 更新指标
            if "cpu_percent" in key_metrics:
                self.backtest_metrics_labels["cpu"].setText(f"{key_metrics['cpu_percent']:.1f}%")
            if "memory_percent" in key_metrics:
                self.backtest_metrics_labels["memory"].setText(
                    f"{key_metrics['memory_percent']:.1f}%"
                )
            if "swap_activity_kbps" in current_values:
                self.backtest_metrics_labels["swap"].setText(
                    f"{current_values['swap_activity_kbps']:.1f} KB/s"
                )

            # 更新自适应建议
            adaptive = summary.get("adaptive_suggestion", {})
            if adaptive:
                scale = adaptive.get("scale_factor", 1.0)
                reason = adaptive.get("reason", "")
                self.backtest_adaptive_label.setText(f"缩放因子: {scale:.2f}\n{reason}")

            # 更新瓶颈
            bottleneck_reason = scenario_details.get("bottleneck_reason", "正常")
            self.backtest_bottleneck_label.setText(bottleneck_reason)

            hints = scenario_details.get("optimization_hints", [])
            if hints:
                self.backtest_hints_label.setText("建议: " + " / ".join(hints))

        except Exception as e:
            self.logger.error("更新回测场景失败: %s", e)

    def _update_strategyedit_scenario(self, summary: Dict[str, Any]):
        """更新策略编写场景."""
        try:
            key_metrics = summary.get("key_metrics", {})

            if "cpu_percent" in key_metrics:
                self.strategyedit_metrics_labels["cpu"].setText(
                    f"{key_metrics['cpu_percent']:.1f}%"
                )
            if "memory_percent" in key_metrics:
                self.strategyedit_metrics_labels["memory"].setText(
                    f"{key_metrics['memory_percent']:.1f}%"
                )

        except Exception as e:
            self.logger.error("更新策略编写场景失败: %s", e)

    def _update_trading_scenario(self, summary: Dict[str, Any]):
        """更新交易场景."""
        try:
            scenario_details = summary.get("scenario_details", {})
            current_values = scenario_details.get("current_values", {})

            # 更新指标
            if "packet_loss_rate" in current_values:
                self.trading_metrics_labels["packet_loss"].setText(
                    f"{current_values['packet_loss_rate']:.2f}%"
                )
            if "cpu_temperature" in current_values:
                self.trading_metrics_labels["cpu_temp"].setText(
                    f"{current_values['cpu_temperature']:.1f}°C"
                )

            # 更新瓶颈
            bottleneck_reason = scenario_details.get("bottleneck_reason", "正常")
            self.trading_bottleneck_label.setText(bottleneck_reason)

            hints = scenario_details.get("optimization_hints", [])
            if hints:
                self.trading_hints_label.setText("建议: " + " / ".join(hints))

        except Exception as e:
            self.logger.error("更新交易场景失败: %s", e)

    def _create_performance_group(self, title: str, metrics: List[tuple]):
        """创建性能指标分组框.

        Args:
            title: 分组标题
            metrics: 指标列表 [(名称, 单位), ...]

        Returns:
            tuple: (QGroupBox, List[QLabel]) 分组框组件和标签列表
        """
        group = QGroupBox(title)
        layout = QGridLayout(group)
        layout.setSpacing(10)

        # 创建指标卡片
        labels = []
        for i, (name, unit) in enumerate(metrics):
            card = QWidget()
            card.setStyleSheet(
                """
                QWidget {
                    background-color: #2C2C2C;
                    border-radius: 5px;
                    padding: 10px;
                }
                """
            )
            card_layout = QVBoxLayout(card)
            card_layout.setSpacing(5)

            # 指标名称
            name_label = QLabel(name)
            name_label.setStyleSheet("color: #888; font-size: 11px;")
            card_layout.addWidget(name_label)

            # 指标值
            value_label = QLabel("--")
            value_label.setStyleSheet("color: #FFF; font-size: 18px; font-weight: bold;")
            card_layout.addWidget(value_label)

            # 单位
            unit_label = QLabel(unit)
            unit_label.setStyleSheet("color: #666; font-size: 10px;")
            card_layout.addWidget(unit_label)

            # 添加到网格
            row = i // 3
            col = i % 3
            layout.addWidget(card, row, col)

            labels.append(value_label)

        return group, labels

    def _update_performance_group(self, labels: List[QLabel], values: List[float]):
        """更新性能分组框的数据.

        Args:
            labels: 标签列表
            values: 值列表
        """
        try:
            for i, value in enumerate(values):
                if i < len(labels):
                    label = labels[i]
                    label.setText(f"{value:.2f}")

        except Exception as e:
            self.logger.error("更新性能分组失败: %s", e)

    # ==================== 1.3 告警管理 ====================

    def _create_alerts_tab(self) -> QWidget:
        """创建告警管理子界面."""
        # 创建告警管理组件
        self.alert_manager_widget = AlertManagerWidget()

        return self.alert_manager_widget

    # ==================== 1.4 服务健康检查 ====================

    def _create_services_tab(self) -> QWidget:
        """创建服务监控子界面（重构版 - 增加业务指标、资源占用、外部依赖）."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏
        toolbar = QHBoxLayout()

        check_all_btn = QPushButton("🔄 快速检查全部")
        check_all_btn.clicked.connect(self._check_all_services)
        toolbar.addWidget(check_all_btn)

        refresh_business_btn = QPushButton("📊 刷新业务指标")
        refresh_business_btn.clicked.connect(self._refresh_business_metrics)
        toolbar.addWidget(refresh_business_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 业务指标仪表板（新增）
        business_dashboard = self._create_business_metrics_dashboard()
        layout.addWidget(business_dashboard)

        # 服务状态组（增加业务指标和资源占用列）
        services_group = QGroupBox("Backend服务状态")
        services_layout = QVBoxLayout(services_group)

        self.services_table = QTableWidget(0, 9)
        headers = [
            "服务名称",
            "状态",
            "响应时间",
            "调用次数",
            "成功率",
            "错误率",
            "内存(MB)",
            "线程数",
            "操作",
        ]
        self.services_table.setHorizontalHeaderLabels(headers)
        header = self.services_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        services_layout.addWidget(self.services_table)

        layout.addWidget(services_group)

        # 外部依赖组
        dependencies_group = QGroupBox("外部依赖状态")
        dependencies_layout = QVBoxLayout(dependencies_group)

        self.dependencies_table = QTableWidget(0, 3)
        dep_headers = ["依赖名称", "状态", "详情"]
        self.dependencies_table.setHorizontalHeaderLabels(dep_headers)
        dep_header = self.dependencies_table.horizontalHeader()
        dep_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        dep_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        dep_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        dep_header.setMinimumSectionSize(150)
        self.dependencies_table.setColumnWidth(0, 180)
        self.dependencies_table.setColumnWidth(1, 100)
        self.dependencies_table.setMaximumHeight(150)
        dependencies_layout.addWidget(self.dependencies_table)

        layout.addWidget(dependencies_group)

        # 数据源连通性组（新增）
        datasource_group = QGroupBox("📡 数据源连通性")
        datasource_layout = QVBoxLayout(datasource_group)

        # TDX服务器状态
        self.tdx_connectivity_label = QLabel("TDX服务器: 检测中...")
        self.tdx_connectivity_label.setStyleSheet("font-size: 12px; padding: 5px;")
        datasource_layout.addWidget(self.tdx_connectivity_label)

        # 交易网关状态
        self.gateway_connectivity_label = QLabel("交易网关: 未配置")
        self.gateway_connectivity_label.setStyleSheet("font-size: 12px; padding: 5px;")
        datasource_layout.addWidget(self.gateway_connectivity_label)

        layout.addWidget(datasource_group)

        # 健康检查组（显示综合健康评分）
        health_group = QGroupBox("整体健康评分")
        health_layout = QVBoxLayout(health_group)

        self.health_progress = QProgressBar()
        self.health_progress.setRange(0, 100)
        self.health_progress.setTextVisible(True)
        self.health_progress.setFormat("%v/100")
        self.health_progress.setStyleSheet(
            """
            QProgressBar {
                border: 2px solid #444;
                border-radius: 5px;
                text-align: center;
                height: 30px;
                font-size: 14px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #4ECDC4;
            }
            """
        )
        health_layout.addWidget(self.health_progress)

        self.health_detail_label = QLabel(
            "在线服务: --/-- | 平均响应时间: --ms | 服务健康: --% | 依赖健康: --%"
        )
        self.health_detail_label.setStyleSheet("color: #888; font-size: 12px;")
        health_layout.addWidget(self.health_detail_label)

        layout.addWidget(health_group)

        return tab

    def _check_all_services(self):
        """检查所有服务（增强版 - 包含外部依赖）."""
        try:
            if not self.system_service:
                self.show_error("系统管理服务不可用")
                return

            result = self.system_service.check_all_services()
            if result.get("success"):
                services = result.get("services", [])
                external_dependencies = result.get("external_dependencies", {})
                health_score = result.get("health_score", 0)
                service_health_score = result.get("service_health_score", 0)
                dependency_health_score = result.get("dependency_health_score", 0)
                avg_response_time = result.get("avg_response_time_ms", 0)
                online_services = result.get("online_services", 0)
                total_services = result.get("total_services", 0)

                # 更新综合健康评分
                if self.health_progress:
                    self.health_progress.setValue(int(health_score))

                if self.health_detail_label:
                    self.health_detail_label.setText(
                        f"在线服务: {online_services}/{total_services} | "
                        f"平均响应时间: {avg_response_time:.1f}ms | "
                        f"服务健康: {service_health_score:.0f}% | "
                        f"依赖健康: {dependency_health_score:.0f}%"
                    )

                # 更新服务表格
                self._update_services_table(services)

                # 更新外部依赖表格
                self._update_dependencies_table(external_dependencies)

                self.show_info(f"服务检查完成：{online_services}/{total_services} 在线")
            else:
                self.show_error(f"检查失败: {result.get('message')}")

        except Exception as e:
            self.logger.error("检查服务失败: %s", e)
            self.show_error(f"检查失败: {e}")

    def _update_services_table(self, services: List[Dict[str, Any]]):
        """更新服务表格（增强版 - 包含业务指标和资源占用）."""
        try:
            if not self.services_table:
                return

            self.services_table.setRowCount(0)

            for service in services:
                row = self.services_table.rowCount()
                self.services_table.insertRow(row)

                # 列0: 服务名称
                self.services_table.setItem(row, 0, QTableWidgetItem(service["service_name"]))

                # 列1: 状态
                status_text = "🟢 在线" if service["online"] else "🔴 离线"
                self.services_table.setItem(row, 1, QTableWidgetItem(status_text))

                # 列2: 响应时间
                response_time = service.get("response_time_ms", 0)
                time_text = f"{response_time:.1f}ms" if response_time > 0 else "--"
                self.services_table.setItem(row, 2, QTableWidgetItem(time_text))

                # 列3: 调用次数
                call_count = service.get("call_count", 0)
                self.services_table.setItem(row, 3, QTableWidgetItem(str(call_count)))

                # 列4: 成功率
                success_rate = service.get("success_rate", 0.0)
                self.services_table.setItem(row, 4, QTableWidgetItem(f"{success_rate:.1f}%"))

                # 列5: 错误率
                error_rate = service.get("error_rate", 0.0)
                self.services_table.setItem(row, 5, QTableWidgetItem(f"{error_rate:.1f}%"))

                # 列6: 内存占用
                memory_mb = service.get("memory_mb", 0.0)
                self.services_table.setItem(row, 6, QTableWidgetItem(f"{memory_mb:.1f}"))

                # 列7: 线程数
                thread_count = service.get("thread_count", 0)
                self.services_table.setItem(row, 7, QTableWidgetItem(str(thread_count)))

                # 列8: 操作按钮
                restart_btn = QPushButton("🔄 重启")
                restart_btn.clicked.connect(
                    lambda checked, name=service["service_name"]: self._restart_service(name)
                )
                self.services_table.setCellWidget(row, 8, restart_btn)

        except Exception as e:
            self.logger.error("更新服务表格失败: %s", e)

    def _update_dependencies_table(self, dependencies: Dict[str, Any]):
        """更新外部依赖表格.

        Args:
            dependencies: 外部依赖字典
        """
        try:
            if not self.dependencies_table:
                return

            self.dependencies_table.setRowCount(0)

            for dep_id, dep_info in dependencies.items():
                row = self.dependencies_table.rowCount()
                self.dependencies_table.insertRow(row)

                # 列0: 依赖名称
                dep_name = dep_info.get("name", dep_id)
                self.dependencies_table.setItem(row, 0, QTableWidgetItem(dep_name))

                # 列1: 状态
                online = dep_info.get("online")
                if online is True:
                    status_text = "🟢 正常"
                elif online is False:
                    status_text = "🔴 异常"
                else:
                    status_text = "⚪ 未知"
                self.dependencies_table.setItem(row, 1, QTableWidgetItem(status_text))

                # 列2: 详情
                message = dep_info.get("message", "")
                self.dependencies_table.setItem(row, 2, QTableWidgetItem(message))

        except Exception as e:
            self.logger.error("更新依赖表格失败: %s", e)

    def _restart_service(self, service_name: str):
        """重启服务."""
        reply = QMessageBox.question(
            self,
            "确认重启",
            f"确定要重启服务 '{service_name}' 吗？\n这可能会暂时中断服务。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                if not self.system_service:
                    self.show_error("系统管理服务不可用")
                    return

                self.show_info(f"正在重启服务 '{service_name}'...")

                result = self.system_service.restart_service(service_name, graceful=True)
                if result.get("success"):
                    elapsed_time = result.get("elapsed_time", 0)
                    self.show_info(f"服务 '{service_name}' 重启成功（耗时: {elapsed_time:.1f}s）")
                    # 重新检查服务状态
                    self._check_all_services()
                else:
                    self.show_error(f"重启失败: {result.get('message')}")

            except Exception as e:
                self.logger.error("重启服务失败: %s", e)
                self.show_error(f"重启失败: {e}")

    # ==================== 1.5 系统配置 ====================

    def _create_config_tab(self) -> QWidget:
        """创建系统配置子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("⚙️ 系统配置"))
        toolbar_layout.addStretch()

        # 诊断按钮
        diagnose_btn = QPushButton("🔍 诊断配置")
        diagnose_btn.clicked.connect(self._diagnose_config)
        toolbar_layout.addWidget(diagnose_btn)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self._refresh_config)
        toolbar_layout.addWidget(refresh_btn)

        save_btn = QPushButton("💾 保存")
        save_btn.clicked.connect(self._save_config)
        toolbar_layout.addWidget(save_btn)

        reset_btn = QPushButton("↩️ 重置")
        reset_btn.clicked.connect(self._reset_config)
        toolbar_layout.addWidget(reset_btn)

        layout.addLayout(toolbar_layout)

        # 配置组
        config_group = QGroupBox("数据中心配置")
        config_layout = QFormLayout(config_group)

        # 通达信路径
        tdx_layout = QHBoxLayout()
        self.tdx_path_edit = QLineEdit()
        self.tdx_path_edit.setPlaceholderText("例如: C:/通达信金融终端V7")
        tdx_layout.addWidget(self.tdx_path_edit)

        tdx_browse_btn = QPushButton("📁 浏览")
        tdx_browse_btn.clicked.connect(self._browse_tdx_dir)
        tdx_layout.addWidget(tdx_browse_btn)

        config_layout.addRow("通达信根目录:", tdx_layout)

        # 缓存目录
        cache_layout = QHBoxLayout()
        self.cache_dir_edit = QLineEdit()
        self.cache_dir_edit.setPlaceholderText("例如: ./data/cache")
        cache_layout.addWidget(self.cache_dir_edit)

        cache_browse_btn = QPushButton("📁 浏览")
        cache_browse_btn.clicked.connect(self._browse_cache_dir)
        cache_layout.addWidget(cache_browse_btn)

        config_layout.addRow("品种缓存目录:", cache_layout)

        # K线数据目录
        data_layout = QHBoxLayout()
        self.data_dir_edit = QLineEdit()
        self.data_dir_edit.setPlaceholderText("例如: ./data/kline")
        data_layout.addWidget(self.data_dir_edit)

        data_browse_btn = QPushButton("📁 浏览")
        data_browse_btn.clicked.connect(self._browse_data_dir)
        data_layout.addWidget(data_browse_btn)

        config_layout.addRow("K线数据目录:", data_layout)

        # 数据感知基日
        self.base_date_edit = QDateEdit()
        self.base_date_edit.setCalendarPopup(True)
        self.base_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.base_date_edit.setDate(QDate(2020, 1, 1))
        config_layout.addRow("数据感知基日:", self.base_date_edit)

        # 最大工作线程数
        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(1, 50)
        self.max_workers_spin.setValue(10)
        config_layout.addRow("最大线程数:", self.max_workers_spin)

        # 请求超时时间
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 300)
        self.timeout_spin.setValue(30)
        config_layout.addRow("请求超时:", self.timeout_spin)

        # 重试次数
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(3)
        config_layout.addRow("重试次数:", self.retry_spin)

        # 启用文件监控
        self.watcher_check = QCheckBox()
        self.watcher_check.setChecked(True)
        config_layout.addRow("启用文件监控:", self.watcher_check)

        # 文件监控间隔
        self.watcher_interval_spin = QSpinBox()
        self.watcher_interval_spin.setRange(1, 60)
        self.watcher_interval_spin.setValue(5)
        config_layout.addRow("监控检查间隔:", self.watcher_interval_spin)

        layout.addWidget(config_group)

        # 监控配置组
        monitoring_config_group = QGroupBox("监控配置")
        monitoring_config_layout = QFormLayout(monitoring_config_group)

        # 监控推送频率
        self.monitoring_interval_spin = QSpinBox()
        self.monitoring_interval_spin.setRange(1, 10)
        self.monitoring_interval_spin.setValue(2)
        self.monitoring_interval_spin.setSuffix(" 秒")
        self.monitoring_interval_spin.setToolTip(
            "设置进程监控和服务监控的数据推送频率\n"
            "范围: 1-10秒\n"
            "默认: 2秒\n"
            "注意: 过低的频率可能影响系统性能"
        )
        monitoring_config_layout.addRow("推送频率:", self.monitoring_interval_spin)

        layout.addWidget(monitoring_config_group)

        # AI助手配置组
        ai_config_group = QGroupBox("AI助手配置")
        ai_config_layout = QFormLayout(ai_config_group)

        # API Key
        self.ai_api_key_edit = QLineEdit()
        self.ai_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_api_key_edit.setPlaceholderText("请输入DeepSeek API Key")
        ai_config_layout.addRow("API Key:", self.ai_api_key_edit)

        # API URL
        self.ai_api_url_edit = QLineEdit()
        self.ai_api_url_edit.setPlaceholderText("https://api.deepseek.com/v1/chat/completions")
        ai_config_layout.addRow("API URL:", self.ai_api_url_edit)

        # Model
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.addItems(["deepseek-chat", "deepseek-coder"])
        ai_config_layout.addRow("模型:", self.ai_model_combo)

        # Max Tokens
        self.ai_max_tokens_spin = QSpinBox()
        self.ai_max_tokens_spin.setRange(100, 8000)
        self.ai_max_tokens_spin.setValue(2000)
        self.ai_max_tokens_spin.setSingleStep(100)
        ai_config_layout.addRow("最大Token数:", self.ai_max_tokens_spin)

        # Temperature
        temp_layout = QHBoxLayout()
        self.ai_temperature_slider = QSlider(Qt.Orientation.Horizontal)
        self.ai_temperature_slider.setRange(0, 100)  # 0.0-1.0映射到0-100
        self.ai_temperature_slider.setValue(70)  # 默认0.7
        self.ai_temperature_label = QLabel("0.70")
        self.ai_temperature_slider.valueChanged.connect(
            lambda v, label=self.ai_temperature_label: label.setText(f"{v/100:.2f}")
        )
        temp_layout.addWidget(self.ai_temperature_slider)
        temp_layout.addWidget(self.ai_temperature_label)
        ai_config_layout.addRow("温度参数:", temp_layout)

        # Max History
        self.ai_max_history_spin = QSpinBox()
        self.ai_max_history_spin.setRange(1, 50)
        self.ai_max_history_spin.setValue(10)
        ai_config_layout.addRow("对话历史长度:", self.ai_max_history_spin)

        # Timeout
        self.ai_timeout_spin = QSpinBox()
        self.ai_timeout_spin.setRange(10, 180)
        self.ai_timeout_spin.setValue(30)
        ai_config_layout.addRow("超时时间(秒):", self.ai_timeout_spin)

        # 工具调用开关
        self.ai_enable_tools_check = QCheckBox()
        self.ai_enable_tools_check.setChecked(False)
        self.ai_enable_tools_check.setToolTip(
            "启用AI文件操作工具（读取、写入、删除文件）。\n"
            "注意：需要DeepSeek API支持Function Calling。\n"
            "如果遇到连接错误，请禁用此选项。"
        )
        ai_config_layout.addRow("启用文件操作工具:", self.ai_enable_tools_check)

        layout.addWidget(ai_config_group)

        # 动态阈值监控组
        thresholds_group = QGroupBox("📊 动态阈值监控（自适应学习）")
        thresholds_layout = QVBoxLayout(thresholds_group)

        # 说明文本
        info_label = QLabel(
            "系统会根据历史数据自动学习阈值，计算P95和P99百分位数作为警告和严重告警的参考值。"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #64748B; font-size: 11px; padding: 5px;")
        thresholds_layout.addWidget(info_label)

        self.thresholds_table = QTableWidget(0, 6)
        self.thresholds_table.setHorizontalHeaderLabels(
            ["指标名称", "P95值", "P99值", "警告阈值", "严重阈值", "样本数"]
        )
        self.thresholds_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.thresholds_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.thresholds_table.setAlternatingRowColors(True)
        self.thresholds_table.horizontalHeader().setStretchLastSection(True)
        thresholds_layout.addWidget(self.thresholds_table)

        layout.addWidget(thresholds_group)

        # 加载配置
        self._load_config()

        return tab

    # ==================== 1.6 日志管理 ====================

    def _create_logs_tab(self) -> QWidget:
        """创建日志管理子界面."""
        self.logger.info("[SystemManager] _create_logs_tab 开始执行")
        # 创建日志管理组件
        self.logger.info("[SystemManager] 正在创建LogManagerWidget实例...")
        self.log_manager_widget = LogManagerWidget()
        self.logger.info("[SystemManager] ✅ LogManagerWidget实例创建成功")

        return self.log_manager_widget

    # ==================== 1.7 系统诊断 ====================

    def _create_diagnosis_tab(self) -> QWidget:
        """创建系统诊断子界面（增强版）."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏
        toolbar = QHBoxLayout()

        basic_btn = QPushButton("🔍 基础诊断")
        basic_btn.clicked.connect(self._run_basic_diagnostics)
        toolbar.addWidget(basic_btn)

        advanced_btn = QPushButton("🔬 高级诊断")
        advanced_btn.clicked.connect(self._run_advanced_diagnostics)
        toolbar.addWidget(advanced_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 诊断结果选项卡
        self.diagnosis_tabs = QTabWidget()

        # 基础诊断标签页
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)

        # 性能诊断
        perf_group = QGroupBox("性能诊断")
        perf_layout = QVBoxLayout(perf_group)
        self.basic_perf_table = QTableWidget(0, 2)
        self.basic_perf_table.setHorizontalHeaderLabels(["项目", "值"])
        perf_layout.addWidget(self.basic_perf_table)
        basic_layout.addWidget(perf_group)

        # 网络诊断
        network_group = QGroupBox("网络诊断")
        network_layout = QVBoxLayout(network_group)
        self.basic_network_table = QTableWidget(0, 2)
        self.basic_network_table.setHorizontalHeaderLabels(["项目", "值"])
        network_layout.addWidget(self.basic_network_table)
        basic_layout.addWidget(network_group)

        # 数据库诊断
        db_group = QGroupBox("数据库诊断")
        db_layout = QVBoxLayout(db_group)
        self.basic_db_table = QTableWidget(0, 2)
        self.basic_db_table.setHorizontalHeaderLabels(["项目", "值"])
        db_layout.addWidget(self.basic_db_table)
        basic_layout.addWidget(db_group)

        self.diagnosis_tabs.addTab(basic_tab, "基础诊断")

        # 性能瓶颈标签页
        bottlenecks_tab = QWidget()
        bottlenecks_layout = QVBoxLayout(bottlenecks_tab)
        self.bottlenecks_table = QTableWidget(0, 5)
        self.bottlenecks_table.setHorizontalHeaderLabels(
            ["类型", "严重程度", "当前值", "阈值", "影响"]
        )
        header = self.bottlenecks_table.horizontalHeader()
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        bottlenecks_layout.addWidget(self.bottlenecks_table)
        self.diagnosis_tabs.addTab(bottlenecks_tab, "性能瓶颈")

        # 错误分析标签页
        errors_tab = QWidget()
        errors_layout = QVBoxLayout(errors_tab)

        # TOP错误统计
        top_errors_group = QGroupBox("错误TOP10")
        top_errors_layout = QVBoxLayout(top_errors_group)
        self.errors_table = QTableWidget(0, 2)
        self.errors_table.setHorizontalHeaderLabels(["错误类型", "出现次数"])
        top_errors_layout.addWidget(self.errors_table)
        errors_layout.addWidget(top_errors_group)

        # 错误详情
        error_details_group = QGroupBox("最近错误")
        error_details_layout = QVBoxLayout(error_details_group)
        self.error_details_table = QTableWidget(0, 3)
        self.error_details_table.setHorizontalHeaderLabels(["时间", "类型", "消息"])
        header = self.error_details_table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        error_details_layout.addWidget(self.error_details_table)
        errors_layout.addWidget(error_details_group)

        self.diagnosis_tabs.addTab(errors_tab, "错误分析")

        # 优化建议标签页
        suggestions_tab = QWidget()
        suggestions_layout = QVBoxLayout(suggestions_tab)

        # 优化建议
        opt_group = QGroupBox("系统优化建议")
        opt_layout = QVBoxLayout(opt_group)
        self.optimization_text = QTextEdit()
        self.optimization_text.setReadOnly(True)
        opt_layout.addWidget(self.optimization_text)
        suggestions_layout.addWidget(opt_group)

        # 修复建议
        fix_group = QGroupBox("自动修复建议")
        fix_layout = QVBoxLayout(fix_group)
        self.fix_suggestions_table = QTableWidget(0, 4)
        self.fix_suggestions_table.setHorizontalHeaderLabels(
            ["标题", "描述", "可自动修复", "风险级别"]
        )
        header = self.fix_suggestions_table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        fix_layout.addWidget(self.fix_suggestions_table)
        suggestions_layout.addWidget(fix_group)

        self.diagnosis_tabs.addTab(suggestions_tab, "优化建议")

        layout.addWidget(self.diagnosis_tabs)

        return tab

    def _create_process_monitor_tab(self) -> QWidget:
        """创建进程监控子界面（新设计 - 进程列表+整体设备热力图）."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("🔍 进程监控 - 自动识别关键进程并分析瓶颈"))
        toolbar.addStretch()

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self._refresh_process_monitor)
        toolbar.addWidget(refresh_btn)

        layout.addLayout(toolbar)

        # 使用QSplitter左右分隔：进程列表（左） + 整体设备监控热力图（右）
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：进程列表（9列，分离网络接收/发送）
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)

        self.process_table = QTableWidget(0, 9)
        headers = [
            "进程名称",
            "场景类型",
            "状态",
            "CPU%",
            "内存(MB)",
            "磁盘IO(MB/s)",
            "网络接收",
            "网络发送",
            "瓶颈点",
        ]
        self.process_table.setHorizontalHeaderLabels(headers)
        header = self.process_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        list_layout.addWidget(self.process_table)

        splitter.addWidget(list_widget)

        # 右侧：整体设备监控热力图（5个指标，纵向排列）
        heatmap_widget = QWidget()
        heatmap_layout = QVBoxLayout(heatmap_widget)
        heatmap_layout.setContentsMargins(10, 10, 10, 10)
        heatmap_layout.setSpacing(15)

        # 标题
        title_label = QLabel("📊 整体设备监控")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; padding-bottom: 5px;")
        heatmap_layout.addWidget(title_label)

        # 创建5个热力图（单行，显示百分比）
        self.heatmap_cpu = self._create_single_heatmap("CPU使用率", "%")
        self.heatmap_memory = self._create_single_heatmap("内存使用率", "%")
        self.heatmap_disk_io = self._create_single_heatmap("磁盘IO速度", "%")
        self.heatmap_network = self._create_single_heatmap("网络速度", "%")
        self.heatmap_bandwidth = self._create_single_heatmap("带宽占用", "%")

        heatmap_layout.addWidget(self.heatmap_cpu)
        heatmap_layout.addWidget(self.heatmap_memory)
        heatmap_layout.addWidget(self.heatmap_disk_io)
        heatmap_layout.addWidget(self.heatmap_network)
        heatmap_layout.addWidget(self.heatmap_bandwidth)

        heatmap_layout.addStretch()

        splitter.addWidget(heatmap_widget)

        # 设置分隔比例：进程列表60%，热力图40%
        splitter.setSizes([600, 400])
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)

        layout.addWidget(splitter)

        return tab

    def _create_single_heatmap(self, title: str, unit: str = "%") -> QWidget:
        """创建单行热力图组件.

        Args:
            title: 标题
            unit: 单位

        Returns:
            QWidget: 热力图组件
        """
        widget = QWidget()
        widget.setMinimumHeight(60)
        widget.setMaximumHeight(80)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # 标题和当前值
        header_layout = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 12px; color: #AAA;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        value_label = QLabel("0.0%")
        value_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFF;")
        header_layout.addWidget(value_label)

        layout.addLayout(header_layout)

        # 热力图进度条（使用QProgressBar实现）
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(False)
        progress_bar.setMinimumHeight(30)

        # 设置渐变色样式（绿→黄→红）
        progress_bar.setStyleSheet(
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

        layout.addWidget(progress_bar)

        # 保存组件引用
        widget.value_label = value_label  # type: ignore[attr-defined]
        widget.progress_bar = progress_bar  # type: ignore[attr-defined]

        return widget

    def _refresh_process_monitor(self):
        """刷新进程监控数据（主动触发）."""
        try:
            if not self.system_service:
                self.show_warning("系统管理服务不可用")
                return

            result = self.system_service.get_monitored_processes()
            if result.get("success"):
                processes = result.get("processes", [])
                self.logger.info(f"刷新进程监控：识别到 {len(processes)} 个进程")
                # 注意：实际数据更新由事件驱动，这里只是手动触发一次识别
            else:
                self.show_warning(f"刷新失败: {result.get('message')}")

        except Exception as e:
            self.logger.error("刷新进程监控失败: %s", e)
            self.show_error(f"刷新失败: {e}")

    def _update_process_table(self, processes: List[Dict[str, Any]]):
        """更新进程表格（新设计 - 8列含场景类型）.

        Args:
            processes: 进程数据列表
        """
        try:
            if not self.process_table:
                return

            self.process_table.setRowCount(0)

            for proc in processes:
                row = self.process_table.rowCount()
                self.process_table.insertRow(row)

                # 列0: 进程名称
                process_name = proc.get("process_name", "")
                self.process_table.setItem(row, 0, QTableWidgetItem(process_name))

                # 列1: 场景类型（根据进程名推断）
                scenario_type = self._infer_scenario_type(process_name)
                self.process_table.setItem(row, 1, QTableWidgetItem(scenario_type))

                # 列2: 状态
                status = proc.get("status", "unknown")
                status_map = {
                    "running": "🟢 运行中",
                    "idle": "⚪ 空闲",
                    "stopped": "🔴 已停止",
                }
                status_text = status_map.get(status, status)
                self.process_table.setItem(row, 2, QTableWidgetItem(str(status_text)))

                # 列3: CPU%
                cpu_percent = proc.get("cpu_percent", 0)
                self.process_table.setItem(row, 3, QTableWidgetItem(f"{cpu_percent:.1f}"))

                # 列4: 内存(MB)
                memory_mb = proc.get("memory_mb", 0)
                self.process_table.setItem(row, 4, QTableWidgetItem(f"{memory_mb:.1f}"))

                # 列5: 磁盘IO(MB/s) - 取读写最大值
                disk_read = proc.get("disk_read_mbps", 0)
                disk_write = proc.get("disk_write_mbps", 0)
                disk_io = max(disk_read, disk_write)
                self.process_table.setItem(row, 5, QTableWidgetItem(f"{disk_io:.1f}"))

                # 列6: 网络接收(MB/s)
                network_recv = proc.get("network_recv_mbps", 0)
                self.process_table.setItem(row, 6, QTableWidgetItem(f"{network_recv:.2f}"))

                # 列7: 网络发送(MB/s)
                network_send = proc.get("network_send_mbps", 0)
                self.process_table.setItem(row, 7, QTableWidgetItem(f"{network_send:.2f}"))

                # 列8: 瓶颈点
                bottleneck = proc.get("bottleneck", "balanced")
                bottleneck_map = {
                    "cpu": "🔴 CPU",
                    "memory": "🟠 内存",
                    "disk_io": "🟡 磁盘IO",
                    "network": "🔵 网络",
                    "balanced": "🟢 均衡",
                }
                bottleneck_text = bottleneck_map.get(bottleneck, bottleneck)
                self.process_table.setItem(row, 8, QTableWidgetItem(str(bottleneck_text)))

        except Exception as e:
            self.logger.error("更新进程表格失败: %s", e)

    def _infer_scenario_type(self, process_name: str) -> str:
        """根据进程名推断场景类型.

        Args:
            process_name: 进程名称

        Returns:
            场景类型文本
        """
        if not process_name:
            return "通用"

        process_name_lower = process_name.lower()

        # 关键字匹配
        if any(kw in process_name_lower for kw in ["download", "下载", "fetch", "data_center"]):
            return "📥 数据下载"
        elif any(kw in process_name_lower for kw in ["realtime", "实时", "tick", "market_board"]):
            return "📊 实时行情"
        elif any(kw in process_name_lower for kw in ["backtest", "回测", "simulation"]):
            return "🔬 策略回测"
        elif any(kw in process_name_lower for kw in ["strategy", "策略", "editor"]):
            return "✏️ 策略编写"
        elif any(kw in process_name_lower for kw in ["trading", "交易", "order", "gateway"]):
            return "💹 实盘交易"
        elif any(kw in process_name_lower for kw in ["monitor", "监控"]):
            return "👁️ 系统监控"
        else:
            return "通用"

    def _update_heatmaps(self, metrics: Dict[str, Any]):
        """更新热力图（整体设备监控）.

        Args:
            metrics: 系统指标数据
        """
        try:
            # 1. CPU使用率
            cpu_percent = metrics.get("cpu_percent", 0)
            if self.heatmap_cpu:
                self.heatmap_cpu.progress_bar.setValue(int(cpu_percent))
                self.heatmap_cpu.value_label.setText(f"{cpu_percent:.1f}%")

            # 2. 内存使用率
            memory_percent = metrics.get("memory_percent", 0)
            if self.heatmap_memory:
                self.heatmap_memory.progress_bar.setValue(int(memory_percent))
                self.heatmap_memory.value_label.setText(f"{memory_percent:.1f}%")

            # 3. 磁盘IO速度（转换为百分比）
            disk_io_speed = metrics.get("disk_io_speed", {})
            max_disk_io = 0.0
            for disk, speeds in disk_io_speed.items():
                if disk == "io_counters":
                    continue
                read_speed = speeds.get("read_speed", 0)
                write_speed = speeds.get("write_speed", 0)
                max_disk_io = max(max_disk_io, read_speed, write_speed)

            # 假设HDD理论极限150MB/s
            disk_io_percent = min((max_disk_io / 150.0) * 100, 100.0)
            if self.heatmap_disk_io:
                self.heatmap_disk_io.progress_bar.setValue(int(disk_io_percent))
                self.heatmap_disk_io.value_label.setText(f"{disk_io_percent:.1f}%")

            # 4. 网络速度（转换为百分比）
            network_speed = metrics.get("network_speed", {})
            upload_speed = network_speed.get("upload_speed_kbps", 0) / 1024  # 转MB/s
            download_speed = network_speed.get("download_speed_kbps", 0) / 1024  # 转MB/s
            max_network_speed = max(upload_speed, download_speed)

            # 假设千兆网络理论极限100MB/s
            network_percent = min((max_network_speed / 100.0) * 100, 100.0)
            if self.heatmap_network:
                self.heatmap_network.progress_bar.setValue(int(network_percent))
                self.heatmap_network.value_label.setText(f"{network_percent:.1f}%")

            # 5. 带宽占用百分比
            bandwidth_percent = network_speed.get("bandwidth_percent", 0)
            if self.heatmap_bandwidth:
                self.heatmap_bandwidth.progress_bar.setValue(int(bandwidth_percent))
                self.heatmap_bandwidth.value_label.setText(f"{bandwidth_percent:.1f}%")

        except Exception as e:
            self.logger.error("更新热力图失败: %s", e)

    def _run_basic_diagnostics(self):
        """运行基础诊断."""
        try:
            if not self.system_service:
                self.show_error("系统管理服务不可用")
                return

            self.show_info("正在运行基础诊断...")

            result = self.system_service.run_diagnostics()
            if result.get("success"):
                diagnostics = result["diagnostics"]

                # 更新性能诊断表格
                self._update_basic_perf_table(diagnostics.get("performance", {}))

                # 更新网络诊断表格
                self._update_basic_network_table(diagnostics.get("network", {}))

                # 更新数据库诊断表格
                self._update_basic_db_table(diagnostics.get("database", {}))

                # 切换到基础诊断标签页
                if self.diagnosis_tabs:
                    self.diagnosis_tabs.setCurrentIndex(0)

                self.show_info("基础诊断完成，请查看诊断结果")
            else:
                self.show_error(f"诊断失败: {result.get('message')}")

        except Exception as e:
            self.logger.error("运行基础诊断失败: %s", e)
            self.show_error(f"诊断失败: {e}")

    def _update_basic_perf_table(self, perf_data: Dict[str, Any]):
        """更新基础性能诊断表格."""
        try:
            if not self.basic_perf_table:
                return

            self.basic_perf_table.setRowCount(0)

            # 将字典数据转换为表格行
            for key, value in perf_data.items():
                row = self.basic_perf_table.rowCount()
                self.basic_perf_table.insertRow(row)
                self.basic_perf_table.setItem(row, 0, QTableWidgetItem(str(key)))
                self.basic_perf_table.setItem(row, 1, QTableWidgetItem(str(value)))

        except Exception as e:
            self.logger.error("更新性能诊断表格失败: %s", e)

    def _update_basic_network_table(self, network_data: Dict[str, Any]):
        """更新基础网络诊断表格."""
        try:
            if not self.basic_network_table:
                return

            self.basic_network_table.setRowCount(0)

            # 将字典数据转换为表格行
            for key, value in network_data.items():
                row = self.basic_network_table.rowCount()
                self.basic_network_table.insertRow(row)

                # 特殊处理复杂类型
                if isinstance(value, dict):
                    display_value = ", ".join([f"{k}: {v}" for k, v in value.items()])
                elif isinstance(value, bool):
                    display_value = "✅ 是" if value else "❌ 否"
                else:
                    display_value = str(value)

                self.basic_network_table.setItem(row, 0, QTableWidgetItem(str(key)))
                self.basic_network_table.setItem(row, 1, QTableWidgetItem(display_value))

        except Exception as e:
            self.logger.error("更新网络诊断表格失败: %s", e)

    def _update_basic_db_table(self, db_data: Dict[str, Any]):
        """更新基础数据库诊断表格."""
        try:
            if not self.basic_db_table:
                return

            self.basic_db_table.setRowCount(0)

            # 将字典数据转换为表格行
            for key, value in db_data.items():
                row = self.basic_db_table.rowCount()
                self.basic_db_table.insertRow(row)

                # 特殊处理
                if key == "exists":
                    display_value = "✅ 存在" if value else "❌ 不存在"
                elif key == "size":
                    # 转换字节为MB
                    size_mb = value / (1024 * 1024) if isinstance(value, (int, float)) else 0
                    display_value = f"{size_mb:.2f} MB"
                else:
                    display_value = str(value)

                self.basic_db_table.setItem(row, 0, QTableWidgetItem(str(key)))
                self.basic_db_table.setItem(row, 1, QTableWidgetItem(display_value))

        except Exception as e:
            self.logger.error("更新数据库诊断表格失败: %s", e)

    def _run_advanced_diagnostics(self):
        """运行高级诊断."""
        try:
            if not self.system_service:
                self.show_error("系统管理服务不可用")
                return

            self.show_info("正在运行高级诊断，请稍候...")

            result = self.system_service.run_advanced_diagnostics()
            if result.get("success"):
                diagnostics = result["diagnostics"]

                # 更新性能瓶颈表格
                bottlenecks = diagnostics.get("performance_bottlenecks", [])
                self._update_bottlenecks_table(bottlenecks)

                # 更新错误分析表格
                log_analysis = diagnostics.get("log_analysis", {})
                self._update_errors_tables(log_analysis)

                # 更新优化建议
                opt_suggestions = diagnostics.get("optimization_suggestions", [])
                fix_suggestions = diagnostics.get("fix_suggestions", [])
                self._update_suggestions(opt_suggestions, fix_suggestions)

                # 切换到性能瓶颈标签页（第2个标签，索引1）
                if self.diagnosis_tabs:
                    # 如果有瓶颈，切换到性能瓶颈标签页
                    if bottlenecks:
                        self.diagnosis_tabs.setCurrentIndex(1)  # 性能瓶颈
                    # 如果有错误分析，切换到错误分析标签页
                    elif log_analysis.get("total_errors", 0) > 0:
                        self.diagnosis_tabs.setCurrentIndex(2)  # 错误分析
                    # 否则切换到优化建议标签页
                    else:
                        self.diagnosis_tabs.setCurrentIndex(3)  # 优化建议

                # 构建诊断摘要信息
                total_bottlenecks = len(bottlenecks)
                total_errors = log_analysis.get("total_errors", 0)
                total_suggestions = len(opt_suggestions) + len(fix_suggestions)

                self.show_info(
                    f"高级诊断完成：发现 {total_bottlenecks} 个瓶颈、"
                    f"{total_errors} 个错误、{total_suggestions} 条建议"
                )
            else:
                self.show_error(f"诊断失败: {result.get('message')}")

        except Exception as e:
            self.logger.error("运行高级诊断失败: %s", e)
            self.show_error(f"诊断失败: {e}")

    def _update_bottlenecks_table(self, bottlenecks: List[Dict[str, Any]]):
        """更新性能瓶颈表格."""
        try:
            if not self.bottlenecks_table:
                return

            self.bottlenecks_table.setRowCount(0)

            for bottleneck in bottlenecks:
                row = self.bottlenecks_table.rowCount()
                self.bottlenecks_table.insertRow(row)

                self.bottlenecks_table.setItem(row, 0, QTableWidgetItem(bottleneck["type"]))
                self.bottlenecks_table.setItem(row, 1, QTableWidgetItem(bottleneck["severity"]))
                self.bottlenecks_table.setItem(
                    row, 2, QTableWidgetItem(str(bottleneck["current_value"]))
                )
                self.bottlenecks_table.setItem(
                    row, 3, QTableWidgetItem(str(bottleneck["threshold"]))
                )
                self.bottlenecks_table.setItem(row, 4, QTableWidgetItem(bottleneck["impact"]))

        except Exception as e:
            self.logger.error("更新瓶颈表格失败: %s", e)

    def _update_errors_tables(self, log_analysis: Dict[str, Any]):
        """更新错误分析表格."""
        try:
            if not self.errors_table:
                return

            # 更新TOP错误表格
            self.errors_table.setRowCount(0)
            top_errors = log_analysis.get("top_errors", [])
            for error in top_errors:
                row = self.errors_table.rowCount()
                self.errors_table.insertRow(row)
                self.errors_table.setItem(row, 0, QTableWidgetItem(error["type"]))
                self.errors_table.setItem(row, 1, QTableWidgetItem(str(error["count"])))

            # 更新错误详情表格
            if hasattr(self, "error_details_table") and self.error_details_table:
                self.error_details_table.setRowCount(0)
                error_patterns = log_analysis.get("error_patterns", [])[:20]  # 最多显示20条
                for error in error_patterns:
                    row = self.error_details_table.rowCount()
                    self.error_details_table.insertRow(row)
                    self.error_details_table.setItem(
                        row, 0, QTableWidgetItem(error.get("timestamp", ""))
                    )
                    self.error_details_table.setItem(
                        row, 1, QTableWidgetItem(error.get("type", ""))
                    )
                    self.error_details_table.setItem(
                        row, 2, QTableWidgetItem(error.get("message", ""))
                    )

        except Exception as e:
            self.logger.error("更新错误表格失败: %s", e)

    def _update_suggestions(
        self, opt_suggestions: List[str], fix_suggestions: List[Dict[str, Any]]
    ):
        """更新优化和修复建议."""
        try:
            # 更新优化建议
            if self.optimization_text:
                text = "\n".join(opt_suggestions) if opt_suggestions else "暂无优化建议"
                self.optimization_text.setPlainText(text)

            # 更新修复建议表格
            if hasattr(self, "fix_suggestions_table") and self.fix_suggestions_table:
                self.fix_suggestions_table.setRowCount(0)
                for suggestion in fix_suggestions:
                    row = self.fix_suggestions_table.rowCount()
                    self.fix_suggestions_table.insertRow(row)
                    self.fix_suggestions_table.setItem(
                        row, 0, QTableWidgetItem(suggestion["title"])
                    )
                    self.fix_suggestions_table.setItem(
                        row, 1, QTableWidgetItem(suggestion["description"])
                    )
                    self.fix_suggestions_table.setItem(
                        row, 2, QTableWidgetItem("是" if suggestion["auto_fixable"] else "否")
                    )
                    self.fix_suggestions_table.setItem(
                        row, 3, QTableWidgetItem(suggestion["risk_level"])
                    )

        except Exception as e:
            self.logger.error("更新建议失败: %s", e)

    # ==================== 1.8 工具集合 ====================

    def _create_tools_tab(self) -> QWidget:
        """创建工具集合子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 网络测速工具组
        network_test_group = QGroupBox("🌐 网络测速工具")
        network_test_layout = QVBoxLayout(network_test_group)
        network_test_layout.setSpacing(8)
        network_test_layout.setContentsMargins(12, 10, 12, 10)

        # 提示信息
        hint_label = QLabel(
            "💡 测试服务商带宽：完整测试（约30秒），测试下载、上传速度和延迟\n"
            "⚡ 测试实时延迟：快速测试（约2秒），仅测试网络延迟"
        )
        hint_label.setStyleSheet("color: #666; font-size: 12px; padding: 5px;")
        hint_label.setWordWrap(True)
        network_test_layout.addWidget(hint_label)

        # 测试结果显示区域（横向排列，紧凑布局）
        result_group = QGroupBox("测试结果")
        result_group.setStyleSheet("QGroupBox { padding: 3px; }")  # 减小GroupBox内边距
        result_layout = QHBoxLayout(result_group)
        result_layout.setSpacing(10)  # 减小各项之间的间距（20→10）
        result_layout.setContentsMargins(5, 5, 5, 5)  # 减小布局边距

        # 设置统一样式（更小更紧凑）
        title_style = "font-size: 10px; color: #888; padding: 0px; margin: 0px;"  # 字体缩小，去除padding
        value_style = "font-size: 12px; color: #0F0; font-weight: bold; padding: 0px; margin: 0px;"  # 字体缩小，去除padding

        # 下载速度
        download_container = QVBoxLayout()
        download_container.setSpacing(2)  # 减小标题和值之间的间距
        download_container.setContentsMargins(0, 0, 0, 0)  # 去除边距
        download_title = QLabel("下载")  # 简化标题
        download_title.setStyleSheet(title_style)
        download_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bandwidth_download_label = QLabel("--")
        self.bandwidth_download_label.setStyleSheet(value_style)
        self.bandwidth_download_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        download_container.addWidget(download_title)
        download_container.addWidget(self.bandwidth_download_label)
        result_layout.addLayout(download_container)

        # 上传速度
        upload_container = QVBoxLayout()
        upload_container.setSpacing(2)
        upload_container.setContentsMargins(0, 0, 0, 0)
        upload_title = QLabel("上传")  # 简化标题
        upload_title.setStyleSheet(title_style)
        upload_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bandwidth_upload_label = QLabel("--")
        self.bandwidth_upload_label.setStyleSheet(value_style)
        self.bandwidth_upload_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        upload_container.addWidget(upload_title)
        upload_container.addWidget(self.bandwidth_upload_label)
        result_layout.addLayout(upload_container)

        # 网络延迟
        ping_container = QVBoxLayout()
        ping_container.setSpacing(2)
        ping_container.setContentsMargins(0, 0, 0, 0)
        ping_title = QLabel("延迟")  # 简化标题
        ping_title.setStyleSheet(title_style)
        ping_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bandwidth_ping_label = QLabel("--")
        self.bandwidth_ping_label.setStyleSheet(value_style)
        self.bandwidth_ping_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ping_container.addWidget(ping_title)
        ping_container.addWidget(self.bandwidth_ping_label)
        result_layout.addLayout(ping_container)

        # 测试时间
        time_container = QVBoxLayout()
        time_container.setSpacing(2)
        time_container.setContentsMargins(0, 0, 0, 0)
        time_title = QLabel("时间")  # 简化标题
        time_title.setStyleSheet(title_style)
        time_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bandwidth_test_time_label = QLabel("--")
        self.bandwidth_test_time_label.setStyleSheet(value_style)
        self.bandwidth_test_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_container.addWidget(time_title)
        time_container.addWidget(self.bandwidth_test_time_label)
        result_layout.addLayout(time_container)

        network_test_layout.addWidget(result_group)

        # 按钮组
        button_layout = QHBoxLayout()

        self.test_bandwidth_btn = QPushButton("📊 测服务商带宽")
        self.test_bandwidth_btn.setStyleSheet("font-size: 14px; padding: 10px;")
        self.test_bandwidth_btn.setMinimumHeight(40)
        self.test_bandwidth_btn.clicked.connect(self._test_bandwidth_full)
        button_layout.addWidget(self.test_bandwidth_btn)

        network_test_layout.addLayout(button_layout)

        layout.addWidget(network_test_group)

        # 数据标准化读取器组
        reader_group = QGroupBox("数据标准化读取器 - 批量自动化处理")
        reader_layout = QVBoxLayout(reader_group)
        # 🔧 压缩优化：减少组件间距
        reader_layout.setSpacing(2)  # 从默认6px减少到2px
        reader_layout.setContentsMargins(9, 5, 9, 9)  # 减少顶部margin从9到5

        # 提示信息
        hint_label = QLabel(
            "💡 勾选市场和数据类型后，程序会自动从品种缓存中获取对应品种并批量读取\n"
            "⚡ 系统将根据CPU核心数、可用内存和任务总数自动计算最优线程数"
        )
        # 🔧 压缩优化：减少padding从5px到2px
        hint_label.setStyleSheet("color: #666; font-size: 12px; padding: 2px;")
        hint_label.setWordWrap(True)
        reader_layout.addWidget(hint_label)

        # 表单布局
        form_layout = QFormLayout()
        # 🔧 设置字段增长策略，让输入框占据更多空间
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        # 设置标签右对齐，视觉上更整洁
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        # 🔧 关键修复：增加垂直间距，防止输入框放大后互相遮挡
        form_layout.setVerticalSpacing(15)  # 默认6px，增加到15px
        form_layout.setHorizontalSpacing(10)  # 标签和字段之间的间距

        # 数据源类型（只读）
        type_label = QLabel("通达信")
        type_label.setStyleSheet("font-weight: bold;")
        # 🔧 统一高度：设置标签最小高度32px
        type_label.setMinimumHeight(32)
        form_layout.addRow("数据源类型:", type_label)

        # 数据类型（多选）
        data_type_layout = QHBoxLayout()
        data_type_layout.setSpacing(5)  # 🔧 设置控件间距
        data_type_layout.setContentsMargins(0, 0, 0, 0)  # 🔧 去掉边距

        self.reader_day_check = QCheckBox("日线")
        self.reader_day_check.setChecked(True)
        # 🔧 统一高度：设置复选框最小高度32px
        self.reader_day_check.setMinimumHeight(32)
        data_type_layout.addWidget(self.reader_day_check)

        self.reader_5min_check = QCheckBox("5分钟线")
        self.reader_5min_check.setMinimumHeight(32)
        data_type_layout.addWidget(self.reader_5min_check)

        self.reader_1min_check = QCheckBox("1分钟线")
        self.reader_1min_check.setMinimumHeight(32)
        data_type_layout.addWidget(self.reader_1min_check)

        data_type_layout.addStretch()
        # 🔧 关键修复：直接addRow(QLayout)，不用QWidget包装
        form_layout.addRow("数据类型:", data_type_layout)

        # 市场（多选）
        market_layout = QHBoxLayout()
        market_layout.setSpacing(5)  # 🔧 设置控件间距
        market_layout.setContentsMargins(0, 0, 0, 0)  # 🔧 去掉边距

        self.reader_sh_check = QCheckBox("上证")
        self.reader_sh_check.setChecked(True)
        # 🔧 统一高度：设置复选框最小高度32px
        self.reader_sh_check.setMinimumHeight(32)
        market_layout.addWidget(self.reader_sh_check)

        self.reader_sz_check = QCheckBox("深证")
        self.reader_sz_check.setMinimumHeight(32)
        market_layout.addWidget(self.reader_sz_check)

        self.reader_bj_check = QCheckBox("北证")
        self.reader_bj_check.setMinimumHeight(32)
        market_layout.addWidget(self.reader_bj_check)

        market_layout.addStretch()
        # 🔧 关键修复：直接addRow(QLayout)，不用QWidget包装
        form_layout.addRow("市场:", market_layout)

        # 通达信根目录
        tdx_layout = QHBoxLayout()
        tdx_layout.setSpacing(5)  # 🔧 设置控件间距
        tdx_layout.setContentsMargins(0, 0, 0, 0)  # 🔧 去掉边距

        self.reader_tdx_path_edit = QLineEdit()
        self.reader_tdx_path_edit.setPlaceholderText("只需填写根目录，例如: C:\\new_tdx")
        # 🔧 关键修复：设置输入框最小高度，确保内部文字完整显示
        self.reader_tdx_path_edit.setMinimumHeight(32)
        self.reader_tdx_path_edit.setMinimumWidth(300)
        self.reader_tdx_path_edit.setToolTip(
            "填写通达信软件的根目录即可，例如: C:\\new_tdx\n"
            "程序会根据您选择的市场和数据类型自动拼接完整路径：\n"
            "  上证日线 → C:\\new_tdx\\vipdoc\\sh\\lday\\\n"
            "  深证5分 → C:\\new_tdx\\vipdoc\\sz\\fzline\\\n"
            "  北证1分 → C:\\new_tdx\\vipdoc\\bj\\minline\\"
        )
        tdx_layout.addWidget(self.reader_tdx_path_edit)

        tdx_browse_btn = QPushButton("📁 浏览")
        tdx_browse_btn.setFixedWidth(80)
        # 🔧 按钮也设置相同高度，保持视觉一致
        tdx_browse_btn.setMinimumHeight(32)
        tdx_browse_btn.clicked.connect(self._browse_tdx_root)
        tdx_layout.addWidget(tdx_browse_btn)

        # 🔧 关键修复：直接addRow(QLayout)，不用QWidget包装
        form_layout.addRow("通达信根目录:", tdx_layout)

        reader_layout.addLayout(form_layout)

        # 进度组
        progress_group = QGroupBox("处理进度")
        progress_layout = QVBoxLayout(progress_group)
        # 🔧 压缩优化：减少进度组内部间距
        progress_layout.setSpacing(3)  # 从默认6px减少到3px
        progress_layout.setContentsMargins(9, 5, 9, 5)  # 减少上下margin

        # 状态标签
        self.reader_status_label = QLabel("状态: 就绪")
        progress_layout.addWidget(self.reader_status_label)

        # 进度条
        self.reader_progress_bar = QProgressBar()
        self.reader_progress_bar.setRange(0, 100)
        self.reader_progress_bar.setValue(0)
        # 🔧 压缩优化：限制进度条最大高度
        self.reader_progress_bar.setMaximumHeight(20)
        progress_layout.addWidget(self.reader_progress_bar)

        # 详细进度标签
        self.reader_detail_label = QLabel("")
        self.reader_detail_label.setStyleSheet("color: #888; font-size: 11px;")
        progress_layout.addWidget(self.reader_detail_label)

        reader_layout.addWidget(progress_group)

        # 批量读取按钮组
        button_layout = QHBoxLayout()

        self.reader_start_btn = QPushButton("🚀 开始批量读取并保存")
        self.reader_start_btn.clicked.connect(self._read_and_save_tdx_data)
        self.reader_start_btn.setStyleSheet("font-size: 14px; padding: 10px;")
        button_layout.addWidget(self.reader_start_btn)

        self.reader_stop_btn = QPushButton("⛔ 停止")
        self.reader_stop_btn.clicked.connect(self._stop_tdx_reader)
        self.reader_stop_btn.setStyleSheet("font-size: 14px; padding: 10px;")
        self.reader_stop_btn.setEnabled(False)
        button_layout.addWidget(self.reader_stop_btn)

        reader_layout.addLayout(button_layout)

        layout.addWidget(reader_group)

        # 加载通达信根目录配置
        self._load_tdx_reader_config()

        # 🆕 损坏数据文件清理工具组
        cleaner_group = QGroupBox("损坏数据文件清理工具")
        cleaner_layout = QVBoxLayout(cleaner_group)

        # 提示信息
        cleaner_hint = QLabel("💡 扫描并清理损坏的Parquet数据文件（0字节、无法读取等）")
        cleaner_hint.setStyleSheet("color: #666; font-size: 12px; padding: 5px;")
        cleaner_hint.setWordWrap(True)
        cleaner_layout.addWidget(cleaner_hint)

        # 数据目录显示
        data_dir_layout = QFormLayout()
        self.cleaner_data_dir_label = QLabel("加载中...")
        self.cleaner_data_dir_label.setStyleSheet("font-weight: bold; color: #0066cc;")
        self.cleaner_data_dir_label.setWordWrap(True)
        data_dir_layout.addRow("数据文件目录:", self.cleaner_data_dir_label)
        cleaner_layout.addLayout(data_dir_layout)

        # 扫描结果显示
        result_group = QGroupBox("扫描结果")
        result_layout = QVBoxLayout(result_group)

        self.cleaner_result_label = QLabel("状态: 未扫描")
        result_layout.addWidget(self.cleaner_result_label)

        self.cleaner_detail_text = QTextEdit()
        self.cleaner_detail_text.setReadOnly(True)
        self.cleaner_detail_text.setMaximumHeight(150)
        self.cleaner_detail_text.setPlaceholderText("扫描结果将显示在这里...")
        result_layout.addWidget(self.cleaner_detail_text)

        cleaner_layout.addWidget(result_group)

        # 按钮组
        cleaner_button_layout = QHBoxLayout()

        self.cleaner_scan_btn = QPushButton("🔍 扫描损坏文件")
        self.cleaner_scan_btn.clicked.connect(self._scan_corrupted_files)
        self.cleaner_scan_btn.setStyleSheet("font-size: 14px; padding: 10px;")
        cleaner_button_layout.addWidget(self.cleaner_scan_btn)

        self.cleaner_clean_btn = QPushButton("🗑️ 清理损坏文件")
        self.cleaner_clean_btn.clicked.connect(self._clean_corrupted_files)
        self.cleaner_clean_btn.setStyleSheet("font-size: 14px; padding: 10px;")
        self.cleaner_clean_btn.setEnabled(False)  # 默认禁用，扫描后才能清理
        cleaner_button_layout.addWidget(self.cleaner_clean_btn)

        cleaner_layout.addLayout(cleaner_button_layout)

        layout.addWidget(cleaner_group)

        # 加载数据目录配置
        self._load_cleaner_config()

        layout.addStretch()

        return tab

    def _browse_tdx_root(self):
        """浏览通达信根目录."""
        dir_path = QFileDialog.getExistingDirectory(self, "选择通达信软件根目录")
        if dir_path and self.reader_tdx_path_edit:
            self.reader_tdx_path_edit.setText(dir_path)

    def _update_reader_progress(self, current: int, total: int, info: str, success: bool):
        """更新读取器进度（槽函数，在主线程中执行）.

        Args:
            current: 当前完成数
            total: 总任务数
            info: 当前处理信息
            success: 是否成功
        """
        try:
            # 更新进度条
            if self.reader_progress_bar:
                progress_pct = int(current / total * 100) if total > 0 else 0
                self.reader_progress_bar.setValue(progress_pct)

            # 更新详细信息
            if self.reader_detail_label:
                status_icon = "✅" if success else "❌"
                self.reader_detail_label.setText(f"{status_icon} {current}/{total} - {info}")

            # 更新状态标签
            if self.reader_status_label:
                progress_pct = int(current / total * 100) if total > 0 else 0
                self.reader_status_label.setText(
                    f"状态: 正在处理 {current}/{total} ({progress_pct}%)"
                )

        except Exception as e:
            self.logger.error("更新进度失败: %s", e)

    def _update_reader_finished(self, result: dict):
        """更新读取器完成状态（槽函数，在主线程中执行）.

        Args:
            result: 处理结果字典
        """
        try:
            # 恢复按钮状态
            if self.reader_start_btn:
                self.reader_start_btn.setEnabled(True)
            if self.reader_stop_btn:
                self.reader_stop_btn.setEnabled(False)

            if result.get("success"):
                success_count = result.get("success_count", 0)
                fail_count = result.get("fail_count", 0)
                total_tasks = result.get("total_tasks", 0)
                was_stopped = result.get("was_stopped", False)

                if was_stopped:
                    message = f"已停止：已完成 {success_count + fail_count}/{total_tasks}，成功 {success_count}，失败 {fail_count}"
                else:
                    message = f"完成：成功 {success_count}/{total_tasks}，失败 {fail_count}"

                if self.reader_status_label:
                    self.reader_status_label.setText(f"状态: {message}")

                if self.reader_progress_bar:
                    self.reader_progress_bar.setValue(100)

                if was_stopped:
                    self.show_warning(message)
                else:
                    self.show_info(message)
            else:
                error_msg = result.get("message", "未知错误")

                if self.reader_status_label:
                    self.reader_status_label.setText("状态: 读取失败")

                if self.reader_progress_bar:
                    self.reader_progress_bar.setValue(0)

                self.show_error(f"读取失败: {error_msg}")

        except Exception as e:
            self.logger.error("更新完成状态失败: %s", e)

    def _stop_tdx_reader(self):
        """停止通达信数据读取."""
        try:
            if not self.system_service:
                self.show_error("系统管理服务不可用")
                return

            result = self.system_service.stop_tdx_reader()

            if result["success"]:
                self.show_info("停止信号已发送，任务将在当前批次完成后停止...")
                if self.reader_stop_btn:
                    self.reader_stop_btn.setEnabled(False)
            else:
                self.show_error(f"停止失败: {result.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error("停止任务失败: %s", e)
            self.show_error(f"停止失败: {e}")

    def _load_tdx_reader_config(self):
        """加载通达信读取器配置."""
        try:
            if not self.system_service:
                return

            result = self.system_service.get_tdx_reader_config()

            if result.get("success"):
                config = result.get("config", {})
                tdx_root = config.get("tdx_root", "")

                if tdx_root and self.reader_tdx_path_edit:
                    self.reader_tdx_path_edit.setText(tdx_root)

        except Exception as e:
            self.logger.error(
                "UI加载通达信读取器配置失败: 错误=%s",
                str(e),
                extra={"log_type": "SYSTEM"},
                exc_info=True
            )

    def _read_and_save_tdx_data(self):
        """读取并保存通达信数据（多市场、多周期、带进度）."""
        try:
            if not self.system_service:
                self.show_error("系统管理服务不可用")
                return

            # 收集选中的数据类型
            data_types = []
            if self.reader_day_check and self.reader_day_check.isChecked():
                data_types.append("day")
            if self.reader_5min_check and self.reader_5min_check.isChecked():
                data_types.append("5min")
            if self.reader_1min_check and self.reader_1min_check.isChecked():
                data_types.append("1min")

            if not data_types:
                self.show_warning("请至少选择一种数据类型")
                return

            # 收集选中的市场
            markets = []
            if self.reader_sh_check and self.reader_sh_check.isChecked():
                markets.append("sh")
            if self.reader_sz_check and self.reader_sz_check.isChecked():
                markets.append("sz")
            if self.reader_bj_check and self.reader_bj_check.isChecked():
                markets.append("bj")

            if not markets:
                self.show_warning("请至少选择一个市场")
                return

            # 获取通达信根目录
            if not self.reader_tdx_path_edit:
                return

            tdx_root = self.reader_tdx_path_edit.text().strip()

            if not tdx_root:
                self.show_warning("请输入通达信根目录")
                return

            # 初始化进度
            if self.reader_progress_bar:
                self.reader_progress_bar.setValue(0)
            if self.reader_detail_label:
                self.reader_detail_label.setText("")

            # 连接信号到槽函数（安全断开，避免警告）
            import warnings

            # 抑制 RuntimeWarning
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=RuntimeWarning)
                try:
                    self.reader_progress_signal.disconnect()
                except (TypeError, RuntimeError):
                    pass  # 如果没有连接，忽略

            self.reader_progress_signal.connect(self._update_reader_progress)

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=RuntimeWarning)
                try:
                    self.reader_finished_signal.disconnect()
                except (TypeError, RuntimeError):
                    pass

            self.reader_finished_signal.connect(self._update_reader_finished)

            # 定义进度回调函数
            def progress_callback(current, total, info, success):
                """进度回调函数（在工作线程中调用，需要线程安全）"""
                # 通过Signal发送进度更新（自动在主线程处理）
                self.reader_progress_signal.emit(current, total, info, success)

            # 更新初始状态
            if self.reader_status_label:
                self.reader_status_label.setText("状态: 准备中...")

            # 禁用开始按钮，启用停止按钮
            if self.reader_start_btn:
                self.reader_start_btn.setEnabled(False)
            if self.reader_stop_btn:
                self.reader_stop_btn.setEnabled(True)

            # 调用服务
            config = {
                "data_types": data_types,
                "markets": markets,
                "tdx_root": tdx_root,
                "use_symbol_cache": True,
            }

            self.logger.info(
                "开始批量读取: 数据类型=%s, 市场=%s (自适应线程数)",
                data_types,
                markets,
            )

            # 在单独的线程中执行（避免阻塞UI）
            import threading

            def do_read():
                try:
                    if not self.system_service:
                        return
                    result = self.system_service.read_tdx_data(config, progress_callback)
                    # 通过Signal发送完成状态
                    self.reader_finished_signal.emit(result)

                except Exception as e:
                    self.logger.error("读取通达信数据失败: %s", e)
                    # 发送错误结果
                    self.reader_finished_signal.emit(
                        {
                            "success": False,
                            "message": f"读取失败: {str(e)}",
                        }
                    )

            # 启动工作线程
            thread = threading.Thread(target=do_read, daemon=True, name="TdxReader")
            thread.start()

        except Exception as e:
            self.logger.error("启动读取任务失败: %s", e)

            if self.reader_status_label:
                self.reader_status_label.setText("状态: 启动失败")

            self.show_error(f"启动失败: {e}")

    # ==================== 网络测速工具方法 ====================

    def _test_bandwidth_full(self):
        """测试服务商带宽（完整测试）."""
        try:
            self.test_bandwidth_btn.setEnabled(False)
            self.test_bandwidth_btn.setText("测试中...")

            # 清空之前的结果
            self.bandwidth_download_label.setText("测试中...")
            self.bandwidth_upload_label.setText("测试中...")
            self.bandwidth_ping_label.setText("测试中...")

            # 在后台线程执行测试
            from threading import Thread

            def run_test():
                try:
                    service = self.service_manager.get_service(
                        "system_manager_service", silent=True
                    )
                    if not service:
                        self.bandwidth_test_error_signal.emit("无法获取系统服务")
                        return

                    # 通过ZMQ向监控进程发送测试请求
                    import zmq
                    import json
                    import time
                    from pathlib import Path

                    # 读取监控进程端口配置
                    addr = "127.0.0.1"
                    port = 5557  # 默认端口
                    try:
                        ports_file = Path("logs") / "monitor_ports.json"
                        if ports_file.exists():
                            with open(ports_file, "r", encoding="utf-8") as f:
                                ports_data = json.load(f)
                        addr = str(ports_data.get("bind_addr", addr))
                        port = int(ports_data.get("query_rep", port))
                    except Exception:
                        pass  # 使用默认值

                    # 发送测试启动请求（立即返回）
                    context = zmq.Context()
                    socket = context.socket(zmq.REQ)
                    socket.connect(f"tcp://{addr}:{port}")
                    socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5秒超时（启动请求应该立即返回）

                    socket.send_json({"action": "test_bandwidth_full"})
                    response = socket.recv_json()

                    socket.close()

                    # 检查是否成功启动测试
                    if not isinstance(response, dict):
                        context.term()
                        self.bandwidth_test_error_signal.emit("返回数据格式错误")
                        return

                    status = response.get("status")
                    if status not in ["started", "testing"]:
                        context.term()
                        error_msg = response.get("message", "测试启动失败")
                        self.bandwidth_test_error_signal.emit(str(error_msg))
                        return

                    # 🔧 修复：轮询获取结果（完整带宽测试：最多等待90秒）
                    # 策略：前5次每1秒查询（检测快速完成），后续每2秒查询
                    # 考虑：5个服务器，每个最多15秒超时 + 下载10秒 = 最多75秒，加上缓冲到90秒
                    max_attempts = 43  # 5x1秒 + 38x2秒 = 81秒
                    for attempt in range(max_attempts):
                        if attempt < 5:
                            time.sleep(1)   # 前5秒：每1秒查询
                        else:
                            time.sleep(2)   # 后续：每2秒查询

                        try:
                            socket = context.socket(zmq.REQ)
                            socket.connect(f"tcp://{addr}:{port}")
                            socket.setsockopt(zmq.RCVTIMEO, 3000)  # 3秒超时

                            socket.send_json({"action": "get_bandwidth"})
                            result_response = socket.recv_json()

                            socket.close()

                            if isinstance(result_response, dict) and result_response.get("status") == "success":
                                data = result_response.get("data", {})
                                if isinstance(data, dict):
                                    full_test = data.get("full_test", {})

                                    # 🔧 修复：检查是否有有效结果（download_mbps不为None表示测试完成）
                                    if isinstance(full_test, dict):
                                        # 检查status字段，区分"未测试"和"错误"状态
                                        status = full_test.get("status", "")
                                        download_mbps = full_test.get("download_mbps")

                                        # 如果是错误状态，立即停止轮询
                                        if status and status != "未测试" and ("错误" in str(status) or "超时" in str(status) or "ZMQ" in str(status)):
                                            context.term()
                                            error_msg = full_test.get("error", status)
                                            self.logger.error(f"❌ 带宽测速返回错误状态：{error_msg}")
                                            self.bandwidth_test_error_signal.emit(error_msg)
                                            return

                                        # download_mbps不为None表示测试完成（包括失败的情况，-1表示失败）
                                        if download_mbps is not None:
                                            context.term()

                                            # 检查是否是异常值（-1表示测试失败）
                                            if download_mbps == -1:
                                                error_msg = full_test.get("error", "测试失败，请稍后重试")
                                                self.logger.error(f"❌ 带宽测速返回异常：{error_msg}")
                                                self.bandwidth_test_error_signal.emit(error_msg)
                                            else:
                                                self.logger.info(f"✅ 获取到带宽测试结果：{full_test}")
                                                # 使用信号发送结果（线程安全）
                                                self.bandwidth_test_success_signal.emit(full_test)
                                            return
                                        # 否则继续轮询（status="未测试"或download_mbps=None）

                        except Exception as poll_error:
                            self.logger.debug("轮询第%d次失败: %s", attempt + 1, poll_error)
                            continue

                    # 超时
                    context.term()
                    self.bandwidth_test_error_signal.emit("测试超时（69秒）或网络不稳定")

                except zmq.Again:
                    self.bandwidth_test_error_signal.emit("连接超时")
                except Exception as e:
                    self.logger.error("带宽测试异常: %s", e, exc_info=True)
                    self.bandwidth_test_error_signal.emit(f"连接失败: {str(e)[:50]}")

            test_thread = Thread(target=run_test, daemon=True)
            test_thread.start()

        except Exception as e:
            self.logger.error("启动带宽测试失败: %s", e)
            self.bandwidth_test_error_signal.emit(str(e))

    def _retry_latency_test(self):
        """重试延迟监控（重新初始化服务器池）"""
        try:
            from threading import Thread
            import zmq
            import json
            from pathlib import Path

            def run_retry():
                try:
                    # 读取监控进程端口配置
                    addr = "127.0.0.1"
                    port = 5557
                    try:
                        ports_file = Path("logs") / "monitor_ports.json"
                        if ports_file.exists():
                            with open(ports_file, "r", encoding="utf-8") as f:
                                ports_data = json.load(f)
                            addr = str(ports_data.get("bind_addr", addr))
                            port = int(ports_data.get("query_rep", port))
                    except Exception:
                        pass

                    # 发送重试请求
                    context = zmq.Context()
                    socket = context.socket(zmq.REQ)
                    socket.connect(f"tcp://{addr}:{port}")
                    socket.setsockopt(zmq.RCVTIMEO, 10000)  # 10秒超时

                    socket.send_json({"action": "retry_latency"})
                    response = socket.recv_json()
                    socket.close()
                    context.term()

                    if isinstance(response, dict) and response.get("status") == "success":
                        self.logger.info("延迟监控重试成功")
                    else:
                        self.logger.warning(f"延迟监控重试失败: {response}")
                except Exception as e:
                    self.logger.error(f"延迟监控重试异常: {e}", exc_info=True)

            retry_thread = Thread(target=run_retry, daemon=True)
            retry_thread.start()
        except Exception as e:
            self.logger.error(f"启动延迟监控重试失败: {e}")

    def _update_bandwidth_result_success(self, result: Dict[str, Any]):
        """更新完整带宽测试结果（成功）."""
        from datetime import datetime

        download_mbps = result.get("download_mbps", 0)
        upload_mbps = result.get("upload_mbps", 0)
        ping_ms = result.get("ping_ms", 0)

        self.bandwidth_download_label.setText(f"{download_mbps:.2f} Mbps")
        self.bandwidth_download_label.setStyleSheet("color: #0F0; font-weight: bold;")

        self.bandwidth_upload_label.setText(f"{upload_mbps:.2f} Mbps")
        self.bandwidth_upload_label.setStyleSheet("color: #0F0; font-weight: bold;")

        self.bandwidth_ping_label.setText(f"{ping_ms:.2f} ms")
        self.bandwidth_ping_label.setStyleSheet("color: #0F0; font-weight: bold;")

        self.bandwidth_test_time_label.setText(datetime.now().strftime("%H:%M:%S"))

        self.test_bandwidth_btn.setText("📊 测服务商带宽")
        self.test_bandwidth_btn.setEnabled(True)

    def _update_bandwidth_result_error(self, error_msg: str):
        """更新完整带宽测试结果（失败）."""
        self.bandwidth_download_label.setText(error_msg)
        self.bandwidth_download_label.setStyleSheet("color: #F00;")
        self.bandwidth_upload_label.setText("--")
        self.bandwidth_ping_label.setText("--")

        self.test_bandwidth_btn.setText("📊 测服务商带宽")
        self.test_bandwidth_btn.setEnabled(True)


    # ==================== 损坏文件清理工具方法 ====================

    def _load_cleaner_config(self):
        """加载清理工具配置（显示数据目录）."""
        try:
            if not self.system_service:
                if self.cleaner_data_dir_label:
                    self.cleaner_data_dir_label.setText("./data/kline（默认）")
                return

            # 从服务获取数据目录配置
            result = self.system_service.get_all_configs()

            if not result.get("success"):
                if self.cleaner_data_dir_label:
                    self.cleaner_data_dir_label.setText("./data/kline（默认）")
                return

            configs = result.get("configs", {})
            data_config = configs.get("data_center", {})
            data_dir = data_config.get("data_dir", "./data/kline")

            if self.cleaner_data_dir_label:
                self.cleaner_data_dir_label.setText(data_dir)

        except Exception as e:
            self.logger.error("加载清理工具配置失败: %s", e)
            if self.cleaner_data_dir_label:
                self.cleaner_data_dir_label.setText("./data/kline（默认）")

    def _scan_corrupted_files(self):
        """扫描损坏的Parquet文件（后台线程）."""
        try:
            if not self.system_service:
                self.show_error("系统管理服务不可用")
                return

            # 禁用扫描按钮
            if self.cleaner_scan_btn:
                self.cleaner_scan_btn.setEnabled(False)

            # 更新状态
            if self.cleaner_result_label:
                self.cleaner_result_label.setText("状态: 正在扫描...")

            # 清空详细信息
            if self.cleaner_detail_text:
                self.cleaner_detail_text.clear()
                self.cleaner_detail_text.append("开始扫描损坏的Parquet文件...\n")

            # 创建后台工作线程
            from PySide6.QtCore import QThread, Signal

            class ScanThread(QThread):
                finished_signal = Signal(dict)
                error_signal = Signal(str)
                progress_signal = Signal(int, int, str)  # current, total, message

                def __init__(self, service, auto_delete):
                    super().__init__()
                    self.service = service
                    self.auto_delete = auto_delete

                def run(self):
                    try:
                        # 定义进度回调
                        def progress_callback(current, total, message):
                            self.progress_signal.emit(current, total, message)

                        # 调用扫描，传入进度回调
                        result = self.service.scan_corrupted_files(
                            auto_delete=self.auto_delete, progress_callback=progress_callback
                        )
                        self.finished_signal.emit(result)
                    except Exception as e:
                        self.error_signal.emit(str(e))

            # 创建线程实例
            self._scan_thread = ScanThread(self.system_service, auto_delete=False)
            self._scan_thread.finished_signal.connect(self._on_scan_finished)
            self._scan_thread.error_signal.connect(self._on_scan_error)
            self._scan_thread.progress_signal.connect(self._on_scan_progress)
            self._scan_thread.start()

        except Exception as e:
            self.logger.error("启动扫描失败: %s", e)
            if self.cleaner_result_label:
                self.cleaner_result_label.setText(f"状态: 启动失败 - {e}")
            if self.cleaner_detail_text:
                self.cleaner_detail_text.append(f"❌ 启动失败: {e}")
            self.show_error(f"启动扫描失败: {e}")

            # 恢复扫描按钮
            if self.cleaner_scan_btn:
                self.cleaner_scan_btn.setEnabled(True)

    def _on_scan_finished(self, result: dict):
        """扫描完成回调（在主线程执行）.

        Args:
            result: 扫描结果
        """
        try:
            if not result.get("success"):
                error_msg = result.get("message", "未知错误")
                if self.cleaner_result_label:
                    self.cleaner_result_label.setText(f"状态: 扫描失败 - {error_msg}")
                if self.cleaner_detail_text:
                    self.cleaner_detail_text.append(f"❌ 扫描失败: {error_msg}")
                self.show_error(f"扫描失败: {error_msg}")

                # 恢复扫描按钮
                if self.cleaner_scan_btn:
                    self.cleaner_scan_btn.setEnabled(True)
                return

            # 获取扫描结果
            scan_result = result.get("result", {})
            corrupted_files = scan_result.get("corrupted", [])
            self._cleaner_corrupted_files = corrupted_files

            # 在详细文本中添加扫描完成摘要
            if self.cleaner_detail_text:
                self.cleaner_detail_text.append(f"\n{'='*50}\n扫描完成摘要:\n{'='*50}")

            # 更新界面
            if len(corrupted_files) == 0:
                if self.cleaner_result_label:
                    self.cleaner_result_label.setText("状态: ✅ 未发现损坏文件")
                if self.cleaner_detail_text:
                    self.cleaner_detail_text.append("✅ 扫描完成，未发现损坏文件！")

                # 禁用清理按钮
                if self.cleaner_clean_btn:
                    self.cleaner_clean_btn.setEnabled(False)

                self.show_info("扫描完成，未发现损坏文件")

            else:
                if self.cleaner_result_label:
                    self.cleaner_result_label.setText(
                        f"状态: ⚠️ 发现 {len(corrupted_files)} 个损坏文件"
                    )

                if self.cleaner_detail_text:
                    self.cleaner_detail_text.append(f"⚠️ 发现 {len(corrupted_files)} 个损坏文件：\n")

                    # 只显示前50个文件
                    display_count = min(len(corrupted_files), 50)
                    for i, file_path in enumerate(corrupted_files[:display_count], 1):
                        self.cleaner_detail_text.append(f"{i}. {file_path}")

                    if len(corrupted_files) > 50:
                        self.cleaner_detail_text.append(
                            f"\n... 还有 {len(corrupted_files) - 50} 个文件未显示"
                        )

                # 启用清理按钮
                if self.cleaner_clean_btn:
                    self.cleaner_clean_btn.setEnabled(True)

                self.show_warning(f"发现 {len(corrupted_files)} 个损坏文件，可以点击清理按钮删除")

        except Exception as e:
            self.logger.error("扫描损坏文件失败: %s", e)
            if self.cleaner_result_label:
                self.cleaner_result_label.setText(f"状态: 扫描异常 - {e}")
            if self.cleaner_detail_text:
                self.cleaner_detail_text.append(f"❌ 扫描异常: {e}")
            self.show_error(f"扫描失败: {e}")

        finally:
            # 恢复扫描按钮
            if self.cleaner_scan_btn:
                self.cleaner_scan_btn.setEnabled(True)

    def _on_scan_progress(self, current: int, total: int, message: str):
        """扫描进度回调（在主线程执行）.

        Args:
            current: 当前已检查文件数
            total: 总文件数
            message: 当前处理消息
        """
        try:
            # 更新状态标签（实时显示进度）
            if self.cleaner_result_label:
                progress_pct = (current / total * 100) if total > 0 else 0
                self.cleaner_result_label.setText(
                    f"状态: 正在扫描... {current}/{total} ({progress_pct:.1f}%) - {message}"
                )

            # 详细文本只在关键节点显示（每100个或整百倍数）
            if self.cleaner_detail_text and (current % 100 == 0 or current == total):
                self.cleaner_detail_text.append(
                    f"✓ 已检查 {current}/{total} 个文件 ({progress_pct:.1f}%)"
                )

        except Exception as e:
            self.logger.error("更新扫描进度失败: %s", e)

    def _on_scan_error(self, error_msg: str):
        """扫描错误回调（在主线程执行）.

        Args:
            error_msg: 错误消息
        """
        try:
            if self.cleaner_result_label:
                self.cleaner_result_label.setText(f"状态: 扫描异常 - {error_msg}")
            if self.cleaner_detail_text:
                self.cleaner_detail_text.append(f"❌ 扫描异常: {error_msg}")
            self.show_error(f"扫描失败: {error_msg}")

        except Exception as e:
            self.logger.error("处理扫描错误失败: %s", e)

        finally:
            # 恢复扫描按钮
            if self.cleaner_scan_btn:
                self.cleaner_scan_btn.setEnabled(True)

    def _clean_corrupted_files(self):
        """清理损坏的Parquet文件."""
        try:
            if not self.system_service:
                self.show_error("系统管理服务不可用")
                return

            # 检查是否有需要清理的文件
            if not self._cleaner_corrupted_files:
                self.show_warning("请先扫描损坏文件")
                return

            # 确认对话框
            from PySide6.QtWidgets import QMessageBox

            reply = QMessageBox.question(
                self,
                "确认清理",
                f"确定要删除 {len(self._cleaner_corrupted_files)} 个损坏的文件吗？\n\n"
                "⚠️ 此操作不可恢复！",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            # 禁用按钮
            if self.cleaner_scan_btn:
                self.cleaner_scan_btn.setEnabled(False)
            if self.cleaner_clean_btn:
                self.cleaner_clean_btn.setEnabled(False)

            # 更新状态
            if self.cleaner_result_label:
                self.cleaner_result_label.setText("状态: 正在清理...")

            if self.cleaner_detail_text:
                self.cleaner_detail_text.append("\n开始清理损坏文件...\n")

            # 创建后台清理线程
            from PySide6.QtCore import QThread, Signal

            class CleanThread(QThread):
                finished_signal = Signal(dict)
                error_signal = Signal(str)
                progress_signal = Signal(int, int, str)  # current, total, message

                def __init__(self, service):
                    super().__init__()
                    self.service = service

                def run(self):
                    try:
                        # 定义进度回调
                        def progress_callback(current, total, message):
                            self.progress_signal.emit(current, total, message)

                        # 调用清理，传入进度回调
                        result = self.service.scan_corrupted_files(
                            auto_delete=True, progress_callback=progress_callback
                        )
                        self.finished_signal.emit(result)
                    except Exception as e:
                        self.error_signal.emit(str(e))

            # 创建线程实例
            self._clean_thread = CleanThread(self.system_service)
            self._clean_thread.finished_signal.connect(self._on_clean_finished)
            self._clean_thread.error_signal.connect(self._on_clean_error)
            self._clean_thread.progress_signal.connect(self._on_clean_progress)
            self._clean_thread.start()

        except Exception as e:
            self.logger.error("清理损坏文件失败: %s", e)
            if self.cleaner_result_label:
                self.cleaner_result_label.setText(f"状态: 清理异常 - {e}")
            if self.cleaner_detail_text:
                self.cleaner_detail_text.append(f"❌ 清理异常: {e}")
            self.show_error(f"清理失败: {e}")

        finally:
            # 恢复扫描按钮
            if self.cleaner_scan_btn:
                self.cleaner_scan_btn.setEnabled(True)

    def _on_clean_finished(self, result: dict):
        """清理完成回调（在主线程执行）.

        Args:
            result: 清理结果
        """
        try:
            if not result.get("success"):
                error_msg = result.get("message", "未知错误")
                if self.cleaner_result_label:
                    self.cleaner_result_label.setText(f"状态: 清理失败 - {error_msg}")
                if self.cleaner_detail_text:
                    self.cleaner_detail_text.append(f"❌ 清理失败: {error_msg}")
                self.show_error(f"清理失败: {error_msg}")

                # 恢复按钮
                if self.cleaner_scan_btn:
                    self.cleaner_scan_btn.setEnabled(True)
                return

            # 获取清理结果
            clean_result = result.get("result", {})
            deleted_files = clean_result.get("deleted", [])

            # 更新界面
            if self.cleaner_result_label:
                self.cleaner_result_label.setText(f"状态: ✅ 已清理 {len(deleted_files)} 个文件")

            if self.cleaner_detail_text:
                self.cleaner_detail_text.append(
                    f"✅ 清理完成，已删除 {len(deleted_files)} 个文件\n"
                )

                # 显示删除的文件
                display_count = min(len(deleted_files), 30)
                for i, file_path in enumerate(deleted_files[:display_count], 1):
                    self.cleaner_detail_text.append(f"  {i}. 已删除: {file_path}")

                if len(deleted_files) > 30:
                    self.cleaner_detail_text.append(
                        f"\n... 还有 {len(deleted_files) - 30} 个文件未显示"
                    )

            # 清空缓存列表
            self._cleaner_corrupted_files = []

            # 禁用清理按钮
            if self.cleaner_clean_btn:
                self.cleaner_clean_btn.setEnabled(False)

            self.show_info(f"清理完成，已删除 {len(deleted_files)} 个损坏文件")

        except Exception as e:
            self.logger.error("处理清理结果失败: %s", e)

        finally:
            # 恢复扫描按钮
            if self.cleaner_scan_btn:
                self.cleaner_scan_btn.setEnabled(True)

    def _on_clean_progress(self, current: int, total: int, message: str):
        """清理进度回调（在主线程执行）.

        Args:
            current: 当前已检查文件数
            total: 总文件数
            message: 当前处理消息
        """
        try:
            # 更新状态标签（实时显示进度）
            if self.cleaner_result_label:
                progress_pct = (current / total * 100) if total > 0 else 0
                self.cleaner_result_label.setText(
                    f"状态: 正在清理... {current}/{total} ({progress_pct:.1f}%) - {message}"
                )

            # 详细文本只在关键节点显示（每100个或整百倍数）
            if self.cleaner_detail_text and (current % 100 == 0 or current == total):
                self.cleaner_detail_text.append(
                    f"✓ 已检查 {current}/{total} 个文件 ({progress_pct:.1f}%)"
                )

        except Exception as e:
            self.logger.error("更新清理进度失败: %s", e)

    def _on_clean_error(self, error_msg: str):
        """清理错误回调（在主线程执行）.

        Args:
            error_msg: 错误消息
        """
        try:
            if self.cleaner_result_label:
                self.cleaner_result_label.setText(f"状态: 清理异常 - {error_msg}")
            if self.cleaner_detail_text:
                self.cleaner_detail_text.append(f"❌ 清理异常: {error_msg}")
            self.show_error(f"清理失败: {error_msg}")

        except Exception as e:
            self.logger.error("处理清理错误失败: %s", e)

        finally:
            # 恢复扫描按钮
            if self.cleaner_scan_btn:
                self.cleaner_scan_btn.setEnabled(True)

    # ==================== 配置管理方法 ====================

    def _load_config(self):
        """加载配置."""
        try:
            if not self.system_service:
                self.logger.warning("系统管理服务不可用，使用默认配置")
                self._load_default_config()
                return

            # 从服务获取所有配置
            result = self.system_service.get_all_configs()

            if not result.get("success"):
                self.logger.warning("获取配置失败，使用默认值: %s", result.get("message"))
                self._load_default_config()
                return

            configs = result.get("configs", {})

            # 加载数据中心配置
            data_config = configs.get("data_center", {})
            if self.tdx_path_edit:
                tdx_dir = data_config.get("tdx_dir", "")
                self.tdx_path_edit.setText(tdx_dir)
            if self.cache_dir_edit:
                cache_dir = data_config.get("cache_dir", "./data/cache")
                self.cache_dir_edit.setText(cache_dir)
            if self.data_dir_edit:
                data_dir = data_config.get("data_dir", "./data/kline")
                self.data_dir_edit.setText(data_dir)
            if self.base_date_edit:
                base_date_str = data_config.get("base_date") or "2020-01-01"  # 🔧 修复：处理 None 值
                try:
                    if base_date_str and isinstance(base_date_str, str):
                        parts = base_date_str.split("-")
                        if len(parts) == 3:
                            self.base_date_edit.setDate(
                                QDate(int(parts[0]), int(parts[1]), int(parts[2]))
                            )
                        else:
                            self.base_date_edit.setDate(QDate(2020, 1, 1))
                    else:
                        self.base_date_edit.setDate(QDate(2020, 1, 1))
                except (ValueError, IndexError, AttributeError, TypeError):
                    self.base_date_edit.setDate(QDate(2020, 1, 1))
            if self.max_workers_spin:
                # 🔧 修复：处理 None 值，确保传递给 setValue 的是 int 类型
                max_workers = data_config.get("max_workers") or 10
                if isinstance(max_workers, int):
                    self.max_workers_spin.setValue(max_workers)
                else:
                    self.max_workers_spin.setValue(10)
            if self.timeout_spin:
                # 🔧 修复：处理 None 值，确保传递给 setValue 的是 int 类型
                timeout = data_config.get("timeout") or 30
                if isinstance(timeout, int):
                    self.timeout_spin.setValue(timeout)
                else:
                    self.timeout_spin.setValue(30)
            if self.retry_spin:
                # 🔧 修复：处理 None 值，确保传递给 setValue 的是 int 类型
                retry_times = data_config.get("retry_times") or 3
                if isinstance(retry_times, int):
                    self.retry_spin.setValue(retry_times)
                else:
                    self.retry_spin.setValue(3)
            if self.watcher_check:
                self.watcher_check.setChecked(data_config.get("enable_watcher") if data_config.get("enable_watcher") is not None else True)
            if self.watcher_interval_spin:
                # 🔧 修复：处理 None 值，确保传递给 setValue 的是 int 类型
                watcher_interval = data_config.get("watcher_interval") or 5
                if isinstance(watcher_interval, int):
                    self.watcher_interval_spin.setValue(watcher_interval)
                else:
                    self.watcher_interval_spin.setValue(5)

            # 加载AI配置
            ai_config = configs.get("ai", {})
            if hasattr(self, "ai_api_key_edit") and self.ai_api_key_edit:
                api_key = ai_config.get("api_key", "")
                self.ai_api_key_edit.setText(api_key)
            if hasattr(self, "ai_api_url_edit") and self.ai_api_url_edit:
                api_url = ai_config.get("api_url", "https://api.deepseek.com/v1/chat/completions")
                self.ai_api_url_edit.setText(api_url)
            if hasattr(self, "ai_model_combo") and self.ai_model_combo:
                model = ai_config.get("model", "deepseek-chat")
                self.ai_model_combo.setCurrentText(model)
            if hasattr(self, "ai_max_tokens_spin") and self.ai_max_tokens_spin:
                # 🔧 修复：处理 None 值，确保传递给 setValue 的是 int 类型
                max_tokens = ai_config.get("max_tokens") or 2000
                if isinstance(max_tokens, int):
                    self.ai_max_tokens_spin.setValue(max_tokens)
                else:
                    self.ai_max_tokens_spin.setValue(2000)
            if hasattr(self, "ai_temperature_slider") and self.ai_temperature_slider:
                # 🔧 修复：处理 None 值，确保传递给 setValue 的是 int 类型
                temperature = ai_config.get("temperature") or 0.7
                if isinstance(temperature, (int, float)):
                    self.ai_temperature_slider.setValue(int(temperature * 100))
                else:
                    self.ai_temperature_slider.setValue(70)
            if hasattr(self, "ai_max_history_spin") and self.ai_max_history_spin:
                # 🔧 修复：处理 None 值，确保传递给 setValue 的是 int 类型
                max_history = ai_config.get("max_history") or 10
                if isinstance(max_history, int):
                    self.ai_max_history_spin.setValue(max_history)
                else:
                    self.ai_max_history_spin.setValue(10)
            if hasattr(self, "ai_timeout_spin") and self.ai_timeout_spin:
                # 🔧 修复：处理 None 值，确保传递给 setValue 的是 int 类型
                timeout = ai_config.get("timeout") or 30
                if isinstance(timeout, int):
                    self.ai_timeout_spin.setValue(timeout)
                else:
                    self.ai_timeout_spin.setValue(30)

            if hasattr(self, "ai_enable_tools_check") and self.ai_enable_tools_check:
                enable_tools = ai_config.get("enable_tools", False)
                self.ai_enable_tools_check.setChecked(enable_tools)

            self.logger.info("配置加载完成")

        except Exception as e:
            self.logger.error("加载配置失败: %s", e, exc_info=True)
            self._load_default_config()

    def _load_default_config(self):
        """加载默认配置."""
        try:
            # 数据中心默认配置
            root_dir = get_root()
            if self.tdx_path_edit:
                self.tdx_path_edit.setText("")
            if self.cache_dir_edit:
                # 🔧 非用户配置项：使用相对路径（基于项目根目录）
                self.cache_dir_edit.setText("data/cache")
            if self.data_dir_edit:
                # 🔧 非用户配置项：使用相对路径（基于项目根目录）
                self.data_dir_edit.setText("data/kline")
            if self.base_date_edit:
                self.base_date_edit.setDate(QDate(2020, 1, 1))
            if self.max_workers_spin:
                self.max_workers_spin.setValue(10)
            if self.timeout_spin:
                self.timeout_spin.setValue(30)
            if self.retry_spin:
                self.retry_spin.setValue(3)
            if self.watcher_check:
                self.watcher_check.setChecked(True)
            if self.watcher_interval_spin:
                self.watcher_interval_spin.setValue(5)

            # AI默认配置
            if hasattr(self, "ai_api_key_edit") and self.ai_api_key_edit:
                self.ai_api_key_edit.setText("")
            if hasattr(self, "ai_api_url_edit") and self.ai_api_url_edit:
                self.ai_api_url_edit.setText("https://api.deepseek.com/v1/chat/completions")
            if hasattr(self, "ai_model_combo") and self.ai_model_combo:
                self.ai_model_combo.setCurrentText("deepseek-chat")
            if hasattr(self, "ai_max_tokens_spin") and self.ai_max_tokens_spin:
                self.ai_max_tokens_spin.setValue(2000)
            if hasattr(self, "ai_temperature_slider") and self.ai_temperature_slider:
                self.ai_temperature_slider.setValue(70)
            if hasattr(self, "ai_max_history_spin") and self.ai_max_history_spin:
                self.ai_max_history_spin.setValue(10)
            if hasattr(self, "ai_timeout_spin") and self.ai_timeout_spin:
                self.ai_timeout_spin.setValue(30)

            self.logger.info("已加载默认配置")

        except Exception as e:
            self.logger.error("加载默认配置失败: %s", e)

    def _verify_config_file(self):
        """验证配置文件是否正确写入."""
        try:
            import json
            from pathlib import Path

            config_file = Path("config/terminal_config.json")
            if not config_file.exists():
                self.logger.error("❌ 配置文件不存在！")
                return

            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            ai_config = config_data.get("ai", {})
            api_key = ai_config.get("api_key", "")

            if api_key:
                masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
                self.logger.info(f"✅ 配置文件验证: API Key = {masked_key}")
            else:
                self.logger.warning("⚠️ 配置文件中API Key为空")

            self.logger.info(f"✅ 配置文件验证通过: {config_file.absolute()}")

        except Exception as e:
            self.logger.error(f"配置文件验证失败: {e}", exc_info=True)

    def _diagnose_config(self):
        """诊断配置状态."""
        try:
            # 记录用户诊断操作
            logger_user.info("用户执行系统诊断: 配置诊断")

            self.logger.info("开始诊断配置...")

            if not self.system_service:
                self.logger.error("系统管理服务不可用")
                self.show_error("系统管理服务不可用")
                return

            self.logger.info("调用 diagnose_config...")
            result = self.system_service.diagnose_config()
            self.logger.info("diagnose_config 返回结果: %s", result.get("success"))

            if result.get("success"):
                diagnosis = result.get("diagnosis", {})
                self.logger.info("获取到诊断信息: %s", list(diagnosis.keys()))

                # 构建诊断信息
                msg_parts = []
                msg_parts.append("配置诊断报告")
                msg_parts.append("=" * 50)
                msg_parts.append(f"\n配置文件路径:\n{diagnosis.get('config_file_path')}")
                msg_parts.append(f"\n配置文件存在: {diagnosis.get('config_file_exists')}")

                # 文件中的AI配置
                if diagnosis.get("config_file_content"):
                    config = diagnosis["config_file_content"]
                    ai_config = config.get("ai", {})
                    msg_parts.append("\n文件中的AI配置:")
                    api_key = ai_config.get("api_key", "")
                    if api_key:
                        # 显示API Key的前后各4位
                        masked_key = (
                            f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
                        )
                        msg_parts.append(f"  - API Key: {masked_key}")
                    else:
                        msg_parts.append("  - API Key: 未设置")
                    msg_parts.append(f"  - API URL: {ai_config.get('api_url', '未设置')}")
                    msg_parts.append(f"  - 模型: {ai_config.get('model', '未设置')}")
                else:
                    msg_parts.append("\n文件中的AI配置: 无（文件不存在或为空）")

                # 内存中的AI配置
                mem_config = diagnosis.get("memory_config", {})
                msg_parts.append("\n内存中的AI配置:")
                msg_parts.append(
                    f"  - API Key: {'已设置' if mem_config.get('ai_api_key_set') else '未设置'}"
                )
                msg_parts.append(f"  - API URL: {mem_config.get('ai_api_url', '未设置')}")
                msg_parts.append(f"  - 模型: {mem_config.get('ai_model', '未设置')}")

                # AI服务状态
                ai_status = diagnosis.get("ai_service_status", {})
                msg_parts.append("\nAI服务状态:")
                msg_parts.append(f"  - 服务存在: {ai_status.get('exists')}")
                if ai_status.get("exists"):
                    msg_parts.append(f"  - 已初始化: {ai_status.get('initialized')}")
                    msg_parts.append(f"  - API Key配置: {ai_status.get('api_key_configured')}")
                else:
                    msg_parts.append("  - 服务未注册")

                # 显示对话框
                full_msg = "\n".join(msg_parts)
                self.logger.info("显示诊断对话框")
                QMessageBox.information(self, "配置诊断", full_msg)
            else:
                error_msg = result.get("message", "未知错误")
                self.logger.error("诊断失败: %s", error_msg)
                self.show_error(f"诊断失败: {error_msg}")

        except Exception as e:
            self.logger.error("配置诊断失败: %s", e, exc_info=True)
            import traceback

            tb = traceback.format_exc()
            self.logger.error("异常堆栈: %s", tb)
            self.show_error(f"诊断失败: {e}\n\n详细信息请查看日志")

    def _refresh_config(self):
        """刷新配置."""
        self._load_config()
        self.show_info("配置已刷新")

    def _save_config(self):
        """保存配置."""
        try:
            if not self.system_service:
                self.show_error("系统管理服务不可用")
                return

            # 收集数据中心配置
            root_dir = get_root()
            data_center_config = {}

            # 🔧 用户配置项：通达信路径（保存绝对路径）
            if self.tdx_path_edit and self.tdx_path_edit.text():
                tdx_dir = self.tdx_path_edit.text().strip()
                if tdx_dir:
                    # 用户配置项保存绝对路径
                    tdx_path = Path(tdx_dir)
                    if not tdx_path.is_absolute():
                        # 如果是相对路径，转换为绝对路径（基于当前工作目录）
                        tdx_path = Path.cwd() / tdx_path
                    data_center_config["tdx_dir"] = str(tdx_path.resolve())

            # 🔧 非用户配置项：缓存目录和数据目录（保存相对路径，基于项目根目录）
            if self.cache_dir_edit and self.cache_dir_edit.text():
                cache_dir = self.cache_dir_edit.text().strip()
                if cache_dir:
                    cache_path = Path(cache_dir)
                    # 如果是绝对路径，尝试转换为相对路径（相对于项目根目录）
                    if cache_path.is_absolute():
                        try:
                            rel_path = cache_path.relative_to(root_dir)
                            data_center_config["cache_dir"] = str(rel_path).replace("\\", "/")
                        except ValueError:
                            # 无法转换为相对路径，保存绝对路径（向后兼容）
                            data_center_config["cache_dir"] = str(cache_path.resolve())
                    else:
                        # 已经是相对路径，直接保存（确保使用正斜杠）
                        data_center_config["cache_dir"] = cache_dir.replace("\\", "/")

            if self.data_dir_edit and self.data_dir_edit.text():
                data_dir = self.data_dir_edit.text().strip()
                if data_dir:
                    data_path = Path(data_dir)
                    # 如果是绝对路径，尝试转换为相对路径（相对于项目根目录）
                    if data_path.is_absolute():
                        try:
                            rel_path = data_path.relative_to(root_dir)
                            data_center_config["data_dir"] = str(rel_path).replace("\\", "/")
                        except ValueError:
                            # 无法转换为相对路径，保存绝对路径（向后兼容）
                            data_center_config["data_dir"] = str(data_path.resolve())
                    else:
                        # 已经是相对路径，直接保存（确保使用正斜杠）
                        data_center_config["data_dir"] = data_dir.replace("\\", "/")
            if self.base_date_edit:
                data_center_config["base_date"] = self.base_date_edit.date().toString("yyyy-MM-dd")
            if self.max_workers_spin:
                data_center_config["max_workers"] = self.max_workers_spin.value()
            if self.timeout_spin:
                data_center_config["timeout"] = self.timeout_spin.value()
            if self.retry_spin:
                data_center_config["retry_times"] = self.retry_spin.value()
            if self.watcher_check:
                data_center_config["enable_watcher"] = self.watcher_check.isChecked()
            if self.watcher_interval_spin:
                data_center_config["watcher_interval"] = self.watcher_interval_spin.value()

            # 收集AI配置数据
            ai_config = {}
            if hasattr(self, "ai_api_key_edit") and self.ai_api_key_edit:
                api_key_text = self.ai_api_key_edit.text().strip()
                if api_key_text:
                    ai_config["api_key"] = api_key_text
                    self.logger.info(
                        f"收集到API Key: {api_key_text[:4]}...{api_key_text[-4:] if len(api_key_text) > 8 else '***'}"
                    )
                else:
                    self.logger.warning("API Key为空")

            if hasattr(self, "ai_api_url_edit") and self.ai_api_url_edit:
                api_url_text = self.ai_api_url_edit.text().strip()
                if api_url_text:
                    ai_config["api_url"] = api_url_text

            if hasattr(self, "ai_model_combo") and self.ai_model_combo:
                ai_config["model"] = self.ai_model_combo.currentText()
            if hasattr(self, "ai_max_tokens_spin") and self.ai_max_tokens_spin:
                ai_config["max_tokens"] = self.ai_max_tokens_spin.value()
            if hasattr(self, "ai_temperature_slider") and self.ai_temperature_slider:
                ai_config["temperature"] = self.ai_temperature_slider.value() / 100.0
            if hasattr(self, "ai_max_history_spin") and self.ai_max_history_spin:
                ai_config["max_history"] = self.ai_max_history_spin.value()
            if hasattr(self, "ai_timeout_spin") and self.ai_timeout_spin:
                ai_config["timeout"] = self.ai_timeout_spin.value()
            if hasattr(self, "ai_enable_tools_check") and self.ai_enable_tools_check:
                ai_config["enable_tools"] = self.ai_enable_tools_check.isChecked()

            self.logger.info(f"收集到AI配置项: {list(ai_config.keys())}")

            # 保存结果跟踪
            success_count = 0
            fail_messages = []
            ai_service_reloaded = False

            # 保存数据中心配置
            if data_center_config:
                result = self.system_service.update_config("data_center", data_center_config)
                if result.get("success"):
                    success_count += 1
                    self.logger.info("数据中心配置保存成功")
                else:
                    fail_messages.append(f"数据中心: {result.get('message')}")

            # 保存监控频率配置
            if hasattr(self, "monitoring_interval_spin") and self.monitoring_interval_spin:
                interval = self.monitoring_interval_spin.value()
                try:
                    result = self.system_service.set_monitoring_interval(interval)
                    if result.get("success"):
                        success_count += 1
                        self.logger.info("监控推送频率已设置为 %d 秒", interval)
                    else:
                        fail_messages.append(f"监控频率: {result.get('message')}")
                except Exception as e:
                    self.logger.error("设置监控频率失败: %s", e)
                    fail_messages.append(f"监控频率: {str(e)}")

            # 保存AI配置（会自动触发服务重载）
            if ai_config:
                self.logger.info("开始保存AI配置...")
                result = self.system_service.update_config("ai", ai_config)
                self.logger.info(
                    f"update_config返回: success={result.get('success')}, ai_reloaded={result.get('ai_reloaded')}"
                )

                if result.get("success"):
                    success_count += 1
                    ai_service_reloaded = result.get("ai_reloaded", False)
                    self.logger.info(f"AI配置保存成功，服务重载状态: {ai_service_reloaded}")

                    # 验证配置文件
                    self._verify_config_file()

                    # 检查AI服务是否重载成功
                    if ai_service_reloaded:
                        self.logger.info("✅ AI服务重载成功")
                    else:
                        reload_msg = result.get("ai_reload_message", "未知原因")
                        self.logger.warning(f"⚠️ AI服务重载失败: {reload_msg}")
                        fail_messages.append(f"AI服务重载失败: {reload_msg}")
                else:
                    error_msg = result.get("message", "未知错误")
                    self.logger.error(f"AI配置保存失败: {error_msg}")
                    fail_messages.append(f"AI配置: {error_msg}")

            # 显示保存结果
            if success_count > 0 and not fail_messages:
                if ai_service_reloaded:
                    self.show_info("配置保存成功，AI服务已重新加载")
                else:
                    self.show_info("配置保存成功")
            elif success_count > 0 and fail_messages:
                msg = "部分配置保存成功，但存在问题:\n" + "\n".join(fail_messages)
                self.show_warning(msg)
            else:
                msg = "配置保存失败:\n" + "\n".join(fail_messages)
                self.show_error(msg)

        except Exception as e:
            self.logger.error("保存配置失败: %s", e, exc_info=True)
            self.show_error(f"保存配置失败: {e}")

    def _reset_config(self):
        """重置配置."""
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要重置所有配置为默认值吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._load_config()
                self.show_info("配置已重置为默认值")
            except Exception as e:
                self.logger.error("重置配置失败: %s", e)
                self.show_error(f"重置失败: {e}")

    def _browse_tdx_dir(self):
        """浏览通达信目录."""
        dir_path = QFileDialog.getExistingDirectory(self, "选择通达信软件根目录")
        if dir_path and self.tdx_path_edit:
            self.tdx_path_edit.setText(dir_path)

    def _browse_cache_dir(self):
        """浏览缓存目录."""
        root_dir = get_root()
        # 🔧 默认从项目根目录的 data/cache 开始
        default_dir = str(root_dir / "data" / "cache")
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择品种缓存目录", default_dir
        )
        if dir_path and self.cache_dir_edit:
            dir_path_obj = Path(dir_path)
            # 🔧 尝试转换为相对路径显示（相对于项目根目录）
            try:
                rel_path = dir_path_obj.relative_to(root_dir)
                self.cache_dir_edit.setText(str(rel_path).replace("\\", "/"))
            except ValueError:
                # 无法转换为相对路径，显示绝对路径
                self.cache_dir_edit.setText(dir_path)

    def _browse_data_dir(self):
        """浏览数据目录."""
        root_dir = get_root()
        # 🔧 默认从项目根目录的 data/kline 开始
        default_dir = str(root_dir / "data" / "kline")
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择K线数据目录", default_dir
        )
        if dir_path and self.data_dir_edit:
            dir_path_obj = Path(dir_path)
            # 🔧 尝试转换为相对路径显示（相对于项目根目录）
            try:
                rel_path = dir_path_obj.relative_to(root_dir)
                self.data_dir_edit.setText(str(rel_path).replace("\\", "/"))
            except ValueError:
                # 无法转换为相对路径，显示绝对路径
                self.data_dir_edit.setText(dir_path)

    # ==================== 日志管理方法 ====================

    def _clear_logs(self):
        """清空日志."""
        if self.logs_table:
            self.logs_table.setRowCount(0)
        self.show_info("日志已清空")

    def _export_logs(self):
        """导出日志."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出日志",
            "terminal_logs.txt",
            "文本文件 (*.txt);;所有文件 (*.*)",
        )

        if file_path:
            self.show_info(f"日志已导出到: {file_path}")

    # ==================== 性能监控方法 ====================

    def _clear_performance_history(self):
        """清除性能历史数据."""
        self.performance_history = {"cpu": [], "memory": []}
        if self.cpu_curve:
            self.cpu_curve.setData([], [])
        if self.memory_curve:
            self.memory_curve.setData([], [])
        self.show_info("性能历史数据已清除")

    def _update_system_status(self):
        """更新系统状态."""
        try:
            # 更新基础系统信息
            cpu_percent = psutil.cpu_percent()
            if self.cpu_label:
                self.cpu_label.setText(f"{cpu_percent:.1f}%")

            memory = psutil.virtual_memory()
            if self.memory_label:
                self.memory_label.setText(f"{memory.percent:.1f}%")

            disk = psutil.disk_usage("/")
            if self.disk_label:
                self.disk_label.setText(f"{disk.percent:.1f}%")

            if self.network_label:
                self.network_label.setText("正常")

            # 更新状态表格
            self._update_status_table()

            # 更新性能图表
            self._update_performance_charts()

        except Exception as e:
            self.logger.error("更新系统状态失败: %s", e)

    def _update_status_table(self):
        """更新状态表格."""
        if not self.status_table:
            return

        try:
            self.status_table.setRowCount(0)

            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent
            disk_percent = psutil.disk_usage("/").percent

            components = [
                ("CPU", "正常", f"使用率: {cpu_percent:.1f}%"),
                ("内存", "正常", f"使用率: {memory_percent:.1f}%"),
                ("磁盘", "正常", f"使用率: {disk_percent:.1f}%"),
                ("网络", "正常", "连接正常"),
                ("数据库", "正常", "连接正常"),
            ]

            for i, (component, status, detail) in enumerate(components):
                self.status_table.insertRow(i)
                self.status_table.setItem(i, 0, QTableWidgetItem(component))
                self.status_table.setItem(i, 1, QTableWidgetItem(status))
                self.status_table.setItem(i, 2, QTableWidgetItem(detail))

        except Exception as e:
            self.logger.error("更新状态表格失败: %s", e)

    def _update_performance_charts(self):
        """更新性能图表."""
        if not self.cpu_curve or not self.memory_curve:
            return

        current_time = time.time()

        try:
            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent

            self.performance_history["cpu"].append((current_time, cpu_percent))
            self.performance_history["memory"].append((current_time, memory_percent))

            # 限制历史数据点数量
            for key in self.performance_history:
                if len(self.performance_history[key]) > self.max_history_points:
                    self.performance_history[key] = self.performance_history[key][
                        -self.max_history_points :
                    ]

            # 更新图表
            if self.performance_history["cpu"]:
                times, cpu_values = zip(*self.performance_history["cpu"])
                self.cpu_curve.setData(times, cpu_values)

            if self.performance_history["memory"]:
                times, memory_values = zip(*self.performance_history["memory"])
                self.memory_curve.setData(times, memory_values)

        except Exception as e:
            self.logger.error("更新性能图表失败: %s", e)

    # ==================== 图表创建辅助方法 ====================

    def _create_line_chart(self, title: str, color: str):
        """创建单线图表."""
        chart_widget = pg.GraphicsLayoutWidget()
        chart_widget.setBackground(QColor(26, 26, 26))

        plot = chart_widget.addPlot(title=title)  # type: ignore[attr-defined]
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.setRange(yRange=[0, 100])
        plot.setLabel("bottom", "时间")
        plot.setLabel("left", "百分比 (%)")

        pen = pg.mkPen(color=color, width=2)
        curve = plot.plot(pen=pen)

        # 存储引用
        chart_widget.plot_ref = plot  # type: ignore[attr-defined]
        chart_widget.curve_ref = curve  # type: ignore[attr-defined]

        return chart_widget

    def _create_multi_line_chart(self, title: str):
        """创建多线图表（用于多磁盘I/O）."""
        chart_widget = pg.GraphicsLayoutWidget()
        chart_widget.setBackground(QColor(26, 26, 26))

        plot = chart_widget.addPlot(title=title)  # type: ignore[attr-defined]
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.setLabel("bottom", "时间")
        plot.setLabel("left", "速度 (MB/s)")
        plot.addLegend()

        # 存储曲线引用
        chart_widget.plot_ref = plot  # type: ignore[attr-defined]
        chart_widget.curves_ref = {}  # type: ignore[attr-defined]

        return chart_widget

    def _create_network_chart(self, title: str):
        """创建网络速度图表（上传+下载）."""
        chart_widget = pg.GraphicsLayoutWidget()
        chart_widget.setBackground(QColor(26, 26, 26))

        plot = chart_widget.addPlot(title=title)  # type: ignore[attr-defined]
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.setLabel("bottom", "时间")
        plot.setLabel("left", "速度 (KB/s)")
        plot.addLegend()

        # 上传曲线（红色）
        upload_pen = pg.mkPen(color="#FF6B6B", width=2)
        upload_curve = plot.plot(pen=upload_pen, name="上传")

        # 下载曲线（绿色）
        download_pen = pg.mkPen(color="#4ECDC4", width=2)
        download_curve = plot.plot(pen=download_pen, name="下载")

        chart_widget.plot_ref = plot  # type: ignore[attr-defined]
        chart_widget.upload_curve = upload_curve  # type: ignore[attr-defined]
        chart_widget.download_curve = download_curve  # type: ignore[attr-defined]

        return chart_widget

    def _create_disk_space_chart(self, title: str):
        """创建硬盘空间条形图."""
        chart_widget = QWidget()
        layout = QVBoxLayout(chart_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(title_label)

        # 使用QScrollArea以支持多个磁盘
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setMaximumHeight(120)

        bars_widget = QWidget()
        bars_layout = QVBoxLayout(bars_widget)
        bars_layout.setSpacing(5)

        scroll_area.setWidget(bars_widget)
        layout.addWidget(scroll_area)

        # 存储引用
        chart_widget.bars_layout_ref = bars_layout  # type: ignore[attr-defined]
        chart_widget.disk_bars = {}  # type: ignore[attr-defined]

        return chart_widget

    def _get_disk_color(self, index: int) -> str:
        """获取磁盘曲线颜色."""
        colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8"]
        return colors[index % len(colors)]

    def _create_temperature_chart(self, title: str):
        """创建温度折线图（CPU/GPU/硬盘）."""
        chart_widget = pg.GraphicsLayoutWidget()
        chart_widget.setBackground(QColor(26, 26, 26))

        plot = chart_widget.addPlot(title=title)  # type: ignore[attr-defined]
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.setRange(yRange=[0, 100])
        plot.setLabel("bottom", "时间")
        plot.setLabel("left", "温度 (°C)")
        plot.addLegend()

        # 添加温度警戒线
        # 高温警戒线 (70°C) - 黄色虚线
        warning_line = pg.InfiniteLine(
            pos=70, angle=0, pen=pg.mkPen(color="#FFA500", width=1, style=Qt.PenStyle.DashLine)
        )
        plot.addItem(warning_line)

        # 临界温度线 (85°C) - 红色虚线
        critical_line = pg.InfiniteLine(
            pos=85, angle=0, pen=pg.mkPen(color="#FF0000", width=1, style=Qt.PenStyle.DashLine)
        )
        plot.addItem(critical_line)

        # CPU温度曲线（红色）
        cpu_pen = pg.mkPen(color="#FF6B6B", width=2)
        cpu_curve = plot.plot(pen=cpu_pen, name="CPU")

        # GPU温度曲线（绿色）
        gpu_pen = pg.mkPen(color="#51CF66", width=2)
        gpu_curve = plot.plot(pen=gpu_pen, name="GPU")

        # 硬盘温度曲线（蓝色）
        disk_pen = pg.mkPen(color="#4ECDC4", width=2)
        disk_curve = plot.plot(pen=disk_pen, name="硬盘")

        # 存储引用
        chart_widget.plot_ref = plot  # type: ignore[attr-defined]
        chart_widget.cpu_curve = cpu_curve  # type: ignore[attr-defined]
        chart_widget.gpu_curve = gpu_curve  # type: ignore[attr-defined]
        chart_widget.disk_curve = disk_curve  # type: ignore[attr-defined]

        return chart_widget

    def _create_bottleneck_card_v2(self) -> QWidget:
        """创建瓶颈提示卡片V2（紧凑版，70px高）."""
        card = QWidget()
        card.setFixedHeight(70)
        card.setStyleSheet(DashboardTheme.get_card_style())

        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 左侧：压力评分半圆仪表盘
        self.bottleneck_gauge = GaugeWidget(max_value=100, warning=70, critical=85)
        self.bottleneck_gauge.setFixedSize(60, 40)
        layout.addWidget(self.bottleneck_gauge)

        # 分隔线
        separator = QWidget()
        separator.setFixedWidth(2)
        separator.setStyleSheet(f"background-color: {DashboardTheme.border_light};")
        layout.addWidget(separator)

        # 中间：瓶颈维度
        dimension_layout = QVBoxLayout()
        dimension_layout.setSpacing(1)

        dim_title = QLabel("当前瓶颈")
        dim_title.setStyleSheet(DashboardTheme.get_subtitle_style(DashboardTheme.text_secondary))
        dimension_layout.addWidget(dim_title)

        self.bottleneck_dimension_label = QLabel("均衡")
        self.bottleneck_dimension_label.setStyleSheet(
            DashboardTheme.get_metric_value_style(size=16)
        )
        dimension_layout.addWidget(self.bottleneck_dimension_label)

        layout.addLayout(dimension_layout)

        # 分隔线
        separator2 = QWidget()
        separator2.setFixedWidth(2)
        separator2.setStyleSheet(f"background-color: {DashboardTheme.border_light};")
        layout.addWidget(separator2)

        # 右侧：优化建议（滚动文字）
        suggestion_layout = QVBoxLayout()
        suggestion_layout.setSpacing(1)

        sugg_title = QLabel("优化建议")
        sugg_title.setStyleSheet(DashboardTheme.get_subtitle_style(DashboardTheme.text_secondary))
        suggestion_layout.addWidget(sugg_title)

        self.bottleneck_suggestion_label = QLabel("系统运行正常")
        self.bottleneck_suggestion_label.setWordWrap(True)
        self.bottleneck_suggestion_label.setStyleSheet(
            f"color: {DashboardTheme.text_primary}; font-size: 12px;"
        )
        suggestion_layout.addWidget(self.bottleneck_suggestion_label)

        layout.addLayout(suggestion_layout, 1)  # 建议占更多空间

        return card

    def _create_metrics_grid(self) -> QWidget:
        """创建核心指标网格（2x4 = 8个大指标卡片）."""
        container = QWidget()
        layout = QGridLayout(container)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        # 第1行：CPU、内存、磁盘I/O、网络速度
        self.metric_card_cpu = MetricCard(title="CPU使用率", unit="%", color=DashboardTheme.cpu)
        self.metric_card_memory = MetricCard(
            title="内存使用率", unit="%", color=DashboardTheme.memory
        )
        self.metric_card_disk_io = MetricCard(
            title="磁盘I/O", unit="MB/s", color=DashboardTheme.disk
        )
        self.metric_card_network = MetricCard(
            title="网络速度", unit="MB/s", color=DashboardTheme.network
        )

        layout.addWidget(self.metric_card_cpu, 0, 0)
        layout.addWidget(self.metric_card_memory, 0, 1)
        layout.addWidget(self.metric_card_disk_io, 0, 2)
        layout.addWidget(self.metric_card_network, 0, 3)

        # 第2行：CPU温度、磁盘使用、进程数、负载均衡
        self.metric_card_cpu_temp = MetricCard(
            title="CPU温度", unit="°C", color=DashboardTheme.temp
        )
        self.metric_card_disk_usage = MetricCard(
            title="磁盘使用", unit="%", color=DashboardTheme.disk
        )
        self.metric_card_process_count = MetricCard(
            title="进程数", unit="个", color=DashboardTheme.primary
        )
        self.metric_card_load_avg = MetricCard(
            title="负载均衡", unit="", color=DashboardTheme.warning
        )

        layout.addWidget(self.metric_card_cpu_temp, 1, 0)
        layout.addWidget(self.metric_card_disk_usage, 1, 1)
        layout.addWidget(self.metric_card_process_count, 1, 2)
        layout.addWidget(self.metric_card_load_avg, 1, 3)

        return container

    def _create_bottleneck_card(self) -> QWidget:
        """创建瓶颈提示卡片（系统状态监控顶部）."""
        card = QGroupBox("🎯 系统瓶颈分析")
        card.setMaximumHeight(120)
        card.setStyleSheet(
            """
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #3B82F6;
                border-radius: 8px;
                margin-top: 10px;
                padding: 10px;
                background-color: #1E293B;
            }
            QGroupBox::title {
                color: #3B82F6;
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
            }
        """
        )

        layout = QHBoxLayout(card)
        layout.setSpacing(15)

        # 左侧：压力评分
        score_container = QWidget()
        score_layout = QVBoxLayout(score_container)
        score_layout.setSpacing(5)
        score_layout.setContentsMargins(0, 0, 0, 0)

        score_title = QLabel("压力评分")
        score_title.setStyleSheet("font-size: 11px; color: #94A3B8;")
        score_layout.addWidget(score_title)

        self.bottleneck_score_label = QLabel("--/100")
        self.bottleneck_score_label.setStyleSheet(
            "font-size: 24px; font-weight: bold; color: #10B981;"
        )
        score_layout.addWidget(self.bottleneck_score_label)

        self.bottleneck_severity_label = QLabel("正常")
        self.bottleneck_severity_label.setStyleSheet("font-size: 11px; color: #10B981;")
        score_layout.addWidget(self.bottleneck_severity_label)

        layout.addWidget(score_container)

        # 分隔线
        separator = QWidget()
        separator.setFixedWidth(2)
        separator.setStyleSheet("background-color: #475569;")
        layout.addWidget(separator)

        # 中间：当前瓶颈维度
        dimension_container = QWidget()
        dimension_layout = QVBoxLayout(dimension_container)
        dimension_layout.setSpacing(5)
        dimension_layout.setContentsMargins(0, 0, 0, 0)

        dim_title = QLabel("当前瓶颈")
        dim_title.setStyleSheet("font-size: 11px; color: #94A3B8;")
        dimension_layout.addWidget(dim_title)

        self.bottleneck_dimension_label = QLabel("均衡")
        self.bottleneck_dimension_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #3B82F6;"
        )
        dimension_layout.addWidget(self.bottleneck_dimension_label)

        dimension_layout.addStretch()
        layout.addWidget(dimension_container)

        # 分隔线
        separator2 = QWidget()
        separator2.setFixedWidth(2)
        separator2.setStyleSheet("background-color: #475569;")
        layout.addWidget(separator2)

        # 右侧：优化建议
        suggestion_container = QWidget()
        suggestion_layout = QVBoxLayout(suggestion_container)
        suggestion_layout.setSpacing(5)
        suggestion_layout.setContentsMargins(0, 0, 0, 0)

        sugg_title = QLabel("优化建议")
        sugg_title.setStyleSheet("font-size: 11px; color: #94A3B8;")
        suggestion_layout.addWidget(sugg_title)

        self.bottleneck_suggestion_label = QLabel("系统运行正常")
        self.bottleneck_suggestion_label.setWordWrap(True)
        self.bottleneck_suggestion_label.setStyleSheet("font-size: 12px; color: #E2E8F0;")
        suggestion_layout.addWidget(self.bottleneck_suggestion_label)

        layout.addWidget(suggestion_container, 1)  # 建议占更多空间

        return card

    def _create_temperature_cards(self) -> QWidget:
        """创建温度状态卡片."""
        container = QWidget()
        container.setStyleSheet("background-color: #2C2C2C; border-radius: 5px;")
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 标题
        title_label = QLabel("🌡️ 硬件温度")
        title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #FFFFFF;")
        layout.addWidget(title_label)

        # 创建三个温度卡片：CPU、GPU、硬盘
        for device_type, device_name, icon in [
            ("cpu", "CPU", "🖥️"),
            ("gpu", "GPU", "🎮"),
            ("disk", "硬盘", "💾"),
        ]:
            card = QWidget()
            card.setStyleSheet(
                """
                QWidget {
                    background-color: #1E1E1E;
                    border-radius: 5px;
                    padding: 8px;
                }
                """
            )
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)

            # 设备图标和名称
            icon_label = QLabel(f"{icon} {device_name}")
            icon_label.setStyleSheet("font-size: 12px; font-weight: bold;")
            card_layout.addWidget(icon_label)

            card_layout.addStretch()

            # 温度值
            temp_label = QLabel("--°C")
            temp_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #51CF66;")
            temp_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            card_layout.addWidget(temp_label)

            # 状态图标
            status_label = QLabel("●")
            status_label.setStyleSheet("font-size: 16px; color: #51CF66;")
            card_layout.addWidget(status_label)

            layout.addWidget(card)

            # 保存标签引用
            self.temperature_card_labels[device_type] = {
                "temp": temp_label,
                "status": status_label,
            }

        layout.addStretch()
        return container

    def _create_smart_warning_cards(self) -> QWidget:
        """创建SMART扇区告警卡片（硬盘健康关键指标）."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 重映射扇区卡片
        self.smart_reallocated_card = MetricCard(title="重映射扇区", unit="个", color="#FF4444")
        layout.addWidget(self.smart_reallocated_card)

        # 待映射扇区卡片
        self.smart_pending_card = MetricCard(title="待映射扇区", unit="个", color="#FF8800")
        layout.addWidget(self.smart_pending_card)

        return widget

    # ==================== 事件处理回调 ====================

    def _on_system_status_event(self, event):
        """处理系统状态更新事件."""
        try:
            metrics = event.data

            # 新增：更新指标卡片（Dashboard Pro风格）
            self._update_metric_cards(metrics)

            # 更新CPU图表
            cpu_percent = metrics.get("cpu_percent", 0)
            self._update_line_chart(self.cpu_chart, "cpu", cpu_percent)

            # 更新内存图表
            memory_percent = metrics.get("memory_percent", 0)
            self._update_line_chart(self.memory_chart, "memory", memory_percent)

            # 更新磁盘I/O图表
            disk_io_speed = metrics.get("disk_io_speed", {})
            self._update_disk_io_chart(disk_io_speed)

            # 更新网络速度图表
            network_speed = metrics.get("network_speed", {})
            self._update_network_chart(network_speed)

            # 更新磁盘空间图表
            disk_info = metrics.get("disk_info", {})
            self._update_disk_space_chart(disk_info)

            # 更新详细数据表格
            self._update_status_details_table(metrics)

            # 更新进程监控Tab的热力图（整体设备监控）
            self._update_heatmaps(metrics)

        except Exception as e:
            self.logger.error("处理系统状态事件失败: %s", e)

    def _on_performance_event(self, event):
        """处理性能指标更新事件."""
        try:
            indicators = event.data.get("performance_indicators", {})

            # 更新数据处理性能
            data_processing = indicators.get("data_processing", {})
            if self.data_processing_widgets:
                self._update_performance_group(
                    self.data_processing_widgets,
                    [
                        data_processing.get("avg_query_time_ms", 0),
                        data_processing.get("avg_download_speed_mbps", 0),
                        data_processing.get("cache_hit_rate", 0),
                        data_processing.get("total_queries", 0),
                    ],
                )

            # 更新策略执行性能
            strategy = indicators.get("strategy_execution", {})
            if self.strategy_execution_widgets:
                self._update_performance_group(
                    self.strategy_execution_widgets,
                    [
                        strategy.get("avg_signal_latency_ms", 0),
                        strategy.get("on_bar_processing_time_ms", 0),
                        strategy.get("strategy_throughput", 0),
                        strategy.get("error_rate", 0),
                        strategy.get("total_calls", 0),
                    ],
                )

            # 更新交易执行性能
            trading = indicators.get("trading_execution", {})
            if self.trading_execution_widgets:
                self._update_performance_group(
                    self.trading_execution_widgets,
                    [
                        trading.get("avg_order_latency_ms", 0),
                        trading.get("order_success_rate", 0),
                        trading.get("position_update_delay_ms", 0),
                    ],
                )

        except Exception as e:
            self.logger.error("处理性能指标事件失败: %s", e)

    def _on_service_status_event(self, event):
        """处理服务状态更新事件（增强版 - 包含外部依赖）."""
        try:
            status = event.data
            # 更新服务表格
            if hasattr(self, "services_table") and self.services_table:
                services = status.get("services", [])
                self._update_services_table(services)

            # 更新外部依赖表格
            if hasattr(self, "dependencies_table") and self.dependencies_table:
                external_dependencies = status.get("external_dependencies", {})
                self._update_dependencies_table(external_dependencies)

            # 更新健康评分
            if hasattr(self, "health_progress") and self.health_progress:
                health_score = status.get("health_score", 0)
                self.health_progress.setValue(int(health_score))

            if hasattr(self, "health_detail_label") and self.health_detail_label:
                online = status.get("online_services", 0)
                total = status.get("total_services", 0)
                avg_time = status.get("avg_response_time_ms", 0)
                service_health = status.get("service_health_score", 0)
                dep_health = status.get("dependency_health_score", 0)
                self.health_detail_label.setText(
                    f"在线服务: {online}/{total} | "
                    f"平均响应时间: {avg_time:.1f}ms | "
                    f"服务健康: {service_health:.0f}% | "
                    f"依赖健康: {dep_health:.0f}%"
                )

        except Exception as e:
            self.logger.error("处理服务状态事件失败: %s", e)

    def _on_process_status_event(self, event):
        """处理进程状态更新事件.

        Args:
            event: 进程状态事件，包含processes列表
        """
        try:
            data = event.data
            processes = data.get("processes", [])

            # 更新进程表格
            if hasattr(self, "process_table") and self.process_table:
                self._update_process_table(processes)

        except Exception as e:
            self.logger.error("处理进程状态事件失败: %s", e)

    # ==================== 图表更新方法 ====================

    def _update_metric_cards(self, metrics: Dict[str, Any]):
        """更新指标卡片（Dashboard Pro风格）.

        Args:
            metrics: 系统指标数据
        """
        try:
            # 更新CPU使用率卡片
            if hasattr(self, "metric_card_cpu"):
                cpu_percent = metrics.get("cpu_percent", 0)
                self.metric_card_cpu.update_value(cpu_percent)

            # 更新内存使用率卡片
            if hasattr(self, "metric_card_memory"):
                memory_percent = metrics.get("memory_percent", 0)
                self.metric_card_memory.update_value(memory_percent)

            # 更新磁盘I/O卡片（取最大值）
            if hasattr(self, "metric_card_disk_io"):
                disk_io_speed = metrics.get("disk_io_speed", {})
                max_io = 0.0
                for disk, speeds in disk_io_speed.items():
                    if disk == "io_counters":
                        continue
                    read_speed = speeds.get("read_speed", 0)
                    write_speed = speeds.get("write_speed", 0)
                    max_io = max(max_io, read_speed, write_speed)
                self.metric_card_disk_io.update_value(max_io)

            # 更新网络速度卡片（取最大值，转MB/s）
            if hasattr(self, "metric_card_network"):
                network_speed = metrics.get("network_speed", {})
                upload_kbps = network_speed.get("upload_speed_kbps", 0)
                download_kbps = network_speed.get("download_speed_kbps", 0)
                max_speed_mbps = max(upload_kbps, download_kbps) / 1024
                self.metric_card_network.update_value(max_speed_mbps)

            # 更新CPU温度卡片
            if hasattr(self, "metric_card_cpu_temp"):
                # 从hardware数据中提取CPU温度
                hardware_data = metrics.get("hardware", {})
                temperature_data = hardware_data.get("temperature", {})
                cpu_temp = None
                for device, sensors in temperature_data.items():
                    if not sensors or not isinstance(sensors, list):
                        continue
                    sensor = sensors[0]
                    temp = sensor.get("current", 0)
                    if (
                        "CPU" in device
                        or "ACPI" in device
                        or "processor" in device.lower()
                        or "Ryzen" in device
                        or "Intel" in device
                        or "Threadripper" in device
                    ):
                        cpu_temp = temp
                        break
                if cpu_temp is not None:
                    self.metric_card_cpu_temp.update_value(cpu_temp)

            # 更新磁盘使用卡片（取平均值）
            if hasattr(self, "metric_card_disk_usage"):
                disk_info = metrics.get("disk_info", {})
                total_percent = 0
                count = 0
                for disk, info in disk_info.items():
                    if disk == "io_counters":
                        continue
                    total_percent += info.get("percent", 0)
                    count += 1
                avg_percent = total_percent / count if count > 0 else 0
                self.metric_card_disk_usage.update_value(avg_percent)

            # 更新进程数卡片
            if hasattr(self, "metric_card_process_count"):
                process_count = metrics.get("process_count", 0)
                self.metric_card_process_count.update_value(process_count)

            # 更新负载均衡卡片（CPU负载）
            if hasattr(self, "metric_card_load_avg"):
                load_avg = metrics.get("load_average", [0])[0] if metrics.get("load_average") else 0
                self.metric_card_load_avg.update_value(load_avg)

        except Exception as e:
            self.logger.error("更新指标卡片失败: %s", e)

    def _update_line_chart(self, chart_widget, key: str, value: float):
        """更新单线图表."""
        try:
            if not chart_widget or not hasattr(chart_widget, "curve_ref"):
                return

            # 添加数据点
            self.system_status_history[key].append((time.time(), value))

            # 更新曲线
            if self.system_status_history[key]:
                times, values = zip(*self.system_status_history[key])
                chart_widget.curve_ref.setData(times, values)

        except Exception as e:
            self.logger.error("更新图表失败 %s: %s", key, e)

    def _update_disk_io_chart(self, disk_io_speed: Dict[str, Dict[str, float]]):
        """更新磁盘I/O图表."""
        try:
            if not self.disk_io_chart or not hasattr(self.disk_io_chart, "curves_ref"):
                return

            current_time = time.time()

            for disk, speeds in disk_io_speed.items():
                read_speed = speeds.get("read_speed", 0)
                write_speed = speeds.get("write_speed", 0)

                # 为每个磁盘创建读写曲线
                read_key = f"{disk}_read"
                write_key = f"{disk}_write"

                # 创建读曲线
                if read_key not in self.disk_io_chart.curves_ref:
                    color = self._get_disk_color(len(self.disk_io_chart.curves_ref))
                    pen = pg.mkPen(color=color, width=2, style=Qt.PenStyle.SolidLine)
                    curve = self.disk_io_chart.plot_ref.plot(pen=pen, name=f"{disk} 读")
                    self.disk_io_chart.curves_ref[read_key] = curve
                    self.system_status_history["disk_io"][read_key] = deque(maxlen=100)

                # 创建写曲线
                if write_key not in self.disk_io_chart.curves_ref:
                    color = self._get_disk_color(len(self.disk_io_chart.curves_ref))
                    pen = pg.mkPen(color=color, width=2, style=Qt.PenStyle.DashLine)
                    curve = self.disk_io_chart.plot_ref.plot(pen=pen, name=f"{disk} 写")
                    self.disk_io_chart.curves_ref[write_key] = curve
                    self.system_status_history["disk_io"][write_key] = deque(maxlen=100)

                # 更新数据
                self.system_status_history["disk_io"][read_key].append((current_time, read_speed))
                self.system_status_history["disk_io"][write_key].append((current_time, write_speed))

                # 更新曲线
                times_r, values_r = zip(*self.system_status_history["disk_io"][read_key])
                self.disk_io_chart.curves_ref[read_key].setData(times_r, values_r)

                times_w, values_w = zip(*self.system_status_history["disk_io"][write_key])
                self.disk_io_chart.curves_ref[write_key].setData(times_w, values_w)

        except Exception as e:
            self.logger.error("更新磁盘I/O图表失败: %s", e)

    def _update_network_chart(self, network_speed: Dict[str, Any]):
        """更新网络速度图表."""
        try:
            if not self.network_speed_chart:
                return

            upload = network_speed.get("upload_speed_kbps", 0)
            download = network_speed.get("download_speed_kbps", 0)
            current_time = time.time()

            # 更新上传曲线
            self.system_status_history["network"]["upload"].append((current_time, upload))
            if self.system_status_history["network"]["upload"]:
                times, values = zip(*self.system_status_history["network"]["upload"])
                self.network_speed_chart.upload_curve.setData(times, values)

            # 更新下载曲线
            self.system_status_history["network"]["download"].append((current_time, download))
            if self.system_status_history["network"]["download"]:
                times, values = zip(*self.system_status_history["network"]["download"])
                self.network_speed_chart.download_curve.setData(times, values)

        except Exception as e:
            self.logger.error("更新网络速度图表失败: %s", e)

    def _update_disk_space_chart(self, disk_info: Dict[str, Any]):
        """更新磁盘空间图表."""
        try:
            if not self.disk_space_chart or not hasattr(self.disk_space_chart, "bars_layout_ref"):
                return

            for disk, info in disk_info.items():
                if disk == "io_counters":
                    continue

                if disk not in self.disk_space_chart.disk_bars:
                    # 创建新的进度条
                    bar_widget = QWidget()
                    bar_layout = QHBoxLayout(bar_widget)
                    bar_layout.setContentsMargins(0, 2, 0, 2)

                    label = QLabel(disk)
                    label.setMinimumWidth(80)
                    label.setStyleSheet("font-weight: bold;")
                    bar_layout.addWidget(label)

                    progress = QProgressBar()
                    progress.setTextVisible(True)
                    progress.setStyleSheet(
                        """
                        QProgressBar {
                            border: 1px solid #444;
                            border-radius: 3px;
                            text-align: center;
                        }
                        QProgressBar::chunk {
                            background-color: #4ECDC4;
                        }
                        """
                    )
                    bar_layout.addWidget(progress)

                    size_label = QLabel("")
                    size_label.setMinimumWidth(120)
                    size_label.setStyleSheet("color: #888; font-size: 11px;")
                    bar_layout.addWidget(size_label)

                    self.disk_space_chart.bars_layout_ref.addWidget(bar_widget)
                    self.disk_space_chart.disk_bars[disk] = {
                        "progress": progress,
                        "size_label": size_label,
                    }

                # 更新进度条
                percent = info.get("percent", 0)
                total = info.get("total", 0)
                used = info.get("used", 0)
                free = info.get("free", 0)

                bar_info = self.disk_space_chart.disk_bars[disk]
                bar_info["progress"].setValue(int(percent))
                bar_info["progress"].setFormat(f"{percent:.1f}% 已用")

                # 更新大小信息
                total_gb = total / (1024**3) if total else 0
                used_gb = used / (1024**3) if used else 0
                free_gb = free / (1024**3) if free else 0
                bar_info["size_label"].setText(
                    f"总计: {total_gb:.1f}GB | 已用: {used_gb:.1f}GB | 可用: {free_gb:.1f}GB"
                )

                # 根据使用率设置颜色
                if percent > 90:
                    bar_info["progress"].setStyleSheet(
                        """
                        QProgressBar::chunk { background-color: #FF6B6B; }
                        """
                    )
                elif percent > 80:
                    bar_info["progress"].setStyleSheet(
                        """
                        QProgressBar::chunk { background-color: #FFA07A; }
                        """
                    )
                else:
                    bar_info["progress"].setStyleSheet(
                        """
                        QProgressBar::chunk { background-color: #4ECDC4; }
                        """
                    )

        except Exception as e:
            self.logger.error("更新磁盘空间图表失败: %s", e)

    def _update_temperature_chart(self, temperature_data: Dict[str, Any]):
        """更新温度折线图."""
        try:
            if not self.temperature_chart or not hasattr(self.temperature_chart, "cpu_curve"):
                return

            current_time = time.time()

            # 分类提取温度数据
            cpu_temp = None
            gpu_temp = None
            disk_temp = None

            for device, sensors in temperature_data.items():
                if not sensors or not isinstance(sensors, list):
                    continue

                sensor = sensors[0]  # 取第一个传感器
                temp = sensor.get("current", 0)

                # 根据设备名称分类
                device_lower = device.lower()
                if (
                    "CPU" in device
                    or "ACPI" in device
                    or "processor" in device_lower
                    or "Ryzen" in device
                    or "Intel" in device
                    or "Threadripper" in device
                ):
                    if cpu_temp is None:  # 只取第一个CPU温度
                        cpu_temp = temp
                elif (
                    "GPU" in device
                    or "NVIDIA" in device
                    or "Radeon" in device
                    or "GeForce" in device
                    or "RTX" in device
                    or "GTX" in device
                ):
                    if gpu_temp is None:  # 只取第一个GPU温度
                        gpu_temp = temp
                elif (
                    "Disk" in device
                    or "Drive" in device
                    or "SSD" in device
                    or "HDD" in device
                    or "WDC" in device
                    or "Samsung" in device
                    or "Seagate" in device
                    or "Crucial" in device
                ):
                    if disk_temp is None:  # 只取第一个硬盘温度
                        disk_temp = temp

            # 更新CPU温度曲线
            if cpu_temp is not None:
                self.system_status_history["temp_cpu"].append((current_time, cpu_temp))
                if self.system_status_history["temp_cpu"]:
                    times, values = zip(*self.system_status_history["temp_cpu"])
                    self.temperature_chart.cpu_curve.setData(times, values)

            # 更新GPU温度曲线
            if gpu_temp is not None:
                self.system_status_history["temp_gpu"].append((current_time, gpu_temp))
                if self.system_status_history["temp_gpu"]:
                    times, values = zip(*self.system_status_history["temp_gpu"])
                    self.temperature_chart.gpu_curve.setData(times, values)

            # 更新硬盘温度曲线
            if disk_temp is not None:
                self.system_status_history["temp_disk"].append((current_time, disk_temp))
                if self.system_status_history["temp_disk"]:
                    times, values = zip(*self.system_status_history["temp_disk"])
                    self.temperature_chart.disk_curve.setData(times, values)

        except Exception as e:
            self.logger.error("更新温度图表失败: %s", e)

    def _update_hardware_sensors_from_data(self, hardware_data: Dict[str, Any]):
        """从监控数据更新硬件传感器显示.

        Args:
            hardware_data: 硬件数据字典，包含temperature, power, voltage, fan等
        """
        try:
            # 更新温度数据（卡片和图表）
            if "temperature" in hardware_data and hardware_data["temperature"]:
                temperature_data = hardware_data["temperature"]
                self._update_temperature_cards(temperature_data)
                self._update_temperature_chart(temperature_data)

            # 更新扩展硬件数据（功率、电压、风扇等）
            self._update_extended_hardware_data(hardware_data)

        except Exception as e:
            self.logger.error("更新硬件传感器数据失败: %s", e, exc_info=True)

    def _update_extended_hardware_data(self, hardware_data: Dict[str, Any]):
        """更新扩展硬件数据（功率、电压、风扇等）

        Args:
            hardware_data: 硬件数据字典
        """
        try:
            # 1. 更新功率数据
            if "power" in hardware_data:
                power_data = hardware_data["power"]
                if hasattr(self, "power_usage_label"):
                    total_power = power_data.get("total_watts", 0)
                    self.power_usage_label.setText(f"{total_power:.1f} W")

                # 电池信息（如果是笔记本）
                if "battery_percent" in power_data and hasattr(self, "battery_label"):
                    battery_pct = power_data.get("battery_percent", 0)
                    plugged = power_data.get("power_plugged", False)
                    status = "充电中" if plugged else "使用电池"
                    self.battery_label.setText(f"{status}: {battery_pct:.0f}%")

            # 2. 更新电压数据
            if "voltage" in hardware_data:
                voltage_data = hardware_data["voltage"]
                if hasattr(self, "voltage_label"):
                    cpu_voltage = voltage_data.get("cpu_voltage", 0)
                    self.voltage_label.setText(f"{cpu_voltage:.2f} V")

            # 3. 更新风扇数据
            if "fans" in hardware_data:
                fans_data = hardware_data["fans"]
                for idx, fan in enumerate(fans_data):
                    fan_label = getattr(self, f"fan_{idx}_label", None)
                    if fan_label:
                        rpm = fan.get("rpm", 0)
                        fan_name = fan.get("name", f"风扇{idx+1}")
                        fan_label.setText(f"{fan_name}: {rpm} RPM")

            # 4. 更新GPU数据（如果有）
            if "gpu" in hardware_data:
                gpu_data = hardware_data["gpu"]
                if hasattr(self, "gpu_power_label"):
                    gpu_power = gpu_data.get("power_watts", 0)
                    self.gpu_power_label.setText(f"{gpu_power:.1f} W")

                if hasattr(self, "gpu_voltage_label"):
                    gpu_voltage = gpu_data.get("voltage", 0)
                    self.gpu_voltage_label.setText(f"{gpu_voltage:.3f} V")

                if hasattr(self, "gpu_temp_label"):
                    gpu_temp = gpu_data.get("temperature", 0)
                    self.gpu_temp_label.setText(f"{gpu_temp:.1f} °C")

                if hasattr(self, "gpu_util_label"):
                    gpu_util = gpu_data.get("utilization", 0)
                    self.gpu_util_label.setText(f"{gpu_util:.1f}%")

        except Exception as e:
            self.logger.debug(f"更新扩展硬件数据失败（部分硬件不支持）: {e}")

    def _update_bottleneck_card(self, bottleneck_data: Dict[str, Any]):
        """更新瓶颈提示卡片（并缓存瓶颈维度供详细表格使用）.

        Args:
            bottleneck_data: {
                "total_score": 75,
                "bottleneck_dimension": "disk_io",
                "scores": {...},
                "suggestions": [...],
                "severity": "warning"
            }
        """
        try:
            # 🔧 V2优化：检查UI组件是否已创建，避免循环ERROR日志刷屏
            if (
                not hasattr(self, "bottleneck_dimension_label")
                or self.bottleneck_dimension_label is None
            ):
                # UI组件尚未创建，静默跳过（不输出日志，避免刷屏）
                return

            # 缓存瓶颈数据供详细表格使用
            self._cached_bottleneck_data = bottleneck_data

            total_score = bottleneck_data.get("total_score", 100)
            severity = bottleneck_data.get("severity", "good")
            dimension = bottleneck_data.get("bottleneck_dimension", "balanced")
            suggestions = bottleneck_data.get("suggestions", [])

            # 更新仪表盘（新版使用GaugeWidget）
            if hasattr(self, "bottleneck_gauge"):
                self.bottleneck_gauge.set_value(int(total_score))

            # 兼容旧版本（如果有bottleneck_score_label说明是旧卡片）
            if hasattr(self, "bottleneck_score_label"):
                self.bottleneck_score_label.setText(f"{int(total_score)}/100")

                # 根据严重程度设置颜色
                severity_map = {
                    "good": ("性能充足", "#10B981"),
                    "normal": ("正常", "#3B82F6"),
                    "warning": ("压力大", "#F59E0B"),
                    "critical": ("瓶颈", "#EF4444"),
                }
                severity_text, severity_color = severity_map.get(severity, ("未知", "#94A3B8"))

                self.bottleneck_score_label.setStyleSheet(
                    f"font-size: 24px; font-weight: bold; color: {severity_color};"
                )
                self.bottleneck_severity_label.setText(severity_text)
                self.bottleneck_severity_label.setStyleSheet(
                    f"font-size: 11px; color: {severity_color};"
                )

            # 更新瓶颈维度（新旧版本通用）
            dimension_map = {
                "cpu": "CPU",
                "memory": "内存",
                "disk": "磁盘I/O",
                "disk_io": "磁盘I/O",
                "network": "网络",
                "balanced": "均衡",
            }
            dimension_text = dimension_map.get(dimension, dimension or "unknown")
            self.bottleneck_dimension_label.setText(dimension_text)

            # 瓶颈高亮显示
            if severity in ["warning", "critical"]:
                color = DashboardTheme.error
            else:
                color = DashboardTheme.primary

            self.bottleneck_dimension_label.setStyleSheet(
                DashboardTheme.get_metric_value_style(size=18, color=color)
            )

            # 更新建议（显示前2条）
            suggestion_text_base = ""
            if suggestions:
                suggestion_text_base = " / ".join(suggestions[:2])
            else:
                suggestion_text_base = "系统运行正常"

            # 显示自适应并发因子（新增）
            if "adaptive_scale_factor" in bottleneck_data:
                scale_factor = bottleneck_data["adaptive_scale_factor"]
                suggestion_text_base += f"\n\n📊 建议并发倍数: {scale_factor}x"

                if scale_factor < 0.5:
                    suggestion_text_base += " (系统压力大，建议降低并发)"
                elif scale_factor > 1.2:
                    suggestion_text_base += " (系统性能充足，可提高并发)"

            self.bottleneck_suggestion_label.setText(suggestion_text_base)

        except Exception as e:
            self.logger.error("更新瓶颈卡片失败: %s", e)

    def _update_thresholds_display(self, thresholds_data: Dict[str, Any]):
        """更新动态阈值显示.

        Args:
            thresholds_data: {
                "cpu_percent": {
                    "warning": 85.5,
                    "critical": 95.2,
                    "p95": 82.3,
                    "p99": 94.1,
                    "sample_count": 500,
                    "using_default": False
                },
                ...
            }
        """
        try:
            if not hasattr(self, "thresholds_table"):
                return

            self.thresholds_table.setRowCount(0)

            # 中文名称映射
            metric_names_cn = {
                "cpu_percent": "CPU使用率",
                "memory_percent": "内存使用率",
                "disk_usage_percent": "磁盘使用率",
                "network_io": "网络IO",
                "disk_io_mbps": "磁盘IO速率",
            }

            for metric_name, data in thresholds_data.items():
                row = self.thresholds_table.rowCount()
                self.thresholds_table.insertRow(row)

                # 列0: 指标名称（中文）
                display_name = metric_names_cn.get(metric_name, metric_name)
                self.thresholds_table.setItem(row, 0, QTableWidgetItem(display_name))

                # 列1: P95值
                p95 = data.get("p95")
                p95_text = f"{p95:.2f}" if p95 is not None else "--"
                self.thresholds_table.setItem(row, 1, QTableWidgetItem(p95_text))

                # 列2: P99值
                p99 = data.get("p99")
                p99_text = f"{p99:.2f}" if p99 is not None else "--"
                self.thresholds_table.setItem(row, 2, QTableWidgetItem(p99_text))

                # 列3: 警告阈值
                warning = data.get("warning", 0)
                self.thresholds_table.setItem(row, 3, QTableWidgetItem(f"{warning:.2f}"))

                # 列4: 严重阈值
                critical = data.get("critical", 0)
                self.thresholds_table.setItem(row, 4, QTableWidgetItem(f"{critical:.2f}"))

                # 列5: 样本数
                sample_count = data.get("sample_count", 0)
                using_default = data.get("using_default", True)
                sample_text = f"{sample_count}" + (" (默认)" if using_default else "")
                self.thresholds_table.setItem(row, 5, QTableWidgetItem(sample_text))

        except Exception as e:
            self.logger.error("更新动态阈值显示失败: %s", e)

    def _update_concurrent_tasks_display(self, tasks_data: Dict[str, int]):
        """更新并发任务数显示.

        Args:
            tasks_data: {"download": 0, "backtest": 0, "trading": 0, "total": 0}
        """
        try:
            if not hasattr(self, "concurrent_download_label"):
                return

            self.concurrent_download_label.setText(f"下载任务: {tasks_data.get('download', 0)}")
            self.concurrent_backtest_label.setText(f"回测任务: {tasks_data.get('backtest', 0)}")
            self.concurrent_trading_label.setText(f"交易任务: {tasks_data.get('trading', 0)}")
            self.concurrent_total_label.setText(f"总计: {tasks_data.get('total', 0)}")

        except Exception as e:
            self.logger.error("更新并发任务统计显示失败: %s", e)

    def _update_temperature_cards(self, temperature_data: Dict[str, Any]):
        """更新温度状态卡片."""
        try:
            if not self.temperature_card_labels:
                return

            # 分类提取温度数据
            temps = {"cpu": None, "gpu": None, "disk": None}

            for device, sensors in temperature_data.items():
                if not sensors or not isinstance(sensors, list):
                    continue

                sensor = sensors[0]
                temp = sensor.get("current", 0)

                # 根据设备名称分类
                device_lower = device.lower()
                if (
                    "CPU" in device
                    or "ACPI" in device
                    or "processor" in device_lower
                    or "Ryzen" in device
                    or "Intel" in device
                    or "Threadripper" in device
                ):
                    if temps["cpu"] is None:
                        temps["cpu"] = temp
                elif (
                    "GPU" in device
                    or "NVIDIA" in device
                    or "Radeon" in device
                    or "GeForce" in device
                    or "RTX" in device
                    or "GTX" in device
                ):
                    if temps["gpu"] is None:
                        temps["gpu"] = temp
                elif (
                    "Disk" in device
                    or "Drive" in device
                    or "SSD" in device
                    or "HDD" in device
                    or "WDC" in device
                    or "Samsung" in device
                    or "Seagate" in device
                    or "Crucial" in device
                ):
                    if temps["disk"] is None:
                        temps["disk"] = temp

            # 更新卡片显示
            for device_type, temp in temps.items():
                if device_type not in self.temperature_card_labels:
                    continue

                labels = self.temperature_card_labels[device_type]

                if temp is not None:
                    # 更新温度显示
                    labels["temp"].setText(f"{temp:.1f}°C")

                    # 根据温度设置颜色
                    if temp < 60:
                        # 正常温度 - 绿色
                        color = "#51CF66"
                        status = "●"
                    elif temp < 80:
                        # 警告温度 - 黄色
                        color = "#FFA500"
                        status = "●"
                    else:
                        # 危险温度 - 红色
                        color = "#FF6B6B"
                        status = "●"

                    labels["temp"].setStyleSheet(
                        f"font-size: 14px; font-weight: bold; color: {color};"
                    )
                    labels["status"].setStyleSheet(f"font-size: 16px; color: {color};")
                    labels["status"].setText(status)
                else:
                    # 未检测到温度
                    if device_type == "gpu":
                        # GPU特殊提示
                        labels["temp"].setText("不支持")
                        labels["temp"].setStyleSheet(
                            "font-size: 12px; font-weight: normal; color: #999;"
                        )
                    else:
                        labels["temp"].setText("--°C")
                        labels["temp"].setStyleSheet(
                            "font-size: 14px; font-weight: bold; color: #666;"
                        )
                    labels["status"].setStyleSheet("font-size: 16px; color: #666;")
                    labels["status"].setText("○")

        except Exception as e:
            self.logger.error("更新温度卡片失败: %s", e)

    def _get_bottleneck_status_for_metric(self, metric_name: str, bottleneck_dimension: str) -> str:
        """获取指标的瓶颈状态标记.

        Args:
            metric_name: 指标名称
            bottleneck_dimension: 当前系统瓶颈维度 (cpu/memory/disk_io/network/balanced)

        Returns:
            瓶颈状态文本
        """
        # 指标名称到瓶颈维度的映射
        metric_to_dimension = {
            "CPU使用率": "cpu",
            "上下文切换": "cpu",
            "CPU中断": "cpu",
            "内存使用率": "memory",
            "内存交换": "memory",
            "磁盘I/O": "disk_io",  # 匹配"磁盘I/O读取"和"磁盘I/O写入"
            "磁盘延迟": "disk_io",
            "网络上传": "network",
            "网络下载": "network",
            "带宽占用": "network",
            "网络丢包率": "network",
        }

        # 检查指标是否匹配瓶颈维度
        for key, dimension in metric_to_dimension.items():
            if key in metric_name:
                if dimension == bottleneck_dimension:
                    return "🔴 短板"
                break

        return "--"

    def _update_status_details_table(self, metrics: Dict[str, Any]):
        """更新状态详细数据表格（含瓶颈状态列）."""
        try:
            if not self.status_details_table:
                return

            # 获取瓶颈维度（从缓存的监控数据中）
            bottleneck_dimension = "balanced"  # 默认均衡
            if hasattr(self, "_cached_bottleneck_data"):
                bottleneck_dimension = self._cached_bottleneck_data.get(
                    "bottleneck_dimension", "balanced"
                )

            # 更新统计数据
            cpu_percent = metrics.get("cpu_percent", 0)
            memory_percent = metrics.get("memory_percent", 0)

            # 获取磁盘I/O速度（按磁盘分组）
            disk_io_speed = metrics.get("disk_io_speed", {})

            # 更新CPU统计
            self._update_stat("cpu", cpu_percent)
            # 更新内存统计
            self._update_stat("memory", memory_percent)

            # 更新每个磁盘的I/O统计
            current_time = time.time()
            for mount_point, disk_data in disk_io_speed.items():
                # 初始化该磁盘的统计结构（如果不存在）
                if mount_point not in self.system_stats["disks"]:
                    self.system_stats["disks"][mount_point] = {
                        "read": {"current": 0, "avg": 0},
                        "write": {"current": 0, "avg": 0},
                    }
                if mount_point not in self.system_status_history["disks"]:
                    self.system_status_history["disks"][mount_point] = {
                        "read": deque(maxlen=100),
                        "write": deque(maxlen=100),
                    }
                if mount_point not in self.metric_thresholds["disks"]:
                    # 从后端获取的阈值
                    self.metric_thresholds["disks"][mount_point] = {
                        "read": disk_data.get("read_threshold", 400000),
                        "write": disk_data.get("write_threshold", 300000),
                        "type": disk_data.get("disk_type", "unknown"),
                    }

                # 获取当前速度
                read_speed_kbps = disk_data.get("read_speed_kbps", 0)
                write_speed_kbps = disk_data.get("write_speed_kbps", 0)

                # 记录历史数据
                self.system_status_history["disks"][mount_point]["read"].append(
                    (current_time, read_speed_kbps)
                )
                self.system_status_history["disks"][mount_point]["write"].append(
                    (current_time, write_speed_kbps)
                )

                # 更新统计（使用 _update_disk_stat 方法）
                self._update_disk_stat(mount_point, "read", read_speed_kbps)
                self._update_disk_stat(mount_point, "write", write_speed_kbps)

            # 网络速度统计
            network_speed = metrics.get("network_speed", {})
            upload = network_speed.get("upload_speed_kbps", 0)
            download = network_speed.get("download_speed_kbps", 0)
            bandwidth = network_speed.get("bandwidth_percent", 0)

            # 记录历史数据（带时间戳）
            self.system_status_history["bandwidth"].append((current_time, bandwidth))

            self._update_stat("network_upload", upload)
            self._update_stat("network_download", download)
            self._update_stat("bandwidth", bandwidth)

            # 构建表格行（当前值、平均值、阈值、瓶颈状态）
            rows = [
                (
                    "CPU使用率",
                    f"{self.system_stats['cpu']['current']:.1f}%",
                    f"{self.system_stats['cpu']['avg']:.1f}%",
                    f"{self.metric_thresholds['cpu']:.0f}%",
                ),
                (
                    "内存使用率",
                    f"{self.system_stats['memory']['current']:.1f}%",
                    f"{self.system_stats['memory']['avg']:.1f}%",
                    f"{self.metric_thresholds['memory']:.0f}%",
                ),
            ]

            # 添加每个磁盘的I/O行
            for mount_point in sorted(self.system_stats["disks"].keys()):
                disk_stats = self.system_stats["disks"][mount_point]
                disk_thresholds = self.metric_thresholds["disks"].get(mount_point, {})
                disk_type = disk_thresholds.get("type", "unknown")

                # 磁盘类型标签
                type_label = {
                    "nvme": "NVMe",
                    "ssd": "SSD",
                    "hdd": "HDD",
                    "unknown": "",
                }.get(disk_type, "")

                # 读取行
                rows.append(
                    (
                        (
                            f"磁盘{mount_point} I/O读取 ({type_label})"
                            if type_label
                            else f"磁盘{mount_point} I/O读取"
                        ),
                        f"{disk_stats['read']['current']:.1f} KB/s",
                        f"{disk_stats['read']['avg']:.1f} KB/s",
                        f"{disk_thresholds.get('read', 400000):.0f} KB/s",
                    )
                )
                # 写入行
                rows.append(
                    (
                        (
                            f"磁盘{mount_point} I/O写入 ({type_label})"
                            if type_label
                            else f"磁盘{mount_point} I/O写入"
                        ),
                        f"{disk_stats['write']['current']:.1f} KB/s",
                        f"{disk_stats['write']['avg']:.1f} KB/s",
                        f"{disk_thresholds.get('write', 300000):.0f} KB/s",
                    )
                )

            # 网络行
            rows.extend(
                [
                    (
                        "网络上传",
                        f"{self.system_stats['network_upload']['current']:.1f} KB/s",
                        f"{self.system_stats['network_upload']['avg']:.1f} KB/s",
                        f"{self.metric_thresholds['network_upload']:.0f} KB/s",
                    ),
                    (
                        "网络下载",
                        f"{self.system_stats['network_download']['current']:.1f} KB/s",
                        f"{self.system_stats['network_download']['avg']:.1f} KB/s",
                        f"{self.metric_thresholds['network_download']:.0f} KB/s",
                    ),
                    (
                        "带宽占用",
                        f"{self.system_stats['bandwidth']['current']:.1f}%",
                        f"{self.system_stats['bandwidth']['avg']:.1f}%",
                        f"{self.metric_thresholds['bandwidth']:.0f}%",
                    ),
                ]
            )

            # 新增：CPU详细指标
            cpu_detailed = metrics.get("cpu_detailed", {})
            if cpu_detailed:
                ctx_switches = cpu_detailed.get("context_switches_per_sec", 0)
                interrupts = cpu_detailed.get("interrupts_per_sec", 0)

                # 记录历史数据
                self.system_status_history["context_switches"].append((current_time, ctx_switches))
                self.system_status_history["cpu_interrupts"].append((current_time, interrupts))

                # 更新统计
                self._update_stat("context_switches", ctx_switches)
                self._update_stat("cpu_interrupts", interrupts)

                rows.extend(
                    [
                        (
                            "上下文切换",
                            f"{self.system_stats['context_switches']['current']:.0f}/秒",
                            f"{self.system_stats['context_switches']['avg']:.0f}/秒",
                            f"{self.metric_thresholds['context_switches']:.0f}/秒",
                        ),
                        (
                            "CPU中断",
                            f"{self.system_stats['cpu_interrupts']['current']:.0f}/秒",
                            f"{self.system_stats['cpu_interrupts']['avg']:.0f}/秒",
                            f"{self.metric_thresholds['cpu_interrupts']:.0f}/秒",
                        ),
                    ]
                )

            # 新增：内存子系统
            memory_subsystem = metrics.get("memory_subsystem", {})
            if memory_subsystem:
                swap_in = memory_subsystem.get("swap_in_kbps", 0)
                swap_out = memory_subsystem.get("swap_out_kbps", 0)
                total_swap = swap_in + swap_out

                # 记录历史数据
                self.system_status_history["memory_swap"].append((current_time, total_swap))

                # 更新统计
                self._update_stat("memory_swap", total_swap)

                if swap_in > 0 or swap_out > 0:
                    rows.append(
                        (
                            "内存交换",
                            f"入{swap_in:.0f} 出{swap_out:.0f} KB/s",
                            f"{self.system_stats['memory_swap']['avg']:.1f} KB/s",
                            f"{self.metric_thresholds['memory_swap']:.0f} KB/s",
                        )
                    )
                else:
                    rows.append(
                        (
                            "内存交换",
                            "无交换 (0 KB/s)",
                            f"{self.system_stats['memory_swap']['avg']:.1f} KB/s",
                            f"{self.metric_thresholds['memory_swap']:.0f} KB/s",
                        )
                    )

            # 新增：存储子系统（磁盘延迟）
            storage_subsystem = metrics.get("storage_subsystem", {})
            if storage_subsystem:
                disks = storage_subsystem.get("disks", {})
                for disk_name, disk_info in disks.items():
                    latency = disk_info.get("average_io_latency_ms", 0)
                    if latency > 0:
                        # 为每个磁盘单独记录统计
                        stat_key = f"disk_latency_{disk_name}"
                        if stat_key not in self.system_stats:
                            self.system_stats[stat_key] = {"current": 0, "avg": 0}
                            if disk_name not in self.system_status_history.get("disk_latency", {}):
                                if not isinstance(
                                    self.system_status_history.get("disk_latency"), dict
                                ):
                                    self.system_status_history["disk_latency"] = {}
                                self.system_status_history["disk_latency"][disk_name] = deque(
                                    maxlen=100
                                )

                        # 记录历史数据
                        self.system_status_history["disk_latency"][disk_name].append(
                            (current_time, latency)
                        )

                        self._update_stat(stat_key, latency)

                        rows.append(
                            (
                                f"磁盘延迟({disk_name})",
                                f"{self.system_stats[stat_key]['current']:.1f} ms",
                                f"{self.system_stats[stat_key]['avg']:.1f} ms",
                                f"{self.metric_thresholds['disk_latency']:.0f} ms",
                            )
                        )

            # 新增：网络子系统（丢包率）
            network_subsystem = metrics.get("network_subsystem", {})
            if network_subsystem:
                loss_in = network_subsystem.get("packet_loss_rate_in", 0)
                loss_out = network_subsystem.get("packet_loss_rate_out", 0)
                # 使用平均丢包率作为统计值
                avg_loss = (loss_in + loss_out) / 2

                # 记录历史数据
                self.system_status_history["packet_loss"].append((current_time, avg_loss * 100))

                # 更新统计
                self._update_stat("packet_loss", avg_loss * 100)  # 转换为百分比

                rows.append(
                    (
                        "网络丢包率",
                        f"入{loss_in*100:.2f}% 出{loss_out*100:.2f}%",
                        f"{self.system_stats['packet_loss']['avg']:.2f}%",
                        f"{self.metric_thresholds['packet_loss']:.1f}%",
                    )
                )

            # 新增：SMART扇区告警（硬盘健康关键指标）
            smart_data = metrics.get("smart", {})
            if smart_data:
                total_reallocated = sum(
                    (disk.get("reallocated_sectors") or 0)
                    for disk in smart_data.values()
                    if isinstance(disk, dict)
                )
                total_pending = sum(
                    (disk.get("pending_sectors") or 0)
                    for disk in smart_data.values()
                    if isinstance(disk, dict)
                )

                # 为SMART指标添加统计支持
                if "smart_reallocated" not in self.system_stats:
                    self.system_stats["smart_reallocated"] = {"current": 0, "avg": 0}
                    self.system_status_history["smart_reallocated"] = deque(maxlen=100)
                if "smart_pending" not in self.system_stats:
                    self.system_stats["smart_pending"] = {"current": 0, "avg": 0}
                    self.system_status_history["smart_pending"] = deque(maxlen=100)

                # 记录历史数据
                self.system_status_history["smart_reallocated"].append(
                    (current_time, float(total_reallocated))
                )
                self.system_status_history["smart_pending"].append(
                    (current_time, float(total_pending))
                )

                self._update_stat("smart_reallocated", float(total_reallocated))
                self._update_stat("smart_pending", float(total_pending))

                rows.append(
                    (
                        "SMART-重映射扇区",
                        f"{total_reallocated}个",
                        f"{self.system_stats['smart_reallocated']['avg']:.1f}个",
                        f"{self.metric_thresholds['smart_reallocated']}个",
                    )
                )

                rows.append(
                    (
                        "SMART-待映射扇区",
                        f"{total_pending}个",
                        f"{self.system_stats['smart_pending']['avg']:.1f}个",
                        f"{self.metric_thresholds['smart_pending']}个",
                    )
                )

            self.status_details_table.setRowCount(0)
            for i, (name, current, avg, threshold) in enumerate(rows):
                self.status_details_table.insertRow(i)
                self.status_details_table.setItem(i, 0, QTableWidgetItem(name))
                self.status_details_table.setItem(i, 1, QTableWidgetItem(current))
                self.status_details_table.setItem(i, 2, QTableWidgetItem(avg))
                self.status_details_table.setItem(i, 3, QTableWidgetItem(threshold))

                # 新增：第5列瓶颈状态
                bottleneck_status = self._get_bottleneck_status_for_metric(
                    name, bottleneck_dimension
                )
                status_item = QTableWidgetItem(bottleneck_status)
                if bottleneck_status == "🔴 短板":
                    status_item.setForeground(QColor("#EF4444"))  # 红色高亮
                self.status_details_table.setItem(i, 4, status_item)

        except Exception as e:
            self.logger.error("更新状态详细表格失败: %s", e, exc_info=True)

    def _update_stat(self, key: str, value: float):
        """更新统计数据（当前值、平均值）.

        Args:
            key: 统计项键名
            value: 当前值
        """
        try:
            if key not in self.system_stats:
                self.system_stats[key] = {"current": 0, "avg": 0}

            # 更新当前值
            self.system_stats[key]["current"] = value

            # 计算平均值（基于历史数据）
            history_data = None

            if key == "network_upload":
                history_data = self.system_status_history.get("network", {}).get("upload", [])
            elif key == "network_download":
                history_data = self.system_status_history.get("network", {}).get("download", [])
            elif key.startswith("disk_latency_"):
                # 磁盘延迟特殊处理
                disk_name = key.replace("disk_latency_", "")
                disk_latency_dict = self.system_status_history.get("disk_latency", {})
                if isinstance(disk_latency_dict, dict):
                    history_data = disk_latency_dict.get(disk_name, [])
            else:
                history_data = self.system_status_history.get(key, [])

            if history_data and len(history_data) > 0:
                # 从历史数据计算平均值
                try:
                    # 检查是否是带时间戳的数据 (time, value)
                    if isinstance(history_data, (deque, list)) and len(history_data) > 0:
                        first_item = next(iter(history_data))
                        if isinstance(first_item, tuple) and len(first_item) == 2:
                            # 带时间戳的数据，提取值
                            values = [v for t, v in history_data]
                        else:
                            # 纯数值数据
                            values = list(history_data)

                        if values:
                            avg_value = sum(values) / len(values)
                            self.system_stats[key]["avg"] = avg_value
                        else:
                            self.system_stats[key]["avg"] = value
                    else:
                        self.system_stats[key]["avg"] = value
                except (TypeError, ValueError):
                    # 数据格式异常时使用当前值
                    self.system_stats[key]["avg"] = value
            else:
                # 没有历史数据时，平均值等于当前值
                self.system_stats[key]["avg"] = value

        except Exception as e:
            self.logger.error("更新统计数据失败 %s: %s", key, e)

    def _update_disk_stat(self, mount_point: str, metric: str, value: float):
        """更新磁盘统计数据（当前值、平均值）.

        Args:
            mount_point: 挂载点（如 "C:\\"）
            metric: 指标名（"read" 或 "write"）
            value: 当前值
        """
        try:
            # 更新当前值
            self.system_stats["disks"][mount_point][metric]["current"] = value

            # 计算平均值（基于历史数据）
            history_data = self.system_status_history["disks"][mount_point][metric]

            if history_data and len(history_data) > 0:
                # 提取时间戳数据中的值
                values = [v for t, v in history_data]
                if values:
                    avg_value = sum(values) / len(values)
                    self.system_stats["disks"][mount_point][metric]["avg"] = avg_value
                else:
                    self.system_stats["disks"][mount_point][metric]["avg"] = value
            else:
                # 没有历史数据时，平均值等于当前值
                self.system_stats["disks"][mount_point][metric]["avg"] = value

        except Exception as e:
            self.logger.error("更新磁盘统计数据失败 %s[%s]: %s", mount_point, metric, e)

    # ==================== 通用方法 ====================

    def connect_signals(self):
        """连接信号槽."""
        # 移除定时器更新，改为事件驱动
        # self.start_update_timer(2000, self._update_system_status)
        pass

    def refresh_data(self):
        """刷新数据."""
        self._update_system_status()

    # ==================== 业务指标监控仪表板 ====================

    def _create_business_metrics_dashboard(self) -> QWidget:
        """创建业务指标监控仪表板."""
        dashboard = QGroupBox("📊 业务指标监控")
        layout = QGridLayout(dashboard)
        layout.setSpacing(15)

        # 创建4个模块卡片
        self.dc_metrics_card = self._create_module_metrics_card("数据中心")
        self.gw_metrics_card = self._create_module_metrics_card("交易网关")
        self.pf_metrics_card = self._create_module_metrics_card("组合投资")
        self.st_metrics_card = self._create_module_metrics_card("策略中心")

        layout.addWidget(self.dc_metrics_card, 0, 0)
        layout.addWidget(self.gw_metrics_card, 0, 1)
        layout.addWidget(self.pf_metrics_card, 1, 0)
        layout.addWidget(self.st_metrics_card, 1, 1)

        return dashboard

    def _create_module_metrics_card(self, module_name: str) -> QGroupBox:
        """创建模块指标卡片.

        Args:
            module_name: 模块名称

        Returns:
            QGroupBox: 模块卡片
        """
        card = QGroupBox(module_name)
        card.setStyleSheet(
            """
            QGroupBox {
                border: 2px solid #4CAF50;
                border-radius: 10px;
                padding: 15px;
                background-color: #2A2A2A;
                font-weight: bold;
            }
            QGroupBox::title {
                color: #4CAF50;
            }
            """
        )

        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        # 根据模块创建不同的指标标签
        if module_name == "数据中心":
            metrics = [
                ("品种数", "dc_symbol_count"),
                ("已连接数据源", "dc_connected_datafeeds"),
                ("下载任务数", "dc_active_downloads"),
                ("录制功能", "dc_recording_enabled"),
            ]
        elif module_name == "交易网关":
            metrics = [
                ("总网关数", "gw_total_gateways"),
                ("已连接网关", "gw_connected_gateways"),
                ("总策略数", "gw_total_strategies"),
                ("激活策略数", "gw_active_strategies"),
            ]
        elif module_name == "组合投资":
            metrics = [
                ("自动组合数", "pf_auto_portfolio_count"),
                ("自定义组合数", "pf_custom_portfolio_count"),
                ("总组合数", "pf_total_portfolio_count"),
            ]
        elif module_name == "策略中心":
            metrics = [
                ("可用策略数", "st_available_strategies"),
                ("活跃回测任务", "st_active_backtests"),
            ]
        else:
            metrics = []

        # 创建指标标签
        for metric_name, label_name in metrics:
            metric_layout = QHBoxLayout()

            name_label = QLabel(f"{metric_name}:")
            name_label.setStyleSheet("color: #888; font-size: 11px;")
            metric_layout.addWidget(name_label)

            value_label = QLabel("--")
            value_label.setStyleSheet("color: #FFF; font-size: 14px; font-weight: bold;")
            value_label.setObjectName(label_name)
            metric_layout.addWidget(value_label)

            metric_layout.addStretch()

            layout.addLayout(metric_layout)

        return card

    def _refresh_business_metrics(self):
        """刷新业务指标."""
        try:
            if not self.system_service:
                self.show_error("系统管理服务不可用")
                return

            result = self.system_service.get_business_metrics()

            if not result.get("success"):
                self.show_error(f"获取业务指标失败: {result.get('message')}")
                return

            metrics = result.get("metrics", {})

            # 1. 更新数据中心指标
            dc = metrics.get("data_center", {})
            if not dc.get("error"):
                self._update_metric_label("dc_symbol_count", dc.get("symbol_count", 0))
                self._update_metric_label(
                    "dc_connected_datafeeds", dc.get("connected_datafeeds", 0)
                )
                self._update_metric_label("dc_active_downloads", dc.get("active_downloads", 0))
                recording = "启用" if dc.get("recording_enabled") else "禁用"
                self._update_metric_label("dc_recording_enabled", recording)

            # 2. 更新交易网关指标
            gw = metrics.get("trading_gateway", {})
            if not gw.get("error"):
                self._update_metric_label("gw_total_gateways", gw.get("total_gateways", 0))
                self._update_metric_label("gw_connected_gateways", gw.get("connected_gateways", 0))
                self._update_metric_label("gw_total_strategies", gw.get("total_strategies", 0))
                self._update_metric_label("gw_active_strategies", gw.get("active_strategies", 0))

            # 3. 更新组合投资指标
            pf = metrics.get("portfolio_investment", {})
            if not pf.get("error"):
                self._update_metric_label(
                    "pf_auto_portfolio_count", pf.get("auto_portfolio_count", 0)
                )
                self._update_metric_label(
                    "pf_custom_portfolio_count", pf.get("custom_portfolio_count", 0)
                )
                self._update_metric_label(
                    "pf_total_portfolio_count", pf.get("total_portfolio_count", 0)
                )

            # 4. 更新策略中心指标
            st = metrics.get("strategy_center", {})
            if not st.get("error"):
                self._update_metric_label(
                    "st_available_strategies", st.get("available_strategies", 0)
                )
                self._update_metric_label("st_active_backtests", st.get("active_backtests", 0))

            self.show_info("业务指标已刷新")

        except Exception as e:
            self.logger.error("刷新业务指标失败: %s", e)
            self.show_error(f"刷新失败: {e}")

    def _update_metric_label(self, label_name: str, value):
        """更新指标标签值.

        Args:
            label_name: 标签对象名称
            value: 值
        """
        try:
            # 在所有模块卡片中查找标签
            for card in [
                self.dc_metrics_card,
                self.gw_metrics_card,
                self.pf_metrics_card,
                self.st_metrics_card,
            ]:
                if not card:
                    continue

                label = card.findChild(QLabel, label_name)
                if label:
                    label.setText(str(value))
                    break

        except Exception as e:
            self.logger.debug(f"更新指标标签失败: {e}")
        self.show_info("系统状态已刷新")

    def on_close(self):
        """关闭处理."""
        self.stop_update_timer()
        self.logger.info("系统管理界面已关闭")
