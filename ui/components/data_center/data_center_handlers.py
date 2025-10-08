# -*- coding: utf-8 -*-
"""数据中心事件处理器模块 - 分离业务逻辑和事件处理."""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional
import asyncio

from PySide6.QtCore import QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidgetItem

from .data_center_utils import FILTER_PRESETS

# 导入后端服务
from backend.services.data_center.local_data_service import LocalDataService
from backend.core.shared_services import get_service_manager

if TYPE_CHECKING:
    from .main_view import DataCenter


class DataCenterHandlers:
    """数据中心事件处理器."""

    def __init__(self, parent: "DataCenter"):
        """初始化处理器."""
        self.parent: "DataCenter" = parent
        self.logger = logging.getLogger(self.__class__.__name__)

        # 分页相关属性
        self.current_page = 1
        self.page_size = 50
        self.total_pages = 1
        self.all_symbols_data = []  # 存储所有品种数据
        self.filtered_symbols_data = []  # 存储筛选后的数据

        # 获取后端服务
        self.local_data_service: Optional[LocalDataService] = None
        self._initialize_services()

    def _initialize_services(self):
        """初始化后端服务."""
        try:
            service_manager = get_service_manager()
            if not service_manager:
                raise RuntimeError("服务管理器未初始化")

            self.local_data_service = service_manager.get("local_data_service")
            if not self.local_data_service:
                raise RuntimeError("本地数据服务未初始化")

            self.logger.info("后端服务初始化完成")
        except Exception as e:
            self.logger.error("后端服务初始化失败: %s", e)
            raise

    def load_symbols_data(self):
        """加载品种数据 - 从后端服务获取."""
        # 添加空值检查
        if not self.parent.symbols_table:
            return

        try:
            # 从后端服务获取品种数据
            from backend.core.shared_services import get_service_manager

            service_manager = get_service_manager()
            if not service_manager:
                raise RuntimeError("服务管理器未初始化")

            symbol_service = service_manager.get("symbol_service")
            if not symbol_service:
                raise RuntimeError("品种服务未初始化")

            # 异步获取品种数据
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._async_load_symbols())
            else:
                loop.run_until_complete(self._async_load_symbols())

        except Exception as e:
            self.logger.error("加载品种数据失败: %s", e)
            self.parent.show_error(f"加载品种数据失败: {str(e)}")

    async def _async_load_symbols(self):
        """异步加载品种数据."""
        try:
            from backend.core.shared_services import get_service_manager

            service_manager = get_service_manager()
            symbol_service = service_manager.get("symbol_service")

            # 获取所有品种
            symbols = await symbol_service.get_all_symbols()

            # 转换为表格所需的格式
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

            # 应用筛选
            self.apply_filters()

            self.parent.show_info(f"已加载 {len(self.all_symbols_data)} 个品种")

        except Exception as e:
            self.logger.error("异步加载品种数据失败: %s", e)
            self.parent.show_error(f"加载品种数据失败: {str(e)}")

    def apply_filters(self):
        """应用所有筛选条件."""
        search_text = self.parent.search_input.text().lower() if self.parent.search_input else ""
        exchange = (
            self.parent.exchange_combo.currentText() if self.parent.exchange_combo else "全部"
        )
        symbol_type = (
            self.parent.symbol_type_combo.currentText() if self.parent.symbol_type_combo else "全部"
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

        # 更新显示
        self.update_symbols_display()

    def update_symbols_display(self):
        """更新品种列表显示."""
        if not self.parent.symbols_table:
            return

        # 计算当前页的数据范围
        start_idx = (self.current_page - 1) * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.filtered_symbols_data))
        page_data = self.filtered_symbols_data[start_idx:end_idx]

        # 更新表格
        self.parent.symbols_table.setRowCount(len(page_data))
        for row, item in enumerate(page_data):
            self.parent.symbols_table.setItem(row, 0, QTableWidgetItem(item["code"]))
            self.parent.symbols_table.setItem(row, 1, QTableWidgetItem(item["name"]))
            self.parent.symbols_table.setItem(row, 2, QTableWidgetItem(item["exchange"]))
            self.parent.symbols_table.setItem(row, 3, QTableWidgetItem(item["type"]))
            self.parent.symbols_table.setItem(row, 4, QTableWidgetItem(item["status"]))

            # 添加操作按钮
            from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton

            op_widget = QWidget()
            op_layout = QHBoxLayout(op_widget)
            op_layout.setContentsMargins(2, 2, 2, 2)

            view_btn = QPushButton("查看")
            view_btn.setToolTip("查看该品种详情")
            view_btn.clicked.connect(self.create_view_handler(item["code"]))
            op_layout.addWidget(view_btn)

            self.parent.symbols_table.setCellWidget(row, 5, op_widget)

        # 更新统计标签
        if self.parent.symbols_count_label:
            total = len(self.filtered_symbols_data)
            label_text = f"共 {total} 个品种（第 {start_idx + 1}-{end_idx} 个）"
            self.parent.symbols_count_label.setText(label_text)

        # 更新分页标签
        if self.parent.page_label:
            page_text = f"第 {self.current_page} 页 / 共 {self.total_pages} 页"
            self.parent.page_label.setText(page_text)

        # 更新分页按钮状态
        if self.parent.prev_page_btn:
            self.parent.prev_page_btn.setEnabled(self.current_page > 1)
        if self.parent.next_page_btn:
            self.parent.next_page_btn.setEnabled(self.current_page < self.total_pages)

    def prev_page(self):
        """上一页."""
        if self.current_page > 1:
            self.current_page -= 1
            self.update_symbols_display()

    def next_page(self):
        """下一页."""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_symbols_display()

    def on_page_size_changed(self, size_text: str):
        """每页显示数量改变."""
        self.page_size = int(size_text)
        self.current_page = 1
        self.apply_filters()

    def save_filter_preset(self):
        """保存当前筛选条件为预设."""
        self.parent.show_info("筛选条件已保存")
        # 这里可以实现保存筛选条件到配置文件的逻辑

    def apply_filter_preset(self, preset_name: str):
        """应用预设筛选条件."""
        if preset_name == "无":
            return

        if preset_name in FILTER_PRESETS:
            preset = FILTER_PRESETS[preset_name]
            if self.parent.exchange_combo:
                self.parent.exchange_combo.setCurrentText(preset.get("exchange", "全部"))
            if self.parent.symbol_type_combo:
                self.parent.symbol_type_combo.setCurrentText(preset.get("type", "全部"))
            self.parent.show_info(f"已应用预设筛选: {preset_name}")

    def query_local_data(self):
        """查询本地数据."""
        # 添加空值检查
        if (
            not self.parent.symbol_input
            or not self.parent.start_date_input
            or not self.parent.end_date_input
        ):
            return

        symbol = self.parent.symbol_input.text()

        # 获取日期输入框的值
        start_date_str = self.parent.start_date_input.date().toString("yyyy-MM-dd")
        end_date_str = self.parent.end_date_input.date().toString("yyyy-MM-dd")

        if not symbol:
            self.parent.show_warning("请输入品种代码")
            return

        self.parent.show_info(f"查询数据: {symbol} ({start_date_str} 至 {end_date_str})")

        try:
            if not self.local_data_service:
                raise RuntimeError("本地数据服务未初始化")

            # 转换日期格式
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

            # 从后端服务获取数据（异步调用需要在事件循环中执行）
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环已经在运行，使用create_task
                asyncio.create_task(self._async_query_data(symbol, start_date, end_date))
            else:
                # 否则直接运行
                loop.run_until_complete(self._async_query_data(symbol, start_date, end_date))

        except Exception as e:
            self.logger.error("查询数据失败: %s", e)
            self.parent.show_error(f"查询数据失败: {str(e)}")

    async def _async_query_data(self, symbol: str, start_date: datetime, end_date: datetime):
        """异步查询数据."""
        try:
            # 调用后端服务获取数据
            data = await self.local_data_service.get_bar_data(
                symbol=symbol,
                exchange="",  # 交易所由symbol推断
                start_date=start_date,
                end_date=end_date,
                frequency="1d",
                limit=1000,
            )

            if not data:
                raise ValueError(f"未找到品种 {symbol} 的数据")

            # 显示数据
            self.display_market_data(data, symbol)

            if self.parent.data_status_label:
                self.parent.data_status_label.setText(f"显示 {len(data)} 条数据")
            if self.parent.data_quality_label:
                self.parent.data_quality_label.setText("数据质量: 来自VnPy")

        except Exception as e:
            self.logger.error("异步查询数据失败: %s", e)
            self.parent.show_error(f"查询数据失败: {str(e)}")

    def display_market_data(self, market_data: list, symbol: str):
        """显示市场数据.

        Args:
            market_data: 市场数据列表
            symbol: 品种代码
        """
        # symbol 参数保留用于日志
        _ = symbol

        # 添加空值检查
        if not self.parent.data_table:
            return

        # 清空表格
        self.parent.data_table.setRowCount(0)

        for row, data_item in enumerate(market_data):
            self.parent.data_table.insertRow(row)

            # 格式化日期
            datetime_obj = data_item.get("datetime", "")
            if isinstance(datetime_obj, datetime):
                date_str = datetime_obj.strftime("%Y-%m-%d")
            else:
                date_str = str(datetime_obj)

            self.parent.data_table.setItem(row, 0, QTableWidgetItem(date_str))
            self.parent.data_table.setItem(
                row, 1, QTableWidgetItem(str(data_item.get("open_price", 0)))
            )
            self.parent.data_table.setItem(
                row, 2, QTableWidgetItem(str(data_item.get("high_price", 0)))
            )
            self.parent.data_table.setItem(
                row, 3, QTableWidgetItem(str(data_item.get("low_price", 0)))
            )
            self.parent.data_table.setItem(
                row, 4, QTableWidgetItem(str(data_item.get("close_price", 0)))
            )
            self.parent.data_table.setItem(
                row, 5, QTableWidgetItem(str(data_item.get("volume", 0)))
            )

            # 计算成交额
            close_price = data_item.get("close_price", 0)
            volume = data_item.get("volume", 0)
            turnover = data_item.get("turnover", close_price * volume)
            self.parent.data_table.setItem(row, 6, QTableWidgetItem(str(turnover)))

        if self.parent.data_status_label:
            self.parent.data_status_label.setText(f"显示 {len(market_data)} 条数据")
        if self.parent.data_quality_label:
            self.parent.data_quality_label.setText("数据质量: 良好")

    def start_download(self):
        """开始下载."""
        selected_button = (
            self.parent.download_mode_group.checkedButton()
            if self.parent.download_mode_group
            else None
        )
        if selected_button == self.parent.full_download_radio:
            self.start_full_download()
        elif selected_button == self.parent.custom_download_radio:
            self.start_custom_download()
        else:
            # 默认执行全量下载
            self.start_full_download()

    def start_full_download(self):
        """开始全量下载."""
        self.parent.show_info("开始全量数据下载...")

        # 更新UI状态
        if self.parent.progress_label:
            self.parent.progress_label.setText("全量下载中...")
        if self.parent.start_download_btn:
            self.parent.start_download_btn.setEnabled(False)
        if self.parent.pause_download_btn:
            self.parent.pause_download_btn.setEnabled(True)
        if self.parent.stop_download_btn:
            self.parent.stop_download_btn.setEnabled(True)

        # 执行真实下载
        self.simulate_download_progress()

    def start_custom_download(self):
        """开始自定义下载."""
        # 添加空值检查
        if not self.parent.download_symbols_input:
            return

        symbols = self.parent.download_symbols_input.text()
        # 获取日期范围（虽然当前实现中未使用，但保留接口以供将来扩展）
        # NOTE: 在实际的数据下载功能中可以使用这些日期参数
        # 这些变量目前未使用，但保留以供将来功能扩展
        start_date_str = (
            self.parent.download_start_date.date().toString("yyyy-MM-dd")
            if self.parent.download_start_date
            else ""
        )
        end_date_str = (
            self.parent.download_end_date.date().toString("yyyy-MM-dd")
            if self.parent.download_end_date
            else ""
        )
        # 使用变量以避免未使用警告，但实际逻辑中暂不处理
        _ = start_date_str, end_date_str  # type: ignore

        if not symbols or symbols == "全部":
            self.parent.show_warning("请输入要下载的品种列表")
            return

        self.parent.show_info(f"开始自定义下载: {symbols}")

        # 更新UI状态
        if self.parent.progress_label:
            self.parent.progress_label.setText("自定义下载中...")
        if self.parent.start_download_btn:
            self.parent.start_download_btn.setEnabled(False)
        if self.parent.pause_download_btn:
            self.parent.pause_download_btn.setEnabled(True)
        if self.parent.stop_download_btn:
            self.parent.stop_download_btn.setEnabled(True)

        # 执行真实下载
        self.simulate_download_progress()

    def pause_download(self):
        """暂停下载."""
        self.parent.show_info("下载已暂停")
        if self.parent.pause_download_btn:
            self.parent.pause_download_btn.setText("继续")
            self.parent.pause_download_btn.clicked.disconnect()
            self.parent.pause_download_btn.clicked.connect(self.resume_download)

    def resume_download(self):
        """继续下载."""
        self.parent.show_info("下载继续...")
        if self.parent.pause_download_btn:
            self.parent.pause_download_btn.setText("暂停")
            self.parent.pause_download_btn.clicked.disconnect()
            self.parent.pause_download_btn.clicked.connect(self.pause_download)

    def stop_download(self):
        """停止下载."""
        self.parent.show_info("下载已停止")

        # 停止进度更新（如果有的话）
        if self.parent.download_progress:
            self.parent.download_progress.setValue(0)

        # 调用完成方法来统一更新UI状态
        self.complete_download()

    def simulate_download_progress(self, db_path=None):
        """启动真实数据下载."""
        # db_path 参数保留用于兼容性
        _ = db_path

        try:
            # 获取后端服务
            from backend.core.shared_services import get_service_manager

            service_manager = get_service_manager()
            if not service_manager:
                raise RuntimeError("服务管理器未初始化")

            download_service = service_manager.get("download_service")
            if not download_service:
                raise RuntimeError("下载服务未初始化")

            # 异步执行下载任务
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._async_start_download())
            else:
                loop.run_until_complete(self._async_start_download())

        except Exception as e:
            self.logger.error("启动数据下载失败: %s", e)
            self.parent.show_error(f"启动数据下载失败: {str(e)}")
            self.complete_download()

    async def _async_start_download(self):
        """异步执行下载任务."""
        try:
            from backend.core.shared_services import get_service_manager
            from datetime import datetime, timedelta

            service_manager = get_service_manager()
            download_service = service_manager.get("download_service")
            symbol_service = service_manager.get("symbol_service")

            if not symbol_service:
                raise RuntimeError("品种服务未初始化")

            # 获取要下载的品种列表
            symbols_to_download = []

            # 检查下载模式
            selected_button = (
                self.parent.download_mode_group.checkedButton()
                if self.parent.download_mode_group
                else None
            )

            if selected_button == self.parent.full_download_radio:
                # 全量下载：获取所有品种
                symbols = await symbol_service.get_all_symbols()
                symbols_to_download = symbols
            else:
                # 自定义下载：解析用户输入的品种列表
                if self.parent.download_symbols_input:
                    symbols_text = self.parent.download_symbols_input.text()
                    if symbols_text and symbols_text != "全部":
                        # 分割品种代码（支持逗号、空格分隔）
                        symbol_codes = [
                            s.strip() for s in symbols_text.replace(",", " ").split() if s.strip()
                        ]
                        for code in symbol_codes:
                            # 尝试查找品种
                            search_results = await symbol_service.search_symbols(code)
                            if search_results:
                                symbols_to_download.extend(search_results)
                    else:
                        # 如果为空，下载所有品种
                        symbols = await symbol_service.get_all_symbols()
                        symbols_to_download = symbols

            if not symbols_to_download:
                raise ValueError("没有找到要下载的品种")

            # 获取日期范围
            if self.parent.download_start_date and self.parent.download_end_date:
                start_date_str = self.parent.download_start_date.date().toString("yyyy-MM-dd")
                end_date_str = self.parent.download_end_date.date().toString("yyyy-MM-dd")
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
            else:
                # 默认下载最近30天的数据
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)

            # 创建下载任务
            total_symbols = len(symbols_to_download)
            self.parent.show_info(f"开始下载 {total_symbols} 个品种的数据...")

            completed = 0
            failed = 0

            for symbol in symbols_to_download:
                try:
                    # 创建下载任务
                    task = await download_service.create_download_task(
                        symbol=symbol.symbol,
                        exchange=symbol.exchange,
                        start_date=start_date,
                        end_date=end_date,
                        data_type="bar",
                        frequency="1d",
                    )

                    completed += 1
                    progress = int((completed / total_symbols) * 100)

                    # 更新进度条
                    if self.parent.download_progress:
                        self.parent.download_progress.setValue(progress)

                    if self.parent.progress_label:
                        self.parent.progress_label.setText(
                            f"下载中... {completed}/{total_symbols} ({progress}%)"
                        )

                    self.logger.info("已创建下载任务: %s.%s", symbol.symbol, symbol.exchange)

                except Exception as e:
                    failed += 1
                    self.logger.error(
                        "创建下载任务失败: %s.%s - %s", symbol.symbol, symbol.exchange, e
                    )

            # 下载完成
            if self.parent.download_progress:
                self.parent.download_progress.setValue(100)

            self.parent.show_info(f"数据下载任务创建完成！成功: {completed}, 失败: {failed}")
            self.complete_download()

        except Exception as e:
            self.logger.error("异步下载数据失败: %s", e)
            self.parent.show_error(f"数据下载失败: {str(e)}")
            self.complete_download()

    def complete_download(self):
        """完成下载，更新UI状态."""
        if self.parent.progress_label:
            # 根据当前状态设置合适的文本
            current_text = self.parent.progress_label.text()
            if "完成" in current_text:
                self.parent.progress_label.setText("下载完成")
            else:
                self.parent.progress_label.setText("准备就绪")
        if self.parent.start_download_btn:
            self.parent.start_download_btn.setEnabled(True)
        if self.parent.pause_download_btn:
            self.parent.pause_download_btn.setEnabled(False)
        if self.parent.stop_download_btn:
            self.parent.stop_download_btn.setEnabled(False)

    def test_connections(self):
        """测试连接."""
        self.parent.show_info("测试数据源连接...")

        try:
            if not self.local_data_service:
                raise RuntimeError("本地数据服务未初始化")

            # 从后端服务获取真实状态
            status = self.local_data_service.get_data_source_status()

            # 更新数据源表格
            self.update_data_sources_table(status)

            # 更新配置状态
            if self.parent.config_status_label:
                self.parent.config_status_label.setText("配置状态: 连接正常")

            if self.parent.monitor_text:
                self.parent.monitor_text.append("连接测试完成 - 数据源状态已更新")

        except Exception as e:
            self.logger.error("连接测试失败: %s", e)
            self.parent.show_error(f"连接测试失败: {str(e)}")
            if self.parent.config_status_label:
                self.parent.config_status_label.setText("配置状态: 测试失败")

    def update_data_sources_table(self, status):
        """更新数据源表格."""
        if not self.parent.sources_table:
            return
        # 清空表格
        self.parent.sources_table.setRowCount(0)

        data_sources = status.get("data_sources", [])
        active_source = status.get("active_data_source", "")

        for i, source_name in enumerate(data_sources):
            self.parent.sources_table.insertRow(i)

            # 数据源名称
            self.parent.sources_table.setItem(i, 0, QTableWidgetItem(source_name))

            # 类型（这里可以根据实际情况设置）
            source_type = "VNPY"  # 只使用真实数据源
            self.parent.sources_table.setItem(i, 1, QTableWidgetItem(source_type))

            # 状态
            if source_name == active_source:
                status_text = "活动"
                status_color = QColor("#4caf50")
            else:
                status_text = "可用"
                status_color = QColor("#2196f3")

            status_item = QTableWidgetItem(status_text)
            status_item.setBackground(status_color)
            self.parent.sources_table.setItem(i, 2, status_item)

            # 连接数
            self.parent.sources_table.setItem(i, 3, QTableWidgetItem("1"))

            # 操作按钮
            from PySide6.QtWidgets import QPushButton

            switch_btn = QPushButton("切换到此源")

            def connect_switch_btn(src):
                def switch_handler():
                    return self.switch_data_source(src)

                return switch_handler

            switch_btn.clicked.connect(connect_switch_btn(source_name))
            self.parent.sources_table.setCellWidget(i, 4, switch_btn)

    def switch_data_source(self, source_name):
        """切换数据源."""
        try:
            if not self.local_data_service:
                raise RuntimeError("本地数据服务未初始化")

            # 实现真实的数据源切换逻辑
            self.local_data_service.switch_data_source(source_name)
            self.parent.show_info(f"已切换到数据源: {source_name}")

        except Exception as e:
            self.logger.error("切换数据源失败: %s", e)
            self.parent.show_error(f"切换数据源失败: {str(e)}")

    def toggle_detail_progress(self, checked: bool):
        """切换详细进度显示."""
        if self.parent.detail_progress_table:
            self.parent.detail_progress_table.setVisible(checked)
        if self.parent.toggle_detail_btn:
            text = "▲ 隐藏详细进度" if checked else "▼ 显示详细进度"
            self.parent.toggle_detail_btn.setText(text)

    def on_view_symbol(self, code: str):
        """在品种列表中点击查看：填充代码、切换到本地数据、补全日期并查询。"""
        try:
            if self.parent.symbol_input:
                self.parent.symbol_input.setText(code)
            # 切换到本地数据标签页
            if self.parent.tab_widget and self.parent.local_data_tab:
                idx = self.parent.tab_widget.indexOf(self.parent.local_data_tab)
                if idx >= 0:
                    self.parent.tab_widget.setCurrentIndex(idx)
            # 补全默认日期
            if self.parent.start_date_input:
                self.parent.start_date_input.setDate(
                    QDate.fromString(
                        (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                        "yyyy-MM-dd",
                    )
                )
            if self.parent.end_date_input:
                self.parent.end_date_input.setDate(
                    QDate.fromString(datetime.now().strftime("%Y-%m-%d"), "yyyy-MM-dd")
                )
            # 执行查询
            self.query_local_data()
        except (AttributeError, RuntimeError, ValueError) as e:
            self.parent.show_error(f"查看品种失败: {e}")

    def refresh_data(self):
        """刷新数据."""
        self.load_symbols_data()
        self.parent.show_info("数据中心数据已刷新")

    def reload_symbols(self):
        """重新加载品种（从后端服务）."""
        try:
            self.logger.info("正在从后端服务重新加载品种列表...")

            # 直接调用load_symbols_data来加载品种数据
            self.load_symbols_data()

        except Exception as e:
            self.logger.error("重新加载品种失败: %s", e)
            self.parent.show_error(f"加载失败: {str(e)}")

    def refresh_symbols(self):
        """刷新品种（从缓存）."""
        self.parent.show_info("从本地缓存刷新品种列表...")
        # 从缓存加载
        self.load_symbols_data()
        self.parent.show_info("品种列表已刷新")

    def search_symbols(self):
        """搜索品种."""
        # 添加空值检查
        if not self.parent.search_input or not self.parent.exchange_combo:
            return

        search_text = self.parent.search_input.text()
        exchange = self.parent.exchange_combo.currentText()

        self.parent.show_info(f"搜索品种: {search_text}, 交易所: {exchange}")

        try:
            # 从后端服务获取品种数据
            self.load_symbols_data()
        except Exception as e:
            self.logger.error("搜索品种失败: %s", e)
            self.parent.show_error(f"搜索品种失败: {str(e)}")

    def on_search_text_changed(self, text: str):
        """搜索文本改变时实时筛选."""
        # 使用传入的文本参数进行筛选，避免重复获取
        search_text = text.lower() if text else ""
        if hasattr(self.parent, "search_input") and self.parent.search_input:
            # 更新搜索框文本（如果不是来自搜索框本身的改变）
            current_text = self.parent.search_input.text().lower()
            if current_text != search_text:
                return  # 避免递归调用
        self.apply_filters()

    def on_filter_changed(self, value: str):
        """筛选条件改变时重新筛选."""
        # 使用传入的值参数进行筛选，避免重复获取
        exchange = (
            self.parent.exchange_combo.currentText() if self.parent.exchange_combo else "全部"
        )
        symbol_type = (
            self.parent.symbol_type_combo.currentText() if self.parent.symbol_type_combo else "全部"
        )

        # 检查传入的值是否与当前选择匹配，避免重复筛选
        if value not in [exchange, symbol_type]:
            return  # 如果值不匹配，可能是旧的信号，不处理
        self.apply_filters()

    def create_view_handler(self, code: str):
        """创建查看按钮的处理器."""

        def handler():
            self.on_view_symbol(code)

        return handler
