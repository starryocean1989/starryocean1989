# -*- coding: utf-8 -*-
"""
原生高性能容器模块

提供高性能LRU缓存和优先级队列功能。
"""

import logging
import platform
from typing import Any, Optional

from backend.infrastructure.system_vnpy.logging_system import (
    LogType,
    bind_logger_defaults,
)

_logger = bind_logger_defaults(
    logging.getLogger("backend.native.collections.wrapper"),
    log_type=LogType.SYSTEM.value,
    scenario="backend.native.collections",
)
IS_WINDOWS = platform.system() == "Windows"

# Python降级实现
class _FallbackLRUCache:
    """LRU缓存的Python降级实现"""
    def __init__(self, maxsize: int = 128):
        self._maxsize = maxsize
        self._cache: dict = {}
        self._order: list = []
    
    def get(self, key: Any) -> Any:
        if key not in self._cache:
            raise KeyError(key)
        # 移到最前面
        if key in self._order:
            self._order.remove(key)
        self._order.append(key)
        return self._cache[key]
    
    def set(self, key: Any, value: Any) -> None:
        # 如果已存在，更新并移到最前
        if key in self._cache:
            self._order.remove(key)
        self._cache[key] = value
        self._order.append(key)
        # 检查是否超出容量
        while len(self._cache) > self._maxsize:
            oldest = self._order.pop(0)
            del self._cache[oldest]
    
    def size(self) -> int:
        return len(self._cache)

class _FallbackPriorityQueue:
    """优先级队列的Python降级实现"""
    def __init__(self):
        self._items: list = []
    
    def push(self, item: Any, priority: int = 0) -> None:
        self._items.append((priority, item))
        self._items.sort(key=lambda x: x[0], reverse=True)
    
    def pop(self) -> Any:
        if not self._items:
            raise IndexError("pop from empty queue")
        return self._items.pop(0)[1]
    
    def size(self) -> int:
        return len(self._items)

class _FallbackMatchCache:
    """匹配缓存的Python降级实现"""
    def __init__(self):
        self._cache: dict = {}
    
    def add(self, pattern: str, items: list) -> None:
        self._cache[pattern] = items
    
    def get(self, pattern: str) -> Optional[list]:
        return self._cache.get(pattern)
    
    def clear(self) -> None:
        self._cache.clear()

if IS_WINDOWS:
    try:
        from .native_collections import (
            HighPerfLRUCache,
            HighPerfPriorityQueue,
        )
        # HighPerfMatchCache导入可能失败，单独处理
        try:
            from .native_collections import HighPerfMatchCache
        except ImportError:
            _logger.warning(
                "HighPerfMatchCache not available, using fallback",
                extra={"native_module": "backend.native.collections.match_cache"},
            )
            HighPerfMatchCache = _FallbackMatchCache
        
        COLLECTIONS_AVAILABLE = True
        _logger.debug(
            "native_collections extension loaded successfully",
            extra={"native_module": "backend.native.collections.core"},
        )
        __all__ = [
            "HighPerfLRUCache",
            "HighPerfPriorityQueue",
            "HighPerfMatchCache",
            "COLLECTIONS_AVAILABLE",
        ]
    except ImportError as e:
        _logger.warning(
            "Collections C extension not available, using Python fallback",
            extra={
                "native_module": "backend.native.collections.core",
                "error": str(e),
            },
        )
        COLLECTIONS_AVAILABLE = False
        HighPerfLRUCache = _FallbackLRUCache
        HighPerfPriorityQueue = _FallbackPriorityQueue
        HighPerfMatchCache = _FallbackMatchCache
        __all__ = [
            "HighPerfLRUCache",
            "HighPerfPriorityQueue",
            "HighPerfMatchCache",
            "COLLECTIONS_AVAILABLE",
        ]
else:
    _logger.warning(
        "Collections extension only supports Windows, using Python fallback",
        extra={
            "native_module": "backend.native.collections.core",
            "platform": platform.system(),
        },
    )
    COLLECTIONS_AVAILABLE = False
    HighPerfLRUCache = _FallbackLRUCache
    HighPerfPriorityQueue = _FallbackPriorityQueue
    HighPerfMatchCache = _FallbackMatchCache
    __all__ = [
        "HighPerfLRUCache",
        "HighPerfPriorityQueue",
        "HighPerfMatchCache",
        "COLLECTIONS_AVAILABLE",
    ]

__version__ = "1.0.0"

