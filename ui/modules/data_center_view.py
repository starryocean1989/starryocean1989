# -*- coding: utf-8 -*-
"""数据中心界面 - 主视图（重构版）.

标准架构：4个子界面采用选项卡形式。
合并tabs/handlers/utils逻辑，统一backend调用。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDate, QThread, QTimer, Signal, Qt, QStringListModel
from PySide6.QtWidgets import QCompleter
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.core.base import get_service_manager, get_event_engine
from backend.core.service_base import LoggerMixin
from backend.services.database_adapter import get_db_manager
from ui.shared_widgets.base_widget import BaseWidget

# vnpy事件相关
from vnpy.event import Event

# 事件类型常量（与backend保持一致）
EVENT_CHINASTOCK_DOWNLOAD = "eChinaStockDownload"
EVENT_DATA_QUALITY_UPDATE = "eDataQualityUpdate"  # 数据质量更新事件
EVENT_DATA_SCAN_COMPLETE = "eDataScanComplete"  # 扫描完成事件

# ==================== 常量定义 ====================

EXCHANGES = ["全部", "上交所", "深交所", "北交所"]
SYMBOL_TYPES = ["全部", "股票", "基金", "可转债"]
PAGE_SIZE_OPTIONS = ["20", "50", "100", "200"]

SYMBOLS_TABLE_HEADERS = ["品种代码", "品种名称", "交易所", "类型", "状态"]
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

    def __init__(self, data_center_service, start_date, parent=None):
        """初始化工作线程.

        Args:
            data_center_service: 数据中心服务实例
            start_date: 开始日期（增量下载）
            parent: 父对象
        """
        super().__init__(parent)
        self.data_center_service = data_center_service
        self.start_date = start_date

    def run(self):
        """线程执行函数（在后台线程中运行）."""
        import logging
        from datetime import datetime

        logger = logging.getLogger(__name__)

        # 使用print确保能看到输出
        print(
            ">>> [DOWNLOAD THREAD] DownloadThread.run() 开始执行",
            flush=True,
        )
        print(
            f">>> [DOWNLOAD THREAD] 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            flush=True,
        )
        print(
            f">>> [DOWNLOAD THREAD] 开始日期: {self.start_date}",
            flush=True,
        )
        logger.info(">>> [DOWNLOAD THREAD] DownloadThread.run() 开始执行")

        try:
            # 🆕 记录开始时间（用于历史记录）
            self.start_time = datetime.now()

            print(">>> [DOWNLOAD THREAD] 发送进度信号...", flush=True)
            self.progress_signal.emit("正在准备下载...")

            # 在后台线程中执行耗时操作
            import time

            start_time = time.time()

            try:
                print(
                    ">>> [DOWNLOAD THREAD] 调用后端服务开始增量下载...",
                    flush=True,
                )
                print(
                    f">>> [DOWNLOAD THREAD] 调用时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    flush=True,
                )
                # 优先调用带进度的新方法；不存在则回退旧方法
                if hasattr(self.data_center_service, "start_incremental_download_with_progress"):

                    def _cb(percent, message):
                        try:
                            self.progress_signal.emit(str(message))
                        except Exception:
                            pass

                    print(
                        ">>> [DOWNLOAD THREAD] 调用 start_incremental_download_with_progress()",
                        flush=True,
                    )
                    result = self.data_center_service.start_incremental_download_with_progress(
                        self.start_date, _cb
                    )
                    print(
                        ">>> [DOWNLOAD THREAD] start_incremental_download_with_progress() 返回",
                        flush=True,
                    )
                else:
                    print(
                        ">>> [DOWNLOAD THREAD] 调用 start_incremental_download()",
                        flush=True,
                    )
                    result = self.data_center_service.start_incremental_download(self.start_date)
            except Exception as download_error:
                logger.error("下载过程异常: %s", download_error, exc_info=True)
                print(f">>> [DOWNLOAD THREAD] 下载异常: {download_error}", flush=True)
                self.error_signal.emit(f"下载失败: {str(download_error)}")
                return

            elapsed = time.time() - start_time

            # 🆕 记录耗时（用于历史记录）
            self.duration = elapsed

            print(
                ">>> [DOWNLOAD THREAD] 后端服务调用完成",
                flush=True,
            )
            print(
                f">>> [DOWNLOAD THREAD] 完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                flush=True,
            )
            print(
                f">>> [DOWNLOAD THREAD] 总耗时: {elapsed:.2f}秒",
                flush=True,
            )
            print(
                f">>> [DOWNLOAD THREAD] 返回结果: {result}",
                flush=True,
            )

            # 检查是否过快完成（可能有问题）
            if elapsed < 5.0:
                print(
                    f"⚠️ [DOWNLOAD THREAD] 警告: 下载在{elapsed:.2f}秒内完成，可能存在问题！",
                    flush=True,
                )
                logger.warning(f"下载过快完成（{elapsed:.2f}秒），请检查是否正常")

            # 发送完成信号
            print(
                f">>> [DOWNLOAD THREAD] 发送完成信号: success={result.get('success')}", flush=True
            )

            try:
                self.finished_signal.emit(result)
                print(">>> [DOWNLOAD THREAD] 完成信号已发送", flush=True)
            except Exception as signal_err:
                print(f">>> [DOWNLOAD THREAD] 发送完成信号失败: {signal_err}", flush=True)
                logger.error("发送完成信号失败: %s", signal_err, exc_info=True)

            print(">>> [DOWNLOAD THREAD] DownloadThread.run() 执行完成", flush=True)

        except Exception as e:
            # 发送错误信号
            print(f">>> [DOWNLOAD THREAD] 发生异常: {e}", flush=True)
            logger.error(">>> [DOWNLOAD THREAD] 发生异常: %s", e, exc_info=True)
            import traceback

            traceback.print_exc()

            # 确保信号发送成功
            try:
                self.error_signal.emit(f"下载失败: {str(e)}")
            except Exception as signal_err:
                print(f">>> [DOWNLOAD THREAD] 发送错误信号失败: {signal_err}", flush=True)
                logger.error("发送错误信号失败: %s", signal_err)


class DataCenter(BaseWidget, LoggerMixin):
    """数据中心主界面（重构版）."""

    def __init__(self, parent=None):
        """初始化数据中心界面."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.data_center_service = None
        self.db_manager = get_db_manager()  # 🆕 数据库管理器

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

        # 🔧 进度轮询定时器（备用）
        self.progress_timer: Optional[QTimer] = None

        # 🔧 vnpy事件引擎
        self.event_engine = None

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
        self.symbol_loading_progress: Optional[QProgressBar] = None  # 🔧 品种加载进度条

        # 本地数据选项卡控件
        self.missing_symbol_warning: Optional[QLabel] = None  # 🔧 品种缺失警告
        self.symbol_input: Optional[QLineEdit] = None
        self.symbol_input_status_label: Optional[QLabel] = None  # 🆕 品种索引加载状态提示
        self.interval_combo: Optional[QComboBox] = None  # 周期选择框
        self.start_date_input: Optional[QDateEdit] = None
        self.end_date_input: Optional[QDateEdit] = None
        self.data_table: Optional[QTableWidget] = None
        self.data_status_label: Optional[QLabel] = None
        self.data_quality_label: Optional[QLabel] = None
        self.repair_data_btn: Optional[QPushButton] = None  # 🔧 数据修复按钮
        self.current_queried_symbol: Optional[str] = None  # 🔧 当前查询的品种（用于修复）

        # 品种智能联想相关
        self.symbol_cache: List[Dict[str, Any]] = []  # 品种缓存（用于品种列表搜索框的拼音匹配）
        self.local_data_cache: List[Dict[str, Any]] = []  # 本地数据索引（用于本地数据搜索框联想）
        self.symbol_completer: Optional[QCompleter] = None  # 本地数据搜索框自动补全器
        # 注意：品种列表搜索框不再使用QCompleter，搜索直接触发品种列表过滤

        # 🆕 质量概览控件
        self.quality_overview_widget: Optional[QWidget] = None
        self.total_symbols_label: Optional[QLabel] = None
        self.downloaded_symbols_label: Optional[QLabel] = None  # 🚀 新增
        self.missing_symbols_label: Optional[QLabel] = None
        self.error_symbols_label: Optional[QLabel] = None
        self.warning_symbols_label: Optional[QLabel] = None
        self.quality_score_label: Optional[QLabel] = None
        self.toggle_quality_detail_btn: Optional[QPushButton] = None
        self.quality_detail_table: Optional[QTableWidget] = None

        # 数据下载选项卡控件
        self.download_symbols_input: Optional[QLineEdit] = None
        self.download_start_date: Optional[QDateEdit] = None
        self.download_progress: Optional[QProgressBar] = None
        self.progress_label: Optional[QLabel] = None
        self.progress_text: Optional[QPlainTextEdit] = (
            None  # 🆕 进度文本日志框（使用QPlainTextEdit避免递归重绘）
        )
        self.start_download_btn: Optional[QPushButton] = None
        self.pause_download_btn: Optional[QPushButton] = None
        self.stop_download_btn: Optional[QPushButton] = None
        self.server_status_label: Optional[QLabel] = None  # 🔧 服务器状态显示

        # 下载历史相关
        self.download_history: List[Dict[str, Any]] = []  # 下载历史列表
        self.history_tab_widget: Optional[QTabWidget] = None  # 历史选项卡组件
        self.max_history_records = 20  # 最多保留20条历史
        self._progress_text_buffer: List[str] = []  # 进度文本缓冲区（用于批量更新）
        self._progress_update_timer: Optional[QTimer] = None  # 进度更新定时器

        # 数据源管理选项卡控件
        self.sources_table: Optional[QTableWidget] = None
        self.config_status_label: Optional[QLabel] = None
        self.monitor_text: Optional[QTextEdit] = None
        self.polling_gateway_config: Optional[Dict[str, Any]] = None  # 🔧 轮询网关配置
        self.virtual_gateway_config: Optional[Dict[str, Any]] = None  # 🔧 虚拟网关配置

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

        # 🔧 注册vnpy事件监听器
        self._register_event_handlers()

        # 🆕 延迟加载质量概览（给服务和后台扫描留出初始化时间）
        # 使用5秒延迟，确保：
        # 1. data_center_service完全初始化
        # 2. china_stock_engine可用
        # 3. 后台数据扫描有机会完成
        if self.data_center_service:
            QTimer.singleShot(5000, self._load_quality_overview_with_retry)

        # 🆕 延迟加载品种缓存用于品种列表搜索框的拼音匹配
        QTimer.singleShot(2000, self._load_symbol_cache_for_autocomplete)

        # 🆕 本地数据索引加载策略：优先使用后台数据质量扫描的结果（推送事件），超时后才启动后备方案
        # 后备方案延迟15秒启动（给数据质量扫描留出时间，通常5-10秒完成）
        self._local_data_index_loaded = False  # 标记是否已加载
        QTimer.singleShot(15000, self._load_local_data_index_fallback)

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

        # 🔧 调整顺序：数据下载提到本地数据前面
        # 2.2 数据下载子界面
        self.download_tab = self._create_download_tab()
        if self.download_tab:
            self.tab_widget.addTab(self.download_tab, "⬇️ 数据下载")

        # 2.3 本地数据子界面
        self.local_data_tab = self._create_local_data_tab()
        if self.local_data_tab:
            self.tab_widget.addTab(self.local_data_tab, "💾 本地数据")

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
        refresh_btn.setToolTip("从本地缓存刷新品种列表（带日期验证）")
        refresh_btn.clicked.connect(self._refresh_symbols)
        toolbar_layout.addWidget(refresh_btn)

        # 注：删除品种列表按钮已移除（缓存管理已自动化，次日0时自动失效）

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

        # 搜索框（直接联动品种列表过滤，不使用QCompleter）
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入代码/名称/拼音首字母...")
        self.search_input.setToolTip(
            "搜索框直接联动品种列表过滤\n"
            "支持：代码、名称、拼音首字母匹配\n"
            "品种列表本身就是联想结果"
        )

        # 搜索框直接触发品种列表过滤，不使用QCompleter
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

        # 添加品种加载进度条（默认隐藏）
        self.symbol_loading_progress = QProgressBar()
        self.symbol_loading_progress.setRange(0, 0)  # 不确定进度模式
        self.symbol_loading_progress.setTextVisible(True)
        self.symbol_loading_progress.setFormat("正在加载品种列表，请稍候...")
        self.symbol_loading_progress.setVisible(False)
        symbols_layout.addWidget(self.symbol_loading_progress)

        # 添加提示标签
        hint_label = QLabel("💡 提示：点击上方【↻ 刷新品种】按钮加载品种列表")
        hint_label.setStyleSheet("color: #888; font-size: 12px; padding: 10px;")
        symbols_layout.addWidget(hint_label)

        self.symbols_table = QTableWidget(0, 5)
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

        # 🔧 新增：品种缺失警告区域（默认隐藏）
        self.missing_symbol_warning = QLabel()
        self.missing_symbol_warning.setStyleSheet(
            "background-color: #FFF3CD; color: #856404; padding: 10px; "
            "border: 1px solid #FFEEBA; border-radius: 5px;"
        )
        self.missing_symbol_warning.setVisible(False)
        self.missing_symbol_warning.setWordWrap(True)
        layout.addWidget(self.missing_symbol_warning)

        # 查询组
        query_group = QGroupBox("本地数据查询")
        query_layout = QFormLayout(query_group)

        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText(
            "输入代码/名称/拼音首字母，如: 600000 / 浦发银行 / pfyh"
        )
        self.symbol_input.textChanged.connect(self._on_symbol_input_changed)

        # 创建自动补全器
        self.symbol_completer = QCompleter()
        self.symbol_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.symbol_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.symbol_input.setCompleter(self.symbol_completer)

        query_layout.addRow("品种代码:", self.symbol_input)

        # 🆕 品种索引加载状态提示
        self.symbol_input_status_label = QLabel("⏳ 正在加载品种索引...")
        self.symbol_input_status_label.setStyleSheet(
            "color: #999; font-size: 11px; padding-left: 5px;"
        )
        self.symbol_input_status_label.setWordWrap(True)
        query_layout.addRow("", self.symbol_input_status_label)

        # 周期选择框
        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["1day", "5min", "1min"])
        self.interval_combo.setCurrentText("1day")
        query_layout.addRow("K线周期:", self.interval_combo)

        self.start_date_input = QDateEdit()
        self.start_date_input.setCalendarPopup(True)
        self.start_date_input.setDisplayFormat("yyyy-MM-dd")  # 设置日期显示格式
        self.start_date_input.setDate(QDate.currentDate().addMonths(-1))
        self.start_date_input.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        query_layout.addRow("开始日期:", self.start_date_input)

        self.end_date_input = QDateEdit()
        self.end_date_input.setCalendarPopup(True)
        self.end_date_input.setDisplayFormat("yyyy-MM-dd")  # 设置日期显示格式
        self.end_date_input.setDate(QDate.currentDate())
        self.end_date_input.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        query_layout.addRow("结束日期:", self.end_date_input)

        query_btn = QPushButton("查询")
        query_btn.clicked.connect(self._query_local_data)
        query_layout.addRow("", query_btn)

        # 🆕 数据质量概览组（自动感知）
        quality_overview_group = QGroupBox()
        quality_overview_layout = QVBoxLayout(quality_overview_group)

        # 🆕 添加标题栏（包含状态指示器）
        quality_overview_header = QHBoxLayout()
        header_label = QLabel("📊 数据质量概览（自动感知）")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        quality_overview_header.addWidget(header_label)

        # 🆕 状态指示器（转圈图标）
        self.quality_scan_status_label = QLabel("⏸️")  # 初始状态：待机
        self.quality_scan_status_label.setToolTip("数据质量感知状态：待机")
        self.quality_scan_status_label.setStyleSheet("font-size: 14px; color: #999;")
        quality_overview_header.addWidget(self.quality_scan_status_label)
        quality_overview_header.addStretch()

        quality_overview_layout.addLayout(quality_overview_header)

        # 🚀 添加说明提示
        hint_label = QLabel(
            "💡 说明：「总品种」=品种缓存总数（5724个已过滤品种），「已下载」=本地有数据的品种数，"
            "「缺失」=缓存中有但本地无数据，「警告」=已下载但数据不完整，「过时」=数据未更新到最新交易日的品种数"
        )
        hint_label.setStyleSheet("color: #666; font-size: 11px; padding: 5px;")
        hint_label.setWordWrap(True)
        quality_overview_layout.addWidget(hint_label)

        # 质量概览卡片（紧凑显示）
        self.quality_overview_widget = QWidget()
        overview_layout = QHBoxLayout(self.quality_overview_widget)
        overview_layout.setContentsMargins(5, 5, 5, 5)

        # 总品种数（品种缓存）
        self.total_symbols_label = QLabel("总品种: 正在扫描...")
        self.total_symbols_label.setToolTip("品种缓存中的品种总数（5724个已过滤品种）")
        self.total_symbols_label.setStyleSheet("color: #999;")
        overview_layout.addWidget(self.total_symbols_label)

        # 🆕 已下载品种数
        self.downloaded_symbols_label = QLabel("已下载: 正在扫描...")
        self.downloaded_symbols_label.setStyleSheet("color: #999;")
        self.downloaded_symbols_label.setToolTip("本地已下载数据的品种数")
        overview_layout.addWidget(self.downloaded_symbols_label)

        # 缺失品种
        self.missing_symbols_label = QLabel("缺失: 正在扫描...")
        self.missing_symbols_label.setStyleSheet("color: #999;")
        self.missing_symbols_label.setToolTip("品种列表中有但本地完全无数据的品种数")
        overview_layout.addWidget(self.missing_symbols_label)

        # 错误品种
        self.error_symbols_label = QLabel("错误: 正在扫描...")
        self.error_symbols_label.setStyleSheet("color: #999;")
        overview_layout.addWidget(self.error_symbols_label)

        # 警告品种
        self.warning_symbols_label = QLabel("警告: 正在扫描...")
        self.warning_symbols_label.setStyleSheet("color: #999;")
        overview_layout.addWidget(self.warning_symbols_label)

        # 🆕 过时品种（数据未更新到最新交易日）
        self.outdated_symbols_label = QLabel("过时: 正在扫描...")
        self.outdated_symbols_label.setStyleSheet("color: #999;")
        self.outdated_symbols_label.setToolTip("数据未更新到最新交易日的品种数")
        overview_layout.addWidget(self.outdated_symbols_label)

        # 🆕 平均滞后天数
        self.avg_gap_label = QLabel("平均滞后: 正在扫描...")
        self.avg_gap_label.setStyleSheet("color: #999;")
        self.avg_gap_label.setToolTip("所有已下载品种的平均滞后天数（交易日）")
        overview_layout.addWidget(self.avg_gap_label)

        # 质量评分
        self.quality_score_label = QLabel("评分: 正在扫描...")
        self.quality_score_label.setStyleSheet("color: #999;")
        overview_layout.addWidget(self.quality_score_label)

        # 刷新按钮
        refresh_quality_btn = QPushButton("🔄")
        refresh_quality_btn.setToolTip("手动刷新数据质量概览")
        refresh_quality_btn.setMaximumWidth(40)
        refresh_quality_btn.clicked.connect(self._refresh_quality_overview)
        overview_layout.addWidget(refresh_quality_btn)

        overview_layout.addStretch()
        quality_overview_layout.addWidget(self.quality_overview_widget)

        # 详情展开按钮
        self.toggle_quality_detail_btn = QPushButton("显示详细信息")
        self.toggle_quality_detail_btn.setCheckable(True)
        self.toggle_quality_detail_btn.toggled.connect(self._toggle_quality_detail)
        quality_overview_layout.addWidget(self.toggle_quality_detail_btn)

        # 详细质量表格（默认隐藏）
        self.quality_detail_table = QTableWidget(0, 4)
        self.quality_detail_table.setHorizontalHeaderLabels(
            ["品种代码", "状态", "质量评分", "问题描述"]
        )
        quality_detail_header = self.quality_detail_table.horizontalHeader()
        quality_detail_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.quality_detail_table.setVisible(False)
        self.quality_detail_table.setMaximumHeight(200)
        quality_overview_layout.addWidget(self.quality_detail_table)

        # 状态栏组
        status_group = QGroupBox("本地数据状态")
        status_layout = QVBoxLayout(status_group)

        self.data_status_label = QLabel("等待质量概览加载...")
        status_layout.addWidget(self.data_status_label)

        self.data_quality_label = QLabel("全局质量评分: --")
        status_layout.addWidget(self.data_quality_label)

        # 🔧 修复数据按钮（默认隐藏，基于全局质量问题显示）
        self.repair_data_btn = QPushButton("🔧 修复数据")
        self.repair_data_btn.setVisible(False)
        self.repair_data_btn.clicked.connect(self._repair_data)
        self.repair_data_btn.setToolTip("自动修复全局数据质量问题")
        status_layout.addWidget(self.repair_data_btn)

        # 数据展示组
        data_group = QGroupBox("数据展示")
        data_layout = QVBoxLayout(data_group)

        self.data_table = QTableWidget(0, 7)
        self.data_table.setHorizontalHeaderLabels(LOCAL_DATA_TABLE_HEADERS)
        header = self.data_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        data_layout.addWidget(self.data_table)

        # 🎨 新布局结构：上下两部分
        # 上部分：左右分栏
        top_layout = QHBoxLayout()

        # 左栏：查询组件
        top_layout.addWidget(query_group, stretch=1)

        # 右栏：质量概览 + 本地状态
        right_layout = QVBoxLayout()
        right_layout.addWidget(quality_overview_group)
        right_layout.addWidget(status_group)
        right_layout.addStretch()
        top_layout.addLayout(right_layout, stretch=1)

        layout.addLayout(top_layout)

        # 下部分：数据展示（全宽）
        layout.addWidget(data_group)

        return tab

    # ==================== 数据下载子界面 ====================

    def _create_download_tab(self) -> QWidget:
        """创建数据下载子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 下载配置组（仅增量下载）
        config_group = QGroupBox("增量下载配置")
        config_layout = QFormLayout(config_group)

        # 添加说明标签
        info_label = QLabel("📊 增量下载：下载指定日期范围的历史数据（最多支持最近100天）")
        info_label.setStyleSheet("color: #666; padding: 5px;")
        config_layout.addRow(info_label)

        # 日期选择器
        self.download_start_date = QDateEdit()
        self.download_start_date.setCalendarPopup(True)
        self.download_start_date.setDisplayFormat("yyyy-MM-dd")
        self.download_start_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)

        # 设置日期范围：最多最近100天
        min_date = QDate.currentDate().addDays(-100)
        max_date = QDate.currentDate()
        self.download_start_date.setMinimumDate(min_date)
        self.download_start_date.setMaximumDate(max_date)
        self.download_start_date.setDate(QDate.currentDate().addDays(-30))  # 默认最近30天

        # 连接日期变更信号，验证100天限制
        self.download_start_date.dateChanged.connect(self._validate_date_range)

        config_layout.addRow("开始日期:", self.download_start_date)

        # 添加提示标签
        hint_label = QLabel("💡 数据将从开始日期下载至今天")
        hint_label.setStyleSheet("color: #888; font-size: 11px;")
        config_layout.addRow(hint_label)

        layout.addWidget(config_group)

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

        # 添加服务器状态显示
        self.server_status_label = QLabel("可用服务器: 检测中...")
        self.server_status_label.setStyleSheet(
            "color: #0066cc; font-weight: bold; padding: 8px; "
            "background-color: #f0f8ff; border-radius: 4px;"
        )
        self.server_status_label.setToolTip("服务器池状态（自动更新）")
        control_layout.addWidget(self.server_status_label)

        layout.addWidget(control_group)

        # 进度组（简化版：只保留文本日志）
        progress_group = QGroupBox("下载进度")
        progress_layout = QVBoxLayout(progress_group)

        # 创建但隐藏progress_label和download_progress（保持代码兼容性）
        self.progress_label = QLabel("准备就绪")
        self.progress_label.setVisible(False)  # 隐藏

        self.download_progress = QProgressBar()
        self.download_progress.setTextVisible(True)
        self.download_progress.setFormat("%p% (%v/%m)")
        self.download_progress.setVisible(False)  # 隐藏

        # 🆕 文本日志框（使用QPlainTextEdit避免递归重绘，唯一显示的进度组件）
        self.progress_text = QPlainTextEdit()
        self.progress_text.setReadOnly(True)
        self.progress_text.setMinimumHeight(200)  # 增加高度，因为是唯一的进度组件
        self.progress_text.setMaximumBlockCount(1000)  # 自动限制最大行数
        self.progress_text.setStyleSheet(
            "QPlainTextEdit { "
            "  font-family: 'Consolas', 'Courier New', monospace; "
            "  font-size: 11pt; "
            "  color: #e0e0e0; "  # 浅灰色字体
            "  background-color: #1e1e1e; "  # 深色背景（VS Code风格）
            "  border: 1px solid #3c3c3c; "
            "  padding: 8px; "
            "  selection-background-color: #264f78; "  # 选中背景色
            "}"
        )
        self.progress_text.setPlaceholderText("下载进度将显示在这里...")
        progress_layout.addWidget(self.progress_text)

        # 🆕 左右分栏容器：左侧进度，右侧历史
        history_container = QWidget()
        history_layout = QHBoxLayout(history_container)
        history_layout.setSpacing(10)

        # 左侧：当前下载进度（压缩宽度）
        progress_group.setMaximumWidth(600)
        history_layout.addWidget(progress_group)

        # 右侧：下载历史
        history_group = self._create_download_history_group()
        history_layout.addWidget(history_group, stretch=1)

        layout.addWidget(history_container)

        return tab

    def _create_download_history_group(self) -> QGroupBox:
        """创建下载历史组件."""
        history_group = QGroupBox("下载历史")
        history_layout = QVBoxLayout(history_group)

        # 提示标签
        hint_label = QLabel("💡 最多保留20条历史记录")
        hint_label.setStyleSheet("color: #888; font-size: 11px;")
        history_layout.addWidget(hint_label)

        # 历史记录选项卡
        self.history_tab_widget = QTabWidget()
        self.history_tab_widget.setTabsClosable(True)
        self.history_tab_widget.tabCloseRequested.connect(self._on_delete_history)
        self.history_tab_widget.setMovable(False)

        # 设置样式
        self.history_tab_widget.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid #3c3c3c;
                background-color: #2d2d2d;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #e0e0e0;
                padding: 8px 12px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #4a4a4a;
            }
            QTabBar::tab:hover {
                background-color: #505050;
            }
        """
        )

        # 初始提示（无历史记录时显示）
        if not self.download_history:
            empty_widget = QWidget()
            empty_layout = QVBoxLayout(empty_widget)
            empty_label = QLabel("暂无下载历史")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #666; font-size: 13px; padding: 50px;")
            empty_layout.addWidget(empty_label)
            self.history_tab_widget.addTab(empty_widget, "空")
            self.history_tab_widget.setTabEnabled(0, False)

        history_layout.addWidget(self.history_tab_widget)

        # 🆕 从数据库加载历史记录
        QTimer.singleShot(500, self._load_download_history_from_database)

        return history_group

    def _create_history_detail_widget(self, record: Dict[str, Any]) -> QWidget:
        """创建历史记录详情组件.

        Args:
            record: 历史记录字典

        Returns:
            QWidget: 历史详情组件
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        # 基本信息卡片
        info_group = QGroupBox("基本信息")
        info_layout = QFormLayout(info_group)

        info_layout.addRow("任务ID:", QLabel(record.get("task_id", "N/A")))

        start_time = record.get("start_time")
        if isinstance(start_time, datetime):
            info_layout.addRow("开始时间:", QLabel(start_time.strftime("%Y-%m-%d %H:%M:%S")))
        else:
            info_layout.addRow("开始时间:", QLabel(str(start_time)))

        end_time = record.get("end_time")
        if isinstance(end_time, datetime):
            info_layout.addRow("结束时间:", QLabel(end_time.strftime("%Y-%m-%d %H:%M:%S")))
        else:
            info_layout.addRow("结束时间:", QLabel(str(end_time)))

        duration = record.get("duration", 0)
        info_layout.addRow("总耗时:", QLabel(f"{duration:.1f} 秒"))

        # 状态显示（带颜色）
        status = record.get("status", "unknown")
        status_label = QLabel(status)
        if status == "success":
            status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            status_label.setText("成功")
        elif status == "failed":
            status_label.setStyleSheet("color: #F44336; font-weight: bold;")
            status_label.setText("失败")
        else:
            status_label.setStyleSheet("color: #FF9800; font-weight: bold;")
            status_label.setText("未知")
        info_layout.addRow("状态:", status_label)

        layout.addWidget(info_group)

        # 统计信息卡片
        stats_group = QGroupBox("下载统计")
        stats_layout = QFormLayout(stats_group)

        total_tasks = record.get("total_tasks", 0)
        completed_tasks = record.get("completed_tasks", 0)
        success_count = record.get("success_count", 0)
        failed_count = record.get("failed_count", 0)
        skipped_count = record.get("skipped_count", 0)

        stats_layout.addRow("总任务数:", QLabel(str(total_tasks)))
        stats_layout.addRow("完成任务:", QLabel(str(completed_tasks)))
        stats_layout.addRow("成功数量:", QLabel(f"{success_count} ✓"))
        stats_layout.addRow("失败数量:", QLabel(f"{failed_count} ✗"))
        stats_layout.addRow("跳过数量:", QLabel(f"{skipped_count} ⊘"))

        # 成功率
        if total_tasks > 0:
            success_rate = success_count / total_tasks * 100
            stats_layout.addRow("成功率:", QLabel(f"{success_rate:.1f}%"))
        else:
            stats_layout.addRow("成功率:", QLabel("N/A"))

        layout.addWidget(stats_group)

        layout.addStretch()

        return widget

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
        """重新加载品种（异步版本）.

        注意：此方法用于从服务器重新获取品种列表，无需检查缓存是否存在。
        即使缓存被删除，也可以通过此方法重新获取数据。
        """
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
            # 🚀 关键修复：使用Qt.ConnectionType.QueuedConnection确保跨线程信号安全
            self.reload_thread.finished_signal.connect(
                self._on_reload_finished, Qt.ConnectionType.QueuedConnection
            )
            self.reload_thread.error_signal.connect(
                self._on_reload_error, Qt.ConnectionType.QueuedConnection
            )
            self.reload_thread.progress_signal.connect(
                self.show_info, Qt.ConnectionType.QueuedConnection
            )
            self.logger.info(">>> 信号连接完成")

            # 启动线程
            self.logger.info(">>> 启动线程...")
            self.reload_thread.start()
            self.logger.info(">>> 线程已启动，isRunning: %s", self.reload_thread.isRunning())

            # 显示加载进度条
            if self.symbol_loading_progress:
                self.symbol_loading_progress.setVisible(True)

            # 显示加载提示
            self.show_info("正在重新加载品种列表，请稍候...")
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

            # 隐藏加载进度条
            if self.symbol_loading_progress:
                self.symbol_loading_progress.setVisible(False)

            if result.get("success"):
                data = result.get("data", [])
                self.logger.info(">>> 获取到数据: %d个", len(data))
                self.all_symbols_data = data
                self.logger.info(">>> all_symbols_data已更新: %d个", len(self.all_symbols_data))

                # 🔧 关键：重新加载品种后立即更新联想缓存
                self._load_symbol_cache_for_autocomplete()
                self.logger.info(">>> 品种联想缓存已更新")

                self._apply_filters()
                self.logger.info(">>> _apply_filters()完成")

                # 显示加载成功信息（带后台过滤提示）
                if result.get("filtering_in_background"):
                    self.show_info(
                        f"✅ 成功加载 {result['symbol_count']} 个品种\n"
                        f"💡 正在后台过滤未上市品种，完成后将自动更新..."
                    )
                else:
                    self.show_info(f"✅ 成功加载 {result['symbol_count']} 个品种")

                # 检查空品种类别并弹窗提醒
                empty_categories = result.get("empty_categories", [])
                if empty_categories:
                    self._show_empty_categories_warning(empty_categories)

                # 如果有其他警告信息，显示警告
                if result.get("warning"):
                    self.show_warning(result["warning"])
            else:
                self.logger.error(">>> 加载失败: %s", result.get("message"))
                self.show_error(f"加载失败: {result.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error(">>> 处理加载结果失败: %s", e, exc_info=True)
            self.show_error(f"处理结果失败: {e}")

        finally:
            # 隐藏加载进度条
            if self.symbol_loading_progress:
                self.symbol_loading_progress.setVisible(False)

            # 清理线程引用
            self.reload_thread = None
            self.logger.info(">>> _on_reload_finished() 执行完成")

    def _on_reload_error(self, error_message: str):
        """重新加载出错的回调（在UI线程中执行）.

        Args:
            error_message: 错误消息
        """
        self.logger.error("重新加载品种失败: %s", error_message)

        # 隐藏加载进度条
        if self.symbol_loading_progress:
            self.symbol_loading_progress.setVisible(False)

        self.show_error(error_message)

        # 清理线程引用
        self.reload_thread = None

    def _refresh_symbols(self):
        """刷新品种（从缓存，带日期验证）."""
        try:
            if not self.data_center_service:
                self.show_error("数据中心服务未初始化")
                return

            # 调用 refresh_symbol_list() 从缓存加载已过滤的品种
            result = self.data_center_service.refresh_symbol_list()

            if not result["success"]:
                # 缓存不存在
                if "缓存不存在" in result.get("message", ""):
                    self.logger.warning("品种列表缓存不存在")
                    QMessageBox.warning(
                        self,
                        "无法刷新",
                        "品种列表缓存不存在！\n\n"
                        "请先点击「🔄 重新加载品种」按钮来初始化品种数据。\n\n"
                        "提示：\n"
                        "• 「🔄 重新加载品种」：从通达信服务器获取完整品种列表\n"
                        "• 「↻ 刷新品种」：从本地缓存刷新品种列表",
                        QMessageBox.StandardButton.Ok,
                    )
                else:
                    self.show_error(f"刷新失败: {result.get('message', '未知错误')}")
                return

            # 获取数据
            data = result.get("data", [])
            is_outdated = result.get("is_outdated", False)

            if not data or len(data) == 0:
                self.logger.warning("品种缓存为空")
                self.show_warning("⚠️ 无品种缓存，请先点击【重新加载品种】按钮获取品种列表")
                self.all_symbols_data = []
                self.filtered_symbols_data = []
                self._update_symbols_table()
                return

            # 显示缓存状态（如果过时，询问用户是否继续）
            if is_outdated:
                reply = QMessageBox.information(
                    self,
                    "缓存过时提示",
                    "品种列表缓存已过时（次日0时已失效）\n\n"
                    "建议点击「🔄 重新加载品种」进行增量更新。\n\n"
                    "是否继续使用过时缓存？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.No:
                    return

            # 更新数据
            self.all_symbols_data = data
            self._apply_filters()

            # 刷新品种列表后重新加载联想缓存
            self._load_symbol_cache_for_autocomplete()

            status = "（过时）" if is_outdated else "（有效）"
            self.show_info(f"刷新成功{status}，共 {result['symbol_count']} 个品种")

        except Exception as e:
            self.logger.error("刷新品种失败: %s", e)
            self.show_error(f"刷新失败: {e}")

    # 注：_clear_symbol_cache 方法已移除
    # 原因：缓存管理已完全自动化，次日0时自动失效并更新，无需手动删除

    def _show_empty_categories_warning(self, empty_categories: List[str]):
        """显示空品种类别警告弹窗.

        Args:
            empty_categories: 为空的品种类别列表
        """
        try:
            # 构造警告消息
            categories_str = "、".join(empty_categories)
            warning_msg = (
                f"⚠️ 品种列表获取完成，但以下品种列表为空：\n\n"
                f"【{categories_str}】\n\n"
                f"请排查相关问题：\n"
                f"• 上证A股/深证A股为空：API接口可能异常\n"
                f"• 北证A股为空：addedcode_bj.cfg文件可能不完整或解析失败\n"
                f"• T+0基金为空：spblock.dat文件可能缺失或不包含T+0基金板块\n"
                f"• 可转债为空：tdxstat2.cfg文件可能缺失或不包含可转债数据\n\n"
                f"建议操作：\n"
                f"• 检查通达信软件根目录配置是否正确\n"
                f"• 确认配置文件是否完整且可读\n"
                f"• 重新安装通达信软件或更新配置文件"
            )

            # 显示警告对话框
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("品种列表警告")
            msg_box.setText(warning_msg)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()

            self.logger.warning("已显示空品种类别警告弹窗: %s", empty_categories)

        except Exception as e:
            self.logger.error("显示空品种类别警告失败: %s", e, exc_info=True)

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

                def matches_symbol(symbol_data):
                    """检查品种是否匹配搜索条件"""
                    try:
                        code = self._extract_symbol_code(symbol_data).lower()
                        name = self._extract_symbol_name(symbol_data).lower()

                        # 查找该品种的拼音首字母（如果在联想缓存中）
                        pinyin = ""
                        for cached_symbol in self.symbol_cache:
                            if (
                                cached_symbol.get("code") == code
                                and cached_symbol.get("name") == name
                            ):
                                pinyin = cached_symbol.get("pinyin", "").lower()
                                break

                        # 三种匹配方式：代码、名称、拼音首字母
                        return search_text in code or search_text in name or search_text in pinyin
                    except Exception:
                        # 如果出现异常，至少保证代码和名称匹配
                        code = self._extract_symbol_code(symbol_data).lower()
                        name = self._extract_symbol_name(symbol_data).lower()
                        return search_text in code or search_text in name

                filtered = [s for s in filtered if matches_symbol(s)]

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

        # 🔧 增强容错性：检查数据有效性
        if not self.filtered_symbols_data:
            self.logger.debug("filtered_symbols_data为空，清空表格")
            self.symbols_table.setRowCount(0)
            if self.symbols_count_label:
                self.symbols_count_label.setText("共 0 个品种")
            if self.page_label:
                self.page_label.setText("第 1 页 / 共 1 页")
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
            try:
                # 🚀 兼容性处理：symbol可能是字典或字符串
                if isinstance(symbol, dict):
                    # 🔧 处理嵌套字典结构：后端返回的数据结构
                    # symbol = {
                    #     'symbol': {'code': '600000', 'name': '浦发银行', 'market': 1},
                    #     'code': {'code': '600000', 'name': '浦发银行', 'market': 1},
                    #     'name': {'code': '600000', 'name': '浦发银行', 'market': 1},
                    #     'exchange': '上交所',
                    #     'product_type': '股票'
                    # }

                    # 获取品种信息字典（优先从symbol键获取，这是后端主要返回的）
                    symbol_info = None
                    if "symbol" in symbol and isinstance(symbol["symbol"], dict):
                        symbol_info = symbol["symbol"]
                    elif "code" in symbol and isinstance(symbol["code"], dict):
                        symbol_info = symbol["code"]
                    elif "name" in symbol and isinstance(symbol["name"], dict):
                        symbol_info = symbol["name"]

                    if symbol_info:
                        symbol_code = symbol_info.get("code", "")
                        symbol_name = symbol_info.get("name", "")
                        symbol_exchange = symbol.get("exchange", "")
                        symbol_type = symbol.get("product_type", "")
                    else:
                        # 备用处理：如果嵌套结构不匹配，尝试直接获取
                        symbol_code = symbol.get("code", "")
                        if isinstance(symbol_code, dict) and "code" in symbol_code:
                            symbol_code = symbol_code["code"]
                        symbol_name = symbol.get("name", "")
                        if isinstance(symbol_name, dict) and "name" in symbol_name:
                            symbol_name = symbol_name["name"]
                        symbol_exchange = symbol.get("exchange", "")
                        symbol_type = symbol.get("product_type", "")
                else:
                    # 旧格式：字符串
                    symbol_code = str(symbol)
                    symbol_name = ""
                    symbol_exchange = ""
                    symbol_type = ""

                # 🔧 数据验证：确保品种代码不为空
                if not symbol_code:
                    self.logger.warning(f"第{i}行品种数据无效，跳过: {symbol}")
                    # 🔧 调试日志：记录数据结构类型
                    self.logger.debug(
                        f"数据结构类型: symbol={type(symbol)}, symbol_code={type(symbol_code)}"
                    )
                    if isinstance(symbol, dict):
                        self.logger.debug(f"symbol.keys()={list(symbol.keys())}")
                        for k, v in symbol.items():
                            self.logger.debug(f"  {k}: {type(v)} = {v}")
                    continue

                # 确保所有字段都是字符串类型，避免类型错误
                symbol_code_str = str(symbol_code) if symbol_code else ""
                symbol_name_str = str(symbol_name) if symbol_name else ""
                symbol_exchange_str = str(symbol_exchange) if symbol_exchange else ""
                symbol_type_str = str(symbol_type) if symbol_type else ""

                self.symbols_table.setItem(i, 0, QTableWidgetItem(symbol_code_str))
                self.symbols_table.setItem(i, 1, QTableWidgetItem(symbol_name_str))
                self.symbols_table.setItem(i, 2, QTableWidgetItem(symbol_exchange_str))
                self.symbols_table.setItem(i, 3, QTableWidgetItem(symbol_type_str))
                self.symbols_table.setItem(i, 4, QTableWidgetItem("正常"))
            except Exception as e:
                self.logger.error(f"更新第{i}行品种数据失败: {e}, symbol={symbol}", exc_info=True)
                # 继续处理下一行，不中断整个表格更新
                continue

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
        """搜索文本改变，直接触发品种列表过滤（品种列表本身就是联想结果）"""
        # 搜索框直接触发品种列表过滤，不需要单独的QCompleter联想列表
        self._apply_filters()

    def _on_filter_changed(self, _value: str):
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

    def _extract_symbol_code(self, symbol_data: Dict[str, Any]) -> str:
        """提取品种代码（直接从品种数据中获取）

        Args:
            symbol_data: 品种数据字典

        Returns:
            品种代码字符串
        """
        if not isinstance(symbol_data, dict):
            return ""

        # 品种数据结构：{"symbol": "600000", "code": "600000", "name": "浦发银行", ...}
        return str(symbol_data.get("symbol") or symbol_data.get("code") or "")

    def _extract_symbol_name(self, symbol_data: Dict[str, Any]) -> str:
        """提取品种名称（直接从品种数据中获取并清理乱码）

        Args:
            symbol_data: 品种数据字典

        Returns:
            品种名称字符串（已清理乱码）
        """
        if not isinstance(symbol_data, dict):
            return ""

        # 获取品种名称
        name = str(symbol_data.get("name") or "")

        # 清理常见乱码字符
        name = self._clean_symbol_name_encoding(name)

        return name

    def _clean_symbol_name_encoding(self, name: str) -> str:
        """清理品种名称中的乱码字符

        Args:
            name: 原始品种名称

        Returns:
            清理后的品种名称
        """
        if not name:
            return ""

        # 清理常见乱码字符
        cleaned = name.replace("\x00", "")  # 移除空字符
        cleaned = cleaned.replace("\u0000", "")  # 移除Unicode空字符
        cleaned = cleaned.replace("\ufffd", "")  # 移除替换字符
        cleaned = cleaned.strip()  # 移除前后空白字符

        return cleaned

    def _get_pinyin_initials(self, text: str) -> str:
        """获取文本的拼音首字母

        使用pypinyin库（如果可用），否则返回空字符串

        Args:
            text: 中文文本

        Returns:
            拼音首字母字符串（小写）
        """
        # 防护措施：避免处理无效输入
        if not text or not isinstance(text, str):
            return ""

        # 防护措施：纯数字不应该生成拼音首字母
        if text.isdigit():
            return text[0] if text else ""

        try:
            from pypinyin import lazy_pinyin

            # 防护措施：限制文本长度，避免处理过长的文本
            if len(text) > 100:
                text = text[:100]

            pinyin_list = lazy_pinyin(text)

            # 防护措施：确保拼音列表不为空且每个元素都是字符串
            if not pinyin_list:
                return ""

            initials = []
            for p in pinyin_list:
                if isinstance(p, str) and p:
                    initials.append(p[0].lower())
                else:
                    # 对于非字符串元素，取第一个字符
                    initials.append(str(p)[0].lower() if p else "")

            return "".join(initials)

        except ImportError:
            self.logger.debug("pypinyin未安装，智能联想拼音功能不可用")
            return ""
        except Exception as e:
            self.logger.debug(f"获取拼音首字母失败: {e}, text='{text}'")
            return ""

    def _on_symbol_input_changed(self, text: str):
        """处理品种输入变化，实现智能联想（本地数据搜索框）

        使用本地数据索引作为唯一联想源（已下载的品种）。

        Args:
            text: 输入的文本
        """
        print(f"🔍 DEBUG: _on_symbol_input_changed() 被调用！text='{text}'")  # 调试语句8
        if not text or len(text) < 1:
            self.logger.debug("输入为空，跳过联想")
            return

        # 检查缓存是否已加载
        if not self.local_data_cache:
            print(f"❌ DEBUG: local_data_cache 为空！cache={self.local_data_cache}")  # 调试语句9
            self.logger.debug("⚠️  local_data_cache为空，联想功能不可用（可能还未加载或本地无数据）")
            return

        print(f"✅ DEBUG: local_data_cache 有数据！大小={len(self.local_data_cache)}")  # 调试语句10

        try:
            self.logger.debug(f"🔍 联想查询: '{text}', 缓存大小: {len(self.local_data_cache)}")
            # 过滤匹配的品种（使用本地数据索引）
            matches = []
            text_lower = text.lower()

            for symbol in self.local_data_cache:
                code = symbol.get("code", "")
                name = symbol.get("name", "")
                pinyin = symbol.get("pinyin", "")

                # 匹配规则：代码包含、名称包含、拼音首字母包含（统一使用小写匹配）
                if text_lower in code.lower() or text_lower in name.lower() or text_lower in pinyin:
                    # 只显示代码和名称（简洁美观）
                    display = f"{code} {name}" if name else code
                    matches.append(display)

            self.logger.debug(f"  找到 {len(matches)} 个匹配项")

            # 更新补全列表（限制20条）
            if self.symbol_completer:
                model = QStringListModel(matches[:20])
                self.symbol_completer.setModel(model)
                self.logger.debug(f"✅ 联想列表已更新: {min(len(matches), 20)} 项")
            else:
                self.logger.debug("⚠️  symbol_completer 未初始化")

        except Exception as e:
            self.logger.error(f"❌ 更新本地数据搜索联想失败: {e}", exc_info=True)

    def _load_symbol_cache_for_autocomplete(self):
        """加载品种缓存用于品种列表搜索框的拼音匹配

        注意：此缓存仅用于品种列表搜索框的拼音首字母匹配，
        搜索框不使用QCompleter，搜索直接触发品种列表过滤。
        """
        try:
            if not self.data_center_service:
                self.logger.debug("[品种列表搜索框] 数据中心服务不可用")
                return

            # 从缓存读取品种列表
            symbols = self.data_center_service.get_symbols_from_cache()
            if not symbols:
                self.logger.debug("[品种列表搜索框] 品种缓存为空，拼音匹配暂不可用")
                return

            # 预处理：添加拼音首字母（分批处理，避免内存问题）
            self.symbol_cache = []
            success_count = 0
            error_count = 0

            # 分批处理，每批处理1000个品种，避免一次性处理过多数据
            batch_size = 1000
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i : i + batch_size]
                self.logger.debug(
                    f"处理品种批次 {i//batch_size + 1}/{(len(symbols) + batch_size - 1)//batch_size}"
                )

                for symbol in batch:
                    try:
                        if isinstance(symbol, dict):
                            # 直接从品种数据中提取代码和名称
                            code = self._extract_symbol_code(symbol)
                            raw_name = str(symbol.get("name") or "")
                            name = self._clean_symbol_name_encoding(raw_name)

                            # 使用清理后的名称（后端已过滤掉API中不存在的品种）
                            final_name = name

                            # 确保品种代码和最终名称都有效
                            if code and final_name:
                                pinyin = self._get_pinyin_initials(final_name)
                                self.symbol_cache.append(
                                    {"code": code, "name": final_name, "pinyin": pinyin}
                                )
                                success_count += 1
                            else:
                                error_count += 1
                                self.logger.debug(
                                    f"跳过无效品种数据: code={code}, raw_name='{raw_name}', cleaned_name='{name}', final_name='{final_name}'"
                                )
                        else:
                            error_count += 1
                            self.logger.debug(f"跳过非字典品种数据: {symbol}")
                    except Exception as e:
                        error_count += 1
                        self.logger.debug(f"处理品种数据失败: {e}, data={symbol}")

                # 处理一批后强制垃圾回收，避免内存累积
                import gc

                gc.collect()

            # 所有无效品种应在后端早期阶段已过滤，前端只记录最终加载结果
            if error_count > 0:
                self.logger.debug(f"品种缓存加载时跳过了{error_count}个无效数据")
            self.logger.info(f"品种缓存加载完成: {success_count} 个品种")

        except Exception as e:
            self.logger.error(f"加载品种缓存失败: {e}", exc_info=True)

    def _load_local_data_index_for_autocomplete(self):
        """异步加载本地数据索引用于本地数据搜索框联想

        使用后台线程扫描本地数据目录，避免阻塞UI。
        """
        import threading

        def load_in_background():
            """后台线程执行数据加载"""
            try:
                if not self.data_center_service:
                    self.logger.debug("[本地数据搜索框] 数据中心服务不可用")
                    # 🆕 更新状态提示为错误
                    QTimer.singleShot(0, lambda: self._update_loading_status_error("服务不可用"))
                    return

                self.logger.info("[后台] 开始扫描本地数据索引...")

                # 从本地数据索引获取已下载的品种列表
                local_symbols = self.data_center_service.get_local_data_index()
                if not local_symbols:
                    self.logger.debug("[本地数据搜索框] 本地数据索引为空（尚未下载数据）")
                    # 🆕 更新状态提示为无数据
                    QTimer.singleShot(0, lambda: self._update_local_data_cache([], 0, 0))
                    return

                # 预处理：添加拼音首字母
                temp_cache = []
                success_count = 0
                error_count = 0

                for symbol in local_symbols:
                    try:
                        if isinstance(symbol, dict):
                            code = symbol.get("code", "")
                            name = symbol.get("name", "")

                            if code:
                                pinyin = self._get_pinyin_initials(name) if name else ""
                                temp_cache.append({"code": code, "name": name, "pinyin": pinyin})
                                success_count += 1
                            else:
                                error_count += 1
                        else:
                            error_count += 1
                    except Exception as e:
                        error_count += 1
                        self.logger.debug(f"[后台] 处理品种失败: {e}")

                # 使用QTimer在主线程中更新缓存
                QTimer.singleShot(
                    0, lambda: self._update_local_data_cache(temp_cache, success_count, error_count)
                )

            except Exception as e:
                self.logger.error(f"[后台] 加载本地数据索引失败: {e}", exc_info=True)
                # 🆕 更新状态提示为错误
                QTimer.singleShot(0, lambda: self._update_loading_status_error("加载失败"))

        # 启动后台线程
        thread = threading.Thread(target=load_in_background, daemon=True, name="LoadLocalDataIndex")
        thread.start()

    def _update_local_data_cache(self, cache, success_count, error_count):
        """在主线程中更新本地数据缓存"""
        print(f"🔍 DEBUG: _update_local_data_cache() 被调用！cache大小={len(cache)}")  # 调试语句6
        self.local_data_cache = cache
        print(f"✅ DEBUG: local_data_cache 已更新！大小={len(self.local_data_cache)}")  # 调试语句7
        # 所有无效品种应在后端早期阶段已过滤，前端只记录最终加载结果
        if error_count > 0:
            self.logger.debug(f"本地数据索引加载时跳过了{error_count}个无效数据")
        self.logger.info(f"本地数据索引加载完成: {success_count} 个品种")
        
        # 🆕 更新状态提示标签
        if self.symbol_input_status_label:
            if success_count > 0:
                self.symbol_input_status_label.setText(f"✅ 已加载 {success_count} 个品种")
                self.symbol_input_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; padding-left: 5px;")
                # 3秒后隐藏提示
                status_label = self.symbol_input_status_label  # 保存引用避免类型检查问题
                QTimer.singleShot(3000, lambda: status_label.setVisible(False) if status_label else None)
            else:
                self.symbol_input_status_label.setText("⚠️ 本地暂无数据，请先下载")
                self.symbol_input_status_label.setStyleSheet("color: #FF9800; font-size: 11px; padding-left: 5px;")

    def _update_loading_status_error(self, reason: str):
        """更新索引加载状态为错误"""
        if self.symbol_input_status_label:
            self.symbol_input_status_label.setText(f"⚠️ 索引加载失败（{reason}），请手动输入完整代码")
            self.symbol_input_status_label.setStyleSheet("color: #F44336; font-size: 11px; padding-left: 5px;")

    def _on_local_data_index_ready(self, event):
        """处理本地数据索引就绪事件（来自后台数据质量扫描）"""
        try:
            if self._local_data_index_loaded:
                return  # 已加载，跳过
            
            data = event.data
            symbol_list = data.get("symbols", [])
            count = data.get("count", 0)
            
            self.logger.info(f"📋 收到本地数据索引事件: {count} 个品种")
            
            # 添加拼音首字母
            temp_cache = []
            for symbol_info in symbol_list:
                try:
                    code = symbol_info.get("code", "")
                    name = symbol_info.get("name", "")
                    if code:
                        pinyin = self._get_pinyin_initials(name) if name else ""
                        temp_cache.append({"code": code, "name": name, "pinyin": pinyin})
                except Exception as e:
                    self.logger.debug(f"处理品种失败: {e}")
            
            # 更新缓存
            self._update_local_data_cache(temp_cache, len(temp_cache), 0)
            self._local_data_index_loaded = True
            
        except Exception as e:
            self.logger.error(f"处理本地数据索引事件失败: {e}", exc_info=True)

    def _load_local_data_index_fallback(self):
        """后备方案：如果事件推送未到达，手动加载本地数据索引"""
        if self._local_data_index_loaded:
            self.logger.info("本地数据索引已通过事件加载，跳过后备方案")
            return
        
        self.logger.info("未收到本地数据索引事件，启动后备方案手动加载...")
        # 调用原有的加载方法
        self._load_local_data_index_for_autocomplete()

    def _on_quality_scan_phase(self, event):
        """处理数据质量扫描阶段性推送事件
        
        增量更新UI，用户可以立即看到各个阶段的数据，无需等待全部扫描完成。
        """
        try:
            data = event.data
            phase = data.get("phase", 0)
            metrics = data.get("metrics", {})
            status = data.get("status", "")
            
            self.logger.info(f"📊 收到阶段{phase}推送: {metrics}")
            
            # 更新对应的UI组件
            if "total_symbols" in metrics:
                if self.total_symbols_label:
                    self.total_symbols_label.setText(f"总品种: {metrics['total_symbols']}")
                    self.total_symbols_label.setStyleSheet("")  # 清除灰色
            
            if "downloaded_symbols" in metrics:
                if self.downloaded_symbols_label:
                    self.downloaded_symbols_label.setText(f"已下载: {metrics['downloaded_symbols']}")
                    self.downloaded_symbols_label.setStyleSheet("color: #4CAF50;")
            
            if "missing_symbols" in metrics:
                if self.missing_symbols_label:
                    self.missing_symbols_label.setText(f"缺失: {metrics['missing_symbols']}")
                    self.missing_symbols_label.setStyleSheet("color: #FF9800;")
            
            if "outdated_symbols" in metrics:
                if self.outdated_symbols_label:
                    self.outdated_symbols_label.setText(f"过时: {metrics['outdated_symbols']}")
                    self.outdated_symbols_label.setStyleSheet("color: #FF9800;")
            
            if "avg_gap_days" in metrics:
                if self.avg_gap_label:
                    self.avg_gap_label.setText(f"平均滞后: {metrics['avg_gap_days']}天")
                    self.avg_gap_label.setStyleSheet("")  # 清除灰色
            
            if "error_symbols" in metrics:
                if self.error_symbols_label:
                    self.error_symbols_label.setText(f"错误: {metrics['error_symbols']}")
                    self.error_symbols_label.setStyleSheet("color: #F44336;")
            
            if "warning_symbols" in metrics:
                if self.warning_symbols_label:
                    self.warning_symbols_label.setText(f"警告: {metrics['warning_symbols']}")
                    self.warning_symbols_label.setStyleSheet("color: #FFC107;")
            
            if "quality_score" in metrics:
                if self.quality_score_label:
                    score = metrics['quality_score']
                    self.quality_score_label.setText(f"评分: {score}")
                    # 根据评分设置颜色
                    if score >= 90:
                        color = "#4CAF50"  # 绿色
                    elif score >= 70:
                        color = "#FFC107"  # 黄色
                    else:
                        color = "#F44336"  # 红色
                    self.quality_score_label.setStyleSheet(f"color: {color};")
            
            # 更新扫描状态指示器
            if self.quality_scan_status_label:
                status_icons = {
                    "scanning": "🔍",
                    "checking_freshness": "⏱️",
                    "scanning_quality": "🔬",
                    "calculating_score": "🧮",
                    "complete": "✅",
                }
                icon = status_icons.get(status, "🔄")
                self.quality_scan_status_label.setText(icon)
                
                status_texts = {
                    "scanning": "扫描中",
                    "checking_freshness": "检查更新状态",
                    "scanning_quality": "检查质量",
                    "calculating_score": "计算评分",
                    "complete": "完成",
                }
                tooltip = status_texts.get(status, "处理中")
                self.quality_scan_status_label.setToolTip(f"数据质量感知状态：{tooltip}")
                
        except Exception as e:
            self.logger.error(f"处理质量扫描阶段事件失败: {e}", exc_info=True)

    # ==================== 本地数据事件处理 ====================

    def _query_local_data(self):
        """查询本地数据."""
        try:
            self.logger.info("🔍 开始查询本地数据...")

            # 检查服务
            if not self.data_center_service:
                self.logger.error("❌ 数据中心服务未初始化")
                self.show_error("数据中心服务未初始化")
                return

            # 检查输入
            if not self.symbol_input or not self.symbol_input.text().strip():
                self.logger.warning("⚠️  品种代码为空")
                self.show_warning("请输入品种代码")
                return

            symbol = self.symbol_input.text().strip()
            self.logger.info(f"  品种代码: {symbol}")

            # 获取日期
            start_date_str = ""
            end_date_str = ""

            if self.start_date_input:
                qdate = self.start_date_input.date()
                start_date_str = qdate.toString("yyyy-MM-dd")
                self.logger.info(f"  开始日期: {start_date_str}")

            if self.end_date_input:
                qdate = self.end_date_input.date()
                end_date_str = qdate.toString("yyyy-MM-dd")
                self.logger.info(f"  结束日期: {end_date_str}")

            # 获取周期
            interval = self.interval_combo.currentText() if self.interval_combo else "1day"
            self.logger.info(f"  周期: {interval}")

            # 检查data_table
            if not self.data_table:
                self.logger.error("❌ data_table 未初始化")
                self.show_error("数据展示组件未初始化")
                return

            self.logger.info(f"✅ data_table 已就绪，当前行数: {self.data_table.rowCount()}")

            self.show_info("正在查询本地数据...")

            # 调用后端查询
            result = self.data_center_service.query_local_data(
                symbol=symbol, start_date=start_date_str, end_date=end_date_str, interval=interval
            )

            self.logger.info(f"  查询结果: success={result.get('success')}")

            if result["success"]:
                data = result.get("data", [])
                self.logger.info(f"  返回数据: {len(data)} 条记录")

                # 更新数据展示表格
                self.data_table.setRowCount(len(data))
                self.logger.info(f"  表格行数已设置为: {len(data)}")
                for i, record in enumerate(data):
                    self.data_table.setItem(i, 0, QTableWidgetItem(str(record.get("datetime", ""))))
                    self.data_table.setItem(i, 1, QTableWidgetItem(str(record.get("open", ""))))
                    self.data_table.setItem(i, 2, QTableWidgetItem(str(record.get("high", ""))))
                    self.data_table.setItem(i, 3, QTableWidgetItem(str(record.get("low", ""))))
                    self.data_table.setItem(i, 4, QTableWidgetItem(str(record.get("close", ""))))
                    self.data_table.setItem(i, 5, QTableWidgetItem(str(record.get("volume", ""))))
                    self.data_table.setItem(i, 6, QTableWidgetItem(str(record.get("turnover", 0))))

                # 显示查询成功提示
                if len(data) == 0:
                    msg = f"查询成功，品种 {symbol} 暂无本地数据"
                    self.logger.info(f"✅ {msg}")
                    self.show_info(msg)
                else:
                    # 🆕 获取数据更新状态
                    try:
                        quality_result = self.data_center_service.check_data_quality(
                            symbol, interval
                        )
                        if quality_result.get("success"):
                            gap_days = quality_result.get("gap_days", -1)
                            local_latest = quality_result.get("local_latest_date", "未知")
                            latest_trading = quality_result.get("latest_trading_day", "未知")

                            if gap_days >= 0:
                                if gap_days == 0:
                                    freshness_msg = (
                                        f"✅ 数据已是最新（最新交易日：{latest_trading}）"
                                    )
                                elif gap_days == 1:
                                    freshness_msg = f"⚠️ 数据滞后1个交易日（本地最新：{local_latest}，最新交易日：{latest_trading}）"
                                else:
                                    freshness_msg = f"⚠️ 数据滞后{gap_days}个交易日（本地最新：{local_latest}，最新交易日：{latest_trading}）"

                                msg = f"查询成功，共 {len(data)} 条记录\n{freshness_msg}"
                            else:
                                msg = f"查询成功，共 {len(data)} 条记录"
                        else:
                            msg = f"查询成功，共 {len(data)} 条记录"
                    except Exception as e:
                        self.logger.debug(f"获取数据更新状态失败: {e}")
                        msg = f"查询成功，共 {len(data)} 条记录"

                    self.logger.info(f"✅ {msg}")
                    self.show_info(msg)
            else:
                # 查询失败
                error_msg = result.get("message", "未知错误")
                self.logger.error(f"❌ 查询失败: {error_msg}")
                self.show_error(f"查询失败: {error_msg}")

        except Exception as e:
            self.logger.error("❌ 查询本地数据异常: %s", e, exc_info=True)
            self.show_error(f"查询失败: {e}")

    # 🚫 已废弃：单品种质量检查方法（改为全局质量概览联动）
    # def _check_data_quality_for_symbol(self, symbol: str, interval: str = "1d"):
    #     """检查指定品种的数据质量（数据感知功能）.
    #
    #     Args:
    #         symbol: 品种代码
    #         interval: K线周期，默认"1d"
    #
    #     注意：此方法已废弃，本地数据状态现在由质量概览组件联动更新
    #     """
    #     pass

    def _repair_data(self):
        """修复当前品种的数据."""
        try:
            if not self.data_center_service:
                self.show_error("数据中心服务未初始化")
                return

            if not self.current_queried_symbol:
                self.show_warning("没有需要修复的品种")
                return

            symbol = self.current_queried_symbol

            # 确认对话框
            reply = QMessageBox.question(
                self,
                "确认修复",
                f"确定要修复品种 {symbol} 的数据吗？\n\n"
                "将重新下载最近30天的数据来修复缺失和错误。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            self.logger.info("🔧 开始修复品种 %s 的数据...", symbol)
            self.show_info("正在修复数据，请稍候...")

            # 调用修复API（传入空列表，因为后端会自动修复）
            result = self.data_center_service.auto_repair_data(symbol, [])

            if result.get("success"):
                self.show_info(f"✅ {result.get('message')}")
                self.logger.info("✅ 数据修复成功")

                # 修复后重新查询数据
                self._query_local_data()
            else:
                self.show_error(f"修复失败: {result.get('message')}")
                self.logger.error("❌ 数据修复失败: %s", result.get("message"))

        except Exception as e:
            self.logger.error("修复数据失败: %s", e, exc_info=True)
            self.show_error(f"修复失败: {str(e)}")

    # ==================== 数据下载事件处理 ====================

    def _validate_date_range(self):
        """验证日期范围（确保不超过100天）."""
        if not self.download_start_date:
            return

        start_date = self.download_start_date.date()
        current_date = QDate.currentDate()
        days_diff = start_date.daysTo(current_date)

        if days_diff > 100:
            self.show_warning("增量下载最多支持最近100天数据，已自动调整为100天前")
            self.download_start_date.setDate(current_date.addDays(-100))

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

            # 获取增量下载参数
            if self.download_start_date:
                qdate = self.download_start_date.date()
                start_date = qdate.toString("yyyy-MM-dd")
            else:
                start_date = datetime.now().strftime("%Y-%m-%d")

            self.logger.info(">>> 增量下载，开始日期: %s", start_date)

            # 验证日期范围（前端双重保险）
            current_date = QDate.currentDate()
            days_diff = qdate.daysTo(current_date)
            if days_diff > 100:
                self.show_error("增量下载最多支持最近100天数据，请重新选择日期")
                return

            # 🔧 关键修复：提前生成并保存任务ID
            # 不等待下载完成回调，立即保存任务ID以便停止操作
            task_id = f"incremental_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.current_download_task_id = task_id
            self.logger.info(">>> 生成任务ID: %s", task_id)

            # 创建下载线程
            self.logger.info(">>> 创建 DownloadThread...")
            self.download_thread = DownloadThread(self.data_center_service, start_date, self)
            self.logger.info(">>> DownloadThread 创建成功: %s", self.download_thread)

            # 连接信号
            self.logger.info(">>> 连接信号...")
            # 🚀 关键修复：使用Qt.ConnectionType.QueuedConnection确保跨线程信号安全
            # 这会确保槽函数在主线程的事件循环中执行，避免绘图冲突
            self.download_thread.finished_signal.connect(
                self._on_download_finished, Qt.ConnectionType.QueuedConnection
            )
            self.download_thread.error_signal.connect(
                self._on_download_error, Qt.ConnectionType.QueuedConnection
            )
            # 🚀 改用文本追加槽函数，避免show_info的UI重绘
            self.download_thread.progress_signal.connect(
                self._append_progress_text, Qt.ConnectionType.QueuedConnection
            )
            self.logger.info(">>> 信号连接完成")

            # 启动线程
            self.logger.info(">>> 启动下载线程...")
            self.download_thread.start()
            self.logger.info(">>> 线程已启动，isRunning: %s", self.download_thread.isRunning())

            # ✅ 设置初始进度文本（QPlainTextEdit用setPlainText）
            if self.progress_text:
                self.progress_text.setPlainText(f"开始增量下载... (开始日期: {start_date})")

            # 更新按钮状态
            if self.start_download_btn:
                self.start_download_btn.setEnabled(False)
            if self.pause_download_btn:
                self.pause_download_btn.setEnabled(True)
            if self.stop_download_btn:
                self.stop_download_btn.setEnabled(True)

            # 显示加载提示（改用print，避免UI更新）
            # self.show_info(f"正在启动下载任务...")
            print(f"正在启动下载任务... (任务ID: {task_id})")
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
            self.logger.info(
                ">>> result: success=%s, message=%s", result.get("success"), result.get("message")
            )

            # 🆕 下载完成后刷新本地数据索引，更新本地数据搜索框的联想列表
            # 🔧 关键修复：延迟调用，避免在信号槽中执行耗时操作导致递归重绘
            if result.get("success"):
                QTimer.singleShot(1000, self._load_local_data_index_for_autocomplete)
            self.logger.info("=" * 60)

            if result.get("success"):
                task_id = result.get("task_id") or getattr(self, "current_download_task_id", None)
                message = result.get("message", "")

                # 🔧 区分"任务已启动"和"任务已完成"
                if "已启动" in message or "启动" in message:
                    # 异步下载：任务刚启动，不是完成
                    # 禁用show_info，避免UI崩溃
                    # self.show_info(f"✅ {message}（任务ID: {task_id}）")
                    # self.show_info("📊 下载正在后台进行...")
                    self.logger.info(">>> 下载任务已启动（异步）: %s", task_id)
                    print(f"✅ {message}（任务ID: {task_id}）")
                    print("📊 下载正在后台进行，请查看终端进度...")

                    # 🔧 启动进度轮询定时器
                    self._start_progress_polling()

                    # 注意：保持按钮状态，允许用户停止下载
                else:
                    # 同步下载或真正完成
                    # 禁用show_info，避免UI崩溃
                    # self.show_info(f"✅ 下载任务已完成！任务ID: {task_id}")
                    self.logger.info(">>> 下载任务完成成功: %s", task_id)
                    print(f"✅ 下载任务已完成！任务ID: {task_id}")

                    # 🆕 记录下载历史
                    self._add_download_history(result)

                    self._reset_download_state()
            else:
                self.logger.error(">>> 下载任务失败: %s", result.get("message"))
                # 🔧 避免UI操作导致崩溃，只打印错误信息
                print(f"❌ 下载任务失败: {result.get('message', '未知错误')}")

                # 🆕 记录下载历史（即使失败也要记录）
                if result.get("task_id"):
                    self._add_download_history(result)

                self._reset_download_state()

        except Exception as e:
            self.logger.error(">>> 处理下载结果失败: %s", e, exc_info=True)
            # 🔧 避免UI操作导致崩溃，只打印错误信息
            print(f"❌ 处理下载结果失败: {e}")
            self._reset_download_state()

    def _on_download_error(self, error_message: str):
        """下载出错的回调（在UI线程中执行）.

        Args:
            error_message: 错误消息
        """
        self.logger.error("下载失败: %s", error_message)
        # 🔧 避免UI操作导致崩溃，只打印错误信息
        print(f"❌ 下载失败: {error_message}")

        # 🔧 修复：统一使用 _reset_download_state() 清理状态
        self._reset_download_state()

    def _pause_download(self):
        """暂停下载."""
        if not self.data_center_service:
            self.show_error("数据中心服务不可用")
            return

        task_id = getattr(self, "current_download_task_id", None)
        if not task_id:
            self.show_warning("没有活动的下载任务")
            return

        # 🔧 新架构：调用后端暂停方法
        result = self.data_center_service.pause_download(task_id)

        if result.get("success"):
            self.show_info("⏸️ 已发送暂停信号，下载将在当前品种完成后暂停...")
            self.logger.info(">>> 暂停信号已发送")
            # 更新按钮状态
            if self.pause_download_btn:
                self.pause_download_btn.setText("恢复下载")
                self.pause_download_btn.clicked.disconnect()
                self.pause_download_btn.clicked.connect(self._resume_download)
        else:
            self.show_warning(f"暂停请求失败: {result.get('message')}")
            self.logger.warning(">>> 暂停请求失败: %s", result.get("message"))

    def _resume_download(self):
        """恢复下载."""
        if not self.data_center_service:
            self.show_error("数据中心服务不可用")
            return

        if not hasattr(self, "current_download_task_id"):
            self.show_warning("没有暂停的下载任务")
            return

        current_id = getattr(self, "current_download_task_id", None)
        if not current_id:
            self.show_warning("没有需要恢复的下载任务")
            return

        result = self.data_center_service.resume_download(current_id)

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

            # 🔧 新架构：调用后端停止方法（后端会通知后台线程停止）
            if not self.data_center_service:
                self.show_error("数据中心服务不可用")
                return

            # 调用后端停止方法
            task_id = getattr(self, "current_download_task_id", None)
            if not task_id:
                self.show_warning("没有正在运行的下载任务")
                return

            result = self.data_center_service.stop_download(task_id)

            if result.get("success"):
                # 不调用show_info，避免UI更新导致崩溃
                # self.show_info("⛔ 已发送停止信号...")
                self.logger.info(">>> 停止信号已发送")
                print("⛔ 停止信号已发送，下载将在当前品种完成后停止...")
            else:
                self.show_warning(f"停止请求失败: {result.get('message')}")
                self.logger.warning(">>> 停止请求失败: %s", result.get("message"))

            # 旧逻辑：尝试停止QThread（用于兼容旧的同步下载）
            thread_stopped = False
            if self.download_thread and self.download_thread.isRunning():
                self.logger.info(">>> 检测到运行中的QThread线程，尝试终止...")
                try:
                    # 请求线程终止
                    self.download_thread.requestInterruption()
                    # 等待最多3秒
                    if self.download_thread.wait(3000):
                        self.logger.info(">>> QThread已正常终止")
                        thread_stopped = True
                    else:
                        # 强制终止（不推荐，但必要时使用）
                        self.logger.warning(">>> QThread未响应，强制终止...")
                        self.download_thread.terminate()
                        self.download_thread.wait(1000)
                        thread_stopped = True
                except Exception as thread_error:
                    self.logger.error(">>> 终止线程失败: %s", thread_error)

            # 🔧 修复：再尝试通过后端服务停止任务
            backend_stopped = False
            task_id = getattr(self, "current_download_task_id", None)
            if self.data_center_service and task_id:
                self.logger.info(">>> 尝试通过后端服务停止任务: %s", task_id)
                try:
                    result = self.data_center_service.stop_download(task_id)
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

    def _register_event_handlers(self):
        """注册vnpy事件监听器"""
        try:
            self.event_engine = get_event_engine()

            if self.event_engine:
                # 注册下载事件监听器
                self.event_engine.register(EVENT_CHINASTOCK_DOWNLOAD, self._on_download_event)
                # 注册数据质量事件监听器
                self.event_engine.register(EVENT_DATA_QUALITY_UPDATE, self._on_data_quality_update)
                self.event_engine.register(EVENT_DATA_SCAN_COMPLETE, self._on_data_scan_complete)
                # 🆕 注册本地数据索引就绪事件监听器
                self.event_engine.register("eLocalDataIndexReady", self._on_local_data_index_ready)
                # 🆕 注册数据质量阶段性推送事件监听器
                self.event_engine.register("eQualityScanPhase", self._on_quality_scan_phase)
                # 注册服务器池状态事件监听器
                self.event_engine.register(
                    "EVENT_SERVER_POOL_STATUS", self._on_server_status_update
                )
                self.logger.info("✅ vnpy事件监听器已注册（下载+数据质量+本地索引+阶段推送+服务器状态）")

                # 🆕 主动查询一次服务器状态（Pull模式）
                # 解决启动时已完成测速但前端还未创建的问题
                self._fetch_initial_server_status()
            else:
                self.logger.warning("⚠️ event_engine不可用，事件推送功能不可用")
                self.logger.info("将使用备用的轮询机制")

        except Exception as e:
            self.logger.error("注册事件监听器失败: %s", e)

    def _unregister_event_handlers(self):
        """注销vnpy事件监听器"""
        try:
            if self.event_engine:
                self.event_engine.unregister(EVENT_CHINASTOCK_DOWNLOAD, self._on_download_event)
                self.event_engine.unregister(
                    EVENT_DATA_QUALITY_UPDATE, self._on_data_quality_update
                )
                self.event_engine.unregister(EVENT_DATA_SCAN_COMPLETE, self._on_data_scan_complete)
                self.event_engine.unregister("eLocalDataIndexReady", self._on_local_data_index_ready)
                self.event_engine.unregister("eQualityScanPhase", self._on_quality_scan_phase)
                self.event_engine.unregister(
                    "EVENT_SERVER_POOL_STATUS", self._on_server_status_update
                )
                self.logger.info("✅ vnpy事件监听器已注销")
        except Exception as e:
            self.logger.error("注销事件监听器失败: %s", e)

    def _on_server_status_update(self, event):
        """处理服务器状态更新事件"""
        try:
            data = event.data
            available = data.get("available", 0)
            total = data.get("total", 0)
            status = data.get("status", "unknown")

            # 更新UI显示
            status_text = f"可用服务器: {available}/{total}"
            if status == "available" and available > 0:
                if self.server_status_label:
                    self.server_status_label.setText(f"✅ {status_text}")
                    self.server_status_label.setStyleSheet(
                        "color: #00aa00; font-weight: bold; padding: 8px; "
                        "background-color: #f0fff0; border-radius: 4px;"
                    )
            else:
                if self.server_status_label:
                    self.server_status_label.setText(f"⚠️ {status_text} (未就绪)")
                    self.server_status_label.setStyleSheet(
                        "color: #ff6600; font-weight: bold; padding: 8px; "
                        "background-color: #fff8f0; border-radius: 4px;"
                    )

            self.logger.debug(f"服务器状态已更新: {status_text}")

        except Exception as e:
            self.logger.error("处理服务器状态事件失败: %s", e, exc_info=True)

    def _fetch_initial_server_status(self):
        """获取初始服务器状态（主动Pull模式）

        解决启动时服务器池已完成测速但前端还未创建的时序问题。
        采用Pull-Push混合模式：启动时主动查询，后续依赖事件推送。
        """
        try:
            if not self.data_center_service:
                self.logger.warning("数据中心服务未初始化，跳过初始服务器状态查询")
                return

            # 从后端查询当前服务器状态
            status = self.data_center_service.get_server_status()
            available = status.get("available_count", 0)
            total = status.get("total_count", 0)
            status_str = status.get("status", "unknown")

            # 手动更新UI显示
            status_text = f"可用服务器: {available}/{total}"
            if status_str == "available" and available > 0:
                if self.server_status_label:
                    self.server_status_label.setText(f"✅ {status_text}")
                    self.server_status_label.setStyleSheet(
                        "color: #00aa00; font-weight: bold; padding: 8px; "
                        "background-color: #f0fff0; border-radius: 4px;"
                    )
                self.logger.info(f"✅ 获取初始服务器状态: {status_text}")
            else:
                if self.server_status_label:
                    self.server_status_label.setText(f"⚠️ {status_text} (未就绪)")
                    self.server_status_label.setStyleSheet(
                        "color: #ff6600; font-weight: bold; padding: 8px; "
                        "background-color: #fff8f0; border-radius: 4px;"
                    )
                self.logger.debug(f"服务器状态未就绪: {status_text}")  # 降级为DEBUG

        except Exception as e:
            self.logger.error("获取初始服务器状态失败: %s", e, exc_info=True)
            if self.server_status_label:
                self.server_status_label.setText("⚠️ 可用服务器: 获取失败")
                self.server_status_label.setStyleSheet(
                    "color: #cc0000; font-weight: bold; padding: 8px; "
                    "background-color: #fff0f0; border-radius: 4px;"
                )

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 注销事件监听器
        self._unregister_event_handlers()
        # 调用父类方法
        super().closeEvent(event)

    def _on_download_event(self, event: Event):
        """处理下载事件（vnpy事件回调）

        🆕 简化版：只更新进度条、状态标签、总进度统计
        - 减少文本输出频率，避免UI卡顿
        - 使用 append() 而非 setText()，性能更好
        """
        try:
            event_data = event.data
            status = event_data.get("status")

            if status == "progress":
                # 进度更新事件
                progress_pct = event_data.get("progress", 0)
                completed = event_data.get("completed", 0)
                total = event_data.get("total", 0)
                current_item = event_data.get("current_item", "")

                # 1. 更新进度条（每次都更新）
                if self.download_progress:
                    self.download_progress.setMaximum(total)
                    self.download_progress.setValue(completed)

                # 2. 更新状态标签（每次都更新）
                if self.progress_label:
                    self.progress_label.setText(
                        f"📥 下载中: {completed}/{total} ({progress_pct:.1f}%)"
                    )

                # 3. 文本日志（降低频率，仅关键节点）
                should_log = (
                    completed == 1  # 第一个
                    or completed == total  # 最后一个
                    or completed % 500 == 0  # 每500个输出一次
                )

                if should_log and self.progress_text:
                    log_text = f"[{completed}/{total}] {progress_pct:.1f}% - {current_item}"
                    self._append_progress_text(log_text)

            elif status == "success":
                # 下载成功完成
                count = event_data.get("count", 0)
                self.logger.info("✅ 下载完成事件：%d 个数据集", count)

                # 更新UI
                if self.download_progress:
                    self.download_progress.setValue(self.download_progress.maximum())
                if self.progress_label:
                    self.progress_label.setText(f"✅ 下载完成：{count} 个数据集")

                # 输出完成摘要
                self._append_progress_text("")
                self._append_progress_text("=" * 50)
                self._append_progress_text(f"✅ 下载完成，共成功保存 {count} 个数据集")
                self._append_progress_text("=" * 50)

                # 重置状态
                self._reset_download_state()
                self.show_info(f"✅ 下载任务已全部完成！共 {count} 个数据集")

            elif status == "error":
                # 下载失败
                error_msg = event_data.get("error", "未知错误")
                self.logger.error("❌ 下载失败事件：%s", error_msg)

                if self.progress_label:
                    self.progress_label.setText("❌ 下载失败")

                # 输出失败摘要
                self._append_progress_text("")
                self._append_progress_text("=" * 50)
                self._append_progress_text(f"❌ 下载失败: {error_msg}")
                self._append_progress_text("=" * 50)

                self._reset_download_state()
                self.show_error(f"下载失败: {error_msg}")

            elif status == "stopped":
                # 下载被停止
                count = event_data.get("count", 0)
                self.logger.info("⛔ 下载停止事件：已完成 %d 个", count)

                if self.progress_label:
                    self.progress_label.setText(f"⛔ 下载已停止：{count} 个数据集")

                # 输出停止摘要
                self._append_progress_text("")
                self._append_progress_text("=" * 50)
                self._append_progress_text(f"⛔ 下载已停止，已完成 {count} 个数据集")
                self._append_progress_text("=" * 50)

                self._reset_download_state()
                self.show_info(f"下载已停止，已完成 {count} 个数据集")

        except Exception as e:
            self.logger.error("处理下载事件失败: %s", e, exc_info=True)

    def _append_progress_text(self, text: str):
        """追加进度文本到日志框（使用QPlainTextEdit + 批量更新）

        QPlainTextEdit专为大量文本设计，性能优异且不易触发递归重绘。
        配合批量更新进一步优化性能，避免高频UI刷新。

        注意：此方法通过QueuedConnection调用，已在主线程执行，可直接使用QTimer。

        Args:
            text: 要追加的文本
        """
        try:
            if not self.progress_text:
                return

            # 初始化缓冲区
            if not hasattr(self, "_progress_text_buffer"):
                self._progress_text_buffer = []
                self._progress_update_timer = None

            self._progress_text_buffer.append(text)

            # 启动批量更新定时器（200ms合并一次更新）
            # 由于通过QueuedConnection调用，此时已在主线程，可以直接创建QTimer
            if self._progress_update_timer is None:
                self._progress_update_timer = QTimer(self)
                self._progress_update_timer.setSingleShot(True)
                self._progress_update_timer.timeout.connect(self._flush_progress_text_buffer)
                self._progress_update_timer.start(200)
            elif not self._progress_update_timer.isActive():
                self._progress_update_timer.start(200)

        except Exception as e:
            self.logger.debug("追加进度文本失败: %s", e)

    def _flush_progress_text_buffer(self):
        """批量刷新进度文本缓冲区到UI"""
        try:
            if not self.progress_text or not hasattr(self, "_progress_text_buffer"):
                return

            if not self._progress_text_buffer:
                return

            # QPlainTextEdit的appendPlainText更高效且不会触发递归重绘
            # 批量追加所有文本
            batch_text = "\n".join(self._progress_text_buffer)
            self.progress_text.appendPlainText(batch_text)

            # 清空缓冲区
            self._progress_text_buffer.clear()

            # QPlainTextEdit的setMaximumBlockCount已自动限制行数，无需手动删除
            # 自动滚动到底部
            scrollbar = self.progress_text.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(scrollbar.maximum())

        except Exception as e:
            self.logger.debug("刷新进度文本缓冲区失败: %s", e)

    def _start_progress_polling(self):
        """启动进度轮询定时器（仅在事件引擎不可用时使用）"""
        # 同时启用事件推送与轮询，确保在任意环境下都有进度反馈
        if self.event_engine:
            self.logger.info(">>> 使用vnpy事件推送机制，并启动轮询做冗余")
        else:
            self.logger.info(">>> event_engine不可用，启动备用轮询机制")

        if self.progress_timer is None:
            self.progress_timer = QTimer(self)
            self.progress_timer.timeout.connect(self._update_download_progress)

        # 启动定时器，每1秒轮询一次
        if not self.progress_timer.isActive():
            self.progress_timer.start(1000)
            self.logger.info(">>> 进度轮询定时器已启动（每1秒更新）")

    def _stop_progress_polling(self):
        """停止进度轮询定时器"""
        if self.progress_timer and self.progress_timer.isActive():
            self.progress_timer.stop()
            self.logger.info(">>> 进度轮询定时器已停止")

    def _update_download_progress(self):
        """更新下载进度（定时器回调）"""
        try:
            if not self.data_center_service:
                return

            # 获取实时进度
            progress_data = self.data_center_service.get_download_progress()

            if not progress_data.get("success"):
                return

            is_downloading = progress_data.get("is_downloading", False)

            if not is_downloading:
                # 下载已完成，停止轮询
                self.logger.info(">>> 检测到下载完成，停止轮询并重置状态")
                self._stop_progress_polling()

                # 更新UI显示完成状态
                if self.download_progress:
                    self.download_progress.setValue(100)
                if self.progress_label:
                    self.progress_label.setText("✅ 下载完成")

                # 重置按钮状态
                self._reset_download_state()
                self.show_info("✅ 下载任务已全部完成！")
                return

            # 更新进度条和标签
            progress_pct = progress_data.get("progress", 0)
            completed = progress_data.get("completed", 0)
            total = progress_data.get("total", 0)
            current_symbol = progress_data.get("current_symbol", "")
            current_interval = progress_data.get("current_interval", "")

            if self.download_progress:
                self.download_progress.setValue(int(progress_pct))

            if self.progress_label:
                self.progress_label.setText(
                    f"📥 下载中: {completed}/{total} ({progress_pct:.1f}%) - 当前: {current_symbol} {current_interval}"
                )

        except Exception as e:
            self.logger.error(">>> 更新进度失败: %s", e)

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

            # 🔧 停止进度轮询定时器
            self._stop_progress_polling()

            # 清理线程引用（延迟清理，避免访问违例）
            if self.download_thread:
                self.logger.info(">>> 清理下载线程引用")
                download_thread_ref = self.download_thread

                # 如果线程还在运行，尝试断开信号连接
                try:
                    if download_thread_ref.isRunning():
                        # 🔧 使用try-except包裹每个disconnect，避免部分失败
                        try:
                            download_thread_ref.finished_signal.disconnect()
                        except Exception:
                            pass
                        try:
                            download_thread_ref.error_signal.disconnect()
                        except Exception:
                            pass
                        try:
                            download_thread_ref.progress_signal.disconnect()
                        except Exception:
                            pass

                        # 🔧 等待线程完成（最多等待1秒）
                        if not download_thread_ref.wait(1000):
                            self.logger.warning(">>> 下载线程未能在1秒内完成，强制清理")
                except Exception as e:
                    self.logger.debug(f">>> 清理线程时出现异常: {e}")

                # 🔧 延迟清理：使用QTimer延迟释放线程对象
                def delayed_cleanup():
                    try:
                        if (
                            hasattr(self, "download_thread")
                            and self.download_thread is download_thread_ref
                        ):
                            self.download_thread = None
                            self.logger.debug(">>> 延迟清理：线程对象已释放")
                    except Exception as cleanup_err:
                        self.logger.debug(f">>> 延迟清理失败: {cleanup_err}")

                QTimer.singleShot(500, delayed_cleanup)  # 500ms后清理

            # 清理任务ID
            if hasattr(self, "current_download_task_id"):
                self.logger.info(
                    ">>> 清理任务ID: %s", getattr(self, "current_download_task_id", None)
                )
                self.current_download_task_id = None

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

    # ==================== 下载历史管理 ====================

    def _load_download_history_from_database(self):
        """从数据库加载历史记录."""
        try:
            if not self.db_manager:
                self.logger.warning("数据库管理器不可用，无法加载历史记录")
                return

            # 从数据库获取历史记录
            db_records = self.db_manager.get_download_history(limit=self.max_history_records)

            if not db_records:
                self.logger.info("数据库中没有下载历史记录")
                return

            # 清空当前历史
            self.download_history.clear()
            if self.history_tab_widget:
                # 清除所有选项卡
                while self.history_tab_widget.count() > 0:
                    self.history_tab_widget.removeTab(0)

            # 加载数据库记录到内存和UI
            for db_record in reversed(db_records):  # 反转，最旧的先添加
                # 转换数据库记录为内存格式
                record = {
                    "id": db_record["id"],  # 保存数据库ID用于删除
                    "task_id": db_record["task_id"],
                    "start_time": (
                        datetime.fromisoformat(db_record["start_time"])
                        if isinstance(db_record["start_time"], str)
                        else db_record["start_time"]
                    ),
                    "end_time": (
                        datetime.fromisoformat(db_record["end_time"])
                        if isinstance(db_record["end_time"], str)
                        else db_record["end_time"]
                    ),
                    "duration": db_record["duration"],
                    "status": db_record["status"],
                    "total_tasks": db_record["total_tasks"],
                    "completed_tasks": db_record["completed_tasks"],
                    "success_count": db_record["success_count"],
                    "failed_count": db_record["failed_count"],
                    "skipped_count": db_record["skipped_count"],
                    "start_date": db_record["start_date"],
                    "message": db_record["message"],
                    "log_text": db_record["log_text"],
                }

                self.download_history.append(record)
                self._update_history_tabs()

            self.logger.info("从数据库加载了 %d 条下载历史记录", len(db_records))

        except Exception as e:
            self.logger.error(f"从数据库加载历史记录失败: {e}", exc_info=True)

    def _add_download_history(self, result: Dict[str, Any]):
        """添加下载历史记录（保存到数据库）.

        Args:
            result: 下载结果字典
        """
        try:
            # 从result和当前状态构建历史记录
            record = {
                "task_id": result.get("task_id", "N/A"),
                "start_time": getattr(self.download_thread, "start_time", datetime.now()),
                "end_time": datetime.now(),
                "duration": getattr(self.download_thread, "duration", 0),
                "status": "success" if result.get("success") else "failed",
                "total_tasks": result.get("total_tasks", 0),
                "completed_tasks": result.get("completed_tasks", 0),
                "success_count": result.get("success_count", 0),
                "failed_count": result.get("failed_count", 0),
                "skipped_count": result.get("skipped_count", 0),
                "start_date": result.get("start_date", ""),
                "message": result.get("message", ""),
                "log_text": self.progress_text.toPlainText() if self.progress_text else "",
            }

            # 🆕 保存到数据库
            if self.db_manager:
                if self.db_manager.save_download_history(record):
                    # 自动清理旧记录（只保留最近20条）
                    self.db_manager.cleanup_old_download_history(
                        keep_count=self.max_history_records
                    )

                    # 从数据库重新加载以获取ID
                    latest_records = self.db_manager.get_download_history(limit=1)
                    if latest_records:
                        record["id"] = latest_records[0]["id"]
                else:
                    self.logger.warning("历史记录未能保存到数据库")
            else:
                self.logger.warning("数据库管理器不可用，历史记录仅保存在内存中")

            # 限制内存中的历史记录数量（最多20条）
            if len(self.download_history) >= self.max_history_records:
                # 删除最旧的记录
                self.download_history.pop(0)
                if self.history_tab_widget and self.history_tab_widget.count() > 0:
                    # 如果第一个是空提示tab，不删除
                    if self.history_tab_widget.isTabEnabled(0):
                        self.history_tab_widget.removeTab(0)

            # 添加到内存列表
            self.download_history.append(record)

            # 更新UI
            self._update_history_tabs()

            self.logger.info("已添加下载历史记录: %s", record.get("task_id"))

        except Exception as e:
            self.logger.error(f"添加下载历史失败: {e}", exc_info=True)

    def _update_history_tabs(self):
        """更新历史选项卡显示."""
        try:
            if not self.history_tab_widget:
                return

            # 如果是首次添加，清除空提示
            if self.history_tab_widget.count() == 1 and not self.history_tab_widget.isTabEnabled(0):
                self.history_tab_widget.clear()

            # 添加最新的历史记录选项卡
            if self.download_history:
                latest_record = self.download_history[-1]
                detail_widget = self._create_history_detail_widget(latest_record)

                # 选项卡标题：时间 + 状态emoji
                status = latest_record.get("status", "unknown")
                status_emoji = "✓" if status == "success" else "✗"
                start_time = latest_record.get("start_time")
                if isinstance(start_time, datetime):
                    tab_title = f"{status_emoji} {start_time.strftime('%H:%M:%S')}"
                else:
                    tab_title = f"{status_emoji} {start_time}"

                self.history_tab_widget.addTab(detail_widget, tab_title)
                self.history_tab_widget.setCurrentIndex(self.history_tab_widget.count() - 1)

                self.logger.info("已添加历史选项卡: %s", tab_title)

        except Exception as e:
            self.logger.error(f"更新历史选项卡失败: {e}", exc_info=True)

    def _on_delete_history(self, index: int):
        """删除指定的历史记录（从数据库和内存）.

        Args:
            index: 选项卡索引
        """
        try:
            if 0 <= index < len(self.download_history):
                # 获取记录
                record = self.download_history[index]

                # 🆕 从数据库删除
                if self.db_manager and "id" in record:
                    if not self.db_manager.delete_download_history(record["id"]):
                        self.logger.warning("从数据库删除历史记录失败")

                # 从内存列表中删除
                del self.download_history[index]

                # 从UI中删除
                if self.history_tab_widget:
                    self.history_tab_widget.removeTab(index)

                    # 如果删除后为空，显示空提示
                    if self.history_tab_widget.count() == 0:
                        empty_widget = QWidget()
                        empty_layout = QVBoxLayout(empty_widget)
                        empty_label = QLabel("暂无下载历史")
                        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        empty_label.setStyleSheet("color: #666; font-size: 13px; padding: 50px;")
                        empty_layout.addWidget(empty_label)
                        self.history_tab_widget.addTab(empty_widget, "空")
                        self.history_tab_widget.setTabEnabled(0, False)

                self.logger.info(f"已删除下载历史记录，索引: {index}, 数据库ID: {record.get('id')}")

        except Exception as e:
            self.logger.error(f"删除历史记录失败: {e}", exc_info=True)

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
                    # 只保留轮询转推送和虚拟推送
                    source_list = [
                        {"id": "polling_gateway", "name": "轮询转推送", "type": "本地"},
                        {"id": "virtual_gateway", "name": "虚拟推送", "type": "本地"},
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

                        # 操作按钮容器
                        button_widget = QWidget()
                        button_layout = QHBoxLayout(button_widget)
                        button_layout.setContentsMargins(5, 5, 5, 5)  # 增加边距，让按钮更舒适
                        button_layout.setSpacing(8)  # 增加按钮间距

                        # 对于polling_gateway和virtual_gateway，添加配置按钮
                        if source_id in ["polling_gateway", "virtual_gateway"]:
                            config_btn = QPushButton("配置")
                            config_btn.setMinimumHeight(32)  # 设置按钮最小高度
                            config_btn.setMinimumWidth(60)  # 设置按钮最小宽度
                            config_btn.clicked.connect(
                                lambda _checked, sid=source_id: self._configure_gateway(sid)
                            )
                            button_layout.addWidget(config_btn)

                            # 启动/停止按钮
                            if connected:
                                stop_btn = QPushButton("停止")
                                stop_btn.setMinimumHeight(32)  # 设置按钮最小高度
                                stop_btn.setMinimumWidth(60)  # 设置按钮最小宽度
                                stop_btn.clicked.connect(
                                    lambda _checked, sid=source_id: self._stop_gateway(sid)
                                )
                                button_layout.addWidget(stop_btn)
                            else:
                                start_btn = QPushButton("启动")
                                start_btn.setMinimumHeight(32)  # 设置按钮最小高度
                                start_btn.setMinimumWidth(60)  # 设置按钮最小宽度
                                start_btn.clicked.connect(
                                    lambda _checked, sid=source_id: self._start_gateway(sid)
                                )
                                button_layout.addWidget(start_btn)
                        else:
                            # 其他数据源保持原有的连接/断开按钮
                            connect_btn = QPushButton("连接" if not connected else "断开")
                            connect_btn.setMinimumHeight(32)  # 设置按钮最小高度
                            connect_btn.setMinimumWidth(60)  # 设置按钮最小宽度
                            connect_btn.clicked.connect(
                                lambda _checked, sid=source_id, conn=connected: (
                                    self._toggle_source_connection(sid, conn)
                                )
                            )
                            button_layout.addWidget(connect_btn)

                        self.sources_table.setCellWidget(i, 4, button_widget)

                    # 设置表格行高以适应按钮高度
                    for row in range(self.sources_table.rowCount()):
                        self.sources_table.setRowHeight(row, 45)  # 设置行高以适应按钮

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

    def _configure_gateway(self, gateway_id: str):
        """配置网关."""
        try:
            from PySide6.QtWidgets import QDateTimeEdit
            from PySide6.QtCore import QDateTime

            if gateway_id == "polling_gateway":
                # 轮询网关配置对话框
                dialog = QDialog(self)
                dialog.setWindowTitle("配置轮询转推送网关")
                dialog.setMinimumWidth(500)

                layout = QFormLayout(dialog)

                # 轮询间隔
                interval_spin = QSpinBox()
                interval_spin.setRange(1, 600)
                interval_spin.setValue(60)
                interval_spin.setSuffix(" 秒")
                layout.addRow("轮询间隔:", interval_spin)

                # 订阅品种
                symbols_input = QLineEdit()
                symbols_input.setPlaceholderText("例如: 600000,000001,000002")
                layout.addRow("订阅品种:", symbols_input)

                # 按钮
                button_box = QDialogButtonBox(
                    QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
                )
                button_box.accepted.connect(dialog.accept)
                button_box.rejected.connect(dialog.reject)
                layout.addWidget(button_box)

                if dialog.exec() == QDialog.DialogCode.Accepted:
                    # 保存配置到实例变量
                    self.polling_gateway_config = {
                        "interval": interval_spin.value(),
                        "symbols": [
                            s.strip() for s in symbols_input.text().split(",") if s.strip()
                        ],
                    }
                    self.show_info("轮询网关配置已保存")

            elif gateway_id == "virtual_gateway":
                # 虚拟网关配置对话框
                dialog = QDialog(self)
                dialog.setWindowTitle("配置虚拟推送网关")
                dialog.setMinimumWidth(500)

                layout = QFormLayout(dialog)

                # 起始时间
                datetime_edit = QDateTimeEdit()
                datetime_edit.setCalendarPopup(True)
                datetime_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
                datetime_edit.setDateTime(QDateTime.currentDateTime().addMonths(-1))
                layout.addRow("起始时间:", datetime_edit)

                # 推送速度
                speed_spin = QDoubleSpinBox()
                speed_spin.setRange(0.1, 10.0)
                speed_spin.setValue(1.0)
                speed_spin.setSingleStep(0.1)
                speed_spin.setSuffix(" 倍")
                layout.addRow("推送速度:", speed_spin)

                # 订阅品种
                symbols_input = QLineEdit()
                symbols_input.setPlaceholderText("例如: 600000,000001,000002")
                layout.addRow("订阅品种:", symbols_input)

                # 按钮
                button_box = QDialogButtonBox(
                    QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
                )
                button_box.accepted.connect(dialog.accept)
                button_box.rejected.connect(dialog.reject)
                layout.addWidget(button_box)

                if dialog.exec() == QDialog.DialogCode.Accepted:
                    # 保存配置到实例变量
                    self.virtual_gateway_config = {
                        "start_datetime": datetime_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
                        "speed": speed_spin.value(),
                        "symbols": [
                            s.strip() for s in symbols_input.text().split(",") if s.strip()
                        ],
                    }
                    self.show_info("虚拟网关配置已保存")

        except Exception as e:
            self.logger.error("配置网关失败: %s", e)
            self.show_error(f"配置失败: {e}")

    def _start_gateway(self, gateway_id: str):
        """启动网关."""
        try:
            if not self.data_center_service:
                self.show_error("数据中心服务不可用")
                return

            if gateway_id == "polling_gateway":
                # 检查是否已配置
                config = getattr(self, "polling_gateway_config", None)
                if not config:
                    self.show_warning("请先配置轮询网关")
                    return

                # 启动网关
                result = self.data_center_service.start_polling_gateway(config)

                if result["success"]:
                    self.show_info("轮询网关启动成功")
                    self._load_data_sources()
                else:
                    self.show_error(f"启动失败: {result.get('message', '未知错误')}")

            elif gateway_id == "virtual_gateway":
                # 检查是否已配置
                config = getattr(self, "virtual_gateway_config", None)
                if not config:
                    self.show_warning("请先配置虚拟网关")
                    return

                # 启动网关
                result = self.data_center_service.start_virtual_gateway(config)

                if result["success"]:
                    self.show_info("虚拟网关启动成功")
                    self._load_data_sources()
                else:
                    self.show_error(f"启动失败: {result.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error("启动网关失败: %s", e)
            self.show_error(f"启动失败: {e}")

    def _stop_gateway(self, gateway_id: str):
        """停止网关."""
        try:
            if not self.data_center_service:
                self.show_error("数据中心服务不可用")
                return

            if gateway_id == "polling_gateway":
                result = self.data_center_service.stop_polling_gateway()
            elif gateway_id == "virtual_gateway":
                result = self.data_center_service.stop_virtual_gateway()
            else:
                self.show_error(f"未知网关: {gateway_id}")
                return

            if result["success"]:
                self.show_info("网关已停止")
                self._load_data_sources()
            else:
                self.show_error(f"停止失败: {result.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error("停止网关失败: %s", e)
            self.show_error(f"停止失败: {e}")

    # ==================== 通用方法 ====================

    def connect_signals(self):
        """连接信号槽."""

    def refresh_data(self):
        """刷新数据."""
        self._refresh_symbols()

    def on_close(self):
        """关闭处理."""
        self.logger.info("数据中心界面已关闭")

    # ==================== 数据质量概览方法 ====================

    def _load_quality_overview_with_retry(self) -> None:
        """带重试的加载质量概览（初始化时调用）"""
        try:
            # 检查服务是否可用
            if not self.data_center_service:
                self.logger.debug("数据中心服务不可用，跳过质量概览加载")
                return

            # 检查china_stock_engine是否可用
            if not hasattr(self.data_center_service, "china_stock_engine"):
                self.logger.debug("china_stock_engine属性不存在，跳过质量概览加载")
                return

            if not self.data_center_service.china_stock_engine:
                self.logger.debug("china_stock_engine不可用，稍后重试...")
                # 3秒后重试一次
                QTimer.singleShot(3000, self._load_quality_overview_with_retry)
                return

            # 服务可用，开始加载
            self._load_quality_overview_async()

        except Exception as e:
            self.logger.debug("初始化质量概览失败（静默处理）: %s", e)

    def _load_quality_overview_async(self) -> None:
        """异步加载数据质量概览（不阻塞UI，带状态指示）"""
        import threading
        from PySide6.QtCore import QTimer

        # 🆕 直接设置为"正在扫描"状态（已在主线程）
        self._set_quality_scan_status(True)

        def load_in_background():
            try:
                self.logger.info("【后台】开始加载数据质量概览...")

                if not self.data_center_service:
                    self.logger.warning("【后台】数据中心服务不可用")
                    # 🆕 服务不可用时重置状态
                    QTimer.singleShot(0, lambda: self._set_quality_scan_status(False))
                    return

                result = self.data_center_service.get_data_quality_overview()

                if result.get("success"):
                    # 🆕 更新UI并重置状态（在主线程中执行）
                    QTimer.singleShot(
                        0,
                        lambda: [
                            self._update_quality_overview_ui(result),
                            self._set_quality_scan_status(False),
                        ],
                    )
                    self.logger.info("【后台】质量概览加载完成")
                else:
                    self.logger.warning("【后台】质量概览加载失败: %s", result.get("message"))
                    # 🆕 加载失败时重置状态
                    QTimer.singleShot(0, lambda: self._set_quality_scan_status(False))

            except Exception as e:
                self.logger.error("【后台】加载质量概览异常: %s", e, exc_info=True)
                # 🆕 异常时重置状态
                QTimer.singleShot(0, lambda: self._set_quality_scan_status(False))

        # 启动后台线程
        load_thread = threading.Thread(
            target=load_in_background, daemon=True, name="LoadQualityOverviewThread"
        )
        load_thread.start()

    def _set_quality_scan_status(self, scanning: bool) -> None:
        """设置质量扫描状态指示器

        Args:
            scanning: True=正在扫描，False=扫描完成
        """
        if not hasattr(self, "quality_scan_status_label"):
            self.logger.warning("quality_scan_status_label 未初始化，无法设置状态")
            return

        if self.quality_scan_status_label is None:
            self.logger.warning("quality_scan_status_label 为 None，无法设置状态")
            return

        try:
            if scanning:
                # 正在扫描：显示转圈图标
                self.quality_scan_status_label.setText("🔄")
                self.quality_scan_status_label.setStyleSheet("color: #2196F3; font-size: 14px;")
                self.quality_scan_status_label.setToolTip("正在进行数据质量感知...")
                self.logger.info("✓ 状态指示器：正在扫描")
            else:
                # 扫描完成：显示绿色对勾
                self.quality_scan_status_label.setText("✅")
                self.quality_scan_status_label.setStyleSheet("color: #4CAF50; font-size: 14px;")
                self.quality_scan_status_label.setToolTip("数据质量感知已完成")
                self.logger.info("✓ 状态指示器：扫描完成")
        except Exception as e:
            self.logger.error("设置状态指示器失败: %s", e, exc_info=True)

    def _refresh_quality_overview(self) -> None:
        """手动刷新数据质量概览（触发后端重新扫描）"""
        try:
            self.logger.info("手动刷新数据质量概览...")

            # 🆕 设置为"正在扫描"状态
            self._set_quality_scan_status(True)

            if not self.data_center_service:
                self.show_error("数据中心服务未初始化")
                self._set_quality_scan_status(False)
                return

            # 🆕 调用后端触发扫描（force_refresh=True）
            success = self.data_center_service.trigger_data_quality_scan(force_refresh=True)

            if success:
                self.show_info("数据质量扫描已触发，等待结果推送...")
                self.logger.info("✓ 已触发后端数据质量扫描")
            else:
                self.show_warning("触发扫描失败，请检查后端服务状态")
                self._set_quality_scan_status(False)  # 🆕 失败时重置状态

        except Exception as e:
            self.logger.error("触发数据质量扫描失败: %s", e, exc_info=True)
            self.show_error(f"刷新失败: {e}")
            self._set_quality_scan_status(False)  # 🆕 异常时重置状态

    def _update_quality_overview_ui(self, overview_data: dict) -> None:
        """更新质量概览UI显示

        Args:
            overview_data: 质量概览数据
        """
        try:
            # 更新各标签
            total = overview_data.get("total_symbols", 0)
            local = overview_data.get("local_symbols", 0)  # 🚀 新增
            missing = overview_data.get("missing_symbols", 0)
            errors = overview_data.get("error_symbols", 0)
            warnings = overview_data.get("warning_symbols", 0)
            score = overview_data.get("quality_score", 0)

            # 🆕 数据更新状态
            outdated = overview_data.get("outdated_symbols", 0)
            avg_gap = overview_data.get("avg_gap_days", 0)

            # 🚀 更新显示
            if self.total_symbols_label:
                self.total_symbols_label.setText(f"总品种: {total}")

            # 🚀 更新已下载品种数（本地有数据的品种数）
            if self.downloaded_symbols_label:
                self.downloaded_symbols_label.setText(f"已下载: {local}")

            if self.missing_symbols_label:
                self.missing_symbols_label.setText(f"缺失: {missing}")

            if self.error_symbols_label:
                self.error_symbols_label.setText(f"错误: {errors}")

            if self.warning_symbols_label:
                self.warning_symbols_label.setText(f"警告: {warnings}")

            # 🆕 更新过时品种数
            if self.outdated_symbols_label:
                self.outdated_symbols_label.setText(f"过时: {outdated}")

            # 🆕 更新平均滞后天数
            if self.avg_gap_label:
                if avg_gap > 0:
                    self.avg_gap_label.setText(f"平均滞后: {avg_gap}天")
                    # 根据滞后天数设置颜色
                    if avg_gap <= 1:
                        self.avg_gap_label.setStyleSheet("color: #4CAF50;")  # 绿色
                    elif avg_gap <= 5:
                        self.avg_gap_label.setStyleSheet("color: #FFC107;")  # 黄色
                    else:
                        self.avg_gap_label.setStyleSheet("color: #F44336;")  # 红色
                else:
                    self.avg_gap_label.setText("平均滞后: --")
                    self.avg_gap_label.setStyleSheet("")

            if self.quality_score_label:
                # 根据评分设置颜色
                if score >= 90:
                    color = "#4CAF50"  # 绿色
                    icon = "✅"
                elif score >= 70:
                    color = "#FFC107"  # 黄色
                    icon = "⚠️"
                else:
                    color = "#F44336"  # 红色
                    icon = "❌"

                self.quality_score_label.setText(f"{icon} 评分: {score}")
                self.quality_score_label.setStyleSheet(f"color: {color}; font-weight: bold;")

            # 更新详情表格（如果展开）
            if self.toggle_quality_detail_btn and self.toggle_quality_detail_btn.isChecked():
                self._update_quality_detail_table(overview_data.get("details", []))

            # 🎯 新增：联动更新本地数据状态组件
            if self.data_status_label:
                self.data_status_label.setText(f"本地数据: {local}/{total} 个品种已下载")

            if self.data_quality_label:
                self.data_quality_label.setText(f"全局质量评分: {score}/100")

            # 🎯 新增：根据全局质量问题显示/隐藏修复按钮
            if self.repair_data_btn:
                has_issues = errors > 0 or warnings > 0
                self.repair_data_btn.setVisible(has_issues)

            self.logger.info("质量概览UI已更新（含本地状态联动）")

        except Exception as e:
            self.logger.error("更新质量概览UI失败: %s", e, exc_info=True)

    def _toggle_quality_detail(self, checked: bool) -> None:
        """展开/折叠质量详情表格

        Args:
            checked: 是否展开
        """
        try:
            if self.quality_detail_table:
                self.quality_detail_table.setVisible(checked)

                # 如果展开，加载详情数据
                if checked:
                    # 获取最新概览数据
                    if self.data_center_service:
                        result = self.data_center_service.get_data_quality_overview()
                        if result.get("success"):
                            details = result.get("details", [])
                            self._update_quality_detail_table(details)

        except Exception as e:
            self.logger.error("切换质量详情失败: %s", e, exc_info=True)

    def _get_status_info(self, detail: dict) -> tuple:
        """获取状态信息（文本、图标、排序键）

        Args:
            detail: 品种详情字典

        Returns:
            tuple: (status_text, status_icon, sort_key)
        """
        status = detail.get("status", "normal")

        status_map = {
            "missing": ("缺失", "❌", 1),
            "error": ("错误", "🔴", 2),
            "warning": ("警告", "⚠️", 3),
            "normal": ("正常", "✅", 4),
        }

        return status_map.get(status, ("未知", "❓", 5))

    def _update_quality_detail_table(self, details: list) -> None:
        """更新质量详情表格（只显示有问题的品种）

        Args:
            details: 详情列表（后端已过滤为有问题的品种并排序）
        """
        try:
            if not self.quality_detail_table:
                return

            # 清空表格
            self.quality_detail_table.setRowCount(0)

            # 🆕 检查是否有问题品种
            if not details:
                # 🆕 无问题时显示友好提示
                self.quality_detail_table.insertRow(0)
                no_issue_item = QTableWidgetItem("🎉 所有品种数据质量良好，无需修复")
                no_issue_item.setForeground(Qt.GlobalColor.darkGreen)
                self.quality_detail_table.setItem(0, 0, no_issue_item)
                self.quality_detail_table.setSpan(0, 0, 1, 4)  # 合并单元格
                self.logger.info("质量详情表格：无问题品种")
                return

            self.logger.info("质量详情表格：显示 %d 个有问题的品种", len(details))

            # 填充数据（后端已过滤并排序）
            for i, detail in enumerate(details):
                self.quality_detail_table.insertRow(i)

                # 第1列：品种代码
                symbol = detail.get("symbol", "")
                self.quality_detail_table.setItem(i, 0, QTableWidgetItem(symbol))

                # 第2列：状态（带图标和颜色）
                status_text, status_icon, _ = self._get_status_info(detail)
                status_item = QTableWidgetItem(f"{status_icon} {status_text}")

                # 根据状态设置颜色
                status = detail.get("status", "normal")
                if status == "missing":
                    status_item.setForeground(Qt.GlobalColor.red)
                elif status == "error":
                    status_item.setForeground(Qt.GlobalColor.red)
                elif status == "warning":
                    status_item.setForeground(Qt.GlobalColor.darkYellow)
                else:
                    status_item.setForeground(Qt.GlobalColor.darkGreen)

                self.quality_detail_table.setItem(i, 1, status_item)

                # 第3列：质量评分（保持颜色标识）
                score = detail.get("score", 0)
                score_item = QTableWidgetItem(str(score))

                # 根据评分设置背景颜色
                if score >= 80:
                    score_item.setBackground(Qt.GlobalColor.green)
                elif score >= 60:
                    score_item.setBackground(Qt.GlobalColor.yellow)
                else:
                    score_item.setBackground(Qt.GlobalColor.red)

                self.quality_detail_table.setItem(i, 2, score_item)

                # 🆕 第4列：问题描述（使用后端返回的issues字段）
                issues_text = detail.get("issues", "无问题")

                # 截取前50个字符显示
                brief_desc = issues_text[:50] + "..." if len(issues_text) > 50 else issues_text

                desc_item = QTableWidgetItem(brief_desc)

                # 🆕 设置Tooltip显示完整问题描述
                desc_item.setToolTip(issues_text)

                self.quality_detail_table.setItem(i, 3, desc_item)

            self.logger.info("质量详情表格已更新: %d 条记录", len(details))

        except Exception as e:
            self.logger.error("更新质量详情表格失败: %s", e, exc_info=True)

    def _on_data_quality_update(self, event: Event) -> None:
        """处理数据质量更新事件（vnpy事件回调）

        Args:
            event: vnpy事件对象
        """
        try:
            data = event.data

            # 🆕 检查是否是整体概览更新（包含total_symbols字段）
            if "total_symbols" in data:
                # 整体概览更新
                self.logger.info("✅ 收到数据质量整体概览更新事件")

                # 直接使用事件数据更新UI
                self._update_quality_overview_ui(
                    {
                        "success": True,
                        "total_symbols": data.get("total_symbols", 0),
                        "local_symbols": data.get("local_symbols", 0),
                        "missing_symbols": data.get("missing_symbols", 0),
                        "error_symbols": data.get("error_symbols", 0),
                        "warning_symbols": data.get("warning_symbols", 0),
                        "quality_score": data.get("quality_score", 0),
                    }
                )

                # 🆕 扫描完成，重置状态指示器
                self._set_quality_scan_status(False)
            else:
                # 单个品种更新（旧格式兼容）
                symbol = data.get("symbol")
                score = data.get("score", 0)
                self.logger.debug("收到单品种质量更新: symbol=%s, score=%s", symbol, score)
                # 增量更新：重新加载整体概览
                self._load_quality_overview_async()

        except Exception as e:
            self.logger.error("处理质量更新事件失败: %s", e, exc_info=True)

    def _on_data_scan_complete(self, event: Event) -> None:
        """处理数据质量扫描完成事件（vnpy事件回调）

        Args:
            event: vnpy事件对象
        """
        try:
            event_data = event.data
            total = event_data.get("total_symbols", 0)
            score = event_data.get("quality_score", 0)

            self.logger.info("收到扫描完成事件: 总品种=%s, 评分=%s", total, score)

            # 刷新UI显示
            if self.data_center_service is not None:
                result = self.data_center_service.get_data_quality_overview()
                if result.get("success"):
                    self._update_quality_overview_ui(result)
                    self.logger.info("质量概览已自动更新")
                    # 静默更新，不显示提示（避免干扰用户）

            # 🆕 扫描完成，重置状态指示器
            self._set_quality_scan_status(False)

        except Exception as e:
            self.logger.error("处理扫描完成事件失败: %s", e)
