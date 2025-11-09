# -*- coding: utf-8 -*-
"""Native 扩展日志桥接模块.

此模块提供 Python 侧的日志桥接入口，供 C 扩展通过 C API 调用以输出统一日志。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from backend.infrastructure.system_vnpy.logging_system import (
    LogType,
    bind_logger_defaults,
    get_alert_logger,
)

__all__ = [
    "NativeLogLevel",
    "install_native_logging_bridge",
    "native_call_guard",
    "native_async_call_guard",
    "log_from_native",
]


@dataclass(frozen=True)
class NativeLogLevel:
    """与 C 端约定的日志等级常量."""

    DEBUG: int = 10
    INFO: int = 20
    WARNING: int = 30
    ERROR: int = 40
    CRITICAL: int = 50


# 默认 logger 设置
_logger = bind_logger_defaults(
    logging.getLogger("backend.native.bridge"),
    log_type=LogType.SYSTEM.value,
    scenario="native.bridge",
)
_alert_logger = get_alert_logger("backend.native.bridge.alert", scenario="native.bridge")

# 映射 C 端等级到 logging 模块等级
_LEVEL_MAP: Dict[int, int] = {
    NativeLogLevel.DEBUG: logging.DEBUG,
    NativeLogLevel.INFO: logging.INFO,
    NativeLogLevel.WARNING: logging.WARNING,
    NativeLogLevel.ERROR: logging.ERROR,
    NativeLogLevel.CRITICAL: logging.CRITICAL,
}

# 可注入自定义 handler
_custom_handler: Optional[Callable[[Dict[str, Any]], None]] = None


def install_native_logging_bridge(
    *,
    logger: Optional[logging.Logger] = None,
    alert_logger: Optional[logging.Logger] = None,
    level_map: Optional[Dict[int, int]] = None,
    handler: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> None:
    """安装日志桥接配置.

    Args:
        logger: 主日志对象，默认使用 ``backend.native.bridge``。
        alert_logger: 告警日志对象，用于 ERROR 及以上级别。
        level_map: 自定义等级映射（C 端等级 -> logging 等级）。
        handler: 若提供，将在记录日志前回调；可用于采集统计信息。
    """

    global _logger, _alert_logger, _LEVEL_MAP, _custom_handler

    if logger is not None:
        _logger = bind_logger_defaults(
            logger,
            log_type=LogType.SYSTEM.value,
            scenario="native.bridge",
        )
    if alert_logger is not None:
        _alert_logger = alert_logger
    if level_map:
        _LEVEL_MAP = {**_LEVEL_MAP, **level_map}
    _custom_handler = handler


def _emit_log(record: Dict[str, Any]) -> None:
    level = record.get("level", NativeLogLevel.INFO)
    component = record.get("component") or record.get("module") or "native"
    function = record.get("function") or "<unknown>"
    line = record.get("line", 0)
    message = record.get("message") or ""
    details = record.get("details")

    python_level = _LEVEL_MAP.get(level, logging.INFO)

    extra = {
        "log_type": LogType.SYSTEM.value,
        "scenario": component or "native.bridge",
        "native_module": component,
        "native_function": function,
        "native_line": line,
    }
    if details:
        extra["native_details"] = details

    _logger.log(python_level, message, extra=extra)

    if python_level >= logging.ERROR and _alert_logger is not None:
        _alert_logger.error(
            message,
            extra={
                "scenario": component or "native.bridge",
                "native_function": function,
                "native_line": line,
                "native_details": details,
            },
        )


def log_from_native(
    level: int,
    component: str,
    function: str,
    line: int,
    message: str,
    details: Optional[str] = None,
) -> None:
    """供 C 扩展调用的日志入口."""

    record = {
        "level": level,
        "component": component,
        "function": function,
        "line": line,
        "message": message,
        "details": details,
    }

    if _custom_handler is not None:
        try:
            _custom_handler(record)
        except Exception:  # noqa: BLE001
            _logger.debug("native logging handler raised", exc_info=True)

    _emit_log(record)


def _log_exception(component: Optional[str], func_name: str, exc: BaseException) -> None:
    message = f"{func_name} raised {type(exc).__name__}: {exc}"
    details = getattr(exc, "details", None)
    log_from_native(
        NativeLogLevel.ERROR,
        component or "native.bridge",
        func_name,
        line=0,
        message=message,
        details=str(details) if details else None,
    )


def native_call_guard(
    component: Optional[str] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """同步函数守护装饰器，捕获异常并输出统一日志."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(func):
            raise TypeError("native_call_guard 不支持异步函数，请使用 native_async_call_guard")

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                _log_exception(component or func.__module__, func.__qualname__, exc)
                raise

        wrapper.__name__ = func.__name__
        wrapper.__qualname__ = func.__qualname__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


def native_async_call_guard(
    component: Optional[str] = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """异步函数守护装饰器，捕获异常并输出统一日志."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        if not inspect.iscoroutinefunction(func):
            raise TypeError("native_async_call_guard 仅适用于 async 函数")

        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                _log_exception(component or func.__module__, func.__qualname__, exc)
                raise

        wrapper.__name__ = func.__name__
        wrapper.__qualname__ = func.__qualname__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


async def run_guarded_native_coroutine(
    coro: Awaitable[Any],
    *,
    component: Optional[str] = None,
    name: str = "<native-coro>",
) -> Any:
    """对外提供的异步执行辅助，用于包装直接返回协程的场景."""

    try:
        return await coro
    except Exception as exc:  # noqa: BLE001
        _log_exception(component or getattr(coro, "__module__", "native.bridge"), name, exc)
        raise


def ensure_event_loop_future(fut: Awaitable[Any]) -> Awaitable[Any]:
    """确保在事件循环中运行的便捷函数（便于 native 模块复用）."""

    if asyncio.isfuture(fut) or asyncio.iscoroutine(fut):
        return asyncio.ensure_future(fut)
    raise TypeError("ensure_event_loop_future 只接受 Future 或协程对象")
