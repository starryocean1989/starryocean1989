# -*- coding: utf-8 -*-
"""内置终端组件.

提供Python REPL和输出查看：
- Python代码执行
- 命令历史
- 输出重定向
"""

from typing import List, Optional
import sys
from io import StringIO

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTextEdit,
    QLineEdit,
    QHBoxLayout,
    QPushButton,
)
from PySide6.QtGui import QTextCursor, QFont

from backend.core.utils import LoggerMixin


class TerminalWidget(QWidget, LoggerMixin):
    """内置终端组件."""

    # 信号
    command_executed = Signal(str)  # 命令执行信号

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化终端组件."""
        super().__init__(parent)

        # 命令历史
        self.command_history: List[str] = []
        self.history_index = -1
        self.max_history = 100

        # Python环境
        self.python_globals = {}
        self.python_locals = {}

        # 设置UI
        self._setup_ui()

        # 初始化Python环境
        self._init_python_env()

        # 显示欢迎信息
        self._show_welcome()

        self.logger.info("终端组件初始化完成")

    def _setup_ui(self):
        """设置用户界面."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 输出区域
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Consolas, Monaco, Courier New", 10))
        self.output_text.setStyleSheet(
            """
            QTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: none;
            }
        """
        )
        layout.addWidget(self.output_text)

        # 输入区域
        input_layout = QHBoxLayout()

        # 提示符
        prompt_label = QPushButton(">>>")
        prompt_label.setMaximumWidth(40)
        prompt_label.setFlat(True)
        prompt_label.setStyleSheet(
            """
            QPushButton {
                background-color: #1E1E1E;
                color: #4EC9B0;
                border: none;
                font-family: 'Consolas, Monaco, Courier New';
                font-size: 10pt;
                text-align: right;
                padding-right: 5px;
            }
        """
        )
        input_layout.addWidget(prompt_label)

        # 输入框
        self.input_line = QLineEdit()
        self.input_line.setFont(QFont("Consolas, Monaco, Courier New", 10))
        self.input_line.setStyleSheet(
            """
            QLineEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                padding: 3px;
            }
        """
        )
        self.input_line.returnPressed.connect(self._execute_command)
        input_layout.addWidget(self.input_line)

        # 清空按钮
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear_output)
        input_layout.addWidget(clear_btn)

        layout.addLayout(input_layout)

        # 设置焦点
        self.input_line.setFocus()

    def _init_python_env(self):
        """初始化Python环境."""
        # 导入常用模块
        self.python_globals = {
            "__name__": "__console__",
            "__doc__": None,
        }

        # 导入常用库
        try:
            import numpy as np
            import pandas as pd
            from pathlib import Path

            self.python_globals["np"] = np
            self.python_globals["pd"] = pd
            self.python_globals["Path"] = Path

            self.logger.info("Python环境初始化完成（numpy, pandas, Path）")
        except ImportError as e:
            self.logger.warning(f"导入模块失败: {e}")

    def _show_welcome(self):
        """显示欢迎信息."""
        welcome_text = f"""
<span style='color: #4EC9B0;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>
<span style='color: #DCDCAA;'>欢迎使用策略中心 Python 终端</span>
<span style='color: #4EC9B0;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>

<span style='color: #9CDCFE;'>Python版本:</span> {sys.version}

<span style='color: #9CDCFE;'>可用模块:</span> numpy (np), pandas (pd), Path

<span style='color: #9CDCFE;'>提示:</span>
  • 输入Python代码并按Enter执行
  • 使用 ↑↓ 键浏览命令历史
  • 输入 help() 查看帮助
  • 输入 clear() 清空屏幕

<span style='color: #4EC9B0;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>
"""
        self.output_text.append(welcome_text)

    def _execute_command(self):
        """执行命令."""
        command = self.input_line.text().strip()
        if not command:
            return

        # 添加到历史
        self.command_history.append(command)
        if len(self.command_history) > self.max_history:
            self.command_history.pop(0)
        self.history_index = len(self.command_history)

        # 清空输入框
        self.input_line.clear()

        # 显示命令
        self._append_output(f"<span style='color: #4EC9B0;'>&gt;&gt;&gt;</span> {command}")

        # 特殊命令处理
        if command == "clear()" or command == "clear":
            self._clear_output()
            return

        if command == "help()" or command == "help":
            self._show_help()
            return

        # 执行Python代码
        self._execute_python(command)

        # 发送信号
        self.command_executed.emit(command)

    def _execute_python(self, code: str):
        """执行Python代码.

        Args:
            code: Python代码
        """
        try:
            # 重定向stdout和stderr
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = StringIO()
            sys.stderr = StringIO()

            try:
                # 尝试作为表达式执行（有返回值）
                result = eval(code, self.python_globals, self.python_locals)

                # 获取输出
                stdout_output = sys.stdout.getvalue()
                stderr_output = sys.stderr.getvalue()

                # 显示输出
                if stdout_output:
                    self._append_output(f"<span style='color: #CE9178;'>{stdout_output}</span>")

                if stderr_output:
                    self._append_output(f"<span style='color: #F48771;'>{stderr_output}</span>")

                # 显示返回值（除了None）
                if result is not None:
                    self._append_output(f"<span style='color: #DCDCAA;'>{repr(result)}</span>")

            except SyntaxError:
                # 作为语句执行（无返回值）
                sys.stdout = StringIO()
                sys.stderr = StringIO()

                exec(code, self.python_globals, self.python_locals)

                # 获取输出
                stdout_output = sys.stdout.getvalue()
                stderr_output = sys.stderr.getvalue()

                # 显示输出
                if stdout_output:
                    self._append_output(f"<span style='color: #CE9178;'>{stdout_output}</span>")

                if stderr_output:
                    self._append_output(f"<span style='color: #F48771;'>{stderr_output}</span>")

            finally:
                # 恢复stdout和stderr
                sys.stdout = old_stdout
                sys.stderr = old_stderr

        except Exception as e:
            # 显示错误
            error_msg = f"{type(e).__name__}: {str(e)}"
            self._append_output(f"<span style='color: #F48771;'>❌ {error_msg}</span>")
            self.logger.error(f"Python代码执行失败: {e}", exc_info=True)

    def _append_output(self, text: str):
        """添加输出文本.

        Args:
            text: 输出文本
        """
        self.output_text.append(text)

        # 滚动到底部
        cursor = self.output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_text.setTextCursor(cursor)

    def _clear_output(self):
        """清空输出."""
        self.output_text.clear()
        self._show_welcome()

    def _show_help(self):
        """显示帮助信息."""
        help_text = """
<span style='color: #DCDCAA;'>━━━ 帮助信息 ━━━</span>

<span style='color: #9CDCFE;'>可用命令:</span>
  • clear() - 清空屏幕
  • help() - 显示此帮助信息
  • dir(obj) - 列出对象的属性
  • type(obj) - 查看对象类型
  • help(obj) - 查看对象帮助文档

<span style='color: #9CDCFE;'>可用模块:</span>
  • np - NumPy
  • pd - Pandas
  • Path - pathlib.Path

<span style='color: #9CDCFE;'>示例:</span>
  &gt;&gt;&gt; 1 + 1
  &gt;&gt;&gt; print("Hello, World!")
  &gt;&gt;&gt; import math
  &gt;&gt;&gt; math.sqrt(16)
  &gt;&gt;&gt; df = pd.DataFrame({'A': [1, 2, 3]})
"""
        self._append_output(help_text)

    def keyPressEvent(self, event):
        """按键事件."""
        if event.key() == Qt.Key.Key_Up:
            # 向上浏览历史
            if self.command_history and self.history_index > 0:
                self.history_index -= 1
                self.input_line.setText(self.command_history[self.history_index])

        elif event.key() == Qt.Key.Key_Down:
            # 向下浏览历史
            if self.command_history and self.history_index < len(self.command_history) - 1:
                self.history_index += 1
                self.input_line.setText(self.command_history[self.history_index])
            elif self.history_index == len(self.command_history) - 1:
                self.history_index = len(self.command_history)
                self.input_line.clear()

        else:
            super().keyPressEvent(event)

    def write(self, text: str):
        """写入输出（用于重定向输出）.

        Args:
            text: 输出文本
        """
        self._append_output(text.rstrip())

    def execute_code(self, code: str):
        """执行代码（外部调用）.

        Args:
            code: Python代码
        """
        self._append_output(f"<span style='color: #4EC9B0;'>&gt;&gt;&gt;</span> {code}")
        self._execute_python(code)
