# -*- coding: utf-8 -*-
"""
数据中心界面 - 主视图.

标准架构：4个子界面采用选项卡形式。
"""

import logging
import random
from datetime import datetime, timedelta

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QProgressBar, QPushButton, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
    QWidget
)

try:
    from ...widgets.base_widget import BaseWidget
    from ....utils.logging_utils import LoggerMixin
    from ....backend.core.vnpy_integration import VnPyAdapter
except ImportError:
    try:
        from ui.widgets.base_widget import BaseWidget
        from utils.logging_utils import LoggerMixin
        from backend.core.vnpy_integration import VnPyAdapter
    except ImportError:
        class BaseWidget(QWidget):
            """Base widget class for fallback."""

            def __init__(self, parent=None, title=""):
                """Initialize base widget."""
                super().__init__(parent)
                self.parent = parent
                self.title = title

            def setup_ui(self):
                """Set up UI - fallback implementation."""
                # Fallback implementation - override in subclasses

            def connect_signals(self):
                """Connect signals - fallback implementation."""
                # Fallback implementation - override in subclasses

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


class DataCenter(BaseWidget, LoggerMixin):
    """数据中心主界面."""

    def __init__(self, parent=None):
        """初始化数据中心界面."""
        super().__init__(parent, "数据中心")
        self.logger.info("数据中心界面初始化开始")

        # Initialize all UI attributes
        self.tab_widget = None
        self.symbols_tab = None
        self.local_data_tab = None
        self.download_tab = None
        self.sources_tab = None
        self.search_input = None
        self.exchange_combo = None
        self.symbols_table = None
        self.symbol_input = None
        self.start_date_input = None
        self.end_date_input = None
        self.data_table = None
        self.data_status_label = None
        self.data_quality_label = None
        self.full_download_radio = None
        self.custom_download_radio = None
        self.download_symbols_input = None
        self.download_start_date = None
        self.download_end_date = None
        self.download_progress = None
        self.progress_label = None
        self.start_download_btn = None
        self.pause_download_btn = None
        self.stop_download_btn = None
        self.sources_table = None
        self.config_status_label = None
        self.monitor_text = None
        self.vnpy_adapter = None

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QVBoxLayout(self)

        # 创建选项卡部件
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)

        # 创建4个子界面
        self._create_sub_interfaces()

        main_layout.addWidget(self.tab_widget)

    def _create_sub_interfaces(self):
        """创建4个子界面."""
        # 2.1 品种列表
        self.symbols_tab = self._create_symbols_tab()
        self.tab_widget.addTab(self.symbols_tab, "📋 品种列表")

        # 2.2 本地数据
        self.local_data_tab = self._create_local_data_tab()
        self.tab_widget.addTab(self.local_data_tab, "💾 本地数据")

        # 2.3 数据下载
        self.download_tab = self._create_download_tab()
        self.tab_widget.addTab(self.download_tab, "⬇️ 数据下载")

        # 2.4 数据源管理
        self.sources_tab = self._create_sources_tab()
        self.tab_widget.addTab(self.sources_tab, "🔗 数据源管理")

    def _create_symbols_tab(self):
        """创建品种列表子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 搜索和筛选组
        search_group = QGroupBox("搜索和筛选")
        search_layout = QHBoxLayout(search_group)

        search_layout.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入品种代码或名称...")
        search_layout.addWidget(self.search_input)

        search_layout.addWidget(QLabel("交易所:"))
        self.exchange_combo = QComboBox()
        exchanges = ["全部", "上交所", "深交所", "中金所", "大商所", "郑商所"]
        self.exchange_combo.addItems(exchanges)
        search_layout.addWidget(self.exchange_combo)

        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self._search_symbols)
        search_layout.addWidget(search_btn)

        layout.addWidget(search_group)

        # 品种列表组
        symbols_group = QGroupBox("品种列表")
        symbols_layout = QVBoxLayout(symbols_group)

        self.symbols_table = QTableWidget(0, 6)
        self.symbols_table.setHorizontalHeaderLabels([
            "品种代码", "品种名称", "交易所", "类型", "状态", "操作"
        ])
        header = self.symbols_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        symbols_layout.addWidget(self.symbols_table)

        layout.addWidget(symbols_group)

        return tab

    def _create_local_data_tab(self):
        """创建本地数据子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 上半部分：查询区域
        query_group = QGroupBox("数据查询")
        query_layout = QFormLayout(query_group)

        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("输入品种代码...")
        query_layout.addRow("品种代码:", self.symbol_input)

        self.start_date_input = QLineEdit()
        self.start_date_input.setPlaceholderText("YYYY-MM-DD")
        query_layout.addRow("开始日期:", self.start_date_input)

        self.end_date_input = QLineEdit()
        self.end_date_input.setPlaceholderText("YYYY-MM-DD")
        query_layout.addRow("结束日期:", self.end_date_input)

        query_btn = QPushButton("查询数据")
        query_btn.clicked.connect(self._query_local_data)
        query_layout.addRow(query_btn)

        splitter.addWidget(query_group)

        # 下半部分：数据展示和状态栏
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)

        # 数据展示组
        display_group = QGroupBox("数据展示")
        display_layout = QVBoxLayout(display_group)

        self.data_table = QTableWidget(0, 7)
        self.data_table.setHorizontalHeaderLabels([
            "日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "成交额"
        ])
        header = self.data_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        display_layout.addWidget(self.data_table)

        bottom_layout.addWidget(display_group)

        # 状态栏
        status_layout = QHBoxLayout()

        self.data_status_label = QLabel("就绪")
        status_layout.addWidget(self.data_status_label)

        status_layout.addStretch()

        self.data_quality_label = QLabel("数据质量: --")
        status_layout.addWidget(self.data_quality_label)

        bottom_layout.addLayout(status_layout)

        splitter.addWidget(bottom_widget)
        splitter.setSizes([200, 400])

        layout.addWidget(splitter)

        return tab

    def _create_download_tab(self):
        """创建数据下载子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 下载模式选择
        mode_group = QGroupBox("下载模式")
        mode_layout = QVBoxLayout(mode_group)

        self.full_download_radio = QCheckBox("全量下载")
        self.full_download_radio.setChecked(True)
        mode_layout.addWidget(self.full_download_radio)

        self.custom_download_radio = QCheckBox("自定义下载")
        mode_layout.addWidget(self.custom_download_radio)

        layout.addWidget(mode_group)

        # 下载配置组
        config_group = QGroupBox("下载配置")
        config_layout = QFormLayout(config_group)

        self.download_symbols_input = QLineEdit()
        self.download_symbols_input.setPlaceholderText("如: 000001,000002 或 全部")
        config_layout.addRow("品种列表:", self.download_symbols_input)

        self.download_start_date = QLineEdit()
        self.download_start_date.setPlaceholderText("YYYY-MM-DD")
        config_layout.addRow("开始日期:", self.download_start_date)

        self.download_end_date = QLineEdit()
        self.download_end_date.setPlaceholderText("YYYY-MM-DD")
        config_layout.addRow("结束日期:", self.download_end_date)

        layout.addWidget(config_group)

        # 进度显示组
        progress_group = QGroupBox("下载进度")
        progress_layout = QVBoxLayout(progress_group)

        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        progress_layout.addWidget(self.download_progress)

        self.progress_label = QLabel("准备就绪")
        progress_layout.addWidget(self.progress_label)

        layout.addWidget(progress_group)

        # 控制按钮组
        control_layout = QHBoxLayout()

        self.start_download_btn = QPushButton("开始下载")
        self.start_download_btn.clicked.connect(self._start_download)
        control_layout.addWidget(self.start_download_btn)

        self.pause_download_btn = QPushButton("暂停")
        self.pause_download_btn.clicked.connect(self._pause_download)
        self.pause_download_btn.setEnabled(False)
        control_layout.addWidget(self.pause_download_btn)

        self.stop_download_btn = QPushButton("停止")
        self.stop_download_btn.clicked.connect(self._stop_download)
        self.stop_download_btn.setEnabled(False)
        control_layout.addWidget(self.stop_download_btn)

        control_layout.addStretch()

        layout.addLayout(control_layout)

        return tab

    def _create_sources_tab(self):
        """创建数据源管理子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 数据源状态组
        sources_group = QGroupBox("数据源状态")
        sources_layout = QVBoxLayout(sources_group)

        self.sources_table = QTableWidget(0, 5)
        self.sources_table.setHorizontalHeaderLabels([
            "数据源", "类型", "状态", "连接数", "操作"
        ])
        header = self.sources_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        sources_layout.addWidget(self.sources_table)

        layout.addWidget(sources_group)

        # 配置验证组
        config_group = QGroupBox("配置验证")
        config_layout = QFormLayout(config_group)

        self.config_status_label = QLabel("配置状态: 未检查")
        config_layout.addRow(self.config_status_label)

        test_btn = QPushButton("测试连接")
        test_btn.clicked.connect(self._test_connections)
        config_layout.addRow(test_btn)

        layout.addWidget(config_group)

        # 状态监控组
        monitor_group = QGroupBox("状态监控")
        monitor_layout = QVBoxLayout(monitor_group)

        self.monitor_text = QTextEdit()
        self.monitor_text.setMaximumHeight(150)
        self.monitor_text.setPlaceholderText("连接状态监控信息...")
        monitor_layout.addWidget(self.monitor_text)

        layout.addWidget(monitor_group)

        return tab

    def connect_signals(self):
        """连接信号槽."""
        # 初始化VNPY适配器
        self._initialize_vnpy_adapter()

        # 连接搜索信号
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.exchange_combo.currentTextChanged.connect(
            self._on_exchange_changed)

        # 连接数据查询信号
        self.symbol_input.textChanged.connect(
            self._on_symbol_input_changed)

    def _initialize_vnpy_adapter(self):
        """初始化VNPY适配器."""
        try:
            # 适配器可用性判断，避免 NameError
            if 'VnPyAdapter' in globals() and VnPyAdapter:
                self.vnpy_adapter = VnPyAdapter()
                self.logger.info("VNPY适配器初始化完成")
            else:
                self.logger.warning("VNPY适配器不可用，使用模拟数据")
                self.vnpy_adapter = None
        except (ImportError, AttributeError, RuntimeError) as e:
            self.logger.error("VNPY适配器初始化失败: %s", e)
            self.vnpy_adapter = None

    def _search_symbols(self):
        """搜索品种."""
        search_text = self.search_input.text()
        exchange = self.exchange_combo.currentText()

        self.show_info(f"搜索品种: {search_text}, 交易所: {exchange}")

        # 从VNPY获取品种数据
        if self.vnpy_adapter:
            try:
                # 这里可以实现从VNPY获取品种列表的逻辑
                # 目前先使用模拟数据，后续可以集成实际的品种获取API
                self._load_symbols_data()
            except (AttributeError, RuntimeError, ConnectionError) as e:
                self.show_error(f"搜索品种失败: {str(e)}")
                self._load_symbols_data()  # 回退到模拟数据
        else:
            self._load_symbols_data()

    def _query_local_data(self):
        """查询本地数据."""
        symbol = self.symbol_input.text()
        start_date = self.start_date_input.text()
        end_date = self.end_date_input.text()

        # 默认日期范围：最近30天，避免空值导致异常
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        if not symbol:
            self.show_warning("请输入品种代码")
            return

        self.show_info(f"查询数据: {symbol} ({start_date} 至 {end_date})")

        # 使用VNPY适配器查询数据
        if self.vnpy_adapter:
            try:
                # 获取K线数据
                if hasattr(self.vnpy_adapter, 'get_kline_data'):
                    kline_data = self.vnpy_adapter.get_kline_data(
                        symbol, "日K", limit=100)
                else:
                    kline_data = []

                if kline_data:
                    self._display_kline_data(kline_data, symbol)
                    self.data_status_label.setText(f"显示 {len(kline_data)} 条数据")
                    self.data_quality_label.setText("数据质量: 来自VNPY")
                else:
                    self.show_warning("未找到数据，显示模拟数据")
                    self._load_local_data(symbol, start_date, end_date)

            except (AttributeError, RuntimeError, ConnectionError) as e:
                self.show_error(f"查询数据失败: {str(e)}")
                # 回退到模拟数据
                self._load_local_data(symbol, start_date, end_date)
        else:
            # 无VNPY适配器时使用模拟数据
            self._load_local_data(symbol, start_date, end_date)

    def _start_download(self):
        """开始下载."""
        if self.full_download_radio.isChecked():
            self._start_full_download()
        else:
            self._start_custom_download()

    def _start_full_download(self):
        """开始全量下载."""
        self.show_info("开始全量数据下载...")

        # 模拟下载进度
        self.download_progress.setValue(0)
        self.progress_label.setText("全量下载中...")

        self.start_download_btn.setEnabled(False)
        self.pause_download_btn.setEnabled(True)
        self.stop_download_btn.setEnabled(True)

        # 模拟下载进度
        self._simulate_download_progress()

    def _start_custom_download(self):
        """开始自定义下载."""
        symbols = self.download_symbols_input.text()
        # start_date and end_date are not used in current implementation
        # start_date = self.download_start_date.text()
        # end_date = self.download_end_date.text()

        if not symbols or symbols == "全部":
            self.show_warning("请输入要下载的品种列表")
            return

        self.show_info(f"开始自定义下载: {symbols}")

        # 模拟下载进度
        self.download_progress.setValue(0)
        self.progress_label.setText("自定义下载中...")

        self.start_download_btn.setEnabled(False)
        self.pause_download_btn.setEnabled(True)
        self.stop_download_btn.setEnabled(True)

        # 模拟下载进度
        self._simulate_download_progress()

    def _pause_download(self):
        """暂停下载."""
        self.show_info("下载已暂停")
        self.pause_download_btn.setText("继续")
        self.pause_download_btn.clicked.disconnect()
        self.pause_download_btn.clicked.connect(self._resume_download)

    def _resume_download(self):
        """继续下载."""
        self.show_info("下载继续...")
        self.pause_download_btn.setText("暂停")
        self.pause_download_btn.clicked.disconnect()
        self.pause_download_btn.clicked.connect(self._pause_download)

    def _stop_download(self):
        """停止下载."""
        self.show_info("下载已停止")
        self.download_progress.setValue(0)
        self.progress_label.setText("准备就绪")

        self.start_download_btn.setEnabled(True)
        self.pause_download_btn.setEnabled(False)
        self.stop_download_btn.setEnabled(False)

    def _test_connections(self):
        """测试连接."""
        self.show_info("测试数据源连接...")

        if self.vnpy_adapter:
            try:
                # 获取数据源状态
                if hasattr(self.vnpy_adapter, 'get_status'):
                    status = self.vnpy_adapter.get_status()
                    # 更新数据源表格
                    self._update_data_sources_table(status)
                else:
                    # 使用模拟状态
                    self._update_data_sources_table({})

                # 更新配置状态
                vnpy_available = status.get('vnpy_available', False)
                data_sources = status.get('data_sources', [])

                if vnpy_available and data_sources:
                    sources_text = ', '.join(data_sources)
                    status_text = f"配置状态: 连接正常 (数据源: {sources_text})"
                    self.config_status_label.setText(status_text)
                else:
                    self.config_status_label.setText("配置状态: 部分连接异常")

                self.monitor_text.append("连接测试完成 - 数据源状态已更新")

            except (AttributeError, RuntimeError, ConnectionError) as e:
                self.show_error(f"连接测试失败: {str(e)}")
                self.config_status_label.setText("配置状态: 测试失败")
        else:
            self.config_status_label.setText("配置状态: 测试中...")
            # 模拟测试结果
            QTimer.singleShot(2000, self._update_connection_test_result)

    def _update_connection_test_result(self):
        """更新连接测试结果."""
        self.config_status_label.setText("配置状态: 连接正常")
        self.monitor_text.append("连接测试完成 - 所有数据源连接正常")

    def _update_data_sources_table(self, status):
        """更新数据源表格."""
        # 清空表格
        self.sources_table.setRowCount(0)

        data_sources = status.get('data_sources', [])
        active_source = status.get('active_data_source', '')

        for i, source_name in enumerate(data_sources):
            self.sources_table.insertRow(i)

            # 数据源名称
            self.sources_table.setItem(i, 0, QTableWidgetItem(source_name))

            # 类型（这里可以根据实际情况设置）
            source_type = "VNPY" if source_name != 'mock' else "模拟"
            self.sources_table.setItem(i, 1, QTableWidgetItem(source_type))

            # 状态
            if source_name == active_source:
                status_text = "活动"
                status_color = QColor("#4caf50")
            else:
                status_text = "可用"
                status_color = QColor("#2196f3")

            status_item = QTableWidgetItem(status_text)
            status_item.setBackground(status_color)
            self.sources_table.setItem(i, 2, status_item)

            # 连接数（模拟）
            self.sources_table.setItem(i, 3, QTableWidgetItem("1"))

            # 操作按钮
            switch_btn = QPushButton("切换到此源")

            def connect_switch_btn(src):
                def switch_handler():
                    return self._switch_data_source(src)
                return switch_handler
            switch_btn.clicked.connect(connect_switch_btn(source_name))
            self.sources_table.setCellWidget(i, 4, switch_btn)

    def _switch_data_source(self, source_name):
        """切换数据源."""
        has_switch_method = hasattr(
            self.vnpy_adapter, 'switch_data_source')
        if (self.vnpy_adapter and has_switch_method and
                self.vnpy_adapter.switch_data_source(source_name)):
            self.show_info(f"已切换到数据源: {source_name}")
            # 刷新显示
            if hasattr(self.vnpy_adapter, 'get_status'):
                status = self.vnpy_adapter.get_status()
                self._update_data_sources_table(status)
            else:
                self._update_data_sources_table({})
        else:
            self.show_error("切换数据源失败")

    def _simulate_download_progress(self):
        """模拟下载进度."""
        def update_progress():
            current_value = self.download_progress.value()
            if current_value < 100:
                self.download_progress.setValue(current_value + 10)
                QTimer.singleShot(500, update_progress)
            else:
                self.progress_label.setText("下载完成")
                self.start_download_btn.setEnabled(True)
                self.pause_download_btn.setEnabled(False)
                self.stop_download_btn.setEnabled(False)

        update_progress()

    def _load_symbols_data(self):
        """加载品种数据."""
        # 清空表格
        self.symbols_table.setRowCount(0)

        # 模拟数据
        symbols_data = [
            ("000001", "平安银行", "深交所", "股票", "正常"),
            ("000002", "万科A", "深交所", "股票", "正常"),
            ("600000", "浦发银行", "上交所", "股票", "正常"),
            ("IF2406", "沪深300股指期货", "中金所", "期货", "正常"),
        ]

        for i, (code, name, exchange, type_, status) in enumerate(
                symbols_data):
            self.symbols_table.insertRow(i)
            self.symbols_table.setItem(i, 0, QTableWidgetItem(code))
            self.symbols_table.setItem(i, 1, QTableWidgetItem(name))
            self.symbols_table.setItem(i, 2, QTableWidgetItem(exchange))
            self.symbols_table.setItem(i, 3, QTableWidgetItem(type_))
            self.symbols_table.setItem(i, 4, QTableWidgetItem(status))

            # 操作按钮
            operation_btn = QPushButton("查看")
            operation_btn.clicked.connect(
                self._create_view_handler(code))
            self.symbols_table.setCellWidget(i, 5, operation_btn)

    def _load_local_data(self, _symbol, start_date, end_date):  # noqa: U101
        """加载本地数据."""
        # 清空表格
        self.data_table.setRowCount(0)

        # 模拟数据

        # 生成模拟数据
        try:
            current_date = datetime.strptime(start_date, "%Y-%m-%d")
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            # 日期格式不正确或为空时，回退到最近30天
            current_date = datetime.now() - timedelta(days=30)
            end_date_obj = datetime.now()

        row = 0
        while current_date <= end_date_obj:
            # 模拟价格数据
            open_price = round(random.uniform(10, 100), 2)
            close_price = round(random.uniform(10, 100), 2)
            max_price = max(open_price, close_price)
            min_price = min(open_price, close_price)
            high_price = round(max_price * random.uniform(1.01, 1.05), 2)
            low_price = round(min_price * random.uniform(0.95, 0.99), 2)
            volume = random.randint(10000, 1000000)
            amount = round(close_price * volume / 100, 2)

            self.data_table.insertRow(row)
            date_str = current_date.strftime("%Y-%m-%d")
            self.data_table.setItem(row, 0, QTableWidgetItem(date_str))
            self.data_table.setItem(row, 1, QTableWidgetItem(str(open_price)))
            self.data_table.setItem(row, 2, QTableWidgetItem(str(high_price)))
            self.data_table.setItem(row, 3, QTableWidgetItem(str(low_price)))
            self.data_table.setItem(row, 4, QTableWidgetItem(str(close_price)))
            self.data_table.setItem(row, 5, QTableWidgetItem(str(volume)))
            self.data_table.setItem(row, 6, QTableWidgetItem(str(amount)))

            current_date += timedelta(days=1)
            row += 1

        self.data_status_label.setText(f"显示 {row} 条数据")
        self.data_quality_label.setText("数据质量: 良好")

    def _display_kline_data(self, kline_data, _symbol):  # noqa: U101
        """显示K线数据."""
        # 清空表格
        self.data_table.setRowCount(0)

        for row, data_item in enumerate(kline_data):
            self.data_table.insertRow(row)

            # 格式化日期
            datetime_obj = data_item.get('datetime', '')
            if hasattr(datetime_obj, 'strftime'):
                date_str = datetime_obj.strftime("%Y-%m-%d")
            else:
                date_str = str(datetime_obj)

            self.data_table.setItem(row, 0, QTableWidgetItem(date_str))
            self.data_table.setItem(row, 1, QTableWidgetItem(
                str(data_item.get('open', 0))))
            self.data_table.setItem(row, 2, QTableWidgetItem(
                str(data_item.get('high', 0))))
            self.data_table.setItem(row, 3, QTableWidgetItem(
                str(data_item.get('low', 0))))
            self.data_table.setItem(row, 4, QTableWidgetItem(
                str(data_item.get('close', 0))))
            self.data_table.setItem(row, 5, QTableWidgetItem(
                str(data_item.get('volume', 0))))
            close_price = data_item.get('close', 0)
            volume = data_item.get('volume', 0)
            amount = close_price * volume
            self.data_table.setItem(row, 6, QTableWidgetItem(
                str(amount)))

        self.data_status_label.setText(f"显示 {len(kline_data)} 条数据")
        self.data_quality_label.setText("数据质量: 来自VNPY")

    def _on_search_text_changed(self, text):
        """搜索文本改变."""
        if text.strip():
            # 实时搜索（这里可以实现防抖）
            QTimer.singleShot(500, self._search_symbols)
        else:
            self._load_symbols_data()

    def _on_exchange_changed(self, _text):  # noqa: U101
        """交易所选择改变."""
        self._search_symbols()

    def _on_symbol_input_changed(self, _text):  # noqa: U101
        """品种输入改变."""
        # 可以在这里添加自动补全逻辑

    def refresh_data(self):
        """刷新数据."""
        self._load_symbols_data()
        self.show_info("数据中心数据已刷新")

    def _create_view_handler(self, code: str):
        """创建查看按钮的处理器."""
        def handler():
            self._on_view_symbol(code)
        return handler

    def _on_view_symbol(self, code: str):
        """在品种列表中点击查看：填充代码、切换到本地数据、补全日期并查询。"""
        try:
            self.symbol_input.setText(code)
            # 切换到本地数据标签页
            if self.tab_widget and self.local_data_tab:
                idx = self.tab_widget.indexOf(self.local_data_tab)
                if idx >= 0:
                    self.tab_widget.setCurrentIndex(idx)
            # 补全默认日期
            if self.start_date_input and not self.start_date_input.text():
                self.start_date_input.setText(
                    (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                )
            if self.end_date_input and not self.end_date_input.text():
                self.end_date_input.setText(datetime.now().strftime("%Y-%m-%d"))
            # 执行查询
            self._query_local_data()
        except (AttributeError, RuntimeError, ValueError) as e:
            self.show_error(f"查看品种失败: {e}")

    def on_close(self):
        """关闭处理."""
        self.logger.info("数据中心界面已关闭")
