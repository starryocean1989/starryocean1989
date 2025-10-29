# -*- coding: utf-8 -*-
"""
增强状态栏组件.

提供更丰富的状态信息展示：
- 左侧：当前操作状态
- 中间：后台任务指示器
- 中间-右：告警汇总
- 右侧：系统资源监控

作者：系统重构团队
日期：2025-10-27
"""

from typing import Dict, List

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vnpy.event import Event, EventEngine

from backend.infrastructure.system_vnpy.unified_log_system import (
    EVENT_LOG_ALERT,
    EVENT_LOG_NOTIFICATION,
    EVENT_LOG_PROGRESS,
    EVENT_UI_STATUSBAR,
)


# =============================================================================
# 后台任务指示器
# =============================================================================


class BackgroundTaskIndicator(QWidget):
    """后台任务指示器.

    显示当前运行的后台任务，如"下载中×2"、"扫描中×1"。
    """

    clicked = Signal()

    def __init__(self):
        """初始化任务指示器."""
        super().__init__()

        # 任务计数
        self.tasks: Dict[str, int] = {}  # {task_type: count}

        self.setup_ui()

    def setup_ui(self):
        """设置UI."""
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 0, 2, 0)

        self.label = QLabel("无任务")
        self.label.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(self.label)

        self.setLayout(layout)

        # 点击展开任务列表
        self.label.mousePressEvent = lambda e: self.clicked.emit()

    def add_task(self, task_type: str):
        """添加任务.

        Args:
            task_type: 任务类型（如"下载"、"扫描"）
        """
        self.tasks[task_type] = self.tasks.get(task_type, 0) + 1
        self._update_display()

    def remove_task(self, task_type: str):
        """移除任务.

        Args:
            task_type: 任务类型
        """
        if task_type in self.tasks:
            self.tasks[task_type] -= 1
            if self.tasks[task_type] <= 0:
                del self.tasks[task_type]
        self._update_display()

    def _update_display(self):
        """更新显示."""
        if not self.tasks:
            self.label.setText("无任务")
            self.label.setStyleSheet("color: #999; font-size: 11px;")
        else:
            # 显示任务汇总
            task_texts = [f"{k}×{v}" for k, v in self.tasks.items()]
            text = " | ".join(task_texts)
            self.label.setText(f"🔄 {text}")
            self.label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")

    def get_task_count(self) -> int:
        """获取任务总数.

        Returns:
            任务总数
        """
        return sum(self.tasks.values())


# =============================================================================
# 告警汇总组件
# =============================================================================


class AlertSummaryWidget(QWidget):
    """告警汇总组件.

    显示未处理告警数量，点击展开告警列表。
    """

    clicked = Signal()

    def __init__(self):
        """初始化告警汇总."""
        super().__init__()

        # 告警列表（去重：相同rule_id只保留最新的）
        self.alerts: List[Dict] = []
        self.alert_rules: Dict[str, Dict] = {}  # {rule_id: alert_data}

        self.setup_ui()

    def setup_ui(self):
        """设置UI."""
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 0, 2, 0)

        self.icon_label = QLabel("")
        self.icon_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.icon_label)

        self.count_label = QLabel("0")
        self.count_label.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(self.count_label)

        self.setLayout(layout)

        # 初始隐藏
        self.setVisible(False)

        # 点击展开告警列表
        self.icon_label.mousePressEvent = lambda e: self.clicked.emit()
        self.count_label.mousePressEvent = lambda e: self.clicked.emit()

    def add_alert(self, alert_data: Dict):
        """添加告警.

        Args:
            alert_data: 告警数据字典
        """
        # 去重：相同rule_id的告警只保留最新的
        rule_id = alert_data.get("rule_id", alert_data.get("module", "unknown"))

        if rule_id in self.alert_rules:
            # 移除旧告警
            old_alert = self.alert_rules[rule_id]
            if old_alert in self.alerts:
                self.alerts.remove(old_alert)

        # 添加新告警
        self.alert_rules[rule_id] = alert_data
        self.alerts.append(alert_data)

        self._update_display()

    def remove_alert(self, rule_id: str):
        """移除告警.

        Args:
            rule_id: 规则ID
        """
        if rule_id in self.alert_rules:
            alert = self.alert_rules[rule_id]
            if alert in self.alerts:
                self.alerts.remove(alert)
            del self.alert_rules[rule_id]

        self._update_display()

    def clear_all(self):
        """清空所有告警."""
        self.alerts.clear()
        self.alert_rules.clear()
        self._update_display()

    def _update_display(self):
        """更新显示."""
        count = len(self.alerts)

        if count == 0:
            self.setVisible(False)
        else:
            self.setVisible(True)

            # 更新图标（按最高严重级别）
            highest_level = self._get_highest_level()
            if highest_level == "CRITICAL":
                self.icon_label.setText("🔴")
                self.count_label.setStyleSheet(
                    "color: #F44336; font-size: 11px; font-weight: bold;"
                )
            elif highest_level == "ERROR":
                self.icon_label.setText("🟠")
                self.count_label.setStyleSheet(
                    "color: #FF9800; font-size: 11px; font-weight: bold;"
                )
            else:
                self.icon_label.setText("⚠️")
                self.count_label.setStyleSheet(
                    "color: #FFC107; font-size: 11px; font-weight: bold;"
                )

            self.count_label.setText(str(count))

    def _get_highest_level(self) -> str:
        """获取最高严重级别.

        Returns:
            级别名称
        """
        level_priority = {
            "CRITICAL": 3,
            "ERROR": 2,
            "WARNING": 1,
        }

        highest = "WARNING"
        highest_priority = 0

        for alert in self.alerts:
            level = alert.get("level", "WARNING")
            priority = level_priority.get(level, 0)
            if priority > highest_priority:
                highest_priority = priority
                highest = level

        return highest

    def get_alerts(self) -> List[Dict]:
        """获取所有告警.

        Returns:
            告警列表
        """
        return self.alerts.copy()


# =============================================================================
# 告警列表对话框
# =============================================================================


class AlertListDialog(QDialog):
    """告警列表对话框."""

    def __init__(self, alerts: List[Dict], parent=None):
        """初始化对话框.

        Args:
            alerts: 告警列表
            parent: 父窗口
        """
        super().__init__(parent)
        self.alerts = alerts

        self.setWindowTitle("告警列表")
        self.resize(600, 400)

        self.setup_ui()

    def setup_ui(self):
        """设置UI."""
        layout = QVBoxLayout()

        # 标题
        title_label = QLabel(f"当前有 {len(self.alerts)} 个未处理告警")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)

        # 告警列表
        self.list_widget = QListWidget()
        for alert in self.alerts:
            level = alert.get("level", "WARNING")
            message = alert.get("message", "")
            timestamp = alert.get("timestamp", "")

            # 图标
            icon_map = {
                "CRITICAL": "🔴",
                "ERROR": "🟠",
                "WARNING": "⚠️",
            }
            icon = icon_map.get(level, "⚠️")

            item_text = f"{icon} [{level}] {message}\n    时间: {timestamp[:19]}"
            item = QListWidgetItem(item_text)
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        clear_btn = QPushButton("清空全部")
        clear_btn.clicked.connect(self.accept)
        button_layout.addWidget(clear_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)


# =============================================================================
# 增强状态栏主组件
# =============================================================================


class EnhancedStatusBar(QWidget):
    """增强状态栏.

    布局：[操作状态] [后台任务×2] | [告警×3] | [CPU/内存]
    """

    def __init__(self, event_engine: EventEngine):
        """初始化增强状态栏.

        Args:
            event_engine: VNPY事件引擎
        """
        super().__init__()

        self.event_engine = event_engine

        self.setup_ui()
        self.connect_events()

        # 启动资源监控定时器
        self.resource_timer = QTimer()
        self.resource_timer.timeout.connect(self._update_resources)
        self.resource_timer.start(5000)  # 每5秒更新

    def setup_ui(self):
        """设置UI."""
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(10)

        # 左侧：操作状态
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.status_label, 2)

        # 中间：后台任务指示器
        self.task_indicator = BackgroundTaskIndicator()
        self.task_indicator.clicked.connect(self._on_task_indicator_clicked)
        layout.addWidget(self.task_indicator, 1)

        # 分隔符
        separator1 = QLabel("|")
        separator1.setStyleSheet("color: #666;")
        layout.addWidget(separator1)

        # 中间-右：告警汇总
        self.alert_summary = AlertSummaryWidget()
        self.alert_summary.clicked.connect(self._on_alert_summary_clicked)
        layout.addWidget(self.alert_summary, 1)

        # 分隔符
        separator2 = QLabel("|")
        separator2.setStyleSheet("color: #666;")
        layout.addWidget(separator2)

        # 右侧：系统资源
        self.resource_label = QLabel("CPU: --% | 内存: --%")
        self.resource_label.setStyleSheet("font-size: 11px; color: #999;")
        layout.addWidget(self.resource_label, 1)

        self.setLayout(layout)

    def connect_events(self):
        """订阅LoggingHub事件."""
        self.event_engine.register(EVENT_UI_STATUSBAR, self.on_status_update)
        self.event_engine.register(EVENT_LOG_PROGRESS, self.on_progress)
        self.event_engine.register(EVENT_LOG_ALERT, self.on_alert)
        self.event_engine.register(EVENT_LOG_NOTIFICATION, self.on_notification)

    def on_status_update(self, event: Event):
        """处理状态更新事件.

        Args:
            event: 事件对象
        """
        try:
            data = event.data
            message = data.get("message", "")
            self.status_label.setText(message)
        except Exception:
            pass

    def on_progress(self, event: Event):
        """处理进度事件.

        Args:
            event: 事件对象
        """
        try:
            data = event.data
            message = data.get("message", "")
            details = data.get("details", {})

            # 判断任务类型
            if "下载" in message or "download" in message.lower():
                task_type = "下载"
            elif "扫描" in message or "scan" in message.lower():
                task_type = "扫描"
            else:
                task_type = "任务"

            # 检查是否完成
            progress = details.get("progress", 0) if details else 0
            if progress >= 100:
                self.task_indicator.remove_task(task_type)
            elif progress > 0:
                # 进度>0表示任务进行中
                if self.task_indicator.tasks.get(task_type, 0) == 0:
                    self.task_indicator.add_task(task_type)

            # 更新状态标签
            self.status_label.setText(message)
        except Exception:
            pass

    def on_alert(self, event: Event):
        """处理告警事件.

        Args:
            event: 事件对象
        """
        try:
            data = event.data
            self.alert_summary.add_alert(data)
        except Exception:
            pass

    def on_notification(self, event: Event):
        """处理通知事件.

        Args:
            event: 事件对象
        """
        try:
            data = event.data
            message = data.get("message", "")
            self.status_label.setText(message)

            # 任务完成通知，移除对应的任务指示
            if "完成" in message or "success" in message.lower():
                # 尝试移除所有可能的任务类型
                for task_type in ["下载", "扫描", "任务"]:
                    if task_type in message:
                        self.task_indicator.remove_task(task_type)
        except Exception:
            pass

    def _update_resources(self):
        """更新系统资源信息."""
        if not HAS_PSUTIL:
            self.resource_label.setText("系统监控不可用")
            return

        try:
            cpu_percent = float(psutil.cpu_percent(interval=0.1))
            memory = psutil.virtual_memory()
            memory_percent = float(memory.percent)

            # 根据使用率调整颜色
            if cpu_percent > 80.0 or memory_percent > 80.0:
                color = "#F44336"  # 红色
            elif cpu_percent > 60.0 or memory_percent > 60.0:
                color = "#FF9800"  # 橙色
            else:
                color = "#4CAF50"  # 绿色

            text = f"CPU: {cpu_percent:.1f}% | 内存: {memory_percent:.1f}%"
            self.resource_label.setText(text)
            self.resource_label.setStyleSheet(
                f"font-size: 11px; color: {color}; font-weight: bold;"
            )
        except Exception:
            self.resource_label.setText("资源监控异常")

    def _on_task_indicator_clicked(self):
        """任务指示器点击事件."""
        # TODO: 显示任务详情对话框
        # 当前版本暂不实现

    def _on_alert_summary_clicked(self):
        """告警汇总点击事件."""
        alerts = self.alert_summary.get_alerts()
        if alerts:
            dialog = AlertListDialog(alerts, parent=self)
            if dialog.exec():
                # 用户点击"清空全部"
                self.alert_summary.clear_all()


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    "EnhancedStatusBar",
    "BackgroundTaskIndicator",
    "AlertSummaryWidget",
    "AlertListDialog",
]
