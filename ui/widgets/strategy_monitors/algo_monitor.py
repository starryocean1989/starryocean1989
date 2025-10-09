# -*- coding: utf-8 -*-
"""
算法交易监控组件.

显示算法交易策略的特定监控数据：
- 算法执行进度
- 目标价格 vs 实际价格
- 已成交量 vs 未成交量
- 执行性能统计
"""

from typing import Any, Dict, Optional

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
                    self.stats_table.item(i, 1).setText(value)

        except Exception as e:
            print(f"更新算法交易监控数据失败: {e}")
