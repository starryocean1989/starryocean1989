# -*- coding: utf-8 -*-
from __future__ import annotations

from concurrent.futures import Future
from typing import Any, List, Tuple

import pytest

import backend.infrastructure.native.native_scheduler as scheduler_module


class ImmediateExecutor:
    def __init__(self, max_workers: int, registry: List[int]) -> None:
        self.max_workers = max_workers
        self.registry = registry
        self.registry.append(max_workers)
        self.shutdown_calls: List[bool] = []

    def submit(self, fn, worker_args):
        fut = Future()
        try:
            result = fn(*worker_args)
        except Exception as exc:  # pragma: no cover
            fut.set_exception(exc)
        else:
            fut.set_result(result)
        return fut

    def shutdown(self, wait: bool = True) -> None:
        self.shutdown_calls.append(wait)


class DeferredExecutor:
    def __init__(self, max_workers: int) -> None:
        self.max_workers = max_workers
        self._queue: List[Tuple[Any, Tuple[Any, ...], Future]] = []
        self.shutdown_called: List[bool] = []

    def submit(self, fn, worker_args):
        fut = Future()
        self._queue.append((fn, worker_args, fut))
        return fut

    def run_all(self) -> None:
        queue = list(self._queue)
        self._queue.clear()
        for fn, worker_args, fut in queue:
            try:
                result = fn(*worker_args)
            except Exception as exc:  # pragma: no cover
                fut.set_exception(exc)
            else:
                fut.set_result(result)

    def shutdown(self, wait: bool = True) -> None:
        self.shutdown_called.append(wait)


def _capturing_factory(registry: List[int]):
    def factory(max_workers: int):
        return ImmediateExecutor(max_workers, registry)
    return factory


def _deferred_factory(executor: DeferredExecutor):
    def factory(max_workers: int):
        return executor
    return factory


def test_register_category_invokes_executor_factory():
    calls: List[int] = []
    scheduler = scheduler_module.NativeScheduler(executor_factory=_capturing_factory(calls))
    try:
        scheduler.register_category("demo", max_workers=3)
        assert calls == [3]
    finally:
        scheduler.shutdown()


def test_submit_executes_callable_and_returns_future():
    scheduler = scheduler_module.NativeScheduler(executor_factory=_capturing_factory([]))
    try:
        scheduler.register_category("demo", max_workers=2)

        def callable(value: int) -> int:
            return value * 2

        future = scheduler.submit("demo", callable, call_args=(21,))
        assert future.result(timeout=1.0) == 42
    finally:
        scheduler.shutdown()


def test_stats_reflects_pending_queue_size():
    executor = DeferredExecutor(max_workers=1)
    scheduler = scheduler_module.NativeScheduler(executor_factory=_deferred_factory(executor))
    try:
        scheduler.register_category("demo", max_workers=1)

        def passthrough(value: int) -> int:
            return value

        scheduler.submit("demo", passthrough, call_args=(1,))

        stats = scheduler.stats()
        assert stats["demo"]["queue_size"] == 1

        executor.run_all()
        stats_after = scheduler.stats()
        assert stats_after["demo"]["queue_size"] == 0
    finally:
        executor.run_all()
        scheduler.shutdown()


def test_shutdown_propagates_wait_flag():
    executor = DeferredExecutor(max_workers=1)
    scheduler = scheduler_module.NativeScheduler(executor_factory=_deferred_factory(executor))
    scheduler.register_category("demo", max_workers=1)
    scheduler.shutdown(wait=False)

    assert executor.shutdown_called == [False]
