# -*- coding: utf-8 -*-
"""
日志表格复选框委托：用于第0列复选框的无白底绘制。
设计目标：
- 未选中：透明背景，仅边框（跟随主题），避免白底突兀；
- 选中：主题色实心填充并绘制白色对勾；
- 居中显示，大小与常规指示器一致（16x16）。
"""

from PySide6.QtCore import Qt, QSize, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QStyledItemDelegate


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
            p2 = indicator_rect.topLeft() + QPoint(indicator_rect.width() // 2 - 1, indicator_rect.height() - 4)
            p3 = indicator_rect.topLeft() + QPoint(indicator_rect.width() - 4, 4)
            painter.drawLine(p1, p2)
            painter.drawLine(p2, p3)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # type: ignore[override]
        if index.column() == 0:
            return QSize(self.INDICATOR_SIZE, self.INDICATOR_SIZE)
        return super().sizeHint(option, index)


