# -*- coding: utf-8 -*-
"""Git集成面板（简化版）.

提供基本的Git操作：
- 查看文件状态
- 提交更改
- 查看历史
- 分支切换
"""

import subprocess
from typing import List, Dict, Optional
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QTextEdit,
    QLineEdit,
    QLabel,
    QGroupBox,
    QComboBox,
)

from backend.core.utils import LoggerMixin


class GitPanel(QWidget, LoggerMixin):
    """Git集成面板（简化版）."""

    # 信号
    file_selected = Signal(str)  # 文件选择信号

    def __init__(self, repo_path: str = ".", parent: Optional[QWidget] = None):
        """初始化Git面板.

        Args:
            repo_path: Git仓库路径
            parent: 父组件
        """
        super().__init__(parent)

        self.repo_path = Path(repo_path)

        # 检查Git可用性
        self.git_available = self._check_git()

        # 设置UI
        self._setup_ui()

        # 如果Git可用，刷新状态
        if self.git_available:
            self.refresh_status()

        self.logger.info(f"Git面板初始化完成，仓库: {self.repo_path}")

    def _check_git(self) -> bool:
        """检查Git是否可用.

        Returns:
            bool: Git是否可用
        """
        try:
            result = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception as e:
            self.logger.warning(f"Git不可用: {e}")
            return False

    def _setup_ui(self):
        """设置用户界面."""
        layout = QVBoxLayout(self)

        if not self.git_available:
            # Git不可用提示
            warning_label = QLabel("⚠️ Git不可用\n\n请确保已安装Git并添加到PATH环境变量")
            warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            warning_label.setStyleSheet("color: orange; font-size: 14px;")
            layout.addWidget(warning_label)
            return

        # 分支信息
        branch_layout = QHBoxLayout()
        branch_layout.addWidget(QLabel("当前分支:"))

        self.branch_combo = QComboBox()
        self.branch_combo.currentTextChanged.connect(self._on_branch_changed)
        branch_layout.addWidget(self.branch_combo)

        refresh_branch_btn = QPushButton("🔄")
        refresh_branch_btn.setMaximumWidth(30)
        refresh_branch_btn.clicked.connect(self._refresh_branches)
        branch_layout.addWidget(refresh_branch_btn)

        layout.addLayout(branch_layout)

        # 文件状态组
        status_group = QGroupBox("文件状态")
        status_layout = QVBoxLayout(status_group)

        # 工具栏
        toolbar = QHBoxLayout()

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self.refresh_status)
        toolbar.addWidget(refresh_btn)

        stage_all_btn = QPushButton("✅ 暂存所有")
        stage_all_btn.clicked.connect(self._stage_all)
        toolbar.addWidget(stage_all_btn)

        unstage_all_btn = QPushButton("❌ 取消暂存")
        unstage_all_btn.clicked.connect(self._unstage_all)
        toolbar.addWidget(unstage_all_btn)

        toolbar.addStretch()

        status_layout.addLayout(toolbar)

        # 文件状态树
        self.status_tree = QTreeWidget()
        self.status_tree.setHeaderLabels(["文件", "状态"])
        status_layout.addWidget(self.status_tree)

        layout.addWidget(status_group)

        # 提交组
        commit_group = QGroupBox("提交")
        commit_layout = QVBoxLayout(commit_group)

        # 提交消息
        commit_layout.addWidget(QLabel("提交消息:"))

        self.commit_message = QTextEdit()
        self.commit_message.setPlaceholderText("输入提交消息...")
        self.commit_message.setMaximumHeight(80)
        commit_layout.addWidget(self.commit_message)

        # 提交按钮
        commit_btn = QPushButton("💾 提交")
        commit_btn.clicked.connect(self._commit)
        commit_layout.addWidget(commit_btn)

        layout.addWidget(commit_group)

        # 历史记录组
        history_group = QGroupBox("提交历史（最近10条）")
        history_layout = QVBoxLayout(history_group)

        self.history_list = QTextEdit()
        self.history_list.setReadOnly(True)
        self.history_list.setMaximumHeight(150)
        history_layout.addWidget(self.history_list)

        view_history_btn = QPushButton("🔍 查看完整历史")
        view_history_btn.clicked.connect(self._view_history)
        history_layout.addWidget(view_history_btn)

        layout.addWidget(history_group)

    def refresh_status(self):
        """刷新Git状态."""
        if not self.git_available:
            return

        self.status_tree.clear()

        try:
            # 执行git status
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                self.logger.error(f"Git status失败: {result.stderr}")
                return

            # 解析输出
            lines = result.stdout.strip().split("\n")

            for line in lines:
                if not line.strip():
                    continue

                # 格式: XY filename
                # X: 暂存区状态, Y: 工作区状态
                status = line[:2]
                file_path = line[3:]

                # 解析状态
                status_text = self._parse_status(status)

                # 添加到树
                item = QTreeWidgetItem()
                item.setText(0, file_path)
                item.setText(1, status_text)
                item.setData(0, Qt.ItemDataRole.UserRole, file_path)
                self.status_tree.addTopLevelItem(item)

            # 刷新分支列表
            self._refresh_branches()

            # 刷新历史
            self._refresh_history()

            self.logger.info("Git状态已刷新")

        except Exception as e:
            self.logger.error(f"刷新Git状态失败: {e}")

    def _parse_status(self, status: str) -> str:
        """解析Git状态代码.

        Args:
            status: 状态代码（2字符）

        Returns:
            str: 状态描述
        """
        status_map = {
            "M ": "已修改（暂存）",
            " M": "已修改",
            "MM": "已修改（部分暂存）",
            "A ": "新增（暂存）",
            " A": "新增",
            "D ": "删除（暂存）",
            " D": "删除",
            "R ": "重命名（暂存）",
            "??": "未跟踪",
        }
        return status_map.get(status, status)

    def _stage_all(self):
        """暂存所有更改."""
        if not self.git_available:
            return

        try:
            result = subprocess.run(
                ["git", "add", "."], cwd=self.repo_path, capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                self.logger.info("已暂存所有更改")
                self.refresh_status()
            else:
                self.logger.error(f"暂存失败: {result.stderr}")

        except Exception as e:
            self.logger.error(f"暂存失败: {e}")

    def _unstage_all(self):
        """取消暂存所有更改."""
        if not self.git_available:
            return

        try:
            result = subprocess.run(
                ["git", "reset", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                self.logger.info("已取消暂存所有更改")
                self.refresh_status()
            else:
                self.logger.error(f"取消暂存失败: {result.stderr}")

        except Exception as e:
            self.logger.error(f"取消暂存失败: {e}")

    def _commit(self):
        """提交更改."""
        if not self.git_available:
            return

        message = self.commit_message.toPlainText().strip()
        if not message:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "警告", "请输入提交消息")
            return

        try:
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.information(self, "成功", "提交成功")
                self.commit_message.clear()
                self.refresh_status()
                self.logger.info(f"提交成功: {message}")
            else:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.critical(self, "错误", f"提交失败:\n{result.stderr}")

        except Exception as e:
            self.logger.error(f"提交失败: {e}")

    def _refresh_branches(self):
        """刷新分支列表."""
        if not self.git_available or not hasattr(self, "branch_combo"):
            return

        try:
            # 获取所有分支
            result = subprocess.run(
                ["git", "branch"], cwd=self.repo_path, capture_output=True, text=True, timeout=5
            )

            if result.returncode != 0:
                return

            # 解析分支
            branches = []
            current_branch = None

            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line.startswith("*"):
                    # 当前分支
                    current_branch = line[2:]
                    branches.append(current_branch)
                elif line:
                    branches.append(line)

            # 更新下拉框
            self.branch_combo.clear()
            self.branch_combo.addItems(branches)

            # 设置当前分支
            if current_branch:
                index = self.branch_combo.findText(current_branch)
                if index >= 0:
                    self.branch_combo.setCurrentIndex(index)

        except Exception as e:
            self.logger.error(f"刷新分支失败: {e}")

    def _on_branch_changed(self, branch_name: str):
        """分支切换事件.

        Args:
            branch_name: 分支名称
        """
        # TODO: 实现分支切换功能
        pass

    def _refresh_history(self):
        """刷新提交历史."""
        if not self.git_available:
            return

        try:
            # 获取最近10条提交
            result = subprocess.run(
                ["git", "log", "--oneline", "-n", "10"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                self.history_list.setPlainText(result.stdout)
            else:
                self.history_list.setPlainText("无提交历史")

        except Exception as e:
            self.logger.error(f"刷新历史失败: {e}")

    def _view_history(self):
        """查看完整历史."""
        if not self.git_available:
            return

        try:
            # 获取完整历史
            result = subprocess.run(
                ["git", "log", "--oneline"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                # 在新窗口显示
                from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit

                dialog = QDialog(self)
                dialog.setWindowTitle("Git提交历史")
                dialog.setMinimumSize(600, 400)

                layout = QVBoxLayout(dialog)

                history_text = QTextEdit()
                history_text.setPlainText(result.stdout)
                history_text.setReadOnly(True)
                layout.addWidget(history_text)

                dialog.exec()

        except Exception as e:
            self.logger.error(f"查看历史失败: {e}")
