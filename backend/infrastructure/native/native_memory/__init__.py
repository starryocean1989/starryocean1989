# -*- coding: utf-8 -*-
"""
原生内存操作模块

提供零拷贝内存操作和内存池功能。
Windows平台：使用C扩展实现高性能
其他平台：自动降级到标准库
"""

import platform
import logging

# 创建logger
logger = logging.getLogger(__name__)

# 平台检测
IS_WINDOWS = platform.system() == "Windows"

# 尝试导入C扩展实现
if IS_WINDOWS:
    try:
        from .native_memory import (
            ZeroCopyMemory,
            MemoryPool,
            batch_alloc,
            batch_free,
        )
        MEMORY_AVAILABLE = True
        __all__ = [
            "ZeroCopyMemory",
            "MemoryPool",
            "batch_alloc",
            "batch_free",
            "MEMORY_AVAILABLE",
        ]
    except ImportError:
        # C扩展未编译
        MEMORY_AVAILABLE = False
        __all__ = ["MEMORY_AVAILABLE"]

        def _raise_import_error():
            logger.warning(
                "Memory C扩展未编译，请运行: python setup.py build_ext --inplace in backend/infrastructure/native/native_memory/",
                extra={"log_type": "SYSTEM"}
            )
            raise ImportError(
                "Memory C extension not compiled. "
                "Please run: python setup.py build_ext --inplace in backend/infrastructure/native/native_memory/"
            )

        ZeroCopyMemory = _raise_import_error
        MemoryPool = _raise_import_error
        batch_alloc = _raise_import_error
        batch_free = _raise_import_error
else:
    MEMORY_AVAILABLE = False
    __all__ = ["MEMORY_AVAILABLE"]

    def _raise_platform_error():
        logger.critical("内存操作扩展仅支持Windows平台", extra={"log_type": "SYSTEM"})
        raise RuntimeError("Memory operations extension only supports Windows platform")

    ZeroCopyMemory = _raise_platform_error
    MemoryPool = _raise_platform_error
    batch_alloc = _raise_platform_error
    batch_free = _raise_platform_error

# 模块信息
__version__ = "1.0.0"
__author__ = "Terminal Project"

