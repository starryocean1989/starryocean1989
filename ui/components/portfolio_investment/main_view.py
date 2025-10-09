# -*- coding: utf-8 -*-
"""组合投资界面 - 主视图（重构版）.

混合架构：两个固有业务组件，无独立子界面。
通过PortfolioService访问组合管理和监控功能。
"""
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg

from backend.core.base import get_service_manager
from backend.core.utils import LoggerMixin

from ui.widgets.base_widget import BaseWidget


class PortfolioInvestment(BaseWidget, LoggerMixin):
    """组合投资主界面（重构版）."""

    def __init__(self, parent=None):
        """初始化组合投资."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.portfolio_service = None

        # 初始化UI组件
        self.auto_portfolio_table: Optional[QTableWidget] = None
        self.custom_portfolio_table: Optional[QTableWidget] = None
        self.gateway_tab: Optional[QTabWidget] = None
        self.monitor_data: Dict[str, Any] = {}

        # 监控选项卡字典（用于动态创建）
        self.monitor_tabs: Dict[str, QWidget] = {}

        # 刷新定时器
        self.refresh_timer: Optional[Any] = None

        # 调用父类初始化
        super().__init__(parent, "组合投资")
        self.logger.info("组合投资界面初始化开始")

        # 初始化服务
        self._initialize_service()

    def _initialize_service(self):
        """获取组合投资服务."""
        try:
            # 从服务管理器获取组合投资服务
            self.portfolio_service = self.service_manager.get_service("portfolio_service")
            if self.portfolio_service:
                self.logger.info("组合投资服务获取成功")
            else:
                self.logger.warning("组合投资服务未注册")
        except Exception as e:
            self.logger.error("获取组合投资服务失败: %s", e)
            self.show_error(f"服务获取失败: {e}")

    def setup_ui(self):
        """设置用户界面."""
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

    # ==================== 组合管理组件（固有组件）====================

    def _create_portfolio_manager(self) -> QWidget:
        """创建组合管理组件."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 标题
        title_label = QLabel("📊 组合管理")
        title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        layout.addWidget(title_label)

        # 自动组合组
        auto_group = QGroupBox("自动组合（不可删除）")
        auto_layout = QVBoxLayout(auto_group)

        self.auto_portfolio_table = QTableWidget(0, 3)
        self.auto_portfolio_table.setHorizontalHeaderLabels(["网关名称", "策略数量", "状态"])
        header = self.auto_portfolio_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        auto_layout.addWidget(self.auto_portfolio_table)
        layout.addWidget(auto_group)

        # 自定义组合组
        custom_group = QGroupBox("自定义组合（可删除）")
        custom_layout = QVBoxLayout(custom_group)

        # 工具栏
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
        self.custom_portfolio_table.setHorizontalHeaderLabels(
            ["组合名称", "包含网关", "权重", "操作"]
        )
        header = self.custom_portfolio_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        custom_layout.addWidget(self.custom_portfolio_table)
        layout.addWidget(custom_group)

        return widget

    # ==================== 组合投资监控组件（固有组件）====================

    def _create_monitor_panel(self) -> QWidget:
        """创建组合投资监控组件."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 标题
        title_label = QLabel("📈 组合投资监控")
        title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        layout.addWidget(title_label)

        # 网关选项卡
        self.gateway_tab = QTabWidget()
        self.gateway_tab.setTabsClosable(True)
        self.gateway_tab.setMovable(True)
        self.gateway_tab.tabCloseRequested.connect(self._on_tab_close_requested)

        # 创建示例选项卡
        self._create_example_monitor_tab()

        layout.addWidget(self.gateway_tab)

        return widget

    def _create_example_monitor_tab(self):
        """创建示例监控选项卡."""
        if not self.gateway_tab:
            return

        tab = self._create_monitor_tab("示例网关")
        self.gateway_tab.addTab(tab, "💡 示例")

    def _create_monitor_tab(self, gateway_name: str) -> QWidget:
        """创建监控选项卡."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel(f"网关: {gateway_name}"))
        toolbar_layout.addStretch()

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(lambda: self._refresh_monitor(gateway_name))
        toolbar_layout.addWidget(refresh_btn)

        layout.addLayout(toolbar_layout)

        # 业绩概览组
        overview_group = QGroupBox("实时业绩概览")
        overview_layout = QHBoxLayout(overview_group)

        # 指标卡片
        pnl_card = self._create_metric_card("总盈亏", "--", "#4CAF50")
        overview_layout.addWidget(pnl_card)

        return_card = self._create_metric_card("总收益率", "--", "#2196F3")
        overview_layout.addWidget(return_card)

        dd_card = self._create_metric_card("最大回撤", "--", "#FF9800")
        overview_layout.addWidget(dd_card)

        sharpe_card = self._create_metric_card("夏普比率", "--", "#9C27B0")
        overview_layout.addWidget(sharpe_card)

        layout.addWidget(overview_group)

        # 资金曲线图
        equity_group = QGroupBox("资金曲线")
        equity_layout = QVBoxLayout(equity_group)

        equity_widget = pg.PlotWidget()
        equity_widget.setBackground("#1E1E1E")
        equity_widget.setMinimumHeight(200)
        equity_layout.addWidget(equity_widget)

        layout.addWidget(equity_group)

        # 持仓情况组
        position_group = QGroupBox("持仓情况")
        position_layout = QVBoxLayout(position_group)

        position_table = QTableWidget(0, 5)
        position_table.setHorizontalHeaderLabels(["品种", "持仓", "成本", "市值", "盈亏"])
        header = position_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        position_layout.addWidget(position_table)
        layout.addWidget(position_group)

        return tab

    def _create_metric_card(self, title: str, value: str, color: str) -> QGroupBox:
        """创建指标卡片."""
        card = QGroupBox()
        card.setStyleSheet(
            f"""
            QGroupBox {{
                border: 2px solid {color};
                border-radius: 8px;
                padding: 15px;
                background-color: #2A2A2A;
            }}
            """
        )

        card_layout = QVBoxLayout(card)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 12px; color: #888;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {color};")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(value_label)

        return card

    # ==================== 事件处理 ====================

    def _on_tab_close_requested(self, index: int):
        """处理Tab关闭请求."""
        if not self.gateway_tab:
            return

        tab_name = self.gateway_tab.tabText(index)

        reply = QMessageBox.question(
            self,
            "确认关闭",
            f"确定要关闭监控 '{tab_name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.gateway_tab.removeTab(index)
            self.show_info(f"已关闭监控: {tab_name}")

    def _refresh_monitor(self, gateway_name: str):
        """刷新监控数据."""
        self.show_info(f"刷新监控数据: {gateway_name}")

    def _create_custom_portfolio(self):
        """新建自定义组合."""
        if not self.portfolio_service:
            self.show_error("组合投资服务不可用")
            return

        from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox

        # 创建对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("新建自定义组合")
        dialog.setModal(True)
        dialog.resize(400, 200)

        layout = QFormLayout(dialog)

        # 组合名称
        name_input = QLineEdit()
        layout.addRow("组合名称:", name_input)

        # 网关列表
        gateway_input = QLineEdit()
        gateway_input.setPlaceholderText("输入网关名称，用逗号分隔")
        layout.addRow("包含网关:", gateway_input)

        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            portfolio_name = name_input.text().strip()
            gateways_text = gateway_input.text().strip()

            if not portfolio_name:
                self.show_error("请输入组合名称")
                return

            # 解析网关列表
            gateway_list = [g.strip() for g in gateways_text.split(",") if g.strip()]

            if not gateway_list:
                self.show_error("请至少输入一个网关名称")
                return

            # 调用服务创建组合
            result = self.portfolio_service.create_custom_portfolio(
                portfolio_name=portfolio_name, gateway_names=gateway_list, weights=None
            )

            if result.get("success"):
                self.show_info(f"组合 '{portfolio_name}' 创建成功")
                self.refresh_data()
            else:
                self.show_error(f"创建组合失败: {result.get('message', '未知错误')}")

    def _delete_custom_portfolio(self):
        """删除自定义组合."""
        if not self.custom_portfolio_table:
            return

        current_row = self.custom_portfolio_table.currentRow()
        if current_row < 0:
            self.show_warning("请先选择要删除的组合")
            return

        self.custom_portfolio_table.removeRow(current_row)
        self.show_info("组合已删除")

    # ==================== 通用方法 ====================

    def connect_signals(self):
        """连接信号槽."""
        if self.gateway_tab:
            self.gateway_tab.currentChanged.connect(self._on_gateway_tab_changed)

        # 启动自动刷新定时器
        from PySide6.QtCore import QTimer

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._auto_refresh_portfolios)
        self.refresh_timer.start(5000)  # 每5秒刷新一次

    def _on_gateway_tab_changed(self, index: int):
        """网关选项卡切换."""
        if index >= 0 and self.gateway_tab:
            tab_text = self.gateway_tab.tabText(index)
            self.logger.info("切换到网关: %s", tab_text)

    def refresh_data(self):
        """刷新数据."""
        try:
            if not self.portfolio_service:
                return

            # 获取组合列表
            result = self.portfolio_service.list_portfolios()
            if not result.get("success"):
                return

            portfolios = result.get("portfolios", {})

            # 更新自动组合表格
            self._update_auto_portfolios_table(portfolios.get("auto_portfolios", []))

            # 更新自定义组合表格
            self._update_custom_portfolios_table(portfolios.get("custom_portfolios", []))

            # 动态创建监控选项卡
            self._create_portfolio_monitor_tabs(portfolios)

        except Exception as e:
            self.logger.error("刷新数据失败: %s", e)

    def _update_auto_portfolios_table(self, portfolios: list):
        """更新自动组合表格."""
        if not self.auto_portfolio_table:
            return

        self.auto_portfolio_table.setRowCount(0)
        for portfolio in portfolios:
            row = self.auto_portfolio_table.rowCount()
            self.auto_portfolio_table.insertRow(row)

            gateway_name = portfolio.get("gateway_name", "")
            strategy_count = portfolio.get("strategy_count", 0)

            self.auto_portfolio_table.setItem(row, 0, QTableWidgetItem(gateway_name))
            self.auto_portfolio_table.setItem(row, 1, QTableWidgetItem(str(strategy_count)))
            self.auto_portfolio_table.setItem(row, 2, QTableWidgetItem("运行中"))

    def _update_custom_portfolios_table(self, portfolios: list):
        """更新自定义组合表格."""
        if not self.custom_portfolio_table:
            return

        self.custom_portfolio_table.setRowCount(0)
        for portfolio in portfolios:
            row = self.custom_portfolio_table.rowCount()
            self.custom_portfolio_table.insertRow(row)

            name = portfolio.get("name", "")
            gateway_names = portfolio.get("gateway_names", [])
            weights = portfolio.get("weights", {})

            self.custom_portfolio_table.setItem(row, 0, QTableWidgetItem(name))
            self.custom_portfolio_table.setItem(row, 1, QTableWidgetItem(", ".join(gateway_names)))
            self.custom_portfolio_table.setItem(row, 2, QTableWidgetItem(str(weights)))

            # 添加删除按钮
            delete_btn = QPushButton("删除")
            delete_btn.clicked.connect(lambda _, n=name: self._delete_portfolio_by_name(n))
            self.custom_portfolio_table.setCellWidget(row, 3, delete_btn)

    def _create_portfolio_monitor_tabs(self, portfolios: Dict[str, Any]):
        """动态创建组合监控选项卡."""
        if not self.gateway_tab:
            return

        # 获取所有组合
        all_portfolios = []
        all_portfolios.extend(portfolios.get("auto_portfolios", []))
        all_portfolios.extend(portfolios.get("custom_portfolios", []))

        # 为每个组合创建监控选项卡
        for portfolio in all_portfolios:
            portfolio_id = portfolio.get("id") or portfolio.get("name")

            if portfolio_id not in self.monitor_tabs:
                # 创建新选项卡
                tab = self._create_monitor_tab_with_data(portfolio)
                self.monitor_tabs[portfolio_id] = tab

                # 获取网关名称
                gateway_name = portfolio.get("gateway_name") or portfolio.get("name")
                self.gateway_tab.addTab(tab, f"📊 {gateway_name}")

    def _create_monitor_tab_with_data(self, portfolio: Dict[str, Any]) -> QWidget:
        """创建带数据的监控选项卡."""
        portfolio_id = portfolio.get("id") or portfolio.get("name") or ""
        gateway_name = portfolio.get("gateway_name") or portfolio.get("name") or ""

        tab = self._create_monitor_tab(gateway_name)

        # 获取监控数据并更新
        self._refresh_portfolio_monitoring(portfolio_id, tab)

        return tab

    def _refresh_portfolio_monitoring(self, portfolio_id: str, _tab: QWidget):
        """刷新组合监控数据."""
        if not self.portfolio_service:
            return

        try:
            # 获取监控数据
            result = self.portfolio_service.get_portfolio_monitoring(portfolio_id)
            if not result.get("success"):
                return

            data = result.get("data", {})

            # 更新业绩指标卡片
            # 这里可以通过查找tab中的QLabel来更新数据
            # 为了简化，我们在这里记录日志
            self.logger.info("组合 %s 监控数据: %s" % (portfolio_id, data))

        except Exception as e:
            self.logger.error("刷新组合监控失败: %s" % e)

    def _auto_refresh_portfolios(self):
        """自动刷新组合列表."""
        self.refresh_data()

    def _delete_portfolio_by_name(self, portfolio_name: str):
        """通过名称删除组合."""
        if not self.portfolio_service:
            return

        result = self.portfolio_service.delete_custom_portfolio(portfolio_name)
        if result.get("success"):
            self.show_info(f"组合 '{portfolio_name}' 已删除")
            self.refresh_data()
        else:
            self.show_error(f"删除失败: {result.get('message')}")

    def on_close(self):
        """关闭处理."""
        self.logger.info("组合投资界面已关闭")
