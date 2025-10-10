# -*- coding: utf-8 -*-
"""
Monaco Editor Widget - 基于QWebEngineView.

使用Monaco Editor提供专业的代码编辑功能，包括：
- Python语法高亮
- 智能补全
- 错误提示
- 代码格式化
- VnPy API补全
"""

import os
from typing import Optional

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebChannel import QWebChannel

    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False
    QWebEngineView = None
    QWebChannel = None


class MonacoEditorWidget(QWidget):
    """Monaco Editor组件.

    使用QWebEngineView加载Monaco Editor HTML，提供VSCode级别的代码编辑体验。
    """

    # 信号
    contentChanged = Signal(str)  # 内容变化信号

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化Monaco Editor."""
        super().__init__(parent)

        if not HAS_WEBENGINE:
            raise ImportError(
                "QWebEngineView不可用。请安装PySide6-WebEngine: pip install PySide6-WebEngine"
            )

        # 当前内容
        self._content = ""

        # 调试日志
        import logging

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info("初始化 Monaco Editor Widget")

        # 设置UI
        self._setup_ui()

    def _setup_ui(self):
        """设置用户界面."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建WebEngineView
        self.web_view = QWebEngineView(self)

        # 🔧 允许从远程加载资源（Monaco CDN）
        from PySide6.QtWebEngineCore import QWebEngineSettings

        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)

        self.logger.info("WebEngine 设置已配置（允许远程资源）")

        # 加载Monaco Editor HTML
        html_path = os.path.join(os.path.dirname(__file__), "monaco_editor.html")

        if os.path.exists(html_path) and self.web_view is not None:
            self.logger.info("加载 Monaco HTML: %s", html_path)
            self.web_view.setUrl(QUrl.fromLocalFile(html_path))
        else:
            # 降级方案：显示错误信息
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{
                        background-color: #1e1e1e;
                        color: #d4d4d4;
                        font-family: 'Consolas', monospace;
                        padding: 20px;
                    }}
                    .error {{
                        color: #f48771;
                        font-size: 14px;
                    }}
                </style>
            </head>
            <body>
                <div class="error">
                    <h2>Monaco Editor 加载失败</h2>
                    <p>找不到monaco_editor.html文件。</p>
                    <p>预期路径: {html_path}</p>
                </div>
            </body>
            </html>
            """
            if self.web_view is not None:
                self.web_view.setHtml(error_html)

        if self.web_view is not None:
            layout.addWidget(self.web_view)

    def setText(self, text: str):
        """设置编辑器内容."""
        self._content = text

        if self.web_view:
            # 使用JavaScript设置内容
            js_code = f"""
            if (window.setEditorContent) {{
                window.setEditorContent({self._escape_js_string(text)});
            }}
            """
            self.web_view.page().runJavaScript(js_code)

    def text(self) -> str:
        """获取编辑器内容（同步方法）."""
        return self._content

    def getText(self, callback):
        """获取编辑器内容（异步方法）.

        Args:
            callback: 回调函数，接收一个参数（内容字符串）
        """
        if self.web_view:
            js_code = "window.getEditorContent ? window.getEditorContent() : '';"

            def handle_result(result):
                self._content = result or ""
                callback(self._content)

            self.web_view.page().runJavaScript(js_code, handle_result)
        else:
            callback(self._content)

    def insertPlainText(self, text: str):
        """在光标位置插入文本."""
        if self.web_view:
            js_code = f"""
            if (window.insertTextAtCursor) {{
                window.insertTextAtCursor({self._escape_js_string(text)});
            }}
            """
            self.web_view.page().runJavaScript(js_code)

    def toPlainText(self) -> str:
        """获取纯文本（兼容QPlainTextEdit接口）."""
        return self.text()

    def setPlainText(self, text: str):
        """设置纯文本（兼容QPlainTextEdit接口）."""
        self.setText(text)

    def clear(self):
        """清空编辑器内容."""
        self.setText("")

    # ==================== 断点管理 ====================

    def setBreakpoint(self, line_number: int):
        """设置或取消断点.

        Args:
            line_number: 行号
        """
        if self.web_view:
            js_code = f"window.setBreakpoint ? window.setBreakpoint({line_number}) : [];"
            self.web_view.page().runJavaScript(js_code)
            self.logger.info(f"切换断点: 行 {line_number}")

    def getBreakpoints(self, callback):
        """获取所有断点（异步）.

        Args:
            callback: 回调函数，接收断点列表
        """
        if self.web_view:
            js_code = "window.getBreakpoints ? window.getBreakpoints() : [];"
            self.web_view.page().runJavaScript(js_code, callback)

    def clearBreakpoints(self):
        """清除所有断点."""
        if self.web_view:
            js_code = "window.clearBreakpoints ? window.clearBreakpoints() : null;"
            self.web_view.page().runJavaScript(js_code)
            self.logger.info("已清除所有断点")

    @staticmethod
    def _escape_js_string(text: str) -> str:
        """转义JavaScript字符串."""
        # 替换特殊字符
        text = text.replace("\\", "\\\\")  # 反斜杠
        text = text.replace("\n", "\\n")  # 换行
        text = text.replace("\r", "\\r")  # 回车
        text = text.replace("\t", "\\t")  # 制表符
        text = text.replace('"', '\\"')  # 双引号
        text = text.replace("'", "\\'")  # 单引号
        text = text.replace("`", "\\`")  # 反引号

        return f'"{text}"'
