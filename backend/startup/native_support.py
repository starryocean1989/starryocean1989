# -*- coding: utf-8 -*-
"""
启动阶段原生能力封装

将 native C 扩展（线程池、调度器、同步原语）封装成启动流程可复用的执行器，
同时提供线程安全的服务跟踪器与事件桥接能力，确保 Python 层以最少逻辑管理
执行流程。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from backend.startup.event_bus import StartupEvent, StartupEventType, EventBus

try:
    from backend.infrastructure.native.native_threadpool import (  # type: ignore
        NativeThreadPool,
        THREADPOOL_AVAILABLE as _THREADPOOL_AVAILABLE,
    )
except ImportError:  # pragma: no cover
    from concurrent.futures import ThreadPoolExecutor

    logging.getLogger("backend.startup.native_support").warning(
        "native_threadpool not available, falling back to ThreadPoolExecutor"
    )

    class NativeThreadPool(ThreadPoolExecutor):  # type: ignore
        """Fallback thread pool."""

        def __init__(self, max_workers: int = 4):
            super().__init__(max_workers=max_workers, thread_name_prefix="startup_fallback")

    _THREADPOOL_AVAILABLE = False

try:
    from backend.infrastructure.native.native_scheduler import (  # type: ignore
        NativeScheduler,
        USING_NATIVE_CORE as _SCHEDULER_NATIVE_CORE,
    )
except ImportError:  # pragma: no cover
    NativeScheduler = None  # type: ignore
    _SCHEDULER_NATIVE_CORE = False

try:
    from backend.infrastructure.native.native_gil import HighPerfEvent  # type: ignore

    _HIGH_PERF_EVENT_AVAILABLE = True
except ImportError:  # pragma: no cover
    HighPerfEvent = None  # type: ignore
    _HIGH_PERF_EVENT_AVAILABLE = False


logger = logging.getLogger("backend.startup.native_support")


class QtMainInvoker:
    """在 Qt 主线程执行回调的桥接器，缺失时降级为直接执行."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("backend.startup.qt_invoker")
        self._bridge = None
        self._qt_ready_getter = None
        self._available = False

        try:
            from PySide6.QtCore import QObject, Qt, QCoreApplication, Signal  # type: ignore
        except Exception:  # pragma: no cover - PySide6 缺失时降级
            self.logger.debug("PySide6 不可用，QtMainInvoker 将直接执行回调")
            return

        class _InvokeBridge(QObject):  # type: ignore[misc]
            invoke_signal = Signal(object, object, object)

            def __init__(self, outer_logger: logging.Logger):
                super().__init__()
                self._logger = outer_logger
                self.invoke_signal.connect(self._invoke, Qt.QueuedConnection)  # type: ignore[arg-type]

            def _invoke(self, func, args, kwargs):
                try:
                    func(*args, **kwargs)
                except Exception:
                    self._logger.exception("Qt 主线程回调执行失败")

        self._bridge = _InvokeBridge(self.logger)
        self._qt_ready_getter = QCoreApplication.instance  # type: ignore[attr-defined]
        if self._qt_ready_getter():
            self._available = True
        else:
            self.logger.debug("QCoreApplication 尚未就绪，QtMainInvoker 暂使用直接执行模式")

    @property
    def available(self) -> bool:
        """Qt 主线程是否就绪."""
        if self._qt_ready_getter is None:
            return False
        if not self._available and self._qt_ready_getter():
            self._available = True
        return self._available and self._bridge is not None

    def submit(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        """在 Qt 主线程调度 callback.

        当 Qt 主线程不可用时，将回退为当前线程同步执行。
        """
        if not callable(callback):
            raise TypeError("callback 必须可调用")

        if self.available:
            assert self._bridge is not None  # mypy: 保证存在
            self._bridge.invoke_signal.emit(callback, args, kwargs)  # type: ignore[call-arg]
            return True

        try:
            callback(*args, **kwargs)
        except Exception:
            self.logger.exception("Qt 主线程不可用，直接执行回调时发生异常")
        return False


class NativeSignal:
    """HighPerfEvent 包装（降级到 threading.Event）."""

    __slots__ = ("_event", "_lock")

    def __init__(self) -> None:
        self._lock = threading.RLock()
        if _HIGH_PERF_EVENT_AVAILABLE and HighPerfEvent is not None:
            self._event = HighPerfEvent()
        else:
            self._event = threading.Event()

    def set(self) -> None:
        with self._lock:
            self._event.set()

    def clear(self) -> None:
        if hasattr(self._event, "clear"):
            with self._lock:
                self._event.clear()

    def is_set(self) -> bool:
        if hasattr(self._event, "is_set"):
            return bool(self._event.is_set())
        return False

    def wait(self, timeout: Optional[float] = None) -> bool:
        if _HIGH_PERF_EVENT_AVAILABLE and hasattr(self._event, "wait"):
            if timeout is None:
                timeout_ms = None
            else:
                timeout_ms = int(max(timeout, 0) * 1000)
            result = self._event.wait() if timeout_ms is None else self._event.wait(timeout_ms)
            return bool(result)
        return self._event.wait(timeout)


@dataclass
class ServiceTaskOutcome:
    """服务初始化任务结果."""

    success: bool
    service: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    exception: Optional[BaseException] = None


@dataclass
class NativeStartupFuture:
    """封装提交到原生执行器的 Future."""

    service_name: str
    category: str
    critical: bool
    future: Any
    signal: NativeSignal
    started_at: float
    outcome: Optional[ServiceTaskOutcome] = None
    finished_at: Optional[float] = None
    _callbacks: List[Callable[["NativeStartupFuture"], None]] = field(
        default_factory=list, repr=False
    )

    def wait(self, timeout: Optional[float] = None) -> ServiceTaskOutcome:
        """等待任务完成并返回结果."""
        self.signal.wait(timeout)
        return self.result(timeout=timeout)

    def result(self, timeout: Optional[float] = None) -> ServiceTaskOutcome:
        """获取任务执行结果；必要时阻塞等待."""
        if self.outcome is None:
            try:
                result = self.future.result(timeout=timeout)  # type: ignore[attr-defined]
            except Exception as exc:  # pragma: no cover - 防御性
                self.outcome = ServiceTaskOutcome(
                    success=False,
                    metadata={},
                    message=str(exc),
                    exception=exc,
                )
            else:
                if isinstance(result, ServiceTaskOutcome):
                    self.outcome = result
                else:
                    self.outcome = ServiceTaskOutcome(success=bool(result), metadata={})
            self.finished_at = self.finished_at or time.time()
        return self.outcome

    def add_done_callback(self, callback: Callable[["NativeStartupFuture"], None]) -> None:
        """注册任务完成回调."""
        if not callable(callback):
            raise TypeError("callback 必须可调用")

        if self.outcome is not None:
            try:
                callback(self)
            except Exception:
                logger.exception("执行 NativeStartupFuture 回调失败")
            return

        self._callbacks.append(callback)

    def _notify_callbacks(self) -> None:
        if not self._callbacks:
            return
        callbacks = list(self._callbacks)
        self._callbacks.clear()
        for cb in callbacks:
            try:
                cb(self)
            except Exception:
                logger.exception("执行 NativeStartupFuture 回调失败")


class ServiceStartupTracker:
    """服务就绪追踪器，负责发布事件并提供阻塞等待能力."""

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._event_bus = event_bus
        self._services: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def bind_bus(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def register(
        self,
        service_name: str,
        *,
        category: str,
        critical: bool = False,
    ) -> NativeSignal:
        with self._lock:
            signal = NativeSignal()
            self._services[service_name] = {
                "status": "pending",
                "signal": signal,
                "critical": critical,
                "category": category,
                "metadata": {},
                "message": "",
                "exception": None,
                "start": time.time(),
                "end": None,
            }
            return signal

    def mark_ready(
        self,
        service_name: str,
        metadata: Optional[Dict[str, Any]] = None,
        message: str = "",
    ) -> None:
        payload_metadata = metadata or {}
        with self._lock:
            record = self._services.get(service_name)
            if not record:
                self.register(service_name, category="default")
                record = self._services[service_name]
            signal: NativeSignal = record["signal"]
            record.update(
                status="ready",
                metadata=payload_metadata,
                message=message,
                exception=None,
                end=time.time(),
            )
            signal.set()

        if self._event_bus:
            event = StartupEvent(
                event_type=StartupEventType.NODE_READY,
                node_id=f"service:{service_name}",
                message=message or f"服务 {service_name} 就绪",
                payload={
                    "ready_key": f"service:{service_name}",
                    "service": service_name,
                    "status": "ready",
                    **payload_metadata,
                },
            )
            self._event_bus.publish_threadsafe(event)

    def mark_failed(
        self,
        service_name: str,
        *,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        exception: Optional[BaseException] = None,
    ) -> None:
        payload_metadata = metadata or {}
        with self._lock:
            record = self._services.get(service_name)
            if not record:
                self.register(service_name, category="default")
                record = self._services[service_name]
            signal: NativeSignal = record["signal"]
            record.update(
                status="failed",
                metadata=payload_metadata,
                message=message,
                exception=exception,
                end=time.time(),
            )
            signal.set()

        if self._event_bus:
            event = StartupEvent(
                event_type=StartupEventType.NODE_FAILED,
                node_id=f"service:{service_name}",
                message=message,
                payload={
                    "ready_key": f"service:{service_name}",
                    "service": service_name,
                    "status": "failed",
                    **payload_metadata,
                },
            )
            self._event_bus.publish_threadsafe(event)

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {
                name: {
                    "status": data["status"],
                    "metadata": dict(data.get("metadata", {})),
                    "message": data.get("message", ""),
                    "critical": data.get("critical", False),
                    "category": data.get("category", "default"),
                    "exception": data.get("exception"),
                    "elapsed": (
                        (data.get("end") or time.time()) - data.get("start", time.time())
                    )
                    if data.get("start")
                    else None,
                }
                for name, data in self._services.items()
            }

    def wait_for(self, service_name: str, timeout: Optional[float] = None) -> bool:
        record = self._services.get(service_name)
        if not record:
            return False
        return record["signal"].wait(timeout)

    def wait_for_many(self, service_names: Iterable[str], timeout: Optional[float] = None) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        start = time.time()
        for name in service_names:
            remaining = None
            if timeout is not None:
                elapsed = time.time() - start
                remaining = max(timeout - elapsed, 0.0)
            results[name] = self.wait_for(name, timeout=remaining)
        return results


class NativeStartupRuntime:
    """封装 native 线程池/调度器的启动执行器."""

    def __init__(
        self,
        *,
        max_workers: int = 4,
        event_bus: Optional[EventBus] = None,
        service_tracker: Optional[ServiceStartupTracker] = None,
        use_scheduler: bool = False,
        default_timeout: float = 10.0,
        category_config: Optional[Dict[str, Dict[str, int]]] = None,
        qt_invoker: Optional[QtMainInvoker] = None,
    ) -> None:
        self.logger = logging.getLogger("backend.startup.native_runtime")
        self._event_bus = event_bus
        self._service_tracker = service_tracker
        self._default_timeout = default_timeout
        self._pool_max_workers = max(1, max_workers)
        self._pool = NativeThreadPool(max_workers=self._pool_max_workers)
        self._managed_executors: List[Any] = []
        self._category_config = category_config or {}
        self._registered_categories: set[str] = set()
        self._qt_invoker = qt_invoker or QtMainInvoker()
        self._inflight: Dict[str, NativeStartupFuture] = {}

        self._scheduler = None
        self._use_scheduler = bool(use_scheduler and NativeScheduler is not None)
        if self._use_scheduler:
            try:
                self._scheduler = NativeScheduler(executor_factory=self._create_scheduler_executor)  # type: ignore[arg-type]
            except Exception as exc:  # pragma: no cover - 防御性
                self.logger.warning("NativeScheduler 初始化失败，降级到线程池: %s", exc)
                self._scheduler = None
                self._use_scheduler = False

        self.logger.debug(
            "NativeStartupRuntime 初始化: threadpool_native=%s, scheduler_native=%s, qt_available=%s",
            _THREADPOOL_AVAILABLE,
            _SCHEDULER_NATIVE_CORE if self._scheduler else False,
            self._qt_invoker.available,
        )

    @property
    def default_timeout(self) -> float:
        return self._default_timeout

    def _create_scheduler_executor(self, max_workers: int) -> Any:
        executor = NativeThreadPool(max_workers=max(1, max_workers))
        self._managed_executors.append(executor)
        return executor

    def _ensure_category_registered(self, category: str) -> None:
        if not self._scheduler or category in self._registered_categories:
            return

        config = self._category_config.get(category, {})
        queue_capacity = int(config.get("queue_capacity", 128))
        max_workers = int(config.get("max_workers", self._pool_max_workers))
        try:
            self._scheduler.register_category(
                category,
                queue_capacity=max(1, queue_capacity),
                max_workers=max(1, max_workers),
            )
        except Exception as exc:  # pragma: no cover - 防御性
            self.logger.warning("注册调度类别 %s 失败，降级到线程池: %s", category, exc)
            return
        self._registered_categories.add(category)

    def submit_service(
        self,
        service_name: str,
        func: Callable[[], ServiceTaskOutcome],
        *,
        category: str = "default",
        critical: bool = False,
    ) -> NativeStartupFuture:
        """提交服务初始化任务."""

        if self._service_tracker:
            signal = self._service_tracker.register(service_name, category=category, critical=critical)
        else:
            signal = NativeSignal()

        start_ts = time.time()

        def _runner() -> ServiceTaskOutcome:
            self.logger.debug("服务任务启动: %s (category=%s, critical=%s)", service_name, category, critical)
            try:
                outcome = func()
                if not isinstance(outcome, ServiceTaskOutcome):
                    outcome = ServiceTaskOutcome(success=bool(outcome))
            except BaseException as exc:  # noqa: BLE001
                self.logger.exception("服务任务异常: %s", service_name)
                outcome = ServiceTaskOutcome(
                    success=False,
                    message=str(exc),
                    exception=exc,
                )

            finish_ts = time.time()

            if self._service_tracker:
                metadata = {
                    "elapsed_ms": (finish_ts - start_ts) * 1000,
                    **outcome.metadata,
                }
                if outcome.success:
                    self._service_tracker.mark_ready(
                        service_name,
                        metadata=metadata,
                        message=outcome.message or f"{service_name} ready",
                    )
                else:
                    self._service_tracker.mark_failed(
                        service_name,
                        message=outcome.message or f"{service_name} failed",
                        metadata=metadata,
                        exception=outcome.exception,
                    )

            signal.set()
            return outcome

        if self._scheduler:
            self._ensure_category_registered(category)
            future_impl = self._scheduler.submit(category, _runner, (), {})
        else:
            future_impl = self._pool.submit(_runner)

        wrapper = NativeStartupFuture(
            service_name=service_name,
            category=category,
            critical=critical,
            future=future_impl,
            signal=signal,
            started_at=start_ts,
        )
        self._inflight[service_name] = wrapper

        def _on_done(_completed_future: Any) -> None:
            try:
                wrapper.result(timeout=0)
            finally:
                if not wrapper.signal.is_set():
                    wrapper.signal.set()
                wrapper._notify_callbacks()
                self._inflight.pop(service_name, None)
                if wrapper.outcome:
                    self.logger.debug(
                        "服务任务完成: %s (success=%s, elapsed_ms=%.1f)",
                        service_name,
                        wrapper.outcome.success,
                        (wrapper.finished_at - wrapper.started_at) * 1000  # type: ignore[arg-type]
                        if wrapper.finished_at
                        else -1.0,
                    )

        if hasattr(future_impl, "add_done_callback"):
            future_impl.add_done_callback(_on_done)
        else:
            def _wait_for_completion() -> None:
                try:
                    try:
                        future_impl.result()
                    except Exception:
                        pass
                    _on_done(future_impl)
                except Exception:
                    self.logger.exception("等待服务任务完成时发生异常: %s", service_name)

            waiter = threading.Thread(
                target=_wait_for_completion,
                name=f"startup-future-waiter-{service_name}",
                daemon=True,
            )
            waiter.start()
        return wrapper

    def wait_for_all(
        self,
        futures: List[NativeStartupFuture],
        timeout: Optional[float] = None,
    ) -> List[ServiceTaskOutcome]:
        """等待一组任务完成."""

        if not futures:
            return []

        start = time.time()
        outcomes: List[ServiceTaskOutcome] = []
        for item in futures:
            remaining = None
            if timeout is not None:
                elapsed = time.time() - start
                remaining = max(timeout - elapsed, 0.0)
            outcomes.append(item.wait(remaining))
        return outcomes

    def stats(self) -> Dict[str, Any]:
        """执行器运行状态快照."""
        scheduler_stats = None
        if self._scheduler is not None:
            try:
                scheduler_stats = self._scheduler.stats()
            except Exception:
                scheduler_stats = None

        return {
            "threadpool_native": bool(_THREADPOOL_AVAILABLE),
            "scheduler_in_use": bool(self._scheduler),
            "scheduler_stats": scheduler_stats,
            "qt_main_available": self._qt_invoker.available,
            "inflight": {
                name: {
                    "category": future.category,
                    "critical": future.critical,
                    "started_at": future.started_at,
                    "finished_at": future.finished_at,
                    "done": future.outcome is not None,
                }
                for name, future in self._inflight.items()
            },
        }

    def run_on_qt_main(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        """在 Qt 主线程执行回调."""
        return self._qt_invoker.submit(callback, *args, **kwargs)

    def shutdown(self) -> None:
        """关闭执行器."""
        if self._scheduler:
            try:
                self._scheduler.shutdown()
            except Exception:
                self.logger.exception("NativeScheduler shutdown 失败")
        for executor in self._managed_executors:
            shutdown = getattr(executor, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown(wait=False)
                except Exception:
                    self.logger.exception("调度器子执行器 shutdown 失败")
        self._managed_executors.clear()

        if hasattr(self._pool, "shutdown"):
            self._pool.shutdown(wait=False)


