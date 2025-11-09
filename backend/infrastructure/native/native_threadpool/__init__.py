# -*- coding: utf-8 -*-
"""
原子化线程池组件

优先加载 C 扩展，并提供 Python 回退实现以便在构建前运行测试。
"""

from backend.infrastructure.native.logging_bridge import native_call_guard

try:
    from ._native_threadpool import (  # type: ignore[attr-defined]
        NativeFuture,
        NativeThreadPool,
        THREADPOOL_AVAILABLE,
        __version__,
    )
except ImportError:  # pragma: no cover
    from concurrent.futures import Future, ThreadPoolExecutor
    import logging

    __version__ = "0.0.0"
    THREADPOOL_AVAILABLE = False

    class NativeFuture(Future):
        """基于 concurrent.futures.Future 的回退实现"""

    class NativeThreadPool:
        """回退线程池，基于 ThreadPoolExecutor"""

        __slots__ = ("_executor", "_logger")

        def __init__(self, max_workers: int = 4):
            self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="native_fallback")
            self._logger = logging.getLogger("backend.native.threadpool.fallback")

            # Log initialization
            self._logger.info(f"NativeThreadPool fallback initialized with max_workers={max_workers}")

        @native_call_guard(component="native_threadpool")
        def submit(self, fn, *args, **kwargs):
            fut = NativeFuture()

            def wrapper():
                try:
                    result = fn(*args, **kwargs)
                    self._logger.debug(f"Task completed successfully: {fn.__name__}")
                except Exception as exc:
                    self._logger.error(f"Task failed: {fn.__name__}", exc_info=True)
                    fut.set_exception(exc)
                    return
                fut.set_result(result)

            self._executor.submit(wrapper)
            self._logger.debug(f"Task submitted: {fn.__name__}")
            return fut

        @native_call_guard(component="native_threadpool")
        def shutdown(self, wait: bool = True):
            self._logger.info(f"Shutting down thread pool (wait={wait})")
            self._executor.shutdown(wait=wait)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.shutdown(wait=True)

__all__ = ["NativeThreadPool", "NativeFuture", "THREADPOOL_AVAILABLE", "__version__"]

