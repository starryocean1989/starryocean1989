# -*- coding: utf-8 -*-
"""面向业务的调度器组合适配层."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Mapping, Optional

from backend.infrastructure.native.native_scheduler import NativeScheduler
from backend.infrastructure.native.native_threadpool import NativeThreadPool

LOGGER = logging.getLogger(__name__)


class SchedulerAdapter:
    """封装通用的类别注册与任务提交逻辑."""

    def __init__(
        self,
        *,
        categories: Optional[Mapping[str, Mapping[str, int]]] = None,
        auto_shutdown: bool = True,
        executor_factory: Optional[Any] = None,
    ) -> None:
        self._executor_factory = executor_factory or NativeThreadPool
        self._scheduler = NativeScheduler(executor_factory=self._executor_factory)
        self._categories: Dict[str, Dict[str, int]] = {}
        self._auto_shutdown = auto_shutdown
        if categories:
            self.configure(categories)

    def configure(self, categories: Mapping[str, Mapping[str, int]]) -> None:
        """使用新的类别配置重建调度器."""
        self._scheduler.shutdown(wait=True)
        self._scheduler = NativeScheduler(executor_factory=self._executor_factory)
        self._categories = {}

        for name, cfg in categories.items():
            queue_capacity = max(1, int(cfg.get("queue_capacity", 1024)))
            max_workers = max(1, int(cfg.get("max_workers", 4)))
            self._scheduler.register_category(
                name,
                queue_capacity=queue_capacity,
                max_workers=max_workers,
            )
            self._categories[name] = {
                "queue_capacity": queue_capacity,
                "max_workers": max_workers,
            }
        LOGGER.debug("scheduler adapter configured categories: %s", self._categories)

    def ensure_category(
        self,
        name: str,
        *,
        queue_capacity: Optional[int] = None,
        max_workers: Optional[int] = None,
    ) -> None:
        desired = {
            "queue_capacity": max(1, int(queue_capacity or self._categories.get(name, {}).get("queue_capacity", 1024))),
            "max_workers": max(1, int(max_workers or self._categories.get(name, {}).get("max_workers", 4))),
        }
        current = self._categories.get(name)
        if current == desired:
            return
        updated = dict(self._categories)
        updated[name] = desired
        self.configure(updated)

    def submit(
        self,
        category: str,
        func,
        args: Optional[Iterable[Any]] = None,
        kwargs: Optional[Mapping[str, Any]] = None,
    ):
        positional = tuple(args or ())
        keyword = dict(kwargs or {})
        return self._scheduler.submit(
            category,
            func,
            call_args=positional,
            call_kwargs=keyword,
        )

    def stats(self) -> Dict[str, Any]:
        return self._scheduler.stats()

    def shutdown(self, *, wait: bool = True) -> None:
        self._scheduler.shutdown(wait=wait)

    def get_categories(self) -> Dict[str, Dict[str, int]]:
        return dict(self._categories)

    def __enter__(self) -> "SchedulerAdapter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._auto_shutdown:
            self.shutdown(wait=True)

