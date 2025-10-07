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
    from backend.core.vnpy_integration import TerminalEngine as VnPyAdapter
except ImportError:
    VnPyAdapter = None


# Import base classes with proper fallback handling

if TYPE_CHECKING:
    # For type checking, use the actual imported classes
    from ..widgets.base_widget import BaseWidget  # type: ignore
    from backend.core.utils.logging_utils import LoggerMixin  # type: ignore
else:
    # Runtime imports with fallback
    try:
        from ..widgets.base_widget import BaseWidget  # type: ignore
        from backend.core.utils.logging_utils import LoggerMixin  # type: ignore
    except ImportError:
        try:
            from ui.widgets.base_widget import BaseWidget  # type: ignore
            from backend.core.utils.logging_utils import LoggerMixin  # type: ignore
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

        # Initialize VNPY adapter first
        self.vnpy_adapter = None
        self._initialize_vnpy_adapter()

        # Initialize UI components - 移除容易导致冲突的单例变量
        self.auto_portfolio_table = None
        self.custom_portfolio_table = None
        self.gateway_tab = None

        # 监控数据存储 - 用于管理多个选项卡的数据
        self.monitor_data = {}

        # 更新定时器与就绪标志
        self._update_timer = None
        self.ui_ready = False

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
            except (AttributeError, TypeError, ValueError, RuntimeError) as e:
                left_widget = QWidget()
                ll = QVBoxLayout(left_widget)
                msg = QLabel(f"左侧组合管理加载失败：{e}")
                msg.setStyleSheet("color:#d32f2f;")
                ll.addWidget(msg)
            main_splitter.addWidget(left_widget)

            # 右侧：组合投资监控组件（固有组件）
            try:
                right_widget = self._create_monitor_panel()
            except (AttributeError, TypeError, ValueError, RuntimeError) as e:
                right_widget = QWidget()
                rl = QVBoxLayout(right_widget)
                msg = QLabel(f"右侧监控面板加载失败：{e}")
                msg.setStyleSheet("color:#d32f2f;")
                rl.addWidget(msg)
            main_splitter.addWidget(right_widget)

            main_layout.addWidget(main_splitter)
            # 界面就绪
            self.ui_ready = True
        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
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
        """创建组合投资监控组件 - 保证始终成功"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 标题
        title_label = QLabel("📈 组合投资监控")
        title_label.setStyleSheet("font-weight: bold; font-size: 16px; padding: 5px;")
        layout.addWidget(title_label)

        # 初始化监控数据存储
        self.monitor_data = {}

        # 创建网关选项卡 - 使用保证成功的方法
        self.gateway_tab = QTabWidget()
        self.gateway_tab.setTabsClosable(True)  # 允许关闭Tab
        self.gateway_tab.setMovable(True)  # 允许拖动Tab
        self.gateway_tab.tabCloseRequested.connect(self._on_tab_close_requested)
        self._ensure_monitor_content()

        layout.addWidget(self.gateway_tab)
        return widget

    def _create_metric_card(self, title: str, value: str, color: str):
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
        value_label.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {color};"
        )
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(value_label)

        return card

    def _on_tab_close_requested(self, index: int):
        """处理Tab关闭请求."""
        if not self.gateway_tab:
            return

        # 获取要关闭的Tab名称
        tab_name = self.gateway_tab.tabText(index)

        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "确认关闭",
            f"确定要关闭监控 '{tab_name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.gateway_tab.removeTab(index)
            self.show_info(f"已关闭监控: {tab_name}")

    def _refresh_monitor_data(self, gateway_name: str):
        """刷新监控数据."""
        self.show_info(f"刷新监控数据: {gateway_name}")
        # 这里可以调用后端API刷新数据

    def _export_monitor_report(self, gateway_name: str):
        """导出监控报告."""
        from PySide6.QtWidgets import QFileDialog

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "导出监控报告",
            f"{gateway_name}_监控报告.html",
            "HTML Files (*.html);;PDF Files (*.pdf);;All Files (*)",
        )

        if filename:
            self.show_info(f"导出报告到: {filename}")
            # 这里可以实现实际的报告导出逻辑

    def _ensure_monitor_content(self):
        """确保监控面板有内容显示 - 多层级备份机制"""
        try:
            # 第一层：尝试创建真实网关选项卡
            self._try_create_real_gateway_tabs()

            # 检查是否成功创建了选项卡
            if self.gateway_tab and self.gateway_tab.count() > 0:
                self.logger.info("成功创建网关选项卡")
                return

        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            self.logger.warning("创建真实网关选项卡失败: %s", e)

        try:
            # 第二层：创建示例监控选项卡
            self._create_demo_monitor_tab_safe()

            if self.gateway_tab and self.gateway_tab.count() > 0:
                self.logger.info("成功创建示例监控选项卡")
                return

        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            self.logger.warning("创建示例监控选项卡失败: %s", e)

        # 第三层：最简化的占位选项卡（绝对不会失败）
        self._create_minimal_monitor_tab()

    def _try_create_real_gateway_tabs(self):
        """尝试创建真实网关选项卡"""
        if not self.vnpy_adapter:
            return

        if not hasattr(self.vnpy_adapter, "get_status"):
            return

        status = self.vnpy_adapter.get_status()
        connected_gateways = status.get("connected_gateways", [])

        for gateway_name in connected_gateways:
            tab = self._create_monitor_tab(gateway_name)
            if self.gateway_tab:
                self.gateway_tab.addTab(tab, gateway_name)
                self.logger.info("创建真实网关选项卡: %s", gateway_name)

    def _create_demo_monitor_tab_safe(self):
        """安全创建示例监控选项卡"""
        demo_tab = self._create_demo_monitor_tab()
        if self.gateway_tab:
            self.gateway_tab.addTab(demo_tab, "📊 示例网关")

    def _create_minimal_monitor_tab(self):
        """创建最简化的监控选项卡（绝对不会失败）"""
        try:
            tab = QWidget()
            layout = QVBoxLayout(tab)

            # 简单的欢迎信息
            welcome_label = QLabel("👋 欢迎使用组合投资监控")
            welcome_label.setStyleSheet(
                "font-size: 16px; font-weight: bold; color: #2196F3; padding: 20px;"
            )
            welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(welcome_label)

            # 状态信息
            status_label = QLabel("🔄 正在加载监控数据...")
            status_label.setStyleSheet("color: #666; font-size: 14px; padding: 10px;")
            status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(status_label)

            # 简单的进度条
            progress = QProgressBar()
            progress.setRange(0, 0)  # 无限进度条
            progress.setStyleSheet("QProgressBar { margin: 20px; }")
            layout.addWidget(progress)

            # 添加伸缩空间
            layout.addStretch()

            if self.gateway_tab:
                self.gateway_tab.addTab(tab, "📊 监控面板")
                self.logger.info("成功创建最简化监控选项卡")

        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            self.logger.error("创建最简化监控选项卡也失败: %s", e)
            # 最后的最后手段：空的QWidget
            empty_tab = QWidget()
            if self.gateway_tab:
                self.gateway_tab.addTab(empty_tab, "监控")

    def _create_gateway_tabs(self):
        """创建网关选项卡 - 修复版，确保始终有可见内容"""
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
                        self.logger.info("创建网关选项卡: %s", gateway_name)

                # 如果没有任何网关连接，创建示例选项卡
                if not connected_gateways:
                    self.logger.info("无连接网关，创建示例选项卡")
                    self._create_fallback_gateway_tabs()

            except (AttributeError, TypeError, ValueError, RuntimeError) as e:
                self.logger.error("创建网关选项卡失败: %s", e)
                self._create_fallback_gateway_tabs()
        else:
            self.logger.warning("VNPY适配器不可用，创建示例选项卡")
            self._create_fallback_gateway_tabs()

    def _create_fallback_gateway_tabs(self):
        """创建备用网关选项卡（VNPY不可用时）"""
        try:
            # 创建一个示例监控选项卡，而不是多个
            demo_tab = self._create_demo_monitor_tab()
            if self.gateway_tab:
                self.gateway_tab.addTab(demo_tab, "示例网关")
                self.logger.info("已创建示例网关选项卡")
        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            self.logger.error("创建示例网关选项卡失败: %s", e)
            # 创建最基础的占位选项卡
            self._create_minimal_monitor_tab()

    def _create_monitor_tab(self, gateway_name):
        """为指定网关创建监控选项卡（优化版）"""
        tab = QWidget()
        main_layout = QVBoxLayout(tab)

        # 记录网关名称用于调试
        self.logger.debug("创建监控选项卡: %s", gateway_name)

        # 为每个选项卡创建独立的控件引用，避免共享实例变量
        tab_data = {
            "gateway_name": gateway_name,
            "total_pnl_label": None,
            "total_return_label": None,
            "max_drawdown_label": None,
            "sharpe_ratio_label": None,
            "position_table": None,
            "risk_progress": None,
            "equity_curve": None,  # 资金曲线图
        }

        # 顶部工具栏
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel(f"网关: {gateway_name}"))
        toolbar_layout.addStretch()

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setToolTip("刷新监控数据")
        refresh_btn.clicked.connect(lambda: self._refresh_monitor_data(gateway_name))
        toolbar_layout.addWidget(refresh_btn)

        export_btn = QPushButton("📤 导出")
        export_btn.setToolTip("导出监控报告")
        export_btn.clicked.connect(lambda: self._export_monitor_report(gateway_name))
        toolbar_layout.addWidget(export_btn)

        main_layout.addLayout(toolbar_layout)

        # 业绩概览组（使用卡片式布局）
        overview_group = QGroupBox("实时业绩概览")
        overview_main_layout = QVBoxLayout(overview_group)

        # 使用网格布局显示关键指标卡片
        cards_layout = QHBoxLayout()

        # 盈亏卡片
        pnl_card = self._create_metric_card("总盈亏", "--", "#4CAF50")
        tab_data["total_pnl_label"] = pnl_card
        cards_layout.addWidget(pnl_card)

        # 收益率卡片
        return_card = self._create_metric_card("总收益率", "--", "#2196F3")
        tab_data["total_return_label"] = return_card
        cards_layout.addWidget(return_card)

        # 最大回撤卡片
        dd_card = self._create_metric_card("最大回撤", "--", "#FF9800")
        tab_data["max_drawdown_label"] = dd_card
        cards_layout.addWidget(dd_card)

        # 夏普比率卡片
        sharpe_card = self._create_metric_card("夏普比率", "--", "#9C27B0")
        tab_data["sharpe_ratio_label"] = sharpe_card
        cards_layout.addWidget(sharpe_card)

        overview_main_layout.addLayout(cards_layout)
        main_layout.addWidget(overview_group)

        # 资金曲线图（可选，需要pyqtgraph）
        try:
            import pyqtgraph as pg

            equity_group = QGroupBox("资金曲线")
            equity_layout = QVBoxLayout(equity_group)

            equity_widget = pg.PlotWidget()
            equity_widget.setBackground("#1E1E1E")
            equity_widget.setMinimumHeight(200)
            equity_widget.setLabel("left", "资金", units="元")
            equity_widget.setLabel("bottom", "时间")
            equity_widget.showGrid(x=True, y=True)
            tab_data["equity_curve"] = equity_widget

            equity_layout.addWidget(equity_widget)
            main_layout.addWidget(equity_group)
        except ImportError:
            # 如果没有pyqtgraph，显示文本提示
            equity_placeholder = QLabel("📈 资金曲线图（需要安装pyqtgraph）")
            equity_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            equity_placeholder.setStyleSheet("color: #888; padding: 20px;")
            main_layout.addWidget(equity_placeholder)

        # 持仓情况组
        position_group = QGroupBox("持仓情况")
        position_layout = QVBoxLayout(position_group)

        tab_data["position_table"] = QTableWidget(0, 5)
        tab_data["position_table"].setHorizontalHeaderLabels(
            ["品种", "持仓", "成本", "市值", "盈亏"]
        )
        tab_data["position_table"].horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        position_layout.addWidget(tab_data["position_table"])
        main_layout.addWidget(position_group)

        # 风险指标组
        risk_group = QGroupBox("风险指标")
        risk_layout = QVBoxLayout(risk_group)

        tab_data["risk_progress"] = QProgressBar()
        tab_data["risk_progress"].setRange(0, 100)
        risk_layout.addWidget(QLabel("风险等级:"))
        risk_layout.addWidget(tab_data["risk_progress"])

        main_layout.addWidget(risk_group)

        # 将tab_data存储到选项卡对象中
        tab.tab_data = tab_data  # type: ignore

        # 存储到monitor_data中用于更新
        if not hasattr(self, "monitor_data"):
            self.monitor_data = {}
        self.monitor_data[gateway_name] = tab_data

        return tab

    def connect_signals(self):
        """连接信号槽"""
        # 初始化VNPY适配器
        self._initialize_vnpy_adapter()

        # 连接网关选项卡切换信号
        if self.gateway_tab:
            self.gateway_tab.currentChanged.connect(self._on_gateway_tab_changed)

        # 确保至少有一个选项卡（在_ensure_monitor_content中已处理）
        # 不需要在这里再次检查和创建

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
            self.logger.debug("界面未就绪，不启动定时器")
            return
        if callback is None:
            self.logger.debug("无回调函数，不启动定时器")
            return

        try:
            # 停止旧定时器
            self.stop_update_timer()

            # 创建新定时器
            self._update_timer = QTimer(self)
            self._update_timer.timeout.connect(callback)
            self._update_timer.start(int(interval) if interval else 2000)
            self.logger.debug("定时器已启动，间隔: %sms", interval)
        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            self.logger.error("启动定时器失败: %s", e)

    def stop_update_timer(self):
        """停止更新定时器"""
        try:
            timer = getattr(self, "_update_timer", None)
            if timer and timer.isActive():
                timer.stop()
                self.logger.debug("定时器已停止")
        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            self.logger.error("停止定时器失败: %s", e)
        finally:
            self._update_timer = None

    def _update_portfolio_data(self):
        """更新组合数据"""
        # 空控件守卫：表格或选项卡未创建则不更新
        if any(
            getattr(self, name, None) is None
            for name in [
                "auto_portfolio_table",
                "custom_portfolio_table",
                "gateway_tab",
            ]
        ):
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
        """更新监控数据 - 修复版，支持无网关情况"""
        # 就绪守卫
        if not getattr(self, "ui_ready", False):
            return

        # 控件守卫
        if not getattr(self, "gateway_tab", None):
            self.logger.debug("gateway_tab未初始化，跳过更新")
            return

        # 处理无网关情况：显示示例数据而不是空白
        if not self.gateway_tab or self.gateway_tab.count() == 0:
            self.logger.debug("无网关连接，跳过更新")
            return

        # 有网关时正常更新逻辑
        if self.vnpy_adapter and self.gateway_tab:
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
                        self._update_positions_table(gateway_name, positions)

                    # 更新账户信息
                    if account_info is not None:
                        self._update_account_info(gateway_name, account_info)

                except (AttributeError, TypeError, ValueError, RuntimeError) as e:
                    self.logger.error("更新监控数据失败: %s", e)

    def _update_positions_table(self, gateway_name, positions):
        """更新持仓表格"""
        if not hasattr(self, "monitor_data") or gateway_name not in self.monitor_data:
            return

        tab_data = self.monitor_data[gateway_name]
        position_table = tab_data.get("position_table")

        if position_table is None or not positions:
            return

        # 清空并填充数据
        try:
            position_table.setRowCount(0)

            # 处理positions可能是字典或列表的情况
            if isinstance(positions, dict):
                # 如果是字典，将值转换为列表
                positions_list = list(positions.values())
            elif isinstance(positions, list):
                # 如果是列表，直接使用
                positions_list = positions
            else:
                # 其他类型，记录错误并返回
                self.logger.error(
                    "positions类型错误: %s, 值: %s", type(positions), positions
                )
                return

            # 限制显示数量，避免表格过大
            for i, pos in enumerate(positions_list[:10]):
                # 确保pos是字典类型
                if not isinstance(pos, dict):
                    self.logger.warning("持仓项不是字典类型: %s", type(pos))
                    continue

                position_table.insertRow(i)
                position_table.setItem(
                    i, 0, QTableWidgetItem(str(pos.get("symbol", "--")))
                )
                position_table.setItem(
                    i, 1, QTableWidgetItem(str(pos.get("volume", 0)))
                )
                position_table.setItem(i, 2, QTableWidgetItem(str(pos.get("cost", 0))))
                position_table.setItem(
                    i, 3, QTableWidgetItem(str(pos.get("market_value", 0)))
                )
                position_table.setItem(i, 4, QTableWidgetItem(str(pos.get("pnl", 0))))
        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            self.logger.error("更新持仓表格失败: %s", e)

    def _update_account_info(self, gateway_name, account_info):
        """更新账户信息"""
        if not account_info:
            return

        if not hasattr(self, "monitor_data") or gateway_name not in self.monitor_data:
            return

        tab_data = self.monitor_data[gateway_name]

        # 更新各个标签
        try:
            if tab_data.get("total_pnl_label"):
                tab_data["total_pnl_label"].setText(
                    str(account_info.get("total_pnl", "--"))
                )
            if tab_data.get("total_return_label"):
                tab_data["total_return_label"].setText(
                    str(account_info.get("total_return", "--"))
                )
            if tab_data.get("max_drawdown_label"):
                tab_data["max_drawdown_label"].setText(
                    str(account_info.get("max_drawdown", "--"))
                )
            if tab_data.get("sharpe_ratio_label"):
                tab_data["sharpe_ratio_label"].setText(
                    str(account_info.get("sharpe_ratio", "--"))
                )
        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            self.logger.error("更新账户信息失败: %s", e)

    def _show_demo_monitor_panel(self):
        """显示示例监控面板（无网关连接时）"""
        try:
            # 清空所有选项卡，重新创建示例选项卡
            if self.gateway_tab:
                self.gateway_tab.clear()

                # 创建示例网关选项卡
                demo_tab = self._create_demo_monitor_tab()
                self.gateway_tab.addTab(demo_tab, "示例网关")

                self.logger.info("已显示示例监控面板")
        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            self.logger.error("显示示例监控面板失败: %s", e)

    def _create_demo_monitor_tab(self):
        """创建示例监控选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 状态提示
        status_label = QLabel("📋 当前无活跃网关连接\n以下显示的是示例数据")
        status_label.setStyleSheet(
            """
            color: #666;
            font-size: 12px;
            padding: 10px;
            background-color: #f5f5f5;
            border-radius: 5px;
        """
        )
        layout.addWidget(status_label)

        # 业绩概览组
        overview_group = QGroupBox("示例业绩概览")
        overview_layout = QFormLayout(overview_group)

        demo_data = {
            "总盈亏": "+1,250.00",
            "总收益率": "+2.5%",
            "最大回撤": "-5.2%",
            "夏普比率": "1.85",
        }

        for label_text, value in demo_data.items():
            label = QLabel(value)
            label.setStyleSheet(
                "font-weight: bold; color: #2e7d32;"
                if value.startswith("+")
                else "font-weight: bold; color: #d32f2f;"
            )
            overview_layout.addRow(label_text + ":", label)

        layout.addWidget(overview_group)

        # 持仓情况组
        position_group = QGroupBox("示例持仓情况")
        position_layout = QVBoxLayout(position_group)

        demo_positions = [
            ("螺纹钢2501", "10手", "3,500.00", "35,250.00", "+250.00"),
            ("沪深300股指", "5手", "4,200.00", "21,500.00", "+500.00"),
            ("沪铜2501", "3手", "68,000.00", "206,400.00", "+1,400.00"),
        ]

        position_table = QTableWidget(len(demo_positions), 5)
        position_table.setHorizontalHeaderLabels(
            ["品种", "持仓", "成本", "市值", "盈亏"]
        )
        position_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        for i, (symbol, volume, cost, market_value, pnl) in enumerate(demo_positions):
            position_table.setItem(i, 0, QTableWidgetItem(symbol))
            position_table.setItem(i, 1, QTableWidgetItem(volume))
            position_table.setItem(i, 2, QTableWidgetItem(cost))
            position_table.setItem(i, 3, QTableWidgetItem(market_value))

            pnl_item = QTableWidgetItem(pnl)
            if pnl.startswith("+"):
                pnl_item.setBackground(QColor("#e8f5e8"))
            else:
                pnl_item.setBackground(QColor("#ffebee"))
            position_table.setItem(i, 4, pnl_item)

        position_layout.addWidget(position_table)
        layout.addWidget(position_group)

        # 风险指标组
        risk_group = QGroupBox("示例风险指标")
        risk_layout = QVBoxLayout(risk_group)

        risk_progress = QProgressBar()
        risk_progress.setRange(0, 100)
        risk_progress.setValue(25)  # 低风险
        risk_layout.addWidget(QLabel("风险等级:"))
        risk_layout.addWidget(risk_progress)

        # 风险等级标签
        risk_label = QLabel("低风险 - 系统运行正常")
        risk_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
        risk_layout.addWidget(risk_label)

        layout.addWidget(risk_group)

        return tab

    def refresh_data(self):
        """刷新数据"""
        try:
            self._update_portfolio_data()
            self.show_info("组合投资数据已刷新")
        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            self.show_error(f"刷新数据失败: {e}")

    def on_close(self):
        """关闭处理"""
        try:
            self.stop_update_timer()
        finally:
            self.logger.info("组合投资界面已关闭")
