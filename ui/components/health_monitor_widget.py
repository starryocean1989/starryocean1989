# -*- coding: utf-8 -*-
"""健康监控UI组件."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Dict, Any

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QProgressBar, QFrame,
    QScrollArea, QGridLayout, QTabWidget, QSplitter
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QPalette, QColor

from backend.startup.health import get_health_dashboard_data, get_system_health_status


class HealthStatusWidget(QWidget):
    """健康状态显示组件."""
    
    status_updated = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.setup_timer()
    
    def init_ui(self):
        """初始化UI."""
        layout = QVBoxLayout(self)
        
        # 标题
        title_label = QLabel("系统健康监控")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # 概览页
        self.overview_widget = self._create_overview_widget()
        self.tab_widget.addTab(self.overview_widget, "概览")
        
        # 详细状态页
        self.details_widget = self._create_details_widget()
        self.tab_widget.addTab(self.details_widget, "详细状态")
        
        # 事件历史页
        self.events_widget = self._create_events_widget()
        self.tab_widget.addTab(self.events_widget, "事件历史")
        
        # 恢复记录页
        self.recovery_widget = self._create_recovery_widget()
        self.tab_widget.addTab(self.recovery_widget, "恢复记录")
    
    def _create_overview_widget(self) -> QWidget:
        """创建概览组件."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 健康状态指示器
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.Box)
        status_layout = QHBoxLayout(status_frame)
        
        self.health_percentage_label = QLabel("健康度: --%")
        self.health_percentage_label.setFont(QFont("Arial", 12, QFont.Bold))
        status_layout.addWidget(self.health_percentage_label)
        
        self.health_progress = QProgressBar()
        self.health_progress.setRange(0, 100)
        self.health_progress.setTextVisible(True)
        status_layout.addWidget(self.health_progress)
        
        self.overall_status_label = QLabel("状态: 未知")
        self.overall_status_label.setFont(QFont("Arial", 12))
        status_layout.addWidget(self.overall_status_label)
        
        layout.addWidget(status_frame)
        
        # 进程状态网格
        processes_label = QLabel("进程状态")
        processes_label.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(processes_label)
        
        self.processes_grid = QGridLayout()
        layout.addLayout(self.processes_grid)
        
        # 系统资源状态
        resources_label = QLabel("系统资源")
        resources_label.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(resources_label)
        
        self.resources_text = QTextEdit()
        self.resources_text.setMaximumHeight(120)
        self.resources_text.setReadOnly(True)
        layout.addWidget(self.resources_text)
        
        # 刷新按钮
        refresh_layout = QHBoxLayout()
        self.refresh_button = QPushButton("立即刷新")
        self.refresh_button.clicked.connect(self.refresh_status)
        refresh_layout.addWidget(self.refresh_button)
        
        refresh_layout.addStretch()
        
        self.auto_refresh_checkbox = QPushButton("自动刷新: 开启")
        self.auto_refresh_checkbox.setCheckable(True)
        self.auto_refresh_checkbox.setChecked(True)
        self.auto_refresh_checkbox.clicked.connect(self.toggle_auto_refresh)
        refresh_layout.addWidget(self.auto_refresh_checkbox)
        
        layout.addLayout(refresh_layout)
        
        return widget
    
    def _create_details_widget(self) -> QWidget:
        """创建详细状态组件."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 详细状态文本
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.details_text)
        
        return widget
    
    def _create_events_widget(self) -> QWidget:
        """创建事件历史组件."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 事件列表
        self.events_text = QTextEdit()
        self.events_text.setReadOnly(True)
        self.events_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.events_text)
        
        return widget
    
    def _create_recovery_widget(self) -> QWidget:
        """创建恢复记录组件."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 恢复记录列表
        self.recovery_text = QTextEdit()
        self.recovery_text.setReadOnly(True)
        self.recovery_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.recovery_text)
        
        return widget
    
    def setup_timer(self):
        """设置定时器."""
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(5000)  # 5秒刷新一次
        
        # 状态更新信号连接
        self.status_updated.connect(self.update_ui)
    
    def toggle_auto_refresh(self):
        """切换自动刷新."""
        if self.auto_refresh_checkbox.isChecked():
            self.timer.start(5000)
            self.auto_refresh_checkbox.setText("自动刷新: 开启")
        else:
            self.timer.stop()
            self.auto_refresh_checkbox.setText("自动刷新: 关闭")
    
    def refresh_status(self):
        """刷新健康状态."""
        # 在后台线程中获取数据
        asyncio.create_task(self._fetch_health_data())
    
    async def _fetch_health_data(self):
        """获取健康数据."""
        try:
            # 获取当前状态
            current_status = await get_system_health_status()
            
            # 获取详细报告
            detailed_report = await get_health_dashboard_data()
            
            # 合并数据
            health_data = {
                "current_status": current_status,
                "detailed_report": detailed_report,
                "timestamp": datetime.now().isoformat()
            }
            
            # 发送更新信号
            self.status_updated.emit(health_data)
            
        except Exception as e:
            error_data = {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            self.status_updated.emit(error_data)
    
    def update_ui(self, data: Dict[str, Any]):
        """更新UI显示."""
        try:
            if "error" in data:
                self._show_error(data["error"])
                return
            
            current_status = data.get("current_status", {})
            detailed_report = data.get("detailed_report", {})
            
            # 更新概览
            self._update_overview(current_status, detailed_report)
            
            # 更新详细状态
            self._update_details(detailed_report)
            
            # 更新事件历史
            self._update_events(detailed_report)
            
            # 更新恢复记录
            self._update_recovery(detailed_report)
            
        except Exception as e:
            self._show_error(f"UI更新错误: {e}")
    
    def _update_overview(self, current_status: Dict, detailed_report: Dict):
        """更新概览页面."""
        # 更新健康度
        health_percentage = current_status.get("health_percentage", 0)
        self.health_progress.setValue(int(health_percentage))
        self.health_percentage_label.setText(f"健康度: {health_percentage:.1f}%")
        
        # 更新总体状态
        critical_count = current_status.get("critical_count", 0)
        unhealthy_count = current_status.get("unhealthy_count", 0)
        
        if critical_count > 0:
            status_text = "状态: 严重"
            status_color = "red"
        elif unhealthy_count > 0:
            status_text = "状态: 警告"
            status_color = "orange"
        else:
            status_text = "状态: 正常"
            status_color = "green"
        
        self.overall_status_label.setText(status_text)
        self.overall_status_label.setStyleSheet(f"color: {status_color};")
        
        # 更新进程状态网格
        self._update_processes_grid(current_status)
        
        # 更新系统资源
        self._update_resources_display(detailed_report)
    
    def _update_processes_grid(self, current_status: Dict):
        """更新进程状态网格."""
        # 清空现有内容
        for i in reversed(range(self.processes_grid.count())):
            self.processes_grid.itemAt(i).widget().setParent(None)
        
        detailed_results = current_status.get("detailed_results", {})
        
        row = 0
        for name, result in detailed_results.items():
            # 进程名称
            name_label = QLabel(name)
            name_label.setFont(QFont("Arial", 10, QFont.Bold))
            self.processes_grid.addWidget(name_label, row, 0)
            
            # 状态
            status = result.get("status", "unknown")
            status_label = QLabel(status.upper())
            
            if status == "healthy":
                status_color = "green"
            elif status == "warning":
                status_color = "orange"
            elif status == "unhealthy":
                status_color = "red"
            elif status == "critical":
                status_color = "darkred"
            else:
                status_color = "gray"
            
            status_label.setStyleSheet(f"color: {status_color}; font-weight: bold;")
            self.processes_grid.addWidget(status_label, row, 1)
            
            # 消息
            message = result.get("message", "")
            message_label = QLabel(message[:50] + "..." if len(message) > 50 else message)
            message_label.setWordWrap(True)
            self.processes_grid.addWidget(message_label, row, 2)
            
            row += 1
    
    def _update_resources_display(self, detailed_report: Dict):
        """更新系统资源显示."""
        current_status = detailed_report.get("current_status", {})
        metrics = current_status.get("system_status", {}).get("metrics", {})
        
        resources_text = "系统资源状态:\n"
        
        if metrics:
            cpu_percent = metrics.get("cpu_percent", 0)
            memory_percent = metrics.get("memory_percent", 0)
            disk_percent = metrics.get("disk_percent", 0)
            
            resources_text += f"CPU使用率: {cpu_percent:.1f}%\n"
            resources_text += f"内存使用率: {memory_percent:.1f}%\n"
            resources_text += f"磁盘使用率: {disk_percent:.1f}%\n"
        else:
            resources_text += "暂无系统资源数据"
        
        self.resources_text.setText(resources_text)
    
    def _update_details(self, detailed_report: Dict):
        """更新详细状态页面."""
        details_json = json.dumps(detailed_report, indent=2, ensure_ascii=False)
        self.details_text.setText(details_json)
    
    def _update_events(self, detailed_report: Dict):
        """更新事件历史页面."""
        current_status = detailed_report.get("current_status", {})
        recent_events = current_status.get("recent_events", [])
        
        events_text = "最近事件历史:\n" + "="*50 + "\n"
        
        for event in recent_events:
            timestamp = event.get("timestamp", "")
            event_type = event.get("event_type", "")
            source = event.get("source", "")
            severity = event.get("severity", "")
            message = event.get("message", "")
            
            events_text += f"\n[{timestamp}] {severity.upper()}\n"
            events_text += f"类型: {event_type}\n"
            events_text += f"源: {source}\n"
            events_text += f"消息: {message}\n"
            events_text += "-" * 30 + "\n"
        
        self.events_text.setText(events_text)
    
    def _update_recovery(self, detailed_report: Dict):
        """更新恢复记录页面."""
        current_status = detailed_report.get("current_status", {})
        recent_recoveries = current_status.get("recent_recoveries", [])
        
        recovery_text = "最近恢复记录:\n" + "="*50 + "\n"
        
        for recovery in recent_recoveries:
            timestamp = recovery.get("timestamp", "")
            action = recovery.get("action", "")
            source = recovery.get("source", "")
            success = recovery.get("success", False)
            message = recovery.get("message", "")
            execution_time = recovery.get("execution_time_ms", 0)
            
            recovery_text += f"\n[{timestamp}] {'成功' if success else '失败'}\n"
            recovery_text += f"动作: {action}\n"
            recovery_text += f"源: {source}\n"
            recovery_text += f"耗时: {execution_time:.1f}ms\n"
            recovery_text += f"消息: {message}\n"
            recovery_text += "-" * 30 + "\n"
        
        self.recovery_text.setText(recovery_text)
    
    def _show_error(self, error_message: str):
        """显示错误信息."""
        self.health_percentage_label.setText("健康度: --%")
        self.overall_status_label.setText(f"状态: 错误 - {error_message}")
        self.overall_status_label.setStyleSheet("color: red;")
        
        error_text = f"获取健康数据时发生错误:\n{error_message}"
        self.details_text.setText(error_text)
        self.events_text.setText(error_text)
        self.recovery_text.setText(error_text)


# 便捷函数
def create_health_monitor_widget(parent=None) -> HealthStatusWidget:
    """创建健康监控组件."""
    return HealthStatusWidget(parent)
