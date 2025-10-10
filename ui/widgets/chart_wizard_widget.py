# -*- coding: utf-8 -*-
"""
ChartWizard适配器 - 集成vnpy_chartwizard

封装vnpy_chartwizard的ChartWidget，提供专业级图表功能。
如果vnpy_chartwizard不可用，自动回退到自研ChartWidget。
"""

import logging
from typing import Any, Dict, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ui.widgets.base_widget import BaseWidget

logger = logging.getLogger(__name__)


# 尝试导入vnpy_chartwizard
try:
    from vnpy_chartwizard.ui.widget import ChartWidget as VnpyChartWidget

    HAS_CHART_WIZARD = True
    logger.info("✅ vnpy_chartwizard可用")
except ImportError:
    HAS_CHART_WIZARD = False
    VnpyChartWidget = None
    logger.warning("⚠️ vnpy_chartwizard不可用，将使用降级方案")


class ChartWizardWidget(BaseWidget):
    """ChartWizard适配器组件.

    封装vnpy_chartwizard，提供与原ChartWidget相同的接口。
    """

    # 信号定义
    symbol_changed = Signal(str)
    period_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化ChartWizard适配器.

        Args:
            parent: 父窗口组件
        """
        super().__init__(parent, "专业图表")

        # 图表组件
        self.chart_widget: Optional[Any] = None

        # 当前状态
        self.current_symbol = ""
        self.current_period = "1d"

        # 数据管理器引用
        self.data_manager = None

    def setup_ui(self):
        """设置用户界面."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if HAS_CHART_WIZARD and VnpyChartWidget:
            # 使用vnpy_chartwizard
            try:
                self._setup_chart_wizard(layout)
                self._logger.info("✅ 使用vnpy_chartwizard图表组件")
            except Exception as e:
                self._logger.error(f"初始化vnpy_chartwizard失败: {e}", exc_info=True)
                self._setup_fallback_chart(layout)
        else:
            # 使用降级方案
            self._setup_fallback_chart(layout)

    def _setup_chart_wizard(self, layout: QVBoxLayout):
        """设置vnpy_chartwizard图表.

        Args:
            layout: 布局
        """
        # 创建vnpy_chartwizard图表组件
        # ChartWidget需要一个MainEngine实例
        try:
            from backend.core.base import get_main_engine

            main_engine = get_main_engine()

            if not main_engine:
                self._logger.warning("MainEngine不可用，使用降级方案")
                raise RuntimeError("MainEngine不可用")

            # 创建图表组件
            # vnpy_chartwizard.ChartWidget(main_engine, event_engine)
            self.chart_widget = VnpyChartWidget(main_engine, main_engine.event_engine)

            # 添加到布局
            if self.chart_widget:
                layout.addWidget(self.chart_widget)

            self._logger.info("✅ vnpy_chartwizard图表组件初始化成功")

        except Exception as e:
            self._logger.error(f"❌ 创建vnpy_chartwizard组件失败: {e}")
            raise

    def _setup_fallback_chart(self, layout: QVBoxLayout):
        """设置降级图表（使用自研ChartWidget）.

        Args:
            layout: 布局
        """
        try:
            from ui.widgets.chart_widget import ChartWidget

            self.chart_widget = ChartWidget(self)
            layout.addWidget(self.chart_widget)

            # 连接信号
            if hasattr(self.chart_widget, "symbol_changed"):
                self.chart_widget.symbol_changed.connect(self.symbol_changed)
            if hasattr(self.chart_widget, "period_changed"):
                self.chart_widget.period_changed.connect(self.period_changed)

            self._logger.info("✅ 使用降级图表组件（ChartWidget）")

        except Exception as e:
            self._logger.error(f"创建降级图表组件失败: {e}", exc_info=True)
            # 创建一个简单的占位符
            from PySide6.QtWidgets import QLabel
            from PySide6.QtCore import Qt

            placeholder = QLabel("图表组件不可用")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #888; font-size: 16px;")
            layout.addWidget(placeholder)

    def connect_signals(self):
        """连接信号槽."""
        # vnpy_chartwizard的信号连接在这里处理
        if HAS_CHART_WIZARD and self.chart_widget and hasattr(self.chart_widget, "symbol_changed"):
            try:
                # 如果vnpy_chartwizard有symbol_changed信号，连接它
                self.chart_widget.symbol_changed.connect(self._on_symbol_changed)
            except Exception as e:
                self._logger.warning(f"连接vnpy_chartwizard信号失败: {e}")

    def _on_symbol_changed(self, symbol: str):
        """品种变化回调.

        Args:
            symbol: 品种代码
        """
        self.current_symbol = symbol
        self.symbol_changed.emit(symbol)
        self._logger.info(f"图表品种切换: {symbol}")

    # ========== 公共接口 ==========

    def set_symbol(self, symbol: str):
        """设置品种.

        Args:
            symbol: 品种代码
        """
        self.current_symbol = symbol

        if HAS_CHART_WIZARD and self.chart_widget:
            # vnpy_chartwizard的设置方法
            if hasattr(self.chart_widget, "update_history"):
                try:
                    # 构建vt_symbol
                    # 假设symbol格式为 "000001" 或 "000001.SZSE"
                    if "." not in symbol:
                        # 判断是上海还是深圳
                        if symbol.startswith("6"):
                            vt_symbol = f"{symbol}.SSE"  # 上海交易所
                        else:
                            vt_symbol = f"{symbol}.SZSE"  # 深圳交易所
                    else:
                        vt_symbol = symbol

                    # 更新历史数据
                    self.chart_widget.update_history(vt_symbol)
                    self._logger.info(f"✅ 更新图表品种: {vt_symbol}")
                except Exception as e:
                    self._logger.error(f"❌ 更新图表品种失败: {e}")
        elif self.chart_widget and hasattr(self.chart_widget, "set_symbol"):
            # 降级方案
            self.chart_widget.set_symbol(symbol)

    def set_period(self, period: str):
        """设置周期.

        Args:
            period: 周期（如：1d, 1h, 5m）
        """
        self.current_period = period

        # vnpy_chartwizard通常内置周期切换，这里暂时不处理
        # 如果需要，可以通过vnpy_chartwizard的API设置

        if not HAS_CHART_WIZARD and self.chart_widget and hasattr(self.chart_widget, "set_period"):
            # 降级方案
            self.chart_widget.set_period(period)

    def refresh_data(self):
        """刷新数据."""
        if HAS_CHART_WIZARD and self.chart_widget:
            if hasattr(self.chart_widget, "update_history"):
                try:
                    # 刷新当前品种
                    if self.current_symbol:
                        vt_symbol = self.current_symbol
                        if "." not in vt_symbol:
                            vt_symbol = f"{vt_symbol}.SZSE"
                        self.chart_widget.update_history(vt_symbol)
                except Exception as e:
                    self._logger.error(f"刷新图表数据失败: {e}")
        elif self.chart_widget and hasattr(self.chart_widget, "refresh_data"):
            # 降级方案
            self.chart_widget.refresh_data()

    def add_indicator(self, indicator_type: str):
        """添加技术指标.

        Args:
            indicator_type: 指标类型
        """
        if HAS_CHART_WIZARD and self.chart_widget:
            # vnpy_chartwizard通常内置指标管理
            # 具体实现依赖于vnpy_chartwizard的API
            self._logger.info(f"添加指标: {indicator_type}")
        elif self.chart_widget and hasattr(self.chart_widget, "add_indicator"):
            # 降级方案
            self.chart_widget.add_indicator(indicator_type)

    def remove_indicator(self, indicator_type: str):
        """移除技术指标.

        Args:
            indicator_type: 指标类型
        """
        if HAS_CHART_WIZARD and self.chart_widget:
            self._logger.info(f"移除指标: {indicator_type}")
        elif self.chart_widget and hasattr(self.chart_widget, "remove_indicator"):
            # 降级方案
            self.chart_widget.remove_indicator(indicator_type)

    def clear_chart(self):
        """清空图表."""
        if HAS_CHART_WIZARD and self.chart_widget:
            if hasattr(self.chart_widget, "clear_all"):
                self.chart_widget.clear_all()
        elif self.chart_widget and hasattr(self.chart_widget, "clear_chart"):
            # 降级方案
            self.chart_widget.clear_chart()

    def export_chart(self, filepath: str):
        """导出图表.

        Args:
            filepath: 导出文件路径
        """
        try:
            if HAS_CHART_WIZARD and self.chart_widget:
                # vnpy_chartwizard导出功能
                if hasattr(self.chart_widget, "save_to_file"):
                    self.chart_widget.save_to_file(filepath)
                    self.show_info(f"图表已导出到: {filepath}")
                else:
                    self.show_warning("vnpy_chartwizard不支持导出功能")
            elif self.chart_widget and hasattr(self.chart_widget, "export_chart"):
                # 降级方案
                self.chart_widget.export_chart()
            else:
                self.show_warning("当前图表组件不支持导出功能")
        except Exception as e:
            self.show_error(f"导出图表失败: {str(e)}")
            self._logger.error(f"导出图表失败: {e}", exc_info=True)

    # ========== 数据接口 ==========

    def load_history_data(self, symbol: str, exchange: str, interval: str, start: str, end: str):
        """加载历史数据.

        Args:
            symbol: 品种代码
            exchange: 交易所
            interval: 周期
            start: 开始日期
            end: 结束日期
        """
        if HAS_CHART_WIZARD and self.chart_widget:
            try:
                vt_symbol = f"{symbol}.{exchange}"

                # vnpy_chartwizard加载历史数据
                if hasattr(self.chart_widget, "update_history"):
                    self.chart_widget.update_history(vt_symbol)

                self._logger.info(f"加载历史数据: {vt_symbol} {interval} {start}~{end}")
            except Exception as e:
                self._logger.error(f"加载历史数据失败: {e}")
                self.show_error(f"加载数据失败: {str(e)}")
        else:
            self._logger.warning("vnpy_chartwizard不可用，无法加载历史数据")

    def on_bar(self, bar: Dict[str, Any]):
        """K线数据推送.

        Args:
            bar: K线数据
        """
        if HAS_CHART_WIZARD and self.chart_widget and hasattr(self.chart_widget, "update_bar"):
            # vnpy_chartwizard实时更新
            try:
                # 转换为vnpy的BarData对象
                from vnpy.trader.object import BarData
                from vnpy.trader.constant import Exchange, Interval
                from datetime import datetime

                bar_data = BarData(
                    symbol=bar.get("symbol", ""),
                    exchange=Exchange(bar.get("exchange", "SZSE")),
                    datetime=bar.get("datetime", datetime.now()),
                    interval=Interval(bar.get("interval", "1m")),
                    volume=bar.get("volume", 0.0),
                    open_price=bar.get("open_price", 0.0),
                    high_price=bar.get("high_price", 0.0),
                    low_price=bar.get("low_price", 0.0),
                    close_price=bar.get("close_price", 0.0),
                    gateway_name=bar.get("gateway_name", ""),
                )

                self.chart_widget.update_bar(bar_data)
            except Exception as e:
                self._logger.error(f"更新K线失败: {e}")

    def on_tick(self, tick: Dict[str, Any]):
        """Tick数据推送.

        Args:
            tick: Tick数据
        """
        if HAS_CHART_WIZARD and self.chart_widget and hasattr(self.chart_widget, "update_tick"):
            # vnpy_chartwizard实时更新
            try:
                # 转换为vnpy的TickData对象
                from vnpy.trader.object import TickData
                from vnpy.trader.constant import Exchange
                from datetime import datetime

                tick_data = TickData(
                    symbol=tick.get("symbol", ""),
                    exchange=Exchange(tick.get("exchange", "SZSE")),
                    datetime=tick.get("datetime", datetime.now()),
                    name=tick.get("name", ""),
                    volume=tick.get("volume", 0.0),
                    last_price=tick.get("last_price", 0.0),
                    bid_price_1=tick.get("bid_price_1", 0.0),
                    ask_price_1=tick.get("ask_price_1", 0.0),
                    bid_volume_1=tick.get("bid_volume_1", 0.0),
                    ask_volume_1=tick.get("ask_volume_1", 0.0),
                    gateway_name=tick.get("gateway_name", ""),
                )

                self.chart_widget.update_tick(tick_data)
            except Exception as e:
                self._logger.error(f"更新Tick失败: {e}")

    def on_close(self):
        """关闭处理."""
        # 清理资源
        if self.chart_widget:
            try:
                if hasattr(self.chart_widget, "close"):
                    self.chart_widget.close()
            except Exception as e:
                self._logger.error(f"关闭图表组件失败: {e}")

        super().on_close()


# 导出函数，用于自动选择合适的图表组件
def create_chart_widget(parent: Optional[QWidget] = None) -> ChartWizardWidget:
    """创建图表组件（自动选择最佳实现）.

    Args:
        parent: 父窗口

    Returns:
        图表组件实例
    """
    return ChartWizardWidget(parent)
