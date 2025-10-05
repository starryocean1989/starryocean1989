# -*- coding: utf-8 -*-
"""
专业图表组件 - 基于pyqtgraph的金融图表
提供K线图、分时图、技术指标等专业图表功能
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QSplitter
from PySide6.QtCore import Qt, Signal, QTimer, QThread
from PySide6.QtGui import QColor

from .base_widget import BaseWidget

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    pg = None

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False


class ChartDataWorker(QThread):
    """图表数据处理工作线程"""

    data_ready = Signal(dict)

    def __init__(self, symbol: str, period: str, data_api=None):
        super().__init__()
        self.symbol = symbol
        self.period = period
        self.data_api = data_api
        self.running = False

    def run(self):
        """运行数据获取任务"""
        self.running = True

        try:
            # 获取历史数据
            if self.data_api and hasattr(self.data_api, 'get_kline_data'):
                kline_data = self.data_api.get_kline_data(self.symbol, self.period, limit=200)
            else:
                # 模拟数据
                kline_data = self._generate_mock_data()

            # 计算技术指标
            indicators = self._calculate_indicators(kline_data)

            result = {
                'symbol': self.symbol,
                'period': self.period,
                'kline_data': kline_data,
                'indicators': indicators
            }

            self.data_ready.emit(result)

        except Exception as e:
            self.data_ready.emit({'error': str(e)})
        finally:
            self.running = False

    def _generate_mock_data(self) -> List[Dict[str, Any]]:
        """生成模拟数据"""
        data = []
        base_price = 100.0

        for i in range(200):
            # 模拟价格波动
            change = np.random.normal(0, 0.02)
            open_price = base_price
            close_price = open_price * (1 + change)

            # 确保价格合理性
            high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.01)))
            low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.01)))

            volume = np.random.randint(10000, 1000000)

            data.append({
                'datetime': datetime.now() - timedelta(days=200-i),
                'open': round(open_price, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'close': round(close_price, 2),
                'volume': volume
            })

            base_price = close_price

        return data

    def _calculate_indicators(self, kline_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算技术指标"""
        if not TALIB_AVAILABLE or not kline_data:
            return {}

        try:
            # 提取价格数据
            closes = np.array([item['close'] for item in kline_data])
            highs = np.array([item['high'] for item in kline_data])
            lows = np.array([item['low'] for item in kline_data])
            volumes = np.array([item['volume'] for item in kline_data])

            indicators = {}

            # MA均线
            indicators['ma5'] = talib.MA(closes, timeperiod=5)
            indicators['ma10'] = talib.MA(closes, timeperiod=10)
            indicators['ma20'] = talib.MA(closes, timeperiod=20)
            indicators['ma60'] = talib.MA(closes, timeperiod=60)

            # MACD
            macd, macdsignal, macdhist = talib.MACD(closes, fastperiod=12, slowperiod=26, signalperiod=9)
            indicators['macd'] = macd
            indicators['macdsignal'] = macdsignal
            indicators['macdhist'] = macdhist

            # RSI
            indicators['rsi'] = talib.RSI(closes, timeperiod=14)

            # KDJ
            slowk, slowd = talib.STOCH(highs, lows, closes,
                                     fastk_period=9, slowk_period=3, slowd_period=3)
            indicators['kdj_k'] = slowk
            indicators['kdj_d'] = slowd
            indicators['kdj_j'] = 3 * slowk - 2 * slowd

            # BOLL
            upper, middle, lower = talib.BBANDS(closes, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
            indicators['boll_upper'] = upper
            indicators['boll_middle'] = middle
            indicators['boll_lower'] = lower

            return indicators

        except Exception as e:
            return {'error': f'指标计算失败: {str(e)}'}


class ChartWidget(BaseWidget):
    """专业图表组件"""

    # 信号定义
    symbol_changed = Signal(str)
    period_changed = Signal(str)
    indicator_toggled = Signal(str, bool)

    def __init__(self, parent=None):
        # 颜色配置 - 必须在super().__init__()之前初始化
        self.colors = {
            'background': QColor(26, 26, 26),
            'foreground': QColor(255, 255, 255),
            'grid': QColor(64, 64, 64),
            'up': QColor(255, 100, 100),      # 红色 - 上涨
            'down': QColor(100, 255, 100),    # 绿色 - 下跌
            'ma5': QColor(255, 255, 0),       # 黄色
            'ma10': QColor(0, 255, 255),      # 青色
            'ma20': QColor(255, 0, 255),      # 品红
            'ma60': QColor(128, 128, 128),    # 灰色
        }

        # 图表组件 - 必须在super().__init__()之前初始化
        self.indicator_charts = {}

        super().__init__(parent, "专业图表")

        self.current_symbol = "000001"
        self.current_period = "日K"
        self.chart_data = []
        self.indicators_data = {}

        # 图表组件
        self.main_chart = None
        self.volume_chart = None

        # 数据工作线程
        self.data_worker = None

    def setup_ui(self):
        """设置用户界面"""
        if not PYQTGRAPH_AVAILABLE:
            # 如果pyqtgraph不可用，显示替代界面
            self._create_fallback_ui()
            return

        main_layout = QVBoxLayout(self)

        # 创建图表布局
        chart_layout = QVBoxLayout()

        # 主图区域
        self._create_main_chart()
        chart_layout.addWidget(self.main_chart_widget)

        # 成交量图表
        self._create_volume_chart()
        chart_layout.addWidget(self.volume_chart_widget)

        # 技术指标图表
        self._create_indicator_charts()
        for chart in self.indicator_charts.values():
            chart_layout.addWidget(chart)

        main_layout.addLayout(chart_layout, 1)

        # 控制面板
        control_layout = self._create_control_panel()
        main_layout.addLayout(control_layout)

    def _create_fallback_ui(self):
        """创建备用界面（pyqtgraph不可用时）"""
        from PySide6.QtWidgets import QLabel

        layout = QVBoxLayout(self)

        label = QLabel("📈 专业图表组件\n\n需要安装pyqtgraph库以获得完整功能")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 16px;
                padding: 40px;
            }
        """)
        layout.addWidget(label)

    def _create_main_chart(self):
        """创建主图表（K线图）"""
        if not PYQTGRAPH_AVAILABLE:
            return

        # 创建图形窗口
        self.main_chart_widget = pg.GraphicsLayoutWidget()
        self.main_chart_widget.setBackground(self.colors['background'])

        # 创建主图表
        self.main_chart = self.main_chart_widget.addPlot(title="K线图")
        self.main_chart.showGrid(x=True, y=True)
        self.main_chart.getAxis('bottom').setPen(self.colors['foreground'])
        self.main_chart.getAxis('left').setPen(self.colors['foreground'])

        # 设置坐标轴样式
        self.main_chart.getAxis('bottom').setTextPen(self.colors['foreground'])
        self.main_chart.getAxis('left').setTextPen(self.colors['foreground'])

        # 隐藏自动缩放按钮
        self.main_chart.hideButtons()

        # 创建蜡烛图项目
        try:
            # 尝试使用CandlestickItem
            if hasattr(pg, 'CandlestickItem'):
                self.candlestick = pg.CandlestickItem()
            else:
                # 如果CandlestickItem不可用，使用普通的PlotDataItem
                self.candlestick = pg.PlotDataItem()
            self.main_chart.addItem(self.candlestick)
        except Exception as e:
            # 如果创建失败，使用简单的PlotDataItem
            self.candlestick = pg.PlotDataItem()
            self.main_chart.addItem(self.candlestick)

    def _create_volume_chart(self):
        """创建成交量图表"""
        if not PYQTGRAPH_AVAILABLE:
            return

        self.volume_chart_widget = pg.GraphicsLayoutWidget()
        self.volume_chart_widget.setBackground(self.colors['background'])

        self.volume_chart = self.volume_chart_widget.addPlot(title="成交量")
        self.volume_chart.showGrid(x=True, y=True)
        self.volume_chart.getAxis('bottom').setPen(self.colors['foreground'])
        self.volume_chart.getAxis('left').setPen(self.colors['foreground'])
        self.volume_chart.getAxis('bottom').setTextPen(self.colors['foreground'])
        self.volume_chart.getAxis('left').setTextPen(self.colors['foreground'])
        self.volume_chart.hideButtons()

        # 创建柱状图项目
        self.volume_bars = pg.BarGraphItem(x=[], height=[], width=0.8, brush=self.colors['up'])
        self.volume_chart.addItem(self.volume_bars)

    def _create_indicator_charts(self):
        """创建技术指标图表"""
        if not PYQTGRAPH_AVAILABLE:
            return

        # MACD图表
        macd_win = pg.GraphicsLayoutWidget()
        macd_win.setBackground(self.colors['background'])
        macd_plot = macd_win.addPlot(title="MACD")
        macd_plot.showGrid(x=True, y=True)
        macd_plot.getAxis('bottom').setPen(self.colors['foreground'])
        macd_plot.getAxis('left').setPen(self.colors['foreground'])
        macd_plot.getAxis('bottom').setTextPen(self.colors['foreground'])
        macd_plot.getAxis('left').setTextPen(self.colors['foreground'])
        macd_plot.hideButtons()
        self.indicator_charts['macd'] = macd_win

        # RSI图表
        rsi_win = pg.GraphicsLayoutWidget()
        rsi_win.setBackground(self.colors['background'])
        rsi_plot = rsi_win.addPlot(title="RSI")
        rsi_plot.showGrid(x=True, y=True)
        rsi_plot.getAxis('bottom').setPen(self.colors['foreground'])
        rsi_plot.getAxis('left').setPen(self.colors['foreground'])
        rsi_plot.getAxis('bottom').setTextPen(self.colors['foreground'])
        rsi_plot.getAxis('left').setTextPen(self.colors['foreground'])
        rsi_plot.hideButtons()
        self.indicator_charts['rsi'] = rsi_win

    def _create_control_panel(self):
        """创建控制面板"""
        layout = QHBoxLayout()

        # 品种选择
        symbol_layout = QHBoxLayout()
        symbol_layout.addWidget(QLabel("品种:"))
        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems([
            "000001 - 平安银行", "000002 - 万科A", "600000 - 浦发银行",
            "IF2406 - 沪深300股指期货", "IC2406 - 中证500股指期货"
        ])
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
        """连接信号槽"""
        if PYQTGRAPH_AVAILABLE:
            # 连接鼠标交互信号
            self.main_chart.scene().sigMouseClicked.connect(self._on_chart_clicked)

    def _on_symbol_changed(self, text: str):
        """品种选择改变"""
        symbol_code = text.split(" - ")[0] if text else "000001"
        if symbol_code != self.current_symbol:
            self.current_symbol = symbol_code
            self.symbol_changed.emit(symbol_code)
            self._logger.info(f"切换品种: {text}")
            self._load_chart_data()

    def _on_period_changed(self, text: str):
        """周期选择改变"""
        if text != self.current_period:
            self.current_period = text
            self.period_changed.emit(text)
            self._logger.info(f"切换周期: {text}")
            self._load_chart_data()

    def _on_chart_clicked(self, event):
        """图表点击事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self.main_chart.vb.mapSceneToView(event.scenePos())
            self._logger.info(f"图表点击位置: x={pos.x()}, y={pos.y()}")

    def _load_chart_data(self):
        """加载图表数据"""
        if not PYQTGRAPH_AVAILABLE:
            return

        # 停止当前工作线程
        if self.data_worker and self.data_worker.isRunning():
            self.data_worker.running = False
            self.data_worker.wait()

        # 创建新的数据工作线程
        from integration.vnpy_adapter import VnPyAdapter
        adapter = VnPyAdapter()

        self.data_worker = ChartDataWorker(
            symbol=self.current_symbol,
            period=self.current_period,
            data_api=adapter
        )

        self.data_worker.data_ready.connect(self._on_data_ready)
        self.data_worker.start()

        self.show_info("正在加载图表数据...")

    def _on_data_ready(self, result: Dict[str, Any]):
        """数据准备完成回调"""
        if 'error' in result:
            self.show_error(f"数据加载失败: {result['error']}")
            return

        try:
            self.chart_data = result['kline_data']
            self.indicators_data = result.get('indicators', {})

            self._update_chart_display()
            self.show_info("图表数据加载完成")

        except Exception as e:
            self.show_error(f"图表更新失败: {str(e)}")

    def _update_chart_display(self):
        """更新图表显示"""
        if not PYQTGRAPH_AVAILABLE or not self.chart_data:
            return

        try:
            # 提取数据
            timestamps = [item['datetime'].timestamp() for item in self.chart_data]
            opens = [item['open'] for item in self.chart_data]
            closes = [item['close'] for item in self.chart_data]
            highs = [item['high'] for item in self.chart_data]
            lows = [item['low'] for item in self.chart_data]
            volumes = [item['volume'] for item in self.chart_data]

            # 更新K线图
            self.candlestick.setData(timestamps, opens, closes, highs, lows)

            # 更新成交量图表
            self.volume_bars.setOpts(x=timestamps, height=volumes)

            # 更新技术指标
            self._update_indicators()

            # 调整坐标轴范围
            self.main_chart.setXRange(min(timestamps), max(timestamps))
            self.volume_chart.setXRange(min(timestamps), max(timestamps))

            # 更新指标图表的X轴范围
            for chart in self.indicator_charts.values():
                chart.setXRange(min(timestamps), max(timestamps))

        except Exception as e:
            self._logger.error(f"图表显示更新失败: {e}")

    def _update_indicators(self):
        """更新技术指标显示"""
        if not self.indicators_data:
            return

        try:
            timestamps = [item['datetime'].timestamp() for item in self.chart_data]

            # 更新MACD指标
            if 'macd' in self.indicators_data and self.indicators_data['macd'] is not None:
                try:
                    # 清除旧的MACD线条
                    self.indicator_charts['macd'].clear()

                    # 绘制MACD线条
                    macd_values = self.indicators_data['macd']
                    macdsignal_values = self.indicators_data['macdsignal']
                    macdhist_values = self.indicators_data['macdhist']

                    # MACD线（蓝色）
                    macd_line = pg.PlotCurveItem(
                        x=timestamps[-len(macd_values):],
                        y=macd_values,
                        pen=pg.mkPen(color='blue', width=1)
                    )
                    # 使用plot方法替代addItem来避免geometryChanged问题
                    self.indicator_charts['macd'].plot(
                        x=timestamps[-len(macd_values):],
                        y=macd_values,
                        pen=pg.mkPen(color='blue', width=1)
                    )

                    # Signal线（橙色）
                    self.indicator_charts['macd'].plot(
                        x=timestamps[-len(macdsignal_values):],
                        y=macdsignal_values,
                        pen=pg.mkPen(color='orange', width=1)
                    )
                except Exception as macd_error:
                    self._logger.warning(f"MACD指标更新失败: {macd_error}")
                    # 使用简单的plot方法作为备用
                    if 'macd' in self.indicators_data and self.indicators_data['macd'] is not None:
                        self.indicator_charts['macd'].clear()
                        self.indicator_charts['macd'].plot(
                            x=timestamps[-len(self.indicators_data['macd']):],
                            y=self.indicators_data['macd'],
                            pen=pg.mkPen(color='blue', width=1)
                        )

            # 更新RSI指标
            if 'rsi' in self.indicators_data and self.indicators_data['rsi'] is not None:
                try:
                    self.indicator_charts['rsi'].clear()

                    rsi_values = self.indicators_data['rsi']
                    # 使用plot方法替代addItem来避免geometryChanged问题
                    self.indicator_charts['rsi'].plot(
                        x=timestamps[-len(rsi_values):],
                        y=rsi_values,
                        pen=pg.mkPen(color='yellow', width=1)
                    )

                    # 添加超买超卖线
                    self.indicator_charts['rsi'].addLine(y=70, pen=pg.mkPen(color='red', style=Qt.PenStyle.DashLine))
                    self.indicator_charts['rsi'].addLine(y=30, pen=pg.mkPen(color='green', style=Qt.PenStyle.DashLine))
                except Exception as rsi_error:
                    self._logger.warning(f"RSI指标更新失败: {rsi_error}")
                    # 使用简单的plot方法作为备用
                    if 'rsi' in self.indicators_data and self.indicators_data['rsi'] is not None:
                        self.indicator_charts['rsi'].clear()
                        self.indicator_charts['rsi'].plot(
                            x=timestamps[-len(self.indicators_data['rsi']):],
                            y=self.indicators_data['rsi'],
                            pen=pg.mkPen(color='yellow', width=1)
                        )

        except Exception as e:
            self._logger.error(f"指标更新失败: {e}")

    def refresh_data(self):
        """刷新数据"""
        self._load_chart_data()

    def set_symbol(self, symbol: str):
        """设置品种"""
        if symbol != self.current_symbol:
            self.current_symbol = symbol
            # 找到对应的显示文本
            for i in range(self.symbol_combo.count()):
                text = self.symbol_combo.itemText(i)
                if text.startswith(symbol):
                    self.symbol_combo.setCurrentIndex(i)
                    break

    def set_period(self, period: str):
        """设置周期"""
        if period != self.current_period:
            self.current_period = period
            index = self.period_combo.findText(period)
            if index >= 0:
                self.period_combo.setCurrentIndex(index)

    def add_indicator(self, indicator_type: str, params: Dict[str, Any] = None):
        """添加技术指标"""
        self._logger.info(f"添加技术指标: {indicator_type}")
        # 这里可以实现动态添加指标的功能

    def remove_indicator(self, indicator_type: str):
        """移除技术指标"""
        self._logger.info(f"移除技术指标: {indicator_type}")
        # 这里可以实现动态移除指标的功能

    def set_chart_style(self, style: str):
        """设置图表样式"""
        self._logger.info(f"设置图表样式: {style}")
        # 这里可以实现不同的图表样式

    def export_chart(self, format_type: str = "png"):
        """导出图表"""
        try:
            if PYQTGRAPH_AVAILABLE:
                # 导出主图表
                exporter = pg.exporters.ImageExporter(self.main_chart.scene())
                filename = f"chart_{self.current_symbol}_{self.current_period}.{format_type}"
                exporter.export(filename)
                self.show_info(f"图表已导出到: {filename}")
            else:
                self.show_warning("图表导出功能需要pyqtgraph支持")
        except Exception as e:
            self.show_error(f"图表导出失败: {str(e)}")

    def on_close(self):
        """关闭处理"""
        # 停止数据工作线程
        if self.data_worker and self.data_worker.isRunning():
            self.data_worker.running = False
            self.data_worker.wait()

        super().on_close()
