# -*- coding: utf-8 -*-
"""
原生序列化模块

提供批量序列化/反序列化和零拷贝序列化功能。
Windows平台：使用C扩展实现高性能
其他平台：自动降级到标准库
"""

import logging
import platform
from typing import Any, Optional

logger = logging.getLogger(__name__)
IS_WINDOWS = platform.system() == "Windows"

_native_zero_copy: Optional[Any] = None


def _try_import_native(module_name: str):
    full_name = f"{__name__}.{module_name}"
    try:
        module = __import__(full_name, fromlist=["batch_serialize"])
    except ImportError as exc:
        logger.debug("Failed to import %s: %s", module_name, exc)
        return None
    return module


if IS_WINDOWS:
    module = None
    for candidate in ("native_serialization_new", "native_serialization"):
        module = _try_import_native(candidate)
        if module is not None:
            break

    if module is not None:
        batch_serialize = module.batch_serialize  # type: ignore[attr-defined]
        batch_deserialize = module.batch_deserialize  # type: ignore[attr-defined]
        _native_zero_copy = module.zero_copy_serialize  # type: ignore[attr-defined]
        SERIALIZATION_AVAILABLE = True
        __all__ = [
            "batch_serialize",
            "batch_deserialize",
            "zero_copy_serialize",
            "SERIALIZATION_AVAILABLE",
        ]
    else:
        SERIALIZATION_AVAILABLE = False
        __all__ = ["SERIALIZATION_AVAILABLE"]

        def _raise_import_error(*_args, **_kwargs):
            raise ImportError("Serialization C extension not compiled")

        batch_serialize = batch_deserialize = zero_copy_serialize = _raise_import_error
else:
    SERIALIZATION_AVAILABLE = False
    __all__ = ["SERIALIZATION_AVAILABLE"]

    def _raise_platform_error(*_args, **_kwargs):
        raise RuntimeError("Serialization extension only supports Windows platform")

    batch_serialize = batch_deserialize = zero_copy_serialize = _raise_platform_error


if _native_zero_copy is not None:
    try:
        import pandas as _pd  # noqa: WPS433 单次导入
    except ImportError:  # pragma: no cover - pandas 不可用时回退
        _pd = None

    def zero_copy_serialize(obj):  # type: ignore[assignment]
        """包装原生零拷贝函数，提供 DataFrame 兼容回退."""

        result = _native_zero_copy(obj)  # type: ignore[misc]
        if _pd is None or not isinstance(obj, _pd.DataFrame):
            return result

        if isinstance(result, memoryview):
            return result

        try:
            from backend.infrastructure.data_module_vnpy.arrow_utils import dataframe_to_arrow_buffer

            buffer = dataframe_to_arrow_buffer(obj)
            if buffer is not None:
                return buffer
        except Exception:  # pragma: no cover - 回退时记录调试信息
            logger.debug("zero_copy DataFrame fallback to native result", exc_info=True)

        return result

from .payload import (
    DataFramePayload,
    build_dataframe_payload,
    payload_to_dataframe,
    payload_to_records,
)

__all__ += [
    "DataFramePayload",
    "build_dataframe_payload",
    "payload_to_dataframe",
    "payload_to_records",
]

__version__ = "1.0.0"

