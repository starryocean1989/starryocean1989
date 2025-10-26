# -*- coding: utf-8 -*-
"""
任务队列监控组件

提供任务队列状态的实时监控和可视化。
"""

import logging
from collections import deque
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QGridLayout
import pyqtgraph as pg

from .widgets import MetricCard


class TaskQueueMonitorWidget(QWidget):
    """任务队列监控组件

    显示任务队列的实时状态，包括：
    - 队列长度
    - 任务吞吐量
    - 平均等待时间
    - 优先级分布
    """

    def __init__(self, parent=None):
        """初始化监控组件

        Args:
            parent: 父组件
        """
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        # 队列管理器引用（在setup时注入）
        self.queue_facade = None

        # 历史数据（用于绘图）
        self.history_size = 100
        self.queue_length_history = deque(maxlen=self.history_size)
        self.throughput_history = deque(maxlen=self.history_size)
        self.timestamp_history = deque(maxlen=self.history_size)

        # 初始化UI
        self._init_ui()

        # 创建监控定时器
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self._update_metrics)
        self.monitor_timer.start(1000)  # 每秒更新

        self.logger.info("✅ TaskQueueMonitorWidget 已初始化")

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 标题
        title_label = QLabel("📊 任务队列监控")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        layout.addWidget(title_label)

        # 指标卡片区域
        metrics_layout = QHBoxLayout()

        # 队列长度卡片
        self.queue_length_card = MetricCard(title="队列长度", value="0", unit="", icon="📦")
        metrics_layout.addWidget(self.queue_length_card)

        # 吞吐量卡片
        self.throughput_card = MetricCard(title="吞吐量", value="0.0", unit="任务/秒", icon="⚡")
        metrics_layout.addWidget(self.throughput_card)

        # 平均等待时间卡片
        self.wait_time_card = MetricCard(title="平均等待", value="0.00", unit="秒", icon="⏱️")
        metrics_layout.addWidget(self.wait_time_card)

        layout.addLayout(metrics_layout)

        # 状态统计区域
        stats_group = QGroupBox("任务统计")
        stats_layout = QGridLayout()

        # 状态标签
        self.total_tasks_label = QLabel("总任务数: 0")
        self.queued_tasks_label = QLabel("排队中: 0")
        self.running_tasks_label = QLabel("执行中: 0")
        self.completed_tasks_label = QLabel("已完成: 0")
        self.failed_tasks_label = QLabel("失败: 0")

        stats_layout.addWidget(self.total_tasks_label, 0, 0)
        stats_layout.addWidget(self.queued_tasks_label, 0, 1)
        stats_layout.addWidget(self.running_tasks_label, 1, 0)
        stats_layout.addWidget(self.completed_tasks_label, 1, 1)
        stats_layout.addWidget(self.failed_tasks_label, 2, 0)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # 历史图表区域
        charts_group = QGroupBox("历史趋势")
        charts_layout = QVBoxLayout()

        # 队列长度图表
        self.queue_plot = pg.PlotWidget(title="队列长度")
        self.queue_plot.setLabel("left", "队列长度")
        self.queue_plot.setLabel("bottom", "时间（秒）")
        self.queue_plot.showGrid(x=True, y=True)
        self.queue_curve = self.queue_plot.plot(pen=pg.mkPen(color="b", width=2))
        self.queue_plot.setFixedHeight(200)
        charts_layout.addWidget(self.queue_plot)

        # 吞吐量图表
        self.throughput_plot = pg.PlotWidget(title="任务吞吐量")
        self.throughput_plot.setLabel("left", "任务/秒")
        self.throughput_plot.setLabel("bottom", "时间（秒）")
        self.throughput_plot.showGrid(x=True, y=True)
        self.throughput_curve = self.throughput_plot.plot(pen=pg.mkPen(color="g", width=2))
        self.throughput_plot.setFixedHeight(200)
        charts_layout.addWidget(self.throughput_plot)

        charts_group.setLayout(charts_layout)
        layout.addWidget(charts_group)

        # 优先级分布区域
        priority_group = QGroupBox("优先级分布")
        priority_layout = QGridLayout()

        self.urgent_label = QLabel("紧急: 0")
        self.high_label = QLabel("高: 0")
        self.normal_label = QLabel("普通: 0")
        self.low_label = QLabel("低: 0")

        priority_layout.addWidget(self.urgent_label, 0, 0)
        priority_layout.addWidget(self.high_label, 0, 1)
        priority_layout.addWidget(self.normal_label, 1, 0)
        priority_layout.addWidget(self.low_label, 1, 1)

        priority_group.setLayout(priority_layout)
        layout.addWidget(priority_group)

        # 添加弹性空间
        layout.addStretch()

    def setup(self, queue_facade):
        """设置队列门面引用

        Args:
            queue_facade: LoadBalancerQueueFacade实例
        """
        self.queue_facade = queue_facade
        self.logger.info("✅ TaskQueueMonitorWidget 已连接到队列门面")

    def _update_metrics(self):
        """更新监控指标（定时器回调）"""
        if not self.queue_facade:
            return

        try:
            # 获取指标
            metrics = self.queue_facade.get_queue_metrics()

            if not metrics:
                return

            # 更新指标卡片
            queue_length = metrics.get("queue_length", 0)
            self.queue_length_card.update_value(str(queue_length))

            throughput = metrics.get("throughput", 0.0)
            self.throughput_card.update_value(f"{throughput:.1f}")

            avg_wait_time = metrics.get("avg_wait_time", 0.0)
            self.wait_time_card.update_value(f"{avg_wait_time:.2f}")

            # 更新状态统计
            total_tasks = metrics.get("total_tasks", 0)
            status_counts = metrics.get("status_counts", {})

            self.total_tasks_label.setText(f"总任务数: {total_tasks}")
            self.queued_tasks_label.setText(f"排队中: {status_counts.get('queued', 0)}")
            self.running_tasks_label.setText(f"执行中: {status_counts.get('running', 0)}")
            self.completed_tasks_label.setText(f"已完成: {status_counts.get('completed', 0)}")
            self.failed_tasks_label.setText(f"失败: {status_counts.get('failed', 0)}")

            # 更新优先级分布
            priority_counts = metrics.get("priority_counts", {})
            self.urgent_label.setText(f"紧急: {priority_counts.get('URGENT', 0)}")
            self.high_label.setText(f"高: {priority_counts.get('HIGH', 0)}")
            self.normal_label.setText(f"普通: {priority_counts.get('NORMAL', 0)}")
            self.low_label.setText(f"低: {priority_counts.get('LOW', 0)}")

            # 更新历史数据
            import time

            current_time = time.time()
            self.queue_length_history.append(queue_length)
            self.throughput_history.append(throughput)
            self.timestamp_history.append(current_time)

            # 更新图表
            self._update_charts()

        except Exception as e:
            self.logger.error(f"❌ 更新指标失败: {e}", exc_info=True)

    def _update_charts(self):
        """更新历史图表"""
        if len(self.timestamp_history) < 2:
            return

        # 计算相对时间（秒）
        base_time = self.timestamp_history[0]
        relative_times = [t - base_time for t in self.timestamp_history]

        # 更新队列长度图表
        self.queue_curve.setData(relative_times, list(self.queue_length_history))

        # 更新吞吐量图表
        self.throughput_curve.setData(relative_times, list(self.throughput_history))

    def clear_history(self):
        """清除历史数据"""
        self.queue_length_history.clear()
        self.throughput_history.clear()
        self.timestamp_history.clear()
        self.logger.info("✅ 历史数据已清除")
