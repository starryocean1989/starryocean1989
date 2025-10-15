# -*- coding: utf-8 -*-
"""
告警管理界面组件.

提供告警查看、确认、解决功能，支持实时告警推送和状态管理。
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QTimer, Signal, Qt
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QMessageBox,
    QInputDialog,
    QGroupBox,
    QCheckBox,
    QFrame,
    QSizePolicy,
)

from backend.core.utils import EVENT_ALERT_CREATED, EVENT_ALERT_UPDATED, AlertSeverity, AlertStatus


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
            acknowledge_btn.setStyleSheet("""
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
            """)
            button_layout.addWidget(acknowledge_btn)

            resolve_btn = QPushButton("解决")
            resolve_btn.clicked.connect(self._resolve_alert)
            resolve_btn.setStyleSheet("""
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
            """)
            button_layout.addWidget(resolve_btn)
        elif status == "acknowledged":
            # 已确认：解决按钮
            resolve_btn = QPushButton("解决")
            resolve_btn.clicked.connect(self._resolve_alert)
            resolve_btn.setStyleSheet("""
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
            """)
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
                return base_style + "QWidget { background-color: #ffebee; border-left: 4px solid #d32f2f; }"
            elif severity == "error":
                return base_style + "QWidget { background-color: #fff3e0; border-left: 4px solid #f57c00; }"
            else:
                return base_style + "QWidget { background-color: #e3f2fd; border-left: 4px solid #2196f3; }"
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
            self._call_alert_action("acknowledge", note if note else "")

    def _resolve_alert(self) -> None:
        """解决告警."""
        note, ok = QInputDialog.getText(self, "解决告警", "请输入解决备注（可选）:")
        if ok:
            self._call_alert_action("resolve", note if note else "")

    def _call_alert_action(self, action: str, note: str) -> None:
        """调用告警操作."""
        try:
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            system_service = service_manager.get_service("system_manager_service")

            if system_service:
                if action == "acknowledge":
                    result = system_service.acknowledge_alert(self.alert_id, note)
                elif action == "resolve":
                    result = system_service.resolve_alert(self.alert_id, note)

                if result.get("success"):
                    # 更新卡片样式
                    self.alert_data["status"] = "acknowledged" if action == "acknowledge" else "resolved"
                    self.setStyleSheet(self._get_card_style())

                    # 重新加载告警列表（直接调用父组件方法）
                    parent = self.parent()
                    while parent and not hasattr(parent, 'refresh_alerts'):
                        parent = parent.parent()
                    if parent and hasattr(parent, 'refresh_alerts'):
                        parent.refresh_alerts()
                else:
                    QMessageBox.warning(self, "错误", f"操作失败: {result.get('message')}")
            else:
                QMessageBox.warning(self, "错误", "系统管理服务不可用")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"操作失败: {str(e)}")


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

        # 启动定时器
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
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            system_service = service_manager.get_service("system_manager_service")

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
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            system_service = service_manager.get_service("system_manager_service")

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
            # 新告警创建
            self.add_alert(event_data)
        elif event_type == EVENT_ALERT_UPDATED:
            # 告警状态更新
            self.update_alert(event_data)

    def get_current_filters(self) -> Dict[str, Any]:
        """获取当前筛选条件."""
        return {
            "status": self.status_combo.currentText() if self.status_combo.currentText() != "全部" else None,
            "severity": self.severity_combo.currentText() if self.severity_combo.currentText() != "全部" else None,
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
