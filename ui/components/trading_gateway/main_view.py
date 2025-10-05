# -*- coding: utf-8 -*-
"""交易网关界面 - 主视图.

混合架构：网关管理器（固有组件）+ 2个子界面.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

try:
    from ui.widgets.base_widget import BaseWidget
    from utils.logging_utils import LoggerMixin
    from backend.core.vnpy_integration import VnPyAdapter as _VnPyAdapter
    VNPY_AVAILABLE = True
except ImportError:
    _VnPyAdapter = None
    VNPY_AVAILABLE = False

    class BaseWidget(QWidget):
        """Base widget class."""

        def __init__(self, parent=None, title=""):
            """Initialize base widget."""
            super().__init__(parent)
            self.parent = parent
            self.title = title

        def setup_ui(self):
            """Set up UI - fallback implementation."""
            # Fallback implementation - no UI setup needed

        def connect_signals(self):
            """Connect signals - fallback implementation."""
            # Fallback implementation - no signals to connect

        def show_info(self, message: str):
            """Show info message."""
            print(f"INFO: {message}")

        def show_error(self, message: str):
            """Show error message."""
            print(f"ERROR: {message}")

        def show_warning(self, message: str):
            """Show warning message."""
            print(f"WARNING: {message}")

    class LoggerMixin:
        """Logger mixin class."""

        @property
        def logger(self):
            """Get logger instance."""
            return logging.getLogger(self.__class__.__name__)


class TradingGateway(BaseWidget, LoggerMixin):
    """交易网关主界面."""

    def __init__(self, parent=None):
        """Initialize trading gateway."""
        super().__init__(parent, "交易网关")
        self.logger.info("交易网关界面初始化开始")

        # Initialize UI components
        self.new_gateway_btn = None
        self.gateways_table = None
        self.content_tab = None
        self.strategy_tab = None
        self.monitor_tab = None
        self.strategy_table = None
        self.deploy_btn = None
        self.start_all_btn = None
        self.stop_all_btn = None
        self.template_combo = None
        self.monitor_table = None
        self.vnpy_adapter = None

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QHBoxLayout(self)

        # 创建主分割器
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setSizes([300, 800])

        # 左侧：网关管理器（固有组件）
        left_widget = self._create_gateway_manager()
        main_splitter.addWidget(left_widget)

        # 右侧：子界面区域
        right_widget = self._create_content_area()
        main_splitter.addWidget(right_widget)

        main_layout.addWidget(main_splitter)

    def _create_gateway_manager(self):
        """创建网关管理器."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("🔗 网关管理器")
        title_label.setStyleSheet(
            "font-weight: bold; font-size: 14px; padding: 5px;"
        )
        title_layout.addWidget(title_label)

        layout.addLayout(title_layout)

        # 新建网关按钮
        self.new_gateway_btn = QPushButton("新建网关")
        self.new_gateway_btn.clicked.connect(self._create_new_gateway)
        layout.addWidget(self.new_gateway_btn)

        # 网关列表
        gateways_group = QGroupBox("网关实例")
        gateways_layout = QVBoxLayout(gateways_group)

        self.gateways_table = QTableWidget(0, 4)
        self.gateways_table.setHorizontalHeaderLabels(
            ["网关名称", "类型", "状态", "操作"]
        )
        self.gateways_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        gateways_layout.addWidget(self.gateways_table)

        layout.addWidget(gateways_group)

        return widget

    def _create_content_area(self):
        """创建内容区域."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 创建选项卡
        self.content_tab = QTabWidget()

        # 5.1 策略实例子界面
        self.strategy_tab = self._create_strategy_tab()
        self.content_tab.addTab(self.strategy_tab, "🚀 策略实例")

        # 5.2 交易监控子界面
        self.monitor_tab = self._create_monitor_tab()
        self.content_tab.addTab(self.monitor_tab, "📊 交易监控")

        layout.addWidget(self.content_tab)

        return widget

    def _create_strategy_tab(self):
        """创建策略实例子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 策略池展示组
        strategy_group = QGroupBox("策略池")
        strategy_layout = QVBoxLayout(strategy_group)

        self.strategy_table = QTableWidget(0, 5)
        self.strategy_table.setHorizontalHeaderLabels(
            ["策略名称", "网关", "状态", "启动时间", "操作"]
        )
        self.strategy_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        strategy_layout.addWidget(self.strategy_table)

        layout.addWidget(strategy_group)

        # 策略控制组
        control_group = QGroupBox("策略控制")
        control_layout = QHBoxLayout(control_group)

        self.deploy_btn = QPushButton("部署新策略")
        self.deploy_btn.clicked.connect(self._deploy_strategy)
        control_layout.addWidget(self.deploy_btn)

        self.start_all_btn = QPushButton("启动所有")
        self.start_all_btn.clicked.connect(self._start_all_strategies)
        control_layout.addWidget(self.start_all_btn)

        self.stop_all_btn = QPushButton("停止所有")
        self.stop_all_btn.clicked.connect(self._stop_all_strategies)
        control_layout.addWidget(self.stop_all_btn)

        layout.addWidget(control_group)

        return tab

    def _create_monitor_tab(self):
        """创建交易监控子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 监控模板选择
        template_group = QGroupBox("监控模板")
        template_layout = QVBoxLayout(template_group)

        self.template_combo = QComboBox()
        self.template_combo.addItems([
            "algotrading - 算法交易监控",
            "ctastrategy - CTA策略监控",
            "optionmaster - 期权策略监控",
            "portfoliostrategy - 组合策略监控",
            "scripttrader - 脚本交易监控",
            "spreadtrading - 价差交易监控"
        ])
        template_layout.addWidget(self.template_combo)

        layout.addWidget(template_group)

        # 监控内容区域
        monitor_group = QGroupBox("监控内容")
        monitor_layout = QVBoxLayout(monitor_group)

        self.monitor_table = QTableWidget(0, 4)
        self.monitor_table.setHorizontalHeaderLabels(
            ["时间", "事件", "详情", "状态"]
        )
        self.monitor_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        monitor_layout.addWidget(self.monitor_table)

        layout.addWidget(monitor_group)

        return tab

    def connect_signals(self):
        """连接信号槽."""
        # 初始化VNPY适配器
        self._initialize_vnpy_adapter()

        # 连接模板选择信号
        self.template_combo.currentTextChanged.connect(
            self._on_template_changed
        )

        # 启动更新定时器
        self.start_update_timer(
            1000, self._update_gateway_status
        )

    def _initialize_vnpy_adapter(self):
        """初始化VNPY适配器."""
        if VNPY_AVAILABLE and _VnPyAdapter:
            try:
                self.vnpy_adapter = _VnPyAdapter()
                self.logger.info("VNPY适配器初始化完成")
            except (ImportError, RuntimeError, AttributeError) as e:
                self.logger.error("VNPY适配器初始化失败: %s", e)
                self.vnpy_adapter = None
        else:
            self.vnpy_adapter = None
            self.logger.warning("VNPY适配器不可用")

    def _create_new_gateway(self):
        """新建网关."""
        self.show_info("新建网关功能开发中...")

    def _deploy_strategy(self):
        """部署策略."""
        self.show_info("部署策略功能开发中...")

    def _start_all_strategies(self):
        """启动所有策略."""
        self.show_info("启动所有策略...")

    def _stop_all_strategies(self):
        """停止所有策略."""
        if self.vnpy_adapter:
            try:
                # 这里可以实现停止所有策略的逻辑
                self.show_info("停止所有策略...")
                self._update_gateway_status()
            except (RuntimeError, AttributeError, ConnectionError) as e:
                self.show_error(f"停止策略失败: {str(e)}")
        else:
            self.show_warning("VNPY适配器不可用")

    def _start_strategy(self, strategy_name):
        """启动策略."""
        if self.vnpy_adapter:
            try:
                # 这里可以实现启动策略的逻辑
                self.show_info(f"启动策略: {strategy_name}")
                self._update_gateway_status()
            except (RuntimeError, AttributeError, ConnectionError) as e:
                self.show_error(f"启动策略失败: {str(e)}")
        else:
            self.show_warning("VNPY适配器不可用")

    def _stop_strategy(self, strategy_name):
        """停止策略."""
        if self.vnpy_adapter:
            try:
                # 这里可以实现停止策略的逻辑
                self.show_info(f"停止策略: {strategy_name}")
                self._update_gateway_status()
            except (RuntimeError, AttributeError, ConnectionError) as e:
                self.show_error(f"停止策略失败: {str(e)}")
        else:
            self.show_warning("VNPY适配器不可用")

    def _on_template_changed(self, text):
        """模板选择改变."""
        self.logger.info("切换监控模板: %s", text)
        # 这里实现模板切换逻辑

    def _update_gateway_status(self):
        """更新网关状态."""
        if self.vnpy_adapter:
            try:
                # 获取网关状态
                if hasattr(self.vnpy_adapter, 'get_status'):
                    status = self.vnpy_adapter.get_status()
                    # 更新网关表格
                    self._update_gateways_table(status)
                else:
                    # 使用模拟状态
                    status = {}
                    self._update_gateways_table({})

                # 更新策略表格
                self._update_strategies_table(status)

            except (RuntimeError, AttributeError, ConnectionError) as e:
                self.logger.error("更新网关状态失败: %s", e)
        else:
            # 无VNPY适配器时使用模拟数据
            self._update_gateways_table_fallback()

    def _update_gateways_table(self, status):
        """更新网关表格."""
        # 清空表格
        self.gateways_table.setRowCount(0)

        gateways = status.get('gateways', [])
        connected_gateways = status.get('connected_gateways', [])

        for i, gateway_name in enumerate(gateways):
            self.gateways_table.insertRow(i)

            # 网关名称
            self.gateways_table.setItem(i, 0, QTableWidgetItem(gateway_name))

            # 网关类型
            gateway_type = "CTP" if "ctp" in gateway_name.lower() else "其他"
            self.gateways_table.setItem(i, 1, QTableWidgetItem(gateway_type))

            # 连接状态
            is_connected = gateway_name in connected_gateways
            status_text = "已连接" if is_connected else "未连接"
            status_color = (
                QColor("#4caf50") if is_connected else QColor("#ff9800")
            )

            status_item = QTableWidgetItem(status_text)
            status_item.setBackground(status_color)
            self.gateways_table.setItem(i, 2, status_item)

            # 操作按钮
            if is_connected:
                disconnect_btn = QPushButton("断开")
                disconnect_btn.clicked.connect(
                    lambda gw=gateway_name: self._disconnect_gateway(gw)
                )
            else:
                connect_btn = QPushButton("连接")
                connect_btn.clicked.connect(
                    lambda gw=gateway_name: self._connect_gateway(gw)
                )

            self.gateways_table.setCellWidget(
                i, 3, connect_btn if not is_connected else disconnect_btn
            )

    def _update_gateways_table_fallback(self):
        """备用网关表格更新（VNPY不可用时）."""
        # 清空表格
        self.gateways_table.setRowCount(0)

        # 模拟网关数据
        gateways_data = [
            ("CTP", "期货", "已连接"),
            ("IB", "国际", "未连接"),
            ("PaperAccount", "模拟", "已连接")
        ]

        for i, (name, type_, status) in enumerate(gateways_data):
            self.gateways_table.insertRow(i)
            self.gateways_table.setItem(i, 0, QTableWidgetItem(name))
            self.gateways_table.setItem(i, 1, QTableWidgetItem(type_))

            status_item = QTableWidgetItem(status)
            if status == "已连接":
                status_item.setBackground(QColor("#4caf50"))
            else:
                status_item.setBackground(QColor("#ff9800"))
            self.gateways_table.setItem(i, 2, status_item)

            # 操作按钮
            btn_text = "断开" if status == "已连接" else "连接"
            btn = QPushButton(btn_text)
            self.gateways_table.setCellWidget(i, 3, btn)

    def _connect_gateway(self, gateway_name):
        """连接网关."""
        if self.vnpy_adapter:
            try:
                # 这里可以实现实际的网关连接逻辑
                result = self.vnpy_adapter.connect_gateway(
                    gateway_name, {}
                )
                if result.get('success', False):
                    self.show_info(f"网关 {gateway_name} 连接成功")
                    self._update_gateway_status()
                else:
                    self.show_error(
                        f"网关 {gateway_name} 连接失败: "
                        f"{result.get('message', '未知错误')}"
                    )
            except (RuntimeError, AttributeError, ConnectionError) as e:
                self.show_error(f"连接网关失败: {str(e)}")
        else:
            self.show_warning("VNPY适配器不可用")

    def _disconnect_gateway(self, gateway_name):
        """断开网关."""
        if self.vnpy_adapter:
            try:
                result = self.vnpy_adapter.disconnect_gateway(gateway_name)
                if result.get('success', False):
                    self.show_info(f"网关 {gateway_name} 已断开")
                    self._update_gateway_status()
                else:
                    self.show_error(
                        f"断开网关失败: "
                        f"{result.get('message', '未知错误')}"
                    )
            except (RuntimeError, AttributeError, ConnectionError) as e:
                self.show_error(f"断开网关失败: {str(e)}")
        else:
            self.show_warning("VNPY适配器不可用")

    def _update_strategies_table(self, status):
        """更新策略表格."""
        # 清空表格
        self.strategy_table.setRowCount(0)

        # 获取策略信息（这里可以从VNPY获取实际策略信息）
        strategies = [
            ("双均线策略", "CTP", "运行中", "2024-01-01 09:30:00"),
            ("RSI策略", "CTP", "停止", "2024-01-01 10:00:00"),
            ("MACD策略", "IB", "运行中", "2024-01-01 09:45:00")
        ]

        for i, (name, gateway, status, start_time) in enumerate(strategies):
            self.strategy_table.insertRow(i)
            self.strategy_table.setItem(i, 0, QTableWidgetItem(name))
            self.strategy_table.setItem(i, 1, QTableWidgetItem(gateway))

            status_item = QTableWidgetItem(status)
            if status == "运行中":
                status_item.setBackground(QColor("#4caf50"))
            else:
                status_item.setBackground(QColor("#ff9800"))
            self.strategy_table.setItem(i, 2, status_item)

            self.strategy_table.setItem(i, 3, QTableWidgetItem(start_time))

            # 操作按钮
            if status == "运行中":
                stop_btn = QPushButton("停止")
                stop_btn.clicked.connect(
                    lambda s=name: self._stop_strategy(s)
                )
            else:
                start_btn = QPushButton("启动")
                start_btn.clicked.connect(
                    lambda s=name: self._start_strategy(s)
                )

            self.strategy_table.setCellWidget(
                i, 4, start_btn if status != "运行中" else stop_btn
            )

    def refresh_data(self):
        """刷新数据."""
        self.show_info("交易网关数据已刷新")

    def on_close(self):
        """关闭处理."""
        self.stop_update_timer()
        self.logger.info("交易网关界面已关闭")
