# -*- coding: utf-8 -*-
"""
原子化队列组件

优先加载 C 扩展实现，失败时回退到轻量 Python 版本，便于在未构建环境下运行单元测试。
"""

try:
    from ._native_queue import (  # type: ignore[attr-defined]
        NativeQueue,
        QUEUE_AVAILABLE,
        __version__,
    )
except ImportError:  # pragma: no cover
    from collections import deque
    from threading import Lock

    __version__ = "0.0.0"
    QUEUE_AVAILABLE = False

    class NativeQueue:
        """回退实现：基于 deque + 互斥锁"""

        __slots__ = ("_data", "_lock")

        def __init__(self, capacity: int = 1024):
            self._data = deque()  # 无容量限制
            self._lock = Lock()

        def push(self, item):
            with self._lock:
                self._data.append(item)

        def pop(self):
            with self._lock:
                if not self._data:
                    return None
                return self._data.popleft()

        def size(self) -> int:
            with self._lock:
                return len(self._data)

        def clear(self) -> None:
            with self._lock:
                self._data.clear()

        def __len__(self) -> int:
            return self.size()

        def __repr__(self) -> str:  # pragma: no cover - 诊断辅助
            return f"<FallbackNativeQueue size={len(self)}>"

__all__ = ["NativeQueue", "QUEUE_AVAILABLE", "__version__"]

