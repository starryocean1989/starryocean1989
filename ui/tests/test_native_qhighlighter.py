# -*- coding: utf-8 -*-
import pytest

pytest.importorskip("PySide6.QtGui")

try:
    from ui.native_extensions.native_qhighlighter import (
        NativeHighlighterUnavailable,
        build_default_engine,
    )
except NativeHighlighterUnavailable:
    pytest.skip("native_qhighlighter_core 未编译，跳过测试", allow_module_level=True)
except Exception:  # noqa: BLE001
    pytest.skip("native_qhighlighter 无法导入，跳过测试", allow_module_level=True)


def test_highlighter_engine_tokens_keyword():
    engine = build_default_engine()
    tokens = engine.highlight("def foo():\n    return True\n")
    names = [token["name"] for token in tokens]
    assert "keyword" in names


