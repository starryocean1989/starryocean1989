# -*- coding: utf-8 -*-
"""
代码编辑器组件 - 基于QScintilla实现.

提供专业的代码编辑功能，包括：
- Python语法高亮
- 代码补全
- 行号显示
- 代码折叠
- 自动缩进
- 括号匹配
- 错误提示
"""

from typing import Optional

try:
    from PyQt6.Qsci import QsciScintilla, QsciLexerPython, QsciAPIs
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont
    from PySide6.QtWidgets import QWidget

    HAS_QSCINTILLA = True
except ImportError:
    # 降级到简化版实现
    HAS_QSCINTILLA = False
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont
    from PySide6.QtWidgets import QPlainTextEdit, QWidget


if HAS_QSCINTILLA:

    class CodeEditor(QsciScintilla):
        """基于QScintilla的代码编辑器."""

        def __init__(self, parent: Optional[QWidget] = None):
            """初始化代码编辑器."""
            super().__init__(parent)

            # 设置字体
            font = QFont("Consolas, Monaco, Courier New", 10)
            font.setFixedPitch(True)
            self.setFont(font)
            self.setMarginsFont(font)

            # 设置编码
            self.setUtf8(True)

            # 设置Tab宽度为4个空格
            self.setTabWidth(4)
            self.setIndentationsUseTabs(False)
            self.setTabIndents(True)
            self.setAutoIndent(True)

            # 设置缩进指示
            self.setIndentationGuides(True)

            # 设置行号边距
            self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
            self.setMarginWidth(0, "00000")
            self.setMarginsForegroundColor(QColor("#858585"))
            self.setMarginsBackgroundColor(QColor("#252526"))

            # 设置代码折叠边距
            self.setMarginType(1, QsciScintilla.MarginType.SymbolMargin)
            self.setMarginWidth(1, 15)
            self.setMarginSensitivity(1, True)
            self.setFolding(QsciScintilla.FoldStyle.BoxedTreeFoldStyle)
            self.setFoldMarginColors(QColor("#252526"), QColor("#252526"))

            # 设置当前行高亮
            self.setCaretLineVisible(True)
            self.setCaretLineBackgroundColor(QColor("#2A2A2A"))
            self.setCaretForegroundColor(QColor("#FFFFFF"))

            # 设置括号匹配
            self.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)
            self.setMatchedBraceBackgroundColor(QColor("#3C3C3C"))
            self.setMatchedBraceForegroundColor(QColor("#FFFF00"))
            self.setUnmatchedBraceBackgroundColor(QColor("#FF0000"))
            self.setUnmatchedBraceForegroundColor(QColor("#FFFFFF"))

            # 设置选择区域颜色
            self.setSelectionBackgroundColor(QColor("#264F78"))

            # 设置边缘线（80字符提示线）
            self.setEdgeMode(QsciScintilla.EdgeMode.EdgeLine)
            self.setEdgeColumn(88)  # PEP 8推荐88字符
            self.setEdgeColor(QColor("#3C3C3C"))

            # 设置自动换行
            self.setWrapMode(QsciScintilla.WrapMode.WrapNone)

            # 设置滚动条宽度
            self.SendScintilla(QsciScintilla.SCI_SETSCROLLWIDTH, 1)
            self.SendScintilla(QsciScintilla.SCI_SETSCROLLWIDTHTRACKING, True)

            # 应用Python语法高亮
            self._setup_python_lexer()

            # 设置代码补全
            self._setup_autocompletion()

            # 设置背景色（暗色主题）
            self.setPaper(QColor("#1E1E1E"))
            self.setColor(QColor("#D4D4D4"))

        def _setup_python_lexer(self):
            """设置Python语法高亮器."""
            lexer = QsciLexerPython(self)
            lexer.setDefaultFont(self.font())

            # 设置暗色主题配色
            lexer.setDefaultPaper(QColor("#1E1E1E"))
            lexer.setDefaultColor(QColor("#D4D4D4"))

            # 关键字 - 蓝色
            lexer.setColor(QColor("#569CD6"), QsciLexerPython.Keyword)
            lexer.setFont(QFont("Consolas", 10, QFont.Weight.Bold), QsciLexerPython.Keyword)

            # 类名 - 浅绿色
            lexer.setColor(QColor("#4EC9B0"), QsciLexerPython.ClassName)

            # 函数名 - 黄色
            lexer.setColor(QColor("#DCDCAA"), QsciLexerPython.FunctionMethodName)

            # 字符串 - 橙色
            lexer.setColor(QColor("#CE9178"), QsciLexerPython.SingleQuotedString)
            lexer.setColor(QColor("#CE9178"), QsciLexerPython.DoubleQuotedString)
            lexer.setColor(QColor("#CE9178"), QsciLexerPython.TripleSingleQuotedString)
            lexer.setColor(QColor("#CE9178"), QsciLexerPython.TripleDoubleQuotedString)

            # 注释 - 绿色
            lexer.setColor(QColor("#6A9955"), QsciLexerPython.Comment)
            lexer.setColor(QColor("#6A9955"), QsciLexerPython.CommentBlock)

            # 数字 - 浅绿色
            lexer.setColor(QColor("#B5CEA8"), QsciLexerPython.Number)

            # 运算符 - 默认颜色
            lexer.setColor(QColor("#D4D4D4"), QsciLexerPython.Operator)

            # Decorator - 黄色
            lexer.setColor(QColor("#DCDCAA"), QsciLexerPython.Decorator)

            self.setLexer(lexer)

        def _setup_autocompletion(self):
            """设置代码补全."""
            # 启用自动补全
            self.setAutoCompletionSource(QsciScintilla.AutoCompletionSource.AcsAll)
            self.setAutoCompletionThreshold(2)  # 输入2个字符后触发
            self.setAutoCompletionCaseSensitivity(False)
            self.setAutoCompletionReplaceWord(True)

            # 添加VnPy API补全
            self._add_vnpy_apis()

        def _add_vnpy_apis(self):
            """添加VnPy API关键字补全."""
            lexer = self.lexer()
            if not isinstance(lexer, QsciLexerPython):
                return

            apis = QsciAPIs(lexer)

            # VnPy核心类
            vnpy_classes = [
                "CtaTemplate",
                "CtaSignal",
                "TargetPosTemplate",
                "BarData",
                "TickData",
                "OrderData",
                "TradeData",
                "PositionData",
                "AccountData",
                "ContractData",
                "MainEngine",
                "EventEngine",
                "BaseGateway",
                "BarGenerator",
                "ArrayManager",
            ]

            # VnPy核心方法
            vnpy_methods = [
                "on_init",
                "on_start",
                "on_stop",
                "on_tick",
                "on_bar",
                "on_order",
                "on_trade",
                "on_position",
                "on_account",
                "buy",
                "sell",
                "short",
                "cover",
                "cancel_order",
                "cancel_all",
                "write_log",
                "put_event",
                "send_order",
                "load_bar",
                "load_tick",
                "get_contract",
                "get_all_contracts",
            ]

            # VnPy常用常量
            vnpy_constants = [
                "Direction.LONG",
                "Direction.SHORT",
                "Offset.OPEN",
                "Offset.CLOSE",
                "Offset.CLOSETODAY",
                "Offset.CLOSEYESTERDAY",
                "OrderType.LIMIT",
                "OrderType.MARKET",
                "OrderType.STOP",
                "Status.SUBMITTING",
                "Status.NOTTRADED",
                "Status.PARTTRADED",
                "Status.ALLTRADED",
                "Exchange.SSE",
                "Exchange.SZSE",
                "Exchange.SHFE",
                "Exchange.DCE",
                "Exchange.CZCE",
            ]

            # 技术指标（talib）
            talib_functions = [
                "SMA",
                "EMA",
                "WMA",
                "DEMA",
                "TEMA",
                "TRIMA",
                "KAMA",
                "MAMA",
                "T3",
                "MACD",
                "RSI",
                "STOCH",
                "ADX",
                "CCI",
                "BBANDS",
                "ATR",
                "NATR",
                "TRANGE",
                "WILLR",
                "MFI",
                "ROC",
                "ROCP",
            ]

            # 添加所有API
            for cls in vnpy_classes:
                apis.add(cls)
            for method in vnpy_methods:
                apis.add(method)
            for const in vnpy_constants:
                apis.add(const)
            for func in talib_functions:
                apis.add(func)

            # 准备API
            apis.prepare()

        def insertPlainText(self, text: str):
            """插入纯文本（兼容QPlainTextEdit接口）."""
            self.insert(text)

        def toPlainText(self) -> str:
            """获取纯文本（兼容QPlainTextEdit接口）."""
            return self.text()

        def setPlainText(self, text: str):
            """设置纯文本（兼容QPlainTextEdit接口）."""
            self.setText(text)

else:
    # 如果没有QScintilla，降级到简化版实现
    import re
    from PySide6.QtCore import QRect, QSize
    from PySide6.QtGui import QPainter, QSyntaxHighlighter, QTextCharFormat

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
        """Python语法高亮器."""

        def __init__(self, document):
            """初始化高亮器."""
            super().__init__(document)

            # 关键字格式
            keyword_format = QTextCharFormat()
            keyword_format.setForeground(QColor("#569CD6"))
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
            string_format.setForeground(QColor("#CE9178"))

            # 双引号字符串
            self.highlighting_rules.append((r'"[^"\\]*(\\.[^"\\]*)*"', string_format))
            # 单引号字符串
            self.highlighting_rules.append((r"'[^'\\]*(\\.[^'\\]*)*'", string_format))

            # 注释格式
            comment_format = QTextCharFormat()
            comment_format.setForeground(QColor("#6A9955"))
            self.highlighting_rules.append((r"#[^\n]*", comment_format))

            # 函数/类名格式
            function_format = QTextCharFormat()
            function_format.setForeground(QColor("#DCDCAA"))
            self.highlighting_rules.append((r"\bdef\s+(\w+)", function_format))
            self.highlighting_rules.append((r"\bclass\s+(\w+)", function_format))

            # 数字格式
            number_format = QTextCharFormat()
            number_format.setForeground(QColor("#B5CEA8"))
            self.highlighting_rules.append((r"\b[0-9]+\.?[0-9]*\b", number_format))

        def highlightBlock(self, text):
            """高亮当前文本块."""
            for pattern, fmt in self.highlighting_rules:
                for match in re.finditer(pattern, text):
                    start = match.start()
                    length = match.end() - start
                    self.setFormat(start, length, fmt)

    class CodeEditor(QPlainTextEdit):
        """代码编辑器 - 简化版（降级实现）."""

        def __init__(self, parent: Optional[QWidget] = None):
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
                self.line_number_area.update(
                    0, rect.y(), self.line_number_area.width(), rect.height()
                )

            if rect.contains(self.viewport().rect()):
                self.update_line_number_area_width()

        def resizeEvent(self, event):
            """调整大小事件."""
            super().resizeEvent(event)

            cr = self.contentsRect()
            line_width = self.line_number_area_width()
            rect = QRect(cr.left(), cr.top(), line_width, cr.height())
            self.line_number_area.setGeometry(rect)

        def line_number_area_paint_event(self, event):
            """绘制行号."""
            painter = QPainter(self.line_number_area)
            painter.fillRect(event.rect(), QColor("#252526"))

            block = self.firstVisibleBlock()
            block_number = block.blockNumber()
            offset = self.contentOffset()
            geometry = self.blockBoundingGeometry(block).translated(offset)
            top = int(geometry.top())
            bottom = top + int(self.blockBoundingRect(block).height())

            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and bottom >= event.rect().top():
                    number = str(block_number + 1)
                    painter.setPen(QColor("#858585"))
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
