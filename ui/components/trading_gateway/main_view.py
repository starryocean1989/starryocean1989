# -*- coding: utf-8 -*-
"""交易网关界面 - 主视图（重构版）.

混合架构：网关管理器（固有组件）+ 2个子界面。
通过TradingGatewayService访问网关和策略功能。
"""
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt

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
from backend.core.utils import LoggerMixin

from ui.widgets.base_widget import BaseWidget


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
        self.auto_switch_timer: Optional[Any] = None  # QTimer类型

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
                if child.widget():
                    child.widget().deleteLater()

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
        """创建默认监控界面（通用）."""
        monitor_group = QGroupBox("通用监控")
        monitor_layout = QVBoxLayout(monitor_group)

        self.monitor_table = QTableWidget(0, 6)
        self.monitor_table.setHorizontalHeaderLabels(
            ["时间", "策略", "事件", "品种", "详情", "状态"]
        )
        header = self.monitor_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        monitor_layout.addWidget(self.monitor_table)
        if self.monitor_layout is not None:
            self.monitor_layout.addWidget(monitor_group)

    def _create_cta_monitor(self):
        """创建CTA策略专用监控界面."""
        # 尝试导入vnpy_ctastrategy的UI组件
        cta_widget = None
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
            self.logger.info("已加载vnpy_ctastrategy专用监控组件")
        except ImportError:
            self.logger.warning("vnpy_ctastrategy UI组件不可用，使用简化版")

        if cta_widget and self.monitor_layout is not None:
            self.monitor_layout.addWidget(cta_widget)
        else:
            # 简化版CTA监控
            group = QGroupBox("CTA策略监控")
            layout = QVBoxLayout(group)

            table = QTableWidget(0, 7)
            table.setHorizontalHeaderLabels(
                ["策略", "持仓", "入场价", "当前价", "盈亏", "状态", "操作"]
            )
            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

            layout.addWidget(table)
            if self.monitor_layout is not None:
                self.monitor_layout.addWidget(group)

    def _create_algo_monitor(self):
        """创建算法交易专用监控界面."""
        try:
            from vnpy_algotrading.ui import AlgoManager

            if (
                self.trading_service
                and hasattr(self.trading_service, "main_engine")
                and self.trading_service.main_engine is not None
            ):
                algo_widget = AlgoManager(
                    self.trading_service.main_engine, self.trading_service.event_engine
                )
            if self.monitor_layout is not None:
                self.monitor_layout.addWidget(algo_widget)
            self.logger.info("已加载vnpy_algotrading专用监控组件")
        except ImportError:
            # 简化版算法交易监控
            group = QGroupBox("算法交易监控")
            layout = QVBoxLayout(group)

            table = QTableWidget(0, 7)
            table.setHorizontalHeaderLabels(
                ["算法", "目标价", "目标量", "已成交", "进度", "状态", "操作"]
            )
            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

            layout.addWidget(table)
            if self.monitor_layout is not None:
                self.monitor_layout.addWidget(group)

    def _create_option_monitor(self):
        """创建期权策略专用监控界面."""
        try:
            from vnpy_optionmaster.ui import OptionManager

            if (
                self.trading_service
                and hasattr(self.trading_service, "main_engine")
                and self.trading_service.main_engine is not None
            ):
                option_widget = OptionManager(
                    self.trading_service.main_engine, self.trading_service.event_engine
                )
            if self.monitor_layout is not None:
                self.monitor_layout.addWidget(option_widget)
            self.logger.info("已加载vnpy_optionmaster专用监控组件")
        except ImportError:
            # 简化版期权监控
            group = QGroupBox("期权策略监控（希腊字母）")
            layout = QVBoxLayout(group)

            table = QTableWidget(0, 8)
            table.setHorizontalHeaderLabels(
                ["策略", "Delta", "Gamma", "Vega", "Theta", "标的价格", "组合价值", "操作"]
            )
            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

            layout.addWidget(table)
            if self.monitor_layout is not None:
                self.monitor_layout.addWidget(group)

    def _create_portfolio_monitor(self):
        """创建组合策略专用监控界面."""
        try:
            from vnpy_portfoliostrategy.ui import PortfolioStrategyManager

            if (
                self.trading_service
                and hasattr(self.trading_service, "main_engine")
                and self.trading_service.main_engine is not None
            ):
                portfolio_widget = PortfolioStrategyManager(
                    self.trading_service.main_engine, self.trading_service.event_engine
                )
            if self.monitor_layout is not None:
                self.monitor_layout.addWidget(portfolio_widget)
            self.logger.info("已加载vnpy_portfoliostrategy专用监控组件")
        except ImportError:
            # 简化版组合策略监控
            group = QGroupBox("组合策略监控")
            layout = QVBoxLayout(group)

            table = QTableWidget(0, 6)
            table.setHorizontalHeaderLabels(["品种", "持仓", "权重", "市值", "贡献", "操作"])
            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

            layout.addWidget(table)
            if self.monitor_layout is not None:
                self.monitor_layout.addWidget(group)

    def _create_spread_monitor(self):
        """创建价差交易专用监控界面."""
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
            if self.monitor_layout is not None:
                self.monitor_layout.addWidget(spread_widget)
            self.logger.info("已加载vnpy_spreadtrading专用监控组件")
        except ImportError:
            # 简化版价差交易监控
            group = QGroupBox("价差交易监控")
            layout = QVBoxLayout(group)

            table = QTableWidget(0, 7)
            table.setHorizontalHeaderLabels(
                ["价差名称", "价差价格", "腿1价格", "腿2价格", "持仓", "盈亏", "操作"]
            )
            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

            layout.addWidget(table)
            if self.monitor_layout is not None:
                self.monitor_layout.addWidget(group)

    def _create_script_monitor(self):
        """创建脚本交易专用监控界面."""
        try:
            from vnpy_scripttrader.ui import ScriptEngine

            if (
                self.trading_service
                and hasattr(self.trading_service, "main_engine")
                and self.trading_service.main_engine is not None
            ):
                script_widget = ScriptEngine(
                    self.trading_service.main_engine, self.trading_service.event_engine
                )
            else:
                script_widget = None
            if script_widget and self.monitor_layout is not None:
                self.monitor_layout.addWidget(script_widget)
            self.logger.info("已加载vnpy_scripttrader专用监控组件")
        except ImportError:
            # 简化版脚本交易监控
            group = QGroupBox("脚本交易监控")
            layout = QVBoxLayout(group)

            table = QTableWidget(0, 5)
            table.setHorizontalHeaderLabels(["脚本名称", "运行时间", "执行次数", "状态", "操作"])
            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

            layout.addWidget(table)
            if self.monitor_layout is not None:
                self.monitor_layout.addWidget(group)

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
            if gateway_type in ["CTP", "CTP mini"]:
                user_input = QLineEdit()
                dynamic_form_layout.addRow("用户名:", user_input)
                dynamic_fields["user"] = user_input

                server_input = QLineEdit()
                dynamic_form_layout.addRow("服务器地址:", server_input)
                dynamic_fields["server"] = server_input

            elif gateway_type == "paperaccount":
                capital_input = QSpinBox()
                capital_input.setRange(10000, 100000000)
                capital_input.setValue(1000000)
                dynamic_form_layout.addRow("初始资金:", capital_input)
                dynamic_fields["capital"] = capital_input

            elif gateway_type == "TradeX gateway":
                path_input = QLineEdit()
                path_input.setPlaceholderText("TradeX DLL路径")
                dynamic_form_layout.addRow("TradeX路径:", path_input)
                dynamic_fields["tradex_path"] = path_input

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
            config = {
                "type": gateway_type,
                "name": dynamic_fields["name"].text() if "name" in dynamic_fields else "",
            }
            for key, field in dynamic_fields.items():
                if key != "name":
                    if isinstance(field, QLineEdit):
                        config[key] = field.text()
                    elif isinstance(field, QSpinBox):
                        config[key] = field.value()

            self.show_info(f"创建网关: {config['name']} ({gateway_type})")
            self._add_gateway_to_list(config)

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

        connect_btn = QPushButton("连接")
        connect_btn.clicked.connect(lambda checked, r=row: self._connect_gateway(r))
        op_layout.addWidget(connect_btn)

        delete_btn = QPushButton("删除")
        delete_btn.clicked.connect(lambda checked, r=row: self._delete_gateway(r))
        op_layout.addWidget(delete_btn)

        self.gateways_table.setCellWidget(row, 3, op_widget)

    def _connect_gateway(self, row: int):
        """连接网关."""
        if not self.gateways_table:
            return

        gateway_item = self.gateways_table.item(row, 0)
        if not gateway_item:
            return

        gateway_name = gateway_item.text()
        self.show_info(f"连接网关: {gateway_name}")

        # vnpy集成后通过trading_service连接网关
        if self.gateways_table:
            self.gateways_table.setItem(row, 2, QTableWidgetItem("连接中..."))

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
            self.gateways_table.removeRow(row)
            self.show_info(f"已删除网关: {gateway_name}")

    def _deploy_strategy(self):
        """部署策略."""
        if not self.trading_service:
            self.show_error("交易网关服务不可用")
            return

        # 创建策略部署对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("部署策略")
        dialog.setModal(True)
        dialog.resize(500, 400)

        layout = QFormLayout(dialog)

        # 网关选择
        gateway_combo = QComboBox()
        if self.trading_service:
            gateway_list = self.trading_service.get_gateway_list()
            if gateway_list and gateway_list.get("success"):
                for gw in gateway_list.get("gateways", []):
                    gateway_combo.addItem(gw["name"])
        layout.addRow("网关:", gateway_combo)

        # 策略名称
        strategy_name_input = QLineEdit()
        layout.addRow("策略名称:", strategy_name_input)

        # 策略类名
        strategy_class_input = QLineEdit()
        strategy_class_input.setPlaceholderText("例如: DoubleMaStrategy")
        layout.addRow("策略类名:", strategy_class_input)

        # 引擎类型
        engine_combo = QComboBox()
        engine_combo.addItems(
            [
                "CtaStrategy",
                "AlgoTrading",
                "OptionMaster",
                "PortfolioStrategy",
                "ScriptTrader",
                "SpreadTrading",
            ]
        )
        layout.addRow("引擎类型:", engine_combo)

        # 交易品种
        symbols_input = QLineEdit()
        symbols_input.setPlaceholderText("例如: rb2101.SHFE,IF2101.CFFEX")
        layout.addRow("交易品种:", symbols_input)

        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            gateway_name = gateway_combo.currentText()
            strategy_name = strategy_name_input.text().strip()
            strategy_class = strategy_class_input.text().strip()
            engine_type = engine_combo.currentText()
            symbols_text = symbols_input.text().strip()

            if not all([gateway_name, strategy_name, strategy_class]):
                self.show_error("请填写完整的策略信息")
                return

            # 解析交易品种
            vt_symbols = [s.strip() for s in symbols_text.split(",") if s.strip()]

            # 调用服务部署策略
            result = self.trading_service.deploy_strategy(
                gateway_name=gateway_name,
                strategy_name=strategy_name,
                strategy_class=strategy_class,
                strategy_params={
                    "engine_type": engine_type,
                    "vt_symbols": vt_symbols,
                },
            )

            if result.get("success"):
                self.show_info(f"策略 '{strategy_name}' 部署成功")
                self.refresh_data()
            else:
                self.show_error(f"策略部署失败: {result.get('message', '未知错误')}")

    def _start_all_strategies(self):
        """启动所有策略."""
        self.show_info("启动所有策略")

    def _stop_all_strategies(self):
        """停止所有策略."""
        self.show_info("停止所有策略")

    # ==================== 通用方法 ====================

    def connect_signals(self):
        """连接信号槽."""
        # 启动策略状态监控定时器（用于自动切换监控界面）
        from PySide6.QtCore import QTimer

        self.auto_switch_timer = QTimer(self)
        self.auto_switch_timer.timeout.connect(self._check_and_auto_switch_monitor)
        self.auto_switch_timer.start(3000)  # 每3秒检查一次

    def refresh_data(self):
        """刷新数据."""
        self._check_and_auto_switch_monitor()
        self.show_info("交易网关数据已刷新")

    def _check_and_auto_switch_monitor(self):
        """检查并自动切换监控界面.

        需求：策略池只激活1个策略的网关自动切换到监控界面。
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

            # 如果恰好只有1个激活策略，自动切换到监控界面
            if len(active_strategies) == 1:
                strategy = active_strategies[0]

                # 识别策略类型
                strategy_type = self.trading_service.recognize_strategy_type(
                    strategy_class_code=strategy.get("class_code", ""),
                    gateway_name=gateway_name,
                    strategy_name=strategy.get("name", ""),
                )

                # 自动切换到监控Tab
                if self.content_tab and self.content_tab.currentIndex() != 1:
                    self.content_tab.setCurrentIndex(1)  # 切换到监控Tab

                # 根据策略类型切换监控界面
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
                        self.logger.info(f"自动切换到{display_type}监控界面（检测到单策略运行）")

        except Exception as e:
            self.logger.error(f"自动切换监控界面失败: {e}")

    def on_close(self):
        """关闭处理."""
        self.logger.info("交易网关界面已关闭")
