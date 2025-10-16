# -*- coding: utf-8 -*-
"""服务器配置对话框.

提供多服务器并行下载参数配置界面。
"""
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)


class ServerConfigDialog(QDialog):
    """服务器配置对话框."""

    def __init__(self, data_center_service, parent=None):
        """初始化服务器配置对话框.

        Args:
            data_center_service: 数据中心服务实例
            parent: 父窗口
        """
        super().__init__(parent)
        self.data_center_service = data_center_service
        self.setWindowTitle("服务器配置")
        self.setMinimumWidth(500)

        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        """设置用户界面."""
        layout = QVBoxLayout(self)

        # 说明标签
        info_label = QLabel(
            "配置多服务器并行下载参数。\n" "多个服务器可以同时下载不同品种的数据，提高下载速度。"
        )
        info_label.setStyleSheet("color: #666; padding: 10px; background-color: #f0f0f0;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 表单布局
        form_layout = QFormLayout()

        # 并行服务器数量
        self.server_count_spin = QSpinBox()
        self.server_count_spin.setRange(1, 30)
        self.server_count_spin.setValue(5)
        self.server_count_spin.setSuffix(" 个")
        self.server_count_spin.setToolTip("同时使用的服务器数量（1-30）")
        form_layout.addRow("并行服务器数量:", self.server_count_spin)

        # 连接超时时间
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setValue(30)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setToolTip("单个请求的超时时间（5-120秒）")
        form_layout.addRow("连接超时时间:", self.timeout_spin)

        # 重试次数
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(3)
        self.retry_spin.setSuffix(" 次")
        self.retry_spin.setToolTip("下载失败后的重试次数（0-10次）")
        form_layout.addRow("重试次数:", self.retry_spin)

        layout.addLayout(form_layout)

        # 提示信息
        hint_label = QLabel(
            "💡 提示：\n"
            "• 服务器数量越多，下载速度越快，但也会增加网络负载\n"
            "• 建议服务器数量设置为 3-10 个\n"
            "• 如果网络不稳定，可以适当增加超时时间和重试次数"
        )
        hint_label.setStyleSheet("color: #888; font-size: 11px; padding: 10px;")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._save_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_config(self):
        """加载当前配置."""
        try:
            # 从 data_center_service 获取配置
            if self.data_center_service and hasattr(self.data_center_service, "china_stock_engine"):
                engine = self.data_center_service.china_stock_engine
                if engine:
                    # 从 config_manager 读取配置
                    from backend.infrastructure.data_module_vnpy.config import config_manager

                    server_pool_size = config_manager.get("chinastock.server_pool_size", 5)
                    timeout = config_manager.get("chinastock.timeout", 30)
                    retry_times = config_manager.get("chinastock.retry_times", 3)

                    self.server_count_spin.setValue(int(server_pool_size))
                    self.timeout_spin.setValue(int(timeout))
                    self.retry_spin.setValue(int(retry_times))

        except Exception as e:
            import logging

            logging.getLogger(__name__).error("加载服务器配置失败: %s", e)

    def _save_and_accept(self):
        """保存配置并关闭对话框."""
        try:
            # 获取配置值
            server_pool_size = self.server_count_spin.value()
            timeout = self.timeout_spin.value()
            retry_times = self.retry_spin.value()

            # 保存到 config_manager
            from backend.infrastructure.data_module_vnpy.config import config_manager

            config_manager.set("chinastock.server_pool_size", server_pool_size)
            config_manager.set("chinastock.timeout", timeout)
            config_manager.set("chinastock.retry_times", retry_times)

            # 显示成功消息
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "配置保存成功",
                f"服务器配置已保存：\n"
                f"• 并行服务器数量：{server_pool_size} 个\n"
                f"• 连接超时时间：{timeout} 秒\n"
                f"• 重试次数：{retry_times} 次\n\n"
                f"配置将在下次下载时生效。",
            )

            self.accept()

        except Exception as e:
            import logging

            logging.getLogger(__name__).error("保存服务器配置失败: %s", e, exc_info=True)

            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "保存失败", f"保存配置时发生错误：{str(e)}")

    @staticmethod
    def show_config_dialog(data_center_service, parent=None):
        """显示服务器配置对话框（静态方法）.

        Args:
            data_center_service: 数据中心服务实例
            parent: 父窗口

        Returns:
            bool: 用户是否点击了确定按钮
        """
        dialog = ServerConfigDialog(data_center_service, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted
