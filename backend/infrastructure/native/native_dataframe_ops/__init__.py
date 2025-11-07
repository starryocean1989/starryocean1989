# -*- coding: utf-8 -*-
"""native_dataframe_ops 模块导出."""

import platform

__all__ = [
    "DATAFRAME_OPS_AVAILABLE",
    "dataframe_to_records",
    "dataframe_quality_counters",
]


if platform.system() == "Windows":
    try:
        from .dataframe_ops import dataframe_quality_counters, dataframe_to_records

        DATAFRAME_OPS_AVAILABLE = True
    except ImportError:  # pragma: no cover - 构建失败
        DATAFRAME_OPS_AVAILABLE = False

        def dataframe_to_records(*args, **kwargs):  # type: ignore[override]
            raise ImportError("native_dataframe_ops extension is not compiled")

        def dataframe_quality_counters(*args, **kwargs):  # type: ignore[override]
            raise ImportError("native_dataframe_ops extension is not compiled")
else:  # pragma: no cover
    DATAFRAME_OPS_AVAILABLE = False

    def dataframe_to_records(*args, **kwargs):  # type: ignore[override]
        raise RuntimeError("native_dataframe_ops only supports Windows platform")

    def dataframe_quality_counters(*args, **kwargs):  # type: ignore[override]
        raise RuntimeError("native_dataframe_ops only supports Windows platform")


