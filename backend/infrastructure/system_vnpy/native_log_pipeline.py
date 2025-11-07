# -*- coding: utf-8 -*-
"""native_log_pipeline 集成适配层.

本模块不会直接依赖真实的 C 扩展实现，而是提供一个轻量的探测与回退封装，
便于在运行环境中优先启用 `native_log_pipeline`，无法加载时自动回落到
既有的 Python Handler 逻辑。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable, Optional

_NATIVE_MODULE: Optional[Any] = None


def _is_env_enabled() -> bool:
    """读取环境变量开关，默认开启。"""

    value = os.getenv("NATIVE_LOG_PIPELINE", "1").strip().lower()
    return value not in {"0", "false", "off"}


def _load_native(logger: Optional[logging.Logger] = None) -> Optional[Any]:
    """尝试加载 native 扩展模块，失败时返回 ``None``。"""

    global _NATIVE_MODULE

    if _NATIVE_MODULE is not None:
        return _NATIVE_MODULE

    if not _is_env_enabled():
        if logger:
            logger.debug("NATIVE_LOG_PIPELINE 环境变量已关闭，保持 Python 实现")
        return None

    try:
        module = import_module("native_log_pipeline")
        _NATIVE_MODULE = module
        if logger:
            logger.info("检测到 native_log_pipeline 扩展，准备启用")
        return module
    except Exception as exc:  # noqa: BLE001 - 仅做探测日志
        if logger:
            logger.debug("native_log_pipeline 不可用: %s", exc, exc_info=True)
        return None


@dataclass
class NativePipelineAdapter:
    """原生日志管线适配器."""

    handler: Optional[logging.Handler]
    close: Callable[[], None]


def try_install(
    *,
    python_handler: logging.Handler,
    db_path: str,
    event_callback: Optional[Callable[[dict], None]],
    batch_size: int = 128,
    flush_interval_ms: int = 500,
    logger: Optional[logging.Logger] = None,
) -> Optional[NativePipelineAdapter]:
    """尝试安装 native 日志管线。

    如果扩展不可用或初始化失败，将返回 ``None``，调用方应继续使用
    原有的 Python Handler。
    """

    native = _load_native(logger)
    if native is None:
        return None

    # 允许调用方控制是否启用事件桥接
    enable_event_bridge = event_callback is not None

    try:
        install_fn = getattr(native, "install", None)
        if install_fn is None:
            raise AttributeError("native_log_pipeline.install 不存在")

        handler = install_fn(
            batch_size=batch_size,
            flush_interval_ms=flush_interval_ms,
            sqlite_path=db_path,
            enable_event_bridge=enable_event_bridge,
        )
    except Exception as exc:  # noqa: BLE001 - 兼容未知扩展签名
        if logger:
            logger.warning(
                "native_log_pipeline.install 执行失败，回退到 Python Handler: %s",
                exc,
            )
        return None

    # 设置回退 emit
    if hasattr(native, "set_fallback"):
        try:
            native.set_fallback(python_handler.emit)
        except Exception as exc:  # noqa: BLE001
            if logger:
                logger.debug("native_log_pipeline.set_fallback 调用失败: %s", exc)

    # 如果扩展支持事件回调，则绑定统一的发布函数
    if event_callback and hasattr(native, "set_event_callback"):
        try:
            native.set_event_callback(event_callback)
        except Exception as exc:  # noqa: BLE001
            if logger:
                logger.debug("native_log_pipeline.set_event_callback 调用失败: %s", exc)

    def _close() -> None:
        try:
            if hasattr(native, "flush_and_close"):
                native.flush_and_close()
            elif hasattr(native, "flush"):
                native.flush()
        except Exception as exc:  # noqa: BLE001
            if logger:
                logger.debug("native_log_pipeline 关闭失败: %s", exc)

    return NativePipelineAdapter(handler=handler if isinstance(handler, logging.Handler) else None, close=_close)


def flush_and_close(logger: Optional[logging.Logger] = None) -> None:
    """显式触发扩展的刷新与关闭。"""

    native = _load_native(logger)
    if native is None:
        return

    try:
        if hasattr(native, "flush_and_close"):
            native.flush_and_close()
        elif hasattr(native, "flush"):
            native.flush()
    except Exception as exc:  # noqa: BLE001
        if logger:
            logger.debug("native_log_pipeline.flush_and_close 调用失败: %s", exc)

