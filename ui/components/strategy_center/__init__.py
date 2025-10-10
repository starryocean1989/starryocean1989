# -*- coding: utf-8 -*-
"""策略中心组件包.

现代IDE风格的策略开发环境，包含：
- 多标签编辑器
- 文件管理器
- 全局搜索
- 命令面板
- 内置终端
- 调试器
- Git集成
- 文件对比
- 快捷键系统
- 代码片段
"""

# 主视图
from ui.components.strategy_center.main_view import StrategyCenter
from ui.components.strategy_center.main_view_refactored import StrategyCenterRefactored

# 核心组件
from ui.components.strategy_center.editor_tabs import EditorTabWidget
from ui.components.strategy_center.file_explorer import (
    FileExplorerTree,
    FileExplorerWidget,
)
from ui.components.strategy_center.search_panel import SearchPanel
from ui.components.strategy_center.command_palette import CommandPalette
from ui.components.strategy_center.terminal_widget import TerminalWidget

# 调试组件
from ui.components.strategy_center.debugger import Debugger
from ui.components.strategy_center.debug_panel import DebugPanel

# 工具组件
from ui.components.strategy_center.shortcut_manager import (
    ShortcutManager,
    SHORTCUT_DESCRIPTIONS,
)
from ui.components.strategy_center.snippets import SnippetManager
from ui.components.strategy_center.git_panel import GitPanel
from ui.components.strategy_center.diff_viewer import DiffViewer

__all__ = [
    # 主视图
    "StrategyCenter",
    "StrategyCenterRefactored",
    # 核心组件
    "EditorTabWidget",
    "FileExplorerTree",
    "FileExplorerWidget",
    "SearchPanel",
    "CommandPalette",
    "TerminalWidget",
    # 调试组件
    "Debugger",
    "DebugPanel",
    # 工具组件
    "ShortcutManager",
    "SHORTCUT_DESCRIPTIONS",
    "SnippetManager",
    "GitPanel",
    "DiffViewer",
]

# 版本信息
__version__ = "0.1.0"
__author__ = "Strategy Center Team"
__description__ = "现代IDE风格的策略开发环境"
