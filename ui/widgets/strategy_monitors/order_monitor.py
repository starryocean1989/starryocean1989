# -*- coding: utf-8 -*-
"""
订单监控组件 - 基于VnPy BaseMonitor.

显示所有委托订单的实时状态，支持：
- 实时订单更新
- 订单状态跟踪
- 撤单操作
- CSV导出
"""

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vnpy.event import Event, EventEngine
from vnpy.trader.event import EVENT_ORDER


class OrderMonitor(QWidget):
    """订单监控组件.

    功能：
    - 显示所有委托订单
    - 实时更新订单状态
    - 支持撤单操作
    - 支持CSV导出
    """

    # 信号：请求撤单
    cancel_order_signal = Signal(str)  # orderid

    def __init__(
        self,
        event_engine: Optional[EventEngine] = None,
        gateway_name: str = "",
        parent: Optional[QWidget] = None,
    ):
        """初始化订单监控组件.

        Args:
            event_engine: VnPy事件引擎
            gateway_name: 网关名称（用于过滤）
            parent: 父组件
        """
        super().__init__(parent)
        self.event_engine = event_engine
        self.gateway_name = gateway_name

        # 订单数据缓存 {orderid: order_data}
        self.orders: Dict[str, Dict[str, Any]] = {}

        self._setup_ui()
        self._register_event()

    def _setup_ui(self):
        """设置UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 订单表格
        self.table = QTableWidget(0, 9)
        headers = ["委托号", "合约", "方向", "价格", "数量", "成交", "状态", "时间", "操作"]
        self.table.setHorizontalHeaderLabels(headers)

        # 设置列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(8, 80)

        # 设置选择模式
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)

        layout.addWidget(self.table)

    def _register_event(self):
        """注册事件监听."""
        if self.event_engine:
            self.event_engine.register(EVENT_ORDER, self._process_order_event)

    def _process_order_event(self, event: Event):
        """处理订单事件.

        Args:
            event: 订单事件
        """
        try:
            order = event.data

            # 如果指定了网关名称，则过滤
            if self.gateway_name and hasattr(order, "gateway_name"):
                if order.gateway_name != self.gateway_name:
                    return

            # 提取订单数据
            orderid = getattr(order, "orderid", "")
            if not orderid:
                return

            order_data = {
                "orderid": orderid,
                "symbol": getattr(order, "symbol", ""),
                "vt_symbol": getattr(order, "vt_symbol", ""),
                "direction": self._format_direction(getattr(order, "direction", None)),
                "offset": getattr(order, "offset", None),
                "price": getattr(order, "price", 0.0),
                "volume": getattr(order, "volume", 0),
                "traded": getattr(order, "traded", 0),
                "status": self._format_status(getattr(order, "status", None)),
                "time": getattr(order, "time", ""),
                "gateway_name": getattr(order, "gateway_name", ""),
            }

            # 更新缓存
            self.orders[orderid] = order_data

            # 更新表格
            self._update_table()

        except Exception as e:
            print(f"处理订单事件失败: {e}")

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

    def _format_status(self, status) -> str:
        """格式化状态.

        Args:
            status: 状态枚举

        Returns:
            格式化后的状态字符串
        """
        if status is None:
            return ""

        try:
            from vnpy.trader.constant import Status

            status_map = {
                Status.SUBMITTING: "提交中",
                Status.NOTTRADED: "未成交",
                Status.PARTTRADED: "部分成交",
                Status.ALLTRADED: "全部成交",
                Status.CANCELLED: "已撤销",
                Status.REJECTED: "已拒绝",
            }
            return status_map.get(status, str(status.value))
        except Exception:
            return str(status)

    def _update_table(self):
        """更新表格显示."""
        # 保存当前选中行
        current_row = self.table.currentRow()

        # 清空并重建表格
        self.table.setRowCount(0)

        # 按时间倒序排序（最新的在前）
        sorted_orders = sorted(self.orders.values(), key=lambda x: x.get("time", ""), reverse=True)

        for row, order in enumerate(sorted_orders):
            self.table.insertRow(row)

            # 填充数据
            self.table.setItem(row, 0, QTableWidgetItem(order["orderid"]))
            self.table.setItem(row, 1, QTableWidgetItem(order["vt_symbol"]))
            self.table.setItem(row, 2, QTableWidgetItem(order["direction"]))
            self.table.setItem(row, 3, QTableWidgetItem(f"{order['price']:.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(str(order["volume"])))
            self.table.setItem(row, 5, QTableWidgetItem(str(order["traded"])))

            # 状态列（根据状态设置颜色）
            status_item = QTableWidgetItem(order["status"])
            if "成交" in order["status"]:
                status_item.setForeground(Qt.GlobalColor.green)
            elif "撤销" in order["status"] or "拒绝" in order["status"]:
                status_item.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, 6, status_item)

            self.table.setItem(row, 7, QTableWidgetItem(order["time"]))

            # 操作按钮（撤单）
            if "未成交" in order["status"] or "部分成交" in order["status"]:
                cancel_btn = QPushButton("撤单")
                cancel_btn.clicked.connect(
                    lambda checked, oid=order["orderid"]: self._on_cancel_order(oid)
                )
                self.table.setCellWidget(row, 8, cancel_btn)

        # 恢复选中行
        if current_row >= 0 and current_row < self.table.rowCount():
            self.table.setCurrentCell(current_row, 0)

    def _on_cancel_order(self, orderid: str):
        """撤单操作.

        Args:
            orderid: 订单号
        """
        reply = QMessageBox.question(
            self,
            "确认撤单",
            f"确定要撤销订单 {orderid} 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.cancel_order_signal.emit(orderid)

    def clear_data(self):
        """清空数据."""
        self.orders.clear()
        self.table.setRowCount(0)

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
                headers = ["委托号", "合约", "方向", "价格", "数量", "成交", "状态", "时间"]
                writer.writerow(headers)

                # 写入数据
                for order in sorted(
                    self.orders.values(), key=lambda x: x.get("time", ""), reverse=True
                ):
                    writer.writerow(
                        [
                            order["orderid"],
                            order["vt_symbol"],
                            order["direction"],
                            f"{order['price']:.2f}",
                            order["volume"],
                            order["traded"],
                            order["status"],
                            order["time"],
                        ]
                    )

            return True
        except Exception as e:
            print(f"导出CSV失败: {e}")
            return False

    def closeEvent(self, event):
        """关闭事件 - 取消注册事件监听."""
        if self.event_engine:
            self.event_engine.unregister(EVENT_ORDER, self._process_order_event)
        super().closeEvent(event)
