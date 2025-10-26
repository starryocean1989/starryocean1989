# -*- coding: utf-8 -*-
"""
资源限制配置组件

提供资源限制参数的配置界面。
"""

import logging
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QSlider,
    QSpinBox,
    QCheckBox,
    QFormLayout,
    QPushButton,
)
import psutil


class ResourceLimitConfigWidget(QWidget):
    """资源限制配置组件

    提供资源限制参数的配置界面，包括：
    - 小任务CPU/内存限制
    - 大任务CPU/内存限制
    - 任务规模阈值
    - 实时资源使用显示
    """

    # 信号：配置已更改
    config_changed = Signal(dict)

    def __init__(self, parent=None):
        """初始化配置组件

        Args:
            parent: 父组件
        """
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        # 资源限制器引用（在setup时注入）
        self.resource_limiter = None

        # 初始化UI
        self._init_ui()

        self.logger.info("✅ ResourceLimitConfigWidget 已初始化")

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 标题
        title_label = QLabel("⚙️ 资源限制配置")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        layout.addWidget(title_label)

        # 小任务限制配置
        small_task_group = QGroupBox("小任务资源限制 (<1000单元)")
        small_task_layout = QFormLayout()

        # CPU限制
        self.small_cpu_slider = QSlider(Qt.Horizontal)
        self.small_cpu_slider.setRange(10, 100)
        self.small_cpu_slider.setValue(30)
        self.small_cpu_slider.setTickPosition(QSlider.TicksBelow)
        self.small_cpu_slider.setTickInterval(10)
        self.small_cpu_value_label = QLabel("30%")
        self.small_cpu_slider.valueChanged.connect(
            lambda v: self.small_cpu_value_label.setText(f"{v}%")
        )

        cpu_layout = QHBoxLayout()
        cpu_layout.addWidget(self.small_cpu_slider)
        cpu_layout.addWidget(self.small_cpu_value_label)
        small_task_layout.addRow("CPU限制:", cpu_layout)

        # 内存限制
        self.small_memory_slider = QSlider(Qt.Horizontal)
        self.small_memory_slider.setRange(10, 100)
        self.small_memory_slider.setValue(50)
        self.small_memory_slider.setTickPosition(QSlider.TicksBelow)
        self.small_memory_slider.setTickInterval(10)
        self.small_memory_value_label = QLabel("50%")
        self.small_memory_slider.valueChanged.connect(
            lambda v: self.small_memory_value_label.setText(f"{v}%")
        )

        memory_layout = QHBoxLayout()
        memory_layout.addWidget(self.small_memory_slider)
        memory_layout.addWidget(self.small_memory_value_label)
        small_task_layout.addRow("内存限制:", memory_layout)

        small_task_group.setLayout(small_task_layout)
        layout.addWidget(small_task_group)

        # 大任务限制配置
        large_task_group = QGroupBox("大任务资源限制 (≥1000单元)")
        large_task_layout = QFormLayout()

        # CPU限制
        self.large_cpu_slider = QSlider(Qt.Horizontal)
        self.large_cpu_slider.setRange(10, 100)
        self.large_cpu_slider.setValue(80)
        self.large_cpu_slider.setTickPosition(QSlider.TicksBelow)
        self.large_cpu_slider.setTickInterval(10)
        self.large_cpu_value_label = QLabel("80%")
        self.large_cpu_slider.valueChanged.connect(
            lambda v: self.large_cpu_value_label.setText(f"{v}%")
        )

        large_cpu_layout = QHBoxLayout()
        large_cpu_layout.addWidget(self.large_cpu_slider)
        large_cpu_layout.addWidget(self.large_cpu_value_label)
        large_task_layout.addRow("CPU限制:", large_cpu_layout)

        # 内存限制
        self.large_memory_slider = QSlider(Qt.Horizontal)
        self.large_memory_slider.setRange(10, 100)
        self.large_memory_slider.setValue(70)
        self.large_memory_slider.setTickPosition(QSlider.TicksBelow)
        self.large_memory_slider.setTickInterval(10)
        self.large_memory_value_label = QLabel("70%")
        self.large_memory_slider.valueChanged.connect(
            lambda v: self.large_memory_value_label.setText(f"{v}%")
        )

        large_memory_layout = QHBoxLayout()
        large_memory_layout.addWidget(self.large_memory_slider)
        large_memory_layout.addWidget(self.large_memory_value_label)
        large_task_layout.addRow("内存限制:", large_memory_layout)

        large_task_group.setLayout(large_task_layout)
        layout.addWidget(large_task_group)

        # 任务规模阈值配置
        threshold_group = QGroupBox("任务规模阈值")
        threshold_layout = QFormLayout()

        self.threshold_spinbox = QSpinBox()
        self.threshold_spinbox.setRange(10, 10000)
        self.threshold_spinbox.setValue(1000)
        self.threshold_spinbox.setSuffix(" 个单元")
        threshold_layout.addRow("小任务/大任务分界:", self.threshold_spinbox)

        threshold_group.setLayout(threshold_layout)
        layout.addWidget(threshold_group)

        # Windows Job Objects配置（可选）
        windows_job_group = QGroupBox("Windows Job Objects（硬限制）")
        windows_job_layout = QFormLayout()

        self.enable_windows_job_checkbox = QCheckBox("启用Windows Job Objects")
        self.enable_windows_job_checkbox.setChecked(False)
        windows_job_layout.addRow("", self.enable_windows_job_checkbox)

        self.job_cpu_spinbox = QSpinBox()
        self.job_cpu_spinbox.setRange(10, 100)
        self.job_cpu_spinbox.setValue(80)
        self.job_cpu_spinbox.setSuffix(" %")
        self.job_cpu_spinbox.setEnabled(False)
        windows_job_layout.addRow("Job CPU限制:", self.job_cpu_spinbox)

        self.job_memory_spinbox = QSpinBox()
        self.job_memory_spinbox.setRange(512, 16384)
        self.job_memory_spinbox.setValue(4096)
        self.job_memory_spinbox.setSuffix(" MB")
        self.job_memory_spinbox.setEnabled(False)
        windows_job_layout.addRow("Job内存限制:", self.job_memory_spinbox)

        # 连接启用/禁用逻辑
        self.enable_windows_job_checkbox.toggled.connect(self.job_cpu_spinbox.setEnabled)
        self.enable_windows_job_checkbox.toggled.connect(self.job_memory_spinbox.setEnabled)

        windows_job_group.setLayout(windows_job_layout)
        layout.addWidget(windows_job_group)

        # 实时资源使用显示
        resource_group = QGroupBox("当前资源使用")
        resource_layout = QFormLayout()

        self.current_cpu_label = QLabel("--")
        self.current_memory_label = QLabel("--")

        resource_layout.addRow("CPU使用率:", self.current_cpu_label)
        resource_layout.addRow("内存使用率:", self.current_memory_label)

        resource_group.setLayout(resource_layout)
        layout.addWidget(resource_group)

        # 按钮区域
        button_layout = QHBoxLayout()

        self.apply_button = QPushButton("应用配置")
        self.apply_button.clicked.connect(self._apply_config)
        button_layout.addWidget(self.apply_button)

        self.reset_button = QPushButton("重置默认")
        self.reset_button.clicked.connect(self._reset_defaults)
        button_layout.addWidget(self.reset_button)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        # 添加弹性空间
        layout.addStretch()

        # 创建资源监控定时器
        from PySide6.QtCore import QTimer

        self.resource_timer = QTimer(self)
        self.resource_timer.timeout.connect(self._update_resource_usage)
        self.resource_timer.start(1000)  # 每秒更新

    def setup(self, resource_limiter):
        """设置资源限制器引用

        Args:
            resource_limiter: HybridResourceLimiter实例
        """
        self.resource_limiter = resource_limiter
        self.logger.info("✅ ResourceLimitConfigWidget 已连接到资源限制器")

    def load_config(self, config: dict):
        """加载配置

        Args:
            config: 配置字典
        """
        try:
            # 小任务配置
            small_task = config.get("small_task", {})
            self.small_cpu_slider.setValue(int(small_task.get("cpu_percent", 30)))
            self.small_memory_slider.setValue(int(small_task.get("memory_percent", 50)))

            # 大任务配置
            large_task = config.get("large_task", {})
            self.large_cpu_slider.setValue(int(large_task.get("cpu_percent", 80)))
            self.large_memory_slider.setValue(int(large_task.get("memory_percent", 70)))

            # 阈值配置
            task_queue = config.get("task_queue", {})
            self.threshold_spinbox.setValue(task_queue.get("task_size_threshold", 1000))

            # Windows Job配置
            self.enable_windows_job_checkbox.setChecked(
                config.get("enable_windows_job_object", False)
            )
            self.job_cpu_spinbox.setValue(config.get("job_cpu_rate", 80))
            self.job_memory_spinbox.setValue(config.get("job_memory_limit_mb", 4096))

            self.logger.info("✅ 配置已加载")
        except Exception as e:
            self.logger.error(f"❌ 加载配置失败: {e}", exc_info=True)

    def get_config(self) -> dict:
        """获取当前配置

        Returns:
            dict: 配置字典
        """
        return {
            "small_task": {
                "cpu_percent": float(self.small_cpu_slider.value()),
                "memory_percent": float(self.small_memory_slider.value()),
            },
            "large_task": {
                "cpu_percent": float(self.large_cpu_slider.value()),
                "memory_percent": float(self.large_memory_slider.value()),
            },
            "task_size_threshold": self.threshold_spinbox.value(),
            "enable_windows_job_object": self.enable_windows_job_checkbox.isChecked(),
            "job_cpu_rate": self.job_cpu_spinbox.value(),
            "job_memory_limit_mb": self.job_memory_spinbox.value(),
        }

    def _apply_config(self):
        """应用配置"""
        config = self.get_config()
        self.config_changed.emit(config)
        self.logger.info(f"✅ 配置已应用: {config}")

        # 显示提示
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(self, "配置已应用", "资源限制配置已更新，将在下次任务执行时生效。")

    def _reset_defaults(self):
        """重置为默认配置"""
        self.small_cpu_slider.setValue(30)
        self.small_memory_slider.setValue(50)
        self.large_cpu_slider.setValue(80)
        self.large_memory_slider.setValue(70)
        self.threshold_spinbox.setValue(1000)
        self.enable_windows_job_checkbox.setChecked(False)
        self.job_cpu_spinbox.setValue(80)
        self.job_memory_spinbox.setValue(4096)

        self.logger.info("✅ 已重置为默认配置")

    def _update_resource_usage(self):
        """更新当前资源使用情况"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_percent = psutil.virtual_memory().percent

            # 设置颜色（根据使用率）
            cpu_color = self._get_usage_color(cpu_percent)
            memory_color = self._get_usage_color(memory_percent)

            self.current_cpu_label.setText(f"{cpu_percent:.1f}%")
            self.current_cpu_label.setStyleSheet(f"color: {cpu_color}; font-weight: bold;")

            self.current_memory_label.setText(f"{memory_percent:.1f}%")
            self.current_memory_label.setStyleSheet(f"color: {memory_color}; font-weight: bold;")

        except Exception as e:
            self.logger.error(f"❌ 更新资源使用失败: {e}", exc_info=True)

    def _get_usage_color(self, usage: float) -> str:
        """根据使用率获取颜色

        Args:
            usage: 使用率（百分比）

        Returns:
            str: 颜色代码
        """
        if usage < 50:
            return "#27ae60"  # 绿色
        elif usage < 75:
            return "#f39c12"  # 橙色
        else:
            return "#e74c3c"  # 红色
