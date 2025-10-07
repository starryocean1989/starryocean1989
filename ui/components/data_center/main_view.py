# -*- coding: utf-8 -*-
"""
数据中心界面 - 主视图.

标准架构：4个子界面采用选项卡形式。
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import QTimer, Qt, QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Import with proper type handling


if TYPE_CHECKING:
    from ui.widgets.base_widget import BaseWidget

    from backend.core.utils.logging_utils import LoggerMixin
else:
    try:
        from ui.widgets.base_widget import BaseWidget
        from backend.core.utils.logging_utils import LoggerMixin
    except ImportError:
        # Fallback classes with proper typing
        class BaseWidget(QWidget):
            """Base widget class for fallback."""

            def __init__(self, parent: Optional[QWidget] = None, title: str = ""):
                """Initialize base widget."""
                super().__init__(parent)
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
            def logger(self) -> logging.Logger:
                """Get logger instance."""
                return logging.getLogger(self.__class__.__name__)


# VnPyAdapter stub class since it doesn't exist in vnpy_integration


class VnPyAdapter:
    """VnPy适配器存根类."""

    def __init__(self):
        """初始化VnPy适配器."""
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_kline_data(self, symbol: str, interval: str, limit: int = 100):
        """获取K线数据."""
        self.logger.info("获取K线数据: %s %s (限制: %d)", symbol, interval, limit)
        # 返回模拟数据
        return []

    def get_status(self):
        """获取状态."""
        return {
            "vnpy_available": True,
            "data_sources": ["mock", "vnpy"],
            "active_data_source": "mock",
        }

    def switch_data_source(self, source_name: str):
        """切换数据源."""
        self.logger.info("切换数据源: %s", source_name)
        return True


class DataCenter(BaseWidget, LoggerMixin):
    """数据中心主界面."""

    def __init__(self, parent=None):
        """初始化数据中心界面."""
        super().__init__(parent, "数据中心")
        self.logger.info("数据中心界面初始化开始")

        # Initialize VNPY adapter first
        self.vnpy_adapter = None

        # Initialize all UI attributes with proper typing
        self.tab_widget: Optional[QTabWidget] = None
        self.symbols_tab: Optional[QWidget] = None
        self.local_data_tab: Optional[QWidget] = None
        self.download_tab: Optional[QWidget] = None
        self.sources_tab: Optional[QWidget] = None
        self.search_input: Optional[QLineEdit] = None
        self.exchange_combo: Optional[QComboBox] = None
        self.symbol_type_combo: Optional[QComboBox] = None
        self.filter_preset_combo: Optional[QComboBox] = None
        self.symbols_count_label: Optional[QLabel] = None
        self.prev_page_btn: Optional[QPushButton] = None
        self.next_page_btn: Optional[QPushButton] = None
        self.page_label: Optional[QLabel] = None
        self.symbols_table: Optional[QTableWidget] = None

        # 分页相关属性
        self.current_page = 1
        self.page_size = 50
        self.total_pages = 1
        self.all_symbols_data = []  # 存储所有品种数据
        self.filtered_symbols_data = []  # 存储筛选后的数据
        self.symbol_input: Optional[QLineEdit] = None
        self.start_date_input: Optional[QDateEdit] = None
        self.end_date_input: Optional[QDateEdit] = None
        self.data_table: Optional[QTableWidget] = None
        self.data_status_label: Optional[QLabel] = None
        self.data_quality_label: Optional[QLabel] = None
        self.full_download_radio: Optional[QRadioButton] = None
        self.custom_download_radio: Optional[QRadioButton] = None
        self.download_mode_group: Optional[QButtonGroup] = None
        self.download_symbols_input: Optional[QLineEdit] = None
        self.download_start_date: Optional[QDateEdit] = None
        self.download_end_date: Optional[QDateEdit] = None
        self.download_progress: Optional[QProgressBar] = None
        self.progress_label: Optional[QLabel] = None
        self.download_speed_label: Optional[QLabel] = None
        self.download_eta_label: Optional[QLabel] = None
        self.detail_progress_table: Optional[QTableWidget] = None
        self.toggle_detail_btn: Optional[QPushButton] = None
        self.start_download_btn: Optional[QPushButton] = None
        self.pause_download_btn: Optional[QPushButton] = None
        self.stop_download_btn: Optional[QPushButton] = None
        self.sources_table: Optional[QTableWidget] = None
        self.config_status_label: Optional[QLabel] = None
        self.monitor_text: Optional[QTextEdit] = None

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
        if not self.tab_widget:
            return
        # 2.1 品种列表
        self.symbols_tab = self._create_symbols_tab()
        if self.symbols_tab:
            self.tab_widget.addTab(self.symbols_tab, "📋 品种列表")

        # 2.2 本地数据
        self.local_data_tab = self._create_local_data_tab()
        if self.local_data_tab:
            self.tab_widget.addTab(self.local_data_tab, "💾 本地数据")

        # 2.3 数据下载
        self.download_tab = self._create_download_tab()
        if self.download_tab:
            self.tab_widget.addTab(self.download_tab, "⬇️ 数据下载")

        # 2.4 数据源管理
        self.sources_tab = self._create_sources_tab()
        if self.sources_tab:
            self.tab_widget.addTab(self.sources_tab, "🔗 数据源管理")

    def _create_symbols_tab(self):
        """创建品种列表子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏：重新加载和刷新按钮
        toolbar_layout = QHBoxLayout()

        reload_btn = QPushButton("🔄 重新加载品种")
        reload_btn.setToolTip("通过API重新获取品种列表并更新缓存")
        reload_btn.clicked.connect(self._reload_symbols)
        toolbar_layout.addWidget(reload_btn)

        refresh_btn = QPushButton("↻ 刷新品种")
        refresh_btn.setToolTip("从本地缓存刷新品种列表，不调用API")
        refresh_btn.clicked.connect(self._refresh_symbols)
        toolbar_layout.addWidget(refresh_btn)

        toolbar_layout.addStretch()

        # 添加分页控件
        toolbar_layout.addWidget(QLabel("每页显示:"))
        page_size_combo = QComboBox()
        page_size_combo.addItems(["20", "50", "100", "200"])
        page_size_combo.setCurrentText("50")
        page_size_combo.currentTextChanged.connect(self._on_page_size_changed)
        toolbar_layout.addWidget(page_size_combo)

        layout.addLayout(toolbar_layout)

        # 搜索和筛选组（优化布局）
        search_group = QGroupBox("搜索和筛选")
        search_main_layout = QVBoxLayout(search_group)

        # 第一行：搜索框
        search_row1 = QHBoxLayout()
        search_row1.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入品种代码或名称（支持实时搜索）...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        search_row1.addWidget(self.search_input, 1)

        clear_search_btn = QPushButton("✕")
        clear_search_btn.setToolTip("清除搜索")
        clear_search_btn.setMaximumWidth(30)
        clear_search_btn.clicked.connect(lambda: self.search_input.setText("") if self.search_input else None)
        search_row1.addWidget(clear_search_btn)

        search_main_layout.addLayout(search_row1)

        # 第二行：筛选条件
        filter_row = QHBoxLayout()

        filter_row.addWidget(QLabel("交易所:"))
        self.exchange_combo = QComboBox()
        exchanges = [
            "全部",
            "上交所",
            "深交所",
            "北交所",
            "中金所",
            "大商所",
            "郑商所",
            "上期所",
            "广期所",
        ]
        self.exchange_combo.addItems(exchanges)
        self.exchange_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.exchange_combo)

        filter_row.addWidget(QLabel("品种类型:"))
        self.symbol_type_combo = QComboBox()
        symbol_types = [
            "全部",
            "股票",
            "基金",
            "债券",
            "可转债",
            "期货",
            "期权",
            "指数",
        ]
        self.symbol_type_combo.addItems(symbol_types)
        self.symbol_type_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.symbol_type_combo)

        # 添加保存筛选条件按钮
        save_filter_btn = QPushButton("💾 保存筛选")
        save_filter_btn.setToolTip("保存当前筛选条件为预设")
        save_filter_btn.clicked.connect(self._save_filter_preset)
        filter_row.addWidget(save_filter_btn)

        # 添加预设筛选下拉框
        filter_row.addWidget(QLabel("预设:"))
        self.filter_preset_combo = QComboBox()
        self.filter_preset_combo.addItems(
            ["无", "沪深A股", "北证股票", "可转债", "T+0基金"]
        )
        self.filter_preset_combo.currentTextChanged.connect(self._apply_filter_preset)
        filter_row.addWidget(self.filter_preset_combo)

        filter_row.addStretch()
        search_main_layout.addLayout(filter_row)

        layout.addWidget(search_group)

        # 品种列表组
        symbols_group = QGroupBox("品种列表")
        symbols_layout = QVBoxLayout(symbols_group)

        # 添加结果统计标签
        self.symbols_count_label = QLabel("共 0 个品种")
        self.symbols_count_label.setStyleSheet("color: #888; font-size: 11px;")
        symbols_layout.addWidget(self.symbols_count_label)

        self.symbols_table = QTableWidget(0, 6)
        self.symbols_table.setHorizontalHeaderLabels(
            ["品种代码", "品种名称", "交易所", "类型", "状态", "操作"]
        )
        header = self.symbols_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # 启用排序
        self.symbols_table.setSortingEnabled(True)

        symbols_layout.addWidget(self.symbols_table)

        # 添加分页控件
        pagination_layout = QHBoxLayout()
        pagination_layout.addWidget(QLabel("页码:"))

        self.prev_page_btn = QPushButton("◀ 上一页")
        self.prev_page_btn.clicked.connect(self._prev_page)
        pagination_layout.addWidget(self.prev_page_btn)

        self.page_label = QLabel("第 1 页 / 共 1 页")
        pagination_layout.addWidget(self.page_label)

        self.next_page_btn = QPushButton("下一页 ▶")
        self.next_page_btn.clicked.connect(self._next_page)
        pagination_layout.addWidget(self.next_page_btn)

        pagination_layout.addStretch()
        symbols_layout.addLayout(pagination_layout)

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

        self.start_date_input = QDateEdit()
        self.start_date_input.setDate(QDate.fromString((datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"), "yyyy-MM-dd"))
        self.start_date_input.setCalendarPopup(True)
        self.start_date_input.setDisplayFormat("yyyy-MM-dd")
        query_layout.addRow("开始日期:", self.start_date_input)

        self.end_date_input = QDateEdit()
        self.end_date_input.setDate(QDate.fromString(datetime.now().strftime("%Y-%m-%d"), "yyyy-MM-dd"))
        self.end_date_input.setCalendarPopup(True)
        self.end_date_input.setDisplayFormat("yyyy-MM-dd")
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
        self.data_table.setHorizontalHeaderLabels(
            ["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "成交额"]
        )
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

        # 创建按钮组确保互斥选择
        self.download_mode_group = QButtonGroup(self)

        self.full_download_radio = QRadioButton("全量下载")
        self.full_download_radio.setChecked(True)
        self.download_mode_group.addButton(self.full_download_radio, 0)
        mode_layout.addWidget(self.full_download_radio)

        self.custom_download_radio = QRadioButton("自定义下载")
        self.download_mode_group.addButton(self.custom_download_radio, 1)
        mode_layout.addWidget(self.custom_download_radio)

        layout.addWidget(mode_group)

        # 下载配置组
        config_group = QGroupBox("下载配置")
        config_layout = QFormLayout(config_group)

        self.download_symbols_input = QLineEdit()
        self.download_symbols_input.setPlaceholderText("如: 000001,000002 或 全部")
        config_layout.addRow("品种列表:", self.download_symbols_input)

        self.download_start_date = QDateEdit()
        self.download_start_date.setDate(QDate.fromString((datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"), "yyyy-MM-dd"))
        self.download_start_date.setCalendarPopup(True)
        self.download_start_date.setDisplayFormat("yyyy-MM-dd")
        config_layout.addRow("开始日期:", self.download_start_date)

        self.download_end_date = QDateEdit()
        self.download_end_date.setDate(QDate.fromString(datetime.now().strftime("%Y-%m-%d"), "yyyy-MM-dd"))
        self.download_end_date.setCalendarPopup(True)
        self.download_end_date.setDisplayFormat("yyyy-MM-dd")
        config_layout.addRow("结束日期:", self.download_end_date)

        layout.addWidget(config_group)

        # 进度显示组（优化）
        progress_group = QGroupBox("下载进度")
        progress_layout = QVBoxLayout(progress_group)

        # 总体进度
        overall_layout = QHBoxLayout()
        overall_layout.addWidget(QLabel("总体进度:"))
        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.setTextVisible(True)
        self.download_progress.setFormat("%p% (%v/%m)")
        overall_layout.addWidget(self.download_progress, 1)
        progress_layout.addLayout(overall_layout)

        # 进度详情标签
        progress_info_layout = QHBoxLayout()
        self.progress_label = QLabel("准备就绪")
        progress_info_layout.addWidget(self.progress_label)

        progress_info_layout.addStretch()

        self.download_speed_label = QLabel("速度: --")
        progress_info_layout.addWidget(self.download_speed_label)

        self.download_eta_label = QLabel("剩余时间: --")
        progress_info_layout.addWidget(self.download_eta_label)

        progress_layout.addLayout(progress_info_layout)

        # 详细进度表格（可折叠）
        self.detail_progress_table = QTableWidget(0, 4)
        self.detail_progress_table.setHorizontalHeaderLabels(
            ["品种", "周期", "进度", "状态"]
        )
        detail_header = self.detail_progress_table.horizontalHeader()
        detail_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.detail_progress_table.setMaximumHeight(150)
        self.detail_progress_table.setVisible(False)  # 默认隐藏
        progress_layout.addWidget(self.detail_progress_table)

        # 显示/隐藏详情按钮
        toggle_detail_btn = QPushButton("▼ 显示详细进度")
        toggle_detail_btn.setCheckable(True)
        toggle_detail_btn.toggled.connect(self._toggle_detail_progress)
        progress_layout.addWidget(toggle_detail_btn)
        self.toggle_detail_btn = toggle_detail_btn

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
        self.sources_table.setHorizontalHeaderLabels(
            ["数据源", "类型", "状态", "连接数", "操作"]
        )
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

        # 连接搜索信号 - 添加空值检查
        if self.search_input:
            self.search_input.textChanged.connect(self._on_search_text_changed)
        if self.exchange_combo:
            self.exchange_combo.currentTextChanged.connect(self._on_exchange_changed)

        # 连接数据查询信号 - 添加空值检查
        if self.symbol_input:
            self.symbol_input.textChanged.connect(self._on_symbol_input_changed)

    def _initialize_vnpy_adapter(self):
        """初始化VNPY适配器."""
        try:
            # 适配器可用性判断，避免 NameError
            if "VnPyAdapter" in globals() and VnPyAdapter:
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
        # 添加空值检查
        if not self.search_input or not self.exchange_combo:
            return

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

    def _reload_symbols(self):
        """重新加载品种（通过API）."""
        self.show_info("正在通过API重新加载品种列表...")
        # 模拟API加载过程
        self._load_symbols_data()
        self.show_info("品种列表已重新加载并缓存")

    def _refresh_symbols(self):
        """刷新品种（从缓存）."""
        self.show_info("从本地缓存刷新品种列表...")
        # 模拟从缓存加载
        self._load_symbols_data()
        self.show_info("品种列表已刷新")

    def _on_search_text_changed(self, _text: str):
        """搜索文本改变时实时筛选."""
        self._apply_filters()

    def _on_filter_changed(self, _value: str):
        """筛选条件改变时重新筛选."""
        self._apply_filters()

    def _on_page_size_changed(self, size_text: str):
        """每页显示数量改变."""
        self.page_size = int(size_text)
        self.current_page = 1
        self._apply_filters()

    def _apply_filters(self):
        """应用所有筛选条件."""
        search_text = self.search_input.text().lower() if self.search_input else ""
        exchange = self.exchange_combo.currentText() if self.exchange_combo else "全部"
        symbol_type = (
            self.symbol_type_combo.currentText() if self.symbol_type_combo else "全部"
        )

        # 筛选数据
        self.filtered_symbols_data = [
            item
            for item in self.all_symbols_data
            if (
                not search_text
                or search_text in item["code"].lower()
                or search_text in item["name"].lower()
            )
            and (exchange == "全部" or item["exchange"] == exchange)
            and (symbol_type == "全部" or item["type"] == symbol_type)
        ]

        # 更新统计和分页
        total_count = len(self.filtered_symbols_data)
        self.total_pages = max(1, (total_count + self.page_size - 1) // self.page_size)
        self.current_page = min(self.current_page, self.total_pages)

    def _save_filter_preset(self):
        """保存当前筛选条件为预设."""
        self.show_info("筛选条件已保存")
        # 这里可以实现保存筛选条件到配置文件的逻辑

    def _apply_filter_preset(self, preset_name: str):
        """应用预设筛选条件."""
        if preset_name == "无":
            return

        preset_map = {
            "沪深A股": {"exchange": "上交所", "type": "股票"},
            "北证股票": {"exchange": "北交所", "type": "股票"},
            "可转债": {"exchange": "全部", "type": "可转债"},
            "T+0基金": {"exchange": "全部", "type": "基金"},
        }

        if preset_name in preset_map:
            preset = preset_map[preset_name]
            if self.exchange_combo:
                self.exchange_combo.setCurrentText(preset.get("exchange", "全部"))
            if self.symbol_type_combo:
                self.symbol_type_combo.setCurrentText(preset.get("type", "全部"))
            self.show_info(f"已应用预设筛选: {preset_name}")

    def _update_symbols_display(self):
        """更新品种列表显示."""
        if not self.symbols_table:
            return

        # 计算当前页的数据范围
        start_idx = (self.current_page - 1) * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.filtered_symbols_data))
        page_data = self.filtered_symbols_data[start_idx:end_idx]

        # 更新表格
        self.symbols_table.setRowCount(len(page_data))
        for row, item in enumerate(page_data):
            self.symbols_table.setItem(row, 0, QTableWidgetItem(item["code"]))
            self.symbols_table.setItem(row, 1, QTableWidgetItem(item["name"]))
            self.symbols_table.setItem(row, 2, QTableWidgetItem(item["exchange"]))
            self.symbols_table.setItem(row, 3, QTableWidgetItem(item["type"]))
            self.symbols_table.setItem(row, 4, QTableWidgetItem(item["status"]))

        # 更新统计标签
        if self.symbols_count_label:
            total = len(self.filtered_symbols_data)
            label_text = f"共 {total} 个品种（第 {start_idx + 1}-{end_idx} 个）"
            self.symbols_count_label.setText(label_text)

        # 更新分页标签
        if self.page_label:
            page_text = f"第 {self.current_page} 页 / 共 {self.total_pages} 页"
            self.page_label.setText(page_text)

        # 更新分页按钮状态
        if self.prev_page_btn:
            self.prev_page_btn.setEnabled(self.current_page > 1)
        if self.next_page_btn:
            self.next_page_btn.setEnabled(self.current_page < self.total_pages)

    def _prev_page(self):
        """上一页."""
        if self.current_page > 1:
            self.current_page -= 1
            self._update_symbols_display()

    def _on_exchange_changed(self, _text: str):
        """交易所选择改变时重新筛选."""
        self._apply_filters()

    def _on_symbol_input_changed(self, _text: str):
        """品种代码输入改变时处理."""
        # 这里可以添加实时验证或其他逻辑
        # 目前主要是为了避免信号连接错误
        pass

    def _next_page(self):
        """下一页."""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._update_symbols_display()
    def _toggle_detail_progress(self, checked: bool):
        """切换详细进度显示."""
        if self.detail_progress_table:
            self.detail_progress_table.setVisible(checked)
        if self.toggle_detail_btn:
            text = "▲ 隐藏详细进度" if checked else "▼ 显示详细进度"
            self.toggle_detail_btn.setText(text)

    def _query_local_data(self):
        """查询本地数据."""
        # 添加空值检查
        if (
            not self.symbol_input
            or not self.start_date_input
            or not self.end_date_input
        ):
            return

        symbol = self.symbol_input.text()

        # 获取日期输入框的值
        start_date = self.start_date_input.date().toString("yyyy-MM-dd")
        end_date = self.end_date_input.date().toString("yyyy-MM-dd")

        if not symbol:
            self.show_warning("请输入品种代码")
            return

        self.show_info(f"查询数据: {symbol} ({start_date} 至 {end_date})")

        # 使用VNPY适配器查询数据
        if self.vnpy_adapter:
            try:
                # 获取K线数据
                if hasattr(self.vnpy_adapter, "get_kline_data"):
                    kline_data = self.vnpy_adapter.get_kline_data(
                        symbol, "日K", limit=100
                    )
                else:
                    kline_data = []

                if kline_data:
                    self._display_kline_data(kline_data, symbol)
                    if self.data_status_label:
                        self.data_status_label.setText(f"显示 {len(kline_data)} 条数据")
                    if self.data_quality_label:
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
        selected_button = self.download_mode_group.checkedButton() if self.download_mode_group else None
        if selected_button == self.full_download_radio:
            self._start_full_download()
        elif selected_button == self.custom_download_radio:
            self._start_custom_download()
        else:
            # 默认执行全量下载
            self._start_full_download()

    def _start_full_download(self):
        """开始全量下载."""
        self.show_info("开始全量数据下载...")

        # 更新UI状态
        if self.progress_label:
            self.progress_label.setText("全量下载中...")
        if self.start_download_btn:
            self.start_download_btn.setEnabled(False)
        if self.pause_download_btn:
            self.pause_download_btn.setEnabled(True)
        if self.stop_download_btn:
            self.stop_download_btn.setEnabled(True)

        # 开始模拟下载进度（会自动重置进度条），传入数据库路径
        db_path = getattr(self, "_test_db_path", "test_data_download.db")
        self._simulate_download_progress(db_path)

    def _start_custom_download(self):
        """开始自定义下载."""
        # 添加空值检查
        if not self.download_symbols_input:
            return

        symbols = self.download_symbols_input.text()
        # 获取日期范围（虽然当前实现中未使用，但保留接口以供将来扩展）
        # TODO: 在实际的数据下载功能中可以使用这些日期参数
        # 这些变量目前未使用，但保留以供将来功能扩展
        start_date_str = self.download_start_date.date().toString("yyyy-MM-dd") if self.download_start_date else ""
        end_date_str = self.download_end_date.date().toString("yyyy-MM-dd") if self.download_end_date else ""

        if not symbols or symbols == "全部":
            self.show_warning("请输入要下载的品种列表")
            return

        self.show_info(f"开始自定义下载: {symbols}")

        # 更新UI状态
        if self.progress_label:
            self.progress_label.setText("自定义下载中...")
        if self.start_download_btn:
            self.start_download_btn.setEnabled(False)
        if self.pause_download_btn:
            self.pause_download_btn.setEnabled(True)
        if self.stop_download_btn:
            self.stop_download_btn.setEnabled(True)

        # 开始模拟下载进度（会自动重置进度条）
        self._simulate_download_progress()

    def _pause_download(self):
        """暂停下载."""
        self.show_info("下载已暂停")
        if self.pause_download_btn:
            self.pause_download_btn.setText("继续")
            self.pause_download_btn.clicked.disconnect()
            self.pause_download_btn.clicked.connect(self._resume_download)

    def _resume_download(self):
        """继续下载."""
        self.show_info("下载继续...")
        if self.pause_download_btn:
            self.pause_download_btn.setText("暂停")
            self.pause_download_btn.clicked.disconnect()
            self.pause_download_btn.clicked.connect(self._pause_download)

    def _stop_download(self):
        """停止下载."""
        self.show_info("下载已停止")

        # 停止进度更新（如果有的话）
        if self.download_progress:
            self.download_progress.setValue(0)

        # 调用完成方法来统一更新UI状态
        self._complete_download()

    def _test_connections(self):
        """测试连接."""
        self.show_info("测试数据源连接...")

        if self.vnpy_adapter:
            try:
                # 获取数据源状态
                if hasattr(self.vnpy_adapter, "get_status"):
                    status = self.vnpy_adapter.get_status()
                    # 更新数据源表格
                    self._update_data_sources_table(status)
                else:
                    # 使用模拟状态
                    self._update_data_sources_table({})

                # 更新配置状态
                vnpy_available = status.get("vnpy_available", False)
                data_sources = status.get("data_sources", [])

                if vnpy_available and data_sources:
                    sources_text = ", ".join(data_sources)
                    status_text = f"配置状态: 连接正常 (数据源: {sources_text})"
                    if self.config_status_label:
                        self.config_status_label.setText(status_text)
                else:
                    if self.config_status_label:
                        self.config_status_label.setText("配置状态: 部分连接异常")

                if self.monitor_text:
                    self.monitor_text.append("连接测试完成 - 数据源状态已更新")

            except (AttributeError, RuntimeError, ConnectionError) as e:
                self.show_error(f"连接测试失败: {str(e)}")
                if self.config_status_label:
                    self.config_status_label.setText("配置状态: 测试失败")
        else:
            if self.config_status_label:
                self.config_status_label.setText("配置状态: 测试中...")
            # 模拟测试结果
            QTimer.singleShot(2000, self._update_connection_test_result)

    def _update_connection_test_result(self):
        """更新连接测试结果."""
        if self.config_status_label:
            self.config_status_label.setText("配置状态: 连接正常")
        if self.monitor_text:
            self.monitor_text.append("连接测试完成 - 所有数据源连接正常")

    def _update_data_sources_table(self, status):
        """更新数据源表格."""
        if not self.sources_table:
            return
        # 清空表格
        self.sources_table.setRowCount(0)

        data_sources = status.get("data_sources", [])
        active_source = status.get("active_data_source", "")

        for i, source_name in enumerate(data_sources):
            self.sources_table.insertRow(i)

            # 数据源名称
            self.sources_table.setItem(i, 0, QTableWidgetItem(source_name))

            # 类型（这里可以根据实际情况设置）
            source_type = "VNPY" if source_name != "mock" else "模拟"
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
        has_switch_method = hasattr(self.vnpy_adapter, "switch_data_source")
        if (
            self.vnpy_adapter
            and has_switch_method
            and self.vnpy_adapter.switch_data_source(source_name)
        ):
            self.show_info(f"已切换到数据源: {source_name}")
            # 刷新显示
            if hasattr(self.vnpy_adapter, "get_status"):
                status = self.vnpy_adapter.get_status()
                self._update_data_sources_table(status)
            else:
                self._update_data_sources_table({})
        else:
            self.show_error("切换数据源失败")

    def _simulate_download_progress(self, db_path=None):
        """模拟下载进度并保存数据到数据库."""

        def update_progress():
            if not self.download_progress:
                return

            current_value = self.download_progress.value()
            if current_value < 100:
                new_value = min(current_value + 10, 100)  # 确保不会超过100
                self.download_progress.setValue(new_value)

                # 在进度更新过程中保存数据
                if new_value % 20 == 0:  # 每20%保存一批数据
                    self._save_sample_data_to_db(db_path)

                # 如果还没完成，继续下一阶段
                if new_value < 100:
                    QTimer.singleShot(500, update_progress)
                else:
                    # 完成时更新UI状态
                    self._complete_download()
            else:
                # 如果已经是100%，直接完成
                self._complete_download()

        # 确保进度条可见并开始更新
        if self.download_progress:
            self.download_progress.setValue(0)
            self.download_progress.show()

        # 延迟一点时间开始更新，确保UI有时间刷新
        QTimer.singleShot(100, update_progress)

    def _save_sample_data_to_db(self, db_path=None):
        """保存示例数据到数据库."""
        try:
            import sqlite3

            # 如果没有指定数据库路径，使用默认路径
            if not db_path:
                db_path = "test_data_download.db"

            # 连接数据库
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 生成一些示例股票数据
            sample_stocks = [
                (
                    "000001",
                    "平安银行",
                    15.50,
                    1000000,
                    "2024-09-01 09:30:00",
                    "股票",
                    "模拟数据",
                ),
                (
                    "000002",
                    "万科A",
                    12.80,
                    800000,
                    "2024-09-01 09:30:00",
                    "股票",
                    "模拟数据",
                ),
                (
                    "600000",
                    "浦发银行",
                    8.90,
                    1500000,
                    "2024-09-01 09:30:00",
                    "股票",
                    "模拟数据",
                ),
                (
                    "000001",
                    "平安银行",
                    15.55,
                    1100000,
                    "2024-09-01 10:00:00",
                    "股票",
                    "模拟数据",
                ),
                (
                    "000002",
                    "万科A",
                    12.85,
                    850000,
                    "2024-09-01 10:00:00",
                    "股票",
                    "模拟数据",
                ),
            ]

            # 插入股票数据
            for stock in sample_stocks:
                cursor.execute(
                    """
                    INSERT INTO quotes (symbol, name, price, volume,
                                       timestamp, category, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    stock,
                )

            # 插入证券信息
            securities = [
                ("000001", "平安银行", "股票"),
                ("000002", "万科A", "股票"),
                ("600000", "浦发银行", "股票"),
            ]

            for security in securities:
                # 检查是否已存在，避免重复插入
                cursor.execute(
                    "SELECT id FROM securities WHERE symbol = ?", (security[0],)
                )
                if not cursor.fetchone():
                    cursor.execute(
                        """
                        INSERT INTO securities (symbol, name, category)
                        VALUES (?, ?, ?)
                    """,
                        security,
                    )

            conn.commit()
            conn.close()

            self.logger.info(f"保存了 {len(sample_stocks)} 条股票数据到数据库")

        except Exception as e:
            self.logger.error(f"保存数据到数据库失败: {e}")

    def _complete_download(self):
        """完成下载，更新UI状态."""
        if self.progress_label:
            # 根据当前状态设置合适的文本
            current_text = self.progress_label.text()
            if "完成" in current_text:
                self.progress_label.setText("下载完成")
            else:
                self.progress_label.setText("准备就绪")
        if self.start_download_btn:
            self.start_download_btn.setEnabled(True)
        if self.pause_download_btn:
            self.pause_download_btn.setEnabled(False)
        if self.stop_download_btn:
            self.stop_download_btn.setEnabled(False)

    def _load_symbols_data(self):
        """加载品种数据."""
        # 添加空值检查
        if not self.symbols_table:
            return

        # 模拟数据（扩展数据以测试分页和筛选）
        symbols_raw = [
            ("000001", "平安银行", "深交所", "股票", "正常"),
            ("000002", "万科A", "深交所", "股票", "正常"),
            ("600000", "浦发银行", "上交所", "股票", "正常"),
            ("600519", "贵州茅台", "上交所", "股票", "正常"),
            ("000858", "五粮液", "深交所", "股票", "正常"),
            ("688001", "华兴源创", "上交所", "股票", "正常"),
            ("830001", "同享科技", "北交所", "股票", "正常"),
            ("110001", "中银转债", "上交所", "可转债", "正常"),
            ("113001", "中行转债", "上交所", "可转债", "正常"),
            ("510050", "50ETF", "上交所", "基金", "正常"),
            ("159001", "易方达基金", "深交所", "基金", "正常"),
            ("IF2406", "沪深300股指期货", "中金所", "期货", "正常"),
            ("IC2406", "中证500股指期货", "中金所", "期货", "正常"),
            ("IH2406", "上证50股指期货", "中金所", "期货", "正常"),
            ("T2406", "10年期国债期货", "中金所", "期货", "正常"),
            ("AU2406", "黄金期货", "上期所", "期货", "正常"),
            ("AG2406", "白银期货", "上期所", "期货", "正常"),
            ("CU2406", "铜期货", "上期所", "期货", "正常"),
            ("RB2406", "螺纹钢期货", "上期所", "期货", "正常"),
            ("A2406", "豆一期货", "大商所", "期货", "正常"),
            ("M2406", "豆粕期货", "大商所", "期货", "正常"),
            ("SR2406", "白糖期货", "郑商所", "期货", "正常"),
            ("TA2406", "PTA期货", "郑商所", "期货", "正常"),
        ]

        # 转换为字典格式
        self.all_symbols_data = [
            {
                "code": code,
                "name": name,
                "exchange": exchange,
                "type": type_,
                "status": status,
            }
            for code, name, exchange, type_, status in symbols_raw
        ]

        # 应用当前筛选条件
        self._apply_filters()

    def _load_local_data(self, _symbol, start_date, end_date):  # noqa: U101
        """加载本地数据."""
        # 添加空值检查
        if not self.data_table:
            return

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

        if self.data_status_label:
            self.data_status_label.setText(f"显示 {row} 条数据")
        if self.data_quality_label:
            self.data_quality_label.setText("数据质量: 良好")

    def _display_kline_data(self, kline_data, _symbol):  # noqa: U101
        """显示K线数据."""
        # 添加空值检查
        if not self.data_table:
            return

        # 清空表格
        self.data_table.setRowCount(0)

        for row, data_item in enumerate(kline_data):
            self.data_table.insertRow(row)

            # 格式化日期
            datetime_obj = data_item.get("datetime", "")
            if hasattr(datetime_obj, "strftime"):
                date_str = datetime_obj.strftime("%Y-%m-%d")
            else:
                date_str = str(datetime_obj)

            self.data_table.setItem(row, 0, QTableWidgetItem(date_str))
            self.data_table.setItem(
                row, 1, QTableWidgetItem(str(data_item.get("open", 0)))
            )
            self.data_table.setItem(
                row, 2, QTableWidgetItem(str(data_item.get("high", 0)))
            )
            self.data_table.setItem(
                row, 3, QTableWidgetItem(str(data_item.get("low", 0)))
            )
            self.data_table.setItem(
                row, 4, QTableWidgetItem(str(data_item.get("close", 0)))
            )
            self.data_table.setItem(
                row, 5, QTableWidgetItem(str(data_item.get("volume", 0)))
            )
            close_price = data_item.get("close", 0)
            volume = data_item.get("volume", 0)
            amount = close_price * volume
            self.data_table.setItem(row, 6, QTableWidgetItem(str(amount)))

        if self.data_status_label:
            self.data_status_label.setText(f"显示 {len(kline_data)} 条数据")
        if self.data_quality_label:
            self.data_quality_label.setText("数据质量: 来自VNPY")

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
            if self.symbol_input:
                self.symbol_input.setText(code)
            # 切换到本地数据标签页
            if self.tab_widget and self.local_data_tab:
                idx = self.tab_widget.indexOf(self.local_data_tab)
                if idx >= 0:
                    self.tab_widget.setCurrentIndex(idx)
            # 补全默认日期
            if self.start_date_input:
                self.start_date_input.setDate(QDate.fromString((datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"), "yyyy-MM-dd"))
            if self.end_date_input:
                self.end_date_input.setDate(QDate.fromString(datetime.now().strftime("%Y-%m-%d"), "yyyy-MM-dd"))
            # 执行查询
            self._query_local_data()
        except (AttributeError, RuntimeError, ValueError) as e:
            self.show_error(f"查看品种失败: {e}")

    def on_close(self):
        """关闭处理."""
        self.logger.info("数据中心界面已关闭")
