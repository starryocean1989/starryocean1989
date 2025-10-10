# -*- coding: utf-8 -*-
"""全局搜索和替换面板.

提供类似VSCode的搜索体验：
- 全局搜索（跨文件）
- 正则表达式支持
- 树形结果展示
- 单个/批量替换
"""

import re
from pathlib import Path
from typing import List, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QTreeWidget,
    QTreeWidgetItem,
    QLabel,
    QGroupBox,
)

from backend.core.utils import LoggerMixin


class SearchPanel(QWidget, LoggerMixin):
    """全局搜索和替换面板."""

    # 信号
    file_selected = Signal(str, int)  # 选择文件和行号

    def __init__(self, search_root: str, parent: Optional[QWidget] = None):
        """初始化搜索面板.

        Args:
            search_root: 搜索根目录
            parent: 父组件
        """
        super().__init__(parent)

        self.search_root = Path(search_root)
        self.search_results: List[Dict] = []

        # 设置UI
        self._setup_ui()

        self.logger.info(f"搜索面板初始化完成，搜索根目录: {self.search_root}")

    def _setup_ui(self):
        """设置用户界面."""
        layout = QVBoxLayout(self)

        # 搜索输入区
        search_group = QGroupBox("搜索")
        search_layout = QVBoxLayout(search_group)

        # 搜索框
        search_input_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入搜索内容...")
        self.search_input.returnPressed.connect(self._do_search)
        search_input_layout.addWidget(self.search_input)

        search_btn = QPushButton("🔍 搜索")
        search_btn.clicked.connect(self._do_search)
        search_input_layout.addWidget(search_btn)

        search_layout.addLayout(search_input_layout)

        # 替换框
        replace_layout = QHBoxLayout()
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("替换为...")
        replace_layout.addWidget(self.replace_input)

        replace_btn = QPushButton("替换")
        replace_btn.clicked.connect(self._do_replace)
        replace_layout.addWidget(replace_btn)

        replace_all_btn = QPushButton("全部替换")
        replace_all_btn.clicked.connect(self._do_replace_all)
        replace_layout.addWidget(replace_all_btn)

        search_layout.addLayout(replace_layout)

        # 搜索选项
        options_layout = QHBoxLayout()

        self.case_sensitive_cb = QCheckBox("大小写敏感")
        options_layout.addWidget(self.case_sensitive_cb)

        self.regex_cb = QCheckBox("正则表达式")
        options_layout.addWidget(self.regex_cb)

        self.whole_word_cb = QCheckBox("全词匹配")
        options_layout.addWidget(self.whole_word_cb)

        options_layout.addStretch()

        search_layout.addLayout(options_layout)

        layout.addWidget(search_group)

        # 搜索结果区
        results_group = QGroupBox("搜索结果")
        results_layout = QVBoxLayout(results_group)

        # 结果统计标签
        self.result_count_label = QLabel("就绪")
        results_layout.addWidget(self.result_count_label)

        # 结果树
        self.result_tree = QTreeWidget()
        self.result_tree.setHeaderLabels(["文件 / 行号 : 内容"])
        self.result_tree.itemDoubleClicked.connect(self._on_result_double_clicked)
        results_layout.addWidget(self.result_tree)

        layout.addWidget(results_group)

    def _do_search(self):
        """执行搜索."""
        pattern = self.search_input.text().strip()
        if not pattern:
            self.logger.warning("搜索内容为空")
            return

        # 清空之前的结果
        self.result_tree.clear()
        self.search_results.clear()

        # 获取搜索选项
        case_sensitive = self.case_sensitive_cb.isChecked()
        is_regex = self.regex_cb.isChecked()
        whole_word = self.whole_word_cb.isChecked()

        self.logger.info(f"开始搜索: '{pattern}', 正则={is_regex}, 大小写={case_sensitive}")

        try:
            # 搜索所有.py文件
            files = list(self.search_root.rglob("*.py"))
            total_matches = 0

            for file_path in files:
                # 跳过__pycache__
                if "__pycache__" in str(file_path):
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    # 搜索每一行
                    matches = []
                    for line_num, line in enumerate(lines, 1):
                        if self._match_line(line, pattern, case_sensitive, is_regex, whole_word):
                            matches.append({"line_num": line_num, "content": line.rstrip()})
                            total_matches += 1

                    # 如果有匹配，添加到结果树
                    if matches:
                        self.search_results.append({"file": str(file_path), "matches": matches})
                        self._add_file_to_tree(file_path, matches)

                except Exception as e:
                    self.logger.error(f"搜索文件失败: {file_path}, 错误: {e}")

            # 更新统计
            file_count = len(self.search_results)
            self.result_count_label.setText(
                f"找到 {total_matches} 处匹配（共 {file_count} 个文件）"
            )

            self.logger.info(f"搜索完成: {total_matches} 处匹配")

        except Exception as e:
            self.logger.error(f"搜索失败: {e}", exc_info=True)

    def _match_line(
        self, line: str, pattern: str, case_sensitive: bool, is_regex: bool, whole_word: bool
    ) -> bool:
        """检查行是否匹配搜索模式.

        Args:
            line: 行内容
            pattern: 搜索模式
            case_sensitive: 是否大小写敏感
            is_regex: 是否正则表达式
            whole_word: 是否全词匹配

        Returns:
            bool: 是否匹配
        """
        try:
            if is_regex:
                # 正则表达式模式
                flags = 0 if case_sensitive else re.IGNORECASE
                return bool(re.search(pattern, line, flags))
            else:
                # 普通搜索
                if whole_word:
                    # 全词匹配
                    pattern_escaped = re.escape(pattern)
                    pattern_regex = rf"\b{pattern_escaped}\b"
                    flags = 0 if case_sensitive else re.IGNORECASE
                    return bool(re.search(pattern_regex, line, flags))
                else:
                    # 普通子字符串匹配
                    if case_sensitive:
                        return pattern in line
                    else:
                        return pattern.lower() in line.lower()
        except re.error:
            # 正则表达式错误
            return False

    def _add_file_to_tree(self, file_path: Path, matches: List[Dict]):
        """添加文件到结果树.

        Args:
            file_path: 文件路径
            matches: 匹配列表
        """
        # 创建文件节点
        file_item = QTreeWidgetItem()
        file_item.setText(0, f"📄 {file_path.name} ({len(matches)}处)")
        file_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "file", "path": str(file_path)})
        self.result_tree.addTopLevelItem(file_item)

        # 添加匹配行
        for match in matches:
            line_item = QTreeWidgetItem()
            line_text = f"  行 {match['line_num']}: {match['content'][:80]}"
            line_item.setText(0, line_text)
            line_item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {
                    "type": "match",
                    "path": str(file_path),
                    "line_num": match["line_num"],
                    "content": match["content"],
                },
            )
            file_item.addChild(line_item)

        # 展开文件节点
        file_item.setExpanded(True)

    def _on_result_double_clicked(self, item: QTreeWidgetItem, column: int):
        """结果双击事件.

        Args:
            item: 树节点
            column: 列索引
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data["type"] == "match":
            # 跳转到文件和行号
            file_path = data["path"]
            line_num = data["line_num"]
            self.file_selected.emit(file_path, line_num)
            self.logger.info(f"跳转到: {file_path}:{line_num}")

    def _do_replace(self):
        """替换当前选中的匹配."""
        selected_items = self.result_tree.selectedItems()
        if not selected_items:
            self.logger.warning("未选择要替换的项")
            return

        replace_text = self.replace_input.text()
        search_text = self.search_input.text()

        replace_count = 0

        for item in selected_items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data["type"] == "match":
                file_path = Path(data["path"])
                line_num = data["line_num"]

                try:
                    # 读取文件
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    # 替换指定行
                    if 0 < line_num <= len(lines):
                        old_line = lines[line_num - 1]
                        new_line = old_line.replace(search_text, replace_text)
                        lines[line_num - 1] = new_line

                        # 写回文件
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.writelines(lines)

                        replace_count += 1
                        self.logger.info(f"已替换: {file_path}:{line_num}")

                except Exception as e:
                    self.logger.error(f"替换失败: {file_path}:{line_num}, 错误: {e}")

        if replace_count > 0:
            self.logger.info(f"完成替换: {replace_count} 处")
            # 重新搜索以更新结果
            self._do_search()

    def _do_replace_all(self):
        """替换所有匹配."""
        if not self.search_results:
            self.logger.warning("没有搜索结果")
            return

        replace_text = self.replace_input.text()
        search_text = self.search_input.text()

        replace_count = 0

        for result in self.search_results:
            file_path = Path(result["file"])

            try:
                # 读取文件
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # 替换所有匹配
                new_content = content.replace(search_text, replace_text)

                if new_content != content:
                    # 写回文件
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_content)

                    replace_count += len(result["matches"])
                    self.logger.info(f"已替换文件: {file_path}")

            except Exception as e:
                self.logger.error(f"替换文件失败: {file_path}, 错误: {e}")

        if replace_count > 0:
            self.logger.info(f"完成全部替换: {replace_count} 处")
            # 重新搜索以更新结果
            self._do_search()
