# -*- coding: utf-8 -*-
"""
组合策略监控组件.

显示组合策略（单策略多品种）的特定监控数据：
- 多品种持仓分布图表
- 各品种盈亏贡献
- 品种相关性
- 风险敞口分析
"""

from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class PortfolioMonitorWidget(QWidget):
    """组合策略监控组件."""

    def __init__(self, gateway_name: str, trading_service: Any, parent: Optional[QWidget] = None):
        """初始化组合策略监控组件.

        Args:
            gateway_name: 网关名称
            trading_service: 交易网关服务
            parent: 父组件
        """
        super().__init__(parent)
        self.gateway_name = gateway_name
        self.trading_service = trading_service

        self._setup_ui()

    def _setup_ui(self):
        """设置UI."""
        layout = QVBoxLayout(self)

        # 持仓概览组
        overview_group = QGroupBox("持仓概览")
        overview_layout = QHBoxLayout(overview_group)

        self.total_symbols_label = QLabel("品种数量: --")
        overview_layout.addWidget(self.total_symbols_label)

        self.total_value_label = QLabel("总市值: --")
        overview_layout.addWidget(self.total_value_label)

        self.total_pnl_label = QLabel("总盈亏: --")
        overview_layout.addWidget(self.total_pnl_label)

        overview_layout.addStretch()
        layout.addWidget(overview_group)

        # 品种持仓表
        position_group = QGroupBox("品种持仓明细")
        position_layout = QVBoxLayout(position_group)

        self.position_table = QTableWidget(0, 8)
        headers = ["品种", "方向", "数量", "均价", "现价", "市值", "盈亏", "权重"]
        self.position_table.setHorizontalHeaderLabels(headers)
        self.position_table.horizontalHeader().setStretchLastSection(True)

        position_layout.addWidget(self.position_table)
        layout.addWidget(position_group)

        # 盈亏贡献表
        contrib_group = QGroupBox("盈亏贡献分析")
        contrib_layout = QVBoxLayout(contrib_group)

        self.contrib_table = QTableWidget(0, 4)
        headers = ["品种", "盈亏", "贡献率", "收益率"]
        self.contrib_table.setHorizontalHeaderLabels(headers)
        self.contrib_table.horizontalHeader().setStretchLastSection(True)

        contrib_layout.addWidget(self.contrib_table)
        layout.addWidget(contrib_group)

        # 风险指标组
        risk_group = QGroupBox("风险指标")
        risk_layout = QVBoxLayout(risk_group)

        self.risk_table = QTableWidget(0, 2)
        self.risk_table.setHorizontalHeaderLabels(["指标", "值"])
        self.risk_table.horizontalHeader().setStretchLastSection(True)
        self.risk_table.verticalHeader().setVisible(False)

        # 添加初始行
        risks = [
            ("组合波动率", "--"),
            ("最大回撤", "--"),
            ("夏普比率", "--"),
            ("Beta系数", "--"),
            ("集中度", "--"),
        ]

        for i, (metric, value) in enumerate(risks):
            self.risk_table.insertRow(i)
            self.risk_table.setItem(i, 0, QTableWidgetItem(metric))
            self.risk_table.setItem(i, 1, QTableWidgetItem(value))

        risk_layout.addWidget(self.risk_table)
        layout.addWidget(risk_group)

    def update_data(self, monitoring_data: Dict[str, Any]):
        """更新监控数据.

        Args:
            monitoring_data: 监控数据字典
        """
        try:
            portfolio_data = monitoring_data.get("portfolio_strategy", {})

            # 更新持仓概览
            overview = portfolio_data.get("overview", {})
            self.total_symbols_label.setText(f"品种数量: {overview.get('symbol_count', 0)}")
            self.total_value_label.setText(f"总市值: {overview.get('total_value', 0):,.2f}")

            total_pnl = overview.get("total_pnl", 0)
            pnl_color = "#4ECDC4" if total_pnl >= 0 else "#FF6B6B"
            self.total_pnl_label.setText(f"总盈亏: {total_pnl:+,.2f}")
            self.total_pnl_label.setStyleSheet(f"color: {pnl_color}; font-weight: bold;")

            # 更新品种持仓表
            positions = portfolio_data.get("positions", [])
            self.position_table.setRowCount(len(positions))

            for i, pos in enumerate(positions):
                self.position_table.setItem(i, 0, QTableWidgetItem(pos.get("symbol", "")))
                self.position_table.setItem(i, 1, QTableWidgetItem(pos.get("direction", "")))
                self.position_table.setItem(i, 2, QTableWidgetItem(str(pos.get("volume", 0))))
                self.position_table.setItem(
                    i, 3, QTableWidgetItem(f"{pos.get('avg_price', 0):.2f}")
                )
                self.position_table.setItem(
                    i, 4, QTableWidgetItem(f"{pos.get('last_price', 0):.2f}")
                )
                self.position_table.setItem(
                    i, 5, QTableWidgetItem(f"{pos.get('market_value', 0):,.2f}")
                )
                self.position_table.setItem(i, 6, QTableWidgetItem(f"{pos.get('pnl', 0):+,.2f}"))
                self.position_table.setItem(i, 7, QTableWidgetItem(f"{pos.get('weight', 0):.2%}"))

            # 更新盈亏贡献表
            contributions = portfolio_data.get("contributions", [])
            self.contrib_table.setRowCount(len(contributions))

            for i, contrib in enumerate(contributions):
                self.contrib_table.setItem(i, 0, QTableWidgetItem(contrib.get("symbol", "")))
                self.contrib_table.setItem(i, 1, QTableWidgetItem(f"{contrib.get('pnl', 0):+,.2f}"))
                self.contrib_table.setItem(
                    i, 2, QTableWidgetItem(f"{contrib.get('contribution', 0):.2%}")
                )
                self.contrib_table.setItem(
                    i, 3, QTableWidgetItem(f"{contrib.get('return', 0):+.2%}")
                )

            # 更新风险指标
            risks = portfolio_data.get("risks", {})
            risk_data = [
                ("组合波动率", f"{risks.get('volatility', 0):.2%}"),
                ("最大回撤", f"{risks.get('max_drawdown', 0):.2%}"),
                ("夏普比率", f"{risks.get('sharpe_ratio', 0):.2f}"),
                ("Beta系数", f"{risks.get('beta', 0):.2f}"),
                ("集中度", f"{risks.get('concentration', 0):.2%}"),
            ]

            for i, (_, value) in enumerate(risk_data):
                if i < self.risk_table.rowCount():
                    self.risk_table.item(i, 1).setText(value)

        except Exception as e:
            print(f"更新组合策略监控数据失败: {e}")
