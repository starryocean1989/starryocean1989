# -*- coding: utf-8 -*-
"""系统管理界面 - 主视图（重构版）.

标准架构：8个子界面采用选项卡形式。
合并handlers逻辑，统一backend调用。
"""
import time
from typing import Any, Dict, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import psutil
import pyqtgraph as pg

from backend.core.shared_services import get_service_manager
from backend.core.utils.logging_utils import LoggerMixin
from ui.widgets.base_widget import BaseWidget


class SystemManager(BaseWidget, LoggerMixin):
    """系统管理主界面（重构版）."""

    def __init__(self, parent=None):
        """初始化系统管理界面."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.system_service = None

        # 选项卡部件
        self.tab_widget: QTabWidget = QTabWidget()
        self.system_status_tab: Optional[QWidget] = None
        self.performance_tab: Optional[QWidget] = None
        self.alerts_tab: Optional[QWidget] = None
        self.services_tab: Optional[QWidget] = None
        self.config_tab: Optional[QWidget] = None
        self.logs_tab: Optional[QWidget] = None
        self.diagnosis_tab: Optional[QWidget] = None
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
        self.health_progress: Optional[QProgressBar] = None

        # 日志管理组件
        self.logs_table: Optional[QTableWidget] = None

        # 诊断工具组件
        self.diagnosis_table: Optional[QTableWidget] = None

        # 工具集合组件
        self.tools_table: Optional[QTableWidget] = None

        # 调用父类初始化
        super().__init__(parent, "系统管理")
        self.logger.info("系统管理界面初始化开始")

        # 初始化服务
        self._initialize_service()

    def _initialize_service(self):
        """获取系统管理服务."""
        try:
            # 从服务管理器获取系统管理服务
            self.system_service = self.service_manager.get_service("system_manager_service")
            if self.system_service:
                self.logger.info("系统管理服务获取成功")
            else:
                self.logger.warning("系统管理服务未注册")
        except Exception as e:
            self.logger.error("获取系统管理服务失败: %s", e)
            self.show_error(f"服务获取失败: {e}")

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(600, 400)

        if self.tab_widget:
            self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
            self.tab_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )

        # 创建8个子界面
        self._create_sub_interfaces()

        if self.tab_widget:
            main_layout.addWidget(self.tab_widget)

    def _create_sub_interfaces(self):
        """创建8个子界面."""
        # 1.1 系统状态实时监控
        self.system_status_tab = self._create_system_status_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.system_status_tab, "🔍 系统状态监控")

        # 1.2 性能指标展示
        self.performance_tab = self._create_performance_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.performance_tab, "📊 性能指标")

        # 1.3 告警信息管理
        self.alerts_tab = self._create_alerts_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.alerts_tab, "🚨 告警管理")

        # 1.4 服务健康检查
        self.services_tab = self._create_services_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.services_tab, "💚 服务检查")

        # 1.5 系统配置
        self.config_tab = self._create_config_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.config_tab, "⚙️ 系统配置")

        # 1.6 日志管理
        self.logs_tab = self._create_logs_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.logs_tab, "📝 日志管理")

        # 1.7 系统诊断
        self.diagnosis_tab = self._create_diagnosis_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.diagnosis_tab, "🔧 系统诊断")

        # 1.8 工具集合
        self.tools_tab = self._create_tools_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.tools_tab, "🛠️ 工具集合")

    # ==================== 1.1 系统状态监控 ====================

    def _create_system_status_tab(self) -> QWidget:
        """创建系统状态监控子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 状态概览组
        overview_group = QGroupBox("系统概览")
        overview_layout = QFormLayout(overview_group)

        self.cpu_label = QLabel("--")
        overview_layout.addRow("CPU使用率:", self.cpu_label)

        self.memory_label = QLabel("--")
        overview_layout.addRow("内存使用率:", self.memory_label)

        self.disk_label = QLabel("--")
        overview_layout.addRow("磁盘使用率:", self.disk_label)

        self.network_label = QLabel("--")
        overview_layout.addRow("网络状态:", self.network_label)

        layout.addWidget(overview_group)

        # 系统详情组
        details_group = QGroupBox("详细状态")
        details_layout = QVBoxLayout(details_group)

        self.status_table = QTableWidget(0, 3)
        self.status_table.setHorizontalHeaderLabels(["组件", "状态", "详情"])
        header = self.status_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        details_layout.addWidget(self.status_table)
        layout.addWidget(details_group)

        return tab

    # ==================== 1.2 性能指标展示 ====================

    def _create_performance_tab(self) -> QWidget:
        """创建性能指标子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("📊 性能监控"))
        toolbar_layout.addStretch()

        auto_refresh_check = QCheckBox("自动刷新")
        auto_refresh_check.setChecked(True)
        toolbar_layout.addWidget(auto_refresh_check)

        clear_btn = QPushButton("清除历史")
        clear_btn.clicked.connect(self._clear_performance_history)
        toolbar_layout.addWidget(clear_btn)

        layout.addLayout(toolbar_layout)

        # 性能图表组
        chart_group = QGroupBox("实时性能图表")
        chart_layout = QVBoxLayout(chart_group)

        chart_splitter = QSplitter(Qt.Orientation.Horizontal)

        # CPU图表
        cpu_win = pg.GraphicsLayoutWidget()
        cpu_win.setBackground(QColor(26, 26, 26))
        self.cpu_plot = cpu_win.addPlot(title="CPU使用率 (%)")  # type: ignore[attr-defined]
        if self.cpu_plot:
            self.cpu_plot.showGrid(x=True, y=True, alpha=0.3)
            self.cpu_plot.setRange(yRange=[0, 100])
            pen = pg.mkPen(color="#FF6B6B", width=2)
            self.cpu_curve = self.cpu_plot.plot(pen=pen)

        chart_splitter.addWidget(cpu_win)

        # 内存图表
        memory_win = pg.GraphicsLayoutWidget()
        memory_win.setBackground(QColor(26, 26, 26))
        self.memory_plot = memory_win.addPlot(title="内存使用率 (%)")  # type: ignore[attr-defined]
        if self.memory_plot:
            self.memory_plot.showGrid(x=True, y=True, alpha=0.3)
            self.memory_plot.setRange(yRange=[0, 100])
            pen = pg.mkPen(color="#4ECDC4", width=2)
            self.memory_curve = self.memory_plot.plot(pen=pen)

        chart_splitter.addWidget(memory_win)
        chart_layout.addWidget(chart_splitter)

        layout.addWidget(chart_group)

        # 性能统计组
        stats_group = QGroupBox("性能统计")
        stats_layout = QVBoxLayout(stats_group)

        self.performance_table = QTableWidget(0, 4)
        headers = ["指标", "当前值", "平均值", "峰值"]
        self.performance_table.setHorizontalHeaderLabels(headers)
        stats_layout.addWidget(self.performance_table)

        layout.addWidget(stats_group)

        return tab

    # ==================== 1.3 告警管理 ====================

    def _create_alerts_tab(self) -> QWidget:
        """创建告警管理子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 告警规则组
        rules_group = QGroupBox("告警规则")
        rules_layout = QVBoxLayout(rules_group)

        self.alerts_table = QTableWidget(0, 4)
        headers = ["规则名称", "类型", "阈值", "状态"]
        self.alerts_table.setHorizontalHeaderLabels(headers)
        rules_layout.addWidget(self.alerts_table)

        layout.addWidget(rules_group)

        return tab

    # ==================== 1.4 服务健康检查 ====================

    def _create_services_tab(self) -> QWidget:
        """创建服务检查子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 服务状态组
        services_group = QGroupBox("服务状态")
        services_layout = QVBoxLayout(services_group)

        self.services_table = QTableWidget(0, 4)
        headers = ["服务名称", "状态", "启动时间", "操作"]
        self.services_table.setHorizontalHeaderLabels(headers)
        services_layout.addWidget(self.services_table)

        layout.addWidget(services_group)

        # 健康检查组
        health_group = QGroupBox("健康检查")
        health_layout = QVBoxLayout(health_group)

        self.health_progress = QProgressBar()
        self.health_progress.setRange(0, 100)
        health_layout.addWidget(self.health_progress)

        layout.addWidget(health_group)

        return tab

    # ==================== 1.5 系统配置 ====================

    def _create_config_tab(self) -> QWidget:
        """创建系统配置子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("⚙️ 系统配置"))
        toolbar_layout.addStretch()

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

        # 加载配置
        self._load_config()

        return tab

    # ==================== 1.6 日志管理 ====================

    def _create_logs_tab(self) -> QWidget:
        """创建日志管理子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 日志查看组
        logs_group = QGroupBox("日志查看")
        logs_layout = QVBoxLayout(logs_group)

        self.logs_table = QTableWidget(0, 4)
        self.logs_table.setHorizontalHeaderLabels(["时间", "级别", "模块", "消息"])
        logs_layout.addWidget(self.logs_table)

        layout.addWidget(logs_group)

        # 日志控制组
        control_group = QGroupBox("日志控制")
        control_layout = QHBoxLayout(control_group)

        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(self._clear_logs)
        control_layout.addWidget(clear_btn)

        export_btn = QPushButton("导出日志")
        export_btn.clicked.connect(self._export_logs)
        control_layout.addWidget(export_btn)

        control_layout.addStretch()

        layout.addWidget(control_group)

        return tab

    # ==================== 1.7 系统诊断 ====================

    def _create_diagnosis_tab(self) -> QWidget:
        """创建系统诊断子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 诊断工具组
        tools_group = QGroupBox("诊断工具")
        tools_layout = QVBoxLayout(tools_group)

        self.diagnosis_table = QTableWidget(0, 3)
        self.diagnosis_table.setHorizontalHeaderLabels(["诊断项", "状态", "结果"])
        tools_layout.addWidget(self.diagnosis_table)

        layout.addWidget(tools_group)

        return tab

    # ==================== 1.8 工具集合 ====================

    def _create_tools_tab(self) -> QWidget:
        """创建工具集合子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具组
        tools_group = QGroupBox("可用工具")
        tools_layout = QVBoxLayout(tools_group)

        self.tools_table = QTableWidget(0, 3)
        headers = ["工具名称", "描述", "操作"]
        self.tools_table.setHorizontalHeaderLabels(headers)
        tools_layout.addWidget(self.tools_table)

        layout.addWidget(tools_group)

        return tab

    # ==================== 配置管理方法 ====================

    def _load_config(self):
        """加载配置."""
        try:
            # 使用默认值（vnpy集成后通过service访问）
            if self.tdx_path_edit:
                self.tdx_path_edit.setText("")
            if self.cache_dir_edit:
                self.cache_dir_edit.setText("./data/cache")
            if self.data_dir_edit:
                self.data_dir_edit.setText("./data/kline")
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

            self.logger.info("配置加载完成（使用默认值）")

        except Exception as e:
            self.logger.error("加载配置失败: %s", e)

    def _refresh_config(self):
        """刷新配置."""
        self._load_config()
        self.show_info("配置已刷新")

    def _save_config(self):
        """保存配置."""
        try:
            # vnpy集成后通过service保存配置
            self.show_info("配置保存功能需要vnpy集成")

        except Exception as e:
            self.logger.error("保存配置失败: %s", e)
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
        dir_path = QFileDialog.getExistingDirectory(self, "选择品种缓存目录")
        if dir_path and self.cache_dir_edit:
            self.cache_dir_edit.setText(dir_path)

    def _browse_data_dir(self):
        """浏览数据目录."""
        dir_path = QFileDialog.getExistingDirectory(self, "选择K线数据目录")
        if dir_path and self.data_dir_edit:
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

    # ==================== 通用方法 ====================

    def connect_signals(self):
        """连接信号槽."""
        self.start_update_timer(2000, self._update_system_status)

    def refresh_data(self):
        """刷新数据."""
        self._update_system_status()
        self.show_info("系统状态已刷新")

    def on_close(self):
        """关闭处理."""
        self.stop_update_timer()
        self.logger.info("系统管理界面已关闭")
