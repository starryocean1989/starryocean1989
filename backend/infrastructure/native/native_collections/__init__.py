# -*- coding: utf-8 -*-
"""
原生高性能容器模块

提供高性能LRU缓存和优先级队列功能。
"""

import platform
import logging

logger = logging.getLogger(__name__)
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    try:
        from .native_collections import (
            HighPerfLRUCache,
            HighPerfPriorityQueue,
            HighPerfMatchCache,
        )
        COLLECTIONS_AVAILABLE = True
        __all__ = [
            "HighPerfLRUCache",
            "HighPerfPriorityQueue",
            "HighPerfMatchCache",
            "COLLECTIONS_AVAILABLE",
        ]
    except ImportError:
        COLLECTIONS_AVAILABLE = False
        __all__ = ["COLLECTIONS_AVAILABLE"]
        def _raise_error():
            raise ImportError("Collections C extension not compiled")
        HighPerfLRUCache = HighPerfPriorityQueue = HighPerfMatchCache = _raise_error
else:
    COLLECTIONS_AVAILABLE = False
    __all__ = ["COLLECTIONS_AVAILABLE"]
    def _raise_error():
        raise RuntimeError("Collections extension only supports Windows")
    HighPerfLRUCache = HighPerfPriorityQueue = HighPerfMatchCache = _raise_error

__version__ = "1.0.0"

