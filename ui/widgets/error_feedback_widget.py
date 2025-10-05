# -*- coding: utf-8 -*-
"""
错误反馈组件 - 提供用户友好的错误反馈界面
"""

import logging
from typing import Dict, Any, Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QScrollArea, QFrame, QProgressBar, QCheckBox,
    QGroupBox, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QToolButton, QMenu
)
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QPixmap, QFont, QColor, QPalette

try:
    from ...utils.error_handler import error_handler, ErrorCategory, ErrorSeverity, ErrorInfo
except ImportError:
    try:
        from utils.error_handler import error_handler, ErrorCategory, ErrorSeverity, ErrorInfo
    except ImportError:
        class ErrorCategory:
            UI = "ui"
            SYSTEM = "system"
            NETWORK = "network"
            DATA = "data"
            VNPY = "vnpy"
            UNKNOWN = "unknown"

        class ErrorSeverity:
            LOW = "low"
            MEDIUM = "medium"
            HIGH = "high"
            CRITICAL = "critical"

        class ErrorInfo:
            def __init__(self, error_id, message, category=None, severity=None, timestamp=None):
                self.error_id = error_id
                self.message = message
                self.category = category or ErrorCategory.UNKNOWN
                self.severity = severity or ErrorSeverity.MEDIUM
                self.timestamp = timestamp

        class MockErrorHandler:
            def handle_error(self, error_id, message, category=None, severity=None, max_retries=1, callback=None, parent_widget=None):
                print(f"错误 {error_id}: {message}")
                return False

        error_handler = MockErrorHandler()


class ErrorNotificationWidget(QFrame):
    """错误通知组件"""

    # 信号定义
    notification_clicked = Signal(str)  # error_id
    retry_requested = Signal(str)     # error_id
    suppress_requested = Signal(str)  # error_id

    def __init__(self, error_info: ErrorInfo, parent=None):
        super().__init__(parent)
        self.error_info = error_info
        self.setup_ui()
        self.setup_animation()

    def setup_ui(self):
        """设置界面"""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setLineWidth(1)

        # 根据严重程度设置样式
        if self.error_info.severity == ErrorSeverity.CRITICAL:
            self.setStyleSheet("""
                QFrame {
                    background-color: #ffebee;
                    border: 2px solid #f44336;
                    border-radius: 8px;
                }
            """)
        elif self.error_info.severity == ErrorSeverity.HIGH:
            self.setStyleSheet("""
                QFrame {
                    background-color: #fff3e0;
                    border: 1px solid #ff9800;
                    border-radius: 6px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: #f5f5f5;
                    border: 1px solid #9e9e9e;
                    border-radius: 4px;
                }
            """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 标题行
        title_layout = QHBoxLayout()

        # 错误图标
        icon_label = QLabel()
        if self.error_info.severity == ErrorSeverity.CRITICAL:
            icon_label.setText("🚨")
        elif self.error_info.severity == ErrorSeverity.HIGH:
            icon_label.setText("⚠️")
        else:
            icon_label.setText("ℹ️")
        icon_label.setFixedSize(24, 24)
        title_layout.addWidget(icon_label)

        # 错误标题
        title_label = QLabel(f"{self.error_info.error_id}")
        title_font = QFont()
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_layout.addWidget(title_label)

        # 严重程度标签
        severity_label = QLabel(self.error_info.severity.value.upper())
        severity_label.setStyleSheet("""
            QLabel {
                background-color: #e0e0e0;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
            }
        """)
        title_layout.addWidget(severity_label)

        title_layout.addStretch()

        # 关闭按钮
        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ffcdd2;
                border-radius: 10px;
            }
        """)
        close_btn.clicked.connect(self.close)
        title_layout.addWidget(close_btn)

        layout.addLayout(title_layout)

        # 错误消息
        message_label = QLabel(self.error_info.message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("color: #424242; margin: 4px 0;")
        layout.addWidget(message_label)

        # 操作按钮
        if self.error_info.retry_count < self.error_info.max_retries:
            button_layout = QHBoxLayout()

            retry_btn = QPushButton("重试")
            retry_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196f3;
                    color: white;
                    border: none;
                    padding: 4px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #1976d2;
                }
            """)
            retry_btn.clicked.connect(lambda: self.retry_requested.emit(self.error_info.error_id))
            button_layout.addWidget(retry_btn)

            suppress_btn = QPushButton("忽略")
            suppress_btn.setStyleSheet("""
                QPushButton {
                    background-color: #9e9e9e;
                    color: white;
                    border: none;
                    padding: 4px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #757575;
                }
            """)
            suppress_btn.clicked.connect(lambda: self.suppress_requested.emit(self.error_info.error_id))
            button_layout.addWidget(suppress_btn)

            button_layout.addStretch()
            layout.addLayout(button_layout)

        # 点击事件
        self.mousePressEvent = lambda event: self.notification_clicked.emit(self.error_info.error_id)

    def setup_animation(self):
        """设置动画效果"""
        self.animation = QPropertyAnimation(self, b"opacity")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.finished.connect(self.show)

    def show_with_animation(self):
        """带动画显示"""
        self.setWindowOpacity(0)
        self.show()
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()


class ErrorFeedbackWidget(QWidget):
    """错误反馈主组件"""

    # 信号定义
    error_selected = Signal(str)  # error_id
    retry_all_requested = Signal()
    clear_all_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._logger = logging.getLogger(self.__class__.__name__)
        self.notification_widgets: Dict[str, ErrorNotificationWidget] = {}
        self.setup_ui()
        self.connect_signals()
        self.start_update_timer()

    def setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)

        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # 左侧：错误通知区域
        self.notification_area = QScrollArea()
        self.notification_area.setWidgetResizable(True)
        self.notification_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.notification_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarNever)

        self.notification_container = QWidget()
        self.notification_layout = QVBoxLayout(self.notification_container)
        self.notification_layout.setContentsMargins(0, 0, 0, 0)
        self.notification_layout.addStretch()

        self.notification_area.setWidget(self.notification_container)
        splitter.addWidget(self.notification_area)

        # 右侧：错误详情和统计
        self.detail_widget = self.create_detail_widget()
        splitter.addWidget(self.detail_widget)

        # 设置分割器比例
        splitter.setSizes([400, 300])

        # 底部：控制按钮
        control_layout = QHBoxLayout()

        self.retry_all_btn = QPushButton("重试所有")
        self.retry_all_btn.clicked.connect(self.retry_all_requested.emit)
        control_layout.addWidget(self.retry_all_btn)

        self.clear_all_btn = QPushButton("清除所有")
        self.clear_all_btn.clicked.connect(self.clear_all_requested.emit)
        control_layout.addWidget(self.clear_all_btn)

        self.auto_retry_checkbox = QCheckBox("自动重试")
        self.auto_retry_checkbox.setChecked(True)
        control_layout.addWidget(self.auto_retry_checkbox)

        control_layout.addStretch()

        # 状态标签
        self.status_label = QLabel("就绪")
        control_layout.addWidget(self.status_label)

        layout.addLayout(control_layout)

    def create_detail_widget(self) -> QWidget:
        """创建详情组件"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 创建选项卡
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)

        # 错误统计选项卡
        stats_tab = self.create_stats_tab()
        tab_widget.addTab(stats_tab, "统计信息")

        # 错误列表选项卡
        errors_tab = self.create_errors_tab()
        tab_widget.addTab(errors_tab, "错误列表")

        # 系统状态选项卡
        system_tab = self.create_system_tab()
        tab_widget.addTab(system_tab, "系统状态")

        return widget

    def create_stats_tab(self) -> QWidget:
        """创建统计选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 错误统计表格
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(2)
        self.stats_table.setHorizontalHeaderLabels(["类别", "数量"])
        self.stats_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.stats_table)

        # 进度条显示
        self.progress_group = QGroupBox("处理进度")
        progress_layout = QVBoxLayout(self.progress_group)

        self.retry_progress = QProgressBar()
        self.retry_progress.setVisible(False)
        progress_layout.addWidget(QLabel("重试进度:"))
        progress_layout.addWidget(self.retry_progress)

        layout.addWidget(self.progress_group)

        return widget

    def create_errors_tab(self) -> QWidget:
        """创建错误列表选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 错误列表表格
        self.errors_table = QTableWidget()
        self.errors_table.setColumnCount(5)
        self.errors_table.setHorizontalHeaderLabels([
            "时间", "错误ID", "类别", "严重程度", "消息"
        ])

        # 设置列宽
        header = self.errors_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        self.errors_table.setColumnWidth(0, 120)
        self.errors_table.setColumnWidth(1, 150)
        self.errors_table.setColumnWidth(2, 80)
        self.errors_table.setColumnWidth(3, 80)

        layout.addWidget(self.errors_table)

        return widget

    def create_system_tab(self) -> QWidget:
        """创建系统状态选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 系统状态信息
        self.system_info_text = QTextEdit()
        self.system_info_text.setReadOnly(True)
        self.system_info_text.setMaximumHeight(200)
        layout.addWidget(QLabel("系统状态:"))
        layout.addWidget(self.system_info_text)

        # 错误处理器状态
        self.error_handler_info_text = QTextEdit()
        self.error_handler_info_text.setReadOnly(True)
        self.error_handler_info_text.setMaximumHeight(200)
        layout.addWidget(QLabel("错误处理器状态:"))
        layout.addWidget(self.error_handler_info_text)

        return widget

    def connect_signals(self):
        """连接信号"""
        # 连接错误处理器信号
        error_handler.error_occurred.connect(self.on_error_occurred)
        error_handler.error_resolved.connect(self.on_error_resolved)
        error_handler.retry_scheduled.connect(self.on_retry_scheduled)

    def start_update_timer(self):
        """启动更新定时器"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(1000)  # 每秒更新一次

    def on_error_occurred(self, error_info: ErrorInfo):
        """错误发生回调"""
        self.logger.info(f"收到错误: {error_info.error_id}")

        # 创建通知组件
        notification = ErrorNotificationWidget(error_info)
        notification.notification_clicked.connect(self.error_selected.emit)
        notification.retry_requested.connect(self.on_retry_requested)
        notification.suppress_requested.connect(self.on_suppress_requested)

        # 添加到通知区域
        self.notification_widgets[error_info.error_id] = notification
        self.notification_layout.insertWidget(0, notification)

        # 显示动画
        notification.show_with_animation()

        # 更新错误列表
        self.add_error_to_table(error_info)

    def on_error_resolved(self, error_id: str):
        """错误解决回调"""
        self.logger.info(f"错误已解决: {error_id}")

        # 移除通知组件
        if error_id in self.notification_widgets:
            notification = self.notification_widgets[error_id]
            notification.deleteLater()
            del self.notification_widgets[error_id]

    def on_retry_scheduled(self, error_id: str, delay: float):
        """重试计划回调"""
        self.logger.info(f"错误 {error_id} 将在 {delay:.1f} 秒后重试")
        self.status_label.setText(f"重试计划: {error_id} ({delay:.1f}s)")

    def on_retry_requested(self, error_id: str):
        """重试请求回调"""
        self.logger.info(f"用户请求重试: {error_id}")
        error_handler.resolve_error(error_id)

    def on_suppress_requested(self, error_id: str):
        """抑制请求回调"""
        self.logger.info(f"用户请求抑制: {error_id}")
        error_handler.suppressor.clear_suppression(error_id)

    def add_error_to_table(self, error_info: ErrorInfo):
        """添加错误到表格"""
        row = self.errors_table.rowCount()
        self.errors_table.insertRow(row)

        # 时间
        import datetime
        time_str = datetime.datetime.fromtimestamp(error_info.timestamp).strftime("%H:%M:%S")
        self.errors_table.setItem(row, 0, QTableWidgetItem(time_str))

        # 错误ID
        self.errors_table.setItem(row, 1, QTableWidgetItem(error_info.error_id))

        # 类别
        self.errors_table.setItem(row, 2, QTableWidgetItem(error_info.category.value))

        # 严重程度
        severity_item = QTableWidgetItem(error_info.severity.value)
        if error_info.severity == ErrorSeverity.CRITICAL:
            severity_item.setBackground(QColor("#ffcdd2"))
        elif error_info.severity == ErrorSeverity.HIGH:
            severity_item.setBackground(QColor("#ffe0b2"))
        self.errors_table.setItem(row, 3, severity_item)

        # 消息
        self.errors_table.setItem(row, 4, QTableWidgetItem(error_info.message))

        # 滚动到最新行
        self.errors_table.scrollToBottom()

    def update_display(self):
        """更新显示"""
        # 更新统计信息
        self.update_stats_table()

        # 更新系统状态
        self.update_system_info()

    def update_stats_table(self):
        """更新统计表格"""
        status = error_handler.get_error_status()

        # 清空表格
        self.stats_table.setRowCount(0)

        # 添加错误类别统计
        for category, count in status.get('error_categories', {}).items():
            if count > 0:
                row = self.stats_table.rowCount()
                self.stats_table.insertRow(row)
                self.stats_table.setItem(row, 0, QTableWidgetItem(category))
                self.stats_table.setItem(row, 1, QTableWidgetItem(str(count)))

        # 添加严重程度统计
        for severity, count in status.get('error_severities', {}).items():
            if count > 0:
                row = self.stats_table.rowCount()
                self.stats_table.insertRow(row)
                self.stats_table.setItem(row, 0, QTableWidgetItem(f"严重程度: {severity}"))
                self.stats_table.setItem(row, 1, QTableWidgetItem(str(count)))

    def update_system_info(self):
        """更新系统信息"""
        status = error_handler.get_error_status()

        system_info = f"""
活跃错误: {status.get('active_errors', 0)}
抑制错误: {status.get('suppressed_errors', 0)}
熔断器: {status.get('circuit_breakers', 0)}
        """.strip()

        self.system_info_text.setPlainText(system_info)

        # 更新错误处理器状态
        error_handler_info = f"""
错误处理器状态正常
最后更新: {time.strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()

        self.error_handler_info_text.setPlainText(error_handler_info)

    def retry_all_errors(self):
        """重试所有错误"""
        for error_id in list(self.notification_widgets.keys()):
            error_handler.resolve_error(error_id)

    def clear_all_errors(self):
        """清除所有错误"""
        for notification in list(self.notification_widgets.values()):
            notification.deleteLater()
        self.notification_widgets.clear()

        # 清空错误列表
        self.errors_table.setRowCount(0)

        # 清除错误处理器状态
        error_handler.suppressor.clear_suppression()

    def closeEvent(self, event):
        """关闭事件"""
        if self.update_timer:
            self.update_timer.stop()
        super().closeEvent(event)
