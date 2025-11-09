# -*- coding: utf-8 -*-
"""
原生数据转换模块

提供批量类型转换和批量字符串操作功能。
"""

import logging
import platform

from backend.infrastructure.system_vnpy.logging_system import (
    LogType,
    bind_logger_defaults,
)

_logger = bind_logger_defaults(
    logging.getLogger("backend.native.conversion.wrapper"),
    log_type=LogType.SYSTEM.value,
    scenario="backend.native.conversion",
)
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    try:
        from .native_conversion import (
            batch_convert as _native_batch_convert,
            batch_encode as _native_batch_encode,
            batch_decode as _native_batch_decode,
        )
        CONVERSION_AVAILABLE = True

        _logger.debug(
            "native_conversion extension loaded",
            extra={"native_module": "backend.native.conversion.core"},
        )

        def batch_convert(payload, target_type):
            return _native_batch_convert(payload, target_type)

        def batch_encode(payload, encoding="utf-8"):
            return _native_batch_encode(payload, encoding)

        def batch_decode(payload, encoding="utf-8"):
            return _native_batch_decode(payload, encoding)

        __all__ = [
            "batch_convert",
            "batch_encode",
            "batch_decode",
            "CONVERSION_AVAILABLE",
        ]
    except ImportError:
        CONVERSION_AVAILABLE = False
        __all__ = ["CONVERSION_AVAILABLE"]
        _logger.warning(
            "native_conversion extension unavailable, using Python fallback",
            extra={"native_module": "backend.native.conversion.core"},
        )
        def _raise_error():
            raise ImportError("Conversion C extension not compiled")
        batch_convert = batch_encode = batch_decode = _raise_error
else:
    CONVERSION_AVAILABLE = False
    __all__ = ["CONVERSION_AVAILABLE"]
    _logger.warning(
        "native_conversion not supported on current platform",
        extra={"native_module": "backend.native.conversion.core", "platform": platform.system()},
    )
    def _raise_error():
        raise RuntimeError("Conversion extension only supports Windows")
    batch_convert = batch_encode = batch_decode = _raise_error

__version__ = "1.0.0"

