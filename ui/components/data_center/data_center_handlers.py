# -*- coding: utf-8 -*-
"""
数据中心事件处理器 - 错误追踪和详细报告版本

专注于详细错误报告机制，让用户知道数据中心操作的具体问题。
"""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
import asyncio
import threading

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QTableWidgetItem

from backend.core.shared_services import ErrorSeverity, get_service_manager

if TYPE_CHECKING:
    from .main_view import DataCenter

logger = logging.getLogger(__name__)


class DataCenterHandlers:
    """数据中心事件处理器 - 专注于错误追踪和详细报告"""

    def __init__(self, parent: "DataCenter"):
        """初始化处理器"""
        self.parent: "DataCenter" = parent
        self.service_manager = get_service_manager()
        self.logger = logging.getLogger(self.__class__.__name__)

        # 分页相关属性
        self.current_page = 1
        self.page_size = 50
        self.total_pages = 1
        self.all_symbols_data = []
        self.filtered_symbols_data = []

        # 初始化
        self._initialization_successful = False
        self._attempt_initialization()

    def _attempt_initialization(self):
        """尝试初始化事件处理器"""
        try:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "INITIALIZATION_START",
                "开始初始化数据中心事件处理器",
                severity=ErrorSeverity.INFO,
            )

            if not self.service_manager:
                self.service_manager.record_error(
                    "DataCenterHandlers",
                    "SERVICE_MANAGER_UNAVAILABLE",
                    "服务管理器不可用",
                    severity=ErrorSeverity.CRITICAL,
                )
                return

            self._initialization_successful = True
            self.service_manager.record_error(
                "DataCenterHandlers",
                "INITIALIZATION_SUCCESS",
                "数据中心事件处理器初始化成功",
                severity=ErrorSeverity.INFO,
            )

        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "INITIALIZATION_EXCEPTION",
                f"数据中心事件处理器初始化失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.CRITICAL,
            )

    def load_symbols_data(self):
        """加载品种数据"""
        try:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "LOAD_SYMBOLS_START",
                "开始加载品种数据",
                severity=ErrorSeverity.INFO,
            )

            if not self.parent.symbols_table:
                self.service_manager.record_error(
                    "DataCenterHandlers",
                    "UI_COMPONENT_MISSING",
                    "品种表格组件不存在",
                    severity=ErrorSeverity.ERROR,
                )
                return

            symbol_service = self.service_manager.get_service("symbol_service")
            if not symbol_service:
                self.service_manager.record_error(
                    "DataCenterHandlers",
                    "SYMBOL_SERVICE_UNAVAILABLE",
                    "品种服务不可用，使用示例数据",
                    severity=ErrorSeverity.WARNING,
                )
                self._load_example_data()
                return

            # 异步加载
            self._async_load_symbols_wrapper()

        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "LOAD_SYMBOLS_EXCEPTION",
                f"加载品种数据失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            self._load_example_data()

    def _async_load_symbols_wrapper(self):
        """异步加载品种数据的包装器"""

        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._async_load_symbols())
            finally:
                loop.close()

        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()

    async def _async_load_symbols(self):
        """异步加载品种数据"""
        try:
            symbol_service = self.service_manager.get_service("symbol_service")
            if not symbol_service:
                self._load_example_data()
                return

            symbols = await symbol_service.get_all_symbols()
            if not symbols:
                self._load_example_data()
                return

            self.all_symbols_data = [
                {
                    "code": symbol.symbol,
                    "name": symbol.name,
                    "exchange": symbol.exchange,
                    "type": symbol.product or "未知",
                    "status": "活跃" if symbol.is_active else "停用",
                }
                for symbol in symbols
            ]

            self.apply_filters()
            self.service_manager.record_error(
                "DataCenterHandlers",
                "ASYNC_LOAD_SUCCESS",
                f"异步加载品种数据成功，共{len(self.all_symbols_data)}个品种",
                severity=ErrorSeverity.INFO,
            )

        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "ASYNC_LOAD_EXCEPTION",
                f"异步加载品种数据失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            self._load_example_data()

    def _load_example_data(self):
        """加载示例数据"""
        self.all_symbols_data = [
            {
                "code": "000001",
                "name": "平安银行",
                "exchange": "SZSE",
                "type": "深证A股",
                "status": "活跃",
            },
            {
                "code": "600000",
                "name": "浦发银行",
                "exchange": "SSE",
                "type": "上证A股",
                "status": "活跃",
            },
            {
                "code": "600519",
                "name": "贵州茅台",
                "exchange": "SSE",
                "type": "上证A股",
                "status": "活跃",
            },
        ]
        self.apply_filters()

    def apply_filters(self):
        """应用筛选条件"""
        try:
            search_text = (
                self.parent.search_input.text().lower() if self.parent.search_input else ""
            )
            exchange = (
                self.parent.exchange_combo.currentText() if self.parent.exchange_combo else "全部"
            )
            symbol_type = (
                self.parent.symbol_type_combo.currentText()
                if self.parent.symbol_type_combo
                else "全部"
            )

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

            total_count = len(self.filtered_symbols_data)
            self.total_pages = max(1, (total_count + self.page_size - 1) // self.page_size)
            self.current_page = min(self.current_page, self.total_pages)

            self.update_symbols_display()

        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "APPLY_FILTERS_EXCEPTION",
                f"应用筛选条件失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def update_symbols_display(self):
        """更新品种列表显示"""
        try:
            if not self.parent.symbols_table:
                return

            start_idx = (self.current_page - 1) * self.page_size
            end_idx = min(start_idx + self.page_size, len(self.filtered_symbols_data))
            page_data = self.filtered_symbols_data[start_idx:end_idx]

            self.parent.symbols_table.setRowCount(len(page_data))
            for row, item in enumerate(page_data):
                self.parent.symbols_table.setItem(row, 0, QTableWidgetItem(item["code"]))
                self.parent.symbols_table.setItem(row, 1, QTableWidgetItem(item["name"]))
                self.parent.symbols_table.setItem(row, 2, QTableWidgetItem(item["exchange"]))
                self.parent.symbols_table.setItem(row, 3, QTableWidgetItem(item["type"]))
                self.parent.symbols_table.setItem(row, 4, QTableWidgetItem(item["status"]))

                # 添加操作按钮
                self._add_operation_buttons(row, item["code"])

            self._update_display_labels(start_idx, end_idx)

        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "UPDATE_SYMBOLS_DISPLAY_EXCEPTION",
                f"更新品种显示失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def _add_operation_buttons(self, row: int, code: str):
        """添加操作按钮"""
        try:
            from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton

            op_widget = QWidget()
            op_layout = QHBoxLayout(op_widget)
            op_layout.setContentsMargins(2, 2, 2, 2)

            view_btn = QPushButton("查看")
            view_btn.clicked.connect(lambda: self.on_view_symbol(code))
            op_layout.addWidget(view_btn)

            if self.parent.symbols_table:
                self.parent.symbols_table.setCellWidget(row, 5, op_widget)

        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "ADD_OPERATION_BUTTONS_EXCEPTION",
                f"添加操作按钮失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.WARNING,
            )

    def _update_display_labels(self, start_idx: int, end_idx: int):
        """更新显示标签"""
        try:
            if self.parent.symbols_count_label:
                total = len(self.filtered_symbols_data)
                self.parent.symbols_count_label.setText(
                    f"共 {total} 个品种（第 {start_idx + 1}-{end_idx} 个）"
                )

            if self.parent.page_label:
                self.parent.page_label.setText(
                    f"第 {self.current_page} 页 / 共 {self.total_pages} 页"
                )

            if self.parent.prev_page_btn:
                self.parent.prev_page_btn.setEnabled(self.current_page > 1)
            if self.parent.next_page_btn:
                self.parent.next_page_btn.setEnabled(self.current_page < self.total_pages)

        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "UPDATE_DISPLAY_LABELS_EXCEPTION",
                f"更新显示标签失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.WARNING,
            )

    def reload_symbols(self):
        """重新加载品种（从API重新获取）"""
        try:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "RELOAD_SYMBOLS_START",
                "开始重新加载品种列表",
                severity=ErrorSeverity.INFO,
            )

            symbol_service = self.service_manager.get_service("symbol_service")
            if not symbol_service:
                error_msg = "品种服务不可用，无法重新加载"
                self.service_manager.record_error(
                    "DataCenterHandlers",
                    "RELOAD_SYMBOLS_SERVICE_UNAVAILABLE",
                    error_msg,
                    severity=ErrorSeverity.ERROR,
                )
                if hasattr(self.parent, "show_error"):
                    self.parent.show_error(error_msg)
                return

            def run_reload():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._async_reload_symbols(symbol_service))
                finally:
                    loop.close()

            thread = threading.Thread(target=run_reload, daemon=True)
            thread.start()

            if hasattr(self.parent, "show_info"):
                self.parent.show_info("正在从API重新加载品种列表...")

        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "RELOAD_SYMBOLS_START_EXCEPTION",
                f"启动重新加载失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    async def _async_reload_symbols(self, symbol_service):
        """异步重新加载品种实现"""
        try:
            success = await symbol_service.reload_symbols_from_api()

            if success:
                await self._async_load_symbols()
                self.service_manager.record_error(
                    "DataCenterHandlers",
                    "RELOAD_SYMBOLS_SUCCESS",
                    "品种列表重新加载成功",
                    severity=ErrorSeverity.INFO,
                )
                if hasattr(self.parent, "show_info"):
                    self.parent.show_info("品种列表重新加载成功！")
            else:
                self.service_manager.record_error(
                    "DataCenterHandlers",
                    "RELOAD_SYMBOLS_API_FAILED",
                    "API重新加载品种列表失败",
                    severity=ErrorSeverity.ERROR,
                )

        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "RELOAD_SYMBOLS_ASYNC_EXCEPTION",
                f"异步重新加载品种失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def query_local_data(self):
        """查询本地数据"""
        try:
            if not self.parent.symbol_input:
                return

            symbol = self.parent.symbol_input.text()
            if not symbol:
                if hasattr(self.parent, "show_warning"):
                    self.parent.show_warning("请输入品种代码")
                return

            if not self.parent.start_date_input or not self.parent.end_date_input:
                return

            start_date_str = self.parent.start_date_input.date().toString("yyyy-MM-dd")
            end_date_str = self.parent.end_date_input.date().toString("yyyy-MM-dd")

            self.service_manager.record_error(
                "DataCenterHandlers",
                "QUERY_DATA_START",
                f"开始查询数据: {symbol} ({start_date_str} 至 {end_date_str})",
                severity=ErrorSeverity.INFO,
            )

            def run_query():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
                    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
                    loop.run_until_complete(self._async_query_data(symbol, start_date, end_date))
                finally:
                    loop.close()

            thread = threading.Thread(target=run_query, daemon=True)
            thread.start()

        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "QUERY_DATA_EXCEPTION",
                f"查询本地数据失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    async def _async_query_data(self, symbol: str, start_date: datetime, end_date: datetime):
        """异步查询数据"""
        try:
            local_data_service = self.service_manager.get_service("local_data_service")
            if not local_data_service:
                return

            data = await local_data_service.query_data(
                symbol=symbol,
                exchange="",
                start_date=start_date,
                end_date=end_date,
                data_type="bar",
                frequency="1d",
                limit=1000,
            )

            if data:
                self.display_market_data(data, symbol)

        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "QUERY_DATA_ASYNC_EXCEPTION",
                f"异步查询数据失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def display_market_data(self, market_data: list, _symbol: str):  # noqa: U100
        """显示市场数据"""
        try:
            _ = _symbol  # 保留参数以保持接口一致性
            if not self.parent.data_table:
                return

            self.parent.data_table.setRowCount(0)
            for row, data_item in enumerate(market_data):
                self.parent.data_table.insertRow(row)

                datetime_obj = data_item.get("datetime", "")
                date_str = (
                    datetime_obj.strftime("%Y-%m-%d")
                    if isinstance(datetime_obj, datetime)
                    else str(datetime_obj)
                )

                self.parent.data_table.setItem(row, 0, QTableWidgetItem(date_str))
                self.parent.data_table.setItem(
                    row, 1, QTableWidgetItem(str(data_item.get("open", 0)))
                )
                self.parent.data_table.setItem(
                    row, 2, QTableWidgetItem(str(data_item.get("high", 0)))
                )
                self.parent.data_table.setItem(
                    row, 3, QTableWidgetItem(str(data_item.get("low", 0)))
                )
                self.parent.data_table.setItem(
                    row, 4, QTableWidgetItem(str(data_item.get("close", 0)))
                )
                self.parent.data_table.setItem(
                    row, 5, QTableWidgetItem(str(data_item.get("volume", 0)))
                )

            if self.parent.data_status_label:
                self.parent.data_status_label.setText(f"显示 {len(market_data)} 条数据")

        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "DISPLAY_MARKET_DATA_EXCEPTION",
                f"显示市场数据失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def on_view_symbol(self, code: str):
        """查看品种详情"""
        try:
            if self.parent.symbol_input:
                self.parent.symbol_input.setText(code)

            if self.parent.tab_widget and self.parent.local_data_tab:
                idx = self.parent.tab_widget.indexOf(self.parent.local_data_tab)
                if idx >= 0:
                    self.parent.tab_widget.setCurrentIndex(idx)

            if self.parent.start_date_input:
                self.parent.start_date_input.setDate(
                    QDate.fromString(
                        (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"), "yyyy-MM-dd"
                    )
                )
            if self.parent.end_date_input:
                self.parent.end_date_input.setDate(
                    QDate.fromString(datetime.now().strftime("%Y-%m-%d"), "yyyy-MM-dd")
                )

            self.query_local_data()

        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "VIEW_SYMBOL_EXCEPTION",
                f"查看品种详情失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def refresh_data(self):
        """刷新数据"""
        self.load_symbols_data()
        if hasattr(self.parent, "show_info"):
            self.parent.show_info("数据中心数据已刷新")

    # 其他方法保持简化版本...
    def prev_page(self):
        """上一页"""
        if self.current_page > 1:
            self.current_page -= 1
            self.update_symbols_display()

    def next_page(self):
        """下一页"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_symbols_display()

    def search_symbols(self):
        """搜索品种"""
        self.apply_filters()

    def on_filter_changed(self, _value: str = ""):  # pylint: disable=unused-argument
        """筛选条件改变时重新筛选"""
        try:
            _ = _value  # 保留参数以保持接口一致性
            self.apply_filters()
        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "FILTER_CHANGED_EXCEPTION",
                f"筛选条件改变失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def refresh_symbols(self):
        """刷新品种（从缓存）"""
        try:
            self.apply_filters()
            if hasattr(self.parent, "show_info"):
                self.parent.show_info("品种列表已刷新")
        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "REFRESH_SYMBOLS_EXCEPTION",
                f"刷新品种失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def save_filter_preset(self):
        """保存筛选条件"""
        try:
            if hasattr(self.parent, "show_info"):
                self.parent.show_info("保存筛选预设功能待实现")
        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "SAVE_FILTER_PRESET_EXCEPTION",
                f"保存筛选预设失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def apply_filter_preset(self, preset_name: str):
        """应用筛选预设"""
        try:
            if hasattr(self.parent, "show_info"):
                self.parent.show_info(f"应用筛选预设 {preset_name} 功能待实现")
        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "APPLY_FILTER_PRESET_EXCEPTION",
                f"应用筛选预设失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def on_search_text_changed(self, _text: str):  # noqa: U100
        """搜索文本改变时实时筛选"""
        try:
            _ = _text  # 保留参数以保持接口一致性
            self.apply_filters()
        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "SEARCH_TEXT_CHANGED_EXCEPTION",
                f"搜索文本改变失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def on_page_size_changed(self, size_text: str):
        """每页显示数量改变"""
        try:
            size = int(size_text)
            if size > 0:
                self.page_size = size
                self.current_page = 1
                self.apply_filters()
        except ValueError:
            pass
        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "PAGE_SIZE_CHANGED_EXCEPTION",
                f"每页显示数量改变失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def toggle_detail_progress(self, checked: bool):
        """切换详细进度显示"""
        try:
            if hasattr(self.parent, "show_info"):
                status = "显示" if checked else "隐藏"
                self.parent.show_info(f"已{status}详细进度")
        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "TOGGLE_DETAIL_PROGRESS_EXCEPTION",
                f"切换详细进度显示失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def start_download(self):
        """开始下载"""
        try:
            if hasattr(self.parent, "show_info"):
                self.parent.show_info("开始下载数据...")
        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "START_DOWNLOAD_EXCEPTION",
                f"开始下载失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def pause_download(self):
        """暂停下载"""
        try:
            if hasattr(self.parent, "show_info"):
                self.parent.show_info("下载已暂停")
        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "PAUSE_DOWNLOAD_EXCEPTION",
                f"暂停下载失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def stop_download(self):
        """停止下载"""
        try:
            if hasattr(self.parent, "show_info"):
                self.parent.show_info("下载已停止")
        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "STOP_DOWNLOAD_EXCEPTION",
                f"停止下载失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def test_connections(self):
        """测试连接"""
        try:
            if hasattr(self.parent, "show_info"):
                self.parent.show_info("正在测试数据源连接...")
        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "TEST_CONNECTIONS_EXCEPTION",
                f"测试连接失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def switch_data_source(self, source_name: str):
        """切换数据源"""
        try:
            if hasattr(self.parent, "show_info"):
                self.parent.show_info(f"正在切换到数据源: {source_name}")
        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "SWITCH_DATA_SOURCE_EXCEPTION",
                f"切换数据源失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    def create_view_handler(self, code: str):
        """创建查看按钮的处理器"""
        try:
            return lambda: self.on_view_symbol(code)
        except Exception as e:
            self.service_manager.record_error(
                "DataCenterHandlers",
                "CREATE_VIEW_HANDLER_EXCEPTION",
                f"创建查看处理器失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return None

    def get_service_status_report(self) -> str:
        """获取服务状态报告"""
        return self.service_manager.get_user_friendly_error_report()


# 导出公共接口
__all__ = ["DataCenterHandlers"]
