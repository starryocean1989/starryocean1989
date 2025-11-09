# -*- coding: utf-8 -*-
"""native_smart_monitor 模块导出.

阶段11埋点：记录关键磁盘SMART监控系统调用的参数与返回码，便于排查权限/资源问题
"""

from __future__ import annotations

import logging

from backend.infrastructure.native.logging_bridge import log_from_native, NativeLogLevel
from backend.infrastructure.system_vnpy.logging_system import (
    LogType,
    bind_logger_defaults,
)

_logger = bind_logger_defaults(
    logging.getLogger("backend.native.native_smart_monitor.wrapper"),
    log_type=LogType.SYSTEM.value,
    scenario="backend.native.native_smart_monitor.wrapper",
)

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
        # 阶段11埋点：记录native_smart_monitor扩展未编译的情况
        details = {
            "scenario": "native_smart_monitor_fallback",
            "error": _ERROR,
        }
        log_from_native(
            NativeLogLevel.WARNING,
            "backend.native.native_smart_monitor.wrapper",
            "get_drive_temperature_data",
            0,
            "native_smart_monitor extension unavailable, falling back to ImportError",
            str(details),
        )

        raise ImportError(f"native_smart_monitor not available: {_ERROR}")  # noqa: B904

__all__ = [
    "SMART_MONITOR_AVAILABLE",
    "get_drive_temperature_data",
]


