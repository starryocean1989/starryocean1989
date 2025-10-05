# -*- coding: utf-8 -*-
"""
行情看板界面 - 主视图
单一界面：所有功能集成在一个综合界面中
"""

from typing import Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QGroupBox, QComboBox,
    QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QTextEdit, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor

from ui.widgets.base_widget import BaseWidget
from utils.logging_utils import LoggerMixin


class MarketDashboard(BaseWidget, LoggerMixin):
    """行情看板主界面"""

    def __init__(self, parent=None):
        super().__init__(parent, "行情看板")
        self.logger.info("行情看板界面初始化开始")

    def setup_ui(self):
        """设置用户界面"""
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
        """创建左侧面板"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 品种选择组
        symbol_group = QGroupBox("品种选择")
        symbol_layout = QVBoxLayout(symbol_group)

        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems([
            "000001 - 平安银行", "000002 - 万科A", "600000 - 浦发银行",
            "IF2406 - 沪深300股指期货", "IC2406 - 中证500股指期货"
        ])
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
        self.market_data_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
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
        """创建中心面板"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 工具栏
        toolbar_layout = QHBoxLayout()

        # 周期选择
        self.period_combo = QComboBox()
        self.period_combo.addItems(["日K", "周K", "月K", "5分钟", "15分钟", "30分钟", "1小时"])
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
        from ui.widgets.chart_widget import ChartWidget
        self.main_chart_widget = ChartWidget(self)
        self.main_chart_widget.setMinimumHeight(300)

        # 连接图表组件信号
        self.main_chart_widget.symbol_changed.connect(self._on_chart_symbol_changed)
        self.main_chart_widget.period_changed.connect(self._on_chart_period_changed)
        self.main_chart_widget.indicator_toggled.connect(self._on_chart_indicator_toggled)

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
        """创建技术指标选项卡"""
        try:
            from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
            import pyqtgraph as pg

            # MACD指标
            macd_tab = QWidget()
            macd_layout = QVBoxLayout(macd_tab)

            # 创建MACD图表
            macd_win = pg.GraphicsLayoutWidget()
            macd_win.setBackground(QColor(26, 26, 26))
            self.macd_plot = macd_win.addPlot(title="MACD")
            self.macd_plot.showGrid(x=True, y=True)
            self.macd_plot.setMinimumHeight(150)

            macd_layout.addWidget(macd_win)
            self.indicators_tab.addTab(macd_tab, "MACD")

            # RSI指标
            rsi_tab = QWidget()
            rsi_layout = QVBoxLayout(rsi_tab)

            # 创建RSI图表
            rsi_win = pg.GraphicsLayoutWidget()
            rsi_win.setBackground(QColor(26, 26, 26))
            self.rsi_plot = rsi_win.addPlot(title="RSI")
            self.rsi_plot.showGrid(x=True, y=True)
            self.rsi_plot.setMinimumHeight(150)

            rsi_layout.addWidget(rsi_win)
            self.indicators_tab.addTab(rsi_tab, "RSI")

            # KDJ指标
            kdj_tab = QWidget()
            kdj_layout = QVBoxLayout(kdj_tab)

            # 创建KDJ图表
            kdj_win = pg.GraphicsLayoutWidget()
            kdj_win.setBackground(QColor(26, 26, 26))
            self.kdj_plot = kdj_win.addPlot(title="KDJ")
            self.kdj_plot.showGrid(x=True, y=True)
            self.kdj_plot.setMinimumHeight(150)

            kdj_layout.addWidget(kdj_win)
            self.indicators_tab.addTab(kdj_tab, "KDJ")

            # BOLL指标
            boll_tab = QWidget()
            boll_layout = QVBoxLayout(boll_tab)

            # 创建BOLL图表
            boll_win = pg.GraphicsLayoutWidget()
            boll_win.setBackground(QColor(26, 26, 26))
            self.boll_plot = boll_win.addPlot(title="BOLL")
            self.boll_plot.showGrid(x=True, y=True)
            self.boll_plot.setMinimumHeight(150)

            boll_layout.addWidget(boll_win)
            self.indicators_tab.addTab(boll_tab, "BOLL")

        except ImportError:
            # 如果pyqtgraph不可用，显示替代内容
            for indicator in ["MACD", "RSI", "KDJ", "BOLL"]:
                tab = QWidget()
                layout = QVBoxLayout(tab)
                layout.addWidget(QLabel(f"📊 {indicator}指标图表"))
                layout.addWidget(QLabel("（需要安装pyqtgraph库）"))
                self.indicators_tab.addTab(tab, indicator)

    def _create_right_panel(self):
        """创建右侧面板"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 叠加功能组
        overlay_group = QGroupBox("叠加功能")
        overlay_layout = QVBoxLayout(overlay_group)

        # 品种叠加
        self.overlay_symbol_combo = QComboBox()
        self.overlay_symbol_combo.addItems([
            "无", "000001 - 平安银行", "000002 - 万科A", "600000 - 浦发银行"
        ])
        overlay_layout.addWidget(QLabel("品种叠加:"))
        overlay_layout.addWidget(self.overlay_symbol_combo)

        # 指标叠加
        self.overlay_indicator_combo = QComboBox()
        self.overlay_indicator_combo.addItems([
            "无", "MA5", "MA10", "MA20", "MA60", "BOLL"
        ])
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
        """连接信号槽"""
        # 连接品种选择信号
        self.symbol_combo.currentTextChanged.connect(self._on_symbol_changed)
        self.overlay_symbol_combo.currentTextChanged.connect(self._on_overlay_changed)
        self.overlay_indicator_combo.currentTextChanged.connect(self._on_indicator_changed)

        # 连接控制信号
        self.coord_type_combo.currentTextChanged.connect(self._on_coord_changed)
        self.style_combo.currentTextChanged.connect(self._on_style_changed)

        # 启动数据更新定时器
        self.start_update_timer(1000, self._update_market_data)

    def _initialize_vnpy_adapter(self):
        """初始化VNPY适配器"""
        try:
            from integration.vnpy_adapter import VnPyAdapter

            self.vnpy_adapter = VnPyAdapter()
            self._logger.info("VNPY适配器初始化完成")

            # 连接实时数据信号
            if self.vnpy_adapter.real_time_worker and hasattr(self.vnpy_adapter.real_time_worker, 'tick_received'):
                self.vnpy_adapter.real_time_worker.tick_received.connect(self._on_real_time_tick)

        except Exception as e:
            self._logger.error(f"VNPY适配器初始化失败: {e}")
            self.show_error(f"VNPY适配器初始化失败: {str(e)}")

    def _on_real_time_tick(self, tick_data: Dict[str, Any]):
        """实时tick数据回调"""
        try:
            # 更新行情数据表格
            symbol = tick_data.get('symbol', '')
            last_price = tick_data.get('last_price', 0)

            # 更新最新价
            self.market_data_table.setItem(0, 1, QTableWidgetItem(str(last_price)))

            # 计算涨跌幅（模拟）
            import random
            change = random.uniform(-5, 5)
            self.market_data_table.setItem(1, 1, QTableWidgetItem(f"{change:.2f}%"))

            # 更新成交量
            volume = tick_data.get('volume', 0)
            self.market_data_table.setItem(2, 1, QTableWidgetItem(str(volume)))

            # 更新图表数据
            if hasattr(self, 'main_chart_widget'):
                # 这里可以传递实时数据给图表组件进行更新
                pass

        except Exception as e:
            self.logger.error(f"处理实时tick数据失败: {e}")

    def _on_symbol_changed(self, text: str):
        """品种选择改变"""
        self.logger.info(f"切换品种: {text}")

        if text:
            symbol_code = text.split(" - ")[0]
            # 订阅新品种的实时数据
            if hasattr(self, 'vnpy_adapter') and self.vnpy_adapter:
                # 取消之前品种的订阅
                current_symbol = getattr(self, '_current_subscribed_symbol', None)
                if current_symbol and current_symbol != symbol_code and hasattr(self.vnpy_adapter, 'unsubscribe_real_time_data'):
                    self.vnpy_adapter.unsubscribe_real_time_data(current_symbol)

                # 订阅新品种
                if hasattr(self.vnpy_adapter, 'subscribe_real_time_data') and self.vnpy_adapter.subscribe_real_time_data(symbol_code):
                    self._current_subscribed_symbol = symbol_code

        self._update_market_data()

    def _on_period_changed(self, text: str):
        """周期选择改变"""
        self._logger.info(f"切换周期: {text}")
        # 这里实现周期切换逻辑

    def _on_overlay_changed(self, text: str):
        """叠加品种改变"""
        self._logger.info(f"叠加品种: {text}")
        # 这里实现品种叠加逻辑

    def _on_indicator_changed(self, text: str):
        """叠加指标改变"""
        self._logger.info(f"叠加指标: {text}")
        # 这里实现指标叠加逻辑

    def _on_coord_changed(self, text: str):
        """坐标类型改变"""
        self._logger.info(f"坐标类型: {text}")
        # 这里实现坐标切换逻辑

    def _on_style_changed(self, text: str):
        """样式改变"""
        self._logger.info(f"图表样式: {text}")
        # 这里实现样式切换逻辑

    def _on_indicator_selected(self, indicator_name: str):
        """指标选择改变"""
        self._logger.info(f"选择技术指标: {indicator_name}")
        # 同步图表组件的品种和周期选择
        if hasattr(self, 'main_chart_widget'):
            current_text = self.symbol_combo.currentText()
            if current_text and " - " in current_text:
                symbol_code = current_text.split(" - ")[0]
                self.main_chart_widget.set_symbol(symbol_code)
            self.main_chart_widget.set_period(self.period_combo.currentText())

    def _on_chart_symbol_changed(self, symbol: str):
        """图表组件品种改变回调"""
        self.logger.info(f"图表组件品种改变: {symbol}")
        # 同步主界面的品种选择
        for i in range(self.symbol_combo.count()):
            text = self.symbol_combo.itemText(i)
            if text.startswith(symbol):
                self.symbol_combo.setCurrentIndex(i)
                break

    def _on_chart_period_changed(self, period: str):
        """图表组件周期改变回调"""
        self.logger.info(f"图表组件周期改变: {period}")
        # 同步主界面的周期选择
        index = self.period_combo.findText(period)
        if index >= 0:
            self.period_combo.setCurrentIndex(index)

    def _on_chart_indicator_toggled(self, indicator: str, enabled: bool):
        """图表组件指标切换回调"""
        self.logger.info(f"图表组件指标切换: {indicator} = {enabled}")
        # 更新指标选择器状态
        index = self.indicator_selector.findText(indicator)
        if index >= 0:
            # 这里可以实现指标启用/禁用的视觉反馈
            pass

    def _search_symbol(self):
        """搜索品种"""
        search_text = self.symbol_search.text()
        self.logger.info(f"搜索品种: {search_text}")
        # 这里实现品种搜索逻辑

    def _refresh_chart(self):
        """刷新图表"""
        self.show_info("刷新图表...")
        # 这里实现图表刷新逻辑

    def _apply_settings(self):
        """应用设置"""
        self.show_info("应用设置...")
        # 这里实现设置应用逻辑

    def _reset_view(self):
        """重置视图"""
        self.show_info("重置视图...")
        # 这里实现视图重置逻辑

    def _update_market_data(self):
        """更新行情数据"""
        try:
            # 模拟实时数据更新
            import random

            current_text = self.symbol_combo.currentText()
            symbol = current_text.split(" - ")[0] if current_text and " - " in current_text else "000001"

            # 更新行情数据表格
            data_items = [
                str(round(random.uniform(10, 100), 2)),
                f"{random.uniform(-5, 5):.2f}%",
                str(random.randint(10000, 1000000)),
                str(round(random.uniform(100000, 10000000), 2)),
                f"{random.uniform(0.1, 10):.2f}%"
            ]

            for i, value in enumerate(data_items):
                self.market_data_table.setItem(i, 1, QTableWidgetItem(value))

            # 更新图表数据（如果图表组件可用）
            if hasattr(self, 'main_chart_widget'):
                self.main_chart_widget.refresh_data()

        except Exception as e:
            self.logger.error(f"更新行情数据失败: {e}")

    def refresh_data(self):
        """刷新数据"""
        self._update_market_data()
        self.show_info("行情数据已刷新")

    def on_close(self):
        """关闭处理"""
        # 停止实时数据订阅
        if hasattr(self, 'vnpy_adapter') and self.vnpy_adapter:
            current_symbol = getattr(self, '_current_subscribed_symbol', None)
            if current_symbol and hasattr(self.vnpy_adapter, 'unsubscribe_real_time_data'):
                self.vnpy_adapter.unsubscribe_real_time_data(current_symbol)
            if hasattr(self.vnpy_adapter, 'stop_real_time_data'):
                self.vnpy_adapter.stop_real_time_data()

        self.stop_update_timer()
        self.logger.info("行情看板界面已关闭")
