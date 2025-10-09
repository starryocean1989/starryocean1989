# -*- coding: utf-8 -*-
"""
专业图表组件 - 基于pyqtgraph的金融图表.

提供K线图、分时图、技术指标等专业图表功能
"""
# pylint: disable=no-name-in-module

from typing import Any, Dict, List

# Qt imports first
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

# Third-party imports
import numpy as np

from ui.widgets.base_widget import BaseWidget

# Backend imports - 检查vnpy可用性
try:
    VNPY_AVAILABLE = True
except ImportError:
    VNPY_AVAILABLE = False


# 全局VnPy适配器实例
vnpy_adapter: "VnPyAdapter"


class VnPyAdapter:
    """VnPy数据适配器 - 提供图表数据获取接口."""

    def __init__(self):
        """初始化VnPy适配器."""
        self.main_engine = None
        self._initialize_engine()

    def _initialize_engine(self):
        """初始化VnPy引擎."""
        try:
            from vnpy.trader.engine import MainEngine
            from vnpy.event import EventEngine

            event_engine = EventEngine()
            self.main_engine = MainEngine(event_engine)

        except ImportError as e:
            self.main_engine = None
            print(f"VnPy引擎初始化失败: {e}")

    def get_kline_data(self, symbol: str, period: str, limit: int = 200) -> List[Dict[str, Any]]:
        """获取K线数据.

        Args:
            symbol: 品种代码
            period: 时间周期
            limit: 数据数量限制

        Returns:
            K线数据列表
        """
        if not self.main_engine:
            # 返回模拟数据用于测试
            return self._get_mock_kline_data(symbol, period, limit)

        try:
            # 这里应该实现从VnPy获取真实数据的逻辑
            # 暂时返回模拟数据
            return self._get_mock_kline_data(symbol, period, limit)

        except Exception as e:
            print(f"获取K线数据失败: {e}")
            return self._get_mock_kline_data(symbol, period, limit)

    def _get_mock_kline_data(self, symbol: str, period: str, limit: int) -> List[Dict[str, Any]]:
        """获取模拟K线数据用于测试.

        Args:
            symbol: 品种代码（暂时未使用）
            period: 时间周期
            limit: 数据数量限制
        """
        import random
        from datetime import datetime, timedelta

        mock_data = []
        base_price = 100.0

        # 根据周期生成不同时间间隔的数据
        if period == "日K":
            delta = timedelta(days=1)
            count = min(limit, 200)
        elif period in ["5分钟", "15分钟", "30分钟", "1小时"]:
            delta = timedelta(minutes=5)
            count = min(limit, 100)
        else:
            delta = timedelta(days=1)
            count = min(limit, 200)

        current_time = datetime.now()

        for _ in range(count):
            # 生成随机价格波动
            price_change = random.uniform(-0.05, 0.05) * base_price
            open_price = base_price + price_change * random.uniform(0.5, 1.5)
            close_price = open_price + price_change * random.uniform(0.8, 1.2)
            high_price = max(open_price, close_price) + abs(price_change) * random.uniform(0.1, 0.3)
            low_price = min(open_price, close_price) - abs(price_change) * random.uniform(0.1, 0.3)
            volume = random.randint(10000, 1000000)

            mock_data.append(
                {
                    "datetime": current_time,
                    "open": round(open_price, 2),
                    "high": round(high_price, 2),
                    "low": round(low_price, 2),
                    "close": round(close_price, 2),
                    "volume": volume,
                }
            )

            current_time -= delta
            base_price = close_price

        return mock_data


# 实例化全局VnPy适配器
vnpy_adapter = VnPyAdapter()

try:
    import pyqtgraph as pg

    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    pg = None

try:
    import talib  # type: ignore

    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    talib = None  # type: ignore


class ChartDataWorker(QThread):
    """图表数据处理工作线程."""

    data_ready = Signal(dict)

    def __init__(self, symbol: str, period: str, data_api=None):
        """初始化图表数据工作线程.

        Args:
            symbol: 交易品种代码
            period: 图表周期
            data_api: 数据接口实例
        """
        super().__init__()
        self.symbol = symbol
        self.period = period
        self.data_api = data_api
        self.running = False

    def run(self):
        """运行数据获取任务."""
        self.running = True

        try:
            # 从VnPy获取历史数据
            if not self.data_api or not hasattr(self.data_api, "get_kline_data"):
                raise RuntimeError("VnPy数据接口不可用")

            kline_data = self.data_api.get_kline_data(self.symbol, self.period, limit=200)

            if not kline_data:
                raise ValueError(f"未找到品种 {self.symbol} 的K线数据")

            # 计算技术指标
            indicators = self._calculate_indicators(kline_data)

            result = {
                "symbol": self.symbol,
                "period": self.period,
                "kline_data": kline_data,
                "indicators": indicators,
            }

            self.data_ready.emit(result)

        except Exception as e:
            self.data_ready.emit({"error": str(e)})
        finally:
            self.running = False

    def _calculate_indicators(self, kline_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算技术指标."""
        if not TALIB_AVAILABLE or not kline_data:
            return {}

        try:
            # 提取价格数据
            closes = np.array([item["close"] for item in kline_data])
            highs = np.array([item["high"] for item in kline_data])
            lows = np.array([item["low"] for item in kline_data])

            # 计算技术指标
            if hasattr(talib, "MACD"):
                macd_result = talib.MACD(  # type: ignore
                    closes, fastperiod=12, slowperiod=26, signalperiod=9
                )
            else:
                macd_result = None

            if hasattr(talib, "BBANDS"):
                boll_result = talib.BBANDS(  # type: ignore
                    closes,
                    timeperiod=20,
                    nbdevup=2,
                    nbdevdn=2,
                    matype=0,  # type: ignore  # 0 = SMA (Simple Moving Average)
                )
            else:
                boll_result = None

            indicators = {}

            # MA指标
            if hasattr(talib, "MA"):
                indicators.update(
                    {
                        "ma5": talib.MA(closes, timeperiod=5),  # type: ignore
                        "ma10": talib.MA(closes, timeperiod=10),  # type: ignore
                        "ma20": talib.MA(closes, timeperiod=20),  # type: ignore
                        "ma60": talib.MA(closes, timeperiod=60),  # type: ignore
                    }
                )

            # MACD指标
            if macd_result:
                indicators.update(
                    {
                        "macd": macd_result[0],
                        "macdsignal": macd_result[1],
                        "macdhist": macd_result[2],
                    }
                )

            # RSI指标
            if hasattr(talib, "RSI"):
                indicators["rsi"] = talib.RSI(closes, timeperiod=14)  # type: ignore

            # 布林带指标
            if boll_result:
                indicators.update(
                    {
                        "boll_upper": boll_result[0],
                        "boll_middle": boll_result[1],
                        "boll_lower": boll_result[2],
                    }
                )

            # KDJ指标需要单独计算
            if hasattr(talib, "STOCH"):
                slowk, slowd = talib.STOCH(  # type: ignore
                    highs, lows, closes, fastk_period=9, slowk_period=3, slowd_period=3
                )
            else:
                slowk, slowd = None, None
            # KDJ指标
            if slowk is not None and slowd is not None:
                indicators.update({"kdj_k": slowk, "kdj_d": slowd, "kdj_j": 3 * slowk - 2 * slowd})

            return indicators

        except (ValueError, TypeError, IndexError) as e:
            return {"error": f"指标计算失败: {str(e)}"}


class ChartWidget(BaseWidget):
    """专业图表组件."""

    # 信号定义
    symbol_changed = Signal(str)
    period_changed = Signal(str)
    indicator_toggled = Signal(str, bool)

    def __init__(self, parent=None):
        """初始化专业图表组件.

        Args:
            parent: 父窗口组件
        """
        # 颜色配置 - 必须在super().__init__()之前初始化
        self.colors = {
            "background": QColor(26, 26, 26),
            "foreground": QColor(255, 255, 255),
            "grid": QColor(64, 64, 64),
            "up": QColor(255, 100, 100),  # 红色 - 上涨
            "down": QColor(100, 255, 100),  # 绿色 - 下跌
            "ma5": QColor(255, 255, 0),  # 黄色
            "ma10": QColor(0, 255, 255),  # 青色
            "ma20": QColor(255, 0, 255),  # 品红
            "ma60": QColor(128, 128, 128),  # 灰色
        }

        # 图表组件 - 必须在super().__init__()之前初始化
        self.indicator_charts = {}

        super().__init__(parent, "专业图表")

        # 初始化所有属性
        self.current_symbol = "000001"
        self.current_period = "日K"
        self.chart_data = []
        self.indicators_data = {}

        # 图表组件
        self.main_chart = None
        self.volume_chart = None
        self.main_chart_widget = None
        self.volume_chart_widget = None
        self.candlestick = None
        self.volume_bars = None
        self.symbol_combo = None
        self.period_combo = None

        # 数据工作线程
        self.data_worker = None

    def setup_ui(self):
        """设置用户界面."""
        if not PYQTGRAPH_AVAILABLE:
            raise ImportError("pyqtgraph未安装，无法创建图表组件。\n请安装：pip install pyqtgraph")

        main_layout = QVBoxLayout(self)

        # 创建图表布局
        chart_layout = QVBoxLayout()

        # 主图区域
        self._create_main_chart()
        if self.main_chart_widget:
            chart_layout.addWidget(self.main_chart_widget)

        # 成交量图表
        self._create_volume_chart()
        if self.volume_chart_widget:
            chart_layout.addWidget(self.volume_chart_widget)

        # 技术指标图表
        self._create_indicator_charts()
        for chart in self.indicator_charts.values():
            chart_layout.addWidget(chart)

        main_layout.addLayout(chart_layout, 1)

        # 控制面板
        control_layout = self._create_control_panel()
        main_layout.addLayout(control_layout)

    def _create_main_chart(self):
        """创建主图表（K线图）."""
        if not PYQTGRAPH_AVAILABLE:
            return

        # 创建图形窗口
        self.main_chart_widget = pg.GraphicsLayoutWidget()  # type: ignore
        if self.main_chart_widget:
            self.main_chart_widget.setBackground(self.colors["background"])

        # 创建主图表
        self.main_chart = self.main_chart_widget.addPlot(title="K线图")  # type: ignore
        self.main_chart.showGrid(x=True, y=True)
        self.main_chart.getAxis("bottom").setPen(self.colors["foreground"])
        self.main_chart.getAxis("left").setPen(self.colors["foreground"])

        # 设置坐标轴样式
        self.main_chart.getAxis("bottom").setTextPen(self.colors["foreground"])
        self.main_chart.getAxis("left").setTextPen(self.colors["foreground"])

        # 隐藏自动缩放按钮
        self.main_chart.hideButtons()

        # 创建蜡烛图项目
        try:
            # 使用PlotDataItem来绘制蜡烛图
            self.candlestick = pg.PlotDataItem()  # type: ignore
            self.main_chart.addItem(self.candlestick)
        except (AttributeError, ImportError):
            # 如果创建失败，使用简单的PlotDataItem
            self.candlestick = pg.PlotDataItem()  # type: ignore
            self.main_chart.addItem(self.candlestick)

    def _create_volume_chart(self):
        """创建成交量图表."""
        if not PYQTGRAPH_AVAILABLE:
            return

        self.volume_chart_widget = pg.GraphicsLayoutWidget()  # type: ignore
        if self.volume_chart_widget:
            self.volume_chart_widget.setBackground(self.colors["background"])

        self.volume_chart = self.volume_chart_widget.addPlot(title="成交量")  # type: ignore
        self.volume_chart.showGrid(x=True, y=True)
        self.volume_chart.getAxis("bottom").setPen(self.colors["foreground"])
        self.volume_chart.getAxis("left").setPen(self.colors["foreground"])
        self.volume_chart.getAxis("bottom").setTextPen(self.colors["foreground"])
        self.volume_chart.getAxis("left").setTextPen(self.colors["foreground"])
        self.volume_chart.hideButtons()

        # 创建柱状图项目
        self.volume_bars = pg.BarGraphItem(  # type: ignore
            x=[], height=[], width=0.8, brush=self.colors["up"]
        )
        self.volume_chart.addItem(self.volume_bars)

    def _create_indicator_charts(self):
        """创建技术指标图表."""
        if not PYQTGRAPH_AVAILABLE:
            return

        # MACD图表
        macd_win = pg.GraphicsLayoutWidget()  # type: ignore
        if macd_win:
            macd_win.setBackground(self.colors["background"])
        macd_plot = macd_win.addPlot(title="MACD")  # type: ignore
        macd_plot.showGrid(x=True, y=True)
        macd_plot.getAxis("bottom").setPen(self.colors["foreground"])
        macd_plot.getAxis("left").setPen(self.colors["foreground"])
        macd_plot.getAxis("bottom").setTextPen(self.colors["foreground"])
        macd_plot.getAxis("left").setTextPen(self.colors["foreground"])
        macd_plot.hideButtons()
        self.indicator_charts["macd"] = macd_win

        # RSI图表
        rsi_win = pg.GraphicsLayoutWidget()  # type: ignore
        if rsi_win:
            rsi_win.setBackground(self.colors["background"])
        rsi_plot = rsi_win.addPlot(title="RSI")  # type: ignore
        rsi_plot.showGrid(x=True, y=True)
        rsi_plot.getAxis("bottom").setPen(self.colors["foreground"])
        rsi_plot.getAxis("left").setPen(self.colors["foreground"])
        rsi_plot.getAxis("bottom").setTextPen(self.colors["foreground"])
        rsi_plot.getAxis("left").setTextPen(self.colors["foreground"])
        rsi_plot.hideButtons()
        self.indicator_charts["rsi"] = rsi_win

    def _create_control_panel(self):
        """创建控制面板."""
        layout = QHBoxLayout()

        # 品种选择
        symbol_layout = QHBoxLayout()
        symbol_layout.addWidget(QLabel("品种:"))
        self.symbol_combo = QComboBox()
        # 从后端服务加载真实品种列表
        self._load_symbols_from_backend()
        self.symbol_combo.currentTextChanged.connect(self._on_symbol_changed)
        symbol_layout.addWidget(self.symbol_combo)
        layout.addLayout(symbol_layout)

        # 周期选择
        period_layout = QHBoxLayout()
        period_layout.addWidget(QLabel("周期:"))
        self.period_combo = QComboBox()
        self.period_combo.addItems(["日K", "周K", "月K", "5分钟", "15分钟", "30分钟", "1小时"])
        self.period_combo.currentTextChanged.connect(self._on_period_changed)
        period_layout.addWidget(self.period_combo)
        layout.addLayout(period_layout)

        layout.addStretch()

        # 操作按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_data)
        layout.addWidget(refresh_btn)

        return layout

    def connect_signals(self):
        """连接信号槽."""
        if PYQTGRAPH_AVAILABLE and self.main_chart and self.main_chart.scene():
            # 连接鼠标交互信号
            self.main_chart.scene().sigMouseClicked.connect(self._on_chart_clicked)

    def _on_symbol_changed(self, text: str):
        """品种选择改变."""
        symbol_code = text.split(" - ")[0] if text else "000001"
        if symbol_code != self.current_symbol:
            self.current_symbol = symbol_code
            self.symbol_changed.emit(symbol_code)
            self._logger.info("切换品种: %s", text)
            self._load_chart_data()

    def _on_period_changed(self, text: str):
        """周期选择改变."""
        if text != self.current_period:
            self.current_period = text
            self.period_changed.emit(text)
            self._logger.info("切换周期: %s", text)
            self._load_chart_data()

    def _on_chart_clicked(self, event):
        """图表点击事件."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.main_chart
            and hasattr(self.main_chart, "vb")
        ):
            pos = self.main_chart.vb.mapSceneToView(event.scenePos())  # type: ignore
            self._logger.info("图表点击位置: x=%s, y=%s", pos.x(), pos.y())

    def _load_chart_data(self):
        """加载图表数据."""
        if not PYQTGRAPH_AVAILABLE:
            return

        # 停止当前工作线程
        if self.data_worker and self.data_worker.isRunning():
            self.data_worker.running = False
            self.data_worker.wait()

        # 创建新的数据工作线程
        if not vnpy_adapter:
            self.show_error("VnPy适配器不可用")
            return

        self.data_worker = ChartDataWorker(
            symbol=self.current_symbol, period=self.current_period, data_api=vnpy_adapter
        )

        self.data_worker.data_ready.connect(self._on_data_ready)
        self.data_worker.start()

        # 不使用弹窗，使用日志记录
        self.logger.info("正在加载图表数据...")

    def _on_data_ready(self, result: Dict[str, Any]):
        """数据准备完成回调."""
        if "error" in result:
            self.show_error(f"数据加载失败: {result['error']}")
            return

        try:
            self.chart_data = result["kline_data"]
            self.indicators_data = result.get("indicators", {})

            self._update_chart_display()
            # 不使用弹窗，使用日志记录
            self.logger.info("图表数据加载完成")

        except (ValueError, TypeError, AttributeError) as e:
            self.show_error(f"图表更新失败: {str(e)}")

    def _update_chart_display(self):
        """更新图表显示."""
        if not PYQTGRAPH_AVAILABLE or not self.chart_data:
            return

        try:
            # 提取数据
            timestamps = [item["datetime"].timestamp() for item in self.chart_data]
            opens = [item["open"] for item in self.chart_data]
            closes = [item["close"] for item in self.chart_data]
            highs = [item["high"] for item in self.chart_data]
            lows = [item["low"] for item in self.chart_data]
            volumes = [item["volume"] for item in self.chart_data]

            # 更新K线图
            if self.candlestick:
                self.candlestick.setData(timestamps, opens, closes, highs, lows)

            # 更新成交量图表
            if self.volume_bars:
                self.volume_bars.setOpts(x=timestamps, height=volumes)

            # 更新技术指标
            self._update_indicators()

            # 调整坐标轴范围
            if self.main_chart:
                self.main_chart.setXRange(min(timestamps), max(timestamps))
            if self.volume_chart:
                self.volume_chart.setXRange(min(timestamps), max(timestamps))

            # 更新指标图表的X轴范围
            for chart in self.indicator_charts.values():
                if chart:
                    chart.setXRange(min(timestamps), max(timestamps))

        except (ValueError, TypeError, AttributeError) as e:
            self._logger.error("图表显示更新失败: %s", e)

    def _update_indicators(self):
        """更新技术指标显示."""
        if not self.indicators_data:
            return

        try:
            timestamps = [item["datetime"].timestamp() for item in self.chart_data]

            # 更新MACD指标
            macd_data = self.indicators_data.get("macd")
            if macd_data is not None:
                try:
                    # 清除旧的MACD线条
                    self.indicator_charts["macd"].clear()

                    # 绘制MACD线条
                    macd_values = macd_data
                    macdsignal_values = self.indicators_data["macdsignal"]
                    # 使用plot方法替代addItem来避免geometryChanged问题
                    if hasattr(pg, "mkPen"):
                        self.indicator_charts["macd"].plot(
                            x=timestamps[-len(macd_values) :],
                            y=macd_values,
                            pen=(
                                pg.mkPen(color="blue", width=1)
                                if pg and hasattr(pg, "mkPen")
                                else None
                            ),
                        )

                    # Signal线（橙色）
                    if hasattr(pg, "mkPen"):
                        self.indicator_charts["macd"].plot(
                            x=timestamps[-len(macdsignal_values) :],
                            y=macdsignal_values,
                            pen=(
                                pg.mkPen(color="orange", width=1)
                                if pg and hasattr(pg, "mkPen")
                                else None
                            ),
                        )
                except (ValueError, TypeError, AttributeError) as macd_error:
                    self._logger.warning("MACD指标更新失败: %s", macd_error)
                    # 使用简单的plot方法作为备用
                    if macd_data is not None:
                        self.indicator_charts["macd"].clear()
                        if hasattr(pg, "mkPen"):
                            self.indicator_charts["macd"].plot(
                                x=timestamps[-len(macd_data) :],
                                y=macd_data,
                                pen=(
                                    pg.mkPen(color="blue", width=1)
                                    if pg and hasattr(pg, "mkPen")
                                    else None
                                ),
                            )

            # 更新RSI指标
            rsi_data = self.indicators_data.get("rsi")
            if rsi_data is not None:
                try:
                    self.indicator_charts["rsi"].clear()

                    rsi_values = rsi_data
                    # 使用plot方法替代addItem来避免geometryChanged问题
                    if hasattr(pg, "mkPen"):
                        self.indicator_charts["rsi"].plot(
                            x=timestamps[-len(rsi_values) :],
                            y=rsi_values,
                            pen=(
                                pg.mkPen(color="yellow", width=1)
                                if pg and hasattr(pg, "mkPen")
                                else None
                            ),
                        )

                    # 添加超买超卖线
                    if hasattr(pg, "mkPen"):
                        self.indicator_charts["rsi"].addLine(
                            y=70,
                            pen=(
                                pg.mkPen(color="red", style=Qt.PenStyle.DashLine)
                                if pg and hasattr(pg, "mkPen")
                                else None
                            ),
                        )
                        self.indicator_charts["rsi"].addLine(
                            y=30,
                            pen=(
                                pg.mkPen(color="green", style=Qt.PenStyle.DashLine)
                                if pg and hasattr(pg, "mkPen")
                                else None
                            ),
                        )
                except (ValueError, TypeError, AttributeError) as rsi_error:
                    self._logger.warning("RSI指标更新失败: %s", rsi_error)
                    # 使用简单的plot方法作为备用
                    if rsi_data is not None:
                        self.indicator_charts["rsi"].clear()
                        if hasattr(pg, "mkPen"):
                            self.indicator_charts["rsi"].plot(
                                x=timestamps[-len(rsi_data) :],
                                y=rsi_data,
                                pen=(
                                    pg.mkPen(color="yellow", width=1)
                                    if pg and hasattr(pg, "mkPen")
                                    else None
                                ),
                            )

        except (ValueError, TypeError, AttributeError) as e:
            self._logger.error("指标更新失败: %s", e)

    def refresh_data(self):
        """刷新数据."""
        self._load_chart_data()

    def set_symbol(self, symbol: str):
        """设置品种."""
        if symbol != self.current_symbol:
            self.current_symbol = symbol
            # 找到对应的显示文本
            if self.symbol_combo:
                for idx in range(self.symbol_combo.count()):
                    text = self.symbol_combo.itemText(idx)
                    if text.startswith(symbol):
                        self.symbol_combo.setCurrentIndex(idx)
                        break

    def set_period(self, period: str):
        """设置周期."""
        if period != self.current_period:
            self.current_period = period
            if self.period_combo:
                index = self.period_combo.findText(period)
                if index >= 0:
                    self.period_combo.setCurrentIndex(index)

    def add_indicator(self, indicator_type: str) -> None:
        """添加技术指标.

        Args:
            indicator_type: 技术指标类型
        """
        self._logger.info("添加技术指标: %s", indicator_type)
        # 这里可以实现动态添加指标的功能

    def remove_indicator(self, indicator_type: str):
        """移除技术指标."""
        self._logger.info("移除技术指标: %s", indicator_type)
        # 这里可以实现动态移除指标的功能

    def set_chart_style(self, style: str):
        """设置图表样式."""
        self._logger.info("设置图表样式: %s", style)
        # 这里可以实现不同的图表样式

    def _load_symbols_from_backend(self):
        """从后端服务加载品种列表."""
        try:
            from backend.core.base import get_service_manager
            import asyncio

            service_manager = get_service_manager()
            symbol_service = service_manager.get_service("symbol_service")

            if symbol_service:
                # 获取事件循环
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # 异步获取品种列表
                symbols = loop.run_until_complete(symbol_service.get_all_symbols())

                if symbols and self.symbol_combo:
                    for symbol in symbols:
                        display_name = f"{symbol['code']} - {symbol['name']}"
                        self.symbol_combo.addItem(display_name)
                    self._logger.info("已加载 %d 个品种", len(symbols))
                else:
                    # 使用默认品种
                    self._load_default_chart_symbols()
            else:
                # 使用默认品种
                self._load_default_chart_symbols()

        except Exception as e:
            self._logger.warning("加载品种列表失败: %s", e)
            # 使用默认品种
            self._load_default_chart_symbols()

    def _load_default_chart_symbols(self):
        """加载默认品种列表."""
        if not self.symbol_combo:
            return

        default_symbols = [
            {"code": "000001", "name": "平安银行"},
            {"code": "000002", "name": "万科A"},
            {"code": "600000", "name": "浦发银行"},
            {"code": "600036", "name": "招商银行"},
        ]
        for symbol in default_symbols:
            display_name = f"{symbol['code']} - {symbol['name']}"
            self.symbol_combo.addItem(display_name)
        self._logger.info("已加载 %d 个默认品种", len(default_symbols))

    def export_chart(self, format_type: str = "png"):
        """导出图表."""
        try:
            if PYQTGRAPH_AVAILABLE:
                # 导出主图表
                exporter = pg.exporters.ImageExporter(self.main_chart.scene())  # type: ignore
                filename = f"chart_{self.current_symbol}_" f"{self.current_period}.{format_type}"
                exporter.export(filename)
                self.show_info(f"图表已导出到: {filename}")
            else:
                self.show_warning("图表导出功能需要pyqtgraph支持")
        except (OSError, AttributeError) as e:
            self.show_error(f"图表导出失败: {str(e)}")

    def on_close(self):
        """关闭处理."""
        # 停止数据工作线程
        if self.data_worker and self.data_worker.isRunning():
            self.data_worker.running = False
            self.data_worker.wait()

        super().on_close()
