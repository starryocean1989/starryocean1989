# -*- coding: utf-8 -*-
"""BootOrchestrator - 前端就绪协议与分层启动编排骨架.

用途:
- 统一管理就绪阶段标记(如: config_ready, backend_ready, ui_ready, ui_visible)
- 允许模块订阅某些就绪点再执行回调 (on_ready)
- 查询就绪状态 (is_ready)
- 线程安全, 可跨线程标记

注意:
- 该类设计为轻量级纯Python, 不依赖Qt对象, 可在任何位置导入和使用
- 回调执行在标记线程直接调用, 如用于Qt UI更新, 建议回调中使用 QTimer.singleShot(0, ...) 切回主线程
"""

from __future__ import annotations
import threading
from typing import Callable, Dict, List, Set


class BootOrchestrator:
    def __init__(self) -> None:
        self._ready_flags: Set[str] = set()
        self._waiters: Dict[str, List[Callable[[], None]]] = {}
        self._lock = threading.RLock()

    def mark_ready(self, flag: str) -> None:
        """标记某个就绪点达到, 并触发对应订阅者."""
        callbacks: List[Callable[[], None]] = []
        with self._lock:
            if flag in self._ready_flags:
                # 已标记过, 避免重复触发, 但保持幂等
                return
            self._ready_flags.add(flag)
            callbacks = self._waiters.pop(flag, [])
        # 在锁外触发回调, 避免死锁
        for cb in callbacks:
            try:
                cb()
            except Exception:
                # 回调自身异常不影响其他订阅者
                pass

    def is_ready(self, flag: str) -> bool:
        with self._lock:
            return flag in self._ready_flags

    def on_ready(self, flag: str, callback: Callable[[], None]) -> None:
        """订阅某个就绪点; 若已就绪则立即触发."""
        call_immediately = False
        with self._lock:
            if flag in self._ready_flags:
                call_immediately = True
            else:
                self._waiters.setdefault(flag, []).append(callback)
        if call_immediately:
            try:
                callback()
            except Exception:
                pass

    # 组合条件: 当多个flag均就绪时触发
    def on_all_ready(self, flags: List[str], callback: Callable[[], None]) -> None:
        def _check_and_fire():
            if all(self.is_ready(f) for f in flags):
                try:
                    callback()
                except Exception:
                    pass
        # 对每个flag都注册一次, 任一flag就绪都会尝试检查
        pending = False
        with self._lock:
            pending = not all(f in self._ready_flags for f in flags)
        if not pending:
            _check_and_fire()
            return
        for f in flags:
            self.on_ready(f, _check_and_fire)


# 提供一个全局单例(可选), 便于快速集成
_global_orchestrator: BootOrchestrator | None = None
_global_lock = threading.Lock()


def get_boot_orchestrator() -> BootOrchestrator:
    global _global_orchestrator
    if _global_orchestrator is None:
        with _global_lock:
            if _global_orchestrator is None:
                _global_orchestrator = BootOrchestrator()
    return _global_orchestrator