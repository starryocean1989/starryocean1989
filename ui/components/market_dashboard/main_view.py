# -*- coding: utf-8 -*-
"""
行情看板界面 - 主视图.

单一界面：所有功能集成在一个综合界面中。
"""

import logging
import random
from typing import Any, Dict, Optional

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

# Optional imports with fallbacks
try:
    import pyqtgraph as pg
except ImportError:
    pg = None

try:
    from integration.vnpy_adapter import VnPyAdapter as _VnPyAdapter  # type: ignore
except ImportError:
    _VnPyAdapter = None

try:
    from ui.widgets.chart_widget import ChartWidget
except ImportError:
    ChartWidget = None

try:
    from ..widgets.base_widget import BaseWidget  # type: ignore
except ImportError:
    try:
        from ui.widgets.base_widget import BaseWidget  # type: ignore
    except ImportError:

        class BaseWidget(QWidget):
            """Base widget class for fallback."""

            def __init__(self, parent=None, title=""):
                """Initialize base widget."""
                super().__init__(parent)
                self.title = title
                self._timer = None

            def setup_ui(self):
                """Set up UI - fallback implementation."""

            def connect_signals(self):
                """Connect signals - fallback implementation."""

            def start_update_timer(self, interval: int = 1000, callback=None):
                """Start update timer."""
                self._timer = QTimer()
                self._timer.timeout.connect(callback)
                self._timer.start(interval)

            def stop_update_timer(self):
                """Stop update timer."""
                if self._timer:
                    self._timer.stop()
                    self._timer = None

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
            """Logger mixin for fallback."""

            @property
            def logger(self):
                """Get logger instance."""
                return logging.getLogger(self.__class__.__name__)


class MockVnPyAdapter:
    """Mock VNPY adapter class."""

    def get_status(self):
        """Get mock status."""
        return {
            "vnpy_available": False,
            "gateways": [],
            "connected_gateways": False,
            "real_time_worker_running": False,
            "subscribed_symbols": [],
        }

    def subscribe_market_data(self, symbol):
        """Mock subscribe market data."""
        # symbol parameter is intentionally unused in mock implementation
        _ = symbol  # Suppress unused argument warning
        return True

    def get_market_data(self, symbol):
        """Get mock market data."""
        return {
            "symbol": symbol,
            "last_price": 100.0,
            "volume": 1000,
            "bid_price": 99.9,
            "ask_price": 100.1,
        }


class MarketDashboard(BaseWidget):  # type: ignore[misc]
    """行情看板主界面."""

    def __init__(self, parent=None):
        """Initialize market dashboard."""
        super().__init__(parent, "行情看板")

        # Initialize all UI components with proper types
        self.symbol_combo: Optional[QComboBox] = None
        self.symbol_search: Optional[QLineEdit] = None
        self.market_data_table: Optional[QTableWidget] = None
        self.period_combo: Optional[QComboBox] = None
        self.main_chart_widget: Optional[Any] = None
        self.indicator_selector: Optional[QComboBox] = None
        self.indicators_tab: Optional[QTabWidget] = None
        self.overlay_symbol_combo: Optional[QComboBox] = None
        self.overlay_indicator_combo: Optional[QComboBox] = None
        self.coord_type_combo: Optional[QComboBox] = None
        self.style_combo: Optional[QComboBox] = None
        self.apply_btn: Optional[QPushButton] = None
        self.reset_btn: Optional[QPushButton] = None
        self.vnpy_adapter: Optional[Any] = None
        self._current_subscribed_symbol: Optional[str] = None

        # Initialize plot objects for indicators
        self.macd_plot: Optional[Any] = None
        self.rsi_plot: Optional[Any] = None
        self.kdj_plot: Optional[Any] = None
        self.boll_plot: Optional[Any] = None

        self._logger = logging.getLogger(self.__class__.__name__)
        self._logger.info("行情看板界面初始化开始")

    @property
    def logger(self):
        """Get logger instance."""
        return self._logger

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QHBoxLayout(self)

        # 创建主分割器
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setSizes([300, 800, 300])  # 左侧、中心、右侧比例

        # 左侧：品种选择和控制面板
        left_widget = self._create_left_panel()
        main_splitter.addWidget(left_widget)

        # 中心：行情主图区和技术指标
        center_widget = self._create_center_panel()
        main_splitter.addWidget(center_widget)

        # 右侧：叠加功能和控制功能
        right_widget = self._create_right_panel()
        main_splitter.addWidget(right_widget)

        main_layout.addWidget(main_splitter)

    def _create_left_panel(self):
        """创建左侧面板."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 品种选择组
        symbol_group = QGroupBox("品种选择")
        symbol_layout = QVBoxLayout(symbol_group)

        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(
            [
                "000001 - 平安银行",
                "000002 - 万科A",
                "600000 - 浦发银行",
                "IF2406 - 沪深300股指期货",
                "IC2406 - 中证500股指期货",
            ]
        )
        self.symbol_combo.currentTextChanged.connect(self._on_symbol_changed)
        symbol_layout.addWidget(self.symbol_combo)

        # 快速搜索
        search_layout = QHBoxLayout()
        self.symbol_search = QLineEdit()
        self.symbol_search.setPlaceholderText("搜索品种...")
        search_layout.addWidget(self.symbol_search)

        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self._search_symbol)
        search_layout.addWidget(search_btn)

        symbol_layout.addLayout(search_layout)

        layout.addWidget(symbol_group)

        # 行情数据组
        data_group = QGroupBox("实时行情")
        data_layout = QVBoxLayout(data_group)

        self.market_data_table = QTableWidget(5, 2)
        self.market_data_table.setHorizontalHeaderLabels(["项目", "数值"])
        header = self.market_data_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.market_data_table.verticalHeader().setVisible(False)
        self.market_data_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # 设置行标题和初始值
        items = ["最新价", "涨跌幅", "成交量", "成交额", "换手率"]
        for i, item in enumerate(items):
            self.market_data_table.setItem(i, 0, QTableWidgetItem(item))
            self.market_data_table.setItem(i, 1, QTableWidgetItem("--"))

        data_layout.addWidget(self.market_data_table)

        layout.addWidget(data_group)

        layout.addStretch()

        return widget

    def _create_center_panel(self):
        """创建中心面板."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 工具栏
        toolbar_layout = QHBoxLayout()

        # 周期选择
        self.period_combo = QComboBox()
        periods = ["日K", "周K", "月K", "5分钟", "15分钟", "30分钟", "1小时"]
        self.period_combo.addItems(periods)
        self.period_combo.currentTextChanged.connect(self._on_period_changed)
        toolbar_layout.addWidget(QLabel("周期:"))
        toolbar_layout.addWidget(self.period_combo)

        toolbar_layout.addStretch()

        # 图表操作按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_chart)
        toolbar_layout.addWidget(refresh_btn)

        layout.addLayout(toolbar_layout)

        # 图表区域组
        chart_group = QGroupBox("行情图表")
        chart_layout = QVBoxLayout(chart_group)

        # 主图区域 - 专业图表组件
        if ChartWidget is not None:
            self.main_chart_widget = ChartWidget(self)
        else:
            # Fallback if chart widget not available
            self.main_chart_widget = QWidget()
        self.main_chart_widget.setMinimumHeight(300)

        # 连接图表组件信号
        if self.main_chart_widget:
            chart = self.main_chart_widget
            if hasattr(chart, "symbol_changed"):
                chart.symbol_changed.connect(self._on_chart_symbol_changed)
            if hasattr(chart, "period_changed"):
                chart.period_changed.connect(self._on_chart_period_changed)
            if hasattr(chart, "indicator_toggled"):
                chart.indicator_toggled.connect(self._on_chart_indicator_toggled)

        # 初始化VNPY适配器和实时数据
        self._initialize_vnpy_adapter()

        chart_layout.addWidget(self.main_chart_widget)

        # 指标副图区域
        indicators_group = QGroupBox("技术指标")
        indicators_layout = QVBoxLayout(indicators_group)

        # 技术指标选择器
        indicator_layout = QHBoxLayout()

        self.indicator_selector = QComboBox()
        self.indicator_selector.addItems(["MACD", "RSI", "KDJ", "BOLL"])
        self.indicator_selector.currentTextChanged.connect(self._on_indicator_selected)
        indicator_layout.addWidget(QLabel("指标:"))
        indicator_layout.addWidget(self.indicator_selector)

        # 指标显示区域
        self.indicators_tab = QTabWidget()
        self.indicators_tab.setTabPosition(QTabWidget.TabPosition.South)

        # 创建指标选项卡
        self._create_indicator_tabs()

        indicators_layout.addLayout(indicator_layout)
        indicators_layout.addWidget(self.indicators_tab)

        chart_layout.addWidget(indicators_group)

        layout.addWidget(chart_group)

        return widget

    def _create_indicator_tabs(self):
        """创建技术指标选项卡."""
        if pg is not None:

            # MACD指标
            macd_tab = QWidget()
            macd_layout = QVBoxLayout(macd_tab)

            # 创建MACD图表
            macd_win = pg.GraphicsLayoutWidget()
            macd_win.setBackground(QColor(26, 26, 26))
            # 使用正确的pyqtgraph方法
            # type: ignore[reportAttributeAccessIssue]
            self.macd_plot = macd_win.addPlot(title="MACD")  # noqa: E501
            if self.macd_plot:
                self.macd_plot.showGrid(x=True, y=True)
                self.macd_plot.setMinimumHeight(150)

            macd_layout.addWidget(macd_win)
            if self.indicators_tab:
                self.indicators_tab.addTab(macd_tab, "MACD")

            # RSI指标
            rsi_tab = QWidget()
            rsi_layout = QVBoxLayout(rsi_tab)

            # 创建RSI图表
            rsi_win = pg.GraphicsLayoutWidget()
            rsi_win.setBackground(QColor(26, 26, 26))
            # 使用正确的pyqtgraph方法
            self.rsi_plot = rsi_win.addPlot(  # type: ignore[reportAttributeAccessIssue]
                title="RSI"
            )
            if self.rsi_plot:
                self.rsi_plot.showGrid(x=True, y=True)
                self.rsi_plot.setMinimumHeight(150)

            rsi_layout.addWidget(rsi_win)
            if self.indicators_tab:
                self.indicators_tab.addTab(rsi_tab, "RSI")

            # KDJ指标
            kdj_tab = QWidget()
            kdj_layout = QVBoxLayout(kdj_tab)

            # 创建KDJ图表
            kdj_win = pg.GraphicsLayoutWidget()
            kdj_win.setBackground(QColor(26, 26, 26))
            # 使用正确的pyqtgraph方法
            self.kdj_plot = kdj_win.addPlot(  # type: ignore[reportAttributeAccessIssue]
                title="KDJ"
            )
            if self.kdj_plot:
                self.kdj_plot.showGrid(x=True, y=True)
                self.kdj_plot.setMinimumHeight(150)

            kdj_layout.addWidget(kdj_win)
            if self.indicators_tab:
                self.indicators_tab.addTab(kdj_tab, "KDJ")

            # BOLL指标
            boll_tab = QWidget()
            boll_layout = QVBoxLayout(boll_tab)

            # 创建BOLL图表
            boll_win = pg.GraphicsLayoutWidget()
            boll_win.setBackground(QColor(26, 26, 26))
            # 使用正确的pyqtgraph方法
            self.boll_plot = boll_win.addPlot(title="BOLL")  # type: ignore
            if self.boll_plot:
                self.boll_plot.showGrid(x=True, y=True)
                self.boll_plot.setMinimumHeight(150)

            boll_layout.addWidget(boll_win)
            if self.indicators_tab:
                self.indicators_tab.addTab(boll_tab, "BOLL")

        else:
            # 如果pyqtgraph不可用，显示替代内容
            for indicator in ["MACD", "RSI", "KDJ", "BOLL"]:
                tab = QWidget()
                layout = QVBoxLayout(tab)
                layout.addWidget(QLabel(f"📊 {indicator}指标图表"))
                layout.addWidget(QLabel("（需要安装pyqtgraph库）"))
                if self.indicators_tab:
                    self.indicators_tab.addTab(tab, indicator)

    def _create_right_panel(self):
        """创建右侧面板."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 叠加功能组
        overlay_group = QGroupBox("叠加功能")
        overlay_layout = QVBoxLayout(overlay_group)

        # 品种叠加
        self.overlay_symbol_combo = QComboBox()
        self.overlay_symbol_combo.addItems(
            ["无", "000001 - 平安银行", "000002 - 万科A", "600000 - 浦发银行"]
        )
        overlay_layout.addWidget(QLabel("品种叠加:"))
        overlay_layout.addWidget(self.overlay_symbol_combo)

        # 指标叠加
        self.overlay_indicator_combo = QComboBox()
        self.overlay_indicator_combo.addItems(
            ["无", "MA5", "MA10", "MA20", "MA60", "BOLL"]
        )
        overlay_layout.addWidget(QLabel("指标叠加:"))
        overlay_layout.addWidget(self.overlay_indicator_combo)

        layout.addWidget(overlay_group)

        # 控制功能组
        control_group = QGroupBox("控制功能")
        control_layout = QVBoxLayout(control_group)

        # 坐标切换
        self.coord_type_combo = QComboBox()
        self.coord_type_combo.addItems(["普通坐标", "对数坐标"])
        control_layout.addWidget(QLabel("坐标类型:"))
        control_layout.addWidget(self.coord_type_combo)

        # 样式配置
        self.style_combo = QComboBox()
        self.style_combo.addItems(["默认样式", "简洁样式", "专业样式"])
        control_layout.addWidget(QLabel("图表样式:"))
        control_layout.addWidget(self.style_combo)

        layout.addWidget(control_group)

        # 操作按钮
        button_layout = QVBoxLayout()

        self.apply_btn = QPushButton("应用设置")
        self.apply_btn.clicked.connect(self._apply_settings)
        button_layout.addWidget(self.apply_btn)

        self.reset_btn = QPushButton("重置视图")
        self.reset_btn.clicked.connect(self._reset_view)
        button_layout.addWidget(self.reset_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        return widget

    def connect_signals(self):
        """连接信号槽."""
        # 连接品种选择信号
        if self.symbol_combo:
            self.symbol_combo.currentTextChanged.connect(self._on_symbol_changed)
        if self.overlay_symbol_combo:
            self.overlay_symbol_combo.currentTextChanged.connect(
                self._on_overlay_changed
            )
        if self.overlay_indicator_combo:
            self.overlay_indicator_combo.currentTextChanged.connect(
                self._on_indicator_changed
            )

        # 连接控制信号
        if self.coord_type_combo:
            self.coord_type_combo.currentTextChanged.connect(self._on_coord_changed)
        if self.style_combo:
            self.style_combo.currentTextChanged.connect(self._on_style_changed)

        # 启动数据更新定时器
        self.start_update_timer(1000, self._update_market_data)

    def _initialize_vnpy_adapter(self):
        """初始化VNPY适配器."""
        try:
            if _VnPyAdapter is not None:
                self.vnpy_adapter = _VnPyAdapter()
                self.logger.info("VNPY适配器初始化完成")

                # 连接实时数据信号
                if hasattr(self.vnpy_adapter, "real_time_worker"):
                    worker = getattr(self.vnpy_adapter, "real_time_worker", None)
                    if worker and hasattr(worker, "tick_received"):
                        worker.tick_received.connect(self._on_real_time_tick)
            else:
                # 如果无法导入，创建一个模拟适配器
                self.vnpy_adapter = MockVnPyAdapter()
                self.logger.info("使用模拟VNPY适配器")

        except (RuntimeError, AttributeError) as e:
            self.logger.error("VNPY适配器初始化失败: %s", e)
            self.vnpy_adapter = MockVnPyAdapter()
            self.logger.info("使用模拟VNPY适配器")

    def _on_real_time_tick(self, tick_data: Dict[str, Any]):
        """实时tick数据回调."""
        try:
            # 更新行情数据表格
            last_price = tick_data.get("last_price", 0)

            # 更新最新价
            if self.market_data_table:
                table = self.market_data_table
                table.setItem(0, 1, QTableWidgetItem(str(last_price)))

                # 计算涨跌幅（模拟）
                change = random.uniform(-5, 5)
                table.setItem(1, 1, QTableWidgetItem(f"{change:.2f}%"))

                # 更新成交量
                volume = tick_data.get("volume", 0)
                table.setItem(2, 1, QTableWidgetItem(str(volume)))

            # 更新图表数据
            if hasattr(self, "main_chart_widget"):
                # 这里可以传递实时数据给图表组件进行更新
                pass

        except (AttributeError, KeyError, TypeError) as e:
            self.logger.error("处理实时tick数据失败: %s", e)

    def _on_symbol_changed(self, text: str):
        """品种选择改变."""
        self.logger.info("切换品种: %s", text)

        if text:
            symbol_code = text.split(" - ", maxsplit=1)[0]
            # 订阅新品种的实时数据
            if hasattr(self, "vnpy_adapter") and self.vnpy_adapter:
                # 取消之前品种的订阅
                current_symbol = getattr(self, "_current_subscribed_symbol", None)
                adapter = self.vnpy_adapter
                if (
                    current_symbol
                    and current_symbol != symbol_code
                    and hasattr(adapter, "unsubscribe_real_time_data")
                ):
                    adapter.unsubscribe_real_time_data(current_symbol)

                # 订阅新品种
                if hasattr(
                    adapter, "subscribe_real_time_data"
                ) and adapter.subscribe_real_time_data(symbol_code):
                    self._current_subscribed_symbol = symbol_code

        self._update_market_data()

    def _on_period_changed(self, text: str):
        """周期选择改变."""
        self.logger.info("切换周期: %s", text)
        # 这里实现周期切换逻辑

    def _on_overlay_changed(self, text: str):
        """叠加品种改变."""
        self.logger.info("叠加品种: %s", text)
        # 这里实现品种叠加逻辑

    def _on_indicator_changed(self, text: str):
        """叠加指标改变."""
        self.logger.info("叠加指标: %s", text)
        # 这里实现指标叠加逻辑

    def _on_coord_changed(self, text: str):
        """坐标类型改变."""
        self.logger.info("坐标类型: %s", text)
        # 这里实现坐标切换逻辑

    def _on_style_changed(self, text: str):
        """样式改变."""
        self.logger.info("图表样式: %s", text)
        # 这里实现样式切换逻辑

    def _on_indicator_selected(self, indicator_name: str):
        """指标选择改变."""
        self.logger.info("选择技术指标: %s", indicator_name)
        # 同步图表组件的品种和周期选择
        if hasattr(self, "main_chart_widget") and self.main_chart_widget:
            if self.symbol_combo:
                current_text = self.symbol_combo.currentText()
                if current_text and " - " in current_text:
                    symbol_code = current_text.split(" - ", maxsplit=1)[0]
                    self.main_chart_widget.set_symbol(symbol_code)
            if self.period_combo and hasattr(self.main_chart_widget, "set_period"):
                self.main_chart_widget.set_period(self.period_combo.currentText())

    def _on_chart_symbol_changed(self, symbol: str):
        """图表组件品种改变回调."""
        self.logger.info("图表组件品种改变: %s", symbol)
        # 同步主界面的品种选择
        if self.symbol_combo:
            for i in range(self.symbol_combo.count()):
                text = self.symbol_combo.itemText(i)
                if text.startswith(symbol):
                    self.symbol_combo.setCurrentIndex(i)
                    break

    def _on_chart_period_changed(self, period: str):
        """图表组件周期改变回调."""
        self.logger.info("图表组件周期改变: %s", period)
        # 同步主界面的周期选择
        if self.period_combo:
            index = self.period_combo.findText(period)
            if index >= 0:
                self.period_combo.setCurrentIndex(index)

    def _on_chart_indicator_toggled(self, indicator: str, enabled: bool):
        """图表组件指标切换回调."""
        self.logger.info("图表组件指标切换: %s = %s", indicator, enabled)
        # 更新指标选择器状态
        if self.indicator_selector:
            index = self.indicator_selector.findText(indicator)
            if index >= 0:
                # 这里可以实现指标启用/禁用的视觉反馈
                pass

    def _search_symbol(self):
        """搜索品种."""
        search_text = self.symbol_search.text() if self.symbol_search else ""
        self.logger.info("搜索品种: %s", search_text)
        # 这里实现品种搜索逻辑

    def _refresh_chart(self):
        """刷新图表."""
        self.show_info("刷新图表...")
        # 这里实现图表刷新逻辑

    def _apply_settings(self):
        """应用设置."""
        self.show_info("应用设置...")
        # 这里实现设置应用逻辑

    def _reset_view(self):
        """重置视图."""
        self.show_info("重置视图...")
        # 这里实现视图重置逻辑

    def _update_market_data(self):
        """更新行情数据."""
        try:
            # 模拟实时数据更新
            current_text = self.symbol_combo.currentText() if self.symbol_combo else ""
            # Extract symbol code if available
            if current_text and " - " in current_text:
                _ = current_text.split(" - ", maxsplit=1)[0]
            else:
                _ = "000001"

            # 更新行情数据表格
            data_items = [
                str(round(random.uniform(10, 100), 2)),
                f"{random.uniform(-5, 5):.2f}%",
                str(random.randint(10000, 1000000)),
                str(round(random.uniform(100000, 10000000), 2)),
                f"{random.uniform(0.1, 10):.2f}%",
            ]

            if self.market_data_table:
                for i, value in enumerate(data_items):
                    self.market_data_table.setItem(i, 1, QTableWidgetItem(value))

            # 更新图表数据（如果图表组件可用）
            if (
                hasattr(self, "main_chart_widget")
                and self.main_chart_widget
                and hasattr(self.main_chart_widget, "refresh_data")
            ):
                self.main_chart_widget.refresh_data()

        except (AttributeError, IndexError, TypeError) as e:
            self.logger.error("更新行情数据失败: %s", e)

    def refresh_data(self):
        """刷新数据."""
        self._update_market_data()
        self.show_info("行情数据已刷新")

    def on_close(self):
        """关闭处理."""
        # 停止实时数据订阅
        if hasattr(self, "vnpy_adapter") and self.vnpy_adapter:
            current_symbol = getattr(self, "_current_subscribed_symbol", None)
            adapter = self.vnpy_adapter
            if current_symbol and hasattr(adapter, "unsubscribe_real_time_data"):
                adapter.unsubscribe_real_time_data(current_symbol)
            if hasattr(adapter, "stop_real_time_data"):
                adapter.stop_real_time_data()

        self.stop_update_timer()
        self.logger.info("行情看板界面已关闭")
