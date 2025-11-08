# -*- coding: utf-8 -*-
"""
启动阶段进程清理工具集。

提供统一的方法触发监控进程与数据进程的清理逻辑，避免在多个模块中复制相同代码。
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

logger = logging.getLogger("backend.startup.cleanup")


def _load_cleanup_functions() -> tuple[List[Callable[[], None]], List[Callable[[], None]]]:
    """动态加载清理函数，避免循环依赖。"""
    process_cleanups: List[Callable[[], None]] = []
    signal_cleanups: List[Callable[[], None]] = []

    try:
        from backend.startup.workers.monitor_launcher import (
            cleanup_all_processes as cleanup_monitor_processes,
            _cleanup_signal_file as cleanup_monitor_signal,
        )

        process_cleanups.append(cleanup_monitor_processes)
        signal_cleanups.append(cleanup_monitor_signal)
    except Exception as exc:  # pragma: no cover - 仅在导入失败时触发
        logger.debug("加载监控进程清理函数失败: %s", exc)

    try:
        from backend.startup.workers.data_launcher import (
            cleanup_all_processes as cleanup_data_processes,
            _cleanup_signal_file as cleanup_data_signal,
        )

        process_cleanups.append(cleanup_data_processes)
        signal_cleanups.append(cleanup_data_signal)
    except Exception as exc:  # pragma: no cover - 仅在导入失败时触发
        logger.debug("加载数据进程清理函数失败: %s", exc)

    return process_cleanups, signal_cleanups


def run_backend_process_cleanup(label: str = "进程清理") -> bool:
    """
    触发监控进程和数据进程的清理逻辑。

    Args:
        label: 用于日志的标签，帮助区分不同触发来源。

    Returns:
        bool: 是否全部清理成功（即未捕获到异常）。
    """
    process_cleanups, signal_cleanups = _load_cleanup_functions()

    if not process_cleanups and not signal_cleanups:
        logger.debug("未能加载任何进程清理函数，跳过清理触发")
        return False

    errors: List[str] = []

    for cleanup in process_cleanups:
        try:
            cleanup()
        except Exception as exc:  # pragma: no cover - 清理失败时记录
            errors.append(f"{cleanup.__module__}.{cleanup.__name__}: {exc}")
            logger.warning("执行%s失败: %s", cleanup, exc, exc_info=True)

    for cleanup_signal in signal_cleanups:
        try:
            cleanup_signal()
        except Exception as exc:  # pragma: no cover - 信号文件清理失败可忽略
            logger.debug("清理信号文件失败（可忽略）: %s", exc)

    if errors:
        logger.error("❌ %s失败: %s", label, "; ".join(errors))
        return False

    logger.info("✅ %s完成", label)
    return True


__all__ = ["run_backend_process_cleanup"]

