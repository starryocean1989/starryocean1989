# -*- coding: utf-8 -*-
"""数据中心界面 - 主视图（重构版）.

标准架构：4个子界面采用选项卡形式。
合并tabs/handlers/utils逻辑，统一backend调用。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDate
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
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.core.base import get_service_manager

from backend.core.utils import LoggerMixin
from ui.widgets.base_widget import BaseWidget

# ==================== 常量定义 ====================

EXCHANGES = ["全部", "上交所", "深交所", "北交所", "中金所", "大商所", "郑商所", "上期所", "广期所"]
SYMBOL_TYPES = ["全部", "股票", "基金", "债券", "可转债", "期货", "期权", "指数"]
PAGE_SIZE_OPTIONS = ["20", "50", "100", "200"]

SYMBOLS_TABLE_HEADERS = ["品种代码", "品种名称", "交易所", "类型", "状态", "操作"]
LOCAL_DATA_TABLE_HEADERS = ["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "成交额"]
DOWNLOAD_PROGRESS_TABLE_HEADERS = ["品种", "周期", "进度", "状态"]
SOURCES_TABLE_HEADERS = ["数据源", "类型", "状态", "连接数", "操作"]

FILTER_PRESETS = {
    "沪深A股": {"exchange": "上交所", "type": "股票"},
    "北证股票": {"exchange": "北交所", "type": "股票"},
    "可转债": {"exchange": "全部", "type": "可转债"},
    "T+0基金": {"exchange": "全部", "type": "基金"},
}


class DataCenter(BaseWidget, LoggerMixin):
    """数据中心主界面（重构版）."""

    def __init__(self, parent=None):
        """初始化数据中心界面."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.data_center_service = None

        # 初始化分页相关属性
        self.current_page = 1
        self.page_size = 50
        self.total_pages = 1
        self.all_symbols_data: List[Dict[str, Any]] = []
        self.filtered_symbols_data: List[Dict[str, Any]] = []

        # 下载任务相关属性
        self.current_download_task_id: Optional[str] = None

        # 初始化UI控件引用
        self.tab_widget: Optional[QTabWidget] = None
        self.symbols_tab: Optional[QWidget] = None
        self.local_data_tab: Optional[QWidget] = None
        self.download_tab: Optional[QWidget] = None
        self.sources_tab: Optional[QWidget] = None

        # 品种列表选项卡控件
        self.exchange_combo: Optional[QComboBox] = None
        self.symbol_type_combo: Optional[QComboBox] = None
        self.filter_preset_combo: Optional[QComboBox] = None
        self.market_combo: Optional[QComboBox] = None  # 添加缺失的属性
        self.category_combo: Optional[QComboBox] = None  # 添加缺失的属性
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
        self.detail_progress_table: Optional[QTableWidget] = None
        self.toggle_detail_btn: Optional[QPushButton] = None
        self.start_download_btn: Optional[QPushButton] = None
        self.pause_download_btn: Optional[QPushButton] = None
        self.stop_download_btn: Optional[QPushButton] = None

        # 数据源管理选项卡控件
        self.sources_table: Optional[QTableWidget] = None
        self.config_status_label: Optional[QLabel] = None
        self.monitor_text: Optional[QTextEdit] = None

        # 调用父类初始化
        super().__init__(parent, "数据中心")
        self.logger.info("数据中心界面初始化完成")

        # 获取数据中心服务
        self._initialize_service()

    def _initialize_service(self):
        """获取数据中心服务."""
        try:
            # 从服务管理器获取数据中心服务
            self.data_center_service = self.service_manager.get_service("data_center_service")
            if self.data_center_service:
                self.logger.info("数据中心服务获取成功")
            else:
                self.logger.warning("数据中心服务未注册")
        except Exception as e:
            self.logger.error("获取数据中心服务失败: %s", e)
            self.show_error(f"服务获取失败: {e}")

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QVBoxLayout(self)

        # 创建选项卡部件
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)

        # 创建4个子界面
        self._create_sub_interfaces()

        if self.tab_widget:
            main_layout.addWidget(self.tab_widget)

    def _create_sub_interfaces(self):
        """创建4个子界面."""
        if not self.tab_widget:
            return

        # 2.1 品种列表子界面
        self.symbols_tab = self._create_symbols_tab()
        if self.symbols_tab:
            self.tab_widget.addTab(self.symbols_tab, "📋 品种列表")

        # 2.3 本地数据子界面
        self.local_data_tab = self._create_local_data_tab()
        if self.local_data_tab:
            self.tab_widget.addTab(self.local_data_tab, "💾 本地数据")

        # 2.2 数据下载子界面
        self.download_tab = self._create_download_tab()
        if self.download_tab:
            self.tab_widget.addTab(self.download_tab, "⬇️ 数据下载")

        # 2.4 数据源管理子界面
        self.sources_tab = self._create_sources_tab()
        if self.sources_tab:
            self.tab_widget.addTab(self.sources_tab, "🔗 数据源管理")

    # ==================== 品种列表子界面 ====================

    def _create_symbols_tab(self) -> QWidget:
        """创建品种列表子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏
        toolbar_layout = QHBoxLayout()
        reload_btn = QPushButton("🔄 重新加载品种")
        reload_btn.setToolTip("通过API重新获取品种列表并更新缓存")
        reload_btn.clicked.connect(self._reload_symbols)
        toolbar_layout.addWidget(reload_btn)

        refresh_btn = QPushButton("↻ 刷新品种")
        refresh_btn.setToolTip("从本地缓存刷新品种列表")
        refresh_btn.clicked.connect(self._refresh_symbols)
        toolbar_layout.addWidget(refresh_btn)

        toolbar_layout.addStretch()
        toolbar_layout.addWidget(QLabel("每页显示:"))
        page_size_combo = QComboBox()
        page_size_combo.addItems(PAGE_SIZE_OPTIONS)
        page_size_combo.setCurrentText("50")
        page_size_combo.currentTextChanged.connect(self._on_page_size_changed)
        toolbar_layout.addWidget(page_size_combo)

        layout.addLayout(toolbar_layout)

        # 搜索和筛选组
        search_group = QGroupBox("搜索和筛选")
        search_layout = QVBoxLayout(search_group)

        # 搜索框
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入品种代码或名称...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        search_row.addWidget(self.search_input, 1)
        search_layout.addLayout(search_row)

        # 筛选条件
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("交易所:"))
        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems(EXCHANGES)
        self.exchange_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.exchange_combo)

        filter_row.addWidget(QLabel("品种类型:"))
        self.symbol_type_combo = QComboBox()
        self.symbol_type_combo.addItems(SYMBOL_TYPES)
        self.symbol_type_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.symbol_type_combo)

        filter_row.addWidget(QLabel("预设:"))
        self.filter_preset_combo = QComboBox()
        self.filter_preset_combo.addItems(["无"] + list(FILTER_PRESETS.keys()))
        self.filter_preset_combo.currentTextChanged.connect(self._apply_filter_preset)
        filter_row.addWidget(self.filter_preset_combo)

        filter_row.addStretch()
        search_layout.addLayout(filter_row)

        layout.addWidget(search_group)

        # 品种列表组
        symbols_group = QGroupBox("品种列表")
        symbols_layout = QVBoxLayout(symbols_group)

        self.symbols_count_label = QLabel("共 0 个品种")
        symbols_layout.addWidget(self.symbols_count_label)

        self.symbols_table = QTableWidget(0, 6)
        self.symbols_table.setHorizontalHeaderLabels(SYMBOLS_TABLE_HEADERS)
        header = self.symbols_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        symbols_layout.addWidget(self.symbols_table)

        # 分页控件
        pagination_layout = QHBoxLayout()
        self.prev_page_btn = QPushButton("上一页")
        self.prev_page_btn.clicked.connect(self._prev_page)
        pagination_layout.addWidget(self.prev_page_btn)

        self.page_label = QLabel("第 1 页 / 共 1 页")
        pagination_layout.addWidget(self.page_label)

        self.next_page_btn = QPushButton("下一页")
        self.next_page_btn.clicked.connect(self._next_page)
        pagination_layout.addWidget(self.next_page_btn)

        symbols_layout.addLayout(pagination_layout)
        layout.addWidget(symbols_group)

        # 初始加载数据
        self._load_symbols_data()

        return tab

    # ==================== 本地数据子界面 ====================

    def _create_local_data_tab(self) -> QWidget:
        """创建本地数据子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 查询组
        query_group = QGroupBox("本地数据查询")
        query_layout = QFormLayout(query_group)

        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("例如: 000001 或 600000")
        query_layout.addRow("品种代码:", self.symbol_input)

        self.start_date_input = QDateEdit()
        self.start_date_input.setCalendarPopup(True)
        self.start_date_input.setDate(QDate.currentDate().addMonths(-1))
        query_layout.addRow("开始日期:", self.start_date_input)

        self.end_date_input = QDateEdit()
        self.end_date_input.setCalendarPopup(True)
        self.end_date_input.setDate(QDate.currentDate())
        query_layout.addRow("结束日期:", self.end_date_input)

        query_btn = QPushButton("查询")
        query_btn.clicked.connect(self._query_local_data)
        query_layout.addRow("", query_btn)

        layout.addWidget(query_group)

        # 数据展示组
        data_group = QGroupBox("数据展示")
        data_layout = QVBoxLayout(data_group)

        self.data_table = QTableWidget(0, 7)
        self.data_table.setHorizontalHeaderLabels(LOCAL_DATA_TABLE_HEADERS)
        header = self.data_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        data_layout.addWidget(self.data_table)

        layout.addWidget(data_group)

        # 状态栏组
        status_group = QGroupBox("本地数据状态")
        status_layout = QVBoxLayout(status_group)

        self.data_status_label = QLabel("等待查询...")
        status_layout.addWidget(self.data_status_label)

        self.data_quality_label = QLabel("数据质量: --")
        status_layout.addWidget(self.data_quality_label)

        layout.addWidget(status_group)

        return tab

    # ==================== 数据下载子界面 ====================

    def _create_download_tab(self) -> QWidget:
        """创建数据下载子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 下载模式组
        mode_group = QGroupBox("下载模式")
        mode_layout = QVBoxLayout(mode_group)

        self.download_mode_group = QButtonGroup()
        self.full_download_radio = QRadioButton("全量下载（全品类、全周期、固定长度历史数据）")
        self.full_download_radio.setChecked(True)
        self.download_mode_group.addButton(self.full_download_radio, 1)
        mode_layout.addWidget(self.full_download_radio)

        self.custom_download_radio = QRadioButton("增量下载（自定义日期范围）")
        self.download_mode_group.addButton(self.custom_download_radio, 2)
        mode_layout.addWidget(self.custom_download_radio)

        # 增量下载配置
        custom_layout = QFormLayout()
        self.download_start_date = QDateEdit()
        self.download_start_date.setCalendarPopup(True)
        self.download_start_date.setDate(QDate.currentDate().addMonths(-3))
        custom_layout.addRow("开始日期:", self.download_start_date)

        self.download_end_date = QDateEdit()
        self.download_end_date.setCalendarPopup(True)
        self.download_end_date.setDate(QDate.currentDate())
        custom_layout.addRow("结束日期:", self.download_end_date)

        mode_layout.addLayout(custom_layout)
        layout.addWidget(mode_group)

        # 控制组
        control_group = QGroupBox("下载控制")
        control_layout = QHBoxLayout(control_group)

        self.start_download_btn = QPushButton("开始下载")
        self.start_download_btn.clicked.connect(self._start_download)
        control_layout.addWidget(self.start_download_btn)

        self.pause_download_btn = QPushButton("暂停")
        self.pause_download_btn.setEnabled(False)
        self.pause_download_btn.clicked.connect(self._pause_download)
        control_layout.addWidget(self.pause_download_btn)

        self.stop_download_btn = QPushButton("停止")
        self.stop_download_btn.setEnabled(False)
        self.stop_download_btn.clicked.connect(self._stop_download)
        control_layout.addWidget(self.stop_download_btn)

        control_layout.addStretch()
        layout.addWidget(control_group)

        # 进度组
        progress_group = QGroupBox("下载进度")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_label = QLabel("准备就绪")
        progress_layout.addWidget(self.progress_label)

        self.download_progress = QProgressBar()
        progress_layout.addWidget(self.download_progress)

        # 详细进度
        self.toggle_detail_btn = QPushButton("显示详细进度")
        self.toggle_detail_btn.setCheckable(True)
        self.toggle_detail_btn.toggled.connect(self._toggle_detail_progress)
        progress_layout.addWidget(self.toggle_detail_btn)

        self.detail_progress_table = QTableWidget(0, 4)
        self.detail_progress_table.setHorizontalHeaderLabels(DOWNLOAD_PROGRESS_TABLE_HEADERS)
        self.detail_progress_table.setVisible(False)
        progress_layout.addWidget(self.detail_progress_table)

        layout.addWidget(progress_group)

        return tab

    # ==================== 数据源管理子界面 ====================

    def _create_sources_tab(self) -> QWidget:
        """创建数据源管理子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 数据源列表组
        sources_group = QGroupBox("数据源列表")
        sources_layout = QVBoxLayout(sources_group)

        self.sources_table = QTableWidget(0, 5)
        self.sources_table.setHorizontalHeaderLabels(SOURCES_TABLE_HEADERS)
        header = self.sources_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        sources_layout.addWidget(self.sources_table)

        layout.addWidget(sources_group)

        # 配置状态组
        config_group = QGroupBox("配置状态")
        config_layout = QVBoxLayout(config_group)

        self.config_status_label = QLabel("未连接任何数据源")
        config_layout.addWidget(self.config_status_label)

        layout.addWidget(config_group)

        # 监控组
        monitor_group = QGroupBox("实时监控")
        monitor_layout = QVBoxLayout(monitor_group)

        self.monitor_text = QTextEdit()
        self.monitor_text.setReadOnly(True)
        self.monitor_text.setMaximumHeight(150)
        monitor_layout.addWidget(self.monitor_text)

        layout.addWidget(monitor_group)

        # 初始加载数据源
        self._load_data_sources()

        return tab

    # ==================== 品种列表事件处理 ====================

    def _reload_symbols(self):
        """重新加载品种（通过API）."""
        try:
            if not self.data_center_service:
                self.show_error("数据中心服务未初始化")
                return

            self.show_info("正在重新加载品种列表...")
            result = self.data_center_service.reload_symbol_list(force=True)

            if result["success"]:
                self.all_symbols_data = result.get("data", [])
                self._apply_filters()
                self.show_info(f"成功加载 {result['symbol_count']} 个品种")
            else:
                self.show_error(f"加载失败: {result.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error("重新加载品种失败: %s", e)
            self.show_error(f"加载失败: {e}")

    def _refresh_symbols(self):
        """刷新品种（从缓存）."""
        try:
            if not self.data_center_service:
                self.show_error("数据中心服务未初始化")
                return

            result = self.data_center_service.refresh_symbol_list()

            if result["success"]:
                self.all_symbols_data = result.get("data", [])
                self._apply_filters()
                self.show_info(f"刷新成功，共 {result['symbol_count']} 个品种")
            else:
                self.show_error(f"刷新失败: {result.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error("刷新品种失败: %s", e)
            self.show_error(f"刷新失败: {e}")

    def _load_symbols_data(self):
        """初始加载品种数据."""
        self._refresh_symbols()

    def _apply_filters(self):
        """应用筛选条件."""
        if not self.all_symbols_data:
            self.filtered_symbols_data = []
            self._update_symbols_table()
            return

        filtered = self.all_symbols_data

        # 搜索关键字
        if self.search_input:
            search_text = self.search_input.text().strip().lower()
            if search_text:
                filtered = [
                    s
                    for s in filtered
                    if search_text in s.get("symbol", "").lower()
                    or search_text in s.get("name", "").lower()
                ]

        # 交易所筛选
        if self.exchange_combo:
            exchange = self.exchange_combo.currentText()
            if exchange != "全部":
                filtered = [s for s in filtered if s.get("exchange") == exchange]

        # 品种类型筛选
        if self.symbol_type_combo:
            symbol_type = self.symbol_type_combo.currentText()
            if symbol_type != "全部":
                filtered = [s for s in filtered if s.get("product_type") == symbol_type]

        self.filtered_symbols_data = filtered
        self.current_page = 1
        self._update_symbols_table()

    def _update_symbols_table(self):
        """更新品种表格."""
        if not self.symbols_table:
            return

        # 计算分页
        total_items = len(self.filtered_symbols_data)
        self.total_pages = max(1, (total_items + self.page_size - 1) // self.page_size)
        start_idx = (self.current_page - 1) * self.page_size
        end_idx = min(start_idx + self.page_size, total_items)
        page_data = self.filtered_symbols_data[start_idx:end_idx]

        # 更新表格
        self.symbols_table.setRowCount(len(page_data))
        for i, symbol in enumerate(page_data):
            self.symbols_table.setItem(i, 0, QTableWidgetItem(symbol.get("symbol", "")))
            self.symbols_table.setItem(i, 1, QTableWidgetItem(symbol.get("name", "")))
            self.symbols_table.setItem(i, 2, QTableWidgetItem(symbol.get("exchange", "")))
            self.symbols_table.setItem(i, 3, QTableWidgetItem(symbol.get("product_type", "")))
            self.symbols_table.setItem(i, 4, QTableWidgetItem("正常"))

            # 操作按钮
            view_btn = QPushButton("查看")
            view_btn.clicked.connect(self._create_view_handler(symbol.get("symbol", "")))
            self.symbols_table.setCellWidget(i, 5, view_btn)

        # 更新统计和分页
        if self.symbols_count_label:
            self.symbols_count_label.setText(f"共 {total_items} 个品种")
        if self.page_label:
            self.page_label.setText(f"第 {self.current_page} 页 / 共 {self.total_pages} 页")
        if self.prev_page_btn:
            self.prev_page_btn.setEnabled(self.current_page > 1)
        if self.next_page_btn:
            self.next_page_btn.setEnabled(self.current_page < self.total_pages)

    def _on_search_text_changed(self, text: str):
        """搜索文本改变."""
        self._apply_filters()

    def _on_filter_changed(self, value: str):
        """筛选条件改变."""
        self._apply_filters()

    def _apply_filter_preset(self, preset_name: str):
        """应用筛选预设."""
        if preset_name == "无" or preset_name not in FILTER_PRESETS:
            return

        preset = FILTER_PRESETS[preset_name]
        if self.exchange_combo:
            self.exchange_combo.setCurrentText(preset.get("exchange", "全部"))
        if self.symbol_type_combo:
            self.symbol_type_combo.setCurrentText(preset.get("type", "全部"))

    def _on_page_size_changed(self, size_text: str):
        """每页显示数量改变."""
        self.page_size = int(size_text)
        self.current_page = 1
        self._update_symbols_table()

    def _prev_page(self):
        """上一页."""
        if self.current_page > 1:
            self.current_page -= 1
            self._update_symbols_table()

    def _next_page(self):
        """下一页."""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._update_symbols_table()

    def _create_view_handler(self, code: str):
        """创建查看按钮的处理器."""

        def handler():
            self._on_view_symbol(code)

        return handler

    def _on_view_symbol(self, code: str):
        """查看品种详情."""
        if self.symbol_input:
            self.symbol_input.setText(code)
        if self.tab_widget:
            self.tab_widget.setCurrentIndex(1)
        self._query_local_data()

    def _save_filter_preset(self):
        """保存筛选预设."""
        if not self.data_center_service:
            self.show_error("数据中心服务不可用")
            return

        from PySide6.QtWidgets import QInputDialog

        # 弹出对话框让用户输入预设名称
        preset_name, ok = QInputDialog.getText(
            self, "保存筛选预设", "请输入预设名称:", text="我的筛选"
        )

        if ok and preset_name:
            # 收集当前筛选条件
            filters = {}

            if self.market_combo:
                filters["market"] = self.market_combo.currentText()
            if self.category_combo:
                filters["category"] = self.category_combo.currentText()
            if self.search_input:
                filters["search"] = self.search_input.text()

            # 保存预设
            result = self.data_center_service.save_filter_preset(preset_name, filters)

            if result.get("success"):
                self.show_info(f"筛选预设 '{preset_name}' 保存成功")
            else:
                self.show_error(f"保存失败: {result.get('message', '未知错误')}")

    # ==================== 本地数据事件处理 ====================

    def _query_local_data(self):
        """查询本地数据."""
        try:
            if not self.data_center_service:
                self.show_error("数据中心服务未初始化")
                return

            if not self.symbol_input or not self.symbol_input.text().strip():
                self.show_warning("请输入品种代码")
                return

            symbol = self.symbol_input.text().strip()
            start_date_str = ""
            end_date_str = ""

            if self.start_date_input:
                qdate = self.start_date_input.date()
                start_date_str = qdate.toString("yyyy-MM-dd")
            if self.end_date_input:
                qdate = self.end_date_input.date()
                end_date_str = qdate.toString("yyyy-MM-dd")

            self.show_info("正在查询本地数据...")
            result = self.data_center_service.query_local_data(
                symbol=symbol, start_date=start_date_str, end_date=end_date_str, interval="1d"
            )

            if result["success"]:
                data = result.get("data", [])
                if self.data_table:
                    self.data_table.setRowCount(len(data))
                    for i, record in enumerate(data):
                        self.data_table.setItem(
                            i, 0, QTableWidgetItem(str(record.get("datetime", "")))
                        )
                        self.data_table.setItem(i, 1, QTableWidgetItem(str(record.get("open", ""))))
                        self.data_table.setItem(i, 2, QTableWidgetItem(str(record.get("high", ""))))
                        self.data_table.setItem(i, 3, QTableWidgetItem(str(record.get("low", ""))))
                        self.data_table.setItem(
                            i, 4, QTableWidgetItem(str(record.get("close", "")))
                        )
                        self.data_table.setItem(
                            i, 5, QTableWidgetItem(str(record.get("volume", "")))
                        )
                        self.data_table.setItem(
                            i, 6, QTableWidgetItem(str(record.get("turnover", 0)))
                        )

                if self.data_status_label:
                    self.data_status_label.setText(f"查询成功，共 {len(data)} 条记录")
            else:
                self.show_error(f"查询失败: {result.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error("查询本地数据失败: %s", e)
            self.show_error(f"查询失败: {e}")

    # ==================== 数据下载事件处理 ====================

    def _start_download(self):
        """开始下载."""
        try:
            if not self.data_center_service:
                self.show_error("数据中心服务未初始化")
                return

            if self.full_download_radio and self.full_download_radio.isChecked():
                result = self.data_center_service.start_full_download()
                if result["success"]:
                    self.show_info(f"全量下载已启动，任务ID: {result['task_id']}")
                else:
                    self.show_error(f"启动失败: {result.get('message', '未知错误')}")
                    return
            else:
                if self.download_start_date:
                    qdate = self.download_start_date.date()
                    start_date_str = qdate.toString("yyyy-MM-dd")
                else:
                    start_date_str = datetime.now().strftime("%Y-%m-%d")

                result = self.data_center_service.start_incremental_download(start_date_str)
                if result["success"]:
                    self.show_info(f"增量下载已启动，任务ID: {result['task_id']}")
                else:
                    self.show_error(f"启动失败: {result.get('message', '未知错误')}")
                    return

            if self.start_download_btn:
                self.start_download_btn.setEnabled(False)
            if self.pause_download_btn:
                self.pause_download_btn.setEnabled(True)
            if self.stop_download_btn:
                self.stop_download_btn.setEnabled(True)

        except Exception as e:
            self.logger.error("启动下载失败: %s", e)
            self.show_error(f"启动失败: {e}")

    def _pause_download(self):
        """暂停下载."""
        if not self.data_center_service:
            self.show_error("数据中心服务不可用")
            return

        if not hasattr(self, "current_download_task_id"):
            self.show_warning("没有正在运行的下载任务")
            return

        result = self.data_center_service.pause_download(self.current_download_task_id)

        if result.get("success"):
            self.show_info("下载已暂停")
            if self.pause_download_btn:
                self.pause_download_btn.setText("恢复下载")
                self.pause_download_btn.clicked.disconnect()
                self.pause_download_btn.clicked.connect(self._resume_download)
        else:
            self.show_error(f"暂停失败: {result.get('message', '未知错误')}")

    def _resume_download(self):
        """恢复下载."""
        if not self.data_center_service:
            self.show_error("数据中心服务不可用")
            return

        if not hasattr(self, "current_download_task_id"):
            self.show_warning("没有暂停的下载任务")
            return

        result = self.data_center_service.resume_download(self.current_download_task_id)

        if result.get("success"):
            self.show_info("下载已恢复")
            if self.pause_download_btn:
                self.pause_download_btn.setText("暂停下载")
                self.pause_download_btn.clicked.disconnect()
                self.pause_download_btn.clicked.connect(self._pause_download)
        else:
            self.show_error(f"恢复失败: {result.get('message', '未知错误')}")

    def _stop_download(self):
        """停止下载."""
        if not self.data_center_service:
            self.show_error("数据中心服务不可用")
            return

        if not hasattr(self, "current_download_task_id"):
            self.show_warning("没有正在运行的下载任务")
            return

        result = self.data_center_service.stop_download(self.current_download_task_id)

        if result.get("success"):
            self.show_info("下载已停止")
            if self.start_download_btn:
                self.start_download_btn.setEnabled(True)
            if self.pause_download_btn:
                self.pause_download_btn.setEnabled(False)
            if self.stop_download_btn:
                self.stop_download_btn.setEnabled(False)

            # 清除任务ID
            if hasattr(self, "current_download_task_id"):
                delattr(self, "current_download_task_id")
        else:
            self.show_error(f"停止失败: {result.get('message', '未知错误')}")
        if self.start_download_btn:
            self.start_download_btn.setEnabled(True)
        if self.pause_download_btn:
            self.pause_download_btn.setEnabled(False)
        if self.stop_download_btn:
            self.stop_download_btn.setEnabled(False)

    def _toggle_detail_progress(self, checked: bool):  # noqa: U101
        """切换详细进度显示."""
        if self.detail_progress_table:
            self.detail_progress_table.setVisible(checked)

    # ==================== 数据源管理事件处理 ====================

    def _load_data_sources(self):
        """加载数据源列表."""
        try:
            if not self.data_center_service:
                return

            # 获取数据源状态
            result = self.data_center_service.get_datafeed_status()

            if result["success"]:
                sources_data = result.get("datafeeds", {})

                if self.sources_table:
                    # 固定的4个数据源
                    source_list = [
                        {"id": "data_engine", "name": "Data Engine", "type": "本地"},
                        {"id": "ifind", "name": "iFind", "type": "商业"},
                        {"id": "rqdata", "name": "RQData", "type": "商业"},
                        {"id": "tushare", "name": "Tushare", "type": "商业"},
                    ]

                    self.sources_table.setRowCount(len(source_list))
                    for i, source in enumerate(source_list):
                        source_id = source["id"]
                        status_info = sources_data.get(source_id, {})

                        self.sources_table.setItem(i, 0, QTableWidgetItem(source["name"]))
                        self.sources_table.setItem(i, 1, QTableWidgetItem(source["type"]))

                        # 状态
                        connected = status_info.get("connected", False)
                        pushing = status_info.get("pushing_data", False)
                        if pushing:
                            status_text = "推送中"
                        elif connected:
                            status_text = "已连接"
                        else:
                            status_text = "未连接"
                        self.sources_table.setItem(i, 2, QTableWidgetItem(status_text))
                        self.sources_table.setItem(i, 3, QTableWidgetItem("0"))

                        # 操作按钮
                        connect_btn = QPushButton("连接" if not connected else "断开")
                        connect_btn.clicked.connect(
                            lambda _checked, sid=source_id, conn=connected: self._toggle_source_connection(
                                sid, conn
                            )
                        )
                        self.sources_table.setCellWidget(i, 4, connect_btn)

        except Exception as e:
            self.logger.error("加载数据源失败: %s", e)

    def _toggle_source_connection(self, source_id: str, currently_connected: bool):
        """切换数据源连接状态."""
        try:
            if not self.data_center_service:
                return

            if currently_connected:
                result = self.data_center_service.disconnect_datafeed(source_id)
            else:
                result = self.data_center_service.connect_datafeed(source_id)

            if result["success"]:
                self.show_info(result.get("message", "操作成功"))
                self._load_data_sources()
            else:
                self.show_error(f"操作失败: {result.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error("切换数据源连接失败: %s", e)
            self.show_error(f"操作失败: {e}")

    # ==================== 通用方法 ====================

    def connect_signals(self):
        """连接信号槽."""

    def refresh_data(self):
        """刷新数据."""
        self._refresh_symbols()

    def on_close(self):
        """关闭处理."""
        self.logger.info("数据中心界面已关闭")
