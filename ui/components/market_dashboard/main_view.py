# -*- coding: utf-8 -*-
"""行情看板界面 - 主视图（重构版）.

单一界面：所有功能集成在一个综合界面中。
通过MarketBoardService访问行情数据。
集成vnpy_chartwizard专业图表组件。
"""
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg

from backend.core.base import get_service_manager
from backend.core.utils import LoggerMixin

from ui.widgets.base_widget import BaseWidget
from ui.widgets.chart_wizard_widget import ChartWizardWidget
from ui.widgets.chart_toolbar_widget import ChartToolbar


class MarketDashboard(BaseWidget, LoggerMixin):
    """行情看板主界面（重构版）."""

    def __init__(self, parent=None):
        """初始化行情看板."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.market_service = None

        # 初始化UI组件
        self.symbol_combo: Optional[QComboBox] = None
        self.symbol_search: Optional[QLineEdit] = None
        self.market_data_table: Optional[QTableWidget] = None
        self.period_combo: Optional[QComboBox] = None
        self.chart_type_combo: Optional[QComboBox] = None
        self.main_chart_widget: Optional[ChartWizardWidget] = None
        self.chart_toolbar: Optional[ChartToolbar] = None
        self.indicator_selector: Optional[QComboBox] = None
        self.indicators_tab: Optional[QTabWidget] = None
        self.overlay_symbol_combo: Optional[QComboBox] = None
        self.overlay_indicator_combo: Optional[QComboBox] = None
        self.coord_type_combo: Optional[QComboBox] = None

        # 指标图表
        self.macd_plot: Optional[Any] = None
        self.rsi_plot: Optional[Any] = None

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

        self.symbol_combo = QComboBox()
        self._load_symbol_list()
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

        # 指标副图区域
        indicators_group = QGroupBox("技术指标")
        indicators_layout = QVBoxLayout(indicators_group)

        indicator_layout = QHBoxLayout()
        self.indicator_selector = QComboBox()
        self.indicator_selector.addItems(["MACD", "RSI", "KDJ", "BOLL"])
        indicator_layout.addWidget(QLabel("指标:"))
        indicator_layout.addWidget(self.indicator_selector)
        indicators_layout.addLayout(indicator_layout)

        self.indicators_tab = QTabWidget()
        self.indicators_tab.setTabPosition(QTabWidget.TabPosition.South)
        self._create_indicator_tabs()
        indicators_layout.addWidget(self.indicators_tab)

        chart_layout.addWidget(indicators_group)
        layout.addWidget(chart_group)

        return widget

    def _create_indicator_tabs(self):
        """创建技术指标选项卡."""
        # MACD指标
        macd_tab = QWidget()
        macd_layout = QVBoxLayout(macd_tab)
        macd_win = pg.GraphicsLayoutWidget()
        macd_win.setBackground(QColor(26, 26, 26))
        self.macd_plot = macd_win.addPlot(title="MACD")  # type: ignore[attr-defined]
        if self.macd_plot:
            self.macd_plot.showGrid(x=True, y=True)
        macd_layout.addWidget(macd_win)
        if self.indicators_tab:
            self.indicators_tab.addTab(macd_tab, "MACD")

        # RSI指标
        rsi_tab = QWidget()
        rsi_layout = QVBoxLayout(rsi_tab)
        rsi_win = pg.GraphicsLayoutWidget()
        rsi_win.setBackground(QColor(26, 26, 26))
        self.rsi_plot = rsi_win.addPlot(title="RSI")  # type: ignore[attr-defined]
        if self.rsi_plot:
            self.rsi_plot.showGrid(x=True, y=True)
        rsi_layout.addWidget(rsi_win)
        if self.indicators_tab:
            self.indicators_tab.addTab(rsi_tab, "RSI")

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
            # vnpy集成后通过market_service的realtime_service获取品种列表
            self._load_default_symbols()

        except Exception as e:
            self.logger.error("加载品种列表失败: %s", e)
            self._load_default_symbols()

    def _load_default_symbols(self):
        """加载默认品种列表."""
        default_symbols = [
            "000001 - 平安银行",
            "000002 - 万科A",
            "600000 - 浦发银行",
            "600036 - 招商银行",
        ]
        if self.symbol_combo:
            for symbol in default_symbols:
                self.symbol_combo.addItem(symbol)

    def _search_symbol(self):
        """搜索品种."""
        search_text = self.symbol_search.text() if self.symbol_search else ""
        self.logger.info("搜索品种: %s", search_text)

    def _on_chart_type_changed(self, _chart_type: str):  # noqa: U100
        """图表类型切换."""
        self.show_info(f"切换图表类型: {_chart_type}")

    def _on_period_changed(self, _period: str):  # noqa: U100
        """周期改变."""
        self.show_info(f"切换周期: {_period}")

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

            current_text = self.symbol_combo.currentText() if self.symbol_combo else ""
            if not current_text or " - " not in current_text:
                return

            # vnpy集成后通过market_service的realtime_service获取行情数据
            # 暂时显示占位符
            if self.market_data_table:
                self.market_data_table.setItem(0, 1, QTableWidgetItem("--"))
                self.market_data_table.setItem(1, 1, QTableWidgetItem("--"))
                self.market_data_table.setItem(2, 1, QTableWidgetItem("--"))
                self.market_data_table.setItem(3, 1, QTableWidgetItem("--"))
                self.market_data_table.setItem(4, 1, QTableWidgetItem("--"))

        except Exception as e:
            self.logger.error("更新行情数据失败: %s", e)

    # ==================== 通用方法 ====================

    def connect_signals(self):
        """连接信号槽."""
        if self.symbol_combo:
            self.symbol_combo.currentTextChanged.connect(self._on_symbol_changed)

        # 连接图表组件信号
        if self.main_chart_widget and hasattr(self.main_chart_widget, "symbol_changed"):
            self.main_chart_widget.symbol_changed.connect(self._on_chart_symbol_changed)

        # 启动数据更新定时器
        self.start_update_timer(1000, self._update_market_data)

    def _on_chart_symbol_changed(self, symbol: str):
        """图表品种改变回调.

        Args:
            symbol: 品种代码
        """
        self.logger.info(f"图表品种已切换: {symbol}")

    def _on_symbol_changed(self, text: str):
        """品种改变."""
        # 解析品种代码
        if text and " - " in text:
            symbol_code = text.split(" - ")[0].strip()

            # 更新图表品种
            if self.main_chart_widget and hasattr(self.main_chart_widget, "set_symbol"):
                self.main_chart_widget.set_symbol(symbol_code)

        # 更新行情数据
        self._update_market_data()

        # 自动检测数据断点
        self._auto_detect_data_gaps(text)

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
            gap_start = gap.get("gap_start", "")
            gap_end = gap.get("gap_end", "")
            gap_days = gap.get("gap_days", 0)
            gap_details.append(f"{i}. {gap_start} ~ {gap_end} (缺失 {gap_days} 个周期)")

        gap_text.setText("\n".join(gap_details))
        layout.addWidget(gap_text)

        # 获取增量更新建议
        suggestion_result = {"success": False}  # 默认值
        if self.market_service:
            suggestion_result = self.market_service.suggest_incremental_update(symbol, interval)
        if suggestion_result.get("success"):
            suggestion = suggestion_result.get("suggestion", {})
            update_info = "\n建议增量更新：\n"
            update_info += f"开始日期：{suggestion.get('start_date', '')}\n"
            update_info += f"结束日期：{suggestion.get('end_date', '')}\n"

            if interval in ["1min", "5min"]:
                update_info += "支持精确更新到前一根K线"

            suggestion_label = QLabel(update_info)
            suggestion_label.setStyleSheet("color: #4CAF50;")
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
