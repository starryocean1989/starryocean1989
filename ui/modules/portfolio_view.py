# -*- coding: utf-8 -*-
"""组合投资界面 - 主视图（重构版）.

混合架构：两个固有业务组件，无独立子界面。
通过PortfolioService访问组合管理和监控功能。
"""
from typing import Any, Dict, List, Optional

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
from backend.core.service_base import LoggerMixin

from ui.shared_widgets.base_widget import BaseWidget


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

        # 基准指数选择（新增）
        from PySide6.QtWidgets import QComboBox

        benchmark_combo = QComboBox()
        benchmark_combo.addItems(
            [
                "000300 - 沪深300",
                "000001 - 上证指数",
                "399001 - 深证成指",
                "399006 - 创业板指",
                "000016 - 上证50",
                "000905 - 中证500",
                "000852 - 中证1000",
            ]
        )
        benchmark_combo.setProperty("gateway_name", gateway_name)
        benchmark_combo.currentTextChanged.connect(
            lambda text: self._on_benchmark_changed(gateway_name, text)
        )
        toolbar_layout.addWidget(QLabel("基准指数:"))
        toolbar_layout.addWidget(benchmark_combo)

        toolbar_layout.addSpacing(20)

        # 周期选择
        period_combo = QComboBox()
        period_combo.addItems(["日度", "周度", "月度", "年度"])
        period_combo.setProperty("gateway_name", gateway_name)
        period_combo.currentTextChanged.connect(
            lambda text: self._on_period_changed(gateway_name, text)
        )
        toolbar_layout.addWidget(QLabel("统计周期:"))
        toolbar_layout.addWidget(period_combo)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(lambda: self._refresh_monitor(gateway_name))
        toolbar_layout.addWidget(refresh_btn)

        layout.addLayout(toolbar_layout)

        # 业绩概览组（增强版：盈亏分离显示）
        overview_group = QGroupBox("实时业绩概览")
        overview_layout = QVBoxLayout(overview_group)

        # 第一行：总盈亏和收益率
        row1_layout = QHBoxLayout()

        # 总盈亏卡片
        pnl_card = self._create_metric_card("总盈亏", "--", "#4CAF50")
        pnl_card.setProperty("metric_type", "total_pnl")
        pnl_card.setProperty("gateway_name", gateway_name)
        row1_layout.addWidget(pnl_card)

        return_card = self._create_metric_card("总收益率", "--", "#2196F3")
        return_card.setProperty("metric_type", "return")
        return_card.setProperty("gateway_name", gateway_name)
        row1_layout.addWidget(return_card)

        overview_layout.addLayout(row1_layout)

        # 第二行：盈亏分离显示（Trading P&L vs Holding P&L）
        row2_layout = QHBoxLayout()

        trading_pnl_card = self._create_metric_card("已实现收益", "--", "#00BCD4")
        trading_pnl_card.setProperty("metric_type", "trading_pnl")
        trading_pnl_card.setProperty("gateway_name", gateway_name)
        row2_layout.addWidget(trading_pnl_card)

        holding_pnl_card = self._create_metric_card("未实现收益", "--", "#8BC34A")
        holding_pnl_card.setProperty("metric_type", "holding_pnl")
        holding_pnl_card.setProperty("gateway_name", gateway_name)
        row2_layout.addWidget(holding_pnl_card)

        overview_layout.addLayout(row2_layout)

        # 第三行：风险指标
        row3_layout = QHBoxLayout()

        dd_card = self._create_metric_card("最大回撤", "--", "#FF9800")
        dd_card.setProperty("metric_type", "drawdown")
        dd_card.setProperty("gateway_name", gateway_name)
        row3_layout.addWidget(dd_card)

        sharpe_card = self._create_metric_card("夏普比率", "--", "#9C27B0")
        sharpe_card.setProperty("metric_type", "sharpe")
        sharpe_card.setProperty("gateway_name", gateway_name)
        row3_layout.addWidget(sharpe_card)

        overview_layout.addLayout(row3_layout)

        layout.addWidget(overview_group)

        # 高级风险指标组（新增）
        risk_group = QGroupBox("高级风险指标")
        risk_layout = QVBoxLayout(risk_group)

        # 创建两行风险指标
        risk_row1 = QHBoxLayout()
        risk_row2 = QHBoxLayout()

        # VaR指标
        var_card = self._create_small_metric_card("VaR(95%)", "--", "#FF5722")
        var_card.setProperty("metric_type", "var_95")
        var_card.setProperty("gateway_name", gateway_name)
        risk_row1.addWidget(var_card)

        cvar_card = self._create_small_metric_card("CVaR(95%)", "--", "#FF7043")
        cvar_card.setProperty("metric_type", "cvar_95")
        cvar_card.setProperty("gateway_name", gateway_name)
        risk_row1.addWidget(cvar_card)

        vol_card = self._create_small_metric_card("年化波动率", "--", "#FFC107")
        vol_card.setProperty("metric_type", "volatility")
        vol_card.setProperty("gateway_name", gateway_name)
        risk_row1.addWidget(vol_card)

        risk_layout.addLayout(risk_row1)

        # 第二行风险指标
        sortino_card = self._create_small_metric_card("索提诺比率", "--", "#AB47BC")
        sortino_card.setProperty("metric_type", "sortino_ratio")
        sortino_card.setProperty("gateway_name", gateway_name)
        risk_row2.addWidget(sortino_card)

        calmar_card = self._create_small_metric_card("卡玛比率", "--", "#7E57C2")
        calmar_card.setProperty("metric_type", "calmar_ratio")
        calmar_card.setProperty("gateway_name", gateway_name)
        risk_row2.addWidget(calmar_card)

        beta_card = self._create_small_metric_card("Beta值", "--", "#5C6BC0")
        beta_card.setProperty("metric_type", "beta")
        beta_card.setProperty("gateway_name", gateway_name)
        risk_row2.addWidget(beta_card)

        risk_layout.addLayout(risk_row2)

        layout.addWidget(risk_group)

        # 资金曲线图
        equity_group = QGroupBox("资金曲线")
        equity_layout = QVBoxLayout(equity_group)

        equity_widget = pg.PlotWidget()
        equity_widget.setBackground("#1E1E1E")
        equity_widget.setMinimumHeight(200)
        equity_widget.showGrid(x=True, y=True, alpha=0.3)
        equity_widget.setLabel("left", "权益", units="元")
        equity_widget.setLabel("bottom", "日期")
        equity_widget.setProperty("gateway_name", gateway_name)
        equity_widget.setProperty("chart_type", "equity")
        equity_layout.addWidget(equity_widget)

        layout.addWidget(equity_group)

        # 回撤曲线图（新增）
        drawdown_group = QGroupBox("回撤曲线")
        drawdown_layout = QVBoxLayout(drawdown_group)

        drawdown_widget = pg.PlotWidget()
        drawdown_widget.setBackground("#1E1E1E")
        drawdown_widget.setMinimumHeight(200)
        drawdown_widget.showGrid(x=True, y=True, alpha=0.3)
        drawdown_widget.setLabel("left", "回撤率", units="%")
        drawdown_widget.setLabel("bottom", "日期")
        drawdown_widget.setProperty("gateway_name", gateway_name)
        drawdown_widget.setProperty("chart_type", "drawdown")
        drawdown_layout.addWidget(drawdown_widget)

        layout.addWidget(drawdown_group)

        # VnPy核心监控组件（新增选项卡）
        vnpy_monitors_group = QGroupBox("VnPy核心监控")
        vnpy_monitors_layout = QVBoxLayout(vnpy_monitors_group)

        from backend.core.base import get_event_engine
        from ui.shared_widgets.basic_monitors import (
            OrderMonitor,
            TradeMonitor,
            PositionMonitor,
            AccountMonitor,
        )

        # 创建监控选项卡
        vnpy_monitor_tabs = QTabWidget()
        event_engine = get_event_engine()

        vnpy_monitor_tabs.addTab(AccountMonitor(event_engine, gateway_name, self), "💰 资金")
        vnpy_monitor_tabs.addTab(PositionMonitor(event_engine, gateway_name, self), "📊 持仓")
        vnpy_monitor_tabs.addTab(OrderMonitor(event_engine, gateway_name, self), "📝 订单")
        vnpy_monitor_tabs.addTab(TradeMonitor(event_engine, gateway_name, self), "✅ 成交")

        vnpy_monitors_layout.addWidget(vnpy_monitor_tabs)
        layout.addWidget(vnpy_monitors_group)

        # 持仓情况组
        position_group = QGroupBox("持仓情况")
        position_layout = QVBoxLayout(position_group)

        position_table = QTableWidget(0, 5)
        position_table.setHorizontalHeaderLabels(["品种", "持仓", "成本", "市值", "盈亏"])
        position_table.setProperty("gateway_name", gateway_name)
        header = position_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        position_layout.addWidget(position_table)
        layout.addWidget(position_group)

        # 历史业绩分析组
        history_group = QGroupBox("历史业绩分析")
        history_layout = QVBoxLayout(history_group)

        # 周期统计表格
        period_table = QTableWidget(0, 5)
        period_table.setHorizontalHeaderLabels(
            ["周期", "收益", "收益率(%)", "起始权益", "结束权益"]
        )
        period_table.setProperty("gateway_name", gateway_name)
        period_table.setMaximumHeight(200)
        header = period_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        history_layout.addWidget(period_table)
        layout.addWidget(history_group)

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

    def _create_small_metric_card(self, title: str, value: str, color: str) -> QGroupBox:
        """创建小尺寸指标卡片（用于高级风险指标）."""
        card = QGroupBox()
        card.setStyleSheet(
            f"""
            QGroupBox {{
                border: 1px solid {color};
                border-radius: 6px;
                padding: 10px;
                background-color: #2A2A2A;
            }}
            """
        )

        card_layout = QVBoxLayout(card)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 10px; color: #888;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {color};")
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

    def _on_benchmark_changed(self, gateway_name: str, benchmark_text: str):
        """基准指数选择变化处理.

        Args:
            gateway_name: 网关名称
            benchmark_text: 基准指数文本（格式: "000300 - 沪深300"）
        """
        try:
            # 提取指数代码
            index_code = benchmark_text.split(" - ")[0] if " - " in benchmark_text else "000300"

            self.logger.info("切换基准指数: %s (代码: %s)", benchmark_text, index_code)

            # 重新计算风险指标（会使用新的基准）
            self._refresh_monitor(gateway_name)

        except Exception as e:
            self.logger.error("切换基准指数失败: %s", e)

    def _on_period_changed(self, gateway_name: str, period_text: str):
        """周期选择变化处理."""
        period_map = {
            "日度": "daily",
            "周度": "weekly",
            "月度": "monthly",
            "年度": "yearly",
        }
        period = period_map.get(period_text, "daily")
        self.logger.info("切换统计周期: %s -> %s", period_text, period)
        # 重新加载历史业绩数据
        self._refresh_monitor(gateway_name, period)

    def _refresh_monitor(self, gateway_name: str, period: str = "daily"):
        """刷新监控数据（增强版：包含风险指标和曲线图）.

        Args:
            gateway_name: 网关名称
            period: 统计周期
        """
        try:
            if not self.portfolio_service:
                self.show_error("组合投资服务不可用")
                return

            # 获取实时监控数据
            result = self.portfolio_service.get_portfolio_monitoring(gateway_name)
            if result.get("success"):
                data = result.get("data", {})
                self._update_real_time_metrics(gateway_name, data)

            # 获取历史业绩数据
            history_result = self.portfolio_service.get_historical_performance(
                portfolio_name=gateway_name, period=period
            )
            if history_result.get("success"):
                history_data = history_result.get("data", {})
                self._update_historical_performance(gateway_name, history_data, period)

            # 获取高级风险指标（新增）
            risk_result = self.portfolio_service.calculate_risk_metrics(
                portfolio_name=gateway_name, lookback_days=60
            )
            if risk_result.get("success"):
                risk_metrics = risk_result.get("metrics", {})
                self._update_risk_metrics(gateway_name, risk_metrics)

            # 获取收益率序列并更新曲线图（新增）
            self._update_equity_and_drawdown_charts(gateway_name)

            self.show_info(f"监控数据已刷新: {gateway_name}")

        except Exception as e:
            self.logger.error("刷新监控数据失败: %s", e)
            self.show_error(f"刷新失败: {str(e)}")

    def _update_real_time_metrics(self, gateway_name: str, data: Dict[str, Any]):
        """更新实时业绩指标卡片（增强版：支持盈亏分离显示）.

        Args:
            gateway_name: 网关名称
            data: 监控数据，包含：
                - total_pnl: 总盈亏
                - trading_pnl: 已实现收益（Trading P&L）
                - holding_pnl: 未实现收益（Holding P&L）
                - total_balance: 总权益
        """
        try:
            total_pnl = data.get("total_pnl", 0)
            trading_pnl = data.get("trading_pnl", 0)  # 已实现收益
            holding_pnl = data.get("holding_pnl", 0)  # 未实现收益
            total_balance = data.get("total_balance", 1000000)

            # 计算收益率
            return_rate = (total_pnl / total_balance * 100) if total_balance > 0 else 0

            # 查找并更新指标卡片
            if self.gateway_tab:
                for i in range(self.gateway_tab.count()):
                    tab = self.gateway_tab.widget(i)
                    if tab:
                        # 查找该Tab下的所有QGroupBox
                        cards = tab.findChildren(QGroupBox)
                        for card in cards:
                            gw_name = card.property("gateway_name")
                            metric_type = card.property("metric_type")

                            if gw_name == gateway_name and metric_type:
                                # 查找卡片中的值标签（第二个QLabel）
                                labels = card.findChildren(QLabel)
                                if len(labels) >= 2:
                                    value_label = labels[1]

                                    if metric_type == "total_pnl":
                                        value_label.setText(f"{total_pnl:,.2f}")
                                        # 设置颜色：盈利绿色，亏损红色
                                        color = "#4CAF50" if total_pnl >= 0 else "#F44336"
                                        value_label.setStyleSheet(
                                            f"font-size: 20px; font-weight: bold; color: {color};"
                                        )
                                    elif metric_type == "trading_pnl":
                                        # 已实现收益
                                        value_label.setText(f"{trading_pnl:,.2f}")
                                        color = "#00BCD4" if trading_pnl >= 0 else "#F44336"
                                        value_label.setStyleSheet(
                                            f"font-size: 20px; font-weight: bold; color: {color};"
                                        )
                                    elif metric_type == "holding_pnl":
                                        # 未实现收益
                                        value_label.setText(f"{holding_pnl:,.2f}")
                                        color = "#8BC34A" if holding_pnl >= 0 else "#F44336"
                                        value_label.setStyleSheet(
                                            f"font-size: 20px; font-weight: bold; color: {color};"
                                        )
                                    elif metric_type == "return":
                                        value_label.setText(f"{return_rate:.2f}%")
                                        color = "#2196F3" if return_rate >= 0 else "#F44336"
                                        value_label.setStyleSheet(
                                            f"font-size: 20px; font-weight: bold; color: {color};"
                                        )
                                    elif metric_type == "drawdown":
                                        value_label.setText("--")  # 需要历史数据计算
                                    elif metric_type == "sharpe":
                                        value_label.setText("--")  # 需要历史数据计算

        except Exception as e:
            self.logger.error("更新实时指标失败: %s", e)

    def _update_risk_metrics(self, gateway_name: str, risk_metrics: Dict[str, Any]):
        """更新高级风险指标卡片.

        Args:
            gateway_name: 网关名称
            risk_metrics: 风险指标数据
        """
        try:
            # 提取风险指标
            var_95 = risk_metrics.get("var_95", 0)
            cvar_95 = risk_metrics.get("cvar_95", 0)
            volatility = risk_metrics.get("volatility", 0)
            sortino_ratio = risk_metrics.get("sortino_ratio", 0)
            calmar_ratio = risk_metrics.get("calmar_ratio", 0)
            beta = risk_metrics.get("beta")

            # 查找并更新风险指标卡片
            if self.gateway_tab:
                for i in range(self.gateway_tab.count()):
                    tab = self.gateway_tab.widget(i)
                    if tab:
                        cards = tab.findChildren(QGroupBox)
                        for card in cards:
                            gw_name = card.property("gateway_name")
                            metric_type = card.property("metric_type")

                            if gw_name == gateway_name and metric_type:
                                labels = card.findChildren(QLabel)
                                if len(labels) >= 2:
                                    value_label = labels[1]

                                    if metric_type == "var_95":
                                        value_label.setText(f"{var_95*100:.2f}%")
                                    elif metric_type == "cvar_95":
                                        value_label.setText(f"{cvar_95*100:.2f}%")
                                    elif metric_type == "volatility":
                                        value_label.setText(f"{volatility*100:.2f}%")
                                    elif metric_type == "sortino_ratio":
                                        value_label.setText(f"{sortino_ratio:.2f}")
                                    elif metric_type == "calmar_ratio":
                                        value_label.setText(f"{calmar_ratio:.2f}")
                                    elif metric_type == "beta":
                                        if beta is not None:
                                            value_label.setText(f"{beta:.2f}")
                                        else:
                                            value_label.setText("N/A")

        except Exception as e:
            self.logger.error("更新风险指标失败: %s", e)

    def _update_equity_and_drawdown_charts(self, gateway_name: str):
        """更新权益曲线和回撤曲线.

        Args:
            gateway_name: 网关名称
        """
        try:
            if not self.portfolio_service:
                return

            # 获取收益率序列
            returns_result = (
                self.portfolio_service._get_portfolio_returns(  # pylint: disable=protected-access
                    portfolio_name=gateway_name, lookback_days=60
                )
            )

            if not returns_result.get("success"):
                self.logger.warning("无法获取收益率数据: %s", returns_result.get("message"))
                return

            equity_curve = returns_result.get("equity_curve", [])
            returns = returns_result.get("returns", [])

            if not equity_curve or not returns:
                return

            # 计算回撤序列
            import numpy as np

            cumulative = np.array(equity_curve)
            running_max = np.maximum.accumulate(cumulative)
            drawdown = (cumulative - running_max) / running_max * 100  # 转换为百分比

            # 查找并更新图表
            if self.gateway_tab:
                for i in range(self.gateway_tab.count()):
                    tab = self.gateway_tab.widget(i)
                    if tab:
                        # 查找PlotWidget
                        plot_widgets = tab.findChildren(pg.PlotWidget)
                        for plot_widget in plot_widgets:
                            gw_name = plot_widget.property("gateway_name")
                            chart_type = plot_widget.property("chart_type")

                            if gw_name == gateway_name:
                                if chart_type == "equity":
                                    # 更新权益曲线
                                    plot_widget.clear()
                                    x_data = list(range(len(equity_curve)))
                                    plot_widget.plot(
                                        x_data,
                                        equity_curve,
                                        pen=pg.mkPen(color="#4CAF50", width=2),
                                        name="权益曲线",
                                    )
                                    self.logger.debug(
                                        "已更新权益曲线: %s个数据点", len(equity_curve)
                                    )

                                elif chart_type == "drawdown":
                                    # 更新回撤曲线
                                    plot_widget.clear()
                                    x_data = list(range(len(drawdown)))
                                    plot_widget.plot(
                                        x_data,
                                        drawdown,
                                        pen=pg.mkPen(color="#F44336", width=2),
                                        fillLevel=0,
                                        brush=(244, 67, 54, 50),
                                        name="回撤曲线",
                                    )
                                    self.logger.debug("已更新回撤曲线: %s个数据点", len(drawdown))

        except Exception as e:
            self.logger.error("更新曲线图失败: %s", e)

    def _update_historical_performance(
        self, gateway_name: str, history_data: Dict[str, Any], _period: str
    ):
        """更新历史业绩展示.

        Args:
            gateway_name: 网关名称
            history_data: 历史数据
            _period: 统计周期（保留参数，暂未使用）
        """
        try:
            performance_curve = history_data.get("performance_curve", [])
            period_stats = history_data.get("period_statistics", [])
            drawdown_analysis = history_data.get("drawdown_analysis", [])

            # 更新资金曲线图
            self._update_equity_curve(gateway_name, performance_curve)

            # 更新周期统计表格
            self._update_period_statistics_table(gateway_name, period_stats)

            # 更新回撤指标
            if drawdown_analysis:
                analysis = drawdown_analysis[0]
                max_drawdown = analysis.get("max_drawdown", 0)

                # 更新最大回撤卡片
                if self.gateway_tab:
                    for i in range(self.gateway_tab.count()):
                        tab = self.gateway_tab.widget(i)
                        if tab:
                            cards = tab.findChildren(QGroupBox)
                            for card in cards:
                                if (
                                    card.property("gateway_name") == gateway_name
                                    and card.property("metric_type") == "drawdown"
                                ):
                                    labels = card.findChildren(QLabel)
                                    if len(labels) >= 2:
                                        labels[1].setText(f"{max_drawdown:.2f}%")

        except Exception as e:
            self.logger.error("更新历史业绩失败: %s", e)

    def _update_equity_curve(self, gateway_name: str, performance_curve: List[Dict[str, Any]]):
        """更新资金曲线图.

        Args:
            gateway_name: 网关名称
            performance_curve: 业绩曲线数据
        """
        try:
            if not performance_curve:
                return

            # 查找对应的PlotWidget
            if self.gateway_tab:
                for i in range(self.gateway_tab.count()):
                    tab = self.gateway_tab.widget(i)
                    if tab:
                        plot_widgets = tab.findChildren(pg.PlotWidget)
                        for plot_widget in plot_widgets:
                            if plot_widget.property("gateway_name") == gateway_name:
                                # 清除旧数据
                                plot_widget.clear()

                                # 提取数据
                                dates = [p["date"] for p in performance_curve]
                                equities = [p["equity"] for p in performance_curve]

                                # 绘制曲线
                                x = list(range(len(equities)))
                                plot_widget.plot(
                                    x,
                                    equities,
                                    pen=pg.mkPen(color="#4CAF50", width=2),
                                    name="权益曲线",
                                )

                                # 设置X轴标签（显示日期）
                                # 简化显示，每隔一定间隔显示一个日期
                                if len(dates) > 10:
                                    step = len(dates) // 10
                                    ticks = [(i, dates[i]) for i in range(0, len(dates), step)]
                                else:
                                    ticks = [(i, dates[i]) for i in range(len(dates))]

                                axis = plot_widget.getAxis("bottom")
                                axis.setTicks([ticks])

        except Exception as e:
            self.logger.error("更新资金曲线失败: %s", e)

    def _update_period_statistics_table(
        self, gateway_name: str, period_stats: List[Dict[str, Any]]
    ):
        """更新周期统计表格.

        Args:
            gateway_name: 网关名称
            period_stats: 周期统计数据
        """
        try:
            if not period_stats:
                return

            # 查找对应的表格
            if self.gateway_tab:
                for i in range(self.gateway_tab.count()):
                    tab = self.gateway_tab.widget(i)
                    if tab:
                        tables = tab.findChildren(QTableWidget)
                        for table in tables:
                            header_item = table.horizontalHeaderItem(0)
                            if (
                                table.property("gateway_name") == gateway_name
                                and header_item
                                and header_item.text() == "周期"
                            ):
                                # 清空表格
                                table.setRowCount(0)

                                # 填充数据
                                for stat in period_stats:
                                    row = table.rowCount()
                                    table.insertRow(row)

                                    table.setItem(row, 0, QTableWidgetItem(stat.get("period", "")))
                                    table.setItem(
                                        row, 1, QTableWidgetItem(f"{stat.get('pnl', 0):,.2f}")
                                    )
                                    table.setItem(
                                        row,
                                        2,
                                        QTableWidgetItem(f"{stat.get('return_rate', 0):.2f}"),
                                    )
                                    table.setItem(
                                        row,
                                        3,
                                        QTableWidgetItem(f"{stat.get('start_equity', 0):,.2f}"),
                                    )
                                    table.setItem(
                                        row,
                                        4,
                                        QTableWidgetItem(f"{stat.get('end_equity', 0):,.2f}"),
                                    )

        except Exception as e:
            self.logger.error("更新周期统计表格失败: %s", e)

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
        """动态创建组合监控选项卡.

        需求：为激活超过1个策略的网关自动创建监控选项卡（自动组合）。
        为用户自定义组合创建虚拟网关监控选项卡（自定义组合）。
        """
        if not self.gateway_tab:
            return

        # 收集需要创建的组合ID
        current_portfolio_ids = set()

        # 1. 处理自动组合
        auto_portfolios = portfolios.get("auto_portfolios", [])
        for portfolio in auto_portfolios:
            portfolio_id = portfolio.get("id")
            gateway_name = portfolio.get("gateway_name", "")
            strategy_count = portfolio.get("strategy_count", 0)

            if portfolio_id:
                current_portfolio_ids.add(portfolio_id)

                if portfolio_id not in self.monitor_tabs:
                    # 创建新选项卡（自动组合）
                    tab = self._create_monitor_tab_with_data(portfolio)
                    self.monitor_tabs[portfolio_id] = tab

                    # 添加到选项卡（标识为自动组合）
                    self.gateway_tab.addTab(tab, f"🔄 {gateway_name} ({strategy_count}策略)")
                    self.logger.info("创建自动组合监控选项卡: %s", gateway_name)

        # 2. 处理自定义组合
        custom_portfolios = portfolios.get("custom_portfolios", [])
        for portfolio in custom_portfolios:
            portfolio_id = portfolio.get("virtual_gateway_id") or portfolio.get("name")
            portfolio_name = portfolio.get("name", "")
            gateway_names = portfolio.get("gateway_names", [])

            if portfolio_id:
                current_portfolio_ids.add(portfolio_id)

                if portfolio_id not in self.monitor_tabs:
                    # 创建新选项卡（虚拟网关）
                    tab = self._create_monitor_tab_with_data(portfolio)
                    self.monitor_tabs[portfolio_id] = tab

                    # 添加到选项卡（标识为虚拟网关）
                    gw_count = len(gateway_names)
                    self.gateway_tab.addTab(tab, f"🌐 {portfolio_name} ({gw_count}网关)")
                    self.logger.info("创建虚拟网关监控选项卡: %s", portfolio_name)

        # 3. 移除不再存在的组合选项卡
        to_remove = []
        for portfolio_id in self.monitor_tabs:
            if portfolio_id not in current_portfolio_ids:
                to_remove.append(portfolio_id)

        for portfolio_id in to_remove:
            # 查找并移除选项卡
            tab = self.monitor_tabs.pop(portfolio_id)
            for i in range(self.gateway_tab.count()):
                if self.gateway_tab.widget(i) == tab:
                    self.gateway_tab.removeTab(i)
                    self.logger.info("移除组合监控选项卡: %s", portfolio_id)
                    break

    def _create_monitor_tab_with_data(self, portfolio: Dict[str, Any]) -> QWidget:
        """创建带数据的监控选项卡."""
        portfolio_id = portfolio.get("id") or portfolio.get("name") or ""
        gateway_name = portfolio.get("gateway_name") or portfolio.get("name") or ""

        tab = self._create_monitor_tab(gateway_name)

        # 获取监控数据并更新
        self._refresh_portfolio_monitoring(portfolio_id, tab)

        return tab

    def _refresh_portfolio_monitoring(self, portfolio_id: str, _tab: QWidget):
        """刷新组合监控数据.

        Args:
            portfolio_id: 组合ID
            _tab: 监控选项卡组件
        """
        if not self.portfolio_service:
            return

        try:
            # 获取监控数据
            result = self.portfolio_service.get_portfolio_monitoring(portfolio_id)
            if not result.get("success"):
                return

            data = result.get("data", {})

            # 更新实时业绩指标
            self._update_real_time_metrics(portfolio_id, data)

            # 获取历史业绩数据
            history_result = self.portfolio_service.get_historical_performance(
                portfolio_name=portfolio_id, period="daily"
            )
            if history_result.get("success"):
                history_data = history_result.get("data", {})
                self._update_historical_performance(portfolio_id, history_data, "daily")

        except Exception as e:
            self.logger.error("刷新组合监控失败: %s", e)

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
