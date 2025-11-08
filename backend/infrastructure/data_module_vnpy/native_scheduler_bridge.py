# -*- coding: utf-8 -*-
"""
Native 调度器桥接层

用于在业务模块中以统一方式调用 C 扩展调度核心；当扩展不可用时保持空对象，便于渐进式迁移。
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, Optional, Tuple


class NativeSchedulerBridge:
    """封装 native_scheduler 的薄层接口，支持按需重建类别配置。"""

    DEFAULT_CATEGORIES: Dict[str, Dict[str, int]] = {
        "network_download": {"queue_capacity": 4096, "max_workers": 16},
        "local_scan": {"queue_capacity": 8192, "max_workers": 8},
        "local_read": {"queue_capacity": 4096, "max_workers": 8},
    }

    def __init__(
        self,
        categories: Optional[Dict[str, Dict[str, int]]] = None,
        *,
        auto_shutdown: bool = True,
    ):
        module = importlib.import_module("backend.infrastructure.native.native_scheduler")
        scheduler_available = getattr(module, "SCHEDULER_AVAILABLE", False)
        if not scheduler_available:
            raise RuntimeError("native_scheduler extension unavailable")

        self._native_scheduler_cls = getattr(module, "NativeScheduler")
        self._auto_shutdown = auto_shutdown
        self._scheduler = None
        self._categories: Dict[str, Dict[str, int]] = {}
        self._initialise(categories or self.DEFAULT_CATEGORIES)

    def _initialise(self, categories: Dict[str, Dict[str, int]]) -> None:
        if self._scheduler is not None:
            try:
                self._scheduler.shutdown(wait=True)
            except Exception:  # pragma: no cover - 安全兜底
                pass

        self._scheduler = self._native_scheduler_cls()
        self._categories = {}
        for name, cfg in categories.items():
            queue_capacity = max(1, int(cfg.get("queue_capacity", 1024)))
            max_workers = max(1, int(cfg.get("max_workers", 4)))
            self._scheduler.register_category(
                name,
                queue_capacity=queue_capacity,
                max_workers=max_workers,
            )
            self._categories[name] = {"queue_capacity": queue_capacity, "max_workers": max_workers}

    @property
    def available(self) -> bool:
        return self._scheduler is not None

    @property
    def categories(self) -> Dict[str, Dict[str, int]]:
        return dict(self._categories)

    def ensure_category(self, name: str, *, queue_capacity: Optional[int] = None, max_workers: Optional[int] = None) -> None:
        queue_capacity = max(1, int(queue_capacity or self._categories.get(name, {}).get("queue_capacity", 1024)))
        max_workers = max(1, int(max_workers or self._categories.get(name, {}).get("max_workers", 4)))
        desired = {"queue_capacity": queue_capacity, "max_workers": max_workers}
        current = self._categories.get(name)
        if current == desired:
            return

        updated = dict(self._categories)
        updated[name] = desired
        self._initialise(updated)

    def submit(
        self,
        category: str,
        func,
        args: Tuple[Any, ...] | None = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ):
        if self._scheduler is None:
            raise RuntimeError("NativeSchedulerBridge is not initialised")
        if args is None:
            args = ()
        elif not isinstance(args, tuple):
            args = tuple(args)

        if kwargs is None:
            kwargs = {}
        elif not isinstance(kwargs, dict):
            kwargs = dict(kwargs)
        submit_kwargs = {"call_args": args}
        if kwargs:
            submit_kwargs["call_kwargs"] = kwargs

        return self._scheduler.submit(category, func, **submit_kwargs)

    def stats(self) -> Dict[str, Any]:
        if self._scheduler is None:
            return {}
        return self._scheduler.stats()

    def shutdown(self, wait: bool = True) -> None:
        if self._scheduler is None:
            return
        try:
            self._scheduler.shutdown(wait=wait)
        finally:
            self._scheduler = None

    def get_metrics(self) -> Dict[str, Any]:
        return self.stats()

    def reset(self, categories: Dict[str, Dict[str, int]]) -> None:
        """重建调度器（例如需要调整线程数时调用）。"""
        self._initialise(categories)

    def __enter__(self) -> "NativeSchedulerBridge":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._auto_shutdown:
            self.shutdown(wait=True)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<NativeSchedulerBridge categories={list(self._categories.keys())}>"

