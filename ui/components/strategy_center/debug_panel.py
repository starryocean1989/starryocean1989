# -*- coding: utf-8 -*-
"""调试面板.

显示和管理断点：
- 断点列表
- 启用/禁用断点
- 日志输出查看
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QTextEdit,
    QLabel,
    QGroupBox,
)

from backend.core.utils import LoggerMixin
from ui.components.strategy_center.debugger import Debugger


class DebugPanel(QWidget, LoggerMixin):
    """调试面板."""

    # 信号
    breakpoint_clicked = Signal(str, int)  # 断点点击信号（文件路径、行号）

    def __init__(self, debugger: Debugger, parent: Optional[QWidget] = None):
        """初始化调试面板.

        Args:
            debugger: 调试器实例
            parent: 父组件
        """
        super().__init__(parent)

        self.debugger = debugger

        # 设置UI
        self._setup_ui()

        # 刷新断点列表
        self.refresh_breakpoints()

        self.logger.info("调试面板初始化完成")

    def _setup_ui(self):
        """设置用户界面."""
        layout = QVBoxLayout(self)

        # 断点列表组
        breakpoint_group = QGroupBox("断点列表")
        breakpoint_layout = QVBoxLayout(breakpoint_group)

        # 工具栏
        toolbar = QHBoxLayout()

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self.refresh_breakpoints)
        toolbar.addWidget(refresh_btn)

        clear_btn = QPushButton("🗑️ 清除所有")
        clear_btn.clicked.connect(self._clear_all_breakpoints)
        toolbar.addWidget(clear_btn)

        export_btn = QPushButton("💾 导出")
        export_btn.clicked.connect(self._export_breakpoints)
        toolbar.addWidget(export_btn)

        import_btn = QPushButton("📂 导入")
        import_btn.clicked.connect(self._import_breakpoints)
        toolbar.addWidget(import_btn)

        toolbar.addStretch()

        breakpoint_layout.addLayout(toolbar)

        # 断点树
        self.breakpoint_tree = QTreeWidget()
        self.breakpoint_tree.setHeaderLabels(["文件 / 行号"])
        self.breakpoint_tree.itemDoubleClicked.connect(self._on_breakpoint_double_clicked)
        breakpoint_layout.addWidget(self.breakpoint_tree)

        # 统计标签
        self.stats_label = QLabel("断点数: 0")
        breakpoint_layout.addWidget(self.stats_label)

        layout.addWidget(breakpoint_group)

        # 日志输出组
        log_group = QGroupBox("断点日志")
        log_layout = QVBoxLayout(log_group)

        self.log_output = QTextEdit()
        self.log_output.setPlaceholderText("断点触发的日志将显示在这里...")
        self.log_output.setReadOnly(True)
        log_layout.addWidget(self.log_output)

        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.clicked.connect(self.log_output.clear)
        log_layout.addWidget(clear_log_btn)

        layout.addWidget(log_group)

    def refresh_breakpoints(self):
        """刷新断点列表."""
        self.breakpoint_tree.clear()

        all_breakpoints = self.debugger.get_breakpoints()
        total_count = 0

        for file_path, line_numbers in all_breakpoints.items():
            # 创建文件节点
            file_item = QTreeWidgetItem()
            file_name = Path(file_path).name
            file_item.setText(0, f"📄 {file_name} ({len(line_numbers)}个)")
            file_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "file", "path": file_path})
            self.breakpoint_tree.addTopLevelItem(file_item)

            # 添加断点行
            for line_num in line_numbers:
                line_item = QTreeWidgetItem()
                line_item.setText(0, f"  🔴 行 {line_num}")
                line_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {"type": "breakpoint", "path": file_path, "line": line_num},
                )
                file_item.addChild(line_item)

            # 展开文件节点
            file_item.setExpanded(True)
            total_count += len(line_numbers)

        # 更新统计
        self.stats_label.setText(f"断点数: {total_count}")

        self.logger.info(f"断点列表已刷新: {total_count} 个断点")

    def _on_breakpoint_double_clicked(self, item: QTreeWidgetItem, column: int):
        """断点双击事件.

        Args:
            item: 树节点
            column: 列索引
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data["type"] == "breakpoint":
            # 跳转到断点位置
            file_path = data["path"]
            line_num = data["line"]
            self.breakpoint_clicked.emit(file_path, line_num)
            self.logger.info(f"跳转到断点: {file_path}:{line_num}")

    def _clear_all_breakpoints(self):
        """清除所有断点."""
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "确认",
            "确定要清除所有断点吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.debugger.clear_breakpoints()
            self.refresh_breakpoints()
            self.logger.info("已清除所有断点")

    def _export_breakpoints(self):
        """导出断点配置."""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出断点配置", "breakpoints.json", "JSON文件 (*.json)"
        )

        if file_path:
            self.debugger.export_breakpoints(file_path)
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self, "成功", f"断点已导出到: {file_path}")

    def _import_breakpoints(self):
        """导入断点配置."""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(self, "导入断点配置", "", "JSON文件 (*.json)")

        if file_path:
            self.debugger.import_breakpoints(file_path)
            self.refresh_breakpoints()
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self, "成功", f"断点已从 {file_path} 导入")

    def append_log(self, message: str):
        """添加日志消息.

        Args:
            message: 日志消息
        """
        self.log_output.append(message)
