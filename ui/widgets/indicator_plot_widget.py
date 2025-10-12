# -*- coding: utf-8 -*-
"""指标副图组件.

独立的技术指标显示组件，支持：
- 多种技术指标（MACD、RSI、KDJ、BOLL等）
- 可显示/隐藏
- 可删除
- 可调整高度
"""

import logging
from typing import Any, Dict, Optional

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg

logger = logging.getLogger(__name__)


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
        logger.info(f"请求关闭副图: {self.indicator_type}")
        self.close_requested.emit()

    def update_data(self, data: Dict[str, Any]):
        """更新指标数据.

        Args:
            data: 指标数据
        """
        try:
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
                logger.warning(f"未实现的指标类型: {self.indicator_type}")

        except Exception as e:
            logger.error(f"更新指标数据失败: {e}", exc_info=True)

    def _plot_macd(self, data: Dict[str, Any]):
        """绘制MACD指标.

        Args:
            data: MACD数据 {macd: [], signal: [], hist: []}
        """
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
        if isinstance(data, list):
            rsi_data = data
        else:
            rsi_data = data.get("rsi", data.get("data", []))

        if not rsi_data:
            return

        x = list(range(len(rsi_data)))
        self.plot_item.plot(x, rsi_data, pen="g", name="RSI")

        # 添加超买超卖线
        self.plot_item.addLine(y=70, pen=pg.mkPen("r", width=1, style=Qt.PenStyle.DashLine))
        self.plot_item.addLine(y=30, pen=pg.mkPen("g", width=1, style=Qt.PenStyle.DashLine))

    def _plot_kdj(self, data: Dict[str, Any]):
        """绘制KDJ指标.

        Args:
            data: KDJ数据 {k: [], d: [], j: []}
        """
        k_line = data.get("k", [])
        d_line = data.get("d", [])
        j_line = data.get("j", [])

        if not k_line:
            return

        x = list(range(len(k_line)))
        self.plot_item.plot(x, k_line, pen="r", name="K")
        self.plot_item.plot(x, d_line, pen="g", name="D")
        self.plot_item.plot(x, j_line, pen="b", name="J")

    def _plot_boll(self, data: Dict[str, Any]):
        """绘制BOLL指标.

        Args:
            data: BOLL数据 {upper: [], middle: [], lower: []}
        """
        upper = data.get("upper", [])
        middle = data.get("middle", [])
        lower = data.get("lower", [])

        if not middle:
            return

        x = list(range(len(middle)))
        self.plot_item.plot(x, upper, pen="r", name="Upper")
        self.plot_item.plot(x, middle, pen="y", name="Middle")
        self.plot_item.plot(x, lower, pen="g", name="Lower")

    def _plot_volume(self, data: Dict[str, Any]):
        """绘制成交量.

        Args:
            data: 成交量数据，可以是列表或字典 {volume: []}
        """
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
        self.plot_item.addItem(bg)

    def clear(self):
        """清空图表."""
        if self.plot_item:
            self.plot_item.clear()
