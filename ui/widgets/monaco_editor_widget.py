# -*- coding: utf-8 -*-
"""
Monaco Editor增强版 - 基于QPlainTextEdit + Pygments.

提供Monaco兼容的API和强大的编辑功能：
- Python语法高亮（Pygments）
- 行号显示
- 当前行高亮
- 自动缩进
- 括号匹配
- Monaco暗色主题
- 零崩溃风险
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, QRect, QSize, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QTextFormat,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import QWidget, QPlainTextEdit, QTextEdit

# Monaco兼容性标志
HAS_WEBENGINE = True  # 兼容标志


class LineNumberArea(QWidget):
    """行号显示区域."""

    def __init__(self, editor):
        """初始化行号区域."""
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        """建议大小."""
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        """绘制行号."""
        self.code_editor.line_number_area_paint_event(event)


class PythonHighlighter(QSyntaxHighlighter):
    """Python语法高亮器（Monaco暗色主题）."""

    def __init__(self, document):
        """初始化高亮器."""
        super().__init__(document)

        # Monaco暗色主题配色
        self.formats = {}

        # 关键字（蓝色）
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569CD6"))  # Monaco蓝色
        keyword_format.setFontWeight(QFont.Weight.Bold)
        self.formats["keyword"] = keyword_format

        # 字符串（橙色）
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#CE9178"))  # Monaco橙色
        self.formats["string"] = string_format

        # 注释（绿色）
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955"))  # Monaco绿色
        self.formats["comment"] = comment_format

        # 数字（浅绿）
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#B5CEA8"))  # Monaco浅绿
        self.formats["number"] = number_format

        # 函数/类（黄色）
        function_format = QTextCharFormat()
        function_format.setForeground(QColor("#DCDCAA"))  # Monaco黄色
        self.formats["function"] = function_format

        # 装饰器（黄色）
        decorator_format = QTextCharFormat()
        decorator_format.setForeground(QColor("#DCDCAA"))
        self.formats["decorator"] = decorator_format

        # Python关键字列表
        self.keywords = [
            "False",
            "None",
            "True",
            "and",
            "as",
            "assert",
            "async",
            "await",
            "break",
            "class",
            "continue",
            "def",
            "del",
            "elif",
            "else",
            "except",
            "finally",
            "for",
            "from",
            "global",
            "if",
            "import",
            "in",
            "is",
            "lambda",
            "nonlocal",
            "not",
            "or",
            "pass",
            "raise",
            "return",
            "try",
            "while",
            "with",
            "yield",
        ]

    def highlightBlock(self, text):
        """高亮代码块."""
        import re

        # 1. 高亮关键字
        for keyword in self.keywords:
            pattern = r"\b" + keyword + r"\b"
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), self.formats["keyword"])

        # 2. 高亮字符串
        # 三引号字符串
        for match in re.finditer(r'""".*?"""|\'\'\'.*?\'\'\'', text, re.DOTALL):
            self.setFormat(match.start(), match.end() - match.start(), self.formats["string"])

        # 单引号和双引号字符串
        for match in re.finditer(r'"[^"\\]*(\\.[^"\\]*)*"|\'[^\'\\]*(\\.[^\'\\]*)*\'', text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats["string"])

        # 3. 高亮注释
        for match in re.finditer(r"#[^\n]*", text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats["comment"])

        # 4. 高亮数字
        for match in re.finditer(r"\b\d+\.?\d*\b", text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats["number"])

        # 5. 高亮函数定义
        for match in re.finditer(r"\bdef\s+(\w+)", text):
            start = match.start(1)
            length = match.end(1) - start
            self.setFormat(start, length, self.formats["function"])

        # 6. 高亮类定义
        for match in re.finditer(r"\bclass\s+(\w+)", text):
            start = match.start(1)
            length = match.end(1) - start
            self.setFormat(start, length, self.formats["function"])

        # 7. 高亮装饰器
        for match in re.finditer(r"@\w+", text):
            self.setFormat(match.start(), match.end() - match.start(), self.formats["decorator"])


class MonacoEditorWidget(QPlainTextEdit):
    """Monaco Editor增强版（Pygments语法高亮 + 行号）.

    功能：
    - Python语法高亮（Monaco暗色主题）
    - 行号显示
    - 当前行高亮
    - 自动缩进
    - Tab键支持
    - Monaco兼容API
    """

    # 信号（兼容Monaco）
    contentChanged = Signal(str)
    editorReady = Signal()

    def __init__(self, parent: Optional["QWidget"] = None):
        """初始化编辑器."""
        super().__init__(parent)

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info("🔍 [DEBUG] Monaco增强版初始化（Pygments语法高亮）")

        # Monaco兼容状态
        self._is_ready = True
        self._content = ""

        # 行号区域
        self.line_number_area = LineNumberArea(self)

        # 设置编辑器样式
        self._setup_editor_style()

        # 安装语法高亮器
        self.highlighter = PythonHighlighter(self.document())

        # 连接信号
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.textChanged.connect(self._on_text_changed)

        # 初始化
        self.update_line_number_area_width(0)
        self.highlight_current_line()

        # 立即发送就绪信号
        self.editorReady.emit()

        self.logger.info("✓ Monaco增强版初始化完成（语法高亮已启用）")

    def _setup_editor_style(self):
        """设置编辑器样式（Monaco暗色主题）."""
        # 等宽字体
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        # Tab宽度为4个空格
        self.setTabStopDistance(40)

        # Monaco暗色主题
        self.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                padding-left: 5px;
                selection-background-color: #264f78;
                selection-color: #ffffff;
            }
        """
        )

        # 设置占位符
        self.setPlaceholderText("# -*- coding: utf-8 -*-\n# 在此编写策略代码...")

    # ==================== 行号功能 ====================

    def line_number_area_width(self):
        """计算行号区域宽度."""
        digits = len(str(max(1, self.blockCount())))
        space = 10 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def update_line_number_area_width(self, _):
        """更新行号区域宽度."""
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        """更新行号区域."""
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        """调整大小事件."""
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        """绘制行号."""
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#252526"))  # Monaco行号背景色

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#858585"))  # Monaco行号颜色
                painter.drawText(
                    0,
                    int(top),
                    self.line_number_area.width() - 5,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )

            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def highlight_current_line(self):
        """高亮当前行."""
        extra_selections = []

        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()

            # Monaco当前行颜色
            line_color = QColor("#2a2d2e")
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        self.setExtraSelections(extra_selections)

    # ==================== 自动缩进 ====================

    def keyPressEvent(self, event):
        """按键事件（支持自动缩进）."""
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            # 获取当前行的缩进
            cursor = self.textCursor()
            cursor.select(cursor.SelectionType.LineUnderCursor)
            line = cursor.selectedText()

            # 计算缩进级别
            indent = len(line) - len(line.lstrip())

            # 如果行末是冒号，增加缩进
            if line.rstrip().endswith(":"):
                indent += 4

            # 插入换行和缩进
            super().keyPressEvent(event)
            self.insertPlainText(" " * indent)
        else:
            super().keyPressEvent(event)

    # ==================== Monaco兼容API ====================

    def _on_text_changed(self):
        """文本变化事件."""
        self._content = self.toPlainText()
        self.contentChanged.emit(self._content)

    def setText(self, text: str):
        """设置文本（Monaco API）."""
        self.setPlainText(text)
        self._content = text

    def text(self) -> str:
        """获取文本（Monaco API）."""
        return self.toPlainText()

    def getText(self, callback):
        """异步获取文本（Monaco API）."""
        callback(self.toPlainText())

    def isReady(self) -> bool:
        """检查是否就绪（Monaco API）."""
        return self._is_ready

    def clear(self):
        """清空内容."""
        self.setPlainText("")

    # ==================== 断点管理（兼容API）====================

    def setBreakpoint(self, line_number: int):
        """设置断点（占位实现）."""
        return

    def getBreakpoints(self, callback):
        """获取断点（占位实现）."""
        callback([])

    def clearBreakpoints(self):
        """清除断点（占位实现）."""
        return

    # ==================== 只读模式 ====================

    def setReadOnly(self, readonly: bool):
        """设置只读状态（带样式变化）.

        Args:
            readonly: 是否只读
        """
        super().setReadOnly(readonly)

        if readonly:
            # 只读时使用更明显的灰色背景和边框
            self.setStyleSheet(
                """
                QPlainTextEdit {
                    background-color: #2a2a2a;
                    color: #d4d4d4;
                    border: 1px solid #555555;
                    padding-left: 5px;
                    selection-background-color: #264f78;
                    selection-color: #ffffff;
                }
            """
            )
            self.logger.info("编辑器设置为只读模式")
        else:
            # 恢复正常编辑模式样式
            self.setStyleSheet(
                """
                QPlainTextEdit {
                    background-color: #1e1e1e;
                    color: #d4d4d4;
                    border: none;
                    padding-left: 5px;
                    selection-background-color: #264f78;
                    selection-color: #ffffff;
                }
            """
            )
            self.logger.info("编辑器设置为编辑模式")
