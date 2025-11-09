# -*- coding: utf-8 -*-
"""native_socket_metrics 模块导出.

阶段11埋点：记录关键套接字指标收集系统调用的参数与返回码，便于排查权限/资源问题
"""

import platform
import logging

from backend.infrastructure.native.logging_bridge import log_from_native, NativeLogLevel
from backend.infrastructure.system_vnpy.logging_system import (
    LogType,
    bind_logger_defaults,
)

_logger = bind_logger_defaults(
    logging.getLogger("backend.native.native_socket_metrics.wrapper"),
    log_type=LogType.SYSTEM.value,
    scenario="backend.native.native_socket_metrics.wrapper",
)

__all__ = [
    "SOCKET_METRICS_AVAILABLE",
    "get_socket_metrics",
    "get_tcp_buffer_snapshot",
]


if platform.system() == "Windows":
    try:
        from .socket_metrics import get_socket_metrics, get_tcp_buffer_snapshot

        SOCKET_METRICS_AVAILABLE = True
    except ImportError:  # pragma: no cover - 构建失败时的降级
        SOCKET_METRICS_AVAILABLE = False

        def get_socket_metrics():  # type: ignore[override]
            # 阶段11埋点：记录native_socket_metrics扩展未编译的情况
            log_from_native(
                NativeLogLevel.WARNING,
                "backend.native.native_socket_metrics.wrapper",
                "get_socket_metrics",
                0,
                "native_socket_metrics extension unavailable, raising ImportError",
                str({"scenario": "native_socket_metrics_fallback"}),
            )
            raise ImportError("native_socket_metrics extension is not compiled")

        def get_tcp_buffer_snapshot():  # type: ignore[override]
            # 阶段11埋点：记录native_socket_metrics扩展未编译的情况
            log_from_native(
                NativeLogLevel.WARNING,
                "backend.native.native_socket_metrics.wrapper",
                "get_tcp_buffer_snapshot",
                0,
                "native_socket_metrics extension unavailable, raising ImportError",
                str({"scenario": "native_socket_metrics_fallback"}),
            )
            raise ImportError("native_socket_metrics extension is not compiled")
else:  # pragma: no cover - 非Windows环境降级
    SOCKET_METRICS_AVAILABLE = False

    def get_socket_metrics():  # type: ignore[override]
        # 阶段11埋点：记录平台不支持的情况
        log_from_native(
            NativeLogLevel.WARNING,
            "backend.native.native_socket_metrics.wrapper",
            "get_socket_metrics",
            0,
            "native_socket_metrics unsupported platform, raising RuntimeError",
            str(
                {
                    "scenario": "native_socket_metrics_platform_unsupported",
                    "platform": platform.system(),
                }
            ),
        )
        raise RuntimeError("native_socket_metrics only supports Windows platform")

    def get_tcp_buffer_snapshot():  # type: ignore[override]
        # 阶段11埋点：记录平台不支持的情况
        log_from_native(
            NativeLogLevel.WARNING,
            "backend.native.native_socket_metrics.wrapper",
            "get_tcp_buffer_snapshot",
            0,
            "native_socket_metrics unsupported platform, raising RuntimeError",
            str(
                {
                    "scenario": "native_socket_metrics_platform_unsupported",
                    "platform": platform.system(),
                }
            ),
        )
        raise RuntimeError("native_socket_metrics only supports Windows platform")


