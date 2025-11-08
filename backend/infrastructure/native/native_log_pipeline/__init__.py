# -*- coding: utf-8 -*-
"""native_log_pipeline Python 接口."""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from .pipeline import (  # type: ignore[F401]
    DEFAULT_BATCH_SIZE,
    DEFAULT_FLUSH_MS,
    Pipeline,
    get_version,
    install as _install,
)

__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_FLUSH_MS",
    "Pipeline",
    "install",
    "create",
    "set_fallback",
    "flush_and_close",
    "get_version",
]


class NativeLogPipelineError(RuntimeError):
    """统一的原生日志管线异常."""


def install(
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    flush_ms: float = DEFAULT_FLUSH_MS,
    fallback: Optional[Callable[[Iterable[dict]], None]] = None,
    event_callback: Optional[Callable[[Iterable[dict]], None]] = None,
    sqlite_path: Optional[str] = None,
) -> Pipeline:
    """创建并返回原生管线实例."""

    try:
        pipeline: Pipeline = _install(
            batch_size=batch_size,
            flush_ms=flush_ms,
            fallback=fallback,
            event_callback=event_callback,
            sqlite_path=sqlite_path,
        )
    except Exception as exc:  # noqa: BLE001
        raise NativeLogPipelineError(str(exc)) from exc
    return pipeline


def create(**kwargs) -> Pipeline:
    """兼容旧接口，转到 :func:`install`."""
    return install(**kwargs)


def set_fallback(pipeline: Pipeline, fallback: Callable[[Iterable[dict]], None]) -> None:
    """更新原生缓冲区的兜底回调."""
    pipeline.set_fallback(fallback)


def flush_and_close(pipeline: Optional[Pipeline]) -> None:
    """安全关闭原生缓冲区."""
    if pipeline is None:
        return
    pipeline.flush_and_close()
