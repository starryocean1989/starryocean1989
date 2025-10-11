# -*- coding: utf-8 -*-
"""策略中心组件包.

现代IDE风格的策略开发环境，包含：
- 多标签编辑器
- 文件管理器
- 全局搜索
- 内置终端
- 快捷键系统
"""

# 主视图
from ui.components.strategy_center.main_view import StrategyCenter

# 核心组件
from ui.components.strategy_center.editor_tabs import EditorTabWidget
from ui.components.strategy_center.file_explorer import (
    FileExplorerTree,
    FileExplorerWidget,
)
from ui.components.strategy_center.search_panel import SearchPanel
from ui.components.strategy_center.terminal_widget import TerminalWidget
from ui.components.strategy_center.shortcut_manager import (
    ShortcutManager,
    SHORTCUT_DESCRIPTIONS,
)

__all__ = [
    # 主视图
    "StrategyCenter",
    # 核心组件
    "EditorTabWidget",
    "FileExplorerTree",
    "FileExplorerWidget",
    "SearchPanel",
    "TerminalWidget",
    # 工具组件
    "ShortcutManager",
    "SHORTCUT_DESCRIPTIONS",
]

# 版本信息
__version__ = "0.2.0"
__author__ = "Strategy Center Team"
__description__ = "现代IDE风格的策略开发环境（重构版）"
