# -*- coding: utf-8 -*-
"""行情看板界面 - 主视图（重构版）.

单一界面：所有功能集成在一个综合界面中。
通过MarketBoardService访问行情数据。
集成vnpy_chartwizard专业图表组件。
"""
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.core.base import get_service_manager
from backend.core.utils import LoggerMixin

from ui.widgets.base_widget import BaseWidget
from ui.widgets.chart_wizard_widget import ChartWizardWidget
from ui.widgets.chart_toolbar_widget import ChartToolbar
from ui.widgets.symbol_search_widget import SymbolSearchWidget
from ui.widgets.indicator_plot_widget import IndicatorPlotWidget


class MarketDashboard(BaseWidget, LoggerMixin):
    """行情看板主界面（重构版）."""

    def __init__(self, parent=None):
        """初始化行情看板."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.market_service = None

        # 初始化UI组件
        self.symbol_combo: Optional[QComboBox] = None
        self.symbol_search: Optional[SymbolSearchWidget] = None
        self.market_data_table: Optional[QTableWidget] = None
        self.period_combo: Optional[QComboBox] = None
        self.chart_type_combo: Optional[QComboBox] = None
        self.main_chart_widget: Optional[ChartWizardWidget] = None
        self.chart_toolbar: Optional[ChartToolbar] = None
        self.overlay_symbol_combo: Optional[QComboBox] = None
        self.overlay_indicator_combo: Optional[QComboBox] = None
        self.coord_type_combo: Optional[QComboBox] = None

        # 副图管理
        self.subplot_container: Optional[QSplitter] = None  # 副图容器（可调整高度）
        self.subplots: List[IndicatorPlotWidget] = []  # 副图列表
        self.add_subplot_btn: Optional[QPushButton] = None

        # 调用父类初始化
        super().__init__(parent, "行情看板")
        self.logger.info("行情看板界面初始化开始")

        # 初始化服务
        self._initialize_service()

    def _initialize_service(self):
        """获取行情看板服务."""
        try:
            # 从服务管理器获取行情看板服务
            self.market_service = self.service_manager.get_service("market_board_service")
            if self.market_service:
                self.logger.info("行情看板服务获取成功")
            else:
                self.logger.warning("行情看板服务未注册")
        except Exception as e:
            self.logger.error("获取行情看板服务失败: %s", e)
            self.show_error(f"服务获取失败: {e}")

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QHBoxLayout(self)

        # 创建主分割器
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setSizes([300, 800, 300])

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

    # ==================== 左侧面板 ====================

    def _create_left_panel(self) -> QWidget:
        """创建左侧面板."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 品种选择组
        symbol_group = QGroupBox("品种选择")
        symbol_layout = QVBoxLayout(symbol_group)

        # 使用新的搜索组件（集成了下拉和搜索功能）
        self.symbol_search = SymbolSearchWidget()
        self._load_symbol_list()
        symbol_layout.addWidget(self.symbol_search)

        layout.addWidget(symbol_group)

        # 实时行情组
        data_group = QGroupBox("实时行情")
        data_layout = QVBoxLayout(data_group)

        self.market_data_table = QTableWidget(5, 2)
        self.market_data_table.setHorizontalHeaderLabels(["项目", "数值"])
        header = self.market_data_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.market_data_table.verticalHeader().setVisible(False)

        items = ["最新价", "涨跌幅", "成交量", "成交额", "换手率"]
        for i, item in enumerate(items):
            self.market_data_table.setItem(i, 0, QTableWidgetItem(item))
            self.market_data_table.setItem(i, 1, QTableWidgetItem("--"))

        data_layout.addWidget(self.market_data_table)
        layout.addWidget(data_group)

        layout.addStretch()

        return widget

    # ==================== 中心面板 ====================

    def _create_center_panel(self) -> QWidget:
        """创建中心面板."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 基础工具栏
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("图表:"))

        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItems(["K线图", "分时图", "Tick图"])
        self.chart_type_combo.currentTextChanged.connect(self._on_chart_type_changed)
        toolbar_layout.addWidget(self.chart_type_combo)

        self.period_combo = QComboBox()
        periods = ["日K", "周K", "月K", "5分钟", "15分钟", "30分钟", "1小时"]
        self.period_combo.addItems(periods)
        self.period_combo.currentTextChanged.connect(self._on_period_changed)
        toolbar_layout.addWidget(QLabel("周期:"))
        toolbar_layout.addWidget(self.period_combo)

        toolbar_layout.addStretch()

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self._refresh_chart)
        toolbar_layout.addWidget(refresh_btn)

        layout.addLayout(toolbar_layout)

        # 图表工具栏
        self.chart_toolbar = ChartToolbar(self)
        self.chart_toolbar.tool_changed.connect(self._on_chart_tool_changed)
        layout.addWidget(self.chart_toolbar)

        # 主图区域
        chart_group = QGroupBox("行情图表")
        chart_layout = QVBoxLayout(chart_group)

        # 使用vnpy_chartwizard专业图表组件
        self.main_chart_widget = ChartWizardWidget(self)
        self.main_chart_widget.setMinimumHeight(300)
        chart_layout.addWidget(self.main_chart_widget)

        layout.addWidget(chart_group)

        # 副图区域（可动态添加/删除的指标副图）
        subplot_group = QGroupBox("技术指标副图")
        subplot_main_layout = QVBoxLayout(subplot_group)

        # 副图工具栏
        subplot_toolbar = QHBoxLayout()
        self.add_subplot_btn = QPushButton("➕ 添加副图")
        self.add_subplot_btn.clicked.connect(self._add_subplot)
        subplot_toolbar.addWidget(self.add_subplot_btn)
        subplot_toolbar.addStretch()
        subplot_main_layout.addLayout(subplot_toolbar)

        # 副图容器（使用QSplitter，可调整各副图高度）
        self.subplot_container = QSplitter(Qt.Orientation.Vertical)
        subplot_main_layout.addWidget(self.subplot_container)

        # 默认添加成交量副图（第一个副图）
        self._add_subplot("VOLUME", auto_created=True)

        layout.addWidget(subplot_group)

        return widget

    def _add_subplot(self, indicator_type: str = "MACD", auto_created: bool = False):
        """添加副图.

        Args:
            indicator_type: 指标类型
            auto_created: 是否自动创建（如默认的成交量副图）
        """
        try:
            # 创建新副图
            subplot = IndicatorPlotWidget(indicator_type=indicator_type)

            # 连接关闭信号
            subplot.close_requested.connect(lambda: self._remove_subplot(subplot))

            # 添加到容器
            if self.subplot_container:
                self.subplot_container.addWidget(subplot)

            # 添加到列表
            self.subplots.append(subplot)

            logger_msg = (
                f"自动创建副图: {indicator_type}" if auto_created else f"添加副图: {indicator_type}"
            )
            self.logger.info(logger_msg)

            if not auto_created:
                self.show_info(f"已添加 {indicator_type} 副图")

        except Exception as e:
            self.logger.error(f"添加副图失败: {e}", exc_info=True)
            self.show_error(f"添加副图失败: {e}")

    def _remove_subplot(self, subplot: IndicatorPlotWidget):
        """移除副图.

        Args:
            subplot: 要移除的副图组件
        """
        try:
            if subplot in self.subplots:
                # 从列表中移除
                self.subplots.remove(subplot)

                # 从容器中移除
                if self.subplot_container:
                    self.subplot_container.removeWidget(subplot)

                # 删除组件
                subplot.deleteLater()

                self.logger.info(f"移除副图: {subplot.indicator_type}")
                self.show_info(f"已移除 {subplot.indicator_type} 副图")

        except Exception as e:
            self.logger.error(f"移除副图失败: {e}", exc_info=True)
            self.show_error(f"移除副图失败: {e}")

    # ==================== 右侧面板 ====================

    def _create_right_panel(self) -> QWidget:
        """创建右侧面板."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 叠加功能组
        overlay_group = QGroupBox("叠加功能")
        overlay_layout = QVBoxLayout(overlay_group)

        self.overlay_symbol_combo = QComboBox()
        self.overlay_symbol_combo.addItem("无")
        overlay_layout.addWidget(QLabel("品种叠加:"))
        overlay_layout.addWidget(self.overlay_symbol_combo)

        self.overlay_indicator_combo = QComboBox()
        self.overlay_indicator_combo.addItem("无")
        self.overlay_indicator_combo.addItems(["MA5", "MA10", "MA20", "BOLL"])
        overlay_layout.addWidget(QLabel("指标叠加:"))
        overlay_layout.addWidget(self.overlay_indicator_combo)

        layout.addWidget(overlay_group)

        # 控制功能组
        control_group = QGroupBox("控制功能")
        control_layout = QVBoxLayout(control_group)

        self.coord_type_combo = QComboBox()
        self.coord_type_combo.addItems(["普通坐标", "对数坐标"])
        control_layout.addWidget(QLabel("坐标类型:"))
        control_layout.addWidget(self.coord_type_combo)

        layout.addWidget(control_group)

        layout.addStretch()

        return widget

    # ==================== 事件处理 ====================

    def _load_symbol_list(self):
        """加载品种列表."""
        try:
            # 从DataCenterService获取品种列表
            data_center_service = self.service_manager.get_service("data_center_service")
            if data_center_service:
                self.logger.info("正在从DataCenterService加载品种列表...")
                # 🔧 修复：使用正确的方法名 refresh_symbol_list
                result = data_center_service.refresh_symbol_list()

                if result.get("success"):
                    # 🔧 修复：DataCenterService返回的是"data"字段，不是"symbols"字段
                    symbols = result.get("data", [])
                    if symbols:
                        self._populate_symbol_combo(symbols)
                        self.logger.info("✅ 成功加载 %s 个品种", len(symbols))
                        return
                    else:
                        self.logger.warning("品种列表为空，使用默认品种")
                else:
                    self.logger.warning("获取品种列表失败: %s", result.get("message", "未知错误"))
            else:
                self.logger.warning("DataCenterService不可用")

            # 如果失败，使用默认品种
            self._load_default_symbols()

        except Exception as e:
            self.logger.error("加载品种列表失败: %s", e)
            self._load_default_symbols()

    def _populate_symbol_combo(self, symbols):
        """填充品种搜索框.

        Args:
            symbols: 品种列表
        """
        if not self.symbol_search:
            return

        # 使用新的搜索组件设置品种列表
        self.symbol_search.set_symbols(symbols)

    def _load_default_symbols(self):
        """加载默认品种列表."""
        default_symbols = [
            "000001 - 平安银行",
            "000002 - 万科A",
            "600000 - 浦发银行",
            "600036 - 招商银行",
        ]
        if self.symbol_search:
            self.symbol_search.set_symbols(default_symbols)

    def _on_chart_type_changed(self, _chart_type: str):  # noqa: U100
        """图表类型切换."""
        self.show_info(f"切换图表类型: {_chart_type}")

    def _get_current_interval(self) -> str:
        """获取当前选择的周期.

        Returns:
            周期字符串 (1d, 5m, 1m等)
        """
        if not self.period_combo:
            return "1d"

        period_text = self.period_combo.currentText()
        interval_map = {
            "日K": "1d",
            "周K": "1w",
            "月K": "1m",
            "5分钟": "5m",
            "15分钟": "15m",
            "30分钟": "30m",
            "1小时": "1h",
        }
        return interval_map.get(period_text, "1d")

    def _load_historical_data(self, symbol: str):
        """加载历史K线数据.

        Args:
            symbol: 品种代码
        """
        if not self.market_service:
            self.logger.warning("MarketBoardService不可用")
            return

        try:
            from datetime import datetime, timedelta

            # 获取当前周期
            interval = self._get_current_interval()

            # 计算查询时间范围（最近1年）
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

            self.logger.info(
                "正在加载历史数据: symbol=%s, interval=%s, %s~%s",
                symbol,
                interval,
                start_date,
                end_date,
            )

            # 查询历史数据
            result = self.market_service.query_historical_data(
                symbol=symbol, start_date=start_date, end_date=end_date, interval=interval
            )

            if result.get("success"):
                data = result.get("data", [])
                if data:
                    self.logger.info("✅ 成功加载 %s 条K线数据", len(data))
                    # 更新图表
                    self._update_chart_with_data(symbol, data, interval)
                    # 计算并显示技术指标
                    self._calculate_and_show_indicators(data)
                else:
                    self.logger.warning("⚠️ 无历史数据: %s", symbol)
                    self.show_warning(f"品种 {symbol} 无历史数据")
            else:
                error_msg = result.get("message", "未知错误")
                self.logger.error("❌ 加载历史数据失败: %s", error_msg)
                self.show_error(f"加载历史数据失败: {error_msg}")

        except Exception as e:
            self.logger.error("加载历史数据异常: %s", e, exc_info=True)
            self.show_error(f"加载历史数据异常: {e}")

    def _update_chart_with_data(self, symbol: str, data: list, interval: str):  # noqa: U100
        """更新图表数据.

        Args:
            symbol: 品种代码
            data: K线数据列表（未使用，图表组件内部自动查询）
            interval: 数据周期（未使用，图表组件内部自动查询）
        """
        if not self.main_chart_widget:
            self.logger.warning("图表组件不可用")
            return

        try:
            # 直接使用ChartWizardWidget的set_symbol方法
            # 它内部会自动查询数据并更新图表
            if hasattr(self.main_chart_widget, "set_symbol"):
                self.main_chart_widget.set_symbol(symbol)
                self.logger.info("✅ 图表数据已更新")
            else:
                self.logger.warning("图表组件不支持set_symbol方法")

        except Exception as e:
            self.logger.error("更新图表失败: %s", e, exc_info=True)
            self.show_error(f"更新图表失败: {e}")

    def _calculate_and_show_indicators(self, kline_data: list):
        """计算并显示技术指标.

        Args:
            kline_data: K线数据列表
        """
        if not self.market_service or not kline_data:
            return

        try:
            # 提取收盘价和成交量
            close_prices = [bar.get("close", 0) for bar in kline_data if bar.get("close")]
            volumes = [bar.get("volume", 0) for bar in kline_data if bar.get("volume")]

            if len(close_prices) < 30:
                self.logger.warning("数据量不足，无法计算技术指标")
                return

            # 更新所有副图的指标数据
            for subplot in self.subplots:
                indicator_type = subplot.indicator_type

                if indicator_type == "VOLUME":
                    # 成交量副图
                    subplot.update_data({"volume": volumes})

                elif indicator_type == "MACD":
                    # 计算MACD
                    result = self.market_service.calculate_indicator(
                        data=close_prices, indicator_name="MACD", params={}
                    )
                    if result.get("success"):
                        subplot.update_data(result.get("data", {}))

                elif indicator_type == "RSI":
                    # 计算RSI
                    result = self.market_service.calculate_indicator(
                        data=close_prices, indicator_name="RSI", params={"period": 14}
                    )
                    if result.get("success"):
                        subplot.update_data({"rsi": result.get("data", [])})

                elif indicator_type == "BOLL":
                    # 计算BOLL
                    result = self.market_service.calculate_indicator(
                        data=close_prices, indicator_name="BBANDS", params={"period": 20}
                    )
                    if result.get("success"):
                        subplot.update_data(result.get("data", {}))

                # 其他指标类型可以在这里扩展

            self.logger.info("✅ 技术指标已更新")

        except Exception as e:
            self.logger.error("计算技术指标失败: %s", e, exc_info=True)

    def _on_period_changed(self, _period: str):  # noqa: U100
        """周期改变."""
        self.show_info(f"切换周期: {_period}")

        # 更新ChartWizardWidget的周期
        if self.main_chart_widget and hasattr(self.main_chart_widget, "set_period"):
            interval = self._get_current_interval()
            self.main_chart_widget.set_period(interval)

        # 重新加载当前品种的数据
        if self.symbol_search:
            current_text = self.symbol_search.currentText()
            if current_text and " - " in current_text:
                symbol_code = current_text.split(" - ")[0].strip()
                self._load_historical_data(symbol_code)

    def _on_chart_tool_changed(self, _tool: str):  # noqa: U100
        """图表工具改变."""
        self.show_info(f"切换工具: {_tool}")

    def _refresh_chart(self):
        """刷新图表."""
        self.show_info("刷新图表")

    def _update_market_data(self):
        """更新行情数据."""
        try:
            if not self.market_service:
                return

            current_text = self.symbol_search.currentText() if self.symbol_search else ""
            if not current_text or " - " not in current_text:
                return

            # 解析品种代码
            symbol_code = current_text.split(" - ")[0].strip()

            # 获取实时数据
            realtime_data = self.market_service.get_realtime_data(symbol_code)

            if realtime_data and self.market_data_table:
                # 更新表格数据
                last_price = realtime_data.get("last_price", 0)
                volume = realtime_data.get("volume", 0)

                # 最新价
                self.market_data_table.setItem(0, 1, QTableWidgetItem(f"{last_price:.2f}"))

                # 涨跌幅（需要昨收价计算，暂时显示占位符）
                self.market_data_table.setItem(1, 1, QTableWidgetItem("--"))

                # 成交量
                self.market_data_table.setItem(2, 1, QTableWidgetItem(f"{volume:,.0f}"))

                # 成交额（暂时显示占位符）
                self.market_data_table.setItem(3, 1, QTableWidgetItem("--"))

                # 换手率（暂时显示占位符）
                self.market_data_table.setItem(4, 1, QTableWidgetItem("--"))
            elif self.market_data_table:
                # 无实时数据，显示占位符
                for i in range(5):
                    self.market_data_table.setItem(i, 1, QTableWidgetItem("--"))

        except Exception as e:
            self.logger.error("更新行情数据失败: %s", e)

    # ==================== 通用方法 ====================

    def connect_signals(self):
        """连接信号槽."""
        # 连接品种搜索组件信号
        if self.symbol_search:
            self.symbol_search.currentTextChanged.connect(self._on_symbol_changed)
            # 也可以连接symbol_selected信号以获取品种代码
            self.symbol_search.symbol_selected.connect(self._on_symbol_code_selected)

        # 连接图表组件信号
        if self.main_chart_widget and hasattr(self.main_chart_widget, "symbol_changed"):
            self.main_chart_widget.symbol_changed.connect(self._on_chart_symbol_changed)

        # 连接坐标类型切换信号
        if self.coord_type_combo:
            self.coord_type_combo.currentTextChanged.connect(self._on_coord_type_changed)

        # 启动数据更新定时器
        self.start_update_timer(1000, self._update_market_data)

    def _on_chart_symbol_changed(self, symbol: str):
        """图表品种改变回调.

        Args:
            symbol: 品种代码
        """
        self.logger.info(f"图表品种已切换: {symbol}")

    def _on_symbol_code_selected(self, code: str):
        """品种代码选择回调（由SymbolSearchWidget触发）.

        Args:
            code: 品种代码
        """
        self.logger.info(f"品种代码已选择: {code}")
        # 这里可以添加额外的处理逻辑，如果需要的话

    def _on_coord_type_changed(self, coord_type: str):
        """坐标类型改变回调.

        Args:
            coord_type: 坐标类型（"普通坐标" 或 "对数坐标"）
        """
        try:
            is_log = coord_type == "对数坐标"
            self.logger.info(f"坐标类型切换为: {coord_type}")

            if self.main_chart_widget and hasattr(self.main_chart_widget, "set_coordinate_type"):
                self.main_chart_widget.set_coordinate_type("log" if is_log else "linear")
                self.show_info(f"已切换为{coord_type}")
            else:
                self.logger.warning("图表组件不支持坐标类型切换")
                self.show_warning("当前图表组件不支持坐标类型切换")

        except Exception as e:
            self.logger.error(f"切换坐标类型失败: {e}", exc_info=True)
            self.show_error(f"切换坐标类型失败: {e}")

    def _on_symbol_changed(self, text: str):
        """品种改变."""
        # 解析品种代码
        if text and " - " in text:
            symbol_code = text.split(" - ")[0].strip()

            # 订阅实时行情
            self._subscribe_realtime_data(symbol_code)

            # 加载历史K线数据
            self._load_historical_data(symbol_code)

            # 更新图表品种
            if self.main_chart_widget and hasattr(self.main_chart_widget, "set_symbol"):
                self.main_chart_widget.set_symbol(symbol_code)

        # 更新行情数据
        self._update_market_data()

        # 自动检测数据断点
        self._auto_detect_data_gaps(text)

    def _subscribe_realtime_data(self, symbol: str):
        """订阅实时行情数据.

        Args:
            symbol: 品种代码
        """
        if not self.market_service:
            self.logger.warning("MarketBoardService不可用，无法订阅实时行情")
            return

        try:
            self.logger.info("订阅实时行情: %s", symbol)
            result = self.market_service.subscribe_realtime_data(symbol)

            if result.get("success"):
                self.logger.info("✅ 成功订阅实时行情: %s", symbol)

                # 启动数据录制（如果还未启动）
                if not self.market_service.recording_enabled:
                    self._start_data_recording()
            else:
                self.logger.warning("⚠️ 订阅实时行情失败: %s", result.get("message", "未知错误"))

        except Exception as e:
            self.logger.error("订阅实时行情异常: %s", e, exc_info=True)

    def _start_data_recording(self):
        """启动数据录制."""
        if not self.market_service:
            return

        try:
            self.logger.info("启动数据录制...")
            result = self.market_service.start_recording()

            if result.get("success"):
                self.logger.info("✅ 数据录制已启动")
            else:
                self.logger.warning("⚠️ 数据录制启动失败: %s", result.get("message", "未知错误"))

        except Exception as e:
            self.logger.error("启动数据录制异常: %s", e, exc_info=True)

    def _auto_detect_data_gaps(self, symbol_text: str):
        """自动检测数据断点并提示用户.

        Args:
            symbol_text: 品种文本（格式："代码 - 名称"）
        """
        if not self.market_service or not symbol_text or " - " not in symbol_text:
            return

        try:
            # 解析品种代码
            symbol_code = symbol_text.split(" - ")[0].strip()

            # 获取当前选择的周期
            interval = "1d"  # 默认日线
            if self.period_combo:
                period_text = self.period_combo.currentText()
                interval_map = {
                    "1分钟": "1min",
                    "5分钟": "5min",
                    "15分钟": "15min",
                    "30分钟": "30min",
                    "60分钟": "60min",
                    "日线": "1d",
                    "周线": "1w",
                    "月线": "1m",
                }
                interval = interval_map.get(period_text, "1d")

            # 调用backend的断点检测
            from datetime import datetime, timedelta

            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

            result = self.market_service.detect_data_gaps(
                symbol=symbol_code, start_date=start_date, end_date=end_date, interval=interval
            )

            if not result.get("success"):
                return

            has_gaps = result.get("has_gaps", False)
            gaps = result.get("gaps", [])

            # 如果检测到断点，弹出提示
            if has_gaps and gaps:
                self._show_gap_warning_dialog(symbol_code, interval, gaps)

        except Exception as e:
            self.logger.error("自动检测数据断点失败: %s", e)

    def _show_gap_warning_dialog(self, symbol: str, interval: str, gaps: list):
        """显示数据断点警告对话框.

        Args:
            symbol: 品种代码
            interval: 数据周期
            gaps: 断点列表
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("数据断点检测")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(400)

        layout = QVBoxLayout(dialog)

        # 提示信息
        info_label = QLabel(f"检测到品种 {symbol}（{interval}）的数据存在断点：")
        info_label.setStyleSheet("font-weight: bold; color: #FF9800;")
        layout.addWidget(info_label)

        # 断点详情
        gap_text = QTextEdit()
        gap_text.setReadOnly(True)

        gap_details = []
        for i, gap in enumerate(gaps[:10], 1):  # 最多显示10个断点
            gap_start = gap.get("start", "")
            gap_end = gap.get("end", "")
            # 根据interval类型选择正确的缺失数量字段
            if interval in ["1m", "5m", "15m", "30m", "1h"]:
                missing_count = gap.get("missing_bars", 0)
                unit = "根K线"
            else:
                missing_count = gap.get("missing_days", 0)
                unit = "天"
            gap_details.append(f"{i}. {gap_start} ~ {gap_end} (缺失约 {missing_count} {unit})")

        gap_text.setText("\n".join(gap_details))
        layout.addWidget(gap_text)

        # 获取增量更新建议
        suggestion_result = {"success": False}  # 默认值
        if self.market_service:
            suggestion_result = self.market_service.suggest_incremental_update(symbol, interval)
        if suggestion_result.get("success") and suggestion_result.get("needs_update"):
            last_date = suggestion_result.get("last_date", "")
            days_behind = suggestion_result.get("days_behind", 0)
            suggested_start = suggestion_result.get("suggested_start_date", "")

            update_info = "\n💡 增量更新建议：\n"
            update_info += f"本地最后数据日期：{last_date}\n"
            update_info += f"数据落后：{days_behind} 天\n"
            update_info += f"建议从 {suggested_start} 开始更新\n"

            if interval in ["1m", "5m"]:
                update_info += "\n✨ 支持精确更新到前一根K线"

            suggestion_label = QLabel(update_info)
            suggestion_label.setStyleSheet("color: #4CAF50; padding: 10px;")
            layout.addWidget(suggestion_label)

        # 按钮
        button_layout = QHBoxLayout()

        update_btn = QPushButton("立即更新")
        update_btn.clicked.connect(lambda: self._start_incremental_update(symbol, interval, dialog))
        button_layout.addWidget(update_btn)

        ignore_btn = QPushButton("忽略")
        ignore_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(ignore_btn)

        layout.addLayout(button_layout)

        dialog.exec()

    def _start_incremental_update(self, symbol: str, interval: str, dialog: QDialog):
        """开始增量更新.

        Args:
            symbol: 品种代码
            interval: 数据周期
            dialog: 对话框（用于关闭）
        """
        try:
            # 调用数据中心服务进行增量下载
            data_center_service = self.service_manager.get_service("data_center_service")

            if data_center_service:
                # 先获取建议的更新范围（从market_service）
                if self.market_service:
                    suggestion_result = self.market_service.suggest_incremental_update_range(
                        symbol=symbol, interval=interval
                    )

                    if suggestion_result.get("success"):
                        # 提取建议的开始日期
                        update_start_time = suggestion_result.get("update_start_time", "")
                        # 如果是ISO格式（包含时间），只取日期部分
                        start_date = (
                            update_start_time.split("T")[0]
                            if "T" in update_start_time
                            else update_start_time
                        )

                        # 如果没有获取到有效日期，使用默认值（最近30天）
                        if not start_date:
                            from datetime import datetime, timedelta

                            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                    else:
                        # 如果获取建议失败，使用默认值
                        from datetime import datetime, timedelta

                        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                else:
                    # market_service不可用，使用默认值
                    from datetime import datetime, timedelta

                    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

                # 使用正确的API签名调用增量下载
                result = data_center_service.start_incremental_download(start_date=start_date)

                if result.get("success"):
                    self.show_info(
                        f"已启动增量更新：{symbol} ({interval})\n从 {start_date} 开始更新"
                    )
                    dialog.accept()
                else:
                    self.show_error(f"启动增量更新失败：{result.get('message', '未知错误')}")
            else:
                self.show_warning("数据中心服务不可用")

        except Exception as e:
            self.logger.error("启动增量更新失败: %s", e)
            self.show_error(f"启动增量更新失败: {e}")

    def refresh_data(self):
        """刷新数据."""
        self._update_market_data()
        self.show_info("行情数据已刷新")

    def on_close(self):
        """关闭处理."""
        self.stop_update_timer()
        self.logger.info("行情看板界面已关闭")
