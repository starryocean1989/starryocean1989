# -*- coding: utf-8 -*-
"""
成交监控组件 - 基于VnPy BaseMonitor.

显示所有成交记录，支持：
- 实时成交更新
- 成交统计
- CSV导出
"""

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vnpy.event import Event, EventEngine
from vnpy.trader.event import EVENT_TRADE


class TradeMonitor(QWidget):
    """成交监控组件.

    功能：
    - 显示所有成交记录
    - 实时更新成交数据
    - 成交统计（总成交量、总成交额、成交均价）
    - 支持CSV导出
    """

    def __init__(
        self,
        event_engine: Optional[EventEngine] = None,
        gateway_name: str = "",
        parent: Optional[QWidget] = None,
    ):
        """初始化成交监控组件.

        Args:
            event_engine: VnPy事件引擎
            gateway_name: 网关名称（用于过滤）
            parent: 父组件
        """
        super().__init__(parent)
        self.event_engine = event_engine
        self.gateway_name = gateway_name

        # 成交数据缓存 {tradeid: trade_data}
        self.trades: Dict[str, Dict[str, Any]] = {}

        self._setup_ui()
        self._register_event()

    def _setup_ui(self):
        """设置UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 统计信息组
        stats_group = QGroupBox("成交统计")
        stats_layout = QHBoxLayout(stats_group)

        self.trade_count_label = QLabel("成交笔数: 0")
        stats_layout.addWidget(self.trade_count_label)

        self.total_volume_label = QLabel("总成交量: 0")
        stats_layout.addWidget(self.total_volume_label)

        self.total_turnover_label = QLabel("总成交额: 0.00")
        stats_layout.addWidget(self.total_turnover_label)

        self.avg_price_label = QLabel("成交均价: --")
        stats_layout.addWidget(self.avg_price_label)

        stats_layout.addStretch()
        layout.addWidget(stats_group)

        # 成交表格
        self.table = QTableWidget(0, 8)
        headers = ["成交号", "委托号", "合约", "方向", "价格", "数量", "成交额", "时间"]
        self.table.setHorizontalHeaderLabels(headers)

        # 设置列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

        # 设置选择模式
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)

        layout.addWidget(self.table)

    def _register_event(self):
        """注册事件监听."""
        if self.event_engine:
            self.event_engine.register(EVENT_TRADE, self._process_trade_event)

    def _process_trade_event(self, event: Event):
        """处理成交事件.

        Args:
            event: 成交事件
        """
        try:
            trade = event.data

            # 如果指定了网关名称，则过滤
            if self.gateway_name and hasattr(trade, "gateway_name"):
                if trade.gateway_name != self.gateway_name:
                    return

            # 提取成交数据
            tradeid = getattr(trade, "tradeid", "")
            if not tradeid:
                return

            price = getattr(trade, "price", 0.0)
            volume = getattr(trade, "volume", 0)
            turnover = price * volume

            trade_data = {
                "tradeid": tradeid,
                "orderid": getattr(trade, "orderid", ""),
                "symbol": getattr(trade, "symbol", ""),
                "vt_symbol": getattr(trade, "vt_symbol", ""),
                "direction": self._format_direction(getattr(trade, "direction", None)),
                "offset": getattr(trade, "offset", None),
                "price": price,
                "volume": volume,
                "turnover": turnover,
                "time": getattr(trade, "time", ""),
                "gateway_name": getattr(trade, "gateway_name", ""),
            }

            # 更新缓存
            self.trades[tradeid] = trade_data

            # 更新表格和统计
            self._update_table()
            self._update_statistics()

        except Exception as e:
            print(f"处理成交事件失败: {e}")

    def _format_direction(self, direction) -> str:
        """格式化方向.

        Args:
            direction: 方向枚举

        Returns:
            格式化后的方向字符串
        """
        if direction is None:
            return ""

        try:
            from vnpy.trader.constant import Direction

            if direction == Direction.LONG:
                return "多"
            elif direction == Direction.SHORT:
                return "空"
            else:
                return str(direction.value)
        except Exception:
            return str(direction)

    def _update_table(self):
        """更新表格显示."""
        # 保存当前选中行
        current_row = self.table.currentRow()

        # 清空并重建表格
        self.table.setRowCount(0)

        # 按时间倒序排序（最新的在前）
        sorted_trades = sorted(self.trades.values(), key=lambda x: x.get("time", ""), reverse=True)

        for row, trade in enumerate(sorted_trades):
            self.table.insertRow(row)

            # 填充数据
            self.table.setItem(row, 0, QTableWidgetItem(trade["tradeid"]))
            self.table.setItem(row, 1, QTableWidgetItem(trade["orderid"]))
            self.table.setItem(row, 2, QTableWidgetItem(trade["vt_symbol"]))

            # 方向列（根据方向设置颜色）
            direction_item = QTableWidgetItem(trade["direction"])
            if trade["direction"] == "多":
                direction_item.setForeground(Qt.GlobalColor.red)
            elif trade["direction"] == "空":
                direction_item.setForeground(Qt.GlobalColor.green)
            self.table.setItem(row, 3, direction_item)

            self.table.setItem(row, 4, QTableWidgetItem(f"{trade['price']:.2f}"))
            self.table.setItem(row, 5, QTableWidgetItem(str(trade["volume"])))
            self.table.setItem(row, 6, QTableWidgetItem(f"{trade['turnover']:,.2f}"))
            self.table.setItem(row, 7, QTableWidgetItem(trade["time"]))

        # 恢复选中行
        if current_row >= 0 and current_row < self.table.rowCount():
            self.table.setCurrentCell(current_row, 0)

    def _update_statistics(self):
        """更新统计信息."""
        trade_count = len(self.trades)
        total_volume = sum(t["volume"] for t in self.trades.values())
        total_turnover = sum(t["turnover"] for t in self.trades.values())

        # 计算成交均价
        avg_price = total_turnover / total_volume if total_volume > 0 else 0

        # 更新标签
        self.trade_count_label.setText(f"成交笔数: {trade_count}")
        self.total_volume_label.setText(f"总成交量: {total_volume:,}")
        self.total_turnover_label.setText(f"总成交额: {total_turnover:,.2f}")
        self.avg_price_label.setText(
            f"成交均价: {avg_price:.2f}" if total_volume > 0 else "成交均价: --"
        )

    def clear_data(self):
        """清空数据."""
        self.trades.clear()
        self.table.setRowCount(0)
        self._update_statistics()

    def export_to_csv(self, filename: str):
        """导出到CSV文件.

        Args:
            filename: 文件名
        """
        try:
            import csv

            with open(filename, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)

                # 写入表头
                headers = ["成交号", "委托号", "合约", "方向", "价格", "数量", "成交额", "时间"]
                writer.writerow(headers)

                # 写入数据
                for trade in sorted(
                    self.trades.values(), key=lambda x: x.get("time", ""), reverse=True
                ):
                    writer.writerow(
                        [
                            trade["tradeid"],
                            trade["orderid"],
                            trade["vt_symbol"],
                            trade["direction"],
                            f"{trade['price']:.2f}",
                            trade["volume"],
                            f"{trade['turnover']:.2f}",
                            trade["time"],
                        ]
                    )

            return True
        except Exception as e:
            print(f"导出CSV失败: {e}")
            return False

    def closeEvent(self, event):
        """关闭事件 - 取消注册事件监听."""
        if self.event_engine:
            self.event_engine.unregister(EVENT_TRADE, self._process_trade_event)
        super().closeEvent(event)
