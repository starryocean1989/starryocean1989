# -*- coding: utf-8 -*-
"""
跨进程父子关系守护工具。

用于在子进程中监控父进程是否仍然存活，防止主进程异常退出后子进程成为孤儿。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Optional

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - 极端情况下psutil不可用
    psutil = None  # type: ignore

_watchdog_registry: dict[str, int] = {}
_registry_lock = threading.Lock()


def ensure_parent_watchdog(
    label: str,
    logger: Optional[logging.Logger] = None,
    check_interval: float = 5.0,
) -> bool:
    """
    启动父进程存活监控线程。

    Args:
        label: 当前子进程的标识，用于日志和去重。
        logger: 可选Logger实例，用于记录监控信息。
        check_interval: 监控检查的时间间隔（秒）。

    Returns:
        bool: 如果成功启动或已存在同标签的监控线程返回True，否则False。
    """
    if psutil is None:
        if logger:
            logger.warning(
                "[PARENT-WATCHDOG] psutil 不可用，无法开启父进程监控，子进程在主进程崩溃时可能残留"
            )
        return False

    parent_pid = os.getppid()

    # 在Windows服务环境中，父进程可能为0或1，此时无需再监控
    if parent_pid <= 1:
        if logger:
            logger.debug(
                "[PARENT-WATCHDOG] 未检测到有效的父进程 (ppid=%d)，跳过监控", parent_pid
            )
        return False

    with _registry_lock:
        existing_pid = _watchdog_registry.get(label)
        if existing_pid == parent_pid:
            # 同一父进程的监控已经存在
            if logger:
                logger.debug(
                    "[PARENT-WATCHDOG] label=%s 的父进程监控已存在 (ppid=%d)",
                    label,
                    parent_pid,
                )
            return True

        _watchdog_registry[label] = parent_pid

    assert psutil is not None  # 安全保障：此处已确认psutil可用

    def _terminate_process(reason: str) -> None:
        if logger:
            logger.error(
                "[PARENT-WATCHDOG] ❌ 检测到父进程异常，原因: %s，当前进程将立即退出",
                reason,
            )
        # 使用os._exit保证立即退出，避免阻塞在asyncio事件循环或Qt主循环中
        os._exit(0)

    def _watch() -> None:
        psutil_module = psutil  # 类型收窄，后续引用安全

        try:
            parent = psutil_module.Process(parent_pid)  # type: ignore[attr-defined]
        except psutil_module.Error:  # type: ignore[attr-defined]
            _terminate_process("无法获取父进程信息")
            return

        if logger:
            logger.info(
                "[PARENT-WATCHDOG] 已启动父进程监控线程 label=%s, parent_pid=%d",
                label,
                parent_pid,
            )

        while True:
            time.sleep(check_interval)
            try:
                if not parent.is_running():
                    _terminate_process("父进程已停止运行")
                    break

                if parent.status() == psutil_module.STATUS_ZOMBIE:  # type: ignore[attr-defined]
                    _terminate_process("父进程进入僵尸状态")
                    break

                # 如果父进程退出，新的同PID进程很难立即出现，但仍做额外校验
                if parent.ppid() <= 1:
                    _terminate_process("父进程已脱离原有父子关系")
                    break
            except psutil_module.NoSuchProcess:  # type: ignore[attr-defined]
                _terminate_process("父进程不存在")
                break
            except psutil_module.Error as exc:  # type: ignore[attr-defined]  # pragma: no cover - psutil异常
                if logger:
                    logger.warning(
                        "[PARENT-WATCHDOG] 检查父进程状态失败: %s，稍后重试", exc
                    )

    watchdog_thread = threading.Thread(
        target=_watch,
        name=f"{label}-parent-watchdog",
        daemon=True,
    )
    watchdog_thread.start()

    return True


__all__ = ["ensure_parent_watchdog"]

