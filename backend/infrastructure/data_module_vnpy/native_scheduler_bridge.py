# -*- coding: utf-8 -*-
"""
Native 调度器桥接层

用于在业务模块中以统一方式调用 C 扩展调度核心；当扩展不可用时保持空对象，便于渐进式迁移。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from backend.infrastructure.native.native_scheduler import USING_NATIVE_CORE
from backend.infrastructure.scheduling.native_scheduler_adapter import SchedulerAdapter

logger = logging.getLogger(__name__)


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
        self._adapter = SchedulerAdapter(
            categories=categories or self.DEFAULT_CATEGORIES,
            auto_shutdown=auto_shutdown,
        )
        self._auto_shutdown = auto_shutdown
        try:
            logger.info(
                "NativeSchedulerBridge initialised: using_native=%s, categories=%s",
                USING_NATIVE_CORE,
                list(self._adapter.get_categories().keys()),
            )
        except Exception:  # pragma: no cover - 安全兜底
            logger.debug("bridge init logging failed", exc_info=True)

    @property
    def available(self) -> bool:
        return True

    @property
    def categories(self) -> Dict[str, Dict[str, int]]:
        return self._adapter.get_categories()

    def ensure_category(
        self,
        name: str,
        *,
        queue_capacity: Optional[int] = None,
        max_workers: Optional[int] = None,
    ) -> None:
        self._adapter.ensure_category(
            name,
            queue_capacity=queue_capacity,
            max_workers=max_workers,
        )

    def submit(
        self,
        category: str,
        func,
        args: Tuple[Any, ...] | None = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ):
        return self._adapter.submit(category, func, args=args, kwargs=kwargs)

    def stats(self) -> Dict[str, Any]:
        return self._adapter.stats()

    def shutdown(self, wait: bool = True) -> None:
        logger.info("bridge shutdown: wait=%s", wait)
        self._adapter.shutdown(wait=wait)

    def get_metrics(self) -> Dict[str, Any]:
        return self.stats()

    def reset(self, categories: Dict[str, Dict[str, int]]) -> None:
        self._adapter.configure(categories)

    def __enter__(self) -> "NativeSchedulerBridge":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._auto_shutdown:
            self.shutdown(wait=True)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<NativeSchedulerBridge categories={list(self.categories.keys())}>"

