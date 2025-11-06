# -*- coding: utf-8 -*-
"""
原生数据转换模块

提供批量类型转换和批量字符串操作功能。
"""

import platform
import logging

logger = logging.getLogger(__name__)
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    try:
        from .native_conversion import (
            batch_convert,
            batch_encode,
            batch_decode,
        )
        CONVERSION_AVAILABLE = True
        __all__ = [
            "batch_convert",
            "batch_encode",
            "batch_decode",
            "CONVERSION_AVAILABLE",
        ]
    except ImportError:
        CONVERSION_AVAILABLE = False
        __all__ = ["CONVERSION_AVAILABLE"]
        def _raise_error():
            raise ImportError("Conversion C extension not compiled")
        batch_convert = batch_encode = batch_decode = _raise_error
else:
    CONVERSION_AVAILABLE = False
    __all__ = ["CONVERSION_AVAILABLE"]
    def _raise_error():
        raise RuntimeError("Conversion extension only supports Windows")
    batch_convert = batch_encode = batch_decode = _raise_error

__version__ = "1.0.0"

