# -*- coding: utf-8 -*-
"""
ChartWizard适配器 - 集成vnpy_chartwizard

封装vnpy_chartwizard的ChartWidget，提供专业级图表功能。
如果vnpy_chartwizard不可用，自动回退到自研ChartWidget。
"""

import logging
from typing import Any, Dict, List, Optional

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
        # 🔧 修复：先初始化所有属性，再调用super().__init__()
        # 因为BaseWidget.__init__会调用setup_ui()，需要这些属性已经存在

        # 🔧 线程安全修复：延迟获取引擎，避免在初始化时访问可能未就绪的资源
        # 引擎将在实际需要时通过_get_engines()方法获取
        self.main_engine: Optional[Any] = None
        self.event_engine: Optional[Any] = None
        self._engines_initialized = False

        # 图表组件
        self.chart_widget: Optional[Any] = None

        # 当前状态
        self.current_symbol = ""
        self.current_period = "1d"

        # 数据管理器引用
        self.data_manager = None

        # 最后调用父类初始化（会触发setup_ui()）
        super().__init__(parent, "专业图表")

    def _get_engines(self) -> bool:
        """延迟获取MainEngine和EventEngine.

        Returns:
            bool: 是否成功获取引擎
        """
        if self._engines_initialized:
            return True

        try:
            from backend.core.base import get_main_engine, get_event_engine

            self.main_engine = get_main_engine()
            self.event_engine = get_event_engine()

            if self.main_engine and self.event_engine:
                self._engines_initialized = True
                self._logger.info("✅ 成功获取MainEngine和EventEngine")
                return True
            else:
                self._logger.warning("⚠️ MainEngine或EventEngine尚未初始化")
                return False
        except Exception as e:
            self._logger.error(f"获取引擎失败: {e}", exc_info=True)
            return False

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
        # vnpy_chartwizard.ChartWidget需要MainEngine和EventEngine参数
        try:
            # 🔧 线程安全修复：延迟获取引擎
            if not self._get_engines():
                self._logger.warning("⚠️ MainEngine或EventEngine不可用，使用降级方案")
                raise RuntimeError("MainEngine或EventEngine不可用")

            # 尝试使用vnpy_chartwizard（需要MainEngine和EventEngine）
            # 注意：vnpy_chartwizard.ChartWidget 实际上是ChartWizardWidget，不是单独的图表组件
            # 我们这里直接使用vnpy.chart.ChartWidget
            try:
                from vnpy.chart import ChartWidget, CandleItem, VolumeItem

                # 创建vnpy.chart图表组件（不需要MainEngine）
                self.chart_widget = ChartWidget()

                # 添加K线图和成交量图
                self.chart_widget.add_plot("candle", hide_x_axis=True)
                self.chart_widget.add_plot("volume", maximum_height=200)
                self.chart_widget.add_item(CandleItem, "candle", "candle")
                self.chart_widget.add_item(VolumeItem, "volume", "volume")
                self.chart_widget.add_cursor()

                # 添加到布局
                layout.addWidget(self.chart_widget)

                self._logger.info("✅ vnpy.chart图表组件初始化成功")

            except ImportError as e:
                self._logger.error(f"❌ 无法导入vnpy.chart: {e}")
                raise

        except Exception as e:
            self._logger.error(f"❌ 创建vnpy图表组件失败: {e}, 使用降级方案")
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

    def _convert_to_bar_data(
        self, data_list: List[Dict[str, Any]], symbol: str, exchange: str
    ) -> List[Any]:
        """将数据转换为vnpy的BarData格式.

        Args:
            data_list: 数据字典列表
            symbol: 品种代码
            exchange: 交易所代码

        Returns:
            List[BarData]: BarData对象列表
        """
        try:
            from vnpy.trader.object import BarData
            from vnpy.trader.constant import Exchange, Interval
            from datetime import datetime

            bars = []

            # 转换交易所字符串为Exchange枚举
            try:
                exchange_enum = Exchange(exchange)
            except ValueError:
                self._logger.warning(f"未知的交易所: {exchange}，使用SSE")
                exchange_enum = Exchange.SSE

            # 转换周期字符串为Interval枚举
            interval_map = {
                "1d": Interval.DAILY,
                "1w": Interval.WEEKLY,
                "1h": Interval.HOUR,
                "1m": Interval.MINUTE,
                "5m": Interval.MINUTE,
                "15m": Interval.MINUTE,
                "30m": Interval.MINUTE,
            }
            interval_enum = interval_map.get(
                self.current_period if hasattr(self, "current_period") else "1d", Interval.DAILY
            )

            for item in data_list:
                try:
                    # 处理日期时间
                    if "datetime" in item:
                        dt_str = item["datetime"]
                    elif "date" in item:
                        dt_str = item["date"]
                    else:
                        continue

                    # 转换为datetime对象
                    if isinstance(dt_str, str):
                        # 尝试多种日期格式
                        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"]:
                            try:
                                dt = datetime.strptime(dt_str, fmt)
                                break
                            except ValueError:
                                continue
                        else:
                            self._logger.warning(f"无法解析日期: {dt_str}")
                            continue
                    elif isinstance(dt_str, datetime):
                        dt = dt_str
                    else:
                        continue

                    # 创建BarData对象
                    bar = BarData(
                        gateway_name="DB",  # 数据库数据
                        symbol=symbol,
                        exchange=exchange_enum,
                        datetime=dt,
                        interval=interval_enum,
                        volume=float(item.get("volume", 0)),
                        turnover=float(item.get("turnover", 0)),
                        open_interest=float(item.get("open_interest", 0)),
                        open_price=float(item.get("open", 0)),
                        high_price=float(item.get("high", 0)),
                        low_price=float(item.get("low", 0)),
                        close_price=float(item.get("close", 0)),
                    )
                    bars.append(bar)

                except Exception as e:
                    self._logger.warning(f"转换单条数据失败: {e}, 数据: {item}")
                    continue

            return bars

        except Exception as e:
            self._logger.error(f"数据转换失败: {e}", exc_info=True)
            return []

    # ========== 公共接口 ==========

    def set_symbol(self, symbol: str):
        """设置品种.

        Args:
            symbol: 品种代码
        """
        self.current_symbol = symbol

        if HAS_CHART_WIZARD and self.chart_widget:
            # vnpy_chartwizard需要BarData列表
            # 从数据中心获取历史K线数据并转换
            try:
                from backend.core.base import get_service_manager
                from datetime import datetime, timedelta

                service_mgr = get_service_manager()
                if not service_mgr:
                    self._logger.warning("服务管理器不可用，无法加载图表数据")
                    return

                data_service = service_mgr.get_service("data_center_service")
                if not data_service:
                    self._logger.warning("数据服务不可用，无法加载图表数据")
                    return

                # 构建vt_symbol（去掉交易所后缀用于查询）
                query_symbol = symbol.split(".")[0] if "." in symbol else symbol

                # 确定交易所
                if "." in symbol:
                    exchange_str = symbol.split(".")[1]
                elif symbol.startswith("6"):
                    exchange_str = "SSE"
                else:
                    exchange_str = "SZSE"

                # 计算查询时间范围（最近200个交易日）
                end_date = datetime.now()
                start_date = end_date - timedelta(days=300)  # 多取一些天数确保有200个交易日

                # 查询本地数据
                result = data_service.query_local_data(
                    symbol=query_symbol,
                    start_date=start_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d"),
                    interval=self.current_period if hasattr(self, "current_period") else "1d",
                )

                if result.get("success") and result.get("data"):
                    # 转换为BarData列表
                    bars = self._convert_to_bar_data(result["data"], query_symbol, exchange_str)

                    if bars:
                        # 更新图表
                        if hasattr(self.chart_widget, "update_history"):
                            self.chart_widget.update_history(bars)
                            self._logger.info(f"✅ 成功加载 {len(bars)} 条K线数据: {symbol}")
                        else:
                            self._logger.warning("图表组件不支持update_history方法")
                    else:
                        self._logger.warning(f"数据转换失败: {symbol}")
                else:
                    self._logger.warning(f"无K线数据: {symbol}, {result.get('message', '')}")

            except Exception as e:
                self._logger.error(f"❌ 更新图表品种失败: {e}", exc_info=True)
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

    def set_coordinate_type(self, coord_type: str):
        """设置坐标类型.

        Args:
            coord_type: 坐标类型（"linear" 或 "log"）
        """
        try:
            is_log = coord_type == "log"
            self._logger.info(f"设置坐标类型: {coord_type}")

            if HAS_CHART_WIZARD and self.chart_widget:
                # 使用vnpy.chart的图表组件
                try:
                    # vnpy.chart的ChartWidget支持设置Y轴为对数坐标
                    if hasattr(self.chart_widget, "_plots"):
                        # 获取所有plot
                        for plot_name, plot_item in self.chart_widget._plots.items():
                            if plot_item and hasattr(plot_item, "setLogMode"):
                                # 设置Y轴为对数模式
                                plot_item.setLogMode(x=False, y=is_log)
                                self._logger.info(
                                    f"✅ 图表 {plot_name} 已切换为{'对数' if is_log else '线性'}坐标"
                                )
                    elif hasattr(self.chart_widget, "setLogMode"):
                        # 直接在图表widget上设置
                        self.chart_widget.setLogMode(x=False, y=is_log)
                        self._logger.info(f"✅ 图表已切换为{'对数' if is_log else '线性'}坐标")
                    else:
                        self._logger.warning("图表组件不支持setLogMode方法")

                except Exception as e:
                    self._logger.error(f"设置vnpy图表坐标类型失败: {e}", exc_info=True)

            elif self.chart_widget and hasattr(self.chart_widget, "set_coordinate_type"):
                # 降级方案：使用自定义ChartWidget
                self.chart_widget.set_coordinate_type(coord_type)
                self._logger.info(f"✅ 降级图表已切换为{coord_type}坐标")
            else:
                self._logger.warning("图表组件不支持坐标类型切换")

        except Exception as e:
            self._logger.error(f"设置坐标类型失败: {e}", exc_info=True)

    def refresh_data(self):
        """刷新数据."""
        if HAS_CHART_WIZARD and self.chart_widget:
            # 重新加载当前品种的数据
            if self.current_symbol:
                self.set_symbol(self.current_symbol)
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
                from backend.core.base import get_service_manager

                service_mgr = get_service_manager()
                if not service_mgr:
                    self.show_error("服务管理器不可用")
                    return

                data_service = service_mgr.get_service("data_center_service")
                if not data_service:
                    self.show_error("数据服务不可用")
                    return

                # 查询指定时间范围的数据
                result = data_service.query_local_data(
                    symbol=symbol, start_date=start, end_date=end, interval=interval
                )

                if result.get("success") and result.get("data"):
                    # 转换为BarData列表
                    bars = self._convert_to_bar_data(result["data"], symbol, exchange)

                    if bars:
                        # 更新图表
                        self.chart_widget.update_history(bars)
                        self._logger.info(
                            f"✅ 加载历史数据成功: {symbol}.{exchange} {interval} {start}~{end}, {len(bars)}条"
                        )
                    else:
                        self.show_warning("数据转换失败")
                else:
                    self.show_warning(f"无历史数据: {result.get('message', '')}")

            except Exception as e:
                self._logger.error(f"加载历史数据失败: {e}", exc_info=True)
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
