# -*- coding: utf-8 -*-
"""快捷键管理系统.

提供全局快捷键管理：
- 快捷键注册
- 快捷键冲突检测
- 快捷键配置持久化
"""

from typing import Dict, Callable, Optional
from pathlib import Path
import json

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget

from backend.core.service_base import LoggerMixin


class ShortcutManager(QObject, LoggerMixin):
    """快捷键管理器."""

    # 信号
    shortcut_triggered = Signal(str)  # 快捷键触发信号

    # 默认快捷键配置
    DEFAULT_SHORTCUTS = {
        # 文件操作
        "file.new": "Ctrl+N",
        "file.open": "Ctrl+O",
        "file.save": "Ctrl+S",
        "file.save_all": "Ctrl+Shift+S",
        "file.close": "Ctrl+W",
        "file.close_all": "Ctrl+Shift+W",
        "file.reopen": "Ctrl+Shift+T",
        # 编辑操作
        "edit.undo": "Ctrl+Z",
        "edit.redo": "Ctrl+Y",
        "edit.cut": "Ctrl+X",
        "edit.copy": "Ctrl+C",
        "edit.paste": "Ctrl+V",
        "edit.select_all": "Ctrl+A",
        "edit.find": "Ctrl+F",
        "edit.replace": "Ctrl+H",
        "edit.format": "Ctrl+Shift+F",
        "edit.comment": "Ctrl+/",
        # 导航
        "nav.goto_line": "Ctrl+G",
        "nav.goto_file": "Ctrl+P",
        "nav.next_tab": "Ctrl+Tab",
        "nav.prev_tab": "Ctrl+Shift+Tab",
        "nav.command_palette": "Ctrl+Shift+P",
        # 搜索
        "search.find_in_files": "Ctrl+Shift+F",
        "search.replace_in_files": "Ctrl+Shift+H",
        # 视图
        "view.toggle_sidebar": "Ctrl+B",
        "view.toggle_terminal": "Ctrl+`",
        "view.toggle_ai_assistant": "Ctrl+I",
        "view.zoom_in": "Ctrl++",
        "view.zoom_out": "Ctrl+-",
        "view.zoom_reset": "Ctrl+0",
        # 运行和调试
        "run.backtest": "F5",
        "run.stop": "Shift+F5",
        "debug.toggle_breakpoint": "F9",
        "debug.clear_breakpoints": "Ctrl+Shift+F9",
        "debug.step_over": "F10",
        "debug.step_into": "F11",
        "debug.step_out": "Shift+F11",
        # 终端
        "terminal.clear": "Ctrl+L",
        "terminal.new": "Ctrl+Shift+`",
        # 其他
        "other.save_layout": "Ctrl+Shift+L",
        "other.settings": "Ctrl+,",
        "other.help": "F1",
    }

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化快捷键管理器.

        Args:
            parent: 父组件
        """
        super().__init__(parent)

        self.parent_widget = parent

        # 快捷键映射：{action_id: {key_sequence, callback, shortcut_object}}
        self.shortcuts: Dict[str, Dict] = {}

        # 配置文件路径
        self.config_file = Path("config/shortcuts.json")

        # 加载配置
        self._load_config()

        self.logger.info("快捷键管理器初始化完成")

    def register_shortcut(
        self,
        action_id: str,
        callback: Callable,
        key_sequence: Optional[str] = None,
        description: str = "",
    ) -> bool:
        """注册快捷键.

        Args:
            action_id: 操作ID
            callback: 回调函数
            key_sequence: 快捷键序列（如果为None，使用默认配置）
            description: 描述

        Returns:
            bool: 是否注册成功
        """
        try:
            # 如果未指定快捷键，使用默认值
            if key_sequence is None:
                key_sequence = self.DEFAULT_SHORTCUTS.get(action_id, "")

            if not key_sequence:
                self.logger.warning(f"操作 {action_id} 没有快捷键")
                return False

            # 检查冲突
            if self._check_conflict(action_id, key_sequence):
                self.logger.warning(f"快捷键冲突: {key_sequence}")
                return False

            # 创建QShortcut
            if self.parent_widget:
                shortcut = QShortcut(QKeySequence(key_sequence), self.parent_widget)
                shortcut.activated.connect(lambda: self._on_shortcut_activated(action_id, callback))
            else:
                shortcut = None
                self.logger.warning(f"未设置父组件，无法创建快捷键: {action_id}")

            # 保存到映射
            self.shortcuts[action_id] = {
                "key_sequence": key_sequence,
                "callback": callback,
                "shortcut": shortcut,
                "description": description,
            }

            self.logger.info(f"注册快捷键: {action_id} = {key_sequence}")
            return True

        except Exception as e:
            self.logger.error(f"注册快捷键失败: {action_id}, 错误: {e}")
            return False

    def unregister_shortcut(self, action_id: str):
        """注销快捷键.

        Args:
            action_id: 操作ID
        """
        if action_id in self.shortcuts:
            shortcut_obj = self.shortcuts[action_id]["shortcut"]
            if shortcut_obj:
                shortcut_obj.setEnabled(False)
                shortcut_obj.deleteLater()

            del self.shortcuts[action_id]
            self.logger.info(f"注销快捷键: {action_id}")

    def update_shortcut(self, action_id: str, new_key_sequence: str) -> bool:
        """更新快捷键.

        Args:
            action_id: 操作ID
            new_key_sequence: 新的快捷键序列

        Returns:
            bool: 是否更新成功
        """
        if action_id not in self.shortcuts:
            self.logger.warning(f"操作 {action_id} 未注册")
            return False

        # 检查冲突
        if self._check_conflict(action_id, new_key_sequence):
            self.logger.warning(f"快捷键冲突: {new_key_sequence}")
            return False

        # 更新快捷键
        shortcut_info = self.shortcuts[action_id]
        shortcut_obj = shortcut_info["shortcut"]

        if shortcut_obj:
            shortcut_obj.setKey(QKeySequence(new_key_sequence))

        shortcut_info["key_sequence"] = new_key_sequence

        self.logger.info(f"更新快捷键: {action_id} = {new_key_sequence}")

        # 保存配置
        self._save_config()

        return True

    def get_shortcut_key(self, action_id: str) -> str:
        """获取操作的快捷键.

        Args:
            action_id: 操作ID

        Returns:
            str: 快捷键序列
        """
        if action_id in self.shortcuts:
            return self.shortcuts[action_id]["key_sequence"]
        return ""

    def get_all_shortcuts(self) -> Dict[str, str]:
        """获取所有快捷键.

        Returns:
            Dict: {action_id: key_sequence}
        """
        return {action_id: info["key_sequence"] for action_id, info in self.shortcuts.items()}

    def reset_to_defaults(self):
        """重置为默认快捷键."""
        # 注销所有现有快捷键
        for action_id in list(self.shortcuts.keys()):
            self.unregister_shortcut(action_id)

        # 删除配置文件
        if self.config_file.exists():
            self.config_file.unlink()

        self.logger.info("快捷键已重置为默认值")

    def _check_conflict(self, action_id: str, key_sequence: str) -> bool:
        """检查快捷键冲突.

        Args:
            action_id: 操作ID
            key_sequence: 快捷键序列

        Returns:
            bool: 是否存在冲突
        """
        for existing_id, info in self.shortcuts.items():
            if existing_id != action_id and info["key_sequence"] == key_sequence:
                return True
        return False

    def _on_shortcut_activated(self, action_id: str, callback: Callable):
        """快捷键激活回调.

        Args:
            action_id: 操作ID
            callback: 回调函数
        """
        try:
            self.logger.debug(f"快捷键触发: {action_id}")
            callback()
            self.shortcut_triggered.emit(action_id)
        except Exception as e:
            self.logger.error(f"快捷键回调执行失败: {action_id}, 错误: {e}")

    def _load_config(self):
        """加载配置."""
        if not self.config_file.exists():
            return

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            # 合并配置（覆盖默认值）
            for action_id, key_sequence in config.items():
                if action_id in self.DEFAULT_SHORTCUTS:
                    self.DEFAULT_SHORTCUTS[action_id] = key_sequence

            self.logger.info(f"快捷键配置已加载: {self.config_file}")

        except Exception as e:
            self.logger.error(f"加载快捷键配置失败: {e}")

    def _save_config(self):
        """保存配置."""
        try:
            # 确保配置目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            # 收集当前配置
            config = {action_id: info["key_sequence"] for action_id, info in self.shortcuts.items()}

            # 保存到文件
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            self.logger.info(f"快捷键配置已保存: {self.config_file}")

        except Exception as e:
            self.logger.error(f"保存快捷键配置失败: {e}")


# 全局快捷键描述（用于UI显示）
SHORTCUT_DESCRIPTIONS = {
    # 文件操作
    "file.new": "新建文件",
    "file.open": "打开文件",
    "file.save": "保存文件",
    "file.save_all": "保存所有文件",
    "file.close": "关闭文件",
    "file.close_all": "关闭所有文件",
    "file.reopen": "重新打开关闭的文件",
    # 编辑操作
    "edit.undo": "撤销",
    "edit.redo": "重做",
    "edit.cut": "剪切",
    "edit.copy": "复制",
    "edit.paste": "粘贴",
    "edit.select_all": "全选",
    "edit.find": "查找",
    "edit.replace": "替换",
    "edit.format": "格式化代码",
    "edit.comment": "注释/取消注释",
    # 导航
    "nav.goto_line": "跳转到行",
    "nav.goto_file": "快速打开文件",
    "nav.next_tab": "下一个标签",
    "nav.prev_tab": "上一个标签",
    "nav.command_palette": "命令面板",
    # 搜索
    "search.find_in_files": "全局搜索",
    "search.replace_in_files": "全局替换",
    # 视图
    "view.toggle_sidebar": "切换侧边栏",
    "view.toggle_terminal": "切换终端",
    "view.toggle_ai_assistant": "切换AI助手",
    "view.zoom_in": "放大",
    "view.zoom_out": "缩小",
    "view.zoom_reset": "重置缩放",
    # 运行和调试
    "run.backtest": "运行回测",
    "run.stop": "停止回测",
    "debug.toggle_breakpoint": "切换断点",
    "debug.clear_breakpoints": "清除所有断点",
    "debug.step_over": "单步跳过",
    "debug.step_into": "单步进入",
    "debug.step_out": "单步跳出",
    # 终端
    "terminal.clear": "清空终端",
    "terminal.new": "新建终端",
    # 其他
    "other.save_layout": "保存布局",
    "other.settings": "设置",
    "other.help": "帮助",
}
