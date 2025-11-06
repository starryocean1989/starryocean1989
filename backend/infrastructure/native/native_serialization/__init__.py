# -*- coding: utf-8 -*-
"""
原生序列化模块

提供批量序列化/反序列化和零拷贝序列化功能。
Windows平台：使用C扩展实现高性能
其他平台：自动降级到标准库
"""

import platform
import logging

logger = logging.getLogger(__name__)
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    try:
        from .native_serialization import (
            batch_serialize,
            batch_deserialize,
            zero_copy_serialize,
        )
        SERIALIZATION_AVAILABLE = True
        __all__ = [
            "batch_serialize",
            "batch_deserialize",
            "zero_copy_serialize",
            "SERIALIZATION_AVAILABLE",
        ]
    except ImportError:
        SERIALIZATION_AVAILABLE = False
        __all__ = ["SERIALIZATION_AVAILABLE"]
        def _raise_import_error():
            raise ImportError("Serialization C extension not compiled")
        batch_serialize = batch_deserialize = zero_copy_serialize = _raise_import_error
else:
    SERIALIZATION_AVAILABLE = False
    __all__ = ["SERIALIZATION_AVAILABLE"]
    def _raise_platform_error():
        raise RuntimeError("Serialization extension only supports Windows platform")
    batch_serialize = batch_deserialize = zero_copy_serialize = _raise_platform_error

__version__ = "1.0.0"

