# -*- coding: utf-8 -*-
"""
组合投资界面 - 主视图
混合架构：两个固有业务组件，无独立子界面
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget,
    QProgressBar, QFormLayout, QLineEdit
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor

from ui.widgets.base_widget import BaseWidget
from utils.logging_utils import LoggerMixin


class PortfolioInvestment(BaseWidget, LoggerMixin):
    """组合投资主界面"""

    def __init__(self, parent=None):
        super().__init__(parent, "组合投资")
        self.logger.info("组合投资界面初始化开始")

        # 初始化VNPY适配器 - 在super().__init__()之后
        self._initialize_vnpy_adapter()

    def _initialize_vnpy_adapter(self):
        """初始化VNPY适配器"""
        try:
            from integration.vnpy_adapter import VnPyAdapter
            self.vnpy_adapter = VnPyAdapter()
            self._logger.info("VNPY适配器初始化完成")
        except Exception as e:
            self._logger.error(f"VNPY适配器初始化失败: {e}")
            self.vnpy_adapter = None

        # 确保属性始终存在
        if not hasattr(self, 'vnpy_adapter'):
            self.vnpy_adapter = None

    def setup_ui(self):
        """设置用户界面"""
        main_layout = QHBoxLayout(self)

        # 创建主分割器
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setSizes([400, 600])

        # 左侧：组合管理组件（固有组件）
        left_widget = self._create_portfolio_manager()
        main_splitter.addWidget(left_widget)

        # 右侧：组合投资监控组件（固有组件）
        right_widget = self._create_monitor_panel()
        main_splitter.addWidget(right_widget)

        main_layout.addWidget(main_splitter)

    def _create_portfolio_manager(self):
        """创建组合管理组件"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 标题
        title_label = QLabel("📊 组合管理")
        title_label.setStyleSheet("font-weight: bold; font-size: 16px; padding: 5px;")
        layout.addWidget(title_label)

        # 自动组合组
        auto_group = QGroupBox("自动组合（不可删除）")
        auto_layout = QVBoxLayout(auto_group)

        self.auto_portfolio_table = QTableWidget(0, 3)
        self.auto_portfolio_table.setHorizontalHeaderLabels(["网关名称", "策略数量", "状态"])
        self.auto_portfolio_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        auto_layout.addWidget(self.auto_portfolio_table)

        layout.addWidget(auto_group)

        # 自定义组合组
        custom_group = QGroupBox("自定义组合（可删除）")
        custom_layout = QVBoxLayout(custom_group)

        # 自定义组合工具栏
        toolbar_layout = QHBoxLayout()

        create_btn = QPushButton("新建组合")
        create_btn.clicked.connect(self._create_custom_portfolio)
        toolbar_layout.addWidget(create_btn)

        delete_btn = QPushButton("删除组合")
        delete_btn.clicked.connect(self._delete_custom_portfolio)
        toolbar_layout.addWidget(delete_btn)

        toolbar_layout.addStretch()

        custom_layout.addLayout(toolbar_layout)

        # 自定义组合列表
        self.custom_portfolio_table = QTableWidget(0, 4)
        self.custom_portfolio_table.setHorizontalHeaderLabels(["组合名称", "包含网关", "权重", "操作"])
        self.custom_portfolio_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        custom_layout.addWidget(self.custom_portfolio_table)

        layout.addWidget(custom_group)

        return widget

    def _create_monitor_panel(self):
        """创建组合投资监控组件"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 标题
        title_label = QLabel("📈 组合投资监控")
        title_label.setStyleSheet("font-weight: bold; font-size: 16px; padding: 5px;")
        layout.addWidget(title_label)

        # 网关选项卡
        self.gateway_tab = QTabWidget()

        # 为每个网关创建选项卡
        self._create_gateway_tabs()

        layout.addWidget(self.gateway_tab)

        return widget

    def _create_gateway_tabs(self):
        """创建网关选项卡"""
        # 清空现有选项卡
        self.gateway_tab.clear()

        if self.vnpy_adapter:
            try:
                # 从VNPY获取连接的网关列表
                if hasattr(self.vnpy_adapter, 'get_status'):
                    status = self.vnpy_adapter.get_status()
                    connected_gateways = status.get('connected_gateways', [])
                else:
                    connected_gateways = []

                # 为每个连接的网关创建选项卡
                for gateway_name in connected_gateways:
                    tab = self._create_monitor_tab(gateway_name)
                    self.gateway_tab.addTab(tab, gateway_name)

                # 如果有虚拟网关，也创建选项卡
                # 这里可以根据实际需求添加虚拟网关的逻辑

            except Exception as e:
                self.logger.error(f"创建网关选项卡失败: {e}")
                self._create_fallback_gateway_tabs()
        else:
            self._create_fallback_gateway_tabs()

    def _create_fallback_gateway_tabs(self):
        """创建备用网关选项卡（VNPY不可用时）"""
        # 示例网关选项卡
        gateway_names = ["CTP-001", "虚拟网关-001", "IB-001"]

        for gateway_name in gateway_names:
            tab = self._create_monitor_tab(gateway_name)
            self.gateway_tab.addTab(tab, gateway_name)

    def _create_monitor_tab(self, gateway_name):
        """为指定网关创建监控选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 业绩概览组
        overview_group = QGroupBox("业绩概览")
        overview_layout = QFormLayout(overview_group)

        self.total_pnl_label = QLabel("--")
        overview_layout.addRow("总盈亏:", self.total_pnl_label)

        self.total_return_label = QLabel("--")
        overview_layout.addRow("总收益率:", self.total_return_label)

        self.max_drawdown_label = QLabel("--")
        overview_layout.addRow("最大回撤:", self.max_drawdown_label)

        self.sharpe_ratio_label = QLabel("--")
        overview_layout.addRow("夏普比率:", self.sharpe_ratio_label)

        layout.addWidget(overview_group)

        # 持仓情况组
        position_group = QGroupBox("持仓情况")
        position_layout = QVBoxLayout(position_group)

        self.position_table = QTableWidget(0, 5)
        self.position_table.setHorizontalHeaderLabels(["品种", "持仓", "成本", "市值", "盈亏"])
        self.position_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        position_layout.addWidget(self.position_table)

        layout.addWidget(position_group)

        # 风险指标组
        risk_group = QGroupBox("风险指标")
        risk_layout = QVBoxLayout(risk_group)

        self.risk_progress = QProgressBar()
        self.risk_progress.setRange(0, 100)
        risk_layout.addWidget(QLabel("风险等级:"))
        risk_layout.addWidget(self.risk_progress)

        layout.addWidget(risk_group)

        return tab

    def connect_signals(self):
        """连接信号槽"""
        # 初始化VNPY适配器
        self._initialize_vnpy_adapter()

        # 连接网关选项卡切换信号
        self.gateway_tab.currentChanged.connect(self._on_gateway_tab_changed)

        # 启动更新定时器
        self.start_update_timer(2000, self._update_portfolio_data)

    def _initialize_vnpy_adapter(self):
        """初始化VNPY适配器"""
        try:
            from integration.vnpy_adapter import VnPyAdapter
            self.vnpy_adapter = VnPyAdapter()
            self.logger.info("VNPY适配器初始化完成")
        except Exception as e:
            self.logger.error(f"VNPY适配器初始化失败: {e}")
            self.vnpy_adapter = None

    def _create_custom_portfolio(self):
        """新建自定义组合"""
        self.show_info("新建自定义组合功能开发中...")

    def _delete_custom_portfolio(self):
        """删除自定义组合"""
        self.show_info("删除自定义组合功能开发中...")

    def _on_gateway_tab_changed(self, index):
        """网关选项卡切换"""
        if index >= 0:
            tab_text = self.gateway_tab.tabText(index)
            self.logger.info(f"切换到网关: {tab_text}")

    def _update_portfolio_data(self):
        """更新组合数据"""
        if self.vnpy_adapter:
            try:
                # 从VNPY获取真实数据
                if hasattr(self.vnpy_adapter, 'get_status'):
                    status = self.vnpy_adapter.get_status()
                    # 更新自动组合表格
                    self._update_auto_portfolios(status)
                else:
                    # 使用模拟数据
                    self._update_auto_portfolios_fallback()

                # 更新自定义组合表格
                if hasattr(self.vnpy_adapter, 'get_status'):
                    self._update_custom_portfolios(status)
                else:
                    self._update_custom_portfolios_fallback()

                # 更新监控数据
                self._update_monitor_data()

            except Exception as e:
                self.logger.error(f"更新组合数据失败: {e}")
                # 回退到模拟数据
                self._update_auto_portfolios_fallback()
                self._update_custom_portfolios_fallback()
        else:
            # 无VNPY适配器时使用模拟数据
            self._update_auto_portfolios_fallback()
            self._update_custom_portfolios_fallback()

    def _update_auto_portfolios(self, status):
        """更新自动组合"""
        # 清空表格
        self.auto_portfolio_table.setRowCount(0)

        connected_gateways = status.get('connected_gateways', [])

        for i, gateway_name in enumerate(connected_gateways):
            self.auto_portfolio_table.insertRow(i)

            # 网关名称
            self.auto_portfolio_table.setItem(i, 0, QTableWidgetItem(gateway_name))

            # 策略数量（模拟，实际需要从VNPY获取）
            strategies_count = "多个策略"  # 这里需要实际实现策略计数
            self.auto_portfolio_table.setItem(i, 1, QTableWidgetItem(strategies_count))

            # 状态（已连接的网关都是运行中）
            status_text = "运行中"
            self.auto_portfolio_table.setItem(i, 2, QTableWidgetItem(status_text))

            # 设置状态颜色
            status_item = self.auto_portfolio_table.item(i, 2)
            status_item.setBackground(QColor("#4caf50"))

    def _update_auto_portfolios_fallback(self):
        """备用自动组合更新（VNPY不可用时）"""
        # 清空表格
        self.auto_portfolio_table.setRowCount(0)

        # 模拟数据
        auto_data = [
            ("CTP主账户", "3个策略", "运行中"),
            ("IB国际账户", "2个策略", "运行中"),
        ]

        for i, (gateway, strategies, status) in enumerate(auto_data):
            self.auto_portfolio_table.insertRow(i)
            self.auto_portfolio_table.setItem(i, 0, QTableWidgetItem(gateway))
            self.auto_portfolio_table.setItem(i, 1, QTableWidgetItem(strategies))
            self.auto_portfolio_table.setItem(i, 2, QTableWidgetItem(status))

            # 设置状态颜色
            status_item = self.auto_portfolio_table.item(i, 2)
            if status == "运行中":
                status_item.setBackground(QColor("#4caf50"))
            else:
                status_item.setBackground(QColor("#ff9800"))

    def _update_custom_portfolios(self):
        """更新自定义组合"""
        # 清空表格
        self.custom_portfolio_table.setRowCount(0)

        # 模拟数据
        custom_data = [
            ("成长组合", "CTP主账户, IB国际账户", "50%, 50%", "编辑"),
            ("价值组合", "CTP主账户", "100%", "编辑"),
        ]

        for i, (name, gateways, weights, operation) in enumerate(custom_data):
            self.custom_portfolio_table.insertRow(i)
            self.custom_portfolio_table.setItem(i, 0, QTableWidgetItem(name))
            self.custom_portfolio_table.setItem(i, 1, QTableWidgetItem(gateways))
            self.custom_portfolio_table.setItem(i, 2, QTableWidgetItem(weights))

            # 操作按钮
            operation_btn = QPushButton(operation)
            self.custom_portfolio_table.setCellWidget(i, 3, operation_btn)

    def _update_custom_portfolios_fallback(self):
        """备用自定义组合更新（VNPY不可用时）"""
        # 清空表格
        self.custom_portfolio_table.setRowCount(0)

        # 模拟数据
        custom_data = [
            ("成长组合", "CTP主账户, IB国际账户", "50%, 50%", "编辑"),
            ("价值组合", "CTP主账户", "100%", "编辑"),
        ]

        for i, (name, gateways, weights, operation) in enumerate(custom_data):
            self.custom_portfolio_table.insertRow(i)
            self.custom_portfolio_table.setItem(i, 0, QTableWidgetItem(name))
            self.custom_portfolio_table.setItem(i, 1, QTableWidgetItem(gateways))
            self.custom_portfolio_table.setItem(i, 2, QTableWidgetItem(weights))

            # 操作按钮
            operation_btn = QPushButton(operation)
            self.custom_portfolio_table.setCellWidget(i, 3, operation_btn)

    def _update_monitor_data(self):
        """更新监控数据"""
        if not self.vnpy_adapter:
            return

        current_tab = self.gateway_tab.currentWidget()
        if current_tab:
            # 获取当前网关名称
            current_index = self.gateway_tab.currentIndex()
            gateway_name = self.gateway_tab.tabText(current_index)

            try:
                # 从VNPY获取持仓信息
                positions = self.vnpy_adapter.get_positions(gateway_name)
                account_info = self.vnpy_adapter.get_account_info(gateway_name)

                # 更新持仓表格
                self._update_positions_table(positions)

                # 更新账户信息
                self._update_account_info(account_info)

            except Exception as e:
                self.logger.error(f"更新监控数据失败: {e}")

    def _update_positions_table(self, positions):
        """更新持仓表格"""
        # 这里需要找到当前活动选项卡中的持仓表格
        # 由于选项卡动态创建，这里的实现需要更复杂的控件管理
        # 目前先记录持仓数据，实际显示需要更复杂的实现

        if positions:
            # 这里应该更新持仓表格
            # 由于控件结构复杂，这里简化处理
            pass

    def _update_account_info(self, account_info):
        """更新账户信息"""
        # 这里应该更新业绩概览信息
        # 由于控件结构复杂，这里简化处理
        if account_info:
            # 更新账户余额、可用资金等信息
            pass

    def refresh_data(self):
        """刷新数据"""
        self._update_portfolio_data()
        self.show_info("组合投资数据已刷新")

    def on_close(self):
        """关闭处理"""
        self.stop_update_timer()
        self.logger.info("组合投资界面已关闭")
