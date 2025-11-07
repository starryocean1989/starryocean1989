# -*- coding: utf-8 -*-
"""native_socket_metrics 模块导出."""

import platform

__all__ = [
    "SOCKET_METRICS_AVAILABLE",
    "get_socket_metrics",
]


if platform.system() == "Windows":
    try:
        from .socket_metrics import get_socket_metrics

        SOCKET_METRICS_AVAILABLE = True
    except ImportError:  # pragma: no cover - 构建失败时的降级
        SOCKET_METRICS_AVAILABLE = False

        def get_socket_metrics():  # type: ignore[override]
            raise ImportError("native_socket_metrics extension is not compiled")
else:  # pragma: no cover - 非Windows环境降级
    SOCKET_METRICS_AVAILABLE = False

    def get_socket_metrics():  # type: ignore[override]
        raise RuntimeError("native_socket_metrics only supports Windows platform")


