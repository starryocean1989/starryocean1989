# -*- coding: utf-8 -*-
"""高性能任务调度器，提供原生与纯 Python 双实现。"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Callable, Optional

try:  # pragma: no cover - 可选原生扩展
    from ._native_scheduler import (
        NativeScheduler as _NativeSchedulerCore,
        SCHEDULER_AVAILABLE as _CORE_AVAILABLE,
        __version__,
    )
except ImportError:  # pragma: no cover
    _NativeSchedulerCore = None
    _CORE_AVAILABLE = False
    __version__ = "0.0.0"

from .py_impl import PyNativeScheduler


def _env_enabled(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


_FORCE_NATIVE = _env_enabled("NATIVE_SCHEDULER_FORCE_NATIVE")
_FORCE_PY = _env_enabled("NATIVE_SCHEDULER_FORCE_PY")
USING_NATIVE_CORE = bool(_NativeSchedulerCore and _CORE_AVAILABLE and not _FORCE_PY)
if _FORCE_NATIVE and not USING_NATIVE_CORE:
    raise ImportError("native scheduler core requested but native extension is unavailable")


class NativeScheduler:
    """统一调度接口，根据运行环境选择原生或 Python 实现。"""

    def __init__(self, *, executor_factory: Optional[Callable[[int], object]] = None) -> None:
        if USING_NATIVE_CORE:
            if executor_factory is None:
                raise ValueError("executor_factory is required when native core is enabled")
            self._impl = _NativeSchedulerCore(executor_factory=executor_factory)  # type: ignore[call-arg]
        else:
            self._impl = PyNativeScheduler(executor_factory=executor_factory)

    def register_category(self, *args, **kwargs):
        return self._impl.register_category(*args, **kwargs)

    def submit(self, *args, **kwargs):
        return self._impl.submit(*args, **kwargs)

    def stats(self, *args, **kwargs):
        return self._impl.stats(*args, **kwargs)

    def shutdown(self, *args, **kwargs):
        return self._impl.shutdown(*args, **kwargs)


SCHEDULER_AVAILABLE = True


if TYPE_CHECKING:  # pragma: no cover
    from backend.infrastructure.scheduling.cron_scheduler import NativeCronScheduler  # noqa: F401


def __getattr__(name: str):
    if name == "NativeCronScheduler":
        from backend.infrastructure.scheduling.cron_scheduler import NativeCronScheduler as _Cron

        return _Cron
    raise AttributeError(name)


__all__ = [
    "NativeScheduler",
    "SCHEDULER_AVAILABLE",
    "USING_NATIVE_CORE",
    "__version__",
    "NativeCronScheduler",
]

