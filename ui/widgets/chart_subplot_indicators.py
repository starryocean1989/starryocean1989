# -*- coding: utf-8 -*-
"""
图表副图指标组件

提供MACD、RSI、KDJ等常用副图指标的实现。
基于 vnpy.chart 的 ChartItem 架构。
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


# 副图指标使用 pyqtgraph 直接绘制，无需 vnpy.chart.ChartItem


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

    def add_macd(self, plot_name: str = "macd", macd_data: Dict = None):
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
            logger.error(f"❌ 添加MACD副图失败: {e}", exc_info=True)
            return False

    def add_rsi(self, plot_name: str = "rsi", rsi_data: List = None, period: int = 14):
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
            logger.error(f"❌ 添加RSI副图失败: {e}", exc_info=True)
            return False

    def add_kdj(self, plot_name: str = "kdj", kdj_data: Dict = None):
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
            logger.error(f"❌ 添加KDJ副图失败: {e}", exc_info=True)
            return False

    def remove_indicator(self, indicator_type: str):
        """移除副图指标.

        Args:
            indicator_type: 指标类型（MACD、RSI、KDJ等）
        """
        if indicator_type not in self.indicators:
            logger.warning(f"指标不存在: {indicator_type}")
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
            logger.error(f"❌ 移除指标失败: {e}", exc_info=True)
            return False

    def get_indicator_list(self) -> List[str]:
        """获取当前已添加的指标列表.

        Returns:
            指标类型列表
        """
        return list(self.indicators.keys())


# 导出
__all__ = [
    "SubplotIndicatorManager",
]
