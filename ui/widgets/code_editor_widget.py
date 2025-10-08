# -*- coding: utf-8 -*-
"""
代码编辑器组件 - 带行号和语法高亮.

支持Python语法高亮和行号显示
"""

import re

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import QPlainTextEdit, QWidget


class LineNumberArea(QWidget):
    """行号显示区域."""

    def __init__(self, editor):
        """初始化行号区域."""
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):  # pylint: disable=invalid-name
        """建议大小."""
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):  # pylint: disable=invalid-name
        """绘制行号."""
        self.code_editor.line_number_area_paint_event(event)


class PythonHighlighter(QSyntaxHighlighter):
    """Python语法高亮器."""

    def __init__(self, document):
        """初始化高亮器."""
        super().__init__(document)

        # 关键字格式
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569CD6"))  # VS Code蓝色
        keyword_format.setFontWeight(QFont.Weight.Bold)

        # Python关键字
        keywords = [
            "and",
            "as",
            "assert",
            "break",
            "class",
            "continue",
            "def",
            "del",
            "elif",
            "else",
            "except",
            "False",
            "finally",
            "for",
            "from",
            "global",
            "if",
            "import",
            "in",
            "is",
            "lambda",
            "None",
            "nonlocal",
            "not",
            "or",
            "pass",
            "raise",
            "return",
            "True",
            "try",
            "while",
            "with",
            "yield",
            "async",
            "await",
        ]

        self.highlighting_rules = []

        # 添加关键字规则
        for keyword in keywords:
            pattern = f"\\b{keyword}\\b"
            self.highlighting_rules.append((pattern, keyword_format))

        # 字符串格式
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#CE9178"))  # VS Code橙色

        # 双引号字符串正则表达式
        double_quote_pattern = r'"[^"\\]*(\\.[^"\\]*)*"'
        self.highlighting_rules.append((double_quote_pattern, string_format))

        # 单引号字符串正则表达式
        single_quote_pattern = r"'[^'\\]*(\\.[^'\\]*)*'"
        self.highlighting_rules.append((single_quote_pattern, string_format))

        # 注释格式
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955"))  # VS Code绿色
        self.highlighting_rules.append((r"#[^\n]*", comment_format))

        # 函数/类名格式
        function_format = QTextCharFormat()
        function_format.setForeground(QColor("#DCDCAA"))  # VS Code黄色
        self.highlighting_rules.append((r"\bdef\s+(\w+)", function_format))
        self.highlighting_rules.append((r"\bclass\s+(\w+)", function_format))

        # 数字格式
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#B5CEA8"))  # VS Code浅绿
        self.highlighting_rules.append((r"\b[0-9]+\.?[0-9]*\b", number_format))

    def highlightBlock(self, text):  # pylint: disable=invalid-name
        """高亮当前文本块."""
        for pattern, fmt in self.highlighting_rules:
            for match in re.finditer(pattern, text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, fmt)


class CodeEditor(QPlainTextEdit):
    """代码编辑器 - 带行号和语法高亮."""

    def __init__(self, parent=None):
        """初始化代码编辑器."""
        super().__init__(parent)

        # 设置字体
        font = QFont("Consolas, Monaco, Courier New", 10)
        font.setFixedPitch(True)
        self.setFont(font)

        # 设置Tab宽度为4个空格
        tab_stop = 4
        metrics = self.fontMetrics()
        self.setTabStopDistance(tab_stop * metrics.horizontalAdvance(" "))

        # 创建行号区域
        self.line_number_area = LineNumberArea(self)

        # 连接信号
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)

        # 更新行号区域宽度
        self.update_line_number_area_width()

        # 应用Python语法高亮
        self.highlighter = PythonHighlighter(self.document())

        # 设置背景色（暗色主题）
        self.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                selection-background-color: #264F78;
            }
        """
        )

    def line_number_area_width(self):
        """计算行号区域宽度."""
        digits = len(str(max(1, self.blockCount())))
        space = 10 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def update_line_number_area_width(self):
        """更新行号区域宽度."""
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        """更新行号区域."""
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width()

    def resizeEvent(self, event):  # pylint: disable=invalid-name
        """调整大小事件."""
        super().resizeEvent(event)

        cr = self.contentsRect()
        line_width = self.line_number_area_width()
        rect = QRect(cr.left(), cr.top(), line_width, cr.height())
        self.line_number_area.setGeometry(rect)

    def line_number_area_paint_event(self, event):
        """绘制行号."""
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#252526"))  # VS Code行号背景

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        offset = self.contentOffset()
        geometry = self.blockBoundingGeometry(block).translated(offset)
        top = int(geometry.top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#858585"))  # VS Code行号颜色
                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 5,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1
