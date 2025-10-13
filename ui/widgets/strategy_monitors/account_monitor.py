# -*- coding: utf-8 -*-
"""
资金监控组件 - 基于VnPy BaseMonitor.

显示账户资金情况，支持：
- 实时资金更新
- 资金统计
- 风险指标
- CSV导出
"""

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
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
from vnpy.trader.event import EVENT_ACCOUNT


class AccountMonitor(QWidget):
    """资金监控组件.

    功能：
    - 显示账户资金信息
    - 实时更新资金数据
    - 资金统计和风险指标
    - 支持CSV导出
    """

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

    def _process_account_event(self, event: Event):
        """处理资金事件.

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

            # 更新缓存
            self.accounts[accountid] = account_data

            # 如果只有一个账户或者匹配网关，更新主显示
            if len(self.accounts) == 1 or (
                self.gateway_name and account_data["gateway_name"] == self.gateway_name
            ):
                self._update_main_display(account_data)

            # 更新账户列表
            self._update_accounts_table()

        except Exception as e:
            print(f"处理资金事件失败: {e}")

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
            self.funds_table.item(i, 1).setText(value)

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
            item.setText(value)

            # 风险度高于80%时标红
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
            self.funds_table.item(i, 1).setText("--")

        for i in range(self.risk_table.rowCount()):
            self.risk_table.item(i, 1).setText("--")

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
