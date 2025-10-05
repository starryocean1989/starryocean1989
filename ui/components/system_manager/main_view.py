# -*- coding: utf-8 -*-
"""
系统管理界面 - 主视图.

标准架构：8个子界面采用选项卡形式.
"""

import logging
import time
from typing import Any, Dict, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QProgressBar, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pyqtgraph as pg
except ImportError:
    pg = None

try:
    from backend.infrastructure.data_module_vnpy.core_adapter import (
        VnPyCoreAdapter as _VnPyAdapter
    )
except ImportError:
    try:
        from backend.core.vnpy_integration import (
            TerminalEngine as _VnPyAdapter
        )
    except ImportError:
        _VnPyAdapter = None

try:
    from ui.widgets.base_widget import BaseWidget
    from utils.logging_utils import LoggerMixin
except ImportError:
    # 简化版本
    class BaseWidget(QWidget):
        """基础组件类."""

        def __init__(self, parent=None, title=""):
            """初始化基础组件."""
            super().__init__(parent)
            self.parent = parent
            self.title = title
            self._timer = None

        def setup_ui(self):
            """Set up UI - fallback implementation."""

        def connect_signals(self):
            """Connect signals - fallback implementation."""

        def start_update_timer(self, interval: int, callback):
            """启动更新定时器."""
            self._timer = QTimer()
            self._timer.timeout.connect(callback)
            self._timer.start(interval)

        def stop_update_timer(self):
            """停止更新定时器."""
            if self._timer:
                self._timer.stop()
                self._timer = None

        def show_info(self, message: str):
            """显示信息."""
            print(f"INFO: {message}")

        def show_error(self, message: str):
            """Show error message."""
            print(f"ERROR: {message}")

        def show_warning(self, message: str):
            """Show warning message."""
            print(f"WARNING: {message}")

    class LoggerMixin:
        """日志混入类."""

        @property
        def logger(self):
            """获取日志记录器."""
            return logging.getLogger(self.__class__.__name__)


class MockVnPyAdapter:
    """模拟VNPY适配器类."""

    def get_status(self):
        """获取模拟状态."""
        return {
            'vnpy_available': False,
            'gateways': [],
            'connected_gateways': False,
            'real_time_worker_running': False,
            'subscribed_symbols': []
        }


class SystemManager(BaseWidget, LoggerMixin):
    """系统管理主界面."""

    def __init__(self, parent=None):
        """初始化系统管理界面."""
        super().__init__(parent, "系统管理")
        self.logger.info("系统管理界面初始化开始")

        # 初始化所有UI组件属性
        self.tab_widget: Optional[QTabWidget] = None
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
        self.vnpy_status_label: Optional[QLabel] = None

        # 性能监控组件
        self.cpu_plot: Optional[Any] = None
        self.cpu_curve: Optional[Any] = None
        self.memory_plot: Optional[Any] = None
        self.memory_curve: Optional[Any] = None
        self.performance_history: Dict[str, list] = {'cpu': [], 'memory': []}
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

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QVBoxLayout(self)

        # 创建选项卡部件
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)

        # 创建8个子界面
        self._create_sub_interfaces()

        main_layout.addWidget(self.tab_widget)

        # 设置样式
        self.setStyleSheet("""
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
        """)

    def _create_sub_interfaces(self):
        """创建8个子界面."""
        # 1.1 系统状态实时监控
        self.system_status_tab = self._create_system_status_tab()
        self.tab_widget.addTab(self.system_status_tab, "🔍 系统状态监控")

        # 1.2 性能指标展示
        self.performance_tab = self._create_performance_tab()
        self.tab_widget.addTab(self.performance_tab, "📊 性能指标")

        # 1.3 告警信息管理
        self.alerts_tab = self._create_alerts_tab()
        self.tab_widget.addTab(self.alerts_tab, "🚨 告警管理")

        # 1.4 服务健康检查
        self.services_tab = self._create_services_tab()
        self.tab_widget.addTab(self.services_tab, "💚 服务检查")

        # 1.5 系统配置
        self.config_tab = self._create_config_tab()
        self.tab_widget.addTab(self.config_tab, "⚙️ 系统配置")

        # 1.6 日志管理
        self.logs_tab = self._create_logs_tab()
        self.tab_widget.addTab(self.logs_tab, "📝 日志管理")

        # 1.7 系统诊断
        self.diagnosis_tab = self._create_diagnosis_tab()
        self.tab_widget.addTab(self.diagnosis_tab, "🔧 系统诊断")

        # 1.8 工具集合
        self.tools_tab = self._create_tools_tab()
        self.tab_widget.addTab(self.tools_tab, "🛠️ 工具集合")

    def _create_system_status_tab(self):
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

    def _create_performance_tab(self):
        """创建性能指标子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 性能图表组
        chart_group = QGroupBox("性能图表")
        chart_layout = QVBoxLayout(chart_group)

        # 性能图表组件
        if pg is not None:
            # 创建性能图表
            chart_widget = QWidget()
            chart_widget_layout = QVBoxLayout(chart_widget)

            # CPU使用率图表
            cpu_win = pg.GraphicsLayoutWidget()
            cpu_win.setBackground(QColor(26, 26, 26))
            self.cpu_plot = cpu_win.addPlot(title="CPU使用率 (%)")
            self.cpu_plot.showGrid(x=True, y=True)
            self.cpu_plot.setRange(yRange=[0, 100])

            pen = pg.mkPen(color='red', width=2)
            self.cpu_curve = self.cpu_plot.plot(pen=pen)

            # 内存使用率图表
            memory_win = pg.GraphicsLayoutWidget()
            memory_win.setBackground(QColor(26, 26, 26))
            self.memory_plot = memory_win.addPlot(title="内存使用率 (%)")
            self.memory_plot.showGrid(x=True, y=True)
            self.memory_plot.setRange(yRange=[0, 100])

            pen = pg.mkPen(color='blue', width=2)
            self.memory_curve = self.memory_plot.plot(pen=pen)

            chart_widget_layout.addWidget(cpu_win)
            chart_widget_layout.addWidget(memory_win)

            chart_layout.addWidget(chart_widget)

        else:
            # 如果pyqtgraph不可用，显示替代内容
            text = ("📈 性能图表区域\n\n" +
                    "需要安装pyqtgraph库以获得完整功能")
            chart_placeholder = QLabel(text)
            chart_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            style = "color: #888; font-size: 14px; padding: 20px;"
            chart_placeholder.setStyleSheet(style)
            chart_layout.addWidget(chart_placeholder)

        layout.addWidget(chart_group)

        # 性能统计组
        stats_group = QGroupBox("性能统计")
        stats_layout = QVBoxLayout(stats_group)

        self.performance_table = QTableWidget(0, 4)
        headers = ["指标", "当前值", "平均值", "峰值"]
        self.performance_table.setHorizontalHeaderLabels(headers)
        header = self.performance_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        stats_layout.addWidget(self.performance_table)

        layout.addWidget(stats_group)

        return tab

    def _create_alerts_tab(self):
        """创建告警管理子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

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

        # 配置组
        config_group = QGroupBox("系统配置")
        config_layout = QFormLayout(config_group)

        self.config_table = QTableWidget(0, 3)
        self.config_table.setHorizontalHeaderLabels(["配置项", "当前值", "描述"])
        header = self.config_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        config_layout.addWidget(self.config_table)

        layout.addWidget(config_group)

        return tab

    def _create_logs_tab(self):
        """创建日志管理子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

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

    def connect_signals(self):
        """连接信号槽."""
        # 初始化VNPY适配器
        self._initialize_vnpy_adapter()

        # 启动状态更新定时器
        self.start_update_timer(2000, self._update_system_status)

    def _initialize_vnpy_adapter(self):
        """初始化VNPY适配器."""
        try:
            if _VnPyAdapter is not None:
                self.vnpy_adapter = _VnPyAdapter()
                self.logger.info("VNPY适配器初始化完成")
            else:
                # 如果无法导入，创建一个模拟适配器
                self.vnpy_adapter = MockVnPyAdapter()
                self.logger.info("使用模拟VNPY适配器")
        except (RuntimeError, AttributeError) as e:
            self.logger.error("VNPY适配器初始化失败: %s", e)
            self.vnpy_adapter = None

    def _update_system_status(self):
        """更新系统状态."""
        try:
            if psutil is None:
                self.logger.warning("psutil库未安装，无法获取系统状态")
                return

            # 更新基础系统信息
            cpu_percent = psutil.cpu_percent()
            self.cpu_label.setText(f"{cpu_percent:.1f}%")

            memory = psutil.virtual_memory()
            self.memory_label.setText(f"{memory.percent:.1f}%")

            disk = psutil.disk_usage('/')
            self.disk_label.setText(f"{disk.percent:.1f}%")

            network = psutil.net_if_addrs()
            self.network_label.setText(f"接口数: {len(network)}")

            # 更新VNPY系统状态
            if self.vnpy_adapter and hasattr(self.vnpy_adapter, 'get_status'):
                vnpy_status = self.vnpy_adapter.get_status()
            else:
                vnpy_status = {}

                # 更新VNPY状态标签
                vnpy_available = vnpy_status.get('vnpy_available', False)
                status_text = "可用" if vnpy_available else "不可用"
                vnpy_status_text = f"VNPY: {status_text} | "

                gateways = vnpy_status.get('gateways', [])
                vnpy_status_text += f"网关: {len(gateways)} | "

                worker_running = vnpy_status.get('real_time_worker_running',
                                                 False)
                worker_text = "运行" if worker_running else "停止"
                vnpy_status_text += f"实时数据: {worker_text}"

                # 添加VNPY状态标签（如果不存在）
                if not hasattr(self, 'vnpy_status_label'):
                    layout = self.system_status_tab.layout()
                    if isinstance(layout, QVBoxLayout):
                        overview_group = layout.itemAt(0).widget()
                        if isinstance(overview_group, QGroupBox):
                            overview_layout = overview_group.layout()
                            if isinstance(overview_layout, QFormLayout):
                                self.vnpy_status_label = QLabel("--")
                                overview_layout.addRow("VNPY状态:",
                                                       self.vnpy_status_label)

                if hasattr(self, 'vnpy_status_label'):
                    self.vnpy_status_label.setText(vnpy_status_text)

            # 更新状态表格
            self._update_status_table()

            # 更新性能图表
            self._update_performance_charts()

        except (AttributeError, RuntimeError) as e:
            self.logger.error("更新系统状态失败: %s", e)

    def _update_performance_charts(self):
        """更新性能图表."""
        try:
            if (psutil is None or not hasattr(self, 'cpu_curve') or
                    self.cpu_curve is None):
                return

            current_time = time.time()

            # 获取当前性能数据
            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent

            # 添加到历史数据
            self.performance_history['cpu'].append((current_time, cpu_percent))
            self.performance_history['memory'].append((current_time,
                                                      memory_percent))

            # 限制历史数据点数量
            for key, history in self.performance_history.items():
                if len(history) > self.max_history_points:
                    self.performance_history[key] = history[
                        -self.max_history_points:]

            # 更新图表
            if self.performance_history['cpu']:
                times, cpu_values = zip(*self.performance_history['cpu'])
                self.cpu_curve.setData(times, cpu_values)

            if self.performance_history['memory']:
                times, memory_values = zip(*self.performance_history['memory'])
                self.memory_curve.setData(times, memory_values)

        except (AttributeError, RuntimeError) as e:
            self.logger.error("更新性能图表失败: %s", e)

    def _update_status_table(self):
        """更新状态表格."""
        try:
            if psutil is None:
                return

            # 清空表格
            self.status_table.setRowCount(0)

            # 基础系统组件状态
            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent
            disk_percent = psutil.disk_usage('/').percent

            base_components = [
                ("CPU", "正常", f"使用率: {cpu_percent:.1f}%"),
                ("内存", "正常", f"使用率: {memory_percent:.1f}%"),
                ("磁盘", "正常", f"使用率: {disk_percent:.1f}%"),
                ("网络", "正常", "连接正常"),
                ("数据库", "正常", "连接正常")
            ]

            # VNPY相关组件状态
            vnpy_components = []
            if self.vnpy_adapter and hasattr(self.vnpy_adapter, 'get_status'):
                vnpy_status = self.vnpy_adapter.get_status()
                vnpy_available = vnpy_status.get('vnpy_available', False)
                gateways = vnpy_status.get('gateways', [])
                worker_running = vnpy_status.get('real_time_worker_running',
                                                 False)
                subscribed = vnpy_status.get('subscribed_symbols', [])

                vnpy_components.extend([
                    ("VNPY引擎", "可用" if vnpy_available else "不可用",
                     f"状态: {'运行' if vnpy_available else '停止'}"),
                    ("交易网关", "正常" if vnpy_status.get('connected_gateways')
                     else "未连接", f"网关数: {len(gateways)}"),
                    ("实时数据", "运行" if worker_running else "停止",
                     f"订阅品种: {len(subscribed)}")
                ])
            else:
                vnpy_components.extend([
                    ("VNPY引擎", "不可用", "VNPY适配器未初始化"),
                    ("交易网关", "未知", "VNPY不可用"),
                    ("实时数据", "停止", "VNPY不可用")
                ])

            # 合并所有组件
            all_components = base_components + vnpy_components

            for i, (component, status, detail) in enumerate(all_components):
                self.status_table.insertRow(i)
                self.status_table.setItem(i, 0, QTableWidgetItem(component))
                self.status_table.setItem(i, 1, QTableWidgetItem(status))
                self.status_table.setItem(i, 2, QTableWidgetItem(detail))

                # 设置状态颜色
                status_item = self.status_table.item(i, 1)
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
        self.logs_table.setRowCount(0)
        self.show_info("日志已清空")

    def _export_logs(self):
        """导出日志."""
        # 这里实现日志导出功能
        self.show_info("日志导出功能开发中...")

    def refresh_data(self):
        """刷新数据."""
        self._update_system_status()
        self.show_info("系统状态已刷新")

    def on_close(self):
        """关闭处理."""
        self.stop_update_timer()
        self.logger.info("系统管理界面已关闭")
