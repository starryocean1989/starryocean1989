# -*- coding: utf-8 -*-
"""文件对比查看器.

提供文件对比功能：
- 选择两个文件对比
- 并排显示
- 高亮差异
"""

import difflib
from typing import Optional, List
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QFileDialog,
    QLabel,
    QSplitter,
    QGroupBox,
)
from PySide6.QtGui import QTextCharFormat, QColor, QFont

from backend.core.utils import LoggerMixin


class DiffViewer(QWidget, LoggerMixin):
    """文件对比查看器."""

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化对比查看器."""
        super().__init__(parent)

        # 当前对比的文件
        self.file1_path: Optional[str] = None
        self.file2_path: Optional[str] = None

        # 设置UI
        self._setup_ui()

        self.logger.info("文件对比查看器初始化完成")

    def _setup_ui(self):
        """设置用户界面."""
        layout = QVBoxLayout(self)

        # 文件选择栏
        file_select_layout = QHBoxLayout()

        # 文件1
        file1_layout = QHBoxLayout()
        self.file1_label = QLabel("文件1: 未选择")
        file1_layout.addWidget(self.file1_label)

        select_file1_btn = QPushButton("选择文件1")
        select_file1_btn.clicked.connect(self._select_file1)
        file1_layout.addWidget(select_file1_btn)

        file_select_layout.addLayout(file1_layout)

        file_select_layout.addSpacing(20)

        # 文件2
        file2_layout = QHBoxLayout()
        self.file2_label = QLabel("文件2: 未选择")
        file2_layout.addWidget(self.file2_label)

        select_file2_btn = QPushButton("选择文件2")
        select_file2_btn.clicked.connect(self._select_file2)
        file2_layout.addWidget(select_file2_btn)

        file_select_layout.addLayout(file2_layout)

        layout.addLayout(file_select_layout)

        # 对比按钮
        compare_layout = QHBoxLayout()

        compare_btn = QPushButton("🔍 开始对比")
        compare_btn.clicked.connect(self._compare_files)
        compare_layout.addWidget(compare_btn)

        compare_layout.addStretch()

        # 统计信息
        self.stats_label = QLabel("")
        compare_layout.addWidget(self.stats_label)

        layout.addLayout(compare_layout)

        # 对比结果区（并排显示）
        result_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：文件1
        left_group = QGroupBox("文件1")
        left_layout = QVBoxLayout(left_group)
        self.file1_text = QTextEdit()
        self.file1_text.setReadOnly(True)
        self.file1_text.setFont(QFont("Consolas, Monaco, Courier New", 10))
        left_layout.addWidget(self.file1_text)
        result_splitter.addWidget(left_group)

        # 右侧：文件2
        right_group = QGroupBox("文件2")
        right_layout = QVBoxLayout(right_group)
        self.file2_text = QTextEdit()
        self.file2_text.setReadOnly(True)
        self.file2_text.setFont(QFont("Consolas, Monaco, Courier New", 10))
        right_layout.addWidget(self.file2_text)
        result_splitter.addWidget(right_group)

        result_splitter.setSizes([500, 500])

        layout.addWidget(result_splitter)

    def _select_file1(self):
        """选择文件1."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择文件1", "strategies/user_strategies", "Python文件 (*.py);;所有文件 (*.*)"
        )

        if file_path:
            self.file1_path = file_path
            self.file1_label.setText(f"文件1: {Path(file_path).name}")
            self.logger.info(f"选择文件1: {file_path}")

    def _select_file2(self):
        """选择文件2."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择文件2", "strategies/user_strategies", "Python文件 (*.py);;所有文件 (*.*)"
        )

        if file_path:
            self.file2_path = file_path
            self.file2_label.setText(f"文件2: {Path(file_path).name}")
            self.logger.info(f"选择文件2: {file_path}")

    def _compare_files(self):
        """对比文件."""
        if not self.file1_path or not self.file2_path:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "警告", "请先选择两个文件")
            return

        try:
            # 读取文件内容
            with open(self.file1_path, "r", encoding="utf-8") as f:
                file1_lines = f.readlines()

            with open(self.file2_path, "r", encoding="utf-8") as f:
                file2_lines = f.readlines()

            # 使用difflib生成diff
            differ = difflib.Differ()
            diff_result = list(differ.compare(file1_lines, file2_lines))

            # 统计差异
            added_lines = sum(1 for line in diff_result if line.startswith("+ "))
            removed_lines = sum(1 for line in diff_result if line.startswith("- "))

            self.stats_label.setText(f"差异: +{added_lines} -{removed_lines}")

            # 分离两个文件的内容并高亮
            file1_html = self._generate_diff_html(diff_result, is_left=True)
            file2_html = self._generate_diff_html(diff_result, is_left=False)

            # 显示结果
            self.file1_text.setHtml(file1_html)
            self.file2_text.setHtml(file2_html)

            self.logger.info(f"对比完成: +{added_lines} -{removed_lines}")

        except Exception as e:
            self.logger.error(f"对比文件失败: {e}")
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "错误", f"对比失败: {str(e)}")

    def _generate_diff_html(self, diff_result: List[str], is_left: bool) -> str:
        """生成diff的HTML显示.

        Args:
            diff_result: diff结果
            is_left: 是否是左侧文件

        Returns:
            str: HTML内容
        """
        html = "<pre style='font-family: Consolas, Monaco, monospace; font-size: 10pt;'>"

        for line in diff_result:
            if line.startswith("  "):
                # 未修改的行
                content = line[2:].rstrip("\n")
                html += f"<div style='background-color: #1E1E1E; color: #D4D4D4;'>{self._escape_html(content)}</div>"

            elif line.startswith("- ") and is_left:
                # 删除的行（只在左侧显示）
                content = line[2:].rstrip("\n")
                html += f"<div style='background-color: #4B1818; color: #F88379;'>{self._escape_html(content)}</div>"

            elif line.startswith("+ ") and not is_left:
                # 新增的行（只在右侧显示）
                content = line[2:].rstrip("\n")
                html += f"<div style='background-color: #1B5C1B; color: #89D185;'>{self._escape_html(content)}</div>"

            elif line.startswith("? "):
                # 变化标记（忽略）
                pass

        html += "</pre>"

        return html

    @staticmethod
    def _escape_html(text: str) -> str:
        """转义HTML特殊字符.

        Args:
            text: 原始文本

        Returns:
            str: 转义后的文本
        """
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace(" ", "&nbsp;")
            .replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
        )

    def compare_files(self, file1: str, file2: str):
        """对比两个文件（外部调用）.

        Args:
            file1: 文件1路径
            file2: 文件2路径
        """
        self.file1_path = file1
        self.file2_path = file2
        self.file1_label.setText(f"文件1: {Path(file1).name}")
        self.file2_label.setText(f"文件2: {Path(file2).name}")
        self._compare_files()
