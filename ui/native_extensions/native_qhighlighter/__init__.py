# -*- coding: utf-8 -*-
"""
native_qhighlighter 包初始化。

该包提供 `NativePythonHighlighter`，利用 C++ 扩展实现批量 token 化，
在 PySide6 `QSyntaxHighlighter` 中加速代码高亮。模块在导入失败时会自动降级，
外部可通过 `NATIVE_QHIGHLIGHTER=0` 环境变量强制关闭。
"""

from __future__ import annotations

from .highlighter import (
    NativePythonHighlighter,
    NativeHighlighterUnavailable,
    build_default_engine,
    get_default_theme,
)

__all__ = [
    "NativePythonHighlighter",
    "NativeHighlighterUnavailable",
    "build_default_engine",
    "get_default_theme",
]


