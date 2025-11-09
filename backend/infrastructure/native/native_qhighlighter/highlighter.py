# -*- coding: utf-8 -*-
"""
Native qhighlighter Python 包装。

该模块提供:
- `build_default_engine`: 使用默认主题创建原生引擎
- `NativePythonHighlighter`: 基于 PySide6 的 QSyntaxHighlighter 子类

当 C++ 扩展不可用时，模块会抛出 `NativeHighlighterUnavailable` 供调用方
捕获并降级到 Python 实现。
"""

from __future__ import annotations

import json
import logging
from importlib import resources
from typing import Any, Dict, Optional, cast

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat  # type: ignore
_PACKAGE_NAME = cast(str, __package__ or __name__)


logger = logging.getLogger(__name__)

try:  # noqa: SIM105
    from . import native_qhighlighter_core as _core  # type: ignore
except Exception as exc:  # noqa: BLE001
    _core = None
    _import_error = exc
else:
    _import_error = None


class NativeHighlighterUnavailable(RuntimeError):
    """原生高亮器不可用时的异常。"""


def _ensure_core_available() -> None:
    if _core is None:
        raise NativeHighlighterUnavailable(
            "native_qhighlighter_core 未找到，请在 "
            "backend/infrastructure/native/native_qhighlighter 目录执行 "
            "`python setup.py build_ext --inplace` 或运行 "
            "`backend/infrastructure/native/compile_all.bat`。"
        ) from _import_error


def get_default_theme(theme_name: str = "monaco-dark") -> Dict[str, Dict[str, str]]:
    """加载默认主题配置。"""

    with resources.files(_PACKAGE_NAME).joinpath("themes.json").open("r", encoding="utf-8") as fh:
        themes = json.load(fh)

    theme = themes.get(theme_name)
    if not theme:
        raise KeyError(f"未找到主题 {theme_name}")
    return theme


def build_default_engine(theme_name: str = "monaco-dark") -> Any:
    """构建默认的原生引擎实例。"""

    _ensure_core_available()
    theme = get_default_theme(theme_name)
    patterns = []
    for name, cfg in theme.items():
        patterns.append(
            {
                "name": name,
                "pattern": cfg["pattern"],
                "case_sensitive": cfg.get("case_sensitive", False),
                "color": cfg["color"],
                "italic": cfg.get("italic", False),
                "bold": cfg.get("bold", False),
            }
        )
    return _core.HighlighterEngine(patterns, theme_name=theme_name)  # type: ignore[return-value]


class NativePythonHighlighter(QSyntaxHighlighter):
    """基于原生引擎的 QSyntaxHighlighter。"""

    def __init__(
        self,
        document,
        theme: str = "monaco-dark",
        fallback_highlighter: Optional[QSyntaxHighlighter] = None,
    ):
        _ensure_core_available()
        super().__init__(document)
        self._engine = build_default_engine(theme)
        self._theme = theme
        self._fallback = fallback_highlighter
        self._formats: Dict[str, QTextCharFormat] = {}
        self._apply_theme(theme)

    def _apply_theme(self, theme: str) -> None:
        theme_info = get_default_theme(theme)
        self._formats.clear()
        for name, cfg in theme_info.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(cfg.get("color", "#FFFFFF")))
            if cfg.get("bold"):
                fmt.setFontWeight(QFont.Weight.Bold)
            if cfg.get("italic"):
                fmt.setFontItalic(True)
            self._formats[name] = fmt

        self._engine.set_theme(
            [
                {
                    "name": name,
                    "pattern": cfg["pattern"],
                    "case_sensitive": cfg.get("case_sensitive", False),
                    "color": cfg["color"],
                    "italic": cfg.get("italic", False),
                    "bold": cfg.get("bold", False),
                }
                for name, cfg in theme_info.items()
            ]
        )

    def set_theme(self, theme: str) -> None:
        """设置主题。"""

        if theme == self._theme:
            return
        try:
            self._apply_theme(theme)
        except Exception as exc:  # noqa: BLE001
            logger.warning("native_qhighlighter 设置主题失败: %s", exc, exc_info=True)
            return
        self._theme = theme
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        try:
            tokens = self._engine.highlight(text)
        except Exception as exc:  # noqa: BLE001
            logger.error("native_qhighlighter 高亮失败，尝试降级: %s", exc, exc_info=True)
            if self._fallback is not None:
                self._fallback.highlightBlock(text)
            return

        for token in tokens:
            name = token.get("name")
            fmt = self._formats.get(name)
            if fmt is None:
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(token.get("color", "#FFFFFF")))
            start = int(token["start"])
            length = int(token["length"])
            self.setFormat(start, length, fmt)


