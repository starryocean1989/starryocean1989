# -*- coding: utf-8 -*-
"""
快捷键管理器

提供全局快捷键注册、管理和配置持久化功能。
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QKeySequence, QShortcut

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class ShortcutManager(QObject):
    """快捷键管理器"""

    # 快捷键触发信号
    shortcut_triggered = Signal(str, str)  # (action_name, description)

    # 预设全局快捷键
    DEFAULT_SHORTCUTS = {
        # 文件操作
        "Ctrl+S": {"action": "save_file", "description": "保存当前文件"},
        "Ctrl+N": {"action": "new_strategy", "description": "新建策略"},
        "Ctrl+O": {"action": "open_file", "description": "打开文件"},
        "Ctrl+W": {"action": "close_tab", "description": "关闭当前标签页"},
        # 数据操作
        "F5": {"action": "refresh_data", "description": "刷新数据"},
        "Ctrl+R": {"action": "reload_symbols", "description": "重新加载品种"},
        "Ctrl+D": {"action": "download_data", "description": "下载数据"},
        # 策略操作
        "F9": {"action": "run_backtest", "description": "运行回测"},
        "Ctrl+B": {"action": "format_code", "description": "格式化代码"},
        "Ctrl+/": {"action": "toggle_comment", "description": "切换注释"},
        # 交易操作
        "Ctrl+G": {"action": "connect_gateway", "description": "连接网关"},
        "Space": {"action": "toggle_strategy", "description": "启停策略"},
        # 界面操作
        "Ctrl+Tab": {"action": "next_interface", "description": "切换到下一个功能界面"},
        "Ctrl+Shift+Tab": {
            "action": "prev_interface",
            "description": "切换到上一个功能界面",
        },
        "Ctrl+1": {"action": "goto_system", "description": "跳转到系统管理"},
        "Ctrl+2": {"action": "goto_data", "description": "跳转到数据中心"},
        "Ctrl+3": {"action": "goto_market", "description": "跳转到行情看板"},
        "Ctrl+4": {"action": "goto_strategy", "description": "跳转到策略中心"},
        "Ctrl+5": {"action": "goto_trading", "description": "跳转到交易网关"},
        "Ctrl+6": {"action": "goto_portfolio", "description": "跳转到组合投资"},
        # 系统操作
        "Ctrl+,": {"action": "open_settings", "description": "打开设置"},
        "Ctrl+H": {"action": "show_help", "description": "显示帮助"},
        "F11": {"action": "toggle_fullscreen", "description": "切换全屏"},
        "Ctrl+Q": {"action": "quit_app", "description": "退出应用"},
        # 行情看板特定
        "Left": {"action": "chart_prev_bar", "description": "上一根K线"},
        "Right": {"action": "chart_next_bar", "description": "下一根K线"},
        "+": {"action": "chart_zoom_in", "description": "放大图表"},
        "-": {"action": "chart_zoom_out", "description": "缩小图表"},
    }

    def __init__(self, parent: "Optional[QWidget]" = None):
        """
        初始化快捷键管理器

        Args:
            parent: 父窗口（通常是主窗口）
        """
        super().__init__(parent)
        self.parent_widget = parent
        self.shortcuts: Dict[str, QShortcut] = {}
        self.custom_shortcuts: Dict[str, Dict] = {}
        self.action_callbacks: Dict[str, Callable] = {}

        # 配置文件路径
        self.config_file = Path("config/shortcuts.json")

        # 加载自定义快捷键
        self._load_custom_shortcuts()

        logger.info("快捷键管理器初始化完成")

    def register_shortcut(
        self,
        key_sequence: str,
        action_name: str,
        description: str,
        callback: Optional[Callable] = None,
        widget: "Optional[QWidget]" = None,
    ) -> bool:
        """
        注册快捷键

        Args:
            key_sequence: 快捷键序列（如"Ctrl+S"）
            action_name: 动作名称
            description: 描述
            callback: 回调函数（可选）
            widget: 作用域窗口（None表示全局）

        Returns:
            bool: 是否注册成功
        """
        try:
            # 检查冲突
            if key_sequence in self.shortcuts:
                logger.warning("快捷键冲突: %s 已被占用", key_sequence)
                return False

            # 创建快捷键
            parent = widget or self.parent_widget
            if not parent:
                logger.error("无法注册快捷键 %s：未指定parent", key_sequence)
                return False

            shortcut = QShortcut(QKeySequence(key_sequence), parent)

            # 连接回调
            if callback:
                shortcut.activated.connect(callback)
                self.action_callbacks[action_name] = callback
            else:
                # 使用默认信号
                shortcut.activated.connect(
                    lambda: self.shortcut_triggered.emit(action_name, description)
                )

            # 保存快捷键
            self.shortcuts[key_sequence] = shortcut

            logger.info("注册快捷键: %s -> %s", key_sequence, action_name)
            return True

        except Exception as e:
            logger.error("注册快捷键失败 %s: %s", key_sequence, e)
            return False

    def unregister_shortcut(self, key_sequence: str) -> bool:
        """
        取消注册快捷键

        Args:
            key_sequence: 快捷键序列

        Returns:
            bool: 是否成功
        """
        if key_sequence in self.shortcuts:
            shortcut = self.shortcuts.pop(key_sequence)
            shortcut.setEnabled(False)
            logger.info("取消注册快捷键: %s", key_sequence)
            return True
        return False

    def register_default_shortcuts(self) -> None:
        """注册所有默认快捷键"""
        for key_seq, info in self.DEFAULT_SHORTCUTS.items():
            self.register_shortcut(key_seq, info["action"], info["description"])
        logger.info("注册了%d个默认快捷键", len(self.DEFAULT_SHORTCUTS))

    def get_all_shortcuts(self) -> Dict[str, Dict]:
        """获取所有快捷键配置"""
        shortcuts = {}
        for key_seq, info in self.DEFAULT_SHORTCUTS.items():
            shortcuts[key_seq] = info
        # 合并自定义快捷键
        shortcuts.update(self.custom_shortcuts)
        return shortcuts

    def set_custom_shortcut(
        self, key_sequence: str, action_name: str, description: str
    ) -> bool:
        """
        设置自定义快捷键

        Args:
            key_sequence: 快捷键序列
            action_name: 动作名称
            description: 描述

        Returns:
            bool: 是否成功
        """
        try:
            # 检查冲突
            if key_sequence in self.DEFAULT_SHORTCUTS:
                logger.warning("无法覆盖默认快捷键: %s", key_sequence)
                return False

            # 保存自定义快捷键
            self.custom_shortcuts[key_sequence] = {
                "action": action_name,
                "description": description,
            }

            # 持久化
            self._save_custom_shortcuts()

            # 注册快捷键
            self.register_shortcut(key_sequence, action_name, description)

            logger.info("设置自定义快捷键: %s", key_sequence)
            return True

        except Exception as e:
            logger.error("设置自定义快捷键失败: %s", e)
            return False

    def remove_custom_shortcut(self, key_sequence: str) -> bool:
        """移除自定义快捷键"""
        if key_sequence in self.custom_shortcuts:
            del self.custom_shortcuts[key_sequence]
            self.unregister_shortcut(key_sequence)
            self._save_custom_shortcuts()
            logger.info("移除自定义快捷键: %s", key_sequence)
            return True
        return False

    def _load_custom_shortcuts(self) -> None:
        """从配置文件加载自定义快捷键"""
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.custom_shortcuts = json.load(f)
                logger.info("加载了%d个自定义快捷键", len(self.custom_shortcuts))
        except Exception as e:
            logger.error("加载自定义快捷键失败: %s", e)
            self.custom_shortcuts = {}

    def _save_custom_shortcuts(self) -> None:
        """保存自定义快捷键到配置文件"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.custom_shortcuts, f, indent=2, ensure_ascii=False)
            logger.info("保存自定义快捷键成功")
        except Exception as e:
            logger.error("保存自定义快捷键失败: %s", e)

    def get_shortcut_help(self) -> str:
        """生成快捷键帮助文档"""
        help_text = "# 快捷键列表\n\n"

        # 按类别组织
        categories = {
            "文件操作": ["save_file", "new_strategy", "open_file", "close_tab"],
            "数据操作": ["refresh_data", "reload_symbols", "download_data"],
            "策略操作": ["run_backtest", "format_code", "toggle_comment"],
            "交易操作": ["connect_gateway", "toggle_strategy"],
            "界面操作": [
                "next_interface",
                "prev_interface",
                "goto_system",
                "goto_data",
                "goto_market",
                "goto_strategy",
                "goto_trading",
                "goto_portfolio",
            ],
            "系统操作": ["open_settings", "show_help", "toggle_fullscreen", "quit_app"],
            "行情操作": [
                "chart_prev_bar",
                "chart_next_bar",
                "chart_zoom_in",
                "chart_zoom_out",
            ],
        }

        all_shortcuts = self.get_all_shortcuts()

        for category, actions in categories.items():
            help_text += f"## {category}\n\n"
            for key_seq, info in all_shortcuts.items():
                if info["action"] in actions:
                    help_text += f"- **{key_seq}**: {info['description']}\n"
            help_text += "\n"

        return help_text

    def export_to_file(self, file_path: str) -> bool:
        """导出快捷键列表到文件"""
        try:
            help_text = self.get_shortcut_help()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(help_text)
            logger.info("快捷键帮助文档已导出到: %s", file_path)
            return True
        except Exception as e:
            logger.error("导出快捷键帮助文档失败: %s", e)
            return False


__all__ = ["ShortcutManager"]
