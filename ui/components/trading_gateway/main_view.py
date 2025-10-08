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

from backend.core.shared_services import get_service_manager
from backend.core.utils.logging_utils import LoggerMixin
from ui.widgets.base_widget import BaseWidget


# 网关类型配置
GATEWAY_TYPES = {
    "CTP": "国内期货、期权",
    "CTP mini": "国内期货、期权（迷你版）",
    "Sopt": "国内ETF期权",
    "tts": "国内期货仿真交易",
    "ib": "海外证券、期货、期权、贵金属",
    "paperaccount": "纯本地模拟交易",
    "TDX gateway": "国内股票交易",
}


class TradingGateway(BaseWidget, LoggerMixin):
    """交易网关主界面（重构版）."""

    def __init__(self, parent=None):
        """初始化交易网关."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.trading_service = None

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
            if self.trading_service:
                self.logger.info("交易网关服务获取成功")
            else:
                self.logger.warning("交易网关服务未注册")
        except Exception as e:
            self.logger.error("获取交易网关服务失败: %s", e)
            self.show_error(f"服务获取失败: {e}")

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
        """创建交易监控子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 监控模板组
        template_group = QGroupBox("监控模板")
        template_layout = QVBoxLayout(template_group)

        self.template_combo = QComboBox()
        templates = ["委托监控", "持仓监控", "资金监控", "成交监控", "综合监控"]
        self.template_combo.addItems(templates)
        template_layout.addWidget(self.template_combo)

        layout.addWidget(template_group)

        # 监控内容组
        monitor_group = QGroupBox("监控内容")
        monitor_layout = QVBoxLayout(monitor_group)

        self.monitor_table = QTableWidget(0, 4)
        self.monitor_table.setHorizontalHeaderLabels(["时间", "事件", "详情", "状态"])
        header = self.monitor_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        monitor_layout.addWidget(self.monitor_table)
        layout.addWidget(monitor_group)

        return tab

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

            elif gateway_type == "TDX gateway":
                path_input = QLineEdit()
                path_input.setPlaceholderText("通达信安装路径")
                dynamic_form_layout.addRow("通达信路径:", path_input)
                dynamic_fields["tdx_path"] = path_input

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
        connect_btn.clicked.connect(lambda _c, r=row: self._connect_gateway(r))  # noqa: U100
        op_layout.addWidget(connect_btn)

        delete_btn = QPushButton("删除")
        delete_btn.clicked.connect(lambda _c, r=row: self._delete_gateway(r))  # noqa: U100
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
        self.show_info("部署策略功能需要vnpy集成")

    def _start_all_strategies(self):
        """启动所有策略."""
        self.show_info("启动所有策略")

    def _stop_all_strategies(self):
        """停止所有策略."""
        self.show_info("停止所有策略")

    # ==================== 通用方法 ====================

    def connect_signals(self):
        """连接信号槽."""

    def refresh_data(self):
        """刷新数据."""
        self.show_info("交易网关数据已刷新")

    def on_close(self):
        """关闭处理."""
        self.logger.info("交易网关界面已关闭")
