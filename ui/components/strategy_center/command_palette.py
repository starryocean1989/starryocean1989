# -*- coding: utf-8 -*-
"""命令面板组件.

提供类似VSCode的命令面板：
- 模糊搜索命令
- 快捷键提示
- 最近使用记录
- 命令分类
"""

from typing import Dict, Callable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QWidget,
)
from PySide6.QtGui import QKeySequence

from backend.core.utils import LoggerMixin


class CommandPalette(QDialog, LoggerMixin):
    """命令面板对话框."""

    # 信号
    command_executed = Signal(str)  # 命令执行信号

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化命令面板."""
        super().__init__(parent)

        # 命令注册表：{command_id: {label, shortcut, callback, category}}
        self.commands: Dict[str, Dict] = {}

        # 最近使用的命令
        self.recent_commands: List[str] = []
        self.max_recent = 10

        # 设置UI
        self._setup_ui()

        # 注册默认命令
        self._register_default_commands()

        self.logger.info("命令面板初始化完成")

    def _setup_ui(self):
        """设置用户界面."""
        self.setWindowTitle("命令面板")
        self.setModal(True)
        self.setMinimumSize(600, 400)

        # 设置无边框窗口样式
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)

        layout = QVBoxLayout(self)

        # 搜索输入框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入命令名称或关键字...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._execute_selected_command)
        layout.addWidget(self.search_input)

        # 提示标签
        hint_label = QLabel("按 ↑↓ 选择命令，Enter 执行，Esc 关闭")
        hint_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(hint_label)

        # 命令列表
        self.command_list = QListWidget()
        self.command_list.itemDoubleClicked.connect(self._execute_selected_command)
        layout.addWidget(self.command_list)

        # 设置焦点到搜索框
        self.search_input.setFocus()

    def _register_default_commands(self):
        """注册默认命令."""
        # 文件操作
        self.register_command(
            "file.new", "文件: 新建策略", "Ctrl+N", None, "文件操作"  # callback需要从外部设置
        )

        self.register_command("file.open", "文件: 打开文件", "Ctrl+O", None, "文件操作")

        self.register_command("file.save", "文件: 保存", "Ctrl+S", None, "文件操作")

        self.register_command("file.save_all", "文件: 保存全部", "Ctrl+Shift+S", None, "文件操作")

        self.register_command("file.close", "文件: 关闭", "Ctrl+W", None, "文件操作")

        # 编辑操作
        self.register_command("edit.format", "编辑: 格式化代码", "Ctrl+Shift+F", None, "编辑操作")

        self.register_command("edit.comment", "编辑: 注释/取消注释", "Ctrl+/", None, "编辑操作")

        # 搜索
        self.register_command("search.find", "搜索: 查找", "Ctrl+F", None, "搜索")

        self.register_command("search.replace", "搜索: 替换", "Ctrl+H", None, "搜索")

        self.register_command("search.global", "搜索: 全局搜索", "Ctrl+Shift+F", None, "搜索")

        # 回测
        self.register_command("backtest.run", "回测: 运行当前策略", "F5", None, "回测")

        self.register_command("backtest.stop", "回测: 停止回测", "Shift+F5", None, "回测")

        # 调试
        self.register_command("debug.toggle_breakpoint", "调试: 切换断点", "F9", None, "调试")

        self.register_command("debug.clear_breakpoints", "调试: 清除所有断点", "", None, "调试")

        # AI助手
        self.register_command("ai.toggle", "AI: 显示/隐藏AI助手", "Ctrl+I", None, "AI助手")

        # 视图
        self.register_command(
            "view.command_palette", "视图: 打开命令面板", "Ctrl+Shift+P", None, "视图"
        )

    def register_command(
        self,
        command_id: str,
        label: str,
        shortcut: str,
        callback: Optional[Callable],
        category: str = "其他",
    ):
        """注册命令.

        Args:
            command_id: 命令ID
            label: 命令标签
            shortcut: 快捷键
            callback: 回调函数
            category: 命令分类
        """
        self.commands[command_id] = {
            "label": label,
            "shortcut": shortcut,
            "callback": callback,
            "category": category,
        }
        self.logger.debug(f"注册命令: {command_id} - {label}")

    def set_command_callback(self, command_id: str, callback: Callable):
        """设置命令回调函数.

        Args:
            command_id: 命令ID
            callback: 回调函数
        """
        if command_id in self.commands:
            self.commands[command_id]["callback"] = callback
            self.logger.debug(f"设置命令回调: {command_id}")

    def show_palette(self):
        """显示命令面板."""
        # 清空搜索框
        self.search_input.clear()

        # 加载所有命令
        self._load_all_commands()

        # 显示对话框
        self.exec()

    def _load_all_commands(self):
        """加载所有命令到列表."""
        self.command_list.clear()

        # 先显示最近使用的命令
        if self.recent_commands:
            # 添加分类标题
            title_item = QListWidgetItem("━━━ 最近使用 ━━━")
            title_item.setFlags(Qt.ItemFlag.NoItemFlags)  # 不可选择
            title_item.setForeground(Qt.GlobalColor.gray)
            self.command_list.addItem(title_item)

            for command_id in self.recent_commands:
                if command_id in self.commands:
                    self._add_command_to_list(command_id)

            # 添加分隔线
            separator = QListWidgetItem("")
            separator.setFlags(Qt.ItemFlag.NoItemFlags)
            self.command_list.addItem(separator)

        # 按分类显示所有命令
        categories = {}
        for command_id, command in self.commands.items():
            category = command["category"]
            if category not in categories:
                categories[category] = []
            categories[category].append(command_id)

        for category, command_ids in sorted(categories.items()):
            # 添加分类标题
            title_item = QListWidgetItem(f"━━━ {category} ━━━")
            title_item.setFlags(Qt.ItemFlag.NoItemFlags)
            title_item.setForeground(Qt.GlobalColor.gray)
            self.command_list.addItem(title_item)

            # 添加该分类的命令
            for command_id in sorted(command_ids):
                self._add_command_to_list(command_id)

        # 选中第一个可选项
        if self.command_list.count() > 0:
            for i in range(self.command_list.count()):
                item = self.command_list.item(i)
                if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                    self.command_list.setCurrentRow(i)
                    break

    def _add_command_to_list(self, command_id: str):
        """添加命令到列表.

        Args:
            command_id: 命令ID
        """
        command = self.commands[command_id]

        # 格式化显示：命令标签 + 快捷键
        label = command["label"]
        shortcut = command["shortcut"]

        if shortcut:
            display_text = f"{label}    ({shortcut})"
        else:
            display_text = label

        item = QListWidgetItem(display_text)
        item.setData(Qt.ItemDataRole.UserRole, command_id)
        self.command_list.addItem(item)

    def _on_search_text_changed(self, text: str):
        """搜索文本变化.

        Args:
            text: 搜索文本
        """
        query = text.strip().lower()

        if not query:
            # 显示所有命令
            self._load_all_commands()
            return

        # 模糊搜索
        self.command_list.clear()

        for command_id, command in self.commands.items():
            label = command["label"].lower()

            # 简单的模糊匹配
            if query in label:
                self._add_command_to_list(command_id)

        # 选中第一项
        if self.command_list.count() > 0:
            self.command_list.setCurrentRow(0)

    def _execute_selected_command(self):
        """执行选中的命令."""
        current_item = self.command_list.currentItem()
        if not current_item:
            return

        command_id = current_item.data(Qt.ItemDataRole.UserRole)
        if not command_id:
            return

        command = self.commands.get(command_id)
        if not command:
            return

        # 添加到最近使用
        if command_id in self.recent_commands:
            self.recent_commands.remove(command_id)
        self.recent_commands.insert(0, command_id)
        if len(self.recent_commands) > self.max_recent:
            self.recent_commands.pop()

        # 执行回调
        callback = command["callback"]
        if callback:
            try:
                callback()
                self.logger.info(f"执行命令: {command['label']}")
            except Exception as e:
                self.logger.error(f"执行命令失败: {command['label']}, 错误: {e}")

        # 发送信号
        self.command_executed.emit(command_id)

        # 关闭面板
        self.accept()

    def keyPressEvent(self, event):
        """按键事件."""
        if event.key() == Qt.Key.Key_Escape:
            # Esc关闭
            self.reject()
        elif event.key() == Qt.Key.Key_Down:
            # 向下选择（跳过不可选项）
            current_row = self.command_list.currentRow()
            for i in range(current_row + 1, self.command_list.count()):
                item = self.command_list.item(i)
                if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                    self.command_list.setCurrentRow(i)
                    break
        elif event.key() == Qt.Key.Key_Up:
            # 向上选择（跳过不可选项）
            current_row = self.command_list.currentRow()
            for i in range(current_row - 1, -1, -1):
                item = self.command_list.item(i)
                if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                    self.command_list.setCurrentRow(i)
                    break
        else:
            super().keyPressEvent(event)
