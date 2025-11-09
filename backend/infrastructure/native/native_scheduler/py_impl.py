# -*- coding: utf-8 -*-
"""纯 Python 回退实现，与原生接口保持一致。"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional, Tuple


class _CategoryContext:
    __slots__ = ("executor", "max_workers", "pending", "lock")

    def __init__(self, executor: Any, max_workers: int) -> None:
        self.executor = executor
        self.max_workers = max_workers
        self.pending = 0
        self.lock = threading.Lock()

    def submit(self, func: Callable[..., Any], args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Future:
        with self.lock:
            self.pending += 1

        future: Future = self.executor.submit(func, *args, **kwargs)

        def _cleanup(_future: Future) -> None:
            with self.lock:
                self.pending -= 1

        future.add_done_callback(_cleanup)
        return future

    def stats(self) -> Dict[str, Any]:
        with self.lock:
            return {"pending": self.pending, "queue_size": self.pending, "max_workers": self.max_workers}

    def shutdown(self, wait: bool) -> None:
        shutdown = getattr(self.executor, "shutdown", None)
        if callable(shutdown):
            shutdown(wait=wait)


class PyNativeScheduler:
    """ThreadPoolExecutor 驱动的回退实现。"""

    def __init__(self, *, executor_factory: Optional[Callable[[int], Any]] = None) -> None:
        self._lock = threading.RLock()
        self._categories: Dict[str, _CategoryContext] = {}
        self._shutdown = False
        self._executor_factory = executor_factory or self._default_executor_factory

    @staticmethod
    def _default_executor_factory(max_workers: int) -> ThreadPoolExecutor:
        return ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="py-native-scheduler")

    def register_category(
        self,
        name: str,
        *,
        queue_capacity: int = 1024,  # 保留兼容参数
        max_workers: int = 4,
    ) -> None:
        del queue_capacity
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        executor = self._executor_factory(max_workers)
        if executor is None:
            raise RuntimeError("executor_factory returned None")

        context = _CategoryContext(executor=executor, max_workers=max_workers)
        with self._lock:
            if self._shutdown:
                raise RuntimeError("scheduler already shutdown")
            if name in self._categories:
                raise ValueError(f"category {name!r} already registered")
            self._categories[name] = context

    def submit(
        self,
        category: str,
        func: Callable[..., Any],
        call_args: Optional[Tuple[Any, ...]] = None,
        call_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Future:
        if not callable(func):
            raise TypeError("callable must be callable")

        args = tuple(call_args or ())
        kwargs = dict(call_kwargs or {})

        with self._lock:
            if self._shutdown:
                raise RuntimeError("scheduler already shutdown")
            try:
                context = self._categories[category]
            except KeyError as exc:
                raise KeyError("category not registered") from exc

        return context.submit(func, args, kwargs)

    def stats(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {name: ctx.stats() for name, ctx in self._categories.items()}

    def shutdown(self, wait: bool = True) -> None:
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
            contexts = list(self._categories.values())
            self._categories.clear()

        for ctx in contexts:
            ctx.shutdown(wait)


__all__ = ["PyNativeScheduler"]

