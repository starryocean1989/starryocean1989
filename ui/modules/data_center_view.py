# -*- coding: utf-8 -*-
"""数据中心界面 - 主视图（重构版）.

标准架构：4个子界面采用选项卡形式。
合并tabs/handlers/utils逻辑，统一backend调用。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDate, QThread, QTimer, Signal, Qt
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

SYMBOLS_TABLE_HEADERS = ["品种代码", "品种名称", "交易所", "类型", "状态", "操作"]
LOCAL_DATA_TABLE_HEADERS = ["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "成交额"]
DOWNLOAD_PROGRESS_TABLE_HEADERS = ["品种", "周期", "进度", "状态"]
SOURCES_TABLE_HEADERS = ["数据源", "类型", "状态", "连接数", "操作"]


# ==================== 服务器配置对话框 ====================


class ServerConfigDialog(QDialog):
    """服务器配置对话框."""

    def __init__(self, data_center_service, parent=None):
        """初始化服务器配置对话框.

        Args:
            data_center_service: 数据中心服务实例
            parent: 父窗口
        """
        super().__init__(parent)
        self.data_center_service = data_center_service
        self.setWindowTitle("服务器配置")
        self.setMinimumWidth(500)

        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        """设置用户界面."""
        layout = QVBoxLayout(self)

        # 说明标签
        info_label = QLabel(
            "配置多服务器并行下载参数。\n" "多个服务器可以同时下载不同品种的数据，提高下载速度。"
        )
        info_label.setStyleSheet("color: #666; padding: 10px; background-color: #f0f0f0;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 表单布局
        form_layout = QFormLayout()

        # 并行服务器数量
        self.server_count_spin = QSpinBox()
        self.server_count_spin.setRange(1, 30)
        self.server_count_spin.setValue(5)
        self.server_count_spin.setSuffix(" 个")
        self.server_count_spin.setToolTip("同时使用的服务器数量（1-30）")
        form_layout.addRow("并行服务器数量:", self.server_count_spin)

        # 连接超时时间
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setValue(30)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setToolTip("单个请求的超时时间（5-120秒）")
        form_layout.addRow("连接超时时间:", self.timeout_spin)

        # 重试次数
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(3)
        self.retry_spin.setSuffix(" 次")
        self.retry_spin.setToolTip("下载失败后的重试次数（0-10次）")
        form_layout.addRow("重试次数:", self.retry_spin)

        layout.addLayout(form_layout)

        # 提示信息
        hint_label = QLabel(
            "💡 提示：\n"
            "• 服务器数量越多，下载速度越快，但也会增加网络负载\n"
            "• 建议服务器数量设置为 3-10 个\n"
            "• 如果网络不稳定，可以适当增加超时时间和重试次数"
        )
        hint_label.setStyleSheet("color: #888; font-size: 11px; padding: 10px;")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._save_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_config(self):
        """加载当前配置."""
        try:
            # 从 data_center_service 获取配置
            if self.data_center_service and hasattr(self.data_center_service, "china_stock_engine"):
                engine = self.data_center_service.china_stock_engine
                if engine:
                    # 从 config_manager 读取配置
                    from backend.infrastructure.data_module_vnpy.config import config_manager

                    server_pool_size = config_manager.get("chinastock.server_pool_size", 5)
                    timeout = config_manager.get("chinastock.timeout", 30)
                    retry_times = config_manager.get("chinastock.retry_times", 3)

                    self.server_count_spin.setValue(int(server_pool_size))
                    self.timeout_spin.setValue(int(timeout))
                    self.retry_spin.setValue(int(retry_times))

        except Exception as e:
            import logging

            logging.getLogger(__name__).error("加载服务器配置失败: %s", e)

    def _save_and_accept(self):
        """保存配置并关闭对话框."""
        try:
            # 获取配置值
            server_pool_size = self.server_count_spin.value()
            timeout = self.timeout_spin.value()
            retry_times = self.retry_spin.value()

            # 保存到 config_manager
            from backend.infrastructure.data_module_vnpy.config import config_manager

            config_manager.set("chinastock.server_pool_size", server_pool_size)
            config_manager.set("chinastock.timeout", timeout)
            config_manager.set("chinastock.retry_times", retry_times)

            # 显示成功消息
            QMessageBox.information(
                self,
                "配置保存成功",
                f"服务器配置已保存：\n"
                f"• 并行服务器数量：{server_pool_size} 个\n"
                f"• 连接超时时间：{timeout} 秒\n"
                f"• 重试次数：{retry_times} 次\n\n"
                f"配置将在下次下载时生效。",
            )

            self.accept()

        except Exception as e:
            import logging

            logging.getLogger(__name__).error("保存服务器配置失败: %s", e, exc_info=True)

            QMessageBox.warning(self, "保存失败", f"保存配置时发生错误：{str(e)}")

    @staticmethod
    def show_config_dialog(data_center_service, parent=None):
        """显示服务器配置对话框（静态方法）.

        Args:
            data_center_service: 数据中心服务实例
            parent: 父窗口

        Returns:
            bool: 用户是否点击了确定按钮
        """
        dialog = ServerConfigDialog(data_center_service, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted


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
            f">>> [DOWNLOAD THREAD] DownloadThread.run() 开始执行",
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
            print(">>> [DOWNLOAD THREAD] 发送进度信号...", flush=True)
            self.progress_signal.emit("正在准备下载...")

            # 在后台线程中执行耗时操作
            import time

            start_time = time.time()

            try:
                print(
                    f">>> [DOWNLOAD THREAD] 调用后端服务开始增量下载...",
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
                        f">>> [DOWNLOAD THREAD] 调用 start_incremental_download_with_progress()",
                        flush=True,
                    )
                    result = self.data_center_service.start_incremental_download_with_progress(
                        self.start_date, _cb
                    )
                    print(
                        f">>> [DOWNLOAD THREAD] start_incremental_download_with_progress() 返回",
                        flush=True,
                    )
                else:
                    print(
                        f">>> [DOWNLOAD THREAD] 调用 start_incremental_download()",
                        flush=True,
                    )
                    result = self.data_center_service.start_incremental_download(self.start_date)
            except Exception as download_error:
                logger.error("下载过程异常: %s", download_error, exc_info=True)
                print(f">>> [DOWNLOAD THREAD] 下载异常: {download_error}", flush=True)
                self.error_signal.emit(f"下载失败: {str(download_error)}")
                return

            elapsed = time.time() - start_time
            print(
                f">>> [DOWNLOAD THREAD] 后端服务调用完成",
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
        self.start_date_input: Optional[QDateEdit] = None
        self.end_date_input: Optional[QDateEdit] = None
        self.data_table: Optional[QTableWidget] = None
        self.data_status_label: Optional[QLabel] = None
        self.data_quality_label: Optional[QLabel] = None
        self.repair_data_btn: Optional[QPushButton] = None  # 🔧 数据修复按钮
        self.current_queried_symbol: Optional[str] = None  # 🔧 当前查询的品种（用于修复）

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
        self.progress_text: Optional[QTextEdit] = None  # 🔧 进度文本显示
        self.detail_progress_table: Optional[QTableWidget] = None
        self.toggle_detail_btn: Optional[QPushButton] = None
        self.start_download_btn: Optional[QPushButton] = None
        self.pause_download_btn: Optional[QPushButton] = None
        self.stop_download_btn: Optional[QPushButton] = None
        self.server_config_btn: Optional[QPushButton] = None  # 🔧 服务器配置按钮

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

        clear_cache_btn = QPushButton("🗑️ 删除品种列表")
        clear_cache_btn.setToolTip("删除品种列表缓存（清理集合A-I的所有缓存）")
        clear_cache_btn.clicked.connect(self._clear_symbol_cache)
        toolbar_layout.addWidget(clear_cache_btn)

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
        self.symbol_input.setPlaceholderText("例如: 000001 或 600000")
        query_layout.addRow("品种代码:", self.symbol_input)

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

        # 🔧 新增：数据修复按钮（默认隐藏）
        self.repair_data_btn = QPushButton("🔧 修复数据")
        self.repair_data_btn.setVisible(False)
        self.repair_data_btn.clicked.connect(self._repair_data)
        self.repair_data_btn.setToolTip("自动修复数据质量问题")
        status_layout.addWidget(self.repair_data_btn)

        layout.addWidget(status_group)

        # 🆕 数据质量概览组（自动感知）
        quality_overview_group = QGroupBox("📊 数据质量概览（自动感知）")
        quality_overview_layout = QVBoxLayout(quality_overview_group)

        # 🚀 添加说明提示
        hint_label = QLabel(
            "💡 说明：「总品种」=品种缓存总数（5724个已过滤品种），「已下载」=本地有数据的品种数，"
            "「缺失」=缓存中有但本地无数据，「警告」=已下载但数据不完整"
        )
        hint_label.setStyleSheet("color: #666; font-size: 11px; padding: 5px;")
        hint_label.setWordWrap(True)
        quality_overview_layout.addWidget(hint_label)

        # 质量概览卡片（紧凑显示）
        self.quality_overview_widget = QWidget()
        overview_layout = QHBoxLayout(self.quality_overview_widget)
        overview_layout.setContentsMargins(5, 5, 5, 5)

        # 总品种数（品种缓存）
        self.total_symbols_label = QLabel("总品种: --")
        self.total_symbols_label.setToolTip("品种缓存中的品种总数（5724个已过滤品种）")
        overview_layout.addWidget(self.total_symbols_label)

        # 🆕 已下载品种数
        self.downloaded_symbols_label = QLabel("已下载: --")
        self.downloaded_symbols_label.setStyleSheet("color: #4CAF50;")
        self.downloaded_symbols_label.setToolTip("本地已下载数据的品种数")
        overview_layout.addWidget(self.downloaded_symbols_label)

        # 缺失品种
        self.missing_symbols_label = QLabel("缺失: --")
        self.missing_symbols_label.setStyleSheet("color: #FF9800;")
        self.missing_symbols_label.setToolTip("品种列表中有但本地完全无数据的品种数")
        overview_layout.addWidget(self.missing_symbols_label)

        # 错误品种
        self.error_symbols_label = QLabel("错误: --")
        self.error_symbols_label.setStyleSheet("color: #F44336;")
        overview_layout.addWidget(self.error_symbols_label)

        # 警告品种
        self.warning_symbols_label = QLabel("警告: --")
        self.warning_symbols_label.setStyleSheet("color: #FFC107;")
        overview_layout.addWidget(self.warning_symbols_label)

        # 质量评分
        self.quality_score_label = QLabel("评分: --")
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

        layout.addWidget(quality_overview_group)

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

        # 添加服务器配置按钮
        self.server_config_btn = QPushButton("⚙ 服务器配置")
        self.server_config_btn.setToolTip("配置多服务器并行下载参数")
        self.server_config_btn.clicked.connect(self._show_server_config)
        control_layout.addWidget(self.server_config_btn)

        layout.addWidget(control_group)

        # 进度组
        progress_group = QGroupBox("下载进度")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_label = QLabel("准备就绪")
        progress_layout.addWidget(self.progress_label)

        self.download_progress = QProgressBar()
        progress_layout.addWidget(self.download_progress)

        # 🚀 添加文本进度显示（只追加，不重绘）
        self.progress_text = QTextEdit()
        self.progress_text.setReadOnly(True)
        self.progress_text.setMaximumHeight(150)
        self.progress_text.setPlaceholderText("下载进度将显示在这里...")
        progress_layout.addWidget(self.progress_text)

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

                self._apply_filters()
                self.logger.info(">>> _apply_filters()完成")

                # 显示加载成功信息
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
        """刷新品种（从缓存）."""
        try:
            if not self.data_center_service:
                self.show_error("数据中心服务未初始化")
                return

            result = self.data_center_service.refresh_symbol_list()

            if result["success"]:
                data = result.get("data", [])

                # 🔧 增强健壮性：检查品种缓存是否为空
                if not data or len(data) == 0:
                    self.logger.warning("品种缓存为空，提示用户重新加载品种")
                    self.show_warning("⚠️ 无品种缓存，请先点击【重新加载品种】按钮获取品种列表")
                    # 清空表格显示
                    self.all_symbols_data = []
                    self.filtered_symbols_data = []
                    self._update_symbols_table()
                    return

                self.all_symbols_data = data
                self._apply_filters()
                self.show_info(f"刷新成功，共 {result['symbol_count']} 个品种")
            else:
                self.show_error(f"刷新失败: {result.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error("刷新品种失败: %s", e)
            self.show_error(f"刷新失败: {e}")

    def _clear_symbol_cache(self):
        """删除品种列表缓存（清理集合A-I的所有缓存）."""
        try:
            from PySide6.QtWidgets import QMessageBox

            # 确认对话框
            reply = QMessageBox.question(
                self,
                "确认删除",
                "确定要删除品种列表缓存吗？\n\n"
                "这将清理所有品种相关的缓存数据（集合A-I），\n"
                "删除后需要重新加载品种列表。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            if not self.data_center_service:
                self.show_error("数据中心服务未初始化")
                return

            self.logger.info("开始删除品种列表缓存...")
            result = self.data_center_service.clear_symbol_cache()

            if result.get("success"):
                # 清空内存数据
                self.all_symbols_data = []
                self.filtered_symbols_data = []
                self._update_symbols_table()

                self.show_info("✅ 品种列表缓存已删除")
                self.logger.info("品种列表缓存删除成功")
            else:
                self.show_error(f"删除失败: {result.get('message', '未知错误')}")
                self.logger.error("删除品种列表缓存失败: %s", result.get("message"))

        except Exception as e:
            self.logger.error("删除品种列表缓存异常: %s", e, exc_info=True)
            self.show_error(f"删除失败: {e}")

    def _show_empty_categories_warning(self, empty_categories: List[str]):
        """显示空品种类别警告弹窗.

        Args:
            empty_categories: 为空的品种类别列表
        """
        try:
            from PySide6.QtWidgets import QMessageBox

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

                # 操作按钮
                view_btn = QPushButton("查看")
                view_btn.clicked.connect(self._create_view_handler(symbol_code_str))
                self.symbols_table.setCellWidget(i, 5, view_btn)
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

    def _on_search_text_changed(self, _text: str):
        """搜索文本改变."""
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
        """查询本地数据（增强版：查询后自动检查质量）."""
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

                # 更新表格
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

                # 🔧 始终更新状态标签
                if self.data_status_label:
                    if len(data) == 0:
                        self.data_status_label.setText(f"查询成功，品种 {symbol} 暂无本地数据")
                    else:
                        self.data_status_label.setText(f"查询成功，共 {len(data)} 条记录")

                # 🔧 保存当前查询的品种
                self.current_queried_symbol = symbol

                # 🔧 自动检查数据质量
                self._check_data_quality_for_symbol(symbol)
            else:
                # 查询失败时也要更新状态
                error_msg = result.get("message", "未知错误")
                if self.data_status_label:
                    self.data_status_label.setText(f"查询失败: {error_msg}")
                if self.data_quality_label:
                    self.data_quality_label.setText("数据质量: 无法检查")
                self.show_error(f"查询失败: {error_msg}")

        except Exception as e:
            self.logger.error("查询本地数据失败: %s", e, exc_info=True)
            # 🔧 更新状态标签显示错误
            if self.data_status_label:
                self.data_status_label.setText(f"查询异常: {str(e)}")
            if self.data_quality_label:
                self.data_quality_label.setText("数据质量: 查询异常")
            self.show_error(f"查询失败: {e}")

    def _check_data_quality_for_symbol(self, symbol: str, interval: str = "1d"):
        """检查指定品种的数据质量（数据感知功能）.

        Args:
            symbol: 品种代码
            interval: K线周期，默认"1d"
        """
        try:
            if not self.data_center_service:
                self.logger.warning("⚠️ 数据中心服务不可用，无法检查质量")
                if self.data_quality_label:
                    self.data_quality_label.setText("数据质量: 服务不可用")
                return

            self.logger.info("🔍 开始检查品种 %s 的数据质量...", symbol)

            # 调用后端质量检查API
            quality_result = self.data_center_service.check_data_quality(symbol, interval)

            if not quality_result.get("success"):
                error_msg = quality_result.get("message", "未知错误")
                self.logger.warning("⚠️ 质量检查失败: %s", error_msg)
                if self.data_quality_label:
                    self.data_quality_label.setText(f"数据质量: 检查失败 - {error_msg}")
                return

            # 解析质量检查结果
            quality_status = quality_result.get("quality_status", "unknown")
            quality_score = quality_result.get("quality_score", 0)
            data_count = quality_result.get("data_count", 0)
            missing_dates_count = quality_result.get("missing_dates_count", 0)
            errors_count = quality_result.get("errors_count", 0)
            warnings_count = quality_result.get("warnings_count", 0)
            can_repair = quality_result.get("can_repair", False)

            # 🔧 检查品种是否缺失（没有本地数据）
            if data_count == 0 and quality_status == "error":
                # 显示品种缺失警告
                if self.missing_symbol_warning:
                    warning_text = (
                        f"⚠️ 品种 {symbol} 没有本地数据！\n\n"
                        "可能原因：\n"
                        "1. 该品种未包含在最新的品种列表中\n"
                        "2. 该品种的历史数据尚未下载\n\n"
                        "建议操作：\n"
                        "• 点击【品种列表】选项卡，刷新品种列表\n"
                        "• 点击【数据下载】选项卡，下载全量数据\n"
                        "• 或点击下方的【修复数据】按钮"
                    )
                    self.missing_symbol_warning.setText(warning_text)
                    self.missing_symbol_warning.setVisible(True)
            else:
                # 隐藏品种缺失警告
                if self.missing_symbol_warning:
                    self.missing_symbol_warning.setVisible(False)

            # 构建质量显示文本
            if quality_status == "excellent":
                status_icon = "✅"
                status_text = "正常"
            elif quality_status == "good":
                status_icon = "✅"
                status_text = "良好"
            elif quality_status == "warning":
                status_icon = "⚠️"
                status_text = "有警告"
            elif quality_status == "error":
                status_icon = "❌"
                status_text = "有错误"
            else:
                status_icon = "❓"
                status_text = "未知"

            # 更新质量标签
            quality_text = f"{status_icon} 数据质量: {status_text} (评分: {quality_score}/100)"

            # 添加详细信息
            details = []
            if data_count > 0:
                details.append(f"{data_count}条记录")
            if missing_dates_count > 0:
                details.append(f"缺失{missing_dates_count}天")
            if errors_count > 0:
                details.append(f"{errors_count}个错误")
            if warnings_count > 0:
                details.append(f"{warnings_count}个警告")

            if details:
                quality_text += f" | {', '.join(details)}"

            if self.data_quality_label:
                self.data_quality_label.setText(quality_text)

            # 显示/隐藏修复按钮
            if self.repair_data_btn:
                if can_repair and (errors_count > 0 or missing_dates_count > 0):
                    self.repair_data_btn.setVisible(True)
                    self.repair_data_btn.setEnabled(True)
                else:
                    self.repair_data_btn.setVisible(False)

            self.logger.info("✅ 质量检查完成: %s", quality_text)

        except Exception as e:
            self.logger.error("检查数据质量失败: %s", e, exc_info=True)
            if self.data_quality_label:
                self.data_quality_label.setText(f"质量检查失败: {str(e)}")

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
            from PySide6.QtWidgets import QMessageBox

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

    def _show_server_config(self):
        """显示服务器配置对话框"""
        try:
            if not self.data_center_service:
                self.show_error("数据中心服务未初始化")
                return

            # 显示配置对话框
            ServerConfigDialog.show_config_dialog(self.data_center_service, self)

        except Exception as e:
            self.logger.error("显示服务器配置对话框失败: %s", e, exc_info=True)
            self.show_error(f"显示配置对话框失败: {str(e)}")

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

            # 🚀 清空进度文本并显示开始信息
            if self.progress_text:
                self.progress_text.clear()
                self.progress_text.append(f"开始增量下载... (开始日期: {start_date})\n")

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
                    self._reset_download_state()
            else:
                self.logger.error(">>> 下载任务失败: %s", result.get("message"))
                self.show_error(f"下载失败: {result.get('message', '未知错误')}")
                self._reset_download_state()

        except Exception as e:
            self.logger.error(">>> 处理下载结果失败: %s", e, exc_info=True)
            self.show_error(f"处理结果失败: {e}")
            self._reset_download_state()

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

    def _append_progress_text(self, text: str):
        """追加进度文本到QTextEdit（不重绘）

        Args:
            text: 进度文本
        """
        try:
            if hasattr(self, "progress_text") and self.progress_text:
                # 使用append而非setText，只追加不重绘整体
                self.progress_text.append(text)
                # 滚动到底部
                self.progress_text.verticalScrollBar().setValue(
                    self.progress_text.verticalScrollBar().maximum()
                )
        except Exception as e:
            self.logger.debug("追加进度文本失败: %s", e)

    def _toggle_detail_progress(self, checked: bool):  # noqa: U101
        """切换详细进度显示."""
        if self.detail_progress_table:
            self.detail_progress_table.setVisible(checked)

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
                self.logger.info("✅ vnpy事件监听器已注册（下载+数据质量）")
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
                self.logger.info("✅ vnpy事件监听器已注销")
        except Exception as e:
            self.logger.error("注销事件监听器失败: %s", e)

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 注销事件监听器
        self._unregister_event_handlers()
        # 调用父类方法
        super().closeEvent(event)

    def _on_download_event(self, event: Event):
        """处理下载事件（vnpy事件回调）"""
        try:
            event_data = event.data
            status = event_data.get("status")

            # 🔧 调试日志
            self.logger.info(">>> 收到下载事件: status=%s", status)

            # 🚀 调试：在文本框显示收到事件（帮助诊断）
            if status == "progress" and self.progress_text:
                completed = event_data.get("completed", 0)
                if completed == 1:  # 第一个进度事件
                    self.progress_text.append("✓ 收到下载进度事件，开始显示进度...\n")

            if status == "progress":
                # 进度更新事件
                progress_pct = event_data.get("progress", 0)
                completed = event_data.get("completed", 0)
                total = event_data.get("total", 0)
                current_item = event_data.get("current_item", "")

                # 更新UI进度条和标签
                if self.download_progress:
                    self.download_progress.setValue(int(progress_pct))

                if self.progress_label:
                    self.progress_label.setText(
                        f"📥 下载中: {completed}/{total} ({progress_pct:.1f}%) - {current_item}"
                    )

                # 🚀 文本进度显示（每100个显示一次，避免刷屏）
                if self.progress_text:
                    if completed % 100 == 0:
                        self.progress_text.append(
                            f"✓ 已下载 {completed}/{total} 个数据集 ({progress_pct:.1f}%)"
                        )
                    elif completed == total:
                        # 最后一个也显示
                        self.progress_text.append(
                            f"✓ 已下载 {completed}/{total} 个数据集 ({progress_pct:.1f}%)"
                        )

                # 每100个打印一次日志
                if completed % 100 == 0:
                    self.logger.info(">>> 进度: %d/%d (%.1f%%)", completed, total, progress_pct)

            elif status == "success":
                # 下载成功完成
                count = event_data.get("count", 0)
                self.logger.info(">>> 下载完成事件：%d 个数据集", count)

                # 更新UI
                if self.download_progress:
                    self.download_progress.setValue(100)
                if self.progress_label:
                    self.progress_label.setText(f"✅ 下载完成：{count} 个数据集")

                # 🚀 文本显示下载完成摘要
                if self.progress_text:
                    self.progress_text.append(
                        f"\n{'='*50}\n下载完成摘要:\n{'='*50}\n"
                        f"✅ 下载完成，共成功保存 {count} 个数据集"
                    )

                # 重置状态
                self._reset_download_state()
                self.show_info(f"✅ 下载任务已全部完成！共 {count} 个数据集")

            elif status == "error":
                # 下载失败
                error_msg = event_data.get("error", "未知错误")
                self.logger.error(">>> 下载失败事件：%s", error_msg)

                if self.progress_label:
                    self.progress_label.setText("❌ 下载失败")

                # 🚀 文本显示失败摘要
                if self.progress_text:
                    self.progress_text.append(
                        f"\n{'='*50}\n下载失败:\n{'='*50}\n" f"❌ {error_msg}"
                    )

                self._reset_download_state()
                self.show_error(f"下载失败: {error_msg}")

            elif status == "stopped":
                # 下载被停止
                count = event_data.get("count", 0)
                self.logger.info(">>> 下载停止事件：已完成 %d 个", count)

                if self.progress_label:
                    self.progress_label.setText(f"⛔ 下载已停止：{count} 个数据集")

                # 🚀 文本显示停止摘要
                if self.progress_text:
                    self.progress_text.append(
                        f"\n{'='*50}\n下载已停止:\n{'='*50}\n"
                        f"⛔ 已下载 {count} 个数据集（用户手动停止）"
                    )

                self._reset_download_state()
                self.show_info(f"下载已停止，已完成 {count} 个数据集")

        except Exception as e:
            self.logger.error("处理下载事件失败: %s", e)

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
                        button_layout.setContentsMargins(2, 2, 2, 2)
                        button_layout.setSpacing(2)

                        # 对于polling_gateway和virtual_gateway，添加配置按钮
                        if source_id in ["polling_gateway", "virtual_gateway"]:
                            config_btn = QPushButton("配置")
                            config_btn.clicked.connect(
                                lambda _checked, sid=source_id: self._configure_gateway(sid)
                            )
                            button_layout.addWidget(config_btn)

                            # 启动/停止按钮
                            if connected:
                                stop_btn = QPushButton("停止")
                                stop_btn.clicked.connect(
                                    lambda _checked, sid=source_id: self._stop_gateway(sid)
                                )
                                button_layout.addWidget(stop_btn)
                            else:
                                start_btn = QPushButton("启动")
                                start_btn.clicked.connect(
                                    lambda _checked, sid=source_id: self._start_gateway(sid)
                                )
                                button_layout.addWidget(start_btn)
                        else:
                            # 其他数据源保持原有的连接/断开按钮
                            connect_btn = QPushButton("连接" if not connected else "断开")
                            connect_btn.clicked.connect(
                                lambda _checked, sid=source_id, conn=connected: (
                                    self._toggle_source_connection(sid, conn)
                                )
                            )
                            button_layout.addWidget(connect_btn)

                        self.sources_table.setCellWidget(i, 4, button_widget)

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
            from PySide6.QtWidgets import QDialog, QDialogButtonBox, QDateTimeEdit
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
        """异步加载数据质量概览（不阻塞UI）"""
        import threading

        def load_in_background():
            try:
                self.logger.info("【后台】开始加载数据质量概览...")

                if not self.data_center_service:
                    self.logger.warning("【后台】数据中心服务不可用")
                    return

                result = self.data_center_service.get_data_quality_overview()

                if result.get("success"):
                    # 使用线程安全的方式更新UI
                    # 需要通过信号槽或QTimer在主线程中更新
                    from PySide6.QtCore import QTimer

                    # 延迟调用，确保在UI线程中执行
                    QTimer.singleShot(0, lambda: self._update_quality_overview_ui(result))
                    self.logger.info("【后台】质量概览加载完成")
                else:
                    self.logger.warning("【后台】质量概览加载失败: %s", result.get("message"))

            except Exception as e:
                self.logger.error("【后台】加载质量概览异常: %s", e, exc_info=True)

        # 启动后台线程
        load_thread = threading.Thread(
            target=load_in_background, daemon=True, name="LoadQualityOverviewThread"
        )
        load_thread.start()

    def _refresh_quality_overview(self) -> None:
        """手动刷新数据质量概览"""
        try:
            self.logger.info("手动刷新数据质量概览...")

            if not self.data_center_service:
                self.show_error("数据中心服务未初始化")
                return

            # 调用后端API获取最新概览
            result = self.data_center_service.get_data_quality_overview()

            if result.get("success"):
                self._update_quality_overview_ui(result)
                self.show_info("质量概览已刷新")
            else:
                self.show_warning(f"刷新失败: {result.get('message')}")

        except Exception as e:
            self.logger.error("刷新质量概览失败: %s", e, exc_info=True)
            self.show_error(f"刷新失败: {e}")

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

            self.logger.info("质量概览UI已更新")

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
        """更新质量详情表格

        Args:
            details: 详情列表（已按状态优先级排序）
        """
        try:
            if not self.quality_detail_table:
                return

            # 清空表格
            self.quality_detail_table.setRowCount(0)

            # 填充数据
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

                # 第4列：问题描述（简要）+ Tooltip（详细）
                issues = detail.get("issues", [])
                intervals = detail.get("intervals", {})

                # 生成简要描述
                if status == "missing":
                    brief_desc = "完全缺失"
                else:
                    # 统计错误和警告数量
                    total_errors = sum(interval.get("errors", 0) for interval in intervals.values())
                    total_warnings = sum(
                        interval.get("warnings", 0) for interval in intervals.values()
                    )
                    total_missing_dates = sum(
                        interval.get("missing_dates", 0) for interval in intervals.values()
                    )

                    desc_parts = []
                    if total_errors > 0:
                        desc_parts.append(f"{total_errors}个错误")
                    if total_warnings > 0:
                        desc_parts.append(f"{total_warnings}个警告")
                    if total_missing_dates > 0:
                        desc_parts.append(f"缺失{total_missing_dates}天")

                    brief_desc = ", ".join(desc_parts) if desc_parts else "正常"

                desc_item = QTableWidgetItem(brief_desc)

                # 设置Tooltip显示详细问题列表
                if issues:
                    tooltip_text = "\n".join(issues[:20])  # 最多显示20条
                    if len(issues) > 20:
                        tooltip_text += f"\n... 还有 {len(issues) - 20} 条问题"
                    desc_item.setToolTip(tooltip_text)
                else:
                    desc_item.setToolTip("无问题")

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
            event_data = event.data
            symbol = event_data.get("symbol")
            score = event_data.get("score", 0)

            self.logger.debug("收到质量更新事件: symbol=%s, score=%s", symbol, score)

            # 增量更新：重新加载整体概览
            # （简化处理：收到任何品种更新都刷新整体）
            self._load_quality_overview_async()

        except Exception as e:
            self.logger.error("处理质量更新事件失败: %s", e)

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
                    # 静默更新，不显示提示（避免干扰用户）
                    self.logger.info("质量概览已自动更新")

        except Exception as e:
            self.logger.error("处理扫描完成事件失败: %s", e)
