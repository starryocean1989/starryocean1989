# -*- coding: utf-8 -*-
"""策略中心IDE快速开始示例.

演示如何使用新的IDE功能。

运行方式：
    python 策略中心IDE快速开始示例.py
"""

import sys
from pathlib import Path

# 添加项目路径到sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication, QMainWindow, QSplitter, QTabWidget, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut

# 导入策略中心IDE组件
from ui.components.strategy_center.editor_tabs import EditorTabWidget
from ui.components.strategy_center.file_explorer import FileExplorerWidget
from ui.components.strategy_center.search_panel import SearchPanel
from ui.components.strategy_center.command_palette import CommandPalette
from ui.components.strategy_center.terminal_widget import TerminalWidget
from ui.components.strategy_center.debugger import Debugger
from ui.components.strategy_center.debug_panel import DebugPanel
from ui.components.strategy_center.shortcut_manager import ShortcutManager
from ui.components.strategy_center.snippets import SnippetManager
from ui.components.strategy_center.git_panel import GitPanel
from ui.components.strategy_center.diff_viewer import DiffViewer


class StrategyIDEDemo(QMainWindow):
    """策略IDE演示窗口."""

    def __init__(self):
        """初始化演示窗口."""
        super().__init__()

        self.setWindowTitle("策略中心 - IDE模式（演示）")
        self.resize(1400, 900)

        # 创建所有组件
        self._create_components()

        # 创建布局
        self._create_layout()

        # 连接信号
        self._connect_signals()

        # 设置快捷键
        self._setup_shortcuts()

        # 显示欢迎消息
        self._show_welcome()

    def _create_components(self):
        """创建所有组件."""
        print("📦 创建组件...")

        # 核心组件
        self.editor_tabs = EditorTabWidget()
        self.file_explorer = FileExplorerWidget("strategies/user_strategies")
        self.search_panel = SearchPanel("strategies/user_strategies")
        self.command_palette = CommandPalette()
        self.terminal = TerminalWidget()

        # 调试组件
        self.debugger = Debugger()
        self.debug_panel = DebugPanel(self.debugger)

        # 工具组件
        self.git_panel = GitPanel()
        self.diff_viewer = DiffViewer()

        # 管理器
        self.shortcut_manager = ShortcutManager(parent=self)
        self.snippet_manager = SnippetManager()

        print("✅ 组件创建完成")

    def _create_layout(self):
        """创建布局."""
        print("🎨 创建布局...")

        # 主垂直分割器
        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # 上部：水平分割器
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：文件管理器
        top_splitter.addWidget(self.file_explorer)

        # 中央：编辑器
        top_splitter.addWidget(self.editor_tabs)

        # 右侧：工具面板
        right_tabs = QTabWidget()
        right_tabs.addTab(self.search_panel, "🔍 搜索")
        right_tabs.addTab(self.debug_panel, "🐛 调试")
        right_tabs.addTab(self.git_panel, "📦 Git")
        right_tabs.addTab(self.diff_viewer, "🔄 对比")
        top_splitter.addWidget(right_tabs)

        # 设置比例
        top_splitter.setSizes([200, 800, 300])

        main_splitter.addWidget(top_splitter)

        # 下部：底部面板
        bottom_tabs = QTabWidget()
        bottom_tabs.addTab(self.terminal, "🖥️ 终端")

        from PySide6.QtWidgets import QTextEdit

        output_text = QTextEdit()
        output_text.setPlaceholderText("输出信息将显示在这里...")
        output_text.setReadOnly(True)
        bottom_tabs.addTab(output_text, "📋 输出")

        main_splitter.addWidget(bottom_tabs)

        # 设置比例
        main_splitter.setSizes([700, 200])

        self.setCentralWidget(main_splitter)

        print("✅ 布局创建完成")

    def _connect_signals(self):
        """连接信号槽."""
        print("🔗 连接信号...")

        # 文件管理器 -> 编辑器
        self.file_explorer.file_double_clicked.connect(self.editor_tabs.open_file)

        # 搜索面板 -> 编辑器
        self.search_panel.file_selected.connect(self._open_file_at_line)

        # 调试面板 -> 编辑器
        self.debug_panel.breakpoint_clicked.connect(self._open_file_at_line)

        # 编辑器 -> 状态栏
        self.editor_tabs.file_saved.connect(
            lambda path: self.statusBar().showMessage(f"已保存: {Path(path).name}", 3000)
        )

        print("✅ 信号连接完成")

    def _setup_shortcuts(self):
        """设置快捷键."""
        print("⌨️ 设置快捷键...")

        # 注册核心快捷键
        self.shortcut_manager.register_shortcut(
            "file.save", self.editor_tabs.save_file, description="保存文件"
        )

        self.shortcut_manager.register_shortcut(
            "file.save_all", self.editor_tabs.save_all_files, description="保存所有文件"
        )

        self.shortcut_manager.register_shortcut(
            "nav.command_palette", self.command_palette.show_palette, description="打开命令面板"
        )

        # 设置命令面板回调
        self.command_palette.set_command_callback("file.save", self.editor_tabs.save_file)
        self.command_palette.set_command_callback("file.save_all", self.editor_tabs.save_all_files)
        self.command_palette.set_command_callback("file.close", self.editor_tabs._close_current_tab)

        print(f"✅ 快捷键设置完成（{len(self.shortcut_manager.shortcuts)}个）")

    def _open_file_at_line(self, file_path: str, line_num: int = 0):
        """打开文件并跳转到指定行.

        Args:
            file_path: 文件路径
            line_num: 行号
        """
        # 打开文件
        self.editor_tabs.open_file(file_path)

        # TODO: 实现跳转到行号功能
        # 需要在Monaco Editor中添加goToLine方法
        if line_num > 0:
            print(f"📍 跳转到: {file_path}:{line_num}")

    def _show_welcome(self):
        """显示欢迎消息."""
        welcome_text = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    策略中心 - IDE模式（演示）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎉 欢迎使用现代IDE风格的策略开发环境！

📚 核心功能：
  • 多标签编辑（Ctrl+Tab切换）
  • 文件管理器（右键菜单、拖拽）
  • 全局搜索（Ctrl+Shift+F）
  • 命令面板（Ctrl+Shift+P）
  • Python终端（实时执行代码）
  • 断点调试（F9设置断点）
  • Git集成（查看状态、提交）
  • 文件对比（差异高亮）

⌨️ 快捷键提示：
  Ctrl+N       - 新建文件
  Ctrl+S       - 保存文件
  Ctrl+W       - 关闭标签
  Ctrl+P       - 快速打开
  Ctrl+Shift+P - 命令面板
  F9           - 切换断点
  F5           - 运行回测

💡 提示：
  1. 按 Ctrl+Shift+P 打开命令面板查看所有命令
  2. 在文件管理器中右键查看更多操作
  3. 使用搜索面板进行全局搜索
  4. 在终端中测试Python代码片段

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
开始编码吧！ 🚀
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        self.terminal.write(welcome_text)

        # 在状态栏显示提示
        self.statusBar().showMessage("按 Ctrl+Shift+P 打开命令面板", 10000)


def main():
    """主函数."""
    print("\n" + "=" * 50)
    print("  策略中心IDE演示程序")
    print("=" * 50 + "\n")

    # 创建应用
    app = QApplication(sys.argv)

    # 设置应用样式
    app.setStyle("Fusion")

    # 创建主窗口
    window = StrategyIDEDemo()
    window.show()

    print("\n✅ IDE窗口已打开")
    print("💡 提示：按 Ctrl+Shift+P 打开命令面板")
    print("💡 提示：双击文件管理器中的文件打开")
    print("\n" + "=" * 50 + "\n")

    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
