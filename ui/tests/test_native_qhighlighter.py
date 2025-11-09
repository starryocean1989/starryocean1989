# -*- coding: utf-8 -*-
import importlib

import pytest

pytest.importorskip("PySide6.QtGui")

_module = None
_errors = []
for _name in (
    "native_qhighlighter",
    "backend.infrastructure.native.native_qhighlighter",
):
    try:
        _module = importlib.import_module(_name)
    except ModuleNotFoundError as exc:
        _errors.append(str(exc))
    except Exception as exc:  # noqa: BLE001
        _errors.append(str(exc))
    else:
        break

if _module is None:
    pytest.skip(
        "native_qhighlighter 无法导入，跳过测试: " + ("; ".join(_errors) or "未找到模块"),
        allow_module_level=True,
    )

NativeHighlighterUnavailable = getattr(_module, "NativeHighlighterUnavailable")
build_default_engine = getattr(_module, "build_default_engine")


def test_highlighter_engine_tokens_keyword():
    try:
        engine = build_default_engine()
    except NativeHighlighterUnavailable:
        pytest.skip("native_qhighlighter_core 未编译，跳过测试", allow_module_level=True)
    tokens = engine.highlight("def foo():\n    return True\n")
    names = [token["name"] for token in tokens]
    assert "keyword" in names


