# -*- coding: utf-8 -*-
"""native_vnpy_conversion 原生批量转换接口.

按照统一日志系统规则，Python 层包装对外函数，确保异常被统一捕获并桥接输出。
"""

from __future__ import annotations

from typing import Iterable, Optional
try:
    from backend.infrastructure.native.logging_bridge import native_call_guard
except Exception:  # pragma: no cover - 在独立安装包环境下允许退化
    def native_call_guard(component: str | None = None):  # type: ignore[override]
        def _decorator(func):
            return func
        return _decorator

try:
    from .conversion import (  # type: ignore[F401]
        CONVERSION_AVAILABLE,
        batch_convert as _batch_convert,
        convert_one as _convert_one,
        get_version,
    )
    
    @native_call_guard(component="native_vnpy_conversion")
    def batch_convert(objects: Iterable[object], data_type: Optional[str] = None, output: str = "dict", fields: Optional[Iterable[str]] = None):  # type: ignore[override]
        return _batch_convert(objects, data_type, output, fields)

    @native_call_guard(component="native_vnpy_conversion")
    def convert_one(obj: object, fields: Optional[Iterable[str]] = None):  # type: ignore[override]
        return _convert_one(obj, fields)
except Exception:  # pragma: no cover - 扩展不可用时降级
    CONVERSION_AVAILABLE = False  # type: ignore[assignment]

    def _raise_not_available(*_args, **_kwargs):  # type: ignore[override]
        raise ImportError("native_vnpy_conversion extension is not compiled")

    batch_convert = _raise_not_available  # type: ignore[assignment]
    convert_one = _raise_not_available  # type: ignore[assignment]

    def get_version() -> str:  # pragma: no cover - fallback
        return "0.0.0"


__all__ = [
    "CONVERSION_AVAILABLE",
    "batch_convert",
    "convert_one",
    "get_version",
]

