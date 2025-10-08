# -*- coding: utf-8 -*-
"""
数据中心界面 - 主视图.

标准架构：4个子界面采用选项卡形式。
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from backend.core.utils.logging_utils import LoggerMixin

    from ui.widgets.base_widget import BaseWidget
else:
    try:
        from backend.core.utils.logging_utils import LoggerMixin
        from ui.widgets.base_widget import BaseWidget
    except ImportError as e:
        raise ImportError(
            f"无法导入必要的UI组件: {e}\n"
            "请确保已正确安装所有依赖：pip install -r requirements.txt"
        )


from .data_center_tabs import DataCenterTabs
from .data_center_handlers import DataCenterHandlers


class DataCenter(BaseWidget, LoggerMixin):
    """数据中心主界面."""

    def __init__(self, parent=None):
        """初始化数据中心界面."""
        # 初始化UI控件引用为None
        self.tab_widget: Optional[QTabWidget] = None
        self.symbols_tab: Optional[QWidget] = None
        self.local_data_tab: Optional[QWidget] = None
        self.download_tab: Optional[QWidget] = None
        self.sources_tab: Optional[QWidget] = None

        # 初始化tabs和handlers为None（将在setup_ui中创建）
        self.tabs = None
        self.handlers = None

        # 调用父类初始化，这时setup_ui()会被调用
        super().__init__(parent, "数据中心")
        self.logger.info("数据中心界面初始化完成")

    # Properties to delegate widget access to tabs manager
    @property
    def symbols_table(self) -> Optional[QTableWidget]:
        """品种表格."""
        return self.tabs.symbols_table

    @property
    def search_input(self) -> Optional[QLineEdit]:
        """搜索输入框."""
        return self.tabs.search_input

    @property
    def exchange_combo(self) -> Optional[QComboBox]:
        """交易所下拉框."""
        return self.tabs.exchange_combo

    @property
    def symbol_type_combo(self) -> Optional[QComboBox]:
        """品种类型下拉框."""
        return self.tabs.symbol_type_combo

    @property
    def symbols_count_label(self) -> Optional[QLabel]:
        """品种统计标签."""
        return self.tabs.symbols_count_label

    @property
    def page_label(self) -> Optional[QLabel]:
        """分页标签."""
        return self.tabs.page_label

    @property
    def prev_page_btn(self) -> Optional[QPushButton]:
        """上一页按钮."""
        return self.tabs.prev_page_btn

    @property
    def next_page_btn(self) -> Optional[QPushButton]:
        """下一页按钮."""
        return self.tabs.next_page_btn

    @property
    def symbol_input(self) -> Optional[QLineEdit]:
        """品种代码输入框."""
        return self.tabs.symbol_input

    @property
    def start_date_input(self) -> Optional[QDateEdit]:
        """开始日期输入框."""
        return self.tabs.start_date_input

    @property
    def end_date_input(self) -> Optional[QDateEdit]:
        """结束日期输入框."""
        return self.tabs.end_date_input

    @property
    def data_table(self) -> Optional[QTableWidget]:
        """数据表格."""
        return self.tabs.data_table

    @property
    def data_status_label(self) -> Optional[QLabel]:
        """数据状态标签."""
        return self.tabs.data_status_label

    @property
    def data_quality_label(self) -> Optional[QLabel]:
        """数据质量标签."""
        return self.tabs.data_quality_label

    @property
    def download_mode_group(self) -> Optional[QButtonGroup]:
        """下载模式按钮组."""
        return self.tabs.download_mode_group

    @property
    def full_download_radio(self) -> Optional[QRadioButton]:
        """全量下载单选按钮."""
        return self.tabs.full_download_radio

    @property
    def custom_download_radio(self) -> Optional[QRadioButton]:
        """自定义下载单选按钮."""
        return self.tabs.custom_download_radio

    @property
    def download_symbols_input(self) -> Optional[QLineEdit]:
        """下载品种输入框."""
        return self.tabs.download_symbols_input

    @property
    def download_start_date(self) -> Optional[QDateEdit]:
        """下载开始日期."""
        return self.tabs.download_start_date

    @property
    def download_end_date(self) -> Optional[QDateEdit]:
        """结束日期."""
        return self.tabs.download_end_date

    @property
    def progress_label(self) -> Optional[QLabel]:
        """进度标签."""
        return self.tabs.progress_label

    @property
    def start_download_btn(self) -> Optional[QPushButton]:
        """开始下载按钮."""
        return self.tabs.start_download_btn

    @property
    def pause_download_btn(self) -> Optional[QPushButton]:
        """暂停下载按钮."""
        return self.tabs.pause_download_btn

    @property
    def stop_download_btn(self) -> Optional[QPushButton]:
        """停止下载按钮."""
        return self.tabs.stop_download_btn

    @property
    def download_progress(self) -> Optional[QProgressBar]:
        """下载进度条."""
        return self.tabs.download_progress

    @property
    def config_status_label(self) -> Optional[QLabel]:
        """配置状态标签."""
        return self.tabs.config_status_label

    @property
    def monitor_text(self) -> Optional[QTextEdit]:
        """监控文本框."""
        return self.tabs.monitor_text

    @property
    def sources_table(self) -> Optional[QTableWidget]:
        """数据源表格."""
        return self.tabs.sources_table

    @property
    def detail_progress_table(self) -> Optional[QTableWidget]:
        """详细进度表格."""
        return self.tabs.detail_progress_table

    @property
    def toggle_detail_btn(self) -> Optional[QPushButton]:
        """详细进度切换按钮."""
        return self.tabs.toggle_detail_btn

    def setup_ui(self):
        """设置用户界面."""
        # 在setup_ui中创建tabs和handlers（此时self已经是完整的QWidget）
        if self.tabs is None:
            self.tabs = DataCenterTabs(self)
        if self.handlers is None:
            self.handlers = DataCenterHandlers(self)

        main_layout = QVBoxLayout(self)

        # 创建选项卡部件
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)

        # 创建4个子界面（通过选项卡管理器）
        self._create_sub_interfaces()

        if self.tab_widget:
            main_layout.addWidget(self.tab_widget)

    def _create_sub_interfaces(self):
        """创建4个子界面."""
        if not self.tab_widget:
            return

        # 使用选项卡管理器创建各个选项卡
        self.symbols_tab = self.tabs.create_symbols_tab()
        if self.symbols_tab:
            self.tab_widget.addTab(self.symbols_tab, "📋 品种列表")

        self.local_data_tab = self.tabs.create_local_data_tab()
        if self.local_data_tab:
            self.tab_widget.addTab(self.local_data_tab, "💾 本地数据")

        self.download_tab = self.tabs.create_download_tab()
        if self.download_tab:
            self.tab_widget.addTab(self.download_tab, "⬇️ 数据下载")

        self.sources_tab = self.tabs.create_sources_tab()
        if self.sources_tab:
            self.tab_widget.addTab(self.sources_tab, "🔗 数据源管理")

    def connect_signals(self):
        """连接信号槽."""
        # 连接品种输入框筛选功能
        if self.tabs.symbol_input:
            self.tabs.symbol_input.textChanged.connect(self.handlers.on_filter_changed)

    # 委托所有业务逻辑方法给处理器
    def _reload_symbols(self):
        """重新加载品种（通过API）."""
        return self.handlers.reload_symbols()

    def _refresh_symbols(self):
        """刷新品种（从缓存）."""
        return self.handlers.refresh_symbols()

    def _save_filter_preset(self):
        """保存筛选条件."""
        return self.handlers.save_filter_preset()

    def _apply_filter_preset(self, preset_name: str):
        """应用筛选预设."""
        return self.handlers.apply_filter_preset(preset_name)

    def _on_search_text_changed(self, text: str):
        """搜索文本改变时实时筛选."""
        return self.handlers.on_search_text_changed(text)

    def _on_filter_changed(self, value: str):
        """筛选条件改变时重新筛选."""
        return self.handlers.on_filter_changed(value)

    def _on_page_size_changed(self, size_text: str):
        """每页显示数量改变."""
        return self.handlers.on_page_size_changed(size_text)

    def _prev_page(self):
        """上一页."""
        return self.handlers.prev_page()

    def _next_page(self):
        """下一页."""
        return self.handlers.next_page()

    def _toggle_detail_progress(self, checked: bool):
        """切换详细进度显示."""
        return self.handlers.toggle_detail_progress(checked)

    def _query_local_data(self):
        """查询本地数据."""
        return self.handlers.query_local_data()

    def _start_download(self):
        """开始下载."""
        return self.handlers.start_download()

    def _pause_download(self):
        """暂停下载."""
        return self.handlers.pause_download()

    def _stop_download(self):
        """停止下载."""
        return self.handlers.stop_download()

    def _test_connections(self):
        """测试连接."""
        return self.handlers.test_connections()

    def _switch_data_source(self, source_name):
        """切换数据源."""
        return self.handlers.switch_data_source(source_name)

    def refresh_data(self):
        """刷新数据."""
        return self.handlers.refresh_data()

    def _create_view_handler(self, code: str):
        """创建查看按钮的处理器."""
        return self.handlers.create_view_handler(code)

    def _on_view_symbol(self, code: str):
        """在品种列表中点击查看：填充代码、切换到本地数据、补全日期并查询。"""
        return self.handlers.on_view_symbol(code)

    def on_close(self):
        """关闭处理."""
        self.logger.info("数据中心界面已关闭")
