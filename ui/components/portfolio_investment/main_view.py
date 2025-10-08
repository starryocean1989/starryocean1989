# -*- coding: utf-8 -*-
"""
组合投资界面 - 主视图

混合架构：两个固有业务组件，无独立子界面
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
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


# Import base classes - no fallback, fail fast

if TYPE_CHECKING:
    # For type checking, use the actual imported classes
    from ..widgets.base_widget import BaseWidget  # type: ignore

    from backend.core.utils.logging_utils import LoggerMixin  # type: ignore
else:
    # Runtime imports - fail if dependencies are missing
    try:
        from ..widgets.base_widget import BaseWidget  # type: ignore
        from backend.core.utils.logging_utils import LoggerMixin  # type: ignore
    except ImportError:
        try:
            from ui.widgets.base_widget import BaseWidget  # type: ignore
            from backend.core.utils.logging_utils import LoggerMixin  # type: ignore
        except ImportError as e:
            raise ImportError(
                f"无法导入必要的UI组件: {e}\n"
                "请确保已正确安装所有依赖：pip install -r requirements.txt"
            )


class PortfolioInvestment(BaseWidget, LoggerMixin):
    """组合投资主界面"""

    def __init__(self, parent=None):
        """Initialize portfolio investment interface."""
        # Initialize all attributes BEFORE calling super().__init__
        # because BaseWidget may call setup_ui() automatically

        # Initialize VNPY adapter first
        self.vnpy_adapter = None

        # Initialize UI components - 移除容易导致冲突的单例变量
        self.auto_portfolio_table = None
        self.custom_portfolio_table = None
        self.gateway_tab = None

        # 监控数据存储 - 用于管理多个选项卡的数据
        self.monitor_data = {}

        # 更新定时器与就绪标志
        self._update_timer = None
        self.ui_ready = False

        # Now call parent init which may trigger setup_ui()
        super().__init__(parent, "组合投资")
        self.logger.info("组合投资界面初始化开始")

        # Initialize VNPY adapter after UI setup
        self._initialize_vnpy_adapter()

    def setup_ui(self):
        """设置用户界面"""
        # 设置组件大小策略为扩展
        from PySide6.QtWidgets import QSizePolicy

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.setLayout(main_layout)
        self.setMinimumSize(600, 400)

        # 创建主分割器
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setSizes([400, 600])
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 1)

        # 左侧：组合管理组件（固有组件）
        left_widget = self._create_portfolio_manager()
        main_splitter.addWidget(left_widget)

        # 右侧：组合投资监控组件（固有组件）
        right_widget = self._create_monitor_panel()
        main_splitter.addWidget(right_widget)

        main_layout.addWidget(main_splitter)
        # 界面就绪
        self.ui_ready = True

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
        value_label.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {color};")
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
        """确保监控面板有内容显示 - 只创建真实网关选项卡"""
        # 尝试创建真实网关选项卡
        self._try_create_real_gateway_tabs()

        # 如果没有网关，显示提示占位符
        if self.gateway_tab and self.gateway_tab.count() == 0:
            self.logger.info("无可用网关，创建提示占位符")
            self._create_no_gateway_placeholder()

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

    def _create_no_gateway_placeholder(self):
        """创建无网关提示占位符"""
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 图标
        icon_label = QLabel("🔌")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 48px;")
        layout.addWidget(icon_label)

        # 标题
        title_label = QLabel("未连接网关")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #999; margin: 10px;")
        layout.addWidget(title_label)

        # 提示信息
        hint_label = QLabel("当前无可用网关连接\n请先在「交易网关」界面配置并连接网关")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet("color: #666; font-size: 12px;")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        if self.gateway_tab:
            self.gateway_tab.addTab(placeholder, "💡 提示")

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

                # 如果没有任何网关连接，显示错误
                if not connected_gateways:
                    self.logger.warning("无连接网关")
                    raise RuntimeError("无可用网关连接，请先配置并连接网关")

            except Exception as e:
                self.logger.error("创建网关选项卡失败: %s", e)
                raise
        else:
            raise RuntimeError("VnPy适配器不可用，无法创建网关监控")

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

        # 资金曲线图
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
        if VnPyAdapter is None:
            raise ImportError("VnPy适配器不可用，请检查VnPy安装")

        self.vnpy_adapter = VnPyAdapter()
        self.logger.info("VNPY适配器初始化完成")

    def _create_custom_portfolio(self):
        """新建自定义组合"""
        raise NotImplementedError("自定义组合功能需要实现portfolio_service集成。")

    def _delete_custom_portfolio(self):
        """删除自定义组合"""
        raise NotImplementedError("删除自定义组合功能需要实现portfolio_service集成。")

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

        if not self.vnpy_adapter:
            # VnPy适配器未初始化时不更新数据
            return

        try:
            # 从VNPY获取真实数据
            if not hasattr(self.vnpy_adapter, "get_status"):
                raise AttributeError("VnPy适配器缺少get_status方法")

            status = self.vnpy_adapter.get_status()

            # 更新自动组合表格
            self._update_auto_portfolios(status)

            # 更新自定义组合表格
            self._update_custom_portfolios(status)

            # 更新监控数据
            self._update_monitor_data()

        except Exception as e:
            self.logger.error("更新组合数据失败: %s", e)
            raise

    def _update_auto_portfolios(self, status):
        """更新自动组合"""
        # 清空表格
        if self.auto_portfolio_table:
            self.auto_portfolio_table.setRowCount(0)

        connected_gateways = status.get("connected_gateways", [])

        if not connected_gateways:
            # 没有连接的网关是正常情况
            return

        for i, gateway_name in enumerate(connected_gateways):
            if self.auto_portfolio_table:
                self.auto_portfolio_table.insertRow(i)

                # 网关名称
                self.auto_portfolio_table.setItem(i, 0, QTableWidgetItem(gateway_name))

                # 策略数量 - 功能未实现
                strategies_count = "0"

                self.auto_portfolio_table.setItem(i, 1, QTableWidgetItem(strategies_count))

                # 状态（已连接的网关都是运行中）
                status_text = "运行中"
                self.auto_portfolio_table.setItem(i, 2, QTableWidgetItem(status_text))

                # 设置状态颜色
                status_item = self.auto_portfolio_table.item(i, 2)
                if status_item:
                    status_item.setBackground(QColor("#4caf50"))

    def _update_custom_portfolios(self):
        """更新自定义组合 - 从后端服务获取真实数据"""
        # 清空表格
        if self.custom_portfolio_table:
            self.custom_portfolio_table.setRowCount(0)

        # 自定义组合功能需要实现portfolio_service
        # 目前返回空列表
        pass

    def _update_monitor_data(self):
        """更新监控数据 - 修复版，支持无网关情况"""
        # 就绪守卫
        if not getattr(self, "ui_ready", False):
            return

        # 控件守卫
        if not getattr(self, "gateway_tab", None):
            self.logger.debug("gateway_tab未初始化，跳过更新")
            return

        # 处理无网关情况：直接返回
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
                self.logger.error("positions类型错误: %s, 值: %s", type(positions), positions)
                return

            # 限制显示数量，避免表格过大
            for i, pos in enumerate(positions_list[:10]):
                # 确保pos是字典类型
                if not isinstance(pos, dict):
                    self.logger.warning("持仓项不是字典类型: %s", type(pos))
                    continue

                position_table.insertRow(i)
                position_table.setItem(i, 0, QTableWidgetItem(str(pos.get("symbol", "--"))))
                position_table.setItem(i, 1, QTableWidgetItem(str(pos.get("volume", 0))))
                position_table.setItem(i, 2, QTableWidgetItem(str(pos.get("cost", 0))))
                position_table.setItem(i, 3, QTableWidgetItem(str(pos.get("market_value", 0))))
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
                tab_data["total_pnl_label"].setText(str(account_info.get("total_pnl", "--")))
            if tab_data.get("total_return_label"):
                tab_data["total_return_label"].setText(str(account_info.get("total_return", "--")))
            if tab_data.get("max_drawdown_label"):
                tab_data["max_drawdown_label"].setText(str(account_info.get("max_drawdown", "--")))
            if tab_data.get("sharpe_ratio_label"):
                tab_data["sharpe_ratio_label"].setText(str(account_info.get("sharpe_ratio", "--")))
        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            self.logger.error("更新账户信息失败: %s", e)

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
