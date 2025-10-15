# -*- coding: utf-8 -*-
"""
告警滚动条组件.

在主窗口底部状态栏显示滚动告警信息，支持点击跳转到告警管理界面。
"""

from typing import Any, Dict, Optional

from PySide6.QtCore import QPropertyAnimation, QRect, QTimer, Signal, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import QLabel, QWidget

from backend.core.utils import EVENT_ALERT_CREATED


class AlertTicker(QWidget):
    """告警滚动条组件."""

    # 信号定义
    clicked = Signal()  # 点击信号

    def __init__(self, parent=None):
        """初始化告警滚动条."""
        super().__init__(parent)

        # 设置固定高度和背景色
        self.setFixedHeight(30)
        self.setStyleSheet("""
            QWidget {
                background-color: #dc3545;
                border-radius: 5px;
                margin: 2px;
            }
        """)

        # 告警信息
        self.current_alert: Optional[Dict[str, Any]] = None
        self.display_text = ""

        # 动画相关
        self.animation: Optional[QPropertyAnimation] = None
        self.slide_timer: Optional[QTimer] = None

        # 显示控制
        self.show_duration = 5000  # 显示5秒
        self.hide_timer: Optional[QTimer] = None

        # 字体设置
        self.font = QFont("Arial", 10, QFont.Weight.Bold)

        # 隐藏初始状态
        self.hide()

    def show_alert(self, alert_data: Dict[str, Any], duration: int = 5000) -> None:
        """显示告警信息.

        Args:
            alert_data: 告警数据
            duration: 显示时长（毫秒）
        """
        self.current_alert = alert_data
        self.show_duration = duration

        # 构建显示文本
        severity = alert_data.get("severity", "info").upper()
        message = alert_data.get("message", "")
        rule_name = alert_data.get("rule_name", "")

        self.display_text = f"⚠️ [{severity}] {message} (来源: {rule_name})"

        # 调整字体大小以适应宽度
        self._adjust_font_size()

        # 显示组件
        self.show()
        self.raise_()

        # 启动隐藏定时器
        self._start_hide_timer()

        # 启动滚动动画（如果文本过长）
        if self._needs_scrolling():
            self._start_scroll_animation()
        else:
            # 重置位置
            self.updateGeometry()

    def _adjust_font_size(self) -> None:
        """调整字体大小以适应组件宽度."""
        parent_width = self.parent().width() if self.parent() else 800

        # 计算可用宽度（留出边距）
        available_width = parent_width - 20

        # 尝试不同的字体大小
        for font_size in range(10, 7, -1):  # 从10到8递减
            test_font = QFont("Arial", font_size, QFont.Weight.Bold)
            font_metrics = self.fontMetrics()

            # 计算文本宽度
            text_width = font_metrics.boundingRect(self.display_text).width()

            if text_width <= available_width:
                self.font = test_font
                break

    def _needs_scrolling(self) -> None:
        """判断是否需要滚动动画."""
        if not self.display_text:
            return False

        # 计算文本宽度
        font_metrics = self.fontMetrics()
        text_width = font_metrics.boundingRect(self.display_text).width()

        # 如果文本宽度超过组件宽度，需要滚动
        return text_width > self.width()

    def _start_scroll_animation(self) -> None:
        """启动滚动动画."""
        if self.animation:
            self.animation.stop()

        # 计算滚动距离
        font_metrics = self.fontMetrics()
        text_width = font_metrics.boundingRect(self.display_text).width()
        scroll_distance = text_width - self.width() + 20  # 额外滚动一点

        if scroll_distance <= 0:
            return

        # 创建滚动动画
        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(3000)  # 3秒完成一次滚动
        self.animation.setStartValue(self.pos())
        self.animation.setEndValue(self.pos() + QPoint(-scroll_distance, 0))
        self.animation.setLoopCount(-1)  # 无限循环

        self.animation.start()

    def _start_hide_timer(self) -> None:
        """启动隐藏定时器."""
        if self.hide_timer:
            self.hide_timer.stop()

        self.hide_timer = QTimer()
        self.hide_timer.timeout.connect(self.hide)
        self.hide_timer.start(self.show_duration)

    def hide(self) -> None:
        """隐藏组件."""
        super().hide()

        # 停止所有动画和定时器
        if self.animation:
            self.animation.stop()

        if self.slide_timer:
            self.slide_timer.stop()

        if self.hide_timer:
            self.hide_timer.stop()

        # 清空当前告警
        self.current_alert = None

    def mousePressEvent(self, event) -> None:
        """鼠标点击事件."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event) -> None:
        """绘制事件."""
        if not self.display_text:
            return

        painter = QPainter(self)
        painter.setFont(self.font)

        # 设置文字颜色
        painter.setPen(QColor(255, 255, 255))

        # 绘制文字
        rect = self.rect()
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.display_text)

    def resizeEvent(self, event) -> None:
        """大小改变事件."""
        super().resizeEvent(event)

        # 重新判断是否需要滚动
        if self._needs_scrolling() and self.isVisible():
            self._start_scroll_animation()
        else:
            # 停止滚动动画
            if self.animation:
                self.animation.stop()

    def get_alert_data(self) -> Optional[Dict[str, Any]]:
        """获取当前显示的告警数据.

        Returns:
            告警数据或None
        """
        return self.current_alert

    def set_display_duration(self, duration_ms: int) -> None:
        """设置显示时长.

        Args:
            duration_ms: 显示时长（毫秒）
        """
        self.show_duration = duration_ms
