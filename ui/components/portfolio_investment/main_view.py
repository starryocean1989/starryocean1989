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
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg

from backend.core.shared_services import get_service_manager
from backend.core.utils.logging_utils import LoggerMixin
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
        self.show_info("新建自定义组合功能需要vnpy集成")

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

    def _on_gateway_tab_changed(self, index: int):
        """网关选项卡切换."""
        if index >= 0 and self.gateway_tab:
            tab_text = self.gateway_tab.tabText(index)
            self.logger.info("切换到网关: %s", tab_text)

    def refresh_data(self):
        """刷新数据."""
        self.show_info("组合投资数据已刷新")

    def on_close(self):
        """关闭处理."""
        self.logger.info("组合投资界面已关闭")
