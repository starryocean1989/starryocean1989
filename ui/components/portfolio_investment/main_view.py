# -*- coding: utf-8 -*-
"""
组合投资界面 - 主视图

混合架构：两个固有业务组件，无独立子界面
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from ....backend.core.vnpy_integration import TerminalEngine as VnPyAdapter
except ImportError:
    try:
        from backend.core.vnpy_integration import TerminalEngine as VnPyAdapter
    except ImportError:
        VnPyAdapter = None

# Import base classes with proper fallback handling

if TYPE_CHECKING:
    # For type checking, use the actual imported classes
    from ...widgets.base_widget import BaseWidget
    from ....utils.logging_utils import LoggerMixin
else:
    # Runtime imports with fallback
    try:
        from ...widgets.base_widget import BaseWidget
        from ....utils.logging_utils import LoggerMixin
    except ImportError:
        try:
            from ui.widgets.base_widget import BaseWidget
            from utils.logging_utils import LoggerMixin
        except ImportError:
            # Create fallback implementations
            class BaseWidget(QWidget):
                """Base widget fallback implementation."""

                def __init__(self, parent=None, title=""):
                    """Initialize base widget."""
                    super().__init__(parent)
                    self._parent = parent
                    self.title = title

                def setup_ui(self):
                    """Set up UI - fallback implementation."""

                def connect_signals(self):
                    """Connect signals - fallback implementation."""

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
                """Logger mixin fallback implementation."""

                @property
                def logger(self):
                    """Get logger instance."""
                    return logging.getLogger(self.__class__.__name__)


class PortfolioInvestment(BaseWidget, LoggerMixin):
    """组合投资主界面"""

    def __init__(self, parent=None):
        """Initialize portfolio investment interface."""
        super().__init__(parent, "组合投资")
        self.logger.info("组合投资界面初始化开始")

        # Initialize UI components
        self.auto_portfolio_table = None
        self.custom_portfolio_table = None
        self.gateway_tab = None
        self.total_pnl_label = None
        self.total_return_label = None
        self.max_drawdown_label = None
        self.sharpe_ratio_label = None
        self.position_table = None
        self.risk_progress = None

        # 更新定时器与就绪标志
        self._update_timer = None
        self.ui_ready = False
        # 初始化VNPY适配器 - 在super().__init__()之后
        self._initialize_vnpy_adapter()

    def setup_ui(self):
        """设置用户界面"""
        try:
            main_layout = QHBoxLayout()
            self.setLayout(main_layout)
            self.setMinimumSize(400, 300)

            # 创建主分割器
            main_splitter = QSplitter(Qt.Orientation.Horizontal)
            main_splitter.setSizes([400, 600])
            main_splitter.setStretchFactor(0, 1)
            main_splitter.setStretchFactor(1, 1)

            # 左侧：组合管理组件（固有组件）
            try:
                left_widget = self._create_portfolio_manager()
            except Exception as e:
                left_widget = QWidget()
                ll = QVBoxLayout(left_widget)
                msg = QLabel(f"左侧组合管理加载失败：{e}")
                msg.setStyleSheet("color:#d32f2f;")
                ll.addWidget(msg)
            main_splitter.addWidget(left_widget)

            # 右侧：组合投资监控组件（固有组件）
            try:
                right_widget = self._create_monitor_panel()
            except Exception as e:
                right_widget = QWidget()
                rl = QVBoxLayout(right_widget)
                msg = QLabel(f"右侧监控面板加载失败：{e}")
                msg.setStyleSheet("color:#d32f2f;")
                rl.addWidget(msg)
            main_splitter.addWidget(right_widget)

            main_layout.addWidget(main_splitter)
            # 界面就绪
            self.ui_ready = True
        except Exception as e:
            # 占位回退，避免整体不可见
            fallback = QWidget()
            fl = QVBoxLayout(fallback)
            msg = QLabel(f"组合投资界面加载失败：{e}\n已切换到占位界面。")

            msg.setStyleSheet("color:#d32f2f;")
            fl.addWidget(msg)
            outer = QHBoxLayout()
            self.setLayout(outer)
            outer.addWidget(fallback)

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
        self.auto_portfolio_table.setHorizontalHeaderLabels(
            ["网关名称", "策略数量", "状态"]
        )
        self.auto_portfolio_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

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
        self.custom_portfolio_table.setHorizontalHeaderLabels(
            ["组合名称", "包含网关", "权重", "操作"]
        )
        self.custom_portfolio_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

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
        gateways = getattr(self, "gateways", None)
        # 容错：数据类型不合法时回退为空
        if not isinstance(gateways, (list, tuple)):
            gateways = []
        self._create_gateway_tabs()

        # 若无任何选项卡，立即加入占位选项卡保证初次渲染可见
        try:
            if self.gateway_tab and self.gateway_tab.count() == 0:
                placeholder = QWidget()
                pl = QVBoxLayout(placeholder)
                msg = QLabel("暂无连接的网关，已显示示例面板。")
                msg.setStyleSheet("color:#555;")
                pl.addWidget(msg)
                demo_table = QTableWidget(0, 3)
                demo_table.setHorizontalHeaderLabels(["组合", "权重", "状态"])
                demo_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                pl.addWidget(demo_table)
                self.gateway_tab.addTab(placeholder, "示例网关")
        except Exception as e:
            # 占位失败也不影响主界面显示
            self.logger.warning("添加占位选项卡失败: %s", e)

        layout.addWidget(self.gateway_tab)

        return widget

    def _create_gateway_tabs(self):
        """创建网关选项卡"""
        # 清空现有选项卡
        if self.gateway_tab:
            self.gateway_tab.clear()

        if self.vnpy_adapter:
            try:
                # 从VNPY获取连接的网关列表
                if hasattr(self.vnpy_adapter, "get_status"):
                    status = self.vnpy_adapter.get_status()
                    connected_gateways = status.get("connected_gateways", [])
                else:
                    connected_gateways = []

                # 为每个连接的网关创建选项卡
                for gateway_name in connected_gateways:
                    tab = self._create_monitor_tab(gateway_name)
                    if self.gateway_tab:
                        self.gateway_tab.addTab(tab, gateway_name)

                # 如果有虚拟网关，也创建选项卡
                # 这里可以根据实际需求添加虚拟网关的逻辑

            except (AttributeError, TypeError, ValueError) as e:
                self.logger.error("创建网关选项卡失败: %s", e)
                self._create_fallback_gateway_tabs()
        else:
            self._create_fallback_gateway_tabs()

    def _create_fallback_gateway_tabs(self):
        """创建备用网关选项卡（VNPY不可用时）"""
        # 示例网关选项卡
        gateway_names = ["CTP-001", "虚拟网关-001", "IB-001"]

        for gateway_name in gateway_names:
            tab = self._create_monitor_tab(gateway_name)
            if self.gateway_tab:
                self.gateway_tab.addTab(tab, gateway_name)

    def _create_monitor_tab(self, gateway_name):
        """为指定网关创建监控选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 记录网关名称用于调试
        self.logger.debug("创建监控选项卡: %s", gateway_name)

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
        self.position_table.setHorizontalHeaderLabels(
            ["品种", "持仓", "成本", "市值", "盈亏"]
        )
        self.position_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

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
        if self.gateway_tab:
            self.gateway_tab.currentChanged.connect(self._on_gateway_tab_changed)

        # 当没有任何网关选项卡时，加入占位选项卡，避免界面空白
        if self.gateway_tab and self.gateway_tab.count() == 0:
            placeholder = QWidget()
            pl = QVBoxLayout(placeholder)
            msg = QLabel("暂无连接的网关，当前显示示例面板。")
            msg.setStyleSheet("color:#555;")
            pl.addWidget(msg)
            # 简易示例占位表格
            demo_table = QTableWidget(0, 3)
            demo_table.setHorizontalHeaderLabels(["组合", "权重", "状态"])
            demo_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            pl.addWidget(demo_table)
            self.gateway_tab.addTab(placeholder, "示例网关")

        # 启动更新定时器
        self.start_update_timer(2000, self._update_portfolio_data)

    def _initialize_vnpy_adapter(self):
        """初始化VNPY适配器"""
        # 确保属性始终存在
        self.vnpy_adapter = None

        try:
            if VnPyAdapter is not None:
                self.vnpy_adapter = VnPyAdapter()
                self.logger.info("VNPY适配器初始化完成")
            else:
                self.vnpy_adapter = None
                self.logger.warning("VNPY适配器不可用")
        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            self.logger.error("VNPY适配器初始化失败: %s", e)
            self.vnpy_adapter = None

    def _create_custom_portfolio(self):
        """新建自定义组合"""
        self.show_info("新建自定义组合功能开发中...")

    def _delete_custom_portfolio(self):
        """删除自定义组合"""
        self.show_info("删除自定义组合功能开发中...")

    def _on_gateway_tab_changed(self, index):
        """网关选项卡切换"""
        if index >= 0 and self.gateway_tab:
            tab_text = self.gateway_tab.tabText(index)
            self.logger.info("切换到网关: %s", tab_text)

    def start_update_timer(self, interval: int = 1000, callback=None):
        """启动更新定时器（安全守卫）"""
        if not getattr(self, "ui_ready", False):
            return
        if callback is None:
            return
        if getattr(self, "_update_timer", None) is None:
            self._update_timer = QTimer(self)
            self._update_timer.timeout.connect(callback)
        if self._update_timer:
            self._update_timer.start(int(interval) if interval else 2000)

    def stop_update_timer(self):
        """停止更新定时器"""
        try:
            timer = getattr(self, "_update_timer", None)
            if timer:
                timer.stop()
        finally:
            self._update_timer = None

    def _update_portfolio_data(self):
        """更新组合数据"""
        # 空控件守卫：表格或选项卡未创建则不更新
        if any(getattr(self, name, None) is None for name in [
            "auto_portfolio_table", "custom_portfolio_table", "gateway_tab"
        ]):
            return

        if self.vnpy_adapter:
            try:
                # 从VNPY获取真实数据
                if hasattr(self.vnpy_adapter, "get_status"):
                    status = self.vnpy_adapter.get_status()
                    # 更新自动组合表格
                    self._update_auto_portfolios(status)
                else:
                    # 使用模拟数据
                    self._update_auto_portfolios_fallback()

                # 更新自定义组合表格
                if hasattr(self.vnpy_adapter, "get_status"):
                    self._update_custom_portfolios()
                else:
                    self._update_custom_portfolios_fallback()

                # 更新监控数据
                self._update_monitor_data()

            except (AttributeError, TypeError, ValueError, RuntimeError) as e:
                self.logger.error("更新组合数据失败: %s", e)
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
        if self.auto_portfolio_table:
            self.auto_portfolio_table.setRowCount(0)

        connected_gateways = status.get("connected_gateways", [])

        for i, gateway_name in enumerate(connected_gateways):
            if self.auto_portfolio_table:
                self.auto_portfolio_table.insertRow(i)

                # 网关名称
                self.auto_portfolio_table.setItem(i, 0, QTableWidgetItem(gateway_name))

                # 策略数量（模拟，实际需要从VNPY获取）
                strategies_count = "多个策略"  # 需要实际实现策略计数
                self.auto_portfolio_table.setItem(
                    i, 1, QTableWidgetItem(strategies_count)
                )

                # 状态（已连接的网关都是运行中）
                status_text = "运行中"
                self.auto_portfolio_table.setItem(i, 2, QTableWidgetItem(status_text))

                # 设置状态颜色
                status_item = self.auto_portfolio_table.item(i, 2)
                if status_item:
                    status_item.setBackground(QColor("#4caf50"))

    def _update_auto_portfolios_fallback(self):
        """备用自动组合更新（VNPY不可用时）"""
        # 清空表格
        if self.auto_portfolio_table:
            self.auto_portfolio_table.setRowCount(0)

        # 模拟数据
        auto_data = [
            ("CTP主账户", "3个策略", "运行中"),
            ("IB国际账户", "2个策略", "运行中"),
        ]

        for i, (gateway, strategies, status) in enumerate(auto_data):
            if self.auto_portfolio_table:
                self.auto_portfolio_table.insertRow(i)
                self.auto_portfolio_table.setItem(i, 0, QTableWidgetItem(gateway))
                self.auto_portfolio_table.setItem(i, 1, QTableWidgetItem(strategies))
                self.auto_portfolio_table.setItem(i, 2, QTableWidgetItem(status))

                # 设置状态颜色
                status_item = self.auto_portfolio_table.item(i, 2)
                if status_item:
                    if status == "运行中":
                        status_item.setBackground(QColor("#4caf50"))
                    else:
                        status_item.setBackground(QColor("#ff9800"))

    def _update_custom_portfolios(self):
        """更新自定义组合"""
        # 清空表格
        if self.custom_portfolio_table:
            self.custom_portfolio_table.setRowCount(0)

        # 模拟数据
        custom_data = [
            ("成长组合", "CTP主账户, IB国际账户", "50%, 50%", "编辑"),
            ("价值组合", "CTP主账户", "100%", "编辑"),
        ]

        for i, (name, gateways, weights, operation) in enumerate(custom_data):
            if self.custom_portfolio_table:
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
        if self.custom_portfolio_table:
            self.custom_portfolio_table.setRowCount(0)

        # 模拟数据
        custom_data = [
            ("成长组合", "CTP主账户, IB国际账户", "50%, 50%", "编辑"),
            ("价值组合", "CTP主账户", "100%", "编辑"),
        ]

        for i, (name, gateways, weights, operation) in enumerate(custom_data):
            if self.custom_portfolio_table:
                self.custom_portfolio_table.insertRow(i)
                self.custom_portfolio_table.setItem(i, 0, QTableWidgetItem(name))
                self.custom_portfolio_table.setItem(i, 1, QTableWidgetItem(gateways))
                self.custom_portfolio_table.setItem(i, 2, QTableWidgetItem(weights))

                # 操作按钮
                operation_btn = QPushButton(operation)
                self.custom_portfolio_table.setCellWidget(i, 3, operation_btn)

    def _update_monitor_data(self):
        # 就绪与控件守卫
        if not getattr(self, "ui_ready", False):
            return
        tab = getattr(self, "gateway_tab", None)
        if tab is None or not hasattr(tab, "currentIndex"):
            return
        # 数据容错：组合数据必须为 dict/list
        data = getattr(self, "portfolio_data", None)
        if data is None or not isinstance(data, (dict, list)):
            return
        """更新监控数据"""
        # 就绪与控件守卫
        if not getattr(self, "ui_ready", False):
            return
        if not getattr(self, "gateway_tab", None):
            return
        if self.gateway_tab.count() == 0:
            return
        if not self.vnpy_adapter:
            return

        if self.gateway_tab:
            current_tab = self.gateway_tab.currentWidget()
            if current_tab:
                # 获取当前网关名称
                current_index = self.gateway_tab.currentIndex()
                gateway_name = self.gateway_tab.tabText(current_index)

                try:
                    # 从VNPY获取持仓信息
                    positions = None
                    account_info = None

                    if hasattr(self.vnpy_adapter, "get_positions"):
                        positions = self.vnpy_adapter.get_positions(gateway_name)
                    else:
                        self.logger.warning("TerminalEngine 缺少 get_positions 方法")

                    if hasattr(self.vnpy_adapter, "get_account_info"):
                        account_info = self.vnpy_adapter.get_account_info(gateway_name)
                    else:
                        self.logger.warning("TerminalEngine 缺少 get_account_info 方法")

                    # 更新持仓表格
                    if positions is not None:
                        self._update_positions_table(positions)

                    # 更新账户信息
                    if account_info is not None:
                        self._update_account_info(account_info)

                except (AttributeError, TypeError, ValueError, RuntimeError) as e:
                    self.logger.error("更新监控数据失败: %s", e)

    def _update_positions_table(self, positions):
        """更新持仓表格"""
        # 当前示例未将 position_table 绑定到具体选项卡，直接判空返回
        if getattr(self, "position_table", None) is None:
            return
        if not positions:
            return
        # 简化：仅清空并填充前几行示例
        self.position_table.setRowCount(0)
        for i, pos in enumerate(positions[:10]):
            self.position_table.insertRow(i)
            self.position_table.setItem(i, 0, QTableWidgetItem(str(pos.get("symbol", "--"))))
            self.position_table.setItem(i, 1, QTableWidgetItem(str(pos.get("volume", 0))))
            self.position_table.setItem(i, 2, QTableWidgetItem(str(pos.get("cost", 0))))
            self.position_table.setItem(i, 3, QTableWidgetItem(str(pos.get("market_value", 0))))
            self.position_table.setItem(i, 4, QTableWidgetItem(str(pos.get("pnl", 0))))

    def _update_account_info(self, account_info):
        """更新账户信息"""
        if not account_info:
            return
        # 判空守卫
        for name in ["total_pnl_label", "total_return_label", "max_drawdown_label", "sharpe_ratio_label"]:
            if getattr(self, name, None) is None:
                return
        self.total_pnl_label.setText(str(account_info.get("total_pnl", "--")))
        self.total_return_label.setText(str(account_info.get("total_return", "--")))
        self.max_drawdown_label.setText(str(account_info.get("max_drawdown", "--")))
        self.sharpe_ratio_label.setText(str(account_info.get("sharpe_ratio", "--")))

    def refresh_data(self):
        """刷新数据"""
        try:
            self._update_portfolio_data()
            self.show_info("组合投资数据已刷新")
        except Exception as e:
            self.show_error(f"刷新数据失败: {e}")

    def on_close(self):
        """关闭处理"""
        try:
            self.stop_update_timer()
        finally:
            self.logger.info("组合投资界面已关闭")
