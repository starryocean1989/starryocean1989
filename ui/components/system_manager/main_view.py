# -*- coding: utf-8 -*-
"""
系统管理界面 - 主视图.

标准架构：8个子界面采用选项卡形式.
"""

import time
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
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

try:
    from backend.core.vnpy_integration import TerminalEngine as _VnPyAdapter
except ImportError:
    _VnPyAdapter = None

# 尝试导入更高级的版本
try:
    from ui.widgets.base_widget import BaseWidget as _BaseWidget
    from backend.core.utils.logging_utils import LoggerMixin as _LoggerMixin
    from ui.components.system_manager.system_manager_handlers import SystemManagerHandlers

    # Use imported classes
    BaseWidget = _BaseWidget  # type: ignore
    LoggerMixin = _LoggerMixin  # type: ignore
except ImportError as e:
    # 导入失败时直接报错，不使用fallback
    raise ImportError(
        "无法导入必要的UI组件，请确保已正确安装所有依赖：pip install -r requirements.txt"
    ) from e


class SystemManager(BaseWidget, LoggerMixin):
    """系统管理主界面."""

    def __init__(self, parent=None):
        """初始化系统管理界面."""
        # 必须先初始化所有属性，再调用super().__init__()
        # 因为BaseWidget会在__init__中自动调用setup_ui()
        self.tab_widget: QTabWidget = QTabWidget()
        self.system_status_tab: Optional[QWidget] = None
        self.performance_tab: Optional[QWidget] = None
        self.alerts_tab: Optional[QWidget] = None
        self.services_tab: Optional[QWidget] = None
        self.config_tab: Optional[QWidget] = None
        self.logs_tab: Optional[QWidget] = None
        self.diagnosis_tab: Optional[QWidget] = None
        self.tools_tab: Optional[QWidget] = None

        # 初始化处理器
        self.handlers = SystemManagerHandlers(self)

        # 系统状态组件
        self.cpu_label: Optional[QLabel] = None
        self.memory_label: Optional[QLabel] = None
        self.disk_label: Optional[QLabel] = None
        self.network_label: Optional[QLabel] = None
        self.status_table: Optional[QTableWidget] = None
        self.vnpy_status_label: Optional[QLabel] = None

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
        self.cache_dir_label: Optional[QLabel] = None
        self.data_dir_label: Optional[QLabel] = None
        self.cache_files_label: Optional[QLabel] = None
        self.data_symbols_label: Optional[QLabel] = None
        self.tdx_status_label: Optional[QLabel] = None

        # 性能监控组件
        self.cpu_plot: Optional[Any] = None
        self.cpu_curve: Optional[Any] = None
        self.memory_plot: Optional[Any] = None
        self.memory_curve: Optional[Any] = None
        self.disk_plot: Optional[Any] = None
        self.disk_read_curve: Optional[Any] = None
        self.disk_write_curve: Optional[Any] = None
        self.network_plot: Optional[Any] = None
        self.network_recv_curve: Optional[Any] = None
        self.network_send_curve: Optional[Any] = None
        self.performance_history: Dict[str, list] = {
            "cpu": [],
            "memory": [],
            "disk_read": [],
            "disk_write": [],
            "net_recv": [],
            "net_send": [],
        }
        self.max_history_points: int = 100
        self.performance_table: Optional[QTableWidget] = None

        # 告警管理组件
        self.alerts_table: Optional[QTableWidget] = None
        self.alert_history_table: Optional[QTableWidget] = None

        # 服务管理组件
        self.services_table: Optional[QTableWidget] = None
        self.health_progress: Optional[QProgressBar] = None

        # 配置管理组件
        self.config_table: Optional[QTableWidget] = None

        # 日志管理组件
        self.logs_table: Optional[QTableWidget] = None

        # 诊断工具组件
        self.diagnosis_table: Optional[QTableWidget] = None
        self.diagnosis_text: Optional[QLabel] = None

        # 工具集合组件
        self.tools_table: Optional[QTableWidget] = None

        # VNPY适配器
        self.vnpy_adapter: Optional[Any] = None

        # 现在调用父类初始化，这时setup_ui()会被调用
        super().__init__(parent, "系统管理")
        self.logger.info("系统管理界面初始化开始")

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 设置组件大小策略为扩展

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(600, 400)

        # 选项卡部件已在__init__中初始化
        if self.tab_widget:
            self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
            # 确保tab_widget填充可用空间
            self.tab_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )

        # 创建8个子界面
        self._create_sub_interfaces()

        if self.tab_widget:
            main_layout.addWidget(self.tab_widget)

        # 设置样式
        self.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid #404040;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #ffffff;
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #1e88e5;
            }
            QTabBar::tab:hover {
                background-color: #383838;
            }
        """
        )

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

    def _create_system_status_tab(self):
        """创建系统状态监控子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

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

    def _create_performance_tab(self):
        """创建性能指标子界面（优化版）."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 工具栏
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("📊 性能监控"))
        toolbar_layout.addStretch()

        auto_refresh_check = QCheckBox("自动刷新")
        auto_refresh_check.setChecked(True)
        auto_refresh_check.setToolTip("每5秒自动更新图表")
        toolbar_layout.addWidget(auto_refresh_check)

        clear_btn = QPushButton("清除历史")
        clear_btn.setToolTip("清除历史数据")
        clear_btn.clicked.connect(self._clear_performance_history)
        toolbar_layout.addWidget(clear_btn)

        export_btn = QPushButton("📤 导出")
        export_btn.setToolTip("导出性能报告")
        export_btn.clicked.connect(self._export_performance_report)
        toolbar_layout.addWidget(export_btn)

        layout.addLayout(toolbar_layout)

        # 性能图表组（优化布局）
        chart_group = QGroupBox("实时性能图表")
        chart_layout = QVBoxLayout(chart_group)

        # 性能图表组件
        # 使用2x2网格布局展示4个图表
        chart_splitter = QSplitter(Qt.Orientation.Vertical)

        # 上半部分：CPU和内存
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        # CPU使用率图表
        cpu_win = pg.GraphicsLayoutWidget()
        cpu_win.setBackground(QColor(26, 26, 26))
        self.cpu_plot = cpu_win.addPlot(title="CPU使用率 (%)")  # type: ignore
        if self.cpu_plot:
            self.cpu_plot.showGrid(x=True, y=True, alpha=0.3)
            self.cpu_plot.setRange(yRange=[0, 100])
            self.cpu_plot.setLabel("left", "CPU %")
            self.cpu_plot.setLabel("bottom", "时间点")
            pen = pg.mkPen(color="#FF6B6B", width=2)
            self.cpu_curve = self.cpu_plot.plot(pen=pen)
            # 添加阈值线
            threshold_line = pg.InfiniteLine(
                pos=80,
                angle=0,
                pen=pg.mkPen("y", width=1, style=Qt.PenStyle.DashLine),
            )
            self.cpu_plot.addItem(threshold_line)

        # 内存使用率图表
        memory_win = pg.GraphicsLayoutWidget()
        memory_win.setBackground(QColor(26, 26, 26))
        self.memory_plot = memory_win.addPlot(title="内存使用率 (%)")  # type: ignore
        if self.memory_plot:
            self.memory_plot.showGrid(x=True, y=True, alpha=0.3)
            self.memory_plot.setRange(yRange=[0, 100])
            self.memory_plot.setLabel("left", "内存 %")
            self.memory_plot.setLabel("bottom", "时间点")
            pen = pg.mkPen(color="#4ECDC4", width=2)
            self.memory_curve = self.memory_plot.plot(pen=pen)
            # 添加阈值线
            threshold_line = pg.InfiniteLine(
                pos=80,
                angle=0,
                pen=pg.mkPen("y", width=1, style=Qt.PenStyle.DashLine),
            )
            self.memory_plot.addItem(threshold_line)

        top_layout.addWidget(cpu_win)
        top_layout.addWidget(memory_win)
        chart_splitter.addWidget(top_widget)

        # 下半部分：磁盘I/O和网络流量
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        # 磁盘I/O图表
        disk_win = pg.GraphicsLayoutWidget()
        disk_win.setBackground(QColor(26, 26, 26))
        self.disk_plot = disk_win.addPlot(title="磁盘I/O (MB/s)")  # type: ignore
        if self.disk_plot:
            self.disk_plot.showGrid(x=True, y=True, alpha=0.3)
            self.disk_plot.setLabel("left", "MB/s")
            self.disk_plot.setLabel("bottom", "时间点")
            read_pen = pg.mkPen(color="#95E1D3", width=2)
            write_pen = pg.mkPen(color="#F38181", width=2)
            self.disk_read_curve = self.disk_plot.plot(pen=read_pen, name="读")
            self.disk_write_curve = self.disk_plot.plot(pen=write_pen, name="写")
            self.disk_plot.addLegend()

        # 网络流量图表
        network_win = pg.GraphicsLayoutWidget()
        network_win.setBackground(QColor(26, 26, 26))
        self.network_plot = network_win.addPlot(title="网络流量 (KB/s)")  # type: ignore
        if self.network_plot:
            self.network_plot.showGrid(x=True, y=True, alpha=0.3)
            self.network_plot.setLabel("left", "KB/s")
            self.network_plot.setLabel("bottom", "时间点")
            recv_pen = pg.mkPen(color="#A8E6CF", width=2)
            send_pen = pg.mkPen(color="#FFD3B6", width=2)
            self.network_recv_curve = self.network_plot.plot(pen=recv_pen, name="接收")
            self.network_send_curve = self.network_plot.plot(pen=send_pen, name="发送")
            self.network_plot.addLegend()

        bottom_layout.addWidget(disk_win)
        bottom_layout.addWidget(network_win)
        chart_splitter.addWidget(bottom_widget)

        chart_splitter.setSizes([300, 300])
        chart_layout.addWidget(chart_splitter)

        layout.addWidget(chart_group)

        # 性能统计组（优化展示）
        stats_group = QGroupBox("性能统计")
        stats_layout = QVBoxLayout(stats_group)

        self.performance_table = QTableWidget(0, 4)
        headers = ["指标", "当前值", "平均值", "峰值"]
        self.performance_table.setHorizontalHeaderLabels(headers)
        header = self.performance_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # 添加初始数据行
        metrics = [
            "CPU使用率",
            "内存使用率",
            "磁盘读取",
            "磁盘写入",
            "网络接收",
            "网络发送",
        ]
        self.performance_table.setRowCount(len(metrics))
        for i, metric in enumerate(metrics):
            self.performance_table.setItem(i, 0, QTableWidgetItem(metric))
            self.performance_table.setItem(i, 1, QTableWidgetItem("--"))
            self.performance_table.setItem(i, 2, QTableWidgetItem("--"))
            self.performance_table.setItem(i, 3, QTableWidgetItem("--"))

        stats_layout.addWidget(self.performance_table)

        layout.addWidget(stats_group)

        return tab

    def _create_alerts_tab(self):
        """创建告警管理子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 告警规则组
        rules_group = QGroupBox("告警规则")
        rules_layout = QVBoxLayout(rules_group)

        self.alerts_table = QTableWidget(0, 4)
        headers = ["规则名称", "类型", "阈值", "状态"]
        self.alerts_table.setHorizontalHeaderLabels(headers)
        header = self.alerts_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        rules_layout.addWidget(self.alerts_table)

        layout.addWidget(rules_group)

        # 告警历史组
        history_group = QGroupBox("告警历史")
        history_layout = QVBoxLayout(history_group)

        self.alert_history_table = QTableWidget(0, 4)
        headers = ["时间", "级别", "消息", "状态"]
        self.alert_history_table.setHorizontalHeaderLabels(headers)
        header = self.alert_history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        history_layout.addWidget(self.alert_history_table)

        layout.addWidget(history_group)

        return tab

    def _create_services_tab(self):
        """创建服务检查子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 服务状态组
        services_group = QGroupBox("服务状态")
        services_layout = QVBoxLayout(services_group)

        self.services_table = QTableWidget(0, 4)
        headers = ["服务名称", "状态", "启动时间", "操作"]
        self.services_table.setHorizontalHeaderLabels(headers)
        header = self.services_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

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

    def _create_config_tab(self):
        """创建系统配置子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 顶部工具栏
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("⚙️ 系统配置"))
        toolbar_layout.addStretch()

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setToolTip("重新加载配置")
        refresh_btn.clicked.connect(self._refresh_config)
        toolbar_layout.addWidget(refresh_btn)

        save_btn = QPushButton("💾 保存")
        save_btn.setToolTip("保存配置更改")
        save_btn.clicked.connect(self._save_config)
        toolbar_layout.addWidget(save_btn)

        reset_btn = QPushButton("↩️ 重置")
        reset_btn.setToolTip("重置为默认配置")
        reset_btn.clicked.connect(self._reset_config)
        toolbar_layout.addWidget(reset_btn)

        layout.addLayout(toolbar_layout)

        # data_module_vnpy配置组
        data_config_group = QGroupBox("数据中心配置（data_module_vnpy）")
        data_config_layout = QFormLayout(data_config_group)
        data_config_layout.setSpacing(10)

        # 保存配置控件引用
        self.config_widgets = {}

        # 通达信软件根目录
        tdx_layout = QHBoxLayout()
        self.tdx_path_edit = QLineEdit()
        self.tdx_path_edit.setPlaceholderText("例如: C:/通达信金融终端V7")
        tdx_layout.addWidget(self.tdx_path_edit)

        tdx_browse_btn = QPushButton("📁 浏览")
        tdx_browse_btn.clicked.connect(self._browse_tdx_dir)
        tdx_layout.addWidget(tdx_browse_btn)

        tdx_validate_btn = QPushButton("✓ 验证")
        tdx_validate_btn.clicked.connect(self._validate_tdx_path)
        tdx_layout.addWidget(tdx_validate_btn)

        data_config_layout.addRow("通达信根目录*:", tdx_layout)
        self.config_widgets["chinastock.tdx_dir"] = self.tdx_path_edit

        # 品种列表缓存目录
        cache_layout = QHBoxLayout()
        self.cache_dir_edit = QLineEdit()
        self.cache_dir_edit.setPlaceholderText("例如: ./data/cache")
        cache_layout.addWidget(self.cache_dir_edit)

        cache_browse_btn = QPushButton("📁 浏览")
        cache_browse_btn.clicked.connect(self._browse_cache_dir)
        cache_layout.addWidget(cache_browse_btn)

        data_config_layout.addRow("品种缓存目录:", cache_layout)
        self.config_widgets["chinastock.cache_dir"] = self.cache_dir_edit

        # K线数据存储目录
        data_layout = QHBoxLayout()
        self.data_dir_edit = QLineEdit()
        self.data_dir_edit.setPlaceholderText("例如: ./data/kline")
        data_layout.addWidget(self.data_dir_edit)

        data_browse_btn = QPushButton("📁 浏览")
        data_browse_btn.clicked.connect(self._browse_data_dir)
        data_layout.addWidget(data_browse_btn)

        data_config_layout.addRow("K线数据目录:", data_layout)
        self.config_widgets["chinastock.data_dir"] = self.data_dir_edit

        # 数据感知基日
        from PySide6.QtCore import QDate

        self.base_date_edit = QDateEdit()
        self.base_date_edit.setCalendarPopup(True)
        self.base_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.base_date_edit.setDate(QDate(2020, 1, 1))
        data_config_layout.addRow("数据感知基日:", self.base_date_edit)
        self.config_widgets["chinastock.base_date"] = self.base_date_edit

        # 最大工作线程数
        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(1, 50)
        self.max_workers_spin.setValue(10)
        self.max_workers_spin.setSuffix(" 线程")
        data_config_layout.addRow("最大线程数:", self.max_workers_spin)
        self.config_widgets["chinastock.max_workers"] = self.max_workers_spin

        # 请求超时时间
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 300)
        self.timeout_spin.setValue(30)
        self.timeout_spin.setSuffix(" 秒")
        data_config_layout.addRow("请求超时:", self.timeout_spin)
        self.config_widgets["chinastock.timeout"] = self.timeout_spin

        # 请求重试次数
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(3)
        self.retry_spin.setSuffix(" 次")
        data_config_layout.addRow("重试次数:", self.retry_spin)
        self.config_widgets["chinastock.retry_times"] = self.retry_spin

        # 启用文件监控
        self.watcher_check = QCheckBox()
        self.watcher_check.setChecked(True)
        data_config_layout.addRow("启用文件监控:", self.watcher_check)
        self.config_widgets["chinastock.enable_watcher"] = self.watcher_check

        # 文件监控间隔
        self.watcher_interval_spin = QSpinBox()
        self.watcher_interval_spin.setRange(1, 60)
        self.watcher_interval_spin.setValue(5)
        self.watcher_interval_spin.setSuffix(" 秒")
        data_config_layout.addRow("监控检查间隔:", self.watcher_interval_spin)
        self.config_widgets["chinastock.watcher_interval"] = self.watcher_interval_spin

        layout.addWidget(data_config_group)

        # 配置统计组
        stats_group = QGroupBox("配置状态")
        stats_layout = QFormLayout(stats_group)

        self.cache_dir_label = QLabel("-")
        stats_layout.addRow("品种缓存路径:", self.cache_dir_label)

        self.data_dir_label = QLabel("-")
        stats_layout.addRow("K线数据路径:", self.data_dir_label)

        self.cache_files_label = QLabel("-")
        stats_layout.addRow("缓存文件数:", self.cache_files_label)

        self.data_symbols_label = QLabel("-")
        stats_layout.addRow("已下载品种数:", self.data_symbols_label)

        self.tdx_status_label = QLabel("-")
        stats_layout.addRow("通达信状态:", self.tdx_status_label)

        layout.addWidget(stats_group)

        # 说明文字
        help_label = QLabel(
            "💡 提示：\n"
            "• 通达信根目录用于解析spblock.dat文件，获取北证A股、T+0基金、含可转债等特殊品种\n"
            "• 如果不配置通达信路径，仅能获取上证A股和深证A股\n"
            "• 修改配置后需要点击'保存'按钮并重启应用才能生效"
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            "color: #666; padding: 10px; background: #f5f5f5; border-radius: 5px;"
        )
        layout.addWidget(help_label)

        layout.addStretch()

        # 加载初始配置
        self._load_initial_config()

        return tab

    def _create_logs_tab(self):
        """创建日志管理子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 日志查看组
        logs_group = QGroupBox("日志查看")
        logs_layout = QVBoxLayout(logs_group)

        self.logs_table = QTableWidget(0, 4)
        self.logs_table.setHorizontalHeaderLabels(["时间", "级别", "模块", "消息"])
        header = self.logs_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

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

    def _create_diagnosis_tab(self):
        """创建系统诊断子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 诊断工具组
        tools_group = QGroupBox("诊断工具")
        tools_layout = QVBoxLayout(tools_group)

        self.diagnosis_table = QTableWidget(0, 3)
        self.diagnosis_table.setHorizontalHeaderLabels(["诊断项", "状态", "结果"])
        header = self.diagnosis_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        tools_layout.addWidget(self.diagnosis_table)

        layout.addWidget(tools_group)

        # 诊断结果组
        results_group = QGroupBox("诊断结果")
        results_layout = QVBoxLayout(results_group)

        self.diagnosis_text = QLabel("诊断结果将显示在这里...")
        self.diagnosis_text.setWordWrap(True)
        style = "padding: 10px; background-color: #2d2d2d; border-radius: 4px;"
        self.diagnosis_text.setStyleSheet(style)
        results_layout.addWidget(self.diagnosis_text)

        layout.addWidget(results_group)

        return tab

    def _create_tools_tab(self):
        """创建工具集合子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 工具组
        tools_group = QGroupBox("可用工具")
        tools_layout = QVBoxLayout(tools_group)

        self.tools_table = QTableWidget(0, 3)
        headers = ["工具名称", "描述", "操作"]
        self.tools_table.setHorizontalHeaderLabels(headers)
        header = self.tools_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        tools_layout.addWidget(self.tools_table)

        layout.addWidget(tools_group)

        return tab

    def _clear_performance_history(self):
        """清除性能历史数据."""
        self.performance_history = {
            "cpu": [],
            "memory": [],
            "disk_read": [],
            "disk_write": [],
            "net_recv": [],
            "net_send": [],
        }
        self.show_info("性能历史数据已清除")
        # 清空图表
        if self.cpu_curve:
            self.cpu_curve.setData([], [])
        if self.memory_curve:
            self.memory_curve.setData([], [])
        if hasattr(self, "disk_read_curve") and self.disk_read_curve:
            self.disk_read_curve.setData([], [])
        if hasattr(self, "disk_write_curve") and self.disk_write_curve:
            self.disk_write_curve.setData([], [])
        if hasattr(self, "network_recv_curve") and self.network_recv_curve:
            self.network_recv_curve.setData([], [])
        if hasattr(self, "network_send_curve") and self.network_send_curve:
            self.network_send_curve.setData([], [])

    def _export_performance_report(self):
        """导出性能报告."""
        from PySide6.QtWidgets import QFileDialog

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "导出性能报告",
            "performance_report.html",
            "HTML Files (*.html);;PDF Files (*.pdf);;CSV Files (*.csv)",
        )

        if filename:
            self.show_info(f"导出性能报告到: {filename}")
            # 这里可以实现实际的报告导出逻辑

    def connect_signals(self):
        """连接信号槽."""
        try:
            # 初始化VNPY适配器
            self._initialize_vnpy_adapter()

            # 启动状态更新定时器
            self.start_update_timer(2000, self._update_system_status)
        except Exception as e:
            self.logger.error("连接信号失败: %s", e)
            import traceback

            self.logger.error("详细错误: %s", traceback.format_exc())

    def _initialize_vnpy_adapter(self):
        """初始化VNPY适配器."""
        if _VnPyAdapter is None:
            raise ImportError("VnPy未安装或配置错误，无法初始化系统管理")

        try:
            self.vnpy_adapter = _VnPyAdapter()
            self.logger.info("VNPY适配器初始化完成")
        except (RuntimeError, AttributeError) as e:
            self.logger.error("VNPY适配器初始化失败: %s", e)
            raise RuntimeError(f"VNPY适配器初始化失败: {e}") from e

    def _update_system_status(self):
        """更新系统状态."""
        if not self.vnpy_adapter:
            raise RuntimeError("VNPY适配器未初始化")

        try:
            # 更新基础系统信息
            cpu_percent = psutil.cpu_percent()
            if hasattr(self, "cpu_label") and self.cpu_label:
                self.cpu_label.setText(f"{cpu_percent:.1f}%")

            memory = psutil.virtual_memory()
            if hasattr(self, "memory_label") and self.memory_label:
                self.memory_label.setText(f"{memory.percent:.1f}%")

            disk = psutil.disk_usage("/")
            if hasattr(self, "disk_label") and self.disk_label:
                self.disk_label.setText(f"{disk.percent:.1f}%")

            network = psutil.net_if_addrs()
            if hasattr(self, "network_label") and self.network_label:
                self.network_label.setText(f"接口数: {len(network)}")

            # 更新VNPY系统状态 - 必须有get_status方法
            if not hasattr(self.vnpy_adapter, "get_status"):
                raise AttributeError("VNPY适配器缺少get_status方法")

            vnpy_status = self.vnpy_adapter.get_status()

            # 更新VNPY状态标签
            vnpy_available = vnpy_status.get("vnpy_available", False)
            status_text = "可用" if vnpy_available else "不可用"
            vnpy_status_text = f"VNPY: {status_text} | "

            gateways = vnpy_status.get("gateways", [])
            vnpy_status_text += f"网关: {len(gateways)} | "

            worker_running = vnpy_status.get("real_time_worker_running", False)
            worker_text = "运行" if worker_running else "停止"
            vnpy_status_text += f"实时数据: {worker_text}"

            # 添加VNPY状态标签（如果不存在）
            if not hasattr(self, "vnpy_status_label"):
                layout = self.system_status_tab.layout() if self.system_status_tab else None
                if layout and isinstance(layout, QVBoxLayout):
                    overview_group = layout.itemAt(0).widget()
                    if isinstance(overview_group, QGroupBox):
                        overview_layout = overview_group.layout()
                        if isinstance(overview_layout, QFormLayout):
                            self.vnpy_status_label = QLabel("--")
                            overview_layout.addRow("VNPY状态:", self.vnpy_status_label)

            if hasattr(self, "vnpy_status_label") and self.vnpy_status_label:
                self.vnpy_status_label.setText(vnpy_status_text)

            # 更新状态表格
            self._update_status_table()

            # 更新性能图表
            self._update_performance_charts()

        except (AttributeError, RuntimeError) as e:
            self.logger.error("更新系统状态失败: %s", e)

    def _update_performance_charts(self):
        """更新性能图表."""
        if not hasattr(self, "cpu_curve") or self.cpu_curve is None:
            return

        current_time = time.time()

        try:
            # 获取当前性能数据
            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent

            # 添加到历史数据
            self.performance_history["cpu"].append((current_time, cpu_percent))
            self.performance_history["memory"].append((current_time, memory_percent))

            # 限制历史数据点数量
            for key, history in self.performance_history.items():
                if len(history) > self.max_history_points:
                    self.performance_history[key] = history[-self.max_history_points :]

            # 更新图表
            if self.performance_history["cpu"] and self.cpu_curve:
                times, cpu_values = zip(*self.performance_history["cpu"])
                self.cpu_curve.setData(times, cpu_values)

            if self.performance_history["memory"] and self.memory_curve:
                times, memory_values = zip(*self.performance_history["memory"])
                self.memory_curve.setData(times, memory_values)
        except (AttributeError, RuntimeError) as e:
            self.logger.error("更新性能图表失败: %s", e)

    def _update_status_table(self):
        """更新状态表格."""
        # 清空表格
        try:
            if self.status_table:
                self.status_table.setRowCount(0)

            # 基础系统组件状态
            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent
            disk_percent = psutil.disk_usage("/").percent

            base_components = [
                ("CPU", "正常", f"使用率: {cpu_percent:.1f}%"),
                ("内存", "正常", f"使用率: {memory_percent:.1f}%"),
                ("磁盘", "正常", f"使用率: {disk_percent:.1f}%"),
                ("网络", "正常", "连接正常"),
                ("数据库", "正常", "连接正常"),
            ]

            # VNPY相关组件状态 - 必须有VNPY适配器
            if not self.vnpy_adapter:
                raise RuntimeError("VNPY适配器未初始化")

            if not hasattr(self.vnpy_adapter, "get_status"):
                raise AttributeError("VNPY适配器缺少get_status方法")

            vnpy_status = self.vnpy_adapter.get_status()
            vnpy_available = vnpy_status.get("vnpy_available", False)
            gateways = vnpy_status.get("gateways", [])
            worker_running = vnpy_status.get("real_time_worker_running", False)
            subscribed = vnpy_status.get("subscribed_symbols", [])

            # 处理 subscribed 可能是 int 或 list 的情况
            if isinstance(subscribed, int):
                subscribed_count = subscribed
            elif isinstance(subscribed, list):
                subscribed_count = len(subscribed)
            else:
                subscribed_count = 0

            vnpy_components = [
                (
                    "VNPY引擎",
                    "可用" if vnpy_available else "不可用",
                    f"状态: {'运行' if vnpy_available else '停止'}",
                ),
                (
                    "交易网关",
                    ("正常" if vnpy_status.get("connected_gateways") else "未连接"),
                    f"网关数: {len(gateways)}",
                ),
                (
                    "实时数据",
                    "运行" if worker_running else "停止",
                    f"订阅品种: {subscribed_count}",
                ),
            ]

            # 合并所有组件
            all_components = base_components + vnpy_components

            if self.status_table:
                for i, (component, status, detail) in enumerate(all_components):
                    self.status_table.insertRow(i)
                    self.status_table.setItem(i, 0, QTableWidgetItem(component))
                    self.status_table.setItem(i, 1, QTableWidgetItem(status))
                    self.status_table.setItem(i, 2, QTableWidgetItem(detail))

                    # 设置状态颜色
                    status_item = self.status_table.item(i, 1)
                    if status_item:
                        if status in ["正常", "可用", "运行"]:
                            status_item.setBackground(QColor("#4caf50"))
                        elif status in ["不可用", "停止", "未知"]:
                            status_item.setBackground(QColor("#ff9800"))
                        else:
                            status_item.setBackground(QColor("#f44336"))
        except (AttributeError, RuntimeError) as e:
            self.logger.error("更新状态表格失败: %s", e)

    def _clear_logs(self):
        """清空日志."""
        if self.logs_table:
            self.logs_table.setRowCount(0)
        self.show_info("日志已清空")

    def _export_logs(self):
        """导出日志."""
        from PySide6.QtWidgets import QFileDialog
        from datetime import datetime
        import os

        try:
            # 弹出文件保存对话框
            default_filename = f"terminal_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出日志", default_filename, "文本文件 (*.txt);;所有文件 (*.*)"
            )

            if not file_path:
                return

            # 从日志表格获取日志内容
            if not self.logs_table:
                raise RuntimeError("日志表格未初始化")

            log_lines = []
            for row in range(self.logs_table.rowCount()):
                time_item = self.logs_table.item(row, 0)
                level_item = self.logs_table.item(row, 1)
                module_item = self.logs_table.item(row, 2)
                message_item = self.logs_table.item(row, 3)

                if time_item and level_item and module_item and message_item:
                    log_line = f"[{time_item.text()}] [{level_item.text()}] {module_item.text()}: {message_item.text()}"
                    log_lines.append(log_line)

            # 如果没有日志，从实际日志文件读取
            if not log_lines:
                logs_dir = "logs"
                if os.path.exists(logs_dir):
                    log_file = os.path.join(logs_dir, "terminal_v0.50.log")
                    if os.path.exists(log_file):
                        with open(log_file, "r", encoding="utf-8") as f:
                            log_lines = f.readlines()

            # 保存到文件
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(log_lines))

            self.show_info(f"日志已导出到: {file_path}")

        except Exception as e:
            self.show_error(f"导出日志失败: {str(e)}")

    def refresh_data(self):
        """刷新数据."""
        self._update_system_status()
        self.show_info("系统状态已刷新")

    def on_close(self):
        """关闭处理."""
        self.stop_update_timer()
        self.logger.info("系统管理界面已关闭")

    # ========== 配置管理方法 ==========

    def _load_initial_config(self):
        """加载初始配置."""
        try:
            config = self.handlers.load_data_module_config()

            # 填充配置到UI控件
            for _name, cfg in config.items():
                key = cfg["key"]
                value = cfg["value"]

                if key == "chinastock.tdx_dir" and self.tdx_path_edit:
                    self.tdx_path_edit.setText(str(value))
                elif key == "chinastock.cache_dir" and self.cache_dir_edit:
                    self.cache_dir_edit.setText(str(value))
                elif key == "chinastock.data_dir" and self.data_dir_edit:
                    self.data_dir_edit.setText(str(value))
                elif key == "chinastock.base_date" and self.base_date_edit:
                    from PySide6.QtCore import QDate

                    date_parts = str(value).split("-")
                    if len(date_parts) == 3:
                        self.base_date_edit.setDate(
                            QDate(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
                        )
                elif key == "chinastock.max_workers" and self.max_workers_spin:
                    self.max_workers_spin.setValue(int(value))
                elif key == "chinastock.timeout" and self.timeout_spin:
                    self.timeout_spin.setValue(int(value))
                elif key == "chinastock.retry_times" and self.retry_spin:
                    self.retry_spin.setValue(int(value))
                elif key == "chinastock.enable_watcher" and self.watcher_check:
                    self.watcher_check.setChecked(bool(value))
                elif key == "chinastock.watcher_interval" and self.watcher_interval_spin:
                    self.watcher_interval_spin.setValue(int(value))

            # 更新配置统计
            self._update_config_stats()

            self.logger.info("配置加载完成")

        except Exception as e:
            self.logger.error("加载配置失败: %s", e)
            self.show_error(f"加载配置失败: {e}")

    def _refresh_config(self):
        """刷新配置."""
        try:
            self._load_initial_config()
            self.show_info("配置已刷新")
        except Exception as e:
            self.show_error(f"刷新配置失败: {e}")

    def _save_config(self):
        """保存配置."""
        try:
            # 检查必要的控件是否初始化
            if not all(
                [
                    self.tdx_path_edit,
                    self.cache_dir_edit,
                    self.data_dir_edit,
                    self.base_date_edit,
                    self.max_workers_spin,
                    self.timeout_spin,
                    self.retry_spin,
                    self.watcher_check,
                    self.watcher_interval_spin,
                ]
            ):
                self.show_error("配置控件未初始化")
                return

            # 收集配置更新
            assert self.tdx_path_edit is not None
            assert self.cache_dir_edit is not None
            assert self.data_dir_edit is not None
            assert self.base_date_edit is not None
            assert self.max_workers_spin is not None
            assert self.timeout_spin is not None
            assert self.retry_spin is not None
            assert self.watcher_check is not None
            assert self.watcher_interval_spin is not None

            config_updates = {
                "chinastock.tdx_dir": self.tdx_path_edit.text().strip(),
                "chinastock.cache_dir": self.cache_dir_edit.text().strip(),
                "chinastock.data_dir": self.data_dir_edit.text().strip(),
                "chinastock.base_date": self.base_date_edit.date().toString("yyyy-MM-dd"),
                "chinastock.max_workers": self.max_workers_spin.value(),
                "chinastock.timeout": self.timeout_spin.value(),
                "chinastock.retry_times": self.retry_spin.value(),
                "chinastock.enable_watcher": self.watcher_check.isChecked(),
                "chinastock.watcher_interval": self.watcher_interval_spin.value(),
            }

            # 保存配置
            success = self.handlers.save_data_module_config(config_updates)

            if success:
                self.show_info("配置保存成功！\n\n注意：部分配置需要重启应用后才能生效")
                self._update_config_stats()
            else:
                self.show_error("配置保存失败，请查看日志")

        except Exception as e:
            self.logger.error("保存配置失败: %s", e)
            self.show_error(f"保存配置失败: {e}")

    def _reset_config(self):
        """重置配置."""
        try:
            # 确认对话框
            reply = QMessageBox.question(
                self,
                "确认重置",
                "确定要重置所有配置为默认值吗？\n此操作不可撤销。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                success = self.handlers.reset_to_defaults()

                if success:
                    self.show_info("配置已重置为默认值")
                    self._load_initial_config()
                else:
                    self.show_error("重置配置失败")

        except Exception as e:
            self.logger.error("重置配置失败: %s", e)
            self.show_error(f"重置配置失败: {e}")

    def _browse_tdx_dir(self):
        """浏览选择通达信目录."""
        try:
            dir_path = QFileDialog.getExistingDirectory(
                self, "选择通达信软件根目录", "", QFileDialog.Option.ShowDirsOnly
            )

            if dir_path and self.tdx_path_edit:
                self.tdx_path_edit.setText(dir_path)
                # 自动验证路径
                self._validate_tdx_path()

        except Exception as e:
            self.logger.error("浏览目录失败: %s", e)

    def _browse_cache_dir(self):
        """浏览选择品种缓存目录."""
        try:
            dir_path = QFileDialog.getExistingDirectory(
                self, "选择品种缓存目录", "", QFileDialog.Option.ShowDirsOnly
            )

            if dir_path and self.cache_dir_edit:
                self.cache_dir_edit.setText(dir_path)

        except Exception as e:
            self.logger.error("浏览目录失败: %s", e)

    def _browse_data_dir(self):
        """浏览选择K线数据目录."""
        try:
            dir_path = QFileDialog.getExistingDirectory(
                self, "选择K线数据目录", "", QFileDialog.Option.ShowDirsOnly
            )

            if dir_path and self.data_dir_edit:
                self.data_dir_edit.setText(dir_path)

        except Exception as e:
            self.logger.error("浏览目录失败: %s", e)

    def _validate_tdx_path(self):
        """验证通达信路径."""
        try:
            if not self.tdx_path_edit:
                return

            tdx_path = self.tdx_path_edit.text().strip()
            is_valid, message = self.handlers.validate_tdx_path(tdx_path)

            if is_valid:
                QMessageBox.information(self, "验证成功", message, QMessageBox.StandardButton.Ok)
            else:
                QMessageBox.warning(self, "验证失败", message, QMessageBox.StandardButton.Ok)

        except Exception as e:
            self.logger.error("验证路径失败: %s", e)
            QMessageBox.critical(self, "错误", f"验证路径失败: {e}")

    def _update_config_stats(self):
        """更新配置统计信息."""
        try:
            stats = self.handlers.get_config_statistics()

            if self.cache_dir_label:
                self.cache_dir_label.setText(stats.get("cache_dir", "-"))
            if self.data_dir_label:
                self.data_dir_label.setText(stats.get("data_dir", "-"))
            if self.cache_files_label:
                self.cache_files_label.setText(str(stats.get("cache_files_count", 0)))
            if self.data_symbols_label:
                self.data_symbols_label.setText(str(stats.get("data_symbols_count", 0)))

            if self.tdx_status_label:
                if stats.get("tdx_configured"):
                    self.tdx_status_label.setText("✓ 已配置")
                    self.tdx_status_label.setStyleSheet("color: green;")
                else:
                    self.tdx_status_label.setText("✗ 未配置")
                    self.tdx_status_label.setStyleSheet("color: orange;")

        except Exception as e:
            self.logger.error("更新配置统计失败: %s", e)


# 导出公共接口
__all__ = ["SystemManager"]
