# -*- coding: utf-8 -*-
"""native_log_pipeline 扩展的集成封装."""

from __future__ import annotations

import logging
import os
from importlib import import_module
from typing import Any, Callable, Iterable, Optional

DEFAULT_BATCH_SIZE = 256
DEFAULT_FLUSH_MS = 2000.0

BatchCallback = Callable[[Iterable[dict]], None]


def _env_flag(name: str, default: str = "1") -> bool:
    value = os.getenv(name, default)
    if value is None:
        return False
    return value.strip().lower() not in {"0", "false", "off", "no"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    try:
        return int(raw.strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "")
    try:
        return float(raw.strip() or default)
    except ValueError:
        return default


class PipelineHandle:
    """包装 native_log_pipeline.Pipeline，提供统一操作。"""

    __slots__ = ("pipeline", "_logger")

    def __init__(self, pipeline: Any, logger: Optional[logging.Logger] = None) -> None:
        self.pipeline = pipeline
        self._logger = logger

    def push(self, record: dict) -> bool:
        return bool(self.pipeline.push(record))

    def pending(self) -> int:
        return int(self.pipeline.pending())

    def flush(self, *, force: bool = False) -> bool:
        try:
            return bool(self.pipeline.flush(force=bool(force)))
        except AttributeError:
            if self._logger:
                self._logger.debug("native pipeline 缺少 flush 接口，尝试 take_batch")
            batch = self.pipeline.take_batch()
            return bool(batch)

    def flush_and_close(self) -> None:
        try:
            self.pipeline.flush_and_close()
        except AttributeError:
            try:
                self.pipeline.clear()
            except Exception:  # noqa: BLE001
                if self._logger:
                    self._logger.debug("native pipeline clear 失败", exc_info=True)

    def set_fallback(self, callback: BatchCallback) -> None:
        try:
            self.pipeline.set_fallback(callback)
        except AttributeError:
            if self._logger:
                self._logger.debug("native pipeline 不支持 set_fallback 接口")

    def stats(self) -> dict[str, Any]:
        try:
            stats_obj = self.pipeline.stats()
        except AttributeError:
            return {}
        if isinstance(stats_obj, dict):
            return stats_obj
        return dict(stats_obj or {})


def _should_enable() -> bool:
    return _env_flag("NATIVE_LOG_PIPELINE", "1")


def install_pipeline(
    on_batch: BatchCallback,
    logger: Optional[logging.Logger] = None,
    *,
    sqlite_path: Optional[str] = None,
) -> Optional[PipelineHandle]:
    """根据环境变量安装原生日志管线，安装失败自动回退."""

    if not _should_enable():
        if logger:
            logger.debug("native_log_pipeline 被 NATIVE_LOG_PIPELINE=0 禁用")
        return None

    try:
        module = import_module("native_log_pipeline")
    except Exception as exc:  # noqa: BLE001
        if logger:
            logger.debug("native_log_pipeline 模块导入失败：%s", exc, exc_info=True)
        return None

    batch_size = max(1, _env_int("NATIVE_LOG_PIPELINE_BATCH", DEFAULT_BATCH_SIZE))
    flush_ms = max(0.0, _env_float("NATIVE_LOG_PIPELINE_FLUSH_MS", DEFAULT_FLUSH_MS))

    env_sqlite = os.getenv("NATIVE_LOG_PIPELINE_SQLITE", "").strip()
    if env_sqlite:
        sqlite_path = env_sqlite

    def _fallback(batch: Iterable[dict]) -> None:
        try:
            on_batch(list(batch))
        except Exception:  # noqa: BLE001
            if logger:
                logger.error("native_log_pipeline fallback 处理失败", exc_info=True)

    try:
        pipeline_obj = module.install(
            batch_size=batch_size,
            flush_ms=flush_ms,
            fallback=_fallback,
            event_callback=None,
            sqlite_path=sqlite_path,
        )
    except Exception as exc:  # noqa: BLE001
        if logger:
            logger.debug("native_log_pipeline.install 失败: %s", exc, exc_info=True)
        return None

    handle = PipelineHandle(pipeline=pipeline_obj, logger=logger)
    if logger:
        config_msg = (
            f"native_log_pipeline 已启用(batch={batch_size}, "
            f"flush_ms={flush_ms}, sqlite={'auto' if sqlite_path else 'disabled'})"
        )
        logger.info(config_msg)
    return handle


def flush_pipeline(handle: Optional[PipelineHandle], *, force: bool = False) -> bool:
    if handle is None:
        return False
    return handle.flush(force=force)


def dispose_pipeline(handle: Optional[PipelineHandle]) -> None:
    if handle is None:
        return
    try:
        handle.flush_and_close()
    except Exception:  # noqa: BLE001
        pass


# 兼容旧接口名称
create_pipeline = install_pipeline


__all__ = [
    "PipelineHandle",
    "install_pipeline",
    "create_pipeline",
    "flush_pipeline",
    "dispose_pipeline",
]

