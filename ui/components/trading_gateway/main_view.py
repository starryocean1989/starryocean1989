# -*- coding: utf-8 -*-
"""交易网关界面 - 主视图.

混合架构：网关管理器（固有组件）+ 2个子界面.
"""

import logging
from typing import Any, Callable, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from ui.widgets.base_widget import BaseWidget as _BaseWidget
    from backend.core.utils.logging_utils import LoggerMixin as _LoggerMixin
    from backend.core.vnpy_integration import TerminalEngine as VnPyAdapter

    BaseWidget = _BaseWidget  # type: ignore[assignment]
    LoggerMixin = _LoggerMixin  # type: ignore[assignment]
    VNPY_AVAILABLE = True
except ImportError as e:
    raise ImportError(
        f"无法导入必要的UI组件或VnPy适配器: {e}\n"
        "请确保已正确安装所有依赖：pip install -r requirements.txt"
    )


class TradingGateway(BaseWidget, LoggerMixin):
    """交易网关主界面."""

    def __init__(self, parent=None):
        """Initialize trading gateway."""
        super().__init__(parent, "交易网关")
        self.logger.info("交易网关界面初始化开始")

        # Initialize UI components
        self.new_gateway_btn = None
        # 更新定时器与就绪标志
        self._update_timer = None
        self.ui_ready = False
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

        # Initialize VNPY adapter first
        self.vnpy_adapter = None
        self._initialize_vnpy_adapter()

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
        # 界面就绪
        self.ui_ready = True

    def _create_gateway_manager(self):
        """创建网关管理器."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("🔗 网关管理器")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
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
        self.gateways_table.setHorizontalHeaderLabels(["网关名称", "类型", "状态", "操作"])
        self.gateways_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

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
        self.strategy_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

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
        # 从后端服务获取监控模板列表
        templates = self._get_available_templates()
        self.template_combo.addItems(templates)
        template_layout.addWidget(self.template_combo)

        layout.addWidget(template_group)

        # 监控内容区域
        monitor_group = QGroupBox("监控内容")
        monitor_layout = QVBoxLayout(monitor_group)

        self.monitor_table = QTableWidget(0, 4)
        self.monitor_table.setHorizontalHeaderLabels(["时间", "事件", "详情", "状态"])
        self.monitor_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        monitor_layout.addWidget(self.monitor_table)

        layout.addWidget(monitor_group)

        return tab

    def connect_signals(self):
        """连接信号槽."""
        # 初始化VNPY适配器
        self._initialize_vnpy_adapter()

        # 连接模板选择信号（空控件守卫）
        if self.template_combo is not None:
            self.template_combo.currentTextChanged.connect(self._on_template_changed)

        # 启动更新定时器（就绪守卫）
        self.start_update_timer(1000, self._update_gateway_status)

    def _initialize_vnpy_adapter(self):
        """初始化VNPY适配器."""
        if VNPY_AVAILABLE and VnPyAdapter:
            try:
                self.vnpy_adapter = VnPyAdapter()
                self.logger.info("VNPY适配器初始化完成")
            except (ImportError, RuntimeError, AttributeError) as e:
                self.logger.error("VNPY适配器初始化失败: %s", e)
                self.vnpy_adapter = None
        else:
            self.vnpy_adapter = None
            self.logger.warning("VNPY适配器不可用")

    def _get_available_gateway_types(self):
        """从后端服务获取可用网关类型列表."""
        try:
            from backend.services.trading_gateway.gateway_manager_service import (
                GatewayManagerService,
            )

            gateway_service = GatewayManagerService()
            # 返回网关类型列表，格式：["类型 - 描述"]
            return [f"{key} - {value}" for key, value in gateway_service.gateway_types.items()]
        except Exception as e:
            self.logger.error("获取网关类型列表失败: %s", e)
            raise RuntimeError(f"无法获取网关类型列表: {str(e)}")

    def _get_available_templates(self):
        """从后端服务获取可用监控模板列表."""
        try:
            # 监控模板是固定的几个选项
            return ["委托监控", "持仓监控", "资金监控", "成交监控", "综合监控"]
        except Exception as e:
            self.logger.error("获取监控模板列表失败: %s", e)
            raise RuntimeError(f"无法获取监控模板列表: {str(e)}")

    def _create_new_gateway(self):
        """新建网关 - 显示动态表单对话框."""
        from PySide6.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QFormLayout,
            QLineEdit,
            QComboBox,
            QDialogButtonBox,
            QSpinBox,
            QCheckBox,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("新建交易网关")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)
        form_layout = QFormLayout()

        # 网关类型选择 - 从后端服务获取
        gateway_type_combo = QComboBox()
        gateway_types = self._get_available_gateway_types()
        gateway_type_combo.addItems(gateway_types)
        form_layout.addRow("网关类型:", gateway_type_combo)

        # 动态表单容器
        dynamic_form_layout = QFormLayout()
        form_layout.addRow(dynamic_form_layout)

        # 存储动态字段
        dynamic_fields = {}

        def update_form(gateway_type_text):
            """根据网关类型更新表单字段."""
            # 清空动态表单
            while dynamic_form_layout.rowCount() > 0:
                dynamic_form_layout.removeRow(0)
            dynamic_fields.clear()

            # 提取网关类型
            gateway_type = gateway_type_text.split(" - ")[0]

            # 通用字段
            name_input = QLineEdit()
            name_input.setPlaceholderText("输入网关名称...")
            dynamic_form_layout.addRow("网关名称*:", name_input)
            dynamic_fields["name"] = name_input

            # 根据不同网关类型添加不同字段
            if gateway_type == "CTP":
                user_input = QLineEdit()
                dynamic_form_layout.addRow("用户名*:", user_input)
                dynamic_fields["user"] = user_input

                auth_input = QLineEdit()
                dynamic_form_layout.addRow("授权码*:", auth_input)
                dynamic_fields["auth_code"] = auth_input

                td_server = QLineEdit()
                td_server.setPlaceholderText("交易服务器地址")
                dynamic_form_layout.addRow("交易服务器*:", td_server)
                dynamic_fields["td_address"] = td_server

                md_server = QLineEdit()
                md_server.setPlaceholderText("行情服务器地址")
                dynamic_form_layout.addRow("行情服务器*:", md_server)
                dynamic_fields["md_address"] = md_server

                broker_input = QLineEdit()
                dynamic_form_layout.addRow("经纪商代码:", broker_input)
                dynamic_fields["broker_id"] = broker_input

            elif gateway_type == "CTP mini":
                user_input = QLineEdit()
                dynamic_form_layout.addRow("用户名*:", user_input)
                dynamic_fields["user"] = user_input

                td_server = QLineEdit()
                dynamic_form_layout.addRow("交易服务器*:", td_server)
                dynamic_fields["td_address"] = td_server

            elif gateway_type == "Sopt":
                user_input = QLineEdit()
                dynamic_form_layout.addRow("用户名*:", user_input)
                dynamic_fields["user"] = user_input

                server_input = QLineEdit()
                dynamic_form_layout.addRow("服务器地址*:", server_input)
                dynamic_fields["server"] = server_input

            elif gateway_type == "tts":
                user_input = QLineEdit()
                dynamic_form_layout.addRow("用户名*:", user_input)
                dynamic_fields["user"] = user_input

                server_input = QLineEdit()
                server_input.setPlaceholderText("仿真服务器地址")
                dynamic_form_layout.addRow("服务器地址*:", server_input)
                dynamic_fields["server"] = server_input

            elif gateway_type == "ib":
                host_input = QLineEdit()
                host_input.setText("127.0.0.1")
                dynamic_form_layout.addRow("主机*:", host_input)
                dynamic_fields["host"] = host_input

                port_input = QSpinBox()
                port_input.setRange(1, 65535)
                port_input.setValue(7497)
                dynamic_form_layout.addRow("端口*:", port_input)
                dynamic_fields["port"] = port_input

                client_id = QSpinBox()
                client_id.setRange(0, 9999)
                client_id.setValue(1)
                dynamic_form_layout.addRow("客户端ID:", client_id)
                dynamic_fields["client_id"] = client_id

            elif gateway_type == "paperaccount":
                capital_input = QSpinBox()
                capital_input.setRange(10000, 100000000)
                capital_input.setValue(1000000)
                capital_input.setSuffix(" 元")
                dynamic_form_layout.addRow("初始资金*:", capital_input)
                dynamic_fields["capital"] = capital_input

                fee_input = QLineEdit()
                fee_input.setText("0.0003")
                dynamic_form_layout.addRow("手续费率:", fee_input)
                dynamic_fields["fee_rate"] = fee_input

                slippage_input = QLineEdit()
                slippage_input.setText("0")
                dynamic_form_layout.addRow("滑点:", slippage_input)
                dynamic_fields["slippage"] = slippage_input

            elif gateway_type == "TDX gateway":
                path_input = QLineEdit()
                path_input.setPlaceholderText("通达信安装路径")
                dynamic_form_layout.addRow("通达信路径*:", path_input)
                dynamic_fields["tdx_path"] = path_input

                auto_connect = QCheckBox("启动时自动连接")
                dynamic_form_layout.addRow("", auto_connect)
                dynamic_fields["auto_connect"] = auto_connect

        # 初始化表单
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
                "name": (
                    dynamic_fields["name"].text()
                    if "name" in dynamic_fields and dynamic_fields["name"] is not None
                    else ""
                ),
            }
            # 收集所有字段值
            for key, field in dynamic_fields.items():
                if key != "name":
                    if isinstance(field, QLineEdit):
                        config[key] = field.text()
                    elif isinstance(field, QSpinBox):
                        config[key] = field.value()
                    elif isinstance(field, QCheckBox):
                        config[key] = field.isChecked()

            self.show_info(f"创建网关: {config['name']} ({gateway_type})")
            self._add_gateway_to_list(config)

    def _add_gateway_to_list(self, config: dict):
        """添加网关到列表."""
        if not self.gateways_table:
            return

        row = self.gateways_table.rowCount()
        self.gateways_table.insertRow(row)

        # 设置网关信息
        self.gateways_table.setItem(row, 0, QTableWidgetItem(config.get("name", "")))
        self.gateways_table.setItem(row, 1, QTableWidgetItem(config.get("type", "")))
        self.gateways_table.setItem(row, 2, QTableWidgetItem("未连接"))

        # 创建操作按钮
        op_widget = QWidget()
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(2, 2, 2, 2)

        connect_btn = QPushButton("连接")
        connect_btn.clicked.connect(lambda r=row, c=config: self._connect_gateway_with_config(r, c))
        op_layout.addWidget(connect_btn)

        delete_btn = QPushButton("删除")
        delete_btn.clicked.connect(lambda r=row: self._delete_gateway(r))
        op_layout.addWidget(delete_btn)

        self.gateways_table.setCellWidget(row, 3, op_widget)

    def _connect_gateway_with_config(self, row: int, config: dict):
        """连接网关（带配置）."""
        from PySide6.QtWidgets import QInputDialog

        # 弹出密码输入对话框
        password, ok = QInputDialog.getText(
            self, "连接网关", "请输入密码:", QLineEdit.EchoMode.Password
        )

        if ok and password:
            self.show_info(f"正在连接网关: {config.get('name', '')}...")
            # 调用后端API连接网关
            if self.vnpy_adapter:
                result = self.vnpy_adapter.connect_gateway(config)
                if result:
                    if self.gateways_table:
                        self.gateways_table.setItem(row, 2, QTableWidgetItem("已连接"))
                    self.show_info("网关连接成功")
                else:
                    raise RuntimeError("网关连接失败")
            else:
                raise RuntimeError("VNPY适配器不可用")

    def _delete_gateway(self, row: int):
        """删除网关."""
        from PySide6.QtWidgets import QMessageBox

        if not self.gateways_table:
            return

        gateway_item = self.gateways_table.item(row, 0)
        gateway_name = gateway_item.text() if gateway_item is not None else "未知网关"

        # 确认对话框
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
        raise NotImplementedError("部署策略功能需要实现strategy_pool_service集成。")

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

    def start_update_timer(
        self, interval: int = 1000, callback: Optional[Callable[..., Any]] = None
    ):
        """启动更新定时器（安全守卫）."""
        if not getattr(self, "ui_ready", False):
            return
        if callback is None:
            return
        timer = getattr(self, "_update_timer", None)
        if timer is None:
            self._update_timer = QTimer(self)
            self._update_timer.timeout.connect(callback)
            timer = self._update_timer
        if timer is not None:
            timer.start(int(interval) if interval else 1000)

    def stop_update_timer(self):
        """停止更新定时器."""
        try:
            if getattr(self, "_update_timer", None) is not None:
                self._update_timer.stop()  # type: ignore[union-attr]
        finally:
            self._update_timer = None

    def _update_gateway_status(self):
        """更新网关状态."""
        if not self.vnpy_adapter:
            raise RuntimeError("VnPy适配器不可用，无法更新网关列表")

        # 获取网关状态 - 必须有get_status方法
        if not hasattr(self.vnpy_adapter, "get_status"):
            raise AttributeError("VnPy适配器缺少get_status方法")

        status = self.vnpy_adapter.get_status()

        # 更新网关表格
        self._update_gateways_table(status)

        # 更新策略表格
        self._update_strategies_table(status)

    def _update_gateways_table(self, status):
        """更新网关表格."""
        # 空控件守卫
        if self.gateways_table is None:
            return

        if not status:
            raise ValueError("status参数不能为空")

        # 清空表格
        self.gateways_table.setRowCount(0)

        gateways = status.get("gateways", [])
        if not gateways:
            # 没有网关时不是错误，只是空列表
            return

        connected_gateways = status.get("connected_gateways", [])

        for i, gateway_name in enumerate(gateways):
            self.gateways_table.insertRow(i)

            # 网关名称
            self.gateways_table.setItem(i, 0, QTableWidgetItem(gateway_name))

            # 网关类型 - 从真实数据获取
            gateway_type = status.get("gateway_types", {}).get(gateway_name, "未知")
            self.gateways_table.setItem(i, 1, QTableWidgetItem(gateway_type))

            # 连接状态
            is_connected = gateway_name in connected_gateways
            status_text = "已连接" if is_connected else "未连接"
            status_color = QColor("#4caf50") if is_connected else QColor("#ff9800")

            status_item = QTableWidgetItem(status_text)
            status_item.setBackground(status_color)
            self.gateways_table.setItem(i, 2, status_item)

            # 操作按钮
            btn = QPushButton("断开" if is_connected else "连接")
            if is_connected:
                btn.clicked.connect(lambda gw=gateway_name: self._disconnect_gateway(gw))
            else:
                btn.clicked.connect(lambda gw=gateway_name: self._connect_gateway(gw))
            self.gateways_table.setCellWidget(i, 3, btn)

    def _connect_gateway(self, gateway_name):
        """连接网关."""
        if self.vnpy_adapter:
            try:
                # 兼容不同签名与方法名
                result = None
                if hasattr(self.vnpy_adapter, "connect_gateway"):
                    try:
                        result = self.vnpy_adapter.connect_gateway(gateway_name)
                    except TypeError:
                        result = self.vnpy_adapter.connect_gateway(gateway_name, **{})
                elif hasattr(self.vnpy_adapter, "connect"):
                    try:
                        result = self.vnpy_adapter.connect(gateway_name)  # type: ignore
                    except TypeError:
                        result = self.vnpy_adapter.connect(gateway_name, **{})  # type: ignore

                if (isinstance(result, dict) and result.get("success", False)) or (result is True):
                    self.show_info(f"网关 {gateway_name} 连接成功")
                    self._update_gateway_status()
                else:
                    self.show_error(f"网关 {gateway_name} 连接失败")
            except (RuntimeError, AttributeError, ConnectionError) as e:
                self.show_error(f"连接网关失败: {str(e)}")
        else:
            self.show_warning("VNPY适配器不可用")

    def _disconnect_gateway(self, gateway_name):
        """断开网关."""
        if self.vnpy_adapter:
            try:
                result = None
                if hasattr(self.vnpy_adapter, "disconnect_gateway"):
                    result = self.vnpy_adapter.disconnect_gateway(gateway_name)  # type: ignore
                elif hasattr(self.vnpy_adapter, "disconnect"):
                    result = self.vnpy_adapter.disconnect(  # type: ignore[attr-defined]
                        gateway_name
                    )

                if (isinstance(result, dict) and result.get("success", False)) or (result is True):
                    self.show_info(f"网关 {gateway_name} 已断开")
                    self._update_gateway_status()
                else:
                    self.show_error("断开网关失败")
            except (RuntimeError, AttributeError, ConnectionError) as e:
                self.show_error(f"断开网关失败: {str(e)}")
        else:
            self.show_warning("VNPY适配器不可用")

    def _update_strategies_table(self):
        """更新策略表格."""
        # 空控件守卫
        if self.strategy_table is None:
            return
        # 清空表格
        self.strategy_table.setRowCount(0)

        # 从VNPY获取实际策略信息
        if not self.vnpy_adapter:
            raise RuntimeError("VNPY适配器未初始化")

        # 获取真实策略列表
        if hasattr(self.vnpy_adapter, "get_strategies"):
            strategies = self.vnpy_adapter.get_strategies()
        else:
            self.logger.warning("VNPY适配器缺少get_strategies方法")
            strategies = []

        for i, strategy_info in enumerate(strategies):
            self.strategy_table.insertRow(i)
            self.strategy_table.setItem(i, 0, QTableWidgetItem(strategy_info.get("name", "")))
            self.strategy_table.setItem(i, 1, QTableWidgetItem(strategy_info.get("gateway", "")))

            status_text = strategy_info.get("status", "")
            status_item = QTableWidgetItem(status_text)
            if status_text == "运行中":
                status_item.setBackground(QColor("#4caf50"))
            else:
                status_item.setBackground(QColor("#ff9800"))
            self.strategy_table.setItem(i, 2, status_item)

            self.strategy_table.setItem(i, 3, QTableWidgetItem(strategy_info.get("start_time", "")))

            # 操作按钮
            strategy_name = strategy_info.get("name", "")
            btn = QPushButton("停止" if status_text == "运行中" else "启动")
            if status_text == "运行中":
                btn.clicked.connect(lambda s=strategy_name: self._stop_strategy(s))
            else:
                btn.clicked.connect(lambda s=strategy_name: self._start_strategy(s))
            self.strategy_table.setCellWidget(i, 4, btn)

    def refresh_data(self):
        """刷新数据."""
        self.show_info("交易网关数据已刷新")

    def on_close(self):
        """关闭处理."""
        self.stop_update_timer()
        self.logger.info("交易网关界面已关闭")
