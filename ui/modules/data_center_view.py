# -*- coding: utf-8 -*-
"""数据中心界面 - 主视图（重构版）.

标准架构：4个子界面采用选项卡形式。
合并tabs/handlers/utils逻辑，统一backend调用。

🆕 GUI异步集成示例:

现有实现(保留,继续工作):
    # 使用QThread + Signal/Slot
    class ReloadSymbolsThread(QThread):
        finished_signal = Signal(dict)

        def run(self):
            result = self.data_center_service.reload_symbol_list()
            self.finished_signal.emit(result)

    def on_reload_button_clicked(self):
        self.thread = ReloadSymbolsThread(self.service)
        self.thread.finished_signal.connect(self._on_reload_finished)
        self.thread.start()

可选异步实现(需要qasync):
    # 直接使用合并的 async_slot

    @async_slot
    async def on_reload_button_clicked_async(self):
        '''qasync版本:直接await,无需QThread'''
        try:
            self.reload_button.setEnabled(False)
            self.status_label.setText("正在加载...")

            # 直接await异步操作(需要后端提供async版本)
            result = await self.service.reload_symbol_list_async()

            # 更新UI
            self._on_reload_finished(result)

        except Exception as e:
            logger_user.error(f"加载失败: {e}")
            self.status_label.setText(f"加载失败: {e}")
        finally:
            self.reload_button.setEnabled(True)

使用建议:
- 现有QThread代码继续工作,不强制迁移
- 新功能可选择使用async版本(需qasync支持)
- 异步版本代码更简洁,无需Signal/Slot样板代码
"""
import logging
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDate, QThread, QTimer, Signal, Qt, QStringListModel
from PySide6.QtWidgets import QCompleter
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
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
from ui.components.widgets import BaseWidget

# vnpy事件相关
from vnpy.event import Event
from backend.services.vnpy_imports import EVENT_TICK

# 事件类型常量（与backend保持一致）
EVENT_CHINASTOCK_DOWNLOAD = "eChinaStockDownload"
EVENT_DATA_QUALITY_UPDATE = "eDataQualityUpdate"  # 数据质量更新事件
EVENT_DATA_SCAN_COMPLETE = "eDataScanComplete"  # 扫描完成事件
EVENT_SYMBOL_CACHE_LOADED = "eSymbolCacheLoaded"  # 品种列表缓存加载完成
EVENT_VALIDATION_COMPLETED = "eValidationCompleted"  # 启动流程验证完成

# UI层专用logger
logger_user = logging.getLogger("ui.user_feedback")

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
        # UI专用logger
        import logging

        self.logger = logging.getLogger("ui.data_center.worker")

    def run(self):
        """线程执行函数（在后台线程中运行）."""
        import time
        start_time = time.time()

        try:
            # 使用ai_log_process包裹重新请求品种列表流程
            try:
                from backend.infrastructure.system_vnpy.unified_log_system import (
                    get_logging_hub,
                    ai_log_process,
                )
            except ImportError:
                ai_log_process = None
                get_logging_hub = None

            if ai_log_process:
                stage_logger = logging.getLogger("task.refresh_symbol_list.stage")
                try:
                    hub = get_logging_hub() if get_logging_hub else None
                except ImportError:
                    hub = None
                try:
                    context_manager = ai_log_process("refresh_symbol_list") if hub else None
                except Exception:
                    context_manager = None
                
                if context_manager:
                    with context_manager:
                        # 阶段节点日志（输出到Terminal）
                        stage_logger.info(
                            "📍 重新请求品种列表开始",
                            extra={"log_type": "STAGE_NODE", "scenario": "refresh_symbol_list"},
                        )
                        
                        # 详细日志（只写入AI日志文件）
                        self.logger.debug(
                            "[SYMBOL-RELOAD] 品种重载工作线程开始",
                            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                        )
                        self.logger.debug(
                            f"[SYMBOL-RELOAD] 服务实例类型: {type(self.data_center_service).__name__}",
                            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                        )
                        self.logger.debug(
                            f"[SYMBOL-RELOAD] 服务实例: {self.data_center_service}",
                            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                        )
                        self.logger.debug(
                            "[SYMBOL-RELOAD] 强制重新加载: force=True",
                            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                        )
                        self.progress_signal.emit("正在连接服务器...")

                        # 在后台线程中执行耗时操作
                        reload_start_time = time.time()
                        self.logger.debug(
                            "[SYMBOL-RELOAD] 调用服务层reload_symbol_list方法...",
                            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                        )
                        result = self.data_center_service.reload_symbol_list(force=True)
                        reload_elapsed = time.time() - reload_start_time
                        elapsed = time.time() - start_time

                        # 记录结果详情
                        if result and result.get("success"):
                            symbol_count = result.get("symbol_count", 0)
                            message = result.get("message", "")
                            warning = result.get("warning")
                            empty_categories = result.get("empty_categories", [])
                            self.logger.debug(
                                f"[SYMBOL-RELOAD] 重载结果详情: symbol_count={symbol_count}, "
                                f"message={message}, warning={'存在' if warning else '无'}, "
                                f"empty_categories={empty_categories}",
                                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                            )
                            self.logger.info(
                                f"[SYMBOL-RELOAD] 品种重载完成: 耗时={elapsed:.2f}s, 数量={symbol_count}, "
                                f"服务层耗时={reload_elapsed:.2f}s",
                                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                            )
                            if warning:
                                self.logger.warning(
                                    f"[SYMBOL-RELOAD] ⚠️ 品种重载警告: {warning}",
                                    extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"},
                                )
                        else:
                            msg = result.get("message", "重载失败") if result else "重载失败"
                            self.logger.warning(
                                f"[SYMBOL-RELOAD] ⚠️ 品种重载失败: {msg}, 耗时={elapsed:.2f}s",
                                extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"},
                            )
                            self.logger.debug(
                                f"[SYMBOL-RELOAD] 失败结果详情: {result}",
                                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                            )
                        
                        # 阶段节点日志（输出到Terminal）
                        if result and result.get("success"):
                            symbol_count = result.get("symbol_count", 0)
                            stage_logger.info(
                                f"✅ 重新请求品种列表完成: 耗时={elapsed:.2f}s, 数量={symbol_count}",
                                extra={"log_type": "STAGE_NODE", "scenario": "refresh_symbol_list"},
                            )
                        else:
                            msg = result.get("message", "重载失败") if result else "重载失败"
                            stage_logger.warning(
                                f"⚠️ 重新请求品种列表失败: {msg}",
                                extra={"log_type": "STAGE_NODE", "scenario": "refresh_symbol_list"},
                            )

                        self.finished_signal.emit(result)
            else:
                # 降级处理：如果ai_log_process不可用，直接执行
                self.logger.warning(
                    "[SYMBOL-RELOAD] ⚠️ 日志系统不可用，使用降级模式",
                    extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"},
                )
                self.logger.debug(
                    "[SYMBOL-RELOAD] 降级模式：品种重载工作线程开始",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                )
                self.progress_signal.emit("正在连接服务器...")

                reload_start_time = time.time()
                result = self.data_center_service.reload_symbol_list(force=True)
                reload_elapsed = time.time() - reload_start_time
                elapsed = time.time() - start_time

                self.logger.info(
                    f"[SYMBOL-RELOAD] 品种重载完成（降级模式）: 耗时={elapsed:.2f}s, 数量={result.get('symbol_count', 0)}, "
                    f"服务层耗时={reload_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
                )

                self.finished_signal.emit(result)

        except Exception as e:
            elapsed = time.time() - start_time
            # 记录异常并发送错误信号
            self.logger.error(
                f"[SYMBOL-RELOAD] ❌ 品种重载失败: {e}, 耗时={elapsed:.2f}s",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "refresh_symbol_list"},
            )
            self.logger.debug(
                f"[SYMBOL-RELOAD] 异常类型: {type(e).__name__}, 异常详情: {str(e)}",
                extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
            )
            self.error_signal.emit(f"加载失败: {str(e)}")


class DownloadThread(QThread):
    """异步数据下载的工作线程."""

    # 定义信号
    finished_signal = Signal(dict)  # 完成信号，传递结果字典
    error_signal = Signal(str)  # 错误信号，传递错误消息
    progress_signal = Signal(str)  # 进度信号，传递进度消息

    def __init__(self, data_center_service, start_date, parent=None, symbols=None, end_date=None):
        """初始化工作线程.

        Args:
            data_center_service: 数据中心服务实例
            start_date: 开始日期（增量下载）
            parent: 父对象
            symbols: 可选，指定品种列表（用于修复下载）
            end_date: 可选，结束日期
        """
        super().__init__(parent)
        self.data_center_service = data_center_service
        self.start_date = start_date
        self.end_date = end_date  # 可选：结束日期
        self.symbols = symbols  # 可选：指定品种列表（用于修复下载）
        # UI专用logger
        import logging

        self.logger = logging.getLogger("ui.data_center.worker")

    def run(self):
        """线程执行函数（在后台线程中运行）."""
        from datetime import datetime
        import time

        try:
            # 使用ai_log_process包裹数据下载流程
            try:
                from backend.infrastructure.system_vnpy.unified_log_system import (
                    ai_log_process,
                )
            except ImportError:
                ai_log_process = None

            # 记录开始时间（用于历史记录）
            self.start_time = datetime.now()

            if ai_log_process:
                stage_logger = logging.getLogger("task.data_download")
                download_type = "修复下载" if self.symbols else "增量下载"
                metadata = {
                    "download_type": download_type,
                    "start_date": str(self.start_date),
                    "symbol_count": len(self.symbols) if self.symbols else None,
                }
                if self.end_date:
                    metadata["end_date"] = str(self.end_date)
                
                with ai_log_process("data_download", metadata):
                    # 阶段节点日志（输出到Terminal）
                    stage_logger.info(
                        f"📍 数据下载开始: {download_type}",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )
                    
                    # 详细日志（只写入AI日志文件）
                    if self.symbols:
                        self.logger.debug(
                            f"[DATA-DOWNLOAD] 开始批量下载: 开始日期={self.start_date}, 品种数={len(self.symbols)}, "
                            f"结束日期={'有' if self.end_date else '无'}",
                            extra={"log_type": "SYSTEM", "scenario": "data_download"},
                        )
                        self.logger.debug(
                            f"[DATA-DOWNLOAD] 服务实例类型: {type(self.data_center_service).__name__}",
                            extra={"log_type": "SYSTEM", "scenario": "data_download"},
                        )
                        self.logger.info(
                            f"[DATA-DOWNLOAD] 批量下载任务开始: 开始日期={self.start_date}, 品种数={len(self.symbols)}",
                            extra={"log_type": "SYSTEM", "scenario": "data_download"},
                        )
                    else:
                        self.logger.debug(
                            f"[DATA-DOWNLOAD] 开始增量下载: 开始日期={self.start_date}, 结束日期={'有' if self.end_date else '无'}",
                            extra={"log_type": "SYSTEM", "scenario": "data_download"},
                        )
                        self.logger.debug(
                            f"[DATA-DOWNLOAD] 服务实例类型: {type(self.data_center_service).__name__}",
                            extra={"log_type": "SYSTEM", "scenario": "data_download"},
                        )
                        self.logger.info(
                            f"[DATA-DOWNLOAD] 增量下载任务开始: 开始日期={self.start_date}",
                            extra={"log_type": "SYSTEM", "scenario": "data_download"},
                        )

                    self.progress_signal.emit("正在准备下载...")

                    # 在后台线程中执行耗时操作
                    start_time = time.time()

                    try:
                        # 优先调用带进度的新方法；不存在则回退旧方法
                        has_progress_method = hasattr(self.data_center_service, "start_incremental_download_with_progress")
                        self.logger.debug(
                            f"[DATA-DOWNLOAD] 服务是否有start_incremental_download_with_progress方法: {has_progress_method}",
                            extra={"log_type": "SYSTEM", "scenario": "data_download"},
                        )
                        
                        if has_progress_method:
                            self.logger.debug(
                                "[DATA-DOWNLOAD] 使用带进度的下载方法",
                                extra={"log_type": "SYSTEM", "scenario": "data_download"},
                            )

                            def _cb(percent, message):
                                try:
                                    # 下载进度通过信号发送，并记录到日志（使用PROGRESS类型）
                                    self.progress_signal.emit(str(message))
                                    self.logger.debug(
                                        f"[DATA-DOWNLOAD] 进度: {percent}% - {message}",
                                        extra={"log_type": "PROGRESS", "scenario": "data_download"},
                                    )
                                except Exception as e:
                                    self.logger.debug(
                                        f"[DATA-DOWNLOAD] 进度回调异常: {e}",
                                        extra={"log_type": "SYSTEM", "scenario": "data_download"},
                                    )

                            # 调用下载方法（传递symbols参数）
                            self.logger.debug(
                                f"[DATA-DOWNLOAD] 调用start_incremental_download_with_progress方法: "
                                f"start_date={self.start_date}, symbols={'有' if self.symbols else '无'}",
                                extra={"log_type": "SYSTEM", "scenario": "data_download"},
                            )
                            result = self.data_center_service.start_incremental_download_with_progress(
                                self.start_date, _cb, symbols=self.symbols
                            )
                        else:
                            self.logger.debug(
                                "[DATA-DOWNLOAD] 使用旧版下载方法（无进度回调）",
                                extra={"log_type": "SYSTEM", "scenario": "data_download"},
                            )
                            result = self.data_center_service.start_incremental_download(self.start_date)

                    except Exception as download_error:
                        elapsed = time.time() - start_time
                        self.logger.error(
                            f"[DATA-DOWNLOAD] ❌ 下载过程异常: {download_error}, 耗时={elapsed:.2f}s",
                            exc_info=True,
                            extra={"log_type": "ALERT", "scenario": "data_download"},
                        )
                        self.logger.debug(
                            f"[DATA-DOWNLOAD] 异常类型: {type(download_error).__name__}, 异常详情: {str(download_error)}",
                            extra={"log_type": "SYSTEM", "scenario": "data_download"},
                        )
                        stage_logger.error(
                            f"❌ 数据下载失败: {download_error}",
                            extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                        )
                        self.error_signal.emit(f"下载失败: {str(download_error)}")
                        return

                    elapsed = time.time() - start_time

                    # 记录耗时（用于历史记录）
                    self.duration = elapsed

                    # 记录下载完成
                    success_count = result.get("success_count", 0)
                    failed_count = result.get("failed_count", 0)
                    task_id = result.get("task_id")
                    message = result.get("message", "")
                    self.logger.debug(
                        f"[DATA-DOWNLOAD] 下载结果详情: success_count={success_count}, failed_count={failed_count}, "
                        f"task_id={task_id}, message={message}",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"},
                    )
                    self.logger.info(
                        f"[DATA-DOWNLOAD] 批量下载完成: 总耗时={elapsed:.2f}s, 成功={success_count}, 失败={failed_count}",
                        extra={"log_type": "SYSTEM", "scenario": "data_download"},
                    )

                    # 阶段节点日志（输出到Terminal）
                    stage_logger.info(
                        f"✅ 数据下载完成: 耗时={elapsed:.2f}s, 成功={success_count}, 失败={failed_count}",
                        extra={"log_type": "STAGE_NODE", "scenario": "data_download"},
                    )

                    # 检查是否过快完成（可能有问题）
                    if elapsed < 5.0:
                        self.logger.warning(
                            f"[DATA-DOWNLOAD] ⚠️ 下载过快完成: 耗时={elapsed:.2f}s, 请检查是否正常",
                            extra={"log_type": "ALERT", "scenario": "data_download"},
                        )

                    # 发送完成信号
                    try:
                        self.finished_signal.emit(result)
                    except Exception as signal_err:
                        self.logger.error(
                            "❌ 发送完成信号失败: %s",
                            signal_err,
                            exc_info=True,
                            extra={"log_type": "ALERT", "scenario": "data_download"},
                        )
            else:
                # 降级处理：如果ai_log_process不可用，直接执行
                if self.symbols:
                    self.logger.info(
                        "开始批量下载: 开始日期=%s, 品种数=%d",
                        self.start_date,
                        len(self.symbols),
                        extra={"log_type": "SYSTEM", "scenario": "data_download"},
                    )
                else:
                    self.logger.info(
                        "开始增量下载: 开始日期=%s",
                        self.start_date,
                        extra={"log_type": "SYSTEM", "scenario": "data_download"},
                    )

                self.progress_signal.emit("正在准备下载...")

                start_time = time.time()

                try:
                    if hasattr(self.data_center_service, "start_incremental_download_with_progress"):

                        def _cb(percent, message):
                            try:
                                self.progress_signal.emit(str(message))
                                self.logger.debug(
                                    f"[DATA-DOWNLOAD] 进度: {percent}% - {message}",
                                    extra={"log_type": "PROGRESS", "scenario": "data_download"},
                                )
                            except Exception:
                                pass

                        result = self.data_center_service.start_incremental_download_with_progress(
                            self.start_date, _cb, symbols=self.symbols
                        )
                    else:
                        result = self.data_center_service.start_incremental_download(self.start_date)

                except Exception as download_error:
                    self.logger.error(
                        "❌ 下载过程异常: %s",
                        download_error,
                        exc_info=True,
                        extra={"log_type": "ALERT", "scenario": "data_download"},
                    )
                    self.error_signal.emit(f"下载失败: {str(download_error)}")
                    return

                elapsed = time.time() - start_time
                self.duration = elapsed

                success_count = result.get("success_count", 0)
                failed_count = result.get("failed_count", 0)
                self.logger.info(
                    "批量下载完成: 总耗时=%.2fs, 成功=%d, 失败=%d",
                    elapsed,
                    success_count,
                    failed_count,
                    extra={"log_type": "SYSTEM", "scenario": "data_download"},
                )

                if elapsed < 5.0:
                    self.logger.warning(
                        "下载过快完成: 耗时=%.2fs, 请检查是否正常",
                        elapsed,
                        extra={"log_type": "ALERT", "scenario": "data_download"},
                    )

                try:
                    self.finished_signal.emit(result)
                except Exception as signal_err:
                    self.logger.error(
                        "❌ 发送完成信号失败: %s",
                        signal_err,
                        exc_info=True,
                        extra={"log_type": "ALERT", "scenario": "data_download"},
                    )

        except Exception as e:
            # 记录异常并发送错误信号
            self.logger.error(
                "❌ 下载线程发生异常: %s",
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "data_download"},
            )

            # 确保信号发送成功
            try:
                self.error_signal.emit(f"下载失败: {str(e)}")
            except Exception as signal_err:
                self.logger.error(
                    "❌ 发送错误信号失败: %s",
                    signal_err,
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "data_download"},
                )


class DataCenter(BaseWidget, LoggerMixin):
    """数据中心主界面（重构版）."""

    # 🔧 关键修复：定义Qt Signal用于跨线程UI更新
    # 原因：vnpy事件引擎在独立线程中运行，使用Signal确保槽函数在主线程执行
    quality_update_signal = Signal(dict)  # 数据质量更新信号
    quality_scan_status_signal = Signal(bool)  # 扫描状态信号（True=扫描中, False=完成）

    # 🆕 专用信号：为每个UI更新场景创建专门的信号
    symbol_cache_loaded_signal = Signal(int)  # 品种缓存加载信号：symbol_count
    data_metrics_update_signal = Signal(
        int, int, int, int, list
    )  # 数据指标更新：total, downloaded, missing, invalid_count, details
    invalid_symbols_update_signal = Signal(int)  # 失效品种更新：count
    validation_completed_signal = Signal(bool)  # 启动流程验证完成：success
    quality_scan_phase_signal = Signal(int, dict, str)  # 质量扫描阶段：phase, metrics, status
    append_details_signal = Signal(list)  # 🔧 新增：追加问题详情信号（避免QTimer.singleShot不可靠）

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
        self.current_queried_symbol: Optional[str] = None  # 🔧 当前查询的品种（用于修复）

        # 品种智能联想相关
        self.symbol_cache: List[Dict[str, Any]] = []  # 品种缓存（用于品种列表搜索框的拼音匹配）
        self.symbol_pinyin_dict: Dict[tuple, str] = (
            {}
        )  # 🚀 品种拼音字典索引：(code, name) -> pinyin（O(1)查找）
        self.local_data_cache: List[Dict[str, Any]] = []  # 本地数据索引（用于本地数据搜索框联想）
        self.symbol_completer: Optional[QCompleter] = None  # 本地数据搜索框自动补全器
        # 注意：品种列表搜索框不再使用QCompleter，搜索直接触发品种列表过滤

        # pypinyin状态追踪（避免重复ImportError日志）
        self._pypinyin_import_error_logged = False

        # 🆕 流程状态追踪变量
        self._lightweight_running = True  # 启动流程运行中（初始为True）
        self._heavy_scan_running = False  # 数据质量扫描运行中

        # 🆕 问题数据计数（用于按钮启用逻辑）
        self._symbol_cache_count = 0  # 总品种数（启动流程步骤4）
        self._symbol_cache_event_received = False  # 🔧 新增：事件是否已到达标志位（时序控制）
        self._downloaded_count = 0  # 已下载品种数
        self._missing_count = 0  # 品种缺失数
        self._invalid_symbols_count = 0  # 失效品种数
        self._outdated_count = 0  # 过时品种数
        self._error_count = 0  # 错误品种数
        self._data_missing_count = 0  # 数据缺失品种数
        self._warning_count = 0  # 警告品种数

        # 🆕 品种问题组件（上部分）
        self.symbol_issues_section: Optional[QWidget] = None
        self.symbol_total_label: Optional[QLabel] = None
        self.symbol_downloaded_label: Optional[QLabel] = None
        self.symbol_missing_label: Optional[QLabel] = None
        self.symbol_invalid_label: Optional[QLabel] = None
        self.symbol_outdated_label: Optional[QLabel] = None
        self.repair_symbol_issues_btn: Optional[QPushButton] = None
        self.delete_invalid_symbols_btn: Optional[QPushButton] = None
        self.toggle_symbol_issues_detail_btn: Optional[QPushButton] = None
        self.symbol_issues_detail_table: Optional[QTableWidget] = None

        # 🆕 数据问题组件（下部分）
        self.data_issues_section: Optional[QWidget] = None
        self.data_error_label: Optional[QLabel] = None
        self.data_missing_label: Optional[QLabel] = None
        self.data_warning_label: Optional[QLabel] = None
        self.scan_data_btn: Optional[QPushButton] = None
        self.repair_data_issues_btn: Optional[QPushButton] = None
        self.toggle_data_issues_detail_btn: Optional[QPushButton] = None
        self.data_issues_detail_table: Optional[QTableWidget] = None

        # 🔧 保留旧属性用于兼容（逐步迁移）
        self.quality_overview_widget: Optional[QWidget] = None
        self.total_symbols_label: Optional[QLabel] = None
        self.downloaded_symbols_label: Optional[QLabel] = None
        self.missing_symbols_label: Optional[QLabel] = None
        self.invalid_symbols_label: Optional[QLabel] = None
        self.outdated_symbols_label: Optional[QLabel] = None
        self.error_symbols_label: Optional[QLabel] = None
        self.data_missing_symbols_label: Optional[QLabel] = None
        self.warning_symbols_label: Optional[QLabel] = None
        self.toggle_quality_detail_btn: Optional[QPushButton] = None
        self.quality_detail_table: Optional[QTableWidget] = None
        self.repair_download_btn: Optional[QPushButton] = None
        self.delete_invalid_btn: Optional[QPushButton] = None

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

        # 实时监控相关
        from collections import deque

        self.tick_buffer = deque(maxlen=20)  # 最多保存20条tick数据
        self.monitor_paused = False
        self.monitor_pause_btn: Optional[QPushButton] = None
        self.monitor_clear_btn: Optional[QPushButton] = None

        # ⚠ 关键修复：在调用super().__init__之前先获取服务
        # 因为super().__init__会调用setup_ui()，而setup_ui()会调用_load_symbols_data()
        # 如果此时服务还没初始化，会导致错误
        try:
            self.data_center_service = self.service_manager.get_service("data_center_service")
        except Exception as e:
            import logging

            logging.getLogger(__name__).error("获取数据中心服务失败: %s", e)

        # 🔍 诊断：使用临时logger（super().__init__()之前）
        import logging

        temp_logger = logging.getLogger("ui.components.datacenter.init")
        temp_logger.info("[DataCenter.__init__] 📍 步骤1: 准备调用super().__init__()")

        # 调用父类初始化
        super().__init__(parent, "数据中心")

        # 🔍 诊断：super().__init__()之后（现在self.logger可用）
        self.logger.info("[DataCenter.__init__] 📍 步骤2: super().__init__()已返回")
        self.logger.info("数据中心界面初始化完成")

        # 检查服务状态并记录
        if self.data_center_service:
            self.logger.info("✓ 数据中心服务已就绪")
        else:
            self.logger.warning("⚠ 数据中心服务未注册", extra={"log_type": "SYSTEM"})

        # 🔧 关键修复：连接Signal到Slot（在主线程中自动执行）
        # 原因：Qt的Signal/Slot机制自动处理跨线程调度，无需手动使用QTimer
        self.logger.info("[DataCenter.__init__] 📍 步骤3: 准备连接Signal到Slot")
        self.quality_update_signal.connect(self._update_quality_overview_ui)
        self.quality_scan_status_signal.connect(self._set_quality_scan_status)

        # 🆕 连接专用信号到对应的UI更新槽函数
        self.symbol_cache_loaded_signal.connect(self._update_symbol_cache_ui)
        self.data_metrics_update_signal.connect(self._update_data_metrics_ui)
        self.invalid_symbols_update_signal.connect(self._update_invalid_symbols_ui)
        self.validation_completed_signal.connect(self._update_validation_completed_ui)
        self.quality_scan_phase_signal.connect(self._update_quality_scan_phase_ui)
        self.append_details_signal.connect(
            self._append_quality_details
        )  # 🔧 新增：连接详情追加信号
        self.logger.info(
            "[DataCenter.__init__] 📍 步骤4: Signal已连接到Slot（包括append_details_signal）"
        )

        # 🔧 注册vnpy事件监听器
        self.logger.info("[DataCenter.__init__] 📍 步骤5: 准备调用_register_event_handlers()")
        self._register_event_handlers()
        self.logger.info("[DataCenter.__init__] 📍 步骤6: _register_event_handlers()已返回")

        # 🆕 关键修复：主动拉取启动流程数据（补偿机制）
        # 原因：后端可能在前端初始化完成前就推送了事件，导致事件丢失
        # 延迟1秒执行，确保事件处理器已注册且数据库已更新
        QTimer.singleShot(1000, self._pull_startup_data)

        # 🆕 延迟加载质量概览（给服务和后台扫描留出初始化时间）
        # 使用5秒延迟，确保：
        # 1. data_center_service完全初始化
        # 2. china_stock_engine可用
        # 3. 后台数据扫描有机会完成
        if self.data_center_service:
            QTimer.singleShot(5000, self._load_quality_overview_with_retry)

        # 🚀 性能优化：启动时延迟加载品种缓存用于品种列表搜索框的拼音匹配
        # 字典构建已移到后台线程，主线程只做O(1)赋值，不会卡顿
        QTimer.singleShot(2000, self._load_symbol_cache_for_autocomplete)

        # 🆕 本地数据索引加载策略：优先使用后台数据质量扫描的结果（推送事件），超时后才启动后备方案
        # 后备方案延迟3秒启动（快速提供联想功能，避免用户等待过久）
        # 如果事件先到达，后备方案会跳过；如果事件延迟，后备方案保证用户体验
        self._local_data_index_loaded = False  # 标记是否已加载
        QTimer.singleShot(3000, self._load_local_data_index_fallback)

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
        # 🔧 修复：初始状态隐藏，等待后端事件推送后再显示合适的状态
        self.symbol_input_status_label = QLabel()
        self.symbol_input_status_label.setStyleSheet(
            "color: #999; font-size: 11px; padding-left: 5px;"
        )
        self.symbol_input_status_label.setWordWrap(True)
        self.symbol_input_status_label.setVisible(False)  # 初始隐藏
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

        # 🔧 重构：使用新的上下两部分组件
        # 上部分：品种问题展示
        symbol_issues_section = self._create_symbol_issues_section()

        # 下部分：数据问题展示
        data_issues_section = self._create_data_issues_section()

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

        # 右栏：品种问题组件
        right_layout = QVBoxLayout()
        right_layout.addWidget(symbol_issues_section)
        right_layout.addStretch()
        top_layout.addLayout(right_layout, stretch=1)

        layout.addLayout(top_layout)

        # 中间部分：数据问题组件（全宽）
        layout.addWidget(data_issues_section)

        # 下部分：数据展示（全宽）
        layout.addWidget(data_group)

        return tab

    # ==================== 品种问题组件（上部分）====================

    def _create_symbol_issues_section(self) -> QWidget:
        """创建品种问题展示组件（上部分）

        数据来源：启动流程事件
        显示：总品种、已下载、品种缺失、失效品种、过时品种
        """
        section = QGroupBox("品种问题")
        layout = QVBoxLayout(section)

        # 指标显示区域（5个标签）
        metrics_widget = QWidget()
        metrics_layout = QGridLayout(metrics_widget)
        metrics_layout.setSpacing(10)
        metrics_layout.setContentsMargins(5, 5, 5, 5)

        # 第一行：总品种、已下载、品种缺失
        self.symbol_total_label = QLabel("总品种: 正在加载...")
        self.symbol_total_label.setToolTip("品种缓存中的品种总数")
        self.symbol_total_label.setStyleSheet("color: #999;")
        metrics_layout.addWidget(self.symbol_total_label, 0, 0)

        self.symbol_downloaded_label = QLabel("已下载: 正在扫描...")
        self.symbol_downloaded_label.setToolTip("本地已下载数据的品种数")
        self.symbol_downloaded_label.setStyleSheet("color: #999;")
        metrics_layout.addWidget(self.symbol_downloaded_label, 0, 1)

        self.symbol_missing_label = QLabel("品种缺失: 正在扫描...")
        self.symbol_missing_label.setToolTip("品种列表中有但本地完全无数据的品种数")
        self.symbol_missing_label.setStyleSheet("color: #999;")
        metrics_layout.addWidget(self.symbol_missing_label, 0, 2)

        # 第二行：失效品种、过时品种
        self.symbol_invalid_label = QLabel("失效品种: 正在扫描...")
        self.symbol_invalid_label.setToolTip("已退市或失效的品种数")
        self.symbol_invalid_label.setStyleSheet("color: #999;")
        metrics_layout.addWidget(self.symbol_invalid_label, 1, 0)

        self.symbol_outdated_label = QLabel("过时: 等待扫描...")
        self.symbol_outdated_label.setToolTip("数据未更新到最新交易日的品种数")
        self.symbol_outdated_label.setStyleSheet("color: #999;")
        metrics_layout.addWidget(self.symbol_outdated_label, 1, 1)

        layout.addWidget(metrics_widget)

        # 按钮区域
        buttons_layout = QHBoxLayout()

        self.repair_symbol_issues_btn = QPushButton("修复品种问题")
        self.repair_symbol_issues_btn.setToolTip("下载缺失品种和过时品种的数据（最多100天）")
        self.repair_symbol_issues_btn.setEnabled(False)
        self.repair_symbol_issues_btn.clicked.connect(self._repair_symbol_issues)
        buttons_layout.addWidget(self.repair_symbol_issues_btn)

        self.delete_invalid_symbols_btn = QPushButton("删除失效品种")
        self.delete_invalid_symbols_btn.setToolTip("删除失效品种的数据文件")
        self.delete_invalid_symbols_btn.clicked.connect(self._delete_invalid_symbols)
        buttons_layout.addWidget(self.delete_invalid_symbols_btn)

        self.toggle_symbol_issues_detail_btn = QPushButton("显示详细信息")
        self.toggle_symbol_issues_detail_btn.setCheckable(True)
        self.toggle_symbol_issues_detail_btn.toggled.connect(self._toggle_symbol_issues_detail)
        buttons_layout.addWidget(self.toggle_symbol_issues_detail_btn)

        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        # 详情表格（默认隐藏）
        self.symbol_issues_detail_table = QTableWidget(0, 4)
        self.symbol_issues_detail_table.setHorizontalHeaderLabels(
            ["品种代码", "品种名称", "状态", "问题描述"]
        )
        header = self.symbol_issues_detail_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.symbol_issues_detail_table.setVisible(False)
        self.symbol_issues_detail_table.setMaximumHeight(200)
        layout.addWidget(self.symbol_issues_detail_table)

        self.symbol_issues_section = section
        return section

    # ==================== 数据问题组件（下部分）====================

    def _create_data_issues_section(self) -> QWidget:
        """创建数据问题展示组件（下部分）

        数据来源：数据扫描结果
        显示：错误、数据缺失、警告
        """
        section = QGroupBox("数据问题")
        layout = QVBoxLayout(section)

        # 指标显示区域（3个标签）
        metrics_widget = QWidget()
        metrics_layout = QGridLayout(metrics_widget)
        metrics_layout.setSpacing(10)
        metrics_layout.setContentsMargins(5, 5, 5, 5)

        self.data_error_label = QLabel("错误: 等待扫描...")
        self.data_error_label.setToolTip("数据文件损坏或格式错误的品种数")
        self.data_error_label.setStyleSheet("color: #999;")
        metrics_layout.addWidget(self.data_error_label, 0, 0)

        self.data_missing_label = QLabel("数据缺失: 等待扫描...")
        self.data_missing_label.setToolTip(
            "有数据但部分交易日缺失的品种数（排除品种缺失和过时导致的）"
        )
        self.data_missing_label.setStyleSheet("color: #999;")
        metrics_layout.addWidget(self.data_missing_label, 0, 1)

        self.data_warning_label = QLabel("警告: 等待扫描...")
        self.data_warning_label.setToolTip("数据不完整的品种数")
        self.data_warning_label.setStyleSheet("color: #999;")
        metrics_layout.addWidget(self.data_warning_label, 0, 2)

        layout.addWidget(metrics_widget)

        # 按钮区域
        buttons_layout = QHBoxLayout()

        self.scan_data_btn = QPushButton("数据扫描")
        self.scan_data_btn.setToolTip("扫描数据错误、数据缺失、警告")
        self.scan_data_btn.setEnabled(False)
        self.scan_data_btn.clicked.connect(self._trigger_data_scan)
        buttons_layout.addWidget(self.scan_data_btn)

        self.repair_data_issues_btn = QPushButton("修复数据问题")
        self.repair_data_issues_btn.setToolTip("下载修复错误、数据缺失、警告（最多100天）")
        self.repair_data_issues_btn.setEnabled(False)
        self.repair_data_issues_btn.clicked.connect(self._repair_data_issues)
        buttons_layout.addWidget(self.repair_data_issues_btn)

        self.toggle_data_issues_detail_btn = QPushButton("显示详细信息")
        self.toggle_data_issues_detail_btn.setCheckable(True)
        self.toggle_data_issues_detail_btn.toggled.connect(self._toggle_data_issues_detail)
        buttons_layout.addWidget(self.toggle_data_issues_detail_btn)

        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        # 详情表格（默认隐藏）
        self.data_issues_detail_table = QTableWidget(0, 4)
        self.data_issues_detail_table.setHorizontalHeaderLabels(
            ["品种代码", "品种名称", "状态", "问题描述"]
        )
        header = self.data_issues_detail_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.data_issues_detail_table.setVisible(False)
        self.data_issues_detail_table.setMaximumHeight(200)
        layout.addWidget(self.data_issues_detail_table)

        self.data_issues_section = section
        return section

    # ==================== 品种问题处理方法 ====================

    def _repair_symbol_issues(self) -> None:
        """修复品种问题：下载缺失品种和过时品种的数据"""
        try:
            self.logger.info("修复品种问题：开始收集问题品种")

            # 从详情表格收集缺失和过时品种
            missing_symbols = []
            outdated_symbols = []

            if self.symbol_issues_detail_table:
                for row in range(self.symbol_issues_detail_table.rowCount()):
                    symbol_item = self.symbol_issues_detail_table.item(row, 0)
                    status_item = self.symbol_issues_detail_table.item(row, 2)

                    if symbol_item and status_item:
                        symbol = symbol_item.text()
                        status_text = status_item.text()

                        if "缺失" in status_text or "missing" in status_text.lower():
                            missing_symbols.append(symbol)
                        elif "过时" in status_text or "outdated" in status_text.lower():
                            outdated_symbols.append(symbol)

            # 如果没有详情表格数据，从计数标签推断
            if not missing_symbols and not outdated_symbols:
                if self._missing_count > 0 or self._outdated_count > 0:
                    self.show_warning("请先点击'显示详细信息'查看问题品种，然后再修复")
                    return
                else:
                    self.show_info("没有需要修复的品种问题")
                    return

            problem_symbols = missing_symbols + outdated_symbols
            self.logger.info(
                f"收集到 {len(missing_symbols)} 个缺失品种，{len(outdated_symbols)} 个过时品种"
            )

            # 检查是否有超过100天的问题
            from datetime import date, timedelta

            today = date.today()
            limit_date = today - timedelta(days=100)

            has_old_data = False
            if self.symbol_issues_detail_table:
                for row in range(self.symbol_issues_detail_table.rowCount()):
                    issues_item = self.symbol_issues_detail_table.item(row, 3)
                    if issues_item:
                        issues_text = issues_item.text()
                        # 检查问题描述中是否提到超过100天
                        if "滞后" in issues_text or "gap_days" in issues_text.lower():
                            # 尝试提取天数
                            import re

                            match = re.search(r"(\d+)\s*天", issues_text)
                            if match:
                                gap_days = int(match.group(1))
                                if gap_days > 100:
                                    has_old_data = True
                                    break

            # 显示提示
            if has_old_data:
                msg = (
                    f"检测到 {len(problem_symbols)} 个问题品种需要修复\n\n"
                    f"⚠️ 注意：项目设计仅支持最近100天的数据请求，"
                    f"超过100天的问题数据请通过其他渠道更新。\n\n"
                    f"本次将修复最近100天内的数据。"
                )
            else:
                msg = f"将修复 {len(problem_symbols)} 个问题品种的数据（最近100天）"

            self.show_info(msg)

            # 调用下载接口
            start_date = limit_date
            end_date = today
            self._start_download_with_symbols(problem_symbols, start_date, end_date)

            self.logger.info(f"已触发 {len(problem_symbols)} 个品种的修复下载")

        except Exception as e:
            self.logger.error(f"修复品种问题失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            self.show_error(f"修复品种问题失败: {e}")

    def _delete_invalid_symbols(self) -> None:
        """删除失效品种（复用现有方法）"""
        self._trigger_delete_invalid()

    def _toggle_symbol_issues_detail(self, checked: bool) -> None:
        """切换品种问题详情表格显示"""
        try:
            if self.symbol_issues_detail_table:
                self.symbol_issues_detail_table.setVisible(checked)
                if checked:
                    self.symbol_issues_detail_table.viewport().update()
        except Exception as e:
            self.logger.error(f"切换品种问题详情表格失败: {e}", extra={"log_type": "SYSTEM"}, exc_info=True)

    def _append_symbol_issues_details(self, new_details: list) -> None:
        """追加品种问题详情到表格

        Args:
            new_details: 详情列表，包含status为missing、invalid、outdated的记录
        """
        try:
            if not self.symbol_issues_detail_table:
                return

            # 过滤：只添加品种问题相关的（missing、invalid、outdated）
            filtered_details = [
                d for d in new_details if d.get("status") in ["missing", "invalid", "outdated"]
            ]

            if not filtered_details:
                return

            # 如果表格显示的是"无问题"提示，先清空
            if self.symbol_issues_detail_table.rowCount() == 1:
                first_item = self.symbol_issues_detail_table.item(0, 0)
                if first_item and "无问题" in first_item.text():
                    self.symbol_issues_detail_table.setRowCount(0)

            # 增量追加
            for detail in filtered_details:
                row = self.symbol_issues_detail_table.rowCount()
                self.symbol_issues_detail_table.insertRow(row)

                # 品种代码
                symbol = detail.get("symbol", "")
                self.symbol_issues_detail_table.setItem(row, 0, QTableWidgetItem(symbol))

                # 品种名称
                name = detail.get("name", "")
                self.symbol_issues_detail_table.setItem(row, 1, QTableWidgetItem(name))

                # 状态
                status = detail.get("status", "")
                status_text = {
                    "missing": "品种缺失",
                    "invalid": "失效品种",
                    "outdated": "过时",
                }.get(status, status or "")
                status_item = QTableWidgetItem(status_text)
                self.symbol_issues_detail_table.setItem(row, 2, status_item)

                # 问题描述
                issues = detail.get("issues", "")
                self.symbol_issues_detail_table.setItem(row, 3, QTableWidgetItem(issues))

            self.logger.debug(f"追加了 {len(filtered_details)} 条品种问题详情")

        except Exception as e:
            self.logger.error(f"追加品种问题详情失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def _update_symbol_issues_ui(
        self, total_symbols=None, downloaded=None, missing=None, invalid_count=None, outdated=None
    ):
        """更新品种问题UI显示"""
        try:
            if total_symbols is not None and self.symbol_total_label:
                self.symbol_total_label.setText(f"总品种: {total_symbols}")
                self.symbol_total_label.setStyleSheet("")

            if downloaded is not None and self.symbol_downloaded_label:
                self.symbol_downloaded_label.setText(f"已下载: {downloaded}")
                self.symbol_downloaded_label.setStyleSheet("color: #4CAF50;")
                self._downloaded_count = downloaded

            if missing is not None and self.symbol_missing_label:
                self.symbol_missing_label.setText(f"品种缺失: {missing}")
                if missing > 0:
                    self.symbol_missing_label.setStyleSheet("color: #FF9800;")
                else:
                    self.symbol_missing_label.setStyleSheet("color: #4CAF50;")
                self._missing_count = missing

            if invalid_count is not None and self.symbol_invalid_label:
                self.symbol_invalid_label.setText(f"失效品种: {invalid_count}")
                if invalid_count > 0:
                    self.symbol_invalid_label.setStyleSheet("color: #FF9800;")
                else:
                    self.symbol_invalid_label.setStyleSheet("color: #4CAF50;")
                self._invalid_symbols_count = invalid_count

            if outdated is not None and self.symbol_outdated_label:
                self.symbol_outdated_label.setText(f"过时: {outdated}")
                if outdated > 0:
                    self.symbol_outdated_label.setStyleSheet("color: #FF9800;")
                else:
                    self.symbol_outdated_label.setStyleSheet("color: #4CAF50;")
                self._outdated_count = outdated

            # 更新修复按钮状态
            if self.repair_symbol_issues_btn:
                should_enable = (self._missing_count > 0) or (self._outdated_count > 0)
                self.repair_symbol_issues_btn.setEnabled(should_enable)

        except Exception as e:
            self.logger.error(f"更新品种问题UI失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    # ==================== 数据问题处理方法 ====================

    def _repair_data_issues(self) -> None:
        """修复数据问题：下载修复错误、数据缺失、警告"""
        try:
            self.logger.info("修复数据问题：开始收集问题品种")

            # 从详情表格收集问题品种
            problem_symbols = []

            if self.data_issues_detail_table:
                for row in range(self.data_issues_detail_table.rowCount()):
                    symbol_item = self.data_issues_detail_table.item(row, 0)
                    if symbol_item:
                        symbol = symbol_item.text()
                        problem_symbols.append(symbol)

            # 如果没有详情表格数据，从计数标签推断
            if not problem_symbols:
                if self._error_count > 0 or self._data_missing_count > 0 or self._warning_count > 0:
                    self.show_warning("请先点击'显示详细信息'查看问题品种，然后再修复")
                    return
                else:
                    self.show_info("没有需要修复的数据问题")
                    return

            self.logger.info(f"收集到 {len(problem_symbols)} 个问题品种")

            # 检查是否有超过100天的问题
            from datetime import date, timedelta

            today = date.today()
            limit_date = today - timedelta(days=100)

            has_old_data = False
            if self.data_issues_detail_table:
                for row in range(self.data_issues_detail_table.rowCount()):
                    issues_item = self.data_issues_detail_table.item(row, 3)
                    if issues_item:
                        issues_text = issues_item.text()
                        # 检查问题描述中是否提到超过100天
                        if "滞后" in issues_text or "gap_days" in issues_text.lower():
                            import re

                            match = re.search(r"(\d+)\s*天", issues_text)
                            if match:
                                gap_days = int(match.group(1))
                                if gap_days > 100:
                                    has_old_data = True
                                    break

            # 显示提示
            if has_old_data:
                msg = (
                    f"检测到 {len(problem_symbols)} 个问题品种需要修复\n\n"
                    f"⚠️ 注意：项目设计仅支持最近100天的数据请求，"
                    f"超过100天的问题数据请通过其他渠道更新。\n\n"
                    f"本次将修复最近100天内的数据。"
                )
            else:
                msg = f"将修复 {len(problem_symbols)} 个问题品种的数据（最近100天）"

            self.show_info(msg)

            # 切换到下载界面
            if hasattr(self, "tab_widget") and self.tab_widget:
                for i in range(self.tab_widget.count()):
                    if self.tab_widget.tabText(i) == "数据下载":
                        self.tab_widget.setCurrentIndex(i)
                        self.logger.info("已切换到数据下载tab")
                        break

            # 调用下载接口
            start_date = limit_date
            end_date = today
            self._start_download_with_symbols(problem_symbols, start_date, end_date)

            self.logger.info(f"已触发 {len(problem_symbols)} 个品种的修复下载")

        except Exception as e:
            self.logger.error(f"修复数据问题失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            self.show_error(f"修复数据问题失败: {e}")

    def _toggle_data_issues_detail(self, checked: bool) -> None:
        """切换数据问题详情表格显示"""
        try:
            if self.data_issues_detail_table:
                self.data_issues_detail_table.setVisible(checked)
                if checked:
                    self.data_issues_detail_table.viewport().update()
        except Exception as e:
            self.logger.error(f"切换数据问题详情表格失败: {e}", extra={"log_type": "SYSTEM"}, exc_info=True)

    def _append_data_issues_details(self, new_details: list) -> None:
        """追加数据问题详情到表格

        Args:
            new_details: 详情列表，只添加status为error、data_missing、warning的记录
                        排除missing和outdated（这些属于品种问题）
        """
        try:
            if not self.data_issues_detail_table:
                return

            # 过滤：只添加数据问题相关的（error、data_missing、warning），排除missing和outdated
            filtered_details = [
                d for d in new_details if d.get("status") in ["error", "data_missing", "warning"]
            ]

            if not filtered_details:
                return

            # 如果表格显示的是"无问题"提示，先清空
            if self.data_issues_detail_table.rowCount() == 1:
                first_item = self.data_issues_detail_table.item(0, 0)
                if first_item and "无问题" in first_item.text():
                    self.data_issues_detail_table.setRowCount(0)

            # 增量追加
            for detail in filtered_details:
                row = self.data_issues_detail_table.rowCount()
                self.data_issues_detail_table.insertRow(row)

                # 品种代码
                symbol = detail.get("symbol", "")
                self.data_issues_detail_table.setItem(row, 0, QTableWidgetItem(symbol))

                # 品种名称
                name = detail.get("name", "")
                self.data_issues_detail_table.setItem(row, 1, QTableWidgetItem(name))

                # 状态
                status = detail.get("status", "")
                status_text = {"error": "错误", "data_missing": "数据缺失", "warning": "警告"}.get(
                    status, status or ""
                )
                status_item = QTableWidgetItem(status_text)
                self.data_issues_detail_table.setItem(row, 2, status_item)

                # 问题描述
                issues = detail.get("issues", "")
                self.data_issues_detail_table.setItem(row, 3, QTableWidgetItem(issues))

            self.logger.debug(f"追加了 {len(filtered_details)} 条数据问题详情")

        except Exception as e:
            self.logger.error(f"追加数据问题详情失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def _update_data_issues_ui(self, error_count=None, data_missing_count=None, warning_count=None):
        """更新数据问题UI显示"""
        try:
            if error_count is not None and self.data_error_label:
                self.data_error_label.setText(f"错误: {error_count}")
                if error_count > 0:
                    self.data_error_label.setStyleSheet("color: #F44336;")
                else:
                    self.data_error_label.setStyleSheet("color: #4CAF50;")
                self._error_count = error_count

            if data_missing_count is not None and self.data_missing_label:
                self.data_missing_label.setText(f"数据缺失: {data_missing_count}")
                if data_missing_count > 0:
                    self.data_missing_label.setStyleSheet("color: #FF9800;")
                else:
                    self.data_missing_label.setStyleSheet("color: #4CAF50;")
                self._data_missing_count = data_missing_count

            if warning_count is not None and self.data_warning_label:
                self.data_warning_label.setText(f"警告: {warning_count}")
                if warning_count > 0:
                    self.data_warning_label.setStyleSheet("color: #FFC107;")
                else:
                    self.data_warning_label.setStyleSheet("color: #4CAF50;")
                self._warning_count = warning_count

            # 更新修复按钮状态
            if self.repair_data_issues_btn:
                should_enable = (
                    (self._error_count > 0)
                    or (self._data_missing_count > 0)
                    or (self._warning_count > 0)
                )
                self.repair_data_issues_btn.setEnabled(should_enable)

            # 更新扫描按钮状态（启动流程完成后启用）
            if self.scan_data_btn:
                self.scan_data_btn.setEnabled(True)

        except Exception as e:
            self.logger.error(
                "UI更新数据问题UI失败: 错误=%s",
                str(e),
                extra={"log_type": "SYSTEM"},
                exc_info=True
            )

    # ==================== 数据下载子界面 ====================

    def _create_download_tab(self) -> QWidget:
        """创建数据下载子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ✅ 新增：前置条件提示
        prerequisite_label = QLabel(
            "📌 <b>下载前置条件</b>：请确保已在【品种列表】选项卡中点击【🔄 重新加载品种】或【↻ 刷新品种】按钮，"
            "等待品种列表加载完成后再开始下载。否则会提示'未找到可下载的品种'。"
        )
        prerequisite_label.setStyleSheet(
            "background-color: #FFF3CD; color: #856404; padding: 10px; "
            "border: 1px solid #FFEEBA; border-radius: 5px; margin-bottom: 10px;"
        )
        prerequisite_label.setWordWrap(True)
        layout.addWidget(prerequisite_label)

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

        # 添加服务器状态显示与刷新测速按钮
        self.refresh_servers_btn = QPushButton("🔄 刷新")
        self.refresh_servers_btn.setToolTip("重新测速服务器池并刷新可用服务器")
        self.refresh_servers_btn.clicked.connect(self._retest_servers)
        control_layout.addWidget(self.refresh_servers_btn)

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

    def _retest_servers(self) -> None:
        """手动触发服务器池重新测速并刷新状态（使用QThread+Signal）。"""
        try:
            # 设置场景（通过extra参数传递scenario）
            try:
                from backend.infrastructure.system_vnpy.unified_log_system import (
                    ai_log_process,
                )
            except ImportError:
                ai_log_process = None

            if not self.refresh_servers_btn or not self.server_status_label:
                return

            # 获取服务实例（容错）
            if not self.data_center_service:
                self.data_center_service = self.service_manager.get_service("data_center_service")
                if not self.data_center_service:
                    self.show_warning("数据中心服务不可用，无法刷新服务器池")
                    return

            # UI 禁用，提示中
            self.refresh_servers_btn.setEnabled(False)
            self.server_status_label.setText("⏳ 正在重新测速...")
            self.server_status_label.setStyleSheet(
                "color: #0066cc; font-weight: bold; padding: 8px; "
                "background-color: #f0f8ff; border-radius: 4px;"
            )

            # 创建QThread工作线程（Qt原生，支持事件循环）
            from PySide6.QtCore import QThread, Signal

            class ServerRetestThread(QThread):
                """服务器重新测速工作线程（Qt原生）。"""

                finished_signal = Signal(dict)  # 完成信号，传递结果

                def __init__(self, service, parent=None):
                    super().__init__(parent)
                    self.service = service
                    self.logger = logging.getLogger("ui.data_center.speedtest")

                def run(self):
                    """后台执行测速。"""
                    import time
                    start_time = time.time()
                    
                    # 使用ai_log_process上下文管理器
                    try:
                        from backend.infrastructure.system_vnpy.unified_log_system import (
                            get_logging_hub,
                            ai_log_process,
                        )
                        stage_logger = logging.getLogger("task.manual_speedtest.stage")
                        
                        try:
                            hub = get_logging_hub()
                        except ImportError:
                            hub = None
                        
                        try:
                            context_manager = ai_log_process("manual_speedtest") if hub else None
                        except Exception:
                            context_manager = None
                        
                        if context_manager:
                            with context_manager:
                                # 阶段节点日志（输出到Terminal，通过extra传递scenario）
                                stage_logger.info(
                                    "📍 手动测速开始: 正在连接到服务器...",
                                    extra={"log_type": "STAGE_NODE", "scenario": "manual_speedtest"},
                                )
                                
                                # DEBUG日志（只写入AI日志文件，通过extra传递scenario）
                                self.logger.debug(
                                    "[SPEEDTEST] 开始执行服务器池测速",
                                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                                )
                                self.logger.debug(
                                    f"[SPEEDTEST] 服务实例类型: {type(self.service).__name__ if self.service else 'None'}",
                                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                                )
                                self.logger.debug(
                                    f"[SPEEDTEST] 服务实例: {self.service}",
                                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                                )
                                self.logger.debug(
                                    f"[SPEEDTEST] 服务是否有retest_server_pool方法: {hasattr(self.service, 'retest_server_pool') if self.service else False}",
                                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                                )
                                
                                result = None
                                try:
                                    if self.service and hasattr(self.service, "retest_server_pool"):
                                        self.logger.debug(
                                            "[SPEEDTEST] 调用服务层测速方法...",
                                            extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                                        )
                                        # 调用服务层测速方法
                                        result = self.service.retest_server_pool()
                                        elapsed = time.time() - start_time
                                        self.logger.debug(
                                            f"[SPEEDTEST] 服务层测速方法调用完成: 耗时={elapsed:.2f}s",
                                            extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                                        )
                                        
                                        # 记录测速结果
                                        if result and result.get("success"):
                                            stats = result.get("stats", {})
                                            available = stats.get("available", 0)
                                            total = stats.get("total", 0)
                                            ipv4_count = stats.get("ipv4_count", 0)
                                            ipv6_count = stats.get("ipv6_count", 0)
                                            self.logger.debug(
                                                f"[SPEEDTEST] 测速结果详情: available={available}, total={total}, "
                                                f"ipv4_count={ipv4_count}, ipv6_count={ipv6_count}",
                                                extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                                            )
                                            self.logger.info(
                                                f"[SPEEDTEST] 测速完成: 可用服务器={available}/{total}, 耗时={elapsed:.2f}s",
                                                extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                                            )
                                            stage_logger.info(
                                                f"✅ 测速完成: 可用服务器={available}/{total}, 耗时={elapsed:.2f}s",
                                                extra={"log_type": "STAGE_NODE", "scenario": "manual_speedtest"},
                                            )
                                        else:
                                            msg = result.get("message", "测速失败") if result else "测速失败"
                                            elapsed = time.time() - start_time
                                            self.logger.warning(
                                                f"[SPEEDTEST] ⚠️ 测速失败: {msg}, 耗时={elapsed:.2f}s",
                                                extra={"log_type": "ALERT", "scenario": "manual_speedtest"},
                                            )
                                            self.logger.debug(
                                                f"[SPEEDTEST] 失败结果详情: {result}",
                                                extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                                            )
                                            stage_logger.warning(
                                                f"⚠️ 测速失败: {msg}",
                                                extra={"log_type": "STAGE_NODE", "scenario": "manual_speedtest"},
                                            )
                                    else:
                                        result = {"success": False, "message": "后端未实现刷新API"}
                                        elapsed = time.time() - start_time
                                        self.logger.error(
                                            f"[SPEEDTEST] ❌ 后端未实现刷新API, 耗时={elapsed:.2f}s",
                                            extra={"log_type": "ALERT", "scenario": "manual_speedtest"},
                                        )
                                        self.logger.debug(
                                            f"[SPEEDTEST] 服务状态: service={'存在' if self.service else '不存在'}, "
                                            f"has_method={'是' if hasattr(self.service, 'retest_server_pool') if self.service else '否'}",
                                            extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                                        )
                                        stage_logger.error(
                                            "❌ 后端未实现刷新API",
                                            extra={"log_type": "STAGE_NODE", "scenario": "manual_speedtest"},
                                        )
                                except Exception as e:  # pylint: disable=broad-except
                                    result = {"success": False, "message": str(e)}
                                    elapsed = time.time() - start_time
                                    self.logger.error(
                                        f"[SPEEDTEST] ❌ 测速异常: {e}, 耗时={elapsed:.2f}s",
                                        exc_info=True,
                                        extra={"log_type": "ALERT", "scenario": "manual_speedtest"},
                                    )
                                    self.logger.debug(
                                        f"[SPEEDTEST] 异常类型: {type(e).__name__}, 异常详情: {str(e)}",
                                        extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                                    )
                                    stage_logger.error(
                                        f"❌ 测速异常: {e}",
                                        extra={"log_type": "STAGE_NODE", "scenario": "manual_speedtest"},
                                    )
                                
                                self.finished_signal.emit(result)
                    except ImportError:
                        # 降级处理：日志系统不可用时使用简单日志
                        self.logger.warning(
                            "[SPEEDTEST] ⚠️ 日志系统不可用，使用降级模式",
                            extra={"log_type": "ALERT", "scenario": "manual_speedtest"},
                        )
                        result = None
                        try:
                            if self.service and hasattr(self.service, "retest_server_pool"):
                                self.logger.debug(
                                    "[SPEEDTEST] 降级模式：调用服务层测速方法",
                                    extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                                )
                                result = self.service.retest_server_pool()
                            else:
                                result = {"success": False, "message": "后端未实现刷新API"}
                        except Exception as e:  # pylint: disable=broad-except
                            result = {"success": False, "message": str(e)}
                            self.logger.error(
                                f"[SPEEDTEST] ❌ 降级模式测速异常: {e}",
                                exc_info=True,
                                extra={"log_type": "ALERT", "scenario": "manual_speedtest"},
                            )
                        elapsed = time.time() - start_time
                        self.logger.info(
                            f"[SPEEDTEST] 手动测速完成（降级模式）: 耗时={elapsed:.2f}s",
                            extra={"log_type": "SYSTEM", "scenario": "manual_speedtest"},
                        )

                    # 发射信号（线程安全，Qt会自动调度到主线程）
                    self.finished_signal.emit(result)

            # 创建并启动线程
            self._retest_thread = ServerRetestThread(self.data_center_service, self)

            # 连接信号（QueuedConnection确保在主线程执行）
            self._retest_thread.finished_signal.connect(
                self._on_retest_finished, Qt.ConnectionType.QueuedConnection
            )

            # 启动线程
            self._retest_thread.start()
            self.logger.info("后台测速线程已启动（QThread）")

        except Exception as e:  # pylint: disable=broad-except
            self.logger.error("刷新服务器池失败: %s", e, exc_info=True, extra={"log_type": "USER_FEEDBACK"})
            self.show_error(f"刷新服务器池失败: {e}")
            # 恢复按钮状态
            if hasattr(self, "refresh_servers_btn") and self.refresh_servers_btn:
                self.refresh_servers_btn.setEnabled(True)

    def _on_retest_finished(self, result: dict) -> None:
        """测速完成回调（在主线程中执行，线程安全）。

        Args:
            result: 测速结果字典
        """
        try:
            success = bool(result.get("success"))
            if success:
                stats = result.get("stats", {})
                available = stats.get("available", 0)
                total = stats.get("total", 0)
                if self.server_status_label:
                    self.server_status_label.setText(f"✅ 可用服务器: {available}/{total}")
                    self.server_status_label.setStyleSheet(
                        "color: #00aa00; font-weight: bold; padding: 8px; "
                        "background-color: #f0fff0; border-radius: 4px;"
                    )
                self.logger.info("UI更新成功：%d/%d 可用", available, total)
            else:
                msg = result.get("message", "刷新失败")
                if self.server_status_label:
                    self.server_status_label.setText(f"⚠️ 刷新失败: {msg}")
                    self.server_status_label.setStyleSheet(
                        "color: #ff6600; font-weight: bold; padding: 8px; "
                        "background-color: #fff8f0; border-radius: 4px;"
                    )
                self.logger.warning("UI更新失败：%s", msg)
        except Exception as e:  # pylint: disable=broad-except
            self.logger.error("UI更新异常: %s", e, exc_info=True)
        finally:
            # 确保按钮始终恢复（在主线程，线程安全）
            if self.refresh_servers_btn:
                self.refresh_servers_btn.setEnabled(True)
                self.logger.info("刷新按钮已恢复启用")

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

        # 监控控制按钮
        button_layout = QHBoxLayout()

        self.monitor_pause_btn = QPushButton("暂停")
        self.monitor_pause_btn.clicked.connect(self._toggle_monitor_pause)
        button_layout.addWidget(self.monitor_pause_btn)

        self.monitor_clear_btn = QPushButton("清空")
        self.monitor_clear_btn.clicked.connect(self._clear_monitor)
        button_layout.addWidget(self.monitor_clear_btn)

        button_layout.addStretch()
        monitor_layout.addLayout(button_layout)

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
            # 记录用户操作
            logger_user.info("用户点击刷新品种列表按钮")

            self.logger.info("=" * 60)
            self.logger.info(">>> _reload_symbols() 被调用")
            self.logger.info("=" * 60)

            if not self.data_center_service:
                self.logger.error(">>> 数据中心服务未初始化", exc_info=True, extra={"log_type": "SYSTEM"})
                self.show_error("数据中心服务未初始化")
                return

            # 检查是否已有线程在运行
            if self.reload_thread and self.reload_thread.isRunning():
                self.logger.warning(">>> 已有线程在运行，品种列表正在加载中", extra={"log_type": "SYSTEM"})
                # 🚀 修复UI卡死：不弹出模态对话框，只记录日志
                # self.show_warning("品种列表正在加载中，请稍候...")
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
            # 🚀 修复UI卡死：progress_signal改为连接到日志输出，而不是模态对话框
            self.reload_thread.progress_signal.connect(
                lambda msg: self.logger.info("进度: %s", msg), Qt.ConnectionType.QueuedConnection
            )
            self.logger.info(">>> 信号连接完成")

            # 启动线程
            self.logger.info(">>> 启动线程...")
            self.reload_thread.start()
            self.logger.info(">>> 线程已启动，isRunning: %s", self.reload_thread.isRunning())

            # 显示加载进度条
            if self.symbol_loading_progress:
                self.symbol_loading_progress.setVisible(True)

            # 🚀 修复：使用非模态的状态栏消息替代模态对话框，避免阻塞UI
            # self.show_info("正在重新加载品种列表，请稍候...")  # ← 模态对话框，会阻塞UI
            self.logger.info("正在重新加载品种列表...")
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
            import time

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

                # 🚀 性能优化：重新加载品种时清空搜索条件，避免对5000+品种进行搜索匹配
                if self.search_input:
                    self.search_input.clear()
                    self.logger.info(">>> 已清空搜索条件")

                # 🔧 关键：重新加载品种后立即更新联想缓存
                t1 = time.time()
                self._load_symbol_cache_for_autocomplete()
                t2 = time.time()
                self.logger.info(">>> 品种联想缓存已启动（后台），耗时: %.3f秒", t2 - t1)

                # 🚀 延迟执行_apply_filters，等待拼音字典构建完成（500ms足够）
                # 避免在字典未构建时进行过滤，减少不必要的计算
                t3 = time.time()
                QTimer.singleShot(500, lambda: self._delayed_apply_filters(t3))
                self.logger.info(">>> _apply_filters已安排延迟执行")

                # 🚀 修复：将模态对话框改为日志输出，避免阻塞UI
                # 用户体验：不再弹出对话框打断用户操作，改为在日志中记录
                if result.get("filtering_in_background"):
                    self.logger.info(
                        "✅ 成功加载 %d 个品种（正在后台过滤未上市品种）", result["symbol_count"]
                    )
                else:
                    self.logger.info("✅ 成功加载 %d 个品种", result["symbol_count"])

                # 检查空品种类别 - 记录到日志而不是弹窗
                empty_categories = result.get("empty_categories", [])
                if empty_categories:
                    self.logger.warning("以下品种类别为空: %s", ", ".join(empty_categories), extra={"log_type": "SYSTEM"})
                    # 不再弹窗，避免阻塞UI
                    # self._show_empty_categories_warning(empty_categories)

                # 如果有其他警告信息 - 记录到日志而不是弹窗
                if result.get("warning"):
                    self.logger.warning("品种加载警告: %s", result["warning"], extra={"log_type": "SYSTEM"})
                    # 不再弹窗，避免阻塞UI
                    # self.show_warning(result["warning"])
            else:
                self.logger.error(">>> 加载失败: %s", result.get("message"), exc_info=True, extra={"log_type": "USER_FEEDBACK"})
                self.show_error(f"加载失败: {result.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error(">>> 处理加载结果失败: %s", e, exc_info=True, extra={"log_type": "USER_FEEDBACK"})
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
        self.logger.error("重新加载品种失败: %s", error_message, exc_info=True, extra={"log_type": "USER_FEEDBACK"})

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
                    # 🚀 修复UI卡死：使用非阻塞日志替代模态对话框
                    self.logger.warning(
                        "品种列表缓存不存在！请先点击「🔄 重新加载品种」按钮来初始化品种数据。"
                        "提示：「🔄 重新加载品种」从通达信服务器获取完整品种列表，「↻ 刷新品种」从本地缓存刷新品种列表"
                    )
                else:
                    self.show_error(f"刷新失败: {result.get('message', '未知错误')}")
                return

            # 获取数据
            data = result.get("data", [])
            is_outdated = result.get("is_outdated", False)

            if not data or len(data) == 0:
                self.logger.debug("品种缓存为空（可能正在初始化或需要重新加载）")
                self.show_warning("⚠️ 无品种缓存，请先点击【重新加载品种】按钮获取品种列表")
                self.all_symbols_data = []
                self.filtered_symbols_data = []
                self._update_symbols_table()
                return

            # 显示缓存状态（如果过时，记录日志但继续）
            if is_outdated:
                # 🚀 修复UI卡死：不再使用模态对话框询问用户，直接记录日志并继续
                self.logger.warning(
                    "品种列表缓存已过时（次日0时已失效），建议点击「🔄 重新加载品种」进行增量更新"
                )
                # 继续使用过时缓存，不中断用户操作

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

            # 🚀 修复UI卡死：不使用模态对话框，只记录日志
            self.logger.warning("空品种类别警告: %s - %s", empty_categories, warning_msg)

        except Exception as e:
            self.logger.error("显示空品种类别警告失败: %s", e, exc_info=True)

    def _load_symbols_data(self):
        """初始加载品种数据."""
        self._refresh_symbols()

    def _delayed_apply_filters(self, start_time):
        """延迟执行_apply_filters（用于等待拼音字典构建完成）

        Args:
            start_time: 开始时间戳（用于计算总耗时）
        """
        import time

        self._apply_filters()
        end_time = time.time()
        self.logger.info(">>> _apply_filters延迟执行完成，总耗时: %.3f秒", end_time - start_time)

    def _apply_filters(self):
        """应用筛选条件."""
        import time

        t_start = time.time()

        if not self.all_symbols_data:
            self.filtered_symbols_data = []
            self._update_symbols_table()
            return

        filtered = self.all_symbols_data
        self.logger.info(">>> [_apply_filters] 开始过滤，总数据: %d", len(filtered))

        # 搜索关键字
        if self.search_input:
            search_text = self.search_input.text().strip().lower()
            if search_text:
                t1 = time.time()

                def matches_symbol(symbol_data):
                    """检查品种是否匹配搜索条件"""
                    try:
                        code = self._extract_symbol_code(symbol_data).lower()
                        name = self._extract_symbol_name(symbol_data).lower()

                        # 🚀 性能优化：使用O(1)字典查找替代O(n)列表遍历
                        # 从拼音字典索引中查找（避免嵌套循环）
                        key = (code, name)
                        pinyin = self.symbol_pinyin_dict.get(key, "")

                        # 三种匹配方式：代码、名称、拼音首字母
                        return search_text in code or search_text in name or search_text in pinyin
                    except Exception:
                        # 如果出现异常，至少保证代码和名称匹配
                        code = self._extract_symbol_code(symbol_data).lower()
                        name = self._extract_symbol_name(symbol_data).lower()
                        return search_text in code or search_text in name

                filtered = [s for s in filtered if matches_symbol(s)]
                t2 = time.time()
                self.logger.info(
                    ">>> [_apply_filters] 搜索过滤完成，耗时: %.3f秒，结果: %d",
                    t2 - t1,
                    len(filtered),
                )

        # 交易所筛选
        if self.exchange_combo:
            exchange = self.exchange_combo.currentText()
            if exchange != "全部":
                t1 = time.time()
                filtered = [s for s in filtered if s.get("exchange") == exchange]
                t2 = time.time()
                self.logger.info(
                    ">>> [_apply_filters] 交易所过滤完成，耗时: %.3f秒，结果: %d",
                    t2 - t1,
                    len(filtered),
                )

        # 品种类型筛选
        if self.symbol_type_combo:
            symbol_type = self.symbol_type_combo.currentText()
            if symbol_type != "全部":
                t1 = time.time()
                filtered = [s for s in filtered if s.get("product_type") == symbol_type]
                t2 = time.time()
                self.logger.info(
                    ">>> [_apply_filters] 品种类型过滤完成，耗时: %.3f秒，结果: %d",
                    t2 - t1,
                    len(filtered),
                )

        self.filtered_symbols_data = filtered
        self.current_page = 1

        t_table_start = time.time()
        self._update_symbols_table()
        t_table_end = time.time()

        t_end = time.time()
        self.logger.info(">>> [_apply_filters] 表格更新耗时: %.3f秒", t_table_end - t_table_start)
        self.logger.info(">>> [_apply_filters] 总耗时: %.3f秒", t_end - t_start)

    def _update_symbols_table(self):
        """更新品种表格."""
        import time

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

        t_start = time.time()

        # 计算分页
        total_items = len(self.filtered_symbols_data)
        self.total_pages = max(1, (total_items + self.page_size - 1) // self.page_size)
        start_idx = (self.current_page - 1) * self.page_size
        end_idx = min(start_idx + self.page_size, total_items)
        page_data = self.filtered_symbols_data[start_idx:end_idx]

        self.logger.info(">>> [_update_symbols_table] 开始更新表格，数据量: %d行", len(page_data))

        # 🚀 性能优化：禁用排序和更新，避免每次插入都触发重绘
        t1 = time.time()
        self.symbols_table.setSortingEnabled(False)
        self.symbols_table.setUpdatesEnabled(False)
        t2 = time.time()
        self.logger.info(">>> [_update_symbols_table] 禁用排序和更新，耗时: %.3f秒", t2 - t1)

        try:
            # 更新表格
            t3 = time.time()
            self.symbols_table.setRowCount(len(page_data))
            t4 = time.time()
            self.logger.info(">>> [_update_symbols_table] setRowCount完成，耗时: %.3f秒", t4 - t3)

            t5 = time.time()
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
                    self.logger.error(
                        f"更新第{i}行品种数据失败: {e}, symbol={symbol}", exc_info=True, extra={"log_type": "SYSTEM"}
                    )
                    # 继续处理下一行，不中断整个表格更新
                    continue

            t6 = time.time()
            self.logger.info(
                ">>> [_update_symbols_table] 填充%d行数据，耗时: %.3f秒", len(page_data), t6 - t5
            )

        finally:
            # 🚀 性能优化：重新启用排序和更新
            t7 = time.time()
            self.symbols_table.setUpdatesEnabled(True)
            self.symbols_table.setSortingEnabled(True)
            t8 = time.time()
            self.logger.info(
                ">>> [_update_symbols_table] 重新启用排序和更新，耗时: %.3f秒", t8 - t7
            )

        # 更新统计和分页
        if self.symbols_count_label:
            self.symbols_count_label.setText(f"共 {total_items} 个品种")
        if self.page_label:
            self.page_label.setText(f"第 {self.current_page} 页 / 共 {self.total_pages} 页")
        if self.prev_page_btn:
            self.prev_page_btn.setEnabled(self.current_page > 1)
        if self.next_page_btn:
            self.next_page_btn.setEnabled(self.current_page < self.total_pages)

        t_end = time.time()
        self.logger.info(">>> [_update_symbols_table] 总耗时: %.3f秒", t_end - t_start)

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
            # 避免重复记录ImportError（只记录一次）
            if not self._pypinyin_import_error_logged:
                self.logger.debug("pypinyin未安装，智能联想拼音功能不可用")
                self._pypinyin_import_error_logged = True
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
        # print(...)  # 🔧 已移除：DEBUG调试输出
        if not text or len(text) < 1:
            self.logger.debug("输入为空，跳过联想")
            return

        # 检查缓存是否已加载
        if not self.local_data_cache:
            # print(...)  # 🔧 已移除：DEBUG调试输出
            self.logger.debug("⚠️  local_data_cache为空，联想功能不可用（可能还未加载或本地无数据）")
            return

        # print(...)  # 🔧 已移除：DEBUG调试输出

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
            self.logger.error(f"❌ 更新本地数据搜索联想失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def _load_symbol_cache_for_autocomplete(self):
        """加载品种缓存用于品种列表搜索框的拼音匹配（异步后台加载）

        注意：此缓存仅用于品种列表搜索框的拼音首字母匹配，
        搜索框不使用QCompleter，搜索直接触发品种列表过滤。

        ⚠️ 重要：使用后台线程加载，避免阻塞UI主线程
        """
        import threading

        def load_in_background():
            """后台线程执行数据加载"""
            try:
                if not self.data_center_service:
                    self.logger.debug("[品种列表搜索框] 数据中心服务不可用")
                    return

                self.logger.info("[后台] 开始加载品种缓存用于搜索联想...")

                # 从缓存读取品种列表
                symbols = self.data_center_service.get_symbols_from_cache()
                if not symbols:
                    self.logger.debug("[品种列表搜索框] 品种缓存为空，拼音匹配暂不可用")
                    return

                # 预处理：添加拼音首字母（分批处理，避免内存问题）
                temp_cache = []
                temp_pinyin_dict = {}  # 🚀 在后台线程构建拼音字典索引
                success_count = 0
                error_count = 0

                # 分批处理，每批处理1000个品种，避免一次性处理过多数据
                batch_size = 1000
                for i in range(0, len(symbols), batch_size):
                    batch = symbols[i : i + batch_size]
                    self.logger.debug(
                        f"[后台] 处理品种批次 {i//batch_size + 1}/{(len(symbols) + batch_size - 1)//batch_size}"
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
                                    temp_cache.append(
                                        {"code": code, "name": final_name, "pinyin": pinyin}
                                    )

                                    # 🚀 同时在后台构建拼音字典索引（避免在主线程中构建）
                                    key = (code.lower(), final_name.lower())
                                    temp_pinyin_dict[key] = pinyin.lower()

                                    success_count += 1
                                else:
                                    error_count += 1
                                    self.logger.debug(
                                        f"[后台] 跳过无效品种数据: code={code}, raw_name='{raw_name}', cleaned_name='{name}', final_name='{final_name}'"
                                    )
                            else:
                                error_count += 1
                                self.logger.debug(f"[后台] 跳过非字典品种数据: {symbol}")
                        except Exception as e:
                            error_count += 1
                            self.logger.debug(f"[后台] 处理品种数据失败: {e}, data={symbol}")

                    # 处理一批后强制垃圾回收，避免内存累积
                    import gc

                    gc.collect()

                # 使用QTimer在主线程中更新缓存（传递已构建好的字典）
                QTimer.singleShot(
                    0,
                    lambda: self._update_symbol_cache(
                        temp_cache, temp_pinyin_dict, success_count, error_count
                    ),
                )

            except Exception as e:
                self.logger.error(f"[后台] 加载品种缓存失败: {e}", exc_info=True)

        # 启动后台线程
        thread = threading.Thread(target=load_in_background, daemon=True, name="LoadSymbolCache")
        thread.start()
        self.logger.info("品种缓存加载已启动（后台线程）")

    def _update_symbol_cache(self, cache, pinyin_dict, success_count, error_count):
        """在主线程中更新品种缓存（用于搜索框拼音匹配）

        Args:
            cache: 品种缓存列表
            pinyin_dict: 拼音字典索引（已在后台构建）
            success_count: 成功处理的品种数
            error_count: 跳过的无效品种数
        """
        try:
            # 🚀 性能优化：只做O(1)赋值操作，字典已在后台线程中构建完成
            # 避免在主线程中执行5000次循环，防止UI卡顿
            self.symbol_cache = cache  # O(1) 引用赋值
            self.symbol_pinyin_dict = pinyin_dict  # O(1) 引用赋值

            # 所有无效品种应在后端早期阶段已过滤，前端只记录最终加载结果
            if error_count > 0:
                self.logger.debug(f"品种缓存加载时跳过了{error_count}个无效数据")
            self.logger.info(
                f"✅ 品种缓存加载完成: {success_count} 个品种（拼音联想已就绪，字典索引已构建）"
            )

        except Exception as e:
            self.logger.error(f"更新品种缓存失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def _load_local_data_index_for_autocomplete(self):
        """加载本地数据索引用于本地数据搜索框联想

        优化方案：简化加载逻辑，直接从数据库读取（已有索引，无需扫描文件）
        学习品种列表的简洁方式，但保持QCompleter机制（不破坏现有架构）
        """
        try:
            self.logger.info("🔄 [联想] 开始加载本地数据索引...")

            # 直接从数据库读取（快速，无需后台线程）
            if not self.db_manager:
                self.logger.warning("🔴 [联想] 数据库管理器不可用")
                return

            # 从数据库获取本地数据索引（步骤7已更新到数据库）
            local_symbol_codes = self.db_manager.get_local_data_index()

            if not local_symbol_codes:
                self.logger.warning("⚠️ [联想] 本地数据索引为空")
                self._update_local_data_cache([], 0, 0)
                return

            self.logger.info(f"🔄 [联想] 从数据库获取到 {len(local_symbol_codes)} 个品种代码")

            # 需要品种名称来提供更好的联想体验
            # 从品种缓存获取名称映射
            code_to_name = {}
            if self.data_center_service:
                try:
                    symbols_list = self.data_center_service.get_symbols_from_cache()
                    if symbols_list:
                        for s in symbols_list:
                            code_to_name[s.get("symbol", "")] = s.get("name", "")
                except Exception as e:
                    self.logger.debug(f"[联想] 获取品种名称映射失败: {e}")

            # 构建联想缓存
            temp_cache = []
            for code in local_symbol_codes:
                name = code_to_name.get(code, "")
                pinyin = self._get_pinyin_initials(name) if name else ""
                temp_cache.append({"code": code, "name": name, "pinyin": pinyin})

            # 直接更新缓存（无需异步）
            self._update_local_data_cache(temp_cache, len(temp_cache), 0)

        except Exception as e:
            self.logger.error(f"❌ [联想] 加载失败: {e}", exc_info=True, extra={"log_type": "USER_FEEDBACK"})
            self._update_loading_status_error("加载失败")

    def _update_local_data_cache(self, cache, success_count, error_count):
        """在主线程中更新本地数据缓存"""
        self.logger.info(
            f"✅ [联想] 主线程更新缓存: 收到{len(cache)}个品种, 成功={success_count}, 失败={error_count}"
        )

        self.local_data_cache = cache
        self._local_data_index_loaded = True  # 🔧 标记已加载，避免重复加载

        # 所有无效品种应在后端早期阶段已过滤，前端只记录最终加载结果
        if error_count > 0:
            self.logger.debug(f"[联想] 加载时跳过了{error_count}个无效数据")

        self.logger.info(f"✅ [联想] 本地数据索引加载完成: {success_count} 个品种，联想功能已启用")

        # 🆕 更新状态提示标签
        if self.symbol_input_status_label:
            # 🔧 修复：显示状态标签
            self.symbol_input_status_label.setVisible(True)
            if success_count > 0:
                self.symbol_input_status_label.setText(f"✅ 已加载 {success_count} 个品种")
                self.symbol_input_status_label.setStyleSheet(
                    "color: #4CAF50; font-size: 11px; padding-left: 5px;"
                )
                # 3秒后隐藏提示
                status_label = self.symbol_input_status_label  # 保存引用避免类型检查问题
                QTimer.singleShot(
                    3000, lambda: status_label.setVisible(False) if status_label else None
                )
            else:
                # 🔧 修复：本地无数据时，不显示警告（因为这是正常情况）
                # 只在手动刷新或下载后再显示相关提示
                self.symbol_input_status_label.setVisible(False)

    def _update_loading_status_error(self, reason: str):
        """更新索引加载状态为错误"""
        if self.symbol_input_status_label:
            self.symbol_input_status_label.setText(
                f"⚠️ 索引加载失败（{reason}），请手动输入完整代码"
            )
            self.symbol_input_status_label.setStyleSheet(
                "color: #F44336; font-size: 11px; padding-left: 5px;"
            )

    def _on_local_data_index_ready(self, event):
        """处理本地数据索引就绪事件（来自后台数据质量扫描）

        ⚠️ 关键：vnpy事件引擎可能在非Qt主线程中调用此方法
        所有Qt UI操作必须通过QTimer.singleShot转发到主线程
        """
        try:
            if self._local_data_index_loaded:
                return  # 已加载，跳过

            data = event.data
            symbol_list = data.get("symbols", [])
            count = data.get("count", 0)

            self.logger.info(f"📋 收到本地数据索引事件: {count} 个品种")

            # 添加拼音首字母（在后台线程中处理，不涉及UI）
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

            # 转发到主线程执行UI更新
            from functools import partial

            QTimer.singleShot(0, partial(self._update_local_data_index_ui, temp_cache))

        except Exception as e:
            self.logger.error(f"处理本地数据索引事件失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def _update_local_data_index_ui(self, temp_cache):
        """更新本地数据索引UI（在主线程中执行）"""
        try:
            # 更新缓存（_update_local_data_cache 会自动设置 _local_data_index_loaded 标志）
            self._update_local_data_cache(temp_cache, len(temp_cache), 0)
        except Exception as e:
            self.logger.error(f"更新本地数据索引UI失败: {e}", exc_info=True)

    def _load_local_data_index_fallback(self):
        """后备方案：如果事件推送未到达，手动加载本地数据索引"""
        if self._local_data_index_loaded:
            self.logger.info("本地数据索引已通过事件加载，跳过后备方案")
            return

        self.logger.info("未收到本地数据索引事件，启动后备方案手动加载...")
        # 调用原有的加载方法
        self._load_local_data_index_for_autocomplete()

    def _on_file_watcher_started(self, event):
        """处理文件监控启动事件

        ⚠️ 关键：vnpy事件引擎可能在非Qt主线程中调用此方法
        所有Qt UI操作必须通过QTimer.singleShot转发到主线程
        """
        try:
            self.logger.info("文件监控已启动，解锁数据扫描按钮")
            # 转发到主线程执行UI更新
            QTimer.singleShot(0, self._handle_file_watcher_started_ui)
        except Exception as e:
            self.logger.error(f"处理文件监控启动事件失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def _handle_file_watcher_started_ui(self):
        """处理文件监控启动UI（在主线程中执行）"""
        try:
            if self.scan_data_btn:
                self.scan_data_btn.setEnabled(True)
        except Exception as e:
            self.logger.error(f"处理文件监控启动UI失败: {e}", exc_info=True)

    def _on_data_metrics_updated(self, event):
        """处理数据指标更新事件

        ⚠️ 关键：vnpy事件引擎可能在非Qt主线程中调用此方法
        所有Qt UI操作必须通过QTimer.singleShot转发到主线程
        """
        try:
            # 🔧 关键修复：添加详细日志，确保事件被接收到
            event_type = event.type if hasattr(event, "type") else "unknown"
            self.logger.info(
                f"[事件处理] 🔔 _on_data_metrics_updated 被调用: event.type={event_type}"
            )

            data = event.data
            total_symbols = data.get("total_symbols", 0)
            downloaded = data.get("downloaded", 0)
            missing = data.get("missing", 0)
            invalid_count = data.get("invalid_count", 0)
            details = data.get("details", [])  # 🆕 获取详细品种列表

            self.logger.info(
                f"[事件处理] 📊 收到数据指标更新事件: 总品种={total_symbols}, "
                f"已下载={downloaded}, 缺失={missing}, 失效={invalid_count}, "
                f"详情={len(details)}个品种"
            )

            # 🔧 使用Qt Signal机制，确保UI更新在主线程执行
            self.logger.debug(f"[事件处理] 准备发射 data_metrics_update_signal: missing={missing}")
            self.data_metrics_update_signal.emit(
                total_symbols, downloaded, missing, invalid_count, details
            )
            self.logger.info(f"[事件处理] ✅ 已发射data_metrics_update_signal: missing={missing}")

        except Exception as e:
            self.logger.error(f"[事件处理] ❌ 处理数据指标更新事件失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def _update_data_metrics_ui(
        self, total_symbols, downloaded, missing, invalid_count, details=None
    ):
        """更新数据指标UI（在主线程中执行）

        Args:
            total_symbols: 总品种数（参考品种+失效品种）
            downloaded: 已下载品种数
            missing: 品种缺失数
            invalid_count: 失效品种数
            details: 详细品种列表（可选），包含缺失和失效品种的详细信息
        """
        self.logger.info(
            f"🔧 [进入] _update_data_metrics_ui: total={total_symbols}, "
            f"downloaded={downloaded}, missing={missing}, invalid={invalid_count}, "
            f"details={len(details) if details else 0}个品种"
        )
        try:
            # 🔧 更新品种问题UI（上部分）
            self._update_symbol_issues_ui(
                total_symbols=total_symbols,
                downloaded=downloaded,
                missing=missing,
                invalid_count=invalid_count,
            )

            # 🆕 如果有详细品种列表，添加到品种问题详情表格
            if details and len(details) > 0:
                self._append_symbol_issues_details(details)
                self.logger.info(f"📋 步骤7增量推送 {len(details)} 个问题品种到详情表格")

            # 🔧 兼容旧代码：同时更新旧UI（如果存在）
            if total_symbols > 0:
                self._symbol_cache_count = total_symbols
                if self.total_symbols_label:
                    self.total_symbols_label.setText(f"总品种: {total_symbols}")
            if self.downloaded_symbols_label:
                self.downloaded_symbols_label.setText(f"已下载: {downloaded}")
            if self.missing_symbols_label:
                self.missing_symbols_label.setText(f"品种缺失: {missing}")
            if self.invalid_symbols_label:
                self.invalid_symbols_label.setText(f"失效品种: {invalid_count}")

            self.logger.info(
                f"✅ 数据指标UI已更新: 总品种={total_symbols}, 已下载={downloaded}, 缺失={missing}"
            )

        except Exception as e:
            self.logger.error(f"处理数据指标更新事件失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def _on_invalid_symbols_updated(self, event):
        """处理失效品种更新事件

        ⚠️ 关键：vnpy事件引擎可能在非Qt主线程中调用此方法
        所有Qt UI操作必须通过QTimer.singleShot转发到主线程
        """
        try:
            data = event.data
            invalid_symbols = data.get("symbols", [])
            count = data.get("count", 0)

            self.logger.info(f"📋 收到失效品种更新: {count} 个品种")

            # 转发到主线程执行UI更新
            from functools import partial

            QTimer.singleShot(0, partial(self._update_invalid_symbols_ui, count))

        except Exception as e:
            self.logger.error(f"处理失效品种更新事件失败: {e}", exc_info=True)

    def _update_invalid_symbols_ui(self, count):
        """更新失效品种UI（在主线程中执行）"""
        self.logger.info(f"🔧 [进入] _update_invalid_symbols_ui: count={count}")
        try:
            # 🔧 更新品种问题UI（上部分）
            self._update_symbol_issues_ui(invalid_count=count)

            # 🔧 兼容旧代码：同时更新旧UI（如果存在）
            if self.invalid_symbols_label:
                self.invalid_symbols_label.setText(f"失效品种: {count}")

        except Exception as e:
            self.logger.error(f"更新失效品种UI失败: {e}", exc_info=True)

    def _on_symbol_cache_loaded(self, event):
        """处理品种列表缓存加载完成事件

        ⚠️ 关键：vnpy事件引擎可能在非Qt主线程中调用此方法
        使用Qt Signal确保UI更新在主线程执行
        """
        try:
            data = event.data
            symbol_count = data.get("symbol_count", 0)
            is_new = data.get("is_new", False)

            self.logger.info(
                f"[事件处理] 📋 收到品种列表加载完成事件: symbol_count={symbol_count}, is_new={is_new}"
            )

            # 🔧 修复：使用Qt Signal机制，确保UI更新在主线程执行
            self.symbol_cache_loaded_signal.emit(symbol_count)
            self.logger.info(
                f"[事件处理] ✅ 已发射symbol_cache_loaded_signal: symbol_count={symbol_count}"
            )

        except Exception as e:
            self.logger.error(f"[事件处理] ❌ 处理品种列表加载完成事件失败: {e}", exc_info=True)

    def _update_symbol_cache_ui(self, symbol_count):
        """更新品种列表缓存UI（在主线程中执行）"""
        self.logger.info(f"[UI更新] 🎯 _update_symbol_cache_ui被调用: symbol_count={symbol_count}")
        try:
            # 更新状态变量
            self._symbol_cache_count = symbol_count
            self._symbol_cache_event_received = True  # 🔧 新增：标记事件已到达
            self.logger.info(f"[UI更新] _symbol_cache_count已更新为: {self._symbol_cache_count}")

            # 🔧 新增：事件到达后，触发主动拉取补充其他数据（本地品种、失效品种）
            # 这些数据可能还没有通过事件推送，需要主动拉取补充
            QTimer.singleShot(500, self._pull_startup_data_supplement)

            # 更新总品种标签
            if self.total_symbols_label:
                self.total_symbols_label.setText(f"总品种: {symbol_count}")
                self.total_symbols_label.setStyleSheet("color: #2196F3; font-weight: bold;")
                self.logger.info(f"[UI更新] ✅ total_symbols_label已更新")
            else:
                self.logger.warning(f"[UI更新] ⚠️ total_symbols_label为None！")

            self.logger.info(f"[UI更新] ✅ 总品种UI更新完成: {symbol_count}")

        except Exception as e:
            self.logger.error(f"[UI更新] ❌ 更新品种列表缓存UI失败: {e}", exc_info=True)

    def _on_validation_completed(self, event):
        """处理启动流程验证完成事件

        ⚠️ 关键：vnpy事件引擎可能在非Qt主线程中调用此方法
        所有Qt UI操作必须通过QTimer.singleShot转发到主线程
        """
        try:
            data = event.data
            success = data.get("success", False)

            self.logger.info(f"🎉 收到启动流程验证完成事件: success={success}")

            # 转发到主线程执行UI更新
            from functools import partial

            QTimer.singleShot(0, partial(self._update_validation_completed_ui, success))

        except Exception as e:
            self.logger.error(f"处理启动流程验证完成事件失败: {e}", exc_info=True)

    def _update_validation_completed_ui(self, success):
        """更新启动流程验证完成UI（在主线程中执行）"""
        self.logger.info(f"🔧 [进入] _update_validation_completed_ui: success={success}")
        try:
            # 更新状态变量
            self._lightweight_running = False

            # 更新按钮状态
            self._update_scan_button_state()

            self.logger.info(f"✅ 启动流程已完成，扫描按钮状态已更新")

        except Exception as e:
            self.logger.error(f"更新启动流程验证完成UI失败: {e}", exc_info=True)

    def _on_data_scan_finished(self, event):
        """处理数据扫描完成事件

        ⚠️ 关键：vnpy事件引擎可能在非Qt主线程中调用此方法
        所有Qt UI操作必须通过QTimer.singleShot转发到主线程
        """
        try:
            data = event.data
            scan_type = data.get("scan_type", "")
            overview = data.get("overview", {})

            self.logger.info(
                f"✓ 数据扫描完成: 类型={scan_type}, "
                f"缺失={overview.get('missing_symbols', 0)}, "
                f"错误={overview.get('error_symbols', 0)}"
            )

            # 转发到主线程执行UI更新
            from functools import partial

            QTimer.singleShot(0, partial(self._handle_data_scan_finished_ui, overview))

        except Exception as e:
            self.logger.error(f"处理数据扫描完成事件失败: {e}", exc_info=True)

    def _handle_data_scan_finished_ui(self, overview):
        """处理数据扫描完成UI（在主线程中执行）"""
        try:
            # 更新UI统计
            if "missing_symbols" in overview:
                if self.missing_symbols_label:
                    self.missing_symbols_label.setText(f"品种缺失: {overview['missing_symbols']}")
            if "error_symbols" in overview:
                if self.data_missing_symbols_label:
                    self.data_missing_symbols_label.setText(
                        f"数据缺失: {overview['error_symbols']}"
                    )
        except Exception as e:
            self.logger.error(f"处理数据扫描完成UI失败: {e}", exc_info=True)

    def _on_quality_scan_phase(self, event):
        """处理数据质量扫描阶段性推送事件

        ⚠️ 关键：vnpy事件引擎可能在非Qt主线程中调用此方法
        所有Qt UI操作必须通过Qt Signal机制转发到主线程

        增量更新UI，用户可以立即看到各个阶段的数据，无需等待全部扫描完成。

        # 优化原因：修复复杂UI更新的线程安全问题（涉及大量QLabel和QTableWidget）
        # 问题：此事件处理器需要更新10+个标签、设置样式、更新表格，跨线程操作会导致严重的Qt警告
        # 解决：使用Qt Signal-Slot机制，确保UI更新在主线程执行（最佳实践）
        # 效果：消除Qt警告，确保UI更新流畅且不卡顿

        # 🔧 关键修复：大量details数据不通过Signal传递，直接在此处理后转发到主线程
        """
        try:
            data = event.data
            phase = data.get("phase", 0)
            metrics = data.get("metrics", {})
            status = data.get("status", "")

            # 🔧 关键：提取details，避免通过Signal传递大量数据
            # 🔧 修复：兼容性处理 - 优先从metrics中读取，如果不存在则从顶层读取（向后兼容）
            details = metrics.get("details", [])
            if not details:
                # 向后兼容：如果metrics中没有details，尝试从顶层读取
                details = data.get("details", [])
            details_count = len(details)

            # 构建不含details的metrics（用于Signal传递）
            metrics_for_signal = {k: v for k, v in metrics.items() if k != "details"}

            # 🔧 修复：只输出摘要信息
            metrics_summary = dict(metrics_for_signal)
            metrics_summary["details_count"] = details_count
            self.logger.info(f"[事件处理] 📊 收到阶段{phase}推送: {metrics_summary}")

            # 🔧 如果有details，通过Signal转发到主线程处理（✅ 更可靠的方式）
            if details and details_count > 0:
                # 🔥 强制输出到terminal
                self.logger.debug(f"[CRITICAL-DEBUG-UI] 前端收到details: {details_count}个")
                sys.stderr.flush()

                self.logger.info(
                    f"[事件处理] 📋 准备通过Signal推送 {details_count} 个问题品种详情到UI"
                )
                # 🔧 修复：使用Signal替代QTimer.singleShot（更可靠）
                self.append_details_signal.emit(details)
            else:
                # 🔥 强制输出：没有details的情况
                self.logger.warning(
                    f"[CRITICAL-DEBUG-UI] 前端收到metrics但details为空！details={details}, details_count={details_count}",
                    extra={"log_type": "SYSTEM"}
                )

            # 🔧 使用Qt Signal传递控制信号和统计数据（不含details）
            self.quality_scan_phase_signal.emit(phase, metrics_for_signal, status)
            self.logger.info(f"[事件处理] ✅ 已发射quality_scan_phase_signal (phase={phase})")

        except Exception as e:
            self.logger.error(f"[事件处理] ❌ 处理质量扫描阶段事件失败: {e}", exc_info=True)

    def _update_quality_scan_phase_ui(self, phase, metrics, status):
        """更新数据质量扫描阶段UI（在主线程中执行）"""
        try:
            # 🔍 诊断：检查metrics和details的完整性
            details_info = (
                "无" if "details" not in metrics else f"{len(metrics.get('details', []))}个"
            )
            self.logger.info(
                f"[UI更新] 🎯 _update_quality_scan_phase_ui被调用: "
                f"phase={phase}, status={status}, "
                f"metrics_keys={list(metrics.keys())}, "
                f"details={details_info}"
            )

            # 🔧 根据phase分离处理逻辑
            if phase == 8:
                # phase=8：更新品种问题UI（过时品种）
                outdated_count = metrics.get("outdated_symbols", 0)
                self._update_symbol_issues_ui(outdated=outdated_count)

                # 🔧 如果有details，追加到品种问题详情表格
                phase_details = metrics.get("details", [])
                if phase_details:
                    self._append_symbol_issues_details(phase_details)

                # 🔧 兼容旧代码
                if self.outdated_symbols_label:
                    self.outdated_symbols_label.setText(f"过时: {outdated_count}")
                    if outdated_count > 0:
                        self.outdated_symbols_label.setStyleSheet("color: #FF9800;")
                    else:
                        self.outdated_symbols_label.setStyleSheet("color: #4CAF50;")

            elif phase == 3:
                # phase=3：更新数据问题UI（错误、数据缺失、警告）
                error_count = metrics.get("error_symbols", 0)
                data_missing_count = metrics.get("data_missing_symbols", 0)
                warning_count = metrics.get("warning_symbols", 0)

                self._update_data_issues_ui(
                    error_count=error_count,
                    data_missing_count=data_missing_count,
                    warning_count=warning_count,
                )

                # 🔧 如果有details，追加到数据问题详情表格
                phase_details = metrics.get("details", [])
                if phase_details:
                    self._append_data_issues_details(phase_details)

                # 🔧 兼容旧代码
                if self.error_symbols_label:
                    self.error_symbols_label.setText(f"错误: {error_count}")
                    if error_count > 0:
                        self.error_symbols_label.setStyleSheet("color: #F44336;")
                    else:
                        self.error_symbols_label.setStyleSheet("color: #4CAF50;")

                if self.data_missing_symbols_label:
                    self.data_missing_symbols_label.setText(f"数据缺失: {data_missing_count}")
                    if data_missing_count > 0:
                        self.data_missing_symbols_label.setStyleSheet("color: #FF9800;")
                    else:
                        self.data_missing_symbols_label.setStyleSheet("color: #4CAF50;")

                if self.warning_symbols_label:
                    self.warning_symbols_label.setText(f"警告: {warning_count}")
                    if warning_count > 0:
                        self.warning_symbols_label.setStyleSheet("color: #FFC107;")
                    else:
                        self.warning_symbols_label.setStyleSheet("color: #4CAF50;")

                # 🆕 阶段3开始时：标记扫描开始，清空数据问题详情表格
                if status == "scanning_quality":
                    self._heavy_scan_running = True
                    if self.data_issues_detail_table:
                        self.data_issues_detail_table.setRowCount(0)
                        self.data_issues_detail_table.viewport().update()

            # 🔒 扫描完成时：重置标志，更新按钮状态
            if status == "complete":
                self.is_quality_scanning = False
                self._heavy_scan_running = False
                if self.scan_data_btn:
                    self.scan_data_btn.setEnabled(True)
                    self.scan_data_btn.setText("数据扫描")
                self.logger.info("✅ 扫描完成，已重置扫描标志并更新按钮状态")

        except Exception as e:
            self.logger.error(f"更新质量扫描阶段UI失败: {e}", exc_info=True)

    # ==================== 本地数据事件处理 ====================

    def _query_local_data(self):
        """查询本地数据."""
        try:
            self.logger.info("🔍 开始查询本地数据...")

            # 检查服务
            if not self.data_center_service:
                self.logger.error("❌ 数据中心服务未初始化", exc_info=True, extra={"log_type": "SYSTEM"})
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

            # 记录用户操作
            logger_user.info(
                "用户查询本地数据: 品种=%s, 周期=%s, 时间范围=%s至%s",
                symbol,
                interval,
                start_date_str,
                end_date_str,
            )

            # 检查data_table
            if not self.data_table:
                self.logger.error("❌ data_table 未初始化")
                self.show_error("数据展示组件未初始化")
                return

            self.logger.info(f"✅ data_table 已就绪，当前行数: {self.data_table.rowCount()}")

            # 不弹窗，只记录日志（查询很快，不需要弹窗提示）
            self.logger.info("正在查询本地数据...")

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
                    # 🆕 区分品种不存在 vs 未下载
                    try:
                        symbol_exists = self.data_center_service.check_symbol_exists(symbol)

                        if not symbol_exists:
                            # 品种代码不存在
                            self.show_warning(
                                f"品种代码 {symbol} 不存在\n"
                                f"请检查代码格式是否正确（如：600000、000001）"
                            )
                            self.logger.warning(f"⚠️ 品种 {symbol} 不存在于交易所品种列表")
                        else:
                            # 品种存在但未下载
                            self.show_info(
                                f"品种 {symbol} 尚未下载本地数据\n"
                                f"建议前往【数据下载】模块进行批量下载"
                            )
                            self.logger.info(f"ℹ️ 品种 {symbol} 存在但未下载本地数据")
                    except Exception as check_error:
                        # 检查失败时使用原有提示
                        msg = f"查询成功，品种 {symbol} 暂无本地数据"
                        self.logger.info(f"✅ {msg}")
                        self.logger.debug(f"品种存在性检查失败: {check_error}")
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

    def _start_download_with_symbols(self, symbols: List[str], start_date, end_date) -> None:
        """开始下载指定品种列表（用于修复下载）

        Args:
            symbols: 品种代码列表
            start_date: 开始日期
            end_date: 结束日期
        """
        try:
            # 检查是否有正在进行的下载
            if self.download_thread and self.download_thread.isRunning():
                self.show_warning("已有下载任务正在运行，请等待完成或先停止")
                return

            # 记录到进度文本
            from datetime import datetime

            timestamp = datetime.now().strftime("%H:%M:%S")
            if self.progress_text:
                self.progress_text.appendPlainText(
                    f"\n[{timestamp}] ========== 开始修复下载 =========="
                )
                self.progress_text.appendPlainText(f"[{timestamp}] 品种数量: {len(symbols)}")
                self.progress_text.appendPlainText(
                    f"[{timestamp}] 日期范围: {start_date} 至 {end_date}"
                )
                self.progress_text.appendPlainText(f"[{timestamp}] 模式: 智能修复（覆盖本地数据）")

            # 创建下载线程
            self.download_thread = DownloadThread(
                data_center_service=self.data_center_service,
                start_date=start_date.strftime("%Y-%m-%d"),
                parent=self,
                symbols=symbols,
                end_date=end_date.strftime("%Y-%m-%d"),
            )

            # 连接信号（使用正确的信号名称）
            self.download_thread.finished_signal.connect(
                self._on_download_finished, Qt.ConnectionType.QueuedConnection
            )
            self.download_thread.error_signal.connect(
                self._on_download_error, Qt.ConnectionType.QueuedConnection
            )
            self.download_thread.progress_signal.connect(
                self._append_progress_text, Qt.ConnectionType.QueuedConnection
            )

            # 更新UI状态
            if self.start_download_btn:
                self.start_download_btn.setEnabled(False)
            if self.pause_download_btn:
                self.pause_download_btn.setEnabled(True)
            if self.stop_download_btn:
                self.stop_download_btn.setEnabled(True)

            # 启动下载
            self.download_thread.start()

            self.logger.info(f"修复下载已启动: {len(symbols)}个品种")

        except Exception as e:
            self.logger.error(f"启动修复下载失败: {e}", exc_info=True)
            self.show_error(f"启动修复下载失败: {e}")

    def _start_download(self):
        """开始下载（异步版本）."""
        try:
            self.logger.info("=" * 60)
            self.logger.info(">>> _start_download() 被调用")
            self.logger.info("=" * 60)

            if not self.data_center_service:
                self.logger.error(">>> 数据中心服务未初始化", exc_info=True, extra={"log_type": "SYSTEM"})
                self.show_error("数据中心服务未初始化")
                return

            # ✅ 新增：检查品种缓存是否存在（避免"未找到可下载的品种"错误）
            symbols = self.data_center_service.get_symbols_from_cache()
            if not symbols or len(symbols) == 0:
                self.logger.warning(">>> 品种列表缓存为空，无法开始下载")
                # 🚀 修复UI卡死：直接切换到品种列表Tab，不使用模态对话框
                self.logger.warning(
                    "品种列表缓存为空，无法开始下载。请先切换到【品种列表】选项卡，点击【🔄 重新加载品种】或【↻ 刷新品种】按钮"
                )
                # 自动切换到品种列表选项卡（第0个选项卡）
                if self.tab_widget:
                    self.tab_widget.setCurrentIndex(0)
                return

            self.logger.info(f">>> 品种缓存检查通过，共 {len(symbols)} 个品种")

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

            # 记录用户操作
            logger_user.info(
                "用户点击开始下载按钮: 开始日期=%s, 品种数=%d", start_date, len(symbols)
            )

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

            # 显示加载提示（使用logger，避免UI更新）
            # self.show_info(f"正在启动下载任务...")
            self.logger.info("正在启动下载任务: 任务ID=%s", task_id)
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
                    self.logger.info("下载任务已启动(异步): 任务ID=%s, 消息=%s", task_id, message)
                    self.logger.info("下载正在后台进行，请查看终端进度")

                    # 🔧 启动进度轮询定时器
                    self._start_progress_polling()

                    # 注意：保持按钮状态，允许用户停止下载
                else:
                    # 同步下载或真正完成
                    # 禁用show_info，避免UI崩溃
                    # self.show_info(f"✅ 下载任务已完成！任务ID: {task_id}")
                    self.logger.info("下载任务完成成功: 任务ID=%s", task_id)

                    # 🆕 记录下载历史
                    self._add_download_history(result)

                    self._reset_download_state()
            else:
                self.logger.error("下载任务失败: %s", result.get("message", "未知错误"))

                # 🆕 记录下载历史（即使失败也要记录）
                if result.get("task_id"):
                    self._add_download_history(result)

                self._reset_download_state()

        except Exception as e:
            self.logger.error("❌ 处理下载结果失败: %s", e, exc_info=True, extra={"log_type": "USER_FEEDBACK"})
            self._reset_download_state()

    def _on_download_error(self, error_message: str):
        """下载出错的回调（在UI线程中执行）.

        Args:
            error_message: 错误消息
        """
        self.logger.error("下载失败: %s", error_message)

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
                self.logger.info("停止信号已发送，下载将在当前品种完成后停止")
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

    def _pull_startup_data(self):
        """主动拉取启动流程数据（补偿机制）

        时序策略：
        1. 如果事件已到达，只拉取本地和失效品种数据
        2. 如果事件未到达，延迟后再次尝试（超时机制）
        """
        try:
            self.logger.debug("🔄 [主动拉取] 开始拉取启动流程数据...")

            # 检查事件是否已到达
            if self._symbol_cache_event_received:
                # 事件已到达，只拉取补充数据（本地品种、失效品种）
                self.logger.debug("🔄 [主动拉取] 事件已到达，只拉取补充数据（本地品种、失效品种）")
                self._pull_supplement_data_only()
                return

            # 事件未到达，延迟后重试（超时机制）
            # 如果3秒后事件仍未到达，则使用备用方案
            self.logger.debug("🔄 [主动拉取] 事件未到达，延迟3秒后重试（超时机制）")
            # 🔧 关键修复：不再延迟，直接执行备用方案
            # 因为QTimer.singleShot回调可能不执行
            self.logger.info("🔧 [主动拉取] 直接执行备用方案，不延迟")
            self._pull_startup_data_fallback()

        except Exception as e:
            self.logger.error(f"❌ [主动拉取] 拉取启动流程数据失败: {e}", exc_info=True)

    def _pull_startup_data_with_timeout(self):
        """带超时的主动拉取（事件未到达时的备用方案）"""
        try:
            # 再次检查事件是否已到达
            if self._symbol_cache_event_received:
                self.logger.debug("🔄 [主动拉取] 超时前事件已到达，切换到补充数据模式")
                self._pull_supplement_data_only()
                # 🔧 关键修复：即使事件已到达，也要确保按钮状态正确
                if self._missing_count > 0:
                    self.logger.info(
                        f"🔧 [主动拉取] 事件已到达，手动触发按钮状态更新: _missing_count={self._missing_count}"
                    )
                    self._update_repair_button_state()
                return

            # 事件仍未到达，使用备用方案
            self.logger.info("ℹ️ [主动拉取] 事件超时未到达，使用备用方案拉取数据")
            self._pull_startup_data_fallback()

            # 🔧 关键修复：备用方案执行后，再次检查是否有缺失数据需要更新按钮
            if self._missing_count > 0:
                self.logger.info(
                    f"🔧 [主动拉取] 备用方案执行后，手动触发按钮状态更新: _missing_count={self._missing_count}"
                )
                self._update_repair_button_state()

        except Exception as e:
            self.logger.error(f"❌ [主动拉取] 超时拉取失败: {e}", exc_info=True)

    def _pull_supplement_data_only(self):
        """只拉取补充数据（本地品种、失效品种），不拉取总品种数"""
        try:
            if not self.db_manager:
                return

            local_symbols = self.db_manager.get_local_data_index()
            invalid_symbols = self.db_manager.get_invalid_symbols()

            self.logger.info(
                f"🔄 [主动拉取] 补充数据: 本地={len(local_symbols)}, 失效={len(invalid_symbols)}"
            )

            # 只更新已下载和失效品种，不更新总品种
            self._update_pulled_data_ui(
                symbol_count=0,  # 不更新总品种
                local_count=len(local_symbols),
                invalid_count=len(invalid_symbols),
                skip_total=True,
            )

        except Exception as e:
            self.logger.error(f"❌ [主动拉取] 补充数据拉取失败: {e}", exc_info=True)

    def _pull_startup_data_fallback(self):
        """备用方案：从缓存文件或服务拉取数据"""
        try:
            # 1. 从数据库获取本地数据索引和缺失品种
            if not self.db_manager:
                self.logger.warning("⚠️ [主动拉取] 数据库管理器不可用")
                return

            local_symbols = self.db_manager.get_local_data_index()
            invalid_symbols = self.db_manager.get_invalid_symbols()

            # 🔧 关键修复：直接查询数据库获取缺失品种数（从最新推送的事件数据）
            missing_count_from_db = 0
            try:
                # 查询最新的数据指标（步骤7推送的数据）
                from backend.services.database_adapter import get_db_manager

                db = get_db_manager()
                # 这里可以从数据库查询最新的缺失品种数，或者直接通过ChinaStockEngine获取
                if self.data_center_service:
                    china_stock_engine = getattr(
                        self.data_center_service, "china_stock_engine", None
                    )
                    if china_stock_engine:
                        # 🔧 修复：架构v3.0重构后，从core_engine导入
                        from backend.infrastructure.data_module_vnpy import (
                            ValidationEventPublisher,
                        )

                        # 通过对比参考品种和本地品种计算缺失
                        pass
            except Exception as e:
                self.logger.debug(f"从数据库查询缺失品种数失败: {e}")

            self.logger.info(
                f"🔄 [主动拉取] 从数据库获取数据: "
                f"本地品种={len(local_symbols)}, 失效品种={len(invalid_symbols)}"
            )

            # 2. 🔧 关键修复：从缓存文件获取参考品种列表，并计算缺失品种
            reference_count = 0
            reference_symbols_set = set()

            # 🔧 诊断：检查前置条件
            self.logger.info(f"🔧 [诊断] data_center_service={self.data_center_service}")

            if self.data_center_service:
                try:
                    china_stock_engine = getattr(
                        self.data_center_service, "china_stock_engine", None
                    )
                    self.logger.info(f"🔧 [诊断] china_stock_engine={china_stock_engine}")

                    if china_stock_engine:
                        cache_manager = getattr(china_stock_engine, "cache_manager", None)
                        self.logger.info(f"🔧 [诊断] cache_manager={cache_manager}")

                        if cache_manager:
                            # 🔧 修复：使用正确的缓存文件名
                            symbols_cache_file = cache_manager.root / "stock_list_classified.json"

                            self.logger.info(
                                f"🔧 [主动拉取] 准备读取缓存文件: {symbols_cache_file}"
                            )

                            if symbols_cache_file.exists():
                                import json

                                with open(symbols_cache_file, "r", encoding="utf-8") as f:
                                    symbols_data = json.load(f)
                                    # 🔧 修复：stock_list_classified.json的数据结构
                                    # 包含：sh_stocks, sz_stocks, bj_stocks, etf_funds, convertible_bonds等
                                    all_symbols_dict = {}

                                    # 提取所有分类中的品种
                                    for category in [
                                        "sh_stocks",
                                        "sz_stocks",
                                        "bj_stocks",
                                        "etf_funds",
                                        "convertible_bonds",
                                    ]:
                                        category_data = symbols_data.get(category, [])
                                        for s in category_data:
                                            if isinstance(s, dict):
                                                symbol = s.get("symbol", "")
                                                if symbol:
                                                    all_symbols_dict[symbol] = s
                                            elif isinstance(s, str):
                                                all_symbols_dict[s] = {"symbol": s}

                                    reference_symbols_set = set(all_symbols_dict.keys())
                                    reference_count = len(reference_symbols_set)

                                    self.logger.info(
                                        f"🔧 [主动拉取] 从缓存获取参考品种数: {reference_count}"
                                    )
                            else:
                                self.logger.warning(
                                    f"⚠️ [主动拉取] 缓存文件不存在: {symbols_cache_file}"
                                )
                        else:
                            self.logger.warning("⚠️ [诊断] cache_manager为None，无法读取缓存")
                    else:
                        self.logger.warning(
                            "⚠️ [诊断] china_stock_engine为None，无法获取cache_manager"
                        )
                except Exception as e:
                    self.logger.error(f"❌ [主动拉取] 从缓存文件获取数据失败: {e}", exc_info=True)
            else:
                self.logger.warning("⚠️ [诊断] data_center_service为None，无法读取缓存")

            # 3. 🔧 关键修复：计算缺失品种数（对比参考品种和本地品种）
            missing_count_calculated = 0
            if reference_symbols_set:
                local_symbols_set = set(local_symbols)
                missing_symbols_set = reference_symbols_set - local_symbols_set
                missing_count_calculated = len(missing_symbols_set)

                self.logger.info(
                    f"🔧 [主动拉取] 计算缺失品种: 参考={len(reference_symbols_set)}, "
                    f"本地={len(local_symbols_set)}, 缺失={missing_count_calculated}"
                )

                # 🔧 关键修复：立即设置 _missing_count
                self._missing_count = missing_count_calculated
                self.logger.info(f"🔧 [主动拉取] 已设置 _missing_count={missing_count_calculated}")

            # 计算总品种数
            total_count = 0
            use_pulled_data = False

            if self._symbol_cache_count > 0:
                # 优先使用事件推送的值（如果已到达）
                total_count = self._symbol_cache_count
                use_pulled_data = True
                self.logger.info(f"🔄 [主动拉取] 使用事件推送值: 总品种={total_count}")
            elif reference_count > 0:
                # 使用缓存文件的值
                total_count = reference_count + len(invalid_symbols)
                use_pulled_data = True
                self.logger.info(f"🔄 [主动拉取] 使用缓存文件: 总品种={total_count}")

            # 4. 更新UI
            if use_pulled_data:
                # 🔧 关键修复：直接更新UI，不通过_update_pulled_data_ui重新计算
                # 因为我们已经在上面计算并设置了 _missing_count
                self._update_pulled_data_ui(
                    symbol_count=total_count,
                    local_count=len(local_symbols),
                    invalid_count=len(invalid_symbols),
                    skip_total=False,
                )
            else:
                # 无法获取总品种数，只更新已下载和失效品种
                self.logger.debug(f"🔄 [主动拉取] 无法获取总品种数，只更新已下载和失效品种")
                self._update_pulled_data_ui(
                    symbol_count=0,
                    local_count=len(local_symbols),
                    invalid_count=len(invalid_symbols),
                    skip_total=True,
                )

            # 🔧 关键修复：无论如何都要强制触发按钮状态更新
            self.logger.info(
                f"🔧 [主动拉取] 最终状态: _missing_count={self._missing_count}, "
                f"即将强制更新按钮状态"
            )
            self._update_repair_button_state()

        except Exception as e:
            self.logger.error(f"❌ [主动拉取] 备用方案拉取失败: {e}", exc_info=True)

    def _pull_startup_data_supplement(self):
        """事件到达后的补充拉取（只拉取本地和失效品种）"""
        self._pull_supplement_data_only()

    def _update_pulled_data_ui(
        self, symbol_count: int, local_count: int, invalid_count: int, skip_total: bool = False
    ):
        """更新主动拉取的数据到UI

        Args:
            symbol_count: 总品种数（参考品种+失效品种）
            local_count: 已下载品种数
            invalid_count: 失效品种数
            skip_total: 是否跳过总品种的更新（当无可用数据源时）
        """
        try:
            if skip_total:
                self.logger.info(
                    f"📋 [主动拉取] 更新UI（跳过总品种）: "
                    f"已下载={local_count}, 失效={invalid_count}"
                )
            else:
                self.logger.info(
                    f"📋 [主动拉取] 更新UI: 总品种={symbol_count}, "
                    f"已下载={local_count}, 失效={invalid_count}"
                )

            # 更新状态变量
            self._downloaded_count = local_count
            self._invalid_symbols_count = invalid_count

            # 🔧 关键修复：保存当前的 _missing_count，避免被错误覆盖
            previous_missing_count = self._missing_count

            if not skip_total:
                # 只有在不跳过时才更新总品种和缺失数
                self._symbol_cache_count = symbol_count
                # 计算品种缺失数：总品种 - 失效 - 已下载
                reference_count = symbol_count - invalid_count
                missing_count = max(0, reference_count - local_count)
                self._missing_count = missing_count
                self.logger.info(
                    f"🔧 [主动拉取] 更新缺失数: {missing_count} (之前={previous_missing_count})"
                )
            else:
                # 🔧 关键修复：skip_total=True 时，不更新 _missing_count
                # 保持事件推送的值，避免覆盖正确的缺失数
                self.logger.info(
                    f"🔧 [主动拉取] 跳过总品种更新，保持 _missing_count={previous_missing_count} "
                    f"(不覆盖事件推送的值)"
                )
                # 使用当前的 _missing_count 更新标签（不重新计算）
                missing_count = previous_missing_count

            # 更新总品种标签（如果 skip_total=False 且有值）
            if not skip_total and symbol_count > 0:
                if self.total_symbols_label:
                    self.total_symbols_label.setText(f"总品种: {symbol_count}")
                    self.total_symbols_label.setStyleSheet("color: #2196F3; font-weight: bold;")

            # 更新品种缺失标签（使用当前的 _missing_count）
            if self.missing_symbols_label:
                current_missing = self._missing_count
                self.missing_symbols_label.setText(f"品种缺失: {current_missing}")
                if current_missing > 0:
                    self.missing_symbols_label.setStyleSheet("color: #FF9800;")
                else:
                    self.missing_symbols_label.setStyleSheet("color: #4CAF50;")

            # 总是更新已下载和失效品种
            if self.downloaded_symbols_label:
                self.downloaded_symbols_label.setText(f"已下载: {local_count}")
                self.downloaded_symbols_label.setStyleSheet("color: #2196F3; font-weight: bold;")

            if self.invalid_symbols_label:
                self.invalid_symbols_label.setText(f"失效品种: {invalid_count}")
                if invalid_count > 0:
                    self.invalid_symbols_label.setStyleSheet("color: #FF5722;")
                else:
                    self.invalid_symbols_label.setStyleSheet("color: #4CAF50;")

            # 🔧 关键修复：更新所有按钮状态
            self._update_delete_invalid_button_state()
            self._update_repair_button_state()  # 🔧 关键修复：确保修复按钮状态也被更新
            # 🔧 关键修复：更新按钮状态前记录当前缺失数
            self.logger.info(
                f"🔧 [主动拉取] 更新按钮状态前: _missing_count={self._missing_count}, "
                f"_outdated_count={self._outdated_count}, _error_count={self._error_count}, "
                f"_data_missing_count={self._data_missing_count}, _warning_count={self._warning_count}"
            )
            self._update_repair_button_state()

            # 🆕 标记启动流程已完成，并更新扫描按钮
            self._lightweight_running = False
            self._update_scan_button_state()
            self.logger.info("🔵 [主动拉取] 启动流程标记为完成，扫描按钮已更新")

            # 🆕 主动触发本地数据联想加载
            self.logger.info("🔄 [主动拉取] 触发本地数据联想加载...")
            self._load_local_data_index_for_autocomplete()

            self.logger.info("✅ [主动拉取] UI更新完成")

        except Exception as e:
            self.logger.error(f"❌ [主动拉取] 更新UI失败: {e}", exc_info=True)

    def _register_event_handlers(self):
        """注册vnpy事件监听器"""
        try:
            self.event_engine = get_event_engine()

            # 🔍 诊断日志
            self.logger.info(f"[事件注册] 步骤1: 获取event_engine实例: {self.event_engine}")

            if self.event_engine:
                self.logger.info("[事件注册] 步骤2: event_engine可用，开始注册事件...")

                # 注册下载事件监听器
                self.event_engine.register(EVENT_CHINASTOCK_DOWNLOAD, self._on_download_event)
                # 注册数据质量事件监听器
                self.event_engine.register(EVENT_DATA_QUALITY_UPDATE, self._on_data_quality_update)
                self.event_engine.register(EVENT_DATA_SCAN_COMPLETE, self._on_data_scan_complete)
                # 🆕 注册本地数据索引就绪事件监听器
                self.event_engine.register("eLocalDataIndexReady", self._on_local_data_index_ready)
                # 🆕 注册数据质量阶段性推送事件监听器
                self.event_engine.register("eQualityScanPhase", self._on_quality_scan_phase)
                # 🔧 输出日志
                self.logger.info("[事件注册] 步骤3: 已注册 eQualityScanPhase")

                # 🔧 关键修复：在步骤4之前添加明确的日志分隔符
                self.logger.info("[事件注册] ===== 开始注册步骤4: eDataMetricsUpdated =====")

                # 🆕 注册新增事件监听器
                # 🔧 关键修复：直接使用硬编码字符串，最简化注册流程
                event_name = "eDataMetricsUpdated"

                self.logger.info(f"[事件注册] 步骤4-开始: event_name='{event_name}'")

                # 🔧 关键修复：直接注册，添加详细错误捕获
                # 直接注册事件处理器
                self.logger.debug(
                    f"[事件注册] 步骤4-准备注册: event_name={event_name}, handler={self._on_data_metrics_updated}"
                )
                try:
                    self.event_engine.register(event_name, self._on_data_metrics_updated)
                    self.logger.info(
                        f"[事件注册] 步骤4: ✅ 已注册 {event_name} -> _on_data_metrics_updated"
                    )
                except Exception as reg_exc:
                    self.logger.error(f"[事件注册] ❌ register()调用失败: {reg_exc}", exc_info=True, extra={"log_type": "SYSTEM"})
                    raise  # 重新抛出，让外层捕获

                # 立即验证事件注册是否成功
                self.logger.debug(f"[事件注册] 步骤4-准备验证: 检查_handlers属性")
                try:
                    if hasattr(self.event_engine, "_handlers"):
                        handlers = self.event_engine._handlers.get(event_name, [])
                        self.logger.debug(f"[事件注册] 步骤4-验证结果: 处理器数量={len(handlers)}")
                        if len(handlers) == 0:
                            self.logger.error(
                                f"[事件注册] ❌ 警告: {event_name} 注册后处理器数量为0！",
                                extra={"log_type": "SYSTEM"}
                            )
                        else:
                            self.logger.info(
                                f"[事件注册] ✅ 验证通过: {event_name} 已注册 {len(handlers)} 个处理器"
                            )
                    else:
                        self.logger.warning(
                            f"[事件注册] ⚠️ event_engine 没有 _handlers 属性，无法验证注册状态",
                            extra={"log_type": "SYSTEM"}
                        )
                except Exception as verify_exc:
                    self.logger.error(f"[事件注册] ❌ 验证过程失败: {verify_exc}", exc_info=True, extra={"log_type": "SYSTEM"})
                    raise  # 重新抛出，让外层捕获
                self.event_engine.register(
                    "eInvalidSymbolsUpdated", self._on_invalid_symbols_updated
                )
                self.logger.info(
                    f"[事件注册] 步骤5: 已注册 eInvalidSymbolsUpdated -> {self._on_invalid_symbols_updated}"
                )
                self.event_engine.register("eFileWatcherStarted", self._on_file_watcher_started)
                self.event_engine.register("eDataScanFinished", self._on_data_scan_finished)
                # 🆕 注册启动流程相关事件监听器
                self.event_engine.register(EVENT_SYMBOL_CACHE_LOADED, self._on_symbol_cache_loaded)
                self.logger.info(
                    f"[事件注册] 步骤6: 已注册 {EVENT_SYMBOL_CACHE_LOADED} -> {self._on_symbol_cache_loaded}"
                )
                self.event_engine.register(
                    EVENT_VALIDATION_COMPLETED, self._on_validation_completed
                )
                self.logger.info(f"[事件注册] 步骤7: 已注册 {EVENT_VALIDATION_COMPLETED}")
                # 注册服务器池状态事件监听器
                self.event_engine.register(
                    "EVENT_SERVER_POOL_STATUS", self._on_server_status_update
                )
                # 注册tick事件监听器（用于实时监控显示）
                self.event_engine.register(EVENT_TICK, self._on_tick_event)

                self.logger.info(
                    "[事件注册] 步骤8: ✅ 完成注册所有事件监听器（下载+数据质量+本地索引+阶段推送+服务器状态+TICK）"
                )

                # 🆕 主动查询一次服务器状态（Pull模式）
                # 解决启动时已完成测速但前端还未创建的问题
                self._fetch_initial_server_status()
            else:
                self.logger.warning("[事件注册] ⚠️ event_engine为None，事件推送功能不可用")
                self.logger.info("[事件注册] 将使用备用的轮询机制")

        except Exception as e:
            self.logger.error(f"[事件注册] ❌ 注册事件监听器失败: {e}", exc_info=True)
            import traceback

            self.logger.error(f"[事件注册] 完整异常堆栈:\n{traceback.format_exc()}")

    def _unregister_event_handlers(self):
        """注销vnpy事件监听器"""
        try:
            if self.event_engine:
                self.event_engine.unregister(EVENT_CHINASTOCK_DOWNLOAD, self._on_download_event)
                self.event_engine.unregister(
                    EVENT_DATA_QUALITY_UPDATE, self._on_data_quality_update
                )
                self.event_engine.unregister(EVENT_DATA_SCAN_COMPLETE, self._on_data_scan_complete)
                self.event_engine.unregister(
                    "eLocalDataIndexReady", self._on_local_data_index_ready
                )
                self.event_engine.unregister("eQualityScanPhase", self._on_quality_scan_phase)
                self.event_engine.unregister(
                    "EVENT_SERVER_POOL_STATUS", self._on_server_status_update
                )
                self.event_engine.unregister(EVENT_TICK, self._on_tick_event)
                self.logger.info("✅ vnpy事件监听器已注销")
        except Exception as e:
            self.logger.error("注销事件监听器失败: %s", e)

    def _on_server_status_update(self, event):
        """处理服务器状态更新事件

        ⚠️ 关键：vnpy事件引擎可能在非Qt主线程中调用此方法
        所有Qt UI操作必须通过QTimer.singleShot转发到主线程

        # 优化原因：修复setText()和setStyleSheet()的线程安全问题
        # 问题：后台服务器测速完成后，通过vnpy事件通知UI更新状态标签
        # 解决：将所有QLabel的setText/setStyleSheet操作转发到主线程
        """
        try:
            data = event.data
            available = data.get("available", 0)
            total = data.get("total", 0)
            status = data.get("status", "unknown")

            self.logger.debug(f"服务器状态已更新: 可用服务器: {available}/{total}")

            # 转发到主线程执行UI更新
            # 优化原因：避免跨线程调用QLabel.setText()和setStyleSheet()
            from functools import partial

            QTimer.singleShot(0, partial(self._update_server_status_ui, available, total, status))

        except Exception as e:
            self.logger.error("处理服务器状态事件失败: %s", e, exc_info=True)

    def _update_server_status_ui(self, available, total, status):
        """更新服务器状态UI（在主线程中执行）"""
        try:
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
        except Exception as e:
            self.logger.error("更新服务器状态UI失败: %s", e, exc_info=True)

    def _fetch_initial_server_status(self):
        """获取初始服务器状态（主动Pull模式）

        解决启动时服务器池已完成测速但前端还未创建的时序问题。
        采用Pull-Push混合模式：启动时主动查询，后续依赖事件推送。
        """
        try:
            if not self.data_center_service:
                self.logger.warning("数据中心服务未初始化，跳过初始服务器状态查询", extra={"log_type": "SYSTEM"})
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

        ⚠️ 关键：vnpy事件引擎可能在非Qt主线程中调用此方法
        所有Qt UI操作必须通过QTimer.singleShot转发到主线程

        # 优化原因：修复Qt线程安全问题
        # 问题：vnpy事件引擎在后台线程中调用此方法，如果直接执行UI操作（如setText, setValue等），
        #       会导致"QObject: Cannot create children for a parent that is in a different thread"警告
        # 解决：使用QTimer.singleShot(0, ...)将UI操作转发到Qt主线程的事件循环中执行
        # 效果：消除线程安全警告，确保UI更新稳定可靠
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

                # 转发到主线程执行UI更新
                # 优化原因：避免在vnpy后台线程中直接调用self.download_progress.setValue()等UI操作
                QTimer.singleShot(
                    0,
                    lambda: self._update_progress_ui(progress_pct, completed, total, current_item),
                )

            elif status == "success":
                # 下载成功完成
                count = event_data.get("count", 0)
                self.logger.info("✅ 下载完成事件：%d 个数据集", count)

                # 转发到主线程执行UI更新
                # 优化原因：show_info()内部会发射Qt信号，必须在主线程执行
                from functools import partial

                QTimer.singleShot(0, partial(self._handle_download_complete, count))

            elif status == "error":
                # 下载失败
                error_msg = event_data.get("error", "未知错误")
                self.logger.error("❌ 下载失败事件：%s", error_msg)

                # 转发到主线程执行UI更新
                # 优化原因：show_error()会创建QMessageBox等UI对象，必须在主线程执行
                from functools import partial

                QTimer.singleShot(0, partial(self._handle_download_error, error_msg))

            elif status == "stopped":
                # 下载被停止
                count = event_data.get("count", 0)
                self.logger.info("⛔ 下载停止事件：已完成 %d 个", count)

                # 转发到主线程执行UI更新
                # 优化原因：避免跨线程访问QWidget（标签、进度条等）
                QTimer.singleShot(0, lambda: self._handle_download_stopped(count))

        except Exception as e:
            self.logger.error("处理下载事件失败: %s", e, exc_info=True)

    def _update_progress_ui(self, progress_pct, completed, total, current_item):
        """更新进度UI（在主线程中执行）

        # 优化原因：UI更新方法独立出来，确保在主线程执行
        # 将事件处理逻辑（数据提取）与UI操作（Widget更新）分离
        # 优点：1) 线程安全 2) 代码结构清晰 3) 方便测试和维护
        """
        try:
            # 1. 更新进度条
            if self.download_progress:
                self.download_progress.setMaximum(total)
                self.download_progress.setValue(completed)

            # 2. 更新状态标签
            if self.progress_label:
                self.progress_label.setText(f"📥 下载中: {completed}/{total} ({progress_pct:.1f}%)")

            # 3. 文本日志（降低频率，仅关键节点）
            should_log = (
                completed == 1  # 第一个
                or completed == total  # 最后一个
                or completed % 500 == 0  # 每500个输出一次
            )

            if should_log and self.progress_text:
                log_text = f"[{completed}/{total}] {progress_pct:.1f}% - {current_item}"
                self._append_progress_text(log_text)

        except Exception as e:
            self.logger.error("更新进度UI失败: %s", e, exc_info=True)

    def _handle_download_complete(self, count):
        """处理下载完成（在主线程中执行）"""
        try:
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

        except Exception as e:
            self.logger.error("处理下载完成失败: %s", e, exc_info=True)

    def _handle_download_error(self, error_msg):
        """处理下载错误（在主线程中执行）"""
        try:
            if self.progress_label:
                self.progress_label.setText("❌ 下载失败")

            # 输出失败摘要
            self._append_progress_text("")
            self._append_progress_text("=" * 50)
            self._append_progress_text(f"❌ 下载失败: {error_msg}")
            self._append_progress_text("=" * 50)

            self._reset_download_state()
            self.show_error(f"下载失败: {error_msg}")

        except Exception as e:
            self.logger.error("处理下载错误失败: %s", e, exc_info=True)

    def _handle_download_stopped(self, count):
        """处理下载停止（在主线程中执行）"""
        try:
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
            self.logger.error("处理下载停止失败: %s", e, exc_info=True)

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
                self._progress_update_timer.start(1000)  # 从200ms改为1秒
            elif not self._progress_update_timer.isActive():
                self._progress_update_timer.start(1000)  # 从200ms改为1秒

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
                    # TDX数据源和虚拟数据源
                    source_list = [
                        {
                            "id": "polling_gateway",
                            "name": "TDX数据源（请求/推送双模式）",
                            "type": "本地",
                        },
                        {"id": "virtual_gateway", "name": "虚拟数据源（回测模拟）", "type": "本地"},
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

            # 更新配置状态显示
            self._update_config_status()

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
                # TDX数据源配置对话框
                dialog = QDialog(self)
                dialog.setWindowTitle("配置TDX数据源（请求/推送双模式）")
                dialog.setMinimumWidth(500)

                layout = QFormLayout(dialog)

                # 说明文字
                info_label = QLabel(
                    "<b>通道激活配置</b><br>"
                    "启动后，TDX数据源将建立服务器连接池并进入就绪状态。<br>"
                    "具体订阅品种由各模块（行情看板、策略中心等）自动注册。"
                )
                info_label.setWordWrap(True)
                info_label.setStyleSheet(
                    "color: #666; padding: 10px; background: #f5f5f5; border-radius: 4px;"
                )
                layout.addRow(info_label)

                # 轮询间隔
                interval_spin = QSpinBox()
                interval_spin.setRange(1, 600)
                interval_spin.setValue(3)  # 改为3秒（实时行情推荐值）
                interval_spin.setSuffix(" 秒")
                layout.addRow("轮询间隔:", interval_spin)

                # 最大服务器数
                max_servers_spin = QSpinBox()
                max_servers_spin.setRange(1, 10)
                max_servers_spin.setValue(5)
                max_servers_spin.setSuffix(" 个")
                layout.addRow("最大服务器数:", max_servers_spin)

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
                        "polling_interval": interval_spin.value(),
                        "max_servers": max_servers_spin.value(),
                        # 不再包含 symbols 字段 - 由自动注册机制处理
                    }
                    self.show_info("TDX数据源配置已保存")

            elif gateway_id == "virtual_gateway":
                # 虚拟数据源配置对话框
                dialog = QDialog(self)
                dialog.setWindowTitle("配置虚拟数据源（回测模拟）")
                dialog.setMinimumWidth(500)

                layout = QFormLayout(dialog)

                # 说明文字
                info_label = QLabel(
                    "<b>回放通道配置</b><br>"
                    "启动后，虚拟数据源将从本地数据库加载历史数据并模拟推送。<br>"
                    "具体订阅品种由各模块（策略回测、回放分析等）自动注册。"
                )
                info_label.setWordWrap(True)
                info_label.setStyleSheet(
                    "color: #666; padding: 10px; background: #f5f5f5; border-radius: 4px;"
                )
                layout.addRow(info_label)

                # 起始时间
                datetime_edit = QDateTimeEdit()
                datetime_edit.setCalendarPopup(True)
                datetime_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
                datetime_edit.setDateTime(QDateTime.currentDateTime().addMonths(-1))
                layout.addRow("起始时间:", datetime_edit)

                # 推送速度
                speed_spin = QDoubleSpinBox()
                speed_spin.setRange(0.1, 1000.0)  # 支持0.1x ~ 1000x
                speed_spin.setValue(1.0)
                speed_spin.setSingleStep(0.1)
                speed_spin.setSuffix(" 倍")
                layout.addRow("推送速度:", speed_spin)

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
                        # 不再包含 symbols 字段 - 由自动注册机制处理
                    }
                    self.show_info("虚拟数据源配置已保存")

        except Exception as e:
            self.logger.error("配置网关失败: %s", e)
            self.show_error(f"配置失败: {e}")

    def _start_gateway(self, gateway_id: str):
        """启动网关（激活通道）."""
        try:
            if not self.data_center_service:
                self.show_error("数据中心服务不可用")
                return

            if gateway_id == "polling_gateway":
                # 检查是否已配置
                config = getattr(self, "polling_gateway_config", None)
                if not config:
                    # 使用默认配置启动
                    config = {
                        "polling_interval": 3.0,
                        "max_servers": 5,
                    }
                    self.show_info("使用默认配置启动TDX数据源")

                # 启动网关（激活通道，不主动订阅品种）
                result = self.data_center_service.start_polling_gateway(config)

                if result["success"]:
                    self.show_info("TDX数据源已启动（通道已激活）\n" "订阅品种将由其他模块自动注册")
                    self._load_data_sources()
                else:
                    self.show_error(f"启动失败: {result.get('message', '未知错误')}")

            elif gateway_id == "virtual_gateway":
                # 检查是否已配置
                config = getattr(self, "virtual_gateway_config", None)
                if not config:
                    self.show_warning("请先配置虚拟数据源（需要设置起始时间和速度）")
                    return

                # 启动网关（激活通道，不主动订阅品种）
                result = self.data_center_service.start_virtual_gateway(config)

                if result["success"]:
                    self.show_info(
                        "虚拟数据源已启动（通道已激活）\n" "订阅品种将由其他模块自动注册"
                    )
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

    def _update_config_status(self):
        """更新配置状态显示"""
        try:
            if not self.data_center_service or not self.config_status_label:
                return

            result = self.data_center_service.get_all_datafeed_status()
            if not result["success"]:
                return

            active_datafeed = result.get("active_datafeed")
            datafeeds = result.get("datafeeds", {})

            # 只显示当前激活的数据源，字体加大、更显眼
            if active_datafeed == "polling_gateway":
                tdx_status = datafeeds.get("polling_gateway", {})
                tdx_pushing = tdx_status.get("pushing_data", False)
                if tdx_pushing:
                    status_html = (
                        "<p style='margin:10px; padding:15px; font-size:16px;'>"
                        "✅ <b style='color:#4CAF50; font-size:18px;'>TDX数据源</b> - "
                        "<span style='color:#4CAF50; font-size:16px;'>已激活，正在推送</span>"
                        "</p>"
                    )
                else:
                    status_html = (
                        "<p style='margin:10px; padding:15px; font-size:16px;'>"
                        "🔵 <b style='color:#2196F3; font-size:18px;'>TDX数据源</b> - "
                        "<span style='color:#2196F3; font-size:16px;'>已连接</span>"
                        "</p>"
                    )
            elif active_datafeed == "virtual_gateway":
                virtual_status = datafeeds.get("virtual_gateway", {})
                virtual_pushing = virtual_status.get("pushing_data", False)
                if virtual_pushing:
                    status_html = (
                        "<p style='margin:10px; padding:15px; font-size:16px;'>"
                        "✅ <b style='color:#4CAF50; font-size:18px;'>虚拟数据源</b> - "
                        "<span style='color:#4CAF50; font-size:16px;'>已激活，正在回放</span>"
                        "</p>"
                    )
                else:
                    status_html = (
                        "<p style='margin:10px; padding:15px; font-size:16px;'>"
                        "🔵 <b style='color:#2196F3; font-size:18px;'>虚拟数据源</b> - "
                        "<span style='color:#2196F3; font-size:16px;'>已连接</span>"
                        "</p>"
                    )
            else:
                # 没有激活的数据源
                status_html = (
                    "<p style='margin:10px; padding:15px; font-size:16px;'>"
                    "<span style='color:#999; font-size:16px;'>未激活任何数据源</span>"
                    "</p>"
                )

            self.config_status_label.setText(status_html)

        except Exception as e:
            self.logger.error("更新配置状态失败: %s", e)

    def _on_tick_event(self, event):
        """处理tick事件

        ⚠️ 关键：vnpy事件引擎可能在非Qt主线程中调用此方法
        所有Qt UI操作必须通过QTimer.singleShot转发到主线程
        """
        try:
            if self.monitor_paused or not self.monitor_text:
                return

            tick = event.data
            from datetime import datetime

            # 计算涨跌幅（需要有pre_close）
            change_pct = 0.0
            if hasattr(tick, "pre_close") and tick.pre_close > 0:
                change_pct = (tick.last_price - tick.pre_close) / tick.pre_close * 100

            # 格式化tick信息
            time_str = datetime.now().strftime("%H:%M:%S")
            color = "red" if change_pct > 0 else "green" if change_pct < 0 else "gray"
            arrow = "↑" if change_pct > 0 else "↓" if change_pct < 0 else "-"

            tick_info = {
                "time": time_str,
                "symbol": tick.symbol,
                "price": tick.last_price,
                "change": change_pct,
                "volume": tick.volume / 10000 if tick.volume else 0,  # 转换为万手
                "color": color,
                "arrow": arrow,
            }

            # 转发到主线程执行UI更新
            QTimer.singleShot(0, lambda: self._handle_tick_ui(tick_info))

        except Exception as e:
            self.logger.error("处理tick事件失败: %s", e)

    def _handle_tick_ui(self, tick_info):
        """处理tick UI更新（在主线程中执行）"""
        try:
            self.tick_buffer.append(tick_info)

            # 更新显示（使用定时器批量更新，避免过于频繁）
            if not hasattr(self, "_monitor_update_timer"):
                self._monitor_update_timer = QTimer()
                self._monitor_update_timer.timeout.connect(self._update_monitor_display)
                self._monitor_update_timer.start(2000)  # 每2秒更新一次 (降低频率)
        except Exception as e:
            self.logger.error("处理tick UI失败: %s", e)

    def _update_monitor_display(self):
        """更新实时监控显示"""
        try:
            if not self.monitor_text or not self.tick_buffer:
                return

            # 构建HTML显示文本
            html = (
                "<pre style='font-family: Consolas, monospace; font-size: 12px; line-height: 1.5;'>"
            )

            for tick_info in self.tick_buffer:
                html += (
                    f"<span style='color:#666;'>[{tick_info['time']}]</span> "
                    f"<b>{tick_info['symbol']}</b>: "
                    f"¥{tick_info['price']:.2f} "
                    f"<span style='color:{tick_info['color']};'>"
                    f"{tick_info['arrow']}{abs(tick_info['change']):.2f}%</span> "
                    f"Vol:{tick_info['volume']:.1f}万\n"
                )

            html += "</pre>"
            self.monitor_text.setHtml(html)

            # 自动滚动到底部
            self.monitor_text.verticalScrollBar().setValue(
                self.monitor_text.verticalScrollBar().maximum()
            )

        except Exception as e:
            self.logger.error("更新监控显示失败: %s", e)

    def _toggle_monitor_pause(self):
        """暂停/继续监控"""
        self.monitor_paused = not self.monitor_paused
        if self.monitor_pause_btn:
            self.monitor_pause_btn.setText("继续" if self.monitor_paused else "暂停")

    def _clear_monitor(self):
        """清空监控"""
        self.tick_buffer.clear()
        if self.monitor_text:
            self.monitor_text.clear()

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
        """设置质量扫描状态指示器（Qt Slot，自动在主线程执行）

        Args:
            scanning: True=正在扫描，False=扫描完成
        """
        self.logger.info(
            "🔧 [Slot] _set_quality_scan_status 被调用: scanning=%s（主线程）", scanning
        )

        # 🔧 已移除quality_scan_status_label，此方法保留但不再执行操作
        # 如果需要状态指示，可以使用其他UI元素
        self.logger.debug(f"数据扫描状态变化: scanning={scanning}")

    def _update_scan_button_state(self):
        """更新数据扫描按钮状态

        启用条件：启动流程未运行 AND 扫描流程未运行
        """
        try:
            if not self.scan_data_btn:
                return

            # 只有两个流程都不在运行时才启用
            should_enable = not self._lightweight_running and not self._heavy_scan_running

            self.scan_data_btn.setEnabled(should_enable)

            if should_enable:
                self.scan_data_btn.setStyleSheet("background-color: #2196F3; color: white;")
                self.logger.debug("🔵 数据扫描按钮已启用")
            else:
                self.scan_data_btn.setStyleSheet("")
                self.logger.debug("⚪ 数据扫描按钮已禁用")

        except Exception as e:
            self.logger.error(f"更新数据扫描按钮状态失败: {e}", exc_info=True)

    def _update_delete_invalid_button_state(self):
        """更新删除失效数据按钮状态（兼容方法）

        🔧 重构：更新新的删除失效品种按钮
        此方法保留用于向后兼容，内部调用新的UI更新方法
        """
        try:
            # 🔧 更新新的删除失效品种按钮
            if self.delete_invalid_symbols_btn:
                should_enable = self._invalid_symbols_count > 0
                self.delete_invalid_symbols_btn.setEnabled(should_enable)

            # 🔧 兼容旧代码：如果旧按钮存在，也更新它
            if self.delete_invalid_btn:
                self.delete_invalid_btn.setEnabled(self._invalid_symbols_count > 0)

        except Exception as e:
            self.logger.error(f"更新删除失效数据按钮状态失败: {e}", exc_info=True)

    def _update_repair_button_state(self):
        """更新修复按钮状态（兼容方法）

        🔧 重构：更新新的两个修复按钮（品种问题修复和数据问题修复）
        此方法保留用于向后兼容，内部调用新的UI更新方法
        """
        try:
            # 🔧 更新品种问题修复按钮
            if self.repair_symbol_issues_btn:
                should_enable = (self._missing_count > 0) or (self._outdated_count > 0)
                self.repair_symbol_issues_btn.setEnabled(should_enable)

            # 🔧 更新数据问题修复按钮
            if self.repair_data_issues_btn:
                should_enable = (
                    (self._error_count > 0)
                    or (self._data_missing_count > 0)
                    or (self._warning_count > 0)
                )
                self.repair_data_issues_btn.setEnabled(should_enable)

            # 🔧 兼容旧代码：如果旧按钮存在，也更新它
            if self.repair_download_btn:
                total_problems = (
                    self._missing_count
                    + self._invalid_symbols_count
                    + self._outdated_count
                    + self._error_count
                    + self._data_missing_count
                    + self._warning_count
                )
                self.repair_download_btn.setEnabled(total_problems > 0)

        except Exception as e:
            self.logger.error(f"更新修复按钮状态失败: {e}", exc_info=True)

    def _trigger_data_scan(self) -> None:
        """触发数据扫描（完整3阶段扫描）

        🔧 关键修复：在后台线程执行，避免阻塞UI主线程导致崩溃
        """
        try:
            if not self.data_center_service:
                self.show_error("数据中心服务未初始化")
                return

            self.logger.info(
                "🔍 触发数据扫描（后台线程）...",
                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
            )

            # 禁用扫描按钮，防止重复触发
            if self.scan_data_btn:
                self.scan_data_btn.setEnabled(False)
                self.scan_data_btn.setText("扫描中...")

            # 🔧 在后台线程执行扫描，避免阻塞UI
            from threading import Thread

            def run_scan():
                """后台线程执行扫描"""
                try:
                    # 使用ai_log_process包裹手动数据扫描流程
                    try:
                        from backend.infrastructure.system_vnpy.unified_log_system import (
                            ai_log_process,
                        )
                    except ImportError:
                        ai_log_process = None

                    import time
                    start_time = time.time()
                    
                    if ai_log_process:
                        stage_logger = logging.getLogger("task.manual_data_scan")
                        with ai_log_process("manual_data_scan", {
                            "scan_type": "errors_missing_only",
                            "trigger": "user_manual",
                        }):
                            # 阶段节点日志（输出到Terminal）
                            stage_logger.info(
                                "📍 手动数据扫描开始",
                                extra={"log_type": "STAGE_NODE", "scenario": "manual_data_scan"},
                            )
                            
                            # 详细日志（只写入AI日志文件）
                            self.logger.debug(
                                "[DATA-SCAN] 开始执行数据扫描...",
                                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                            )
                            self.logger.debug(
                                f"[DATA-SCAN] 服务实例类型: {type(self.data_center_service).__name__ if self.data_center_service else 'None'}",
                                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                            )
                            self.logger.debug(
                                f"[DATA-SCAN] 服务实例: {self.data_center_service}",
                                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                            )
                            self.logger.info(
                                "[DATA-SCAN] 手动数据扫描任务开始",
                                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                            )
                            
                            if not self.data_center_service:
                                self.logger.error(
                                    "[DATA-SCAN] ❌ 数据中心服务未初始化",
                                    exc_info=True,
                                    extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
                                )
                                stage_logger.error(
                                    "❌ 数据中心服务未初始化",
                                    extra={"log_type": "STAGE_NODE", "scenario": "manual_data_scan"},
                                )
                                return
                            
                            self.logger.debug(
                                "[DATA-SCAN] 调用服务层scan_errors_missing_only方法...",
                                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                            )
                            scan_start_time = time.time()
                            result = self.data_center_service.scan_errors_missing_only()
                            scan_elapsed = time.time() - scan_start_time
                            elapsed = time.time() - start_time
                            self.logger.debug(
                                f"[DATA-SCAN] 服务层scan_errors_missing_only方法调用完成: 耗时={scan_elapsed:.2f}s",
                                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                            )

                            # 使用QTimer转发结果到主线程更新UI
                            if result.get("success"):
                                missing = result.get('missing_symbols', 0)
                                error = result.get('error_symbols', 0)
                                warning = result.get('warning_symbols', 0)
                                
                                self.logger.debug(
                                    f"[DATA-SCAN] 扫描结果详情: missing={missing}, error={error}, warning={warning}",
                                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                                )
                                self.logger.info(
                                    f"[DATA-SCAN] ✅ 数据扫描完成: 缺失={missing}, 错误={error}, 警告={warning}, "
                                    f"服务层耗时={scan_elapsed:.2f}s, 总耗时={elapsed:.2f}s",
                                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                                )
                                
                                # 阶段节点日志（输出到Terminal）
                                stage_logger.info(
                                    f"✅ 手动数据扫描完成: 缺失={missing}, 错误={error}, 警告={warning}, 耗时={elapsed:.2f}s",
                                    extra={"log_type": "STAGE_NODE", "scenario": "manual_data_scan"},
                                )
                                
                                QTimer.singleShot(
                                    0,
                                    lambda: self.show_info(
                                        f"扫描完成: 缺失={missing}, "
                                        f"错误={error}, "
                                        f"警告={warning}"
                                    ),
                                )
                            else:
                                msg = result.get('message', '未知错误')
                                elapsed = time.time() - start_time
                                self.logger.warning(
                                    f"[DATA-SCAN] ⚠️ 数据扫描失败: {msg}, 耗时={elapsed:.2f}s",
                                    extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
                                )
                                self.logger.debug(
                                    f"[DATA-SCAN] 失败结果详情: {result}",
                                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                                )
                                
                                # 阶段节点日志（输出到Terminal）
                                stage_logger.warning(
                                    f"⚠️ 手动数据扫描失败: {msg}",
                                    extra={"log_type": "STAGE_NODE", "scenario": "manual_data_scan"},
                                )
                                
                                QTimer.singleShot(
                                    0,
                                    lambda: self.show_error(
                                        f"扫描失败: {msg}"
                                    ),
                                )
                    else:
                        # 降级处理：如果ai_log_process不可用，直接执行
                        self.logger.warning(
                            "[DATA-SCAN] ⚠️ 日志系统不可用，使用降级模式",
                            extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
                        )
                        self.logger.info(
                            "[DATA-SCAN] 降级模式：开始执行数据扫描...",
                            extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                        )
                        
                        if not self.data_center_service:
                            self.logger.error(
                                "[DATA-SCAN] ❌ 数据中心服务未初始化（降级模式）",
                                exc_info=True,
                                extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
                            )
                            return
                        
                        scan_start_time = time.time()
                        result = self.data_center_service.scan_errors_missing_only()
                        scan_elapsed = time.time() - scan_start_time
                        elapsed = time.time() - start_time

                        if result.get("success"):
                            missing = result.get('missing_symbols', 0)
                            error = result.get('error_symbols', 0)
                            warning = result.get('warning_symbols', 0)
                            self.logger.info(
                                f"[DATA-SCAN] ✅ 数据扫描完成（降级模式）: 缺失={missing}, 错误={error}, "
                                f"警告={warning}, 服务层耗时={scan_elapsed:.2f}s, 总耗时={elapsed:.2f}s",
                                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                            )
                            QTimer.singleShot(
                                0,
                                lambda: self.show_info(
                                    f"扫描完成: 缺失={missing}, "
                                    f"错误={error}, "
                                    f"警告={warning}"
                                ),
                            )
                        else:
                            msg = result.get('message', '未知错误')
                            self.logger.warning(
                                f"[DATA-SCAN] ⚠️ 数据扫描失败（降级模式）: {msg}, 耗时={elapsed:.2f}s",
                                extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
                            )
                            QTimer.singleShot(
                                0,
                                lambda: self.show_error(
                                    f"扫描失败: {msg}"
                                ),
                            )

                except Exception as e:
                    elapsed = time.time() - start_time
                    self.logger.error(
                        f"[DATA-SCAN] ❌ 数据扫描异常: {e}, 耗时={elapsed:.2f}s",
                        exc_info=True,
                        extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
                    )
                    self.logger.debug(
                        f"[DATA-SCAN] 异常类型: {type(e).__name__}, 异常详情: {str(e)}",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )
                    QTimer.singleShot(0, lambda: self.show_error(f"扫描失败: {str(e)}"))

                finally:
                    # 恢复扫描按钮状态
                    QTimer.singleShot(0, lambda: self._restore_scan_button())

            # 启动后台线程
            scan_thread = Thread(target=run_scan, daemon=True, name="DataScanThread")
            scan_thread.start()

        except Exception as e:
            self.logger.error(
                "❌ 启动数据扫描失败: %s",
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
            )
            self.show_error(f"启动扫描失败: {str(e)}")
            self._restore_scan_button()

    def _restore_scan_button(self):
        """恢复扫描按钮状态"""
        try:
            if self.scan_data_btn:
                self.scan_data_btn.setEnabled(True)
                self.scan_data_btn.setText("🔍 数据扫描")
                self.scan_data_btn.setStyleSheet("background-color: #2196F3; color: white;")
        except Exception as e:
            self.logger.error(f"恢复扫描按钮状态失败: {e}")

    def _trigger_delete_invalid(self) -> None:
        """触发删除失效数据（带确认对话框）"""
        try:
            from PySide6.QtWidgets import QInputDialog

            self.logger.info("🗑️ [删除失效数据] 用户点击删除按钮")

            # 弹出确认对话框
            text, ok = QInputDialog.getText(
                self,
                "确认删除",
                "请输入'删除'以确认删除失效数据:",
            )

            self.logger.info(f"🗑️ [删除失效数据] 对话框结果: ok={ok}, text='{text}'")

            if not ok or text != "删除":
                self.logger.info("🗑️ [删除失效数据] 用户取消删除操作")
                return

            if not self.data_center_service:
                self.logger.error("🗑️ [删除失效数据] 数据中心服务未初始化", exc_info=True, extra={"log_type": "SYSTEM"})
                self.show_error("数据中心服务未初始化")
                return

            self.logger.info("🗑️ [删除失效数据] 开始删除失效数据...")

            # 调用服务方法
            result = self.data_center_service.delete_invalid_symbols()

            self.logger.info(f"🗑️ [删除失效数据] 服务返回结果: {result}")

            if result.get("success"):
                deleted_count = result.get("deleted", 0)
                failed_count = result.get("failed", 0)
                msg = f"删除完成: 成功={deleted_count}, 失败={failed_count}"
                self.logger.info(f"✅ {msg}")
                self.show_info(msg)

                # 🆕 刷新UI显示
                self.logger.info("🔄 [删除失效数据] 刷新UI...")
                QTimer.singleShot(1000, self._pull_startup_data)
            else:
                error_msg = result.get("message", "未知错误")
                self.logger.error(f"❌ [删除失效数据] 删除失败: {error_msg}")
                self.show_error(f"删除失败: {error_msg}")

        except Exception as e:
            self.logger.error("❌ [删除失效数据] 删除失效数据失败: %s", e, exc_info=True, extra={"log_type": "USER_FEEDBACK"})
            self.show_error(f"删除失效数据失败: {str(e)}")

    def _refresh_quality_overview(self) -> None:
        """手动刷新数据质量概览（触发后端重新扫描）"""
        # 重定向到新的扫描方法
        self._trigger_data_scan()

    def _update_quality_overview_ui(self, overview_data: dict) -> None:
        """更新质量概览UI显示（Qt Slot，自动在主线程执行）

        🔧 重构：同时更新新旧UI组件，确保兼容性

        Args:
            overview_data: 质量概览数据
        """
        self.logger.info("🔧 [Slot] _update_quality_overview_ui 被调用（主线程）")
        try:
            # 提取数据
            total = overview_data.get("total_symbols", 0)
            local = overview_data.get("local_symbols", 0)
            missing = overview_data.get("missing_symbols", 0)
            invalid_count = overview_data.get("invalid_symbols", 0)
            data_missing = overview_data.get("data_missing_symbols", 0)
            errors = overview_data.get("error_symbols", 0)
            warnings = overview_data.get("warning_symbols", 0)
            outdated = overview_data.get("outdated_symbols", 0)

            # 🔧 更新新的UI组件（品种问题）
            self._update_symbol_issues_ui(
                total_symbols=total,
                downloaded=local,
                missing=missing,
                invalid_count=invalid_count,
                outdated=outdated,
            )

            # 🔧 更新新的UI组件（数据问题）
            self._update_data_issues_ui(
                error_count=errors, data_missing_count=data_missing, warning_count=warnings
            )

            # 🔧 兼容旧代码：同时更新旧UI（如果存在）
            if self.total_symbols_label:
                self.total_symbols_label.setText(f"总品种: {total}")
                self.total_symbols_label.setStyleSheet("color: #2196F3;")
            if self.downloaded_symbols_label:
                self.downloaded_symbols_label.setText(f"已下载: {local}")
                self.downloaded_symbols_label.setStyleSheet("color: #4CAF50;")
            if self.missing_symbols_label:
                self.missing_symbols_label.setText(f"品种缺失: {missing}")
                if missing > 0:
                    self.missing_symbols_label.setStyleSheet("color: #FF9800; font-weight: bold;")
                else:
                    self.missing_symbols_label.setStyleSheet("color: #4CAF50;")
            if self.invalid_symbols_label:
                self.invalid_symbols_label.setText(f"失效品种: {invalid_count}")
                if invalid_count > 0:
                    self.invalid_symbols_label.setStyleSheet("color: #FF9800; font-weight: bold;")
                else:
                    self.invalid_symbols_label.setStyleSheet("color: #4CAF50;")
            if self.outdated_symbols_label:
                self.outdated_symbols_label.setText(f"过时: {outdated}")
                if outdated > 0:
                    self.outdated_symbols_label.setStyleSheet("color: #FF9800; font-weight: bold;")
                else:
                    self.outdated_symbols_label.setStyleSheet("color: #4CAF50;")
            if self.data_missing_symbols_label:
                self.data_missing_symbols_label.setText(f"数据缺失: {data_missing}")
                if data_missing > 0:
                    self.data_missing_symbols_label.setStyleSheet("color: #FF9800;")
                else:
                    self.data_missing_symbols_label.setStyleSheet("color: #4CAF50;")
            if self.error_symbols_label:
                self.error_symbols_label.setText(f"错误: {errors}")
                if errors > 0:
                    self.error_symbols_label.setStyleSheet("color: #F44336; font-weight: bold;")
                else:
                    self.error_symbols_label.setStyleSheet("color: #4CAF50;")
            if self.warning_symbols_label:
                self.warning_symbols_label.setText(f"警告: {warnings}")
                if warnings > 0:
                    self.warning_symbols_label.setStyleSheet("color: #FF9800; font-weight: bold;")
                else:
                    self.warning_symbols_label.setStyleSheet("color: #4CAF50;")

            # 🔧 关键修复：启用扫描按钮（表示启动流程已完成）
            if self.scan_data_btn:
                self.scan_data_btn.setEnabled(True)
                self.logger.info("✅ 数据扫描按钮已启用")

            self.logger.info("✅ [Slot] 质量概览UI更新成功")

        except Exception as e:
            self.logger.error("❌ [Slot] 更新质量概览UI失败: %s", e, exc_info=True)

    def _toggle_quality_detail(self, checked: bool) -> None:
        """展开/折叠质量详情表格（兼容方法）

        🔧 重构：此方法已废弃，保留用于向后兼容
        新的架构使用 _toggle_symbol_issues_detail 和 _toggle_data_issues_detail
        """
        try:
            # 🔧 兼容旧代码：如果旧表格存在，也更新它
            if self.quality_detail_table:
                self.quality_detail_table.setVisible(checked)

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
            "missing": ("品种缺失", "❌", 1),
            "error": ("数据错误", "🔴", 2),
            "warning": ("数据缺失", "⚠️", 3),  # warning表示有数据但部分日期缺失
            "normal": ("正常", "✅", 4),
        }

        return status_map.get(status, ("未知", "❓", 5))

    def _update_quality_detail_table(self, details: list) -> None:
        """更新质量详情表格（只显示有问题的品种）

        Args:
            details: 详情列表（后端已过滤为有问题的品种并排序）
        """
        try:
            # print(...)  # 🔧 已移除：DEBUG调试输出
            self.logger.debug(
                "details类型=%s, 大小=%s", type(details), len(details) if details else "None"
            )
            if details and len(details) > 0:
                self.logger.debug(
                    "前3个问题品种: %s",
                    [d.get("symbol", "?") + "(" + d.get("status", "?") + ")" for d in details[:3]],
                )

            if not self.quality_detail_table:
                self.logger.warning("quality_detail_table 为 None")
                return

            # 清空表格
            self.quality_detail_table.setRowCount(0)

            # 🆕 检查是否有问题品种
            if not details:
                # 🆕 无问题时显示友好提示
                self.logger.debug("details为空，显示'无问题'提示")
                self.quality_detail_table.insertRow(0)
                no_issue_item = QTableWidgetItem("🎉 所有品种数据质量良好，无需修复")
                no_issue_item.setForeground(Qt.GlobalColor.darkGreen)
                self.quality_detail_table.setItem(0, 0, no_issue_item)
                self.quality_detail_table.setSpan(0, 0, 1, 4)  # 合并单元格
                self.logger.info("质量详情表格：无问题品种")
                return

            self.logger.info("质量详情表格：开始填充，共%d个问题品种", len(details))

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

    def _append_quality_details(self, new_details: list) -> None:
        """增量追加问题品种到详情表格

        🔧 重构：根据status字段路由到对应的详情表格
        - missing、invalid、outdated -> 品种问题详情表格
        - error、data_missing、warning -> 数据问题详情表格

        Args:
            new_details: 新增的问题品种详情列表
        """
        try:
            if not new_details:
                return

            # 🔧 分离品种问题和数据问题
            symbol_issues_details = []
            data_issues_details = []

            for detail in new_details:
                status = detail.get("status", "")
                if status in ["missing", "invalid", "outdated"]:
                    symbol_issues_details.append(detail)
                elif status in ["error", "data_missing", "warning"]:
                    data_issues_details.append(detail)

            # 分别追加到对应的详情表格
            if symbol_issues_details:
                self._append_symbol_issues_details(symbol_issues_details)

            if data_issues_details:
                self._append_data_issues_details(data_issues_details)

            # 🔧 兼容旧代码：如果存在旧的quality_detail_table，也更新它
            if self.quality_detail_table:
                # 增量追加每个问题品种到旧表格（向后兼容）
                for detail in new_details:
                    row = self.quality_detail_table.rowCount()
                    self.quality_detail_table.insertRow(row)

                    # 第1列：品种代码
                    symbol = detail.get("symbol", "")
                    self.quality_detail_table.setItem(row, 0, QTableWidgetItem(symbol))

                    # 第2列：品种名称
                    name = detail.get("name", "")
                    self.quality_detail_table.setItem(row, 1, QTableWidgetItem(name))

                    # 第3列：状态（带图标和颜色）
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
                    elif status == "outdated":
                        status_item.setForeground(Qt.GlobalColor.darkYellow)
                    elif status == "invalid":
                        status_item.setForeground(Qt.GlobalColor.darkRed)
                    else:
                        status_item.setForeground(Qt.GlobalColor.darkGreen)

                    self.quality_detail_table.setItem(row, 2, status_item)

                    # 第4列：问题描述
                    issues_text = detail.get("issues", "无问题")
                    brief_desc = issues_text[:50] + "..." if len(issues_text) > 50 else issues_text
                    desc_item = QTableWidgetItem(brief_desc)
                    desc_item.setToolTip(issues_text)

                    self.quality_detail_table.setItem(row, 3, desc_item)

                # 🆕 强制刷新表格UI显示
                self.quality_detail_table.viewport().update()

                # 🆕 如果表格已展开，滚动到最新行以提供视觉反馈
                if (
                    self.quality_detail_table.isVisible()
                    and self.quality_detail_table.rowCount() > 0
                ):
                    last_row = self.quality_detail_table.rowCount() - 1
                    last_item = self.quality_detail_table.item(last_row, 0)
                    if last_item:
                        from PySide6.QtWidgets import QAbstractItemView

                        self.quality_detail_table.scrollToItem(
                            last_item, QAbstractItemView.ScrollHint.PositionAtBottom
                        )

                # 🔥 强制输出成功信息
                import sys

                final_count = self.quality_detail_table.rowCount()
                self.logger.debug(
                    f"[CRITICAL-DEBUG] _append_quality_details完成: 追加了 {len(new_details)} 条记录, "
                    f"表格当前总行数: {final_count}, 表格是否可见: {self.quality_detail_table.isVisible()}"
                )

                self.logger.info(
                    "增量追加 %d 个问题品种，当前表格行数: %d（已刷新UI）",
                    len(new_details),
                    self.quality_detail_table.rowCount(),
                )

        except Exception as e:
            # 🔥 强制输出异常信息
            self.logger.error(
                f"[CRITICAL-DEBUG] _append_quality_details异常: {e}",
                exc_info=True,
                extra={"log_type": "SYSTEM"}
            )
            import traceback

            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            self.logger.error("❌ 增量追加质量详情失败: %s", e, exc_info=True, extra={"log_type": "USER_FEEDBACK"})

    def _trigger_repair_download(self) -> None:
        """触发修复下载（智能下载有问题的品种）

        🔧 废弃：此方法已废弃，保留用于向后兼容
        新的架构使用 _repair_symbol_issues 和 _repair_data_issues
        """
        try:
            self.logger.info("用户触发数据修复下载")

            # 1. 检查是否有质量概览数据
            if not self.data_center_service or not self.data_center_service.china_stock_engine:
                self.show_warning("数据引擎未就绪，请稍后再试")
                return

            # 2. 获取质量概览
            overview = self.data_center_service.get_data_quality_overview()
            if not overview or not overview.get("success"):
                self.show_warning("无法获取数据质量概览，请先刷新质量概览")
                return

            # 3. 提取问题品种列表（包括：缺失、过时、错误、数据缺失）
            details = overview.get("details", [])

            # 从details中提取所有问题品种（details已包含所有状态的问题品种）
            problem_symbols = []
            if details:
                problem_symbols = [d.get("symbol") for d in details if d.get("symbol")]

            # 如果details为空，检查概览指标
            if not problem_symbols:
                # 检查是否有任何问题
                missing = overview.get("missing_symbols", 0)
                outdated = overview.get("outdated_symbols", 0)
                errors = overview.get("error_symbols", 0)
                data_missing = overview.get("data_missing_symbols", 0)

                if missing == 0 and outdated == 0 and errors == 0 and data_missing == 0:
                    self.show_info("恭喜！所有品种数据质量良好，无需修复")
                    return
                else:
                    # 有问题但details为空，可能是扫描未完成
                    self.show_warning("质量概览数据不完整，请先刷新质量概览")
                    return

            self.logger.info(f"发现 {len(problem_symbols)} 个需要修复的品种")

            # 4. 检查是否有超过100天的问题数据
            from datetime import date, timedelta

            today = date.today()
            limit_date = today - timedelta(days=100)

            # 检查详情中是否有outdated品种，并判断是否超过100天
            has_old_data = False
            for detail in details:
                status = detail.get("status")
                if status == "outdated":
                    # 尝试从detail中获取last_date信息
                    last_date_str = detail.get("last_date")
                    if last_date_str:
                        try:
                            from datetime import datetime

                            last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
                            if last_date < limit_date:
                                has_old_data = True
                                break
                        except Exception:
                            pass

            # 5. 根据检测结果显示不同提示
            if has_old_data:
                msg = (
                    f"检测到 {len(problem_symbols)} 个问题品种需要修复\n\n"
                    f"⚠️ 注意：最多修复100天内的问题数据，超过100天的问题数据无法修复。\n\n"
                    f"下载进度在数据下载界面展示。"
                )
            else:
                msg = (
                    f"检测到 {len(problem_symbols)} 个问题品种需要修复\n\n"
                    f"下载进度在数据下载界面展示。"
                )

            # 6. 记录日志并直接开始修复（不使用模态对话框）
            # 🚀 修复UI卡死：不使用模态对话框询问用户，直接开始修复
            self.logger.info(msg)

            # 7. 设置下载日期范围（最近100天）
            start_date = limit_date
            end_date = today

            # 8. 切换到数据下载tab
            if hasattr(self, "tab_widget") and self.tab_widget:
                # 找到"数据下载"tab的索引
                for i in range(self.tab_widget.count()):
                    if self.tab_widget.tabText(i) == "数据下载":
                        self.tab_widget.setCurrentIndex(i)
                        self.logger.info("已切换到数据下载tab")
                        break

            # 9. 触发下载（调用现有的下载逻辑）
            self._start_download_with_symbols(problem_symbols, start_date, end_date)

            self.logger.info(f"已触发 {len(problem_symbols)} 个品种的修复下载")

        except Exception as e:
            self.logger.error(f"触发修复下载失败: {e}", exc_info=True)
            self.show_error(f"触发修复下载失败: {e}")

    def _on_data_quality_update(self, event: Event) -> None:
        """处理数据质量更新事件（vnpy事件回调）

        ⚠️ 关键：vnpy事件引擎可能在非Qt主线程中调用此方法
        所有Qt UI操作必须通过QTimer.singleShot转发到主线程

        Args:
            event: vnpy事件对象
        """
        try:
            data = event.data

            # 🆕 检查是否是整体概览更新（包含total_symbols字段）
            if "total_symbols" in data:
                # 整体概览更新
                self.logger.info("✅ 收到数据质量整体概览更新事件")

                quality_data = {
                    "success": True,
                    "total_symbols": data.get("total_symbols", 0),
                    "local_symbols": data.get("local_symbols", 0),
                    "missing_symbols": data.get("missing_symbols", 0),
                    "data_missing_symbols": data.get("data_missing_symbols", 0),  # 新增
                    "error_symbols": data.get("error_symbols", 0),
                    "warning_symbols": data.get("warning_symbols", 0),
                    "data_lagging_days": data.get("data_lagging_days", 0),  # 新增
                    "outdated_symbols": data.get("outdated_symbols", 0),
                    "details": data.get("details", []),  # 🔧 修复：添加问题品种详情
                }

                # 🔧 关键修复：使用Qt Signal/Slot机制代替QTimer.singleShot
                # 原因：Signal自动跨线程调度，Qt保证槽函数在接收者所在线程（主线程）执行
                # 优势：
                # 1. 线程安全：Qt自动处理跨线程调用
                # 2. 可靠性：不依赖事件循环的实现细节
                # 3. 符合Qt最佳实践
                try:
                    self.quality_update_signal.emit(quality_data)
                    self.quality_scan_status_signal.emit(False)  # False = 扫描完成
                    self.logger.info("✅ 已发射质量更新和状态重置信号")
                except Exception as signal_err:
                    self.logger.error("发射Signal失败: %s", signal_err, exc_info=True)
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

        ⚠️ 关键：vnpy事件引擎可能在非Qt主线程中调用此方法
        所有Qt UI操作必须通过QTimer.singleShot转发到主线程

        Args:
            event: vnpy事件对象
        """
        try:
            event_data = event.data
            total = event_data.get("total_symbols", 0)

            self.logger.info("收到扫描完成事件: 总品种=%s", total)

            # 转发到主线程执行UI更新
            QTimer.singleShot(0, lambda: self._handle_scan_complete_ui())

        except Exception as e:
            self.logger.error("处理扫描完成事件失败: %s", e)

    def _handle_scan_complete_ui(self):
        """处理扫描完成UI更新（在主线程中执行）"""
        try:
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
            self.logger.error("处理扫描完成UI失败: %s", e)
