# -*- coding: utf-8 -*-
"""
原子化线程池组件

优先加载 C 扩展，并提供 Python 回退实现以便在构建前运行测试。
"""

try:
    from ._native_threadpool import (  # type: ignore[attr-defined]
        NativeFuture,
        NativeThreadPool,
        THREADPOOL_AVAILABLE,
        __version__,
    )
except ImportError:  # pragma: no cover
    from concurrent.futures import Future, ThreadPoolExecutor

    __version__ = "0.0.0"
    THREADPOOL_AVAILABLE = False

    class NativeFuture(Future):
        """基于 concurrent.futures.Future 的回退实现"""

    class NativeThreadPool:
        """回退线程池，基于 ThreadPoolExecutor"""

        __slots__ = ("_executor",)

        def __init__(self, max_workers: int = 4):
            self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="native_fallback")

        def submit(self, fn, *args, **kwargs):
            fut = NativeFuture()

            def wrapper():
                try:
                    result = fn(*args, **kwargs)
                except Exception as exc:  # pragma: no cover - fallback路径
                    fut.set_exception(exc)
                else:
                    fut.set_result(result)

            self._executor.submit(wrapper)
            return fut

        def shutdown(self, wait: bool = True):
            self._executor.shutdown(wait=wait)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.shutdown(wait=True)

__all__ = ["NativeThreadPool", "NativeFuture", "THREADPOOL_AVAILABLE", "__version__"]

