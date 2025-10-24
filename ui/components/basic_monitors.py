# -*- coding: utf-8 -*-
"""
基础监控组件集合 - VnPy交易监控.

本文件合并了以下组件：
- OrderMonitor: 订单监控
- TradeMonitor: 成交监控
- PositionMonitor: 持仓监控
- AccountMonitor: 资金监控
"""

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vnpy.event import Event, EventEngine
from vnpy.trader.event import EVENT_ORDER, EVENT_TRADE, EVENT_POSITION, EVENT_ACCOUNT


# ===== 1. 订单监控 =====


class OrderMonitor(QWidget):
    """订单监控组件.

    功能：
    - 显示所有委托订单
    - 实时更新订单状态
    - 支持撤单操作
    - 支持CSV导出
    """

    # ✅ 线程安全修复：Signal 必须定义为类属性
    cancel_order_signal = Signal(str)  # orderid - 请求撤单信号
    order_event_signal = Signal(dict)  # 订单事件信号

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

            # ✅ 线程安全修复：连接信号到 UI 更新槽函数
            self.order_event_signal.connect(self._update_order_ui)

    def _process_order_event(self, event: Event):
        """处理订单事件（EventEngine 工作线程）.

        ✅ 线程安全修复：此函数在 EventEngine 工作线程中执行，
        不能直接更新 UI，只发射信号让 Qt 主线程处理。

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

            # ✅ 只发射信号，不做任何 UI 操作（线程安全）
            self.order_event_signal.emit(order_data)

        except Exception as e:
            print(f"发射订单事件信号失败: {e}")

    def _update_order_ui(self, order_data: dict):
        """更新订单 UI（Qt 主线程，线程安全）.

        Args:
            order_data: 订单数据字典
        """
        try:
            # ✅ 所有 UI 操作都在主线程，线程安全！

            # 更新缓存
            orderid = order_data["orderid"]
            self.orders[orderid] = order_data

            # 更新表格
            self._update_table()

        except Exception as e:
            print(f"更新订单 UI 失败: {e}")

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


# ===== 2. 成交监控 =====


class TradeMonitor(QWidget):
    """成交监控组件.

    功能：
    - 显示所有成交记录
    - 实时更新成交数据
    - 成交统计（总成交量、总成交额、成交均价）
    - 支持CSV导出
    """

    # ✅ 线程安全修复：Signal 必须定义为类属性
    trade_event_signal = Signal(dict)  # 成交事件信号

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

            # ✅ 线程安全修复：连接信号到 UI 更新槽函数
            self.trade_event_signal.connect(self._update_trade_ui)

    def _process_trade_event(self, event: Event):
        """处理成交事件（EventEngine 工作线程）.

        ✅ 线程安全修复：此函数在 EventEngine 工作线程中执行，
        不能直接更新 UI，只发射信号让 Qt 主线程处理。

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

            # ✅ 只发射信号，不做任何 UI 操作（线程安全）
            self.trade_event_signal.emit(trade_data)

        except Exception as e:
            print(f"发射成交事件信号失败: {e}")

    def _update_trade_ui(self, trade_data: dict):
        """更新成交 UI（Qt 主线程，线程安全）.

        Args:
            trade_data: 成交数据字典
        """
        try:
            # ✅ 所有 UI 操作都在主线程，线程安全！

            # 更新缓存
            tradeid = trade_data["tradeid"]
            self.trades[tradeid] = trade_data

            # 更新表格和统计
            self._update_table()
            self._update_statistics()

        except Exception as e:
            print(f"更新成交 UI 失败: {e}")

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


# ===== 3. 持仓监控 =====


class PositionMonitor(QWidget):
    """持仓监控组件.

    功能：
    - 显示当前所有持仓
    - 实时更新持仓数据
    - 实时盈亏计算
    - 持仓统计（总持仓、总盈亏）
    - 支持CSV导出
    """

    # ✅ 线程安全修复：Signal 必须定义为类属性
    position_event_signal = Signal(dict)  # 持仓事件信号

    def __init__(
        self,
        event_engine: Optional[EventEngine] = None,
        gateway_name: str = "",
        parent: Optional[QWidget] = None,
    ):
        """初始化持仓监控组件.

        Args:
            event_engine: VnPy事件引擎
            gateway_name: 网关名称（用于过滤）
            parent: 父组件
        """
        super().__init__(parent)
        self.event_engine = event_engine
        self.gateway_name = gateway_name

        # 持仓数据缓存 {vt_positionid: position_data}
        self.positions: Dict[str, Dict[str, Any]] = {}

        self._setup_ui()
        self._register_event()

    def _setup_ui(self):
        """设置UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 统计信息组
        stats_group = QGroupBox("持仓统计")
        stats_layout = QHBoxLayout(stats_group)

        self.position_count_label = QLabel("持仓品种: 0")
        stats_layout.addWidget(self.position_count_label)

        self.total_volume_label = QLabel("总持仓量: 0")
        stats_layout.addWidget(self.total_volume_label)

        self.total_pnl_label = QLabel("总盈亏: 0.00")
        stats_layout.addWidget(self.total_pnl_label)

        self.total_value_label = QLabel("总市值: 0.00")
        stats_layout.addWidget(self.total_value_label)

        stats_layout.addStretch()
        layout.addWidget(stats_group)

        # 持仓表格
        self.table = QTableWidget(0, 10)
        headers = [
            "合约",
            "方向",
            "持仓量",
            "可用量",
            "冻结量",
            "均价",
            "现价",
            "盈亏",
            "盈亏比",
            "更新时间",
        ]
        self.table.setHorizontalHeaderLabels(headers)

        # 设置列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)

        # 设置选择模式
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)

        layout.addWidget(self.table)

    def _register_event(self):
        """注册事件监听."""
        if self.event_engine:
            self.event_engine.register(EVENT_POSITION, self._process_position_event)

            # ✅ 线程安全修复：连接信号到 UI 更新槽函数
            self.position_event_signal.connect(self._update_position_ui)

    def _process_position_event(self, event: Event):
        """处理持仓事件（EventEngine 工作线程）.

        ✅ 线程安全修复：此函数在 EventEngine 工作线程中执行，
        不能直接更新 UI，只发射信号让 Qt 主线程处理。

        Args:
            event: 持仓事件
        """
        try:
            position = event.data

            # 如果指定了网关名称，则过滤
            if self.gateway_name and hasattr(position, "gateway_name"):
                if position.gateway_name != self.gateway_name:
                    return

            # 提取持仓数据
            vt_positionid = getattr(position, "vt_positionid", "")
            if not vt_positionid:
                return

            volume = getattr(position, "volume", 0)
            price = getattr(position, "price", 0.0)
            pnl = getattr(position, "pnl", 0.0)

            # 计算盈亏比
            pnl_ratio = (pnl / (price * volume * 100)) * 100 if (price * volume) > 0 else 0.0

            position_data = {
                "vt_positionid": vt_positionid,
                "vt_symbol": getattr(position, "vt_symbol", ""),
                "direction": self._format_direction(getattr(position, "direction", None)),
                "volume": volume,
                "frozen": getattr(position, "frozen", 0),
                "available": volume - getattr(position, "frozen", 0),
                "price": price,
                "last_price": getattr(position, "last_price", 0.0) or price,
                "pnl": pnl,
                "pnl_ratio": pnl_ratio,
                "yd_volume": getattr(position, "yd_volume", 0),
                "gateway_name": getattr(position, "gateway_name", ""),
            }

            # ✅ 只发射信号，不做任何 UI 操作（线程安全）
            self.position_event_signal.emit(position_data)

        except Exception as e:
            print(f"发射持仓事件信号失败: {e}")

    def _update_position_ui(self, position_data: dict):
        """更新持仓 UI（Qt 主线程，线程安全）.

        Args:
            position_data: 持仓数据字典
        """
        try:
            # ✅ 所有 UI 操作都在主线程，线程安全！

            # 更新缓存
            vt_positionid = position_data["vt_positionid"]
            self.positions[vt_positionid] = position_data

            # 更新表格和统计
            self._update_table()
            self._update_statistics()

        except Exception as e:
            print(f"更新持仓 UI 失败: {e}")

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
            elif direction == Direction.NET:
                return "净"
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

        # 按合约排序
        sorted_positions = sorted(self.positions.values(), key=lambda x: x.get("vt_symbol", ""))

        for row, pos in enumerate(sorted_positions):
            # 跳过零持仓
            if pos["volume"] == 0:
                continue

            self.table.insertRow(row)

            # 填充数据
            self.table.setItem(row, 0, QTableWidgetItem(pos["vt_symbol"]))

            # 方向列（根据方向设置颜色）
            direction_item = QTableWidgetItem(pos["direction"])
            if pos["direction"] == "多":
                direction_item.setForeground(Qt.GlobalColor.red)
            elif pos["direction"] == "空":
                direction_item.setForeground(Qt.GlobalColor.green)
            self.table.setItem(row, 1, direction_item)

            self.table.setItem(row, 2, QTableWidgetItem(str(pos["volume"])))
            self.table.setItem(row, 3, QTableWidgetItem(str(pos["available"])))
            self.table.setItem(row, 4, QTableWidgetItem(str(pos["frozen"])))
            self.table.setItem(row, 5, QTableWidgetItem(f"{pos['price']:.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{pos['last_price']:.2f}"))

            # 盈亏列（根据正负设置颜色）
            pnl_item = QTableWidgetItem(f"{pos['pnl']:+,.2f}")
            pnl_color = Qt.GlobalColor.red if pos["pnl"] >= 0 else Qt.GlobalColor.green
            pnl_item.setForeground(pnl_color)
            self.table.setItem(row, 7, pnl_item)

            # 盈亏比列
            ratio_item = QTableWidgetItem(f"{pos['pnl_ratio']:+.2f}%")
            ratio_item.setForeground(pnl_color)
            self.table.setItem(row, 8, ratio_item)

            # 时间列（使用当前时间）
            import datetime

            current_time = datetime.datetime.now().strftime("%H:%M:%S")
            self.table.setItem(row, 9, QTableWidgetItem(current_time))

        # 恢复选中行
        if current_row >= 0 and current_row < self.table.rowCount():
            self.table.setCurrentCell(current_row, 0)

    def _update_statistics(self):
        """更新统计信息."""
        # 过滤掉零持仓
        active_positions = [p for p in self.positions.values() if p["volume"] > 0]

        position_count = len(active_positions)
        total_volume = sum(p["volume"] for p in active_positions)
        total_pnl = sum(p["pnl"] for p in active_positions)
        total_value = sum(p["volume"] * p["last_price"] for p in active_positions)

        # 更新标签
        self.position_count_label.setText(f"持仓品种: {position_count}")
        self.total_volume_label.setText(f"总持仓量: {total_volume:,}")

        # 总盈亏（根据正负设置颜色）
        pnl_color = "#FF5252" if total_pnl >= 0 else "#4CAF50"
        self.total_pnl_label.setText(f"总盈亏: {total_pnl:+,.2f}")
        self.total_pnl_label.setStyleSheet(f"color: {pnl_color}; font-weight: bold;")

        self.total_value_label.setText(f"总市值: {total_value:,.2f}")

    def clear_data(self):
        """清空数据."""
        self.positions.clear()
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
                headers = [
                    "合约",
                    "方向",
                    "持仓量",
                    "可用量",
                    "冻结量",
                    "均价",
                    "现价",
                    "盈亏",
                    "盈亏比",
                ]
                writer.writerow(headers)

                # 写入数据
                for pos in sorted(self.positions.values(), key=lambda x: x.get("vt_symbol", "")):
                    if pos["volume"] == 0:
                        continue

                    writer.writerow(
                        [
                            pos["vt_symbol"],
                            pos["direction"],
                            pos["volume"],
                            pos["available"],
                            pos["frozen"],
                            f"{pos['price']:.2f}",
                            f"{pos['last_price']:.2f}",
                            f"{pos['pnl']:+,.2f}",
                            f"{pos['pnl_ratio']:+.2f}%",
                        ]
                    )

            return True
        except Exception as e:
            print(f"导出CSV失败: {e}")
            return False

    def closeEvent(self, event):
        """关闭事件 - 取消注册事件监听."""
        if self.event_engine:
            self.event_engine.unregister(EVENT_POSITION, self._process_position_event)
        super().closeEvent(event)


# ===== 4. 资金监控 =====


class AccountMonitor(QWidget):
    """资金监控组件.

    功能：
    - 显示账户资金信息
    - 实时更新资金数据
    - 资金统计和风险指标
    - 支持CSV导出
    """

    # ✅ 线程安全修复：Signal 必须定义为类属性
    account_event_signal = Signal(dict)  # 资金事件信号

    def __init__(
        self,
        event_engine: Optional[EventEngine] = None,
        gateway_name: str = "",
        parent: Optional[QWidget] = None,
    ):
        """初始化资金监控组件.

        Args:
            event_engine: VnPy事件引擎
            gateway_name: 网关名称（用于过滤）
            parent: 父组件
        """
        super().__init__(parent)
        self.event_engine = event_engine
        self.gateway_name = gateway_name

        # 资金数据缓存 {accountid: account_data}
        self.accounts: Dict[str, Dict[str, Any]] = {}

        self._setup_ui()
        self._register_event()

    def _setup_ui(self):
        """设置UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 资金概览组（大字体显示核心指标）
        overview_group = QGroupBox("资金概览")
        overview_layout = QGridLayout(overview_group)

        # 第一行：余额和可用
        self.balance_label = QLabel("--")
        self.balance_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #2196F3;")
        overview_layout.addWidget(QLabel("账户余额:"), 0, 0)
        overview_layout.addWidget(self.balance_label, 0, 1)

        self.available_label = QLabel("--")
        self.available_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #4CAF50;")
        overview_layout.addWidget(QLabel("可用资金:"), 0, 2)
        overview_layout.addWidget(self.available_label, 0, 3)

        # 第二行：冻结和盈亏
        self.frozen_label = QLabel("--")
        self.frozen_label.setStyleSheet("font-size: 20px; color: #FF9800;")
        overview_layout.addWidget(QLabel("冻结资金:"), 1, 0)
        overview_layout.addWidget(self.frozen_label, 1, 1)

        self.pnl_label = QLabel("--")
        self.pnl_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        overview_layout.addWidget(QLabel("持仓盈亏:"), 1, 2)
        overview_layout.addWidget(self.pnl_label, 1, 3)

        layout.addWidget(overview_group)

        # 详细信息组
        details_group = QGroupBox("详细信息")
        details_layout = QHBoxLayout(details_group)

        # 左侧：资金详情
        funds_group = QGroupBox("资金详情")
        funds_layout = QVBoxLayout(funds_group)

        self.funds_table = QTableWidget(0, 2)
        self.funds_table.setHorizontalHeaderLabels(["项目", "金额"])
        header = self.funds_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.funds_table.verticalHeader().setVisible(False)
        self.funds_table.setMaximumHeight(200)

        # 初始化资金明细行
        fund_items = [
            ("初始资金", "--"),
            ("账户余额", "--"),
            ("可用资金", "--"),
            ("冻结资金", "--"),
            ("持仓保证金", "--"),
            ("持仓盈亏", "--"),
        ]

        for i, (name, value) in enumerate(fund_items):
            self.funds_table.insertRow(i)
            self.funds_table.setItem(i, 0, QTableWidgetItem(name))
            self.funds_table.setItem(i, 1, QTableWidgetItem(value))

        funds_layout.addWidget(self.funds_table)
        details_layout.addWidget(funds_group)

        # 右侧：风险指标
        risk_group = QGroupBox("风险指标")
        risk_layout = QVBoxLayout(risk_group)

        self.risk_table = QTableWidget(0, 2)
        self.risk_table.setHorizontalHeaderLabels(["指标", "值"])
        header = self.risk_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.risk_table.verticalHeader().setVisible(False)
        self.risk_table.setMaximumHeight(200)

        # 初始化风险指标行
        risk_items = [
            ("资金使用率", "--"),
            ("保证金占用率", "--"),
            ("盈亏比率", "--"),
            ("风险度", "--"),
        ]

        for i, (name, value) in enumerate(risk_items):
            self.risk_table.insertRow(i)
            self.risk_table.setItem(i, 0, QTableWidgetItem(name))
            self.risk_table.setItem(i, 1, QTableWidgetItem(value))

        risk_layout.addWidget(self.risk_table)
        details_layout.addWidget(risk_group)

        layout.addWidget(details_group)

        # 账户列表组（支持多账户）
        accounts_group = QGroupBox("账户列表")
        accounts_layout = QVBoxLayout(accounts_group)

        self.accounts_table = QTableWidget(0, 6)
        headers = ["账户ID", "余额", "可用", "冻结", "盈亏", "网关"]
        self.accounts_table.setHorizontalHeaderLabels(headers)
        header = self.accounts_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.accounts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.accounts_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.accounts_table.setAlternatingRowColors(True)

        accounts_layout.addWidget(self.accounts_table)
        layout.addWidget(accounts_group)

    def _register_event(self):
        """注册事件监听."""
        if self.event_engine:
            self.event_engine.register(EVENT_ACCOUNT, self._process_account_event)

            # ✅ 线程安全修复：连接信号到 UI 更新槽函数
            self.account_event_signal.connect(self._update_account_ui)

    def _process_account_event(self, event: Event):
        """处理资金事件（EventEngine 工作线程）.

        ✅ 线程安全修复：此函数在 EventEngine 工作线程中执行，
        不能直接更新 UI，只发射信号让 Qt 主线程处理。

        Args:
            event: 资金事件
        """
        try:
            account = event.data

            # 如果指定了网关名称，则过滤
            if self.gateway_name and hasattr(account, "gateway_name"):
                if account.gateway_name != self.gateway_name:
                    return

            # 提取资金数据
            accountid = getattr(account, "accountid", "")
            if not accountid:
                return

            balance = getattr(account, "balance", 0.0)
            frozen = getattr(account, "frozen", 0.0)
            available = getattr(account, "available", 0.0) or (balance - frozen)

            account_data = {
                "accountid": accountid,
                "vt_accountid": getattr(account, "vt_accountid", ""),
                "balance": balance,
                "frozen": frozen,
                "available": available,
                "holding_profit": getattr(account, "holding_profit", 0.0),
                "position_profit": getattr(account, "position_profit", 0.0),
                "margin": getattr(account, "margin", 0.0),
                "gateway_name": getattr(account, "gateway_name", ""),
            }

            # ✅ 只发射信号，不做任何 UI 操作（线程安全）
            self.account_event_signal.emit(account_data)

        except Exception as e:
            print(f"发射资金事件信号失败: {e}")

    def _update_account_ui(self, account_data: dict):
        """更新资金 UI（Qt 主线程，线程安全）.

        Args:
            account_data: 资金数据字典
        """
        try:
            # ✅ 所有 UI 操作都在主线程，线程安全！
            # 更新缓存
            accountid = account_data["accountid"]
            self.accounts[accountid] = account_data

            # 如果只有一个账户或者匹配网关，更新主显示
            if len(self.accounts) == 1 or (
                self.gateway_name and account_data["gateway_name"] == self.gateway_name
            ):
                self._update_main_display(account_data)

            # 更新账户列表
            self._update_accounts_table()

        except Exception as e:
            print(f"更新资金 UI 失败: {e}")

    def _update_main_display(self, account_data: Dict[str, Any]):
        """更新主显示区域.

        Args:
            account_data: 账户数据
        """
        # 更新概览
        balance = account_data["balance"]
        available = account_data["available"]
        frozen = account_data["frozen"]
        pnl = account_data.get("holding_profit", 0.0) or account_data.get("position_profit", 0.0)

        self.balance_label.setText(f"{balance:,.2f}")
        self.available_label.setText(f"{available:,.2f}")
        self.frozen_label.setText(f"{frozen:,.2f}")

        # 盈亏显示（根据正负设置颜色）
        pnl_color = "#F44336" if pnl >= 0 else "#4CAF50"
        self.pnl_label.setText(f"{pnl:+,.2f}")
        self.pnl_label.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {pnl_color};")

        # 更新资金详情表
        fund_values = [
            ("初始资金", f"{balance - pnl:,.2f}"),
            ("账户余额", f"{balance:,.2f}"),
            ("可用资金", f"{available:,.2f}"),
            ("冻结资金", f"{frozen:,.2f}"),
            ("持仓保证金", f"{account_data.get('margin', 0.0):,.2f}"),
            ("持仓盈亏", f"{pnl:+,.2f}"),
        ]

        for i, (_, value) in enumerate(fund_values):
            item = self.funds_table.item(i, 1)
            if item is not None:
                item.setText(value)

        # 计算并更新风险指标
        margin = account_data.get("margin", 0.0)
        used_ratio = (frozen / balance * 100) if balance > 0 else 0
        margin_ratio = (margin / balance * 100) if balance > 0 else 0
        pnl_ratio = (pnl / (balance - pnl) * 100) if (balance - pnl) > 0 else 0
        risk_level = margin_ratio + used_ratio

        risk_values = [
            ("资金使用率", f"{used_ratio:.2f}%"),
            ("保证金占用率", f"{margin_ratio:.2f}%"),
            ("盈亏比率", f"{pnl_ratio:+.2f}%"),
            ("风险度", f"{risk_level:.2f}%"),
        ]

        for i, (_, value) in enumerate(risk_values):
            item = self.risk_table.item(i, 1)
            if item is not None:
                item.setText(value)

            # 风险度高于80%时标红
            if item is not None:
                if i == 3 and risk_level > 80:
                    item.setForeground(Qt.GlobalColor.red)
                else:
                    item.setForeground(Qt.GlobalColor.black)

    def _update_accounts_table(self):
        """更新账户列表表格."""
        self.accounts_table.setRowCount(0)

        for row, (accountid, acc) in enumerate(self.accounts.items()):
            self.accounts_table.insertRow(row)

            self.accounts_table.setItem(row, 0, QTableWidgetItem(accountid))
            self.accounts_table.setItem(row, 1, QTableWidgetItem(f"{acc['balance']:,.2f}"))
            self.accounts_table.setItem(row, 2, QTableWidgetItem(f"{acc['available']:,.2f}"))
            self.accounts_table.setItem(row, 3, QTableWidgetItem(f"{acc['frozen']:,.2f}"))

            # 盈亏列（根据正负设置颜色）
            pnl = acc.get("holding_profit", 0.0) or acc.get("position_profit", 0.0)
            pnl_item = QTableWidgetItem(f"{pnl:+,.2f}")
            pnl_color = Qt.GlobalColor.red if pnl >= 0 else Qt.GlobalColor.green
            pnl_item.setForeground(pnl_color)
            self.accounts_table.setItem(row, 4, pnl_item)

            self.accounts_table.setItem(row, 5, QTableWidgetItem(acc["gateway_name"]))

    def clear_data(self):
        """清空数据."""
        self.accounts.clear()
        self.accounts_table.setRowCount(0)

        # 重置主显示
        self.balance_label.setText("--")
        self.available_label.setText("--")
        self.frozen_label.setText("--")
        self.pnl_label.setText("--")

        # 重置详情表
        for i in range(self.funds_table.rowCount()):
            item = self.funds_table.item(i, 1)
            if item is not None:
                item.setText("--")

        for i in range(self.risk_table.rowCount()):
            item = self.risk_table.item(i, 1)
            if item is not None:
                item.setText("--")

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
                headers = ["账户ID", "余额", "可用", "冻结", "盈亏", "保证金", "网关"]
                writer.writerow(headers)

                # 写入数据
                for accountid, acc in self.accounts.items():
                    pnl = acc.get("holding_profit", 0.0) or acc.get("position_profit", 0.0)
                    writer.writerow(
                        [
                            accountid,
                            f"{acc['balance']:.2f}",
                            f"{acc['available']:.2f}",
                            f"{acc['frozen']:.2f}",
                            f"{pnl:+.2f}",
                            f"{acc.get('margin', 0.0):.2f}",
                            acc["gateway_name"],
                        ]
                    )

            return True
        except Exception as e:
            print(f"导出CSV失败: {e}")
            return False

    def closeEvent(self, event):
        """关闭事件 - 取消注册事件监听."""
        if self.event_engine:
            self.event_engine.unregister(EVENT_ACCOUNT, self._process_account_event)
        super().closeEvent(event)


# ===== 5. 导出 =====

__all__ = [
    "OrderMonitor",
    "TradeMonitor",
    "PositionMonitor",
    "AccountMonitor",
]

