# -*- coding: utf-8 -*-
"""行情看板界面 - 主视图（vnpy_chartwizard版）.

多标签页界面：基于 vnpy_chartwizard 的专业图表应用。
支持多品种同时监控、实时数据自动订阅、Tick转K线合成。
集成品种叠加、指标叠加、对数坐标等高级功能。
"""
from typing import Optional

from PySide6.QtWidgets import (
    QVBoxLayout,
)

from backend.core.base import get_service_manager
from backend.core.utils import LoggerMixin

from ui.widgets.base_widget import BaseWidget
from ui.widgets.chart_wizard_enhanced import ChartWizardEnhanced


class MarketDashboard(BaseWidget, LoggerMixin):
    """行情看板主界面（vnpy_chartwizard版）."""

    def __init__(self, parent=None):
        """初始化行情看板."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.market_service = None

        # 初始化核心组件
        self.chart_wizard: Optional[ChartWizardEnhanced] = None

        # 调用父类初始化
        super().__init__(parent, "行情看板")
        self.logger.info("行情看板界面初始化开始（vnpy_chartwizard版）")

        # 初始化服务
        self._initialize_service()

    def _initialize_service(self):
        """获取行情看板服务."""
        try:
            # 从服务管理器获取行情看板服务
            self.market_service = self.service_manager.get_service("market_board_service")
            if self.market_service:
                self.logger.info("行情看板服务获取成功")
            else:
                self.logger.warning("行情看板服务未注册")
        except Exception as e:
            self.logger.error("获取行情看板服务失败: %s", e)
            self.show_error(f"服务获取失败: {e}")

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建 ChartWizardEnhanced 核心组件
        self.chart_wizard = ChartWizardEnhanced(self)
        main_layout.addWidget(self.chart_wizard)

        self.logger.info("✅ 行情看板界面创建完成（基于vnpy_chartwizard）")

    def connect_signals(self):
        """连接信号槽."""
        # vnpy_chartwizard 已内置完整的事件处理
        # 这里只需要连接自定义的扩展功能

        if self.chart_wizard:
            # 连接图表创建信号
            self.chart_wizard.chart_created.connect(self._on_chart_created)
            # 连接图表关闭信号
            self.chart_wizard.chart_closed.connect(self._on_chart_closed)
            # 连接品种变化信号
            self.chart_wizard.symbol_changed.connect(self._on_symbol_changed)

        self.logger.info("✅ 信号连接完成")

    def _on_chart_created(self, vt_symbol: str):
        """图表创建回调.

        Args:
            vt_symbol: 品种代码
        """
        self.logger.info("图表已创建: %s", vt_symbol)

    def _on_chart_closed(self, vt_symbol: str):
        """图表关闭回调.

        Args:
            vt_symbol: 品种代码
        """
        self.logger.info("图表已关闭: %s", vt_symbol)

    def _on_symbol_changed(self, vt_symbol: str):
        """品种改变.

        Args:
            vt_symbol: 品种代码
        """
        self.logger.info("当前品种: %s", vt_symbol)
        # vnpy_chartwizard 已自动处理订阅、数据加载等
        # 这里可以添加自定义的扩展逻辑

    def refresh_data(self):
        """刷新数据."""
        # vnpy_chartwizard 实时更新，无需手动刷新
        if self.chart_wizard:
            current_chart = self.chart_wizard.get_current_chart()
            if current_chart and hasattr(current_chart, "move_to_right"):
                current_chart.move_to_right()
        self.show_info("已刷新到最新数据")

    def on_close(self):
        """关闭处理."""
        if self.chart_wizard:
            self.chart_wizard.on_close()
        self.logger.info("行情看板界面已关闭")
