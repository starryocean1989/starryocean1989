# -*- coding: utf-8 -*-
"""
图表组件集合 - 专业图表、工具栏、指标管理器.

本文件合并了以下组件：
- ChartWidget: 基于pyqtgraph的金融图表
- ChartToolbar: 图表工具栏
- SubplotIndicatorManager: 副图指标管理器
- IndicatorPlotWidget: 指标副图组件
"""
# pylint: disable=no-name-in-module

import logging
from typing import Any, Dict, List, Optional

# Qt imports
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Third-party imports
import numpy as np

from ui.components.widgets import BaseWidget

# ✅ 使用规范命名
logger = logging.getLogger("ui.components.charts")

# Backend imports - 检查vnpy可用性
try:
    VNPY_AVAILABLE = True
except ImportError:
    VNPY_AVAILABLE = False


# ===== 1. 数据适配器和工作线程 =====

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


# ===== 2. 图表工具栏 =====


class ChartToolbar(QWidget):
    """图表工具栏."""

    # 信号定义
    tool_changed = Signal(str)  # 工具切换信号
    crosshair_toggled = Signal(bool)  # 十字光标切换
    drawing_mode_changed = Signal(str)  # 画线模式切换

    def __init__(self, parent=None):
        """初始化工具栏."""
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """设置UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # 工具标签
        layout.addWidget(QLabel("图表工具:"))

        # 创建工具按钮组（互斥）
        self.tool_group = QButtonGroup(self)

        # 选择工具（默认）
        select_btn = QToolButton()
        select_btn.setText("🖱️ 选择")
        select_btn.setCheckable(True)
        select_btn.setChecked(True)
        select_btn.setToolTip("选择和拖动模式")
        select_btn.clicked.connect(lambda: self.tool_changed.emit("select"))
        self.tool_group.addButton(select_btn, 0)
        layout.addWidget(select_btn)

        # 十字光标
        crosshair_btn = QToolButton()
        crosshair_btn.setText("✛ 十字")
        crosshair_btn.setCheckable(True)
        crosshair_btn.setToolTip("十字光标（显示价格和时间）")
        crosshair_btn.toggled.connect(self.crosshair_toggled.emit)
        layout.addWidget(crosshair_btn)
        self.crosshair_btn = crosshair_btn

        # 画线工具分隔符
        layout.addWidget(QLabel("|"))
        layout.addWidget(QLabel("画线:"))

        # 趋势线
        trend_btn = QToolButton()
        trend_btn.setText("📈 趋势")
        trend_btn.setCheckable(True)
        trend_btn.setToolTip("绘制趋势线")
        trend_btn.clicked.connect(lambda: self.drawing_mode_changed.emit("trend"))
        self.tool_group.addButton(trend_btn, 1)
        layout.addWidget(trend_btn)

        # 水平线
        hline_btn = QToolButton()
        hline_btn.setText("━ 水平")
        hline_btn.setCheckable(True)
        hline_btn.setToolTip("绘制水平线（支撑位/压力位）")
        hline_btn.clicked.connect(lambda: self.drawing_mode_changed.emit("hline"))
        self.tool_group.addButton(hline_btn, 2)
        layout.addWidget(hline_btn)

        # 垂直线
        vline_btn = QToolButton()
        vline_btn.setText("┃ 垂直")
        vline_btn.setCheckable(True)
        vline_btn.setToolTip("绘制垂直线（时间标记）")
        vline_btn.clicked.connect(lambda: self.drawing_mode_changed.emit("vline"))
        self.tool_group.addButton(vline_btn, 3)
        layout.addWidget(vline_btn)

        # 矩形框
        rect_btn = QToolButton()
        rect_btn.setText("▭ 矩形")
        rect_btn.setCheckable(True)
        rect_btn.setToolTip("绘制矩形框（区域标记）")
        rect_btn.clicked.connect(lambda: self.drawing_mode_changed.emit("rectangle"))
        self.tool_group.addButton(rect_btn, 4)
        layout.addWidget(rect_btn)

        # 文本标注
        text_btn = QToolButton()
        text_btn.setText("📝 文本")
        text_btn.setCheckable(True)
        text_btn.setToolTip("添加文本标注")
        text_btn.clicked.connect(lambda: self.drawing_mode_changed.emit("text"))
        self.tool_group.addButton(text_btn, 5)
        layout.addWidget(text_btn)

        # 工具分隔符
        layout.addWidget(QLabel("|"))

        # 撤销/重做
        undo_btn = QPushButton("↶ 撤销")
        undo_btn.setToolTip("撤销上一步操作")
        undo_btn.clicked.connect(self._on_undo)
        layout.addWidget(undo_btn)

        redo_btn = QPushButton("↷ 重做")
        redo_btn.setToolTip("重做")
        redo_btn.clicked.connect(self._on_redo)
        layout.addWidget(redo_btn)

        # 清除所有标注
        clear_all_btn = QPushButton("🗑️ 清除")
        clear_all_btn.setToolTip("清除所有画线和标注")
        clear_all_btn.clicked.connect(self._on_clear_all)
        layout.addWidget(clear_all_btn)

        # 缩放工具
        layout.addWidget(QLabel("|"))

        zoom_in_btn = QPushButton("🔍+ 放大")
        zoom_in_btn.clicked.connect(self._on_zoom_in)
        layout.addWidget(zoom_in_btn)

        zoom_out_btn = QPushButton("🔍- 缩小")
        zoom_out_btn.clicked.connect(self._on_zoom_out)
        layout.addWidget(zoom_out_btn)

        reset_btn = QPushButton("⟲ 重置")
        reset_btn.setToolTip("重置缩放")
        reset_btn.clicked.connect(self._on_reset_zoom)
        layout.addWidget(reset_btn)

        layout.addStretch()

    def _on_undo(self):
        """撤销操作 - 这里可以实现撤销逻辑."""

    def _on_redo(self):
        """重做操作 - 这里可以实现重做逻辑."""

    def _on_clear_all(self):
        """清除所有标注 - 这里可以实现清除逻辑."""

    def _on_zoom_in(self):
        """放大 - 这里可以实现放大逻辑."""

    def _on_zoom_out(self):
        """缩小 - 这里可以实现缩小逻辑."""

    def _on_reset_zoom(self):
        """重置缩放 - 这里可以实现重置逻辑."""


# ===== 3. 副图指标管理器 =====


class SubplotIndicatorManager:
    """副图指标管理器.

    负责在图表中添加和管理副图指标（MACD、RSI、KDJ等）。
    """

    def __init__(self, chart_widget):
        """初始化副图指标管理器.

        Args:
            chart_widget: ChartWidget实例
        """
        self.chart = chart_widget
        self.indicators: Dict[str, Any] = {}  # 指标名称 -> 指标实例

    def add_macd(self, plot_name: str = "macd", macd_data: Optional[Dict[str, Any]] = None):
        """添加MACD副图.

        Args:
            plot_name: Plot区域名称
            macd_data: MACD数据 {"macd": [], "signal": [], "hist": []}
        """
        try:
            import pyqtgraph as pg

            # 添加plot区域
            self.chart.add_plot(plot_name=plot_name, maximum_height=150, hide_x_axis=False)

            if macd_data:
                # 绘制MACD线
                macd_plot = self.chart._plots.get(plot_name)
                if macd_plot:
                    # MACD柱状图
                    if "hist" in macd_data:
                        hist = macd_data["hist"]
                        x_data = list(range(len(hist)))
                        y_data = [
                            h if h is not None and not (isinstance(h, float) and h != h) else 0
                            for h in hist
                        ]

                        # 使用BarGraphItem绘制柱状图
                        colors = ["r" if y < 0 else "g" for y in y_data]
                        bars = pg.BarGraphItem(x=x_data, height=y_data, width=0.6, brushes=colors)
                        macd_plot.addItem(bars)

                    # MACD线（DIF）
                    if "macd" in macd_data:
                        macd_line = macd_data["macd"]
                        x_data = []
                        y_data = []
                        for i, value in enumerate(macd_line):
                            if value is not None and not (
                                isinstance(value, float) and value != value
                            ):
                                x_data.append(i)
                                y_data.append(float(value))

                        if x_data and y_data:
                            pen = pg.mkPen(color="#FFA07A", width=2)
                            curve = pg.PlotDataItem(x=x_data, y=y_data, pen=pen, name="DIF")
                            macd_plot.addItem(curve)

                    # Signal线（DEA）
                    if "signal" in macd_data:
                        signal_line = macd_data["signal"]
                        x_data = []
                        y_data = []
                        for i, value in enumerate(signal_line):
                            if value is not None and not (
                                isinstance(value, float) and value != value
                            ):
                                x_data.append(i)
                                y_data.append(float(value))

                        if x_data and y_data:
                            pen = pg.mkPen(color="#4ECDC4", width=2)
                            curve = pg.PlotDataItem(x=x_data, y=y_data, pen=pen, name="DEA")
                            macd_plot.addItem(curve)

            self.indicators["MACD"] = {
                "plot_name": plot_name,
                "type": "MACD",
            }

            logger.info(f"✅ MACD副图已添加: {plot_name}")
            return True

        except Exception as e:
            logger.error(f"❌ 添加MACD副图失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return False

    def add_rsi(
        self, plot_name: str = "rsi", rsi_data: Optional[List[Any]] = None, period: int = 14
    ):
        """添加RSI副图.

        Args:
            plot_name: Plot区域名称
            rsi_data: RSI数据列表
            period: RSI周期
        """
        try:
            import pyqtgraph as pg

            # 添加plot区域
            self.chart.add_plot(plot_name=plot_name, maximum_height=120, hide_x_axis=False)

            if rsi_data:
                rsi_plot = self.chart._plots.get(plot_name)
                if rsi_plot:
                    # 准备数据
                    x_data = []
                    y_data = []
                    for i, value in enumerate(rsi_data):
                        if value is not None and not (isinstance(value, float) and value != value):
                            x_data.append(i)
                            y_data.append(float(value))

                    if x_data and y_data:
                        # 绘制RSI线
                        pen = pg.mkPen(color="#FFA07A", width=2)
                        curve = pg.PlotDataItem(x=x_data, y=y_data, pen=pen, name=f"RSI({period})")
                        rsi_plot.addItem(curve)

                        # 添加超买超卖参考线
                        from PySide6.QtCore import Qt

                        pen_ref = pg.mkPen(color="#CCCCCC", width=1, style=Qt.PenStyle.DashLine)

                        # 超买线(70)
                        overbought = pg.InfiniteLine(pos=70, angle=0, pen=pen_ref)
                        rsi_plot.addItem(overbought)

                        # 超卖线(30)
                        oversold = pg.InfiniteLine(pos=30, angle=0, pen=pen_ref)
                        rsi_plot.addItem(oversold)

                        # 中线(50)
                        midline = pg.InfiniteLine(pos=50, angle=0, pen=pen_ref)
                        rsi_plot.addItem(midline)

            self.indicators["RSI"] = {
                "plot_name": plot_name,
                "type": "RSI",
                "period": period,
            }

            logger.info(f"✅ RSI副图已添加: {plot_name} (周期: {period})")
            return True

        except Exception as e:
            logger.error(f"❌ 添加RSI副图失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return False

    def add_kdj(self, plot_name: str = "kdj", kdj_data: Optional[Dict[str, Any]] = None):
        """添加KDJ副图.

        Args:
            plot_name: Plot区域名称
            kdj_data: KDJ数据 {"k": [], "d": [], "j": []}
        """
        try:
            import pyqtgraph as pg

            # 添加plot区域
            self.chart.add_plot(plot_name=plot_name, maximum_height=120, hide_x_axis=False)

            if kdj_data:
                kdj_plot = self.chart._plots.get(plot_name)
                if kdj_plot:
                    colors = {"k": "#FFA07A", "d": "#4ECDC4", "j": "#95E1D3"}

                    for line_name in ["k", "d", "j"]:
                        if line_name in kdj_data:
                            line_values = kdj_data[line_name]
                            x_data = []
                            y_data = []

                            for i, value in enumerate(line_values):
                                if value is not None and not (
                                    isinstance(value, float) and value != value
                                ):
                                    x_data.append(i)
                                    y_data.append(float(value))

                            if x_data and y_data:
                                pen = pg.mkPen(color=colors[line_name], width=2)
                                curve = pg.PlotDataItem(
                                    x=x_data, y=y_data, pen=pen, name=line_name.upper()
                                )
                                kdj_plot.addItem(curve)

                    # 添加超买超卖参考线
                    from PySide6.QtCore import Qt

                    pen_ref = pg.mkPen(color="#CCCCCC", width=1, style=Qt.PenStyle.DashLine)

                    # 超买线(80)
                    overbought = pg.InfiniteLine(pos=80, angle=0, pen=pen_ref)
                    kdj_plot.addItem(overbought)

                    # 超卖线(20)
                    oversold = pg.InfiniteLine(pos=20, angle=0, pen=pen_ref)
                    kdj_plot.addItem(oversold)

            self.indicators["KDJ"] = {
                "plot_name": plot_name,
                "type": "KDJ",
            }

            logger.info(f"✅ KDJ副图已添加: {plot_name}")
            return True

        except Exception as e:
            logger.error(f"❌ 添加KDJ副图失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return False

    def remove_indicator(self, indicator_type: str):
        """移除副图指标.

        Args:
            indicator_type: 指标类型（MACD、RSI、KDJ等）
        """
        if indicator_type not in self.indicators:
            logger.warning(f"指标不存在: {indicator_type}", extra={"log_type": "SYSTEM"})
            return False

        try:
            indicator_info = self.indicators[indicator_type]
            plot_name = indicator_info["plot_name"]

            # 移除plot区域
            if hasattr(self.chart, "remove_plot"):
                self.chart.remove_plot(plot_name)

            # 从字典中删除
            del self.indicators[indicator_type]

            logger.info(f"✅ 已移除指标: {indicator_type}")
            return True

        except Exception as e:
            logger.error(f"❌ 移除指标失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return False

    def get_indicator_list(self) -> List[str]:
        """获取当前已添加的指标列表.

        Returns:
            指标类型列表
        """
        return list(self.indicators.keys())


# ===== 4. 指标副图组件 =====


class IndicatorPlotWidget(QWidget):
    """指标副图组件."""

    # 信号
    close_requested = Signal()  # 请求关闭（删除）
    indicator_changed = Signal(str)  # 指标类型变更

    def __init__(
        self, indicator_type: str = "MACD", title: str = "", parent: Optional[QWidget] = None
    ):
        """初始化指标副图组件.

        Args:
            indicator_type: 指标类型（MACD、RSI、KDJ、BOLL等）
            title: 副图标题
            parent: 父组件
        """
        super().__init__(parent)

        self.indicator_type = indicator_type
        self.title = title or indicator_type

        # 图表组件
        self.plot_widget: Optional[Any] = None
        self.plot_item: Optional[Any] = None

        # UI组件
        self.indicator_selector: Optional[QComboBox] = None
        self.hide_button: Optional[QPushButton] = None
        self.close_button: Optional[QPushButton] = None

        # 是否可见
        self.is_visible = True

        self._setup_ui()
        logger.info(f"指标副图组件初始化: {self.indicator_type}")

    def _setup_ui(self):
        """设置用户界面."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # 顶部工具栏
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # 图表区域
        self._create_plot_widget()
        if self.plot_widget:
            layout.addWidget(self.plot_widget)

    def _create_toolbar(self) -> QWidget:
        """创建工具栏.

        Returns:
            工具栏组件
        """
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(5, 2, 5, 2)
        toolbar_layout.setSpacing(5)

        # 指标选择器
        self.indicator_selector = QComboBox()
        self.indicator_selector.addItems(
            ["MACD", "RSI", "KDJ", "BOLL", "CCI", "ATR", "VOLUME"]  # 成交量也可以作为一个指标
        )
        self.indicator_selector.setCurrentText(self.indicator_type)
        self.indicator_selector.currentTextChanged.connect(self._on_indicator_changed)
        toolbar_layout.addWidget(self.indicator_selector)

        toolbar_layout.addStretch()

        # 隐藏/显示按钮
        self.hide_button = QPushButton("隐藏")
        self.hide_button.setFixedWidth(50)
        self.hide_button.clicked.connect(self._toggle_visibility)
        toolbar_layout.addWidget(self.hide_button)

        # 删除按钮
        self.close_button = QPushButton("✕")
        self.close_button.setFixedWidth(30)
        self.close_button.clicked.connect(self._on_close_clicked)
        toolbar_layout.addWidget(self.close_button)

        return toolbar

    def _create_plot_widget(self):
        """创建图表组件."""
        # 使用pyqtgraph创建图表
        if not PYQTGRAPH_AVAILABLE or pg is None:
            logger.warning("pyqtgraph不可用，无法创建图表组件", extra={"log_type": "SYSTEM"})
            return

        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.setBackground(QColor(26, 26, 26))
        self.plot_widget.setMinimumHeight(100)

        # 添加plot
        self.plot_item = self.plot_widget.addPlot(title=self.title)  # type: ignore[attr-defined]
        if self.plot_item:
            self.plot_item.showGrid(x=True, y=True)
            self.plot_item.setLabel("bottom", "时间")

    def _on_indicator_changed(self, indicator_type: str):
        """指标类型改变.

        Args:
            indicator_type: 新的指标类型
        """
        self.indicator_type = indicator_type
        self.title = indicator_type

        # 清空并重置plot标题
        if self.plot_item:
            self.plot_item.clear()
            self.plot_item.setTitle(self.title)

        logger.info(f"指标类型切换为: {indicator_type}")
        self.indicator_changed.emit(indicator_type)

    def _toggle_visibility(self):
        """切换可见性."""
        if self.is_visible:
            # 隐藏图表
            if self.plot_widget:
                self.plot_widget.hide()
            if self.hide_button:
                self.hide_button.setText("显示")
            self.is_visible = False
            logger.debug("副图已隐藏")
        else:
            # 显示图表
            if self.plot_widget:
                self.plot_widget.show()
            if self.hide_button:
                self.hide_button.setText("隐藏")
            self.is_visible = True
            logger.debug("副图已显示")

    def _on_close_clicked(self):
        """关闭按钮点击."""
        logger.info("请求关闭副图: %s", self.indicator_type)
        self.close_requested.emit()

    def update_data(self, data: Dict[str, Any]):
        """更新指标数据.

        Args:
            data: 指标数据
        """
        try:
            # ✅ 数据验证
            if data is None or not isinstance(data, dict):
                logger.warning("图表数据无效: 数据为空或类型错误", extra={"log_type": "SYSTEM"})
                return

            if not self.plot_item or not self.is_visible:
                return

            # 清空旧数据
            self.plot_item.clear()

            # 根据指标类型绘制不同的图表
            if self.indicator_type == "MACD":
                self._plot_macd(data)
            elif self.indicator_type == "RSI":
                self._plot_rsi(data)
            elif self.indicator_type == "KDJ":
                self._plot_kdj(data)
            elif self.indicator_type == "BOLL":
                self._plot_boll(data)
            elif self.indicator_type == "VOLUME":
                self._plot_volume(data)
            else:
                logger.warning("未实现的指标类型: %s", self.indicator_type, extra={"log_type": "SYSTEM"})

            logger.debug("图表更新完成: 指标=%s", self.indicator_type)

        except Exception as e:
            logger.error("❌ 更新指标数据失败: 指标=%s, 错误=%s", self.indicator_type, e, exc_info=True, extra={"log_type": "SYSTEM"})

    def _plot_macd(self, data: Dict[str, Any]):
        """绘制MACD指标.

        Args:
            data: MACD数据 {macd: [], signal: [], hist: []}
        """
        if not self.plot_item or not PYQTGRAPH_AVAILABLE or pg is None:
            return

        macd_line = data.get("macd", [])
        signal_line = data.get("signal", [])
        hist = data.get("hist", [])

        if not macd_line:
            return

        x = list(range(len(macd_line)))

        # 绘制MACD线和信号线
        self.plot_item.plot(x, macd_line, pen="y", name="MACD")
        self.plot_item.plot(x, signal_line, pen="b", name="Signal")

        # 绘制柱状图
        from pyqtgraph import BarGraphItem

        bg = BarGraphItem(x=x, height=hist, width=0.6, brush="r")
        self.plot_item.addItem(bg)

    def _plot_rsi(self, data: Dict[str, Any]):
        """绘制RSI指标.

        Args:
            data: RSI数据，可以是列表或字典 {rsi: []}
        """
        if not self.plot_item or not PYQTGRAPH_AVAILABLE or pg is None:
            return

        # 保存 plot_item 到局部变量，避免类型检查器的 None 警告
        plot_item = self.plot_item

        if isinstance(data, list):
            rsi_data = data
        else:
            rsi_data = data.get("rsi", data.get("data", []))

        if not rsi_data:
            return

        x = list(range(len(rsi_data)))
        plot_item.plot(x, rsi_data, pen="g", name="RSI")

        # 添加超买超卖线
        plot_item.addLine(y=70, pen=pg.mkPen("r", width=1, style=Qt.PenStyle.DashLine))
        plot_item.addLine(y=30, pen=pg.mkPen("g", width=1, style=Qt.PenStyle.DashLine))

    def _plot_kdj(self, data: Dict[str, Any]):
        """绘制KDJ指标.

        Args:
            data: KDJ数据 {k: [], d: [], j: []}
        """
        if not self.plot_item or not PYQTGRAPH_AVAILABLE or pg is None:
            return

        # 保存 plot_item 到局部变量，避免类型检查器的 None 警告
        plot_item = self.plot_item

        k_line = data.get("k", [])
        d_line = data.get("d", [])
        j_line = data.get("j", [])

        if not k_line:
            return

        x = list(range(len(k_line)))
        plot_item.plot(x, k_line, pen="r", name="K")
        plot_item.plot(x, d_line, pen="g", name="D")
        plot_item.plot(x, j_line, pen="b", name="J")

    def _plot_boll(self, data: Dict[str, Any]):
        """绘制BOLL指标.

        Args:
            data: BOLL数据 {upper: [], middle: [], lower: []}
        """
        if not self.plot_item or not PYQTGRAPH_AVAILABLE or pg is None:
            return

        # 保存 plot_item 到局部变量，避免类型检查器的 None 警告
        plot_item = self.plot_item

        upper = data.get("upper", [])
        middle = data.get("middle", [])
        lower = data.get("lower", [])

        if not middle:
            return

        x = list(range(len(middle)))
        plot_item.plot(x, upper, pen="r", name="Upper")
        plot_item.plot(x, middle, pen="y", name="Middle")
        plot_item.plot(x, lower, pen="g", name="Lower")

    def _plot_volume(self, data: Dict[str, Any]):
        """绘制成交量.

        Args:
            data: 成交量数据，可以是列表或字典 {volume: []}
        """
        if not self.plot_item or not PYQTGRAPH_AVAILABLE or pg is None:
            return

        # 保存 plot_item 到局部变量，避免类型检查器的 None 警告
        plot_item = self.plot_item

        if isinstance(data, list):
            volume_data = data
        else:
            volume_data = data.get("volume", data.get("data", []))

        if not volume_data:
            return

        x = list(range(len(volume_data)))

        # 使用柱状图显示成交量
        from pyqtgraph import BarGraphItem

        bg = BarGraphItem(x=x, height=volume_data, width=0.8, brush="b")
        plot_item.addItem(bg)

    def clear(self):
        """清空图表."""
        if self.plot_item:
            self.plot_item.clear()


# ===== 5. 主图表组件 =====


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
            self._logger.error("图表显示更新失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})

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
                    self._logger.warning("MACD指标更新失败: %s", macd_error, extra={"log_type": "SYSTEM"})
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
                    self._logger.warning("RSI指标更新失败: %s", rsi_error, extra={"log_type": "SYSTEM"})
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
            self._logger.error("指标更新失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})

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

            service_manager = get_service_manager()
            # 修复：使用data_center_service代替不存在的symbol_service
            data_center_service = service_manager.get_service("data_center_service")

            if data_center_service:
                # 检查是否有缓存，避免在初始化时触发API加载
                if (
                    hasattr(data_center_service, "_symbol_cache")
                    and data_center_service._symbol_cache
                ):
                    # 只在有缓存时才从服务加载
                    result = data_center_service.refresh_symbol_list()

                    if result.get("success") and self.symbol_combo:
                        symbols = result.get("data", [])
                        if symbols:  # 确保有数据
                            for symbol in symbols:
                                # 兼容不同的数据格式
                                code = symbol.get("code") or symbol.get("symbol", "")
                                name = symbol.get("name", "")
                                if code:
                                    display_name = f"{code} - {name}" if name else code
                                    self.symbol_combo.addItem(display_name, code)
                            self._logger.debug("图表组件已从缓存加载 %d 个品种", len(symbols))
                            return

                # 缓存为空，使用默认品种（避免触发API加载）
                self._load_default_chart_symbols()
            else:
                # 数据中心服务不可用，使用默认品种
                self._logger.debug("数据中心服务不可用，使用默认品种列表")
                self._load_default_chart_symbols()

        except Exception as e:
            self._logger.debug("加载品种列表失败: %s，使用默认品种", e)
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


# ===== 6. 导出 =====

__all__ = [
    "ChartWidget",
    "ChartToolbar",
    "SubplotIndicatorManager",
    "IndicatorPlotWidget",
    "VnPyAdapter",
    "ChartDataWorker",
]
