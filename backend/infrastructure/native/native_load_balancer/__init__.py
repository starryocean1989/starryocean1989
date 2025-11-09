# -*- coding: utf-8 -*-
"""native_load_balancer 模块导出."""

from __future__ import annotations

import logging
import platform

from backend.infrastructure.system_vnpy.logging_system import (
    LogType,
    bind_logger_defaults,
    get_alert_logger,
)

from backend.infrastructure.native.logging_bridge import native_call_guard

__all__ = [
    "LOAD_BALANCER_AVAILABLE",
    "optimize",
]

_LOGGER = bind_logger_defaults(
    logging.getLogger("backend.native.load_balancer"),
    log_type=LogType.SYSTEM.value,
    scenario="backend.native.load_balancer",
)
_ALERT_LOGGER = get_alert_logger(
    "backend.native.load_balancer.alert",
    scenario="backend.native.load_balancer",
)

if platform.system() == "Windows":
    try:
        from .load_balancer import optimize  # type: ignore[import]

        LOAD_BALANCER_AVAILABLE = True
        _LOGGER.debug(
            "native_load_balancer C 扩展已加载",
            extra={
                "scenario": "backend.native.load_balancer",
                "native_module": "backend.native.load_balancer.core",
            },
        )
    except ImportError:  # pragma: no cover - 扩展未编译
        LOAD_BALANCER_AVAILABLE = False

        _LOGGER.warning(
            "native_load_balancer C 扩展未编译，调用将触发降级",
            extra={
                "log_type": LogType.SYSTEM.value,
                "scenario": "backend.native.load_balancer",
                "native_module": "backend.native.load_balancer.core",
                "action_required": "compile_extension",
            },
        )

        @native_call_guard(component="backend.native.load_balancer")
        def optimize(*_args, **_kwargs):  # type: ignore[override]
            _ALERT_LOGGER.error(
                "native_load_balancer 扩展缺失，无法执行负载均衡优化",
                extra={
                    "log_type": LogType.ALERT.value,
                    "scenario": "backend.native.load_balancer",
                    "action_required": "compile_extension",
                    "fallback": "python_calculator",
                },
            )
            raise ImportError("native_load_balancer extension is not compiled")
else:  # pragma: no cover - 非Windows平台
    LOAD_BALANCER_AVAILABLE = False

    def optimize(*_args, **_kwargs):  # type: ignore[override]
        _ALERT_LOGGER.critical(
            "native_load_balancer 仅支持 Windows 平台，当前平台不受支持",
            extra={
                "log_type": LogType.ALERT.value,
                "scenario": "backend.native.load_balancer",
                "current_platform": platform.system(),
                "action_required": "unsupported_platform",
            },
        )
        raise RuntimeError("native_load_balancer only supports Windows platform")


