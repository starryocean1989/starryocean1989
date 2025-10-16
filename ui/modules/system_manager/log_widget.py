# -*- coding: utf-8 -*-
"""
日志管理界面组件.

提供日志查看、筛选、导出功能，支持实时日志推送。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QTimer, Signal, Qt, QDateTime
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QFileDialog,
    QMessageBox,
)

from backend.core.utils import EVENT_LOG_RECORD
from ui.core.boot_orchestrator import get_boot_orchestrator


class LogManagerWidget(QWidget):
    """日志管理界面组件."""

    # 信号定义
    log_record_received = Signal(dict)  # 接收到新的日志记录

    def __init__(self):
        """初始化日志管理界面."""
        super().__init__()

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

        # 自动滚动标志
        self.auto_scroll = True

        # 更新定时器
        self.update_timer: Optional[QTimer] = None

        # 初始化UI
        self._init_ui()

        # 连接信号
        self._connect_signals()

        # 启动定时器改为就绪后启动
        try:
            orch = get_boot_orchestrator()
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

        layout.addStretch()

        # 时间范围选择
        time_label = QLabel("时间范围:")
        self.start_time_edit = QDateTimeEdit()
        # PySide6: 使用 currentDateTime() 然后调整时间
        start_time = QDateTime.currentDateTime().addSecs(-3600)  # 1小时前
        self.start_time_edit.setDateTime(start_time)
        self.start_time_edit.setDisplayFormat("yyyy-MM-dd hh:mm:ss")

        self.end_time_edit = QDateTimeEdit()
        self.end_time_edit.setDateTime(QDateTime.currentDateTime())
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

        # 清空按钮
        self.clear_btn = QPushButton("清空显示")
        layout.addWidget(self.clear_btn)

        return layout

    def _create_log_table(self) -> QTableWidget:
        """创建日志表格."""
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["时间", "级别", "模块", "函数", "行号", "消息"])

        # 设置表头属性
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # 时间
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # 级别
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # 模块
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # 函数
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # 行号
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)  # 消息

        # 设置表格属性
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # 双击查看详情
        table.doubleClicked.connect(self._show_log_detail)

        return table

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
        self.start_time_edit.dateTimeChanged.connect(self._apply_filters)
        self.end_time_edit.dateTimeChanged.connect(self._apply_filters)
        self.search_edit.textChanged.connect(self._apply_filters)
        self.refresh_btn.clicked.connect(self._refresh_logs)
        self.export_btn.clicked.connect(self._export_logs)
        self.clear_btn.clicked.connect(self._clear_display)

    def _toggle_auto_scroll(self) -> None:
        """切换自动滚动."""
        self.auto_scroll = self.auto_scroll_checkbox.isChecked()

    def _apply_filters(self) -> None:
        """应用筛选条件."""
        # 获取筛选条件
        level_text = self.level_combo.currentText()
        level = level_text if level_text != "全部" else None

        start_time = self.start_time_edit.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
        end_time = self.end_time_edit.dateTime().toString("yyyy-MM-ddTHH:mm:ss")

        search_text = self.search_edit.text().strip()
        search_terms = [term.strip() for term in search_text.split()] if search_text else []

        # 应用筛选
        filtered_records = []
        for record in self.log_records:
            # 级别筛选
            if level and record.get("level") != level:
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
        """更新表格显示."""
        self.log_table.setRowCount(len(self.display_records))

        for row, record in enumerate(self.display_records):
            # 时间
            time_item = QTableWidgetItem(record.get("timestamp", ""))
            self.log_table.setItem(row, 0, time_item)

            # 级别（带颜色）
            level = record.get("level", "")
            level_item = QTableWidgetItem(level)
            level_color = self._get_level_color(level)
            level_item.setBackground(level_color)
            self.log_table.setItem(row, 1, level_item)

            # 模块
            module_item = QTableWidgetItem(record.get("module", ""))
            self.log_table.setItem(row, 2, module_item)

            # 函数
            func_item = QTableWidgetItem(record.get("function", ""))
            self.log_table.setItem(row, 3, func_item)

            # 行号
            line_item = QTableWidgetItem(str(record.get("line", "")))
            self.log_table.setItem(row, 4, line_item)

            # 消息（截断过长内容）
            message = record.get("message", "")
            if len(message) > 200:
                message = message[:200] + "..."
            message_item = QTableWidgetItem(message)
            self.log_table.setItem(row, 5, message_item)

        # 如果自动滚动，滚动到最后一行
        if self.auto_scroll and self.display_records:
            self.log_table.scrollToBottom()

    def _get_level_color(self, level: str) -> QColor:
        """获取日志级别对应的颜色."""
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
        total = len(self.log_records)
        filtered = len(self.display_records)

        self.stats_label.setText(f"日志统计: 显示 {filtered} 条 / 总计 {total} 条")

    def _refresh_logs(self) -> None:
        """刷新日志数据."""
        try:
            # 调用后端API获取最新日志
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            system_service = service_manager.get_service("system_manager_service")

            if system_service:
                # 获取最近1000条日志
                result = system_service.query_logs(limit=1000)

                if result.get("success"):
                    self.log_records = result.get("logs", [])
                    self._apply_filters()
                else:
                    QMessageBox.warning(self, "错误", f"获取日志失败: {result.get('message')}")
            else:
                QMessageBox.warning(self, "错误", "系统管理服务不可用")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"刷新日志失败: {str(e)}")

    def _export_logs(self) -> None:
        """导出日志."""
        try:
            # 选择保存路径
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出日志",
                f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                "文本文件 (*.txt);;所有文件 (*.*)",
            )

            if not file_path:
                return

            # 调用后端API导出日志
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            system_service = service_manager.get_service("system_manager_service")

            if system_service:
                # 获取筛选条件
                level_text = self.level_combo.currentText()
                level = level_text if level_text != "全部" else None

                start_time = self.start_time_edit.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
                end_time = self.end_time_edit.dateTime().toString("yyyy-MM-ddTHH:mm:ss")

                search_text = self.search_edit.text().strip()
                module = search_text if search_text else None

                # 导出日志
                result = system_service.export_logs(
                    file_path=file_path,
                    level=level,
                    start_time=start_time,
                    end_time=end_time,
                    module=module,
                )

                if result.get("success"):
                    QMessageBox.information(self, "成功", f"日志已导出到: {file_path}")
                else:
                    QMessageBox.warning(self, "错误", f"导出失败: {result.get('message')}")
            else:
                QMessageBox.warning(self, "错误", "系统管理服务不可用")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出日志失败: {str(e)}")

    def _clear_display(self) -> None:
        """清空显示."""
        self.display_records.clear()
        self.log_table.setRowCount(0)
        self._update_stats()

    def _show_log_detail(self, index) -> None:
        """显示日志详情."""
        if index.row() >= len(self.display_records):
            return

        record = self.display_records[index.row()]

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

        # 每5秒自动刷新一次
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._refresh_logs)
        self.update_timer.start(5000)  # 5秒

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
        try:
            # 先做一次首刷
            self._refresh_logs()
        finally:
            # 启动定时器
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
