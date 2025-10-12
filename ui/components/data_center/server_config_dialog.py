# -*- coding: utf-8 -*-
"""
服务器池配置对话框

允许用户配置多服务器并行下载的参数
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QPushButton,
    QGroupBox,
    QFormLayout,
    QMessageBox,
)


class ServerConfigDialog(QDialog):
    """服务器池配置对话框"""

    def __init__(self, data_center_service, parent=None):
        """
        初始化对话框

        Args:
            data_center_service: 数据中心服务实例
            parent: 父窗口
        """
        super().__init__(parent)
        self.data_center_service = data_center_service
        self.current_size = 5  # 默认值

        self.setWindowTitle("服务器池配置")
        self.setMinimumWidth(500)
        self.setModal(True)

        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)

        # 说明组
        info_group = QGroupBox("多服务器并行下载")
        info_layout = QVBoxLayout(info_group)

        info_label = QLabel(
            "使用多个服务器并行下载可以显著提升速度。\n"
            "每个服务器独立连接，互不干扰。\n\n"
            "💡 I/O密集型任务，可以设置超过CPU核心数！\n\n"
            "建议设置（8核16线程电脑）：\n"
            "  • 保守模式（网络差）：2-3个\n"
            "  • 标准模式（网络一般）：5-8个（推荐）\n"
            "  • 加速模式（网络好）：10-15个\n"
            "  • 极速模式（网络优+高配置）：15-25个\n\n"
            "⚠️ 建议从5开始，逐步增加观察效果\n"
            "⚠️ 速度提升非线性（收益递减）"
        )
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)

        layout.addWidget(info_group)

        # 配置组
        config_group = QGroupBox("配置")
        config_layout = QFormLayout(config_group)

        # 服务器数量滑块
        slider_layout = QVBoxLayout()

        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setMinimum(1)
        self.size_slider.setMaximum(30)
        self.size_slider.setValue(5)
        self.size_slider.setTickPosition(QSlider.TicksBelow)
        self.size_slider.setTickInterval(5)  # 每5个显示一个刻度
        self.size_slider.valueChanged.connect(self._on_slider_changed)
        slider_layout.addWidget(self.size_slider)

        # 数值标签（显示主要刻度）
        value_layout = QHBoxLayout()
        for i in [1, 5, 10, 15, 20, 25, 30]:
            label = QLabel(str(i))
            label.setAlignment(Qt.AlignCenter)
            value_layout.addWidget(label)
            if i < 30:
                value_layout.addStretch()  # 添加弹性空间
        slider_layout.addLayout(value_layout)

        config_layout.addRow("服务器数量:", slider_layout)

        # 当前值显示
        self.current_value_label = QLabel("5个服务器")
        self.current_value_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        config_layout.addRow("当前设置:", self.current_value_label)

        # 预估速度
        self.speed_label = QLabel("预估提速: 4倍")
        config_layout.addRow("", self.speed_label)

        layout.addWidget(config_group)

        # 按钮
        button_layout = QHBoxLayout()

        self.apply_btn = QPushButton("应用")
        self.apply_btn.clicked.connect(self._on_apply)
        button_layout.addWidget(self.apply_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _load_config(self):
        """加载当前配置"""
        try:
            result = self.data_center_service.get_server_pool_config()
            if result.get("success"):
                size = result.get("server_pool_size", 5)
                self.current_size = size
                self.size_slider.setValue(size)
                self._update_display(size)
        except Exception as e:
            QMessageBox.warning(self, "加载配置失败", f"无法加载配置: {str(e)}")

    def _on_slider_changed(self, value):
        """滑块值改变"""
        self._update_display(value)

    def _update_display(self, size):
        """更新显示"""
        self.current_value_label.setText(f"{size}个服务器")

        # 预估速度（使用更科学的非线性模型）
        # 公式：实际提速 = N * 效率系数
        # 效率系数随着服务器数量增加而递减（收益递减原理）
        if size == 1:
            speed_text = "1.0倍（基准）"
        elif size <= 5:
            # 1-5个：效率系数约0.80-0.85（网络开销小）
            efficiency = 0.85 - (size - 1) * 0.01
            actual_speed = size * efficiency
            speed_text = f"约{actual_speed:.1f}倍（效率{efficiency:.0%}）"
        elif size <= 10:
            # 6-10个：效率系数约0.70-0.75（网络开销增加）
            efficiency = 0.80 - (size - 5) * 0.02
            actual_speed = size * efficiency
            speed_text = f"约{actual_speed:.1f}倍（效率{efficiency:.0%}）"
        elif size <= 20:
            # 11-20个：效率系数约0.60-0.65（带宽饱和）
            efficiency = 0.70 - (size - 10) * 0.01
            actual_speed = size * efficiency
            speed_text = f"约{actual_speed:.1f}倍（效率{efficiency:.0%}）"
        else:
            # 21-30个：效率系数约0.50-0.55（收益递减明显）
            efficiency = 0.60 - (size - 20) * 0.01
            actual_speed = size * efficiency
            speed_text = f"约{actual_speed:.1f}倍（效率{efficiency:.0%}）"

        self.speed_label.setText(f"预估提速: {speed_text}")

    def _on_apply(self):
        """应用配置"""
        new_size = self.size_slider.value()

        try:
            result = self.data_center_service.set_server_pool_size(new_size)

            if result.get("success"):
                restart_required = result.get("restart_required", False)
                message = result.get("message", "配置已保存")

                if restart_required:
                    QMessageBox.information(
                        self,
                        "配置成功",
                        f"{message}\n\n"
                        f"旧值: {self.current_size}个服务器\n"
                        f"新值: {new_size}个服务器\n\n"
                        "请重启程序以使新配置生效。",
                    )
                else:
                    QMessageBox.information(self, "配置成功", message)

                self.accept()
            else:
                QMessageBox.warning(self, "配置失败", result.get("message", "配置保存失败"))

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存配置时发生错误: {str(e)}")

    @classmethod
    def show_config_dialog(cls, data_center_service, parent=None):
        """显示配置对话框（类方法）

        Args:
            data_center_service: 数据中心服务
            parent: 父窗口

        Returns:
            bool: 用户是否点击了应用
        """
        dialog = cls(data_center_service, parent)
        return dialog.exec() == QDialog.Accepted
