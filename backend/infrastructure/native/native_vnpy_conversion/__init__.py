# -*- coding: utf-8 -*-
"""native_vnpy_conversion 原生批量转换接口."""

from __future__ import annotations

from typing import Iterable, Optional

try:
    from .conversion import (  # type: ignore[F401]
        CONVERSION_AVAILABLE,
        batch_convert,
        convert_one,
        get_version,
    )
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

