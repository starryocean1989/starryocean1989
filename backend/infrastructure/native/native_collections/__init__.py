# -*- coding: utf-8 -*-
"""原生高性能容器模块."""

from __future__ import annotations

from importlib import import_module

_native_module = import_module(".native_collections", __name__)

HighPerfLRUCache = _native_module.HighPerfLRUCache  # type: ignore[attr-defined]
HighPerfPriorityQueue = _native_module.HighPerfPriorityQueue  # type: ignore[attr-defined]
HighPerfMatchCache = _native_module.HighPerfMatchCache  # type: ignore[attr-defined]
COLLECTIONS_AVAILABLE = bool(getattr(_native_module, "COLLECTIONS_AVAILABLE", True))
__version__ = getattr(_native_module, "__version__", "1.0.0")

__all__ = [
    "HighPerfLRUCache",
    "HighPerfPriorityQueue",
    "HighPerfMatchCache",
    "COLLECTIONS_AVAILABLE",
]
