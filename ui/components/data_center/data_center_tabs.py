# -*- coding: utf-8 -*-
"""数据中心选项卡模块 - 分离各个子界面的创建逻辑."""

import logging
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import QDate, Qt
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
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .data_center_utils import (
    DOWNLOAD_PROGRESS_TABLE_HEADERS,
    EXCHANGES,
    LOCAL_DATA_TABLE_HEADERS,
    PAGE_SIZE_OPTIONS,
    SOURCES_TABLE_HEADERS,
    SYMBOLS_TABLE_HEADERS,
    SYMBOL_TYPES,
)

if TYPE_CHECKING:
    from ui.components.data_center.main_view import DataCenter


class DataCenterTabs:  # pylint: disable=attribute-defined-outside-init,protected-access
    """数据中心选项卡管理器."""

    def __init__(self, parent: "DataCenter"):
        """初始化选项卡管理器."""
        self.parent = parent
        self.logger = logging.getLogger(self.__class__.__name__)

        # 初始化UI控件引用
        self._init_ui_attributes()

    def _init_ui_attributes(self):
        """初始化UI控件属性."""
        # 品种列表选项卡控件
        self.exchange_combo: Optional[QComboBox] = None
        self.symbol_type_combo: Optional[QComboBox] = None
        self.filter_preset_combo: Optional[QComboBox] = None
        self.symbols_count_label: Optional[QLabel] = None
        self.symbols_table: Optional[QTableWidget] = None
        self.search_input: Optional[QLineEdit] = None
        self.page_label: Optional[QLabel] = None
        self.prev_page_btn: Optional[QPushButton] = None
        self.next_page_btn: Optional[QPushButton] = None

        # 本地数据选项卡控件
        self.symbol_input: Optional[QLineEdit] = None
        self.start_date_input: Optional[QDateEdit] = None
        self.end_date_input: Optional[QDateEdit] = None
        self.data_table: Optional[QTableWidget] = None
        self.data_status_label: Optional[QLabel] = None
        self.data_quality_label: Optional[QLabel] = None

        # 数据下载选项卡控件
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

        # 数据源管理选项卡控件
        self.sources_table: Optional[QTableWidget] = None
        self.config_status_label: Optional[QLabel] = None
        self.monitor_text: Optional[QTextEdit] = None

    def create_symbols_tab(self) -> Optional[QWidget]:
        """创建品种列表子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏：重新加载和刷新按钮
        toolbar_layout = QHBoxLayout()

        reload_btn = QPushButton("🔄 重新加载品种")
        reload_btn.setToolTip("通过API重新获取品种列表并更新缓存")
        reload_btn.clicked.connect(self.parent._reload_symbols)
        toolbar_layout.addWidget(reload_btn)

        refresh_btn = QPushButton("↻ 刷新品种")
        refresh_btn.setToolTip("从本地缓存刷新品种列表，不调用API")
        refresh_btn.clicked.connect(self.parent._refresh_symbols)
        toolbar_layout.addWidget(refresh_btn)

        toolbar_layout.addStretch()

        # 添加分页控件
        toolbar_layout.addWidget(QLabel("每页显示:"))
        page_size_combo = QComboBox()
        page_size_combo.addItems(PAGE_SIZE_OPTIONS)
        page_size_combo.setCurrentText("50")
        page_size_combo.currentTextChanged.connect(self.parent._on_page_size_changed)
        toolbar_layout.addWidget(page_size_combo)

        layout.addLayout(toolbar_layout)

        # 搜索和筛选组（优化布局）
        search_group = QGroupBox("搜索和筛选")
        search_main_layout = QVBoxLayout(search_group)

        # 第一行：搜索框
        search_row1 = QHBoxLayout()
        search_row1.addWidget(QLabel("搜索:"))
        search_input = QLineEdit()
        search_input.setPlaceholderText("输入品种代码或名称（支持实时搜索）...")
        search_input.textChanged.connect(self.parent._on_search_text_changed)
        search_row1.addWidget(search_input, 1)
        self.search_input = search_input

        clear_search_btn = QPushButton("✕")
        clear_search_btn.setToolTip("清除搜索")
        clear_search_btn.setMaximumWidth(30)
        clear_search_btn.clicked.connect(lambda: search_input.setText("") if search_input else None)
        search_row1.addWidget(clear_search_btn)

        search_main_layout.addLayout(search_row1)

        # 第二行：筛选条件
        filter_row = QHBoxLayout()

        filter_row.addWidget(QLabel("交易所:"))
        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems(EXCHANGES)
        self.exchange_combo.currentTextChanged.connect(self.parent._on_filter_changed)
        filter_row.addWidget(self.exchange_combo)

        filter_row.addWidget(QLabel("品种类型:"))
        self.symbol_type_combo = QComboBox()
        self.symbol_type_combo.addItems(SYMBOL_TYPES)
        self.symbol_type_combo.currentTextChanged.connect(self.parent._on_filter_changed)
        filter_row.addWidget(self.symbol_type_combo)

        # 添加保存筛选条件按钮
        save_filter_btn = QPushButton("💾 保存筛选")
        save_filter_btn.setToolTip("保存当前筛选条件为预设")
        save_filter_btn.clicked.connect(self.parent._save_filter_preset)
        filter_row.addWidget(save_filter_btn)

        # 添加预设筛选下拉框
        filter_row.addWidget(QLabel("预设:"))
        self.filter_preset_combo = QComboBox()
        self.filter_preset_combo.addItems(["无", "沪深A股", "北证股票", "可转债", "T+0基金"])
        self.filter_preset_combo.currentTextChanged.connect(self.parent._apply_filter_preset)
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
        self.symbols_table.setHorizontalHeaderLabels(SYMBOLS_TABLE_HEADERS)
        header = self.symbols_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # 启用排序
        self.symbols_table.setSortingEnabled(True)

        symbols_layout.addWidget(self.symbols_table)

        # 添加分页控件
        pagination_layout = QHBoxLayout()
        pagination_layout.addWidget(QLabel("页码:"))

        prev_page_btn = QPushButton("◀ 上一页")
        prev_page_btn.clicked.connect(self.parent._prev_page)
        pagination_layout.addWidget(prev_page_btn)
        self.prev_page_btn = prev_page_btn

        page_label = QLabel("第 1 页 / 共 1 页")
        pagination_layout.addWidget(page_label)
        self.page_label = page_label

        next_page_btn = QPushButton("下一页 ▶")
        next_page_btn.clicked.connect(self.parent._next_page)
        pagination_layout.addWidget(next_page_btn)
        self.next_page_btn = next_page_btn

        pagination_layout.addStretch()
        symbols_layout.addLayout(pagination_layout)

        layout.addWidget(symbols_group)

        return tab

    def create_local_data_tab(self) -> Optional[QWidget]:
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
        from datetime import datetime, timedelta

        self.start_date_input.setDate(
            QDate.fromString(
                (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"), "yyyy-MM-dd"
            )
        )
        self.start_date_input.setCalendarPopup(True)
        self.start_date_input.setDisplayFormat("yyyy-MM-dd")
        query_layout.addRow("开始日期:", self.start_date_input)

        self.end_date_input = QDateEdit()
        self.end_date_input.setDate(
            QDate.fromString(datetime.now().strftime("%Y-%m-%d"), "yyyy-MM-dd")
        )
        self.end_date_input.setCalendarPopup(True)
        self.end_date_input.setDisplayFormat("yyyy-MM-dd")
        query_layout.addRow("结束日期:", self.end_date_input)

        query_btn = QPushButton("查询数据")
        query_btn.clicked.connect(self.parent._query_local_data)
        query_layout.addRow(query_btn)

        splitter.addWidget(query_group)

        # 下半部分：数据展示和状态栏
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)

        # 数据展示组
        display_group = QGroupBox("数据展示")
        display_layout = QVBoxLayout(display_group)

        self.data_table = QTableWidget(0, 7)
        self.data_table.setHorizontalHeaderLabels(LOCAL_DATA_TABLE_HEADERS)
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

    def create_download_tab(self) -> Optional[QWidget]:
        """创建数据下载子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 下载模式选择
        mode_group = QGroupBox("下载模式")
        mode_layout = QVBoxLayout(mode_group)

        # 创建按钮组确保互斥选择
        self.download_mode_group = QButtonGroup(self.parent)

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
        from datetime import datetime, timedelta

        self.download_start_date.setDate(
            QDate.fromString(
                (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"), "yyyy-MM-dd"
            )
        )
        self.download_start_date.setCalendarPopup(True)
        self.download_start_date.setDisplayFormat("yyyy-MM-dd")
        config_layout.addRow("开始日期:", self.download_start_date)

        self.download_end_date = QDateEdit()
        self.download_end_date.setDate(
            QDate.fromString(datetime.now().strftime("%Y-%m-%d"), "yyyy-MM-dd")
        )
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
        self.detail_progress_table.setHorizontalHeaderLabels(DOWNLOAD_PROGRESS_TABLE_HEADERS)
        detail_header = self.detail_progress_table.horizontalHeader()
        detail_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.detail_progress_table.setMaximumHeight(150)
        self.detail_progress_table.setVisible(False)  # 默认隐藏
        progress_layout.addWidget(self.detail_progress_table)

        # 显示/隐藏详情按钮
        toggle_detail_btn = QPushButton("▼ 显示详细进度")
        toggle_detail_btn.setCheckable(True)
        toggle_detail_btn.toggled.connect(self.parent._toggle_detail_progress)
        progress_layout.addWidget(toggle_detail_btn)
        self.toggle_detail_btn = toggle_detail_btn

        layout.addWidget(progress_group)

        # 控制按钮组
        control_layout = QHBoxLayout()

        self.start_download_btn = QPushButton("开始下载")
        self.start_download_btn.clicked.connect(self.parent._start_download)
        control_layout.addWidget(self.start_download_btn)

        self.pause_download_btn = QPushButton("暂停")
        self.pause_download_btn.clicked.connect(self.parent._pause_download)
        self.pause_download_btn.setEnabled(False)
        control_layout.addWidget(self.pause_download_btn)

        self.stop_download_btn = QPushButton("停止")
        self.stop_download_btn.clicked.connect(self.parent._stop_download)
        self.stop_download_btn.setEnabled(False)
        control_layout.addWidget(self.stop_download_btn)

        control_layout.addStretch()

        layout.addLayout(control_layout)

        return tab

    def create_sources_tab(self) -> Optional[QWidget]:
        """创建数据源管理子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 数据源状态组
        sources_group = QGroupBox("数据源状态")
        sources_layout = QVBoxLayout(sources_group)

        self.sources_table = QTableWidget(0, 5)
        self.sources_table.setHorizontalHeaderLabels(SOURCES_TABLE_HEADERS)
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
        test_btn.clicked.connect(self.parent._test_connections)
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
