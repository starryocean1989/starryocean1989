# -*- coding: utf-8 -*-
"""
持仓监控组件 - 基于VnPy BaseMonitor.

显示当前持仓情况，支持：
- 实时持仓更新
- 持仓盈亏计算
- 持仓统计
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
from vnpy.trader.event import EVENT_POSITION


class PositionMonitor(QWidget):
    """持仓监控组件.

    功能：
    - 显示当前所有持仓
    - 实时更新持仓数据
    - 实时盈亏计算
    - 持仓统计（总持仓、总盈亏）
    - 支持CSV导出
    """

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

    def _process_position_event(self, event: Event):
        """处理持仓事件.

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

            # 更新缓存
            self.positions[vt_positionid] = position_data

            # 更新表格和统计
            self._update_table()
            self._update_statistics()

        except Exception as e:
            print(f"处理持仓事件失败: {e}")

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
