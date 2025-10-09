# -*- coding: utf-8 -*-
"""
期权策略监控组件.

显示期权策略的特定监控数据：
- Delta/Gamma/Vega/Theta希腊字母
- 波动率微笑
- 期权链盈亏
- 隐含波动率
"""

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class OptionMonitorWidget(QWidget):
    """期权策略监控组件."""

    def __init__(self, gateway_name: str, trading_service: Any, parent: Optional[QWidget] = None):
        """初始化期权策略监控组件.

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

        # 希腊字母组
        greeks_group = QGroupBox("希腊字母")
        greeks_layout = QHBoxLayout(greeks_group)

        # Delta
        delta_layout = QVBoxLayout()
        delta_layout.addWidget(QLabel("Delta"))
        self.delta_label = QLabel("--")
        self.delta_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #4ECDC4;")
        delta_layout.addWidget(self.delta_label, alignment=Qt.AlignmentFlag.AlignCenter)
        greeks_layout.addLayout(delta_layout)

        # Gamma
        gamma_layout = QVBoxLayout()
        gamma_layout.addWidget(QLabel("Gamma"))
        self.gamma_label = QLabel("--")
        self.gamma_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #FF6B6B;")
        gamma_layout.addWidget(self.gamma_label, alignment=Qt.AlignmentFlag.AlignCenter)
        greeks_layout.addLayout(gamma_layout)

        # Vega
        vega_layout = QVBoxLayout()
        vega_layout.addWidget(QLabel("Vega"))
        self.vega_label = QLabel("--")
        self.vega_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #FFD93D;")
        vega_layout.addWidget(self.vega_label, alignment=Qt.AlignmentFlag.AlignCenter)
        greeks_layout.addLayout(vega_layout)

        # Theta
        theta_layout = QVBoxLayout()
        theta_layout.addWidget(QLabel("Theta"))
        self.theta_label = QLabel("--")
        self.theta_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #A8E6CF;")
        theta_layout.addWidget(self.theta_label, alignment=Qt.AlignmentFlag.AlignCenter)
        greeks_layout.addLayout(theta_layout)

        layout.addWidget(greeks_group)

        # 波动率信息组
        vol_group = QGroupBox("波动率信息")
        vol_layout = QHBoxLayout(vol_group)

        self.impl_vol_label = QLabel("隐含波动率: --")
        vol_layout.addWidget(self.impl_vol_label)

        self.hist_vol_label = QLabel("历史波动率: --")
        vol_layout.addWidget(self.hist_vol_label)

        self.vol_diff_label = QLabel("波动率差: --")
        vol_layout.addWidget(self.vol_diff_label)

        vol_layout.addStretch()
        layout.addWidget(vol_group)

        # 期权持仓表
        position_group = QGroupBox("期权持仓")
        position_layout = QVBoxLayout(position_group)

        self.position_table = QTableWidget(0, 7)
        headers = ["合约", "方向", "数量", "均价", "现价", "盈亏", "Delta"]
        self.position_table.setHorizontalHeaderLabels(headers)
        self.position_table.horizontalHeader().setStretchLastSection(True)

        position_layout.addWidget(self.position_table)
        layout.addWidget(position_group)

        # 风险指标组
        risk_group = QGroupBox("风险指标")
        risk_layout = QVBoxLayout(risk_group)

        self.risk_table = QTableWidget(0, 2)
        self.risk_table.setHorizontalHeaderLabels(["指标", "值"])
        self.risk_table.horizontalHeader().setStretchLastSection(True)
        self.risk_table.verticalHeader().setVisible(False)

        # 添加初始行
        risks = [
            ("组合Delta", "--"),
            ("组合Gamma", "--"),
            ("最大损失", "--"),
            ("最大收益", "--"),
            ("盈亏平衡点", "--"),
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
            option_data = monitoring_data.get("option_master", {})

            # 更新希腊字母
            greeks = option_data.get("greeks", {})
            self.delta_label.setText(f"{greeks.get('delta', 0):.4f}")
            self.gamma_label.setText(f"{greeks.get('gamma', 0):.4f}")
            self.vega_label.setText(f"{greeks.get('vega', 0):.4f}")
            self.theta_label.setText(f"{greeks.get('theta', 0):.4f}")

            # 更新波动率信息
            impl_vol = option_data.get("implied_volatility", 0)
            hist_vol = option_data.get("historical_volatility", 0)
            vol_diff = impl_vol - hist_vol

            self.impl_vol_label.setText(f"隐含波动率: {impl_vol:.2%}")
            self.hist_vol_label.setText(f"历史波动率: {hist_vol:.2%}")
            self.vol_diff_label.setText(f"波动率差: {vol_diff:+.2%}")

            # 更新期权持仓表
            positions = option_data.get("positions", [])
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
                self.position_table.setItem(i, 5, QTableWidgetItem(f"{pos.get('pnl', 0):+.2f}"))
                self.position_table.setItem(i, 6, QTableWidgetItem(f"{pos.get('delta', 0):.4f}"))

            # 更新风险指标
            risks = option_data.get("risks", {})
            risk_data = [
                ("组合Delta", f"{risks.get('portfolio_delta', 0):.4f}"),
                ("组合Gamma", f"{risks.get('portfolio_gamma', 0):.4f}"),
                ("最大损失", f"{risks.get('max_loss', 0):,.2f}"),
                ("最大收益", f"{risks.get('max_profit', 0):,.2f}"),
                ("盈亏平衡点", f"{risks.get('breakeven', 0):.2f}"),
            ]

            for i, (_, value) in enumerate(risk_data):
                if i < self.risk_table.rowCount():
                    self.risk_table.item(i, 1).setText(value)

        except Exception as e:
            print(f"更新期权监控数据失败: {e}")
