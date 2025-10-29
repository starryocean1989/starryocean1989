# -*- coding: utf-8 -*-
"""交易网关界面 - 主视图（重构版）.

混合架构：网关管理器（固有组件）+ 2个子界面。
通过TradingGatewayService访问网关和策略功能。
"""
import logging
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt

# UI层专用logger
logger_user = logging.getLogger("ui.user_feedback")

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.core.base import get_service_manager
from backend.core.service_base import LoggerMixin

from ui.components.widgets import BaseWidget


# 网关类型配置
GATEWAY_TYPES = {
    "ctp": "国内期货、期权",
    "ctp_mini": "国内期货、期权（迷你版）",
    "sopt": "国内ETF期权",
    "tts": "国内期货仿真交易",
    "ib": "海外证券、期货、期权、贵金属",
    "paperaccount": "纯本地模拟交易",
    "tdx": "国内股票交易（TradeX）",
}


class TradingGateway(BaseWidget, LoggerMixin):
    """交易网关主界面（重构版）."""

    def __init__(self, parent=None):
        """初始化交易网关."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.trading_service: Optional[Any] = None

        # 初始化UI组件
        self.new_gateway_btn: Optional[QPushButton] = None
        self.gateways_table: Optional[QTableWidget] = None
        self.content_tab: Optional[QTabWidget] = None
        self.strategy_tab: Optional[QWidget] = None
        self.monitor_tab: Optional[QWidget] = None
        self.strategy_table: Optional[QTableWidget] = None
        self.deploy_btn: Optional[QPushButton] = None
        self.start_all_btn: Optional[QPushButton] = None
        self.stop_all_btn: Optional[QPushButton] = None
        self.template_combo: Optional[QComboBox] = None
        self.monitor_table: Optional[QTableWidget] = None
        self.monitor_container: Optional[QWidget] = None
        self.monitor_layout: Optional[QVBoxLayout] = None

        # 调用父类初始化
        super().__init__(parent, "交易网关")
        self.logger.info("交易网关界面初始化开始")

        # 初始化服务
        self._initialize_service()

    def _initialize_service(self):
        """获取交易网关服务."""
        try:
            # 从服务管理器获取交易网关服务
            self.trading_service = self.service_manager.get_service("trading_gateway_service")
            if self.trading_service is not None:
                self.logger.info("交易网关服务获取成功")
            else:
                self.logger.warning("交易网关服务未注册")
        except Exception as e:
            self.logger.error("获取交易网关服务失败: %s", e)
            self.show_error(f"服务获取失败: {e}")
            self.trading_service = None

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

    # ==================== 网关管理器（固有组件） ====================

    def _create_gateway_manager(self) -> QWidget:
        """创建网关管理器."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 标题栏
        title_label = QLabel("🔗 网关管理器")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        # 新建网关按钮
        self.new_gateway_btn = QPushButton("新建网关")
        self.new_gateway_btn.clicked.connect(self._create_new_gateway)
        layout.addWidget(self.new_gateway_btn)

        # 网关列表
        gateways_group = QGroupBox("网关实例")
        gateways_layout = QVBoxLayout(gateways_group)

        self.gateways_table = QTableWidget(0, 4)
        self.gateways_table.setHorizontalHeaderLabels(["网关名称", "类型", "状态", "操作"])
        header = self.gateways_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # 设置选择模式：整行选择，单选
        self.gateways_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.gateways_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        # 监听网关选择事件，切换对应的策略池
        self.gateways_table.itemSelectionChanged.connect(self._on_gateway_selected)

        gateways_layout.addWidget(self.gateways_table)
        layout.addWidget(gateways_group)

        return widget

    # ==================== 内容区域 ====================

    def _create_content_area(self) -> QWidget:
        """创建内容区域."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.content_tab = QTabWidget()

        # 5.1 策略实例子界面
        self.strategy_tab = self._create_strategy_tab()
        self.content_tab.addTab(self.strategy_tab, "🚀 策略实例")

        # 5.2 交易监控子界面
        self.monitor_tab = self._create_monitor_tab()
        self.content_tab.addTab(self.monitor_tab, "📊 交易监控")

        layout.addWidget(self.content_tab)

        return widget

    # ==================== 策略实例子界面 ====================

    def _create_strategy_tab(self) -> QWidget:
        """创建策略实例子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 策略池组
        strategy_group = QGroupBox("策略池")
        strategy_layout = QVBoxLayout(strategy_group)

        self.strategy_table = QTableWidget(0, 5)
        self.strategy_table.setHorizontalHeaderLabels(
            ["策略名称", "网关", "状态", "启动时间", "操作"]
        )
        header = self.strategy_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # 设置选择模式：整行选择（提升用户体验）
        self.strategy_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.strategy_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

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

    # ==================== 交易监控子界面 ====================

    def _create_monitor_tab(self) -> QWidget:
        """创建交易监控子界面（支持差异化策略监控）."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 策略类型选择组
        template_group = QGroupBox("策略类型")
        template_layout = QHBoxLayout(template_group)

        self.template_combo = QComboBox()
        strategy_types = [
            "CTA策略",
            "算法交易",
            "期权策略",
            "组合策略",
            "价差交易",
            "脚本交易",
            "通用监控",
        ]
        self.template_combo.addItems(strategy_types)
        self.template_combo.currentTextChanged.connect(self._on_strategy_type_changed)
        template_layout.addWidget(QLabel("当前策略类型:"))
        template_layout.addWidget(self.template_combo)
        template_layout.addStretch()

        layout.addWidget(template_group)

        # 监控内容容器（动态切换）
        self.monitor_container = QWidget()
        self.monitor_layout = QVBoxLayout(self.monitor_container)
        layout.addWidget(self.monitor_container)

        # 创建默认监控界面
        self._create_default_monitor()

        return tab

    def _on_strategy_type_changed(self, strategy_type: str):
        """策略类型切换事件."""
        # 清空容器
        if self.monitor_layout is not None:
            while self.monitor_layout.count():
                child = self.monitor_layout.takeAt(0)
                widget = child.widget()
                if widget is not None:
                    widget.deleteLater()

        # 根据策略类型创建对应监控界面
        if strategy_type == "CTA策略":
            self._create_cta_monitor()
        elif strategy_type == "算法交易":
            self._create_algo_monitor()
        elif strategy_type == "期权策略":
            self._create_option_monitor()
        elif strategy_type == "组合策略":
            self._create_portfolio_monitor()
        elif strategy_type == "价差交易":
            self._create_spread_monitor()
        elif strategy_type == "脚本交易":
            self._create_script_monitor()
        else:
            self._create_default_monitor()

    def _create_default_monitor(self):
        """创建默认监控界面（通用）- 集成VnPy核心监控组件."""
        from backend.core.base import get_event_engine
        from ui.components.basic_monitors import (
            OrderMonitor,
            TradeMonitor,
            PositionMonitor,
            AccountMonitor,
        )

        # 获取事件引擎
        event_engine = get_event_engine()

        # 获取当前选中的网关名称（用于数据过滤）
        gateway_name = self._get_selected_gateway_name() or ""

        # 创建监控选项卡（VnPy核心4监控 + 自定义监控）
        monitor_tabs = QTabWidget()

        # Tab 1: 资金监控
        account_monitor = AccountMonitor(event_engine, gateway_name, self)
        monitor_tabs.addTab(account_monitor, "💰 资金")

        # Tab 2: 持仓监控
        position_monitor = PositionMonitor(event_engine, gateway_name, self)
        monitor_tabs.addTab(position_monitor, "📊 持仓")

        # Tab 3: 订单监控
        order_monitor = OrderMonitor(event_engine, gateway_name, self)
        monitor_tabs.addTab(order_monitor, "📝 订单")

        # Tab 4: 成交监控
        trade_monitor = TradeMonitor(event_engine, gateway_name, self)
        monitor_tabs.addTab(trade_monitor, "✅ 成交")

        # Tab 5: 事件日志（自定义）
        log_group = QGroupBox("事件日志")
        log_layout = QVBoxLayout(log_group)

        self.monitor_table = QTableWidget(0, 6)
        self.monitor_table.setHorizontalHeaderLabels(
            ["时间", "策略", "事件", "品种", "详情", "状态"]
        )
        header = self.monitor_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        log_layout.addWidget(self.monitor_table)
        monitor_tabs.addTab(log_group, "📋 日志")

        # 添加到主布局
        if self.monitor_layout is not None:
            self.monitor_layout.addWidget(monitor_tabs)

        self.logger.info("✅ 已集成VnPy核心监控组件（资金、持仓、订单、成交）")

    def _create_cta_monitor(self):
        """创建CTA策略专用监控界面 - 集成VnPy核心监控."""
        from backend.core.base import get_event_engine
        from ui.components.basic_monitors import (
            OrderMonitor,
            TradeMonitor,
            PositionMonitor,
            AccountMonitor,
        )

        # 获取事件引擎和网关名称
        event_engine = get_event_engine()
        gateway_name = self._get_selected_gateway_name() or ""

        # 创建监控选项卡
        monitor_tabs = QTabWidget()

        # VnPy核心监控组件
        monitor_tabs.addTab(AccountMonitor(event_engine, gateway_name, self), "💰 资金")
        monitor_tabs.addTab(PositionMonitor(event_engine, gateway_name, self), "📊 持仓")
        monitor_tabs.addTab(OrderMonitor(event_engine, gateway_name, self), "📝 订单")
        monitor_tabs.addTab(TradeMonitor(event_engine, gateway_name, self), "✅ 成交")

        # 尝试添加vnpy_ctastrategy原生组件
        try:
            from vnpy_ctastrategy.ui import CtaManager

            if (
                self.trading_service
                and hasattr(self.trading_service, "main_engine")
                and self.trading_service.main_engine is not None
            ):
                cta_widget = CtaManager(
                    self.trading_service.main_engine, self.trading_service.event_engine
                )
                monitor_tabs.addTab(cta_widget, "🎯 CTA管理器")
                self.logger.info("已加载vnpy_ctastrategy专用监控组件")
        except ImportError:
            self.logger.warning("vnpy_ctastrategy UI组件不可用")

        if self.monitor_layout is not None:
            self.monitor_layout.addWidget(monitor_tabs)

    def _create_algo_monitor(self):
        """创建算法交易专用监控界面 - 集成VnPy核心监控."""
        from backend.core.base import get_event_engine
        from ui.components.basic_monitors import (
            OrderMonitor,
            TradeMonitor,
            PositionMonitor,
            AccountMonitor,
        )

        # 获取事件引擎和网关名称
        event_engine = get_event_engine()
        gateway_name = self._get_selected_gateway_name() or ""

        # 创建监控选项卡
        monitor_tabs = QTabWidget()

        # VnPy核心监控组件
        monitor_tabs.addTab(AccountMonitor(event_engine, gateway_name, self), "💰 资金")
        monitor_tabs.addTab(PositionMonitor(event_engine, gateway_name, self), "📊 持仓")
        monitor_tabs.addTab(OrderMonitor(event_engine, gateway_name, self), "📝 订单")
        monitor_tabs.addTab(TradeMonitor(event_engine, gateway_name, self), "✅ 成交")

        # 算法交易专用监控
        if self.trading_service:
            algo_widget = AlgoMonitorWidget(gateway_name, self.trading_service, self)
            monitor_tabs.addTab(algo_widget, "⚡ 算法监控")

        # 尝试添加vnpy_algotrading原生组件
        try:
            from vnpy_algotrading.ui import AlgoManager

            if (
                self.trading_service
                and hasattr(self.trading_service, "main_engine")
                and self.trading_service.main_engine is not None
            ):
                algo_manager = AlgoManager(
                    self.trading_service.main_engine, self.trading_service.event_engine
                )
                monitor_tabs.addTab(algo_manager, "🎯 Algo管理器")
                self.logger.info("已加载vnpy_algotrading原生组件")
        except ImportError:
            self.logger.warning("vnpy_algotrading UI组件不可用")

        if self.monitor_layout is not None:
            self.monitor_layout.addWidget(monitor_tabs)

    def _create_option_monitor(self):
        """创建期权策略专用监控界面 - 集成VnPy核心监控."""
        from backend.core.base import get_event_engine
        from ui.components.basic_monitors import (
            OrderMonitor,
            TradeMonitor,
            PositionMonitor,
            AccountMonitor,
        )

        # 获取事件引擎和网关名称
        event_engine = get_event_engine()
        gateway_name = self._get_selected_gateway_name() or ""

        # 创建监控选项卡
        monitor_tabs = QTabWidget()

        # VnPy核心监控组件
        monitor_tabs.addTab(AccountMonitor(event_engine, gateway_name, self), "💰 资金")
        monitor_tabs.addTab(PositionMonitor(event_engine, gateway_name, self), "📊 持仓")
        monitor_tabs.addTab(OrderMonitor(event_engine, gateway_name, self), "📝 订单")
        monitor_tabs.addTab(TradeMonitor(event_engine, gateway_name, self), "✅ 成交")

        # 期权专用监控
        if self.trading_service:
            option_widget = OptionMonitorWidget(gateway_name, self.trading_service, self)
            monitor_tabs.addTab(option_widget, "📈 期权监控")

        # 尝试添加vnpy_optionmaster原生组件
        try:
            from vnpy_optionmaster.ui import OptionManager

            if (
                self.trading_service
                and hasattr(self.trading_service, "main_engine")
                and self.trading_service.main_engine is not None
            ):
                option_manager = OptionManager(
                    self.trading_service.main_engine, self.trading_service.event_engine
                )
                monitor_tabs.addTab(option_manager, "🎯 Option管理器")
                self.logger.info("已加载vnpy_optionmaster原生组件")
        except ImportError:
            self.logger.warning("vnpy_optionmaster UI组件不可用")

        if self.monitor_layout is not None:
            self.monitor_layout.addWidget(monitor_tabs)

    def _create_portfolio_monitor(self):
        """创建组合策略专用监控界面 - 集成VnPy核心监控."""
        from backend.core.base import get_event_engine
        from ui.components.basic_monitors import (
            OrderMonitor,
            TradeMonitor,
            PositionMonitor,
            AccountMonitor,
        )

        # 获取事件引擎和网关名称
        event_engine = get_event_engine()
        gateway_name = self._get_selected_gateway_name() or ""

        # 创建监控选项卡
        monitor_tabs = QTabWidget()

        # VnPy核心监控组件
        monitor_tabs.addTab(AccountMonitor(event_engine, gateway_name, self), "💰 资金")
        monitor_tabs.addTab(PositionMonitor(event_engine, gateway_name, self), "📊 持仓")
        monitor_tabs.addTab(OrderMonitor(event_engine, gateway_name, self), "📝 订单")
        monitor_tabs.addTab(TradeMonitor(event_engine, gateway_name, self), "✅ 成交")

        # 组合策略专用监控
        if self.trading_service:
            portfolio_widget = PortfolioMonitorWidget(gateway_name, self.trading_service, self)
            monitor_tabs.addTab(portfolio_widget, "📊 组合监控")

        # 尝试添加vnpy_portfoliostrategy原生组件
        portfolio_widget = None
        try:
            from vnpy_portfoliostrategy.ui import PortfolioStrategyManager

            if (
                self.trading_service
                and hasattr(self.trading_service, "main_engine")
                and self.trading_service.main_engine is not None
            ):
                portfolio_manager = PortfolioStrategyManager(
                    self.trading_service.main_engine, self.trading_service.event_engine
                )
                monitor_tabs.addTab(portfolio_manager, "🎯 Portfolio管理器")
            self.logger.info("已加载vnpy_portfoliostrategy原生组件")
        except ImportError:
            self.logger.warning("vnpy_portfoliostrategy UI组件不可用")

        if self.monitor_layout is not None:
            self.monitor_layout.addWidget(monitor_tabs)

    def _create_spread_monitor(self):
        """创建价差交易专用监控界面 - 集成VnPy核心监控."""
        from backend.core.base import get_event_engine
        from ui.components.basic_monitors import (
            OrderMonitor,
            TradeMonitor,
            PositionMonitor,
            AccountMonitor,
        )

        # 获取事件引擎和网关名称
        event_engine = get_event_engine()
        gateway_name = self._get_selected_gateway_name() or ""

        # 创建监控选项卡
        monitor_tabs = QTabWidget()

        # VnPy核心监控组件
        monitor_tabs.addTab(AccountMonitor(event_engine, gateway_name, self), "💰 资金")
        monitor_tabs.addTab(PositionMonitor(event_engine, gateway_name, self), "📊 持仓")
        monitor_tabs.addTab(OrderMonitor(event_engine, gateway_name, self), "📝 订单")
        monitor_tabs.addTab(TradeMonitor(event_engine, gateway_name, self), "✅ 成交")

        # 尝试添加vnpy_spreadtrading原生组件
        try:
            from vnpy_spreadtrading.ui import SpreadManager

            if (
                self.trading_service
                and hasattr(self.trading_service, "main_engine")
                and self.trading_service.main_engine is not None
            ):
                spread_widget = SpreadManager(
                    self.trading_service.main_engine, self.trading_service.event_engine
                )
                monitor_tabs.addTab(spread_widget, "🎯 Spread管理器")
                self.logger.info("已加载vnpy_spreadtrading原生组件")
        except ImportError:
            self.logger.warning("vnpy_spreadtrading UI组件不可用")

        if self.monitor_layout is not None:
            self.monitor_layout.addWidget(monitor_tabs)

    def _create_script_monitor(self):
        """创建脚本交易专用监控界面 - 集成VnPy核心监控."""
        from backend.core.base import get_event_engine
        from ui.components.basic_monitors import (
            OrderMonitor,
            TradeMonitor,
            PositionMonitor,
            AccountMonitor,
        )

        # 获取事件引擎和网关名称
        event_engine = get_event_engine()
        gateway_name = self._get_selected_gateway_name() or ""

        # 创建监控选项卡
        monitor_tabs = QTabWidget()

        # VnPy核心监控组件
        monitor_tabs.addTab(AccountMonitor(event_engine, gateway_name, self), "💰 资金")
        monitor_tabs.addTab(PositionMonitor(event_engine, gateway_name, self), "📊 持仓")
        monitor_tabs.addTab(OrderMonitor(event_engine, gateway_name, self), "📝 订单")
        monitor_tabs.addTab(TradeMonitor(event_engine, gateway_name, self), "✅ 成交")

        # 尝试添加vnpy_scripttrader原生组件
        try:
            from vnpy_scripttrader.ui import ScriptManager

            if (
                self.trading_service
                and hasattr(self.trading_service, "main_engine")
                and self.trading_service.main_engine is not None
            ):
                script_widget = ScriptManager(
                    self.trading_service.main_engine, self.trading_service.event_engine
                )
                monitor_tabs.addTab(script_widget, "🎯 Script管理器")
                self.logger.info("已加载vnpy_scripttrader原生组件")
        except (ImportError, AttributeError):
            self.logger.warning("vnpy_scripttrader UI组件不可用")

        if self.monitor_layout is not None:
            self.monitor_layout.addWidget(monitor_tabs)

    # ==================== 事件处理 ====================

    def _create_new_gateway(self):
        """新建网关."""
        dialog = QDialog(self)
        dialog.setWindowTitle("新建交易网关")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)
        form_layout = QFormLayout()

        # 网关类型选择
        gateway_type_combo = QComboBox()
        gateway_types = [f"{k} - {v}" for k, v in GATEWAY_TYPES.items()]
        gateway_type_combo.addItems(gateway_types)
        form_layout.addRow("网关类型:", gateway_type_combo)

        # 动态表单容器
        dynamic_form_layout = QFormLayout()
        form_layout.addRow(dynamic_form_layout)

        # 存储动态字段
        dynamic_fields: Dict[str, Any] = {}

        def update_form(gateway_type_text: str):
            """更新表单字段."""
            while dynamic_form_layout.rowCount() > 0:
                dynamic_form_layout.removeRow(0)
            dynamic_fields.clear()

            gateway_type = gateway_type_text.split(" - ")[0]

            # 通用字段
            name_input = QLineEdit()
            name_input.setPlaceholderText("输入网关名称...")
            dynamic_form_layout.addRow("网关名称:", name_input)
            dynamic_fields["name"] = name_input

            # 根据网关类型添加不同字段
            if gateway_type in ["ctp", "ctp_mini"]:
                user_input = QLineEdit()
                user_input.setPlaceholderText("输入用户名...")
                dynamic_form_layout.addRow("用户名:", user_input)
                dynamic_fields["user"] = user_input

                password_input = QLineEdit()
                password_input.setPlaceholderText("输入密码...")
                password_input.setEchoMode(QLineEdit.EchoMode.Password)
                dynamic_form_layout.addRow("密码:", password_input)
                dynamic_fields["password"] = password_input

                server_input = QLineEdit()
                server_input.setPlaceholderText("输入服务器地址...")
                dynamic_form_layout.addRow("服务器地址:", server_input)
                dynamic_fields["server"] = server_input

                broker_input = QLineEdit()
                broker_input.setPlaceholderText("输入经纪商代码...")
                dynamic_form_layout.addRow("经纪商代码:", broker_input)
                dynamic_fields["broker"] = broker_input

            elif gateway_type == "sopt":
                user_input = QLineEdit()
                user_input.setPlaceholderText("输入用户名...")
                dynamic_form_layout.addRow("用户名:", user_input)
                dynamic_fields["user"] = user_input

                password_input = QLineEdit()
                password_input.setPlaceholderText("输入密码...")
                password_input.setEchoMode(QLineEdit.EchoMode.Password)
                dynamic_form_layout.addRow("密码:", password_input)
                dynamic_fields["password"] = password_input

                server_input = QLineEdit()
                server_input.setPlaceholderText("输入服务器地址...")
                dynamic_form_layout.addRow("服务器地址:", server_input)
                dynamic_fields["server"] = server_input

                auth_input = QLineEdit()
                auth_input.setPlaceholderText("输入授权码...")
                dynamic_form_layout.addRow("授权码:", auth_input)
                dynamic_fields["auth_code"] = auth_input

            elif gateway_type == "tts":
                user_input = QLineEdit()
                user_input.setPlaceholderText("输入用户名...")
                dynamic_form_layout.addRow("用户名:", user_input)
                dynamic_fields["user"] = user_input

                password_input = QLineEdit()
                password_input.setPlaceholderText("输入密码...")
                password_input.setEchoMode(QLineEdit.EchoMode.Password)
                dynamic_form_layout.addRow("密码:", password_input)
                dynamic_fields["password"] = password_input

                server_input = QLineEdit()
                server_input.setPlaceholderText("输入服务器地址...")
                dynamic_form_layout.addRow("服务器地址:", server_input)
                dynamic_fields["server"] = server_input

            elif gateway_type == "ib":
                host_input = QLineEdit()
                host_input.setPlaceholderText("默认: 127.0.0.1")
                host_input.setText("127.0.0.1")
                dynamic_form_layout.addRow("服务器地址:", host_input)
                dynamic_fields["host"] = host_input

                port_input = QSpinBox()
                port_input.setRange(1, 65535)
                port_input.setValue(7497)
                dynamic_form_layout.addRow("端口:", port_input)
                dynamic_fields["port"] = port_input

                client_id_input = QSpinBox()
                client_id_input.setRange(1, 999)
                client_id_input.setValue(1)
                dynamic_form_layout.addRow("客户号:", client_id_input)
                dynamic_fields["client_id"] = client_id_input

                account_input = QLineEdit()
                account_input.setPlaceholderText("输入账户ID...")
                dynamic_form_layout.addRow("账户ID:", account_input)
                dynamic_fields["account"] = account_input

            elif gateway_type == "paperaccount":
                capital_input = QSpinBox()
                capital_input.setRange(10000, 100000000)
                capital_input.setValue(1000000)
                capital_input.setSingleStep(10000)
                dynamic_form_layout.addRow("初始资金:", capital_input)
                dynamic_fields["capital"] = capital_input

            elif gateway_type == "tdx":
                server_ip_input = QLineEdit()
                server_ip_input.setPlaceholderText("券商服务器IP")
                dynamic_form_layout.addRow("服务器IP:", server_ip_input)
                dynamic_fields["server_ip"] = server_ip_input

                port_input = QSpinBox()
                port_input.setRange(1, 65535)
                port_input.setValue(7708)
                dynamic_form_layout.addRow("服务器端口:", port_input)
                dynamic_fields["port"] = port_input

                version_input = QLineEdit()
                version_input.setPlaceholderText("例如: 6.40")
                version_input.setText("6.40")
                dynamic_form_layout.addRow("客户端版本:", version_input)
                dynamic_fields["version"] = version_input

                yyb_id_input = QLineEdit()
                yyb_id_input.setPlaceholderText("营业部ID")
                dynamic_form_layout.addRow("营业部ID:", yyb_id_input)
                dynamic_fields["yyb_id"] = yyb_id_input

                account_input = QLineEdit()
                account_input.setPlaceholderText("登录账号")
                dynamic_form_layout.addRow("登录账号:", account_input)
                dynamic_fields["account"] = account_input

                trade_account_input = QLineEdit()
                trade_account_input.setPlaceholderText("交易账号")
                dynamic_form_layout.addRow("交易账号:", trade_account_input)
                dynamic_fields["trade_account"] = trade_account_input

                password_input = QLineEdit()
                password_input.setPlaceholderText("交易密码")
                password_input.setEchoMode(QLineEdit.EchoMode.Password)
                dynamic_form_layout.addRow("交易密码:", password_input)
                dynamic_fields["password"] = password_input

                comm_password_input = QLineEdit()
                comm_password_input.setPlaceholderText("通讯密码")
                comm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
                dynamic_form_layout.addRow("通讯密码:", comm_password_input)
                dynamic_fields["comm_password"] = comm_password_input

        update_form(gateway_type_combo.currentText())
        gateway_type_combo.currentTextChanged.connect(update_form)

        layout.addLayout(form_layout)

        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            gateway_type = gateway_type_combo.currentText().split(" - ")[0]

            # 安全获取网关名称
            name_field = dynamic_fields.get("name")
            gateway_name = name_field.text() if name_field else ""

            # 验证网关名称
            if not gateway_name:
                self.show_error("请输入网关名称")
                return

            # 构建配置
            config = {}
            for key, field in dynamic_fields.items():
                if key != "name":
                    if isinstance(field, QLineEdit):
                        config[key] = field.text()
                    elif isinstance(field, QSpinBox):
                        config[key] = field.value()

            # 调用后端服务创建网关
            if not self.trading_service:
                self.show_error("交易网关服务不可用")
                return

            try:
                result = self.trading_service.create_gateway(gateway_name, gateway_type, config)

                if result.get("success"):
                    # 创建成功后添加到列表
                    display_config = {
                        "name": gateway_name,
                        "type": gateway_type,
                    }
                    self._add_gateway_to_list(display_config)
                    self.show_info(f"网关 '{gateway_name}' 创建成功")
                else:
                    error_msg = result.get("message", "未知错误")
                    self.show_error(f"创建网关失败: {error_msg}")
            except Exception as e:
                self.show_error(f"创建网关时发生错误: {str(e)}")
                self.logger.error(f"创建网关失败: {e}", exc_info=True)

    def _add_gateway_to_list(self, config: dict):
        """添加网关到列表."""
        if not self.gateways_table:
            return

        row = self.gateways_table.rowCount()
        self.gateways_table.insertRow(row)

        self.gateways_table.setItem(row, 0, QTableWidgetItem(config.get("name", "")))
        self.gateways_table.setItem(row, 1, QTableWidgetItem(config.get("type", "")))
        self.gateways_table.setItem(row, 2, QTableWidgetItem("未连接"))

        # 操作按钮
        op_widget = QWidget()
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(2, 2, 2, 2)

        # 连接/断开按钮（可动态切换）
        connect_btn = QPushButton("连接")
        connect_btn.setProperty("row", row)
        connect_btn.setProperty("connected", False)
        connect_btn.clicked.connect(
            lambda checked, btn=connect_btn: self._toggle_gateway_connection(btn)
        )
        op_layout.addWidget(connect_btn)

        delete_btn = QPushButton("删除")
        delete_btn.clicked.connect(lambda checked, r=row: self._delete_gateway(r))
        op_layout.addWidget(delete_btn)

        self.gateways_table.setCellWidget(row, 3, op_widget)

    def _toggle_gateway_connection(self, button: QPushButton):
        """切换网关连接/断开."""
        row = button.property("row")
        is_connected = button.property("connected")

        if is_connected:
            # 当前已连接，执行断开操作
            self._disconnect_gateway_ui(row, button)
        else:
            # 当前未连接，执行连接操作
            self._connect_gateway_ui(row, button)

    def _connect_gateway_ui(self, row: int, button: QPushButton):
        """连接网关（UI版本）."""
        if not self.gateways_table:
            return

        gateway_item = self.gateways_table.item(row, 0)
        if not gateway_item:
            return

        gateway_name = gateway_item.text()

        # 检查服务是否可用
        if not self.trading_service:
            self.show_error("交易网关服务不可用")
            return

        # 获取网关类型
        type_item = self.gateways_table.item(row, 1)
        if not type_item:
            self.show_error("无法获取网关类型")
            return

        gateway_type = type_item.text()

        # 记录用户连接网关操作
        logger_user.info("用户连接网关: 名称=%s, 类型=%s", gateway_name, gateway_type)

        # 对于需要密码的网关，弹出密码输入对话框
        password = None
        if gateway_type != "paperaccount":
            from PySide6.QtWidgets import QInputDialog

            password, ok = QInputDialog.getText(
                self,
                "输入密码",
                f"请输入网关 '{gateway_name}' 的密码:",
                QLineEdit.EchoMode.Password,
            )
            if not ok:
                return

        # 设置连接中状态
        self.gateways_table.setItem(row, 2, QTableWidgetItem("连接中..."))
        self.show_info(f"正在连接网关: {gateway_name}")

        # 调用后端服务连接网关
        try:
            result = self.trading_service.connect_gateway(gateway_name, password)

            if result.get("success"):
                self.gateways_table.setItem(row, 2, QTableWidgetItem("已连接"))
                button.setText("断开")
                button.setProperty("connected", True)
                self.show_info(f"网关 '{gateway_name}' 连接成功")
            else:
                self.gateways_table.setItem(row, 2, QTableWidgetItem("连接失败"))
                error_msg = result.get("message", "未知错误")
                self.show_error(f"网关连接失败: {error_msg}")
        except Exception as e:
            self.gateways_table.setItem(row, 2, QTableWidgetItem("连接失败"))
            self.show_error(f"连接网关时发生错误: {str(e)}")
            self.logger.error(f"连接网关失败: {e}", exc_info=True)

    def _disconnect_gateway_ui(self, row: int, button: QPushButton):
        """断开网关（UI版本）."""
        if not self.gateways_table:
            return

        gateway_item = self.gateways_table.item(row, 0)
        if not gateway_item:
            return

        gateway_name = gateway_item.text()

        # 记录用户断开网关操作
        logger_user.info("用户断开网关: 名称=%s", gateway_name)

        # 检查服务是否可用
        if not self.trading_service:
            self.show_error("交易网关服务不可用")
            return

        # 设置断开中状态
        self.gateways_table.setItem(row, 2, QTableWidgetItem("断开中..."))
        self.show_info(f"正在断开网关: {gateway_name}")

        # 调用后端服务断开网关
        try:
            result = self.trading_service.disconnect_gateway(gateway_name)

            if result.get("success"):
                self.gateways_table.setItem(row, 2, QTableWidgetItem("未连接"))
                button.setText("连接")
                button.setProperty("connected", False)
                self.show_info(f"网关 '{gateway_name}' 已断开")
            else:
                self.gateways_table.setItem(row, 2, QTableWidgetItem("断开失败"))
                error_msg = result.get("message", "未知错误")
                self.show_error(f"网关断开失败: {error_msg}")
        except Exception as e:
            self.gateways_table.setItem(row, 2, QTableWidgetItem("断开失败"))
            self.show_error(f"断开网关时发生错误: {str(e)}")
            self.logger.error(f"断开网关失败: {e}", exc_info=True)

    def _connect_gateway(self, row: int):
        """连接网关（保留兼容）."""
        # 获取按钮
        if self.gateways_table:
            op_widget = self.gateways_table.cellWidget(row, 3)
            if op_widget:
                connect_btn = op_widget.findChild(QPushButton)
                if connect_btn:
                    self._connect_gateway_ui(row, connect_btn)

    def _delete_gateway(self, row: int):
        """删除网关."""
        if not self.gateways_table:
            return

        gateway_item = self.gateways_table.item(row, 0)
        gateway_name = gateway_item.text() if gateway_item else "未知网关"

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除网关 '{gateway_name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 调用后端服务删除网关
            if self.trading_service:
                try:
                    result = self.trading_service.delete_gateway(gateway_name)
                    if result.get("success"):
                        self.gateways_table.removeRow(row)
                        self.show_info(f"已删除网关: {gateway_name}")
                    else:
                        error_msg = result.get("message", "未知错误")
                        self.show_error(f"删除网关失败: {error_msg}")
                except Exception as e:
                    self.show_error(f"删除网关时发生错误: {str(e)}")
                    self.logger.error(f"删除网关失败: {e}", exc_info=True)
            else:
                # 如果服务不可用，至少从界面删除
                self.gateways_table.removeRow(row)
                self.show_info(f"已从界面删除网关: {gateway_name}")

    def _deploy_strategy(self):
        """部署策略."""
        if not self.trading_service:
            self.show_error("交易网关服务不可用")
            return

        # 创建策略部署对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("部署策略")
        dialog.setModal(True)
        dialog.resize(700, 600)

        layout = QVBoxLayout(dialog)

        # 表单布局
        form_layout = QFormLayout()

        # 1. 网关选择（下拉框）
        gateway_combo = QComboBox()
        current_gateway = self._get_selected_gateway_name()  # 获取当前选中的网关
        if self.trading_service:
            try:
                gateways = self.trading_service.list_gateways()
                for gw in gateways:
                    gateway_combo.addItem(gw["name"])

                # 默认选中当前网关
                if current_gateway:
                    index = gateway_combo.findText(current_gateway)
                    if index >= 0:
                        gateway_combo.setCurrentIndex(index)
            except Exception as e:
                self.logger.error(f"获取网关列表失败: {e}")
        form_layout.addRow("选择网关:", gateway_combo)

        # 2. 通过StrategyCenter服务API获取策略列表（重构版）
        self.logger.info("通过strategy_center_service获取策略列表...")

        # 获取策略中心服务
        strategy_service = self.service_manager.get_service("strategy_center_service")
        if not strategy_service:
            self.show_error("策略中心服务不可用")
            return

        # 调用API获取策略列表
        strategies_result = strategy_service.get_available_strategies()

        if not strategies_result.get("success"):
            self.show_error(f"获取策略列表失败: {strategies_result.get('message', '未知错误')}")
            return

        all_strategies = strategies_result.get("strategies", [])
        available_folders = strategies_result.get("folders", [])

        self.logger.info(f"获取到 {len(all_strategies)} 个策略，{len(available_folders)} 个文件夹")

        # 策略文件夹选择（下拉框）
        folder_combo = QComboBox()
        folder_combo.addItem("-- 请选择策略文件夹 --")

        # 添加文件夹选项
        if "根目录" in available_folders:
            folder_combo.addItem("根目录")
        for folder in available_folders:
            if folder != "根目录":
                folder_combo.addItem(folder)

        form_layout.addRow("策略文件夹:", folder_combo)

        # 策略文件选择（下拉框）
        strategy_file_combo = QComboBox()
        strategy_file_combo.addItem("-- 请先选择文件夹 --")
        strategy_file_combo.setEnabled(False)

        strategy_class_map = {}  # 存储策略类名和策略信息的映射

        # 当选择文件夹时，更新策略文件列表
        def on_folder_selected(folder_text):
            strategy_file_combo.clear()
            strategy_class_map.clear()

            if folder_text == "-- 请选择策略文件夹 --":
                strategy_file_combo.addItem("-- 请先选择文件夹 --")
                strategy_file_combo.setEnabled(False)
                return

            strategy_file_combo.setEnabled(True)
            strategy_file_combo.addItem("-- 请选择策略文件 --")

            # 筛选该文件夹下的策略
            folder_strategies = [s for s in all_strategies if s["folder"] == folder_text]

            if not folder_strategies:
                strategy_file_combo.addItem("(该文件夹无策略文件)")
                return

            # 添加策略到下拉框
            for strategy in folder_strategies:
                display_text = strategy["display_name"]
                strategy_file_combo.addItem(display_text)
                strategy_class_map[display_text] = strategy

            self.logger.info(f"文件夹 '{folder_text}' 有 {len(folder_strategies)} 个策略")

        folder_combo.currentTextChanged.connect(on_folder_selected)
        form_layout.addRow("策略文件:", strategy_file_combo)

        # 4. 策略名称（可编辑下拉框 - 显示已有实例名称 + 自动生成）
        strategy_name_combo = QComboBox()
        strategy_name_combo.setEditable(True)
        strategy_name_combo.addItem("-- 自动生成 --")

        # 加载已有策略实例名称作为参考
        try:
            if self.trading_service and gateway_combo.currentText():
                existing_strategies = self.trading_service.list_strategies(
                    gateway_combo.currentText()
                )
                for strat in existing_strategies:
                    strategy_name_combo.addItem(strat["name"] + "_new")
        except Exception as e:
            self.logger.debug(f"加载已有策略名称失败: {e}")

        form_layout.addRow("策略名称:", strategy_name_combo)

        # 5. 交易品种池（增强版）
        symbols_group = QGroupBox("交易品种池")
        symbols_layout = QVBoxLayout(symbols_group)

        # 品种池列表
        from PySide6.QtWidgets import QListWidget

        symbols_list = QListWidget()
        symbols_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )  # 支持Ctrl/Shift多选
        symbols_list.setMinimumHeight(150)
        symbols_list.setMaximumHeight(200)

        # 增强选中视觉效果
        symbols_list.setStyleSheet(
            """
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QListWidget::item {
                padding: 5px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
            }
            QListWidget::item:hover {
                background-color: #e5f3ff;
            }
        """
        )

        symbols_layout.addWidget(symbols_list)

        # 操作按钮栏
        buttons_layout = QHBoxLayout()

        # 添加品种按钮
        add_symbol_btn = QPushButton("➕ 添加品种")
        add_symbol_btn.setToolTip("搜索并添加单个品种")
        buttons_layout.addWidget(add_symbol_btn)

        # 批量添加品种按钮
        batch_add_btn = QPushButton("📋 批量添加")
        batch_add_btn.setToolTip("粘贴品种代码批量添加")
        buttons_layout.addWidget(batch_add_btn)

        # 删除品种按钮
        remove_symbol_btn = QPushButton("➖ 删除品种")
        remove_symbol_btn.setToolTip("删除选中的品种")
        buttons_layout.addWidget(remove_symbol_btn)

        # 删除全部按钮
        clear_all_btn = QPushButton("🗑️ 删除全部")
        clear_all_btn.setToolTip("清空品种池")
        buttons_layout.addWidget(clear_all_btn)

        symbols_layout.addLayout(buttons_layout)

        # 统计信息
        symbol_count_label = QLabel("品种数量: 0")
        symbol_count_label.setStyleSheet("color: #666; font-size: 11px;")
        symbols_layout.addWidget(symbol_count_label)

        layout.addWidget(symbols_group)

        # 6. 策略引擎特定参数组
        engine_params_group = QGroupBox("策略引擎参数")
        engine_params_layout = QFormLayout(engine_params_group)

        # 动态参数字段容器
        engine_param_widgets: Dict[str, Any] = {}

        # 根据引擎类型显示不同的参数输入框
        def update_engine_params(folder_text: str):
            """根据文件夹名称推测引擎类型并更新参数输入"""
            # 清除现有参数
            while engine_params_layout.rowCount() > 0:
                engine_params_layout.removeRow(0)
            engine_param_widgets.clear()

            # 推测引擎类型
            folder_lower = folder_text.lower()

            if "spread" in folder_lower:
                # 价差交易策略：需要 spread_name
                spread_name_input = QLineEdit()
                spread_name_input.setPlaceholderText("例如: rb2501-rb2505 (价差组合名称)")
                engine_params_layout.addRow("价差名称 (spread_name):", spread_name_input)
                engine_param_widgets["spread_name"] = spread_name_input

                hint = QLabel("💡 价差名称用于标识价差组合，如：rb2501-rb2505")
                hint.setStyleSheet("color: #666; font-size: 11px;")
                engine_params_layout.addRow("", hint)

            elif "portfolio" in folder_lower:
                # 组合策略：提示将使用vt_symbols
                hint = QLabel("✓ 组合策略将使用上方品种池中的所有品种")
                hint.setStyleSheet("color: #0078d4; font-size: 11px;")
                engine_params_layout.addRow(hint)

            elif "cta" in folder_lower or folder_text == "根目录":
                # CTA策略：提示将使用第一个品种
                hint = QLabel("✓ CTA策略将使用品种池中的第一个品种")
                hint.setStyleSheet("color: #0078d4; font-size: 11px;")
                engine_params_layout.addRow(hint)

            elif "algo" in folder_lower:
                # 算法交易：提示不支持
                hint = QLabel("⚠️ 算法交易引擎不支持通过策略池部署")
                hint.setStyleSheet("color: #ff9800; font-size: 11px;")
                engine_params_layout.addRow(hint)

            elif "script" in folder_lower:
                # 脚本交易：提示不支持
                hint = QLabel("⚠️ 脚本交易引擎不支持通过策略池部署")
                hint.setStyleSheet("color: #ff9800; font-size: 11px;")
                engine_params_layout.addRow(hint)

            elif "option" in folder_lower:
                # 期权策略：提示不支持
                hint = QLabel("⚠️ 期权分析引擎不支持通过策略池部署")
                hint.setStyleSheet("color: #ff9800; font-size: 11px;")
                engine_params_layout.addRow(hint)

        # 连接文件夹选择变化事件
        folder_combo.currentTextChanged.connect(update_engine_params)

        layout.addWidget(engine_params_group)

        # 获取可用品种列表（用于搜索）
        available_symbols = self._get_available_symbols()

        # 更新品种数量显示
        def update_count():
            count = symbols_list.count()
            symbol_count_label.setText(f"品种数量: {count}")

        # 添加品种对话框
        def add_single_symbol():
            """添加单个品种（带搜索）"""
            from PySide6.QtWidgets import QCompleter
            from PySide6.QtCore import Qt

            search_dialog = QDialog(dialog)
            search_dialog.setWindowTitle("搜索并添加品种")
            search_dialog.setMinimumWidth(400)

            search_layout = QVBoxLayout(search_dialog)

            # 搜索输入框
            search_label = QLabel("输入品种代码或名称：")
            search_layout.addWidget(search_label)

            search_input = QLineEdit()
            search_input.setPlaceholderText("例如: 600000, rb2401, IF2312...")

            # 自动补全
            completer = QCompleter(available_symbols)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            search_input.setCompleter(completer)

            search_layout.addWidget(search_input)

            # 搜索结果列表
            result_list = QListWidget()
            result_list.setMaximumHeight(300)

            # 增强搜索结果视觉效果
            result_list.setStyleSheet(
                """
                QListWidget::item {
                    padding: 6px;
                    border-bottom: 1px solid #f0f0f0;
                }
                QListWidget::item:selected {
                    background-color: #0078d4;
                    color: white;
                    font-weight: bold;
                }
                QListWidget::item:hover {
                    background-color: #e5f3ff;
                }
            """
            )

            search_layout.addWidget(result_list)

            # 结果数量提示
            result_count_label = QLabel("输入关键词搜索品种")
            result_count_label.setStyleSheet("color: #666; font-size: 11px;")
            search_layout.addWidget(result_count_label)

            # 搜索函数
            def do_search():
                keyword = search_input.text().strip().lower()
                result_list.clear()
                if keyword:
                    matches = [s for s in available_symbols if keyword in s.lower()]
                    result_count_label.setText(f"找到 {len(matches)} 个匹配品种，显示前50个")
                    for match in matches[:50]:  # 显示前50个结果
                        result_list.addItem(match)
                else:
                    result_count_label.setText("输入关键词搜索品种")

            search_input.textChanged.connect(do_search)
            result_list.itemDoubleClicked.connect(lambda: search_dialog.accept())

            # 按钮
            btn_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            btn_box.accepted.connect(search_dialog.accept)
            btn_box.rejected.connect(search_dialog.reject)
            search_layout.addWidget(btn_box)

            if search_dialog.exec() == QDialog.DialogCode.Accepted:
                # 只添加从搜索结果中选中的品种
                selected_item = result_list.currentItem()
                if selected_item:
                    symbol = selected_item.text()
                    # 验证品种在样本空间中
                    if symbol not in available_symbols:
                        QMessageBox.warning(
                            dialog, "品种无效", f"品种 '{symbol}' 不在可用列表中，无法添加"
                        )
                        return

                    # 检查是否已存在
                    existing = [symbols_list.item(i).text() for i in range(symbols_list.count())]
                    if symbol not in existing:
                        symbols_list.addItem(symbol)
                        update_count()
                    else:
                        QMessageBox.information(dialog, "提示", f"品种 '{symbol}' 已在列表中")
                else:
                    # 没有选中搜索结果，提示用户
                    QMessageBox.warning(dialog, "未选择品种", "请从搜索结果中选择一个品种")

        # 批量添加品种对话框
        def batch_add_symbols():
            """批量添加品种"""
            from PySide6.QtWidgets import QTextEdit

            batch_dialog = QDialog(dialog)
            batch_dialog.setWindowTitle("批量添加品种")
            batch_dialog.setMinimumSize(500, 400)

            batch_layout = QVBoxLayout(batch_dialog)

            hint_text = QLabel(
                "💡 粘贴品种代码（支持空格、逗号、换行分隔）：\n"
                "例如: 600000.SSE 600036.SSE rb2401.SHFE IF2312.CFFEX"
            )
            hint_text.setWordWrap(True)
            batch_layout.addWidget(hint_text)

            text_edit = QTextEdit()
            text_edit.setPlaceholderText("在此粘贴品种代码...")
            batch_layout.addWidget(text_edit)

            btn_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            btn_box.accepted.connect(batch_dialog.accept)
            btn_box.rejected.connect(batch_dialog.reject)
            batch_layout.addWidget(btn_box)

            if batch_dialog.exec() == QDialog.DialogCode.Accepted:
                text = text_edit.toPlainText()
                # 分割文本（支持空格、逗号、换行）
                import re

                symbols_input = re.split(r"[\s,，\n\r]+", text)
                symbols_input = [s.strip() for s in symbols_input if s.strip()]

                # 添加品种（只添加在样本空间中的品种）
                existing = [symbols_list.item(i).text() for i in range(symbols_list.count())]
                added_count = 0
                duplicate_count = 0
                invalid_count = 0
                invalid_symbols = []

                for symbol in symbols_input:
                    if not symbol:
                        continue

                    if symbol in existing:
                        duplicate_count += 1
                    elif symbol in available_symbols:
                        # 品种在样本空间中，可以添加
                        symbols_list.addItem(symbol)
                        existing.append(symbol)
                        added_count += 1
                    else:
                        # 品种不在样本空间中，记录无效品种
                        invalid_count += 1
                        if len(invalid_symbols) < 10:  # 最多显示10个无效品种
                            invalid_symbols.append(symbol)

                update_count()

                # 构建提示消息
                msg = f"成功添加 {added_count} 个品种"
                if duplicate_count > 0:
                    msg += f"\n重复品种: {duplicate_count} 个（已自动过滤）"
                if invalid_count > 0:
                    msg += f"\n无效品种: {invalid_count} 个（不在可用列表中）"
                    if invalid_symbols:
                        msg += f"\n示例: {', '.join(invalid_symbols[:5])}"
                        if invalid_count > 5:
                            msg += "..."

                QMessageBox.information(dialog, "批量添加完成", msg)

        # 删除选中品种
        def remove_selected_symbols():
            """删除选中的品种"""
            selected_items = symbols_list.selectedItems()
            if not selected_items:
                QMessageBox.warning(dialog, "提示", "请先选择要删除的品种")
                return

            for item in selected_items:
                row = symbols_list.row(item)
                symbols_list.takeItem(row)

            update_count()

        # 删除全部品种
        def clear_all_symbols():
            """清空品种池"""
            if symbols_list.count() == 0:
                return

            reply = QMessageBox.question(
                dialog,
                "确认清空",
                f"确定要清空所有 {symbols_list.count()} 个品种吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                symbols_list.clear()
                update_count()

        # 绑定按钮事件
        add_symbol_btn.clicked.connect(add_single_symbol)
        batch_add_btn.clicked.connect(batch_add_symbols)
        remove_symbol_btn.clicked.connect(remove_selected_symbols)
        clear_all_btn.clicked.connect(clear_all_symbols)

        layout.addLayout(form_layout)

        # 当选择策略文件时，自动更新策略名称
        def on_file_selected(text):
            if text != "-- 请选择策略文件 --" and text in strategy_class_map:
                class_name = strategy_class_map[text]["class_name"]

                # 自动生成策略名称
                if strategy_name_combo.currentText() == "-- 自动生成 --":
                    # 查找同类策略的数量，生成递增编号
                    count = 1
                    if self.trading_service and gateway_combo.currentText():
                        try:
                            existing_strategies = self.trading_service.list_strategies(
                                gateway_combo.currentText()
                            )
                            existing_names = [
                                s["name"]
                                for s in existing_strategies
                                if s["name"].startswith(class_name)
                            ]
                            count = len(existing_names) + 1
                        except Exception:
                            pass
                    strategy_name_combo.setCurrentText(f"{class_name}_{count}")

        strategy_file_combo.currentTextChanged.connect(on_file_selected)

        # 提示信息
        hint_label = QLabel(
            "💡 使用说明：\n"
            "1. 选择网关：从已创建的网关中选择\n"
            "2. 选择策略文件夹：选择策略所在的文件夹\n"
            "3. 选择策略文件：系统自动识别策略类\n"
            "4. 策略名称：自动生成或手动输入\n"
            "5. 交易品种池：点击【添加品种】或【批量添加】按钮添加品种"
        )
        hint_label.setStyleSheet(
            "color: #666; padding: 10px; background: #f0f0f0; border-radius: 5px; font-size: 12px;"
        )
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 获取表单数据
            gateway_name = gateway_combo.currentText()
            folder_text = folder_combo.currentText()
            strategy_file_text = strategy_file_combo.currentText()
            strategy_name = strategy_name_combo.currentText().strip()

            # 获取品种池中的所有品种
            selected_symbols = [symbols_list.item(i).text() for i in range(symbols_list.count())]

            # 验证必填项
            if not gateway_name:
                self.show_error("请选择网关")
                return

            if folder_text == "-- 请选择策略文件夹 --":
                self.show_error("请选择策略文件夹")
                return

            if (
                strategy_file_text == "-- 请选择策略文件 --"
                or strategy_file_text == "-- 请先选择文件夹 --"
            ):
                self.show_error("请选择策略文件")
                return

            if strategy_file_text == "(该文件夹无策略文件)":
                self.show_error("所选文件夹中没有策略文件")
                return

            if not strategy_name or strategy_name == "-- 自动生成 --":
                self.show_error("请输入策略名称")
                return

            if not selected_symbols:
                self.show_error("请至少选择一个交易品种")
                return

            # 获取策略信息（从API返回的结构化数据）
            strategy_info = strategy_class_map[strategy_file_text]
            strategy_class = strategy_info["class_name"]

            # 使用API返回的引擎类型（已正确识别）
            engine_type_raw = strategy_info.get("engine_type", "ctastrategy")

            # 转换为MainEngine需要的格式（首字母大写驼峰）
            engine_type_mapping = {
                "ctastrategy": "CtaStrategy",
                "algotrading": "AlgoTrading",
                "portfoliostrategy": "PortfolioStrategy",
                "optionmaster": "OptionMaster",
                "scripttrader": "ScriptTrader",
                "spreadtrading": "SpreadTrading",
            }
            engine_type = engine_type_mapping.get(engine_type_raw, "CtaStrategy")

            # 构建策略参数
            strategy_params = {
                "engine_type": engine_type,
                "vt_symbols": selected_symbols,
            }

            # 添加引擎特定参数（基于识别的引擎类型）
            if engine_type_raw == "spreadtrading":
                # 价差交易策略：需要 spread_name
                if "spread_name" in engine_param_widgets:
                    spread_name = engine_param_widgets["spread_name"].text().strip()
                    if not spread_name:
                        self.show_error("请输入价差名称 (spread_name)")
                        return
                    strategy_params["spread_name"] = spread_name
                else:
                    self.show_error("价差交易策略需要 spread_name 参数")
                    return

            # 调用服务部署策略
            result = self.trading_service.deploy_strategy(
                gateway_name=gateway_name,
                strategy_name=strategy_name,
                strategy_class=strategy_class,
                strategy_params=strategy_params,
            )

            if result.get("success"):
                self.logger.info(f"✓ 策略 '{strategy_name}' 部署到网关 '{gateway_name}' 成功")
                self.show_info(f"策略 '{strategy_name}' 部署成功")
                self.refresh_data()
            else:
                error_msg = result.get("message", "未知错误")
                self.logger.error(f"✗ 策略部署失败: {error_msg}")
                self.show_error(f"策略部署失败: {error_msg}")

    def _get_available_symbols(self):
        """获取可用合约列表（从品种列表缓存）."""
        symbols = []

        try:
            # 从品种列表缓存文件读取
            from pathlib import Path
            import json

            cache_file = Path("data/cache/stock_list_classified.json")

            if cache_file.exists():
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)

                # 提取所有分类下的品种
                classified = cache_data.get("classified", {})

                # 合并所有分类的品种，并添加交易所后缀
                for market, codes in classified.items():
                    for code in codes:
                        # 根据市场添加交易所后缀
                        if "上证" in market or market.startswith("SSE"):
                            symbols.append(f"{code}.SSE")
                        elif "深证" in market or market.startswith("SZSE"):
                            symbols.append(f"{code}.SZSE")
                        elif "北证" in market or market.startswith("BSE"):
                            symbols.append(f"{code}.BSE")
                        else:
                            # 其他分类（基金等）默认上海
                            symbols.append(f"{code}.SSE")

                self.logger.info(f"从品种列表缓存加载了 {len(symbols)} 个合约")
            else:
                self.logger.warning(f"品种列表缓存文件不存在: {cache_file}")

        except Exception as e:
            self.logger.error(f"从品种列表缓存加载失败: {e}", exc_info=True)

        # 如果缓存加载失败，添加一些常用期货合约
        if not symbols:
            symbols = [
                # 期货合约
                "rb2401.SHFE",
                "rb2405.SHFE",  # 螺纹钢
                "hc2401.SHFE",
                "hc2405.SHFE",  # 热卷
                "i2401.DCE",
                "i2405.DCE",  # 铁矿石
                "IF2312.CFFEX",
                "IF2403.CFFEX",  # 股指期货
                "IC2312.CFFEX",
                "IC2403.CFFEX",  # 中证500
                "IH2312.CFFEX",
                "IH2403.CFFEX",  # 上证50
                "au2402.SHFE",
                "au2406.SHFE",  # 黄金
                "ag2402.SHFE",
                "ag2406.SHFE",  # 白银
                # 常用股票示例
                "600000.SSE",
                "600036.SSE",
                "600519.SSE",  # 浦发、招行、茅台
                "000001.SZSE",
                "000002.SZSE",
                "000858.SZSE",  # 平安、万科、五粮液
            ]
            self.logger.info(f"使用默认合约列表，共 {len(symbols)} 个")

        return symbols

    def _start_all_strategies(self):
        """启动当前选中网关的所有策略."""
        if not self.trading_service:
            self.show_error("交易网关服务不可用")
            return

        # 获取当前选中的网关
        gateway_name = self._get_selected_gateway_name()
        if not gateway_name:
            self.show_error("请先选择一个网关")
            return

        # 确认对话框
        reply = QMessageBox.question(
            self,
            "确认启动",
            f"确定要启动网关 '{gateway_name}' 的所有策略吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                result = self.trading_service.start_all_strategies(gateway_name)
                if result.get("success"):
                    count = result.get("count", 0)
                    self.show_info(f"成功启动 {count} 个策略")
                    self.refresh_data()
                else:
                    self.show_error(f"启动失败: {result.get('message', '未知错误')}")
            except Exception as e:
                self.show_error(f"启动所有策略时发生错误: {str(e)}")
                self.logger.error(f"启动所有策略失败: {e}", exc_info=True)

    def _stop_all_strategies(self):
        """停止当前选中网关的所有策略."""
        if not self.trading_service:
            self.show_error("交易网关服务不可用")
            return

        # 获取当前选中的网关
        gateway_name = self._get_selected_gateway_name()
        if not gateway_name:
            self.show_error("请先选择一个网关")
            return

        # 确认对话框
        reply = QMessageBox.question(
            self,
            "确认停止",
            f"确定要停止网关 '{gateway_name}' 的所有策略吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                result = self.trading_service.stop_all_strategies(gateway_name)
                if result.get("success"):
                    count = result.get("count", 0)
                    self.show_info(f"成功停止 {count} 个策略")
                    self.refresh_data()
                else:
                    self.show_error(f"停止失败: {result.get('message', '未知错误')}")
            except Exception as e:
                self.show_error(f"停止所有策略时发生错误: {str(e)}")
                self.logger.error(f"停止所有策略失败: {e}", exc_info=True)

    # ==================== 通用方法 ====================

    def _on_content_tab_changed(self, index: int):
        """处理内容区Tab切换事件."""
        # 当用户切换到监控Tab（index=1）时，更新监控界面显示
        if index == 1:
            self._check_and_update_monitor_display()

    def connect_signals(self):
        """连接信号槽."""
        # 监听Tab切换事件，在用户切换到监控Tab时更新监控界面
        if self.content_tab:
            self.content_tab.currentChanged.connect(self._on_content_tab_changed)

        # ✨ 监听策略状态变化事件，实现自动监控适配
        self._register_strategy_status_listener()

        # 使用延迟加载确保UI和服务都已就绪
        from PySide6.QtCore import QTimer

        QTimer.singleShot(100, self._load_existing_gateways)

    def refresh_data(self):
        """刷新数据."""
        self.logger.info("=" * 50)
        self.logger.info("开始刷新交易网关数据...")
        self.logger.info("=" * 50)

        self._load_existing_gateways()
        # _load_existing_gateways 会调用 _select_gateway_by_name，
        # 而 _select_gateway_by_name 会调用 _load_strategies
        # 所以这里不需要再次调用 _load_strategies

        # 如果当前正在监控Tab，更新监控界面显示
        if self.content_tab and self.content_tab.currentIndex() == 1:
            self._check_and_update_monitor_display()

        self.show_info("交易网关数据已刷新")

        self.logger.info("=" * 50)
        self.logger.info("交易网关数据刷新完成")
        self.logger.info("=" * 50)

    def _load_existing_gateways(self):
        """加载已保存的网关到列表."""
        if not self.trading_service or not self.gateways_table:
            self.logger.warning("_load_existing_gateways: 服务或表格不可用")
            return

        try:
            # 保存当前选中的网关名称
            selected_gateway = self._get_selected_gateway_name()
            self.logger.info(f"当前选中的网关: '{selected_gateway}'")

            # 清空现有列表
            self.gateways_table.setRowCount(0)

            # 获取网关列表
            gateways = self.trading_service.list_gateways()
            gateway_names = [g["name"] for g in gateways]
            self.logger.info(f"从后端获取到 {len(gateways)} 个网关: {gateway_names}")

            # 添加到表格
            for gateway in gateways:
                config = {
                    "name": gateway["name"],
                    "type": gateway["type"],
                }
                self._add_gateway_to_list(config)

                # 更新连接状态
                row = self.gateways_table.rowCount() - 1
                if gateway.get("connected"):
                    self.gateways_table.setItem(row, 2, QTableWidgetItem("已连接"))

            self.logger.info(f"✓ 已添加 {len(gateways)} 个网关到表格")

            # 恢复之前的选择状态
            if selected_gateway:
                self.logger.info(f"尝试恢复选中网关: '{selected_gateway}'")
                self._select_gateway_by_name(selected_gateway)
            elif len(gateways) > 0:
                # 如果之前没有选中的网关，但有网关存在，自动选中第一个
                first_gateway_name = gateways[0]["name"]
                self.logger.info(f"之前没有选中的网关，自动选中第一个: '{first_gateway_name}'")
                self._select_gateway_by_name(first_gateway_name)
            else:
                self.logger.info("没有可用的网关")

        except Exception as e:
            self.logger.error(f"加载网关列表失败: {e}", exc_info=True)

    def _on_gateway_selected(self):
        """网关选择事件处理 - 切换对应的策略池."""
        self._load_strategies()

    def _get_selected_gateway_name(self) -> Optional[str]:
        """获取当前选中的网关名称.

        Returns:
            str: 网关名称，如果没有选中则返回 None
        """
        if not self.gateways_table:
            return None

        current_row = self.gateways_table.currentRow()
        if current_row < 0:
            return None

        gateway_item = self.gateways_table.item(current_row, 0)
        if not gateway_item:
            return None

        return gateway_item.text()

    def _select_gateway_by_name(self, gateway_name: str):
        """根据网关名称选中对应的网关.

        Args:
            gateway_name: 要选中的网关名称
        """
        if not self.gateways_table or not gateway_name:
            return

        self.logger.info(f"尝试选中网关: {gateway_name}")

        # 遍历表格，找到对应的网关并选中
        for row in range(self.gateways_table.rowCount()):
            item = self.gateways_table.item(row, 0)
            if item and item.text() == gateway_name:
                self.gateways_table.selectRow(row)
                self.logger.info(f"✓ 已选中网关: {gateway_name} (第 {row} 行)")
                # 手动触发策略加载，因为selectRow可能不会触发itemSelectionChanged信号
                self._load_strategies()
                return

        # 如果没找到，选中第一个网关
        if self.gateways_table.rowCount() > 0:
            self.gateways_table.selectRow(0)
            first_gateway = self.gateways_table.item(0, 0)
            first_gateway_name = first_gateway.text() if first_gateway else "未知"
            self.logger.info(f"未找到网关 '{gateway_name}'，已选中第一个网关: {first_gateway_name}")
            # 手动触发策略加载
            self._load_strategies()

    def _load_strategies(self):
        """加载当前选中网关的策略到策略池表格."""
        if not self.trading_service or not self.strategy_table:
            self.logger.warning("_load_strategies: 服务或表格不可用")
            return

        try:
            # 清空现有列表
            self.strategy_table.setRowCount(0)

            # 获取当前选中的网关
            gateway_name = self._get_selected_gateway_name()
            self.logger.info(f"_load_strategies: 当前选中网关 = '{gateway_name}'")

            if not gateway_name:
                self.logger.warning("未选中任何网关，策略池为空")
                return

            # 加载该网关的策略列表
            try:
                self.logger.info(f"正在从后端获取网关 '{gateway_name}' 的策略列表...")
                strategies = self.trading_service.list_strategies(gateway_name)
                self.logger.info(
                    f"后端返回 {len(strategies)} 个策略: {[s.get('name') for s in strategies]}"
                )

                for strategy in strategies:
                    self.logger.debug(f"添加策略到表格: {strategy}")
                    self._add_strategy_to_table(gateway_name, strategy)

                self.logger.info(f"✓ 已加载网关 '{gateway_name}' 的 {len(strategies)} 个策略到表格")

            except Exception as e:
                self.logger.error(f"获取网关 {gateway_name} 的策略列表失败: {e}", exc_info=True)

        except Exception as e:
            self.logger.error(f"加载策略列表失败: {e}", exc_info=True)

    def _add_strategy_to_table(self, gateway_name: str, strategy: dict):
        """添加策略到策略池表格.

        Args:
            gateway_name: 网关名称
            strategy: 策略信息字典，包含 name, class, status, deploy_time
        """
        if not self.strategy_table:
            return

        row = self.strategy_table.rowCount()
        self.strategy_table.insertRow(row)

        # 策略名称
        self.strategy_table.setItem(row, 0, QTableWidgetItem(strategy.get("name", "")))

        # 网关名称
        self.strategy_table.setItem(row, 1, QTableWidgetItem(gateway_name))

        # 状态
        status = strategy.get("status", "unknown")
        status_text = {
            "running": "运行中",
            "stopped": "已停止",
            "deployed": "已部署",
            "error": "错误",
        }.get(status, str(status))
        self.strategy_table.setItem(row, 2, QTableWidgetItem(status_text))

        # 启动时间
        deploy_time = strategy.get("deploy_time", "")
        self.strategy_table.setItem(row, 3, QTableWidgetItem(deploy_time))

        # 操作按钮
        op_widget = QWidget()
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(2, 2, 2, 2)

        strategy_name = strategy.get("name", "")

        # 启动/停止按钮
        if status == "running":
            control_btn = QPushButton("停止")
            control_btn.clicked.connect(
                lambda checked, gw=gateway_name, st=strategy_name: self._stop_strategy(gw, st)
            )
        else:
            control_btn = QPushButton("启动")
            control_btn.clicked.connect(
                lambda checked, gw=gateway_name, st=strategy_name: self._start_strategy(gw, st)
            )
        op_layout.addWidget(control_btn)

        # 删除按钮
        delete_btn = QPushButton("删除")
        delete_btn.clicked.connect(
            lambda checked, gw=gateway_name, st=strategy_name: self._remove_strategy(gw, st)
        )
        op_layout.addWidget(delete_btn)

        self.strategy_table.setCellWidget(row, 4, op_widget)

    def _start_strategy(self, gateway_name: str, strategy_name: str):
        """启动策略."""
        if not self.trading_service:
            self.show_error("交易网关服务不可用")
            return

        try:
            result = self.trading_service.start_strategy(gateway_name, strategy_name)
            if result.get("success"):
                self.show_info(f"策略 '{strategy_name}' 已启动")
                self.refresh_data()
            else:
                self.show_error(f"启动策略失败: {result.get('message', '未知错误')}")
        except Exception as e:
            self.show_error(f"启动策略时发生错误: {str(e)}")
            self.logger.error(f"启动策略失败: {e}", exc_info=True)

    def _stop_strategy(self, gateway_name: str, strategy_name: str):
        """停止策略."""
        if not self.trading_service:
            self.show_error("交易网关服务不可用")
            return

        try:
            result = self.trading_service.stop_strategy(gateway_name, strategy_name)
            if result.get("success"):
                self.show_info(f"策略 '{strategy_name}' 已停止")
                self.refresh_data()
            else:
                self.show_error(f"停止策略失败: {result.get('message', '未知错误')}")
        except Exception as e:
            self.show_error(f"停止策略时发生错误: {str(e)}")
            self.logger.error(f"停止策略失败: {e}", exc_info=True)

    def _remove_strategy(self, gateway_name: str, strategy_name: str):
        """删除策略."""
        if not self.trading_service:
            self.show_error("交易网关服务不可用")
            return

        # 确认对话框
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除策略 '{strategy_name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                result = self.trading_service.remove_strategy(gateway_name, strategy_name)
                if result.get("success"):
                    self.show_info(f"策略 '{strategy_name}' 已删除")
                    self.refresh_data()
                else:
                    self.show_error(f"删除策略失败: {result.get('message', '未知错误')}")
            except Exception as e:
                self.show_error(f"删除策略时发生错误: {str(e)}")
                self.logger.error(f"删除策略失败: {e}", exc_info=True)

    def _register_strategy_status_listener(self):
        """注册策略状态变化事件监听器.

        监听策略启动/停止事件，自动切换监控界面显示。
        """
        try:
            from backend.core.base import get_event_engine
            from backend.infrastructure.system_vnpy.system_toolkit import (
                EVENT_STRATEGY_STATUS_CHANGED,
            )

            event_engine = get_event_engine()
            if not event_engine:
                self.logger.warning("EventEngine不可用，无法注册策略状态监听器")
                return

            # 注册事件处理器
            event_engine.register(EVENT_STRATEGY_STATUS_CHANGED, self._on_strategy_status_changed)

            self.logger.info("✅ 已注册策略状态变化事件监听器")

        except Exception as e:
            self.logger.error(f"注册策略状态监听器失败: {e}", exc_info=True)

    def _on_strategy_status_changed(self, event):
        """处理策略状态变化事件.

        Args:
            event: vnpy Event对象
        """
        try:
            # 提取事件数据
            data = event.data if hasattr(event, "data") else event
            gateway_name = data.get("gateway_name", "")
            strategy_name = data.get("strategy_name", "")
            status = data.get("status", "")
            active_count = data.get("active_count", 0)
            strategy_type = data.get("engine_type", "ctastrategy")

            self.logger.info(
                f"📢 收到策略状态事件: {gateway_name}.{strategy_name} -> {status} "
                f"(激活策略数: {active_count})"
            )

            # 刷新策略列表
            self.refresh_data()

            # 如果当前在监控Tab，且该网关正好只有1个激活策略，自动更新监控显示
            if self.content_tab and self.content_tab.currentIndex() == 1:
                if active_count == 1:
                    # 获取当前选中的网关
                    selected_gateway = self._get_selected_gateway_name()
                    if selected_gateway == gateway_name:
                        # 自动切换到对应的监控类型
                        self._auto_switch_monitor_type(strategy_type)

        except Exception as e:
            self.logger.error(f"处理策略状态事件失败: {e}", exc_info=True)

    def _auto_switch_monitor_type(self, strategy_type: str):
        """自动切换监控类型.

        Args:
            strategy_type: 策略类型（ctastrategy/algotrading等）
        """
        try:
            if not self.template_combo:
                return

            type_map = {
                "ctastrategy": "CTA策略",
                "algotrading": "算法交易",
                "optionmaster": "期权策略",
                "portfoliostrategy": "组合策略",
                "spreadtrading": "价差交易",
                "scripttrader": "脚本交易",
            }

            display_type = type_map.get(strategy_type, "通用监控")

            # 如果当前类型不同，才切换
            if self.template_combo.currentText() != display_type:
                self.template_combo.setCurrentText(display_type)
                self.logger.info(f"🔄 自动切换监控类型为: {display_type}")

        except Exception as e:
            self.logger.error(f"自动切换监控类型失败: {e}")

    def _check_and_update_monitor_display(self):
        """检查并更新监控界面显示.

        需求：策略池只激活1个策略的网关在监控Tab中显示对应的监控界面。
        不自动切换Tab，仅在用户切换到监控Tab时根据策略类型显示对应监控。
        """
        if not self.trading_service or not self.gateways_table:
            return

        try:
            # 获取当前选中的网关
            current_row = self.gateways_table.currentRow()
            if current_row < 0:
                return

            gateway_name_item = self.gateways_table.item(current_row, 0)
            if not gateway_name_item:
                return

            gateway_name = gateway_name_item.text()

            # 获取该网关的策略实例
            if gateway_name not in self.trading_service.strategy_instances:
                return

            strategies = self.trading_service.strategy_instances[gateway_name]

            # 检查激活策略数量
            active_strategies = [s for s in strategies.values() if s.get("status") == "running"]

            # 如果恰好只有1个激活策略，更新监控界面显示
            if len(active_strategies) == 1:
                strategy = active_strategies[0]

                # 获取策略引擎类型（使用部署时保存的engine_name）
                engine_name = strategy.get("engine_name", "CtaStrategy")
                strategy_type = (
                    engine_name.lower() if isinstance(engine_name, str) else "ctastrategy"
                )

                # 根据策略类型更新监控界面
                if self.template_combo:
                    type_map = {
                        "ctastrategy": "CTA策略",
                        "algotrading": "算法交易",
                        "optionmaster": "期权策略",
                        "portfoliostrategy": "组合策略",
                        "spreadtrading": "价差交易",
                        "scripttrader": "脚本交易",
                    }

                    display_type = type_map.get(strategy_type, "通用监控")
                    current_type = self.template_combo.currentText()

                    if current_type != display_type:
                        self.template_combo.setCurrentText(display_type)
                        self.logger.info(f"更新监控界面显示为{display_type}（单策略运行）")

        except Exception as e:
            self.logger.error(f"更新监控界面显示失败: {e}")

    def on_close(self):
        """关闭处理."""
        self.logger.info("交易网关界面已关闭")


# ==================== 以下为内部组件（从 shared_widgets 合并） ====================
# 合并说明：PortfolioMonitorWidget, AlgoMonitorWidget, OptionMonitorWidget 只被本文件引用，故合并到此处


class PortfolioMonitorWidget(QWidget):
    """组合策略监控组件."""

    def __init__(self, gateway_name: str, trading_service: Any, parent: Optional[QWidget] = None):
        """初始化组合策略监控组件.

        Args:
            gateway_name: 网关名称
            trading_service: 交易网关服务
            parent: 父组件
        """
        super().__init__(parent)
        self.gateway_name = gateway_name
        self.trading_service = trading_service

        self._setup_ui()

    def _setup_ui(self):
        """设置UI."""
        layout = QVBoxLayout(self)

        # 持仓概览组
        overview_group = QGroupBox("持仓概览")
        overview_layout = QHBoxLayout(overview_group)

        self.total_symbols_label = QLabel("品种数量: --")
        overview_layout.addWidget(self.total_symbols_label)

        self.total_value_label = QLabel("总市值: --")
        overview_layout.addWidget(self.total_value_label)

        self.total_pnl_label = QLabel("总盈亏: --")
        overview_layout.addWidget(self.total_pnl_label)

        overview_layout.addStretch()
        layout.addWidget(overview_group)

        # 品种持仓表
        position_group = QGroupBox("品种持仓明细")
        position_layout = QVBoxLayout(position_group)

        self.position_table = QTableWidget(0, 8)
        headers = ["品种", "方向", "数量", "均价", "现价", "市值", "盈亏", "权重"]
        self.position_table.setHorizontalHeaderLabels(headers)
        self.position_table.horizontalHeader().setStretchLastSection(True)

        position_layout.addWidget(self.position_table)
        layout.addWidget(position_group)

        # 盈亏贡献表
        contrib_group = QGroupBox("盈亏贡献分析")
        contrib_layout = QVBoxLayout(contrib_group)

        self.contrib_table = QTableWidget(0, 4)
        headers = ["品种", "盈亏", "贡献率", "收益率"]
        self.contrib_table.setHorizontalHeaderLabels(headers)
        self.contrib_table.horizontalHeader().setStretchLastSection(True)

        contrib_layout.addWidget(self.contrib_table)
        layout.addWidget(contrib_group)

        # 风险指标组
        risk_group = QGroupBox("风险指标")
        risk_layout = QVBoxLayout(risk_group)

        self.risk_table = QTableWidget(0, 2)
        self.risk_table.setHorizontalHeaderLabels(["指标", "值"])
        self.risk_table.horizontalHeader().setStretchLastSection(True)
        self.risk_table.verticalHeader().setVisible(False)

        # 添加初始行
        risks = [
            ("组合波动率", "--"),
            ("最大回撤", "--"),
            ("夏普比率", "--"),
            ("Beta系数", "--"),
            ("集中度", "--"),
        ]

        for i, (metric, value) in enumerate(risks):
            self.risk_table.insertRow(i)
            self.risk_table.setItem(i, 0, QTableWidgetItem(metric))
            self.risk_table.setItem(i, 1, QTableWidgetItem(value))

        risk_layout.addWidget(self.risk_table)
        layout.addWidget(risk_group)

    def update_data(self, monitoring_data: Dict[str, Any]):
        """更新监控数据.

        Args:
            monitoring_data: 监控数据字典
        """
        try:
            portfolio_data = monitoring_data.get("portfolio_strategy", {})

            # 更新持仓概览
            overview = portfolio_data.get("overview", {})
            self.total_symbols_label.setText(f"品种数量: {overview.get('symbol_count', 0)}")
            self.total_value_label.setText(f"总市值: {overview.get('total_value', 0):,.2f}")

            total_pnl = overview.get("total_pnl", 0)
            pnl_color = "#4ECDC4" if total_pnl >= 0 else "#FF6B6B"
            self.total_pnl_label.setText(f"总盈亏: {total_pnl:+,.2f}")
            self.total_pnl_label.setStyleSheet(f"color: {pnl_color}; font-weight: bold;")

            # 更新品种持仓表
            positions = portfolio_data.get("positions", [])
            self.position_table.setRowCount(len(positions))

            for i, pos in enumerate(positions):
                self.position_table.setItem(i, 0, QTableWidgetItem(pos.get("symbol", "")))
                self.position_table.setItem(i, 1, QTableWidgetItem(pos.get("direction", "")))
                self.position_table.setItem(i, 2, QTableWidgetItem(str(pos.get("volume", 0))))
                self.position_table.setItem(
                    i, 3, QTableWidgetItem(f"{pos.get('avg_price', 0):.2f}")
                )
                self.position_table.setItem(
                    i, 4, QTableWidgetItem(f"{pos.get('last_price', 0):.2f}")
                )
                self.position_table.setItem(
                    i, 5, QTableWidgetItem(f"{pos.get('market_value', 0):,.2f}")
                )
                self.position_table.setItem(i, 6, QTableWidgetItem(f"{pos.get('pnl', 0):+,.2f}"))
                self.position_table.setItem(i, 7, QTableWidgetItem(f"{pos.get('weight', 0):.2%}"))

            # 更新盈亏贡献表
            contributions = portfolio_data.get("contributions", [])
            self.contrib_table.setRowCount(len(contributions))

            for i, contrib in enumerate(contributions):
                self.contrib_table.setItem(i, 0, QTableWidgetItem(contrib.get("symbol", "")))
                self.contrib_table.setItem(i, 1, QTableWidgetItem(f"{contrib.get('pnl', 0):+,.2f}"))
                self.contrib_table.setItem(
                    i, 2, QTableWidgetItem(f"{contrib.get('contribution', 0):.2%}")
                )
                self.contrib_table.setItem(
                    i, 3, QTableWidgetItem(f"{contrib.get('return', 0):+.2%}")
                )

            # 更新风险指标
            risks = portfolio_data.get("risks", {})
            risk_data = [
                ("组合波动率", f"{risks.get('volatility', 0):.2%}"),
                ("最大回撤", f"{risks.get('max_drawdown', 0):.2%}"),
                ("夏普比率", f"{risks.get('sharpe_ratio', 0):.2f}"),
                ("Beta系数", f"{risks.get('beta', 0):.2f}"),
                ("集中度", f"{risks.get('concentration', 0):.2%}"),
            ]

            for i, (_, value) in enumerate(risk_data):
                if i < self.risk_table.rowCount():
                    item = self.risk_table.item(i, 1)
                    if item is not None:
                        item.setText(value)

        except Exception as e:
            print(f"更新组合策略监控数据失败: {e}")


class AlgoMonitorWidget(QWidget):
    """算法交易监控组件."""

    def __init__(self, gateway_name: str, trading_service: Any, parent: Optional[QWidget] = None):
        """初始化算法交易监控组件.

        Args:
            gateway_name: 网关名称
            trading_service: 交易网关服务
            parent: 父组件
        """
        super().__init__(parent)
        self.gateway_name = gateway_name
        self.trading_service = trading_service

        self._setup_ui()

    def _setup_ui(self):
        """设置UI."""
        layout = QVBoxLayout(self)

        # 执行进度组
        progress_group = QGroupBox("算法执行进度")
        progress_layout = QVBoxLayout(progress_group)

        # 进度条
        progress_info_layout = QHBoxLayout()
        progress_info_layout.addWidget(QLabel("执行进度:"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        progress_info_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("0%")
        progress_info_layout.addWidget(self.progress_label)
        progress_layout.addLayout(progress_info_layout)

        # 成交量信息
        volume_layout = QHBoxLayout()
        self.target_volume_label = QLabel("目标数量: --")
        volume_layout.addWidget(self.target_volume_label)

        self.traded_volume_label = QLabel("已成交: --")
        volume_layout.addWidget(self.traded_volume_label)

        self.remaining_volume_label = QLabel("剩余: --")
        volume_layout.addWidget(self.remaining_volume_label)

        volume_layout.addStretch()
        progress_layout.addLayout(volume_layout)

        layout.addWidget(progress_group)

        # 价格信息组
        price_group = QGroupBox("价格信息")
        price_layout = QHBoxLayout(price_group)

        self.target_price_label = QLabel("目标价格: --")
        price_layout.addWidget(self.target_price_label)

        self.avg_price_label = QLabel("平均成交价: --")
        price_layout.addWidget(self.avg_price_label)

        self.slippage_label = QLabel("滑点: --")
        price_layout.addWidget(self.slippage_label)

        price_layout.addStretch()
        layout.addWidget(price_group)

        # 执行统计表
        stats_group = QGroupBox("执行统计")
        stats_layout = QVBoxLayout(stats_group)

        self.stats_table = QTableWidget(0, 2)
        self.stats_table.setHorizontalHeaderLabels(["指标", "值"])
        self.stats_table.horizontalHeader().setStretchLastSection(True)
        self.stats_table.verticalHeader().setVisible(False)

        # 添加初始行
        stats = [
            ("总订单数", "--"),
            ("已完成订单", "--"),
            ("取消订单", "--"),
            ("执行耗时", "--"),
            ("平均延迟", "--"),
        ]

        for i, (metric, value) in enumerate(stats):
            self.stats_table.insertRow(i)
            self.stats_table.setItem(i, 0, QTableWidgetItem(metric))
            self.stats_table.setItem(i, 1, QTableWidgetItem(value))

        stats_layout.addWidget(self.stats_table)
        layout.addWidget(stats_group)

    def update_data(self, monitoring_data: Dict[str, Any]):
        """更新监控数据.

        Args:
            monitoring_data: 监控数据字典
        """
        try:
            algo_data = monitoring_data.get("algo_trading", {})

            # 更新执行进度
            progress = algo_data.get("progress", 0)
            self.progress_bar.setValue(int(progress))
            self.progress_label.setText(f"{progress:.1f}%")

            # 更新成交量信息
            target_volume = algo_data.get("target_volume", 0)
            traded_volume = algo_data.get("traded_volume", 0)
            remaining_volume = target_volume - traded_volume

            self.target_volume_label.setText(f"目标数量: {target_volume:,.0f}")
            self.traded_volume_label.setText(f"已成交: {traded_volume:,.0f}")
            self.remaining_volume_label.setText(f"剩余: {remaining_volume:,.0f}")

            # 更新价格信息
            target_price = algo_data.get("target_price", 0)
            avg_price = algo_data.get("avg_price", 0)
            slippage = avg_price - target_price if target_price > 0 else 0

            self.target_price_label.setText(f"目标价格: {target_price:.2f}")
            self.avg_price_label.setText(f"平均成交价: {avg_price:.2f}")
            self.slippage_label.setText(f"滑点: {slippage:.4f}")

            # 更新执行统计
            stats = algo_data.get("statistics", {})
            stats_data = [
                ("总订单数", str(stats.get("total_orders", "--"))),
                ("已完成订单", str(stats.get("completed_orders", "--"))),
                ("取消订单", str(stats.get("cancelled_orders", "--"))),
                ("执行耗时", f"{stats.get('elapsed_time', '--')} 秒"),
                ("平均延迟", f"{stats.get('avg_latency', '--')} 毫秒"),
            ]

            for i, (_, value) in enumerate(stats_data):
                if i < self.stats_table.rowCount():
                    item = self.stats_table.item(i, 1)
                    if item is not None:
                        item.setText(value)

        except Exception as e:
            print(f"更新算法交易监控数据失败: {e}")


class OptionMonitorWidget(QWidget):
    """期权策略监控组件."""

    def __init__(self, gateway_name: str, trading_service: Any, parent: Optional[QWidget] = None):
        """初始化期权策略监控组件.

        Args:
            gateway_name: 网关名称
            trading_service: 交易网关服务
            parent: 父组件
        """
        super().__init__(parent)
        self.gateway_name = gateway_name
        self.trading_service = trading_service

        self._setup_ui()

    def _setup_ui(self):
        """设置UI."""
        layout = QVBoxLayout(self)

        # 希腊字母组
        greeks_group = QGroupBox("希腊字母")
        greeks_layout = QHBoxLayout(greeks_group)

        # Delta
        delta_layout = QVBoxLayout()
        delta_layout.addWidget(QLabel("Delta"))
        self.delta_label = QLabel("--")
        self.delta_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #4ECDC4;")
        delta_layout.addWidget(self.delta_label, alignment=Qt.AlignmentFlag.AlignCenter)
        greeks_layout.addLayout(delta_layout)

        # Gamma
        gamma_layout = QVBoxLayout()
        gamma_layout.addWidget(QLabel("Gamma"))
        self.gamma_label = QLabel("--")
        self.gamma_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #FF6B6B;")
        gamma_layout.addWidget(self.gamma_label, alignment=Qt.AlignmentFlag.AlignCenter)
        greeks_layout.addLayout(gamma_layout)

        # Vega
        vega_layout = QVBoxLayout()
        vega_layout.addWidget(QLabel("Vega"))
        self.vega_label = QLabel("--")
        self.vega_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #FFD93D;")
        vega_layout.addWidget(self.vega_label, alignment=Qt.AlignmentFlag.AlignCenter)
        greeks_layout.addLayout(vega_layout)

        # Theta
        theta_layout = QVBoxLayout()
        theta_layout.addWidget(QLabel("Theta"))
        self.theta_label = QLabel("--")
        self.theta_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #A8E6CF;")
        theta_layout.addWidget(self.theta_label, alignment=Qt.AlignmentFlag.AlignCenter)
        greeks_layout.addLayout(theta_layout)

        layout.addWidget(greeks_group)

        # 波动率信息组
        vol_group = QGroupBox("波动率信息")
        vol_layout = QHBoxLayout(vol_group)

        self.impl_vol_label = QLabel("隐含波动率: --")
        vol_layout.addWidget(self.impl_vol_label)

        self.hist_vol_label = QLabel("历史波动率: --")
        vol_layout.addWidget(self.hist_vol_label)

        self.vol_diff_label = QLabel("波动率差: --")
        vol_layout.addWidget(self.vol_diff_label)

        vol_layout.addStretch()
        layout.addWidget(vol_group)

        # 期权持仓表
        position_group = QGroupBox("期权持仓")
        position_layout = QVBoxLayout(position_group)

        self.position_table = QTableWidget(0, 7)
        headers = ["合约", "方向", "数量", "均价", "现价", "盈亏", "Delta"]
        self.position_table.setHorizontalHeaderLabels(headers)
        self.position_table.horizontalHeader().setStretchLastSection(True)

        position_layout.addWidget(self.position_table)
        layout.addWidget(position_group)

        # 风险指标组
        risk_group = QGroupBox("风险指标")
        risk_layout = QVBoxLayout(risk_group)

        self.risk_table = QTableWidget(0, 2)
        self.risk_table.setHorizontalHeaderLabels(["指标", "值"])
        self.risk_table.horizontalHeader().setStretchLastSection(True)
        self.risk_table.verticalHeader().setVisible(False)

        # 添加初始行
        risks = [
            ("组合Delta", "--"),
            ("组合Gamma", "--"),
            ("最大损失", "--"),
            ("最大收益", "--"),
            ("盈亏平衡点", "--"),
        ]

        for i, (metric, value) in enumerate(risks):
            self.risk_table.insertRow(i)
            self.risk_table.setItem(i, 0, QTableWidgetItem(metric))
            self.risk_table.setItem(i, 1, QTableWidgetItem(value))

        risk_layout.addWidget(self.risk_table)
        layout.addWidget(risk_group)

    def update_data(self, monitoring_data: Dict[str, Any]):
        """更新监控数据.

        Args:
            monitoring_data: 监控数据字典
        """
        try:
            option_data = monitoring_data.get("option_master", {})

            # 更新希腊字母
            greeks = option_data.get("greeks", {})
            self.delta_label.setText(f"{greeks.get('delta', 0):.4f}")
            self.gamma_label.setText(f"{greeks.get('gamma', 0):.4f}")
            self.vega_label.setText(f"{greeks.get('vega', 0):.4f}")
            self.theta_label.setText(f"{greeks.get('theta', 0):.4f}")

            # 更新波动率信息
            impl_vol = option_data.get("implied_volatility", 0)
            hist_vol = option_data.get("historical_volatility", 0)
            vol_diff = impl_vol - hist_vol

            self.impl_vol_label.setText(f"隐含波动率: {impl_vol:.2%}")
            self.hist_vol_label.setText(f"历史波动率: {hist_vol:.2%}")
            self.vol_diff_label.setText(f"波动率差: {vol_diff:+.2%}")

            # 更新期权持仓表
            positions = option_data.get("positions", [])
            self.position_table.setRowCount(len(positions))

            for i, pos in enumerate(positions):
                self.position_table.setItem(i, 0, QTableWidgetItem(pos.get("symbol", "")))
                self.position_table.setItem(i, 1, QTableWidgetItem(pos.get("direction", "")))
                self.position_table.setItem(i, 2, QTableWidgetItem(str(pos.get("volume", 0))))
                self.position_table.setItem(
                    i, 3, QTableWidgetItem(f"{pos.get('avg_price', 0):.2f}")
                )
                self.position_table.setItem(
                    i, 4, QTableWidgetItem(f"{pos.get('last_price', 0):.2f}")
                )
                self.position_table.setItem(i, 5, QTableWidgetItem(f"{pos.get('pnl', 0):+.2f}"))
                self.position_table.setItem(i, 6, QTableWidgetItem(f"{pos.get('delta', 0):.4f}"))

            # 更新风险指标
            risks = option_data.get("risks", {})
            risk_data = [
                ("组合Delta", f"{risks.get('portfolio_delta', 0):.4f}"),
                ("组合Gamma", f"{risks.get('portfolio_gamma', 0):.4f}"),
                ("最大损失", f"{risks.get('max_loss', 0):,.2f}"),
                ("最大收益", f"{risks.get('max_profit', 0):,.2f}"),
                ("盈亏平衡点", f"{risks.get('breakeven', 0):.2f}"),
            ]

            for i, (_, value) in enumerate(risk_data):
                if i < self.risk_table.rowCount():
                    item = self.risk_table.item(i, 1)
                    if item is not None:
                        item.setText(value)

        except Exception as e:
            print(f"更新期权监控数据失败: {e}")
