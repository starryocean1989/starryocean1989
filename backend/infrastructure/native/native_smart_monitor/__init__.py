# -*- coding: utf-8 -*-
"""native_smart_monitor 模块导出."""

from __future__ import annotations

SMART_MONITOR_AVAILABLE: bool

try:
    from .native_smart_monitor import (  # type: ignore
        SMART_MONITOR_AVAILABLE,
        get_drive_temperature_data,
    )
except ImportError as exc:  # pragma: no cover - 原生模块缺失时进入降级路径
    SMART_MONITOR_AVAILABLE = False
    _ERROR = str(exc)

    def get_drive_temperature_data() -> list:  # type: ignore[misc]
        """降级实现：模块未编译时提示错误."""

        raise ImportError(f"native_smart_monitor not available: {_ERROR}")  # noqa: B904

__all__ = [
    "SMART_MONITOR_AVAILABLE",
    "get_drive_temperature_data",
]


