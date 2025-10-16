# -*- coding: utf-8 -*-
"""
组合监控组件集合 - 高级策略监控.

本文件合并了以下组件：
- PortfolioMonitorWidget: 组合策略监控
- AlgoMonitorWidget: 算法交易监控
- OptionMonitorWidget: 期权策略监控
"""

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


# ===== 1. 组合策略监控 =====


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
                    item = self.risk_table.item(i, 1)
                    if item is not None:
                        item.setText(value)

        except Exception as e:
            print(f"更新组合策略监控数据失败: {e}")


# ===== 2. 算法交易监控 =====


class AlgoMonitorWidget(QWidget):
    """算法交易监控组件."""

    def __init__(self, gateway_name: str, trading_service: Any, parent: Optional[QWidget] = None):
        """初始化算法交易监控组件.

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

        # 执行进度组
        progress_group = QGroupBox("算法执行进度")
        progress_layout = QVBoxLayout(progress_group)

        # 进度条
        progress_info_layout = QHBoxLayout()
        progress_info_layout.addWidget(QLabel("执行进度:"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        progress_info_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("0%")
        progress_info_layout.addWidget(self.progress_label)
        progress_layout.addLayout(progress_info_layout)

        # 成交量信息
        volume_layout = QHBoxLayout()
        self.target_volume_label = QLabel("目标数量: --")
        volume_layout.addWidget(self.target_volume_label)

        self.traded_volume_label = QLabel("已成交: --")
        volume_layout.addWidget(self.traded_volume_label)

        self.remaining_volume_label = QLabel("剩余: --")
        volume_layout.addWidget(self.remaining_volume_label)

        volume_layout.addStretch()
        progress_layout.addLayout(volume_layout)

        layout.addWidget(progress_group)

        # 价格信息组
        price_group = QGroupBox("价格信息")
        price_layout = QHBoxLayout(price_group)

        self.target_price_label = QLabel("目标价格: --")
        price_layout.addWidget(self.target_price_label)

        self.avg_price_label = QLabel("平均成交价: --")
        price_layout.addWidget(self.avg_price_label)

        self.slippage_label = QLabel("滑点: --")
        price_layout.addWidget(self.slippage_label)

        price_layout.addStretch()
        layout.addWidget(price_group)

        # 执行统计表
        stats_group = QGroupBox("执行统计")
        stats_layout = QVBoxLayout(stats_group)

        self.stats_table = QTableWidget(0, 2)
        self.stats_table.setHorizontalHeaderLabels(["指标", "值"])
        self.stats_table.horizontalHeader().setStretchLastSection(True)
        self.stats_table.verticalHeader().setVisible(False)

        # 添加初始行
        stats = [
            ("总订单数", "--"),
            ("已完成订单", "--"),
            ("取消订单", "--"),
            ("执行耗时", "--"),
            ("平均延迟", "--"),
        ]

        for i, (metric, value) in enumerate(stats):
            self.stats_table.insertRow(i)
            self.stats_table.setItem(i, 0, QTableWidgetItem(metric))
            self.stats_table.setItem(i, 1, QTableWidgetItem(value))

        stats_layout.addWidget(self.stats_table)
        layout.addWidget(stats_group)

    def update_data(self, monitoring_data: Dict[str, Any]):
        """更新监控数据.

        Args:
            monitoring_data: 监控数据字典
        """
        try:
            algo_data = monitoring_data.get("algo_trading", {})

            # 更新执行进度
            progress = algo_data.get("progress", 0)
            self.progress_bar.setValue(int(progress))
            self.progress_label.setText(f"{progress:.1f}%")

            # 更新成交量信息
            target_volume = algo_data.get("target_volume", 0)
            traded_volume = algo_data.get("traded_volume", 0)
            remaining_volume = target_volume - traded_volume

            self.target_volume_label.setText(f"目标数量: {target_volume:,.0f}")
            self.traded_volume_label.setText(f"已成交: {traded_volume:,.0f}")
            self.remaining_volume_label.setText(f"剩余: {remaining_volume:,.0f}")

            # 更新价格信息
            target_price = algo_data.get("target_price", 0)
            avg_price = algo_data.get("avg_price", 0)
            slippage = avg_price - target_price if target_price > 0 else 0

            self.target_price_label.setText(f"目标价格: {target_price:.2f}")
            self.avg_price_label.setText(f"平均成交价: {avg_price:.2f}")
            self.slippage_label.setText(f"滑点: {slippage:.4f}")

            # 更新执行统计
            stats = algo_data.get("statistics", {})
            stats_data = [
                ("总订单数", str(stats.get("total_orders", "--"))),
                ("已完成订单", str(stats.get("completed_orders", "--"))),
                ("取消订单", str(stats.get("cancelled_orders", "--"))),
                ("执行耗时", f"{stats.get('elapsed_time', '--')} 秒"),
                ("平均延迟", f"{stats.get('avg_latency', '--')} 毫秒"),
            ]

            for i, (_, value) in enumerate(stats_data):
                if i < self.stats_table.rowCount():
                    item = self.stats_table.item(i, 1)
                    if item is not None:
                        item.setText(value)

        except Exception as e:
            print(f"更新算法交易监控数据失败: {e}")


# ===== 3. 期权策略监控 =====


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
                    item = self.risk_table.item(i, 1)
                    if item is not None:
                        item.setText(value)

        except Exception as e:
            print(f"更新期权监控数据失败: {e}")


# ===== 4. 导出 =====

__all__ = [
    "PortfolioMonitorWidget",
    "AlgoMonitorWidget",
    "OptionMonitorWidget",
]

