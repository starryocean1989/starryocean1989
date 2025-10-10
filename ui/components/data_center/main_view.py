# -*- coding: utf-8 -*-
"""数据中心界面 - 主视图（重构版）.

标准架构：4个子界面采用选项卡形式。
合并tabs/handlers/utils逻辑，统一backend调用。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDate, QThread, Signal
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

EXCHANGES = ["全部", "上交所", "深交所", "北交所"]
SYMBOL_TYPES = ["全部", "股票", "基金", "可转债"]
PAGE_SIZE_OPTIONS = ["20", "50", "100", "200"]

SYMBOLS_TABLE_HEADERS = ["品种代码", "品种名称", "交易所", "类型", "状态", "操作"]
LOCAL_DATA_TABLE_HEADERS = ["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "成交额"]
DOWNLOAD_PROGRESS_TABLE_HEADERS = ["品种", "周期", "进度", "状态"]
SOURCES_TABLE_HEADERS = ["数据源", "类型", "状态", "连接数", "操作"]


# ==================== 异步工作线程 ====================


class ReloadSymbolsThread(QThread):
    """异步重新加载品种的工作线程."""

    # 定义信号
    finished_signal = Signal(dict)  # 完成信号，传递结果字典
    error_signal = Signal(str)  # 错误信号，传递错误消息
    progress_signal = Signal(str)  # 进度信号，传递进度消息

    def __init__(self, data_center_service, parent=None):
        """初始化工作线程.

        Args:
            data_center_service: 数据中心服务实例
            parent: 父对象
        """
        super().__init__(parent)
        self.data_center_service = data_center_service

    def run(self):
        """线程执行函数（在后台线程中运行）."""
        import logging

        logger = logging.getLogger(__name__)

        # 同时使用print和logging，确保能看到输出
        print(">>> [THREAD] ReloadSymbolsThread.run() 开始执行", flush=True)
        logger.info(">>> [THREAD] ReloadSymbolsThread.run() 开始执行")

        try:
            print(">>> [THREAD] 发送进度信号...", flush=True)
            self.progress_signal.emit("正在连接服务器...")
            logger.info(">>> [THREAD] 发送进度信号: 正在连接服务器...")

            # 在后台线程中执行耗时操作
            print(">>> [THREAD] 开始调用 reload_symbol_list()...", flush=True)
            logger.info(">>> [THREAD] 开始调用 reload_symbol_list()...")
            import time

            start_time = time.time()
            result = self.data_center_service.reload_symbol_list(force=True)
            elapsed = time.time() - start_time

            print(f">>> [THREAD] reload_symbol_list() 完成，耗时: {elapsed:.2f}秒", flush=True)
            logger.info(">>> [THREAD] reload_symbol_list() 完成，耗时: %.2f秒", elapsed)

            # 发送完成信号
            print(
                f">>> [THREAD] 发送完成信号: success={result.get('success')}, count={result.get('symbol_count')}",
                flush=True,
            )
            logger.info(
                ">>> [THREAD] 发送完成信号，结果: success=%s, count=%s",
                result.get("success"),
                result.get("symbol_count"),
            )
            self.finished_signal.emit(result)

            print(">>> [THREAD] ReloadSymbolsThread.run() 执行完成", flush=True)
            logger.info(">>> [THREAD] ReloadSymbolsThread.run() 执行完成")

        except Exception as e:
            # 发送错误信号
            print(f">>> [THREAD] 发生异常: {e}", flush=True)
            logger.error(">>> [THREAD] 发生异常: %s", e, exc_info=True)
            import traceback

            traceback.print_exc()
            self.error_signal.emit(f"加载失败: {str(e)}")


class DownloadThread(QThread):
    """异步数据下载的工作线程."""

    # 定义信号
    finished_signal = Signal(dict)  # 完成信号，传递结果字典
    error_signal = Signal(str)  # 错误信号，传递错误消息
    progress_signal = Signal(str)  # 进度信号，传递进度消息

    def __init__(self, data_center_service, download_type, start_date=None, parent=None):
        """初始化工作线程.

        Args:
            data_center_service: 数据中心服务实例
            download_type: 下载类型 ('full' 或 'incremental')
            start_date: 开始日期（仅增量下载需要）
            parent: 父对象
        """
        super().__init__(parent)
        self.data_center_service = data_center_service
        self.download_type = download_type
        self.start_date = start_date

    def run(self):
        """线程执行函数（在后台线程中运行）."""
        import logging

        logger = logging.getLogger(__name__)

        # 使用print确保能看到输出
        print(
            f">>> [DOWNLOAD THREAD] DownloadThread.run() 开始执行，类型: {self.download_type}",
            flush=True,
        )
        logger.info(">>> [DOWNLOAD THREAD] DownloadThread.run() 开始执行")

        try:
            print(">>> [DOWNLOAD THREAD] 发送进度信号...", flush=True)
            self.progress_signal.emit("正在准备下载...")

            # 在后台线程中执行耗时操作
            import time

            start_time = time.time()

            if self.download_type == "full":
                print(">>> [DOWNLOAD THREAD] 开始全量下载...", flush=True)
                result = self.data_center_service.start_full_download()
            else:
                print(
                    f">>> [DOWNLOAD THREAD] 开始增量下载，开始日期: {self.start_date}...",
                    flush=True,
                )
                result = self.data_center_service.start_incremental_download(self.start_date)

            elapsed = time.time() - start_time
            print(f">>> [DOWNLOAD THREAD] 下载完成，耗时: {elapsed:.2f}秒", flush=True)

            # 发送完成信号
            print(
                f">>> [DOWNLOAD THREAD] 发送完成信号: success={result.get('success')}", flush=True
            )
            self.finished_signal.emit(result)

            print(">>> [DOWNLOAD THREAD] DownloadThread.run() 执行完成", flush=True)

        except Exception as e:
            # 发送错误信号
            print(f">>> [DOWNLOAD THREAD] 发生异常: {e}", flush=True)
            logger.error(">>> [DOWNLOAD THREAD] 发生异常: %s", e, exc_info=True)
            import traceback

            traceback.print_exc()
            self.error_signal.emit(f"下载失败: {str(e)}")


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

        # 异步工作线程
        self.reload_thread: Optional[ReloadSymbolsThread] = None
        self.download_thread: Optional[DownloadThread] = None

        # 初始化UI控件引用
        self.tab_widget: Optional[QTabWidget] = None
        self.symbols_tab: Optional[QWidget] = None
        self.local_data_tab: Optional[QWidget] = None
        self.download_tab: Optional[QWidget] = None
        self.sources_tab: Optional[QWidget] = None

        # 品种列表选项卡控件
        self.exchange_combo: Optional[QComboBox] = None
        self.symbol_type_combo: Optional[QComboBox] = None
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

        # ⚠ 关键修复：在调用super().__init__之前先获取服务
        # 因为super().__init__会调用setup_ui()，而setup_ui()会调用_load_symbols_data()
        # 如果此时服务还没初始化，会导致错误
        try:
            self.data_center_service = self.service_manager.get_service("data_center_service")
        except Exception as e:
            import logging

            logging.getLogger(__name__).error("获取数据中心服务失败: %s", e)

        # 调用父类初始化
        super().__init__(parent, "数据中心")
        self.logger.info("数据中心界面初始化完成")

        # 检查服务状态并记录
        if self.data_center_service:
            self.logger.info("✓ 数据中心服务已就绪")
        else:
            self.logger.warning("⚠ 数据中心服务未注册")

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

        filter_row.addStretch()
        search_layout.addLayout(filter_row)

        layout.addWidget(search_group)

        # 品种列表组
        symbols_group = QGroupBox("品种列表")
        symbols_layout = QVBoxLayout(symbols_group)

        self.symbols_count_label = QLabel("共 0 个品种")
        symbols_layout.addWidget(self.symbols_count_label)

        # 添加提示标签
        hint_label = QLabel("💡 提示：点击上方【↻ 刷新品种】按钮加载品种列表")
        hint_label.setStyleSheet("color: #888; font-size: 12px; padding: 10px;")
        symbols_layout.addWidget(hint_label)

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

        # ⚠️ 修复：移除初始化时的自动加载，避免启动卡顿
        # 用户需要手动点击"刷新品种"按钮来加载数据
        # self._load_symbols_data()

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
        self.start_date_input.setDisplayFormat("yyyy-MM-dd")  # 设置日期显示格式
        self.start_date_input.setDate(QDate.currentDate().addMonths(-1))
        # 不设置按钮样式，使用默认的下拉按钮（会自动显示日历图标）
        query_layout.addRow("开始日期:", self.start_date_input)

        self.end_date_input = QDateEdit()
        self.end_date_input.setCalendarPopup(True)
        self.end_date_input.setDisplayFormat("yyyy-MM-dd")  # 设置日期显示格式
        self.end_date_input.setDate(QDate.currentDate())
        # 不设置按钮样式，使用默认的下拉按钮（会自动显示日历图标）
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

        # 创建单选框（在同一个父容器中会自动互斥）
        self.full_download_radio = QRadioButton("全量下载（全品类、全周期、固定长度历史数据）")
        self.full_download_radio.setChecked(True)
        mode_layout.addWidget(self.full_download_radio)

        self.custom_download_radio = QRadioButton("增量下载（自定义日期范围）")
        mode_layout.addWidget(self.custom_download_radio)

        # 创建 QButtonGroup 用于管理（但不影响界面显示）
        self.download_mode_group = QButtonGroup(self)
        self.download_mode_group.addButton(self.full_download_radio, 1)
        self.download_mode_group.addButton(self.custom_download_radio, 2)

        # 增量下载配置（缩进以显示层级关系）
        custom_config_layout = QVBoxLayout()
        custom_config_layout.setContentsMargins(30, 0, 0, 0)  # 左侧缩进

        date_layout = QFormLayout()
        self.download_start_date = QDateEdit()
        self.download_start_date.setCalendarPopup(True)
        self.download_start_date.setDisplayFormat("yyyy-MM-dd")  # 设置日期显示格式
        self.download_start_date.setDate(QDate.currentDate().addMonths(-3))
        # 不设置按钮样式，使用默认的下拉按钮（会自动显示日历图标）
        date_layout.addRow("开始日期:", self.download_start_date)

        self.download_end_date = QDateEdit()
        self.download_end_date.setCalendarPopup(True)
        self.download_end_date.setDisplayFormat("yyyy-MM-dd")  # 设置日期显示格式
        self.download_end_date.setDate(QDate.currentDate())
        # 不设置按钮样式，使用默认的下拉按钮（会自动显示日历图标）
        date_layout.addRow("结束日期:", self.download_end_date)

        custom_config_layout.addLayout(date_layout)
        mode_layout.addLayout(custom_config_layout)

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
        """重新加载品种（异步版本）."""
        try:
            self.logger.info("=" * 60)
            self.logger.info(">>> _reload_symbols() 被调用")
            self.logger.info("=" * 60)

            if not self.data_center_service:
                self.logger.error(">>> 数据中心服务未初始化")
                self.show_error("数据中心服务未初始化")
                return

            # 检查是否已有线程在运行
            if self.reload_thread and self.reload_thread.isRunning():
                self.logger.warning(">>> 已有线程在运行")
                self.show_warning("品种列表正在加载中，请稍候...")
                return

            # 创建工作线程
            self.logger.info(">>> 创建 ReloadSymbolsThread...")
            self.reload_thread = ReloadSymbolsThread(self.data_center_service, self)
            self.logger.info(">>> ReloadSymbolsThread 创建成功: %s", self.reload_thread)

            # 连接信号
            self.logger.info(">>> 连接信号...")
            self.reload_thread.finished_signal.connect(self._on_reload_finished)
            self.reload_thread.error_signal.connect(self._on_reload_error)
            self.reload_thread.progress_signal.connect(self.show_info)
            self.logger.info(">>> 信号连接完成")

            # 启动线程
            self.logger.info(">>> 启动线程...")
            self.reload_thread.start()
            self.logger.info(">>> 线程已启动，isRunning: %s", self.reload_thread.isRunning())

            # 显示加载提示
            self.show_info("正在重新加载品种列表...")
            self.logger.info(">>> _reload_symbols() 执行完成")

        except Exception as e:
            self.logger.error(">>> 启动重新加载失败: %s", e, exc_info=True)
            self.show_error(f"启动失败: {e}")

    def _on_reload_finished(self, result: Dict[str, Any]):
        """重新加载完成的回调（在UI线程中执行）.

        Args:
            result: reload_symbol_list的返回结果
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info(">>> _on_reload_finished() 被调用")
            self.logger.info(
                ">>> result: success=%s, count=%s",
                result.get("success"),
                result.get("symbol_count"),
            )
            self.logger.info("=" * 60)

            if result.get("success"):
                data = result.get("data", [])
                self.logger.info(">>> 获取到数据: %d个", len(data))
                self.all_symbols_data = data
                self.logger.info(">>> all_symbols_data已更新: %d个", len(self.all_symbols_data))

                self._apply_filters()
                self.logger.info(">>> _apply_filters()完成")

                # 显示加载成功信息
                self.show_info(f"成功加载 {result['symbol_count']} 个品种")

                # 如果有警告信息，显示警告
                if result.get("warning"):
                    self.show_warning(result["warning"])
            else:
                self.logger.error(">>> 加载失败: %s", result.get("message"))
                self.show_error(f"加载失败: {result.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error(">>> 处理加载结果失败: %s", e, exc_info=True)
            self.show_error(f"处理结果失败: {e}")

        finally:
            # 清理线程引用
            self.reload_thread = None
            self.logger.info(">>> _on_reload_finished() 执行完成")

    def _on_reload_error(self, error_message: str):
        """重新加载出错的回调（在UI线程中执行）.

        Args:
            error_message: 错误消息
        """
        self.logger.error("重新加载品种失败: %s", error_message)
        self.show_error(error_message)

        # 清理线程引用
        self.reload_thread = None

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

    def _on_search_text_changed(self, text: str):  # noqa: ARG002
        """搜索文本改变."""
        self._apply_filters()

    def _on_filter_changed(self, value: str):  # noqa: ARG002
        """筛选条件改变."""
        self._apply_filters()

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
        """开始下载（异步版本）."""
        try:
            self.logger.info("=" * 60)
            self.logger.info(">>> _start_download() 被调用")
            self.logger.info("=" * 60)

            if not self.data_center_service:
                self.logger.error(">>> 数据中心服务未初始化")
                self.show_error("数据中心服务未初始化")
                return

            # 检查是否已有线程在运行
            if self.download_thread and self.download_thread.isRunning():
                self.logger.warning(">>> 已有下载线程在运行")
                self.show_warning("下载任务正在进行中，请稍候...")
                return

            # 确定下载类型和参数
            if self.full_download_radio and self.full_download_radio.isChecked():
                download_type = "full"
                start_date = None
                self.logger.info(">>> 选择了全量下载")
            else:
                download_type = "incremental"
                if self.download_start_date:
                    qdate = self.download_start_date.date()
                    start_date = qdate.toString("yyyy-MM-dd")
                else:
                    start_date = datetime.now().strftime("%Y-%m-%d")
                self.logger.info(">>> 选择了增量下载，开始日期: %s", start_date)

            # 🔧 关键修复：提前生成并保存任务ID
            # 不等待下载完成回调，立即保存任务ID以便停止操作
            task_id = f"{download_type}_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.current_download_task_id = task_id
            self.logger.info(">>> 生成任务ID: %s", task_id)

            # 创建下载线程
            self.logger.info(">>> 创建 DownloadThread...")
            self.download_thread = DownloadThread(
                self.data_center_service, download_type, start_date, self
            )
            self.logger.info(">>> DownloadThread 创建成功: %s", self.download_thread)

            # 连接信号
            self.logger.info(">>> 连接信号...")
            self.download_thread.finished_signal.connect(self._on_download_finished)
            self.download_thread.error_signal.connect(self._on_download_error)
            self.download_thread.progress_signal.connect(self.show_info)
            self.logger.info(">>> 信号连接完成")

            # 启动线程
            self.logger.info(">>> 启动下载线程...")
            self.download_thread.start()
            self.logger.info(">>> 线程已启动，isRunning: %s", self.download_thread.isRunning())

            # 更新按钮状态
            if self.start_download_btn:
                self.start_download_btn.setEnabled(False)
            if self.pause_download_btn:
                self.pause_download_btn.setEnabled(True)
            if self.stop_download_btn:
                self.stop_download_btn.setEnabled(True)

            # 显示加载提示
            self.show_info(f"正在启动下载任务... (任务ID: {task_id})")
            self.logger.info(">>> _start_download() 执行完成")

        except Exception as e:
            self.logger.error(">>> 启动下载失败: %s", e, exc_info=True)
            self.show_error(f"启动失败: {e}")
            # 🔧 修复：确保异常情况下也清理状态
            self._reset_download_state()

    def _on_download_finished(self, result: Dict[str, Any]):
        """下载完成的回调（在UI线程中执行）.

        Args:
            result: 下载结果
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info(">>> _on_download_finished() 被调用")
            self.logger.info(">>> result: success=%s", result.get("success"))
            self.logger.info("=" * 60)

            if result.get("success"):
                task_id = result.get("task_id", self.current_download_task_id)
                self.show_info(f"下载任务已完成！任务ID: {task_id}")
                self.logger.info(">>> 下载任务完成成功: %s", task_id)
            else:
                self.logger.error(">>> 下载任务失败: %s", result.get("message"))
                self.show_error(f"下载失败: {result.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error(">>> 处理下载结果失败: %s", e, exc_info=True)
            self.show_error(f"处理结果失败: {e}")

        finally:
            # 🔧 修复：统一使用 _reset_download_state() 清理状态
            self._reset_download_state()
            self.logger.info(">>> _on_download_finished() 执行完成")

    def _on_download_error(self, error_message: str):
        """下载出错的回调（在UI线程中执行）.

        Args:
            error_message: 错误消息
        """
        self.logger.error("下载失败: %s", error_message)
        self.show_error(error_message)

        # 🔧 修复：统一使用 _reset_download_state() 清理状态
        self._reset_download_state()

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
        try:
            self.logger.info(">>> _stop_download() 被调用")

            # 🔧 修复：先尝试停止QThread线程
            thread_stopped = False
            if self.download_thread and self.download_thread.isRunning():
                self.logger.info(">>> 检测到运行中的下载线程，尝试终止...")
                try:
                    # 请求线程终止
                    self.download_thread.requestInterruption()
                    # 等待最多3秒
                    if self.download_thread.wait(3000):
                        self.logger.info(">>> 线程已正常终止")
                        thread_stopped = True
                    else:
                        # 强制终止（不推荐，但必要时使用）
                        self.logger.warning(">>> 线程未响应，强制终止...")
                        self.download_thread.terminate()
                        self.download_thread.wait(1000)
                        thread_stopped = True
                except Exception as thread_error:
                    self.logger.error(">>> 终止线程失败: %s", thread_error)

            # 🔧 修复：再尝试通过后端服务停止任务
            backend_stopped = False
            if self.data_center_service and hasattr(self, "current_download_task_id"):
                self.logger.info(">>> 尝试通过后端服务停止任务: %s", self.current_download_task_id)
                try:
                    result = self.data_center_service.stop_download(self.current_download_task_id)
                    if result.get("success"):
                        self.logger.info(">>> 后端任务停止成功")
                        backend_stopped = True
                    else:
                        self.logger.warning(">>> 后端任务停止失败: %s", result.get("message"))
                except Exception as backend_error:
                    self.logger.error(">>> 后端停止任务异常: %s", backend_error)

            # 🔧 修复：无论如何都清理状态和恢复按钮
            self._reset_download_state()

            # 显示结果
            if thread_stopped or backend_stopped:
                self.show_info("下载已停止")
            else:
                self.show_warning("下载任务已终止（状态已清理）")

            self.logger.info(">>> _stop_download() 执行完成")

        except Exception as e:
            self.logger.error(">>> 停止下载失败: %s", e, exc_info=True)
            # 🔧 修复：即使出错也要清理状态
            self._reset_download_state()
            self.show_error(f"停止操作出错，但状态已清理: {e}")

    def _toggle_detail_progress(self, checked: bool):  # noqa: U101
        """切换详细进度显示."""
        if self.detail_progress_table:
            self.detail_progress_table.setVisible(checked)

    def _reset_download_state(self):
        """重置下载状态（清理线程、任务ID、恢复按钮）.

        这个方法用于清理所有下载相关的状态，确保UI能恢复到可用状态。
        适用场景：
        1. 下载完成后
        2. 下载出错后
        3. 强制停止下载后
        4. 任何需要清理状态的情况
        """
        try:
            self.logger.info(">>> _reset_download_state() 开始清理状态...")

            # 清理线程引用
            if self.download_thread:
                self.logger.info(">>> 清理下载线程引用")
                # 如果线程还在运行，尝试断开信号连接
                try:
                    if self.download_thread.isRunning():
                        self.download_thread.finished_signal.disconnect()
                        self.download_thread.error_signal.disconnect()
                        self.download_thread.progress_signal.disconnect()
                except Exception:
                    pass  # 忽略断开信号的错误

                self.download_thread = None

            # 清理任务ID
            if hasattr(self, "current_download_task_id"):
                self.logger.info(">>> 清理任务ID: %s", self.current_download_task_id)
                delattr(self, "current_download_task_id")

            # 恢复按钮状态
            if self.start_download_btn:
                self.start_download_btn.setEnabled(True)
            if self.pause_download_btn:
                self.pause_download_btn.setEnabled(False)
                # 重置暂停按钮文本和连接
                self.pause_download_btn.setText("暂停")
                try:
                    self.pause_download_btn.clicked.disconnect()
                except Exception:
                    pass
                self.pause_download_btn.clicked.connect(self._pause_download)
            if self.stop_download_btn:
                self.stop_download_btn.setEnabled(False)

            # 重置进度显示
            if self.download_progress:
                self.download_progress.setValue(0)
            if self.progress_label:
                self.progress_label.setText("准备就绪")

            self.logger.info(">>> _reset_download_state() 状态清理完成")

        except Exception as e:
            self.logger.error(">>> 重置下载状态失败: %s", e, exc_info=True)

    # ==================== 数据源管理事件处理 ====================

    def _load_data_sources(self):
        """加载数据源列表."""
        try:
            if not self.data_center_service:
                return

            # 获取数据源状态
            result = self.data_center_service.get_all_datafeed_status()

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
                            lambda _checked, sid=source_id, conn=connected: (  # noqa: ARG005
                                self._toggle_source_connection(sid, conn)
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
