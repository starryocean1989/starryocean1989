# -*- coding: utf-8 -*-
"""native_load_balancer 模块导出."""

from __future__ import annotations

import platform

__all__ = [
    "LOAD_BALANCER_AVAILABLE",
    "optimize",
]

if platform.system() == "Windows":
    try:
        from .load_balancer import optimize  # type: ignore[import]

        LOAD_BALANCER_AVAILABLE: bool = True
    except ImportError:  # pragma: no cover - 扩展未编译
        LOAD_BALANCER_AVAILABLE = False

        def optimize(*_args, **_kwargs):  # type: ignore[override]
            raise ImportError("native_load_balancer extension is not compiled")
else:  # pragma: no cover - 非Windows平台
    LOAD_BALANCER_AVAILABLE = False

    def optimize(*_args, **_kwargs):  # type: ignore[override]
        raise RuntimeError("native_load_balancer only supports Windows platform")


